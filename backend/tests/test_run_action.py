"""run_action: every paging style, page-by-page saving, max_pages, host checks on next links, throttling."""

import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config_loader import load_config, parse_config
from app.core.settings import REPO_ROOT
from app.engine import run as run_module
from app.engine import run_action
from tests.mock_api.app import app as mock_app

MOCK, _ = load_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
GH = parse_config((REPO_ROOT / "templates" / "github.yaml").read_text())
PAGES = [json.loads((REPO_ROOT / "samples" / "github" / f"members_page{i}.json").read_text()) for i in (1, 2, 3)]


@pytest.fixture
def mock(monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "ghp_test_value_1234567890")
    monkeypatch.setenv("SECRET_GITHUB_TOKEN_HOST", "api.github.com")
    run_module._last_request.clear()
    client = TestClient(mock_app)
    client.post("/reset")
    return client


def collect():
    saved = []
    return saved, lambda records, quarantine, page: saved.append((page, len(records), len(quarantine)))


@pytest.mark.parametrize("action", ["users_page_number", "users_offset", "users_cursor", "users_next_link"])
def test_every_paging_style_fetches_all_25_users(mock, action):
    saved, on_page = collect()
    r = run_action(MOCK, action, client=mock, on_page=on_page, sleep=lambda s: None)
    assert r.status == "success" and r.records_valid == 25 and r.records_invalid == 0
    assert [n for _, n, _ in saved] == [10, 10, 5]  # saved page by page
    # page_number and offset need one empty (or total-reaching) page to know they are done
    assert r.pages_fetched == {"users_page_number": 4, "users_offset": 3, "users_cursor": 3, "users_next_link": 3}[action]


def test_max_pages_stops_without_failing(mock):
    cfg = copy.deepcopy(MOCK)
    cfg["actions"]["users_cursor"]["pagination"]["max_pages"] = 2
    r = run_action(cfg, "users_cursor", client=mock, sleep=lambda s: None)
    assert r.status == "success" and r.pages_fetched == 2 and r.records_valid == 20 and "max_pages" in r.notes[0]


def test_dirty_data_counts(mock):
    r = run_action(MOCK, "dirty_users", client=mock)
    assert (r.records_pulled, r.records_valid, r.records_invalid) == (5, 3, 2)


def scripted(*responses):
    seen, queue = [], list(responses)

    def handler(request):
        seen.append(str(request.url))
        item = queue.pop(0)
        return item(request) if callable(item) else item

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_failure_on_a_later_page_keeps_the_earlier_pages(mock):
    link = {"Link": '<https://api.github.com/organizations/9001/members?page=2>; rel="next"'}
    client, _ = scripted(httpx.Response(200, json=PAGES[0], headers=link), *[httpx.Response(503)] * 4)
    saved, on_page = collect()
    r = run_action(GH, "list_members", client=client, on_page=on_page, sleep=lambda s: None)
    assert r.status == "failed" and r.error["code"] == "server_error" and r.retries == 3
    assert r.pages_fetched == 1 and saved == [(1, 3, 0)] and "stay saved" in r.notes[0]


def test_a_next_link_to_another_host_is_refused(mock):
    """D-7.6: the host is checked on every request, so a malicious next link cannot take the token."""
    evil = {"Link": '<https://attacker.example.com/steal?page=2>; rel="next"'}
    client, seen = scripted(httpx.Response(200, json=PAGES[0], headers=evil))
    saved, on_page = collect()
    r = run_action(GH, "list_members", client=client, on_page=on_page, sleep=lambda s: None)
    assert r.status == "failed" and r.error["code"] == "secret_host_mismatch"
    assert len(seen) == 1 and "attacker" not in seen[0] and saved == [(1, 3, 0)]


def test_github_next_link_walk_matches_the_samples(mock):
    def page(n, last=False):
        headers = {} if last else {"Link": f'<https://api.github.com/organizations/9001/members?page={n + 1}>; rel="next"'}
        return httpx.Response(200, json=PAGES[n - 1], headers=headers)

    client, seen = scripted(page(1), page(2), page(3, last=True))
    r = run_action(GH, "list_members", client=client, sleep=lambda s: None)
    assert r.status == "success" and r.pages_fetched == 3 and r.records_valid == 8
    assert seen[0].endswith("/orgs/my-org/members?per_page=100") and seen[1].endswith("members?page=2")


def test_lookup_returns_its_record(mock):
    client, _ = scripted(httpx.Response(200, json={"id": 1, "login": "ada", "email": "A@B.co"}))
    r = run_action(GH, "get_user", {"username": "ada"}, client=client)
    assert r.status == "success" and r.mode == "lookup" and r.record["email"] == "a@b.co"


def test_min_interval_throttles_requests(mock):
    cfg = copy.deepcopy(MOCK)
    cfg["actions"]["users_cursor"]["rate_limit"] = {"min_interval_ms": 300}
    waits = []
    run_action(cfg, "users_cursor", client=mock, sleep=waits.append)
    assert len(waits) == 2 and all(0 < w <= 0.3 for w in waits)


def test_next_link_stops_on_an_empty_page_even_if_a_link_is_still_offered(mock):
    """The Okta System Log returns a next link on every page, so an empty page has to end the run."""
    nxt = {"Link": '<https://api.github.com/organizations/9001/members?page=9>; rel="next"'}
    client, seen = scripted(httpx.Response(200, json=PAGES[0], headers=nxt), httpx.Response(200, json=[], headers=nxt), httpx.Response(500))
    r = run_action(GH, "list_members", client=client, sleep=lambda s: None)
    assert r.status == "success" and r.pages_fetched == 2 and r.records_valid == 3 and len(seen) == 2
