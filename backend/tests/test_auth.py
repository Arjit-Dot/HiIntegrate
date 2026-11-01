"""Accounts and per-person data (D-18): sign-in, 401 without a session, and that one person never sees,
runs or reuses another person's integrations, records, runs or secrets."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import auth
from app.api.deps import engine_dep, outbound_client_dep
from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.main import create_app
from app.scheduler import timer
from app.storage import make_engine, repo, session_factory
from app.storage.models import AuthSession, Base
from tests.helpers import ACCT, PASSWORD, signed_in
from tests.mock_api.app import app as mock_app

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
MOCK["enabled"] = True
V1 = "/api/v1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("SECRET_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")  # reachable only by ENV_SECRETS_ACCOUNT ("tester")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = make_engine(f"sqlite:///{tmp_path}/auth.db")
    Base.metadata.create_all(engine)
    mock = TestClient(mock_app)
    mock.post("/reset")
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    app.dependency_overrides[outbound_client_dep] = lambda: mock
    app.state.engine = engine
    return app, engine


@pytest.fixture
def anon(env):
    return TestClient(env[0])


@pytest.fixture
def alice(env):
    return signed_in(TestClient(env[0]), ACCT)


@pytest.fixture
def bob(env):
    return signed_in(TestClient(env[0]), "bob")


@pytest.fixture(autouse=True)
def _fresh_throttle():
    auth.throttle._fails.clear()


# ---------------------------------------------------------------- sign in and out

def test_register_login_me_logout(anon):
    r = anon.post(f"{V1}/auth/register", json={"username": "Carol", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["username"] == "carol" and r.json()["token"]
    login = anon.post(f"{V1}/auth/login", json={"username": "CAROL", "password": PASSWORD})
    assert login.status_code == 200
    h = {"X-Session-Token": login.json()["token"]}
    assert anon.get(f"{V1}/auth/me", headers=h).json() == {"username": "carol"}
    assert anon.post(f"{V1}/auth/logout", headers=h).status_code == 204
    assert anon.get(f"{V1}/auth/me", headers=h).status_code == 401  # the token no longer works


def test_register_rules_and_duplicate(anon):
    assert anon.post(f"{V1}/auth/register", json={"username": "ab", "password": PASSWORD}).status_code == 400
    assert anon.post(f"{V1}/auth/register", json={"username": "has space", "password": PASSWORD}).status_code == 400
    assert anon.post(f"{V1}/auth/register", json={"username": "dave", "password": "short"}).status_code == 400
    assert anon.post(f"{V1}/auth/register", json={"username": "dave", "password": PASSWORD}).status_code == 201
    dup = anon.post(f"{V1}/auth/register", json={"username": "DAVE", "password": PASSWORD})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"


def test_registration_can_be_closed(anon, monkeypatch):
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    r = anon.post(f"{V1}/auth/register", json={"username": "erin", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "unauthorized"


def test_a_wrong_password_and_an_unknown_user_look_the_same(anon, alice):
    wrong = anon.post(f"{V1}/auth/login", json={"username": ACCT, "password": "not the password"})
    unknown = anon.post(f"{V1}/auth/login", json={"username": "nobody", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_too_many_wrong_passwords_are_throttled(anon, alice):
    for _ in range(auth.throttle.limit):
        assert anon.post(f"{V1}/auth/login", json={"username": ACCT, "password": "wrong password"}).status_code == 401
    blocked = anon.post(f"{V1}/auth/login", json={"username": ACCT, "password": PASSWORD})  # even the right one waits
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"


def test_only_a_hash_of_the_password_and_token_is_stored(env, anon):
    _, engine = env
    token = anon.post(f"{V1}/auth/register", json={"username": "frank", "password": PASSWORD}).json()["token"]
    with session_factory(engine)() as s:
        acct = repo.get_account(s, "frank")
        assert PASSWORD not in acct.password_hash and acct.password_hash.startswith("scrypt$")
        assert auth.verify_password(PASSWORD, acct.password_hash) and not auth.verify_password("other password", acct.password_hash)
        stored = s.get(AuthSession, auth.token_hash(token))
        assert stored is not None and stored.token_hash != token


def test_an_expired_session_is_refused(env, alice):
    _, engine = env
    with session_factory(engine)() as s:
        for row in s.query(AuthSession):
            row.expires_at = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        s.commit()
    assert alice.get(f"{V1}/auth/me").status_code == 401


def test_every_route_but_health_and_sign_in_needs_a_session(env, anon):
    app, _ = env
    open_paths = {f"{V1}/health", f"{V1}/auth/register", f"{V1}/auth/login"}
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        if path in open_paths:
            continue
        for method in methods:
            r = anon.request(method.upper(), path.replace("{", "x").replace("}", ""), json={})
            assert r.status_code == 401, (method, path, r.status_code)
            assert r.json()["error"]["code"] == "unauthorized"
            checked += 1
    assert checked >= 25
    assert anon.get(f"{V1}/health").status_code == 200
    bad = anon.get(f"{V1}/integrations", headers={"X-Session-Token": "made-up"})
    assert bad.status_code == 401


# ---------------------------------------------------------------- one person cannot reach another's data

def add_mock(client):
    r = client.post(f"{V1}/integrations", json=MOCK)
    assert r.status_code == 201, r.text


def test_integrations_are_private_and_names_do_not_clash(alice, bob):
    add_mock(alice)
    assert bob.get(f"{V1}/integrations").json()["total"] == 0
    assert bob.get(f"{V1}/integrations/mock-service").status_code == 404
    assert bob.put(f"{V1}/integrations/mock-service", json=MOCK).status_code == 404
    assert bob.patch(f"{V1}/integrations/mock-service/enabled", json={"enabled": False}).status_code == 404
    assert bob.delete(f"{V1}/integrations/mock-service").status_code == 404
    add_mock(bob)  # the same name is fine for someone else
    assert alice.get(f"{V1}/integrations").json()["total"] == 1
    assert alice.get(f"{V1}/integrations/mock-service").json()["config"]["enabled"] is True  # bob's delete/disable never touched it


def test_runs_records_and_quarantine_are_private(alice, bob):
    add_mock(alice)
    r = alice.post(f"{V1}/integrations/mock-service/actions/users_cursor/run", json={})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    assert alice.get(f"{V1}/results", params={"target": "user"}).json()["total"] > 0
    assert alice.get(f"{V1}/runs").json()["total"] >= 1
    for path, params in ((f"{V1}/results", {"target": "user"}), (f"{V1}/users/unified", {}), (f"{V1}/quarantine", {}), (f"{V1}/runs", {})):
        assert bob.get(path, params=params).json()["total"] == 0, path
    assert bob.get(f"{V1}/runs/{run_id}").status_code == 404  # looks the same as a run that does not exist
    assert bob.get(f"{V1}/quarantine/export").json() == []
    assert bob.post(f"{V1}/integrations/mock-service/actions/users_cursor/run", json={}).status_code == 404


def test_secrets_are_private_and_the_same_name_can_hold_different_values(alice, bob):
    assert alice.put(f"{V1}/secrets/github_token", json={"value": "alice-token-123", "host": "api.github.com"}).status_code == 204
    assert "github_token" not in [i["name"] for i in bob.get(f"{V1}/secrets").json()["items"]]
    assert bob.put(f"{V1}/secrets/github_token", json={"value": "bob-token-4567", "host": "api.github.com"}).status_code == 204
    names = [i["name"] for i in alice.get(f"{V1}/secrets").json()["items"]]
    assert names.count("github_token") == 1
    assert "alice-token-123" not in alice.get(f"{V1}/secrets").text and "bob-token-4567" not in bob.get(f"{V1}/secrets").text


def test_a_person_runs_with_their_own_secret_never_someone_elses(alice, bob):
    cfg = copy.deepcopy(MOCK)
    cfg["auth"]["secret"] = "shared_name"
    for c in (alice, bob):
        assert c.post(f"{V1}/integrations", json=cfg).status_code == 201
    assert alice.put(f"{V1}/secrets/shared_name", json={"value": "mock-secret-123", "host": "localhost"}).status_code == 204  # the real token
    assert bob.put(f"{V1}/secrets/shared_name", json={"value": "bob-has-the-wrong-token", "host": "localhost"}).status_code == 204
    ok = alice.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).json()
    bad = bob.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).json()
    assert ok["ok"] is True and bad["ok"] is False  # bob's run used bob's value, so the service refused it


def test_server_wide_env_secrets_reach_only_the_named_account(alice, bob):
    # SECRET_MOCK_TOKEN is in the environment and ENV_SECRETS_ACCOUNT is "tester" (alice here)
    assert "mock_token" in [i["name"] for i in alice.get(f"{V1}/secrets").json()["items"]]
    assert "mock_token" not in [i["name"] for i in bob.get(f"{V1}/secrets").json()["items"]]
    add_mock(alice)
    add_mock(bob)
    assert alice.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).json()["ok"] is True
    assert bob.post(f"{V1}/integrations/mock-service/test", json={"action": "users_cursor"}).json()["ok"] is False  # no secret of his own


def test_without_an_env_account_nobody_can_use_the_env_secrets(alice, monkeypatch):
    monkeypatch.delenv("ENV_SECRETS_ACCOUNT")
    assert "mock_token" not in [i["name"] for i in alice.get(f"{V1}/secrets").json()["items"]]


def test_the_worker_schedules_each_accounts_integrations_separately(env, alice, bob):
    _, engine = env
    cfg = copy.deepcopy(MOCK)
    cfg["actions"]["users_cursor"]["schedule"] = "every 1h"
    for c in (alice, bob):
        assert c.post(f"{V1}/integrations", json=cfg).status_code == 201
    changes = timer.sync(BackgroundScheduler(timezone="UTC"), engine)
    added = changes["added"]
    assert "bob:mock-service:users_cursor" in added and "tester:mock-service:users_cursor" in added
    assert all(job.startswith(("bob:", "tester:")) for job in added)


def test_a_new_sign_in_is_saved_before_the_token_is_returned(env):
    """FastAPI runs a dependency's cleanup (the commit) after the response is sent, so the session must be committed by
    the route itself: otherwise a client's very next request can arrive first and get a 401."""
    from app.api.auth import _signed_in

    _, engine = env
    writer = session_factory(engine)()
    reply = _signed_in(writer, "racer")  # no commit by the caller, as in the route
    with session_factory(engine)() as other:  # a different connection, like the client's next request
        assert repo.get_auth_session(other, auth.token_hash(reply["token"])) is not None
    writer.close()
