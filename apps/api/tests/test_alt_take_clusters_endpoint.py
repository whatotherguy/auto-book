"""Tests for the batch-loaded alt-take clusters endpoint (no N+1 queries)."""

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app
from app.models import AltTakeCluster, AltTakeMember, Chapter, Issue, VadSegment


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


def test_get_alt_take_clusters_includes_playback_timing(tmp_path, monkeypatch):
    """Test that the API endpoint computes and returns playback window timing fields."""
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

            # Set chapter duration for playback clamping
            with Session(engine) as session:
                db_chapter = session.get(Chapter, chapter_id)
                db_chapter.duration_ms = 10000
                session.add(db_chapter)

                # Create issues with specific timing
                issue_a = Issue(chapter_id=chapter_id, type="repetition", start_ms=1000, end_ms=2000, confidence=0.9)
                issue_b = Issue(chapter_id=chapter_id, type="repetition", start_ms=3000, end_ms=4000, confidence=0.85)
                session.add_all([issue_a, issue_b])
                session.flush()

                # Create cluster with members
                cluster = AltTakeCluster(
                    chapter_id=chapter_id,
                    manuscript_start_idx=0, manuscript_end_idx=2,
                    manuscript_text="hello world", confidence=0.8,
                )
                session.add(cluster)
                session.flush()

                session.add(AltTakeMember(cluster_id=cluster.id, issue_id=issue_a.id, take_order=0))
                session.add(AltTakeMember(cluster_id=cluster.id, issue_id=issue_b.id, take_order=1))

                # Add VAD segment that should affect playback window snapping
                session.add(VadSegment(chapter_id=chapter_id, start_ms=900, end_ms=2100, speech_probability=0.95))
                session.commit()

            resp = client.get(f"/chapters/{chapter_id}/alt-take-clusters")
            assert resp.status_code == 200
            data = resp.json()

            assert len(data) == 1
            members = data[0]["members"]
            assert len(members) == 2

            # Verify that each member has the timing fields
            for member in members:
                assert "content_start_ms" in member
                assert "content_end_ms" in member
                assert "playback_start_ms" in member
                assert "playback_end_ms" in member

                # Playback window should be padded (larger than content window)
                assert member["playback_start_ms"] <= member["content_start_ms"]
                assert member["playback_end_ms"] >= member["content_end_ms"]

            # First member (1000-2000) should have VAD-snapped playback window
            first_member = next(m for m in members if m["content_start_ms"] == 1000)
            assert first_member["content_start_ms"] == 1000
            assert first_member["content_end_ms"] == 2000
            # VAD segment is 900-2100, so playback should extend to include it
            assert first_member["playback_start_ms"] <= 900
            assert first_member["playback_end_ms"] >= 2100
    finally:
        app.dependency_overrides.clear()
