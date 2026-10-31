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
from urllib.parse import urlsplit

import yaml

from app.ai.client import LLMClient, LLMError
from app.ai.docs import DocsError
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

def duplicate_keys(text: str) -> list[dict]:
    """YAML silently keeps the LAST of two equal keys, so a model that writes `requires:` twice loses the first block
    without any error. Report each repeated key so it can be fed back like any other problem."""
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return []
    found: list[dict] = []

    def walk(node, path: str) -> None:
        if isinstance(node, yaml.MappingNode):
            seen: set = set()
            for key_node, value in node.value:
                key = key_node.value if isinstance(key_node, yaml.ScalarNode) else None
                where = f"{path}.{key}" if path else str(key)
                if key in seen:
                    found.append({"path": where, "message": "appears twice in the same block: keep only one", "severity": "error"})
                seen.add(key)
                walk(value, where)
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                walk(item, f"{path}[{i}]")

    walk(root, "")
    return found


_PLACEHOLDER = re.compile(r"\{\{\s*vars\.([A-Za-z_]\w*)\s*\}\}")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def finalize(config: dict) -> dict:
    """Make the draft ready to review. Everything the person would otherwise have to type is filled with the model's
    example, so they only have to check it: every {{vars.x}} gets a value (from requires.vars, else a clear placeholder),
    and value_map keys become strings (YAML turns a bare `true` into a boolean, which would never match)."""
    cfg = deepcopy(config)
    requires = (cfg.get("requires") or {}).get("vars") or {}
    wanted = list(dict.fromkeys([*requires, *_PLACEHOLDER.findall(" ".join(_strings({k: v for k, v in cfg.items() if k != "vars"})))]))
    vars_ = dict(cfg.get("vars") or {})
    for name in wanted:
        if vars_.get(name) in (None, ""):
            info = requires.get(name) if isinstance(requires.get(name), dict) else {}
            vars_[name] = str(info.get("example") or f"your-{name.replace('_', '-')}")
    if vars_:
        cfg["vars"] = vars_
    for action in (cfg.get("actions") or {}).values():
        for entry in (action.get("map") or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get("value_map"), dict):
                entry["value_map"] = {("true" if k is True else "false" if k is False else str(k)): v for k, v in entry["value_map"].items()}
    return cfg


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
        issues = issues + duplicate_keys(answer)
        errors = _errors(issues)
        attempts.append({"attempt": attempt, "valid": config is not None and not errors, "error_count": len(errors)})
        if not errors and config is not None:
            break
        if attempt == RETRIES + 1:
            break
        follow_up = prompt("fix_config", errors=_describe(issues) or "- the text is not valid YAML")
        answer = _strip_fences(llm.generate(system, f"{user}\n\n---\nYour previous answer:\n{answer}\n\n{follow_up}"))
    if config is not None and not _errors(issues):
        config = finalize(config)
        issues = validate_config(config)
        answer = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=110)
    return {"yaml": answer, "config": config, "errors": issues, "attempts": attempts}


# ---------------------------------------------------------------- find the documentation from a service name

class DocsNotFound(DocsError):
    def __init__(self, service: str, tried: list[dict]):
        super().__init__(f"could not find usable API documentation for {service!r} (tried {len(tried)} page{'s' if len(tried) != 1 else ''})")
        self.tried = tried


# A page is useful when it names an endpoint for something the platform stores: users, devices or alerts.
ENDPOINTS = re.compile(r"/[\w./{}-]*(users?|members?|accounts?|devices?|hosts?|endpoints?|assets?|alerts?|events?|findings?|incidents?|vulnerabilit\w*)\b", re.IGNORECASE)
VERBS = re.compile(r"\b(GET|POST)\b")  # often rendered apart from the path, so not required to touch it
URL_ROUNDS = 2  # ask for candidates, and once more if none of them worked
MAX_PAGES_TRIED = 14
MAX_CRAWLED = 3  # pages that loaded but were not the reference: their links are offered to the model


MIN_ENDPOINT_HITS = 3  # one stray mention is not a reference page


def useful(text: str) -> bool:
    return bool(VERBS.search(text)) and len(ENDPOINTS.findall(text)) >= MIN_ENDPOINT_HITS


