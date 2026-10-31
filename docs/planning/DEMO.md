# PS 03 demo — 3 minutes

One continuous screen recording, no cuts, cursor moves slow, narration dictated in Wispr over the good take.
Rehearse in `MOCK_LLM=1` (three clean passes), then record the real version with the live model. Seed first:
`npm run seed` resets the store to the known fixture state so every take is identical.

| Time | Screen | Narration beats (dictate, don't read verbatim) |
|---|---|---|
| 0:00–0:20 | `/meetings`, two meetings listed, memory empty | "Meeting notes get lost. This takes a transcript and turns it into decisions, owners, and dates that stay in memory." |
| 0:20–0:55 | open `m1-standing`, transcript with speaker gutter; extraction chips appear; click one chip → jumps to segment | "Priya's launch date, the owner, and the due date come from the transcript itself — click a record and it points at the sentence it came from." |
| 0:55–1:40 | load `m2-reversal` → **red CONFLICT stamp** → expand it | Pause here. Slow. "Last week the team decided the launch is 8 November. Today Karan said it moves to 22 November. The agent didn't just summarise this meeting — it remembered the previous one and flagged the reversal." Let the quoted lines sit on screen for four seconds. |
| 1:40–2:05 | `/meetings/memory`, old decision struck under the new one | "This is the memory: every topic with its history, dated, with provenance. Nothing here was typed by hand." |
| 2:05–2:35 | items table → Approve → modal preview of payload → confirm → open the real tracker tab | "Nothing gets posted unless a human confirms. This is the exact payload. Approve — and the task is now in the actual tracker, with its due date." |
| 2:35–2:50 | reminder banner (via `?now=2026-11-02`) + `/meetings/digest` for Priya | "Reminders before deadlines, and a weekly digest per person built from the same store." Mention the date override plainly — honesty reads as polish, hiding it reads as a trick. |
| 2:50–3:00 | `/meetings` with conflict count badge | Close on the result, not a logo. "Two meetings in, it already knows what the team changed its mind about." |

## Shot requirements

- Real tracker tab visible with the created task (ladder 3, kill check 4). If the API died, `local` provider view,
  labelled in-narration as the local tracker — the confirmation flow still gets shown.
- The conflict stamp on screen ≥4 seconds. This is the single most valuable frame in the video.
- One provenance footer visible when a record is opened.
- The URL bar visible once at the start (deployed URL, not localhost).
- No chat box anywhere in frame. No other product visible. Do not show `/tutor` — separate submission, separate video,
  narrated under this submission's account for usage attribution.

## Before recording (15-minute gate)

1. `npm run seed && npm run dev`, fresh browser profile, zoom 100%, cursor large, notifications off, clock hidden.
2. Hide anything not on the golden path: comment out nav links to unshipped screens (they must not appear as dead links).
3. `MOCK_LLM=1` pass for timing, then live pass. If live is slower than 4 seconds per model call, pre-warm the
   extraction before recording so the click feels instant.
4. Record 20 seconds longer than needed at both ends; trim, don't re-shoot.

## Submission bundle

- Deployed URL (`/meetings`) verified from that clean profile.
- GitHub repo: `README.md` adapted from [README.md](README.md) + [ARCHITECTURE.md](ARCHITECTURE.md) §1–3 —
  a judge should understand the conflict design in 90 seconds. Include the `MOCK_LLM` disclosure, `.env.example`,
  and a "run in 3 commands" block.
- Video file named `ps03-meetings-demo.mp4`.
- All three dictated: README, commit messages, submission email.

## Cut order if you're out of time

Reminders → digest → extra polish → local-only provider. Never cut the conflict card, never cut the confirmation gate.
