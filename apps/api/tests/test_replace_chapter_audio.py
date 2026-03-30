import io
import wave

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import get_session
from app.main import app
from app.models import AnalysisJob, Chapter, Issue
from app.services.storage import ensure_chapter_dirs


def build_wav_bytes(seconds: float) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(44100)
        frame_count = int(44100 * seconds)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def test_reuploading_chapter_audio_resets_stale_review_state(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    try:
        with TestClient(app) as client:
            project_response = client.post("/projects", json={"name": "Replacement Test"})
            assert project_response.status_code == 200
            project_id = project_response.json()["id"]

            chapter_response = client.post(
                f"/projects/{project_id}/chapters",
                json={"chapter_number": 3, "title": "Test Chapter"},
            )
            assert chapter_response.status_code == 200
            chapter_id = chapter_response.json()["id"]

            first_upload = client.post(
                f"/chapters/{chapter_id}/audio",
                files={"file": ("take-1.wav", build_wav_bytes(1.0), "audio/wav")},
            )
            assert first_upload.status_code == 200

            with Session(engine) as session:
                chapter = session.get(Chapter, chapter_id)
                assert chapter is not None
                dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

                session.add(
                    Issue(
                        chapter_id=chapter_id,
                        type="repetition",
                        start_ms=100,
                        end_ms=250,
                        confidence=0.9,
                    )
                )
                session.add(AnalysisJob(chapter_id=chapter_id, status="completed", progress=100))
                chapter.status = "review"
                chapter.normalized_text = "stale normalized text"
                session.add(chapter)
                session.commit()

                (dirs["analysis"] / "issues.json").write_text("{}", encoding="utf-8")
                (dirs["exports"] / "issues.json").write_text("{}", encoding="utf-8")
                (dirs["working"] / "working-copy.wav").write_bytes(build_wav_bytes(0.5))

            second_upload = client.post(
                f"/chapters/{chapter_id}/audio",
                files={"file": ("take-2.wav", build_wav_bytes(2.0), "audio/wav")},
            )
            assert second_upload.status_code == 200
            payload = second_upload.json()
            assert payload["ok"] is True
            assert payload["status"] == "new"
            assert payload["duration_ms"] >= 1900
            assert payload["audio_file_path"].endswith("take-2.wav")

            with Session(engine) as session:
                chapter = session.get(Chapter, chapter_id)
                assert chapter is not None
                dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

                assert session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AnalysisJob).where(AnalysisJob.chapter_id == chapter_id)).all() == []
                assert chapter.normalized_text == ""
                assert chapter.status == "new"
                assert not (dirs["source"] / "take-1.wav").exists()
                assert (dirs["source"] / "take-2.wav").exists()
                assert list(dirs["analysis"].iterdir()) == []
                assert list(dirs["exports"].iterdir()) == []
                assert list(dirs["working"].iterdir()) == []
    finally:
        app.dependency_overrides.clear()
