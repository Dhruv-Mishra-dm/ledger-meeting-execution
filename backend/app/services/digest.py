"""Per-person weekly digest built only from stored records. It never invents progress."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..clock import today as clock_today
from ..clock import tz
from ..models import ActionItem, ActionStatus, Conflict, ConflictStatus, Decision, DecisionStatus, Digest, Meeting, User


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _action(a: ActionItem) -> dict:
    pub = a.publication
    return {
        "id": a.id, "title": a.title, "status": a.status, "deadline": a.deadline.isoformat() if a.deadline else None,
        "meeting": a.meeting.title, "external_url": pub.external_url if pub and pub.state == "published" and pub.provider != "demo" else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
    }


def build(db: Session, person: User, project_id: int, week_start: date | None = None) -> dict:
    today = clock_today(db)
    ws = week_start or week_start_of(today)
    we = ws + timedelta(days=6)
    start_dt = datetime.combine(ws, time.min, tzinfo=tz())
    end_dt = datetime.combine(we + timedelta(days=1), time.min, tzinfo=tz())

    mine = db.query(ActionItem).filter(ActionItem.project_id == project_id, ActionItem.owner_user_id == person.id).all()

    def done_in_week(a: ActionItem) -> bool:
        if a.status != ActionStatus.DONE or not a.completed_at:
            return False
        c = a.completed_at if a.completed_at.tzinfo else a.completed_at.replace(tzinfo=timezone.utc)  # SQLite returns naive UTC
        return start_dt <= c < end_dt

    completed = [a for a in mine if done_in_week(a)]
    open_ = [a for a in mine if a.status == ActionStatus.APPROVED]
    awaiting = [a for a in mine if a.status == ActionStatus.PROPOSED]
    overdue = [a for a in open_ if a.deadline and a.deadline < today]
    upcoming = [a for a in open_ if a.deadline and today <= a.deadline <= today + timedelta(days=7)]
    pending = [a for a in open_ if a not in overdue]

    my_action_decisions = {a.decision_id for a in mine if a.decision_id}
    decisions = (
        db.query(Decision).join(Meeting, Meeting.id == Decision.meeting_id)
        .filter(Decision.project_id == project_id, Meeting.meeting_date >= ws - timedelta(days=7), Meeting.meeting_date <= we)
        .filter(or_(Decision.speaker == person.name, Decision.id.in_(my_action_decisions or {-1})))
        .order_by(Meeting.meeting_date).all()
    )
    my_action_ids = {a.id for a in mine}
    conflicts = [
        c for c in db.query(Conflict).filter(Conflict.project_id == project_id, Conflict.status.in_(ConflictStatus.UNRESOLVED)).all()
        if c.new_action_id in my_action_ids or c.old_action_id in my_action_ids
        or (c.new_decision_id and db.get(Decision, c.new_decision_id).speaker == person.name)
        or (c.old_decision_id in my_action_decisions) or (c.new_decision_id in my_action_decisions)
    ]

    summary = (
        f"{person.name} completed {len(completed)} task{'s' if len(completed) != 1 else ''} this week, "
        f"has {len(pending)} open task{'s' if len(pending) != 1 else ''}"
        + (f" and {len(overdue)} overdue" if overdue else "")
        + (f", with {len(upcoming)} due in the next 7 days" if upcoming else "")
        + "."
    )
    if awaiting:
        summary += f" {len(awaiting)} extracted task{'s are' if len(awaiting) != 1 else ' is'} awaiting approval."
    if conflicts:
        summary += f" {len(conflicts)} unresolved conflict{'s' if len(conflicts) != 1 else ''} involve{'s' if len(conflicts) == 1 else ''} their work."

    payload = {
        "person": {"id": person.id, "name": person.name}, "project_id": project_id,
        "week_start": ws.isoformat(), "week_end": we.isoformat(), "as_of": today.isoformat(), "summary": summary,
        "completed": [_action(a) for a in completed], "pending": [_action(a) for a in pending],
        "upcoming": [_action(a) for a in upcoming], "overdue": [_action(a) for a in overdue],
        "awaiting_approval": [_action(a) for a in awaiting],
        "decisions": [{"id": d.id, "statement": d.statement, "status": d.status, "meeting": d.meeting.title,
                       "date": d.meeting.meeting_date.isoformat()} for d in decisions if d.status != DecisionStatus.REJECTED],
        "conflicts": [{"id": c.id, "category": c.category, "explanation": c.explanation, "status": c.status} for c in conflicts],
        "source": "Generated from stored task, decision and conflict records only.",
    }
    row = db.query(Digest).filter(Digest.user_id == person.id, Digest.project_id == project_id, Digest.week_start == ws).first()
    if row is None:
        db.add(Digest(user_id=person.id, project_id=project_id, week_start=ws, payload=payload))
    else:
        row.payload = payload
    db.commit()
    return payload
