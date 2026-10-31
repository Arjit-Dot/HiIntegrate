import pytest

from tests.helpers import ACCT


@pytest.fixture(autouse=True)
def _env_secrets_belong_to_the_test_account(monkeypatch):
    """D-18: SECRET_<NAME> variables are reachable only by the one account named in ENV_SECRETS_ACCOUNT.
    Most tests put their token in the environment, so they run as that account."""
    monkeypatch.setenv("ENV_SECRETS_ACCOUNT", ACCT)
