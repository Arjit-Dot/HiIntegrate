"""Check a lookup's inputs before any request is sent (D-2.13)."""

import re
from ipaddress import ip_address

_DOMAIN = re.compile(r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE)
_HASH = re.compile(r"^([a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64})$", re.IGNORECASE)


def validate_inputs(defs: dict, values: dict | None) -> list[dict]:
    """Returns [{"path", "message", "severity"}], empty when the inputs are fine. Unknown inputs are errors too."""
    values = values or {}
    issues = []

    def bad(name: str, message: str) -> None:
        issues.append({"path": f"inputs.{name}", "message": message, "severity": "error"})

    for name, d in defs.items():
        v = values.get(name)
        text = "" if v is None else str(v).strip()
        if not text:
            if d.get("required", True):
                bad(name, "is required")
            continue
        kind = d["type"]
        if kind == "int" and not re.fullmatch(r"-?\d+", text):
            bad(name, "must be a whole number")
        elif kind == "ip":
            try:
                ip_address(text)
            except ValueError:
                bad(name, "must be a valid IPv4 or IPv6 address")
        elif kind == "domain" and not _DOMAIN.fullmatch(text):
            bad(name, "must be a domain name")
        elif kind == "hash" and not _HASH.fullmatch(text):
            bad(name, "must be a hex hash (32, 40 or 64 characters)")
        elif kind == "enum" and text not in d.get("values", []):
            bad(name, "must be one of " + ", ".join(d.get("values", [])))
    for name in values:
        if name not in defs:
            bad(name, "is not an input of this action")
    return issues
