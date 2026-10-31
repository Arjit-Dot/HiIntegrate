"""Cross-service users end to end (D-16): several integrations run through the API, and one person shows once."""

import copy

import pytest
from fastapi.testclient import TestClient

from app.api.deps import engine_dep, outbound_client_dep
from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.main import create_app
from app.storage import make_engine
from app.storage.models import Base
from tests.helpers import signed_in
from tests.mock_api.app import app as mock_app

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    engine = make_engine(f"sqlite:///{tmp_path}/e2e.db")
    Base.metadata.create_all(engine)
    mock = TestClient(mock_app)
    mock.post("/reset")
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    app.dependency_overrides[outbound_client_dep] = lambda: mock
    return signed_in(TestClient(app))


def service(name: str, *, id_from: str = "id") -> dict:
    """Another service that knows the same people, but gives them its own ids (like GitHub, Jira and Okta do)."""
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = name, True
    for action in cfg["actions"].values():
        if "map" in action and "id" in action["map"]:
            action["map"] = {**action["map"], "id": {"path": id_from, "transform": "string"}}
    return cfg


def add(api, cfg):
    assert api.post("/api/v1/integrations", json=cfg).status_code == 201


def pull(api, name, action="users_offset"):
    r = api.post(f"/api/v1/integrations/{name}/actions/{action}/run", json={})
    assert r.status_code == 202, r.text
    run = api.get(f"/api/v1/runs/{r.json()['run_id']}").json()
    assert run["status"] == "success", run
    return run


def unified(api, **params):
    return api.get("/api/v1/users/unified", params={"limit": 500, **params}).json()


def test_the_same_people_on_two_services_appear_once_each(api):
    add(api, service("svc-a"))
    add(api, service("svc-b", id_from="name"))  # a different id for the same person
    pull(api, "svc-a")
    pull(api, "svc-b")
    body = unified(api)
    assert body["total"] == 25  # 25 people, not 50 rows
    assert api.get("/api/v1/results", params={"target": "user", "limit": 500}).json()["total"] == 50  # stored rows are unchanged
    person = next(p for p in body["items"] if p["key"] == "user3@example.com")
    assert [(x["source"], x["id"]) for x in person["sources"]] == [("svc-a", "u-3"), ("svc-b", "User 3")]
    assert person["email"] == "user3@example.com" and person["name"] == "User 3" and person["last_login"]
    assert all(len(p["sources"]) == 2 for p in body["items"])


def test_running_again_does_not_duplicate_people_or_services(api):
    add(api, service("svc-a"))
    add(api, service("svc-b", id_from="name"))
    for _ in range(2):
        pull(api, "svc-a")
        pull(api, "svc-b")
    body = unified(api)
    assert body["total"] == 25 and all(len(p["sources"]) == 2 for p in body["items"])


def test_the_source_filter_keeps_people_but_lists_all_their_services(api):
    add(api, service("svc-a"))
    add(api, service("svc-b", id_from="name"))
    pull(api, "svc-a")
    pull(api, "svc-b", "users_cursor")
    only_a = unified(api, source="svc-a")
    assert only_a["total"] == 25 and all({x["source"] for x in p["sources"]} == {"svc-a", "svc-b"} for p in only_a["items"])
    assert unified(api, source="nobody")["total"] == 0


def test_paging_the_merged_list(api):
    add(api, service("svc-a"))
    add(api, service("svc-b", id_from="name"))
    pull(api, "svc-a")
    pull(api, "svc-b")
    first = unified(api, limit=10, offset=0)
    last = unified(api, limit=10, offset=20)
    assert (len(first["items"]), first["total"], len(last["items"])) == (10, 25, 5)
    assert not {p["key"] for p in first["items"]} & {p["key"] for p in last["items"]}


def test_a_third_service_joins_and_a_user_without_email_is_never_merged(api):
    add(api, service("svc-a"))
    add(api, service("svc-b", id_from="name"))
    add(api, service("svc-c"))
    pull(api, "svc-a")
    pull(api, "svc-b")
    run = pull(api, "svc-c", "dirty_users")  # 3 usable users, 2 quarantined; one usable user has no email
    assert run["records_valid"] == 3 and run["records_invalid"] == 2
    body = unified(api)
    one = next(p for p in body["items"] if p["key"] == "user1@example.com")
    assert [x["source"] for x in one["sources"]] == ["svc-a", "svc-b", "svc-c"]
    lonely = next(p for p in body["items"] if p["key"] == "svc-c:u-banned")
    assert lonely["email"] is None and len(lonely["sources"]) == 1 and lonely["sources"][0]["status"] == "unknown"
    assert body["total"] == 26  # 25 people plus the one person with no email


def test_a_quarantined_record_is_not_a_person(api):
    add(api, service("svc-c"))
    pull(api, "svc-c", "dirty_users")
    keys = {p["key"] for p in unified(api)["items"]}
    assert keys == {"user1@example.com", "user2@example.com", "svc-c:u-banned"}  # the record with no id and the bad date are not here
