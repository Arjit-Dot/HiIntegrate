"""The engine (D-8): calls services. No database, no AI, no routes.

Handoffs: run_action (every page, saved through on_page), test_action (first page, nothing saved).
remap_records comes in Phase 3.
"""

from app.engine.core import extract_records, fetch_page, test_action
from app.engine.errors import RunError
from app.engine.mapping import map_record, map_records
from app.engine.request import build_request
from app.engine.run import RunResult, run_action

__all__ = ["RunError", "RunResult", "build_request", "extract_records", "fetch_page", "map_record", "map_records", "run_action", "test_action"]
