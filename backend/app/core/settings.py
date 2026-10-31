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

# S-12: `<NAME>_FILE=/path` reads the value from a file (a Docker/Kubernetes secret), so `docker inspect` and `ps e` show only
# a path. Allowed for the app's own keys and for SECRET_<NAME>. A value set directly wins over its _FILE.
FILE_VARS = {"ENCRYPTION_KEY", "LLM_API_KEY", "DATABASE_URL", "POSTGRES_PASSWORD", "DASHBOARD_PASSWORD"}


def load_file_values(environ=None) -> list[str]:
    """Fill each NAME from NAME_FILE (when NAME is empty), then drop the NAME_FILE variable. Returns the names filled."""
    import os

    env = os.environ if environ is None else environ
    filled = []
    for var in [v for v in env if v.endswith("_FILE") and len(v) > 5]:
        base = var[:-5]
        if base not in FILE_VARS and not (base.startswith("SECRET_") and not base.endswith("_HOST")):
            continue
        path = env.get(var, "").strip()
        env.pop(var, None)
        if not path or env.get(base, "").strip():
            continue
        try:
            value = Path(path).read_text(encoding="utf-8").strip("\r\n")
        except OSError as exc:
            raise RuntimeError(f"{var} points to {path}, which cannot be read: {exc.strerror}") from None
        if value:
            env[base] = value
            filled.append(base)
    return filled


load_file_values()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    database_url: str = "sqlite:///./dev.db"
    encryption_key: str | None = None

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_from: str | None = None

    llm_api_key: str | None = None
    llm_model: str = "gemini-3.5-flash"
    llm_fallback_model: str | None = "gemini-3.1-flash-lite"  # used when the main model stays overloaded (503) or unreachable

    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
