"""Accounts and sign-in (D-18).

A person registers with a username and password and gets a session token. The token goes in the
`X-Session-Token` header (not `Authorization`, which the optional nginx basic auth already uses, D-17 S-3).
Only the SHA-256 of a token is stored. Passwords are hashed with scrypt and a random salt. Every
route except /health and /auth/register and /auth/login needs a valid token, and the token decides the
`account` that all data access is scoped to.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets as pysecrets
import threading
import time
from datetime import UTC, datetime, timedelta

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
SESSION_DAYS = 7
HEADER = "X-Session-Token"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class AuthError(Exception):
    """Messages are safe to show to the person. They never say which half of a login was wrong."""


def normalize_username(username: str) -> str:
    name = (username or "").strip().lower()
    if not USERNAME_RE.fullmatch(name):
        raise AuthError("A username is 3 to 32 characters: letters, digits, dot, dash or underscore, starting with a letter or digit.")
    return name


def check_password_rules(password: str) -> None:
    if not isinstance(password, str) or not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        raise AuthError(f"A password is {MIN_PASSWORD} to {MAX_PASSWORD} characters.")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}$".format(**_SCRYPT) + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


_dummy: str | None = None


def burn_time(password: str) -> None:
    """Hash once even when the username does not exist, so a login takes the same time either way."""
    global _dummy
    _dummy = _dummy or hash_password("not-a-real-password")
    verify_password(password, _dummy)


def new_token() -> tuple[str, str]:
    token = pysecrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expiry(days: int = SESSION_DAYS) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


class LoginThrottle:
    """Too many wrong passwords for one username in a short time: wait. In memory, per API process."""

    def __init__(self, limit: int = 8, window: float = 300.0):
        self.limit, self.window = limit, window
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window
        recent = [t for t in self._fails.get(key, []) if t > cutoff]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


throttle = LoginThrottle()


def registration_open() -> bool:
    return os.environ.get("ALLOW_REGISTRATION", "true").strip().lower() not in ("0", "false", "no", "off")
