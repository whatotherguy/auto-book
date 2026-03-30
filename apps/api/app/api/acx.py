import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Chapter
from ..services.acx import analyze_acx_audio
from ..services.ingest import write_json_artifact
from ..services.storage import ensure_chapter_dirs

router = APIRouter(tags=["acx"])


def resolve_chapter_audio_path(chapter: Chapter) -> Path | None:
    if chapter.audio_file_path:
        audio_path = Path(chapter.audio_file_path)
        if audio_path.exists():
            return audio_path

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    source_wavs = sorted(
        path for path in dirs["source"].iterdir() if path.is_file() and path.suffix.lower() == ".wav"
    )
    if source_wavs:
        return source_wavs[0]

    working_wavs = sorted(
        path for path in dirs["working"].iterdir() if path.is_file() and path.suffix.lower() == ".wav"
    )
    if working_wavs:
        return working_wavs[0]

    return None


@router.post("/chapters/{chapter_id}/acx-check")
def run_acx_check(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    audio_path = resolve_chapter_audio_path(chapter)
    if not audio_path:
        raise HTTPException(status_code=400, detail="Audio must be uploaded before running ACX preflight")

    resolved_value = str(audio_path.resolve())
    if chapter.audio_file_path != resolved_value:
        chapter.audio_file_path = resolved_value
        session.add(chapter)
        session.commit()
        session.refresh(chapter)

    try:
        report = analyze_acx_audio(audio_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    write_json_artifact(dirs["analysis"] / "acx_report.json", report)
    return report


@router.get("/chapters/{chapter_id}/acx-check")
def get_acx_check(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    report_path = dirs["analysis"] / "acx_report.json"
    if not report_path.exists():
        return None

    return json.loads(report_path.read_text(encoding="utf-8"))
