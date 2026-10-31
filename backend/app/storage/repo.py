"""The only code that touches the database (D-8). Shapes returned match schema/result.schema.json.

D-18: every function that reads or writes a person's data takes `account` (the signed-in username) and only ever
sees rows of that account. There is no way to ask for another account's rows."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.storage.models import (
    RECORD_TABLES,
    Account,
    ActionState,
    AlertAttempt,
    Audit,
    AuthSession,
    Integration,
    PathBaseline,
    Quarantine,
    Run,
    User,
)

RECORD_FIELDS = {
    "user": ["id", "name", "email", "status", "last_login"],
    "device": ["id", "hostname", "ip", "os", "owner", "last_seen"],
    "alert": ["id", "type", "severity", "timestamp", "description"],
}
COUNTED_TRIGGERS = ("schedule", "manual")  # D-5.2: test runs never count towards health


class NotFound(LookupError):
    pass


class Conflict(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- integrations (D-15)

def integration_dict(row: Integration) -> dict:
    return {"name": row.name, "config": row.config, "revision": row.revision, "enabled": row.enabled,
            "created_at": row.created_at, "updated_at": row.updated_at}


def create_integration(s: Session, account: str, config: dict) -> Integration:
    if s.get(Integration, (account, config["name"])):
        raise Conflict(f"an integration named {config['name']} already exists", {"name": config["name"]})
    stamp = now_iso()
    row = Integration(account=account, name=config["name"], config=config, revision=1, enabled=config.get("enabled", True), created_at=stamp, updated_at=stamp)
    s.add(row)
    s.flush()
    return row


def get_integration(s: Session, account: str, name: str) -> Integration:
    row = s.get(Integration, (account, name))
    if row is None:
        raise NotFound(f"no integration named {name}")
    return row


def list_integrations(s: Session, account: str | None = None) -> list[Integration]:
    """One account's integrations. `account=None` is for the worker only: every account's, so each can be scheduled."""
    q = select(Integration).order_by(Integration.account, Integration.name)
    if account is not None:
        q = q.where(Integration.account == account)
    return list(s.scalars(q))


def replace_integration(s: Session, account: str, name: str, config: dict) -> Integration:
    """D-15: update the existing row in place. The name cannot change, because records are keyed by it."""
    row = get_integration(s, account, name)
    if config.get("name") != name:
        raise Conflict(f"the config's name must stay {name}; records are keyed by it", {"name": config.get("name")})
    row.config = config
    row.enabled = config.get("enabled", True)
    row.revision += 1
    row.updated_at = now_iso()
    s.flush()
    return row


def set_enabled(s: Session, account: str, name: str, enabled: bool) -> Integration:
    row = get_integration(s, account, name)
    return replace_integration(s, account, name, {**row.config, "enabled": enabled})


def delete_integration(s: Session, account: str, name: str) -> None:
    s.delete(get_integration(s, account, name))
    for model in (ActionState, PathBaseline, AlertAttempt):  # its history goes with it, so a new integration of the same name starts fresh
        for row in s.scalars(select(model).where(model.account == account, model.integration == name)):
            s.delete(row)
    s.flush()


# ---------------------------------------------------------------- records (D-3, upsert on (source, id))

def upsert_records(s: Session, account: str, target: str, records: list[dict]) -> int:
    if not records:
        return 0
    table = RECORD_TABLES[target].__table__
    cols = RECORD_FIELDS[target] + ["source", "fetched_at", "raw"]
    rows = [{**{c: r.get(c) for c in cols}, "account": account} for r in records]
    dialect = s.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    stmt = insert(table).values(rows)
    update = {c: stmt.excluded[c] for c in cols if c not in ("source", "id")}
    s.execute(stmt.on_conflict_do_update(index_elements=["account", "source", "id"], set_=update))
    return len(rows)


def record_dict(target: str, row: Any, *, with_raw: bool = False) -> dict:
    out = {f: getattr(row, f) for f in RECORD_FIELDS[target]}
    out["source"], out["fetched_at"] = row.source, row.fetched_at
    if with_raw and row.raw is not None:
        out["raw"] = row.raw
    return out


def get_results(s: Session, account: str, filter: dict | None = None) -> list[dict]:
    """The D-8 handoff for the AI summary: records of one type, newest first.
    Pass {"unified": True} for people merged across services (D-16)."""
    f = dict(filter or {})
    if f.pop("unified", False):
        items, _ = list_unified_users(s, account, **{k: v for k, v in f.items() if k in ("source", "limit", "offset")})
        return items
    items, _ = list_results(s, account, **f)
    return items


def list_results(s: Session, account: str, target: str = "user", source: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    model = RECORD_TABLES[target]
    q = select(model).where(model.account == account)
    if source:
        q = q.where(model.source == source)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.scalars(q.order_by(model.fetched_at.desc(), model.source, model.id).limit(limit).offset(offset))
    return [record_dict(target, r) for r in rows], total


# ---------------------------------------------------------------- unified users (D-16, built per request, nothing stored)

def _person_key():
    """The lowercased email, or source:id when a user has no email (such a user is never merged)."""
    return case(((User.email.is_not(None)) & (User.email != ""), func.lower(User.email)), else_=User.source + ":" + User.id)


def list_unified_users(s: Session, account: str, source: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    key = _person_key()
    groups = select(key.label("k"), func.max(User.fetched_at).label("newest")).where(User.account == account).group_by(key)
    if source:  # keep people who appear in this service, but still list all of their services
        groups = groups.where(key.in_(select(key).where(User.account == account, User.source == source)))
    total = s.scalar(select(func.count()).select_from(groups.subquery()))
    page_keys = [r.k for r in s.execute(groups.order_by(func.max(User.fetched_at).desc(), key).limit(limit).offset(offset))]
    if not page_keys:
        return [], total
    rows = list(s.scalars(select(User).where(User.account == account, key.in_(page_keys)).order_by(User.source, User.id)))
    by_key: dict[str, list] = {k: [] for k in page_keys}
    for r in rows:
        by_key[(r.email.lower() if r.email else f"{r.source}:{r.id}")].append(r)
    people = []
    for k in page_keys:
        members = by_key[k]
        logins = [m.last_login for m in members if m.last_login]
        people.append({
            "key": k,
            "email": k if "@" in k and members[0].email else None,
            "name": next((m.name for m in members if m.name), None),
            "last_login": max(logins) if logins else None,
            "sources": [{"source": m.source, "id": m.id, "status": m.status, "last_login": m.last_login, "fetched_at": m.fetched_at} for m in members],
        })
    return people, total


# ---------------------------------------------------------------- quarantine (D-4)

QUARANTINE_FIELDS = ["source", "action", "target_schema", "run_id", "raw", "reason", "field", "created_at"]


def add_quarantine(s: Session, account: str, entries: list[dict]) -> int:
    s.add_all(Quarantine(account=account, **{k: e[k] for k in QUARANTINE_FIELDS}) for e in entries)
    return len(entries)


def _quarantine_query(account, source=None, action=None, run_id=None, target_schema=None, reason=None):
    q = select(Quarantine).where(Quarantine.account == account)
    for column, value in ((Quarantine.source, source), (Quarantine.action, action), (Quarantine.run_id, run_id),
                          (Quarantine.target_schema, target_schema), (Quarantine.reason, reason)):
        if value:
            q = q.where(column == value)
    return q


def quarantine_dict(row: Quarantine) -> dict:
    return {k: getattr(row, k) for k in QUARANTINE_FIELDS}


def list_quarantine(s: Session, account: str, limit: int = 50, offset: int = 0, **filters) -> tuple[list[dict], int]:
    q = _quarantine_query(account, **filters)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    rows = s.scalars(q.order_by(Quarantine.pk.desc()).limit(limit).offset(offset))
    return [quarantine_dict(r) for r in rows], total


def export_quarantine(s: Session, account: str, **filters) -> list[dict]:
    return [quarantine_dict(r) for r in s.scalars(_quarantine_query(account, **filters).order_by(Quarantine.pk))]


# ---------------------------------------------------------------- runs (D-5.1)

RUN_FIELDS = ["integration", "action", "mode", "trigger", "status", "started_at", "finished_at", "duration_ms",
              "pages_fetched", "records_pulled", "records_valid", "records_invalid", "retries", "error"]


def run_dict(row: Run) -> dict:
    return {"run_id": row.run_id, **{k: getattr(row, k) for k in RUN_FIELDS}}


def start_run(s: Session, account: str, integration: str, action: str, mode: str, trigger: str) -> Run:
    """Raises Conflict if the action is already running (the unique index, D-10)."""
    row = Run(account=account, integration=integration, action=action, mode=mode, trigger=trigger, status="running", started_at=now_iso())
    try:
        with s.begin_nested():  # a savepoint, so a clash undoes only this insert
            s.add(row)
    except IntegrityError:
        running = s.scalar(select(Run).where(Run.account == account, Run.integration == integration, Run.action == action, Run.status == "running"))
        raise Conflict(f"{action} is already running", {"run_id": running.run_id if running else None}) from None
    return row


def finish_run(s: Session, row: Run, result: Any) -> Run:
    for k in ("status", "finished_at", "duration_ms", "pages_fetched", "records_pulled", "records_valid", "records_invalid", "retries", "error"):
        setattr(row, k, getattr(result, k))
    s.flush()
    return row


def get_run(s: Session, account: str, run_id: str) -> Run:
    try:
        pk = int(run_id.removeprefix("run-"))
    except ValueError:
        raise NotFound(f"no run {run_id}") from None
    row = s.get(Run, pk)
    if row is None or row.account != account:  # another account's run looks exactly like one that does not exist
        raise NotFound(f"no run {run_id}")
    return row


def list_runs(s: Session, account: str, integration: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    q = select(Run).where(Run.account == account)
    if integration:
        q = q.where(Run.integration == integration)
    if status:
        q = q.where(Run.status == status)
    total = s.scalar(select(func.count()).select_from(q.subquery()))
    return [run_dict(r) for r in s.scalars(q.order_by(Run.pk.desc()).limit(limit).offset(offset))], total


# ---------------------------------------------------------------- health (D-5.2)

def health(s: Session, integration: Integration) -> dict:
    """D-5.2 (revised): judged by the latest finished run of EACH action, so a failing action cannot hide
    behind a healthy one. Only schedule and manual runs count, and only actions still in the config."""
    actions = list(integration.config.get("actions") or {})
    runs = list(s.scalars(select(Run).where(
        Run.account == integration.account, Run.integration == integration.name, Run.trigger.in_(COUNTED_TRIGGERS), Run.status != "running", Run.action.in_(actions),
    ).order_by(Run.pk.desc()).limit(1000)))
    by_action: dict[str, list[Run]] = {}
    for r in runs:  # newest first
        by_action.setdefault(r.action, []).append(r)
    latest = [rs[0] for rs in by_action.values()]
    failing = [r for r in latest if r.status == "failed"]
    drifted = [r for r in latest if r.status == "success" and r.error]  # a success that names a vanished path

    def trailing_failures(rs: list[Run]) -> int:
        n = 0
        for r in rs:
            if r.status != "failed":
                break
            n += 1
        return n

    newest = runs[0] if runs else None
    if not integration.enabled:
        status = "disabled"
    elif not runs:
        status = "never_run"
    elif failing:
        status = "failing"
    elif drifted or any(r.records_invalid for r in latest):
        status = "degraded"
    else:
        status = "healthy"
    worst = max(failing, key=lambda r: r.pk) if failing else None
    return {"status": status, "last_run_at": newest.finished_at if newest else None, "records_pulled": newest.records_pulled if newest else 0,
            "last_error": worst.error if worst else (max(drifted, key=lambda r: r.pk).error if drifted else None),
            "consecutive_failures": max((trailing_failures(rs) for rs in by_action.values()), default=0)}


def has_run(s: Session, account: str, integration: str, action: str) -> bool:
    return s.scalar(select(Run.pk).where(Run.account == account, Run.integration == integration, Run.action == action).limit(1)) is not None


def failure_streak(s: Session, account: str, integration: str, action: str) -> int:
    """Failed schedule/manual runs of this action in a row, newest first (D-5.3). A success ends the streak."""
    n = 0
    for status in s.scalars(select(Run.status).where(
        Run.account == account, Run.integration == integration, Run.action == action, Run.trigger.in_(COUNTED_TRIGGERS), Run.status != "running",
    ).order_by(Run.pk.desc()).limit(1000)):
        if status != "failed":
            break
        n += 1
    return n


# ---------------------------------------------------------------- engine state ({{state.x}})

def get_state(s: Session, account: str, integration: str, action: str) -> dict:
    row = s.get(ActionState, (account, integration, action))
    return {"last_success_at": row.last_success_at} if row and row.last_success_at else {}


def set_last_success(s: Session, account: str, integration: str, action: str, when: str) -> None:
    row = s.get(ActionState, (account, integration, action)) or ActionState(account=account, integration=integration, action=action)
    row.last_success_at = when
    s.add(row)


# ---------------------------------------------------------------- schema drift baseline

def get_baseline(s: Session, account: str, integration: str, action: str) -> set[str]:
    row = s.get(PathBaseline, (account, integration, action))
    return set(row.paths) if row else set()


def add_to_baseline(s: Session, account: str, integration: str, action: str, paths: set[str]) -> None:
    """Paths are only ever added: one that vanished stays remembered, so the drift stays visible until it returns
    or the config stops mapping it."""
    row = s.get(PathBaseline, (account, integration, action)) or PathBaseline(account=account, integration=integration, action=action, paths=[])
    row.paths = sorted(set(row.paths) | paths)
    s.add(row)


# ---------------------------------------------------------------- alert state (D-5.3)

def record_alert_attempt(s: Session, account: str, integration: str, action: str, outcome: str, failures: int, message: str | None = None) -> None:
    row = s.get(AlertAttempt, (account, integration, action)) or AlertAttempt(account=account, integration=integration, action=action)
    row.at, row.outcome, row.failures, row.message = now_iso(), outcome, failures, (message or None) and message[:240]
    s.add(row)


def clear_alert_attempt(s: Session, account: str, integration: str, action: str) -> None:
    row = s.get(AlertAttempt, (account, integration, action))
    if row is not None:
        s.delete(row)


def alert_state(s: Session, integration: Integration) -> dict | None:
    """What the dashboard shows about alerts: the config's rule, and the last attempt of the current failure streak."""
    rule = integration.config.get("alerts")
    if not rule:
        return None
    actions = list(integration.config.get("actions") or {})
    rows = list(s.scalars(select(AlertAttempt).where(AlertAttempt.account == integration.account, AlertAttempt.integration == integration.name, AlertAttempt.action.in_(actions)).order_by(AlertAttempt.at.desc())))
    last = rows[0] if rows else None
    return {"after_failures": rule.get("after_failures", 3), "to": rule.get("to", []),
            "last_attempt": None if last is None else {"action": last.action, "at": last.at, "outcome": last.outcome, "failures": last.failures, "message": last.message}}


