from typing import ClassVar


class RunError(Exception):
    """A run failed. `code` is one of the run error codes in schema/result.schema.json."""

    CODES: ClassVar[set[str]] = {
        "auth_failed", "connection_error", "timeout", "server_error", "rate_limited",
        "bad_response", "api_error", "client_error", "secret_host_mismatch", "schema_drift",
    }

    def __init__(self, code: str, message: str, *, status: int | None = None, retries: int = 0):
        assert code in self.CODES, code
        super().__init__(message)
        self.code, self.message, self.status, self.retries = code, message, status, retries

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
