"""Command line for checking configs without the API or the dashboard (B-2, B-3 fallback).

  python -m app.cli validate <file>
  python -m app.cli test <template-or-file> <action> [--var key=value ...] [--input key=value ...] [--json]

`test` makes one live call (first page only, nothing saved) and shows the raw reply beside the
mapped record. A template can be named by its file name in templates/ (for example `github`).
Exit code: 0 when valid / the call worked, 1 otherwise.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

from app.config_loader import is_valid, load_config
from app.core.logging import setup_logging
from app.core.settings import REPO_ROOT
from app.engine import test_action


def _resolve(target: str) -> Path:
    path = Path(target)
    if path.exists():
        return path
    for candidate in (REPO_ROOT / "templates" / f"{target}.yaml", REPO_ROOT / "templates" / target):
        if candidate.exists():
            return candidate
    raise SystemExit(f"error: no file or template named {target!r}")


def _pairs(items: list[str] | None, flag: str) -> dict:
    out = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise SystemExit(f"error: {flag} expects key=value, got {item!r}")
        out[key] = value
    return out


def _print_issues(path: Path, issues: list[dict]) -> None:
    errors = [i for i in issues if i["severity"] == "error"]
    for i in issues:
        where = f"line {i['line']:<4}" if "line" in i else " " * 9
        print(f"  {where} {i['severity']:<7} {i['path']}: {i['message']}")
    verdict = "VALID" if not errors else "INVALID"
    warnings = len(issues) - len(errors)
    print(f"{verdict}  {path}  ({len(errors)} error{'s' * (len(errors) != 1)}, {warnings} warning{'s' * (warnings != 1)})")


def cmd_validate(args) -> int:
    path = _resolve(args.file)
    _, issues = load_config(path.read_text())
    if args.json:
        print(json.dumps({"valid": is_valid(issues), "errors": issues}, indent=2))
    else:
        _print_issues(path, issues)
    return 0 if is_valid(issues) else 1


def _short(value, limit: int = 1200) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "\n  ... (cut)"


def cmd_test(args, client: httpx.Client | None = None) -> int:
    path = _resolve(args.config)
    cfg, issues = load_config(path.read_text())
    if cfg is None or not is_valid(issues):
        _print_issues(path, issues)
        return 1
    cfg["vars"] = {**(cfg.get("vars") or {}), **_pairs(args.var, "--var")}
    if args.action not in cfg["actions"]:
        print(f"error: {path.name} has no action {args.action!r}. Actions: {', '.join(cfg['actions'])}")
        return 1
    result = test_action(cfg, args.action, _pairs(args.input, "--input"), client=client)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1
    print(f"{'OK' if result['ok'] else 'FAILED'}  {cfg['name']} / {args.action}   status={result['status_code']}  latency={result['latency_ms']}ms")
    if result["raw_sample"] is not None:
        print("\nRaw (first record):\n" + _short(result["raw_sample"]))
        print("\nMapped:\n" + _short(result["mapped_sample"]))
    print("\nMissing paths: " + (", ".join(result["missing_paths"]) or "none"))
    for note in result["notes"]:
        print(f"Note: {note}")
    return 0 if result["ok"] else 1


def cmd_rotate_keys(_args) -> int:
    """S-11: re-encrypt every stored secret with the first key in ENCRYPTION_KEY."""
    from app.secrets import SecretError, StoreUnavailable, rotate_keys
    from app.storage import session_scope

    try:
        with session_scope() as s:
            count = rotate_keys(s)
    except (StoreUnavailable, SecretError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Re-encrypted {count} secret(s) with the first key. You can now remove the old key from ENCRYPTION_KEY.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Check integration configs.")
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="validate a config file and list every problem with its path and line")
    v.add_argument("file")
    v.add_argument("--json", action="store_true", help="print the validate response as JSON")
    t = sub.add_parser("test", help="call the service once (first page only, nothing saved)")
    t.add_argument("config", help="a config file, or a template name such as github")
    t.add_argument("action")
    t.add_argument("--var", action="append", metavar="KEY=VALUE", help="override a var, for example --var org=my-org")
    t.add_argument("--input", action="append", metavar="KEY=VALUE", help="a lookup input, for example --input username=octocat")
    t.add_argument("--json", action="store_true", help="print the test response as JSON")
    sub.add_parser("rotate-keys", help="re-encrypt every stored secret with the first key in ENCRYPTION_KEY (S-11)")
    return p


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    setup_logging("WARNING")
    args = build_parser().parse_args(argv)
    if args.command == "rotate-keys":
        return cmd_rotate_keys(args)
    return cmd_validate(args) if args.command == "validate" else cmd_test(args, client)


if __name__ == "__main__":
    sys.exit(main())
