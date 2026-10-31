# Tracker integration: GitHub Issues

Why GitHub Issues, and not Trello or Todoist: see [ARCHITECTURE.md](ARCHITECTURE.md#tracker-github-issues-with-the-demo-adapter-as-fallback).

## Set up (about 3 minutes)

1. **Repository:** create one (for example `atlas-tasks`, private is fine) or reuse one. Check *Settings → General → Features → Issues* is enabled.
2. **Token:** GitHub → your avatar → *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*.
   - Repository access: **Only select repositories** → choose that repository.
   - Permissions → Repository permissions → **Issues: Read and write** (Metadata: read-only is added automatically).
   - Copy the token. It starts with `github_pat_`.
3. **Configure** `backend\.env`:
   ```
   TRACKER_PROVIDER=github
   GITHUB_TOKEN=github_pat_xxxxxxxx
   GITHUB_REPO=your-github-name/atlas-tasks
   # optional, to set real assignees (each login must be a collaborator on the repo):
   GITHUB_ASSIGNEES=Rahul:rahul-login,Priya:priya-login
   ```
4. Restart the backend (close its window and run `scripts\start.ps1`, or only `scripts\start-backend.ps1`).
5. In the app: **Integrations → Test connection** should say "Connected to your-name/atlas-tasks".

## What gets created

The title is the task title. The body contains the description, owner, due date, project, source meeting and date, related decision, and the evidence quote,
followed by a hidden marker `<!-- meeting-agent:key=mte-<install>-<action id> -->`.
Labels: `meeting-agent`, `owner:<name>`, `due:YYYY-MM-DD`. GitHub creates labels automatically on first use.

## Guarantees

- **Approval first:** the server refuses to publish any task that is not `approved` (HTTP 409).
- **No duplicates:**
  - one publication row per task (database unique constraint);
  - one idempotency key per task;
  - an atomic claim of the `publishing` state;
  - before creating an issue, existing `meeting-agent` issues are scanned for the marker and adopted if found.
- **Failures:** authentication errors, missing repositories, rate limits (`429` / `x-ratelimit-remaining: 0`, with the retry time), timeouts
  and 5xx errors (retried 3 times with backoff) leave the task `failed` with the error shown. It is never marked published, and **Retry publishing** is safe.
- If an assignee is not a collaborator (GitHub returns 422), the issue is still created, with the owner kept in the label and body.

## Without credentials

`TRACKER_PROVIDER=demo` (the default) records a simulated task inside the app. Everywhere it appears, it is labelled
"Simulated — not sent to any external service". **It does not count as the external integration**, and the app never claims it does.

## Adding another tracker

Implement `TrackerProvider` (`configured`, `check`, `preview`, `create_task(task, idempotency_key)`) in `app/trackers/` and
register it in `trackers/factory.py`. Nothing else changes.
