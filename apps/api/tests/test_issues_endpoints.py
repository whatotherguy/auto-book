"""Tests for the issue stats and batch-update endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app
from app.models import Issue


def _make_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    return engine


def _setup_client(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    return TestClient(app), engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_chapter(client):
    project = client.post("/projects", json={"name": "P"}).json()
    chapter = client.post(
        f"/projects/{project['id']}/chapters",
        json={"chapter_number": 1, "title": "C"},
    ).json()
    return chapter["id"]


# ---------------------------------------------------------------------------
# GET /chapters/{id}/issues/stats
# ---------------------------------------------------------------------------


def test_issue_stats_empty_chapter(tmp_path, monkeypatch):
    client, _ = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)
        resp = client.get(f"/chapters/{chapter_id}/issues/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["reviewed"] == 0
        assert data["by_status"] == {}
        assert data["by_type"] == {}
        assert data["by_confidence"] == {"high": 0, "medium": 0, "low": 0}
    finally:
        app.dependency_overrides.clear()


def test_issue_stats_counts_correctly(tmp_path, monkeypatch):
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            session.add(Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.90, status="approved"))
            session.add(Issue(chapter_id=chapter_id, type="repetition", start_ms=200, end_ms=300, confidence=0.75, status="rejected"))
            session.add(Issue(chapter_id=chapter_id, type="false_start", start_ms=400, end_ms=500, confidence=0.50, status="needs_manual"))
            session.commit()

        resp = client.get(f"/chapters/{chapter_id}/issues/stats")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        assert data["reviewed"] == 2  # approved + rejected
        assert data["by_status"]["approved"] == 1
        assert data["by_status"]["rejected"] == 1
        assert data["by_status"]["needs_manual"] == 1
        assert data["by_type"]["repetition"] == 2
        assert data["by_type"]["false_start"] == 1
        assert data["by_confidence"]["high"] == 1
        assert data["by_confidence"]["medium"] == 1
        assert data["by_confidence"]["low"] == 1
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /issues/batch-update
# ---------------------------------------------------------------------------


def test_batch_update_status(tmp_path, monkeypatch):
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            i1 = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9, status="needs_manual")
            i2 = Issue(chapter_id=chapter_id, type="false_start", start_ms=200, end_ms=300, confidence=0.8, status="needs_manual")
            session.add_all([i1, i2])
            session.commit()
            session.refresh(i1)
            session.refresh(i2)
            ids = [i1.id, i2.id]

        resp = client.post("/issues/batch-update", json={"issue_ids": ids, "status": "approved"})
        assert resp.status_code == 200
        updated = resp.json()
        assert len(updated) == 2
        assert all(u["status"] == "approved" for u in updated)
    finally:
        app.dependency_overrides.clear()


def test_batch_update_note(tmp_path, monkeypatch):
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        resp = client.post("/issues/batch-update", json={"issue_ids": [issue_id], "note": "Check this one"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated[0]["note"] == "Check this one"
    finally:
        app.dependency_overrides.clear()


def test_batch_update_missing_ids_returns_404(tmp_path, monkeypatch):
    client, _ = _setup_client(tmp_path, monkeypatch)
    try:
        resp = client.post("/issues/batch-update", json={"issue_ids": [99999], "status": "approved"})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_batch_update_no_fields_returns_422(tmp_path, monkeypatch):
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        resp = client.post("/issues/batch-update", json={"issue_ids": [issue_id]})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_batch_update_empty_ids_returns_422(tmp_path, monkeypatch):
    client, _ = _setup_client(tmp_path, monkeypatch)
    try:
        resp = client.post("/issues/batch-update", json={"issue_ids": [], "status": "approved"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
