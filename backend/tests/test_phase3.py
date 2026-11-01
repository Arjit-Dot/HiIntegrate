"""Phase 3: the timed scheduler, the email alert, incremental sync, remap_records, and a config with no defaults."""

import copy
import threading

import httpx
import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT, get_settings
from app.engine import build_request, remap_records, run_action
from app.scheduler import alerts, runner, timer
from app.storage import make_engine, repo, session_scope
from app.storage.models import Base
from tests.mock_api.app import app as mock_app

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    eng = make_engine(f"sqlite:///{tmp_path}/p3.db")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def mock():
    client = TestClient(mock_app)
    client.post("/reset")
    return client


def service(name="svc", actions=("users_cursor",), schedule=None, **extra) -> dict:
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = name, True
    cfg["actions"] = {a: cfg["actions"][a] for a in actions}
    if schedule:
        for a in cfg["actions"].values():
            a["schedule"] = schedule
    cfg.update(extra)
    return cfg


def add(engine, cfg):
    with session_scope(engine) as s:
        repo.create_integration(s, cfg)


# ---------------------------------------------------------------- the timer

def test_parse_interval():
    assert [timer.parse_interval(t) for t in ("every 10s", "every 5m", "every 2h", "every 1d")] == [10, 300, 7200, 86400]
    with pytest.raises(ValueError):
        timer.parse_interval("hourly")


def test_sync_registers_enabled_pulls_and_follows_the_database(engine):
    sched = BackgroundScheduler(timezone="UTC")  # not started: jobs wait in the list
    add(engine, service("one", ("users_cursor", "get_user"), schedule="every 2m"))
    add(engine, {**service("off"), "enabled": False})
    assert timer.sync(sched, engine) == {"added": ["one:users_cursor"], "updated": [], "removed": []}  # lookups and disabled are skipped
    assert timer.sync(sched, engine) == {"added": [], "updated": [], "removed": []}  # nothing changed, nothing touched

    with session_scope(engine) as s:  # edit in place: the new interval takes effect
        cfg = copy.deepcopy(repo.get_integration(s, "one").config)
        cfg["actions"]["users_cursor"]["schedule"] = "every 30s"
        repo.replace_integration(s, "one", cfg)
    assert timer.sync(sched, engine)["updated"] == ["one:users_cursor"]
    assert sched.get_job("one:users_cursor").trigger.interval.total_seconds() == 30

    with session_scope(engine) as s:
        repo.set_enabled(s, "one", False)
    assert timer.sync(sched, engine)["removed"] == ["one:users_cursor"]
    assert sched.get_jobs() == []

    with session_scope(engine) as s:
        repo.set_enabled(s, "one", True)
        repo.delete_integration(s, "one")
    assert timer.sync(sched, engine) == {"added": [], "updated": [], "removed": []}


def test_a_new_action_runs_at_once_and_a_known_one_waits_an_interval(engine, mock):
    sched = BackgroundScheduler(timezone="UTC")  # not started, so a job only has a next time if we asked for one
    add(engine, service("fresh", ("users_cursor",), schedule="every 1h"))
    timer.sync(sched, engine, client=mock)
    assert sched.get_job("fresh:users_cursor").next_run_time is not None  # never ran: first run at once
    sched.remove_job("fresh:users_cursor")
    runner.run(engine, "fresh", "users_cursor", "schedule", client=mock)
    timer.sync(sched, engine, client=mock)
    assert getattr(sched.get_job("fresh:users_cursor"), "next_run_time", None) is None  # has run: the interval decides, not a restart


def test_a_scheduled_job_runs_the_action_and_saves_records(engine, mock):
    add(engine, service("job", ("users_cursor",)))
    timer.run_job(engine, "job", "users_cursor", client=mock)
    with session_scope(engine) as s:
        runs, _ = repo.list_runs(s, "job")
        assert [(r["trigger"], r["status"], r["records_valid"]) for r in runs] == [("schedule", "success", 25)]


