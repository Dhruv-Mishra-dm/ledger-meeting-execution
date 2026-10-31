"""Real AI provider for any OpenAI-compatible chat-completions endpoint (OpenAI, Gemini, Groq, OpenRouter...).

The model interprets; code verifies. Every response is schema-validated, and then grounded against the transcript:
owners must be people present in the meeting, deadlines must quote words that exist in the transcript, and
evidence indexes must point at real segments. Anything that fails grounding is downgraded, never trusted blindly.
"""
from __future__ import annotations

import json
import re
import time

import httpx
from pydantic import ValidationError

from .base import AIError, DecisionView, ExtractionContext, ExtractionResult, Judgement
from .dates import find_deadline
from .rules import rules_judge
from .text import canonical_topic

EXTRACT_SYSTEM = """You convert a meeting transcript into structured, reviewable work records for a team.
The transcript may be dictated speech: expect filler words, digressions, repeated statements and self-corrections.

Rules:
1. Extract only what the transcript supports. Never invent owners, deadlines, decisions or speaker names.
2. A decision is something the group settled. Suggestions, questions and hypotheticals are NOT decisions.
3. Self-corrections: when a speaker corrects themselves ("actually, let's not use MongoDB... we'll use PostgreSQL"),
   output ONLY the final decision, set previous_value to the abandoned option and add a short note.
4. An action item needs a concrete task. owner = the person who will do it, only if named or self-assigned ("I'll...").
   The person who talks about a task is not automatically its owner. If unclear, owner = null and owner_origin = "unassigned".
   Use owner_origin "inferred" when you resolved a pronoun ("he", "she") or a request nobody explicitly accepted.
5. deadline_raw must be the exact words from the transcript ("by Friday", "November 5"). deadline = ISO date resolved
   against the meeting date. If no deadline is stated, both are null and deadline_origin = "unspecified".
6. evidence_idx = the segment indexes that support the record; evidence_excerpt = a short verbatim quote.
7. topic = a short lowercase subject such as "database", "production launch date", "frontend framework".
   If the subject matches one of the EXISTING DECISIONS, reuse its topic string exactly. value = the chosen option
   or ISO date (value_kind "choice" | "date" | "amount" | "text").
8. Reply with JSON only, matching the schema."""

EXTRACT_SCHEMA = """{
  "decisions": [{"statement": str, "topic": str, "value": str|null, "value_kind": "choice"|"date"|"amount"|"text",
                 "previous_value": str|null, "speaker": str|null, "evidence_idx": [int], "evidence_excerpt": str,
                 "confidence": 0.0-1.0, "origin": "explicit"|"inferred", "notes": str|null}],
  "actions": [{"title": str, "description": str, "owner": str|null, "owner_origin": "explicit"|"inferred"|"unassigned",
               "deadline": "YYYY-MM-DD"|null, "deadline_raw": str|null,
               "deadline_origin": "explicit"|"relative"|"inferred"|"unspecified", "dependencies": [str],
               "related_decision": int|null (index into decisions), "speaker": str|null, "evidence_idx": [int],
               "evidence_excerpt": str, "confidence": 0.0-1.0, "notes": str|null}],
  "corrections": [str], "warnings": [str]
}"""

JUDGE_SYSTEM = """You compare one NEW decision from a meeting with EARLIER decisions from the same project.
For each earlier decision, classify the relationship:
- contradiction: the new decision reverses or replaces the earlier one (even if it says so explicitly)
- deadline_change: the same milestone or deliverable has a different date
- ownership: responsibility is assigned inconsistently
- resource: the commitments allocate the same person or resource incompatibly
- scope: approved scope is removed or materially expanded
- commitment: the two commitments cannot both be met
- compatible: consistent, a restatement, or a compatible elaboration
- unrelated: different subject
Do not treat wording differences as conflicts. Never resolve anything; a human decides.
explanation must cite both meetings by name and date. Reply with JSON only:
{"judgements": [{"candidate_id": int, "relation": str, "explanation": str, "confidence": 0.0-1.0, "recommended_action": str}]}"""


