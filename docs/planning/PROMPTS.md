# PS 03 prompts

**RUNTIME** = ships in `src/platform/prompts/`, called through `platform/llm` with a schema, mocked in
`src/platform/mocks/`. **BUILD** = pasted to your coding agent; dictated, not typed (D-010).

---

## RUNTIME 1 · `meetings.extract`

System:
> You convert a labelled meeting transcript into structured work records. You never invent owners, dates, or
> statements. Every record must point at the transcript segments it came from. Reply with JSON only.

User template:
```
Meeting: {{title}} · {{occurredAt}} · participants: {{participantNames}}
Known topic keys (reuse one when the subject matches; otherwise create a new dotted slug):
{{existingTopicKeys}}

Transcript (index · speaker · text):
{{segments}}

Return:
{
  "decisions": [{ "statement": "<≤140 chars, declarative>", "topicKey": "<slug>",
                  "topicAliases": ["<phrases used in the meeting>"], "ownerIds": ["…"],
                  "evidence": [<segment indexes>], "confidence": 0.0-1.0 }],
  "actions":   [{ "text": "<single observable task>", "ownerId": "<id>",
                  "topicKey": "<slug>",
                  "due": { "raw": "<verbatim phrase or null>", "iso": "<YYYY-MM-DD or null>",
                           "confidence": "explicit" | "inferred" },
                  "evidence": [<segment indexes>] }]
}
Rules:
1. A decision is something settled; an action is something someone must do. Do not duplicate.
2. If an owner is not named in the transcript, use the speaker who took it on; if nobody did, omit the record.
3. Never guess a date. "next week" ⇒ raw verbatim, iso = best resolution from {{occurredAt}},
   confidence = "inferred".
4. Reuse a known topic key whenever the subject is the same, even if the words differ. This is what lets the
   system notice contradictions across meetings.
5. Ignore small talk, scheduling logistics, and status reporting with no decision content.
```
Few-shot: include the `m1-standing` fixture's 6 segments → 2 decisions / 3 actions pair, verbatim, once.

## RUNTIME 2 · `meetings.reconcile`

> You compare two statements about the same topic made in two different meetings. Decide whether the newer one
> contradicts the older one, and say what a human should confirm. Be precise; do not upgrade agreement into conflict.
> A restatement, an elaboration, or a status update is NOT a contradiction. JSON only.

```
Older ({{olderMeetingTitle}}, {{olderOccurredAt}}): "{{olderStatement}}"   context: {{olderEvidence}}
Newer ({{newerMeetingTitle}}, {{newerOccurredAt}}): "{{newerStatement}}"   context: {{newerEvidence}}

Return { "contradicts": bool, "kind": "reversal" | "deadline_shift" | "owner_change" | "scope_change" | "none",
         "explanation": "<one sentence quoting a phrase from each>",
         "recommendation": "<what to ask whom>", "confidence": 0.0-1.0 }
```
Rendering rule lives in code, not the prompt: `confidence < 0.6` shows a quiet note, never the red stamp.

## RUNTIME 3 · `meetings.digest`

> Write a weekly summary for one person from records already given. Do not add facts. Two or three sentences, plain
> business English, no emoji, no exclamation marks, then the lists are rendered separately by the app.

```
Person: {{name}} · week of {{weekStart}}
Decisions they own: {{decisions}}   Actions completed/open: {{actions}}   Conflicts touching them: {{conflicts}}
Return { "summary": "<2-3 sentences>", "attention": ["<up to 3 short flags>"] }
```

---

## BUILD prompts (one per phase — paste into your agent session)

**M1 extraction**
> OBJECTIVE: implement `src/products/meetings/lib/extract.ts` so the m1 fixture yields ≥2 decisions and ≥3 actions
> with owners, topicKeys and evidence segment indexes.
> CONTEXT: read AGENTS.md, docs/STATE.md, ps-03-meeting-execution/ARCHITECTURE.md §1 and PROMPTS.md RUNTIME 1.
> Use `platform/llm` and `platform/store` exactly as typed in docs/ARCHITECTURE.md §4–5. Do not touch
> `src/products/tutor/**`.
> CONSTRAINTS: files you may create are `lib/ingest.ts`, `lib/extract.ts`, `content/meetings/m1-standing.json`,
> `src/platform/prompts/meetings.extract.md`, `src/platform/mocks/meetings.extract.json`. No new dependencies.
> No prompt strings in components. `MOCK_LLM=1` must work with no network.
> DONE WHEN: `npm test` green and `/meetings/m1-standing` shows chips linked to segments.
> REPORT: 3 lines.

**M2 conflict**
> Same CONTEXT/CONSTRAINTS shape. Objective: pure `candidates()` in `lib/conflict.ts` plus `lib/reconcile.ts`; unit
> tests must prove the reversal pair is a candidate and an unrelated active decision is not. Do not put the LLM call
> inside `conflict.ts`. Do not render a conflict stamp anywhere except `ConflictStamp.tsx`.
> DONE WHEN: loading m2-reversal produces the stamp citing both meetings with dates, and `/meetings/memory` shows the
> superseded decision.

**M3 confirmation + provider**
> Objective: `lib/tasks.ts` transition function (pure) + `/api/tasks/post` route that reads stored status and refuses
> anything not `confirmed`, plus `providers/local.ts` and `providers/todoist.ts` behind `TaskProvider`.
> Constraints: `createTask` unreachable from `open`; UI may not call the provider directly.
> DONE WHEN: tests prove the gate; one real task exists in Todoist from the Approve button.

**M4/M5** reminders and digest: state the pure function signature first, then the UI. Both read-only over the store.

## What to reject if an agent produces it

A chat interface. A "Summarize meeting" button that returns prose instead of typed records. Conflict detection that
calls the model on every decision pair. A success toast shown before the provider resolves. Hardcoded demo strings
rendered as if extracted — unless clearly behind `MOCK_LLM=1`, which the README must disclose. A UI that looks like the
tutor product — check against ARCHITECTURE §8.
