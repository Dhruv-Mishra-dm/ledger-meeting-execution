"""Conflict detection (decisions and action items) and human resolution.

Nothing here resolves a conflict on its own: detection only creates OPEN conflicts and marks the new decision
UNDER_REVIEW. State changes to decisions happen exclusively in resolve(), which requires a human reviewer.
"""
from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import audit
from ..ai.base import MeetingAI
from ..ai.text import same_task
from ..clock import utcnow
from ..models import ActionItem, ActionStatus, Conflict, ConflictStatus, Decision, DecisionStatus, Meeting, Notification, User
from . import ServiceError
from .memory import candidates_for, to_view

MIN_CONFIDENCE = 0.5
RESOLUTIONS = {"accept_new", "keep_previous", "compatible", "needs_review"}


def _fmt(d) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}" if d else "unspecified"


def detect_decision_conflicts(db: Session, engine: MeetingAI, new: Decision, live: list[Decision]) -> list[Conflict]:
    cands = candidates_for(new.topic, new.statement, live)
    if not cands:
        return []
    by_id = {c.id: c for c in cands}
    created: list[Conflict] = []
    for j in engine.judge(to_view(new), [to_view(c) for c in cands]):
        old = by_id.get(j.candidate_id)
        if old is None or j.relation == "unrelated":
            continue
        if j.relation == "compatible":
            if old.topic == new.topic and new.related_decision_id is None:
                new.related_decision_id = old.id
                new.notes = _join(new.notes, f"Consistent with decision #{old.id} from '{old.meeting.title}'.")
            continue
        if j.confidence < MIN_CONFIDENCE:
            new.notes = _join(new.notes, f"Possibly related to decision #{old.id} ({j.relation}, low confidence {j.confidence:.2f}).")
            continue
        conflict = Conflict(
            project_id=new.project_id, meeting_id=new.meeting_id, category=j.relation,
            old_decision_id=old.id, new_decision_id=new.id, explanation=j.explanation, confidence=round(j.confidence, 2),
            recommended_action=j.recommended_action or "Review both decisions and record which one stands.",
            detected_by="ai" if engine.is_real_ai else "rules",
        )
        db.add(conflict)
        created.append(conflict)
    if created:
        new.status = DecisionStatus.UNDER_REVIEW
    return created


def _join(a: str | None, b: str) -> str:
    return f"{a} {b}".strip() if a else b


def detect_action_conflicts(db: Session, new: ActionItem, meeting: Meeting) -> list[Conflict]:
    earlier = (
        db.query(ActionItem)
        .join(Meeting, Meeting.id == ActionItem.meeting_id)
        .filter(
            ActionItem.project_id == new.project_id,
            ActionItem.meeting_id != meeting.id,
            ActionItem.status.in_(ActionStatus.LIVE),
            or_(Meeting.meeting_date < meeting.meeting_date, and_(Meeting.meeting_date == meeting.meeting_date, Meeting.id < meeting.id)),
        )
        .order_by(Meeting.meeting_date.desc(), ActionItem.id.desc())
        .all()
    )
    for old in earlier:
        if not same_task(old.title, new.title):
            continue
        if old.owner_name and new.owner_name and old.owner_name.lower() != new.owner_name.lower():
            category = "ownership"
            explanation = (
                f"'{old.meeting.title}' ({_fmt(old.meeting.meeting_date)}) assigned \"{old.title}\" to {old.owner_name}. "
                f"'{meeting.title}' ({_fmt(meeting.meeting_date)}) assigns the same work to {new.owner_name}."
            )
            recommended = f"Confirm whether {new.owner_name} replaces {old.owner_name} as owner, or whether both share it."
        elif old.deadline and new.deadline and old.deadline != new.deadline:
            category = "deadline_change"
            delta = (new.deadline - old.deadline).days
            explanation = (
                f"'{old.meeting.title}' ({_fmt(old.meeting.meeting_date)}) set \"{old.title}\" ({old.owner_name or 'unassigned'}) due {_fmt(old.deadline)}. "
                f"'{meeting.title}' ({_fmt(meeting.meeting_date)}) sets it to {_fmt(new.deadline)} ({abs(delta)} days {'later' if delta > 0 else 'earlier'})."
            )
            recommended = f"Accept the new deadline ({_fmt(new.deadline)}) to supersede the earlier task, or keep the original date."
        else:
            return []  # a restatement of the same task, not a conflict
        conflict = Conflict(
            project_id=new.project_id, meeting_id=meeting.id, category=category, old_action_id=old.id, new_action_id=new.id,
            explanation=explanation, confidence=0.85, recommended_action=recommended, detected_by="rules",
        )
        db.add(conflict)
        return [conflict]
    return []


def unresolved_for_decision(db: Session, decision_id: int, exclude: int | None = None) -> list[Conflict]:
    q = db.query(Conflict).filter(Conflict.new_decision_id == decision_id, Conflict.status.in_(ConflictStatus.UNRESOLVED))
    if exclude:
        q = q.filter(Conflict.id != exclude)
    return q.all()


def unresolved_for_action(db: Session, action_id: int) -> list[Conflict]:
    return db.query(Conflict).filter(Conflict.new_action_id == action_id, Conflict.status.in_(ConflictStatus.UNRESOLVED)).all()


