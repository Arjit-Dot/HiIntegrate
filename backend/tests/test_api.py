"""The API end to end on SQLite, with the mock service behind it: configs in the database (D-15), runs,
results, quarantine, secrets (D-7.6), unified users (D-16) and the error shapes (D-6)."""

import copy
import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.deps import engine_dep, outbound_client_dep
from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.main import create_app
from app.storage import make_engine, repo, session_factory
from app.storage.models import Base
from tests.mock_api.app import app as mock_app

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
MOCK["enabled"] = True
GH_YAML = (REPO_ROOT / "templates" / "github.yaml").read_text()


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("SECRET_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = make_engine(f"sqlite:///{tmp_path}/api.db")
    Base.metadata.create_all(engine)
    mock = TestClient(mock_app)
    mock.post("/reset")
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    app.dependency_overrides[outbound_client_dep] = lambda: mock
    return TestClient(app), engine


@pytest.fixture
def api(env):
    return env[0]


def add_mock(api, cfg=None):
    r = api.post("/api/v1/integrations", json=cfg or MOCK)
    assert r.status_code == 201, r.text
    return r.json()


def run(api, action, inputs=None):
    return api.post(f"/api/v1/integrations/mock-service/actions/{action}/run", json={"inputs": inputs} if inputs else {})


# ---------------------------------------------------------------- configs in the database (D-15)

def test_validate_json_and_yaml_with_lines(api):
    ok = api.post("/api/v1/integrations/validate", content=GH_YAML, headers={"Content-Type": "text/yaml"}).json()
    assert ok == {"valid": True, "errors": []}
    bad = (REPO_ROOT / "samples" / "invalid" / "typo-pagination.yaml").read_text()
    r = api.post("/api/v1/integrations/validate", content=bad, headers={"Content-Type": "text/yaml"}).json()
    assert r["valid"] is False and r["errors"][0]["path"] == "actions.list_users.pagnation" and "line" in r["errors"][0]
    as_json = api.post("/api/v1/integrations/validate", json=parse_config(bad)).json()
    assert as_json["valid"] is False and "line" not in as_json["errors"][0]


def test_create_accepts_yaml_rejects_invalid_and_duplicates(api):
    r = api.post("/api/v1/integrations", content=GH_YAML, headers={"Content-Type": "text/yaml"})
    assert r.status_code == 201 and r.json()["revision"] == 1 and r.json()["health"]["status"] == "never_run"
    dup = api.post("/api/v1/integrations", content=GH_YAML, headers={"Content-Type": "text/yaml"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    broken = api.post("/api/v1/integrations", json={**MOCK, "name": "Bad Name"})
    assert broken.status_code == 400 and broken.json()["error"]["details"]["errors"][0]["path"] == "name"


def test_editing_updates_the_same_integration_in_place(api):
    first = api.post("/api/v1/integrations", content=GH_YAML, headers={"Content-Type": "text/yaml"}).json()
    cfg = copy.deepcopy(first["config"])
    cfg["actions"]["list_repos"] = copy.deepcopy(cfg["actions"]["list_members"])
    cfg["actions"]["list_repos"]["request"]["path"] = "/orgs/{{vars.org}}/repos"
    r = api.put("/api/v1/integrations/github", json=cfg)
    assert r.status_code == 200 and r.json()["revision"] == 2 and "list_repos" in r.json()["config"]["actions"]
    assert api.get("/api/v1/integrations").json()["total"] == 1  # D-15: no second integration
    listed = api.get("/api/v1/integrations").json()["items"][0]
    assert listed["actions"] == [{"name": n, "mode": cfg["actions"][n]["mode"]} for n in cfg["actions"]]
    renamed = api.put("/api/v1/integrations/github", json={**cfg, "name": "github2"})
    assert renamed.status_code == 400 and "must stay github" in renamed.json()["error"]["details"]["errors"][0]["message"]
    assert api.get("/api/v1/integrations/github").json()["revision"] == 2


def test_enable_disable_delete_and_not_found(api):
    add_mock(api)
    r = api.patch("/api/v1/integrations/mock-service/enabled", json={"enabled": False})
    assert r.json()["enabled"] is False and r.json()["health"]["status"] == "disabled"
    assert api.get("/api/v1/integrations/mock-service/health").json()["status"] == "disabled"
    assert api.delete("/api/v1/integrations/mock-service").status_code == 204
    missing = api.get("/api/v1/integrations/mock-service")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_list_filters(api):
    add_mock(api)
    api.post("/api/v1/integrations", content=GH_YAML, headers={"Content-Type": "text/yaml"})
    assert api.get("/api/v1/integrations", params={"q": "git"}).json()["total"] == 1
    assert api.get("/api/v1/integrations", params={"category": "identity"}).json()["items"][0]["name"] == "github"
    assert api.get("/api/v1/integrations", params={"status": "never_run"}).json()["total"] == 2
    assert api.get("/api/v1/integrations", params={"status": "failing"}).json()["total"] == 0


# ---------------------------------------------------------------- runs, results, quarantine, health

def test_a_pull_runs_in_the_background_and_fills_the_table(api):
    add_mock(api)
    r = run(api, "users_offset")
    assert r.status_code == 202 and r.json()["status"] == "running"
    run_id = r.json()["run_id"]
    rec = api.get(f"/api/v1/runs/{run_id}").json()
    assert rec["status"] == "success" and (rec["pages_fetched"], rec["records_pulled"], rec["records_valid"], rec["records_invalid"]) == (3, 25, 25, 0)
    assert rec["mode"] == "pull" and rec["trigger"] == "manual" and rec["error"] is None
    results = api.get("/api/v1/results", params={"target": "user"}).json()
    assert results["total"] == 25 and results["items"][0]["source"] == "mock-service"
    run(api, "users_offset")  # again: records update, they are not duplicated
    assert api.get("/api/v1/results", params={"target": "user"}).json()["total"] == 25
    assert api.get("/api/v1/integrations/mock-service/health").json()["status"] == "healthy"
    assert api.get("/api/v1/runs", params={"integration": "mock-service"}).json()["total"] == 2


def test_dirty_data_is_quarantined_degraded_and_exportable(api):
    add_mock(api)
    run_id = run(api, "dirty_users").json()["run_id"]
    assert api.get("/api/v1/results", params={"target": "user"}).json()["total"] == 3
    q = api.get("/api/v1/quarantine", params={"run_id": run_id}).json()
    assert q["total"] == 2 and {i["reason"] for i in q["items"]} == {"missing_required_field", "transform_failed"}
    assert api.get("/api/v1/quarantine", params={"reason": "transform_failed"}).json()["total"] == 1
    assert api.get("/api/v1/integrations/mock-service/health").json()["status"] == "degraded"
    exported = api.get("/api/v1/quarantine/export")
    assert exported.headers["content-disposition"] == 'attachment; filename="quarantine.json"'
    assert len(json.loads(exported.text)) == 2 and json.loads(exported.text)[0]["target_schema"] == "user"
    assert api.get("/api/v1/quarantine", params={"reason": "nonsense"}).status_code == 400


def test_a_failed_pull_is_recorded_and_makes_the_integration_fail(api):
    add_mock(api)
    run_id = run(api, "wrong_key").json()["run_id"]
    rec = api.get(f"/api/v1/runs/{run_id}").json()
    assert rec["status"] == "failed" and rec["error"]["code"] == "auth_failed" and rec["retries"] == 0
    h = api.get("/api/v1/integrations/mock-service/health").json()
    assert h["status"] == "failing" and h["consecutive_failures"] == 1 and h["last_error"]["code"] == "auth_failed"


def test_an_action_that_is_already_running_returns_409(env):
    api, engine = env
    add_mock(api)
    with session_factory(engine)() as s:
        repo.start_run(s, "mock-service", "users_offset", "pull", "schedule")
        s.commit()
    r = run(api, "users_offset")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict" and r.json()["error"]["details"]["run_id"].startswith("run-")


def test_test_runs_are_recorded_but_ignored_by_health(api):
    add_mock(api)
    r = api.post("/api/v1/integrations/mock-service/test", json={"action": "users_offset"}).json()
    assert r["ok"] and r["pages_fetched"] == 1 and r["mapped_sample"]["id"] == "u-1"
    runs = api.get("/api/v1/runs").json()["items"]
    assert runs[0]["trigger"] == "test" and runs[0]["status"] == "success"
    assert api.get("/api/v1/results", params={"target": "user"}).json()["total"] == 0  # nothing saved
    assert api.get("/api/v1/integrations/mock-service/health").json()["status"] == "never_run"
    bad = api.post("/api/v1/integrations/mock-service/test", json={"action": "wrong_key"}).json()
    assert bad["ok"] is False and bad["notes"][0].startswith("auth_failed")
    assert api.get("/api/v1/runs").json()["items"][0]["error"]["code"] == "auth_failed"


# ---------------------------------------------------------------- lookups

def test_a_lookup_returns_its_record_and_saves_it(api):
    add_mock(api)
    r = run(api, "get_user", {"id": "u-3"})
    assert r.status_code == 200 and r.json()["id"] == "u-3" and r.json()["email"] == "user3@example.com"
    assert r.headers["x-run-id"].startswith("run-")
    assert api.get("/api/v1/runs/" + r.headers["x-run-id"]).json()["mode"] == "lookup"
    assert api.get("/api/v1/results", params={"target": "user"}).json()["total"] == 1


def test_lookup_inputs_are_checked_before_any_request(api):
    add_mock(api)
    r = run(api, "get_user")
    assert r.status_code == 400 and r.json()["error"]["details"]["errors"] == [{"path": "inputs.id", "message": "is required", "severity": "error"}]
    assert run(api, "get_user", {"id": "u-1", "extra": "x"}).status_code == 400
    assert api.get("/api/v1/runs").json()["total"] == 0  # a rejected request creates no run


def test_a_lookup_that_fails_at_the_service_is_a_502_and_still_recorded(api):
    add_mock(api)
    missing = run(api, "get_user", {"id": "u-999"})
    assert missing.status_code == 502 and missing.json()["error"]["code"] == "run_failed"
    assert missing.json()["error"]["details"]["error_code"] == "client_error"
    wrong = run(api, "get_user_wrong_key", {"id": "x"})
    assert wrong.status_code == 502 and wrong.json()["error"]["details"]["error_code"] == "auth_failed"
    assert api.get("/api/v1/runs", params={"status": "failed"}).json()["total"] == 2


def test_unknown_action_and_unknown_integration(api):
    add_mock(api)
    assert run(api, "nope").status_code == 404
    assert api.post("/api/v1/integrations/ghost/actions/x/run", json={}).status_code == 404


# ---------------------------------------------------------------- secrets and host pinning (D-7)

def test_secrets_are_write_only_and_host_pinned(api):
    assert api.put("/api/v1/secrets/github_token", json={"value": "ghp_value_123456", "host": "api.github.com"}).status_code == 204
    items = api.get("/api/v1/secrets").json()["items"]
    entry = next(i for i in items if i["name"] == "github_token")
    assert entry["host"] == "api.github.com" and entry["set"] is True and "ghp_value_123456" not in json.dumps(items)
    bad = api.put("/api/v1/secrets/github_token", json={"value": "x" * 10, "host": "https://api.github.com/x"})
    assert bad.status_code == 400 and "bare host" in bad.json()["error"]["message"]
    assert api.put("/api/v1/secrets/bad name!", json={"value": "x", "host": "a.com"}).status_code == 400
    assert api.put("/api/v1/secrets/x_token", json={"value": "", "host": "a.com"}).status_code == 400


def test_secret_store_unavailable_without_a_key_is_501(api, monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY")
    r = api.put("/api/v1/secrets/x_token", json={"value": "value_123456", "host": "api.github.com"})
    assert r.status_code == 501 and r.json()["error"]["code"] == "unsupported"


def test_a_stored_secret_pinned_to_another_host_is_refused_end_to_end(api):
    add_mock(api)
    api.put("/api/v1/secrets/mock_token", json={"value": "mock-secret-123", "host": "api.github.com"})  # the store wins over .env
    run_id = run(api, "users_offset").json()["run_id"]
    rec = api.get(f"/api/v1/runs/{run_id}").json()
    assert rec["status"] == "failed" and rec["error"]["code"] == "secret_host_mismatch" and rec["pages_fetched"] == 0
    api.put("/api/v1/secrets/mock_token", json={"value": "mock-secret-123", "host": "localhost"})  # enter it again for the real host
    assert api.get(f"/api/v1/runs/{run(api, 'users_offset').json()['run_id']}").json()["status"] == "success"


# ---------------------------------------------------------------- templates, paging and error shapes

def test_templates_are_starting_points(api):
    items = api.get("/api/v1/templates").json()["items"]
    assert {"github", "jira", "okta", "service-template", "generic-user"} <= {t["id"] for t in items}
    github = next(t for t in items if t["id"] == "github")
    assert github["requires"]["secrets"] == ["github_token"]
    one = api.get("/api/v1/templates/okta").json()
    assert one["config"]["name"] == "okta" and one["yaml"].startswith("version: 1")
    assert api.get("/api/v1/templates/nope").status_code == 404
    assert api.get("/api/v1/templates/..%2Fschema").status_code == 404
    assert api.get("/api/v1/integrations").json()["total"] == 0  # reading a template adds nothing


def test_paging_and_error_shape(api):
    add_mock(api)
    run(api, "users_offset")
    page = api.get("/api/v1/results", params={"target": "user", "limit": 10, "offset": 20}).json()
    assert (len(page["items"]), page["total"], page["limit"], page["offset"]) == (5, 25, 10, 20)
    for r in (api.get("/api/v1/results"), api.get("/api/v1/results", params={"target": "robot"}), api.get("/api/v1/runs", params={"limit": 9999})):
        assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------- unified users (D-16)

def test_unified_users_merge_by_email_and_never_merge_without_one(env):
    api, engine = env

    def user(source, id_, email, name, status="active", last_login=None, fetched="2026-01-01T09:00:00Z"):
        return {"id": id_, "name": name, "email": email, "status": status, "last_login": last_login, "source": source, "fetched_at": fetched}

    with session_factory(engine)() as s:
        repo.upsert_records(s, "user", [
            user("github", "4021", "grace@acme.com", "ghopper"),
            user("jira", "5b10a1", "Grace@Acme.com".lower(), "Grace Hopper", last_login="2025-12-01T10:00:00Z"),
            user("okta", "00u1grace", "grace@acme.com", None, "suspended", "2025-12-20T10:00:00Z", "2026-01-01T09:05:00Z"),
            user("github", "4022", None, "no-email-ada"),
            user("jira", "u-2", None, "no-email-ada"),  # same name, no email: never merged
            user("okta", "00u2", "alan@acme.com", "Alan Turing"),
        ])
        s.commit()
    body = api.get("/api/v1/users/unified").json()
    assert body["total"] == 4
    grace = next(p for p in body["items"] if p["key"] == "grace@acme.com")
    assert [x["source"] for x in grace["sources"]] == ["github", "jira", "okta"]
    assert grace["name"] == "ghopper" and grace["last_login"] == "2025-12-20T10:00:00Z" and grace["email"] == "grace@acme.com"
    assert next(x for x in grace["sources"] if x["source"] == "okta")["status"] == "suspended"
    lonely = [p for p in body["items"] if p["email"] is None]
    assert sorted(p["key"] for p in lonely) == ["github:4022", "jira:u-2"] and all(len(p["sources"]) == 1 for p in lonely)
    only_okta = api.get("/api/v1/users/unified", params={"source": "okta"}).json()
    assert only_okta["total"] == 2 and next(p for p in only_okta["items"] if p["key"] == "grace@acme.com")["sources"].__len__() == 3
    assert api.get("/api/v1/users/unified", params={"limit": 2, "offset": 2}).json()["items"].__len__() == 2
    assert api.get("/api/v1/results", params={"target": "user"}).json()["total"] == 6  # stored rows are unchanged


def test_unified_users_from_real_runs_rerun_does_not_duplicate(api):
    add_mock(api)
    run(api, "users_offset")
    run(api, "users_offset")
    unified = api.get("/api/v1/users/unified", params={"limit": 500}).json()
    assert unified["total"] == 25 and all(len(p["sources"]) == 1 for p in unified["items"])


# ---------------------------------------------------------------- the responses match the contract

def test_responses_match_result_schema(env):
    from jsonschema import Draft202012Validator

    from app.engine.mapping import validator_for

    api, engine = env
    add_mock(api)
    run(api, "dirty_users")
    run(api, "wrong_key")
    with session_factory(engine)() as s:
        repo.upsert_records(s, "user", [{"id": "1", "name": "A", "email": "a@x.co", "status": "active", "last_login": None, "source": "github", "fetched_at": "2026-01-01T09:00:00Z"}])
        s.commit()
    schema = json.loads((REPO_ROOT / "schema" / "result.schema.json").read_text())

    def check(def_name, body):
        v = Draft202012Validator({**schema["$defs"][def_name], "$defs": schema["$defs"]})
        errors = [e.message for e in v.iter_errors(body)]
        assert not errors, (def_name, errors, body)

    for item in api.get("/api/v1/results", params={"target": "user"}).json()["items"]:
        assert not list(validator_for("user").iter_errors(item)), item
    for item in api.get("/api/v1/quarantine").json()["items"]:
        check("quarantine_record", item)
    for item in api.get("/api/v1/runs").json()["items"]:
        check("run_record", item)
    check("health", api.get("/api/v1/integrations/mock-service/health").json())
    for item in api.get("/api/v1/users/unified").json()["items"]:
        check("unified_user", item)
