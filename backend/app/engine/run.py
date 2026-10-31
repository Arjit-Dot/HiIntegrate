"""A full run of one action: every page, saved page by page (D-2.8, D-5.1, D-8).

Handoff (D-8):  run_action(config, action, inputs, trigger, ...) -> RunResult

The engine has no database. `on_page(records, quarantine, page_number)` is called after each page,
so the caller (the runner) saves it at once: if page 7 fails, pages 1 to 6 are already stored.

Paging stops when (schema/README.md):
  next_link    there is no next link (Link header rel="next", or the body path), or a page has no records.
               The empty-page rule matters for polling APIs such as the Okta System Log, which return a next
               link on EVERY page, even after the last record.
  offset       a page is empty, or the offset reaches total_path
  page_number  a page is empty (stop_when_empty, the default)
  cursor       there is no next cursor
  any style    max_pages (default 100) is reached; this is noted, not a failure
Every request, including a next-page link, goes through the secret's host check (D-7.6).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx
import jmespath

from app.engine.core import extract_records, fetch_page, now_iso
from app.engine.errors import RunError
from app.engine.mapping import map_records

OnPage = Callable[[list, list, int], None]
_last_request: dict[str, float] = {}  # per process (D-10): last request time per integration, for min_interval_ms


@dataclass
class RunResult:
    integration: str
    action: str
    mode: str
    trigger: str
    status: str = "running"  # running, success, failed
    started_at: str = ""
    finished_at: str | None = None
    duration_ms: int | None = None
    pages_fetched: int = 0
    records_pulled: int = 0
    records_valid: int = 0
    records_invalid: int = 0
    retries: int = 0
    error: dict | None = None
    notes: list[str] = field(default_factory=list)
    record: dict | None = None  # a lookup's mapped record
    quarantined: dict | None = None  # a lookup's quarantine entry, if its record was rejected


def _throttle(cfg: dict, action: dict, sleep: Callable[[float], None]) -> None:
    rate = {**((cfg.get("defaults") or {}).get("rate_limit") or {}), **(action.get("rate_limit") or {})}
    gap = (rate.get("min_interval_ms") or 0) / 1000
    key = cfg["name"]
    if gap and key in _last_request:
        wait = gap - (time.monotonic() - _last_request[key])
        if wait > 0:
            sleep(wait)
    _last_request[key] = time.monotonic()


def run_action(cfg: dict, action_name: str, inputs: dict | None = None, trigger: str = "manual", *,
               state: dict | None = None, client: httpx.Client | None = None, on_page: OnPage | None = None,
               sleep: Callable[[float], None] = time.sleep, now: datetime | None = None, run_id: str = "run",
               secret_lookup=None) -> RunResult:
    action = cfg["actions"][action_name]
    started = time.monotonic()
    started_at = now or datetime.now(UTC)
    result = RunResult(integration=cfg["name"], action=action_name, mode=action["mode"], trigger=trigger, started_at=now_iso(started_at))
    pg = action.get("pagination") if action["mode"] == "pull" else None
    max_pages = (pg or {}).get("max_pages", 100)
    own = client is None
    client = client or httpx.Client(timeout=(cfg.get("defaults") or {}).get("timeout_seconds", 30), follow_redirects=False)

    url: str | None = None
    extra: dict = {}
    if pg and pg["type"] == "offset":
        extra = {pg["offset_param"]: 0, pg["limit_param"]: pg["limit"]}
    elif pg and pg["type"] == "page_number":
        extra = {pg["param"]: pg["start"]}

    try:
        while True:
            _throttle(cfg, action, sleep)
            body, response, retries, _ = fetch_page(client, cfg, action_name, inputs=inputs, state=state, now=now, url=url,
                                                    extra_params=extra if url is None else None, secret_lookup=secret_lookup, sleep=sleep)
            result.retries += retries
            result.pages_fetched += 1
            raws = extract_records(cfg, action_name, body)
            records, quarantine = map_records(cfg, action_name, raws, run_id=run_id, fetched_at=now_iso(now))
            result.records_pulled += len(raws)
            result.records_valid += len(records)
            result.records_invalid += len(quarantine)
            if action["mode"] == "lookup":
                result.record = records[0] if records else None
                result.quarantined = quarantine[0] if quarantine else None
            if on_page and (records or quarantine):
                on_page(records, quarantine, result.pages_fetched)

            if not pg:
                break
            if result.pages_fetched >= max_pages:
                result.notes.append(f"Stopped at max_pages ({max_pages}).")
                break
            kind = pg["type"]
            if kind == "next_link":
                if not raws:
                    break
                link = response.links.get("next", {}).get("url") if pg["source"] == "header" else jmespath.search(pg["path"], body)
                if not link:
                    break
                url = urljoin(str(response.request.url), link)
            elif kind == "offset":
                if not raws:
                    break
                total = jmespath.search(pg["total_path"], body) if pg.get("total_path") else None
                extra[pg["offset_param"]] += pg["limit"]
                if isinstance(total, int) and extra[pg["offset_param"]] >= total:
                    break
            elif kind == "page_number":
                if not raws and pg.get("stop_when_empty", True):
                    break
                extra[pg["param"]] += 1
            elif kind == "cursor":
                cursor = jmespath.search(pg["next_cursor_path"], body)
                if cursor in (None, ""):
                    break
                extra = {pg["cursor_param"]: cursor}
        result.status = "success"
    except RunError as exc:
        result.status = "failed"
        result.retries += exc.retries
        result.error = exc.as_dict()
        if result.pages_fetched:
            result.notes.append(f"Failed after {result.pages_fetched} page(s); those pages stay saved.")
    finally:
        if own:
            client.close()
        result.finished_at = now_iso()
        result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


__all__ = ["RunResult", "run_action"]
