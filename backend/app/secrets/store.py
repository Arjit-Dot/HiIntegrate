import logging
import os
import re
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("app.secrets")

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")  # D-7.3, the same rule as the config schema
HOST_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
PREFIX = "SECRET_"
HOST_SUFFIX = "_HOST"


class SecretError(Exception):
    """Base class. Messages name the secret, never its value."""


class SecretNotFound(SecretError):
    pass


class SecretHostMismatch(SecretError):
    """The request would send a secret to a host it is not pinned to (run error: secret_host_mismatch)."""

    code = "secret_host_mismatch"


@dataclass(frozen=True)
class Secret:
    name: str
    value: str = field(repr=False)
    host: str | None = None  # the pinned host, or None if the secret is not pinned

    def __str__(self) -> str:
        return f"Secret({self.name}, host={self.host or 'unpinned'})"


def _env_name(name: str) -> str:
    return PREFIX + name.upper()


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise SecretNotFound("a secret name must be letters, digits and underscores, up to 64 characters")


class StoreUnavailable(SecretError):
    """The encrypted store cannot be used (no ENCRYPTION_KEY, or it is not a valid key)."""


def _fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise StoreUnavailable("ENCRYPTION_KEY is not set, so the encrypted secret store is not available")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise StoreUnavailable("ENCRYPTION_KEY is not a valid key (it must be 32 url-safe base64 bytes)") from None


def store_available() -> bool:
    try:
        _fernet()
        return True
    except StoreUnavailable:
        return False


def _check_host_value(host: str) -> str:
    host = (host or "").strip().lower()
    if not HOST_PATTERN.fullmatch(host):
        raise SecretError("host must be a bare host such as api.github.com (no scheme, path or port)")
    return host


def set_secret(session, name: str, value: str, host: str) -> None:
    """D-7.1, D-7.6: store the value encrypted, with the one host it may be sent to. A second call replaces both."""
    from datetime import UTC, datetime

    from app.storage.models import Secret as SecretRow

    _check_name(name)
    if not value:
        raise SecretError("a secret needs a value")
    host = _check_host_value(host)
    ciphertext = _fernet().encrypt(value.encode()).decode()
    row = session.get(SecretRow, name.lower()) or SecretRow(name=name.lower())
    row.ciphertext, row.host = ciphertext, host
    row.updated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.add(row)
    session.flush()


def _stored(session, name: str) -> Secret | None:
    from app.storage.models import Secret as SecretRow

    row = session.get(SecretRow, name.lower())
    if row is None:
        return None
    try:
        value = _fernet().decrypt(row.ciphertext.encode()).decode()
    except InvalidToken:
        raise SecretError(f"secret {name} cannot be decrypted: ENCRYPTION_KEY is not the key it was stored with. Enter the value again") from None
    return Secret(name=name, value=value, host=row.host)


def get_secret(name: str, session=None) -> Secret:
    """D-8 handoff. With a session the encrypted store is checked first, then the environment (D-7.1).
    Raises SecretNotFound if neither has it."""
    _check_name(name)
    if session is not None:
        stored = _stored(session, name)
        if stored is not None:
            return stored
    return _env_secret(name)


def _env_secret(name: str) -> Secret:
    """The environment source: SECRET_<NAME> and the optional SECRET_<NAME>_HOST (Phase 1, and the fallback after it)."""
    _check_name(name)
    value = os.environ.get(_env_name(name), "")
    if not value:
        raise SecretNotFound(f"secret {name} is not set (expected {_env_name(name)} in the environment)")
    host = os.environ.get(_env_name(name) + HOST_SUFFIX, "").strip().lower() or None
    if host and not HOST_PATTERN.fullmatch(host):
        raise SecretNotFound(f"{_env_name(name)}{HOST_SUFFIX} is not a valid host (use a bare host such as api.github.com)")
    return Secret(name=name, value=value, host=host)


_warned_unpinned: set[str] = set()


def check_host(secret: Secret, request_host: str) -> None:
    """Refuse to send a pinned secret to any other host (D-7.6). Call before EVERY request,
    including next-page links and redirects. An unpinned secret is allowed with a warning."""
    host = (request_host or "").lower()
    if secret.host is None:
        if secret.name not in _warned_unpinned:
            _warned_unpinned.add(secret.name)
            log.warning("secret %s is not pinned to a host; set %s%s", secret.name, _env_name(secret.name), HOST_SUFFIX)
        return
    if host != secret.host:
        raise SecretHostMismatch(
            f"refused: secret {secret.name} is pinned to {secret.host}, but this request goes to {host or 'an unknown host'}. Nothing was sent."
        )


def list_secrets(session=None) -> list[dict]:
    """Names, whether each is set, its pinned host and when it was stored. Never values (GET /secrets).
    A secret in the store wins over one with the same name in the environment."""
    out: dict[str, dict] = {}
    for env_name, value in sorted(os.environ.items()):
        if not env_name.startswith(PREFIX) or env_name.endswith(HOST_SUFFIX) or not value:
            continue
        name = env_name[len(PREFIX):].lower()
        host = os.environ.get(env_name + HOST_SUFFIX, "").strip().lower() or None
        out[name] = {"name": name, "set": True, "host": host, "updated_at": None}
    if session is not None:
        from sqlalchemy import select

        from app.storage.models import Secret as SecretRow

        for row in session.scalars(select(SecretRow)):
            out[row.name] = {"name": row.name, "set": True, "host": row.host, "updated_at": row.updated_at}
    return [out[k] for k in sorted(out)]
