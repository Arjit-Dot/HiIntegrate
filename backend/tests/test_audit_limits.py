"""S-7 audit log and S-9 limits: what is recorded (names, never values), who can read it, when the API answers 429,
and the engine's response size cap."""

import copy

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import ratelimit
from app.api.deps import engine_dep, outbound_client_dep
from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine.errors import RunError
from app.engine.http import Policy, send
from app.main import create_app
from app.storage import make_engine
from app.storage.models import Base
from tests.helpers import ACCT, signed_in
from tests.mock_api.app import app as mock_app

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
MOCK["enabled"] = True
V1 = "/api/v1"
SECRET_VALUE = "super-secret-value-9f3a"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = make_engine(f"sqlite:///{tmp_path}/a.db")
    Base.metadata.create_all(engine)
    mock = TestClient(mock_app)
    mock.post("/reset")
    application = create_app()
    application.dependency_overrides[engine_dep] = lambda: engine
    application.dependency_overrides[outbound_client_dep] = lambda: mock
    return application


@pytest.fixture
def alice(app):
    return signed_in(TestClient(app), ACCT)


@pytest.fixture
def bob(app):
    return signed_in(TestClient(app), "bob")


def audit(client, **params):
    r = client.get(f"{V1}/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- S-7 ---------------------------------------------------------------------------------------------------------

def test_every_change_is_recorded_with_names_and_never_values(alice):
    assert alice.post(f"{V1}/integrations", json=MOCK).status_code == 201
    changed = copy.deepcopy(MOCK)
    changed["description"] = "edited"
    assert alice.put(f"{V1}/integrations/mock-service", json=changed).status_code == 200
    assert alice.patch(f"{V1}/integrations/mock-service/enabled", json={"enabled": False}).status_code == 200
    assert alice.put(f"{V1}/secrets/mock_token", json={"value": SECRET_VALUE, "host": "localhost"}).status_code == 204
    assert alice.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).status_code == 200
    assert alice.delete(f"{V1}/integrations/mock-service").status_code == 204

    page = audit(alice)
    events = [e["event"] for e in reversed(page["items"])]
    assert events == ["integration.created", "integration.updated", "integration.disabled", "secret.set", "action.tested",
                      "integration.deleted"]
    by_event = {e["event"]: e for e in page["items"]}
    assert by_event["integration.created"]["revision"] == 1 and by_event["integration.updated"]["revision"] == 2
    assert by_event["secret.set"]["target"] == "mock_token"
    assert by_event["action.tested"]["target"] == "mock-service/users_cursor"
    assert all(e["request_id"] for e in page["items"])
    assert SECRET_VALUE not in alice.get(f"{V1}/audit").text
    assert "edited" not in alice.get(f"{V1}/audit").text  # config bodies are not stored either


def test_a_manual_run_is_recorded(alice):
    alice.post(f"{V1}/integrations", json=MOCK)
    r = alice.post(f"{V1}/integrations/mock-service/actions/users_cursor/run")
    assert r.status_code == 202
    assert audit(alice, event="action.run")["items"][0]["target"] == "mock-service/users_cursor"


def test_the_log_is_filtered_and_paged(alice):
    alice.post(f"{V1}/integrations", json=MOCK)
    alice.put(f"{V1}/secrets/a", json={"value": "x", "host": "localhost"})
    alice.put(f"{V1}/secrets/b", json={"value": "x", "host": "localhost"})
    assert audit(alice, event="secret.set")["total"] == 2
    assert audit(alice, target="b")["items"][0]["target"] == "b"
    page = audit(alice, limit=1, offset=1)
    assert page["total"] == 3 and len(page["items"]) == 1


def test_each_account_reads_only_its_own_log(alice, bob):
    alice.post(f"{V1}/integrations", json=MOCK)
    assert audit(alice)["total"] == 1
    assert audit(bob)["total"] == 0


def test_the_log_needs_a_sign_in(app):
    assert TestClient(app).get(f"{V1}/audit").status_code == 401


def test_a_failed_change_leaves_no_entry(alice):
    assert alice.put(f"{V1}/integrations/nope", json=MOCK).status_code in (400, 404)
    assert alice.delete(f"{V1}/integrations/nope").status_code == 404
    assert audit(alice)["total"] == 0


# --- S-9: rate limits --------------------------------------------------------------------------------------------