def _urls(data: dict) -> list[str]:
    urls = [u.strip() for u in data.get("urls", []) if isinstance(u, str) and u.strip().startswith("https://")]
    return list(dict.fromkeys(urls))[:6]


def suggest_urls(llm: LLMClient, service: str, failed: list[dict] | None = None) -> list[str]:
    user = f"Service: {service}"
    if failed:
        user += "\nThese URLs did not work, so suggest different ones:\n" + "\n".join(f"- {f['url']} ({f['reason']})" for f in failed)
    return _urls(_parse_json(llm.generate(prompt("discover_docs"), scrub(user), json_output=True)))


def pick_links(llm: LLMClient, service: str, page: dict) -> list[str]:
    """The page loaded but is not the reference: let the model choose which of its links to follow."""
    allowed = {link["url"] for link in page.get("links", [])}
    if not allowed:
        return []
    listing = "\n".join(f"{link['url']}  ({link['text']})" for link in page["links"])
    data = _parse_json(llm.generate(prompt("pick_links"), scrub(f"Service: {service}\nPage: {page['url']}\nLinks:\n{listing}"), json_output=True))
    return [u for u in _urls(data) if u in allowed][:4]


def parent_pages(urls: list[str], limit: int = 4) -> list[str]:
    """A guessed deep link that does not exist usually has a real parent page (and the site's front page) that links
    to the right place. Deepest parents first, each only once."""
    out: list[str] = []
    for url in urls:
        parts = urlsplit(url)
        segments = [x for x in parts.path.split("/") if x]
        for n in range(len(segments) - 1, -1, -1):
            parent = f"https://{parts.netloc}/" + "/".join(segments[:n]) + ("/" if n else "")
            if parent not in out and parent not in urls:
                out.append(parent)
    return sorted(out, key=lambda u: -len(u))[:limit]


def find_docs(llm: LLMClient, service: str, fetch) -> tuple[dict, list[dict]]:
    """Ask the model where the documentation is and try pages until one has real API content: first its guesses, then
    the links on pages that loaded but were not the reference, then a second round of guesses that avoids the failures.
    Returns (page, tried). Raises DocsNotFound, carrying everything that was tried, when nothing worked."""
    tried: list[dict] = []
    seen: set[str] = set()
    followed: set[str] = set()
    crawl: list[dict] = []  # pages that loaded but were not the reference
    last: dict = {}  # the page the latest attempt loaded without it being the reference

    def attempt(url: str) -> dict | None:
        last.clear()
        if url in seen or len(tried) >= MAX_PAGES_TRIED:
            return None
        seen.add(url)
        try:
            page = fetch(url)
        except DocsError as exc:
            tried.append({"url": url, "ok": False, "reason": str(exc)})
            return None
        if not useful(page["text"]):
            if not any(t["url"] == page["url"] for t in tried):  # another address that led to a page already seen
                tried.append({"url": page["url"], "ok": False, "reason": "no endpoints for users, devices or alerts were found on the page"})
                if page.get("links") and len(crawl) < MAX_CRAWLED:
                    crawl.append(page)
                    last.update(page)
            return None
        tried.append({"url": page["url"], "ok": True, "reason": None})
        return page

    def follow(landing: dict) -> dict | None:
        """The page loaded but is not the reference: let the model pick which of its links to try."""
        if landing["url"] in followed:
            return None
        followed.add(landing["url"])
        for link in pick_links(llm, service, landing):
            if found := attempt(link):
                return found
        return None

    for round_ in range(URL_ROUNDS):
        for url in suggest_urls(llm, service, [t for t in tried if not t["ok"]]):
            found = attempt(url)
            if not found and last:  # a front page: its links come before the next guess
                found = follow(dict(last))
            if found:
                return found, tried
        if round_ == 0:  # before guessing again, look where the failed guesses should have been, then follow links
            for url in parent_pages([t["url"] for t in tried if not t["ok"]]):
                found = attempt(url) or (follow(dict(last)) if last else None)
                if found:
                    return found, tried
            for earlier in crawl:
                if found := follow(earlier):
                    return found, tried
    raise DocsNotFound(service, tried)


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
