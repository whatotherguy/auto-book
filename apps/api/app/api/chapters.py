from pathlib import Path
import json
import logging
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, delete, select

from ..db import get_session
from ..jobs import start_analysis_job
from ..models import AltTakeCluster, AltTakeMember, AnalysisJob, AudioSignal, Chapter, Issue, Project, ScoringResult, VadSegment
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


def delete_chapter_dependent_records(session: Session, chapter_id: int) -> None:
    """Delete all analysis-derived records for a chapter in FK-safe order.

    The Issue ↔ AltTakeCluster relationship is circular (each holds a nullable
    FK to the other), so we must null out ``AltTakeCluster.preferred_issue_id``
    before deleting ``Issue`` rows to avoid a foreign-key violation.
    """
    # ScoringResult references Issue — delete first.
    session.exec(delete(ScoringResult).where(ScoringResult.chapter_id == chapter_id))

    # AltTakeMember references both AltTakeCluster and Issue — delete before either.
    cluster_ids = session.exec(
        select(AltTakeCluster.id).where(AltTakeCluster.chapter_id == chapter_id)
    ).all()
    if cluster_ids:
        session.exec(delete(AltTakeMember).where(AltTakeMember.cluster_id.in_(cluster_ids)))

        # Break the circular FK: null out the reference from AltTakeCluster → Issue
        # so we can safely delete Issue rows below.
        for cluster in session.exec(
            select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id)
        ).all():
            if cluster.preferred_issue_id is not None:
                cluster.preferred_issue_id = None
                session.add(cluster)

    session.exec(delete(Issue).where(Issue.chapter_id == chapter_id))
    session.exec(delete(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id))
    session.exec(delete(AudioSignal).where(AudioSignal.chapter_id == chapter_id))
    session.exec(delete(VadSegment).where(VadSegment.chapter_id == chapter_id))
    session.exec(delete(AnalysisJob).where(AnalysisJob.chapter_id == chapter_id))


def reset_chapter_audio_review_state(session: Session, chapter: Chapter) -> None:
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

    clear_directory(dirs["working"])
    clear_directory(dirs["analysis"])
    clear_directory(dirs["exports"])

    delete_chapter_dependent_records(session, chapter.id)

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

    delete_chapter_dependent_records(session, chapter_id)
    session.delete(chapter)
    session.commit()

    delete_chapter_dirs(project_id, chapter_number)

    return {"ok": True, "deleted_chapter_id": chapter_id}


