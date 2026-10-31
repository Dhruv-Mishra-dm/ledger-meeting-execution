from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit, serializers
from ..config import settings
from ..db import get_db
from ..ingest.parser import IngestError, extract_text
from ..models import ActionItem, Conflict, Decision, Meeting, Project, ProjectMember, Role, User
from ..security import accessible_project_ids, current_user, ensure_project_access, require_reviewer
from ..services.people import project_people
from ..services.processing import create_meeting, process_meeting
from .deps import get_scoped

router = APIRouter(prefix="/api", tags=["projects & meetings"])


# ------------------------------------------------------------------ projects

class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)


def _project(db: Session, p: Project) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description, "created_at": serializers.iso(p.created_at),
        "meetings": db.query(Meeting).filter(Meeting.project_id == p.id).count(),
        "people": len(project_people(db, p.id)),
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = accessible_project_ids(db, user)
    q = db.query(Project)
    if ids is not None:
        q = q.filter(Project.id.in_(ids or [-1]))
    return [_project(db, p) for p in q.order_by(Project.created_at.desc())]


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    p = Project(name=body.name.strip(), description=body.description.strip())
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A project with this name already exists.")
    db.add(ProjectMember(project_id=p.id, user_id=user.id))
    audit.log(db, item_type="project", item_id=p.id, action="create", actor_id=user.id, project_id=p.id)
    db.commit()
    return _project(db, p)


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _project(db, get_scoped(db, Project, project_id, user))


@router.get("/projects/{project_id}/people")
def people(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    return [serializers.user(u) for u in project_people(db, project_id)]


# ------------------------------------------------------------------ meetings

class MeetingTextIn(BaseModel):
    project_id: int
    title: str = Field(default="", max_length=200)
    meeting_date: date | None = None
    text: str = Field(min_length=1, max_length=400_000)
    source: str = Field(default="dictation", pattern="^(dictation|paste)$")
    dictated_by: str | None = Field(default=None, max_length=80)
    participants: list[str] = Field(default_factory=list, max_length=50)


@router.post("/meetings/upload", status_code=201)
async def upload_meeting(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    title: str = Form(""),
    meeting_date: date | None = Form(None),
    participants: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    project = get_scoped(db, Project, project_id, user)
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        kind, text = extract_text(file.filename or "", data, settings.max_upload_bytes)
        m = create_meeting(
            db, project=project, user=user, text=text, source_type=kind, title=title, meeting_date=meeting_date,
            filename=(file.filename or "")[:255], size=len(data), participants=[p.strip() for p in participants.split(",") if p.strip()],
        )
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return serializers.meeting_brief(m)


@router.post("/meetings/text", status_code=201)
def create_from_text(body: MeetingTextIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Voice-first input: text dictated with Wispr Flow (or pasted) into the meeting composer."""
    project = get_scoped(db, Project, body.project_id, user)
    dictated_by = (body.dictated_by or user.name) if body.source == "dictation" else None
    try:
        m = create_meeting(
            db, project=project, user=user, text=body.text, source_type=body.source, title=body.title, meeting_date=body.meeting_date,
            dictated_by=dictated_by, participants=body.participants,
        )
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return serializers.meeting_brief(m)


@router.get("/meetings")
def list_meetings(project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_project_access(db, user, project_id)
    out = []
    for m in db.query(Meeting).filter(Meeting.project_id == project_id).order_by(Meeting.meeting_date.desc(), Meeting.id.desc()):
        out.append({
            **serializers.meeting_brief(m),
            "decisions": db.query(Decision).filter(Decision.meeting_id == m.id).count(),
            "actions": db.query(ActionItem).filter(ActionItem.meeting_id == m.id).count(),
            "open_conflicts": db.query(Conflict).filter(Conflict.meeting_id == m.id, Conflict.status.in_(["open", "needs_review"])).count(),
        })
    return out


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return serializers.meeting_full(get_scoped(db, Meeting, meeting_id, user))


class ProcessIn(BaseModel):
    engine: str = Field(default="default", pattern="^(default|demo)$")


@router.post("/meetings/{meeting_id}/process")
def process(meeting_id: int, body: ProcessIn | None = None, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    m = get_scoped(db, Meeting, meeting_id, user)
    return process_meeting(db, m, user, force_demo=bool(body and body.engine == "demo"))


@router.get("/meetings/{meeting_id}/review")
def review(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = get_scoped(db, Meeting, meeting_id, user)
    run = None
    from ..models import AIRun

    r = db.query(AIRun).filter(AIRun.meeting_id == m.id, AIRun.ok.is_(True)).order_by(AIRun.id.desc()).first()
    if r:
        run = {"provider": r.provider, "model": r.model, "corrections": r.output.get("corrections", []), "warnings": r.output.get("warnings", [])}
    return {
        "meeting": serializers.meeting_full(m),
        "decisions": [serializers.decision(d) for d in db.query(Decision).filter(Decision.meeting_id == m.id).order_by(Decision.id)],
        "actions": [serializers.action(a) for a in db.query(ActionItem).filter(ActionItem.meeting_id == m.id).order_by(ActionItem.id)],
        "conflicts": [serializers.conflict(db, c) for c in db.query(Conflict).filter(Conflict.meeting_id == m.id).order_by(Conflict.id)],
        "ai_run": run,
    }
