"""Build the HTTP request for an action: placeholders, auth and headers (D-2.3, D-2.5, D-2.16, D-2.17)."""

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.engine.placeholders import PlaceholderError, fill
from app.secrets import Secret, get_secret

USER_AGENT = "HiIntegrate/1.0"


@dataclass
class Prepared:
    request: httpx.Request
    secret: Secret | None
    host: str


def build_request(cfg: dict, action_name: str, *, inputs: dict | None = None, state: dict | None = None,
                  now: datetime | None = None, url: str | None = None, extra_params: dict | None = None,
                  secret_lookup: Callable[[str], Secret] | None = None) -> Prepared:
    """`url` overrides the address (a next-page link). Its host is checked against the secret later.
    `extra_params` adds paging parameters (offset, page, cursor) to the query.
    `secret_lookup` finds a secret by name. The engine has no database, so the runner passes one that
    checks the encrypted store first. Without it, only the environment is used."""
    action = cfg["actions"][action_name]
    vars_ = cfg.get("vars") or {}
    ctx = {"vars": vars_, "inputs": inputs or {}, "state": state or {}, "now": now}
    req = action["request"]

    # Some services (GitHub) refuse a request with no User-Agent, and httpx.Request alone sends none.
    headers = {"User-Agent": USER_AGENT, **((cfg.get("defaults") or {}).get("headers") or {}), **fill(req.get("headers") or {}, **ctx)}
    params = {k: str(v) for k, v in fill(req.get("query") or {}, **ctx).items()} if url is None else {}
    inc = action.get("incremental")
    if inc and url is None:
        # B-1: send "changed since" only when there is a previous success. The first run is a full pull.
        try:
            params[inc["param"]] = str(fill(inc["value"], **ctx))
        except PlaceholderError:
            pass
    params.update({k: str(v) for k, v in (extra_params or {}).items()})
    body = fill(req.get("body"), **ctx)
    if url is None:
        url = fill(cfg["base_url"], vars=vars_).rstrip("/") + fill(req["path"], **ctx)

    auth = cfg["auth"]
    secret = (secret_lookup or get_secret)(auth["secret"]) if auth.get("type") in ("api_key", "bearer", "basic") else None
    if auth["type"] == "api_key":
        token = (auth.get("prefix") or "") + secret.value
        if auth["in"] == "header":
            headers[auth["name"]] = token
        else:
            params[auth["name"]] = token
    elif auth["type"] == "bearer":
        headers["Authorization"] = f"Bearer {secret.value}"
    elif auth["type"] == "basic":
        user = fill(auth["username"], vars=vars_)
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{secret.value}".encode()).decode()

    kwargs = {"json": body} if isinstance(body, (dict, list)) else ({"content": body} if body else {})
    request = httpx.Request(req["method"], url, params=params or None, headers=headers, **kwargs)
    return Prepared(request=request, secret=secret, host=request.url.host)
