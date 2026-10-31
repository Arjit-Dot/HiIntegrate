"""Fetch, extract and test (D-6 test route, D-8 handoffs). Pagination and full runs come in Phase 2."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
import jmespath

from app.engine import lint
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
               extra_params: dict | None = None, secret_lookup=None, sleep: Callable[[float], None] | None = None) -> tuple[Any, httpx.Response, int, int]:
    """One page: build, check the secret's host, send with retries. Returns (body, response, retries, latency_ms)."""
    try:
        prepared = build_request(cfg, action_name, inputs=inputs, state=state, now=now, url=url, extra_params=extra_params,
                                 secret_lookup=secret_lookup)
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


def _paging_params(pg: dict, step: int) -> dict | None:
    """The paging parameters for page `step` (0 is the first), exactly as a full run would send them."""
    if pg["type"] == "offset":
        return {pg["offset_param"]: pg["limit"] * step, pg["limit_param"]: pg["limit"]}
    if pg["type"] == "page_number":
        return {pg["param"]: pg["start"] + step}
    return None


def _check_second_page(client, cfg: dict, action_name: str, body: Any, response: httpx.Response, records: list, *, inputs, now,
                       secret_lookup, sleep) -> tuple[list[str], str]:
    """Fetch page 2 only to see whether the paging settings move forward. Returns (problems, a note for the person)."""
    pg = cfg["actions"][action_name]["pagination"]
    kind, url, extra = pg["type"], None, None
    if kind in ("offset", "page_number"):
        extra = _paging_params(pg, 1)
    elif kind == "next_link":
        link = response.links.get("next", {}).get("url") if pg["source"] == "header" else jmespath.search(pg["path"], body)
        if not link:
            return [], "There is no link to a next page, so this response is all of the data."
        url = urljoin(str(response.request.url), link)
    elif kind == "cursor":
        cursor = jmespath.search(pg["next_cursor_path"], body)
        if cursor in (None, ""):
            return [], "There is no next cursor, so this response is all of the data."
        extra = {pg["cursor_param"]: cursor}
    try:
        body2, _, _, _ = fetch_page(client, cfg, action_name, inputs=inputs, now=now, url=url, extra_params=extra if url is None else None,
                                    secret_lookup=secret_lookup, sleep=sleep)
        records2 = extract_records(cfg, action_name, body2)
    except RunError as exc:
        return [], f"The second page could not be fetched ({exc.code}: {exc.message}), so the paging was not checked."
    key = lambda r: json.dumps(r, sort_keys=True, default=str)
    first = {key(r) for r in records}
    if records2 and all(key(r) in first for r in records2):
        return [f"Page 2 returned the same {len(records2)} record(s) as page 1, so the paging parameter does not move forward."], ""
    if not records2 and kind == "offset" and len(records) >= pg["limit"]:
        return [(f"Page 1 was full ({len(records)} records, the page size) but page 2 was empty. If the service has more records than that, "
                 "the paging settings are wrong.")], ""
    if records2:
        return [], f"Page 2 had {len(records2)} different record(s), so the paging moves forward."
    return [], "Page 2 was empty: the data fits on one page."


def test_action(cfg: dict, action_name: str, inputs: dict | None = None, *, client: httpx.Client | None = None,
                sleep: Callable[[float], None] | None = None, now: datetime | None = None, secret_lookup=None,
                probe_paging: bool = False) -> dict:
    """The D-8 handoff behind POST /integrations/{id}/test (B-3): first page only, nothing saved.
    `probe_paging` (used by the AI authoring loop, not by the test route) also fetches page 2, once, to check the paging settings;
    it adds `probe_problems` to the result."""
    action = cfg["actions"][action_name]
    own = client is None
    client = client or httpx.Client(timeout=Policy.from_config(cfg, action).timeout_seconds, follow_redirects=False)
    result = {"ok": False, "status_code": None, "latency_ms": None, "pages_fetched": 0, "raw_sample": None,
              "mapped_sample": None, "missing_paths": [], "notes": []}
    try:
        pg = action.get("pagination") if (probe_paging and action["mode"] == "pull") else None
        body, response, retries, latency = fetch_page(client, cfg, action_name, inputs=inputs, now=now, secret_lookup=secret_lookup, sleep=sleep,
                                                      extra_params=_paging_params(pg, 0) if pg else None)
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
        result["notes"] += [f"Check: {w}" for w in lint.var_warnings(cfg, action_name)]
        result["notes"] += [f"Check: {w}" for w in lint.paging_problems(action)]
        if pg and records:
            problems, note = _check_second_page(client, cfg, action_name, body, response, records, inputs=inputs, now=now,
                                                secret_lookup=secret_lookup, sleep=sleep)
            result["probe_problems"] = problems
            result["notes"] += [f"Check: {p}" for p in problems] + ([note] if note else [])
            result["notes"].append("The first page was tested, and a second page was fetched only to check the paging. Nothing was saved.")
        else:
            result["notes"].append("Only the first page was fetched. Nothing was saved.")
        result["ok"] = True
    except RunError as exc:
        result["status_code"] = exc.status
        result["notes"].append(f"{exc.code}: {exc.message}")
        result["notes"] += [f"Check: {w}" for w in lint.var_warnings(cfg, action_name)]  # a request that went to a made-up address fails too
    finally:
        if own:
            client.close()
    return result


test_action.__test__ = False  # not a pytest test, despite the name
