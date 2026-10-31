"""The API process (D-10): stateless FastAPI app under /api/v1.

Run:  cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, auth, data, health, integrations, runs, secrets, templates
from app.api.deps import account_dep
from app.core.errors import install_error_handlers
from app.core.logging import request_id_var, setup_logging
from app.core.settings import get_settings
from app.storage import get_engine

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the database when the server starts, so an old or mismatched one stops it with a clear message (D-18)
    instead of failing on the first request."""
    get_engine()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(lifespan=lifespan, title="Integration Platform API", version="1.0.0", docs_url=f"{settings.api_prefix}/docs", openapi_url=f"{settings.api_prefix}/openapi.json")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "X-Run-Id"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = rid
        return response

    install_error_handlers(app)
    # D-18: only /health and the sign-in routes are open. Everything else needs a valid session token.
    for module in (health, auth):
        app.include_router(module.router, prefix=settings.api_prefix)
    for module in (integrations, runs, data, secrets, templates, ai):
        app.include_router(module.router, prefix=settings.api_prefix, dependencies=[Depends(account_dep)])
    return app


app = create_app()
