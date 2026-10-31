"""The worker process (D-10, D-12): runs scheduled pulls. The API never runs this loop.

Run:  cd backend && .venv/bin/python -m app.worker
"""

import logging
import signal
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.scheduler import timer
from app.storage import get_engine

log = logging.getLogger("worker")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    engine = get_engine()
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(timer.sync, "interval", seconds=timer.SYNC_SECONDS, id=timer.SYNC_JOB_ID, args=[scheduler, engine],
                      max_instances=1, coalesce=True)
    scheduler.start()
    timer.sync(scheduler, engine)  # do not wait 15 s for the first look
    log.info("worker started; re-reading the database every %s s", timer.SYNC_SECONDS)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    stop.wait()
    scheduler.shutdown(wait=False)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
