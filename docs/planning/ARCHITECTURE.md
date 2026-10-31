# PS 03 architecture

Depends on the shared layer exactly as specified in [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
Nothing here may re-decide §4 (`MemoryStore`) or §5 (LLM contract).

## 1. Data model

```ts
type Speaker = { id: string; name: string; role?: string };

type Segment = {
  idx: number;              // ordering within the meeting
  speakerId: string;        // attribution is part of the fixture, not inferred
  startSec: number;
  text: string;
};

type Meeting = {
  id: string;               // 'm1-standing'
  title: string;
  occurredAt: string;       // ISO — every memory query is "as of" a date
  participants: Speaker[];
  segments: Segment[];
};

type TopicKey = string;     // normalised slug, e.g. 'pricing.launch-date' — see §3

type Decision = {
  id: string; meetingId: string; topicKey: TopicKey;
  statement: string;        // declarative, present tense, ≤140 chars
  ownerIds: string[];
  evidence: number[];       // Segment.idx values — provenance
  status: 'active' | 'superseded' | 'conflicted';
  supersedes?: string;      // Decision.id
};

type Action = {
  id: string; meetingId: string; topicKey: TopicKey;
  text: string; ownerId: string;
  due?: { iso: string; raw: string; confidence: 'explicit' | 'inferred' };  // 'next week' → inferred
  status: 'open' | 'confirmed' | 'posted' | 'synced' | 'failed';
  sync?: { provider: string; externalId?: string; url?: string };
};

type Conflict = {
  id: string; kind: 'reversal' | 'deadline_shift' | 'owner_change' | 'scope_change';
  olderDecisionId: string; newerDecisionId: string;
  explanation: string;      // LLM-authored, must quote both meetings
  recommendation: string;   // what to ask a human
  createdAt: string; resolvedBy?: string; resolution?: string;
};
```

Store mapping: `namespace='meetings.decision', key=topicKey` · `namespace='meetings.action', key=actionId` ·
`namespace='meetings.conflict', key=olderDecisionId`. Timestamp `at` is the **meeting's** `occurredAt`, never write
time — that is what makes "as of last Tuesday" queries correct and is the difference between memory and a log.

## 2. Pipeline

```
Meeting → truncate/window → LLM extract (decisions + actions + topicKeys + evidence idx)
       → validate + resolve fuzzy dates
       → for each new Decision: candidates = store.history(topicKey) ∪ same-owner/±14d actions
       → if candidates: LLM reconcile → Conflict? → put superseded + put conflicted
       → render items + CONFLICT stamps
       → user confirms → provider.createTask → mark synced (store write)
       → reminders scan / digest aggregation (reads only)
```

## 3. Conflict detection — the part that makes it a system

Two-stage, deliberately. Pure-LLM "compare every new decision against every stored decision" is slow, expensive,
nondeterministic, and impossible to demo reliably.

**Stage 1 — deterministic prefilter** (`lib/conflict.ts`, pure, unit-tested)

```ts
export function candidates(newD: Decision, all: Fact<Decision>[]): Decision[] {
  return all.filter(f => f.value.status === 'active' && f.sourceId !== newD.meetingId && (
    f.value.topicKey === newD.topicKey                    // exact topic match — primary signal
    || overlap(tokenSet(f.value.topicKey), tokenSet(newD.topicKey)) >= 0.5
    || sameOwnerAndNearbyDate(f.value, newD)              // owner + due date within 14 days
  ));
}
```

Topic-key quality is therefore the whole game: the extraction prompt must force a canonical slug and a `topicAliases`
list so `pricing.launch-date` and "the go-live date for the new tiers" collapse together. Give the extractor 5 few-shot
topic examples and hold it to a controlled vocabulary it reuses from previously seen keys (pass the current key list
into the prompt — cheap, and it self-normalises over the demo's two meetings).

**Stage 2 — LLM reconcile** (`meetings.reconcile`, one call per candidate pair, ≤3 pairs per demo)
Returns `{contradicts: boolean, kind, explanation, recommendation, confidence}`. Only `confidence >= 0.6` renders a
stamp; anything lower becomes a quiet "worth checking" line, so the UI never looks wrong on camera.

**Outcome is a state transition, not a toast:** the older decision goes `superseded`/`conflicted`, the new one is
written with `supersedes`, and `/meetings/memory` shows both with a hairline between them. That screen is the evidence.

## 4. Confirmation state machine

`open → confirmed → posting → synced | failed`. `provider.createTask` is only callable from the `confirmed` transition,
enforced in `lib/tasks.ts` rather than in the UI, so an agent-written component cannot bypass it (tests assert it).
`/api/tasks/post` rejects any `actionId` whose stored status is not `confirmed`. The modal preview shows the exact
payload — title, owner name, due date in the provider's syntax — before the call.

## 5. Provider contracts

```ts
interface TaskProvider {
  id: 'local' | 'todoist' | 'notion';
  ready(): boolean;                     // false ⇒ UI shows "not configured", never a fake success
  preview(a: Action): TaskPreview;      // what the human confirms
  createTask(a: Action): Promise<{ externalId: string; url: string }>;
}
```

| Provider | Setup | Notes / gotchas |
|---|---|---|
| `todoist` (primary) | `TODOIST_TOKEN`, `POST https://api.todoist.com/rest/v2/tasks` `{content, due_string, project_id}` | free plan has no assignee — encode owner as `[Priya] …` in the content string and say so in the README; `due_string` accepts natural language which is a nice demo detail |
| `notion` (fallback) | `NOTION_KEY` + `NOTION_DB_ID`, `POST /databases/{id}/pages` with property payload | property names must match the database exactly — verify schema with one read call before writing; needs a shared page |
| `local` (always) | none | own tasks view in-app; honest label "local tracker"; keeps ladder items 1–2 intact |

Decide the provider at P0 and commit it in the log. Switching providers at H5 is how a demo dies.

## 6. Reminders and digest (ladder 4–5, read-only)

`lib/reminders.ts` — pure `dueWithin(actions, now, horizonH=24)` → banner listing overdue/today/tomorrow. For the
demo, a hidden `?now=2026-11-02` override lets the video show a firing reminder without waiting for a real deadline;
label it in the README as a demo affordance rather than hiding it. `lib/digest.ts` — groups the week's actions and
decisions per `ownerId` and calls `meetings.digest` for a 3-sentence summary plus the item list; email send is
skipped unless a key exists, and the UI says "email preview" instead of pretending to send.

## 7. Screens

| Route | Screen | Ladder |
|---|---|---|
| `/meetings` | meeting list + upload; each card shows extracted counts and any open conflict | 1 |
| `/meetings/[id]` | transcript with speaker gutter on the left; extraction chips inline; **CONFLICT stamps** | 1 |
| `/meetings/[id]/items` | decisions / actions tables, confirm buttons, provenance footer | 2 |
| `/meetings/memory` | all decisions by topic with history versions — the money screen | 1 |
| `/meetings/digest` | per-person weekly digest | 5 |
| banner (global) | reminder strip | 4 |

Design tokens: [../docs/ARCHITECTURE.md §8](../docs/ARCHITECTURE.md) — dossier/ledger. Serif body, mono meta and
timestamps, paper ground, red rotated stamp for conflicts, square-cut buttons, 1px rules. No chat surface anywhere.

## 8. Failure modes and what the UI does

| Failure | UI response |
|---|---|
| LLM invalid JSON | one retry ⇒ mock ⇒ "showing cached extraction" badge |
| Provider `ready()` false | "tracker not connected" + local provider offered; no success toast |
| `createTask` throws | status `failed`, payload visible, retry button |
| Transcript without speaker labels | inline "add speaker" affordance; attribution stays honest |
| Zero conflicts found | memory view still shows the topic history; never claim a conflict for drama |

## 9. Files owned by this track

`src/products/meetings/**`, `src/platform/prompts/meetings.*.md`, `src/platform/mocks/meetings.*.json`,
`content/meetings/**`, `src/styles/tokens-meetings.css`, `src/app/(meetings)/**`.
`platform/llm`, `platform/store`, `platform/ui` are shared — request changes, don't edit (AGENTS.md §2).
