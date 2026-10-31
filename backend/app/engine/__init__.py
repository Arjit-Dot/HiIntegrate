"""The engine (D-8): calls services. No database, no AI, no routes.

Handoffs: test_action (first page, nothing saved). run_action and remap_records come in Phase 2 and 3.
"""

from app.engine.core import extract_records, fetch_page, test_action
from app.engine.errors import RunError
from app.engine.mapping import map_record, map_records
from app.engine.request import build_request

__all__ = ["RunError", "build_request", "extract_records", "fetch_page", "map_record", "map_records", "test_action"]
