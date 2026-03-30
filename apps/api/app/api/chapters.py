from pathlib import Path
import json
import logging
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, delete, select

from ..db import get_session
from ..jobs import start_analysis_job
from ..models import AnalysisJob, Chapter, Issue, Project
from ..schemas import AnalyzeChapterRequest, AnalyzeResponse, ChapterCreate, ChapterTextUpdate
from ..services.audio import read_wav_duration_ms
from ..services.manuscript import extract_text_from_manuscript_file
from ..services.storage import clear_directory, delete_chapter_dirs, ensure_chapter_dirs

router = APIRouter(tags=["chapters"])
logger = logging.getLogger(__name__)


def resolve_chapter_audio_path(chapter: Chapter) -> Path | None:
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

    wav_files = [
        path
        for directory in (dirs["source"], dirs["working"])
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".wav"
    ]

    if not wav_files:
        return None

    if len(wav_files) == 1:
        return wav_files[0]

    if chapter.audio_file_path:
        audio_path = Path(chapter.audio_file_path)
        if audio_path.exists():
            return audio_path

    logger.warning(
        "Multiple WAV files found for chapter %s; falling back to most recently modified file.",
        chapter.id,
    )
    return max(wav_files, key=lambda path: path.stat().st_mtime)



def sync_chapter_audio_path(session: Session, chapter: Chapter) -> Path | None:
    audio_path = resolve_chapter_audio_path(chapter)
    resolved_value = str(audio_path.resolve()) if audio_path else None

    if chapter.audio_file_path != resolved_value:
        chapter.audio_file_path = resolved_value
        session.add(chapter)
        session.commit()
        session.refresh(chapter)

    return audio_path


def serialize_chapter(session: Session, chapter: Chapter) -> dict:
    audio_path = sync_chapter_audio_path(session, chapter)
    payload = chapter.model_dump()
    payload["has_audio"] = audio_path is not None
    analysis_path = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)["analysis"] / "transcript.raw.json"
    if analysis_path.exists():
        try:
            transcript_payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            transcript_payload = {}
        payload["transcript_source"] = transcript_payload.get("source")
        payload["transcript_warnings"] = transcript_payload.get("warnings") or []
        payload["transcription_mode"] = transcript_payload.get("transcription_mode")
        payload["transcription_profile"] = transcript_payload.get("profile")
        payload["transcription_model"] = transcript_payload.get("model")
        payload["analysis_artifact_updated_at"] = int(analysis_path.stat().st_mtime * 1000)
    else:
        payload["transcript_source"] = None
        payload["transcript_warnings"] = []
        payload["transcription_mode"] = None
        payload["transcription_profile"] = None
        payload["transcription_model"] = None
        payload["analysis_artifact_updated_at"] = None
    return payload


def reset_chapter_audio_review_state(session: Session, chapter: Chapter) -> None:
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

    for existing_wav in dirs["source"].glob("*.wav"):
        existing_wav.unlink(missing_ok=True)

    clear_directory(dirs["working"])
    clear_directory(dirs["analysis"])
    clear_directory(dirs["exports"])

    session.exec(delete(Issue).where(Issue.chapter_id == chapter.id))
    session.exec(delete(AnalysisJob).where(AnalysisJob.chapter_id == chapter.id))

    chapter.normalized_text = ""
    chapter.status = "new"
    session.add(chapter)


