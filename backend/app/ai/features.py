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

import jmespath
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


AUTH_SCHEMES = {"ssws", "bearer", "token", "basic", "bot", "apikey", "key"}


def _tidy_auth(auth: dict) -> None:
    """Two slips models make with a header key: the scheme as the header NAME (`name: SSWS`), and a prefix with no space
    (`SSWS` + token gives `SSWSabc...`). Both are fixed here, the way the documentation means it."""
    if auth.get("type") != "api_key" or auth.get("in") != "header":
        return
    name, prefix = str(auth.get("name") or ""), auth.get("prefix")
    if name.lower() in AUTH_SCHEMES:
        auth["name"] = "Authorization"
        prefix = prefix or name
    if isinstance(prefix, str) and prefix and prefix.strip().lower() in AUTH_SCHEMES and not prefix.endswith(" "):
        prefix = prefix.strip() + " "
    if prefix:
        auth["prefix"] = prefix


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
    _tidy_auth(cfg.get("auth") or {})
    for action in (cfg.get("actions") or {}).values():
        for entry in (action.get("map") or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get("value_map"), dict):
                entry["value_map"] = {("true" if k is True else "false" if k is False else str(k)): v for k, v in entry["value_map"].items()}
    return cfg


def _read_draft(answer: str) -> tuple[dict | None, list[dict]]:
    config, issues = load_config(answer)
    return config, issues + duplicate_keys(answer)


def _needs_fixing(test: dict) -> bool:
    """A test run says the paths are wrong when it reached the service and mapped fields found nothing, or the records path
    found no list. A call that failed for another reason (login, network) is not the draft's fault."""
    if test.get("problems"):  # paging that cannot work: found from the settings alone, so it needs no real call
        return True
    if not test.get("ran"):
        return False
    if test.get("ok"):
        return bool(test.get("missing_paths"))
    if test.get("status_code") in (405, 410):  # the endpoint or method is gone: the draft's fault, not the login's
        return True
    # The service refused the request itself (a bad path, query or body), and no variable is still an example value, which
    # would be the person's to fix: the draft is wrong, and the service's own message (in the notes) says how.
    if test.get("status_code") in (400, 404, 422) and not any(n.startswith("Check: Variable") for n in test.get("notes", [])):
        return True
    # The saved secret was sent to its own host and refused: the value is the person's, but HOW it is sent (bearer or a header
    # with a prefix such as `SSWS `) is the draft's choice and a common mistake.
    if test.get("status_code") in (401, 403) and not any(n.startswith("Check: Variable") for n in test.get("notes", [])):
        return True
    return any("unexpected response shape" in n for n in test.get("notes", []))


OAUTH_HINTS = re.compile(r"client[_ ]credentials|grant_type|oauth2?/token|/oauth/token", re.IGNORECASE)
TEST_FIXES = 3  # corrections after a real test


def _test_rank(test: dict, config: dict) -> tuple[int, int]:
    """How well a draft did against the real service, to keep the better of two: (level, mapped paths of the tested action).
    Level: works with every path found and the record accepted > works > refused or failed. The path count stops a "fix" that
    hides a missing field by swapping its path for a constant from winning."""
    quarantined = any("would be quarantined" in n for n in test.get("notes", []))
    if test.get("ok") and not test.get("missing_paths") and not test.get("problems") and not quarantined:
        level = 3
    elif test.get("ok"):
        level = 2
    else:
        level = 1 if test.get("ran") else 0
    action = (config.get("actions") or {}).get(test.get("action") or "", {})
    paths = sum(1 for e in (action.get("map") or {}).values() if isinstance(e, str) or (isinstance(e, dict) and e.get("path")))
    return level, paths


