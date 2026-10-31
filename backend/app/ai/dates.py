"""Deterministic date understanding, resolved against the meeting date (never against "today")."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s*(\d{4}))?"

_ABS = [
    (re.compile(rf"\b(\d{{4}})-(\d{{2}})-(\d{{2}})\b"), "iso"),
    (re.compile(rf"\b{_MON}\s+{_DAY}\b{_YEAR}", re.I), "mdy"),
    (re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MON}\b{_YEAR}", re.I), "dmy"),
]
_REL = re.compile(
    r"\b(today|tonight|tomorrow|day after tomorrow|end of (?:the )?day|eod|end of (?:the |this )?week|"
    r"end of (?:the |this )?month|next week|(?:this |next |by |on )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"in (\d+|one|two|three|four|five|six|seven|ten|fourteen) (days?|weeks?))\b",
    re.I,
)
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "fourteen": 14}


@dataclass
class DateMention:
    value: date
    raw: str
    origin: str  # explicit | relative | inferred
    start: int
    end: int


def _mk(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _absolute(m: re.Match, kind: str, ref: date | None) -> date | None:
    if kind == "iso":
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return _absolute_safe(m, kind, ref)


def _month_key(token: str) -> str:
    t = token.lower().rstrip(".")
    return "sept" if t.startswith("sept") else t


def _relative(raw: str, num: str | None, unit: str | None, ref: date) -> tuple[date, str] | None:
    r = raw.lower().strip()
    if r in {"today", "tonight", "end of day", "end of the day", "eod"}:
        return ref, "relative"
    if r == "tomorrow":
        return ref + timedelta(days=1), "relative"
    if r == "day after tomorrow":
        return ref + timedelta(days=2), "relative"
    if r.startswith("end of") and "week" in r:
        return ref + timedelta(days=(4 - ref.weekday()) % 7), "inferred"
    if r.startswith("end of") and "month" in r:
        nxt = (ref.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1), "inferred"
    if r == "next week":
        return ref + timedelta(days=7 - ref.weekday()), "inferred"  # Monday of next week
    if num and unit:
        n = int(num) if num.isdigit() else _NUM[num.lower()]
        return ref + timedelta(days=n * (7 if unit.lower().startswith("week") else 1)), "relative"
    for name, wd in WEEKDAYS.items():
        if name in r:
            delta = (wd - ref.weekday()) % 7 or 7
            if r.startswith("next ") and delta < 7 and wd > ref.weekday():
                delta += 7
            return ref + timedelta(days=delta), "relative"
    return None


def find_dates(text: str, ref: date | None) -> list[DateMention]:
    found: list[DateMention] = []
    taken: list[tuple[int, int]] = []
    for pat, kind in _ABS:
        for m in pat.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            d = _absolute(m, kind, ref)
            if d:
                found.append(DateMention(d, m.group(0).strip(" ,"), "explicit", m.start(), m.end()))
                taken.append((m.start(), m.end()))
    if ref:
        for m in _REL.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            res = _relative(m.group(1), m.group(2), m.group(3), ref)
            if res:
                found.append(DateMention(res[0], m.group(0).strip(), res[1], m.start(), m.end()))
                taken.append((m.start(), m.end()))
    return sorted(found, key=lambda d: d.start)


def _absolute_safe(m: re.Match, kind: str, ref: date | None) -> date | None:
    try:
        if kind == "mdy":
            month, day, year = MONTHS[_month_key(m.group(1))], int(m.group(2)), m.group(3)
        else:
            day, month, year = int(m.group(1)), MONTHS[_month_key(m.group(2))], m.group(3)
    except KeyError:
        return None
    if year:
        return _mk(int(year), month, day)
    base = ref or date.today()
    d = _mk(base.year, month, day)
    # "January 10" said in a December meeting means next January.
    if d and ref and d < ref - timedelta(days=60):
        d = _mk(base.year + 1, month, day)
    return d


def parse_absolute_date(text: str, ref: date | None) -> date | None:
    for pat, kind in _ABS:
        m = pat.search(text)
        if m:
            return _absolute(m, kind, ref)
    return None


_DEADLINE_CUE = re.compile(r"\b(by|before|due(?: on| by)?|until|no later than|deadline(?: is| of)?|on|for)\s*$", re.I)


def find_deadline(text: str, ref: date) -> DateMention | None:
    """The date a task is due: prefer a date introduced by 'by/before/due/deadline'; otherwise the last date."""
    dates = find_dates(text, ref)
    if not dates:
        return None
    cued = [d for d in dates if _DEADLINE_CUE.search(text[: d.start])]
    return cued[-1] if cued else dates[-1]
