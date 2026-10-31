"""Human review of AI-extracted decisions and action items. Every transition is enforced here, server-side."""
from __future__ import annotations

from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import audit
from ..clock import now as clock_now
from ..clock import utcnow
from ..models import ActionItem, ActionStatus, Decision, DecisionStatus, Reminder, User
from . import ServiceError
from .conflicts import unresolved_for_action, unresolved_for_decision
from .people import resolve_person


# ------------------------------------------------------------------ decisions

def approve_decision(db: Session, d: Decision, user: User, comment: str | None = None) -> dict:
    if d.status == DecisionStatus.CONFIRMED:
        return {"id": d.id, "status": d.status, "changed": False}  # repeated approval is a safe no-op
    if d.status == DecisionStatus.UNDER_REVIEW or unresolved_for_decision(db, d.id):
        raise ServiceError(409, "This decision conflicts with an earlier one. Resolve the conflict before confirming it.")
    if d.status != DecisionStatus.PROPOSED:
        raise ServiceError(409, f"A {d.status} decision cannot be confirmed.")
    # Conditional update: only one concurrent request can move proposed -> confirmed.
    res = db.execute(
        update(Decision).where(Decision.id == d.id, Decision.status == DecisionStatus.PROPOSED)
        .values(status=DecisionStatus.CONFIRMED, reviewed_by=user.id, reviewed_at=utcnow())
    )
    if res.rowcount == 0:
        db.rollback()
        db.refresh(d)
        return {"id": d.id, "status": d.status, "changed": False}
    audit.log(db, item_type="decision", item_id=d.id, action="approve", actor_id=user.id, project_id=d.project_id,
              previous_state=DecisionStatus.PROPOSED, new_state=DecisionStatus.CONFIRMED, comment=comment)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "status": d.status, "changed": True}


def reject_decision(db: Session, d: Decision, user: User, comment: str | None = None) -> dict:
    if d.status == DecisionStatus.REJECTED:
        return {"id": d.id, "status": d.status, "changed": False}
    if d.status not in {DecisionStatus.PROPOSED, DecisionStatus.UNDER_REVIEW}:
        raise ServiceError(409, f"A {d.status} decision cannot be rejected. Record a new decision in a meeting instead.")
    prev = d.status
    d.status, d.reviewed_by, d.reviewed_at = DecisionStatus.REJECTED, user.id, utcnow()
    for c in unresolved_for_decision(db, d.id):
        c.status, c.resolved_by, c.resolved_at = "kept_previous", user.id, utcnow()
        c.resolution_comment = f"Closed: new decision #{d.id} was rejected."
        audit.log(db, item_type="conflict", item_id=c.id, action="keep_previous", actor_id=user.id, project_id=d.project_id,
                  previous_state="open", new_state=c.status, comment=c.resolution_comment)
    audit.log(db, item_type="decision", item_id=d.id, action="reject", actor_id=user.id, project_id=d.project_id,
              previous_state=prev, new_state=d.status, comment=comment)
    db.commit()
    return {"id": d.id, "status": d.status, "changed": True}


def edit_decision(db: Session, d: Decision, user: User, changes: dict) -> Decision:
    if d.status not in {DecisionStatus.PROPOSED, DecisionStatus.UNDER_REVIEW}:
        raise ServiceError(409, "Only decisions awaiting review can be edited.")
    before = {k: getattr(d, k) for k in changes}
    for k, v in changes.items():
        setattr(d, k, v)
    audit.log(db, item_type="decision", item_id=d.id, action="edit", actor_id=user.id, project_id=d.project_id,
              previous_state=d.status, new_state=d.status, details={"before": _jsonable(before), "after": _jsonable(changes)})
    db.commit()
    return d


# ------------------------------------------------------------------ actions

