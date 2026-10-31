# Database

SQLite file at `backend/data/app.db`, with WAL mode and foreign keys on. The schema is managed by **Alembic**
(`backend/migrations/`), and the app runs `alembic upgrade head` on every start. To change the schema, edit `app/models.py` and run
`alembic revision --autogenerate -m "..."`.

## Entities

| Table | Purpose | Key constraints |
|---|---|---|
| `users` | People. Seeded accounts can log in; people first seen in transcripts are created with `can_login=false`. | `name` unique, `email` unique |
| `sessions` | Hashed bearer tokens with expiry | PK `token_hash` |
| `projects` | Memory boundary | `name` unique |
| `project_members` | Who can see a project | PK (`project_id`, `user_id`) |
| `meetings` | Transcript, metadata, source, processing status | **unique (`project_id`, `content_hash`)**, which provides duplicate detection |
| `meeting_segments` | Speaker-attributed lines (`speaker` NULL = unattributed) | unique (`meeting_id`, `idx`) |
| `meeting_participants` | Names from metadata or speakers, linked to users | unique (`meeting_id`, `name`) |
| `decisions` | Decision memory | index (`project_id`, `topic`, `status`); FKs `supersedes_id`, `superseded_by_id`, `related_decision_id` → `decisions` |
| `action_items` | Tasks, with owner and deadline provenance (`owner_origin`, `deadline_origin`, `deadline_raw`) | FK `decision_id` (nullable) |
| `conflicts` | Decision or task conflicts, with explanation and resolution | FKs to both sides |
| `task_publications` | One row per published action | **unique `action_id`, unique `idempotency_key`** |
| `reminders` | 24h, due-today and overdue reminders | **unique (`action_id`, `kind`)** |
| `notifications` | In-app inbox | unique `reminder_id` |
| `integrations` | Tracker status only. **No secrets are stored.** | unique `provider` |
| `approval_logs` | Audit trail: actor, action, previous and new state, comment, details | index `project_id` |
| `ai_runs` | Engine, model, input hash and full validated output per extraction | |
| `digests` | Stored weekly digest snapshots | unique (`user_id`, `project_id`, `week_start`) |
| `app_settings` | Demo clock, install id | |

## Status enums

- **Decision:** `proposed` → `confirmed` | `rejected`. `proposed` → `under_review` (open conflict) → `confirmed` | `rejected` | `proposed`. `confirmed` → `superseded` (only through conflict resolution).
- **Action:** `proposed` → `approved` → `done`. `proposed`/`approved` → `rejected`. Any live action → `superseded` (through conflict resolution). Editing an approved action returns it to `proposed`.
- **Conflict:** `open` → `needs_review` → `accepted_new` | `kept_previous` | `compatible`.
- **Publication:** `publishing` → `published` | `failed`; `failed` → `publishing` (retry with the same key).

## Rules that protect integrity

- Decisions are never deleted. Supersession links both directions, and history is always queryable.
- "Live" memory means `proposed`, `under_review` or `confirmed`. Retrieval only considers meetings earlier than the one being processed.
- All status changes use conditional updates (`WHERE status = expected`), so concurrent requests cannot double-apply.
- Times: timestamps are stored in UTC. Dates (meeting date, deadline) are plain dates, displayed without timezone shifts.
  "Today" comes from `clock.now()` in the project timezone (default `Asia/Kolkata`).
