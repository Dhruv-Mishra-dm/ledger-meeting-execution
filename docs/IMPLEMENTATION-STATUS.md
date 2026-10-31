# Implementation status

Last updated: 2026-10-31. Every claim here was either run by an automated test or exercised on the live servers. Unverified items are marked.

## Official requirements (Product Space PS-03)

| # | Requirement | Status | Verified by |
|---|---|---|---|
| 1 | Transcript ingestion with speaker attribution | Done (TXT, DOCX, text PDF, dictation, paste) | tests + live upload |
| 2 | Decisions, action items, owners, deadlines | Done (demo engine + LLM provider) | tests + live run |
| 3 | Conflicts with earlier decisions in memory | Done (contradiction, deadline change, ownership, scope; resource and commitment in LLM mode) | tests + live run |
| 4 | Tasks in a tracker through an integration | GitHub Issues adapter built; demo tracker labelled simulated | adapter tested against mocked GitHub API. **Live GitHub not yet verified (no token here).** |
| 5 | Reminders before deadlines | Done (24h, due today, overdue, persistent, deduplicated) | tests + live run + restart |
| 6 | Weekly digest per person | Done (on demand + Monday 08:00 job) | tests + live run |
| 7 | Confirmation before anything is posted | Done, enforced on the server | tests |
| V | Main input is speech through Wispr Flow | Voice-first dictation composer; engine handles spoken-language patterns | tests (self-correction, filler words, pronouns, requests). **Needs one live check with Wispr Flow on your machine.** |

## Live end-to-end run (2026-10-31, demo engine and demo tracker, through the Vite proxy)

```
Meeting 1: 2 decisions (MongoDB; launch Nov 8), 2 tasks (Rahul Nov 5, Priya Nov 7), 0 conflicts
Meeting 2: contradiction MongoDB -> PostgreSQL (confidence 0.97, "explicitly replacing"); launch Nov 8 restated -> no conflict
           accept new -> affected task flagged: "Complete the database integration"
Meeting 3: compared against 3 live decisions (MongoDB excluded); PostgreSQL consistent -> no conflict;
           deadline change launch Nov 8 -> Nov 22; deadline change Priya docs Nov 7 -> Nov 12
Publishing: unapproved -> 409; approved -> published; repeat -> "Already published; no duplicate was created."
Duplicate upload -> 409 "already uploaded as 'Atlas architecture kickoff'"
Memory: launch date current 2026-11-22 (two Nov 8 versions superseded); database current PostgreSQL (MongoDB superseded)
Demo clock 2026-11-11 -> 3 overdue, 1 due in 24h; Priya digest generated from stored records
Backend restarted -> memory unchanged, reminder count unchanged (4)
```

## Test results

- Backend: **61 passed** (`pytest`)
- Frontend: type-check clean, **5 passed** (`vitest`), production build succeeds

## Screens (all wired to the API)

Sign-in, Dashboard, Projects, Meetings, New meeting (voice-first, upload, paste), Transcript viewer and extraction results (meeting detail tabs),
Decision memory, Conflict review (list and detail), Approval queue, Action items, Integrations, Reminders (with demo clock) and notifications,
Weekly digest, Audit history.

## Needs credentials or your machine

| Item | What to do |
|---|---|
| Live GitHub Issues | Follow TRACKER-INTEGRATION.md, press *Test connection*, publish one task, and confirm the issue appears with labels. |
| Live LLM | Set `AI_PROVIDER=openai`, `AI_API_KEY`, and optionally `AI_MODEL` / `AI_BASE_URL`; process one meeting. |
| Wispr Flow | Dictate into *New meeting* once before recording the demo. |
| Visual UI pass | The UI compiles and every API path it calls was exercised, but this session could not open a browser. Click through the DEMO-GUIDE once. |

## Known limitations

- The demo engine is rule-based. It is strong on the patterns in VOICE-WORKFLOW.md and the categories in `ai/text.py` (technology choices,
  milestone dates, budgets). Open-ended decisions outside those categories are recorded with a generic topic, and only
  negation or scope-style conflicts are detected for them. Real-AI mode covers open-ended language.
- Resource and incompatible-commitment conflicts are classified only in real-AI mode.
- When a decision is superseded, its linked tasks are flagged for review, not changed automatically (by design: a human decides).
- GitHub has no native due-date field, so the date is a `due:` label and appears in the body.
- Single-process SQLite deployment. Not designed for multiple backend instances.
- Email delivery of digests and reminders is not implemented. Both are in-app.