def resolve(db: Session, conflict: Conflict, resolution: str, comment: str | None, user: User) -> dict:
    if resolution not in RESOLUTIONS:
        raise ServiceError(422, f"Unknown resolution '{resolution}'.")
    if conflict.status not in ConflictStatus.UNRESOLVED:
        raise ServiceError(409, f"This conflict was already resolved ({conflict.status.replace('_', ' ')}).")
    if resolution == "needs_review" and not (comment and comment.strip()):
        raise ServiceError(422, "Add a comment explaining what further review is needed.")
    previous = conflict.status
    now = utcnow()
    affected: list[ActionItem] = []
    notes: list[str] = []

    if resolution == "needs_review":
        conflict.status = ConflictStatus.NEEDS_REVIEW
        conflict.resolution_comment = comment
        audit.log(db, item_type="conflict", item_id=conflict.id, action="request_review", actor_id=user.id, project_id=conflict.project_id,
                  previous_state=previous, new_state=conflict.status, comment=comment)
        db.commit()
        return {"conflict_id": conflict.id, "status": conflict.status, "affected_actions": [], "notes": []}

    conflict.status = {"accept_new": ConflictStatus.ACCEPTED_NEW, "keep_previous": ConflictStatus.KEPT_PREVIOUS, "compatible": ConflictStatus.COMPATIBLE}[resolution]
    conflict.resolution_comment = comment
    conflict.resolved_by = user.id
    conflict.resolved_at = now

    if conflict.new_decision_id:
        old, new = db.get(Decision, conflict.old_decision_id), db.get(Decision, conflict.new_decision_id)
        if resolution == "accept_new":
            superseded = _supersede_chain(db, old, new, user, now)
            new.supersedes_id = old.id
            if not unresolved_for_decision(db, new.id, exclude=conflict.id):
                _set_decision(db, new, DecisionStatus.CONFIRMED, user, now, f"Confirmed by resolving conflict #{conflict.id}")
            affected = db.query(ActionItem).filter(ActionItem.decision_id.in_([d.id for d in superseded]), ActionItem.status.in_(ActionStatus.LIVE)).all()
            if affected:
                notes.append(f"{len(affected)} task(s) were planned under the superseded decision; review them.")
        elif resolution == "keep_previous":
            _set_decision(db, new, DecisionStatus.REJECTED, user, now, f"Rejected by resolving conflict #{conflict.id}: previous decision kept")
            for other in unresolved_for_decision(db, new.id, exclude=conflict.id):
                other.status, other.resolved_by, other.resolved_at = ConflictStatus.KEPT_PREVIOUS, user.id, now
                other.resolution_comment = f"Closed automatically: decision #{new.id} was rejected in conflict #{conflict.id}."
        else:  # compatible: both stand; the new decision returns to normal review
            if not unresolved_for_decision(db, new.id, exclude=conflict.id) and new.status == DecisionStatus.UNDER_REVIEW:
                _set_decision(db, new, DecisionStatus.PROPOSED, user, now, f"Conflict #{conflict.id} marked compatible; awaiting normal approval")
    else:
        old, new = db.get(ActionItem, conflict.old_action_id), db.get(ActionItem, conflict.new_action_id)
        if resolution == "accept_new":
            prev = old.status
            old.status = ActionStatus.SUPERSEDED
            audit.log(db, item_type="action", item_id=old.id, action="supersede", actor_id=user.id, project_id=old.project_id,
                      previous_state=prev, new_state=old.status, comment=f"Superseded by action #{new.id} (conflict #{conflict.id})")
            if old.publication and old.publication.state == "published" and old.publication.provider != "demo":
                notes.append(f"The earlier task is still open in the tracker ({old.publication.external_url}); close or update it there.")
        elif resolution == "keep_previous":
            prev = new.status
            new.status = ActionStatus.REJECTED
            new.reviewed_by, new.reviewed_at = user.id, now
            audit.log(db, item_type="action", item_id=new.id, action="reject", actor_id=user.id, project_id=new.project_id,
                      previous_state=prev, new_state=new.status, comment=f"Previous task kept (conflict #{conflict.id})")

    audit.log(db, item_type="conflict", item_id=conflict.id, action=resolution, actor_id=user.id, project_id=conflict.project_id,
              previous_state=previous, new_state=conflict.status, comment=comment,
              details={"affected_action_ids": [a.id for a in affected]})
    if affected:
        db.add(Notification(user_id=None, kind="affected_tasks", title=f"{len(affected)} task(s) follow a superseded decision",
                            body="; ".join(a.title for a in affected), link="/actions"))
    db.commit()
    return {
        "conflict_id": conflict.id, "status": conflict.status, "notes": notes,
        "affected_actions": [{"id": a.id, "title": a.title, "owner": a.owner_name, "status": a.status} for a in affected],
    }


def _set_decision(db: Session, d: Decision, status: str, user: User, now, comment: str) -> None:
    prev = d.status
    d.status, d.reviewed_by, d.reviewed_at = status, user.id, now
    audit.log(db, item_type="decision", item_id=d.id, action=status, actor_id=user.id, project_id=d.project_id,
              previous_state=prev, new_state=status, comment=comment)


def _supersede_chain(db: Session, old: Decision, new: Decision, user: User, now) -> list[Decision]:
    """Supersede the old decision and any earlier decisions it merely reaffirmed. Nothing is deleted."""
    out: list[Decision] = []
    cur: Decision | None = old
    seen: set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if cur.status in DecisionStatus.LIVE:
            prev = cur.status
            cur.status, cur.superseded_by_id = DecisionStatus.SUPERSEDED, new.id
            audit.log(db, item_type="decision", item_id=cur.id, action="supersede", actor_id=user.id, project_id=cur.project_id,
                      previous_state=prev, new_state=cur.status, comment=f"Superseded by decision #{new.id}")
            out.append(cur)
        cur = db.get(Decision, cur.related_decision_id) if cur.related_decision_id else None
    return out
