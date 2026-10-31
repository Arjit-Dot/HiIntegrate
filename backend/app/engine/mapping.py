"""Turn a raw record into a result record (D-2.7, D-3, D-4). Must reproduce docs/examples/expected/.

Rules (the same as schema/tools/lib/map-engine.mjs):
  - a missing or null path uses `default` if given, otherwise the field stays empty (None)
  - transform runs first (failure: transform_failed), then value_map
  - a value outside value_map uses `default` if given, otherwise the record is invalid_value
  - every field in `required`, and always `id`, must be present (missing_required_field)
  - the finished record must match schema/result.schema.json (otherwise invalid_value)
"""

import json
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import jmespath
from jsonschema import Draft202012Validator

from app.core.settings import REPO_ROOT

FIELDS = {
    "user": ["id", "name", "email", "status", "last_login"],
    "device": ["id", "hostname", "ip", "os", "owner", "last_seen"],
    "alert": ["id", "type", "severity", "timestamp", "description"],
}


@lru_cache
def _result_validators() -> dict[str, Draft202012Validator]:
    schema = json.loads((REPO_ROOT / "schema" / "result.schema.json").read_text())
    out = {}
    for name in ("user", "device", "alert", "quarantine_record"):
        sub = {**schema["$defs"][name], "$defs": schema["$defs"]}
        out[name] = Draft202012Validator(sub)
    return out


def validator_for(name: str) -> Draft202012Validator:
    return _result_validators()[name]


class _TransformFailed(Exception):
    pass


def _js_string(v: Any) -> str:
    """String(v) as JavaScript does it, so value_map keys like "true" match booleans."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def to_iso(v: Any, fmt: str | None = None) -> str:
    try:
        if fmt and isinstance(v, str):
            dt = datetime.strptime(v, fmt)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) or (isinstance(v, str) and v.isdigit()):
            n = float(v)
            dt = datetime.fromtimestamp(n / 1000 if n >= 1e11 else n, UTC)
        else:
            dt = datetime.fromisoformat(str(v))
    except (ValueError, OverflowError, OSError) as exc:
        raise _TransformFailed from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (f".{ms:03d}" if ms else "") + "Z"


def _transform(v: Any, t: str | None, fmt: str | None) -> Any:
    if not t:
        return v
    try:
        match t:
            case "string":
                return _js_string(v)
            case "int":
                return int(float(v)) if not isinstance(v, bool) else int(v)
            case "float":
                return float(v)
            case "bool":
                return _js_string(v).lower() in ("true", "1", "yes")
            case "lowercase":
                return _js_string(v).lower()
            case "uppercase":
                return _js_string(v).upper()
            case "datetime":
                return to_iso(v, fmt)
    except (ValueError, TypeError) as exc:
        raise _TransformFailed from exc
    return v


def _empty(v: Any) -> bool:
    return v is None or v == ""


def map_record(cfg: dict, action_name: str, raw: Any, *, run_id: str, fetched_at: str, quarantined_at: str | None = None) -> dict:
    """Returns {"record": {...}} or {"quarantine": {...}}."""
    action = cfg["actions"][action_name]
    target = action["target_schema"]

    def fail(reason: str, field: str) -> dict:
        return {"quarantine": {
            "source": cfg["name"], "action": action_name, "target_schema": target, "run_id": run_id,
            "raw": raw, "reason": reason, "field": field, "created_at": quarantined_at or fetched_at,
        }}

    out: dict[str, Any] = {}
    for field in FIELDS[target]:
        if field not in action["map"]:
            continue
        entry = action["map"][field]
        e = {"path": entry} if isinstance(entry, str) else entry
        v = jmespath.search(e["path"], raw) if e.get("path") else None
        if _empty(v):
            v = e.get("default")
        else:
            try:
                v = _transform(v, e.get("transform"), e.get("format"))
            except _TransformFailed:
                return fail("transform_failed", field)
            if "value_map" in e:
                key = _js_string(v)
                if key in e["value_map"]:
                    v = e["value_map"][key]
                elif "default" in e:
                    v = e["default"]
                else:
                    return fail("invalid_value", field)
        out[field] = v

    for f in dict.fromkeys(["id", *action.get("required", [])]):
        if _empty(out.get(f)):
            return fail("missing_required_field", f)

    record = {f: out[f] for f in FIELDS[target] if f in out}
    record["source"] = cfg["name"]
    record["fetched_at"] = fetched_at
    errors = sorted(validator_for(target).iter_errors(record), key=lambda e: list(e.path))
    if errors:
        bad = errors[0]
        field = str(bad.path[0]) if bad.path else (next((k for k in record if k not in FIELDS[target] + ["source", "fetched_at"]), "") )
        return fail("invalid_value", field)
    return {"record": record}


def map_records(cfg: dict, action_name: str, raws: list, *, run_id: str, fetched_at: str, quarantined_at: str | None = None) -> tuple[list, list]:
    records, quarantine = [], []
    for raw in raws:
        r = map_record(cfg, action_name, raw, run_id=run_id, fetched_at=fetched_at, quarantined_at=quarantined_at)
        (records if "record" in r else quarantine).append(r.get("record") or r.get("quarantine"))
    return records, quarantine


def remap_records(cfg: dict, action_name: str, raw_records: list, *, run_id: str = "remap") -> tuple[list, list]:
    """A dry run for AI propose-fix (D-14): map stored raw records again with a (proposed) config.
    Pure: no network, no database. Returns (records, quarantine), exactly as they would be saved."""
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return map_records(cfg, action_name, raw_records, run_id=run_id, fetched_at=fetched_at)