@router.post("/chapters/{chapter_id}/audio")
async def upload_audio(chapter_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    filename = Path(file.filename or "chapter.wav").name
    if Path(filename).suffix.lower() != ".wav":
        raise HTTPException(status_code=400, detail="Only .wav audio files are supported")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
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

    # Remove old source audio before moving the new file in.
    for existing_wav in dirs["source"].glob("*.wav"):
        existing_wav.unlink(missing_ok=True)

    target = dirs["source"] / filename
    shutil.move(str(temp_target), str(target))

    # Reset derived state only after the new file is safely in place —
    # avoids wiping state if the upload was bad.
    reset_chapter_audio_review_state(session, chapter)

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


@router.get("/chapters/{chapter_id}/audio-signals")
def get_audio_signals(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    signals = session.exec(
        select(AudioSignal).where(AudioSignal.chapter_id == chapter_id)
    ).all()
    return [s.model_dump() for s in signals]


@router.get("/chapters/{chapter_id}/vad-segments")
def get_vad_segments(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    segments = session.exec(
        select(VadSegment).where(VadSegment.chapter_id == chapter_id)
    ).all()
    return [s.model_dump() for s in segments]


@router.get("/chapters/{chapter_id}/alt-take-clusters")
def get_alt_take_clusters(chapter_id: int, session: Session = Depends(get_session)):
    from ..services.take_windows import compute_playback_window

    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    clusters = session.exec(
        select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id)
    ).all()
    if not clusters:
        return []

    # Batch-load all members for these clusters in one query instead of N queries.
    cluster_ids = [c.id for c in clusters]
    all_members = session.exec(
        select(AltTakeMember).where(AltTakeMember.cluster_id.in_(cluster_ids))
    ).all()
    members_by_cluster: dict[int, list] = {c.id: [] for c in clusters}
    for m in all_members:
        members_by_cluster[m.cluster_id].append(m)

    # Load issues and VAD segments to compute playback windows
    member_issue_ids = [m.issue_id for m in all_members]
    issues_by_id: dict[int, Issue] = {}
    if member_issue_ids:
        issues = session.exec(
            select(Issue).where(Issue.id.in_(member_issue_ids))
        ).all()
        issues_by_id = {i.id: i for i in issues}

    vad_segments = session.exec(
        select(VadSegment).where(VadSegment.chapter_id == chapter_id)
    ).all()
    vad_segment_dicts = [{"start_ms": s.start_ms, "end_ms": s.end_ms} for s in vad_segments]

    audio_duration_ms = chapter.duration_ms

    result = []
    for cluster in clusters:
        cluster_dict = cluster.model_dump()
        raw_members = members_by_cluster.get(cluster.id, [])

        # Compute playback windows for each member
        enriched_members = []
        for m in raw_members:
            member_dict = m.model_dump()
            issue = issues_by_id.get(m.issue_id)
            if issue:
                content_start = issue.start_ms
                content_end = issue.end_ms
                playback_start, playback_end = compute_playback_window(
                    content_start,
                    content_end,
                    vad_segments=vad_segment_dicts,
                    audio_duration_ms=audio_duration_ms,
                )
                member_dict["content_start_ms"] = content_start
                member_dict["content_end_ms"] = content_end
                member_dict["playback_start_ms"] = playback_start
                member_dict["playback_end_ms"] = playback_end
                member_dict["base_issue_type"] = issue.type
                member_dict["cluster_role"] = "alt_take_member"
            enriched_members.append(member_dict)

        cluster_dict["members"] = enriched_members
        cluster_dict["ranking"] = None
        result.append(cluster_dict)
    return result


@router.patch("/alt-take-clusters/{cluster_id}/preferred")
def set_preferred_take(
    cluster_id: int,
    payload: dict,
    session: Session = Depends(get_session),
):
    cluster = session.get(AltTakeCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Alt-take cluster not found")

    preferred_issue_id = payload.get("preferred_issue_id")
    if preferred_issue_id is None:
        raise HTTPException(status_code=400, detail="preferred_issue_id required")

    issue = session.get(Issue, preferred_issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    cluster.preferred_issue_id = preferred_issue_id
    session.add(cluster)

    # Update statuses: preferred -> rejected (keep in output), others -> approved (cut)
    members = session.exec(
        select(AltTakeMember).where(AltTakeMember.cluster_id == cluster_id)
    ).all()
    for member in members:
        member_issue = session.get(Issue, member.issue_id)
        if member_issue:
            if member.issue_id == preferred_issue_id:
                member_issue.status = "rejected"
            else:
                member_issue.status = "approved"
            session.add(member_issue)

    session.commit()
    session.refresh(cluster)
    return cluster.model_dump()


@router.get("/chapters/{chapter_id}/scoring-summary")
def get_scoring_summary(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    results = session.exec(
        select(ScoringResult).where(ScoringResult.chapter_id == chapter_id)
    ).all()

    envelopes = [r.model_dump() for r in results]

    # Load baseline from artifact if available
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    baseline_path = dirs["analysis"] / "scoring_result.json"
    baseline_stats = {}
    if baseline_path.exists():
        try:
            import json as _json
            data = _json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline_stats = data.get("baseline", {})
        except Exception:
            pass

    return {"envelopes": envelopes, "baseline_stats": baseline_stats}
