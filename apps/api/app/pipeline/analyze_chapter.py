from __future__ import annotations

import logging

from sqlmodel import Session

from ..models import AnalysisJob, Chapter

logger = logging.getLogger(__name__)
from ..services.align import build_alignment, build_manuscript_tokens, build_spoken_tokens
from ..services.alt_takes import detect_alt_takes
from ..services.audio import read_wav_duration_ms
from ..services.audio_analysis import analyze_audio_signals
from ..services.detect import build_issue_records, persist_issue_models
from ..services.ingest import prepare_working_audio_copy, write_json_artifact
from ..services.prosody import extract_prosody
from ..services.signal_fusion import enrich_issues
from ..services.storage import ensure_chapter_dirs
from ..services.text_normalize import normalize_text
from ..services.transcribe import transcribe_with_whisperx
from ..services.vad import run_vad


def set_job_progress(session: Session, job: AnalysisJob, progress: int, step: str) -> None:
    job.status = "running"
    job.progress = progress
    job.current_step = step
    session.add(job)
    session.commit()


def make_transcribe_progress_callback(session: Session, job: AnalysisJob):
    def callback(step: str, progress: int, message: str) -> None:
        job.status = "running"
        job.progress = progress
        job.current_step = step
        job.error_message = None
        session.add(job)
        session.commit()

    return callback


def run_analysis(
    session: Session,
    chapter: Chapter,
    job: AnalysisJob,
    transcription_mode: str = "optimized",
    force_retranscribe: bool = False,
    cancel_check: callable = None,
    enable_llm_triage: bool = True,
) -> None:
    from ..jobs import JobCancelledError

    def check_cancelled() -> None:
        if cancel_check and cancel_check():
            raise JobCancelledError("Job cancelled by user")

    try:
        dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

        set_job_progress(session, job, 10, "prepare_inputs")
        check_cancelled()

        working_audio_path = prepare_working_audio_copy(chapter.audio_file_path, dirs["working"])
        chapter.duration_ms = read_wav_duration_ms(working_audio_path)
        chapter.normalized_text = normalize_text(chapter.raw_text)
        session.add(chapter)
        session.commit()

        manuscript_tokens = build_manuscript_tokens(chapter.raw_text)
        write_json_artifact(dirs["analysis"] / "manuscript_tokens.json", manuscript_tokens)

        set_job_progress(session, job, 35, "transcribe")
        check_cancelled()

        cache_path = dirs["analysis"] / "transcript.raw.json" if not force_retranscribe else None
        transcript = transcribe_with_whisperx(
            working_audio_path,
            manuscript_text=chapter.raw_text,
            duration_ms=chapter.duration_ms,
            progress_callback=make_transcribe_progress_callback(session, job),
            transcription_mode=transcription_mode,
            cache_path=cache_path,
            cancel_check=cancel_check,
        )
        write_json_artifact(dirs["analysis"] / "transcript.raw.json", transcript)

        if transcript.get("is_placeholder") is True:
            job.status = "failed"
            job.error_message = (
                "Transcription unavailable: WhisperX/faster-whisper is not installed. Install it to run analysis."
            )
            session.add(job)
            session.commit()
            return

        check_cancelled()

        spoken_tokens = build_spoken_tokens(transcript)
        write_json_artifact(dirs["analysis"] / "spoken_tokens.json", spoken_tokens)

        set_job_progress(session, job, 60, "align")
        check_cancelled()

        alignment = build_alignment(manuscript_tokens, spoken_tokens)
        write_json_artifact(dirs["analysis"] / "alignment.json", alignment)

        # === Signal Extraction (Layer 0) ===
        set_job_progress(session, job, 60, "audio_analysis")
        check_cancelled()
        audio_signals = analyze_audio_signals(working_audio_path)
        write_json_artifact(dirs["analysis"] / "audio_signals.json", audio_signals)

        set_job_progress(session, job, 63, "vad")
        check_cancelled()
        vad_segments = run_vad(working_audio_path)
        write_json_artifact(dirs["analysis"] / "vad_segments.json", vad_segments)

        set_job_progress(session, job, 66, "prosody")
        check_cancelled()
        prosody_map = extract_prosody(working_audio_path, spoken_tokens)
        write_json_artifact(dirs["analysis"] / "prosody_features.json", prosody_map)

        # === Issue Detection (extended) ===
        set_job_progress(session, job, 70, "detect_issues")
        check_cancelled()

        issue_records = build_issue_records(
            chapter=chapter,
            transcript=transcript,
            manuscript_tokens=manuscript_tokens,
            spoken_tokens=spoken_tokens,
            alignment=alignment,
            audio_signals=audio_signals,
            vad_segments=vad_segments,
            prosody_map=prosody_map,
        )

        # === Signal Fusion (Layer 1) ===
        set_job_progress(session, job, 74, "signal_fusion")
        check_cancelled()
        issue_records = enrich_issues(
            issue_records, audio_signals, vad_segments,
            prosody_map, spoken_tokens, manuscript_tokens, alignment,
        )

        # === Alt-Take Clustering (Layer 2) ===
        set_job_progress(session, job, 77, "alt_take_clustering")
        check_cancelled()
        alt_take_clusters = detect_alt_takes(
            issue_records, manuscript_tokens, spoken_tokens,
            alignment, prosody_map,
        )
        write_json_artifact(dirs["analysis"] / "alt_take_clusters.json", alt_take_clusters)

        # === Scoring Engine (Layer 3) ===
        set_job_progress(session, job, 80, "scoring")
        check_cancelled()
        from ..services.scoring.pipeline import run_scoring_pipeline
        scoring_result = run_scoring_pipeline(
            issue_records=issue_records,
            audio_signals=audio_signals,
            vad_segments=vad_segments,
            prosody_map=prosody_map,
            manuscript_tokens=manuscript_tokens,
            spoken_tokens=spoken_tokens,
            alignment=alignment,
            alt_take_clusters=alt_take_clusters,
            chapter=chapter,
            session=session,
        )
        issue_records = scoring_result["enriched_issues"]
        alt_take_clusters = scoring_result["alt_take_clusters"]
        write_json_artifact(dirs["analysis"] / "scoring_result.json", scoring_result)

        # Optional LLM triage to filter false positives
        if enable_llm_triage:
            from ..services.triage import is_triage_available, triage_issues

            if is_triage_available():
                set_job_progress(session, job, 85, "triage_issues")
                check_cancelled()
                try:
                    issue_records = triage_issues(issue_records, chapter.raw_text)
                except Exception as exc:
                    logger.warning("LLM triage failed, continuing without: %s", exc)

        write_json_artifact(dirs["analysis"] / "issues.json", issue_records)

        persist_issue_models(session, chapter.id, issue_records)

        # Resolve issue_ids in alt_take_clusters now that issues have DB ids.
        # detect_alt_takes runs before persistence, so members only have issue_index.
        for cluster in alt_take_clusters:
            for member in cluster.get("members", []):
                idx = member.get("issue_index")
                if idx is not None and idx < len(issue_records):
                    member["issue_id"] = issue_records[idx].get("id")

        _persist_signal_data(session, chapter.id, audio_signals, vad_segments, alt_take_clusters, scoring_result)

        chapter.status = "review"
        session.add(chapter)
        session.commit()

        job.status = "completed"
        job.progress = 100
        job.current_step = "done"
        session.add(job)
        session.commit()
    finally:
        try:
            if job.status == "running":
                session.rollback()
                chapter.status = "new"
                job.status = "failed"
                job.error_message = job.error_message or "Analysis did not complete."
                session.add(chapter)
                session.add(job)
                session.commit()
        except Exception as cleanup_exc:
            logger.warning("Failed to update job status in finally block: %s", cleanup_exc)


