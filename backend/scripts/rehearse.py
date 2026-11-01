"""Failure rehearsal: the four organizer tests, run in order against the mock service (D-9).

  1. wrong key        the service answers 401: the run fails with auth_failed and is NOT retried
  2. network off      the connection drops: the run fails with connection_error after retrying
  3. 429              the service says "slow down": the run waits for Retry-After and then succeeds
  4. missing field    some records lack `id`: the run succeeds, those records go to Quarantine

Needs the stack running (docker compose up). Exit code 0 only if all four pass.

  docker compose exec backend python scripts/rehearse.py     # the normal way: inside Compose, where the mock is reachable
  MOCK_ADMIN=http://localhost:8001 python backend/scripts/rehearse.py   # from the host; needs the debug file below
  docker compose -f docker-compose.yml -f docker-compose.debug.yml up  # publishes the API and the mock on 127.0.0.1 only

The mock is not published by the normal Compose file (D-17 S-1), so the first form is the one to use.

Settings (environment): API_BASE (default http://localhost:8000/api/v1), MOCK_BASE_URL (the mock as the
BACKEND reaches it, default http://mock-api:8001), MOCK_ADMIN (the mock as THIS script reaches it, default
the same as MOCK_BASE_URL). The mock's token is a test value, pinned to the host `mock-api` by Compose.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

API = os.environ.get("API_BASE", "http://localhost:8000/api/v1").rstrip("/")
MOCK_BASE_URL = os.environ.get("MOCK_BASE_URL", "http://mock-api:8001").rstrip("/")
MOCK_ADMIN = os.environ.get("MOCK_ADMIN", MOCK_BASE_URL).rstrip("/")
NAME = "mock-service"
CONFIG = Path(__file__).resolve().parents[1] / "tests" / "mock_api" / "mock-service.yaml"


def call(method: str, url: str, body=None, timeout: int = 120):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        return e.code, (json.loads(text) if text else None)


def api(method: str, path: str, body=None):
    return call(method, API + path, body)


def setup() -> None:
    """Make sure the mock integration exists and points at the mock, and reset the mock's counters."""
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["base_url"] = MOCK_BASE_URL
    status, _ = api("GET", f"/integrations/{NAME}")
    status, reply = api("POST", "/integrations", cfg) if status == 404 else api("PUT", f"/integrations/{NAME}", cfg)
    if status not in (200, 201):
        sys.exit(f"Could not set up {NAME}: HTTP {status} {reply}")
    call("POST", MOCK_ADMIN + "/reset")   # the flaky and rate-limit endpoints count calls; start from zero


def run(action: str) -> dict:
    status, reply = api("POST", f"/integrations/{NAME}/actions/{action}/run", {})
    if status != 202:
        raise RuntimeError(f"run of {action} answered {status}: {reply}")
    for _ in range(120):
        _, r = api("GET", f"/runs/{reply['run_id']}")
        if r["status"] != "running":
            return r
        time.sleep(1)
    raise RuntimeError(f"run {reply['run_id']} never finished")


def wrong_key():
    r = run("wrong_key")
    code = r["error"] and r["error"]["code"]
    return (r["status"] == "failed" and code == "auth_failed" and r["retries"] == 0,
            f"status={r['status']} error={code} retries={r['retries']} (want failed, auth_failed, 0 retries)")


def network_off():
    r = run("network_drop")
    code = r["error"] and r["error"]["code"]
    return (r["status"] == "failed" and code in ("connection_error", "timeout") and r["retries"] >= 1,
            f"status={r['status']} error={code} retries={r['retries']} (want failed, connection_error, 1+ retries)")


def rate_limited():
    t = time.time()
    r = run("rate_limited")
    waited = time.time() - t
    return (r["status"] == "success" and r["records_valid"] > 0 and waited >= 0.9,
            f"status={r['status']} records={r['records_valid']} waited={waited:.1f}s (want success after waiting for Retry-After: 1 s)")


def missing_field():
    r = run("dirty_users")
    _, q = api("GET", f"/quarantine?run_id={r['run_id']}")
    reasons = sorted({i["reason"] for i in q["items"]})
    detail = (f"status={r['status']} valid={r['records_valid']} invalid={r['records_invalid']} "
              f"in quarantine={q['total']} reasons={reasons} (want the run to carry on, and every invalid record quarantined)")
    return r["status"] == "success" and r["records_invalid"] > 0 and q["total"] == r["records_invalid"] and r["records_valid"] > 0, detail


TESTS = [("1. wrong key", wrong_key), ("2. network off", network_off), ("3. 429 rate limit", rate_limited), ("4. missing field", missing_field)]


def main() -> int:
    status, _ = api("GET", "/health")
    if status != 200:
        sys.exit(f"The API at {API} is not answering. Start the stack first: docker compose up")
    setup()
    failed = 0
    for title, test in TESTS:
        try:
            ok, detail = test()
        except Exception as e:  # noqa: BLE001  a test that cannot run counts as a failure
            ok, detail = False, f"could not run: {e}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {title:20} {detail}")
    print(f"\n{len(TESTS) - failed} of {len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
