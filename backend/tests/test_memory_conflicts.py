from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Decision
from conftest import add_meeting, approve_all, login, project_id, review, upload_demo

M1 = "[00:00:10] Anshul: The team has agreed to use MongoDB for the application database.\n[00:00:30] Anshul: Rahul will complete the database integration by November 5."
M2 = "[00:00:10] Anshul: After evaluating alternatives, we have decided to migrate the database from MongoDB to PostgreSQL.\n[00:00:30] Anshul: Rahul is now responsible for the migration."


def _resolve(client, h, cid, resolution="accept_new", comment="ok"):
    return client.post(f"/api/conflicts/{cid}/resolve", headers=h, json={"resolution": resolution, "comment": comment})


def test_second_meeting_detects_contradiction_with_evidence(client):
    h = login(client)
    pid = project_id(client, h)
    m1 = add_meeting(client, h, pid, M1, "2026-11-01", "M1")
    approve_all(client, h, m1)
    m2 = add_meeting(client, h, pid, M2, "2026-11-02", "M2")
    data = review(client, h, m2)
    assert len(data["conflicts"]) == 1
    c = data["conflicts"][0]
    assert c["category"] == "contradiction" and c["status"] == "open"
    assert c["previous"]["value"] == "MongoDB" and c["current"]["value"] == "PostgreSQL"
    assert c["previous"]["meeting_title"] == "M1" and c["current"]["meeting_title"] == "M2"
    assert "MongoDB" in c["previous"]["evidence_segments"][0]["text"]
    assert c["recommended_action"] and c["explanation"]
    # No automatic overwrite: the old decision is still confirmed, the new one waits for review.
    assert c["previous"]["status"] == "confirmed" and c["current"]["status"] == "under_review"


