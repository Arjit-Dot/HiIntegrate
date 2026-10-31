"""One error shape for every response (D-6): {"error": {"code", "message", "details"}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

# Codes from schema/openapi.yaml (components.schemas.Error)
CODES = {"validation_error", "not_found", "conflict", "unsupported", "run_failed", "internal_error"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        assert code in CODES, code
        self.status, self.code, self.message, self.details = status, code, message, details
        super().__init__(message)


def error_body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def _code_for_status(status: int) -> str:
    return {404: "not_found", 409: "conflict", 501: "unsupported"}.get(status, "validation_error" if status < 500 else "internal_error")


def install_error_handlers(app: FastAPI) -> None:
    from app.scheduler.runner import InputsInvalid, UnknownAction
    from app.storage.repo import Conflict, NotFound

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(error_body("not_found", str(exc)), status_code=404)

    @app.exception_handler(UnknownAction)
    async def unknown_action(_: Request, exc: UnknownAction):
        return JSONResponse(error_body("not_found", str(exc)), status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse(error_body("conflict", str(exc), exc.details), status_code=409)

    @app.exception_handler(InputsInvalid)
    async def inputs_invalid(_: Request, exc: InputsInvalid):
        return JSONResponse(error_body("validation_error", "The inputs are not valid", {"errors": exc.issues}), status_code=400)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def request_invalid(_: Request, exc: RequestValidationError):
        errors = [
            {"path": ".".join(str(p) for p in e.get("loc", ()) if p != "body") or "(body)", "message": e.get("msg", "invalid"), "severity": "error"}
            for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", "The request is not valid", {"errors": errors}), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        if exc.status_code == 404 and message == "Not Found":
            message = "No such route"
        return JSONResponse(error_body(_code_for_status(exc.status_code), message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse(error_body("internal_error", "Something went wrong on the server"), status_code=500)
