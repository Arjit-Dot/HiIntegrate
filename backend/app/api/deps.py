"""Shared pieces for the routes: the database engine and session, the outbound HTTP client, and paging."""

from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, Query
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.storage import get_engine, session_factory


def engine_dep() -> Engine:
    return get_engine()


def session_dep(engine: Annotated[Engine, Depends(engine_dep)]) -> Iterator[Session]:
    session = session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def outbound_client_dep() -> httpx.Client | None:
    """The engine opens its own client when this is None. Tests override it to reach a mock service."""
    return None


Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def page(items: list, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}
