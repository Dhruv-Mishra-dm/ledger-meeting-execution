"""Approval-gated, idempotent publishing of action items to the task tracker.

Guarantees:
- An action must be APPROVED in the database at the moment of publishing (checked here, not in the UI).
- At most one TaskPublication row per action (unique constraint) and one external task per idempotency key.
- Only one request can hold the 'publishing' state; concurrent clicks get the existing state back.
- A failed call is recorded as 'failed' (never 'published') and can be retried with the same key.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..clock import utcnow
from ..models import ActionItem, ActionStatus, AppSetting, Decision, Project, TaskPublication, User
from ..trackers.base import TaskPayload, TrackerError, TrackerRateLimited
from ..trackers.factory import get_tracker
from . import ServiceError

STALE_AFTER = timedelta(minutes=2)


def install_id(db: Session) -> str:
    row = db.get(AppSetting, "install_id")
    if row is None:
        row = AppSetting(key="install_id", value=secrets.token_hex(4))
        db.add(row)
        db.commit()
    return row.value


def idempotency_key(db: Session, action: ActionItem) -> str:
    return f"mte-{install_id(db)}-{action.id}"


def build_payload(db: Session, action: ActionItem) -> TaskPayload:
    project = db.get(Project, action.project_id)
    decision = db.get(Decision, action.decision_id) if action.decision_id else None
    return TaskPayload(
        title=action.title, description=action.description, owner=action.owner_name, deadline=action.deadline,
        project=project.name, source_meeting=action.meeting.title, source_meeting_date=action.meeting.meeting_date,
        related_decision=decision.statement if decision else None, evidence=action.evidence_excerpt,
    )


def preview(db: Session, action: ActionItem) -> dict:
    tracker = get_tracker()
    p = build_payload(db, action)
    return {
        **tracker.preview(p), "is_external": tracker.is_external, "configured": tracker.configured(),
        "owner": p.owner, "deadline": p.deadline.isoformat() if p.deadline else None, "description": p.description,
        "source_meeting": p.source_meeting, "related_decision": p.related_decision,
    }


def _ser(pub: TaskPublication | None) -> dict | None:
    if pub is None:
        return None
    return {
        "state": pub.state, "provider": pub.provider, "external_id": pub.external_id, "external_url": pub.external_url,
        "attempts": pub.attempts, "last_error": pub.last_error, "is_external": pub.provider != "demo",
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
    }


def publish(db: Session, action: ActionItem, user: User) -> dict:
    db.refresh(action)
    if action.status not in {ActionStatus.APPROVED, ActionStatus.DONE}:
        raise ServiceError(409, "Only approved tasks can be published. Approve this task first.")
    tracker = get_tracker()
    if not tracker.configured():
        raise ServiceError(503, f"{tracker.label} is not configured. See Integrations for setup steps.")
    key = idempotency_key(db, action)

    pub = db.query(TaskPublication).filter(TaskPublication.action_id == action.id).first()
    if pub is None:
        pub = TaskPublication(action_id=action.id, provider=tracker.name, idempotency_key=key, state="publishing", attempts=1,
                              published_by=user.id, updated_at=utcnow())
        db.add(pub)
        try:
            db.commit()
        except IntegrityError:  # another request inserted it first
            db.rollback()
            pub = db.query(TaskPublication).filter(TaskPublication.action_id == action.id).one()
            return {"changed": False, "publication": _ser(pub), "message": "Publishing is already in progress."}
    else:
        if pub.state == "published":
            return {"changed": False, "publication": _ser(pub), "message": "Already published; no duplicate was created."}
        if pub.provider != tracker.name and pub.state == "failed":
            pub.provider = tracker.name
        cutoff = utcnow() - STALE_AFTER
        # Claim the row atomically: failed -> publishing, or a stale 'publishing' left behind by a crash.
        res = db.execute(
            update(TaskPublication)
            .where(TaskPublication.id == pub.id)
            .where((TaskPublication.state == "failed") | ((TaskPublication.state == "publishing") & (TaskPublication.updated_at < cutoff)))
            .values(state="publishing", attempts=TaskPublication.attempts + 1, updated_at=utcnow(), published_by=user.id, provider=tracker.name)
        )
        db.commit()
        if res.rowcount == 0:
            db.refresh(pub)
            return {"changed": False, "publication": _ser(pub), "message": "Publishing is already in progress."}
        db.refresh(pub)

    try:
        created = tracker.create_task(build_payload(db, action), key)
    except TrackerError as exc:
        pub.state, pub.last_error, pub.updated_at = "failed", str(exc), utcnow()
        audit.log(db, item_type="publication", item_id=action.id, action="publish_failed", actor_id=user.id, project_id=action.project_id,
                  previous_state="publishing", new_state="failed", comment=str(exc),
                  details={"provider": tracker.name, "retriable": getattr(exc, "retriable", True),
                           "retry_after_s": exc.retry_after_s if isinstance(exc, TrackerRateLimited) else None})
        db.commit()
        raise ServiceError(502 if not isinstance(exc, TrackerRateLimited) else 429, str(exc)) from exc

    pub.state, pub.external_id, pub.external_url = "published", created.external_id, created.url
    pub.last_error, pub.published_at, pub.updated_at = None, utcnow(), utcnow()
    audit.log(db, item_type="publication", item_id=action.id, action="publish", actor_id=user.id, project_id=action.project_id,
              previous_state="publishing", new_state="published",
              details={"provider": tracker.name, "external_id": created.external_id, "url": created.url, "adopted_existing": created.adopted,
                       "simulated": not tracker.is_external})
    db.commit()
    msg = "Recorded in the demo tracker (simulated, not sent to any external service)." if not tracker.is_external else (
        "Linked to the existing tracker task created earlier (no duplicate)." if created.adopted else f"Created in {tracker.label}.")
    return {"changed": True, "publication": _ser(pub), "message": msg}