def _describe_test(test: dict) -> str:
    lines = [f"Action tested: {test.get('action')}"]
    if test.get("status_code") in (405, 410):
        lines.append(f"The service answered {test['status_code']}: this endpoint or method is no longer available. Use a current endpoint from the documentation.")
    elif test.get("status_code") in (401, 403):
        lines.append(f"The service answered {test['status_code']}: it refused the login. The secret value is the person's and is probably right; "
                     "check HOW the documentation says to send it: `auth.type` (bearer, basic or api_key), the header name and the prefix "
                     "(for example `Authorization: SSWS <token>` is api_key with name Authorization and prefix `SSWS `, not bearer).")
    elif test.get("status_code") in (400, 404, 422):
        lines.append(f"The service answered {test['status_code']}: it refused the request as written (the path, the query parameters or the body). "
                     "Its own message is in the notes below. Fix the request so the service accepts it, using the documentation.")
    if test.get("missing_paths"):
        lines.append("These mapped fields found nothing in the real record: " + ", ".join(test["missing_paths"]))
    lines += [f"Note: {n}" for n in test.get("notes", [])]
    if test.get("raw_sample") is not None:
        lines.append("A real record from the service (masked):\n" + json.dumps(mask(test["raw_sample"]), default=str)[:3000])
    return "\n".join(lines)


def _host_pattern(base_url: str) -> re.Pattern | None:
    """The host of a base URL as a pattern: `{{vars.x}}` stands for any text, so `{{vars.domain}}.atlassian.net` matches acme.atlassian.net."""
    host = re.sub(r":\d+$", "", base_url.split("://", 1)[-1].split("/")[0].split("@")[-1])
    if not host:
        return None
    parts = re.split(r"\{\{[^}]*\}\}", host)
    # A placeholder may stand for one name or for the whole host (`https://{{vars.domain}}` with domain=acme.okta.com).
    return re.compile(".+".join(re.escape(p) for p in parts), re.IGNORECASE)


def own_secret(config: dict, secret_hosts: dict[str, str | None]) -> dict:
    """A secret is pinned to one host, and entering a value for it again moves the pin. So a draft must not reuse an existing secret
    that belongs to another service: when the name exists and is pinned to a host this config does not call, give the draft its own name."""
    cfg = deepcopy(config)
    auth = cfg.get("auth") or {}
    name = auth.get("secret")
    pinned = secret_hosts.get(name) if name else None
    pattern = _host_pattern(cfg.get("base_url", ""))
    if not (name and pinned and pattern) or pattern.fullmatch(pinned):
        return cfg
    stem = re.sub(r"[^a-z0-9_]", "_", str(cfg.get("name", "service")).lower()).strip("_") or "service"
    new, n = f"{stem}_token", 2
    while new in secret_hosts:
        new, n = f"{stem}_token_{n}", n + 1
    auth["secret"] = new
    requires = cfg.get("requires")
    if isinstance(requires, dict) and isinstance(requires.get("secrets"), list):
        requires["secrets"] = [new if x == name else x for x in requires["secrets"]]
    return cfg


