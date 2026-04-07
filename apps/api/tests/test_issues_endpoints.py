"""Tests for the issue stats and batch-update endpoints."""

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
        # New v2 fields
        assert data["by_review_state"] == {}
        assert data["by_editor_decision"] == {}
        assert data["by_model_action"] == {}
    finally:
        app.dependency_overrides.clear()


def test_issue_stats_counts_correctly(tmp_path, monkeypatch):
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            session.add(Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.90, status="approved", review_state="reviewed"))
            session.add(Issue(chapter_id=chapter_id, type="repetition", start_ms=200, end_ms=300, confidence=0.75, status="rejected", review_state="reviewed"))
            session.add(Issue(chapter_id=chapter_id, type="false_start", start_ms=400, end_ms=500, confidence=0.50, status="needs_manual", review_state="unreviewed"))
            session.commit()

        resp = client.get(f"/chapters/{chapter_id}/issues/stats")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        assert data["reviewed"] == 2  # review_state == "reviewed"
        assert data["by_status"]["approved"] == 1
        assert data["by_status"]["rejected"] == 1
        assert data["by_status"]["needs_manual"] == 1
        assert data["by_type"]["repetition"] == 2
        assert data["by_type"]["false_start"] == 1
        assert data["by_confidence"]["high"] == 1
        assert data["by_confidence"]["medium"] == 1
        assert data["by_confidence"]["low"] == 1
        # New v2 fields
        assert data["by_review_state"]["reviewed"] == 2
        assert data["by_review_state"]["unreviewed"] == 1
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


def test_batch_update_editor_decision(tmp_path, monkeypatch):
    """Test batch update with new v2 editor_decision field."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            i1 = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            i2 = Issue(chapter_id=chapter_id, type="false_start", start_ms=200, end_ms=300, confidence=0.8)
            session.add_all([i1, i2])
            session.commit()
            session.refresh(i1)
            session.refresh(i2)
            ids = [i1.id, i2.id]

        resp = client.post("/issues/batch-update", json={"issue_ids": ids, "editor_decision": "cut"})
        assert resp.status_code == 200
        updated = resp.json()
        assert len(updated) == 2
        assert all(u["editor_decision"] == "cut" for u in updated)
        # Setting editor_decision should automatically set review_state to reviewed
        assert all(u["review_state"] == "reviewed" for u in updated)
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


# ---------------------------------------------------------------------------
# PATCH /issues/{id} - single issue update
# ---------------------------------------------------------------------------


def test_update_issue_editor_decision(tmp_path, monkeypatch):
    """Test single issue update with new v2 editor_decision field."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        resp = client.patch(f"/issues/{issue_id}", json={"editor_decision": "keep"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["editor_decision"] == "keep"
        assert updated["review_state"] == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_update_issue_review_state(tmp_path, monkeypatch):
    """Test single issue update with review_state field."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        # First verify default is unreviewed
        with Session(engine) as session:
            assert session.get(Issue, issue_id).review_state == "unreviewed"

        resp = client.patch(f"/issues/{issue_id}", json={"review_state": "reviewed"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["review_state"] == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_update_issue_needs_review_decision(tmp_path, monkeypatch):
    """Test the needs_review decision value."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        resp = client.patch(f"/issues/{issue_id}", json={"editor_decision": "needs_review"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["editor_decision"] == "needs_review"
        # Even needs_review is a decision, so review_state becomes reviewed
        assert updated["review_state"] == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_editor_decision_overrides_review_state_in_same_payload(tmp_path, monkeypatch):
    """Verify precedence: when both review_state and editor_decision are in the same payload,
    editor_decision should win by forcing review_state='reviewed'."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            issue = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        # Send both review_state=unreviewed AND editor_decision=cut in the same request
        # editor_decision should override, resulting in review_state="reviewed"
        resp = client.patch(f"/issues/{issue_id}", json={"editor_decision": "cut", "review_state": "unreviewed"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["editor_decision"] == "cut"
        # editor_decision always implies reviewed, overriding the explicit review_state=unreviewed
        assert updated["review_state"] == "reviewed"

        # Also test batch update with the same conflict
        with Session(engine) as session:
            issue2 = Issue(chapter_id=chapter_id, type="false_start", start_ms=200, end_ms=300, confidence=0.8)
            session.add(issue2)
            session.commit()
            session.refresh(issue2)
            issue2_id = issue2.id

        resp = client.post("/issues/batch-update", json={
            "issue_ids": [issue2_id],
            "editor_decision": "keep",
            "review_state": "unreviewed"
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated[0]["editor_decision"] == "keep"
        assert updated[0]["review_state"] == "reviewed"
    finally:
        app.dependency_overrides.clear()


def test_legacy_status_does_not_overwrite_editor_decision(tmp_path, monkeypatch):
    """Verify that legacy status writes do NOT silently overwrite an existing editor_decision.
    The editor_decision should remain intact when legacy status is updated."""
    client, engine = _setup_client(tmp_path, monkeypatch)
    try:
        chapter_id = _create_chapter(client)

        with Session(engine) as session:
            # Create issue with explicit editor_decision already set
            issue = Issue(
                chapter_id=chapter_id,
                type="repetition",
                start_ms=0,
                end_ms=100,
                confidence=0.9,
                editor_decision="cut",
                review_state="reviewed"
            )
            session.add(issue)
            session.commit()
            session.refresh(issue)
            issue_id = issue.id

        # Update via legacy status field - should NOT clear editor_decision
        resp = client.patch(f"/issues/{issue_id}", json={"status": "approved"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["status"] == "approved"
        # editor_decision must remain intact
        assert updated["editor_decision"] == "cut"
        # review_state should be "reviewed" (both from editor_decision and status=approved mapping)
        assert updated["review_state"] == "reviewed"

        # Test with status that maps to unreviewed - editor_decision should still remain
        with Session(engine) as session:
            issue2 = Issue(
                chapter_id=chapter_id,
                type="false_start",
                start_ms=200,
                end_ms=300,
                confidence=0.8,
                editor_decision="keep",
                review_state="reviewed"
            )
            session.add(issue2)
            session.commit()
            session.refresh(issue2)
            issue2_id = issue2.id

        resp = client.patch(f"/issues/{issue2_id}", json={"status": "needs_manual"})
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["status"] == "needs_manual"
        # editor_decision must remain intact - legacy status should not clear it
        assert updated["editor_decision"] == "keep"
        # review_state might be "unreviewed" from legacy mapping, which is okay
        # The key is editor_decision is NOT touched
    finally:
        app.dependency_overrides.clear()