def test_a_run_still_going_is_skipped(engine, mock):
    add(engine, service("busy", ("users_cursor",)))
    with session_scope(engine) as s:
        repo.start_run(s, "busy", "users_cursor", "pull", "manual")  # left `running`
    timer.run_job(engine, "busy", "users_cursor", client=mock)  # must not raise or add a run
    with session_scope(engine) as s:
        assert repo.list_runs(s, "busy")[1] == 1


def test_a_job_for_a_deleted_integration_does_not_crash(engine):
    timer.run_job(engine, "gone", "users_cursor")


def test_two_workers_cannot_run_the_same_action_twice(engine, mock):
    """D-10: the partial unique index makes a second worker safe."""
    add(engine, service("twice", ("users_cursor",)))
    gate, entered = threading.Event(), threading.Event()
    real = run_action

    def slow(*a, **k):
        entered.set()
        gate.wait(5)
        return real(*a, **k)

    first = threading.Thread(target=lambda: timer.run_job(engine, "twice", "users_cursor", client=mock))
    import app.scheduler.runner as r
    r.run_action = slow
    try:
        first.start()
        assert entered.wait(5)
        timer.run_job(engine, "twice", "users_cursor", client=mock)  # skipped
        gate.set()
        first.join(10)
    finally:
        r.run_action = real
    with session_scope(engine) as s:
        assert repo.list_runs(s, "twice")[1] == 1


# ---------------------------------------------------------------- incremental sync (B-1)

