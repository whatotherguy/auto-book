from sqlmodel import Session, SQLModel, create_engine, select

import app.db as db_module
from app.db import init_db, migrate_issue_status_defaults
from app.models import Issue


def test_migrate_issue_status_defaults_updates_open_issues():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Issue(chapter_id=1, type="repetition", start_ms=0, end_ms=100, confidence=0.9, status="open"))
        session.add(Issue(chapter_id=1, type="missing_text", start_ms=200, end_ms=300, confidence=0.7, status="rejected"))
        session.commit()

        migrate_issue_status_defaults(session)

        issues = session.exec(select(Issue).order_by(Issue.id)).all()

    assert issues[0].status == "approved"
    assert issues[1].status == "rejected"


def test_init_db_skips_create_all_when_alembic_version_exists(monkeypatch):
    engine = create_engine("sqlite://")
    calls: list[str] = []

    class FakeInspector:
        def has_table(self, name: str) -> bool:
            return name == "alembic_version"

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "inspect", lambda _engine: FakeInspector())
    monkeypatch.setattr(SQLModel.metadata, "create_all", lambda _engine: calls.append("create_all"))
    monkeypatch.setattr(db_module, "migrate_issue_status_defaults", lambda _session: calls.append("migrate"))

    init_db()

    assert calls == ["migrate"]


def test_init_db_creates_schema_when_alembic_version_missing(monkeypatch):
    engine = create_engine("sqlite://")
    calls: list[str] = []

    class FakeInspector:
        def has_table(self, name: str) -> bool:
            return False

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "inspect", lambda _engine: FakeInspector())
    monkeypatch.setattr(SQLModel.metadata, "create_all", lambda _engine: calls.append("create_all"))
    monkeypatch.setattr(db_module, "migrate_issue_status_defaults", lambda _session: calls.append("migrate"))

    init_db()

    assert calls == ["create_all", "migrate"]
