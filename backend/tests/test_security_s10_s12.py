"""S-10 retention, S-11 key rotation, S-12 file-based secrets."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import cli
from app.api.deps import engine_dep
from app.core.settings import load_file_values
from app.main import create_app
from app.scheduler import retention
from app.secrets import SecretError, get_secret, rotate_keys, set_secret
from app.storage import make_engine, repo, session_factory
from app.storage.models import Audit, Base, Quarantine, Run, Secret
from tests.helpers import ACCT, signed_in

V1 = "/api/v1"


@pytest.fixture
def engine(tmp_path):
    e = make_engine(f"sqlite:///{tmp_path}/s.db")
    Base.metadata.create_all(e)
    return e


@pytest.fixture
def s(engine):
    session = session_factory(engine)()
    yield session
    session.close()


# --- S-11 --------------------------------------------------------------------------------------------------------

def test_rotation_reencrypts_with_the_first_key_and_the_old_key_can_go(s, monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", old)
    set_secret(s, ACCT, "api_token", "tok-value-123456", "example.com")
    before = s.get(Secret, (ACCT, "api_token")).ciphertext

    monkeypatch.setenv("ENCRYPTION_KEY", f"{new},{old}")  # new first: still readable, new writes use the new key
    assert get_secret("api_token", s, ACCT).value == "tok-value-123456"
    assert rotate_keys(s) == 1
    assert s.get(Secret, (ACCT, "api_token")).ciphertext != before

    monkeypatch.setenv("ENCRYPTION_KEY", new)  # the old key is gone and nothing is lost
    assert get_secret("api_token", s, ACCT).value == "tok-value-123456"
    monkeypatch.setenv("ENCRYPTION_KEY", old)
    with pytest.raises(SecretError):
        get_secret("api_token", s, ACCT)


def test_rotation_changes_nothing_if_a_secret_cannot_be_opened(s, monkeypatch):
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", k1)
    set_secret(s, ACCT, "one_token", "value-one-123456", "example.com")
    before = s.get(Secret, (ACCT, "one_token")).ciphertext
    monkeypatch.setenv("ENCRYPTION_KEY", k2)  # k1 is missing from the list
    with pytest.raises(SecretError, match="nothing was changed"):
        rotate_keys(s)
    assert s.get(Secret, (ACCT, "one_token")).ciphertext == before


def test_a_bad_key_in_the_list_is_refused(s, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", f"{Fernet.generate_key().decode()},not-a-key")
    with pytest.raises(SecretError, match="not a valid key"):
        set_secret(s, ACCT, "x_token", "value-123456", "example.com")


def test_the_cli_rotates(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{tmp_path}/cli.db"
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core.settings import get_settings
    from app.storage import db

    get_settings.cache_clear()
    db.get_engine.cache_clear()
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", old)
    with db.session_scope() as session:
        set_secret(session, ACCT, "cli_token", "value-123456", "example.com")
    monkeypatch.setenv("ENCRYPTION_KEY", f"{new},{old}")
    assert cli.main(["rotate-keys"]) == 0
    assert "Re-encrypted 1 secret" in capsys.readouterr().out
    get_settings.cache_clear()
    db.get_engine.cache_clear()


# --- S-12 --------------------------------------------------------------------------------------------------------

def test_a_file_fills_the_value_and_the_path_variable_is_dropped(tmp_path):
    f = tmp_path / "key"
    f.write_text("file-value-abc\n")
    env = {"LLM_API_KEY_FILE": str(f), "SECRET_GITHUB_TOKEN_FILE": str(f)}
    assert sorted(load_file_values(env)) == ["LLM_API_KEY", "SECRET_GITHUB_TOKEN"]
    assert env == {"LLM_API_KEY": "file-value-abc", "SECRET_GITHUB_TOKEN": "file-value-abc"}  # no *_FILE left, so it is not listed as a secret


def test_a_value_set_directly_wins_over_its_file(tmp_path):
    f = tmp_path / "key"
    f.write_text("from-file")
    env = {"ENCRYPTION_KEY": "direct", "ENCRYPTION_KEY_FILE": str(f)}
    assert load_file_values(env) == [] and env["ENCRYPTION_KEY"] == "direct"


def test_only_known_names_may_come_from_files(tmp_path):
    f = tmp_path / "x"
    f.write_text("v")
    env = {"PATH_FILE": str(f), "SECRET_X_HOST_FILE": str(f), "HOME_FILE": str(f)}
    assert load_file_values(env) == [] and "PATH" not in env and "HOME" not in env


def test_an_unreadable_file_says_which_variable(tmp_path):
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY_FILE points to .*missing"):
        load_file_values({"ENCRYPTION_KEY_FILE": str(tmp_path / "missing")})


# --- S-10 --------------------------------------------------------------------------------------------------------

def _run(account, action, status, days_ago, integration="svc"):
    when = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Run(account=account, integration=integration, action=action, mode="pull", trigger="schedule", status=status, started_at=when,
               finished_at=None if status == "running" else when)


def test_purge_keeps_running_runs_and_the_newest_finished_run_of_each_action(s):
    s.add_all([_run("a", "list", "success", 200), _run("a", "list", "success", 150), _run("a", "list", "failed", 100),
               _run("a", "list", "success", 1), _run("a", "other", "success", 400), _run("a", "third", "running", 300)])
    s.flush()
    deleted = repo.purge_runs(s, repo.cutoff_iso(90))
    left = sorted((r.action, r.status) for r in s.query(Run).all())
    assert deleted == 3
    assert left == [("list", "success"), ("other", "success"), ("third", "running")]  # newest of each action, and the running one


def test_purge_for_one_account_leaves_the_others(s):
    s.add_all([_run("a", "x", "success", 300), _run("a", "x", "success", 200), _run("b", "x", "success", 300), _run("b", "x", "success", 200)])
    s.flush()
    assert repo.purge_runs(s, repo.cutoff_iso(90), "a") == 1
    assert s.query(Run).filter_by(account="a").count() == 1 and s.query(Run).filter_by(account="b").count() == 2


def test_quarantine_and_audit_are_purged_by_age(s):
    old = (datetime.now(UTC) - timedelta(days=500)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = repo.now_iso()
    for when in (old, new):
        s.add(Quarantine(account="a", source="x", action="l", target_schema="user", run_id="run-1", raw={}, reason="invalid_value", field="id", created_at=when))
        s.add(Audit(account="a", at=when, event="secret.set", target="t"))
    s.flush()
    assert repo.purge_quarantine(s, repo.cutoff_iso(90)) == 1 and repo.purge_audit(s, repo.cutoff_iso(365)) == 1
    assert s.query(Quarantine).count() == 1 and s.query(Audit).count() == 1


def test_the_retention_job_uses_the_settings_and_zero_keeps_everything(engine, monkeypatch):
    with session_factory(engine)() as session:
        session.add_all([_run("a", "x", "success", 300), _run("a", "x", "success", 200)])
        session.commit()
    monkeypatch.setenv("RETENTION_RUNS_DAYS", "0")
    assert retention.purge_old(engine)["runs"] == 0
    monkeypatch.setenv("RETENTION_RUNS_DAYS", "30")
    assert retention.purge_old(engine)["runs"] == 1
    monkeypatch.setenv("RETENTION_RUNS_DAYS", "junk")
    assert retention.days("RETENTION_RUNS_DAYS") == 90


@pytest.fixture
def api(engine):
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    return signed_in(TestClient(app), ACCT), signed_in(TestClient(app), "bob")


def test_the_delete_routes_remove_only_my_old_rows_and_are_audited(engine, api):
    mine, theirs = api
    with session_factory(engine)() as session:
        session.add_all([_run(ACCT, "x", "success", 300), _run(ACCT, "x", "success", 200), _run("bob", "x", "success", 300), _run("bob", "x", "success", 200)])
        old = (datetime.now(UTC) - timedelta(days=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
        session.add(Quarantine(account=ACCT, source="x", action="l", target_schema="user", run_id="run-1", raw={}, reason="invalid_value", field="id", created_at=old))
        session.commit()
    assert mine.delete(f"{V1}/runs", params={"older_than_days": 90}).json() == {"deleted": 1}
    assert mine.delete(f"{V1}/quarantine", params={"older_than_days": 90}).json() == {"deleted": 1}
    assert theirs.get(f"{V1}/runs").json()["total"] == 2  # bob's runs are untouched
    events = [e["event"] for e in mine.get(f"{V1}/audit").json()["items"]]
    assert "runs.purged" in events and "quarantine.purged" in events


def test_the_delete_routes_need_a_sign_in_and_a_valid_number(api):
    mine, _ = api
    assert TestClient(mine.app).delete(f"{V1}/runs", params={"older_than_days": 1}).status_code == 401
    assert mine.delete(f"{V1}/runs").status_code == 400
    assert mine.delete(f"{V1}/runs", params={"older_than_days": -1}).status_code == 400
