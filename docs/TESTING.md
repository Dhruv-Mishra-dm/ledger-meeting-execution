# Testing

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1
# or individually:
cd backend;  .\.venv\Scripts\python.exe -m pytest -q
cd frontend; npx tsc -b; npx vitest run
```

Backend tests use a throwaway SQLite file, the demo engine and a fake tracker. They need no network or keys.

**Last run: 61 backend tests passed; frontend type-check clean; 5 vitest tests passed.**

## Coverage map

| Area | Tests (`backend/tests/`) |
|---|---|
| Ingestion | valid TXT (speakers and timestamps kept), valid DOCX, valid text PDF, empty file, unsupported or fake files, duplicate upload (409), missing speaker not invented, meeting date required, parser formats and header, dictation attribution — `test_ingestion.py` |
| Extraction | explicit decision with evidence, suggestions and questions are not decisions, unassigned action, missing deadline, explicit owner and deadline, ambiguous owner, speaker not assumed as owner, multiple speakers, **self-correction**, change of mind, filler words, request then acceptance; LLM: **invalid JSON**, **provider failure**, schema retry, **grounding removes invented owner and deadline**, failure stores nothing, honest mode reporting — `test_extraction.py` |
| Memory and conflicts | contradiction with evidence and no auto-overwrite, confirm blocked until resolved, accept new supersedes and keeps history (and cannot be resolved twice), keep previous, compatible and needs review, members cannot resolve, **compatible restatement is not a conflict**, deadline change, task ownership and deadline conflicts, **ownerless decision retained**, **project isolation**, **persistence after restart**, **golden scenario: meeting 3 uses the latest accepted state** — `test_memory_conflicts.py` |
| Approval and publishing | unapproved and rejected tasks cannot publish, approved task publishes and stores the external id, **repeated approval is safe**, **repeated publishing does not duplicate**, **failed publish is recoverable with the same key**, members cannot approve or publish, editing requires re-approval, demo tracker labelled simulated; GitHub adapter: labels and marker, **adopts an existing issue instead of duplicating**, rate-limit and auth errors — `test_publishing.py` |
| Reminders and digest | 24h, due today, overdue; owner-only notifications; **completed task exclusion**; offline until after the deadline gives overdue only; **no duplicates after restart**; members cannot complete others' tasks; per-person digest is factual; members see only their own; migrations build the schema — `test_reminders_digest.py` |

## Critical regressions (named in the brief)

1. Meeting 3 compares against the latest accepted decision — `test_golden_scenario_third_meeting_uses_latest_accepted_state`
2. Demo output is tied to the correct input — the same test asserts meeting 2's extraction differs and contains PostgreSQL
3. No duplicate external tasks — `test_repeated_publishing_does_not_duplicate`, `test_failed_publish_is_recoverable_without_duplicates`, `test_github_adapter_adopts_existing_issue_instead_of_duplicating`
4. History never disappears — `test_accept_new_supersedes_and_preserves_history`
5. Project isolation — `test_project_memory_is_isolated`

## Manual end-to-end verification performed

The three demo meetings were run against the live servers through the frontend proxy: upload, process, resolve, approve, publish (twice), duplicate
upload, demo clock, digest and dashboard. The backend was then stopped and restarted, and memory plus the reminder count were unchanged. See
[IMPLEMENTATION-STATUS.md](IMPLEMENTATION-STATUS.md) for the results.

**Not verified here:** live GitHub Issues publishing and a live Gemini or OpenAI run, because no credentials were available. Both are
covered by tests against mocked HTTP and need one check with real keys (see TRACKER-INTEGRATION.md).
