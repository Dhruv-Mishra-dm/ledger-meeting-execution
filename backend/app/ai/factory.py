from __future__ import annotations

from ..config import settings
from .base import AIError, MeetingAI
from .rules import RulesEngine


def get_engine(force_demo: bool = False) -> MeetingAI:
    if force_demo or settings.ai_provider in {"demo", "rules", ""}:
        return RulesEngine()
    if settings.ai_provider in {"openai", "gemini", "openai-compatible"}:
        from .openai_compat import OpenAICompatibleEngine

        return OpenAICompatibleEngine(settings.ai_base_url, settings.ai_api_key, settings.ai_model, settings.ai_timeout_s)
    raise AIError(f"Unknown AI_PROVIDER '{settings.ai_provider}'. Use 'demo' or 'openai'.")


def describe() -> dict:
    real = settings.ai_provider not in {"demo", "rules", ""}
    return {
        "provider": settings.ai_provider if real else "demo",
        "is_real_ai": real,
        "model": settings.ai_model if real else None,
        "configured": bool(settings.ai_api_key) if real else True,
        "label": f"Real AI · {settings.ai_model}" if real else "Demo mode · deterministic rules engine (not an LLM)",
    }
