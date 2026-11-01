import logging
import os
import re
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

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


def _fernet() -> MultiFernet:
    """S-11: ENCRYPTION_KEY may hold several keys separated by commas. The FIRST encrypts; every one can decrypt. To
    rotate: put the new key first and keep the old one after it, restart, run `rotate-keys`, then drop the old key."""
    raw = os.environ.get("ENCRYPTION_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise StoreUnavailable("ENCRYPTION_KEY is not set, so the encrypted secret store is not available")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError):
        raise StoreUnavailable("ENCRYPTION_KEY is not a valid key (each key must be 32 url-safe base64 bytes; separate several with commas)") from None


def rotate_keys(session) -> int:
    """S-11: re-encrypt every stored secret with the first key. Returns how many were rewritten. A secret that none of the
    keys can open is left alone and raises SecretError, so nothing is lost by a wrong key list."""
    from app.storage.models import Secret as SecretRow

    f = _fernet()
    rows = session.query(SecretRow).all()
    fresh = {}
    for row in rows:
        try:
            fresh[(row.account, row.name)] = f.rotate(row.ciphertext.encode()).decode()
        except InvalidToken:
            raise SecretError(f"secret {row.name} cannot be decrypted with any key in ENCRYPTION_KEY; nothing was changed") from None
    for row in rows:
        row.ciphertext = fresh[(row.account, row.name)]
    session.flush()
    return len(rows)


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


def set_secret(session, account: str, name: str, value: str, host: str) -> None:
    """D-7.1, D-7.6, D-18: store the value encrypted for this account, with the one host it may be sent to.
    A second call replaces both. Two accounts can use the same name for different values."""
    from datetime import UTC, datetime

    from app.storage.models import Secret as SecretRow

    _check_name(name)
    value = value.strip()  # a pasted key often carries a trailing space or newline, which is an illegal header value
    if not value:
        raise SecretError("a secret needs a value")
    host = _check_host_value(host)
    ciphertext = _fernet().encrypt(value.encode()).decode()
    row = session.get(SecretRow, (account, name.lower())) or SecretRow(account=account, name=name.lower())
    row.ciphertext, row.host = ciphertext, host
    row.updated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.add(row)
    session.flush()


def _stored(session, account: str, name: str) -> Secret | None:
    from app.storage.models import Secret as SecretRow

    row = session.get(SecretRow, (account, name.lower()))
    if row is None:
        return None
    try:
        value = _fernet().decrypt(row.ciphertext.encode()).decode().strip()  # also fixes a value saved with stray whitespace
    except InvalidToken:
        raise SecretError(f"secret {name} cannot be decrypted: ENCRYPTION_KEY is not the key it was stored with (none of its keys opens it). Enter the value again") from None
    return Secret(name=name, value=value, host=row.host)


ENV_ACCOUNT_VAR = "ENV_SECRETS_ACCOUNT"


def _env_allowed(account: str | None) -> bool:
    """D-18: SECRET_<NAME> variables belong to the whole server, so with accounts only ONE named account may use them
    (ENV_SECRETS_ACCOUNT, for the demo and the old .env setup). Nobody else can reach them.
    Without an account (the command line, which has no accounts) they are allowed."""
    if account is None:
        return True
    wanted = os.environ.get(ENV_ACCOUNT_VAR, "").strip().lower()
    return bool(wanted) and wanted == account


def get_secret(name: str, session=None, account: str | None = None) -> Secret:
    """D-8 handoff. With a session the account's own encrypted store is checked first, then the environment if this
    account is the one allowed to use it (D-7.1, D-18). Raises SecretNotFound if neither has it."""
    _check_name(name)
    if session is not None:
        if account is None:
            raise ValueError("get_secret needs the account when it is given a session (D-18)")
        stored = _stored(session, account, name)
        if stored is not None:
            return stored
        if not _env_allowed(account):
            raise SecretNotFound(f"secret {name} is not set: enter its value on the Secrets page")
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


def list_secrets(session=None, account: str | None = None) -> list[dict]:
    """Names, whether each is set, its pinned host and when it was stored. Never values (GET /secrets).
    A secret in the store wins over one with the same name in the environment. With an account, only that
    account's own secrets are listed (plus the environment ones if it is the account allowed to use them)."""
    if session is not None and account is None:
        raise ValueError("list_secrets needs the account when it is given a session (D-18)")
    out: dict[str, dict] = {}
    for env_name, value in sorted(os.environ.items()):
        if not _env_allowed(account):
            break
        if not env_name.startswith(PREFIX) or env_name.endswith(HOST_SUFFIX) or not value:
            continue
        name = env_name[len(PREFIX):].lower()
        host = os.environ.get(env_name + HOST_SUFFIX, "").strip().lower() or None
        out[name] = {"name": name, "set": True, "host": host, "updated_at": None}
    if session is not None:
        from sqlalchemy import select

        from app.storage.models import Secret as SecretRow

        for row in session.scalars(select(SecretRow).where(SecretRow.account == account)):
            out[row.name] = {"name": row.name, "set": True, "host": row.host, "updated_at": row.updated_at}
    return [out[k] for k in sorted(out)]
