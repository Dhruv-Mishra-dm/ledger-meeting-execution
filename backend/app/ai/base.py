"""Contract shared by every AI engine. Engine output is validated against these schemas before anything is stored."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator


class ExtractedDecision(BaseModel):
    statement: str = Field(min_length=3, max_length=400)
    topic: str = Field(min_length=2, max_length=120)
    value: str | None = None
    value_kind: Literal["choice", "date", "amount", "text"] = "text"
    previous_value: str | None = None  # an earlier value mentioned in this same meeting ("from Nov 8 to Nov 22")
    speaker: str | None = None
    evidence_idx: list[int] = Field(min_length=1)
    evidence_excerpt: str = ""
    confidence: float = Field(ge=0, le=1)
    origin: Literal["explicit", "inferred"] = "explicit"
    notes: str | None = None

    @field_validator("topic")
    @classmethod
    def _norm_topic(cls, v: str) -> str:
        return " ".join(v.lower().replace("_", " ").replace(".", " ").split())


class ExtractedAction(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    owner: str | None = None
    owner_origin: Literal["explicit", "inferred", "unassigned"] = "unassigned"
    deadline: date | None = None
    deadline_raw: str | None = None
    deadline_origin: Literal["explicit", "relative", "inferred", "unspecified"] = "unspecified"
    dependencies: list[str] = Field(default_factory=list)
    related_decision: int | None = None  # index into ExtractionResult.decisions
    speaker: str | None = None
    evidence_idx: list[int] = Field(min_length=1)
    evidence_excerpt: str = ""
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None


class ExtractionResult(BaseModel):
    decisions: list[ExtractedDecision] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)  # human-readable self-corrections the engine applied
    warnings: list[str] = Field(default_factory=list)


Relation = Literal["contradiction", "deadline_change", "ownership", "resource", "scope", "commitment", "compatible", "unrelated"]


class Judgement(BaseModel):
    candidate_id: int
    relation: Relation
    explanation: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    recommended_action: str = ""


@dataclass
class SegmentView:
    idx: int
    speaker: str | None
    timestamp: str | None
    text: str


@dataclass
class DecisionView:
    id: int
    topic: str
    statement: str
    value: str | None
    value_kind: str
    previous_value: str | None
    meeting_title: str
    meeting_date: date
    status: str
    speaker: str | None = None
    excerpt: str = ""


@dataclass
class ExtractionContext:
    meeting_title: str
    meeting_date: date
    segments: list[SegmentView]
    participants: list[str]
    known_people: list[str]
    active_decisions: list[DecisionView] = field(default_factory=list)


class AIError(RuntimeError):
    """The engine could not produce a valid result. Nothing is stored when this is raised."""


class MeetingAI(Protocol):
    name: str
    is_real_ai: bool
    model: str | None

    def extract(self, ctx: ExtractionContext) -> ExtractionResult: ...

    def judge(self, new: DecisionView, candidates: list[DecisionView]) -> list[Judgement]: ...
