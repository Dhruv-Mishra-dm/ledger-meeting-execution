import io
import zlib

import docx

from app.ingest.parser import parse_transcript
from conftest import login, project_id

TRANSCRIPT = "[00:00:05] Anshul: We have decided to use PostgreSQL.\n[00:00:20] Rahul: I'll write the schema by November 5."


def _docx_bytes(lines):
    d = docx.Document()
    for line in lines:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _pdf_bytes(lines):
    """Minimal text-based PDF built by hand (no extra dependency)."""
    content = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(f"({ln.replace('(', '').replace(')', '')}) '" for ln in lines) + " ET"
    stream = zlib.compress(content.encode("latin-1"))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return bytes(out)


def _upload(client, h, pid, name, data, date="2026-11-01"):
    return client.post("/api/meetings/upload", headers=h, data={"project_id": pid, "meeting_date": date}, files={"file": (name, data, "application/octet-stream")})


def test_valid_txt_preserves_speakers_and_timestamps(client):
    h = login(client)
    pid = project_id(client, h)
    r = _upload(client, h, pid, "m.txt", TRANSCRIPT.encode())
    assert r.status_code == 201, r.text
    m = client.get(f"/api/meetings/{r.json()['id']}", headers=h).json()
    assert [s["speaker"] for s in m["segments"]] == ["Anshul", "Rahul"]
    assert m["segments"][0]["timestamp"] == "00:00:05"
    assert m["source_type"] == "txt" and m["source_filename"] == "m.txt"


def test_valid_docx(client):
    h = login(client)
    r = _upload(client, h, project_id(client, h), "m.docx", _docx_bytes(TRANSCRIPT.split("\n")))
    assert r.status_code == 201, r.text
    assert r.json()["source_type"] == "docx"
    assert r.json()["participants"] == ["Anshul", "Rahul"]


def test_valid_text_pdf(client):
    h = login(client)
    r = _upload(client, h, project_id(client, h), "m.pdf", _pdf_bytes(["Anshul: We have decided to use PostgreSQL.", "Rahul: I will write the schema."]))
    assert r.status_code == 201, r.text
    m = client.get(f"/api/meetings/{r.json()['id']}", headers=h).json()
    assert m["source_type"] == "pdf"
    assert "PostgreSQL" in " ".join(s["text"] for s in m["segments"])


def test_empty_file_rejected(client):
    h = login(client)
    r = _upload(client, h, project_id(client, h), "empty.txt", b"")
    assert r.status_code == 422 and "empty" in r.json()["detail"].lower()
    r = _upload(client, h, project_id(client, h), "blank.txt", b"   \n  ")
    assert r.status_code == 422


def test_unsupported_and_fake_files_rejected(client):
    h = login(client)
    pid = project_id(client, h)
    assert "Unsupported" in _upload(client, h, pid, "slides.pptx", b"PK...").json()["detail"]
    assert _upload(client, h, pid, "notes.pdf", b"not a pdf").status_code == 422
    assert _upload(client, h, pid, "notes.docx", b"plain text").status_code == 422
    assert _upload(client, h, pid, "bin.txt", b"\x00\x01\x02").status_code == 422


def test_duplicate_upload_detected(client):
    h = login(client)
    pid = project_id(client, h)
    assert _upload(client, h, pid, "a.txt", TRANSCRIPT.encode()).status_code == 201
    r = _upload(client, h, pid, "copy.txt", (TRANSCRIPT + "\n\n").encode())
    assert r.status_code == 409 and "already uploaded" in r.json()["detail"]


def test_missing_speaker_is_not_invented(client):
    h = login(client)
    r = _upload(client, h, project_id(client, h), "m.txt", b"We decided to use React for the frontend.\nSomeone needs to update the style guide.")
    m = client.get(f"/api/meetings/{r.json()['id']}", headers=h).json()
    assert all(s["speaker"] is None for s in m["segments"])


def test_meeting_date_required_when_not_in_header(client):
    h = login(client)
    r = client.post("/api/meetings/upload", headers=h, data={"project_id": project_id(client, h)}, files={"file": ("m.txt", TRANSCRIPT.encode(), "text/plain")})
    assert r.status_code == 422 and "date" in r.json()["detail"].lower()


def test_parser_formats_and_header():
    text = (
        "Meeting: Weekly sync\nDate: November 3, 2026\nParticipants: Asha, Ben\n\n"
        "[Asha 00:01:02] Opening remarks.\nBen (00:02:00): Reply here\ncontinued on the next line.\n00:03:00 Asha: Third.\nBEN: Shouted.\nNote: not a speaker"
    )
    p = parse_transcript(text)
    assert p.header["meeting"] == "Weekly sync" and p.header_participants == ["Asha", "Ben"]
    assert [(s.speaker, s.timestamp) for s in p.segments] == [("Asha", "00:01:02"), ("Ben", "00:02:00"), ("Asha", "00:03:00"), ("Ben", None)]
    assert p.segments[1].text.endswith("continued on the next line.")
    assert "Note: not a speaker" in p.segments[3].text


def test_dictation_is_attributed_to_the_dictating_person(client):
    h = login(client)
    r = client.post("/api/meetings/text", headers=h, json={
        "project_id": project_id(client, h), "meeting_date": "2026-11-02", "source": "dictation",
        "text": "Okay so we decided to use PostgreSQL. Rahul will migrate the data by Friday.",
    })
    assert r.status_code == 201
    m = client.get(f"/api/meetings/{r.json()['id']}", headers=h).json()
    assert m["source_type"] == "dictation" and m["dictated_by"] == "Anshul"
    assert {s["speaker"] for s in m["segments"]} == {"Anshul"}
