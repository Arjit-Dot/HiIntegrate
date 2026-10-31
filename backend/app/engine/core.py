"""Fetch, extract and test (D-6 test route, D-8 handoffs). Pagination and full runs come in Phase 2."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import jmespath

from app.engine.errors import RunError
from app.engine.http import Policy, send
from app.engine.mapping import FIELDS, map_record
from app.engine.placeholders import PlaceholderError
from app.engine.request import build_request
from app.secrets import SecretHostMismatch, SecretNotFound, check_host


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_records(cfg: dict, action_name: str, body: Any) -> list:
    """Apply error_when (D-2.15), then records_path. A lookup's single record comes back as a list of one."""
    action = cfg["actions"][action_name]
    rule = action.get("error_when")
    if rule and jmespath.search(rule["path"], body) == rule["equals"]:
        message = jmespath.search(rule["message_path"], body) if rule.get("message_path") else None
        raise RunError("api_error", f"the service reported an error: {message or 'no message'}")
    path = action.get("records_path", "@")
    found = body if path == "@" else jmespath.search(path, body)
    if isinstance(found, list):
        return found
    if isinstance(found, dict):
        return [found]
    raise RunError("bad_response", f"unexpected response shape: no records at {path!r}")


def fetch_page(client: httpx.Client, cfg: dict, action_name: str, *, inputs=None, state=None, now=None, url=None,
               sleep: Callable[[float], None] | None = None) -> tuple[Any, httpx.Response, int, int]:
    """One page: build, check the secret's host, send with retries. Returns (body, response, retries, latency_ms)."""
    try:
        prepared = build_request(cfg, action_name, inputs=inputs, state=state, now=now, url=url)
    except PlaceholderError as exc:
        raise RunError("client_error", str(exc)) from None
    except SecretNotFound as exc:
        raise RunError("auth_failed", str(exc)) from None
    if prepared.secret is not None:
        try:
            check_host(prepared.secret, prepared.host)
        except SecretHostMismatch as exc:
            raise RunError("secret_host_mismatch", str(exc)) from None
    policy = Policy.from_config(cfg, cfg["actions"][action_name])
    sent = send(client, prepared.request, policy, **({"sleep": sleep} if sleep else {}))
    try:
        body = sent.response.json()
    except ValueError:
        raise RunError("bad_response", "the response is not JSON", status=sent.response.status_code, retries=sent.retries) from None
    return body, sent.response, sent.retries, sent.latency_ms


def _missing_fields(action: dict, raw: Any) -> list[str]:
    missing = []
    for f in FIELDS[action["target_schema"]]:
        entry = action["map"].get(f)
        if entry is None:
            continue
        path = entry if isinstance(entry, str) else entry.get("path")
        if path and jmespath.search(path, raw) in (None, ""):
            missing.append(f)
    return missing


def test_action(cfg: dict, action_name: str, inputs: dict | None = None, *, client: httpx.Client | None = None,
                sleep: Callable[[float], None] | None = None, now: datetime | None = None) -> dict:
    """The D-8 handoff behind POST /integrations/{id}/test (B-3): first page only, nothing saved."""
    action = cfg["actions"][action_name]
    own = client is None
    client = client or httpx.Client(timeout=Policy.from_config(cfg, action).timeout_seconds, follow_redirects=False)
    result = {"ok": False, "status_code": None, "latency_ms": None, "pages_fetched": 0, "raw_sample": None,
              "mapped_sample": None, "missing_paths": [], "notes": []}
    try:
        body, response, retries, latency = fetch_page(client, cfg, action_name, inputs=inputs, now=now, sleep=sleep)
        result.update(status_code=response.status_code, latency_ms=latency, pages_fetched=1)
        records = extract_records(cfg, action_name, body)
        if retries:
            result["notes"].append(f"Succeeded after {retries} retr{'y' if retries == 1 else 'ies'}.")
        if not records:
            result["notes"].append("The first page had no records.")
        else:
            raw = records[0]
            mapped = map_record(cfg, action_name, raw, run_id="test", fetched_at=now_iso(now))
            result.update(raw_sample=raw, mapped_sample=mapped.get("record"), missing_paths=_missing_fields(action, raw))
            if "quarantine" in mapped:
                q = mapped["quarantine"]
                result["notes"].append(f"The first record would be quarantined: {q['reason']} ({q['field']}).")
        result["notes"].append("Only the first page was fetched. Nothing was saved.")
        result["ok"] = True
    except RunError as exc:
        result["status_code"] = exc.status
        result["notes"].append(f"{exc.code}: {exc.message}")
    finally:
        if own:
            client.close()
    return result


test_action.__test__ = False  # not a pytest test, despite the name
