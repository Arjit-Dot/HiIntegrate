from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.audit import record
from app.api.deps import Account, Limit, Offset, page, session_dep
from app.storage import repo

router = APIRouter(tags=["Runs"])
SessionDep = Annotated[Session, Depends(session_dep)]


@router.get("/runs")
def list_runs(s: SessionDep, account: Account, limit: Limit = 50, offset: Offset = 0, integration: str | None = None, status: str | None = None) -> dict:
    items, total = repo.list_runs(s, account, integration, status, limit, offset)
    return page(items, total, limit, offset)


@router.get("/runs/{run_id}")
def get_run(run_id: str, s: SessionDep, account: Account) -> dict:
    return repo.run_dict(repo.get_run(s, account, run_id))


@router.delete("/runs")
def delete_old_runs(s: SessionDep, account: Account, older_than_days: Annotated[int, Query(ge=0)]) -> dict:
    """S-10: delete this account's finished runs older than N days. A running run and the newest finished run of each
    action are kept."""
    n = repo.purge_runs(s, repo.cutoff_iso(older_than_days), account)
    record(s, account, "runs.purged", f"{n} run(s) older than {older_than_days} days")
    return {"deleted": n}
