"""Local mock API for failure tests and fixtures (D-9). Not a data source for the demo count.

Run:  cd backend && .venv/bin/uvicorn tests.mock_api.app:app --port 8001

Every endpoint needs `Authorization: SSWS <MOCK_TOKEN>` (default `mock-secret-123`), except
/health and /wrong-key (which always answers 401, like a revoked key).
"""

import asyncio
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

MOCK_TOKEN = os.environ.get("MOCK_TOKEN", "mock-secret-123")
app = FastAPI(title="Mock API")
_calls: dict[str, int] = defaultdict(int)


def _user(i: int) -> dict:
    return {
        "id": f"u-{i}",
        "name": f"User {i}",
        "email": f"User{i}@Example.com",
        "status": "active" if i % 4 else "disabled",
        "last_login": 1767225600 + i * 3600,
    }


USERS = [_user(i) for i in range(1, 26)]  # 25 users, so every paging style needs 3 pages of 10
DEVICES = [
    {"id": "d-1", "hostname": "ada-laptop", "ip_address": "10.0.0.7", "os": "macOS 15", "owner": "User 1", "last_seen": "2026-01-01T09:00:00Z"},
    {"id": "d-2", "hostname": "build-01", "ip_address": "10.0.0.20", "os": "Ubuntu 24.04", "owner": "", "last_seen": 1767225600},
    {"id": "d-3", "hostname": "alan-phone", "ip_address": "", "os": "iOS 19", "owner": "User 2", "last_seen": "2025-12-31T18:44:00Z"},
]
DIRTY_USERS = [
    _user(1),
    {"name": "No Id", "email": "noid@example.com", "status": "active"},                      # missing_required_field: id
    {"id": "u-bad-date", "name": "Bad Date", "status": "active", "last_login": "31/31/2025"},  # transform_failed: last_login
    {"id": "u-banned", "name": "Banned", "status": "banned"},                                 # unknown status: becomes unknown, or invalid_value with no default
    _user(2),
]


def _alerts() -> list[dict]:
    now = datetime.now(UTC)
    levels = ["info", "warning", "error", "critical", "warning", "info"]
    return [
        {"id": f"a-{i}", "type": "login.failed" if i % 2 else "policy.violation", "severity": levels[i - 1],
         "created_at": (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"), "message": f"Alert {i}"}
        for i, h in enumerate([1, 3, 6, 12, 30, 50], start=1)
    ]


@app.middleware("http")
async def check_auth(request: Request, call_next):
    if request.url.path in ("/health", "/wrong-key", "/reset"):
        return await call_next(request)
    if request.headers.get("Authorization") != f"SSWS {MOCK_TOKEN}":
        return JSONResponse({"errorCode": "E0000011", "errorSummary": "Invalid token provided"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/reset")
def reset():
    _calls.clear()
    return {"reset": True}


# ---------------------------------------------------------------- the four paging styles

@app.get("/pages/page-number")
def page_number(page: int = 1, per_page: int = 10):
    start = (page - 1) * per_page
    return USERS[start:start + per_page]


@app.get("/pages/offset")
def offset(offset: int = 0, limit: int = 10):
    return {"meta": {"total": len(USERS)}, "items": USERS[offset:offset + limit]}


@app.get("/pages/cursor")
def cursor(after: str | None = None, limit: int = 10):
    start = int(after or 0)
    nxt = start + limit
    return {"items": USERS[start:nxt], "meta": {"next": str(nxt) if nxt < len(USERS) else None}}


@app.get("/pages/next-link")
def next_link(request: Request, page: int = 1, per_page: int = 10):
    start = (page - 1) * per_page
    headers = {}
    if start + per_page < len(USERS):
        url = request.url.include_query_params(page=page + 1, per_page=per_page)
        headers["Link"] = f'<{url}>; rel="next"'
    return JSONResponse(USERS[start:start + per_page], headers=headers)


@app.get("/users/{user_id}")
def one_user(user_id: str):
    """A lookup target: u-1 to u-25 exist, anything else is a 404."""
    found = next((u for u in USERS if u["id"] == user_id), None)
    return found if found else JSONResponse({"error": "not found"}, status_code=404)


# ---------------------------------------------------------------- data for the other schemas

@app.get("/devices")
def devices():
    return DEVICES


@app.get("/alerts")
def alerts(since: str | None = None):
    if not since:
        return JSONResponse({"error": "since is required"}, status_code=400)
    try:
        cutoff = datetime.fromisoformat(since)
    except ValueError:
        return JSONResponse({"error": "since must be ISO 8601"}, status_code=400)
    return {"items": [a for a in _alerts() if datetime.fromisoformat(a["created_at"]) >= cutoff]}


@app.get("/dirty/users")
def dirty_users():
    return DIRTY_USERS


# ---------------------------------------------------------------- failures

@app.get("/flaky")
def flaky(fail: int = 2, key: str = "default"):
    """Answers 500 for the first `fail` calls per key, then the users."""
    _calls[f"flaky:{key}"] += 1
    if _calls[f"flaky:{key}"] <= fail:
        return JSONResponse({"error": "temporarily unavailable"}, status_code=500)
    return USERS[:5]


@app.get("/rate-limited")
def rate_limited(times: int = 1, retry_after: int = 2, key: str = "default"):
    """Answers 429 with Retry-After for the first `times` calls per key."""
    _calls[f"rl:{key}"] += 1
    if _calls[f"rl:{key}"] <= times:
        return JSONResponse({"error": "slow down"}, status_code=429, headers={"Retry-After": str(retry_after)})
    return USERS[:5]


@app.get("/rate-limited-no-header")
def rate_limited_no_header(times: int = 1, key: str = "default"):
    _calls[f"rlnh:{key}"] += 1
    if _calls[f"rlnh:{key}"] <= times:
        return JSONResponse({"error": "slow down"}, status_code=429)
    return USERS[:5]


@app.get("/wrong-key")
def wrong_key():
    return JSONResponse({"errorCode": "E0000011", "errorSummary": "Invalid token provided"}, status_code=401)


@app.get("/error-body")
def error_body():
    return {"ok": False, "error": "invalid_auth"}


@app.get("/slow")
async def slow(seconds: float = 5):
    await asyncio.sleep(seconds)
    return USERS[:1]


@app.get("/drop")
def drop():
    """Starts a reply, then cuts the connection (the network-drop test)."""

    def body():
        yield b'[{"id": "u-1", "name": "Cut'
        raise ConnectionResetError("dropped on purpose")

    # Promise more bytes than are sent, so the client sees the connection close mid-body.
    return StreamingResponse(body(), media_type="application/json", headers={"Content-Length": "4096"})
