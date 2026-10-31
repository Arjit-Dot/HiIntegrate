"""The encrypted secret store (D-7.1, D-7.5, D-7.6): Fernet, a required host, store before environment."""

import pytest
from cryptography.fernet import Fernet

from app.secrets import (
    SecretError,
    SecretNotFound,
    StoreUnavailable,
    get_secret,
    list_secrets,
    set_secret,
    store_available,
)
from app.storage import make_engine, session_factory
from app.storage.models import Base
from app.storage.models import Secret as SecretRow


@pytest.fixture
def s(tmp_path, monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("SECRET_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    session = session_factory(engine)()
    yield session
    session.close()


def test_a_stored_secret_is_encrypted_and_comes_back(s):
    set_secret(s, "github_token", "ghp_secret_value_12345", "API.GitHub.com")
    row = s.get(SecretRow, "github_token")
    assert "ghp_secret_value_12345" not in row.ciphertext and row.host == "api.github.com"
    got = get_secret("github_token", s)
    assert got.value == "ghp_secret_value_12345" and got.host == "api.github.com"
    assert "ghp_secret_value_12345" not in repr(got)


def test_setting_again_replaces_value_and_host(s):
    set_secret(s, "okta_token", "first_value_111111", "acme.okta.com")
    set_secret(s, "okta_token", "second_value_22222", "contoso.okta.com")
    got = get_secret("okta_token", s)
    assert got.value == "second_value_22222" and got.host == "contoso.okta.com"


def test_the_store_wins_over_the_environment(s, monkeypatch):
    monkeypatch.setenv("SECRET_JIRA_TOKEN", "from_the_environment")
    assert get_secret("jira_token", s).value == "from_the_environment"       # falls back when not stored
    set_secret(s, "jira_token", "from_the_store_value", "acme.atlassian.net")
    assert get_secret("jira_token", s).value == "from_the_store_value"       # store first
    assert get_secret("jira_token").value == "from_the_environment"          # no session: environment only


def test_a_host_is_required_and_must_be_bare(s):
    for bad in ("", "https://api.github.com", "api.github.com/x", "api.github.com:443", "with space.com"):
        with pytest.raises(SecretError, match="bare host"):
            set_secret(s, "x_token", "value_123456", bad)
    with pytest.raises(SecretError, match="needs a value"):
        set_secret(s, "x_token", "", "api.github.com")
    with pytest.raises(SecretNotFound):
        set_secret(s, "bad name!", "value_123456", "api.github.com")


def test_listing_shows_names_hosts_and_times_never_values(s, monkeypatch):
    monkeypatch.setenv("SECRET_OLD_ONE", "env_value_123456")
    set_secret(s, "github_token", "ghp_secret_value_12345", "api.github.com")
    items = {i["name"]: i for i in list_secrets(s)}
    assert items["github_token"]["host"] == "api.github.com" and items["github_token"]["updated_at"]
    assert items["old_one"] == {"name": "old_one", "set": True, "host": None, "updated_at": None}
    assert "ghp_secret_value_12345" not in str(items)


def test_the_wrong_key_says_so_without_leaking(s, monkeypatch):
    set_secret(s, "github_token", "ghp_secret_value_12345", "api.github.com")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(SecretError, match="not the key it was stored with") as exc:
        get_secret("github_token", s)
    assert "ghp_secret_value_12345" not in str(exc.value)


def test_no_key_means_the_store_is_unavailable(s, monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY")
    assert store_available() is False
    with pytest.raises(StoreUnavailable, match="ENCRYPTION_KEY is not set"):
        set_secret(s, "x_token", "value_123456", "api.github.com")
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-key")
    assert store_available() is False
