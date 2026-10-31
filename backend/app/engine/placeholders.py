"""Fill {{vars.x}}, {{input.x}}, {{state.x}}, {{now}} and {{now - 24h}} (D-2.5, D-2.19). No other logic."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

_PH = re.compile(r"\{\{\s*([^}]*?)\s*\}\}")
_NOW = re.compile(r"^now(?:\s*-\s*(\d+)([smhd]))?$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


class PlaceholderError(ValueError):
    pass


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fill(value: Any, *, vars: dict | None = None, inputs: dict | None = None, state: dict | None = None, now: datetime | None = None) -> Any:
    """Fill placeholders in strings, recursively through dicts and lists. Other values are untouched."""
    if isinstance(value, dict):
        return {k: fill(v, vars=vars, inputs=inputs, state=state, now=now) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, vars=vars, inputs=inputs, state=state, now=now) for v in value]
    if not isinstance(value, str):
        return value
    now = now or datetime.now(UTC)
    scopes = {"vars": vars or {}, "input": inputs or {}, "state": state or {}}

    def one(m: re.Match) -> str:
        token = m.group(1)
        n = _NOW.match(token)
        if n:
            offset = timedelta(**{_UNITS[n.group(2)]: int(n.group(1))}) if n.group(1) else timedelta()
            return iso(now - offset)
        scope, _, key = token.partition(".")
        if scope not in scopes or not key:
            raise PlaceholderError(f"unknown placeholder {{{{{token}}}}}")
        if key not in scopes[scope] or scopes[scope][key] in (None, ""):
            raise PlaceholderError(f"no value for {{{{{token}}}}}")
        return str(scopes[scope][key])

    return _PH.sub(one, value)
