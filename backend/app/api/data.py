"""Stored records and quarantine (D-3, D-4, D-6)."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import Account, Limit, Offset, page, session_dep
from app.storage import repo

router = APIRouter(tags=["Data"])
SessionDep = Annotated[Session, Depends(session_dep)]
Target = Literal["user", "device", "alert"]
Reason = Literal["missing_required_field", "transform_failed", "invalid_value"]


@router.get("/results")
def results(s: SessionDep, account: Account, target: Annotated[Target, Query()], source: str | None = None, limit: Limit = 50, offset: Offset = 0) -> dict:
    items, total = repo.list_results(s, account, target, source, limit, offset)
    return page(items, total, limit, offset)


@router.get("/users/unified")
def unified_users(s: SessionDep, account: Account, source: str | None = None, limit: Limit = 50, offset: Offset = 0) -> dict:
    """D-16: one entry per person, matched by lowercased email, with every service they appear in."""
    items, total = repo.list_unified_users(s, account, source, limit, offset)
    return page(items, total, limit, offset)


@router.get("/quarantine")
def quarantine(s: SessionDep, account: Account, limit: Limit = 50, offset: Offset = 0, source: str | None = None, action: str | None = None,
               run_id: str | None = None, target_schema: Target | None = None, reason: Reason | None = None) -> dict:
    items, total = repo.list_quarantine(s, account, limit, offset, source=source, action=action, run_id=run_id, target_schema=target_schema, reason=reason)
    return page(items, total, limit, offset)


@router.get("/quarantine/export")
def export(s: SessionDep, account: Account, source: str | None = None, action: str | None = None, run_id: str | None = None,
           target_schema: Target | None = None, reason: Reason | None = None) -> Response:
    """Every quarantined record in one file, unpaged (the export you asked for in D-4)."""
    items = repo.export_quarantine(s, account, source=source, action=action, run_id=run_id, target_schema=target_schema, reason=reason)
    return Response(json.dumps(items, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="quarantine.json"'})
