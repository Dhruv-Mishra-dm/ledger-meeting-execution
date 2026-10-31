"""Single source of "now" for every time-based rule.

A demo clock override (stored in the settings table) lets the demo show reminders for November deadlines
without waiting. The UI always shows a banner while the override is active, so it is never hidden.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .config import settings

CLOCK_KEY = "demo_clock"


def tz() -> ZoneInfo:
    return ZoneInfo(settings.default_timezone)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def override(db: Session) -> datetime | None:
    from .models import AppSetting

    row = db.get(AppSetting, CLOCK_KEY)
    if not row or not row.value:
        return None
    return datetime.fromisoformat(row.value)


def now(db: Session) -> datetime:
    """Timezone-aware current time in the project timezone, honouring the demo override."""
    o = override(db)
    return o.astimezone(tz()) if o else utcnow().astimezone(tz())


def today(db: Session) -> date:
    return now(db).date()