def test_writes_over_the_limit_get_429_with_retry_after(alice, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WRITE", "3")
    for i in range(3):
        assert alice.put(f"{V1}/secrets/s{i}", json={"value": "x", "host": "localhost"}).status_code == 204
    r = alice.put(f"{V1}/secrets/s9", json={"value": "x", "host": "localhost"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    assert r.json()["error"]["details"]["bucket"] == "write"


def test_reads_and_validation_are_never_limited(alice, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WRITE", "1")
    for _ in range(10):
        assert alice.get(f"{V1}/integrations").status_code == 200
        assert alice.post(f"{V1}/integrations/validate", json=MOCK).status_code == 200


def test_the_limit_is_per_account(alice, bob, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WRITE", "1")
    assert alice.put(f"{V1}/secrets/a", json={"value": "x", "host": "localhost"}).status_code == 204
    assert alice.put(f"{V1}/secrets/b", json={"value": "x", "host": "localhost"}).status_code == 429
    assert bob.put(f"{V1}/secrets/a", json={"value": "x", "host": "localhost"}).status_code == 204


def test_run_and_ai_routes_have_their_own_limits(alice, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_RUN", "2")
    monkeypatch.setenv("RATE_LIMIT_AI", "1")
    alice.post(f"{V1}/integrations", json=MOCK)
    codes = [alice.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert alice.post(f"{V1}/integrations", json=copy.deepcopy(MOCK) | {"name": "other"}).status_code != 429  # writes are a different bucket
    first = alice.post(f"{V1}/ai/summarize", json={})
    assert first.status_code != 429
    assert alice.post(f"{V1}/ai/summarize", json={}).status_code == 429


def test_zero_turns_a_limit_off(alice, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WRITE", "0")
    for i in range(80):
        assert alice.put(f"{V1}/secrets/s{i % 5}", json={"value": "x", "host": "localhost"}).status_code == 204


def test_the_window_slides():
    limiter = ratelimit.RateLimiter(window=0.2)
    assert limiter.check("a", "write", 1) == 0
    assert limiter.check("a", "write", 1) > 0
    import time

    time.sleep(0.25)
    assert limiter.check("a", "write", 1) == 0


def test_buckets():
    assert ratelimit.bucket_for("GET", "/api/v1/runs") is None
    assert ratelimit.bucket_for("POST", "/api/v1/integrations/validate") is None
    assert ratelimit.bucket_for("POST", "/api/v1/integrations/x/test") == "run"
    assert ratelimit.bucket_for("POST", "/api/v1/integrations/x/actions/y/run") == "run"
    assert ratelimit.bucket_for("PUT", "/api/v1/secrets/x") == "write"
    assert ratelimit.bucket_for("POST", "/api/v1/ai/generate-config") == "ai"
    assert ratelimit.bucket_for("GET", "/api/v1/ai/anything") == "ai"


# --- S-9: size cap -----------------------------------------------------------------------------------------------

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _send(client):
    return send(client, httpx.Request("GET", "https://example.test/x"), Policy(max_retries=0))


def test_a_body_over_the_cap_is_refused_while_reading(monkeypatch):
    monkeypatch.setenv("MAX_RESPONSE_BYTES", "1000")

    def chunks():
        for _ in range(100):
            yield b"x" * 100  # no Content-Length: only reading the stream shows the size

    with pytest.raises(RunError) as exc:
        _send(_client(lambda r: httpx.Response(200, content=chunks())))
    assert exc.value.code == "bad_response" and "limit" in exc.value.message


def test_a_declared_length_over_the_cap_is_refused_before_reading(monkeypatch):
    monkeypatch.setenv("MAX_RESPONSE_BYTES", "1000")
    with pytest.raises(RunError) as exc:
        _send(_client(lambda r: httpx.Response(200, content=b"x" * 5000)))
    assert exc.value.code == "bad_response"


def test_a_normal_body_passes_and_keeps_its_headers(monkeypatch):
    monkeypatch.setenv("MAX_RESPONSE_BYTES", "1000")
    sent = _send(_client(lambda r: httpx.Response(200, json=[{"id": 1}], headers={"Link": '<https://x/next>; rel="next"'})))
    assert sent.response.json() == [{"id": 1}]
    assert sent.response.headers["Link"].startswith("<https://x/next>")
    assert sent.response.status_code == 200


def test_the_default_cap_is_ten_megabytes(monkeypatch):
    from app.engine.http import max_response_bytes

    monkeypatch.delenv("MAX_RESPONSE_BYTES", raising=False)
    assert max_response_bytes() == 10_000_000
