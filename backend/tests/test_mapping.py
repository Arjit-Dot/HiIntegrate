"""Acceptance test: the engine's mapper reproduces docs/examples/expected/ from samples/ (roadmap Phase 2)."""

import copy
import json

import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine import map_record, map_records
from app.engine.mapping import to_iso

FETCHED, QUARANTINED, RUN = "2026-01-01T09:05:00Z", "2026-01-01T09:05:03Z", "run-0001"


def cfg(name):
    return parse_config((REPO_ROOT / "templates" / f"{name}.yaml").read_text())


def sample(path):
    return json.loads((REPO_ROOT / "samples" / path).read_text())


def expected(name):
    return json.loads((REPO_ROOT / "docs" / "examples" / "expected" / f"{name}.json").read_text())


def run(c, action, pages):
    records = c["actions"][action].get("records_path", "@")
    raws = [r for p in pages for r in (p if records == "@" else p[records])]
    return map_records(c, action, raws, run_id=RUN, fetched_at=FETCHED, quarantined_at=QUARANTINED)


LISTS = {
    "github-members": ("github", "list_members", [f"github/members_page{i}.json" for i in (1, 2, 3)]),
    "jira-users": ("jira", "list_users", ["jira/users_search_page1.json", "jira/users_search_page2.json", "jira/users_search_page3_empty.json"]),
    "okta-users": ("okta", "list_users", ["okta/users.json"]),
    "okta-devices": ("okta", "list_devices", ["okta/devices.json"]),
    "okta-alerts": ("okta", "list_alerts", ["okta/logs.json"]),
}
LOOKUPS = {
    "github-get-user": ("github", "get_user", "github/get_user.json"),
    "jira-get-user": ("jira", "get_user", "jira/get_user.json"),
    "okta-get-user": ("okta", "get_user", "okta/get_user.json"),
    "okta-get-device": ("okta", "get_device", "okta/get_device.json"),
}


@pytest.mark.parametrize("name", LISTS)
def test_list_mapping_matches_expected(name):
    service, action, pages = LISTS[name]
    records, quarantine = run(cfg(service), action, [sample(p) for p in pages])
    assert quarantine == []
    assert records == expected(name)


@pytest.mark.parametrize("name", LOOKUPS)
def test_lookup_mapping_matches_expected(name):
    service, action, path = LOOKUPS[name]
    assert map_record(cfg(service), action, sample(path), run_id=RUN, fetched_at=FETCHED)["record"] == expected(name)


def test_quarantine_matches_expected():
    q = []
    for service, action, path in [("github", "list_members", "github/members_bad_record.json"), ("jira", "list_users", "jira/users_search_bad_record.json"),
                                  ("okta", "list_users", "okta/users_bad_record.json"), ("okta", "list_alerts", "okta/logs_bad_record.json")]:
        q += run(cfg(service), action, [sample(path)])[1]
    strict = copy.deepcopy(cfg("okta"))
    del strict["actions"]["list_users"]["map"]["status"]["default"]
    q.append(map_record(strict, "list_users", {"id": "00u1x", "status": "BANNED", "profile": {"login": "x@acme.com", "email": "x@acme.com"}},
                        run_id=RUN, fetched_at=FETCHED, quarantined_at=QUARANTINED)["quarantine"])
    assert q == expected("quarantine")


def test_datetime_transform():
    assert to_iso(1767225600) == "2026-01-01T00:00:00Z"            # epoch seconds
    assert to_iso(1767225600123) == "2026-01-01T00:00:00.123Z"     # epoch milliseconds
    assert to_iso("2026-01-01T09:00:00.000Z") == "2026-01-01T09:00:00Z"
    assert to_iso("2026-01-01T14:30:00+05:30") == "2026-01-01T09:00:00Z"


def test_path_that_is_not_valid_jmespath_is_quarantined_not_a_crash():
    """An AI draft can write `a + ' ' + b`, which is not JMESPath. The record is quarantined (transform_failed), the run does not crash."""
    cfg = {"name": "t", "actions": {"a": {"mode": "pull", "target_schema": "user", "required": ["id"],
                                          "map": {"id": "id", "name": "profile.firstName + ' ' + profile.lastName"}}}}
    out = map_record(cfg, "a", {"id": "1", "profile": {"firstName": "A", "lastName": "B"}}, run_id="r", fetched_at="2026-01-01T00:00:00Z")
    assert out["quarantine"]["reason"] == "transform_failed" and out["quarantine"]["field"] == "name"
