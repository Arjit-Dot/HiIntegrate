"""Fill a running stack with demo data, through the API (the same calls the dashboard makes).

  .venv/bin/python scripts/seed_demo.py                  # from the host, through the dashboard on 127.0.0.1:5173
  docker compose exec backend python scripts/seed_demo.py   # inside Compose (needs a rebuilt image that has this file)

What it creates (safe to run again: it signs in if an account exists and replaces the integration):
  demo-alice   the demo account with data: the Mock service integration, its test secret (pinned to the mock's host),
          and the results of five runs: users (25), devices, alerts, a pull with bad records (they land in Quarantine)
          and a pull with a wrong key (a failed run, so Run history and health show a failure).
  demo-bob     an account with nothing, to show that accounts do not see each other's data.

The mock is a local test service (D-9), and its token is a public test value. No real service or real key is used.
Settings: API_BASE (default http://localhost:5173/api/v1), MOCK_BASE_URL (the mock as the BACKEND reaches it,
default http://mock-api:8001), DEMO_PASSWORD (default Demo-pass-123).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import yaml

API = os.environ.get("API_BASE", "http://localhost:5173/api/v1").rstrip("/")
MOCK_BASE_URL = os.environ.get("MOCK_BASE_URL", "http://mock-api:8001").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-pass-123")
NAME = "mock-service"
CONFIG = Path(__file__).resolve().parents[1] / "tests" / "mock_api" / "mock-service.yaml"
RUNS = [("users_page_number", "users, 3 pages"), ("devices", "devices"), ("alerts", "alerts"),
        ("dirty_users", "users with bad records (quarantine)"), ("wrong_key", "a wrong key (a failed run)")]


def call(method: str, path: str, body=None, token: str = ""):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", **({"X-Session-Token": token} if token else {})}
    req = urllib.request.Request(API + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        return e.code, (json.loads(text) if text else None)
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach {API}: {e.reason}. Is the stack running? (docker compose up -d)")


def sign_in(username: str) -> str:
    status, reply = call("POST", "/auth/register", {"username": username, "password": PASSWORD})
    if status == 409:
        status, reply = call("POST", "/auth/login", {"username": username, "password": PASSWORD})
        if status != 200:
            sys.exit(f"{username} already exists with a different password (HTTP {status}). Set DEMO_PASSWORD, or use another name.")
    elif status != 201:
        sys.exit(f"Could not create {username}: HTTP {status} {reply}")
    return reply["token"]


def run(token: str, action: str) -> dict:
    status, reply = call("POST", f"/integrations/{NAME}/actions/{action}/run", {}, token)
    if status != 202:
        sys.exit(f"run of {action} answered {status}: {reply}")
    for _ in range(120):
        _, r = call("GET", f"/runs/{reply['run_id']}", token=token)
        if r["status"] != "running":
            return r
        time.sleep(1)
    sys.exit(f"{reply['run_id']} never finished")


def main() -> None:
    alice = sign_in("demo-alice")
    sign_in("demo-bob")
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["base_url"] = MOCK_BASE_URL
    status, reply = call("PUT", "/secrets/mock_token", {"value": "mock-secret-123", "host": urlsplit(MOCK_BASE_URL).hostname}, alice)
    if status != 204:
        sys.exit(f"Could not save the test secret: HTTP {status} {reply}")
    exists, _ = call("GET", f"/integrations/{NAME}", token=alice)
    status, reply = call("PUT", f"/integrations/{NAME}", cfg, alice) if exists == 200 else call("POST", "/integrations", cfg, alice)
    if status not in (200, 201):
        sys.exit(f"Could not save the integration: HTTP {status} {reply}")
    print(f"demo-alice: secret mock_token (pinned to {urlsplit(MOCK_BASE_URL).hostname}) and integration {NAME} are set\n")
    for action, what in RUNS:
        r = run(alice, action)
        note = f"  error: {r['error']['code']}" if r.get("error") else ""
        print(f"  {action:<18} {r['status']:<8} valid={r['records_valid']:<3} invalid={r['records_invalid']:<2}  ({what}){note}")
    print(f"\nSign in at the dashboard:\n  demo-alice / {PASSWORD}   (has the data above)\n  demo-bob   / {PASSWORD}   (has nothing, by design)")


if __name__ == "__main__":
    main()
