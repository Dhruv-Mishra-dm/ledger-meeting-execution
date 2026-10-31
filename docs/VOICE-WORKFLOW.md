# Voice workflow (Wispr Flow)

The official page sets two voice requirements for every team. Voice usage is 20% of the score.

## A. Build it by voice

The team dictates prompts, specs and fixes into its AI builder (Claude Code) with **Wispr Flow** instead of typing.

How to make it count and show it:
- Keep Wispr Flow on while working in Claude Code. Dictate every prompt, bug report and follow-up ("the conflict card should quote both meetings…").
- Dictate commit messages, the README edits, the demo narration and the submission text.
- Usage is attributed by account. Each person dictates under their own Wispr account.
- Do not edit screenshots (the rules penalise edited screenshots).

There is no Wispr Flow API. This application does **not** claim a direct Wispr integration. Wispr Flow works as a system-wide
dictation layer that types into any text field, including Claude Code and this app.

## B. Make the product work with voice

**The product's main input is speech captured through Wispr Flow.**

- **Capture a meeting** opens on **Speak with Wispr Flow**. It is a large dictation composer with the cursor already in it. Press the Wispr
  shortcut and talk; Wispr types the cleaned speech into the box.
- *Dictated by* records who spoke. Unlabelled dictated speech is attributed to that person, so no identity is invented. If the speaker says
  "Rahul: …" or "Priya: …", those labels are kept as separate speakers.
- Dictated paragraphs are split into sentences, so evidence can point at the exact sentence.

### What the engine understands in natural speech

| Speech pattern | Example | Result |
|---|---|---|
| Filler words, stutters | "um, so, uh, the the launch…" | removed before analysis; the quote keeps the original words |
| Ellipses and dashes as pauses | "migration… actually" | treated as sentence breaks |
| **Self-correction** | "let's use MongoDB… actually, let's not use MongoDB anymore. We decided to move to PostgreSQL." | one decision, **PostgreSQL**, with `previous: MongoDB` and a note; listed under "Self-corrections understood" |
| Change of mind on a task | "Rahul will do the docs… actually Priya will take the docs" | one task; owner corrected, with a note |
| Pronoun follow-up | "He should finish it by Friday." | adds the deadline to that person's previous task (with a note); a pronoun that starts a new task ("He will…") gives an owner marked **inferred** |
| Relative dates | "by Friday", "tomorrow", "next week" | resolved from the meeting date; marked **relative** or **inferred**, with the original words kept |
| Request, then acceptance | "Priya, can you update the docs?" → "Sure, I'll do it." | owner **inferred** until accepted, then **explicit** |
| Ambiguous owner | "Rahul or Karan will look into it" | left **unassigned**, with a note |
| Suggestions and questions | "Maybe we should switch to Vue?" | not recorded as a decision |
| Repetition | the same decision said twice | merged; evidence lists both sentences |
| Digressions and small talk | "Great, thanks everyone." | ignored |

With `AI_PROVIDER=openai` (Gemini or another model), the same rules are given to the model in the prompt, and the output is then grounded
against the transcript (`ai/openai_compat.py`).

## Optional enhancement: browser microphone

In Chrome and Edge, a **Browser mic (optional)** button appears. It uses the Web Speech API and appends the recognised text. It is a fallback only;
Wispr Flow is the intended input.

## Demonstrating it (30 seconds)

1. Open **New meeting** in the *Helios Analytics* project. The cursor is in the composer.
2. Press the Wispr Flow shortcut and say, naturally, with hesitations:
   > "Okay so, um, quick sync. Rahul will handle the database migration… actually, let's not use MongoDB anymore. We decided to move to
   > PostgreSQL. He should finish it by Friday. Priya, can you update the API docs once the migration is done?"
3. Save. Point at: one PostgreSQL decision (changed from MongoDB) under "Self-corrections understood"; Rahul's task, with Friday from the follow-up
   sentence resolved to a date (relative); Priya's task inferred (asked, not yet accepted), depending on "the migration"; and every item quoting the sentence it came from.
4. Say: "Nothing here is posted until a manager approves it."

If Wispr is unavailable at demo time, **Insert sample** fills the same text. Say that you used it.
