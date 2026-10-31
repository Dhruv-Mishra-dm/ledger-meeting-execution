# PS 03 implementation — phase by phase

Each phase is one commit. Tick the box in this file **and** append a log line to
[../docs/STATE.md](../docs/STATE.md). `STATUS: current` marks where the track is right now — move it as you finish,
and let agents read only that phase.

Exit criteria are self-deception-proof: name the command you run and what you see.

---

## M1 · Ingestion + extraction — H2:00–3:00 — `STATUS: pending`

Files: `lib/ingest.ts`, `lib/extract.ts`, `components/MeetingUpload.tsx`, `components/TranscriptView.tsx`,
prompts `meetings.extract` · `src/app/(meetings)/meetings/[id]/page.tsx`

Build
1. Fixture loader for `content/meetings/*.json` + a paste/upload path that accepts a labelled transcript
   (`[Priya 00:03:12] text`). No ASR — speaker attribution comes from the fixture (AGENTS.md §2, avoided list).
2. `extractMeeting(meeting)` → `{decisions[], actions[]}` using `platform/llm` and the runtime prompt in
   [PROMPTS.md §1](PROMPTS.md). Must emit `topicKey` + `topicAliases` + `evidence: number[]` + fuzzy `due.raw`.
3. Validator: drop items with no owner or no evidence; log the drop count (visible in the UI footer — honest).
4. Store every emitted decision/action as a `Fact` with `at = meeting.occurredAt`.
5. Render transcript with a speaker gutter, chips inline at their evidence segments.

Tests — `lib/extract.spec.ts`: mock fixture round-trip yields ≥1 decision and ≥1 action; a segment with no owner
produces a dropped, counted action.

**Exit:** `MOCK_LLM=1 npm run dev` → `/meetings/m1-standing` shows 2 decisions + 3 actions with owners and dates,
each chip linking to its segment. Then run once with the live model and cache the response as the new mock.
Do not continue to M2 until this is a real UI, not a JSON dump.

## M2 · Cross-meeting memory + conflict — H3:00–4:30 — `STATUS: pending` · **ladder item 1, the centrepiece**

Files: `lib/conflict.ts` (pure prefilter), `lib/reconcile.ts`, `components/ConflictStamp.tsx`,
`components/MemoryView.tsx`, `meetings.reconcile` prompt, `/meetings/memory` route

Build
1. `candidates(newD, all)` exactly as specified in [ARCHITECTURE.md §3](ARCHITECTURE.md) — deterministic, tested,
   no LLM inside it.
2. On ingesting meeting 2, run reconcile over ≤3 candidate pairs; `confidence ≥ 0.6` → `Conflict` fact + status
   transition (`superseded` on the old, `supersedes` on the new).
3. **The stamp**: paper-red `#B3261E`, mono uppercase `CONFLICT`, ~4° rotation, hairline box; expanding reveals the
   two quoted statements with meeting names and dates, the `kind`, and a one-line recommendation.
4. `/meetings/memory`: decisions grouped by `topicKey`, newest first, superseded ones below a rule, every row showing
   which meeting produced it. This is the screen that proves memory exists.
5. Fixture discipline: `m2-reversal.json` must contain one unambiguous reversal (e.g. "launch slips to 22 Nov" after
   "launch is 8 Nov") **and** two decisions that must *not* conflict, so a false positive is visible as a bug.

Tests — `conflict.spec.ts`: reversal pair is a candidate; unrelated active decision is not; same-meeting pairs
excluded; `status='superseded'` excluded from candidates.

**Exit:** load meeting 2 → the red stamp appears, citing both meetings with dates → `/meetings/memory` shows the
old decision struck through under the new one. If the stamp does not fire on the fixture, stop everything and fix it;
this is the one scored moment that cannot be faked.

## M3 · Confirmation + tracker integration — H4:30–5:15 — `STATUS: pending` · ladder 2 + 3

Files: `lib/tasks.ts` (state machine), `lib/providers/{local,todoist,notion}.ts`,
`components/ConfirmModal.tsx`, `app/api/tasks/post/route.ts`

Build
1. State machine first, tests second, UI last: `open → confirmed → posting → synced | failed`, transition function pure.
2. `ConfirmModal` previews the exact provider payload (content string, due syntax, owner) with Approve / Edit / Skip.
3. `/api/tasks/post` re-reads store status server-side and refuses anything not `confirmed`.
4. `local` provider shipped and identical to todoist path (same interface, same transitions) so a dead API costs
   nothing structurally.
5. Real token wired; success shows the provider URL as a link, and the actual app is opened on camera at that moment.

Tests — `tasks.spec.ts`: `createTask` unreachable from `open`; server route rejects unconfirmed id; provider failure
leaves status `failed` with payload retained.

**Exit:** one task exists in the real tracker, created only after Approve, and `kill check 3` and `4` get ticked.
If the API is not green by **H5:15**, drop to `local` and move on (ladder 3 → 3f); keep the gate.

## M4 · Reminders — H5:15–5:45 — `STATUS: pending` · ladder 4

`lib/reminders.ts` pure `dueWithin`; global banner (overdue / today / next 24h); `?now=` override for the video.
**Exit:** banner lists the fixture action due tomorrow using the override, and the README says the override exists.

## M5 · Weekly digest — H5:45–6:00 — `STATUS: pending` · ladder 5

`lib/digest.ts` groups per owner, `meetings.digest` prompt writes 3 sentences + item list; `/meetings/digest` with a
person switcher; "email preview" framing, no send.
**Exit:** two participants' digests render from data already in the store. If M2 or M3 slipped, cut this silently.

## M6 · Demo mode — H6:30–9:30 — `STATUS: pending`

No new features. Per [DEMO.md](DEMO.md): `npm run seed` determinism, provenance footers on every card, empty states,
the three clean mock-mode replays, one live run, narration dictated, unedited screenshots.

## Standing guards for this track

- If a phase overruns by >20 minutes, cut the *next* phase's ladder-bottom item, don't absorb it into the overrun.
- Never post to the tracker without the Approve transition — the requirement is the guardrail, not the API call.
- The conflict card must quote. A paraphrased conflict reads as an LLM making things up; two verbatim lines with
  meeting names and dates reads as a system that knows.
- Do not let the extraction prompt invent owners or dates. `confidence: 'inferred'` is displayed, not hidden.
