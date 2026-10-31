"""The three AI features (D-14). Pure logic over data the route hands in: no database, no network except the model.

The model proposes, the platform checks. `propose_fix` never trusts a whole config from the model: it asks for
small changes by path, applies them to the REAL stored config itself, and validates the result.
"""

import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from app.ai.client import LLMClient, LLMError
from app.ai.redact import mask, safe_config, scrub
from app.config_loader import load_config, validate_config
from app.core.settings import REPO_ROOT

PROMPTS = Path(__file__).parent / "prompts"
MODEL_SAMPLE = 20  # D-14: at most 20 raw records go to the model
RETRIES = 2  # config authoring: the first try plus up to 2 corrections
ALLOWED_FIELDS = {"map", "required", "on_invalid", "records_path", "request", "pagination"}
ALLOWED_REQUEST_KEYS = {"query", "path"}


def prompt(name: str, **values: str) -> str:
    text = (PROMPTS / f"{name}.md").read_text()
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def _template(name: str) -> str:
    return (REPO_ROOT / "templates" / f"{name}.yaml").read_text()


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```[a-zA-Z]*\n(.*?)\n?```\s*$", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(_strip_fences(text))
    except ValueError:
        raise LLMError("the model did not answer in the expected format") from None
    if not isinstance(data, dict):
        raise LLMError("the model did not answer in the expected format")
    return data


def _errors(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["severity"] == "error"]


def _describe(issues: list[dict]) -> str:
    return "\n".join(f"- {i['path']}: {i['message']}" for i in _errors(issues)[:20])


# ---------------------------------------------------------------- config authoring

def generate_config(llm: LLMClient, text: str) -> dict:
    """Docs, curl or a sample response in, a draft config out. Validate, and feed the errors back up to 2 times.
    Returns {yaml, config, errors, attempts}; `attempts` lets the UI show each step."""
    system = prompt("generate_config", rules=prompt("rules"), example_github=_template("github"), example_template=_template("service-template"))
    user = scrub(text)
    attempts: list[dict] = []
    answer = _strip_fences(llm.generate(system, user))
    config, issues = None, []
    for attempt in range(1, RETRIES + 2):
        config, issues = load_config(answer)
        errors = _errors(issues)
        attempts.append({"attempt": attempt, "valid": config is not None and not errors, "error_count": len(errors)})
        if not errors and config is not None:
            break
        if attempt == RETRIES + 1:
            break
        follow_up = prompt("fix_config", errors=_describe(issues) or "- the text is not valid YAML")
        answer = _strip_fences(llm.generate(system, f"{user}\n\n---\nYour previous answer:\n{answer}\n\n{follow_up}"))
    return {"yaml": answer, "config": config, "errors": issues, "attempts": attempts}


# ---------------------------------------------------------------- summary

def summarize(llm: LLMClient, target: str, records: list[dict], total: int) -> str:
    stats = {"total_stored": total, "records_counted": len(records)}
    for field in ("source", "status", "severity", "os"):
        counts = Counter(str(r[field]) for r in records if r.get(field) is not None)
        if counts:
            stats[f"by_{field}"] = dict(counts.most_common(10))
    sample = [mask({k: v for k, v in r.items() if k != "raw"}) for r in records[:25]]
    user = f"Record type: {target}\nCounts: {json.dumps(stats)}\nSample (masked):\n{json.dumps(sample, default=str)}"
    return llm.generate(prompt("summarize"), user, temperature=0.3).strip()


# ---------------------------------------------------------------- propose fix

def _cluster_sample(entries: list[dict]) -> list[dict]:
    """Up to 20 records: one of each (reason, field) first, so the model sees every kind of failure."""
    seen, picked, rest = set(), [], []
    for e in entries:
        key = (e["reason"], e.get("field"))
        (rest if key in seen else picked).append(e)
        seen.add(key)
    return (picked + rest)[:MODEL_SAMPLE]


def _lookup(config: dict, parts: list[str]) -> Any:
    cur: Any = config
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def apply_changes(config: dict, action: str, changes: list[Any]) -> tuple[dict, list[dict], list[str]]:
    """Apply the model's path changes to a copy of the real config. Returns (new config, applied changes, rejected notes).
    Only fields of this action that a fix may touch are allowed, so the model can never reach auth, secrets or base_url."""
    new = deepcopy(config)
    applied, rejected = [], []
    for ch in changes if isinstance(changes, list) else []:
        path = ch.get("path") if isinstance(ch, dict) else None
        if not isinstance(path, str) or "after" not in ch or ch["after"] is None:
            rejected.append(f"ignored a change without a path or a value: {str(ch)[:80]}")
            continue
        parts = path.split(".")
        ok = len(parts) >= 3 and parts[0] == "actions" and parts[1] == action and parts[2] in ALLOWED_FIELDS \
            and (parts[2] != "request" or (len(parts) > 3 and parts[3] in ALLOWED_REQUEST_KEYS))
        if not ok:
            rejected.append(f"ignored a change outside the allowed fields: {path}")
            continue
        parent = new
        for p in parts[:-1]:
            nxt = parent.get(p) if isinstance(parent, dict) else None
            if nxt is None:
                nxt = parent[p] = {}
            if not isinstance(nxt, dict):
                parent = None
                break
            parent = nxt
        if parent is None:
            rejected.append(f"could not apply {path}: a parent is not an object")
            continue
        applied.append({"path": path, "before": deepcopy(_lookup(config, parts)), "after": ch["after"], "reason": str(ch.get("reason", ""))})
        parent[parts[-1]] = ch["after"]
    return new, applied, rejected


def propose_fix(llm: LLMClient, config: dict, action: str, *, kind: str, quarantine: list[dict] | None = None,
                run: dict | None = None) -> dict:
    """Returns {summary, changes, proposed_config, errors}. The model is asked once, and once more if the
    proposal makes the config invalid (D-14). Verification (remap_records) is the caller's job."""
    action_cfg = safe_config(config)["actions"][action]
    system = prompt("propose_fix", rules=prompt("rules"))
    if kind == "quarantine":
        sample = _cluster_sample(quarantine or [])
        clusters = Counter((q["reason"], q.get("field")) for q in quarantine or [])
        evidence = {
            "quarantined_total": len(quarantine or []),
            "reasons": [{"reason": r, "field": f, "count": n} for (r, f), n in clusters.most_common()],
            "raw_records_masked": [{"reason": q["reason"], "field": q.get("field"), "raw": mask(q["raw"])} for q in sample],
        }
    else:
        evidence = {"run": {k: (run or {}).get(k) for k in ("status", "trigger", "error", "pages_fetched", "records_pulled", "records_invalid", "retries")}}
    user = scrub(f"Action: {action}\nAction config (YAML):\n{yaml.safe_dump({action: action_cfg}, sort_keys=False)}\n"
                 f"Problem ({kind}):\n{json.dumps(evidence, default=str)}")

    data = _parse_json(llm.generate(system, user, json_output=True))
    proposed, applied, _ = apply_changes(config, action, data.get("changes"))
    errors = _errors(validate_config(proposed)) if applied else []
    if errors:
        retry = f"{user}\n\n---\nYour previous answer:\n{json.dumps(data)}\n\n{prompt('propose_retry', errors=_describe(errors))}"
        data = _parse_json(llm.generate(system, retry, json_output=True))
        proposed, applied, _ = apply_changes(config, action, data.get("changes"))
        errors = _errors(validate_config(proposed)) if applied else []
    out = {"summary": str(data.get("summary", "")).strip() or "No explanation was given.", "changes": applied, "errors": errors}
    if applied:
        out["proposed_config"] = proposed
    return out
