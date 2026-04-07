from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

from sqlmodel import Session, select

from ..models import Chapter, Issue
from .audio import probe_audio_metadata, read_wav_duration_ms

LONG_PAUSE_TARGET_MS = 300
MIN_KEEP_SEGMENT_MS = 100
CUTTABLE_ISSUE_TYPES = {
    "false_start",
    "repetition",
    "pickup_restart",
    "substitution",
    "long_pause",
    "pickup_candidate",
    "alt_take",
    "non_speech_marker",
}


def auto_approve_safe_cuts(
    session: Session,
    chapter_id: int,
    threshold: float = 0.8,
) -> int:
    """Auto-approve issues with safe_auto_cut recommendation above threshold."""
    from .scoring.pipeline import run_scoring_pipeline  # noqa: F401

    issues = session.exec(
        select(Issue).where(Issue.chapter_id == chapter_id)
    ).all()

    from ..models import ScoringResult
    import json

    approved_count = 0
    for issue in issues:
        scoring = session.exec(
            select(ScoringResult).where(ScoringResult.issue_id == issue.id)
        ).first()
        if not scoring or not scoring.recommendation_json:
            continue
        try:
            rec = json.loads(scoring.recommendation_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if rec.get("action") == "safe_auto_cut" and rec.get("confidence", 0) >= threshold:
            if issue.status != "approved":
                issue.status = "approved"
                session.add(issue)
                approved_count += 1

    if approved_count > 0:
        session.commit()
    return approved_count


def build_auto_edit_export(
    *,
    session: Session,
    chapter: Chapter,
    source_audio_path: Path,
    target_path: Path,
    auto_approve_threshold: float | None = None,
) -> Path:
    # Optionally auto-approve safe cuts before building the edit
    if auto_approve_threshold is not None:
        auto_approve_safe_cuts(session, chapter.id, auto_approve_threshold)

    approved_issues = session.exec(
        select(Issue).where(Issue.chapter_id == chapter.id, Issue.status == "approved")
    ).all()
    duration_ms = resolve_duration_ms(chapter, source_audio_path, approved_issues)
    cut_plan = build_cut_plan(approved_issues, duration_ms=duration_ms)

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if not cut_plan:
        shutil.copy2(source_audio_path, target_path)
        return target_path

    keep_segments = build_keep_segments(duration_ms, cut_plan)
    if not keep_segments:
        shutil.copy2(source_audio_path, target_path)
        return target_path

    return render_edit_export(source_audio_path, target_path, keep_segments)


def build_cut_plan(issues: Iterable[Issue], duration_ms: int) -> list[tuple[int, int]]:
    cuts: list[tuple[int, int]] = []

    for issue in issues:
        if getattr(issue, "status", None) != "approved":
            continue

        issue_type = getattr(issue, "type", "")
        is_alt_take_member = getattr(issue, "alt_take_cluster_id", None) is not None
        if issue_type not in CUTTABLE_ISSUE_TYPES and not is_alt_take_member:
            continue

        start_ms = max(0, int(getattr(issue, "start_ms", 0)))
        end_ms = max(start_ms, int(getattr(issue, "end_ms", start_ms)))
        if issue_type == "long_pause":
            cut_start, cut_end = trim_long_pause(start_ms, end_ms)
        else:
            cut_start, cut_end = start_ms, end_ms

        if cut_end > cut_start:
            cuts.append((cut_start, cut_end))

    if duration_ms > 0:
        cuts = clamp_ranges(cuts, duration_ms)

    return merge_ranges(sorted(cuts))


def resolve_duration_ms(chapter: Chapter, source_audio_path: Path, issues: Sequence[Issue]) -> int:
    if chapter.duration_ms is not None and chapter.duration_ms > 0:
        return chapter.duration_ms

    source_duration_ms = read_wav_duration_ms(source_audio_path)
    if source_duration_ms is not None and source_duration_ms > 0:
        return source_duration_ms

    issue_end_ms = max((max(0, int(getattr(issue, "end_ms", 0))) for issue in issues), default=0)
    return issue_end_ms


def trim_long_pause(start_ms: int, end_ms: int) -> tuple[int, int]:
    duration_ms = max(0, end_ms - start_ms)
    if duration_ms <= LONG_PAUSE_TARGET_MS:
        return start_ms, start_ms  # zero-width = no cut
    # Keep LONG_PAUSE_TARGET_MS of pause, split equally at each edge
    # to preserve breaths at the start and speech onset at the end.
    # Cut the center excess.
    keep_per_edge = LONG_PAUSE_TARGET_MS // 2
    cut_start = start_ms + keep_per_edge
    cut_end = end_ms - (LONG_PAUSE_TARGET_MS - keep_per_edge)
    return cut_start, cut_end


def build_keep_segments(duration_ms: int, cuts: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    if duration_ms <= 0:
        return []

    merged_cuts = merge_ranges(clamp_ranges(cuts, duration_ms))
    keep_segments: list[tuple[int, int]] = []
    cursor = 0

    for cut_start, cut_end in merged_cuts:
        if cut_start > cursor:
            keep_segments.append((cursor, cut_start))
        cursor = max(cursor, cut_end)

    if cursor < duration_ms:
        keep_segments.append((cursor, duration_ms))

    return [(start, end) for start, end in keep_segments if (end - start) >= MIN_KEEP_SEGMENT_MS]


def build_ffmpeg_output_args(source_audio_path: Path) -> list[str]:
    metadata = probe_audio_metadata(source_audio_path)
    codec_name = metadata.get("codec_name") or "pcm_s16le"
    sample_rate_hz = metadata.get("sample_rate_hz")
    channels = metadata.get("channels")

    args = ["-c:a", str(codec_name)]
    if sample_rate_hz:
        args.extend(["-ar", str(sample_rate_hz)])
    if channels:
        args.extend(["-ac", str(channels)])
    return args


def render_edit_export(source_audio_path: Path, target_path: Path, keep_segments: Sequence[tuple[int, int]]) -> Path:
    filter_parts: list[str] = []
    segment_labels: list[str] = []

    for index, (start_ms, end_ms) in enumerate(keep_segments):
        start_seconds = start_ms / 1000
        end_seconds = end_ms / 1000
        label = f"a{index}"
        filter_parts.append(
            f"[0:a]atrim=start={start_seconds:.3f}:end={end_seconds:.3f},asetpts=PTS-STARTPTS[{label}]"
        )
        segment_labels.append(label)

    if len(segment_labels) == 1:
        filter_complex = ";".join(filter_parts)
        output_label = segment_labels[0]
    else:
        chain_label = segment_labels[0]
        for index, next_label in enumerate(segment_labels[1:], start=1):
            next_chain_label = f"cf{index - 1}{index}"
            filter_parts.append(
                f"[{chain_label}][{next_label}]acrossfade=d=0.075:c1=tri:c2=tri[{next_chain_label}]"
            )
            chain_label = next_chain_label

        filter_complex = ";".join(filter_parts)
        output_label = chain_label

    filter_script_path: Path | None = None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as filter_script:
        filter_script.write(filter_complex)
        filter_script_path = Path(filter_script.name)

    try:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_audio_path),
            "-filter_script",
            str(filter_script_path),
            "-map",
            f"[{output_label}]",
            *build_ffmpeg_output_args(source_audio_path),
            str(target_path),
        ]

        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            raise ValueError(f"ffmpeg export failed: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}")
    finally:
        if filter_script_path is not None:
            filter_script_path.unlink(missing_ok=True)

    return target_path


def merge_ranges(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    cleaned = [(max(0, start), max(0, end)) for start, end in ranges if end > start]
    if not cleaned:
        return []

    cleaned.sort(key=lambda item: item[0])
    merged = [cleaned[0]]

    for start, end in cleaned[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def clamp_ranges(ranges: Sequence[tuple[int, int]], duration_ms: int) -> list[tuple[int, int]]:
    clamped: list[tuple[int, int]] = []
    for start, end in ranges:
        start_ms = min(max(0, start), duration_ms)
        end_ms = min(max(0, end), duration_ms)
        if end_ms > start_ms:
            clamped.append((start_ms, end_ms))
    return clamped
