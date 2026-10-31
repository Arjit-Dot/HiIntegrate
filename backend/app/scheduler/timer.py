"""The timed scheduler (D-10, D-12): APScheduler inside the worker process.

The worker re-reads the database every SYNC_SECONDS, so a config that is added, edited, enabled or
disabled in the dashboard takes effect without restarting anything. Each enabled `pull` action gets one
interval job. A run that is still going is skipped, not queued (one running run per action, D-10).
"""

import logging
import re
from datetime import UTC, datetime

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import Engine

from app.scheduler import runner
from app.storage import repo, session_scope

log = logging.getLogger("scheduler")
SYNC_SECONDS = 15
SYNC_JOB_ID = "__sync__"
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_interval(text: str) -> int:
    """"every 5m" -> 300 seconds. The config validator already guarantees the shape."""
    m = re.fullmatch(r"every (\d+)([smhd])", text.strip())
    if not m:
        raise ValueError(f"not a schedule: {text!r}")
    return int(m.group(1)) * _UNITS[m.group(2)]


def run_job(engine: Engine, account: str, integration: str, action: str, **runner_kwargs) -> None:
    """One scheduled run. Never raises, so one bad run cannot stop the timer."""
    try:
        runner.run(engine, account, integration, action, "schedule", **runner_kwargs)
    except repo.Conflict:
        log.info("skipped %s.%s: the previous run is still going", integration, action)
    except (repo.NotFound, runner.UnknownAction):
        log.info("skipped %s.%s: it no longer exists", integration, action)
    except Exception as exc:  # noqa: BLE001
        log.error("scheduled run of %s.%s crashed: %s", integration, action, type(exc).__name__)


def _label(account: str, integration: str, action: str, seconds: int, revision: int) -> str:
    """Kept as the job's name: when it differs from the database, the job is out of date."""
    return f"{account}/{integration}.{action} every {seconds}s (revision {revision})"


def _wanted(engine: Engine) -> dict[str, tuple[str, str, str, int, str]]:
    """job id -> (account, integration, action, seconds, label) for every enabled pull action with a schedule, of every account."""
    wanted = {}
    with session_scope(engine) as s:
        for row in repo.list_integrations(s):
            if not row.enabled:
                continue
            for name, spec in (row.config.get("actions") or {}).items():
                if spec.get("mode") == "pull" and spec.get("schedule"):
                    seconds = parse_interval(spec["schedule"])
                    wanted[f"{row.account}:{row.name}:{name}"] = (row.account, row.name, name, seconds, _label(row.account, row.name, name, seconds, row.revision))
    return wanted


def sync(scheduler: BaseScheduler, engine: Engine, **runner_kwargs) -> dict[str, list[str]]:
    """Make the scheduler's jobs match the database. Returns what changed, for logging and tests."""
    wanted = _wanted(engine)
    changes: dict[str, list[str]] = {"added": [], "updated": [], "removed": []}
    for job in scheduler.get_jobs():
        if job.id == SYNC_JOB_ID:
            continue
        if job.id not in wanted:
            scheduler.remove_job(job.id)
            changes["removed"].append(job.id)
        elif job.name != wanted[job.id][4]:
            scheduler.remove_job(job.id)  # added again below with the new interval
            changes["updated"].append(job.id)
    existing = {j.id for j in scheduler.get_jobs()}
    for job_id, (account, integration, action, seconds, label) in wanted.items():
        if job_id in existing:
            continue
        with session_scope(engine) as s:
            first_time = not repo.has_run(s, account, integration, action)
        extra = {"next_run_time": datetime.now(UTC)} if first_time else {}  # next_run_time=None would pause the job
        scheduler.add_job(
            run_job, IntervalTrigger(seconds=seconds), id=job_id, args=[engine, account, integration, action], kwargs=runner_kwargs,
            name=label, max_instances=1, coalesce=True, misfire_grace_time=seconds, **extra,
        )
        if job_id not in changes["updated"]:
            changes["added"].append(job_id)
    if any(changes.values()):
        log.info("schedule synced: %s", {k: v for k, v in changes.items() if v})
    return changes
