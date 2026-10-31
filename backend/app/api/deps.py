"""Shared pieces for the routes: the database engine and session, the outbound HTTP client, and paging."""

from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, Header, Query
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import auth
from app.core.errors import ApiError
from app.storage import get_engine, repo, session_factory


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


def account_dep(s: Annotated[Session, Depends(session_dep)], x_session_token: Annotated[str | None, Header()] = None) -> str:
    """D-18: the signed-in username, from the X-Session-Token header. Every data route depends on this, and passes the
    result to storage, so a person can only ever reach their own rows. 401 when there is no valid sign-in."""
    row = repo.get_auth_session(s, auth.token_hash(x_session_token)) if x_session_token else None
    if row is None:
        raise ApiError(401, "unauthorized", "Sign in first: send the session token you got from /auth/login in the X-Session-Token header.")
    return row.account


Account = Annotated[str, Depends(account_dep)]
