from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import audit, serializers
from ..ai.factory import describe as ai_describe
from ..clock import CLOCK_KEY, now as clock_now, override, tz, utcnow
from ..db import get_db
from ..models import (
    ActionItem, ActionStatus, AppSetting, ApprovalLog, Conflict, ConflictStatus, Decision, DecisionStatus, Integration, Meeting,
    Notification, Reminder, Role, User,
)
from ..security import can_access_project, current_user, ensure_project_access, require_admin, require_reviewer
from ..services import digest as digest_svc
from ..services import reminders as reminder_svc
from ..trackers.factory import get_tracker

router = APIRouter(prefix="/api", tags=["operations"])


# ------------------------------------------------------------------ system

def tracker_status(db: Session) -> dict:
    t = get_tracker()
    row = db.query(Integration).filter(Integration.provider == t.name).first()
    return {
        "provider": t.name, "label": t.label, "is_external": t.is_external, "configured": t.configured(),
        "status": row.status if row else ("demo" if not t.is_external else "not_checked"),
        "detail": row.detail if row else None, "workspace": row.workspace if row else None,
        "last_checked_at": serializers.iso(row.last_checked_at) if row else None,
    }


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    o = override(db)
    return {
        "ai": ai_describe(),
        "tracker": tracker_status(db),
        "clock": {"now": clock_now(db).isoformat(), "override": o.isoformat() if o else None, "timezone": str(tz())},
    }


class ClockIn(BaseModel):
    day: date | None = Field(default=None, alias="date")  # null clears the demo clock


