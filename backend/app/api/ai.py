"""AI routes (D-14). The only place `app.ai` is called, so the product works fully with the AI switched off.

Every route answers 501 when LLM_API_KEY is not set. Nothing here saves anything: a person applies a fix
with the normal PUT /integrations/{id}.
"""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai import features
from app.ai.client import LLMClient, LLMError
from app.ai.docs import DocsError, fetch_docs, prepare_text
from app.api.deps import session_dep
from app.core.errors import ApiError
from app.engine import remap_records
from app.scheduler.runner import UnknownAction
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


class GenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1)
    url: str | None = Field(default=None, min_length=1, max_length=2000)  # AI mode: a documentation page the server reads
    service: str | None = Field(default=None, min_length=1, max_length=100)  # AI mode: a service name, such as "Jira"; the AI finds the docs


def docs_dep():
    """Tests override this so no real page is fetched."""
    return fetch_docs


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
def generate_config(body: GenerateBody, llm: LlmDep, fetch: Annotated[Callable[[str], dict], Depends(docs_dep)]) -> dict:
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
    out = ask(features.generate_config, llm, "\n\n".join(parts))
    if page:
        out["source"] = {"url": page["url"], "chars": page["chars"], "truncated": page["truncated"]}
    if tried is not None:
        out["tried"] = tried
    return out


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
