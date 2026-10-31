"""S-9: a per-account limit on the routes that change data, start runs or call the AI, so one signed-in client (or a script
holding a stolen token) cannot hammer the engine, the database or the paid model. In memory, per API process, like the login
throttle (D-18). Over the limit the API answers 429 `rate_limited` with a Retry-After header."""

import math
import os
import threading
import time

# requests per minute, per account, per bucket. Override with RATE_LIMIT_WRITE / RATE_LIMIT_RUN / RATE_LIMIT_AI (0 turns one off).
DEFAULTS = {"write": 60, "run": 30, "ai": 20}
WINDOW = 60.0


def limit_for(bucket: str) -> int:
    raw = os.environ.get(f"RATE_LIMIT_{bucket.upper()}", "").strip()
    try:
        return max(0, int(raw)) if raw else DEFAULTS[bucket]
    except ValueError:
        return DEFAULTS[bucket]


def bucket_for(method: str, path: str) -> str | None:
    """Which limit a request counts against. Reads are never limited; validation is cheap and is called as you type."""
    if "/ai/" in path:
        return "ai"
    if method == "GET" or path.endswith("/integrations/validate"):
        return None
    if path.endswith(("/test", "/run")):
        return "run"
    return "write"


class RateLimiter:
    def __init__(self, window: float = WINDOW):
        self.window = window
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def check(self, account: str, bucket: str, limit: int | None = None) -> int:
        """Count one request. Returns 0 if allowed, else the seconds to wait."""
        limit = limit_for(bucket) if limit is None else limit
        if limit == 0:
            return 0
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get((account, bucket), []) if t > now - self.window]
            if len(hits) >= limit:
                self._hits[(account, bucket)] = hits
                return max(1, math.ceil(hits[0] + self.window - now))
            hits.append(now)
            self._hits[(account, bucket)] = hits
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
