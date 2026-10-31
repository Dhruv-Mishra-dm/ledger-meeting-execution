"""MVP authentication: PBKDF2 password hashes, opaque bearer tokens stored hashed, role-based authorization."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .clock import utcnow
from .config import settings
from .db import get_db
from .models import ProjectMember, Role, User, UserSession

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER).hex()
    return f"pbkdf2${_ITER}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
    return hmac.compare_digest(test, digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=settings.session_hours)))
    db.commit()
    return token


def revoke_session(db: Session, token: str) -> None:
    row = db.get(UserSession, _token_hash(token))
    if row:
        db.delete(row)
        db.commit()


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    row = db.get(UserSession, _token_hash(authorization.split(" ", 1)[1].strip()))
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=utcnow().tzinfo)
    if expires < utcnow():
        db.delete(row)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    return row.user


def require_reviewer(user: User = Depends(current_user)) -> User:
    """Approvals, rejections, conflict resolution and publishing are restricted to managers and admins."""
    if user.role not in Role.REVIEWERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a project manager or admin can perform this review action")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def can_access_project(db: Session, user: User, project_id: int) -> bool:
    if user.role == Role.ADMIN:
        return True
    return db.get(ProjectMember, (project_id, user.id)) is not None


def ensure_project_access(db: Session, user: User, project_id: int) -> None:
    if not can_access_project(db, user, project_id):
        # 404 rather than 403 so project existence is not leaked across teams.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def accessible_project_ids(db: Session, user: User) -> list[int] | None:
    """None means unrestricted (admin)."""
    if user.role == Role.ADMIN:
        return None
    return [m.project_id for m in db.query(ProjectMember).filter(ProjectMember.user_id == user.id)]
