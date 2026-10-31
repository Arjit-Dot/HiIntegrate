import logging

import pytest

from app.secrets import Secret, SecretHostMismatch, SecretNotFound, check_host, get_secret, list_secrets


@pytest.fixture
def env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("SECRET_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "ghp_example_value_123")
    monkeypatch.setenv("SECRET_GITHUB_TOKEN_HOST", "API.GitHub.com")
    monkeypatch.setenv("SECRET_JIRA_TOKEN", "jira_example_value_456")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    return monkeypatch


def test_reads_secret_by_name_and_pinned_host(env):
    s = get_secret("github_token")
    assert s.value == "ghp_example_value_123" and s.host == "api.github.com"
    assert get_secret("jira_token").host is None


def test_never_prints_the_value(env):
    s = get_secret("github_token")
    assert "ghp_example_value_123" not in repr(s) and "ghp_example_value_123" not in str(s)


def test_only_secret_prefixed_variables_are_reachable(env):
    with pytest.raises(SecretNotFound):
        get_secret("database_url")  # the app's own key is not a secret a config can use


def test_missing_and_badly_named_secrets(env):
    with pytest.raises(SecretNotFound, match="SECRET_NOPE"):
        get_secret("nope")
    with pytest.raises(SecretNotFound):
        get_secret("example-key.not-a-name/123+xyz")


def test_bad_companion_host(env):
    env.setenv("SECRET_JIRA_TOKEN_HOST", "https://acme.atlassian.net/x")
    with pytest.raises(SecretNotFound, match="not a valid host"):
        get_secret("jira_token")


def test_host_pinning(env):
    s = get_secret("github_token")
    check_host(s, "api.github.com")
    check_host(s, "API.GITHUB.COM")
    with pytest.raises(SecretHostMismatch, match="pinned to api.github.com.*attacker.example.com"):
        check_host(s, "attacker.example.com")
    with pytest.raises(SecretHostMismatch):
        check_host(s, "github.com")  # subdomains and parents are different hosts


def test_unpinned_secret_is_allowed_with_one_warning(env, caplog):
    s = Secret(name="okta_token", value="x" * 10)
    with caplog.at_level(logging.WARNING, logger="app.secrets"):
        check_host(s, "acme.okta.com")
        check_host(s, "acme.okta.com")
    assert sum("not pinned" in r.getMessage() for r in caplog.records) == 1


def test_list_secrets_has_names_and_hosts_only(env):
    items = list_secrets()
    assert {"name": "github_token", "set": True, "host": "api.github.com", "updated_at": None} in items
    assert all("value" not in i for i in items)
    assert "ghp_example_value_123" not in str(items)
