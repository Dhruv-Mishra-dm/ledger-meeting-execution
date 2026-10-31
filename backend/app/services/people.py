from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import ProjectMember, Role, User


def project_people(db: Session, project_id: int) -> list[User]:
    return (
        db.query(User)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project_id)
        .order_by(User.name)
        .all()
    )


def resolve_person(db: Session, project_id: int, name: str | None, create: bool = True) -> User | None:
    """Map a name from a transcript to a person record. Only names that appear in the transcript reach here."""
    if not name or not name.strip():
        return None
    name = name.strip()
    user = db.query(User).filter(func.lower(User.name) == name.lower()).first()
    if user is None:
        first = name.split()[0].lower()
        matches = [u for u in project_people(db, project_id) if u.name.split()[0].lower() == first]
        user = matches[0] if len(matches) == 1 else None
    if user is None and create:
        user = User(name=name, role=Role.MEMBER, can_login=False)
        db.add(user)
        db.flush()
    if user is not None and db.get(ProjectMember, (project_id, user.id)) is None:
        db.add(ProjectMember(project_id=project_id, user_id=user.id))
        db.flush()
    return user
