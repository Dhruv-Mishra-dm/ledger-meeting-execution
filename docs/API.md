# API

Base URL `http://127.0.0.1:8000`. Interactive OpenAPI documentation is at **`/docs`** while the backend runs.
All endpoints except `/api/auth/login`, `/api/auth/demo-accounts` and `/api/health` need the header `Authorization: Bearer <token>`.
Errors return `{"detail": "<human-readable message>"}` with a meaningful status code: 401, 403, 404 (also for other teams' projects), 409 (business rule), 422 (validation), 429 or 502 (tracker or AI failure).

**R** = manager or admin only (enforced on the server).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/login` | `{username, password}` → `{token, user}` |
| POST | `/api/auth/logout` | revokes the token |
| GET | `/api/auth/me` | current user |
| GET | `/api/auth/demo-accounts` | names and roles for the sign-in screen (never passwords) |

## Projects and meetings
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/projects` | POST is **R** |
| GET | `/api/projects/{id}`, `/api/projects/{id}/people` | |
| POST | `/api/meetings/upload` | multipart: `project_id`, `file` (.txt/.docx/.pdf, ≤ 2 MB), optional `title`, `meeting_date`, `participants` (comma-separated). 409 on duplicate. |
| POST | `/api/meetings/text` | voice-first: `{project_id, title, meeting_date, text, source: "dictation"\|"paste", dictated_by, participants[]}` |
| GET | `/api/meetings?project_id=` | list with counts |
| GET | `/api/meetings/{id}` | transcript segments and participants |
| POST | `/api/meetings/{id}/process` | **R**. `{engine: "default"\|"demo"}`. Runs extraction, memory retrieval and conflict detection. 409 if already processed; 502 if AI failed (nothing stored). |
| GET | `/api/meetings/{id}/review` | decisions, actions, conflicts (with evidence segments), AI run info |

## Decisions and memory
| Method | Path | Notes |
|---|---|---|
| GET | `/api/decisions?project_id=&status=&topic=` | |
| GET | `/api/decisions/memory?project_id=` | grouped by topic: current, pending, full history |
| GET | `/api/decisions/{id}` | with history chain, related conflicts and tasks |
| PATCH | `/api/decisions/{id}` | **R**. Statement, topic, value (only while under review) |
| POST | `/api/decisions/{id}/approve` | **R**. Idempotent; 409 while a conflict is open |
| POST | `/api/decisions/{id}/reject` | **R** |

## Conflicts
| Method | Path | Notes |
|---|---|---|
| GET | `/api/conflicts?project_id=&status=unresolved` | both sides with meetings and verbatim evidence |
| GET | `/api/conflicts/{id}` | |
| POST | `/api/conflicts/{id}/resolve` | **R**. `{resolution: accept_new\|keep_previous\|compatible\|needs_review, comment}`. 409 if already resolved. Returns the affected tasks. |

## Action items and publishing
| Method | Path | Notes |
|---|---|---|
| GET | `/api/actions?project_id=&status=a,b&owner_id=` | |
| GET | `/api/actions/{id}` | includes the publication state |
| PATCH | `/api/actions/{id}` | **R**. Title, description, owner_name, deadline, dependencies. An approved task returns to proposed. |
| POST | `/api/actions/{id}/approve` · `/reject` | **R**. Idempotent |
| GET | `/api/actions/{id}/preview` | exact tracker payload |
| POST | `/api/actions/{id}/publish` | **R**. 409 unless approved. Idempotent (repeat returns `changed:false`). 502 or 429 on tracker failure, with state `failed` (retry is safe). |
| POST | `/api/actions/{id}/complete` | owner or **R** |
| POST | `/api/{decision\|action\|conflict}s/{id}/comment` | `{comment}`, saved to the audit log |
| GET | `/api/approvals/queue?project_id=` | conflicts, decisions, tasks to approve, tasks ready to publish |

## Reminders, notifications, digest
| Method | Path | Notes |
|---|---|---|
| GET | `/api/reminders?project_id=` | reminder log, plus overdue and due-soon tasks |
| POST | `/api/reminders/scan` | **R**. Runs now (it also runs every 5 minutes and at startup) |
| GET | `/api/notifications` · POST `/{id}/read` · POST `/read-all` | |
| GET | `/api/digest/{user_id}?project_id=&week_start=` | members can only see their own |

## System
| Method | Path | Notes |
|---|---|---|
| GET | `/api/system/status` | AI mode, tracker mode, clock |
| POST | `/api/system/clock` | **R**. `{date: "YYYY-MM-DD" \| null}` sets the demo clock (shown as a banner) and runs the reminder scan |
| POST | `/api/system/reset-demo` | admin only. Wipes and reseeds |
| GET | `/api/dashboard?project_id=` | counts and lists for the dashboard |
| GET | `/api/integrations` · POST `/api/integrations/check` | status; live credential check (**R**) |
| GET | `/api/audit?project_id=&item_type=&item_id=` | audit trail |
| GET | `/api/health` | liveness |
