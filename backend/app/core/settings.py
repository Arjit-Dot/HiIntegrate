"""Settings read from the environment and the repo-root .env file (D-10, D-12).

Values here are never logged. Service tokens are not settings: they are read by name
through app.secrets (SECRET_<NAME>), never from this object.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# Put .env into the process environment, so app.secrets can read SECRET_<NAME> and the
# log redaction knows every secret value. Variables already set in the environment win.
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    encryption_key: str | None = None

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_from: str | None = None

    llm_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash"

    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
