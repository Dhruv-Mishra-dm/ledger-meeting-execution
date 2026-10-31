from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass
class TaskPayload:
    title: str
    description: str
    owner: str | None
    deadline: date | None
    project: str
    source_meeting: str
    source_meeting_date: date
    related_decision: str | None
    evidence: str
    labels: list[str] = field(default_factory=list)


@dataclass
class CreatedTask:
    external_id: str
    url: str
    adopted: bool = False  # True when an existing task with our idempotency marker was found instead of creating one


class TrackerError(RuntimeError):
    retriable = True


class TrackerAuthError(TrackerError):
    retriable = False


class TrackerConfigError(TrackerError):
    retriable = False


class TrackerRateLimited(TrackerError):
    def __init__(self, message: str, retry_after_s: int | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class TrackerProvider(Protocol):
    name: str
    label: str
    is_external: bool  # False for the simulated demo tracker; the UI must never call that "published externally"

    def configured(self) -> bool: ...

    def check(self) -> dict: ...

    def preview(self, task: TaskPayload) -> dict: ...

    def create_task(self, task: TaskPayload, idempotency_key: str) -> CreatedTask: ...