def test_incremental_sends_changed_since_only_after_a_success(monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    cfg = service("inc", ("users_cursor",))
    cfg["actions"]["users_cursor"]["incremental"] = {"param": "updated_since", "value": "{{state.last_success_at}}"}
    first = build_request(cfg, "users_cursor", state={})
    assert "updated_since" not in first.request.url.params  # the first run is a full pull
    again = build_request(cfg, "users_cursor", state={"last_success_at": "2026-01-01T09:00:00Z"})
    assert again.request.url.params["updated_since"] == "2026-01-01T09:00:00Z"
    link = build_request(cfg, "users_cursor", state={"last_success_at": "x"}, url="http://localhost:8001/next?page=2")
    assert "updated_since" not in link.request.url.params  # a next-page link carries its own query


def test_last_success_is_kept_per_action_and_sent_next_time(engine):
    cfg = service("inc2", ("users_cursor",))
    cfg["actions"]["users_cursor"]["incremental"] = {"param": "updated_since", "value": "{{state.last_success_at}}"}
    add(engine, cfg)
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"items": [], "meta": {"next": None}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    runner.run(engine, "inc2", "users_cursor", "schedule", client=client)
    runner.run(engine, "inc2", "users_cursor", "schedule", client=client)
    assert "updated_since" not in seen[0] and seen[1]["updated_since"].endswith("Z")
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    runner.run(engine, "inc2", "users_cursor", "schedule", client=ok, sleep=lambda s: None)
    with session_scope(engine) as s:
        before = repo.get_state(s, "inc2", "users_cursor")
    runner.run(engine, "inc2", "users_cursor", "schedule", client=ok, sleep=lambda s: None)
    with session_scope(engine) as s:
        assert repo.get_state(s, "inc2", "users_cursor") == before  # a failure does not move the mark


# ---------------------------------------------------------------- the email alert (D-5.3)

class Outbox:
    def __init__(self, monkeypatch, fail=False):
        self.sent, self.passwords = [], []
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        monkeypatch.setenv("SMTP_PORT", "2525")
        get_settings.cache_clear()

        def send(settings, msg, password):
            if fail:
                raise OSError("smtp is down")
            self.sent.append(msg)
            self.passwords.append(password)

        monkeypatch.setattr(alerts, "send", send)


@pytest.fixture(autouse=True)
def _clear_settings():
    yield
    get_settings.cache_clear()


def failing(name="alerted", **alerts_cfg):
    cfg = service(name, ("wrong_key",))
    cfg["alerts"] = {"to": ["secops@example.com"], **alerts_cfg}
    return cfg


def run_failing(engine, mock, name="alerted", trigger="schedule"):
    return runner.run(engine, name, "wrong_key", trigger, client=mock, sleep=lambda s: None)


def test_one_email_at_the_threshold_and_not_again(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    add(engine, failing())
    for _ in range(5):
        run_failing(engine, mock)
    assert len(box.sent) == 1  # at the 3rd failure, not the 4th or 5th
    msg = box.sent[0]
    assert msg["To"] == "secops@example.com" and "alerted is failing (3 failed runs in a row)" in msg["Subject"]
    body = msg.get_content()
    assert "auth_failed" in body and "wrong_key, schedule" in body and "mock-secret-123" not in body


def test_a_success_resets_the_count_so_a_new_streak_alerts_again(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    cfg = failing(after_failures=2)
    bad = copy.deepcopy(cfg)
    bad["actions"]["wrong_key"]["request"]["path"] = "/wrong-key"
    ok = copy.deepcopy(cfg)
    ok["actions"]["wrong_key"]["request"]["path"] = "/pages/cursor"
    add(engine, bad)
    for _ in range(2):
        run_failing(engine, mock)
    assert len(box.sent) == 1
    with session_scope(engine) as s:
        repo.replace_integration(s, "alerted", ok)
    run_failing(engine, mock)  # succeeds: ends the streak
    with session_scope(engine) as s:
        repo.replace_integration(s, "alerted", bad)
    for _ in range(2):
        run_failing(engine, mock)
    assert len(box.sent) == 2


def test_default_threshold_is_three(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    add(engine, failing())
    run_failing(engine, mock)
    run_failing(engine, mock)
    assert box.sent == []


def test_test_runs_do_not_count_towards_the_alert(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    add(engine, failing(after_failures=1))
    run_failing(engine, mock, trigger="test")
    assert box.sent == []
    run_failing(engine, mock, trigger="manual")
    assert len(box.sent) == 1


def test_no_alerts_block_means_no_email(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    cfg = service("quiet", ("wrong_key",))
    add(engine, cfg)
    for _ in range(4):
        runner.run(engine, "quiet", "wrong_key", "schedule", client=mock, sleep=lambda s: None)
    assert box.sent == []


def test_a_failed_send_is_logged_and_never_fails_the_run(engine, mock, monkeypatch, caplog):
    Outbox(monkeypatch, fail=True)
    add(engine, failing(after_failures=1))
    _, result = run_failing(engine, mock)
    assert result.status == "failed" and result.error["code"] == "auth_failed"  # the run is recorded as it was
    assert any("could not be sent" in r.message for r in caplog.records)


def test_missing_smtp_settings_skip_the_email(engine, mock, monkeypatch, caplog):
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    monkeypatch.setattr(get_settings(), "smtp_from", None)
    add(engine, failing(after_failures=1))
    run_failing(engine, mock)  # must not raise


def test_the_smtp_password_is_sent_only_to_its_pinned_host(engine, mock, monkeypatch):
    box = Outbox(monkeypatch)
    monkeypatch.setenv("SECRET_SMTP_PASSWORD", "smtp-pass-123")
    monkeypatch.setenv("SECRET_SMTP_PASSWORD_HOST", "smtp.example.com")
    add(engine, failing(after_failures=1))
    run_failing(engine, mock)
    assert box.passwords == ["smtp-pass-123"]

    box.sent.clear(), box.passwords.clear()
    monkeypatch.setenv("SECRET_SMTP_PASSWORD_HOST", "evil.example.net")
    add(engine, failing("other", after_failures=1))
    run_failing(engine, mock, "other")
    assert box.sent == [] and box.passwords == []  # refused: nothing sent anywhere


def test_the_port_picks_the_connection_kind(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, **kw):
            calls.append(("plain", port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self, **kw):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u))

        def send_message(self, m):
            calls.append(("send",))

    class FakeSSL(FakeSMTP):
        def __init__(self, host, port, **kw):
            calls.append(("ssl", port))

    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(alerts.smtplib, "SMTP_SSL", FakeSSL)
    msg = alerts.build_message(SimpleSettings(), "x", "a", "schedule", 3, None, "t", ["a@example.com"])
    for port in (587, 465, 25):
        calls.clear()
        alerts.send(SimpleSettings(port=port), msg, "pw")
        assert calls[0] == (("ssl", 465) if port == 465 else ("plain", port))
        assert (("starttls",) in calls) == (port == 587)


class SimpleSettings:
    smtp_host, smtp_from, smtp_username = "smtp.example.com", "alerts@example.com", "user"

    def __init__(self, port=587):
        self.smtp_port = port


# ---------------------------------------------------------------- remap_records (D-14)

def test_remap_records_is_a_dry_run_with_a_proposed_config():
    cfg = service("remap", ("dirty_users",))
    action = cfg["actions"]["dirty_users"]
    raws = [{"id": "1", "name": "Ada", "mail": "ada@example.com", "state": "active"}, {"id": "2", "mail": "bob@example.com"}]
    before = remap_records(cfg, "dirty_users", raws)
    fixed = copy.deepcopy(cfg)
    fixed["actions"]["dirty_users"]["map"] = {**action["map"], "email": "mail"}
    after = remap_records(fixed, "dirty_users", raws)
    assert len(before[0]) + len(before[1]) == 2 and len(after[0]) + len(after[1]) == 2
    assert all(r["source"] == "remap" for r in after[0])
    assert all(q["run_id"] == "remap" and q["source"] == "remap" for q in after[1])


def test_remap_records_rescues_records_with_a_fixed_path():
    cfg = service("remap2", ("dirty_users",))
    cfg["actions"]["dirty_users"]["map"]["id"] = "wrong_id"
    raws = [{"id": "1", "name": "Ada", "email": "ada@example.com", "status": "active"}]
    records, quarantine = remap_records(cfg, "dirty_users", raws)
    assert records == [] and quarantine[0]["reason"] == "missing_required_field" and quarantine[0]["field"] == "id"
    cfg["actions"]["dirty_users"]["map"]["id"] = "id"
    records, quarantine = remap_records(cfg, "dirty_users", raws)
    assert len(records) == 1 and quarantine == []


def test_remap_records_touches_no_network_and_no_database(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("remap_records must not use the network")

    monkeypatch.setattr(httpx.Client, "send", boom)
    cfg = service("remap3", ("dirty_users",))
    assert remap_records(cfg, "dirty_users", []) == ([], [])


# ---------------------------------------------------------------- a config with no defaults

def test_a_config_with_no_defaults_runs_with_built_in_values(mock, monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    cfg = service("bare", ("users_cursor",))
    cfg.pop("defaults", None)
    r = run_action(cfg, "users_cursor", client=mock, sleep=lambda s: None)
    assert r.status == "success" and r.records_valid == 25


def test_an_empty_first_page_is_a_success_with_nothing_saved(engine):
    add(engine, service("empty", ("users_cursor",)))
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": [], "meta": {"next": None}})))
    _, result = runner.run(engine, "empty", "users_cursor", "schedule", client=client)
    assert (result.status, result.pages_fetched, result.records_pulled) == ("success", 1, 0)


# ---------------------------------------------------------------- alert state for the dashboard

def alert_state(engine, name="alerted"):
    with session_scope(engine) as s:
        return repo.alert_state(s, repo.get_integration(s, name))


def test_no_alerts_block_means_no_alert_state(engine):
    add(engine, service("quiet", ("wrong_key",)))
    assert alert_state(engine, "quiet") is None


def test_the_rule_is_shown_before_anything_has_happened(engine):
    add(engine, failing(after_failures=2))
    assert alert_state(engine) == {"after_failures": 2, "to": ["secops@example.com"], "last_attempt": None}


def test_a_sent_alert_is_remembered_until_the_next_success(engine, mock, monkeypatch):
    Outbox(monkeypatch)
    add(engine, failing(after_failures=2))
    run_failing(engine, mock)
    assert alert_state(engine)["last_attempt"] is None  # one failure: not due yet
    run_failing(engine, mock)
    last = alert_state(engine)["last_attempt"]
    assert (last["action"], last["outcome"], last["failures"], last["message"]) == ("wrong_key", "sent", 2, None) and last["at"].endswith("Z")
    run_failing(engine, mock)  # still failing: no second email, and the record of the first stays
    assert alert_state(engine)["last_attempt"]["outcome"] == "sent"

    ok = copy.deepcopy(failing(after_failures=2))
    ok["actions"]["wrong_key"]["request"]["path"] = "/pages/cursor"
    with session_scope(engine) as s:
        repo.replace_integration(s, "alerted", ok)
    run_failing(engine, mock)  # succeeds: the streak ends
    assert alert_state(engine)["last_attempt"] is None


def test_a_failed_send_is_remembered_with_the_reason_and_never_the_password(engine, mock, monkeypatch):
    Outbox(monkeypatch, fail=True)
    monkeypatch.setenv("SECRET_SMTP_PASSWORD", "smtp-pass-123")
    monkeypatch.setattr(alerts, "send", lambda settings, msg, password: (_ for _ in ()).throw(OSError(f"login refused for smtp-pass-123 at {settings.smtp_host}")))
    monkeypatch.setenv("SECRET_SMTP_PASSWORD_HOST", "smtp.example.com")
    add(engine, failing(after_failures=1))
    _, result = run_failing(engine, mock)
    assert result.status == "failed"
    last = alert_state(engine)["last_attempt"]
    assert last["outcome"] == "failed" and "login refused" in last["message"] and "smtp-pass-123" not in last["message"] and "[redacted]" in last["message"]


def test_missing_smtp_settings_are_remembered_as_not_configured(engine, mock, monkeypatch):
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_PORT"):
        monkeypatch.delenv(name, raising=False)
    from app.core.settings import Settings

    monkeypatch.setattr(alerts, "get_settings", lambda: Settings(_env_file=None, smtp_host=None, smtp_from=None))
    add(engine, failing(after_failures=1))
    run_failing(engine, mock)
    last = alert_state(engine)["last_attempt"]
    assert last["outcome"] == "not_configured" and "SMTP" in last["message"]


def test_a_test_run_neither_alerts_nor_clears_the_state(engine, mock, monkeypatch):
    Outbox(monkeypatch)
    add(engine, failing(after_failures=1))
    run_failing(engine, mock, trigger="manual")
    runner.run(engine, "alerted", "wrong_key", "test", client=mock, sleep=lambda s: None)
    assert alert_state(engine)["last_attempt"]["outcome"] == "sent"


def test_deleting_an_integration_clears_its_alert_record(engine, mock, monkeypatch):
    Outbox(monkeypatch)
    add(engine, failing(after_failures=1))
    run_failing(engine, mock)
    with session_scope(engine) as s:
        repo.delete_integration(s, "alerted")
    add(engine, failing(after_failures=1))
    assert alert_state(engine)["last_attempt"] is None


def test_the_dashboard_routes_carry_the_alert_state(engine, mock, monkeypatch):
    from app.api.deps import engine_dep
    from app.main import create_app

    Outbox(monkeypatch)
    add(engine, failing(after_failures=1))
    add(engine, service("quiet", ("wrong_key",)))
    run_failing(engine, mock)
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    api = TestClient(app)
    one = api.get("/api/v1/integrations/alerted").json()
    assert one["alert"]["after_failures"] == 1 and one["alert"]["last_attempt"]["outcome"] == "sent"
    listed = {i["name"]: i for i in api.get("/api/v1/integrations").json()["items"]}
    assert listed["alerted"]["alert"]["last_attempt"]["outcome"] == "sent" and listed["quiet"]["alert"] is None
