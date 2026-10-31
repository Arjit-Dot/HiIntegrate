"""Schema drift check (stretch): a mapped path that used to appear and is now missing from every record of a run.

A service that renames or drops a field does not fail the run: the records still map, with the field empty
(or its default). This finds that case so the connection can be marked degraded and the path named.
"Used to appear" comes from a baseline the runner keeps per action (repo.get_baseline), so a field the
service never sent does not raise an alarm.

Only plain paths are checked (`profile.email`, `items[0].id`): a key that is absent from every record counts as
gone. A key that is present with a null value does not, since that is real data. Expressions with filters,
functions or projections are skipped, because "missing" is not well defined for them.
"""

import re
from typing import Any

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*$")
_STEP = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]")
_MISSING = object()
CODE = "schema_drift"


def _walk(raw: Any, path: str) -> Any:
    cur = raw
    for step in _STEP.findall(path):
        if step.startswith("["):
            i = int(step[1:-1])
            if not isinstance(cur, list) or i >= len(cur):
                return _MISSING
            cur = cur[i]
        else:
            if not isinstance(cur, dict) or step not in cur:
                return _MISSING
            cur = cur[step]
    return cur


def mapped_paths(action: dict) -> dict[str, str]:
    """field -> plain path, for the mapped fields that can be checked."""
    out = {}
    for field, entry in (action.get("map") or {}).items():
        path = entry if isinstance(entry, str) else entry.get("path")
        if path and _PLAIN.match(path):
            out[field] = path
    return out


class DriftTracker:
    """Feed it every page's raw records. `seen` is every mapped path that appeared in at least one record.

    Drift is judged against a baseline: the paths seen in earlier successful runs. A path that has never
    appeared (a field the service just does not send) is not drift, only one that was there and is now gone."""

    def __init__(self, action: dict, baseline: set[str] | None = None):
        self.fields = mapped_paths(action)
        self.baseline = baseline or set()
        self.seen: set[str] = set()
        self.total = 0

    def add(self, raws: list) -> None:
        self.total += len(raws)
        for path in set(self.fields.values()) - self.seen:
            if any(_walk(r, path) is not _MISSING for r in raws):
                self.seen.add(path)

    def report(self) -> dict | None:
        if not self.total:
            return None  # an empty response says nothing about the fields
        gone = [f"{path} (field {field})" for field, path in self.fields.items() if path in self.baseline and path not in self.seen]
        if not gone:
            return None
        return {"code": CODE, "message": f"The service no longer sends: {', '.join(gone)}. It did before, and none of {self.total} records "
                                         "have it now. The run succeeded, but those fields are empty."}
