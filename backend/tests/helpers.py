"""Shared by the tests: the account every test acts as (D-18), and a way to sign a test client in."""

ACCT = "tester"
PASSWORD = "correct horse battery"


def signed_in(client, username: str = ACCT):
    """Register (or sign in) `username` and send its session token on every request of this client."""
    r = client.post("/api/v1/auth/register", json={"username": username, "password": PASSWORD})
    if r.status_code == 409:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code in (200, 201), r.text
    client.headers["X-Session-Token"] = r.json()["token"]
    return client
