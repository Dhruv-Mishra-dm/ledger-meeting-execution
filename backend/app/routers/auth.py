from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import audit, serializers
from ..config import settings
from ..db import get_db
from ..models import User
from ..security import create_session, current_user, revoke_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(or_(func.lower(User.name) == body.username.strip().lower(), func.lower(User.email) == body.username.strip().lower())).first()
    if not u or not u.can_login or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Incorrect name or password")
    token = create_session(db, u)
    audit.log(db, item_type="system", item_id=u.id, action="login", actor_id=u.id)
    db.commit()
    return {"token": token, "user": serializers.user(u)}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db), _: User = Depends(current_user)):
    revoke_session(db, authorization.split(" ", 1)[1].strip())
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return serializers.user(user)


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Names and roles of sign-in accounts for the demo entry screen. Never returns passwords."""
    users = db.query(User).filter(User.can_login.is_(True)).order_by(User.role, User.name).all()
    return {
        "accounts": [{"name": u.name, "role": u.role} for u in users],
        "default_password_hint": settings.demo_password == "demo1234",
    }