@router.post("/system/clock")
def set_clock(body: ClockIn, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    row = db.get(AppSetting, CLOCK_KEY) or AppSetting(key=CLOCK_KEY)
    row.value = datetime.combine(body.day, time(9, 0), tzinfo=tz()).isoformat() if body.day else None
    db.merge(row)
    audit.log(db, item_type="system", item_id=None, action="demo_clock", actor_id=user.id, new_state=row.value or "real time")
    db.commit()
    scan = reminder_svc.scan(db)
    return {"override": row.value, "reminders": scan}


@router.post("/system/reset-demo")
def reset_demo(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from ..seed import reset_and_seed

    db.close()
    return reset_and_seed()


# ------------------------------------------------------------------ dashboard

@router.get("/dashboard")
def dashboard(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    today = clock_now(db).date()
    meetings = db.query(Meeting).filter(Meeting.project_id == project_id).order_by(Meeting.meeting_date.desc(), Meeting.id.desc()).all()
    decisions = db.query(Decision).filter(Decision.project_id == project_id).all()
    actions = db.query(ActionItem).filter(ActionItem.project_id == project_id).all()
    conflicts = db.query(Conflict).filter(Conflict.project_id == project_id).all()
    open_conflicts = [c for c in conflicts if c.status in ConflictStatus.UNRESOLVED]
    approved = [a for a in actions if a.status == ActionStatus.APPROVED]
    overdue = [a for a in approved if a.deadline and a.deadline < today]
    upcoming = [a for a in approved if a.deadline and today <= a.deadline <= today + timedelta(days=7)]
    changed = [d for d in decisions if d.status == DecisionStatus.SUPERSEDED]
    recent_changes = []
    for d in sorted(changed, key=lambda x: x.id, reverse=True)[:5]:
        newer = db.get(Decision, d.superseded_by_id) if d.superseded_by_id else None
        recent_changes.append({"topic": d.topic, "from": serializers.decision(d), "to": serializers.decision(newer) if newer else None})
    return {
        "as_of": today.isoformat(),
        "counts": {
            "meetings": len(meetings), "processed": sum(1 for m in meetings if m.status == "processed"),
            "decisions": len(decisions), "confirmed": sum(1 for d in decisions if d.status == DecisionStatus.CONFIRMED),
            "pending_approvals": sum(1 for d in decisions if d.status in {DecisionStatus.PROPOSED, DecisionStatus.UNDER_REVIEW})
            + sum(1 for a in actions if a.status == ActionStatus.PROPOSED),
            "open_conflicts": len(open_conflicts), "open_actions": len(approved), "overdue": len(overdue), "upcoming": len(upcoming),
            "published": sum(1 for a in actions if a.publication and a.publication.state == "published"),
        },
        "current_decisions": [serializers.decision(d) for d in decisions if d.status == DecisionStatus.CONFIRMED][-8:][::-1],
        "recent_changes": recent_changes,
        "open_conflicts": [serializers.conflict(db, c) for c in open_conflicts[:5]],
        "overdue": [serializers.action(a) for a in overdue],
        "upcoming": [serializers.action(a) for a in sorted(upcoming, key=lambda a: a.deadline)],
        "my_tasks": [serializers.action(a) for a in approved if a.owner_user_id == user.id],
        "recent_meetings": [serializers.meeting_brief(m) for m in meetings[:4]],
    }


# ------------------------------------------------------------------ reminders & notifications

@router.get("/reminders")
def list_reminders(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    rows = db.query(Reminder).join(ActionItem, ActionItem.id == Reminder.action_id).filter(ActionItem.project_id == project_id).order_by(Reminder.created_at.desc()).all()
    today = clock_now(db).date()
    approved = db.query(ActionItem).filter(ActionItem.project_id == project_id, ActionItem.status == ActionStatus.APPROVED, ActionItem.deadline.isnot(None)).all()
    return {
        "as_of": today.isoformat(),
        "reminders": [{**serializers.reminder(r), "action": serializers.action(db.get(ActionItem, r.action_id))} for r in rows],
        "overdue": [serializers.action(a) for a in approved if a.deadline < today],
        "due_soon": [serializers.action(a) for a in approved if today <= a.deadline <= today + timedelta(days=1)],
    }


@router.post("/reminders/scan")
def scan_reminders(db: Session = Depends(get_db), _: User = Depends(require_reviewer)):
    return reminder_svc.scan(db)


def _visible_notifications(db: Session, user: User):
    q = db.query(Notification)
    if user.role in Role.REVIEWERS:
        return q.filter(or_(Notification.user_id == user.id, Notification.user_id.is_(None), Notification.reminder_id.isnot(None)))
    return q.filter(Notification.user_id == user.id)


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = _visible_notifications(db, user).order_by(Notification.created_at.desc()).limit(100).all()
    return {"unread": sum(1 for n in rows if n.read_at is None), "items": [serializers.notification(n) for n in rows]}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = _visible_notifications(db, user).filter(Notification.id == notification_id).first()
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return serializers.notification(n)


@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for n in _visible_notifications(db, user).filter(Notification.read_at.is_(None)).all():
        n.read_at = utcnow()
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ digest

@router.get("/digest/{user_id}")
def get_digest(user_id: int, project_id: int, week_start: date | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    if user.role not in Role.REVIEWERS and user.id != user_id:
        raise HTTPException(403, "You can only view your own digest.")
    person = db.get(User, user_id)
    if person is None or not can_access_project(db, person, project_id) and person.role != Role.ADMIN:
        raise HTTPException(404, "Person not found in this project")
    return digest_svc.build(db, person, project_id, week_start)


# ------------------------------------------------------------------ integrations

@router.get("/integrations")
def integrations(db: Session = Depends(get_db), _: User = Depends(current_user)):
    t = get_tracker()
    return {
        "active": tracker_status(db),
        "available": [
            {"provider": "github", "label": "GitHub Issues", "external": True, "env": ["TRACKER_PROVIDER=github", "GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_ASSIGNEES (optional)"]},
            {"provider": "demo", "label": "Demo tracker (simulated)", "external": False, "env": ["TRACKER_PROVIDER=demo"]},
        ],
        "selected": t.name,
    }


@router.post("/integrations/check")
def check_integration(db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    t = get_tracker()
    result = t.check()
    row = db.query(Integration).filter(Integration.provider == t.name).first() or Integration(provider=t.name)
    row.status, row.detail, row.last_checked_at = result.get("status", "error"), result.get("detail"), utcnow()
    row.workspace = getattr(t, "repo", None)
    db.merge(row) if row.id else db.add(row)
    audit.log(db, item_type="system", item_id=None, action="integration_check", actor_id=user.id, new_state=row.status, comment=row.detail)
    db.commit()
    return {**result, "provider": t.name, "is_external": t.is_external}


# ------------------------------------------------------------------ audit

@router.get("/audit")
def audit_log(project_id: int | None = None, item_type: str | None = None, item_id: int | None = None, limit: int = 200,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(ApprovalLog)
    if project_id is not None:
        ensure_project_access(db, user, project_id)
        q = q.filter(or_(ApprovalLog.project_id == project_id, ApprovalLog.project_id.is_(None)))
    elif user.role != Role.ADMIN:
        raise HTTPException(400, "project_id is required")
    if item_type:
        q = q.filter(ApprovalLog.item_type == item_type)
    if item_id is not None:
        q = q.filter(ApprovalLog.item_id == item_id)
    rows = q.order_by(ApprovalLog.id.desc()).limit(min(limit, 500)).all()
    actors = {u.id: u for u in db.query(User).filter(User.id.in_({r.actor_id for r in rows if r.actor_id} or {-1}))}
    return [serializers.log(r, actors.get(r.actor_id)) for r in rows]
