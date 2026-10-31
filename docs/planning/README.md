# PS 03 — Meeting-to-execution agent · duo track

**Submission:** duo (A1 + A2) · **Code:** `src/products/meetings`, routes under `/meetings`
**Read first:** [../docs/DECISIONS.md](../docs/DECISIONS.md) D-005, D-006, D-009 · [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §4, §5, §8

## Thesis, in one line

A meeting memory that notices when this meeting contradicts the last one, and refuses to post anything until a human
confirms it. Without those two behaviours this is a transcript summariser, which is precisely what the brief warns is
not a system.

## Requirements coverage (judge's view)

| Requirement | Where it lives | Ladder |
|---|---|---|
| Transcript ingestion with speaker attribution | `lib/ingest.ts` + upload/fixture UI | 1 |
| Extract decisions, action items, owners, deadlines | `lib/extract.ts` → `meetings.extract` runtime prompt | 1 |
| Conflict detection vs earlier decisions in memory | `lib/conflict.ts` (deterministic prefilter) + `lib/reconcile.ts` (LLM) | 1 |
| Cross-meeting memory | `platform/store` namespace `meetings.decision`, history view `/meetings/memory` | 1 |
| Task creation through an integration | `lib/providers/{local,todoist,notion}.ts` behind `TaskProvider` | 3 |
| Confirmation before anything gets posted | `lib/tasks.ts` state machine + `components/ConfirmModal.tsx` | 2 |
| Reminders before deadlines | `lib/reminders.ts` deadline scan → banner | 4 |
| Weekly digest per person | `lib/digest.ts` → `/meetings/digest` | 5 |

## Scope ladder — cut from the bottom, silently

1. extraction + memory + conflict card · 2. confirmation gate · 3. real tracker task · 4. reminders ·
5. weekly digest · 6. polish beyond the golden path.

**Non-negotiable:** 1 and 2. If 3 fails by H7:15, fall to `local` provider and label it honestly — the confirmation
flow stays, because that is the scored behaviour, not the API call.

## Golden path (see [DEMO.md](DEMO.md))

Upload meeting 1 → items appear → load meeting 2 → **red CONFLICT stamp** because memory says otherwise →
confirm → task appears in the real tracker → reminder banner → digest for a person.

## Division of labour

A1 owns `lib/**` (extraction, prefilter, reconcile, provider interface, state machine) — the parts where a wrong
implementation would still look correct on screen, so they need a human reading the diff. A2 owns screens, tokens,
provenance footers, empty states. Neither edits
the other's files; `platform/**` changes go through A1 because the tutor track depends on them.

## Definition of done for the track

The golden path replays three times identically in `MOCK_LLM=1` and once against the live model, kill checks 1–4
ticked in [../docs/STATE.md](../docs/STATE.md), and `/meetings/memory` shows the superseded decision beside the new
one — the single screen that proves the system has a memory rather than a context window.
