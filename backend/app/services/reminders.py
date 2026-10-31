"""Deadline reminders: 24 hours before, on the due date, and overdue.

Reminder rows are unique per (action, kind), so re-running the scan (every 5 minutes, at startup, or after a
restart) never creates duplicates. Only the reminder for the *current* phase is created: if the app was offline
until after the deadline, the owner gets an overdue reminder, not a stale "due tomorrow" one.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..clock import now as clock_now
from ..models import ActionItem, ActionStatus, Notification, Reminder

KIND_TEXT = {
    "due_24h": ("Due tomorrow", "is due tomorrow"),
    "due_today": ("Due today", "is due today"),
    "overdue": ("Overdue", "is overdue"),
}


def phase(deadline, today) -> str | None:
    if today == deadline - timedelta(days=1):
        return "due_24h"
    if today == deadline:
        return "due_today"
    if today > deadline:
        return "overdue"
    return None


def scan(db: Session, at: datetime | None = None) -> dict:
    today = (at or clock_now(db)).date()
    actions = (
        db.query(ActionItem)
        .filter(ActionItem.status == ActionStatus.APPROVED, ActionItem.deadline.isnot(None))
        .all()
    )
    created = 0
    for a in actions:
        kind = phase(a.deadline, today)
        if kind is None:
            continue
        if db.query(Reminder.id).filter(Reminder.action_id == a.id, Reminder.kind == kind).first():
            continue
        r = Reminder(action_id=a.id, user_id=a.owner_user_id, owner_name=a.owner_name, kind=kind, due_date=a.deadline)
        db.add(r)
        try:
            db.flush()
        except IntegrityError:  # created concurrently by another scan
            db.rollback()
            continue
        title, verb = KIND_TEXT[kind]
        db.add(Notification(
            user_id=a.owner_user_id, reminder_id=r.id, kind=f"reminder_{kind}", title=f"{title}: {a.title}",
            body=f"\"{a.title}\" ({a.owner_name or 'unassigned'}) {verb} ({a.deadline.isoformat()}).", link=f"/actions?focus={a.id}",
        ))
        created += 1
    # Earlier-phase reminders for overdue tasks stay as history; dismiss reminders of tasks no longer active.
    stale = (
        db.query(Reminder)
        .join(ActionItem, ActionItem.id == Reminder.action_id)
        .filter(Reminder.status == "active", ActionItem.status != ActionStatus.APPROVED)
        .all()
    )
    for r in stale:
        r.status = "dismissed"
    if created:
        audit.log(db, item_type="system", item_id=None, action="reminder_scan", actor_id=None, details={"created": created, "as_of": today.isoformat()})
    db.commit()
    return {"created": created, "as_of": today.isoformat(), "dismissed": len(stale)}
