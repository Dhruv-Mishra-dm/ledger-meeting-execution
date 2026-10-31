"""Persistent entities. The database, not the LLM, is the source of truth for every status.

Identity rule: every decision/action has a stable integer id. A decision's *topic* is a searchable
attribute used for retrieval, never its identity, so two decisions on the same topic can coexist and
history is preserved (superseded decisions are kept, linked by supersedes/superseded_by).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import utcnow
from .db import Base


class Role:
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    REVIEWERS = {ADMIN, MANAGER}


class DecisionStatus:
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    # Statuses that represent the project's current (or pending) state and are compared against new meetings.
    LIVE = {PROPOSED, UNDER_REVIEW, CONFIRMED}


class ActionStatus:
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DONE = "done"
    LIVE = {PROPOSED, APPROVED}


class ConflictStatus:
    OPEN = "open"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED_NEW = "accepted_new"
    KEPT_PREVIOUS = "kept_previous"
    COMPATIBLE = "compatible"
    UNRESOLVED = {OPEN, NEEDS_REVIEW}


def _now() -> datetime:
    return utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default=Role.MEMBER)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    can_login: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (UniqueConstraint("project_id", "content_hash", name="uq_meeting_content"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    meeting_date: Mapped[date] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(16))  # txt | docx | pdf | dictation | paste
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64))
    transcript_text: Mapped[str] = mapped_column(Text)
    dictated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")  # uploaded | processing | processed | failed
    process_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    segments: Mapped[list["MeetingSegment"]] = relationship(order_by="MeetingSegment.idx", cascade="all, delete-orphan")
    participants: Mapped[list["MeetingParticipant"]] = relationship(cascade="all, delete-orphan")


class MeetingSegment(Base):
    __tablename__ = "meeting_segments"
    __table_args__ = (UniqueConstraint("meeting_id", "idx"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(80), nullable=True)  # None = not stated in transcript
    timestamp: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text)


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (UniqueConstraint("meeting_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="transcript")  # transcript | metadata


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decision_memory", "project_id", "topic", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    topic: Mapped[str] = mapped_column(String(120))
    statement: Mapped[str] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value_kind: Mapped[str] = mapped_column(String(16), default="text")  # choice | date | text
    previous_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_idx: Mapped[list] = mapped_column(JSON, default=list)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    origin: Mapped[str] = mapped_column(String(16), default="explicit")  # explicit | inferred
    status: Mapped[str] = mapped_column(String(16), default=DecisionStatus.PROPOSED)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    related_decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)  # reaffirms an earlier decision
    decided_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting: Mapped[Meeting] = relationship(foreign_keys=[meeting_id])


class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    owner_origin: Mapped[str] = mapped_column(String(16), default="unassigned")  # explicit | inferred | unassigned
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_raw: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deadline_origin: Mapped[str] = mapped_column(String(16), default="unspecified")  # explicit | relative | inferred | unspecified
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    speaker: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_idx: Mapped[list] = mapped_column(JSON, default=list)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default=ActionStatus.PROPOSED)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting: Mapped[Meeting] = relationship(foreign_keys=[meeting_id])
    publication: Mapped["TaskPublication | None"] = relationship(back_populates="action", uselist=False)


class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), index=True)
    category: Mapped[str] = mapped_column(String(24))  # contradiction | deadline_change | ownership | resource | scope | commitment
    old_decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    new_decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    old_action_id: Mapped[int | None] = mapped_column(ForeignKey("action_items.id"), nullable=True)
    new_action_id: Mapped[int | None] = mapped_column(ForeignKey("action_items.id"), nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    detected_by: Mapped[str] = mapped_column(String(16), default="rules")  # rules | ai
    status: Mapped[str] = mapped_column(String(16), default=ConflictStatus.OPEN)
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskPublication(Base):
    """One row per action item, ever. The unique constraints are the duplicate-publishing guard."""
    __tablename__ = "task_publications"
    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("action_items.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(16))  # publishing | published | failed
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    action: Mapped[ActionItem] = relationship(back_populates="publication")


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("action_id", "kind", name="uq_reminder_once"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("action_items.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # due_24h | due_today | overdue
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reminder_id: Mapped[int | None] = mapped_column(ForeignKey("reminders.id"), unique=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Integration(Base):
    """Integration status only. Secrets live in environment variables and are never stored or returned."""
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="not_checked")
    workspace: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalLog(Base):
    __tablename__ = "approval_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    item_type: Mapped[str] = mapped_column(String(24))  # decision | action | conflict | meeting | publication | system
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AIRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("meetings.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("user_id", "project_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    week_start: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
