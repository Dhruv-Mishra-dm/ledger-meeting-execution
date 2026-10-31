# Security

Scope: a hackathon MVP that runs locally or on a trusted network. Controls are listed with their limits.

## Implemented

| Area | Control | Where |
|---|---|---|
| Secrets | AI and GitHub keys come only from `backend/.env` (git-ignored). No endpoint returns them; `integrations` stores status, never tokens. The frontend never sees a key. | `config.py`, `routers/ops.py` |
| No LLM proxy | There is no browser-callable endpoint that forwards arbitrary prompts. The model is called only from server-side processing. | `services/processing.py` |
| Authentication | PBKDF2-SHA256 (200k iterations, per-user salt) password hashes; random 256-bit bearer tokens stored as SHA-256 hashes, with expiry (72h). | `security.py` |
| Authorization | Approve, reject, edit, resolve, publish and process require manager or admin. Members can only complete their own tasks and read their own digest. Project data is limited to project members; other projects return 404 so their existence is not revealed. | `security.py`, routers |
| Approval gate | Publishing re-reads the task status in the database and refuses anything not `approved`. Editing an approved task returns it to `proposed`. Hiding buttons is not the control. | `services/publishing.py`, `review.py` |
| Idempotency | Unique publication row per task, a unique idempotency key, an atomic claim of the `publishing` state, and a GitHub issue marker. A failed call is recorded as `failed`, never `published`. | `publishing.py`, `trackers/github.py` |
| History | Decisions are never deleted. Supersession is linked and audited. | `services/conflicts.py` |
| Audit | Every upload, processing run, approval, rejection, edit, comment, conflict resolution, publication and clock change is recorded with actor, time and state change. | `audit.py` |
| Upload safety | Extension allow-list, 2 MB limit, magic-byte checks (PDF `%PDF`, DOCX zip containing `word/document.xml`), binary-in-TXT rejection, zip-bomb guard (50 MB uncompressed), encrypted-PDF rejection. Files are parsed in memory and never written to disk or executed. | `ingest/parser.py` |
| Input validation | Pydantic models with length limits on every request body. Transcript limited to 400k characters. | routers |
| LLM output | Schema validation and grounding: owners must be in the meeting, deadline wording must appear in the transcript, evidence must point at real segments. Untrusted transcript content is passed as data inside JSON, and the human gate stops any injected "post this task". | `ai/openai_compat.py` |
| CORS and headers | CORS allow-list (`CORS_ORIGINS`), no credentials mode, limited methods and headers. The dev setup uses a same-origin proxy. Headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`. | `main.py` |
| XSS | React escapes all rendered text; no `dangerouslySetInnerHTML`. | frontend |

## Known limits (not hidden)

- The demo password is shared by the seeded accounts (`DEMO_PASSWORD`). Change it before showing the app on a public URL.
- The bearer token is kept in `localStorage`, which suits a demo. A production version would use HttpOnly cookies plus CSRF protection.
- There is no rate limiting on login. Add it before any public deployment.
- SQLite with a single backend process. Concurrency guards are conditional updates and unique constraints, which is correct for one process.
- GitHub assignees are set only if `GITHUB_ASSIGNEES` maps a name to a collaborator login. Otherwise the owner is a label.
