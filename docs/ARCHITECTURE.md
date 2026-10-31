# Architecture

A modular monolith: one FastAPI backend with SQLite persistence, and one React frontend. There are no microservices and no
extra infrastructure. The database, not the model, is the source of truth for every status.

```
Wispr Flow dictation ─┐
TXT / DOCX / PDF ─────┼─► ingest/parser ─► Meeting + Segments (speaker, timestamp) ─► AI engine (rules | LLM)
Paste ────────────────┘                                                                  │ schema-validated, grounded
                                                                                         ▼
                        memory.live_decisions_before(meeting) ◄── Decisions / ActionItems (status: proposed)
                                       │ same project · earlier meeting · not superseded/rejected
                                       ▼
                        conflicts.detect_*  ──► Conflict (open) + new decision → under_review
                                       │
                         HUMAN: approve / reject / edit · resolve conflict (accept new | keep previous | compatible | needs review)
                                       │
                        publishing.publish (server checks APPROVED) ──► TrackerProvider (GitHub Issues | demo)
                                       │ unique publication row + idempotency key + issue marker
                                       ▼
                        reminders.scan (every 5 min, at startup)  ·  digest.build (on demand, Mondays 08:00)
```

## Components

| Module | Responsibility |
|---|---|
| `app/ingest/parser.py` | Validates files (type, size, magic bytes, empty files, zip bombs, encrypted or scanned PDFs). Extracts text and splits it into speaker-attributed segments in 5 label formats. Parses header metadata. Hashes content for duplicate detection. Never invents speakers. |
| `app/ai/rules.py` | Deterministic demo engine. Handles speech clean-up, decision cues versus suggestions and questions, value extraction (technology choices, dates, amounts), in-meeting self-correction, pronoun follow-ups, requests and acceptances, ambiguous owners, dependencies, and multi-person clauses. |
| `app/ai/openai_compat.py` | Real LLM provider (Gemini or any OpenAI-compatible API). JSON mode, schema validation with one corrective retry, timeouts, rate-limit backoff. **Grounding**: removes owners not in the meeting, deadlines whose words are not in the transcript, and invalid evidence indexes. Code, not the model, resolves calendar dates. |
| `app/ai/base.py` | The engine contract (Pydantic schemas). Nothing is stored unless it validates. |
| `app/services/memory.py` | Project-scoped, time-ordered retrieval of *live* decisions (proposed, under review, confirmed). Takes the latest confirmed decision per topic plus newer unreviewed ones, and builds history chains. |
| `app/services/conflicts.py` | Decision conflicts (engine `judge`) and task conflicts (same work with a different owner or deadline). Human resolution with history-preserving supersession. |
| `app/services/review.py` | Approve, reject, edit and complete with compare-and-set transitions. Every change is audited. |
| `app/services/publishing.py` | Approval-gated, idempotent publishing. |
| `app/services/reminders.py`, `digest.py` | Reminders: phase-based, unique per (task, kind). Digest: per person, from stored records only. |
| `app/trackers/*` | `TrackerProvider` interface: `github` (real) and `demo` (simulated, `is_external=False`). |
| `app/clock.py` | Single source of "now", with a visible demo-clock override. |
| `frontend/` | React, Vite, TypeScript, Tailwind and React Router. Fifteen screens, all wired to the API. |

## Key decisions

### Tracker: GitHub Issues (with the demo adapter as fallback)

Options compared (Trello, GitHub Issues, Todoist):

| Criterion | Trello | **GitHub Issues** | Todoist |
|---|---|---|---|
| Setup for a beginner | API key from the Power-Up admin portal, plus a separate token | **One fine-grained token** | One token |
| Free | yes | yes | yes |
| API stability | good | **excellent, versioned** | recent REST v2 → v1 migration |
| Due dates | native | label `due:YYYY-MM-DD` plus body | native |
| Owners | board members only | collaborators as assignees (optional mapping); otherwise an `owner:` label | shared projects only |
| Duplicate prevention after a crash | database only | **database plus a hidden marker in the issue body, found again before creating** | database only |
| Demo to judges | visual board | clickable issue link; the team already needs GitHub to submit | task list |

