"""Secrets by name (D-7.1, D-7.3, D-7.6).

Handoff function (D-8):  get_secret(name) -> Secret

Two sources behind one function. The encrypted store (the `secrets` table, Fernet, keyed by
ENCRYPTION_KEY) is checked first, then the environment as SECRET_<NAME>, with the optional
companion SECRET_<NAME>_HOST. A stored secret always has a host (D-7.6).

Only variables starting with SECRET_ are ever read, so a config can never reach the app's
own keys (DATABASE_URL, ENCRYPTION_KEY and so on). A Secret never prints its value.
"""

from app.secrets.store import (
    Secret,
    SecretError,
    SecretHostMismatch,
    SecretNotFound,
    StoreUnavailable,
    check_host,
    get_secret,
    list_secrets,
    rotate_keys,
    set_secret,
    store_available,
)

__all__ = [
    "Secret", "SecretError", "SecretHostMismatch", "SecretNotFound", "StoreUnavailable",
    "check_host", "get_secret", "list_secrets", "rotate_keys", "set_secret", "store_available",
]
