"""Transcript ingestion: file bytes -> text -> speaker-attributed segments.

Never invents a speaker or timestamp: lines with no speaker label keep speaker=None ("unattributed"),
unless the transcript was dictated, in which case the dictating person is the real speaker.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date

ALLOWED_EXTENSIONS = {"txt": "txt", "md": "txt", "docx": "docx", "pdf": "pdf"}


class IngestError(ValueError):
    """User-facing validation error (message is shown verbatim in the UI)."""


@dataclass
class Segment:
    idx: int
    speaker: str | None
    timestamp: str | None
    text: str


@dataclass
class ParsedTranscript:
    segments: list[Segment]
    speakers: list[str]
    header: dict[str, str] = field(default_factory=dict)  # Meeting:/Date:/Participants: lines found at the top
    header_participants: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- file -> text

def extract_text(filename: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    """Return (source_type, text). Raises IngestError with a clear message for anything unusable."""
    if not filename or "." not in filename:
        raise IngestError("The file has no extension. Upload a .txt, .docx or .pdf transcript.")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestError(f"Unsupported file type '.{ext}'. Upload a .txt, .docx or text-based .pdf transcript.")
    if len(data) == 0:
        raise IngestError("The file is empty.")
    if len(data) > max_bytes:
        raise IngestError(f"The file is {len(data) // 1024} KB; the limit is {max_bytes // 1024} KB.")
    kind = ALLOWED_EXTENSIONS[ext]
    if kind == "txt":
        text = _decode_text(data)
    elif kind == "docx":
        text = _docx_text(data)
    else:
        text = _pdf_text(data)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise IngestError("The file contains no readable transcript text.")
    return kind, text


def _decode_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise IngestError("This does not look like a text file (binary content detected).")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise IngestError("Could not decode the text file. Save it as UTF-8 and try again.")


def _docx_text(data: bytes) -> str:
    if not data.startswith(b"PK"):
        raise IngestError("This .docx file is not a valid Word document.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if "word/document.xml" not in z.namelist():
                raise IngestError("This .docx file is not a valid Word document.")
            # Zip-bomb guard: refuse absurd decompressed sizes.
            if sum(i.file_size for i in z.infolist()) > 50 * 1024 * 1024:
                raise IngestError("This .docx file is too large once decompressed.")
        import docx  # python-docx

        document = docx.Document(io.BytesIO(data))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                lines.append(" ".join(c.text.strip() for c in row.cells if c.text.strip()))
        return "\n".join(lines)
    except IngestError:
        raise
    except Exception as exc:  # corrupted file
        raise IngestError(f"Could not read the Word document ({type(exc).__name__}).") from exc


def _pdf_text(data: bytes) -> str:
    if not data.lstrip().startswith(b"%PDF"):
        raise IngestError("This .pdf file is not a valid PDF document.")
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestError("This PDF is password-protected. Remove the password and upload again.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(f"Could not read the PDF ({type(exc).__name__}).") from exc
    if not text.strip():
        raise IngestError("This PDF has no text layer (it may be a scanned image). Upload a text-based PDF, DOCX or TXT.")
    return text


# ---------------------------------------------------------------- text -> segments

_NAME = r"[A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*){0,2}"
_TS = r"\d{1,2}:\d{2}(?::\d{2})?"
_PATTERNS = [
    re.compile(rf"^\[(?P<ts>{_TS})\]\s*(?P<name>{_NAME})\s*[:\-–]\s*(?P<text>.*)$"),          # [00:01:12] Rahul: text
    re.compile(rf"^\[(?P<name>{_NAME})\s+(?P<ts>{_TS})\]\s*(?P<text>.*)$"),                    # [Rahul 00:01:12] text
    re.compile(rf"^(?P<name>{_NAME})\s*\((?P<ts>{_TS})\)\s*[:\-–]?\s*(?P<text>.*)$"),          # Rahul (00:01:12): text
    re.compile(rf"^(?P<ts>{_TS})\s*[\-–]?\s*(?P<name>{_NAME})\s*[:\-–]\s*(?P<text>.*)$"),      # 00:01:12 Rahul: text
    re.compile(rf"^(?P<name>{_NAME}|[A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)?)\s*:\s*(?P<text>.+)$"),      # Rahul: text / RAHUL: text
]
_NOT_SPEAKERS = {
    "note", "notes", "action", "actions", "action item", "action items", "decision", "decisions", "agenda", "summary",
    "todo", "update", "updates", "re", "subject", "date", "time", "attendees", "participants", "meeting", "title",
    "project", "location", "present", "absent", "next steps", "minutes", "transcript", "deadline", "owner", "status",
    "http", "https", "warning", "important", "ps", "fyi", "q", "a",
}
_HEADER_KEYS = {"meeting", "title", "date", "project", "attendees", "participants", "present", "location", "time"}


def _clean_name(raw: str) -> str:
    name = raw.strip().strip(".")
    return name.title() if name.isupper() else name


def _split_names(value: str) -> list[str]:
    parts = re.split(r",|;|\band\b|&", value)
    return [p.strip().split("(")[0].strip() for p in parts if p.strip()]


def parse_transcript(text: str, dictated_by: str | None = None) -> ParsedTranscript:
    lines = [ln.strip() for ln in text.split("\n")]
    header: dict[str, str] = {}
    header_participants: list[str] = []
    segments: list[Segment] = []
    current: Segment | None = None
    body_started = False

    for line in lines:
        if not line:
            current = None if dictated_by else current  # blank line ends a dictated paragraph
            continue
        # Header block: "Meeting: ...", "Date: ...", "Participants: a, b" before the dialogue starts.
        m_head = re.match(r"^([A-Za-z ]{2,20})\s*:\s*(.+)$", line)
        if not body_started and m_head and m_head.group(1).strip().lower() in _HEADER_KEYS:
            key = m_head.group(1).strip().lower()
            header[key] = m_head.group(2).strip()
            if key in {"attendees", "participants", "present"}:
                header_participants = _split_names(m_head.group(2))
            continue

        matched = None
        for pat in _PATTERNS:
            m = pat.match(line)
            if m and m.group("name").strip().lower() not in _NOT_SPEAKERS:
                matched = m
                break
        if matched:
            body_started = True
            current = Segment(
                idx=len(segments),
                speaker=_clean_name(matched.group("name")),
                timestamp=matched.groupdict().get("ts"),
                text=matched.group("text").strip(),
            )
            segments.append(current)
        elif current is not None and not dictated_by:
            current.text = f"{current.text} {line}".strip()  # continuation of the previous speaker's turn
        else:
            body_started = True
            for chunk in _chunk_sentences(line) if dictated_by else [line]:
                current = Segment(idx=len(segments), speaker=dictated_by, timestamp=None, text=chunk)
                segments.append(current)

    segments = [s for s in segments if s.text]
    for i, s in enumerate(segments):
        s.idx = i
    speakers: list[str] = []
    for s in segments:
        if s.speaker and s.speaker not in speakers:
            speakers.append(s.speaker)
    return ParsedTranscript(segments=segments, speakers=speakers, header=header, header_participants=header_participants)


def _chunk_sentences(paragraph: str, max_len: int = 320) -> list[str]:
    """Dictated speech often arrives as one long paragraph; split it so evidence can point at a sentence."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", paragraph)
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if buf and len(buf) + len(s) > max_len:
            chunks.append(buf.strip())
            buf = ""
        buf = f"{buf} {s}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def parse_header_date(value: str | None) -> date | None:
    if not value:
        return None
    from ..ai.dates import parse_absolute_date

    return parse_absolute_date(value, None)
