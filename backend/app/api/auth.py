"""Register, sign in, sign out (D-18). Passwords are never returned or logged."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import auth
from app.api.deps import Account, session_dep
from app.core.errors import ApiError
from app.storage import repo

router = APIRouter(tags=["Auth"])
SessionDep = Annotated[Session, Depends(session_dep)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


def _signed_in(s: Session, username: str) -> dict:
    token, hashed = auth.new_token()
    expires = auth.expiry()
    repo.add_auth_session(s, hashed, username, expires)
    return {"username": username, "token": token, "expires_at": expires}


@router.post("/auth/register", status_code=201)
def register(body: Credentials, s: SessionDep) -> dict:
    if not auth.registration_open():
        raise ApiError(403, "unauthorized", "Registration is closed on this server.")
    try:
        username = auth.normalize_username(body.username)
        auth.check_password_rules(body.password)
    except auth.AuthError as exc:
        raise ApiError(400, "validation_error", str(exc)) from None
    repo.create_account(s, username, auth.hash_password(body.password))  # Conflict -> 409 "that username is taken"
    return _signed_in(s, username)


@router.post("/auth/login")
def login(body: Credentials, s: SessionDep) -> dict:
    username = (body.username or "").strip().lower()
    if auth.throttle.blocked(username):
        raise ApiError(429, "rate_limited", "Too many wrong passwords for this username. Wait a few minutes and try again.")
    account = repo.get_account(s, username)
    if account is None:
        auth.burn_time(body.password)
    if account is None or not auth.verify_password(body.password, account.password_hash):
        auth.throttle.fail(username)
        raise ApiError(401, "unauthorized", "Wrong username or password.")
    auth.throttle.clear(username)
    return _signed_in(s, account.username)


@router.post("/auth/logout", status_code=204)
def logout(account: Account, s: SessionDep, x_session_token: Annotated[str | None, Header()] = None) -> Response:
    repo.delete_auth_session(s, auth.token_hash(x_session_token or ""))
    return Response(status_code=204)


@router.get("/auth/me")
def me(account: Account) -> dict:
    return {"username": account}
