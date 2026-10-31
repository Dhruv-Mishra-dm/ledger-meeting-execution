"""Model -> JSON shapes used by the API. Credentials never appear in any of these."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from .models import ActionItem, ApprovalLog, Conflict, Decision, Meeting, Notification, Reminder, User


def iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def user(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "can_login": u.can_login}


def meeting_brief(m: Meeting) -> dict:
    return {
        "id": m.id, "project_id": m.project_id, "title": m.title, "meeting_date": iso(m.meeting_date), "source_type": m.source_type,
        "source_filename": m.source_filename, "source_bytes": m.source_bytes, "status": m.status, "process_error": m.process_error,
        "ai_mode": m.ai_mode, "uploaded_at": iso(m.uploaded_at), "processed_at": iso(m.processed_at), "dictated_by": m.dictated_by,
        "participants": [p.name for p in m.participants], "segment_count": len(m.segments),
    }


def meeting_full(m: Meeting) -> dict:
    return {
        **meeting_brief(m),
        "segments": [{"idx": s.idx, "speaker": s.speaker, "timestamp": s.timestamp, "text": s.text} for s in m.segments],
        "participant_details": [{"name": p.name, "user_id": p.user_id, "source": p.source} for p in m.participants],
    }


def decision(d: Decision) -> dict:
    return {
        "id": d.id, "project_id": d.project_id, "meeting_id": d.meeting_id, "meeting_title": d.meeting.title,
        "meeting_date": iso(d.meeting.meeting_date), "topic": d.topic, "statement": d.statement, "value": d.value,
        "value_kind": d.value_kind, "previous_value": d.previous_value, "speaker": d.speaker, "evidence_idx": d.evidence_idx,
        "evidence_excerpt": d.evidence_excerpt, "confidence": d.confidence, "origin": d.origin, "status": d.status,
        "supersedes_id": d.supersedes_id, "superseded_by_id": d.superseded_by_id, "related_decision_id": d.related_decision_id,
        "notes": d.notes, "reviewed_at": iso(d.reviewed_at), "created_at": iso(d.created_at),
    }


def publication(a: ActionItem) -> dict | None:
    p = a.publication
    if p is None:
        return None
    return {
        "state": p.state, "provider": p.provider, "external_id": p.external_id, "external_url": p.external_url,
        "attempts": p.attempts, "last_error": p.last_error, "is_external": p.provider != "demo", "published_at": iso(p.published_at),
    }


def action(a: ActionItem) -> dict:
    return {
        "id": a.id, "project_id": a.project_id, "meeting_id": a.meeting_id, "meeting_title": a.meeting.title,
        "meeting_date": iso(a.meeting.meeting_date), "decision_id": a.decision_id, "title": a.title, "description": a.description,
        "owner_name": a.owner_name, "owner_user_id": a.owner_user_id, "owner_origin": a.owner_origin, "deadline": iso(a.deadline),
        "deadline_raw": a.deadline_raw, "deadline_origin": a.deadline_origin, "dependencies": a.dependencies, "speaker": a.speaker,
        "evidence_idx": a.evidence_idx, "evidence_excerpt": a.evidence_excerpt, "confidence": a.confidence, "status": a.status,
        "completed_at": iso(a.completed_at), "reviewed_at": iso(a.reviewed_at), "publication": publication(a),
    }


def conflict(db: Session, c: Conflict) -> dict:
    out = {
        "id": c.id, "project_id": c.project_id, "meeting_id": c.meeting_id, "category": c.category, "explanation": c.explanation,
        "confidence": c.confidence, "recommended_action": c.recommended_action, "detected_by": c.detected_by, "status": c.status,
        "resolution_comment": c.resolution_comment, "resolved_at": iso(c.resolved_at), "created_at": iso(c.created_at),
        "resolved_by": user(db.get(User, c.resolved_by)) if c.resolved_by else None,
        "kind": "decision" if c.new_decision_id else "action",
    }
    if c.new_decision_id:
        out["previous"] = decision(db.get(Decision, c.old_decision_id))
        out["current"] = decision(db.get(Decision, c.new_decision_id))
    else:
        out["previous"] = action(db.get(ActionItem, c.old_action_id))
        out["current"] = action(db.get(ActionItem, c.new_action_id))
    for side in ("previous", "current"):
        m = db.get(Meeting, out[side]["meeting_id"])
        idx = set(out[side]["evidence_idx"] or [])
        out[side]["evidence_segments"] = [
            {"idx": s.idx, "speaker": s.speaker, "timestamp": s.timestamp, "text": s.text} for s in m.segments if s.idx in idx
        ]
    return out


def reminder(r: Reminder) -> dict:
    return {"id": r.id, "action_id": r.action_id, "user_id": r.user_id, "owner_name": r.owner_name, "kind": r.kind,
            "due_date": iso(r.due_date), "status": r.status, "created_at": iso(r.created_at)}


def notification(n: Notification) -> dict:
    return {"id": n.id, "user_id": n.user_id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "created_at": iso(n.created_at), "read_at": iso(n.read_at)}


def log(entry: ApprovalLog, actor: User | None) -> dict:
    return {
        "id": entry.id, "project_id": entry.project_id, "item_type": entry.item_type, "item_id": entry.item_id, "action": entry.action,
        "actor": actor.name if actor else "system", "previous_state": entry.previous_state, "new_state": entry.new_state,
        "comment": entry.comment, "details": entry.details, "created_at": iso(entry.created_at),
    }
