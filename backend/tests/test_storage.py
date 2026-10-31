from types import SimpleNamespace

import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.storage import Conflict, NotFound, make_engine, repo, session_factory
from app.storage.models import Base

GH = parse_config((REPO_ROOT / "templates" / "github.yaml").read_text())


@pytest.fixture
def s(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    session = session_factory(engine)()
    yield session
    session.close()


def test_configs_live_in_the_database_and_update_in_place(s):
    row = repo.create_integration(s, GH)
    assert row.revision == 1 and row.config["name"] == "github"
    with pytest.raises(Conflict):
        repo.create_integration(s, GH)
    changed = {**GH, "actions": {**GH["actions"], "list_repos": GH["actions"]["list_members"]}}
    row = repo.replace_integration(s, "github", changed)
    assert row.revision == 2 and "list_repos" in row.config["actions"]
    assert len(repo.list_integrations(s)) == 1  # edited in place, no second integration (D-15)
    with pytest.raises(Conflict, match="must stay github"):
        repo.replace_integration(s, "github", {**GH, "name": "github2"})
    assert repo.set_enabled(s, "github", False).enabled is False and repo.get_integration(s, "github").revision == 3
    repo.delete_integration(s, "github")
    with pytest.raises(NotFound):
        repo.get_integration(s, "github")


def user(i, name, fetched="2026-01-01T09:00:00Z"):
    return {"id": str(i), "name": name, "email": None, "status": "active", "last_login": None, "source": "github", "fetched_at": fetched}


def test_records_upsert_on_source_and_id(s):
    repo.upsert_records(s, "user", [user(1, "Ada"), user(2, "Alan")])
    repo.upsert_records(s, "user", [user(1, "Ada Lovelace", "2026-01-01T10:00:00Z")])
    items, total = repo.list_results(s, "user")
    assert total == 2 and items[0] == user(1, "Ada Lovelace", "2026-01-01T10:00:00Z")
    assert repo.list_results(s, "user", source="jira") == ([], 0)
    assert len(repo.get_results(s, {"target": "user", "limit": 1})) == 1


def test_quarantine_list_and_export(s):
    entry = {"source": "jira", "action": "list_users", "target_schema": "user", "run_id": "run-1", "raw": {"x": 1},
             "reason": "missing_required_field", "field": "id", "created_at": "2026-01-01T09:00:00Z"}
    repo.add_quarantine(s, [entry, {**entry, "run_id": "run-2", "reason": "transform_failed"}])
    assert repo.list_quarantine(s, reason="transform_failed")[1] == 1
    assert [e["run_id"] for e in repo.export_quarantine(s)] == ["run-1", "run-2"]
    assert repo.export_quarantine(s, run_id="run-1") == [entry]


def finish(s, run, status, invalid=0):
    return repo.finish_run(s, run, SimpleNamespace(status=status, finished_at=repo.now_iso(), duration_ms=5, pages_fetched=1, records_pulled=3,
                                                   records_valid=3 - invalid, records_invalid=invalid, retries=0,
                                                   error={"code": "auth_failed", "message": "x"} if status == "failed" else None))


def test_only_one_running_run_per_action(s):
    run = repo.start_run(s, "github", "list_members", "pull", "manual")
    assert run.run_id == "run-1"
    with pytest.raises(Conflict) as exc:
        repo.start_run(s, "github", "list_members", "pull", "schedule")
    assert exc.value.details == {"run_id": "run-1"}
    other = repo.start_run(s, "github", "get_user", "lookup", "manual")  # another action is fine
    finish(s, run, "success")
    again = repo.start_run(s, "github", "list_members", "pull", "manual")  # allowed once the first has finished
    assert again.run_id.startswith("run-") and again.run_id not in ("run-1", other.run_id)
    assert repo.get_run(s, "run-1").status == "success" and repo.run_dict(other)["status"] == "running"
    assert repo.list_runs(s, status="running")[1] == 2


def test_health_rules(s):
    integ = repo.create_integration(s, GH)
    assert repo.health(s, integ)["status"] == "never_run"
    finish(s, repo.start_run(s, "github", "list_members", "pull", "manual"), "success", invalid=1)
    assert repo.health(s, integ)["status"] == "degraded"
    for _ in range(2):
        finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "failed")
    finish(s, repo.start_run(s, "github", "list_members", "pull", "test"), "success")  # test runs are ignored
    h = repo.health(s, integ)
    assert h["status"] == "failing" and h["consecutive_failures"] == 2 and h["last_error"]["code"] == "auth_failed"
    repo.set_enabled(s, "github", False)
    assert repo.health(s, repo.get_integration(s, "github"))["status"] == "disabled"


def test_a_failing_action_cannot_hide_behind_a_healthy_one(s):
    """The bug found on real Okta: list_alerts failed, then list_devices succeeded and the connection looked healthy."""
    integ = repo.create_integration(s, GH)
    finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "failed")
    finish(s, repo.start_run(s, "github", "get_user", "lookup", "manual"), "success")  # a later success on ANOTHER action
    h = repo.health(s, integ)
    assert h["status"] == "failing" and h["consecutive_failures"] == 1 and h["last_error"]["code"] == "auth_failed"
    finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "success")  # the failing action recovers
    h = repo.health(s, integ)
    assert h["status"] == "healthy" and h["consecutive_failures"] == 0 and h["last_error"] is None


def test_health_counts_failures_per_action_and_uses_the_worst(s):
    integ = repo.create_integration(s, GH)
    for _ in range(3):
        finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "failed")
    finish(s, repo.start_run(s, "github", "get_user", "lookup", "manual"), "failed")
    finish(s, repo.start_run(s, "github", "get_user", "lookup", "manual"), "success")
    h = repo.health(s, integ)
    assert h["status"] == "failing" and h["consecutive_failures"] == 3  # list_members has 3 in a row, get_user recovered


def test_degraded_when_any_actions_latest_run_quarantined_records(s):
    integ = repo.create_integration(s, GH)
    finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "success")
    finish(s, repo.start_run(s, "github", "get_user", "lookup", "manual"), "success", invalid=1)
    assert repo.health(s, integ)["status"] == "degraded"


def test_a_removed_action_no_longer_counts(s):
    integ = repo.create_integration(s, GH)
    finish(s, repo.start_run(s, "github", "old_action", "pull", "schedule"), "failed")  # an action that is not in the config
    finish(s, repo.start_run(s, "github", "list_members", "pull", "schedule"), "success")
    assert repo.health(s, integ)["status"] == "healthy"
    only_old = repo.create_integration(s, {**GH, "name": "gh2"})
    finish(s, repo.start_run(s, "gh2", "old_action", "pull", "schedule"), "failed")
    assert repo.health(s, only_old)["status"] == "never_run"


def test_engine_state(s):
    assert repo.get_state(s, "github", "list_members") == {}
    repo.set_last_success(s, "github", "list_members", "2026-01-01T09:00:00Z")
    assert repo.get_state(s, "github", "list_members") == {"last_success_at": "2026-01-01T09:00:00Z"}
