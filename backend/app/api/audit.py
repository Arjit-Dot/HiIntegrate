"""The audit log (S-7): who changed what. Read-only; entries are written by the routes that change data."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Account, Limit, Offset, page, session_dep
from app.core.logging import request_id_var
from app.storage import repo

router = APIRouter(tags=["Audit"])
SessionDep = Annotated[Session, Depends(session_dep)]


def record(s: Session, account: str, event: str, target: str | None = None, revision: int | None = None) -> None:
    """Write one audit entry in the caller's transaction. Names and revisions only, never a value."""
    rid = request_id_var.get()
    repo.add_audit(s, account, event, target, revision, None if rid == "-" else rid)


@router.get("/audit")
def list_audit(s: SessionDep, account: Account, limit: Limit = 50, offset: Offset = 0, event: str | None = None,
               target: str | None = None) -> dict:
    items, total = repo.list_audit(s, account, limit, offset, event, target)
    return page(items, total, limit, offset)
