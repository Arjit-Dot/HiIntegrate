"""Send one request with the built-in reliability rules (D-2.10, D-2.11, D-12).

- Retries after the first try: `max_retries` (default 3), waiting backoff_seconds [1, 2, 4];
  the last wait repeats if there are more retries than waits.
- Retried: timeouts, connection errors and 5xx. Never 401/403 (auth_failed) or other 4xx (client_error).
- 429: wait for Retry-After (seconds or an HTTP date), or the backoff if it is missing. A wait longer
  than max_wait_seconds (default 60) fails with rate_limited. A 429 counts against max_retries,
  so a service that keeps answering 429 cannot hold a run forever.
"""

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.engine.errors import RunError

log = logging.getLogger("app.engine")

# S-9: the most one response may be. A service (or a hostile config pointing at one) cannot fill memory with a huge body.
DEFAULT_MAX_RESPONSE_BYTES = 10_000_000


def max_response_bytes() -> int:
    try:
        return int(os.environ.get("MAX_RESPONSE_BYTES", "")) or DEFAULT_MAX_RESPONSE_BYTES
    except ValueError:
        return DEFAULT_MAX_RESPONSE_BYTES


def _read_capped(client: httpx.Client, request: httpx.Request, cap: int) -> httpx.Response:
    """Send and read the body, stopping at `cap` bytes. Raises bad_response if it is larger."""
    response = client.send(request, stream=True)
    try:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > cap:
            raise RunError("bad_response", f"the response is larger than the {cap}-byte limit", status=response.status_code)
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > cap:
                raise RunError("bad_response", f"the response is larger than the {cap}-byte limit", status=response.status_code)
            chunks.append(chunk)
    finally:
        response.close()
    headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
    return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks), request=request)


@dataclass
class Policy:
    max_retries: int = 3
    backoff_seconds: list[float] = field(default_factory=lambda: [1, 2, 4])
    retry_on: set[str] = field(default_factory=lambda: {"timeout", "connection_error", "5xx"})
    max_wait_seconds: float = 60
    timeout_seconds: float = 30

    @classmethod
    def from_config(cls, cfg: dict, action: dict) -> "Policy":
        defaults = cfg.get("defaults") or {}
        retry = {**(defaults.get("retry") or {}), **(action.get("retry") or {})}
        rate = {**(defaults.get("rate_limit") or {}), **(action.get("rate_limit") or {})}
        p = cls()
        p.max_retries = retry.get("max_retries", p.max_retries)
        p.backoff_seconds = retry.get("backoff_seconds", p.backoff_seconds)
        p.retry_on = set(retry.get("retry_on", p.retry_on))
        p.max_wait_seconds = rate.get("max_wait_seconds", p.max_wait_seconds)
        p.timeout_seconds = defaults.get("timeout_seconds", p.timeout_seconds)
        return p

    def wait_for(self, retry_number: int) -> float:
        waits = self.backoff_seconds or [1]
        return waits[min(retry_number, len(waits)) - 1]


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def service_message(response: httpx.Response, limit: int = 200) -> str:
    """The service's own reason for an error, from the usual places (Cloudflare `errors[0].message`, Okta `errorSummary`,
    Jira `errorMessages`, GitHub `message`, NVD's `message` header), so a person sees why, not just the status. Shortened."""
    found = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        errs = body.get("errors")
        first = errs[0] if isinstance(errs, list) and errs else None
        for v in (first.get("message") if isinstance(first, dict) else first if isinstance(first, str) else None,
                  body.get("errorSummary"), (body.get("errorMessages") or [None])[0] if isinstance(body.get("errorMessages"), list) else None,
                  body.get("message"), body.get("error_description"),
                  body["error"].get("message") if isinstance(body.get("error"), dict) else body.get("error"), body.get("detail")):
            if isinstance(v, str) and v.strip():
                found = v
                break
    found = found or response.headers.get("message")
    if not found:
        return ""
    found = " ".join(found.split())
    return ": " + (found if len(found) <= limit else found[:limit] + "...")


@dataclass
class Sent:
    response: httpx.Response
    retries: int
    latency_ms: int


def send(client: httpx.Client, request: httpx.Request, policy: Policy, *, sleep: Callable[[float], None] = time.sleep) -> Sent:
    retries = 0
    started = time.monotonic()
    while True:
        try:
            response = _read_capped(client, request, max_response_bytes())
        except httpx.TimeoutException as exc:
            kind, failure = "timeout", RunError("timeout", f"timed out: {type(exc).__name__}", retries=retries)
        except httpx.TransportError as exc:
            kind, failure = "connection_error", RunError("connection_error", f"connection error: {type(exc).__name__}", retries=retries)
        else:
            status = response.status_code
            if status < 400:
                return Sent(response, retries, int((time.monotonic() - started) * 1000))
            if status in (401, 403):
                raise RunError("auth_failed", f"authentication failed ({status}){service_message(response)}. Not retried.", status=status, retries=retries)
            if status == 429:
                wait = _retry_after(response.headers.get("Retry-After"))
                if wait is not None and wait > policy.max_wait_seconds:
                    raise RunError("rate_limited", f"rate limited: the service asked to wait {wait:.0f}s, more than {policy.max_wait_seconds:.0f}s",
                                   status=429, retries=retries)
                if retries >= policy.max_retries:
                    raise RunError("rate_limited", "rate limited (429) on every retry", status=429, retries=retries)
                retries += 1
                pause = wait if wait is not None else policy.wait_for(retries)
                log.info("429 from %s, waiting %.1fs (retry %d)", request.url.host, pause, retries)
                sleep(pause)
                continue
            if status >= 500:
                kind, failure = "5xx", RunError("server_error", f"server error ({status})", status=status, retries=retries)
            else:
                raise RunError("client_error", f"request failed ({status}){service_message(response)}", status=status, retries=retries)
        if kind not in policy.retry_on or retries >= policy.max_retries:
            failure.retries = retries
            raise failure
        retries += 1
        pause = policy.wait_for(retries)
        log.info("%s from %s, retry %d in %.1fs", kind, request.url.host, retries, pause)
        sleep(pause)
