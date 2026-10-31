"""Schema drift: a mapped path that vanishes from every record marks the connection degraded and names the path."""

import copy

import httpx
import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine import run_action
from app.engine.drift import DriftTracker, mapped_paths
from app.scheduler import runner
from app.storage import make_engine, repo, session_scope
from app.storage.models import Base
from tests.helpers import ACCT

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())


def action_with(map_):
    return {"mode": "pull", "map": map_}


def test_a_path_that_was_seen_before_and_is_now_gone_is_reported_with_its_field():
    t = DriftTracker(action_with({"id": "id", "email": "profile.email", "name": {"path": "name", "transform": "string"}}),
                     baseline={"id", "profile.email", "name"})
    t.add([{"id": 1, "name": "a", "profile": {}}, {"id": 2, "name": "b"}])
    report = t.report()
    assert report["code"] == "schema_drift" and "profile.email (field email)" in report["message"] and "none of 2 records" in report["message"]
    assert "name (" not in report["message"] and "id (" not in report["message"]
    assert t.seen == {"id", "name"}


def test_a_path_that_was_never_seen_is_not_drift():
    """Without a baseline there is nothing that "vanished": a field the service never sends stays quiet."""
    t = DriftTracker(action_with({"id": "id", "email": "email"}))
    t.add([{"id": 1}])
    assert t.report() is None
    t = DriftTracker(action_with({"id": "id", "email": "email"}), baseline={"id"})
    t.add([{"id": 1}])
    assert t.report() is None


def test_one_record_with_the_path_is_enough_and_pages_add_up():
    t = DriftTracker(action_with({"id": "id", "email": "email"}), baseline={"id", "email"})
    t.add([{"id": 1}])
    t.add([{"id": 2, "email": "x@example.com"}])  # a later page still has it
    assert t.report() is None


def test_a_null_value_is_data_not_drift():
    t = DriftTracker(action_with({"id": "id", "last_login": "last_login"}), baseline={"id", "last_login"})
    t.add([{"id": 1, "last_login": None}])
    assert t.report() is None


def test_no_records_means_nothing_to_judge():
    assert DriftTracker(action_with({"id": "id"}), baseline={"id"}).report() is None


def test_only_plain_paths_are_checked():
    paths = mapped_paths(action_with({"id": "id", "a": "items[0].x", "b": "foo[?x=='y'].z", "c": "length(list)", "d": {"default": "n/a"}}))
    assert paths == {"id": "id", "a": "items[0].x"}


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    eng = make_engine(f"sqlite:///{tmp_path}/d.db")
    Base.metadata.create_all(eng)
    return eng


def users(**extra):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "items": [{"id": str(i), "name": f"u{i}", "email": f"u{i}@example.com", "status": "active", "last_login": None, **extra} for i in (1, 2)], "meta": {"next": None}})))


def cfg_without(field):
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = "drifty", True
    cfg["actions"] = {"users_cursor": cfg["actions"]["users_cursor"]}
    return cfg


def renamed_response():
    """The service renamed `email` to `mail`."""
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        "items": [{"id": str(i), "name": f"u{i}", "mail": f"u{i}@example.com", "status": "active", "last_login": None} for i in (1, 2)], "meta": {"next": None}})))


def health(engine):
    with session_scope(engine) as s:
        return repo.health(s, repo.get_integration(s, ACCT, "drifty"))


def add_drifty(engine):
    with session_scope(engine) as s:
        repo.create_integration(s, ACCT, cfg_without("email"))


def run(engine, client):
    return runner.run(engine, ACCT, "drifty", "users_cursor", "schedule", client=client)[1]


def test_the_first_run_sets_the_baseline_and_is_never_drift(engine):
    add_drifty(engine)
    result = run(engine, renamed_response())  # `email` was never seen, so it did not vanish
    assert result.status == "success" and result.error is None and health(engine)["status"] == "healthy"
    with session_scope(engine) as s:
        assert repo.get_baseline(s, ACCT, "drifty", "users_cursor") == {"id", "name", "status", "last_login"}


