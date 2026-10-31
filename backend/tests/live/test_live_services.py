"""Calls the REAL services with the tokens in .env. Skipped unless LIVE_TESTS=1.

Run:  cd backend && LIVE_TESTS=1 .venv/bin/pytest tests/live -v
Service settings that are not secrets come from .env for convenience: JIRA_BASE_URL, JIRA_EMAIL, OKTA_DOMAIN.

Known at 8:30pm on 31 Oct: Jira answers 404 for every request (even its public server-info page),
so the site in JIRA_BASE_URL is wrong or has no Jira. Okta has no enrolled device, so devices is empty.
"""

import os
import re

import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine import test_action

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1 to call real services")


def template(name):
    return parse_config((REPO_ROOT / "templates" / f"{name}.yaml").read_text())


def jira():
    cfg = template("jira")
    m = re.match(r"https?://([^.]+)\.atlassian\.net", os.environ.get("JIRA_BASE_URL", ""))
    if not m or not os.environ.get("JIRA_EMAIL"):
        pytest.skip("JIRA_BASE_URL and JIRA_EMAIL are needed")
    cfg["vars"].update(site=m.group(1), email=os.environ["JIRA_EMAIL"])
    return cfg


def okta():
    cfg = template("okta")
    m = re.match(r"https?://([^.]+)\.okta\.com", os.environ.get("OKTA_DOMAIN", ""))
    if not m:
        pytest.skip("OKTA_DOMAIN is needed")
    cfg["vars"]["domain"] = m.group(1)
    return cfg


def check(result, *, need_records=True):
    assert result["ok"], result["notes"]
    if need_records:
        assert result["mapped_sample"], "the first page had no records"


def test_github_get_user():
    check(test_action(template("github"), "get_user", {"username": "octocat"}))


def test_jira_list_users():
    check(test_action(jira(), "list_users"))


def test_okta_list_users():
    check(test_action(okta(), "list_users"))


def test_okta_list_alerts():
    check(test_action(okta(), "list_alerts"))


def test_okta_list_devices():
    check(test_action(okta(), "list_devices"))
