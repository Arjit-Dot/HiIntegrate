"""The demo mock service. One process, two "services" on one port (http://mock-api:8001):

  /            the project's own mock (users, devices, alerts, paging styles, flaky, 429, wrong key, drop...),
               exactly as in backend/tests/mock_api/app.py. Auth: `Authorization: SSWS mock-secret-123`.
  /hr/users    "Acme HR": 14 users, 6 good and 8 bad. Six of the bad ones are FIXABLE by a config change
               (the quarantine + Fix with AI scene), two are genuinely bad data. Same SSWS auth.
  /hr/users/{id}  one of them, for the lookup action.

All tokens here are public TEST values.
"""

from base_app import MOCK_TOKEN
from base_app import app as base_app
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------- Acme HR (quarantine + Fix with AI)

hr = FastAPI(title="Acme HR (demo)")


def _hr(i: int, **over) -> dict:
    row = {"id": f"h-{i}", "name": f"Employee {i}", "email": f"Employee{i}@Acme.example", "status": "ACTIVE",
           "last_login": f"2026-01-{i:02d}T09:30:00Z"}
    row.update(over)
    return row


def _mail_only(i: int) -> dict:
    """The HR system sends some people's address as `mail` instead of `email` (a real-world inconsistency)."""
    row = _hr(i)
    row["mail"] = row.pop("email")
    return row


HR_USERS = [
    *[_hr(i) for i in range(1, 6)],                       # h-1..h-5   good
    *[_mail_only(i) for i in range(6, 9)],                # h-6..h-8   missing_required_field: email   (fix: path "email || mail")
    _hr(9, status="TERMINATED"),                          # h-9        good (TERMINATED is in the starting value_map)
    _hr(10, status="ON_LEAVE"),                           # h-10..h-11 invalid_value: status           (fix: add ON_LEAVE)
    _hr(11, status="ON_LEAVE"),
    _hr(12, status="PENDING"),                            # h-12       invalid_value: status           (fix: add PENDING)
    {"name": "No Id", "email": "noid@acme.example", "status": "ACTIVE"},                          # unfixable: no id
    _hr(14, last_login="31/31/2025"),                     # unfixable: an impossible date (transform_failed)
]


@hr.middleware("http")
async def hr_auth(request: Request, call_next):
    if request.headers.get("Authorization") != f"SSWS {MOCK_TOKEN}":
        return JSONResponse({"errorCode": "E0000011", "errorSummary": "Invalid token provided"}, status_code=401)
    return await call_next(request)


@hr.get("/users")
def hr_users():
    return HR_USERS


@hr.get("/users/{user_id}")
def hr_user(user_id: str):
    """A lookup target: h-1 to h-14 (h-13 has no id, so it cannot be found). h-6 shows a quarantined lookup (email under `mail`)."""
    found = next((u for u in HR_USERS if u.get("id") == user_id), None)
    return found if found else JSONResponse({"error": "not found"}, status_code=404)


# ---------------------------------------------------------------- one app, three mounts

app = FastAPI(title="HiIntegrate demo mock")
app.mount("/hr", hr)
app.mount("/", base_app)   # last: it answers everything else, as the plain mock always did
