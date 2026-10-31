from __future__ import annotations

from sqlalchemy.orm import Session

from .models import ApprovalLog


def log(
    db: Session,
    *,
    item_type: str,
    item_id: int | None,
    action: str,
    actor_id: int | None,
    project_id: int | None = None,
    previous_state: str | None = None,
    new_state: str | None = None,
    comment: str | None = None,
    details: dict | None = None,
) -> ApprovalLog:
    """Append an audit record. Caller commits, so the log entry is atomic with the change it describes."""
    entry = ApprovalLog(
        project_id=project_id,
        item_type=item_type,
        item_id=item_id,
        action=action,
        actor_id=actor_id,
        previous_state=previous_state,
        new_state=new_state,
        comment=comment,
        details=details or {},
    )
    db.add(entry)
    return entry
