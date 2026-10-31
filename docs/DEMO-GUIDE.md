# Demo guide: the three-meeting golden scenario (about 3 minutes)

**Project:** Atlas Customer Portal. **People:** Anshul (PM, manager account), Rahul (backend), Priya (documentation), Karan (QA).
**Files:** `demo/transcripts/meeting-1…3*.txt`. DOCX and PDF copies of meeting 3 are in `demo/other-formats/`.

## Before you start (2 minutes)

1. Close the backend window, run `scripts\reset-demo.ps1`, then `scripts\start.ps1`.
2. Sign in as **Anshul / demo1234**, with project *Atlas Customer Portal* selected.
3. Optional real integrations: GitHub configured and **Integrations → Test connection** green; `AI_PROVIDER=openai` with a key.
   Otherwise the app runs in demo mode and says so on screen. **Say so out loud too.**
4. Have Wispr Flow running for step 0.

## 0 · Voice input (the official "make it work with voice" requirement) — 30 s

**New meeting → Speak with Wispr Flow.** Click in the box and dictate with your Wispr Flow shortcut, for example:

> "Okay so quick sync on the portal. Um, Rahul will handle the database migration… actually, let's not use MongoDB anymore.
> We decided to move to PostgreSQL. He should finish it by Friday. Priya, can you update the API docs once the migration is done?"

Use the **Helios Analytics** project for this, so the golden path in Atlas stays clean. Save with "Extract right away" ticked.
**Show:**
- one decision only, **PostgreSQL**, with "changed from MongoDB";
- the "Self-corrections understood" panel;
- Rahul's task, with the deadline taken from the follow-up "He should finish it by Friday" and marked **relative**;
- Priya's task marked **inferred** until she accepts;
- evidence quotes.

## 1 · Meeting 1 — November 1 — 30 s

Switch to **Atlas**. **New meeting → Upload file →** `meeting-1-architecture-kickoff.txt` → Save.
**Show:** the speaker gutter on the **Transcript** tab. On the **Extraction** tab:
- decision **MongoDB** and launch date **Nov 8**;
- tasks: Rahul, *Complete the database integration*, due Nov 5; Priya, *Own the technical documentation*, due Nov 7;
- each with its quote.

**Approve** the two decisions and the two tasks. Open **Approval queue → Publish to tracker** for one task, show the exact payload preview, and publish.
Open the GitHub issue link (or point out the "Simulated" label in demo mode).

## 2 · Meeting 2 — November 2 — the moment that matters — 60 s

Upload `meeting-2-database-change.txt`.
**Show:**
- the red **CONFLICT · Direct contradiction** stamp: "Previously: MongoDB (Atlas architecture kickoff, Nov 1)" beside "Now: PostgreSQL (follow-up, Nov 2)", with both verbatim quotes and the recommendation;
- the PostgreSQL decision is **Under review**: its Approve button is replaced by a notice, and the API refuses confirmation too;
- the launch date restated as Nov 8 is **not** flagged (compatible).

Type a comment ("Load tests justify PostgreSQL") → **Accept the new decision**. The result shows Rahul's MongoDB integration task as **affected**.
Open **Decision memory**: Database = PostgreSQL, with MongoDB struck through underneath and both meetings and dates shown. Nothing was deleted.

## 3 · Meeting 3 — November 8 — 40 s

Upload `meeting-3-launch-readiness.txt` (or the DOCX or PDF copy, to show other formats).
**Show:**
- "We're staying on PostgreSQL" is consistent with the accepted decision, so there is **no MongoDB conflict**. The system compared against the latest accepted state, not the obsolete one;
- **Changed deadline**: launch Nov 8 → Nov 22 (14 days later);
- **Changed deadline** on Priya's documentation task: Nov 7 → Nov 12;
- Karan's retest task, with the dependency "the payment fix".

Accept both. The memory now shows the launch date at Nov 22, with both Nov 8 entries superseded.

## 4 · Reminders and digest — 20 s

Approve the meeting 3 tasks. **Reminders → Demo clock →** set **2026-11-11** → *Set app date*. A banner appears: say that it is a demo clock.
**Show:** overdue reminders for Rahul's tasks, "due in 24h" for Priya's documentation, and the notification bell.
**Weekly digest →** choose Priya, then Rahul: a per-person summary with overdue, upcoming and decisions, all from stored records.
**Audit history:** every approval, resolution and publication, with who and when.

## Fallback (if something breaks live)

Close the backend window and run `scripts\reset-demo.ps1 -Scenario`. All three meetings are then processed, resolved, approved and published
(to the configured tracker), so you can walk through memory, conflicts (filter *All, incl. resolved*), reminders and the digest.

## Duplicate detection (bonus, 5 s)

Upload meeting 1 again: "This transcript was already uploaded as 'Atlas architecture kickoff' (meeting #1)."
