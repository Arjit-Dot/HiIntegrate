"""AI routes (D-14). The only place `app.ai` is called, so the product works fully with the AI switched off.

Every route answers 501 when LLM_API_KEY is not set. Nothing here saves anything: a person applies a fix
with the normal PUT /integrations/{id}.
"""

import re
from collections.abc import Callable
from copy import deepcopy
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai import features
from app.ai.client import LLMClient, LLMError
from app.ai.docs import DocsError, check_url, fetch_docs, prepare_text
from app.api.deps import outbound_client_dep, session_dep
from app.core.errors import ApiError
from app.engine import remap_records, test_action
from app.engine.placeholders import PlaceholderError, fill
from app.scheduler.runner import UnknownAction
from app.secrets import SecretNotFound, get_secret, list_secrets
from app.storage import repo

router = APIRouter(tags=["AI"])
SessionDep = Annotated[Session, Depends(session_dep)]
RECHECK_LIMIT = 200  # D-14: at most 200 stored records are re-checked


def llm_dep() -> LLMClient | None:
    """Tests override this with a scripted model."""
    return LLMClient.from_settings()


def require_llm(llm: LLMClient | None) -> LLMClient:
    if llm is None:
        raise ApiError(501, "unsupported", "The AI features are switched off: LLM_API_KEY is not set")
    return llm


LlmDep = Annotated[LLMClient | None, Depends(llm_dep)]


def ask(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LLMError as exc:
        raise ApiError(502, "internal_error", f"The AI model failed: {exc}") from None


_HOST_VAR = re.compile(r"^(?P<pre>[^{}/]*)\{\{\s*vars\.(?P<var>\w+)\s*\}\}(?P<post>[^{}/]*)$")


def fill_vars_from_pin(config: dict, host: str) -> dict:
    """If the base URL is `https://<prefix>{{vars.x}}<suffix>/...` and the secret is already pinned to `host`, the value of x
    is whatever is left of the host: the person's own site or domain, so they do not have to type it."""
    base = urlsplit(config["base_url"])
    m = _HOST_VAR.match(base.netloc)
    if not m or not host.startswith(m["pre"]) or not host.endswith(m["post"]) or len(host) <= len(m["pre"]) + len(m["post"]):
        return {}
    value = host[len(m["pre"]):len(host) - len(m["post"])]
    config.setdefault("vars", {})[m["var"]] = value
    return {m["var"]: value}


_EXAMPLE_START = ("your-", "you@", "admin@your-", "my-")


def fill_vars_from_saved(s: Session, config: dict, secret_name: str, host: str) -> dict:
    """The person already told us their account email, org or similar when they set up this service before: copy those
    values from a saved integration that uses the same secret on the same host, but only over the AI's example values."""
    vars_ = config.get("vars") or {}
    examples = {k: str(v.get("example")) for k, v in ((config.get("requires") or {}).get("vars") or {}).items() if isinstance(v, dict)}
    filled: dict = {}
    for row in repo.list_integrations(s):
        other = row.config
        if (other.get("auth") or {}).get("secret") != secret_name:
            continue
        try:
            if urlsplit(fill(other["base_url"], vars=other.get("vars"))).hostname != host:
                continue
        except PlaceholderError:
            continue
        for k, v in (other.get("vars") or {}).items():
            current = str(vars_.get(k, ""))
            if k in vars_ and k not in filled and v not in (None, "") and current != str(v) and (current == examples.get(k) or current.startswith(_EXAMPLE_START)):
                config["vars"][k] = v
                filled[k] = v
    return filled


def make_tester(s: Session, client):
    """Try a draft against the real service, first page only, nothing saved (B-3). Built to be safe to run on a draft the AI
    wrote from a web page: the secret is sent only to the host it is already pinned to, never to a host the AI chose."""

    def skipped(config: dict, reason: str, filled: dict | None = None) -> tuple[dict, dict]:
        return config, {"ran": False, "skipped_reason": reason, "missing_paths": [], "notes": [], "filled_vars": filled or {}}

    def tester(config: dict) -> tuple[dict, dict]:
        config = deepcopy(config)
        action = next((n for n, a in config["actions"].items() if a["mode"] == "pull"), None)
        if action is None:
            return skipped(config, "there is no pull action to test")
        auth = config["auth"]
        try:
            secret = get_secret(auth["secret"], s)
        except SecretNotFound:
            return skipped(config, f"the secret {auth['secret']} is not set yet: enter its value, then press Test connection")
        if secret.host is None:
            return skipped(config, f"the secret {auth['secret']} is not pinned to a host, so it is not sent to an address the AI chose")
        filled = fill_vars_from_pin(config, secret.host)
        filled.update(fill_vars_from_saved(s, config, auth["secret"], secret.host))
        try:
            host = urlsplit(fill(config["base_url"], vars=config.get("vars"))).hostname or ""
            check_url(f"https://{host}/")  # a public address only, whatever the draft says
        except (PlaceholderError, DocsError) as exc:
            return skipped(config, f"the base URL cannot be tried yet ({exc}). Fill in Variables, then press Test connection", filled)
        if host != secret.host:
            return skipped(config, f"the secret {auth['secret']} is pinned to {secret.host}, but this config calls {host}", filled)
        result = test_action(config, action, client=client, secret_lookup=lambda name: get_secret(name, s))
        return config, {"ran": True, "action": action, "ok": result["ok"], "status_code": result["status_code"], "missing_paths": result["missing_paths"],
                        "notes": result["notes"], "raw_sample": result["raw_sample"], "filled_vars": filled}

    return tester


class GenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1)
    url: str | None = Field(default=None, min_length=1, max_length=2000)  # AI mode: a documentation page the server reads
    service: str | None = Field(default=None, min_length=1, max_length=100)  # AI mode: a service name, such as "Jira"; the AI finds the docs