def generate_config(llm: LLMClient, text: str, *, existing_secrets: list[str] | None = None, tester=None,
                    secret_hosts: dict[str, str | None] | None = None) -> dict:
    """Docs, curl or a sample response in, a draft config out. Validate, and feed the errors back up to 2 times.
    Then, if `tester` is given, try the draft against the real service once and correct paths that found nothing.
    `tester(config) -> (config, report)` lives in the route: it owns the database, the secrets and the safety checks.
    Returns {yaml, config, errors, attempts, test}; `attempts` lets the UI show each step."""
    system = prompt("generate_config", rules=prompt("rules"), example_github=_template("github"), example_template=_template("service-template"),
                    existing_secrets=", ".join(existing_secrets or []) or "none")
    hosts = secret_hosts or {}
    user = scrub(text)
    attempts: list[dict] = []
    answer = _strip_fences(llm.generate(system, user))
    config, issues = None, []
    wanted_oauth = False
    for attempt in range(1, RETRIES + 2):
        config, issues = load_config(answer)
        issues = issues + duplicate_keys(answer)
        wanted_oauth = wanted_oauth or any("oauth2_client_credentials" in i.get("message", "") for i in issues)
        errors = _errors(issues)
        attempts.append({"attempt": attempt, "valid": config is not None and not errors, "error_count": len(errors)})
        if not errors and config is not None:
            break
        if attempt == RETRIES + 1:
            break
        follow_up = prompt("fix_config", errors=_describe(issues) or "- the text is not valid YAML")
        answer = _strip_fences(llm.generate(system, f"{user}\n\n---\nYour previous answer:\n{answer}\n\n{follow_up}"))
    test = None
    if config is not None and not _errors(issues):
        config = own_secret(finalize(config), hosts)
        if tester:
            config, test = tester(config)
            first_missing = test.get("missing_paths", [])
            # Each correction can expose the next problem (a removed endpoint, then a search the service refuses), so up to
            # TEST_FIXES rounds are allowed. Only a draft that tests at least as well as the current one replaces it.
            for _ in range(TEST_FIXES):
                if not _needs_fixing(test):
                    break
                follow_up = prompt("fix_after_test", result=_describe_test(test))
                fixed = _strip_fences(llm.generate(system, f"{user}\n\n---\nYour previous answer:\n{yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=110)}\n\n{follow_up}"))
                fixed_config, fixed_issues = _read_draft(fixed)
                if fixed_config is None or _errors(fixed_issues):
                    break
                candidate = own_secret(finalize(fixed_config), hosts)
                same = lambda c: {k: v for k, v in c.items() if k != "vars"}  # the tester fills in vars, so they do not count
                if same(candidate) == same(config):
                    attempts.append({"attempt": len(attempts) + 1, "valid": True, "error_count": 0})
                    break  # the model changed nothing, so asking again would not help
                new_config, test_after = tester(candidate)
                attempts.append({"attempt": len(attempts) + 1, "valid": True, "error_count": 0})
                if _test_rank(test_after, new_config) < _test_rank(test, config):
                    break  # the fix made it worse: keep the draft we had
                config, test = new_config, {**test_after, "corrected": True, "missing_before": first_missing}
        issues = validate_config(config)
        # The docs describe a token exchange (OAuth2 client credentials) and the draft just says bearer: the same stand-in, unannounced.
        wanted_oauth = wanted_oauth or ((config.get("auth") or {}).get("type") == "bearer" and bool(OAUTH_HINTS.search(text)))
        if wanted_oauth:  # the service needs a token exchange the platform cannot do; say so instead of passing off a stand-in
            issues.append({"path": "auth.type", "severity": "warning", "message":
                           "The documentation asks for OAuth2 client credentials, which the platform does not support yet. The draft uses "
                           f"{(config.get('auth') or {}).get('type')} instead, so it needs a token you get yourself, and such tokens usually "
                           "expire within hours: scheduled runs will then fail until you enter a new one."})
        answer = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=110)
    return {"yaml": answer, "config": config, "errors": issues, "attempts": attempts, "test": test}


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

SUMMARY_FIELDS = ("source", "status", "severity", "os")


def summarize(llm: LLMClient, target: str, records: list[dict], total: int, counts: dict[str, dict[str, int]] | None = None) -> str:
    """`counts` are exact counts over every stored record (from storage). Without them, the sample is counted, and says so."""
    stats: dict = {"total_stored": total, "sample_size": len(records)}
    for field in SUMMARY_FIELDS:
        found = (counts or {}).get(field) if counts is not None else dict(Counter(str(r[field]) for r in records if r.get(field) is not None).most_common(10))
        if found:
            stats[f"by_{field}" + ("" if counts is not None else "_in_sample")] = found
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


# ---------------------------------------------------------------- mapping suggestions

SCHEMA_FIELDS = {
    "user": ["id", "name", "email", "status", "last_login"],
    "device": ["id", "hostname", "ip", "os", "owner", "last_seen"],
    "alert": ["id", "type", "severity", "timestamp", "description"],
}
ALLOWED = {"status": ["active", "inactive", "suspended", "unknown"], "severity": ["low", "medium", "high", "critical", "unknown"]}
TRANSFORMS = {"string", "int", "float", "bool", "lowercase", "uppercase", "datetime"}
SAMPLE_RECORDS = 3  # how many sample records the model sees (D-14: masked)


def find_records(sample) -> tuple[str, list]:
    """Where the records are in a pasted response. A list is the records. An object with one list of objects in it
    (`data`, `items`, `users`...) means that list. Any other object is one record."""
    if isinstance(sample, list):
        return "@", [r for r in sample if isinstance(r, dict)]
    if isinstance(sample, dict):
        for key, value in sample.items():
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                return key, value
        return "@", ([sample] if sample else [])
    return "@", []


