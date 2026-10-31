from datetime import date

import httpx
import pytest

from app.ai import openai_compat
from app.ai.base import AIError, ExtractionContext, SegmentView
from app.ai.openai_compat import OpenAICompatibleEngine
from app.ai.rules import RulesEngine
from conftest import add_meeting, login, project_id, review


def extract(text, speakers=None, d=date(2026, 11, 2), people=()):
    lines = text.split("\n")
    segs = [SegmentView(i, (speakers[i] if speakers else None), None, t) for i, t in enumerate(lines)]
    return RulesEngine().extract(ExtractionContext("t", d, segs, list(people), list(people)))


def test_explicit_decision_with_evidence():
    r = extract("The team has agreed to use MongoDB for the application database.", ["Anshul"])
    assert len(r.decisions) == 1
    d = r.decisions[0]
    assert (d.topic, d.value, d.speaker, d.evidence_idx) == ("database", "MongoDB", "Anshul", [0])
    assert "agreed to use MongoDB" in d.evidence_excerpt


def test_suggestions_and_questions_are_not_decisions():
    r = extract("Maybe we should switch to Vue?\nShould we use Stripe?\nI suggest we go with AWS.")
    assert r.decisions == []


def test_unassigned_action_and_missing_deadline():
    r = extract("Someone needs to update the onboarding guide.")
    a = r.actions[0]
    assert a.owner is None and a.owner_origin == "unassigned"
    assert a.deadline is None and a.deadline_origin == "unspecified"


def test_explicit_owner_and_deadline():
    r = extract("Rahul will complete the database integration by November 5.", ["Anshul"], people=["Rahul"])
    a = r.actions[0]
    assert (a.owner, a.owner_origin, a.deadline, a.deadline_origin) == ("Rahul", "explicit", date(2026, 11, 5), "explicit")
    assert a.title == "Complete the database integration"


def test_ambiguous_owner_left_unassigned():
    r = extract("Rahul or Karan will look into the flaky tests.")
    assert r.actions[0].owner is None
    assert "Ambiguous owner" in (r.actions[0].notes or "")


def test_speaker_discussing_is_not_assumed_owner():
    r = extract("We should think about the deployment pipeline sometime.", ["Priya"])
    assert all(a.owner != "Priya" for a in r.actions)


def test_multiple_speakers_each_get_their_tasks():
    r = extract("Rahul will set up CI and Priya will write the API docs by Friday.", ["Anshul"], people=["Rahul", "Priya"])
    owners = {a.owner: a for a in r.actions}
    assert set(owners) == {"Rahul", "Priya"}
    assert owners["Priya"].deadline == date(2026, 11, 6) and owners["Priya"].deadline_origin == "relative"


def test_self_correction_keeps_only_final_decision():
    text = ("Okay, so Rahul will handle the database migration... actually, let's not use MongoDB anymore. "
            "We decided to move to PostgreSQL. He should finish it by Friday.")
    r = extract(text, ["Anshul"], people=["Rahul"])
    assert [d.value for d in r.decisions] == ["PostgreSQL"]
    assert r.decisions[0].previous_value == "MongoDB"
    assert any("withdrew MongoDB" in c for c in r.corrections)
    a = r.actions[0]
    assert a.owner == "Rahul" and a.deadline == date(2026, 11, 6)
    assert a.related_decision == 0


def test_in_meeting_change_of_mind():
    r = extract("We'll go with AWS for hosting.\nActually no wait, let's go with Azure instead.", ["A", "A"])
    assert [d.value for d in r.decisions] == ["Azure"]
    assert r.corrections


def test_filler_words_and_stutters_do_not_break_extraction():
    r = extract("Um, so, uh, the the launch, you know, the production launch is scheduled for November 20.")
    assert r.decisions[0].topic == "production launch date" and r.decisions[0].value == "2026-11-20"


