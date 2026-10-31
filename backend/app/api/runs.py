from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Limit, Offset, page, session_dep
from app.storage import repo

router = APIRouter(tags=["Runs"])
SessionDep = Annotated[Session, Depends(session_dep)]


@router.get("/runs")
def list_runs(s: SessionDep, limit: Limit = 50, offset: Offset = 0, integration: str | None = None, status: str | None = None) -> dict:
    items, total = repo.list_runs(s, integration, status, limit, offset)
    return page(items, total, limit, offset)


@router.get("/runs/{run_id}")
def get_run(run_id: str, s: SessionDep) -> dict:
    return repo.run_dict(repo.get_run(s, run_id))
