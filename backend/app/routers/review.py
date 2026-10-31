from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, serializers
from ..db import get_db
from ..models import ActionItem, Conflict, ConflictStatus, Decision, DecisionStatus, Meeting, User
from ..security import current_user, ensure_project_access, require_reviewer
from ..services import conflicts as conflict_svc
from ..services import publishing, review
from ..services.memory import history_chain
from .deps import get_scoped

router = APIRouter(prefix="/api", tags=["review"])


class CommentIn(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class RequiredCommentIn(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


# ------------------------------------------------------------------ decisions & memory

@router.get("/decisions")
def list_decisions(project_id: int, status: str | None = None, topic: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    q = db.query(Decision).join(Meeting, Meeting.id == Decision.meeting_id).filter(Decision.project_id == project_id)
    if status:
        q = q.filter(Decision.status == status)
    if topic:
        q = q.filter(Decision.topic == topic.lower())
    return [serializers.decision(d) for d in q.order_by(Meeting.meeting_date.desc(), Decision.id.desc())]


@router.get("/decisions/memory")
def memory(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Decisions grouped by topic, newest first, with superseded history kept underneath the current state."""
    ensure_project_access(db, user, project_id)
    rows = db.query(Decision).join(Meeting, Meeting.id == Decision.meeting_id).filter(Decision.project_id == project_id).order_by(Meeting.meeting_date.desc(), Decision.id.desc()).all()
    groups: dict[str, list[Decision]] = {}
    for d in rows:
        groups.setdefault(d.topic, []).append(d)
    out = []
    for topic, items in groups.items():
        current = next((d for d in items if d.status == DecisionStatus.CONFIRMED), None)
        pending = [d for d in items if d.status in {DecisionStatus.PROPOSED, DecisionStatus.UNDER_REVIEW}]
        out.append({
            "topic": topic,
            "current": serializers.decision(current) if current else None,
            "pending": [serializers.decision(d) for d in pending],
            "history": [serializers.decision(d) for d in items],
            "open_conflicts": db.query(Conflict).filter(Conflict.new_decision_id.in_([d.id for d in items]), Conflict.status.in_(ConflictStatus.UNRESOLVED)).count(),
            "last_changed": serializers.iso(items[0].meeting.meeting_date),
        })
    out.sort(key=lambda g: g["last_changed"], reverse=True)
    return out


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = get_scoped(db, Decision, decision_id, user)
    related = db.query(Conflict).filter((Conflict.old_decision_id == d.id) | (Conflict.new_decision_id == d.id)).all()
    return {
        **serializers.decision(d),
        "history": [serializers.decision(x) for x in history_chain(db, d)],
        "conflicts": [{"id": c.id, "category": c.category, "status": c.status} for c in related],
        "actions": [serializers.action(a) for a in db.query(ActionItem).filter(ActionItem.decision_id == d.id)],
    }


class DecisionEdit(BaseModel):
    statement: str | None = Field(default=None, min_length=3, max_length=400)
    topic: str | None = Field(default=None, min_length=2, max_length=120)
    value: str | None = Field(default=None, max_length=200)


@router.patch("/decisions/{decision_id}")
def edit_decision(decision_id: int, body: DecisionEdit, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    d = get_scoped(db, Decision, decision_id, user)
    changes = body.model_dump(exclude_unset=True)
    if "topic" in changes and changes["topic"]:
        changes["topic"] = " ".join(changes["topic"].lower().split())
    return serializers.decision(review.edit_decision(db, d, user, changes))


@router.post("/decisions/{decision_id}/approve")
def approve_decision(decision_id: int, body: CommentIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    return review.approve_decision(db, get_scoped(db, Decision, decision_id, user), user, body.comment if body else None)


@router.post("/decisions/{decision_id}/reject")
def reject_decision(decision_id: int, body: CommentIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    return review.reject_decision(db, get_scoped(db, Decision, decision_id, user), user, body.comment if body else None)


# ------------------------------------------------------------------ conflicts

@router.get("/conflicts")
def list_conflicts(project_id: int, status: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    q = db.query(Conflict).filter(Conflict.project_id == project_id)
    if status == "unresolved":
        q = q.filter(Conflict.status.in_(ConflictStatus.UNRESOLVED))
    elif status:
        q = q.filter(Conflict.status == status)
    return [serializers.conflict(db, c) for c in q.order_by(Conflict.id.desc())]


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serializers.conflict(db, get_scoped(db, Conflict, conflict_id, user))


class ResolveIn(BaseModel):
    resolution: str = Field(pattern="^(accept_new|keep_previous|compatible|needs_review)$")
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, body: ResolveIn, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    c = get_scoped(db, Conflict, conflict_id, user)
    result = conflict_svc.resolve(db, c, body.resolution, body.comment, user)
    return {**result, "conflict": serializers.conflict(db, c)}


# ------------------------------------------------------------------ actions

@router.get("/actions")
def list_actions(project_id: int, status: str | None = None, owner_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    q = db.query(ActionItem).filter(ActionItem.project_id == project_id)
    if status:
        q = q.filter(ActionItem.status.in_(status.split(",")))
    if owner_id:
        q = q.filter(ActionItem.owner_user_id == owner_id)
    items = q.all()
    items.sort(key=lambda a: (a.deadline is None, a.deadline or date.max, a.id))
    return [serializers.action(a) for a in items]


@router.get("/actions/{action_id}")
def get_action(action_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serializers.action(get_scoped(db, ActionItem, action_id, user))


class ActionEdit(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    owner_name: str | None = Field(default=None, max_length=80)
    deadline: date | None = None
    dependencies: list[str] | None = Field(default=None, max_length=20)


@router.patch("/actions/{action_id}")
def edit_action(action_id: int, body: ActionEdit, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    a = get_scoped(db, ActionItem, action_id, user)
    changes = body.model_dump(exclude_unset=True)
    if "owner_name" in changes and changes["owner_name"] is not None and not changes["owner_name"].strip():
        changes["owner_name"] = None
    return serializers.action(review.edit_action(db, a, user, changes))


@router.post("/actions/{action_id}/approve")
def approve_action(action_id: int, body: CommentIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    return review.approve_action(db, get_scoped(db, ActionItem, action_id, user), user, body.comment if body else None)


@router.post("/actions/{action_id}/reject")
def reject_action(action_id: int, body: CommentIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    return review.reject_action(db, get_scoped(db, ActionItem, action_id, user), user, body.comment if body else None)


@router.get("/actions/{action_id}/preview")
def preview_action(action_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return publishing.preview(db, get_scoped(db, ActionItem, action_id, user))


@router.post("/actions/{action_id}/publish")
def publish_action(action_id: int, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    a = get_scoped(db, ActionItem, action_id, user)
    result = publishing.publish(db, a, user)
    db.refresh(a)
    return {**result, "action": serializers.action(a)}


@router.post("/actions/{action_id}/complete")
def complete_action(action_id: int, body: CommentIn | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return review.complete_action(db, get_scoped(db, ActionItem, action_id, user), user, body.comment if body else None)


# ------------------------------------------------------------------ comments & approval queue

_COMMENTABLE = {"decision": Decision, "action": ActionItem, "conflict": Conflict}


@router.post("/{item_type}s/{item_id}/comment")
def comment(item_type: str, item_id: int, body: RequiredCommentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = _COMMENTABLE.get(item_type)
    if model is None:
        raise HTTPException(404, "Unknown item type")
    obj = get_scoped(db, model, item_id, user)
    entry = audit.log(db, item_type=item_type, item_id=item_id, action="comment", actor_id=user.id, project_id=obj.project_id,
                      previous_state=getattr(obj, "status", None), new_state=getattr(obj, "status", None), comment=body.comment.strip())
    db.commit()
    return serializers.log(entry, user)


@router.get("/approvals/queue")
def approval_queue(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    decisions = db.query(Decision).filter(Decision.project_id == project_id, Decision.status.in_([DecisionStatus.PROPOSED, DecisionStatus.UNDER_REVIEW])).order_by(Decision.id).all()
    actions = db.query(ActionItem).filter(ActionItem.project_id == project_id, ActionItem.status == "proposed").order_by(ActionItem.id).all()
    ready = [a for a in db.query(ActionItem).filter(ActionItem.project_id == project_id, ActionItem.status == "approved").order_by(ActionItem.id)
             if not a.publication or a.publication.state != "published"]
    conflicts = db.query(Conflict).filter(Conflict.project_id == project_id, Conflict.status.in_(ConflictStatus.UNRESOLVED)).order_by(Conflict.id).all()
    return {
        "decisions": [serializers.decision(d) for d in decisions],
        "actions": [serializers.action(a) for a in actions],
        "ready_to_publish": [serializers.action(a) for a in ready],
        "conflicts": [serializers.conflict(db, c) for c in conflicts],
    }
