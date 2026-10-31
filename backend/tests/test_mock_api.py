"""The mock API behaves as D-9 says, and the engine handles every failure case it serves."""

import pytest
from fastapi.testclient import TestClient

from app.config_loader import load_config
from app.core.settings import REPO_ROOT
from app.engine import RunError, extract_records, fetch_page, map_records
from tests.mock_api.app import app as mock_app

CFG, ISSUES = load_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
AUTH = {"Authorization": "SSWS mock-secret-123"}


@pytest.fixture
def mock(monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    client = TestClient(mock_app)
    client.post("/reset")
    return client


def run(client, action, waits=None):
    body, _, retries, _ = fetch_page(client, CFG, action, sleep=(waits.append if waits is not None else lambda s: None))
    return map_records(CFG, action, extract_records(CFG, action, body), run_id="t", fetched_at="2026-01-01T00:00:00Z"), retries


def test_the_mock_config_is_valid():
    assert not [i for i in ISSUES if i["severity"] == "error"], ISSUES


def test_auth_is_required(mock):
    assert mock.get("/devices").status_code == 401
    assert mock.get("/devices", headers=AUTH).status_code == 200


def test_paging_styles_cover_25_users(mock):
    assert [len(mock.get("/pages/page-number", params={"page": p}, headers=AUTH).json()) for p in (1, 2, 3, 4)] == [10, 10, 5, 0]
    assert mock.get("/pages/offset", params={"offset": 20}, headers=AUTH).json()["meta"]["total"] == 25
    last = mock.get("/pages/cursor", params={"after": "20"}, headers=AUTH).json()
    assert len(last["items"]) == 5 and last["meta"]["next"] is None
    assert "link" in mock.get("/pages/next-link", headers=AUTH).headers
    assert "link" not in mock.get("/pages/next-link", params={"page": 3}, headers=AUTH).headers


def test_engine_maps_each_paging_style(mock):
    for action in ("users_page_number", "users_offset", "users_cursor", "users_next_link"):
        (records, quarantine), _ = run(mock, action)
        assert len(records) == 10 and quarantine == [] and records[0]["email"] == "user1@example.com"


def test_alerts_honour_since(mock):
    (records, _), _ = run(mock, "alerts")
    assert len(records) == 4  # 4 of the 6 alerts are newer than 24 hours
    assert mock.get("/alerts", headers=AUTH).status_code == 400


def test_dirty_data_is_quarantined_and_the_rest_kept(mock):
    (records, quarantine), _ = run(mock, "dirty_users")
    assert len(records) == 3 and [q["reason"] for q in quarantine] == ["missing_required_field", "transform_failed"]


def test_flaky_endpoint_succeeds_after_two_retries(mock):
    waits = []
    (records, _), retries = run(mock, "flaky", waits)
    assert retries == 2 and waits == [1, 2] and len(records) == 5


def test_rate_limit_waits_for_retry_after(mock):
    waits = []
    (records, _), retries = run(mock, "rate_limited", waits)
    assert retries == 1 and waits == [1] and len(records) == 5


@pytest.mark.parametrize(("action", "code"), [("wrong_key", "auth_failed"), ("error_body", "api_error")])
def test_failures_give_the_right_run_error(mock, action, code):
    with pytest.raises(RunError) as exc:
        run(mock, action)
    assert exc.value.code == code and exc.value.retries == 0