**Decision:** GitHub Issues. It is the only option that makes publishing crash-safe across the external boundary, it
needs no new account, and its API is the most stable. **Trade-off:** there is no native due-date field, so the date goes in a label and the issue body. The
SRS recommends Trello. The official statement does not name a tracker, so per the source-of-truth hierarchy we
chose on merit. Adding Trello later means implementing one `TrackerProvider` class.

### Stack: React + Vite + FastAPI + SQLite (deviation from the Phase 0 docs)

The earlier planning docs (`docs/planning/`) assumed a shared Next.js workspace with a JSON-file store. This build
follows the official SRS stack because:
- the persistence requirement rules out JSON or in-process storage;
- SQLAlchemy and Alembic give real migrations, foreign keys and unique constraints, which provide the idempotency guarantees;
- the product is standalone, with no shared platform with PS-02.

All Phase 0 review findings were carried over:
- decisions are keyed by a stable id, with topic as an attribute;
- ownerless decisions are kept;
- conflicts are resolved by a human;
- quotes come verbatim from stored segments;
- demo output is tied to its input;
- there is no generic LLM proxy;
- publishing uses compare-and-set and idempotency keys;
- only the latest version per decision is considered live.

### Conflict detection strategy

1. **Retrieval (deterministic):** live decisions from earlier meetings in the same project. Per topic, take the latest
   confirmed decision plus newer unreviewed ones. Add cross-topic candidates by token similarity. At most 5.
   Superseded or rejected decisions are never candidates, which is the meeting 3 regression guarantee.
2. **Judgement:** the rules engine (value mismatch on the same topic means a contradiction or a deadline change), or the LLM,
   with a rules safety net. A value mismatch the LLM calls "compatible" still surfaces, at lower confidence.
3. **Confidence of at least 0.5** creates a conflict. Below that, a note is attached to the decision.
4. **Outcome:** the conflict is `open` and the new decision is `under_review`. It cannot be confirmed until a human resolves it.
5. **Resolution:**
   - *Accept new* supersedes the old decision and any decisions it merely reaffirmed. Nothing is deleted, and tasks linked to it are flagged.
   - *Keep previous* rejects the new decision.
   - *Compatible* returns the new decision to normal review.
   - *Needs review* keeps the conflict open, with a comment.

Task conflicts: the same work (similar title after ignoring generic verbs) with a different owner gives an **ownership** conflict; the same owner with a different
deadline gives a **deadline change**.

### Voice-first

Wispr Flow is a system-wide dictation tool that types into any text field. There is no public Wispr Flow API, and the app does not
claim to integrate with one. The main input screen is a dictation composer designed for Wispr output. The engine is built for
spoken language: filler words, stutters, ellipses, "actually / scratch that" corrections, pronouns, and requests followed by acceptance.
The browser microphone (Web Speech API) is an optional fallback only. See [VOICE-WORKFLOW.md](VOICE-WORKFLOW.md).

## Differences from the supplementary SRS (documented)

| SRS | Here | Why |
|---|---|---|
| Trello | GitHub Issues | See the tracker comparison above. The official statement does not name a tracker. |
| Semantic or embedding retrieval "if time permits" | Project-filtered topic and keyword retrieval | The SRS's own fallback. Accurate at hackathon scale, deterministic and testable. |
| Email digest | In-app digest, generated on demand and weekly | The SRS lists email as optional. |
| "PDF" SRS | The SRS file is a `.docx` | Content matches the official statement. |

## Implementation sequence (as built)

Foundation → ingestion → rules engine → memory → conflicts → review and publishing → reminders and digest → LLM provider →
API → tests (61 backend, 5 frontend) → UI (15 screens) → end-to-end smoke on live servers → restart test → docs.
