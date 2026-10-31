import pytest

from tests.helpers import ACCT


@pytest.fixture(autouse=True)
def _env_secrets_belong_to_the_test_account(monkeypatch):
    """D-18: SECRET_<NAME> variables are reachable only by the one account named in ENV_SECRETS_ACCOUNT.
    Most tests put their token in the environment, so they run as that account."""
    monkeypatch.setenv("ENV_SECRETS_ACCOUNT", ACCT)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """S-9: the limiter is per process, and every test acts as the same account. Start each test with empty counters."""
    from app import ratelimit

    ratelimit.limiter.reset()