# ---------------------------------------------------------------- accounts and sign-ins (D-18)

def create_account(s: Session, username: str, password_hash: str) -> Account:
    if s.get(Account, username):
        raise Conflict("that username is taken", {"username": username})
    row = Account(username=username, password_hash=password_hash, created_at=now_iso())
    s.add(row)
    s.flush()
    return row


def get_account(s: Session, username: str) -> Account | None:
    return s.get(Account, username)


def add_auth_session(s: Session, token_hash: str, account: str, expires_at: str) -> None:
    s.add(AuthSession(token_hash=token_hash, account=account, created_at=now_iso(), expires_at=expires_at))
    s.flush()


def get_auth_session(s: Session, token_hash: str) -> AuthSession | None:
    """The sign-in for this token hash, unless it has expired (an expired one is removed)."""
    row = s.get(AuthSession, token_hash)
    if row is not None and row.expires_at <= now_iso():
        s.delete(row)
        s.flush()
        return None
    return row


def delete_auth_session(s: Session, token_hash: str) -> None:
    row = s.get(AuthSession, token_hash)
    if row is not None:
        s.delete(row)
        s.flush()


# --- audit log (S-7) ---------------------------------------------------------------------------------------------

def add_audit(s: Session, account: str, event: str, target: str | None = None, revision: int | None = None,
              request_id: str | None = None) -> None:
    """Record one change. Never pass a value: only names, a revision and the request id."""
    s.add(Audit(account=account, at=now_iso(), event=event, target=target, revision=revision, request_id=request_id))


