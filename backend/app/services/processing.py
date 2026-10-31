"""Meeting pipeline: store transcript -> extract -> validate -> persist -> retrieve memory -> detect conflicts."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy.orm import Session

from .. import audit
from ..ai.base import AIError, ExtractionContext, SegmentView
from ..ai.factory import get_engine
from ..clock import utcnow
from ..ingest.parser import IngestError, content_hash, parse_header_date, parse_transcript
from ..models import AIRun, ActionItem, Decision, Meeting, MeetingParticipant, MeetingSegment, Project, User
from . import ServiceError
from .conflicts import detect_action_conflicts, detect_decision_conflicts
from .memory import live_decisions_before, to_view
from .people import project_people, resolve_person


def create_meeting(
    db: Session, *, project: Project, user: User, text: str, source_type: str, title: str | None, meeting_date: date | None,
    filename: str | None = None, size: int = 0, dictated_by: str | None = None, participants: list[str] | None = None,
) -> Meeting:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        raise IngestError("The transcript is empty.")
    if len(text) > 400_000:
        raise IngestError("The transcript is too long (over 400,000 characters). Split it into separate meetings.")
    parsed = parse_transcript(text, dictated_by=dictated_by.strip() if dictated_by else None)
    if not parsed.segments:
        raise IngestError("No transcript content was found.")
    meeting_date = meeting_date or parse_header_date(parsed.header.get("date"))
    if meeting_date is None:
        raise IngestError("Enter the meeting date. It is needed to resolve deadlines such as 'next Friday'.")
    title = (title or "").strip() or parsed.header.get("meeting") or parsed.header.get("title") or (filename.rsplit(".", 1)[0] if filename else "Untitled meeting")

    digest = content_hash(text)
    dup = db.query(Meeting).filter(Meeting.project_id == project.id, Meeting.content_hash == digest).first()
    if dup:
        raise ServiceError(409, f"This transcript was already uploaded as '{dup.title}' (meeting #{dup.id}).")

    meeting = Meeting(
        project_id=project.id, title=title[:200], meeting_date=meeting_date, source_type=source_type, source_filename=filename,
        source_bytes=size or len(text.encode()), content_hash=digest, transcript_text=text, dictated_by=dictated_by, uploaded_by=user.id,
    )
    db.add(meeting)
    db.flush()
    for s in parsed.segments:
        db.add(MeetingSegment(meeting_id=meeting.id, idx=s.idx, speaker=s.speaker, timestamp=s.timestamp, text=s.text))
    names: dict[str, str] = {}
    for n in [*(participants or []), *parsed.header_participants]:
        if n and n.strip():
            names.setdefault(n.strip().lower(), "metadata")
    for n in parsed.speakers:
        names.setdefault(n.lower(), "transcript")
    display = {n.strip().lower(): n.strip() for n in [*(participants or []), *parsed.header_participants, *parsed.speakers] if n and n.strip()}
    for key, source in names.items():
        person = resolve_person(db, project.id, display[key])
        db.add(MeetingParticipant(meeting_id=meeting.id, name=display[key], user_id=person.id if person else None, source=source))
    audit.log(db, item_type="meeting", item_id=meeting.id, action="upload", actor_id=user.id, project_id=project.id, new_state="uploaded",
              details={"source_type": source_type, "filename": filename, "segments": len(parsed.segments), "speakers": parsed.speakers})
    db.commit()
    return meeting


def process_meeting(db: Session, meeting: Meeting, user: User, force_demo: bool = False) -> dict:
    if meeting.status == "processed":
        raise ServiceError(409, "This meeting has already been processed.")
    if meeting.status == "processing":
        raise ServiceError(409, "This meeting is already being processed.")
    meeting.status, meeting.process_error = "processing", None
    db.commit()

    try:
        engine = get_engine(force_demo)
        live = live_decisions_before(db, meeting)
        ctx = ExtractionContext(
            meeting_title=meeting.title,
            meeting_date=meeting.meeting_date,
            segments=[SegmentView(s.idx, s.speaker, s.timestamp, s.text) for s in meeting.segments],
            participants=[p.name for p in meeting.participants],
            known_people=[u.name for u in project_people(db, meeting.project_id)],
            active_decisions=[to_view(d) for d in live][-50:],
        )
        input_hash = hashlib.sha256(json.dumps([meeting.content_hash, engine.name], sort_keys=True).encode()).hexdigest()
        result = engine.extract(ctx)
    except AIError as exc:
        db.rollback()
        meeting.status, meeting.process_error = "failed", str(exc)
        db.add(AIRun(meeting_id=meeting.id, kind="extract", provider="error", input_hash=meeting.content_hash, ok=False, error=str(exc)))
        audit.log(db, item_type="meeting", item_id=meeting.id, action="process_failed", actor_id=user.id, project_id=meeting.project_id, comment=str(exc))
        db.commit()
        raise ServiceError(502, str(exc)) from exc

    try:
        speakers = {s.idx: s.speaker for s in meeting.segments}
        segments_text = {s.idx: s.text for s in meeting.segments}
        decisions: list[Decision] = []
        for d in result.decisions:
            ev = [i for i in d.evidence_idx if i in speakers]
            dec = Decision(
                project_id=meeting.project_id, meeting_id=meeting.id, topic=d.topic, statement=d.statement, value=d.value,
                value_kind=d.value_kind, previous_value=d.previous_value,
                speaker=d.speaker if d.speaker in speakers.values() else speakers.get(ev[0]),
                evidence_idx=ev, evidence_excerpt=d.evidence_excerpt or segments_text.get(ev[0], ""),
                confidence=d.confidence, origin=d.origin, notes=d.notes, decided_on=meeting.meeting_date,
            )
            dec.meeting = meeting
            db.add(dec)
            decisions.append(dec)
        db.flush()

        conflicts = []
        for dec in decisions:
            conflicts += detect_decision_conflicts(db, engine, dec, live)

        actions: list[ActionItem] = []
        for a in result.actions:
            ev = [i for i in a.evidence_idx if i in speakers]
            owner = resolve_person(db, meeting.project_id, a.owner) if a.owner else None
            act = ActionItem(
                project_id=meeting.project_id, meeting_id=meeting.id,
                decision_id=decisions[a.related_decision].id if a.related_decision is not None and a.related_decision < len(decisions) else None,
                title=a.title, description=_description(a), owner_name=owner.name if owner else None, owner_user_id=owner.id if owner else None,
                owner_origin=a.owner_origin if owner else "unassigned", deadline=a.deadline, deadline_raw=a.deadline_raw,
                deadline_origin=a.deadline_origin if a.deadline else "unspecified", dependencies=a.dependencies,
                speaker=a.speaker if a.speaker in speakers.values() else speakers.get(ev[0]), evidence_idx=ev,
                evidence_excerpt=a.evidence_excerpt or segments_text.get(ev[0], ""), confidence=a.confidence,
            )
            act.meeting = meeting
            db.add(act)
            actions.append(act)
        db.flush()
        for act in actions:
            conflicts += detect_action_conflicts(db, act, meeting)

        meeting.status, meeting.ai_mode, meeting.processed_at = "processed", engine.name, utcnow()
        db.add(AIRun(meeting_id=meeting.id, kind="extract", provider=engine.name, model=engine.model, input_hash=input_hash, ok=True,
                     output=result.model_dump(mode="json")))
        audit.log(db, item_type="meeting", item_id=meeting.id, action="process", actor_id=user.id, project_id=meeting.project_id,
                  previous_state="uploaded", new_state="processed",
                  details={"engine": engine.name, "decisions": len(decisions), "actions": len(actions), "conflicts": len(conflicts),
                           "compared_against": [d.id for d in live]})
        db.commit()
    except Exception as exc:
        db.rollback()
        meeting = db.get(Meeting, meeting.id)
        meeting.status, meeting.process_error = "failed", f"Processing error: {type(exc).__name__}: {exc}"
        db.commit()
        raise

    return {
        "meeting_id": meeting.id, "engine": engine.name, "is_real_ai": engine.is_real_ai,
        "decisions": len(decisions), "actions": len(actions), "conflicts": len(conflicts),
        "compared_against": len(live), "corrections": result.corrections, "warnings": result.warnings,
    }


def _description(a) -> str:
    parts = [a.description.strip()] if a.description else []
    if a.notes:
        parts.append(f"Notes: {a.notes}")
    return "\n".join(parts)
