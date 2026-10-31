"""A blank line in .env (`SMTP_PORT=`) must mean "not set", not crash the backend at startup.

`docker compose up` passes every .env line to the containers, blank ones included.
"""

from app.core.settings import Settings


def test_blank_values_count_as_not_set(monkeypatch):
    for name in ("SMTP_PORT", "SMTP_HOST", "SMTP_FROM", "LLM_API_KEY", "ENCRYPTION_KEY", "DATABASE_URL", "LLM_MODEL"):
        monkeypatch.setenv(name, "")
    s = Settings(_env_file=None)
    assert s.smtp_port is None
    assert s.smtp_host is None
    assert s.llm_api_key is None
    assert s.encryption_key is None
    assert s.database_url == "sqlite:///./dev.db"   # the default, not an empty URL
    assert s.llm_model == "gemini-3.5-flash"


def test_a_real_value_is_still_used(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    s = Settings(_env_file=None)
    assert s.smtp_port == 2525
    assert s.database_url.startswith("postgresql+psycopg://")
