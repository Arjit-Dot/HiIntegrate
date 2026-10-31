import json
import re
from functools import lru_cache
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from app.core.settings import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "schema" / "integration.schema.json"
Issue = dict[str, Any]

_PLACEHOLDER = re.compile(r"\{\{\s*([^}]*?)\s*\}\}")
_LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "mock-api"}

_PATTERN_MESSAGES = {
    "schedule": 'must look like "every 10s", "every 5m", "every 2h" or "every 1d" (minimum 10 seconds)',
    "secret": "must be a name (letters, digits, underscores, up to 64), not a key",
    "base_url": "may only contain {{vars.x}} placeholders, and must start with http:// or https://",
    "name": "must be a slug: lowercase letters, digits, - or _",
    "path": "must start with /",
}


class ConfigParseError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@lru_cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


# ---------------------------------------------------------------- parsing

def parse_config(text: str) -> dict:
    """Parse YAML or JSON text (JSON is valid YAML). Raises ConfigParseError."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or "could not be parsed"
        raise ConfigParseError(f"is not valid YAML or JSON: {problem}", mark.line + 1 if mark else None) from None
    if not isinstance(data, dict):
        raise ConfigParseError("must be a mapping of keys to values (a YAML or JSON object)", 1)
    return data


def _line_index(text: str) -> dict[str, int]:
    """Map each dotted path ("actions.list_users.schedule") to its 1-based line in the text."""
    lines: dict[str, int] = {}

    def walk(node, path: str) -> None:
        if isinstance(node, yaml.MappingNode):
            for key_node, value_node in node.value:
                child = f"{path}.{key_node.value}" if path else str(key_node.value)
                lines[child] = key_node.start_mark.line + 1
                walk(value_node, child)
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                child = f"{path}.{i}"
                lines[child] = item.start_mark.line + 1
                walk(item, child)

    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return lines
    if root is not None:
        walk(root, "")
    return lines


def _attach_lines(issues: list[Issue], text: str) -> list[Issue]:
    index = _line_index(text)
    for issue in issues:
        path = issue["path"]
        while path and path not in index:  # fall back to the nearest parent that exists
            path = path.rpartition(".")[0]
        if path in index:
            issue["line"] = index[path]
    return issues


# ---------------------------------------------------------------- schema errors

def _join(parts) -> str:
    return ".".join(str(p) for p in parts)


def _schema_issue(err, data: Any) -> list[Issue]:
    """Turn one jsonschema error into issues worded like the reference check."""
    base = _join(err.absolute_path)
    validator = err.validator

    def issue(path: str, message: str) -> Issue:
        return {"path": path or "(root)", "message": message, "severity": "error"}

    if "propertyNames" in err.schema_path:
        return [issue(f"{base}.{err.instance}" if base else str(err.instance), "is not a field of the target schema")]
    if validator is None:  # a `false` schema: the key is not allowed in this mode or auth type
        key = _false_schema_key(err, data)
        return [issue(f"{base}.{key}" if key and base else (key or base), "is not allowed here (wrong mode or auth type)")]
    if validator == "additionalProperties":
        allowed = set(err.schema.get("properties", {}))
        extra = [k for k in err.instance if k not in allowed]
        return [issue(f"{base}.{k}" if base else k, "is not a known key") for k in extra]
    if validator == "required":
        m = re.match(r"^'(.+)' is a required property$", err.message)
        name = m.group(1) if m else "?"
        return [issue(f"{base}.{name}" if base else name, "is required")]
    if validator == "anyOf":
        return [issue(base, "needs a path (or a default)")]
    if validator == "const":
        return [issue(base, "must be " + json.dumps(err.validator_value))]
    if validator == "enum":
        return [issue(base, "must be one of: " + ", ".join("" if v is None else str(v) for v in err.validator_value))]
    if validator == "pattern":
        last = base.rpartition(".")[2]
        return [issue(base, _PATTERN_MESSAGES.get(last, f'must match pattern "{err.validator_value}"'))]
    if validator == "format":
        return [issue(base, f'must match format "{err.validator_value}"')]
    if validator == "type":
        v = err.validator_value
        return [issue(base, "must be " + (v if isinstance(v, str) else ",".join(v)))]
    simple = {
        "minProperties": "must NOT have fewer than {} properties",
        "minLength": "must NOT have fewer than {} characters",
        "maxLength": "must NOT have more than {} characters",
        "minItems": "must NOT have fewer than {} items",
        "minimum": "must be >= {}",
        "maximum": "must be <= {}",
        "exclusiveMinimum": "must be > {}",
    }
    if validator in simple:
        return [issue(base, simple[validator].format(err.validator_value))]
    if validator == "uniqueItems":
        return [issue(base, "must NOT have duplicate items")]
    return [issue(base, err.message)]


def _false_schema_key(err, data: Any) -> str | None:
    """jsonschema reports a `false` property schema at the parent object. Find which key it was."""
    if not err.schema_path or err.schema_path[-1] != "properties":
        return None
    root = _validator().schema
    node: Any = root
    for step in err.absolute_schema_path:  # follow the schema path, resolving local $refs
        while isinstance(node, dict) and step not in node and "$ref" in node:
            target: Any = root
            for part in node["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            node = target
        node = node[step] if isinstance(node, dict) else node[int(step)]
    parent: Any = data
    for step in err.absolute_path:
        parent = parent[step]
    if not isinstance(node, dict) or not isinstance(parent, dict):
        return None
    for key, sub in node.items():
        if sub is False and key in parent and parent[key] == err.instance:
            return key
    return None


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen, out = set(), []
    for i in issues:
        key = (i["path"], i["message"])
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


# ---------------------------------------------------------------- rules JSON Schema cannot express

def _strings(obj, path: str, out: list) -> list:
    if isinstance(obj, str):
        out.append((path, obj))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _strings(v, f"{path}[{i}]", out)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _strings(v, f"{path}.{k}" if path else k, out)
    return out


def _semantic_issues(cfg: dict) -> list[Issue]:
    issues: list[Issue] = []

    def add(path: str, message: str, severity: str = "error") -> None:
        issues.append({"path": path, "message": message, "severity": severity})

    known_vars = set(cfg.get("vars") or {}) | set((cfg.get("requires") or {}).get("vars") or {})

    def check(path: str, text: str, where: str = "", mode: str | None = None, inputs: dict | None = None) -> None:
        for m in _PLACEHOLDER.finditer(text or ""):
            t = m.group(1)
            if re.fullmatch(r"vars\.[A-Za-z_]\w*", t):
                if t[5:] not in known_vars:
                    add(path, f"{{{{{t}}}}} is not defined in vars or requires.vars")
            elif re.fullmatch(r"state\.[A-Za-z_]\w*", t) or re.fullmatch(r"now(\s*-\s*\d+[smhd])?", t):
                if where == "base_url":
                    add(path, "only {{vars.x}} is allowed in base_url")
            elif re.fullmatch(r"input\.[A-Za-z_]\w*", t):
                if mode != "lookup":
                    add(path, f"{{{{{t}}}}} is allowed only in lookup actions")
                elif t[6:] not in (inputs or {}):
                    add(path, f"{{{{{t}}}}} is used but not declared in inputs")
            else:
                add(path, f"unknown placeholder {{{{{t}}}}}. Use vars, input, state or now")

    base_url = cfg.get("base_url", "")
    check("base_url", base_url, where="base_url")
    plain = re.match(r"^http://([^/:{}\s]+)", base_url)
    if base_url.startswith("http://") and not (plain and plain.group(1) in _LOCAL_HTTP_HOSTS):
        add("base_url", "must use https:// (http:// is allowed only for localhost, 127.0.0.1 and mock-api)")

    auth = cfg.get("auth") or {}
    if auth.get("username"):
        check("auth.username", auth["username"])
    for p, s in _strings(cfg.get("defaults") or {}, "defaults", []):
        check(p, s)
    for p, s in _strings(cfg.get("vars") or {}, "vars", []):
        check(p, s)

    for name, a in (cfg.get("actions") or {}).items():
        base = f"actions.{name}"
        mode, inputs, amap = a.get("mode"), a.get("inputs"), a.get("map")
        for p, s in _strings(a.get("request") or {}, f"{base}.request", []):
            check(p, s, mode=mode, inputs=inputs)
        for p, s in _strings(a.get("incremental") or {}, f"{base}.incremental", []):
            check(p, s, mode=mode, inputs=inputs)
        for f in a.get("required") or []:
            if not (amap and f in amap):
                add(f"{base}.required", f"{f} is listed in required but is not in map")
        if mode == "webhook":
            add(f"{base}.mode", "webhook is reserved and not implemented yet")
        if a.get("response_format") and a["response_format"] != "json":
            add(f"{base}.response_format", f"{a['response_format']} is reserved and not implemented yet. Only json works")
        if "fan_out" in a:
            add(f"{base}.fan_out", "fan_out is reserved and not implemented yet")
        if mode in ("pull", "lookup") and amap and not amap.get("id"):
            add(f"{base}.map.id", "id must be mapped")

    if auth.get("type") == "oauth2_client_credentials":
        add("auth.type", "oauth2_client_credentials is reserved and not supported yet")
    secrets = (cfg.get("requires") or {}).get("secrets")
    if secrets and auth.get("secret") and auth["secret"] not in secrets:
        add("requires.secrets", f"auth.secret {auth['secret']} is not listed in requires.secrets", "warning")
    return issues


# ---------------------------------------------------------------- public API

def validate_config(data: Any) -> list[Issue]:
    """The D-8 handoff: schema errors first; the extra rules run only on a schema-valid config."""
    errors = list(_validator().iter_errors(data))
    if errors:
        issues = [i for err in errors for i in _schema_issue(err, data)]
        return _dedupe(issues) or [{"path": "(root)", "message": "does not match the config schema", "severity": "error"}]
    return _semantic_issues(data)


def load_config(text: str) -> tuple[dict | None, list[Issue]]:
    """Parse and validate YAML or JSON text. Issues carry the line they point at."""
    try:
        data = parse_config(text)
    except ConfigParseError as exc:
        issue: Issue = {"path": "(root)", "message": str(exc), "severity": "error"}
        if exc.line:
            issue["line"] = exc.line
        return None, [issue]
    return data, _attach_lines(validate_config(data), text)


def is_valid(issues: list[Issue]) -> bool:
    return not any(i["severity"] == "error" for i in issues)
