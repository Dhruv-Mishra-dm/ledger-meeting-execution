from app.db import SessionLocal
from app.models import Reminder
from app.services.reminders import scan
from conftest import add_meeting, approve_all, login, project_id, review

TEXT = (
    "[00:00:10] Anshul: Rahul will complete the database integration by November 5.\n"
    "[00:00:20] Anshul: Priya will write the user guide by November 9."
)


def _setup(client):
    h = login(client)
    pid = project_id(client, h)
    mid = add_meeting(client, h, pid, TEXT, "2026-11-01")
    approve_all(client, h, mid)
    acts = {a["owner_name"]: a for a in review(client, h, mid)["actions"]}
    return h, pid, acts


def _clock(client, h, day):
    return client.post("/api/system/clock", headers=h, json={"date": day}).json()


def _kinds(client, h, pid, action_id):
    return sorted(r["kind"] for r in client.get(f"/api/reminders?project_id={pid}", headers=h).json()["reminders"] if r["action_id"] == action_id)


def test_24h_due_today_and_overdue_reminders(client):
    h, pid, acts = _setup(client)
    rahul = acts["Rahul"]["id"]
    _clock(client, h, "2026-11-03")
    assert _kinds(client, h, pid, rahul) == []
    _clock(client, h, "2026-11-04")
    assert _kinds(client, h, pid, rahul) == ["due_24h"]
    _clock(client, h, "2026-11-05")
    assert _kinds(client, h, pid, rahul) == ["due_24h", "due_today"]
    _clock(client, h, "2026-11-07")
    assert _kinds(client, h, pid, rahul) == ["due_24h", "due_today", "overdue"]
    data = client.get(f"/api/reminders?project_id={pid}", headers=h).json()
    assert [a["id"] for a in data["overdue"]] == [rahul]


def test_reminder_goes_to_owner_notifications(client):
    h, pid, acts = _setup(client)
    _clock(client, h, "2026-11-04")
    rahul_notes = client.get("/api/notifications", headers=login(client, "Rahul")).json()["items"]
    priya_notes = client.get("/api/notifications", headers=login(client, "Priya")).json()["items"]
    assert any("Due tomorrow" in n["title"] for n in rahul_notes)
    assert priya_notes == []


def test_completed_tasks_are_excluded(client):
    h, pid, acts = _setup(client)
    rahul = acts["Rahul"]["id"]
    _clock(client, h, "2026-11-04")
    assert client.post(f"/api/actions/{rahul}/complete", headers=login(client, "Rahul")).status_code == 200
    _clock(client, h, "2026-11-05")
    reminders = client.get(f"/api/reminders?project_id={pid}", headers=h).json()["reminders"]
    mine = [r for r in reminders if r["action_id"] == rahul]
    assert [r["kind"] for r in mine] == ["due_24h"] and mine[0]["status"] == "dismissed"


def test_offline_until_after_deadline_only_creates_overdue(client):
    h, pid, acts = _setup(client)
    _clock(client, h, "2026-11-20")
    assert _kinds(client, h, pid, acts["Rahul"]["id"]) == ["overdue"]


def test_no_duplicate_reminders_after_restart(client):
    h, pid, acts = _setup(client)
    _clock(client, h, "2026-11-04")
    for _ in range(3):  # each call simulates the startup catch-up scan of a restarted process
        with SessionLocal() as db:
            scan(db)
    with SessionLocal() as db:
        assert db.query(Reminder).filter(Reminder.action_id == acts["Rahul"]["id"]).count() == 1


def test_member_cannot_complete_someone_elses_task(client):
    h, pid, acts = _setup(client)
    assert client.post(f"/api/actions/{acts['Rahul']['id']}/complete", headers=login(client, "Priya")).status_code == 403


def test_weekly_digest_is_person_specific_and_factual(client):
    h, pid, acts = _setup(client)
    _clock(client, h, "2026-11-06")
    client.post(f"/api/actions/{acts['Priya']['id']}/complete", headers=login(client, "Priya"))
    people = {p["name"]: p["id"] for p in client.get(f"/api/projects/{pid}/people", headers=h).json()}
    rahul = client.get(f"/api/digest/{people['Rahul']}?project_id={pid}", headers=h).json()
    priya = client.get(f"/api/digest/{people['Priya']}?project_id={pid}", headers=h).json()
    assert [a["title"] for a in rahul["overdue"]] == ["Complete the database integration"]
    assert rahul["completed"] == [] and "user guide" not in str(rahul).lower()
    assert [a["title"] for a in priya["completed"]] == ["Write the user guide"] and priya["overdue"] == []
    assert rahul["week_start"] == "2026-11-02"


def test_member_sees_only_own_digest(client):
    h, pid, acts = _setup(client)
    people = {p["name"]: p["id"] for p in client.get(f"/api/projects/{pid}/people", headers=h).json()}
    member = login(client, "Rahul")
    assert client.get(f"/api/digest/{people['Rahul']}?project_id={pid}", headers=member).status_code == 200
    assert client.get(f"/api/digest/{people['Priya']}?project_id={pid}", headers=member).status_code == 403


def test_migrations_build_the_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.config import BACKEND_DIR

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"decisions", "action_items", "conflicts", "reminders", "task_publications", "approval_logs", "notifications"} <= tables
