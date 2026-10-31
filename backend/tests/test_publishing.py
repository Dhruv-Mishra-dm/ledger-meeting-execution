import httpx

from app.trackers.base import TaskPayload
from app.trackers.github import GitHubIssuesProvider, _marker
from conftest import add_meeting, login, project_id, review

TEXT = "[00:00:10] Anshul: Rahul will complete the database integration by November 5."


def _action(client, h):
    mid = add_meeting(client, h, project_id(client, h), TEXT)
    return review(client, h, mid)["actions"][0]


def test_unapproved_task_cannot_publish(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    r = client.post(f"/api/actions/{a['id']}/publish", headers=h)
    assert r.status_code == 409 and "approve" in r.json()["detail"].lower()
    assert fake_tracker.calls == []


def test_rejected_task_cannot_publish(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    client.post(f"/api/actions/{a['id']}/reject", headers=h, json={"comment": "not needed"})
    assert client.post(f"/api/actions/{a['id']}/publish", headers=h).status_code == 409
    assert fake_tracker.calls == []


def test_approved_task_publishes_and_persists_external_id(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    assert client.post(f"/api/actions/{a['id']}/approve", headers=h).json()["changed"] is True
    r = client.post(f"/api/actions/{a['id']}/publish", headers=h)
    assert r.status_code == 200, r.text
    pub = client.get(f"/api/actions/{a['id']}", headers=h).json()["publication"]
    assert pub["state"] == "published" and pub["external_id"] == "1" and pub["external_url"].endswith("/issues/1") and pub["is_external"]


def test_repeated_approval_is_safe(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    first = client.post(f"/api/actions/{a['id']}/approve", headers=h).json()
    second = client.post(f"/api/actions/{a['id']}/approve", headers=h).json()
    assert first["changed"] is True and second["changed"] is False
    audit = client.get(f"/api/audit?project_id={a['project_id']}&item_type=action&item_id={a['id']}", headers=h).json()
    assert [e["action"] for e in audit].count("approve") == 1


def test_repeated_publishing_does_not_duplicate(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    client.post(f"/api/actions/{a['id']}/approve", headers=h)
    for _ in range(3):
        assert client.post(f"/api/actions/{a['id']}/publish", headers=h).status_code == 200
    assert len(fake_tracker.calls) == 1 and len(fake_tracker.created) == 1


def test_failed_publish_is_recoverable_without_duplicates(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    client.post(f"/api/actions/{a['id']}/approve", headers=h)
    fake_tracker.fail_next = 1
    r = client.post(f"/api/actions/{a['id']}/publish", headers=h)
    assert r.status_code == 502
    pub = client.get(f"/api/actions/{a['id']}", headers=h).json()["publication"]
    assert pub["state"] == "failed" and pub["external_id"] is None  # never marked published on failure
    assert client.post(f"/api/actions/{a['id']}/publish", headers=h).status_code == 200
    assert len(set(fake_tracker.calls)) == 1 and len(fake_tracker.created) == 1  # same idempotency key on retry
    assert client.get(f"/api/actions/{a['id']}", headers=h).json()["publication"]["attempts"] == 2


def test_members_cannot_approve_or_publish(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    member = login(client, "Rahul")
    assert client.post(f"/api/actions/{a['id']}/approve", headers=member).status_code == 403
    client.post(f"/api/actions/{a['id']}/approve", headers=h)
    assert client.post(f"/api/actions/{a['id']}/publish", headers=member).status_code == 403
    assert client.post(f"/api/actions/{a['id']}/publish").status_code == 401


def test_editing_an_approved_task_requires_reapproval(client, fake_tracker):
    h = login(client)
    a = _action(client, h)
    client.post(f"/api/actions/{a['id']}/approve", headers=h)
    r = client.patch(f"/api/actions/{a['id']}", headers=h, json={"deadline": "2026-11-06", "owner_name": "Priya"})
    assert r.json()["status"] == "proposed" and r.json()["owner_name"] == "Priya"
    assert client.post(f"/api/actions/{a['id']}/publish", headers=h).status_code == 409


def test_demo_tracker_is_labelled_simulated(client):
    h = login(client)
    a = _action(client, h)
    client.post(f"/api/actions/{a['id']}/approve", headers=h)
    r = client.post(f"/api/actions/{a['id']}/publish", headers=h).json()
    assert "simulated" in r["message"].lower() and r["publication"]["is_external"] is False


# ---------------------------------------------------------------- GitHub adapter against a mocked API

def _payload():
    from datetime import date
    return TaskPayload("Do it", "desc", "Rahul", date(2026, 11, 5), "Atlas", "M1", date(2026, 11, 1), None, "quote")


def test_github_adapter_creates_issue_with_labels_and_marker():
    seen = {}

    def handler(request: httpx.Request):
        if request.method == "GET":
            return httpx.Response(200, json=[])
        seen["body"] = request.read().decode()
        return httpx.Response(201, json={"number": 42, "html_url": "https://github.com/o/r/issues/42"})
    p = GitHubIssuesProvider("t", "o/r", "Rahul:rahul-gh", client=httpx.Client(transport=httpx.MockTransport(handler)))
    created = p.create_task(_payload(), "mte-abc-1")
    assert created.external_id == "42" and not created.adopted
    assert "due:2026-11-05" in seen["body"] and "owner:Rahul" in seen["body"] and "rahul-gh" in seen["body"]
    assert "meeting-agent:key=mte-abc-1" in seen["body"]


def test_github_adapter_adopts_existing_issue_instead_of_duplicating():
    posts = []

    def handler(request: httpx.Request):
        if request.method == "GET":
            return httpx.Response(200, json=[{"number": 7, "html_url": "https://github.com/o/r/issues/7", "body": "x " + _marker("mte-abc-1")}])
        posts.append(1)
        return httpx.Response(201, json={"number": 8, "html_url": "u"})
    p = GitHubIssuesProvider("t", "o/r", client=httpx.Client(transport=httpx.MockTransport(handler)))
    created = p.create_task(_payload(), "mte-abc-1")
    assert created.adopted and created.external_id == "7" and posts == []


def test_github_adapter_reports_rate_limit_and_auth_errors():
    import pytest

    from app.trackers.base import TrackerAuthError, TrackerRateLimited

    limited = GitHubIssuesProvider("t", "o/r", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(403, headers={"x-ratelimit-remaining": "0", "retry-after": "30"}))))
    with pytest.raises(TrackerRateLimited):
        limited.create_task(_payload(), "k")
    bad = GitHubIssuesProvider("t", "o/r", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(TrackerAuthError):
        bad.create_task(_payload(), "k")
    assert GitHubIssuesProvider("", "").check()["status"] == "not_configured"
