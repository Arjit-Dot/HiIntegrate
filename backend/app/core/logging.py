"""JSON logging that never prints a secret (D-7.2).

Every record passes through RedactingFilter, which hides:
  - the value of every SECRET_* variable and of the app's own keys, wherever it appears
  - Authorization headers, and Bearer / Basic / SSWS / Token credentials
  - the password in a database URL
"""

import json
import logging
import os
import re
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

REDACTED = "[REDACTED]"
_OWN_KEYS = ("ENCRYPTION_KEY", "POSTGRES_PASSWORD", "LLM_API_KEY", "DATABASE_URL")
_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;\"']+(\s+[^\s,;\"']+)?)"),
    re.compile(r"(?i)\b(bearer|basic|ssws|token)\s+([A-Za-z0-9._~+/=-]{8,})"),
    re.compile(r"(?i)(://[^:/\s]+:)([^@\s]+)(@)"),
]


def _secret_values() -> list[str]:
    """Values to hide, longest first so a value inside another is not half-hidden."""
    values = []
    for name, value in os.environ.items():
        if value and len(value) >= 6 and (name.startswith("SECRET_") or name in _OWN_KEYS):
            values.append(value)
    return sorted(set(values), key=len, reverse=True)


def redact(text: str, extra_values: list[str] | None = None) -> str:
    for value in (extra_values or []) + _secret_values():
        if value:
            text = text.replace(value, REDACTED)
    text = _PATTERNS[0].sub(lambda m: m.group(1) + REDACTED, text)
    text = _PATTERNS[1].sub(lambda m: m.group(1) + " " + REDACTED, text)
    text = _PATTERNS[2].sub(lambda m: m.group(1) + REDACTED + m.group(3), text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["error"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
