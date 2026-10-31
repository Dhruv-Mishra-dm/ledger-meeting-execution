"""Background jobs: reminder scan every 5 minutes and weekly digests on Monday morning (project timezone)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .clock import tz
from .db import SessionLocal

log = logging.getLogger("scheduler")
_scheduler: BackgroundScheduler | None = None


def reminder_job() -> None:
    from .services.reminders import scan

    with SessionLocal() as db:
        result = scan(db)
        if result["created"]:
            log.info("reminder scan created %s reminder(s)", result["created"])


def digest_job() -> None:
    from .models import Project
    from .services.digest import build
    from .services.people import project_people

    with SessionLocal() as db:
        for project in db.query(Project).all():
            for person in project_people(db, project.id):
                build(db, person, project.id)


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=tz())
    _scheduler.add_job(reminder_job, "interval", minutes=5, id="reminders", max_instances=1, coalesce=True)
    _scheduler.add_job(digest_job, "cron", day_of_week="mon", hour=8, id="weekly_digest", max_instances=1, coalesce=True)
    _scheduler.start()
    reminder_job()  # catch up immediately after a restart (idempotent)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
