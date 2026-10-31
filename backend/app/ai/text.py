"""Shared text utilities: speech clean-up, sentence splitting, topic catalogue and similarity."""
from __future__ import annotations

import re

# ------------------------------------------------------------------ speech clean-up

_FILLERS = re.compile(
    r"(?:^|(?<=[\s,.]))(?:um+|uh+|erm+|er|hmm+|mm+|you know|i mean|basically|literally|kind of|sort of|so yeah|"
    r"okay so|ok so|alright so|all right so|right so|so,? um|like,)(?=[\s,.!?]|$)[,]?",
    re.I,
)
_REPEAT = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.I)


def clean_speech(text: str) -> str:
    """Remove filler words and stutters while keeping meaning ('the the' -> 'the')."""
    t = _FILLERS.sub(" ", text)
    t = _REPEAT.sub(r"\1", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"^[\s,.;:-]+", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation, ellipses and dashes (dictated speech uses all three as pauses)."""
    parts = re.split(r"(?<=[.!?;])\s+|\s*(?:\.\.\.|…)\s*|\s+[—–]\s+|\s+-{2}\s+", text)
    return [p.strip() for p in parts if p and p.strip(" .,;")]


# ------------------------------------------------------------------ topic catalogue

CHOICE_CATEGORIES: list[tuple[str, dict[str, str]]] = [
    ("database", {
        "mongodb": "MongoDB", "mongo": "MongoDB", "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL",
        "sqlite": "SQLite", "dynamodb": "DynamoDB", "firestore": "Firestore", "supabase": "Supabase", "cassandra": "Cassandra",
        "mariadb": "MariaDB", "sql server": "SQL Server", "oracle": "Oracle", "cockroachdb": "CockroachDB",
    }),
    ("frontend framework", {"react": "React", "vue": "Vue", "angular": "Angular", "svelte": "Svelte", "next.js": "Next.js", "nextjs": "Next.js"}),
    ("backend framework", {"fastapi": "FastAPI", "django": "Django", "flask": "Flask", "express": "Express", "spring boot": "Spring Boot", "rails": "Rails"}),
    ("cloud hosting", {"aws": "AWS", "azure": "Azure", "gcp": "GCP", "google cloud": "Google Cloud", "vercel": "Vercel", "render": "Render", "heroku": "Heroku", "netlify": "Netlify", "digitalocean": "DigitalOcean"}),
    ("payment provider", {"stripe": "Stripe", "razorpay": "Razorpay", "paypal": "PayPal", "paytm": "Paytm"}),
    ("authentication provider", {"auth0": "Auth0", "clerk": "Clerk", "okta": "Okta", "cognito": "Cognito", "firebase auth": "Firebase Auth"}),
    ("mobile framework", {"flutter": "Flutter", "react native": "React Native", "swiftui": "SwiftUI", "kotlin": "Kotlin"}),
]
DATE_TOPICS: list[tuple[str, re.Pattern]] = [
    ("production launch date", re.compile(r"\b(launch|go[- ]live|release date|production release|ship date|public release)\b", re.I)),
    ("beta date", re.compile(r"\bbeta\b", re.I)),
    ("code freeze date", re.compile(r"\b(code freeze|feature freeze)\b", re.I)),
    ("demo date", re.compile(r"\b(demo day|client demo|demo date)\b", re.I)),
]
AMOUNT_TOPICS: list[tuple[str, re.Pattern]] = [
    ("budget", re.compile(r"\bbudget\b", re.I)),
    ("pricing", re.compile(r"\b(price|pricing)\b", re.I)),
]
AMOUNT = re.compile(r"(?:\$|₹|rs\.?\s?|inr\s?|usd\s?)\s?\d[\d,]*(?:\.\d+)?\s?(?:k|lakh|lakhs|crore|million|m)?\b|\b\d[\d,]*(?:\.\d+)?\s?(?:k|lakh|lakhs|crore|million)\b", re.I)


def find_choices(text: str) -> list[tuple[str, str, int]]:
    """All (category, canonical value, position) technology mentions, longest token first."""
    low = text.lower()
    hits: list[tuple[str, str, int]] = []
    taken: list[tuple[int, int]] = []
    for cat, vocab in CHOICE_CATEGORIES:
        for token in sorted(vocab, key=len, reverse=True):
            for m in re.finditer(rf"(?<![\w.]){re.escape(token)}(?![\w])", low):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                hits.append((cat, vocab[token], m.start()))
                taken.append((m.start(), m.end()))
    return sorted(hits, key=lambda h: h[2])


def canonical_topic(text: str) -> str | None:
    hits = find_choices(text)
    if hits:
        return hits[0][0]
    for topic, pat in DATE_TOPICS:
        if pat.search(text):
            return topic
    for topic, pat in AMOUNT_TOPICS:
        if pat.search(text):
            return topic
    return None


# ------------------------------------------------------------------ similarity

STOP = set(
    "a an the and or but if so to of in on at by for with from into onto as is are was were be been being it its this that these those "
    "we we'll we're our us you your i i'll me my he she they them their his her will would should could can shall must may might "
    "need needs needed have has had do does did done just also then than now very really okay ok alright yes yeah no not all any "
    "some about up down out over after before again once more most other same such only own let let's lets going go get got make "
    "made new next week today tomorrow team decided decide agreed agree decision use using used".split()
)
GENERIC_VERBS = set(
    "own owns finish finished complete completed completing handle handles handling do doing prepare prepares write writes writing "
    "update updates updating work working start starting take takes care deliver delivering wrap draft review set setup create "
    "creating build building responsible charge look into sort fix".split()
)
SYNONYMS = {
    "docs": "documentation", "doc": "documentation", "documents": "documentation", "document": "documentation",
    "db": "database", "postgres": "postgresql", "mongo": "mongodb", "migrate": "migration", "migrating": "migration",
    "integrate": "integration", "integrating": "integration", "deploy": "deployment", "deploying": "deployment",
    "test": "testing", "tests": "testing", "qa": "testing", "go-live": "launch", "release": "launch",
}


def tokens(text: str, drop_generic_verbs: bool = False) -> set[str]:
    out: set[str] = set()
    for w in re.findall(r"[a-z0-9][a-z0-9.+#-]*", text.lower()):
        w = w.strip(".-")
        w = SYNONYMS.get(w, w)
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = SYNONYMS.get(w[:-1], w[:-1])
        if w in STOP or len(w) < 2:
            continue
        if drop_generic_verbs and w in GENERIC_VERBS:
            continue
        out.add(w)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def same_task(title_a: str, title_b: str) -> bool:
    """Two action items describe the same work (ignoring generic verbs like 'finish'/'own')."""
    a, b = tokens(title_a, True), tokens(title_b, True)
    shared = a & b
    if not shared:
        return False
    strong = len(shared) >= 2 or any(len(w) >= 6 for w in shared)
    return strong and overlap(a, b) >= 0.6
