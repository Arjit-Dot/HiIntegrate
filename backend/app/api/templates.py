"""The template gallery (D-15): templates are starting points only. They are read from templates/ and never run."""

from fastapi import APIRouter

from app.config_loader import parse_config
from app.core.errors import ApiError
from app.core.settings import REPO_ROOT

router = APIRouter(tags=["Templates"])
TEMPLATES = REPO_ROOT / "templates"


def _summary(path) -> dict:
    cfg = parse_config(path.read_text())
    out = {"id": path.stem, "display_name": cfg.get("display_name", cfg["name"]), "category": cfg.get("category", "other"),
           "description": cfg.get("description", "")}
    if cfg.get("requires"):
        out["requires"] = cfg["requires"]
    return out


@router.get("/templates")
def list_templates() -> dict:
    return {"items": [_summary(p) for p in sorted(TEMPLATES.glob("*.yaml"))]}


@router.get("/templates/{template_id}")
def get_template(template_id: str) -> dict:
    path = TEMPLATES / f"{template_id}.yaml"
    if not template_id.replace("-", "").replace("_", "").isalnum() or not path.exists():
        raise ApiError(404, "not_found", f"No template named {template_id}")
    text = path.read_text()
    return {"id": template_id, "config": parse_config(text), "yaml": text}
