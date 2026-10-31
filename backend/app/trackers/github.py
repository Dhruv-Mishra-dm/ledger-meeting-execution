"""GitHub Issues adapter (REST API v3, version 2022-11-28).

Idempotency is two-layered:
1. The database (task_publications has a unique row per action, and a unique idempotency key).
2. Every issue body carries a hidden marker with the idempotency key. Before creating an issue, the adapter
   looks for an existing issue with that marker and adopts it. So even if the app crashed after GitHub created
   the issue but before the database recorded it, a retry links the existing issue instead of duplicating it.
"""
from __future__ import annotations

import time

import httpx

from .base import CreatedTask, TaskPayload, TrackerAuthError, TrackerConfigError, TrackerError, TrackerRateLimited

API = "https://api.github.com"
LABEL = "meeting-agent"


def _marker(key: str) -> str:
    return f"<!-- meeting-agent:key={key} -->"


class GitHubIssuesProvider:
    name = "github"
    label = "GitHub Issues"
    is_external = True

    def __init__(self, token: str, repo: str, assignees: str = "", client: httpx.Client | None = None):
        self.token = token
        self.repo = repo.strip().strip("/")
        self.assignee_map = {}
        for pair in filter(None, (p.strip() for p in assignees.split(","))):
            if ":" in pair:
                person, login = pair.split(":", 1)
                self.assignee_map[person.strip().lower()] = login.strip()
        self._client = client

    # ------------------------------------------------------------------ helpers
    def configured(self) -> bool:
        return bool(self.token and self.repo and "/" in self.repo)

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=20)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.configured():
            raise TrackerConfigError("GitHub is not configured. Set GITHUB_TOKEN and GITHUB_REPO (owner/name) in backend/.env.")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "meeting-to-execution-agent",
        }
        last = "unknown error"
        client = self._http()
        try:
            for attempt in range(3):
                try:
                    resp = client.request(method, API + path, headers=headers, **kwargs)
                except httpx.TimeoutException:
                    last = "GitHub did not respond in time"
                    time.sleep(1 + attempt)
                    continue
                except httpx.HTTPError as exc:
                    last = f"network error contacting GitHub ({type(exc).__name__})"
                    time.sleep(1 + attempt)
                    continue
                if resp.status_code == 401:
                    raise TrackerAuthError("GitHub rejected the token (401). Create a new fine-grained token with Issues: read and write.")
                if resp.status_code == 429 or (resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0"):
                    retry = resp.headers.get("retry-after")
                    reset = resp.headers.get("x-ratelimit-reset")
                    wait = int(retry) if retry and retry.isdigit() else (max(0, int(reset) - int(time.time())) if reset and reset.isdigit() else None)
                    raise TrackerRateLimited(f"GitHub rate limit reached{f'; retry in {wait}s' if wait else ''}.", wait)
                if resp.status_code == 403:
                    raise TrackerAuthError("The GitHub token lacks permission for this repository (needs Issues: read and write).")
                if resp.status_code == 404:
                    raise TrackerConfigError(f"Repository '{self.repo}' was not found or the token cannot access it.")
                if resp.status_code >= 500:
                    last = f"GitHub returned HTTP {resp.status_code}"
                    time.sleep(1 + attempt)
                    continue
                return resp
        finally:
            if self._client is None:
                client.close()
        raise TrackerError(f"{last}. The task was not published; you can retry safely.")

    # ------------------------------------------------------------------ provider API
    def check(self) -> dict:
        if not self.configured():
            return {"ok": False, "status": "not_configured", "detail": "Set GITHUB_TOKEN and GITHUB_REPO in backend/.env."}
        try:
            resp = self._request("GET", f"/repos/{self.repo}")
        except TrackerError as exc:
            return {"ok": False, "status": "error", "detail": str(exc)}
        data = resp.json()
        if not data.get("has_issues", True):
            return {"ok": False, "status": "error", "detail": "Issues are disabled for this repository (Settings > Features > Issues)."}
        perms = data.get("permissions") or {}
        if perms and not (perms.get("push") or perms.get("triage") or perms.get("maintain") or perms.get("admin")):
            return {"ok": False, "status": "error", "detail": "Token can read but not create issues in this repository."}
        return {"ok": True, "status": "connected", "detail": f"Connected to {data.get('full_name', self.repo)}", "url": data.get("html_url")}

    def _body(self, task: TaskPayload, key: str) -> str:
        lines = [
            task.description.strip() or task.title,
            "",
            f"**Owner:** {task.owner or 'Unassigned'}",
            f"**Due:** {task.deadline.isoformat() if task.deadline else 'Not specified'}",
            f"**Project:** {task.project}",
            f"**Source meeting:** {task.source_meeting} ({task.source_meeting_date.isoformat()})",
        ]
        if task.related_decision:
            lines.append(f"**Related decision:** {task.related_decision}")
        if task.evidence:
            lines += ["", "> " + task.evidence.replace("\n", " ")[:500]]
        lines += ["", "_Created by the Meeting-to-Execution Agent after human approval._", _marker(key)]
        return "\n".join(lines)

    def preview(self, task: TaskPayload) -> dict:
        labels = [LABEL, *(task.labels or [])]
        if task.owner:
            labels.append(f"owner:{task.owner}")
        if task.deadline:
            labels.append(f"due:{task.deadline.isoformat()}")
        assignee = self.assignee_map.get((task.owner or "").lower())
        return {"provider": self.label, "repository": self.repo, "title": task.title, "labels": labels, "assignees": [assignee] if assignee else []}

    def find_existing(self, key: str) -> CreatedTask | None:
        marker = _marker(key)
        for page in range(1, 6):
            resp = self._request("GET", f"/repos/{self.repo}/issues", params={"state": "all", "labels": LABEL, "per_page": 100, "page": page})
            items = resp.json()
            for issue in items:
                if marker in (issue.get("body") or ""):
                    return CreatedTask(str(issue["number"]), issue["html_url"], adopted=True)
            if len(items) < 100:
                break
        return None

    def create_task(self, task: TaskPayload, idempotency_key: str) -> CreatedTask:
        existing = self.find_existing(idempotency_key)
        if existing:
            return existing
        preview = self.preview(task)
        body = {"title": task.title[:250], "body": self._body(task, idempotency_key), "labels": preview["labels"]}
        if preview["assignees"]:
            body["assignees"] = preview["assignees"]
        resp = self._request("POST", f"/repos/{self.repo}/issues", json=body)
        if resp.status_code == 422 and "assignees" in body:
            body.pop("assignees")  # assignee not a collaborator: still create the issue, owner stays in the label/body
            resp = self._request("POST", f"/repos/{self.repo}/issues", json=body)
        if resp.status_code not in (200, 201):
            raise TrackerError(f"GitHub returned HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return CreatedTask(str(data["number"]), data["html_url"])
