"""Simulated tracker for running without credentials.

It is honest about what it is: is_external=False, every record says "simulated", and the UI shows
"Recorded in the demo tracker (not published externally)". It never claims an external task exists.
"""
from __future__ import annotations

from .base import CreatedTask, TaskPayload


class DemoTrackerProvider:
    name = "demo"
    label = "Demo tracker (simulated, not external)"
    is_external = False

    def configured(self) -> bool:
        return True

    def check(self) -> dict:
        return {"ok": True, "status": "demo", "detail": "Simulated tracker. Tasks stay inside this app and are not sent to any external service."}

    def preview(self, task: TaskPayload) -> dict:
        labels = ["meeting-agent"]
        if task.owner:
            labels.append(f"owner:{task.owner}")
        if task.deadline:
            labels.append(f"due:{task.deadline.isoformat()}")
        return {"provider": self.label, "repository": None, "title": task.title, "labels": labels, "assignees": []}

    def create_task(self, task: TaskPayload, idempotency_key: str) -> CreatedTask:
        return CreatedTask(external_id=f"SIM-{idempotency_key[-8:]}", url=f"/actions?simulated={idempotency_key[-8:]}")