class OpenAICompatibleEngine:
    is_real_ai = True

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 60):
        if not api_key:
            raise AIError("AI_API_KEY is not set. Add it to backend/.env or use the demo engine.")
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.name = f"openai-compatible:{model}"

    # ------------------------------------------------------------------ transport
    def _chat(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        last_error = "unknown error"
        for attempt in range(3):
            try:
                resp = httpx.post(
                    self.base_url + "chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout_s,
                )
            except httpx.TimeoutException:
                last_error = f"the AI provider did not answer within {self.timeout_s:.0f}s"
                continue
            except httpx.HTTPError as exc:
                last_error = f"network error contacting the AI provider ({type(exc).__name__})"
                time.sleep(1 + attempt)
                continue
            if resp.status_code == 429:
                last_error = "the AI provider rate limit was reached"
                time.sleep(min(float(resp.headers.get("retry-after", 2 + 2 * attempt)), 10))
                continue
            if resp.status_code in (401, 403):
                raise AIError("The AI provider rejected the API key (check AI_API_KEY).")
            if resp.status_code >= 500:
                last_error = f"the AI provider returned HTTP {resp.status_code}"
                time.sleep(1 + attempt)
                continue
            if resp.status_code >= 400:
                raise AIError(f"The AI provider returned HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(_strip_fences(content))
            except (KeyError, IndexError, ValueError, TypeError):
                last_error = "the AI provider returned invalid JSON"
                continue
        raise AIError(f"AI processing failed: {last_error}.")

    # ------------------------------------------------------------------ extraction
    def extract(self, ctx: ExtractionContext) -> ExtractionResult:
        user = json.dumps({
            "meeting": {"title": ctx.meeting_title, "date": ctx.meeting_date.isoformat(), "participants": ctx.participants},
            "known_people": ctx.known_people,
            "existing_decisions": [
                {"topic": d.topic, "statement": d.statement, "value": d.value, "meeting": d.meeting_title, "date": d.meeting_date.isoformat()}
                for d in ctx.active_decisions
            ],
            "segments": [{"idx": s.idx, "speaker": s.speaker, "timestamp": s.timestamp, "text": s.text} for s in ctx.segments],
            "schema": EXTRACT_SCHEMA,
        }, ensure_ascii=False)
        errors = ""
        for _ in range(2):  # one retry with the validation error fed back
            raw = self._chat(EXTRACT_SYSTEM, user + (f"\n\nYour previous reply was invalid: {errors}. Fix it." if errors else ""))
            try:
                result = ExtractionResult.model_validate(raw)
            except ValidationError as exc:
                errors = str(exc)[:600]
                continue
            return ground(result, ctx)
        raise AIError("The AI response did not match the required schema after a retry.")

    def judge(self, new: DecisionView, candidates: list[DecisionView]) -> list[Judgement]:
        if not candidates:
            return []
        user = json.dumps({
            "new": _view(new),
            "earlier": [_view(c) for c in candidates],
        }, ensure_ascii=False)
        try:
            raw = self._chat(JUDGE_SYSTEM, user)
            items = [Judgement.model_validate(j) for j in raw.get("judgements", [])]
        except (AIError, ValidationError, AttributeError):
            return rules_judge(new, candidates)  # fall back to deterministic comparison; caller records detected_by
        valid_ids = {c.id for c in candidates}
        items = [j for j in items if j.candidate_id in valid_ids]
        # Safety net: a different value on the same topic is never silently accepted as compatible.
        by_id = {j.candidate_id: j for j in items}
        for rj in rules_judge(new, candidates):
            aj = by_id.get(rj.candidate_id)
            if rj.relation in {"contradiction", "deadline_change"} and (aj is None or aj.relation in {"compatible", "unrelated"}):
                rj.confidence = min(rj.confidence, 0.6)
                rj.explanation += " (The AI judged these compatible, but the recorded values differ; please check.)"
                by_id[rj.candidate_id] = rj
        return list(by_id.values())


def _view(d: DecisionView) -> dict:
    return {"id": d.id, "topic": d.topic, "statement": d.statement, "value": d.value, "meeting": d.meeting_title,
            "date": d.meeting_date.isoformat(), "status": d.status, "evidence": d.excerpt}


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def ground(result: ExtractionResult, ctx: ExtractionContext) -> ExtractionResult:
    """Verify model output against the transcript. Downgrade anything unsupported instead of trusting it."""
    seg_by_idx = {s.idx: s for s in ctx.segments}
    full = _norm(" ".join(s.text for s in ctx.segments))
    people = {p.lower() for p in [*ctx.participants, *ctx.known_people]} | {s.speaker.lower() for s in ctx.segments if s.speaker}
    first_names = {p.split()[0] for p in people if p}
    warnings = list(result.warnings)

    def fix_evidence(item) -> bool:
        item.evidence_idx = [i for i in item.evidence_idx if i in seg_by_idx]
        if not item.evidence_idx:
            return False
        if not item.evidence_excerpt or _norm(item.evidence_excerpt) not in full:
            item.evidence_excerpt = seg_by_idx[item.evidence_idx[0]].text[:300]
        return True

    decisions = []
    for d in result.decisions:
        if not fix_evidence(d):
            warnings.append(f"Dropped decision without valid evidence: {d.statement[:60]}")
            continue
        d.topic = canonical_topic(f"{d.statement} {d.value or ''}") or d.topic
        decisions.append(d)
    actions = []
    for a in result.actions:
        if not fix_evidence(a):
            warnings.append(f"Dropped action without valid evidence: {a.title[:60]}")
            continue
        if a.owner and a.owner.lower() not in people and a.owner.lower().split()[0] not in first_names and _norm(a.owner) not in full:
            warnings.append(f"Owner '{a.owner}' is not in the transcript; left unassigned.")
            a.owner, a.owner_origin = None, "unassigned"
        if a.deadline_raw and _norm(a.deadline_raw) not in full:
            warnings.append(f"Deadline '{a.deadline_raw}' is not in the transcript; removed.")
            a.deadline, a.deadline_raw, a.deadline_origin = None, None, "unspecified"
        if a.deadline_raw:
            mention = find_deadline(a.deadline_raw, ctx.meeting_date)
            if mention:  # code, not the model, resolves the calendar date
                a.deadline, a.deadline_origin = mention.value, mention.origin
        elif a.deadline is not None:
            a.deadline, a.deadline_origin = None, "unspecified"
        if a.related_decision is not None and not (0 <= a.related_decision < len(decisions)):
            a.related_decision = None
        actions.append(a)
    result.decisions, result.actions, result.warnings = decisions, actions, warnings
    return result