def _entry(field: str, spec: dict, records: list) -> dict:
    """Check one mapping entry against the sample: how many records the path finds a value in, and an example."""
    path = spec.get("path") or ""
    found, example = 0, None
    for r in records:
        try:
            value = jmespath.search(path, r) if path else None
        except jmespath.exceptions.JMESPathError:
            return {"field": field, "path": path, "transform": spec.get("transform"), "value_map": spec.get("value_map"), "confidence": "low",
                    "reason": "this is not a valid path", "found": 0, "of": len(records), "example": None, "valid": False}
        if value not in (None, ""):
            found += 1
            example = example if example is not None else value
    confidence = spec.get("confidence") if spec.get("confidence") in ("high", "medium", "low") else None
    reason = str(spec.get("reason") or "")
    if records and found == 0:
        confidence, reason = "low", (reason + " " if reason else "") + "Nothing was found at this path in the sample."
    elif records and found < len(records) and confidence == "high":
        confidence = "medium"
    return {"field": field, "path": path, "transform": spec.get("transform") if spec.get("transform") in TRANSFORMS else None,
            "value_map": spec.get("value_map") if isinstance(spec.get("value_map"), dict) else None,
            "confidence": confidence or ("high" if records and found == len(records) else "medium" if found else "low"),
            "reason": reason, "found": found, "of": len(records), "example": example, "valid": True}


def preview_mapping(target: str, fields: list[dict], records: list):
    """The first sample record as it would be saved with this mapping, or why it would be quarantined (the same mapper
    the platform runs). Returns {"record": ...} or {"quarantine": {"reason", "field"}}."""
    from app.engine.mapping import map_record

    mapping: dict = {}
    for f in fields:
        if not f["path"] or not f["valid"]:
            continue
        entry: dict = {"path": f["path"]}
        if f.get("transform"):
            entry["transform"] = f["transform"]
        if f.get("value_map"):
            entry["value_map"] = {str(k): v for k, v in f["value_map"].items()}
            entry["default"] = "unknown"
        mapping[f["field"]] = entry
    if "id" not in mapping or not records:
        return {"quarantine": {"reason": "missing_required_field", "field": "id"}}
    cfg = {"name": "preview", "actions": {"a": {"mode": "pull", "target_schema": target, "map": mapping, "required": ["id"]}}}
    out = map_record(cfg, "a", records[0], run_id="preview", fetched_at="2026-01-01T00:00:00Z")
    if "record" in out:
        return {"record": {k: v for k, v in out["record"].items() if k not in ("source", "fetched_at")}}
    q = out["quarantine"]
    return {"quarantine": {"reason": q["reason"], "field": q["field"]}}


def check_mapping(target: str, sample, mapping: dict) -> dict:
    """No model: check a mapping the person wrote or edited against the pasted sample."""
    records_path, records = find_records(sample)
    allowed = SCHEMA_FIELDS[target]
    fields = [_entry(f, spec, records) for f, spec in mapping.items() if f in allowed and isinstance(spec, dict)]
    return {"records_path": records_path, "records_found": len(records), "fields": fields, "preview": preview_mapping(target, fields, records)}


def suggest_mapping(llm: LLMClient, target: str, sample) -> dict:
    """A pasted sample response in, a JMESPath for each field of the target schema out, each one checked against the sample
    by the platform itself. The model's confidence is lowered when its path does not hold up on the real records."""
    _, records = find_records(sample)
    if not records:
        raise LLMError("the sample has no records: paste a response that contains at least one object")
    shown = [mask(r) for r in records[:SAMPLE_RECORDS]]
    schema = {f: ALLOWED.get(f, "any text or null") for f in SCHEMA_FIELDS[target]}
    user = scrub(f"Schema: {target}\nFields and allowed values: {json.dumps(schema)}\nSample records (masked):\n{json.dumps(shown, default=str)[:12000]}")
    data = _parse_json(llm.generate(prompt("suggest_mapping"), user, json_output=True))
    mapping = {}
    for item in data.get("fields", []) if isinstance(data.get("fields"), list) else []:
        if isinstance(item, dict) and item.get("field") in SCHEMA_FIELDS[target] and isinstance(item.get("path"), str):
            mapping[item["field"]] = item
    out = check_mapping(target, sample, mapping)
    order = {f: i for i, f in enumerate(SCHEMA_FIELDS[target])}
    out["fields"].sort(key=lambda f: order[f["field"]])
    return out