def test_request_becomes_explicit_when_accepted():
    r = extract("Priya, can you update the release notes?\nSure, I'll do it by Monday.", ["Anshul", "Priya"], people=["Priya"])
    a = r.actions[0]
    assert a.owner == "Priya" and a.owner_origin == "explicit"


# ---------------------------------------------------------------- real-AI provider (HTTP mocked)

def _engine_with(monkeypatch, responder):
    def fake_post(url, **kwargs):
        return responder(kwargs["json"])
    monkeypatch.setattr(openai_compat.httpx, "post", fake_post)
    monkeypatch.setattr(openai_compat.time, "sleep", lambda s: None)
    return OpenAICompatibleEngine("https://example.invalid/v1/", "k", "test-model", 5)


def _ctx():
    return ExtractionContext("m", date(2026, 11, 2), [SegmentView(0, "Anshul", None, "Rahul will migrate the database by Friday.")], ["Anshul", "Rahul"], ["Anshul", "Rahul"])


def _ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_invalid_model_json_retries_then_fails(monkeypatch):
    calls = []

    def responder(payload):
        calls.append(1)
        return _ok("this is not json")
    engine = _engine_with(monkeypatch, responder)
    with pytest.raises(AIError):
        engine.extract(_ctx())
    assert len(calls) >= 2


def test_provider_failure_raises(monkeypatch):
    engine = _engine_with(monkeypatch, lambda p: httpx.Response(503, text="down"))
    with pytest.raises(AIError, match="503"):
        engine.extract(_ctx())


def test_missing_fields_trigger_schema_retry(monkeypatch):
    replies = iter(['{"decisions": [{"statement": "x"}]}',
                    '{"decisions": [], "actions": [{"title": "Migrate the database", "owner": "Rahul", "owner_origin": "explicit", '
                    '"deadline": "2026-11-06", "deadline_raw": "by Friday", "deadline_origin": "relative", "evidence_idx": [0], "confidence": 0.9}]}'])
    engine = _engine_with(monkeypatch, lambda p: _ok(next(replies)))
    r = engine.extract(_ctx())
    assert r.actions[0].owner == "Rahul" and r.actions[0].deadline == date(2026, 11, 6)


def test_grounding_removes_invented_owner_and_deadline(monkeypatch):
    content = ('{"decisions": [], "actions": [{"title": "Migrate the database", "owner": "Zara", "owner_origin": "explicit", '
               '"deadline": "2026-12-01", "deadline_raw": "December 1", "deadline_origin": "explicit", "evidence_idx": [0, 7], "confidence": 0.9}]}')
    engine = _engine_with(monkeypatch, lambda p: _ok(content))
    a = engine.extract(_ctx()).actions[0]
    assert a.owner is None and a.owner_origin == "unassigned"
    assert a.deadline is None and a.deadline_origin == "unspecified"
    assert a.evidence_idx == [0]


def test_provider_failure_stores_nothing(client, monkeypatch):
    from app.ai import factory

    def boom(force_demo=False):
        raise AIError("AI processing failed: the AI provider returned HTTP 503.")
    monkeypatch.setattr("app.services.processing.get_engine", boom)
    h = login(client)
    mid = add_meeting(client, h, project_id(client, h), "We decided to use React.", process=False)
    r = client.post(f"/api/meetings/{mid}/process", headers=h, json={})
    assert r.status_code == 502
    data = review(client, h, mid)
    assert data["meeting"]["status"] == "failed" and "503" in data["meeting"]["process_error"]
    assert data["decisions"] == [] and data["actions"] == []


def test_ai_mode_is_reported_honestly(client):
    h = login(client)
    status = client.get("/api/system/status", headers=h).json()
    assert status["ai"]["is_real_ai"] is False and "not an LLM" in status["ai"]["label"]
    mid = add_meeting(client, h, project_id(client, h), "We decided to use React for the frontend.")
    assert review(client, h, mid)["meeting"]["ai_mode"] == "demo-rules"
