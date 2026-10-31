"""Database initialisation and demo data.

python -m app.seed            create tables (via migrations) and demo accounts/projects if missing
python -m app.seed --reset    wipe the database and seed again
python -m app.seed --scenario wipe, seed, then run the full three-meeting golden scenario through the services
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from .config import BACKEND_DIR, settings
from .db import Base, SessionLocal, engine
from .models import Project, ProjectMember, Role, User
from .security import hash_password

DEMO_DIR = BACKEND_DIR.parent / "demo" / "transcripts"
ACCOUNTS = [
    ("Admin", Role.ADMIN, "admin@atlas.example"),
    ("Anshul", Role.MANAGER, "anshul@atlas.example"),
    ("Rahul", Role.MEMBER, "rahul@atlas.example"),
    ("Priya", Role.MEMBER, "priya@atlas.example"),
    ("Karan", Role.MEMBER, "karan@atlas.example"),
]
PROJECTS = [
    ("Atlas Customer Portal", "Customer-facing order and billing portal. Golden demo project.", ["Anshul", "Rahul", "Priya", "Karan"]),
    ("Helios Analytics", "Separate internal project, used to show that decision memory is isolated per project.", ["Anshul"]),
]


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


def seed(db: Session) -> dict:
    created = {"users": 0, "projects": 0}
    for name, role, email in ACCOUNTS:
        if db.query(User).filter(User.name == name).first() is None:
            db.add(User(name=name, role=role, email=email, password_hash=hash_password(settings.demo_password), can_login=True))
            created["users"] += 1
    db.flush()
    for pname, desc, members in PROJECTS:
        p = db.query(Project).filter(Project.name == pname).first()
        if p is None:
            p = Project(name=pname, description=desc)
            db.add(p)
            db.flush()
            created["projects"] += 1
        for m in members:
            u = db.query(User).filter(User.name == m).one()
            if db.get(ProjectMember, (p.id, u.id)) is None:
                db.add(ProjectMember(project_id=p.id, user_id=u.id))
    db.commit()
    return created


def reset_and_seed() -> dict:
    engine.dispose()
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate()
    with SessionLocal() as db:
        return {"reset": True, **seed(db)}


def run_scenario(db: Session, publish: bool = True) -> list[str]:
    """Drive the golden path through the same services the API uses. Returns a readable log."""
    from .ingest.parser import extract_text
    from .models import ActionItem, Conflict, Decision
    from .services import conflicts, publishing, review
    from .services.processing import create_meeting, process_meeting

    log: list[str] = []
    manager = db.query(User).filter(User.name == "Anshul").one()
    project = db.query(Project).filter(Project.name == "Atlas Customer Portal").one()
    files = sorted(DEMO_DIR.glob("meeting-*.txt"))
    for i, path in enumerate(files, start=1):
        data = path.read_bytes()
        kind, text = extract_text(path.name, data, settings.max_upload_bytes)
        m = create_meeting(db, project=project, user=manager, text=text, source_type=kind, title=None, meeting_date=None, filename=path.name, size=len(data))
        res = process_meeting(db, m, manager)
        log.append(f"Meeting {i} '{m.title}': {res['decisions']} decisions, {res['actions']} actions, {res['conflicts']} conflicts "
                   f"(compared against {res['compared_against']} earlier decisions)")
        for c in db.query(Conflict).filter(Conflict.meeting_id == m.id, Conflict.status == "open").all():
            conflicts.resolve(db, c, "accept_new", "Accepted in scripted demo run", manager)
            log.append(f"  resolved conflict #{c.id} ({c.category}) -> accept new")
        for d in db.query(Decision).filter(Decision.meeting_id == m.id, Decision.status == "proposed").all():
            review.approve_decision(db, d, manager)
        for a in db.query(ActionItem).filter(ActionItem.meeting_id == m.id, ActionItem.status == "proposed").all():
            review.approve_action(db, a, manager)
            if publish:
                publishing.publish(db, a, manager)
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="wipe and re-seed the database")
    parser.add_argument("--scenario", action="store_true", help="wipe, seed and run the three-meeting scenario")
    args = parser.parse_args(argv)
    if args.reset or args.scenario:
        print(reset_and_seed())
    else:
        migrate()
        with SessionLocal() as db:
            print(seed(db))
    if args.scenario:
        with SessionLocal() as db:
            for line in run_scenario(db):
                print(line)
    print(f"Database: {settings.database_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
