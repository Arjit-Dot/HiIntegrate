import logging

from fastapi import Body
from fastapi.testclient import TestClient

from app.core.errors import ApiError
from app.core.logging import REDACTED, RedactingFilter, redact
from app.main import create_app


def make_client() -> TestClient:
    app = create_app()

    @app.post("/api/v1/_test/body")
    def needs_body(count: int = Body(..., embed=True)):
        return {"count": count}

    @app.get("/api/v1/_test/conflict")
    def conflict():
        raise ApiError(409, "conflict", "list_users is already running", {"run_id": "run-7"})

    @app.get("/api/v1/_test/boom")
    def boom():
        raise RuntimeError("database password is hunter2")

    return TestClient(app, raise_server_exceptions=False)


def test_health_and_request_id():
    c = make_client()
    r = c.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert r.headers["X-Request-Id"]
    assert c.get("/api/v1/health", headers={"X-Request-Id": "abc123"}).headers["X-Request-Id"] == "abc123"


def test_unknown_route_uses_the_error_shape():
    r = make_client().get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "No such route", "details": None}}


def test_bad_body_is_a_400_validation_error_with_paths():
    r = make_client().post("/api/v1/_test/body", json={"count": "lots"})
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]["errors"][0]["path"] == "count"
    assert body["details"]["errors"][0]["severity"] == "error"


def test_api_error_keeps_code_and_details():
    r = make_client().get("/api/v1/_test/conflict")
    assert r.status_code == 409
    assert r.json()["error"] == {"code": "conflict", "message": "list_users is already running", "details": {"run_id": "run-7"}}


def test_unexpected_error_hides_the_cause():
    r = make_client().get("/api/v1/_test/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in r.text


def test_cors_allows_the_frontend():
    r = make_client().get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_redaction(monkeypatch):
    monkeypatch.setenv("SECRET_TEST_TOKEN", "supersecretvalue123")
    assert redact("calling with supersecretvalue123 now") == f"calling with {REDACTED} now"
    assert "abcdefghijkl" not in redact("Authorization: Bearer abcdefghijkl")
    assert "abcdefghijkl" not in redact("header SSWS abcdefghijkl")
    assert redact("postgresql+psycopg://postgres:pw12345678@localhost:5432/db") == f"postgresql+psycopg://postgres:{REDACTED}@localhost:5432/db"
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "token=%s", ("supersecretvalue123",), None)
    RedactingFilter().filter(record)
    assert "supersecretvalue123" not in record.getMessage()
