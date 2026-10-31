"""S-10: keep the database from growing forever. The worker calls `purge_old` once a day.

Old run history, quarantined records and audit entries are deleted. The stored users, devices and alerts are the product's
data and are never purged here. A run still running, and the newest finished run of each action, are always kept.
Settings (days; 0 keeps everything): RETENTION_RUNS_DAYS (90), RETENTION_QUARANTINE_DAYS (90), RETENTION_AUDIT_DAYS (365).
"""

import logging
import os
from datetime import datetime

from sqlalchemy import Engine

from app.storage import repo, session_scope

log = logging.getLogger("worker.retention")
DEFAULTS = {"RETENTION_RUNS_DAYS": 90, "RETENTION_QUARANTINE_DAYS": 90, "RETENTION_AUDIT_DAYS": 365}
INTERVAL_SECONDS = 24 * 3600


def days(name: str) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return max(0, int(raw)) if raw else DEFAULTS[name]
    except ValueError:
        return DEFAULTS[name]


def purge_old(engine: Engine, now: datetime | None = None) -> dict[str, int]:
    done = {"runs": 0, "quarantine": 0, "audit": 0}
    with session_scope(engine) as s:
        if d := days("RETENTION_RUNS_DAYS"):
            done["runs"] = repo.purge_runs(s, repo.cutoff_iso(d, now))
        if d := days("RETENTION_QUARANTINE_DAYS"):
            done["quarantine"] = repo.purge_quarantine(s, repo.cutoff_iso(d, now))
        if d := days("RETENTION_AUDIT_DAYS"):
            done["audit"] = repo.purge_audit(s, repo.cutoff_iso(d, now))
    if any(done.values()):
        log.info("retention: deleted %d run(s), %d quarantined record(s), %d audit entr(ies)", done["runs"], done["quarantine"], done["audit"])
    return done