def approve_action(db: Session, a: ActionItem, user: User, comment: str | None = None) -> dict:
    if a.status == ActionStatus.APPROVED:
        return {"id": a.id, "status": a.status, "changed": False}
    if a.status != ActionStatus.PROPOSED:
        raise ServiceError(409, f"A {a.status} action item cannot be approved.")
    if unresolved_for_action(db, a.id):
        raise ServiceError(409, "This task conflicts with an earlier task. Resolve the conflict first.")
    res = db.execute(
        update(ActionItem).where(ActionItem.id == a.id, ActionItem.status == ActionStatus.PROPOSED)
        .values(status=ActionStatus.APPROVED, reviewed_by=user.id, reviewed_at=utcnow())
    )
    if res.rowcount == 0:
        db.rollback()
        db.refresh(a)
        return {"id": a.id, "status": a.status, "changed": False}
    audit.log(db, item_type="action", item_id=a.id, action="approve", actor_id=user.id, project_id=a.project_id,
              previous_state=ActionStatus.PROPOSED, new_state=ActionStatus.APPROVED, comment=comment)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "status": a.status, "changed": True}


def reject_action(db: Session, a: ActionItem, user: User, comment: str | None = None) -> dict:
    if a.status == ActionStatus.REJECTED:
        return {"id": a.id, "status": a.status, "changed": False}
    if a.publication and a.publication.state in {"published", "publishing"}:
        raise ServiceError(409, "This task has already been sent to the tracker and cannot be rejected here.")
    if a.status not in {ActionStatus.PROPOSED, ActionStatus.APPROVED}:
        raise ServiceError(409, f"A {a.status} action item cannot be rejected.")
    prev = a.status
    a.status, a.reviewed_by, a.reviewed_at = ActionStatus.REJECTED, user.id, utcnow()
    audit.log(db, item_type="action", item_id=a.id, action="reject", actor_id=user.id, project_id=a.project_id,
              previous_state=prev, new_state=a.status, comment=comment)
    db.commit()
    return {"id": a.id, "status": a.status, "changed": True}


def edit_action(db: Session, a: ActionItem, user: User, changes: dict) -> ActionItem:
    if a.publication and a.publication.state in {"published", "publishing"}:
        raise ServiceError(409, "This task is already in the tracker; edit it there.")
    if a.status not in {ActionStatus.PROPOSED, ActionStatus.APPROVED}:
        raise ServiceError(409, f"A {a.status} action item cannot be edited.")
    before = {k: getattr(a, k) for k in changes}
    if "owner_name" in changes:
        owner = resolve_person(db, a.project_id, changes["owner_name"]) if changes["owner_name"] else None
        changes["owner_name"] = owner.name if owner else None
        a.owner_user_id = owner.id if owner else None
        a.owner_origin = "explicit" if owner else "unassigned"  # set by a human reviewer
    if "deadline" in changes:
        a.deadline_origin = "explicit" if changes["deadline"] else "unspecified"
        a.deadline_raw = "set by reviewer" if changes["deadline"] else None
    for k, v in changes.items():
        setattr(a, k, v)
    prev = a.status
    if a.status == ActionStatus.APPROVED:
        a.status = ActionStatus.PROPOSED  # an edited task must be approved again
    audit.log(db, item_type="action", item_id=a.id, action="edit", actor_id=user.id, project_id=a.project_id,
              previous_state=prev, new_state=a.status, details={"before": _jsonable(before), "after": _jsonable(changes)})
    db.commit()
    return a


def complete_action(db: Session, a: ActionItem, user: User, comment: str | None = None) -> dict:
    if a.status == ActionStatus.DONE:
        return {"id": a.id, "status": a.status, "changed": False}
    if a.status != ActionStatus.APPROVED:
        raise ServiceError(409, "Only approved tasks can be marked complete.")
    if user.role not in {"admin", "manager"} and a.owner_user_id != user.id:
        raise ServiceError(403, "Only the task owner or a manager can complete this task.")
    a.status, a.completed_at = ActionStatus.DONE, clock_now(db)  # app clock, so digests agree with the (demo) date
    # Completed tasks receive no further reminders.
    db.query(Reminder).filter(Reminder.action_id == a.id, Reminder.status == "active").update({"status": "dismissed"})
    audit.log(db, item_type="action", item_id=a.id, action="complete", actor_id=user.id, project_id=a.project_id,
              previous_state=ActionStatus.APPROVED, new_state=ActionStatus.DONE, comment=comment)
    db.commit()
    return {"id": a.id, "status": a.status, "changed": True}


def _jsonable(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in d.items()}
