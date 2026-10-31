from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import User
from ..security import ensure_project_access


def get_scoped(db: Session, model, item_id: int, user: User):
    """Load an entity and enforce that the user can access its project (404 otherwise)."""
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found")
    ensure_project_access(db, user, obj.project_id if hasattr(obj, "project_id") else obj.id)
    return obj
