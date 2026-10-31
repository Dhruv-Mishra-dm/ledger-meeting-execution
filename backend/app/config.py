"""Runtime configuration, read once from environment variables (and backend/.env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}")
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    )
    # AI: "demo" = deterministic rules engine (no network). "openai" = any OpenAI-compatible endpoint (OpenAI, Gemini, Groq...).
    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "demo").strip().lower())
    ai_base_url: str = field(default_factory=lambda: os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))
    ai_api_key: str = field(default_factory=lambda: os.getenv("AI_API_KEY", ""))
    ai_model: str = field(default_factory=lambda: os.getenv("AI_MODEL", "gemini-2.0-flash"))
    ai_timeout_s: float = field(default_factory=lambda: float(os.getenv("AI_TIMEOUT_SECONDS", "60")))
    # Tracker: "demo" = clearly-labelled simulated tracker. "github" = real GitHub Issues.
    tracker_provider: str = field(default_factory=lambda: os.getenv("TRACKER_PROVIDER", "demo").strip().lower())
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))  # "owner/name"
    github_assignees: str = field(default_factory=lambda: os.getenv("GITHUB_ASSIGNEES", ""))  # "Rahul:rahul-gh,Priya:priya-gh"
    demo_password: str = field(default_factory=lambda: os.getenv("DEMO_PASSWORD", "demo1234"))
    session_hours: int = field(default_factory=lambda: int(os.getenv("SESSION_HOURS", "72")))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024))))
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    default_timezone: str = field(default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata"))


settings = Settings()
