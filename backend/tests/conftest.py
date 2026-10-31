import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="mte-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["AI_PROVIDER"] = "demo"
os.environ["TRACKER_PROVIDER"] = "demo"
os.environ["DEMO_PASSWORD"] = "test-pass"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.trackers.base import CreatedTask, TrackerError  # noqa: E402
from app.trackers.factory import set_override  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent.parent / "demo" / "transcripts"


@pytest.fixture()
def db_session():
    engine.dispose()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    with SessionLocal() as db:
        yield db
    set_override(None)


@pytest.fixture()
def client(db_session):
    return TestClient(create_app(run_lifespan=False))


def login(client, name="Anshul"):
    r = client.post("/api/auth/login", json={"username": name, "password": "test-pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def project_id(client, headers, name="Atlas Customer Portal"):
    return next(p["id"] for p in client.get("/api/projects", headers=headers).json() if p["name"] == name)


def add_meeting(client, headers, pid, text, meeting_date="2026-11-01", title="Test meeting", source="paste", process=True):
    r = client.post("/api/meetings/text", headers=headers, json={"project_id": pid, "title": title, "meeting_date": meeting_date, "text": text, "source": source})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    if process:
        p = client.post(f"/api/meetings/{mid}/process", headers=headers, json={})
        assert p.status_code == 200, p.text
    return mid


def review(client, headers, mid):
    return client.get(f"/api/meetings/{mid}/review", headers=headers).json()


def upload_demo(client, headers, pid, n):
    path = sorted(DEMO.glob("meeting-*.txt"))[n - 1]
    r = client.post("/api/meetings/upload", headers=headers, data={"project_id": pid}, files={"file": (path.name, path.read_bytes(), "text/plain")})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert client.post(f"/api/meetings/{mid}/process", headers=headers, json={}).status_code == 200
    return mid


def approve_all(client, headers, mid):
    data = review(client, headers, mid)
    for d in data["decisions"]:
        if d["status"] == "proposed":
            assert client.post(f"/api/decisions/{d['id']}/approve", headers=headers).status_code == 200
    for a in data["actions"]:
        if a["status"] == "proposed":
            assert client.post(f"/api/actions/{a['id']}/approve", headers=headers).status_code == 200


class FakeTracker:
    """External tracker double that records every create call."""

    name = "github"
    label = "Fake GitHub"
    is_external = True

    def __init__(self):
        self.calls: list[str] = []
        self.fail_next = 0
        self.created: dict[str, CreatedTask] = {}

    def configured(self):
        return True

    def check(self):
        return {"ok": True, "status": "connected", "detail": "fake"}

    def preview(self, task):
        return {"provider": self.label, "repository": "o/r", "title": task.title, "labels": [], "assignees": []}

    def create_task(self, task, key):
        self.calls.append(key)
        if self.fail_next:
            self.fail_next -= 1
            raise TrackerError("simulated outage")
        if key in self.created:
            return CreatedTask(self.created[key].external_id, self.created[key].url, adopted=True)
        n = len(self.created) + 1
        self.created[key] = CreatedTask(str(n), f"https://github.com/o/r/issues/{n}")
        return self.created[key]


@pytest.fixture()
def fake_tracker():
    t = FakeTracker()
    set_override(t)
    yield t
    set_override(None)
