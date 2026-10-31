import logging
import os
import re
from dataclasses import dataclass, field

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


def get_secret(name: str) -> Secret:
    """Look a secret up by name. Raises SecretNotFound if it is not set."""
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


def list_secrets() -> list[dict]:
    """Names, whether each is set, and its pinned host. Never values (for GET /secrets)."""
    out = []
    for env_name, value in sorted(os.environ.items()):
        if not env_name.startswith(PREFIX) or env_name.endswith(HOST_SUFFIX) or not value:
            continue
        name = env_name[len(PREFIX):].lower()
        host = os.environ.get(env_name + HOST_SUFFIX, "").strip().lower() or None
        out.append({"name": name, "set": True, "host": host, "updated_at": None})
    return out
