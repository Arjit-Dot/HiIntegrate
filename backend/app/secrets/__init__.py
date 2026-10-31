"""Secrets by name (D-7.1, D-7.3, D-7.6).

Handoff function (D-8):  get_secret(name) -> Secret

Phase 1: values come from the environment as SECRET_<NAME> (upper case). The optional
companion SECRET_<NAME>_HOST pins the secret to one host. Phase 2 adds the encrypted store
in front of the environment, behind the same function.

Only variables starting with SECRET_ are ever read, so a config can never reach the app's
own keys (DATABASE_URL, ENCRYPTION_KEY and so on). A Secret never prints its value.
"""

from app.secrets.store import (
    Secret,
    SecretError,
    SecretHostMismatch,
    SecretNotFound,
    check_host,
    get_secret,
    list_secrets,
)

__all__ = ["Secret", "SecretError", "SecretHostMismatch", "SecretNotFound", "check_host", "get_secret", "list_secrets"]
