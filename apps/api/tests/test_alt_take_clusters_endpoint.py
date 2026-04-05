"""Tests for the batch-loaded alt-take clusters endpoint (no N+1 queries)."""

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app
from app.models import AltTakeCluster, AltTakeMember, Issue


def _make_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_get_alt_take_clusters_returns_members(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    try:
        with TestClient(app) as client:
            project = client.post("/projects", json={"name": "P"}).json()
            chapter = client.post(
                f"/projects/{project['id']}/chapters",
                json={"chapter_number": 1, "title": "C"},
            ).json()
            chapter_id = chapter["id"]

            # Insert two clusters, each with two members.
            with Session(engine) as session:
                issue_a = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
                issue_b = Issue(chapter_id=chapter_id, type="repetition", start_ms=200, end_ms=300, confidence=0.85)
                issue_c = Issue(chapter_id=chapter_id, type="false_start", start_ms=400, end_ms=500, confidence=0.9)
                issue_d = Issue(chapter_id=chapter_id, type="false_start", start_ms=600, end_ms=700, confidence=0.8)
                session.add_all([issue_a, issue_b, issue_c, issue_d])
                session.flush()

                cluster1 = AltTakeCluster(
                    chapter_id=chapter_id,
                    manuscript_start_idx=0, manuscript_end_idx=2,
                    manuscript_text="hello world", confidence=0.8,
                )
                cluster2 = AltTakeCluster(
                    chapter_id=chapter_id,
                    manuscript_start_idx=5, manuscript_end_idx=7,
                    manuscript_text="goodbye world", confidence=0.75,
                )
                session.add_all([cluster1, cluster2])
                session.flush()

                session.add(AltTakeMember(cluster_id=cluster1.id, issue_id=issue_a.id, take_order=0))
                session.add(AltTakeMember(cluster_id=cluster1.id, issue_id=issue_b.id, take_order=1))
                session.add(AltTakeMember(cluster_id=cluster2.id, issue_id=issue_c.id, take_order=0))
                session.add(AltTakeMember(cluster_id=cluster2.id, issue_id=issue_d.id, take_order=1))
                session.commit()

            resp = client.get(f"/chapters/{chapter_id}/alt-take-clusters")
            assert resp.status_code == 200
            data = resp.json()

            assert len(data) == 2
            # Each cluster should have exactly 2 members.
            for cluster in data:
                assert "members" in cluster
                assert len(cluster["members"]) == 2
                assert "ranking" in cluster
    finally:
        app.dependency_overrides.clear()


def test_get_alt_take_clusters_returns_empty_list_when_none(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    try:
        with TestClient(app) as client:
            project = client.post("/projects", json={"name": "P"}).json()
            chapter = client.post(
                f"/projects/{project['id']}/chapters",
                json={"chapter_number": 1, "title": "C"},
            ).json()
            resp = client.get(f"/chapters/{chapter['id']}/alt-take-clusters")
            assert resp.status_code == 200
            assert resp.json() == []
    finally:
        app.dependency_overrides.clear()