def docs_dep():
    """Tests override this so no real page is fetched."""
    return fetch_docs


class SuggestMappingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_schema: Literal["user", "device", "alert"]
    sample: object  # a pasted response: a list of records, an object holding a list, or one record
    mapping: dict[str, dict] | None = None  # edited entries to check against the sample, with no model call


class SummarizeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["user", "device", "alert"] = "user"
    source: str | None = None


class ProposeFixBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["quarantine", "run_failure"]
    integration: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    action: str
    run_id: str | None = None


@router.post("/ai/generate-config")
def generate_config(body: GenerateBody, llm: LlmDep, fetch: Annotated[Callable[[str], dict], Depends(docs_dep)], s: SessionDep,
                    client: Annotated[object, Depends(outbound_client_dep)]) -> dict:
    llm = require_llm(llm)
    if not (body.text or body.url or body.service):
        raise ApiError(422, "validation_error", "send a service name, a documentation url or some text",
                       {"errors": [{"path": "service", "message": "give a service name, a url or text", "severity": "error"}]})

    def unusable(message: str, path: str, tried: list[dict] | None = None):
        details = {"errors": [{"path": path, "message": message, "severity": "error"}], **({"tried": tried} if tried is not None else {})}
        return ApiError(422, "validation_error", f"The documentation cannot be used: {message}", details)

    parts: list[str] = [f"Service: {body.service}"] if body.service else []
    page, tried = None, None
    if body.url:  # a link beats a name
        try:
            page = fetch(body.url)
        except DocsError as exc:
            raise unusable(str(exc), "url") from None
    elif body.service and not body.text:  # a name alone: the AI finds the documentation and tries pages until one works
        try:
            page, tried = ask(features.find_docs, llm, body.service, fetch)
        except features.DocsNotFound as exc:
            raise unusable(f"{exc}. Attach the documentation as a file instead", "service", exc.tried) from None
    if page:
        parts.append(f"Documentation page: {page['url']}\n\n{page['text']}")
    if body.text:
        parts.append(prepare_text(body.text))
    names = sorted(x["name"] for x in list_secrets(s))  # names only, never values
    out = ask(features.generate_config, llm, "\n\n".join(parts), existing_secrets=names, tester=make_tester(s, client))
    if out.get("test"):
        out["test"] = {k: v for k, v in out["test"].items() if k != "raw_sample"}  # real data stays on the server
    elif "test" in out:
        del out["test"]
    if page:
        out["source"] = {"url": page["url"], "chars": page["chars"], "truncated": page["truncated"]}
    if tried is not None:
        out["tried"] = tried
    return out


@router.post("/ai/suggest-mapping")
def suggest_mapping(body: SuggestMappingBody, llm: LlmDep) -> dict:
    """With `mapping`, only check the person's entries against the sample (no model, so it works with AI switched off).
    Without it, the model suggests a path per field and the platform checks each one against the real records."""
    if not isinstance(body.sample, (dict, list)) or not features.find_records(body.sample)[1]:
        raise ApiError(422, "validation_error", "The sample has no records: paste a response that contains at least one object",
                       {"errors": [{"path": "sample", "message": "needs at least one record", "severity": "error"}]})
    if body.mapping is not None:
        return features.check_mapping(body.target_schema, body.sample, body.mapping)
    return ask(features.suggest_mapping, require_llm(llm), body.target_schema, body.sample)


@router.post("/ai/summarize")
def summarize(llm: LlmDep, s: SessionDep, body: SummarizeBody | None = None) -> dict:
    llm = require_llm(llm)
    body = body or SummarizeBody()
    records, total = repo.list_results(s, body.target, body.source, limit=200)
    if not records:
        return {"summary": f"There are no stored {body.target} records" + (f" from {body.source}" if body.source else "") + " yet."}
    return {"summary": ask(features.summarize, llm, body.target, records, total)}


@router.post("/ai/propose-fix")
def propose_fix(body: ProposeFixBody, llm: LlmDep, s: SessionDep) -> dict:
    llm = require_llm(llm)
    config = repo.get_integration(s, body.integration).config
    if body.action not in config["actions"]:
        raise UnknownAction(f"{body.integration} has no action {body.action!r}")

    run = None
    if body.kind == "run_failure":
        if not body.run_id:
            raise ApiError(422, "validation_error", "run_id is required for run_failure",
                           {"errors": [{"path": "run_id", "message": "is required for run_failure", "severity": "error"}]})
        run = repo.run_dict(repo.get_run(s, body.run_id))
        if run["integration"] != body.integration or run["action"] != body.action:
            raise repo.NotFound(f"run {body.run_id} is not a run of {body.integration}.{body.action}")
        result = ask(features.propose_fix, llm, config, body.action, kind="run_failure", run=run)
        return {**result, "verification": None}

    rows = repo.export_quarantine(s, source=body.integration, action=body.action, run_id=body.run_id)[-RECHECK_LIMIT:]
    if not rows:
        return {"summary": "There are no quarantined records for this action, so there is nothing to fix.", "changes": [], "errors": [], "verification": None}
    result = ask(features.propose_fix, llm, config, body.action, kind="quarantine", quarantine=rows)
    verification = None
    if result["changes"] and not result["errors"]:
        records, still = remap_records(result["proposed_config"], body.action, [r["raw"] for r in rows])
        verification = {"checked": len(rows), "rescued": len(records), "still_quarantined": len(still), "mapped_samples": records[:3]}
    return {**result, "verification": verification}
