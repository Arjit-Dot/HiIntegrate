"""Secrets are write-only (D-7.2, D-7.5, D-7.6): a value can be set, never read back."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.audit import record
from app.api.deps import Account, session_dep
from app.core.errors import ApiError
from app.secrets import SecretError, StoreUnavailable, list_secrets, set_secret

router = APIRouter(tags=["Secrets"])
SessionDep = Annotated[Session, Depends(session_dep)]


class SecretBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1)
    host: str


@router.get("/secrets")
def get_secrets(s: SessionDep, account: Account) -> dict:
    return {"items": list_secrets(s, account)}


@router.put("/secrets/{name}", status_code=204)
def put_secret(name: Annotated[str, Path(pattern=r"^[A-Za-z0-9_]{1,64}$")], body: SecretBody, s: SessionDep, account: Account) -> Response:
    try:
        set_secret(s, account, name, body.value, body.host)
    except StoreUnavailable as exc:
        raise ApiError(501, "unsupported", str(exc)) from None
    except SecretError as exc:
        raise ApiError(400, "validation_error", str(exc), {"errors": [{"path": "host", "message": str(exc), "severity": "error"}]}) from None
    record(s, account, "secret.set", name)
    return Response(status_code=204)