def test_a_renamed_field_after_a_good_run_succeeds_but_names_the_path(engine):
    add_drifty(engine)
    assert run(engine, users()).error is None  # the baseline now holds `email`
    result = run(engine, renamed_response())
    assert result.status == "success" and result.records_valid == 2
    assert result.error["code"] == "schema_drift" and "email" in result.error["message"]
    h = health(engine)
    assert h["status"] == "degraded" and h["last_error"]["code"] == "schema_drift" and h["consecutive_failures"] == 0
    again = run(engine, renamed_response())  # still gone: the baseline did not forget it
    assert again.error["code"] == "schema_drift"


def test_the_connection_is_healthy_again_once_the_field_is_back(engine):
    add_drifty(engine)
    run(engine, users())
    run(engine, renamed_response())
    assert run(engine, users()).error is None
    h = health(engine)
    assert h["status"] == "healthy" and h["last_error"] is None


def test_a_failed_run_does_not_touch_the_baseline(engine):
    add_drifty(engine)
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    assert run(engine, bad).status == "failed"
    with session_scope(engine) as s:
        assert repo.get_baseline(s, ACCT, "drifty", "users_cursor") == set()


def test_an_empty_response_neither_flags_nor_forgets(engine):
    add_drifty(engine)
    run(engine, users())
    empty = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": [], "meta": {"next": None}})))
    assert run(engine, empty).error is None
    assert run(engine, renamed_response()).error["code"] == "schema_drift"


def test_remapping_the_field_in_the_config_ends_the_drift(engine):
    """The person fixes it by pointing the map at the new name. The old path is no longer checked."""
    add_drifty(engine)
    run(engine, users())
    assert run(engine, renamed_response()).error["code"] == "schema_drift"
    with session_scope(engine) as s:
        cfg = copy.deepcopy(repo.get_integration(s, ACCT, "drifty").config)
        cfg["actions"]["users_cursor"]["map"]["email"] = {"path": "mail", "transform": "lowercase"}
        repo.replace_integration(s, ACCT, "drifty", cfg)
    assert run(engine, renamed_response()).error is None and health(engine)["status"] == "healthy"


def test_the_baseline_is_kept_per_action(engine):
    cfg = cfg_without("email")
    cfg["actions"]["users_page_number"] = copy.deepcopy(MOCK["actions"]["users_page_number"])
    with session_scope(engine) as s:
        repo.create_integration(s, ACCT, cfg)
    run(engine, users())
    with session_scope(engine) as s:
        assert "email" in repo.get_baseline(s, ACCT, "drifty", "users_cursor") and repo.get_baseline(s, ACCT, "drifty", "users_page_number") == set()


def test_deleting_an_integration_clears_its_baseline(engine):
    add_drifty(engine)
    run(engine, users())
    with session_scope(engine) as s:
        repo.delete_integration(s, ACCT, "drifty")
    with session_scope(engine) as s:
        assert repo.get_baseline(s, ACCT, "drifty", "users_cursor") == set()


def test_a_real_failure_outranks_drift_in_health(engine):
    cfg = cfg_without("email")
    cfg["actions"]["wrong_key"] = copy.deepcopy(MOCK["actions"]["wrong_key"])
    with session_scope(engine) as s:
        repo.create_integration(s, ACCT, cfg)
    run(engine, users())
    runner.run(engine, ACCT, "drifty", "users_cursor", "schedule", client=renamed_response())
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    runner.run(engine, ACCT, "drifty", "wrong_key", "schedule", client=bad, sleep=lambda s: None)
    with session_scope(engine) as s:
        h = repo.health(s, repo.get_integration(s, ACCT, "drifty"))
    assert h["status"] == "failing" and h["last_error"]["code"] == "auth_failed"


def test_the_engine_alone_has_no_baseline_and_reports_no_drift(monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    r = run_action(MOCK, "users_cursor", client=renamed_response(), sleep=lambda s: None)
    assert r.status == "success" and r.error is None and r.seen_paths