def test_conflicting_decision_cannot_be_confirmed_without_resolution(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    c = review(client, h, add_meeting(client, h, pid, M2, "2026-11-02"))["conflicts"][0]
    r = client.post(f"/api/decisions/{c['current']['id']}/approve", headers=h)
    assert r.status_code == 409


def test_accept_new_supersedes_and_preserves_history(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    c = review(client, h, add_meeting(client, h, pid, M2, "2026-11-02"))["conflicts"][0]
    r = _resolve(client, h, c["id"])
    assert r.status_code == 200
    assert r.json()["affected_actions"], "tasks planned under MongoDB should be flagged"
    old = client.get(f"/api/decisions/{c['previous']['id']}", headers=h).json()
    new = client.get(f"/api/decisions/{c['current']['id']}", headers=h).json()
    assert old["status"] == "superseded" and old["superseded_by_id"] == new["id"]
    assert new["status"] == "confirmed" and new["supersedes_id"] == old["id"]
    assert [x["value"] for x in new["history"]] == ["MongoDB", "PostgreSQL"]
    memory = client.get(f"/api/decisions/memory?project_id={pid}", headers=h).json()
    db_group = next(g for g in memory if g["topic"] == "database")
    assert db_group["current"]["value"] == "PostgreSQL" and len(db_group["history"]) == 2
    assert _resolve(client, h, c["id"]).status_code == 409  # cannot be resolved twice


def test_keep_previous_rejects_new_and_keeps_old(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    c = review(client, h, add_meeting(client, h, pid, M2, "2026-11-02"))["conflicts"][0]
    assert _resolve(client, h, c["id"], "keep_previous").status_code == 200
    assert client.get(f"/api/decisions/{c['previous']['id']}", headers=h).json()["status"] == "confirmed"
    assert client.get(f"/api/decisions/{c['current']['id']}", headers=h).json()["status"] == "rejected"


def test_mark_compatible_and_request_review(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    c = review(client, h, add_meeting(client, h, pid, M2, "2026-11-02"))["conflicts"][0]
    assert _resolve(client, h, c["id"], "needs_review", "").status_code == 422  # a comment is required
    assert _resolve(client, h, c["id"], "needs_review", "Ask the DBA").json()["status"] == "needs_review"
    assert _resolve(client, h, c["id"], "compatible", "Both used").json()["status"] == "compatible"
    assert client.get(f"/api/decisions/{c['current']['id']}", headers=h).json()["status"] == "proposed"


def test_member_cannot_resolve_conflicts(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    c = review(client, h, add_meeting(client, h, pid, M2, "2026-11-02"))["conflicts"][0]
    assert _resolve(client, login(client, "Rahul"), c["id"]).status_code == 403


def test_compatible_restatement_is_not_a_conflict(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, "Anshul: The production launch is scheduled for November 8.", "2026-11-01"))
    m2 = add_meeting(client, h, pid, "Anshul: The production launch is still scheduled for November 8, nothing changes.", "2026-11-02")
    data = review(client, h, m2)
    assert data["conflicts"] == []
    assert data["decisions"][0]["related_decision_id"] is not None


def test_deadline_change_detected(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, "Anshul: The production launch is scheduled for November 8.", "2026-11-01"))
    m2 = add_meeting(client, h, pid, "Anshul: The production launch is postponed from November 8 to November 22.", "2026-11-08")
    c = review(client, h, m2)["conflicts"][0]
    assert c["category"] == "deadline_change" and "14 days later" in c["explanation"]


def test_action_ownership_and_deadline_conflicts(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, "Anshul: Priya will write the API documentation by November 7.", "2026-11-01"))
    m2 = add_meeting(client, h, pid, "Anshul: Karan will write the API documentation by November 7.", "2026-11-02")
    ownership = review(client, h, m2)["conflicts"][0]
    assert ownership["category"] == "ownership"
    _resolve(client, h, ownership["id"], "keep_previous")  # Priya stays the owner; Karan's copy is rejected
    m3 = add_meeting(client, h, pid, "Anshul: Priya must finish the API documentation by November 12.", "2026-11-03")
    assert review(client, h, m3)["conflicts"][0]["category"] == "deadline_change"


def test_ownerless_decision_is_retained(client):
    h = login(client)
    pid = project_id(client, h)
    mid = add_meeting(client, h, pid, "The production launch is scheduled for November 8.")  # no speaker, no owner
    d = review(client, h, mid)["decisions"]
    assert len(d) == 1 and d[0]["speaker"] is None


def test_project_memory_is_isolated(client):
    h = login(client)
    atlas, helios = project_id(client, h), project_id(client, h, "Helios Analytics")
    approve_all(client, h, add_meeting(client, h, atlas, M1, "2026-11-01"))
    m = add_meeting(client, h, helios, "Anshul: We have decided to use PostgreSQL for the warehouse database.", "2026-11-02")
    assert review(client, h, m)["conflicts"] == []
    # And a member of Atlas cannot see Helios at all.
    assert client.get(f"/api/projects/{helios}", headers=login(client, "Rahul")).status_code == 404


def test_memory_survives_restart(client):
    h = login(client)
    pid = project_id(client, h)
    approve_all(client, h, add_meeting(client, h, pid, M1, "2026-11-01"))
    fresh_engine = create_engine(settings.database_url)  # simulates a new process opening the same database file
    with sessionmaker(bind=fresh_engine)() as db:
        assert db.query(Decision).filter(Decision.value == "MongoDB", Decision.status == "confirmed").count() == 1
    fresh_engine.dispose()


def test_golden_scenario_third_meeting_uses_latest_accepted_state(client):
    """Regression: meeting 3 must compare against PostgreSQL (accepted), never the superseded MongoDB decision."""
    h = login(client)
    pid = project_id(client, h)
    m1 = upload_demo(client, h, pid, 1)
    r1 = review(client, h, m1)
    assert {d["value"] for d in r1["decisions"]} == {"MongoDB", "2026-11-08"}
    assert {(a["owner_name"], a["deadline"]) for a in r1["actions"]} == {("Rahul", "2026-11-05"), ("Priya", "2026-11-07")}
    approve_all(client, h, m1)

    m2 = upload_demo(client, h, pid, 2)
    r2 = review(client, h, m2)
    assert r2 != r1 and {d["value"] for d in r2["decisions"]} == {"PostgreSQL", "2026-11-08"}  # mock output tied to its own input
    assert [c["category"] for c in r2["conflicts"]] == ["contradiction"]
    _resolve(client, h, r2["conflicts"][0]["id"])
    approve_all(client, h, m2)

    m3 = upload_demo(client, h, pid, 3)
    r3 = review(client, h, m3)
    cats = sorted(c["category"] for c in r3["conflicts"])
    assert cats == ["deadline_change", "deadline_change"]  # launch date and Priya's documentation deadline
    assert not any(c["previous"].get("value") == "MongoDB" for c in r3["conflicts"]), "superseded decision was reopened"
    pg = next(d for d in r3["decisions"] if d["value"] == "PostgreSQL")
    assert pg["status"] == "proposed" and pg["related_decision_id"] is not None
    docs = next(a for a in r3["actions"] if a["owner_name"] == "Priya")
    assert docs["deadline"] == "2026-11-12"
    for c in r3["conflicts"]:
        _resolve(client, h, c["id"])
    memory = client.get(f"/api/decisions/memory?project_id={pid}", headers=h).json()
    launch = next(g for g in memory if g["topic"] == "production launch date")
    assert launch["current"]["value"] == "2026-11-22"
    assert sorted(x["status"] for x in launch["history"]) == ["confirmed", "superseded", "superseded"]
