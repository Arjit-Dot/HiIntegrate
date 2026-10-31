"""Retries, 429, auth failures, host pinning and the test route, against a fake transport (no network)."""

import json

import httpx
import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine import RunError, extract_records, fetch_page, test_action
from app.engine.http import Policy, send

GH = parse_config((REPO_ROOT / "templates" / "github.yaml").read_text())
PAGE1 = json.loads((REPO_ROOT / "samples" / "github" / "members_page1.json").read_text())


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "ghp_test_value_1234567890")
    monkeypatch.setenv("SECRET_GITHUB_TOKEN_HOST", "api.github.com")


def scripted(*responses):
    """A transport that plays back responses (or raises exceptions) in order, and records requests."""
    seen, queue = [], list(responses)

    def handler(request):
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def call(*responses):
    client, seen = scripted(*responses)
    waits = []
    req = httpx.Request("GET", "https://api.github.com/x")
    try:
        sent = send(client, req, Policy(), sleep=waits.append)
        return sent, waits, seen, None
    except RunError as exc:
        return None, waits, seen, exc


def test_5xx_is_retried_with_backoff_then_succeeds():
    sent, waits, seen, err = call(httpx.Response(500), httpx.Response(503), httpx.Response(200, json=[]))
    assert err is None and sent.retries == 2 and waits == [1, 2] and len(seen) == 3


def test_server_error_after_three_retries():
    _, waits, seen, err = call(*[httpx.Response(502)] * 4)
    assert err.code == "server_error" and err.retries == 3 and waits == [1, 2, 4] and len(seen) == 4


def test_timeout_and_connection_errors_are_retried():
    _, waits, _, err = call(httpx.ReadTimeout("slow"), httpx.Response(200, json=[]))
    assert err is None and waits == [1]
    _, waits, _, err = call(*[httpx.ConnectError("down")] * 4)
    assert err.code == "connection_error" and waits == [1, 2, 4]


def test_wrong_key_fails_at_once():
    _, waits, seen, err = call(httpx.Response(401))
    assert err.code == "auth_failed" and waits == [] and len(seen) == 1


def test_other_4xx_is_not_retried():
    _, waits, _, err = call(httpx.Response(404))
    assert err.code == "client_error" and err.status == 404 and waits == []


def test_429_waits_for_retry_after():
    _, waits, _, err = call(httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=[]))
    assert err is None and waits == [2]


def test_429_without_header_uses_the_backoff():
    _, waits, _, err = call(httpx.Response(429), httpx.Response(200, json=[]))
    assert err is None and waits == [1]


def test_429_asking_for_too_long_fails_clearly():
    _, waits, _, err = call(httpx.Response(429, headers={"Retry-After": "120"}))
    assert err.code == "rate_limited" and waits == []


def test_last_wait_repeats_when_there_are_more_retries():
    p = Policy(max_retries=5)
    assert [p.wait_for(n) for n in range(1, 6)] == [1, 2, 4, 4, 4]


def test_request_has_bearer_token_and_query():
    client, seen = scripted(httpx.Response(200, json=PAGE1))
    fetch_page(client, GH, "list_members")
    req = seen[0]
    assert req.url.host == "api.github.com" and req.url.path == "/orgs/my-org/members"
    assert req.url.params["per_page"] == "100" and req.headers["Authorization"] == "Bearer ghp_test_value_1234567890"
    assert req.headers["X-GitHub-Api-Version"] == "2022-11-28" and req.headers["User-Agent"] == "HiIntegrate/1.0"


def test_a_pinned_secret_is_never_sent_to_another_host():
    evil = {**GH, "base_url": "https://attacker.example.com"}
    client, seen = scripted(httpx.Response(200, json=[]))
    with pytest.raises(RunError) as exc:
        fetch_page(client, evil, "list_members")
    assert exc.value.code == "secret_host_mismatch" and seen == []


def test_records_path_and_error_when():
    alerts = parse_config((REPO_ROOT / "templates" / "generic-alert.yaml").read_text())
    assert extract_records(alerts, "list_alerts", {"items": [1, 2]}) == [1, 2]
    with pytest.raises(RunError) as exc:
        extract_records(alerts, "list_alerts", {"nope": True})
    assert exc.value.code == "bad_response"
    alerts["actions"]["list_alerts"]["error_when"] = {"path": "ok", "equals": False, "message_path": "error"}
    with pytest.raises(RunError) as exc:
        extract_records(alerts, "list_alerts", {"ok": False, "error": "invalid_auth"})
    assert exc.value.code == "api_error" and "invalid_auth" in exc.value.message


def test_test_action_returns_the_test_response_shape():
    client, _ = scripted(httpx.Response(200, json=PAGE1))
    r = test_action(GH, "list_members", client=client)
    assert r["ok"] and r["status_code"] == 200 and r["pages_fetched"] == 1
    assert r["raw_sample"] == PAGE1[0] and r["mapped_sample"]["id"] == "4021" and r["mapped_sample"]["status"] == "active"
    assert set(r) == {"ok", "status_code", "latency_ms", "pages_fetched", "raw_sample", "mapped_sample", "missing_paths", "notes"}


def test_test_action_reports_a_failure_without_raising():
    client, _ = scripted(httpx.Response(401))
    r = test_action(GH, "list_members", client=client)
    assert r["ok"] is False and r["status_code"] == 401 and r["notes"][0].startswith("auth_failed")


def test_lookup_fills_the_input():
    client, seen = scripted(httpx.Response(200, json={"id": 4021, "login": "ada-l", "name": "Ada", "email": "A@B.co"}))
    r = test_action(GH, "get_user", {"username": "ada-l"}, client=client)
    assert seen[0].url.path == "/users/ada-l" and r["mapped_sample"]["email"] == "a@b.co"