def _persist_signal_data(
    session: Session,
    chapter_id: int,
    audio_signals: list,
    vad_segments: list,
    alt_take_clusters: list,
    scoring_result: dict,
) -> None:
    """Persist audio signals, VAD segments, alt-take clusters, and scoring results."""
    from ..models import AudioSignal, VadSegment, AltTakeCluster, AltTakeMember, ScoringResult
    import json

    # Persist audio signals
    for sig in audio_signals:
        session.add(AudioSignal(
            chapter_id=chapter_id,
            signal_type=sig.get("signal_type", ""),
            start_ms=sig.get("start_ms", 0),
            end_ms=sig.get("end_ms", 0),
            confidence=sig.get("confidence", 0.0),
            rms_db=sig.get("rms_db"),
            spectral_centroid_hz=sig.get("spectral_centroid_hz"),
            zero_crossing_rate=sig.get("zero_crossing_rate"),
            onset_strength=sig.get("onset_strength"),
            bandwidth_hz=sig.get("bandwidth_hz"),
            note=sig.get("note"),
        ))

    # Persist VAD segments
    for seg in vad_segments:
        session.add(VadSegment(
            chapter_id=chapter_id,
            start_ms=seg.get("start_ms", 0),
            end_ms=seg.get("end_ms", 0),
            speech_probability=seg.get("speech_probability", 0.0),
        ))

    # Persist alt-take clusters
    for cluster in alt_take_clusters:
        db_cluster = AltTakeCluster(
            chapter_id=chapter_id,
            manuscript_start_idx=cluster.get("manuscript_start_idx", 0),
            manuscript_end_idx=cluster.get("manuscript_end_idx", 0),
            manuscript_text=cluster.get("manuscript_text", ""),
            preferred_issue_id=cluster.get("preferred_issue_id"),
            confidence=cluster.get("confidence", 0.0),
        )
        session.add(db_cluster)
        session.flush()
        for member in cluster.get("members", []):
            session.add(AltTakeMember(
                cluster_id=db_cluster.id,
                issue_id=member.get("issue_id", 0),
                take_order=member.get("take_order", 0),
            ))

    # Persist scoring results
    for envelope in scoring_result.get("envelopes", []):
        session.add(ScoringResult(
            issue_id=envelope.get("issue_id", 0),
            chapter_id=chapter_id,
            scoring_version=envelope.get("scoring_version", "1.0.0"),
            composite_scores_json=json.dumps(envelope.get("composite_scores", {})),
            detector_outputs_json=json.dumps(envelope.get("detector_outputs", {})),
            recommendation_json=json.dumps(envelope.get("recommendation", {})),
            derived_features_json=json.dumps(envelope.get("derived_features", {})),
            mistake_score=envelope.get("mistake_score", 0.0),
            pickup_score=envelope.get("pickup_score", 0.0),
            performance_score=envelope.get("performance_score", 0.0),
            splice_score=envelope.get("splice_score", 0.0),
            priority=envelope.get("priority", "info"),
            baseline_id=envelope.get("baseline_id", ""),
        ))

    session.commit()
