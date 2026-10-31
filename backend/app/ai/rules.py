"""Deterministic meeting-intelligence engine ("demo mode").

This is NOT an LLM and is labelled as such everywhere in the UI. It is a rule-based extractor that reads the
actual transcript, so every meeting yields its own output (Meeting 2 can never receive Meeting 1's result).
It handles what dictated speech contains: filler words, stutters, ellipses, self-corrections
("actually, let's not use MongoDB"), pronoun follow-ups ("He should finish it by Friday") and requests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .base import DecisionView, ExtractedAction, ExtractedDecision, ExtractionContext, ExtractionResult, Judgement
from .dates import DateMention, find_dates, find_deadline
from .text import (
    AMOUNT, AMOUNT_TOPICS, DATE_TOPICS, GENERIC_VERBS, STOP, clean_speech, find_choices, split_sentences, tokens,
)

STRONG_CUE = re.compile(r"\b(decided|agreed|final decision|decision is|it'?s official|approved|confirmed)\b", re.I)
DECISION_CUE = re.compile(
    r"\b(decided|agreed|final decision|decision is|approved|confirmed|going forward|"
    r"let'?s (?:go with|use|move to|switch to|stick with|keep|replace|migrate to|standardi[sz]e on)|"
    r"we(?:'ll| will| are going to|'re going to|'re| are| shall)? (?:go(?:ing)? with|use|using|move to|moving to|switch(?:ing)? to|"
    r"stick(?:ing)? with|stay(?:ing)? (?:with|on)|keep(?:ing)? using|replace|replacing|migrate|migrating) |"
    r"is (?:now |still )?(?:scheduled|confirmed|set|fixed|locked) (?:for|on|at)|"
    r"(?:is|has been|was|will be|are|have been) (?:now )?(?:postponed|moved|pushed|delayed|rescheduled|pulled in|brought forward|slipping|slipped)|"
    r"(?:slips|slipped|moves|moved) to)\b",
    re.I,
)
HYPOTHETICAL = re.compile(
    r"\b(maybe|perhaps|should we|could we|shall we|what if|might|i suggest|suggestion|propose|proposal|thinking about|"
    r"considering|not sure|do we|would it|we could|option|wondering|how about|if we)\b",
    re.I,
)
HEDGE = re.compile(r"\b(probably|i think|i guess|tentatively|for now)\b", re.I)
NEGATION = re.compile(r"\b(let'?s not|not (?:going to )?use|no longer|don'?t (?:use|go with)|drop(?:ping)?|stop using|scrap|move away from|instead of|rather than|not)\b", re.I)
CORRECTION_CUE = re.compile(r"\b(actually|scratch that|no wait|wait,? no|on second thought|change of plan|correction|instead|i mean)\b", re.I)
AFFIRMATIVE = re.compile(r"^\W*(sure|yes|yeah|yep|ok|okay|will do|on it|got it|absolutely|definitely|no problem|i can|i will|i'll)\b", re.I)
STOP_CAPS = {
    "We", "I", "It", "This", "That", "They", "He", "She", "Everyone", "Someone", "Somebody", "Nobody", "The", "Then", "So",
    "And", "But", "Also", "Okay", "Ok", "Alright", "Now", "Today", "Tomorrow", "Next", "Who", "What", "Which", "There",
    "Here", "You", "Yes", "No", "Well", "Great", "Good", "Thanks", "Actually", "Maybe", "If", "When", "Once", "After",
    "Before", "Our", "My", "Your", "Let", "Let's", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "Production", "Launch", "Everything", "Nothing", "One", "Both", "Each", "Either", "None",
}
DEPENDENCY = re.compile(
    r"\b(?:after|once|when)\s+(?P<a>[^,.;]+?)\s+(?:is|are|has been|have been|gets?)\s+(?:done|finished|complete|completed|ready|merged|approved|signed off)\b"
    r"|\b(?:depends on|dependent on|blocked by|waiting on|waiting for)\s+(?P<b>[^,.;]+)",
    re.I,
)
FOLLOW_UP = re.compile(r"^(?:finish|complete|do|deliver|wrap up|get|have|ship|close)\s+(?:it|that|this|them)\b", re.I)
OWNERSHIP_MODALS = {"responsible for", "in charge of", "owns", "own", "take care of", "takes care of"}


def _fmt(d: date | str | None) -> str:
    if d is None:
        return "unspecified"
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


@dataclass
class _Dec:
    topic: str
    statement: str
    value: str | None
    value_kind: str
    previous_value: str | None
    speaker: str | None
    evidence: list[int]
    excerpt: str
    confidence: float
    notes: list[str] = field(default_factory=list)
    alive: bool = True


@dataclass
class _Act:
    title: str
    description: str
    owner: str | None
    owner_origin: str
    deadline: DateMention | None
    dependencies: list[str]
    decision: _Dec | None
    speaker: str | None
    evidence: list[int]
    excerpt: str
    confidence: float
    notes: list[str] = field(default_factory=list)
    request: bool = False


class _Extractor:
    def __init__(self, ctx: ExtractionContext):
        self.ctx = ctx
        self.ref = ctx.meeting_date
        people = {p.strip() for p in [*ctx.known_people, *ctx.participants] if p and p.strip()}
        people |= {s.speaker for s in ctx.segments if s.speaker}
        # Allow first names to match ("Rahul" for "Rahul Mehta").
        names = set(people) | {p.split()[0] for p in people}
        self.names = sorted((n for n in names if n and n[0].isupper()), key=len, reverse=True)
        self.name_alt = "|".join(re.escape(n) for n in self.names) or r"(?!x)x"
        self.decisions: list[_Dec] = []
        self.actions: list[_Act] = []
        self.retracted: dict[str, str] = {}
        self.last_person: str | None = None
        self.corrections: list[str] = []
        self.warnings: list[str] = []
        self.segment_by_idx = {s.idx: s for s in ctx.segments}

    # ---------------------------------------------------------------- main loop
    def run(self) -> ExtractionResult:
        for seg in self.ctx.segments:
            for raw in split_sentences(seg.text):
                s = clean_speech(raw)
                if len(s) < 4:
                    continue
                dec = self._decision(seg, raw.strip(), s)
                for clause in self._clauses(s):
                    self._action(seg, raw.strip(), clause, dec)
                self._remember_people(s)
        self._confirm_requests()
        self._link_late_decisions()
        return self._result()

    def _clauses(self, s: str) -> list[str]:
        # "Rahul will do X and Priya will do Y" -> two clauses, so each person gets their own task.
        parts = re.split(rf",?\s+(?:and|while|then|also)\s+(?=(?:{self.name_alt})\b)", s)
        return [p for p in parts if p.strip()]

    def _remember_people(self, s: str) -> None:
        for m in re.finditer(rf"\b({self.name_alt})\b", s):
            self.last_person = m.group(1)

    # ---------------------------------------------------------------- decisions
    def _decision(self, seg, raw: str, s: str) -> _Dec | None:
        low = s.lower()
        question = s.rstrip().endswith("?")
        strong = bool(STRONG_CUE.search(low))
        cue = bool(DECISION_CUE.search(low))
        choices = find_choices(s)
        if question or (HYPOTHETICAL.search(low) and not strong):
            return None  # a suggestion or question is not a decision

        negated = self._negated_values(s, choices)
        if choices and negated and all(v in negated for _, v, _ in choices):
            # Pure retraction: "let's not use MongoDB anymore". Remember it and drop any in-meeting decision for it.
            for cat, value, _ in choices:
                self.retracted[cat] = value
                for d in self.decisions:
                    if d.alive and d.topic == cat and d.value == value:
                        d.alive = False
                        self.corrections.append(f"{seg.speaker or 'A speaker'} withdrew '{d.statement}' later in the meeting.")
            return None
        if not cue:
            return None

        topic: str | None = None
        value: str | None = None
        kind = "text"
        previous: str | None = None
        statement = ""

        if choices:
            chosen, previous = self._choose(s, choices, negated)
            if not chosen:
                return None
            topic, value, kind = chosen[0], chosen[1], "choice"
            statement = f"Use {value} as the {topic}"
            withdrawn = self.retracted.pop(topic, None)
            if withdrawn and not previous:
                previous = withdrawn
                self.corrections.append(f"{seg.speaker or 'A speaker'} withdrew {withdrawn} and decided {value} instead; only {value} is recorded.")
        else:
            dates = find_dates(s, self.ref)
            date_topic = next((t for t, p in DATE_TOPICS if p.search(s)), None)
            amount_topic = next((t for t, p in AMOUNT_TOPICS if p.search(s)), None)
            if date_topic and dates:
                topic, kind = date_topic, "date"
                value = dates[-1].value.isoformat()
                if len(dates) >= 2 and dates[0].value != dates[-1].value:
                    previous = dates[0].value.isoformat()
                statement = f"{_cap(topic)} is {_fmt(value)}"
            elif amount_topic and AMOUNT.search(s):
                topic, kind = amount_topic, "amount"
                value = AMOUNT.findall(s)[-1].strip()
                statement = f"{_cap(topic)} is {value}"
            elif strong:
                words = [w for w in re.findall(r"[a-z][a-z0-9-]+", low) if w not in STOP and w not in GENERIC_VERBS]
                if len(words) < 2:
                    return None
                topic = " ".join(words[:3])
                statement = _cap(s.rstrip(".")) if len(s) <= 240 else _cap(s[:237]) + "..."
            else:
                return None

        conf = 0.92 if strong else 0.8
        if HEDGE.search(low):
            conf -= 0.15
        dec = _Dec(topic, statement, value, kind, previous, seg.speaker, [seg.idx], raw, round(conf, 2))

        # Self-correction inside the meeting: the later statement on the same topic wins; history is noted.
        for earlier in self.decisions:
            if earlier.alive and earlier.topic == topic:
                if earlier.value == value:
                    earlier.evidence.append(seg.idx)  # restated, not a new decision
                    return earlier
                earlier.alive = False
                dec.previous_value = dec.previous_value or earlier.value
                note = f"Self-corrected in this meeting: earlier said '{earlier.statement}'."
                dec.notes.append(note)
                self.corrections.append(f"{seg.speaker or 'A speaker'} corrected '{earlier.statement}' to '{statement}'.")
        if previous and kind == "choice" and not dec.notes:
            dec.notes.append(f"Speaker explicitly replaced {previous} with {value}.")
        self.decisions.append(dec)
        return dec

    def _negated_values(self, s: str, choices) -> set[str]:
        out: set[str] = set()
        low = s.lower()
        for m in NEGATION.finditer(low):
            window = low[m.end(): m.end() + 25]
            for _, value, pos in choices:
                if m.end() <= pos <= m.end() + 25 and value.lower()[:4] in window:
                    out.add(value)
        for _, value, pos in choices:
            if re.search(rf"{re.escape(value.lower()[:5])}\w*\s+(?:anymore|any more)", low):
                out.add(value)
        return out

    def _choose(self, s: str, choices, negated: set[str]) -> tuple[tuple[str, str] | None, str | None]:
        low = s.lower()
        previous = None
        m = re.search(r"replac\w*\s+(.+?)\s+with\s+(.+)", low) or re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)", low)
        if m:
            prev_hits = find_choices(m.group(1))
            new_hits = find_choices(m.group(2))
            if prev_hits and new_hits:
                return (new_hits[0][0], new_hits[0][1]), prev_hits[0][1]
        m = re.search(r"\b(?:instead of|rather than|away from)\s+(.+)", low)
        if m:
            prev_hits = find_choices(m.group(1))
            if prev_hits:
                previous = prev_hits[0][1]
        options = [(c, v) for c, v, _ in choices if v not in negated and v != previous]
        return (options[-1] if options else None), previous

    # ---------------------------------------------------------------- actions
    def _action(self, seg, raw: str, s: str, dec: _Dec | None) -> None:
        request = re.search(rf"\b(?P<who>{self.name_alt}),?\s+(?:can|could|would) you\s+(?P<what>[^?]+)", s) or re.search(
            rf"\b(?:can|could) (?P<who>{self.name_alt})\s+(?P<what>[^?]+)\?", s
        )
        if s.rstrip().endswith("?") and not request:
            return
        ambiguous = re.search(r"\b([A-Z][a-z]+)\s+or\s+([A-Z][a-z]+)\b(?=\s+(?:will|should|needs?|has|must|can|'ll|is))", s)
        who_re = rf"(?P<who>{self.name_alt}|[A-Z][a-z]+|I|he|she|they|we|someone|somebody|He|She|They|We|Someone|Somebody)"
        modal_re = (
            r"(?P<modal>'ll|\s+will(?:\s+now)?|\s+is going to|\s+are going to|\s+should|\s+needs? to|\s+has to|\s+have to|"
            r"\s+must|\s+is (?:now )?responsible for|\s+(?:is|are) (?:now )?in charge of|\s+owns|\s+will own|\s+takes? care of|\s+can take)"
        )
        m = None if request else re.search(rf"\b{who_re}{modal_re}\s+(?P<what>.+)", s)
        if not (m or request):
            return
        hit = request or m
        who = hit.group("who")
        what = hit.group("what").strip().rstrip(".!?")
        modal = (m.group("modal").strip().lower() if m else "")
        if who[0].isupper() and who not in self.names and who in STOP_CAPS:
            who = who.lower()
        if who.lower() not in {"i", "he", "she", "they", "we", "someone", "somebody"} and who[0].islower():
            return  # "The docs will live in the wiki" is not a task with an owner called "The"

        owner, origin, conf, notes = None, "unassigned", 0.8, []
        wl = who.lower()
        if request:
            owner, origin, conf = who, "inferred", 0.6
            notes.append("Owner was asked in the meeting; marked inferred until they accept.")
        elif ambiguous and ambiguous.end() <= hit.start("modal") + 1:
            notes.append(f"Ambiguous owner: '{ambiguous.group(0)}'. Left unassigned for review.")
            conf = 0.5
        elif wl == "i":
            if seg.speaker:
                owner, origin = seg.speaker, "explicit"
            else:
                notes.append("Committed by an unidentified speaker.")
        elif wl in {"he", "she"}:
            if self.last_person:
                owner, origin, conf = self.last_person, "inferred", 0.65
                notes.append(f"'{who}' resolved to {self.last_person} (last person mentioned).")
            else:
                notes.append(f"Unclear who '{who}' refers to.")
                conf = 0.5
        elif wl in {"they", "we", "someone", "somebody"}:
            if wl == "we" and (dec is not None or re.match(r"(use|go with|move|switch|stick|stay|keep using|replace|migrate to|launch|be|have)\b", what, re.I)):
                return  # "we will use X" is a decision, not a task
            notes.append("No individual owner was named.")
            conf = 0.5
        else:
            owner, origin = who, "explicit"

        # Pronoun follow-up: "He should finish it by Friday" adds a deadline to the previous task.
        if FOLLOW_UP.match(what) and self.actions:
            target = next((a for a in reversed(self.actions) if owner and a.owner == owner), self.actions[-1])
            dl = find_deadline(s, self.ref)
            if dl:
                target.deadline = dl
                target.evidence.append(seg.idx)
                target.notes = [n for n in target.notes if n != "No deadline stated."]
                target.notes.append(f"Deadline from follow-up sentence: \"{raw}\".")
            return

        if re.match(r"be (?:on leave|out|away|travel|off)\b", what, re.I):
            return
        deadline = find_deadline(what, self.ref) or find_deadline(s, self.ref)
        deps = [(d.group("a") or d.group("b")).strip() for d in DEPENDENCY.finditer(s)]
        title = what
        if deadline:
            title = re.sub(rf"\s*,?\s*(?:by|before|due(?: on| by)?|until|no later than|on|for)?\s*{re.escape(deadline.raw)}\b", "", title, flags=re.I)
        title = DEPENDENCY.sub("", title)
        title = re.sub(r"\s*,?\s*(?:as well|too|asap|please|right away)\s*$", "", title, flags=re.I).strip(" ,.-")
        if any(k in modal for k in OWNERSHIP_MODALS):
            title = f"Handle {title}"
        if len(tokens(title)) == 0:
            return
        title = _cap(title)[:160]

        related = dec or self._related_decision(f"{title} {s}")
        if deadline is None:
            notes.append("No deadline stated.")
        act = _Act(title, _cap(s), owner, origin, deadline, deps, related, seg.speaker, [seg.idx], raw, round(conf + (0.1 if deadline and owner else 0), 2), notes, bool(request))

        # Two people discussing the same task, or a restatement: merge instead of duplicating.
        from .text import same_task

        for prev in self.actions:
            if same_task(prev.title, act.title):
                if prev.owner and act.owner and prev.owner != act.owner:
                    reason = "corrected" if CORRECTION_CUE.search(s) else "reassigned"
                    prev.notes.append(f"Owner {reason} in the meeting from {prev.owner} to {act.owner}.")
                    self.corrections.append(f"Task '{prev.title}' {reason} from {prev.owner} to {act.owner}.")
                    prev.owner, prev.owner_origin = act.owner, act.owner_origin
                if act.deadline and (not prev.deadline or prev.deadline.value != act.deadline.value):
                    if prev.deadline:
                        prev.notes.append(f"Deadline restated in the meeting: {prev.deadline.raw} -> {act.deadline.raw}.")
                    prev.deadline = act.deadline
                prev.owner = prev.owner or act.owner
                prev.evidence.append(seg.idx)
                return
        self.actions.append(act)

    def _related_decision(self, text: str) -> _Dec | None:
        t = tokens(text)
        for d in reversed(self.decisions):
            if not d.alive:
                continue
            if (d.value and d.value.lower() in text.lower()) or (tokens(d.topic) & t):
                return d
        return None

    def _confirm_requests(self) -> None:
        for a in self.actions:
            if not a.request:
                continue
            nxt = self.segment_by_idx.get(a.evidence[0] + 1)
            if nxt and nxt.speaker == a.owner and AFFIRMATIVE.search(nxt.text):
                a.owner_origin, a.confidence = "explicit", 0.85
                a.evidence.append(nxt.idx)
                reply = split_sentences(nxt.text)[0][:80]
                a.notes = [n for n in a.notes if not n.startswith("Owner was asked")] + [f"{a.owner} accepted: \"{reply}\""]

    def _link_late_decisions(self) -> None:
        # A task mentioned before its decision ("Rahul will migrate... we decided PostgreSQL") still links to it.
        for a in self.actions:
            if a.decision is None or not a.decision.alive:
                a.decision = self._related_decision(f"{a.title} {a.description}")

    # ---------------------------------------------------------------- output
    def _result(self) -> ExtractionResult:
        live = [d for d in self.decisions if d.alive]
        index = {id(d): i for i, d in enumerate(live)}
        decisions = [
            ExtractedDecision(
                statement=d.statement, topic=d.topic, value=d.value, value_kind=d.value_kind, previous_value=d.previous_value,
                speaker=d.speaker, evidence_idx=sorted(set(d.evidence)), evidence_excerpt=d.excerpt, confidence=d.confidence,
                origin="explicit", notes=" ".join(d.notes) or None,
            )
            for d in live
        ]
        actions = []
        for a in self.actions:
            dl = a.deadline
            actions.append(ExtractedAction(
                title=a.title, description=a.description, owner=a.owner, owner_origin=a.owner_origin if a.owner else "unassigned",
                deadline=dl.value if dl else None, deadline_raw=dl.raw if dl else None,
                deadline_origin=dl.origin if dl else "unspecified", dependencies=a.dependencies,
                related_decision=index.get(id(a.decision)) if a.decision else None, speaker=a.speaker,
                evidence_idx=sorted(set(a.evidence)), evidence_excerpt=a.excerpt,
                confidence=min(a.confidence, 0.95), notes=" ".join(a.notes) or None,
            ))
        if not decisions and not actions:
            self.warnings.append("No decisions or action items were found in this transcript.")
        return ExtractionResult(decisions=decisions, actions=actions, corrections=self.corrections, warnings=self.warnings)


def rules_judge(new: DecisionView, candidates: list[DecisionView]) -> list[Judgement]:
    """Deterministic relationship between a new decision and earlier live decisions."""
    out: list[Judgement] = []
    for old in candidates:
        if old.topic != new.topic:
            shared = tokens(old.statement) & tokens(new.statement)
            if len(shared) >= 2 and NEGATION.search(new.statement) and not NEGATION.search(old.statement):
                out.append(Judgement(
                    candidate_id=old.id, relation="scope", confidence=0.6,
                    explanation=f"'{new.meeting_title}' appears to reverse or remove something agreed in '{old.meeting_title}' ({_fmt(old.meeting_date)}): \"{old.statement}\".",
                    recommended_action="Check with the decision owner whether the earlier scope still applies.",
                ))
            continue
        if not (old.value and new.value):
            out.append(Judgement(candidate_id=old.id, relation="compatible", confidence=0.6, explanation="Same topic, no conflicting value stated."))
            continue
        if old.value.lower() == new.value.lower():
            out.append(Judgement(
                candidate_id=old.id, relation="compatible", confidence=0.95,
                explanation=f"Consistent with the decision from '{old.meeting_title}' ({_fmt(old.meeting_date)}): {old.value}.",
            ))
            continue
        if new.value_kind == "date":
            delta = (date.fromisoformat(new.value) - date.fromisoformat(old.value)).days
            direction = f"{abs(delta)} days later" if delta > 0 else f"{abs(delta)} days earlier"
            out.append(Judgement(
                candidate_id=old.id, relation="deadline_change", confidence=0.93,
                explanation=(
                    f"'{old.meeting_title}' ({_fmt(old.meeting_date)}) set the {new.topic} to {_fmt(old.value)}. "
                    f"'{new.meeting_title}' ({_fmt(new.meeting_date)}) sets it to {_fmt(new.value)}, {direction}."
                ),
                recommended_action=f"Confirm the new {new.topic} ({_fmt(new.value)}) and check that tasks due before it still make sense.",
            ))
            continue
        explicit = bool(new.previous_value and new.previous_value.lower() == old.value.lower())
        out.append(Judgement(
            candidate_id=old.id, relation="contradiction", confidence=0.97 if explicit else 0.9,
            explanation=(
                f"'{old.meeting_title}' ({_fmt(old.meeting_date)}) decided {old.value} for the {new.topic}. "
                f"'{new.meeting_title}' ({_fmt(new.meeting_date)}) decides {new.value}"
                + (f", explicitly replacing {old.value}." if explicit else ".")
            ),
            recommended_action=(
                f"Confirm whether {new.value} replaces {old.value}. Accepting keeps the {old.value} decision in history as superseded; "
                f"review any tasks that were planned around {old.value}."
            ),
        ))
    return out


class RulesEngine:
    name = "demo-rules"
    is_real_ai = False
    model = None

    def extract(self, ctx: ExtractionContext) -> ExtractionResult:
        return _Extractor(ctx).run()

    def judge(self, new: DecisionView, candidates: list[DecisionView]) -> list[Judgement]:
        return rules_judge(new, candidates)