@router.post("/projects/{project_id}/chapters")
def create_chapter(project_id: int, payload: ChapterCreate, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == payload.chapter_number,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Chapter number already exists for this project")

    chapter = Chapter(
        project_id=project_id,
        chapter_number=payload.chapter_number,
        title=payload.title,
        status="new",
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    ensure_chapter_dirs(project_id, payload.chapter_number)
    return chapter


@router.get("/projects/{project_id}/chapters")
def list_project_chapters(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    statement = select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
    return [serialize_chapter(session, chapter) for chapter in session.exec(statement).all()]


@router.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return serialize_chapter(session, chapter)


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    project_id = chapter.project_id
    chapter_number = chapter.chapter_number

    session.exec(delete(Issue).where(Issue.chapter_id == chapter_id))
    session.exec(delete(AnalysisJob).where(AnalysisJob.chapter_id == chapter_id))
    session.delete(chapter)
    session.commit()

    delete_chapter_dirs(project_id, chapter_number)

    return {"ok": True, "deleted_chapter_id": chapter_id}


@router.post("/chapters/{chapter_id}/audio")
async def upload_audio(chapter_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    filename = Path(file.filename or "chapter.wav").name
    if Path(filename).suffix.lower() != ".wav":
        raise HTTPException(status_code=400, detail="Only .wav audio files are supported")

    temp_target = dirs["working"] / f".upload-{filename}"
    total_size = 0
    with temp_target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            fh.write(chunk)

    if total_size == 0:
        temp_target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded WAV file is empty")

    try:
        duration_ms = read_wav_duration_ms(temp_target)
    except ValueError as exc:
        temp_target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reset_chapter_audio_review_state(session, chapter)

    target = dirs["source"] / filename
    shutil.move(str(temp_target), str(target))

    chapter.audio_file_path = str(target.resolve())
    chapter.duration_ms = duration_ms
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    payload = serialize_chapter(session, chapter)
    payload["ok"] = True
    return payload


@router.get("/chapters/{chapter_id}/audio-file")
def get_audio_file(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    audio_path = sync_chapter_audio_path(session, chapter)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not uploaded")

    return FileResponse(path=audio_path, filename=audio_path.name, media_type="audio/wav")


@router.get("/chapters/{chapter_id}/spoken-tokens")
def get_spoken_tokens(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    path = dirs["analysis"] / "spoken_tokens.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Spoken tokens not available — run analysis first")

    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/chapters/{chapter_id}/alignment")
def get_alignment(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    path = dirs["analysis"] / "alignment.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Alignment data not available — run analysis first")

    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/chapters/{chapter_id}/text")
def upload_text(chapter_id: int, payload: ChapterTextUpdate, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    target = dirs["source"] / "chapter.txt"
    target.write_text(payload.raw_text, encoding="utf-8")

    chapter.raw_text = payload.raw_text
    chapter.text_file_path = str(target.resolve())
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter


@router.post("/chapters/{chapter_id}/text-file")
async def upload_text_file(chapter_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="Manuscript file is required")

    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".pdf"}:
        raise HTTPException(status_code=400, detail="Only .txt and .pdf manuscript files are supported")

    file_bytes = await file.read()
    try:
        extracted_text, _metadata = extract_text_from_manuscript_file(filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to extract manuscript text: {exc}") from exc

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    source_target = dirs["source"] / filename
    source_target.write_bytes(file_bytes)

    extracted_target = dirs["source"] / "chapter.txt"
    extracted_target.write_text(extracted_text, encoding="utf-8")

    chapter.raw_text = extracted_text
    chapter.text_file_path = str(extracted_target.resolve())
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter


@router.post("/chapters/{chapter_id}/analyze", response_model=AnalyzeResponse)
def analyze_chapter(
    chapter_id: int,
    payload: AnalyzeChapterRequest,
    session: Session = Depends(get_session),
):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    sync_chapter_audio_path(session, chapter)

    if not chapter.audio_file_path:
        raise HTTPException(status_code=400, detail="Audio must be uploaded before running analysis")
    if not chapter.raw_text or not chapter.raw_text.strip():
        raise HTTPException(status_code=400, detail="Manuscript text must be provided before running analysis")

    job = AnalysisJob(chapter_id=chapter_id, status="queued", progress=0)
    session.add(job)
    session.commit()
    session.refresh(job)

    start_analysis_job(job.id, transcription_mode=payload.transcription_mode, force_retranscribe=payload.force_retranscribe, enable_llm_triage=payload.enable_llm_triage)

    return AnalyzeResponse(job_id=job.id, status=job.status)
