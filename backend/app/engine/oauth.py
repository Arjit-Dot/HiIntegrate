"""OAuth2 client credentials (D-21): get an access token with a client id and client secret, keep it until it is about to expire.

The client secret is an ordinary secret (`auth.secret`), pinned to a host. The token request goes only to `token_url`, and only if
that host is the one the secret is pinned to, so a config cannot send the secret somewhere else. The access token is then sent
as `Authorization: Bearer`, and the engine's usual host check keeps it on the same host. Tokens are cached in memory per
process, keyed by the endpoint, client id, scope, audience and a hash of the secret, so two accounts never share a token."""

import hashlib
import threading
import time
from urllib.parse import urlsplit

import httpx

from app.engine.errors import RunError
from app.engine.placeholders import PlaceholderError, fill
from app.secrets import Secret, SecretHostMismatch, check_host

EARLY = 60          # seconds before the real expiry at which a token counts as expired
DEFAULT_TTL = 300   # when the service does not say how long the token lasts

_cache: dict[tuple, tuple[str, float]] = {}
_lock = threading.Lock()


def is_oauth(cfg: dict) -> bool:
    return (cfg.get("auth") or {}).get("type") == "oauth2_client_credentials"


def _settings(cfg: dict) -> dict:
    auth, vars_ = cfg["auth"], cfg.get("vars") or {}
    try:
        return {key: fill(auth[key], vars=vars_) for key in ("client_id", "token_url", "scope", "audience") if auth.get(key)}
    except PlaceholderError as exc:
        raise RunError("client_error", str(exc)) from None


def _key(s: dict, secret: Secret) -> tuple:
    return (s["token_url"], s["client_id"], s.get("scope"), s.get("audience"), hashlib.sha256(secret.value.encode()).hexdigest())


def forget(cfg: dict, secret: Secret) -> None:
    """Drop the cached token (after a 401), so the next request fetches a new one."""
    with _lock:
        _cache.pop(_key(_settings(cfg), secret), None)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def access_token(client: httpx.Client, cfg: dict, secret: Secret, *, now=time.monotonic) -> str:
    s = _settings(cfg)
    key = _key(s, secret)
    with _lock:
        cached = _cache.get(key)
    if cached and cached[1] > now():
        return cached[0]
    host = urlsplit(s["token_url"]).hostname or ""
    try:
        check_host(secret, host)
    except SecretHostMismatch as exc:
        raise RunError("secret_host_mismatch", str(exc)) from None
    form = {"grant_type": "client_credentials", "client_id": s["client_id"], "client_secret": secret.value,
            **{k: s[k] for k in ("scope", "audience") if k in s}}
    try:
        response = client.post(s["token_url"], data=form, headers={"Accept": "application/json", "User-Agent": "HiIntegrate/1.0"})
    except httpx.TimeoutException:
        raise RunError("timeout", "the token request timed out") from None
    except httpx.TransportError as exc:
        raise RunError("connection_error", f"the token request failed: {type(exc).__name__}") from None
    if response.status_code >= 400:
        reason = ""
        try:
            reason = str(response.json().get("error") or "")[:60]
        except (ValueError, AttributeError):
            pass
        raise RunError("auth_failed", f"the token request was refused ({response.status_code}{': ' + reason if reason else ''}). "
                       "Check the client id, the client secret and the scopes or audience.", status=response.status_code)
    try:
        body = response.json()
        token = body["access_token"]
    except (ValueError, KeyError, TypeError):
        raise RunError("auth_failed", "the token reply has no access_token") from None
    try:
        ttl = float(body.get("expires_in", DEFAULT_TTL))
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL
    with _lock:
        _cache[key] = (token, now() + max(0.0, ttl - EARLY))
    return token
