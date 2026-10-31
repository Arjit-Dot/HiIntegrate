"""Integration routes (D-6, D-15): configs live in the database and change in place."""

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.audit import record
from app.api.configs import integration_out, read_config, require_valid, summary
from app.api.deps import Account, Limit, Offset, engine_dep, outbound_client_dep, page, session_dep
from app.core.errors import ApiError
from app.scheduler import runner
from app.storage import repo, session_scope

router = APIRouter(tags=["Integrations"])
SessionDep = Annotated[Session, Depends(session_dep)]
EngineDep = Annotated[Engine, Depends(engine_dep)]
ClientDep = Annotated[httpx.Client | None, Depends(outbound_client_dep)]


class EnabledBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class TestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    inputs: dict[str, Any] | None = None


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, Any] | None = None


@router.get("/integrations")
def list_integrations(s: SessionDep, account: Account, limit: Limit = 50, offset: Offset = 0, category: str | None = None,
                      status: str | None = None, q: str | None = None) -> dict:
    items = [summary(s, r) for r in repo.list_integrations(s, account)]
    if category:
        items = [i for i in items if i["category"] == category]
    if status:
        items = [i for i in items if i["health"]["status"] == status]
    if q:
        items = [i for i in items if q.lower() in (i["name"] + " " + i["display_name"]).lower()]
    return page(items[offset:offset + limit], len(items), limit, offset)


@router.post("/integrations/validate")
async def validate(request: Request) -> dict:
    config, issues = await read_config(request)
    return {"valid": config is not None and not any(i["severity"] == "error" for i in issues), "errors": issues}


@router.post("/integrations", status_code=201)
async def create(request: Request, s: SessionDep, account: Account) -> dict:
    config, issues = await read_config(request)
    row = repo.create_integration(s, account, require_valid(config, issues))
    record(s, account, "integration.created", row.name, row.revision)
    return integration_out(s, row)


@router.get("/integrations/{name}")
def get_one(name: str, s: SessionDep, account: Account) -> dict:
    return integration_out(s, repo.get_integration(s, account, name))


@router.put("/integrations/{name}")
async def replace(name: str, request: Request, s: SessionDep, account: Account) -> dict:
    """D-15: update the existing row in place. To add an action, send the config with it included."""
    config, issues = await read_config(request)
    config = require_valid(config, issues)
    if config["name"] != name:
        raise ApiError(400, "validation_error", "The config's name must match the integration being replaced",
                       {"errors": [{"path": "name", "message": f"must stay {name}, because records are keyed by it", "severity": "error"}]})
    row = repo.replace_integration(s, account, name, config)
    record(s, account, "integration.updated", name, row.revision)
    return integration_out(s, row)


@router.delete("/integrations/{name}", status_code=204)
def delete(name: str, s: SessionDep, account: Account) -> Response:
    repo.delete_integration(s, account, name)
    record(s, account, "integration.deleted", name)
    return Response(status_code=204)


@router.patch("/integrations/{name}/enabled")
def set_enabled(name: str, body: EnabledBody, s: SessionDep, account: Account) -> dict:
    row = repo.set_enabled(s, account, name, body.enabled)
    record(s, account, "integration.enabled" if body.enabled else "integration.disabled", name, row.revision)
    return summary(s, row)


@router.get("/integrations/{name}/health")
def get_health(name: str, s: SessionDep, account: Account) -> dict:
    return repo.health(s, repo.get_integration(s, account, name))


@router.post("/integrations/{name}/test")
def test(name: str, body: TestBody, engine: EngineDep, client: ClientDep, account: Account) -> dict:
    with session_scope(engine) as s:
        record(s, account, "action.tested", f"{name}/{body.action}")
    return runner.test(engine, account, name, body.action, body.inputs, client=client)


@router.post("/integrations/{name}/actions/{action}/run")
def run_action(name: str, action: str, background: BackgroundTasks, response: Response, engine: EngineDep, client: ClientDep,
               account: Account, body: RunBody | None = None):
    inputs = body.inputs if body else None
    started = runner.begin(engine, account, name, action, "manual", inputs)
    with session_scope(engine) as s:
        record(s, account, "action.run", f"{name}/{action}")
    if started.mode == "pull":  # D-6: a pull finishes in the background. Poll GET /runs/{run_id}.
        background.add_task(runner.execute, engine, started, inputs, client=client)
        response.status_code = 202
        return {"run_id": started.run_id, "status": "running"}
    result = runner.execute(engine, started, inputs, client=client)
    response.headers["X-Run-Id"] = started.run_id
    if result.status == "success" and result.record:
        return result.record
    if result.status == "success":
        q = result.quarantined or {}
        raise ApiError(502, "run_failed", f"The record was rejected: {q.get('reason', 'invalid')} on {q.get('field', '?')}",
                       {"run_id": started.run_id, "error_code": "bad_response"})
    raise ApiError(502, "run_failed", result.error["message"], {"run_id": started.run_id, "error_code": result.error["code"]})



