"""Read a config from a request body (JSON or YAML text) and summarise integrations."""

import json

from fastapi import Request
from sqlalchemy.orm import Session

from app.config_loader import load_config, validate_config
from app.core.errors import ApiError
from app.storage import repo


async def read_config(request: Request) -> tuple[dict | None, list[dict]]:
    """Returns (config or None, issues). YAML text gets line numbers; JSON gets paths only."""
    raw = (await request.body()).decode("utf-8", errors="replace")
    if "json" in request.headers.get("content-type", "").lower():
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ApiError(400, "validation_error", f"the body is not valid JSON: {exc}") from None
        return (data if isinstance(data, dict) else None), validate_config(data)
    return load_config(raw)


def require_valid(config: dict | None, issues: list[dict]) -> dict:
    if config is None or any(i["severity"] == "error" for i in issues):
        raise ApiError(400, "validation_error", "The config is not valid", {"errors": issues})
    return config


def integration_out(s: Session, row) -> dict:
    return {"config": row.config, "health": repo.health(s, row), "revision": row.revision,
            "created_at": row.created_at, "updated_at": row.updated_at}


def summary(s: Session, row) -> dict:
    cfg = row.config
    actions = cfg.get("actions", {})
    return {
        "name": row.name,
        "display_name": cfg.get("display_name", row.name),
        "category": cfg.get("category", "other"),
        "enabled": row.enabled,
        "auth_type": cfg["auth"]["type"],
        "schemas": sorted({a["target_schema"] for a in actions.values()}),
        "actions": [{"name": n, "mode": a["mode"]} for n, a in actions.items()],
        "health": repo.health(s, row),
    }
