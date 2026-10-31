"""Nothing sensitive goes to the model (D-14): secrets, auth headers, request headers, and personal data in raw records."""

import os
import re
from copy import deepcopy
from typing import Any

REDACTED = "[redacted]"
_HEADER = re.compile(r"(?i)\b(authorization|proxy-authorization|x-api-key|api-key|x-auth-token|x-token|cookie|set-cookie)(\s*[:=]\s*)[^\n'\"]+")
_BEARER = re.compile(r"(?i)\b(bearer|basic|ssws|token)\s+[A-Za-z0-9._~+/=-]{12,}")
_SHAPES = re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|ATATT[A-Za-z0-9_=-]{20,}|AIza[A-Za-z0-9_-]{30,})\b")
_BASIC_AUTH_FLAG = re.compile(r"(?i)(\s(?:-u|--user)\s+)\S+")
_SENSITIVE_ENV = ("SECRET_", "LLM_API_KEY", "ENCRYPTION_KEY", "POSTGRES_PASSWORD")
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
NAME_KEYS = {"name", "displayname", "display_name", "firstname", "first_name", "lastname", "last_name", "fullname", "full_name", "login", "username"}


def _secret_values() -> list[str]:
    values = []
    for key, value in os.environ.items():
        if key.startswith(_SENSITIVE_ENV) and not key.endswith("_HOST") and len(value) >= 6:
            values.append(value)
    return sorted(values, key=len, reverse=True)


def scrub(text: str) -> str:
    """Remove secret values, auth headers and token shapes from free text (docs, curl examples, prompts)."""
    for value in _secret_values():
        text = text.replace(value, REDACTED)
    text = _HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _BASIC_AUTH_FLAG.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    return _SHAPES.sub(REDACTED, text)


def mask(value: Any) -> Any:
    """D-14 privacy: the part of an email before @ becomes ***, and name-like fields become ***. Everything else is kept."""
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in NAME_KEYS and isinstance(v, str) and v else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str):
        return EMAIL.sub(r"***@\2", value)
    return value


def safe_config(config: dict) -> dict:
    """The config as the model may see it: request headers are removed. Secrets are names, never values."""
    cfg = deepcopy(config)
    (cfg.get("defaults") or {}).pop("headers", None)
    for action in (cfg.get("actions") or {}).values():
        (action.get("request") or {}).pop("headers", None)
    return cfg