def list_audit(s: Session, account: str, limit: int = 50, offset: int = 0, event: str | None = None,
               target: str | None = None) -> tuple[list[dict], int]:
    q = select(Audit).where(Audit.account == account)
    if event:
        q = q.where(Audit.event == event)
    if target:
        q = q.where(Audit.target == target)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = s.scalars(q.order_by(Audit.id.desc()).limit(limit).offset(offset)).all()
    return [{"id": r.id, "at": r.at, "event": r.event, "target": r.target, "revision": r.revision, "request_id": r.request_id}
            for r in rows], total


# --- retention (S-10) --------------------------------------------------------------------------------------------

def cutoff_iso(days: int, now: datetime | None = None) -> str:
    from datetime import timedelta

    return ((now or datetime.now(UTC)) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def purge_runs(s: Session, before: str, account: str | None = None) -> int:
    """Delete finished runs that started before `before`. Never a running run, and never the newest finished run of an
    action (so health keeps its last result). `account=None` is for the worker's retention job and covers every account."""
    newest = select(func.max(Run.pk)).where(Run.status != "running").group_by(Run.account, Run.integration, Run.action)
    q = delete(Run).where(Run.started_at < before, Run.status != "running", Run.pk.not_in(newest))
    if account is not None:
        q = q.where(Run.account == account)
    return s.execute(q).rowcount or 0


def purge_quarantine(s: Session, before: str, account: str | None = None) -> int:
    q = delete(Quarantine).where(Quarantine.created_at < before)
    if account is not None:
        q = q.where(Quarantine.account == account)
    return s.execute(q).rowcount or 0


def purge_audit(s: Session, before: str, account: str | None = None) -> int:
    q = delete(Audit).where(Audit.at < before)
    if account is not None:
        q = q.where(Audit.account == account)
    return s.execute(q).rowcount or 0
