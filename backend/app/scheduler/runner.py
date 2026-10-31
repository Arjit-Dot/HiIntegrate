"""The runner (D-8): the one place that runs an action, saves what it fetched, and records the run.

The scheduler's timer and the API's run route both call this, so the API stays thin and the engine
stays free of the database. Pages are saved as they arrive (on_page), so a failure on page 7 keeps
pages 1 to 6. The first sentence of D-5.1 holds here: a test run is recorded but never counts for health.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy import Engine

from app.engine import RunError, RunResult, run_action, test_action
from app.engine.core import now_iso
from app.engine.inputs import validate_inputs
from app.scheduler.alerts import maybe_alert
from app.secrets import get_secret
from app.storage import repo, session_scope


class InputsInvalid(ValueError):
    def __init__(self, issues: list[dict]):
        super().__init__("the inputs are not valid")
        self.issues = issues


class UnknownAction(LookupError):
    pass


@dataclass
class Started:
    run_pk: int
    run_id: str
    integration: str
    action: str
    mode: str
    trigger: str
    config: dict


def _action_or_fail(config: dict, action: str) -> dict:
    if action not in config["actions"]:
        raise UnknownAction(f"{config['name']} has no action {action!r}. Actions: {', '.join(config['actions'])}")
    return config["actions"][action]


def begin(engine: Engine, integration: str, action: str, trigger: str, inputs: dict | None = None) -> Started:
    """Check the inputs, then record a `running` run. Raises repo.NotFound, UnknownAction, InputsInvalid,
    or repo.Conflict when the action is already running (D-10)."""
    with session_scope(engine) as s:
        cfg = repo.get_integration(s, integration).config
        spec = _action_or_fail(cfg, action)
        if spec["mode"] == "lookup":
            issues = validate_inputs(spec.get("inputs") or {}, inputs)
            if issues:
                raise InputsInvalid(issues)
        run = repo.start_run(s, integration, action, spec["mode"], trigger)
        return Started(run.pk, run.run_id, integration, action, spec["mode"], trigger, cfg)


def execute(engine: Engine, started: Started, inputs: dict | None = None, *, client: httpx.Client | None = None,
            sleep: Callable[[float], None] = time.sleep) -> RunResult:
    """Run the action for a recorded run, saving each page, then finish the run."""
    cfg, action_name = started.config, started.action
    spec = cfg["actions"][action_name]
    target = spec["target_schema"]
    keep_records = spec.get("store", True)
    keep_quarantine = spec.get("on_invalid", "quarantine") == "quarantine"

    def on_page(records: list, quarantine: list, _page: int) -> None:
        with session_scope(engine) as s:
            if keep_records:
                repo.upsert_records(s, target, records)
            if keep_quarantine:
                repo.add_quarantine(s, quarantine)

    result = RunResult(integration=started.integration, action=action_name, mode=started.mode, trigger=started.trigger)
    try:
        with session_scope(engine) as lookup_session:
            state = repo.get_state(lookup_session, started.integration, action_name)
            baseline = repo.get_baseline(lookup_session, started.integration, action_name)
            result = run_action(cfg, action_name, inputs, started.trigger, state=state, client=client, on_page=on_page,
                                sleep=sleep, run_id=started.run_id, secret_lookup=lambda name: get_secret(name, lookup_session), baseline=baseline)
    finally:
        # Even if something unexpected broke, never leave the run stuck as `running`.
        with session_scope(engine) as s:
            run = repo.get_run(s, started.run_id)
            if result.status == "running":
                result.status, result.error = "failed", {"code": "bad_response", "message": "the run stopped unexpectedly"}
                result.finished_at = now_iso()
            repo.finish_run(s, run, result)
            if result.status == "success" and started.mode == "pull":
                repo.set_last_success(s, started.integration, action_name, result.started_at)
                repo.add_to_baseline(s, started.integration, action_name, result.seen_paths)
            if result.status == "success" and started.trigger in repo.COUNTED_TRIGGERS:
                repo.clear_alert_attempt(s, started.integration, action_name)  # the failure streak ended, so the alert resets
    maybe_alert(engine, cfg, action_name, started.trigger, result)
    return result


def run(engine: Engine, integration: str, action: str, trigger: str = "manual", inputs: dict | None = None, *,
        client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep) -> tuple[str, RunResult]:
    """begin + execute, for lookups, the scheduler and the command line."""
    started = begin(engine, integration, action, trigger, inputs)
    return started.run_id, execute(engine, started, inputs, client=client, sleep=sleep)


def test(engine: Engine, integration: str, action: str, inputs: dict | None = None, *, client: httpx.Client | None = None,
         sleep: Callable[[float], None] | None = None) -> dict:
    """B-3: one call, first page only, nothing saved. Recorded as a run with trigger `test`, which health ignores."""
    started = begin(engine, integration, action, "test", inputs)
    result: dict = {"ok": False, "notes": ["the test could not run"]}
    try:
        with session_scope(engine) as lookup_session:
            result = test_action(started.config, action, inputs, client=client, sleep=sleep,
                                 secret_lookup=lambda name: get_secret(name, lookup_session))
    finally:
        with session_scope(engine) as s:
            row = repo.get_run(s, started.run_id)
            row.status = "success" if result["ok"] else "failed"
            row.finished_at = now_iso()
            row.pages_fetched = result.get("pages_fetched", 0)
            if not result["ok"]:
                code, _, message = (result["notes"] or ["client_error: the test failed"])[0].partition(": ")
                row.error = {"code": code if code in RunError.CODES else "client_error", "message": message or code}
    return result


test.__test__ = False  # not a pytest test, despite the name
