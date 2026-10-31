from __future__ import annotations

from ..config import settings
from .base import TrackerProvider
from .demo import DemoTrackerProvider
from .github import GitHubIssuesProvider

_override: TrackerProvider | None = None  # tests inject a fake provider here


def get_tracker() -> TrackerProvider:
    if _override is not None:
        return _override
    if settings.tracker_provider == "github":
        return GitHubIssuesProvider(settings.github_token, settings.github_repo, settings.github_assignees)
    return DemoTrackerProvider()


def set_override(provider: TrackerProvider | None) -> None:
    global _override
    _override = provider
