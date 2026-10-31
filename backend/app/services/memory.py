"""Cross-meeting decision memory: retrieval is project-scoped, time-ordered and status-aware."""
from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..ai.base import DecisionView
from ..ai.text import jaccard, tokens
from ..models import Decision, DecisionStatus, Meeting


def to_view(d: Decision) -> DecisionView:
    return DecisionView(
        id=d.id, topic=d.topic, statement=d.statement, value=d.value, value_kind=d.value_kind,
        previous_value=d.previous_value, meeting_title=d.meeting.title, meeting_date=d.meeting.meeting_date,
        status=d.status, speaker=d.speaker, excerpt=d.evidence_excerpt,
    )


def live_decisions_before(db: Session, meeting: Meeting) -> list[Decision]:
    """Decisions from EARLIER meetings of the SAME project that still describe the current (or pending) state.

    Superseded and rejected decisions are excluded, so a third meeting is compared against the latest accepted
    decision, never against an obsolete one.
    """
    return (
        db.query(Decision)
        .join(Meeting, Meeting.id == Decision.meeting_id)
        .filter(
            Decision.project_id == meeting.project_id,
            Decision.meeting_id != meeting.id,
            Decision.status.in_(DecisionStatus.LIVE),
            or_(Meeting.meeting_date < meeting.meeting_date, and_(Meeting.meeting_date == meeting.meeting_date, Meeting.id < meeting.id)),
        )
        .order_by(Meeting.meeting_date, Meeting.id, Decision.id)
        .all()
    )


def current_per_topic(decisions: list[Decision]) -> dict[str, list[Decision]]:
    """Per topic: the most recent confirmed decision plus any newer, not-yet-reviewed ones."""
    by_topic: dict[str, list[Decision]] = {}
    for d in decisions:  # already in chronological order
        by_topic.setdefault(d.topic, []).append(d)
    out: dict[str, list[Decision]] = {}
    for topic, items in by_topic.items():
        confirmed = [d for d in items if d.status == DecisionStatus.CONFIRMED]
        anchor = confirmed[-1] if confirmed else None
        newer = [d for d in items if d.status != DecisionStatus.CONFIRMED and (anchor is None or _later(d, anchor))]
        out[topic] = ([anchor] if anchor else []) + newer
    return out


def _later(a: Decision, b: Decision) -> bool:
    return (a.meeting.meeting_date, a.meeting_id, a.id) > (b.meeting.meeting_date, b.meeting_id, b.id)


def candidates_for(topic: str, statement: str, live: list[Decision], limit: int = 5) -> list[Decision]:
    current = current_per_topic(live)
    picked: list[Decision] = list(current.get(topic, []))
    stoks = tokens(statement)
    scored = []
    for t, items in current.items():
        if t == topic:
            continue
        score = jaccard(tokens(t), tokens(topic)) + jaccard(stoks, tokens(items[-1].statement))
        if score >= 0.4:
            scored.append((score, items[-1]))
    picked += [d for _, d in sorted(scored, key=lambda x: -x[0])]
    return picked[:limit]


def history_chain(db: Session, decision: Decision) -> list[Decision]:
    """All versions of a decision, oldest first, following supersedes links in both directions."""
    seen: set[int] = set()
    chain = [decision]
    cur = decision
    while cur.supersedes_id and cur.supersedes_id not in seen:
        seen.add(cur.id)
        cur = db.get(Decision, cur.supersedes_id)
        chain.insert(0, cur)
    cur = decision
    while cur.superseded_by_id and cur.superseded_by_id not in seen:
        seen.add(cur.id)
        cur = db.get(Decision, cur.superseded_by_id)
        chain.append(cur)
    return chain
