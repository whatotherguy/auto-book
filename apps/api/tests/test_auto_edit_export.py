from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.export import (
    LONG_PAUSE_TARGET_MS,
    build_cut_plan,
    build_ffmpeg_output_args,
    build_keep_segments,
)


def make_issue(issue_type: str, start_ms: int, end_ms: int, status: str = "approved"):
    return SimpleNamespace(type=issue_type, start_ms=start_ms, end_ms=end_ms, status=status)


def test_build_cut_plan_uses_only_approved_cuttable_issues():
    issues = [
        make_issue("repetition", 1_000, 2_000),
        make_issue("missing_text", 2_500, 3_000),
        make_issue("false_start", 4_000, 4_500, status="rejected"),
        make_issue("pickup_restart", 5_000, 6_000),
    ]

    cut_plan = build_cut_plan([issue for issue in issues if issue.status == "approved"], duration_ms=10_000)

    assert cut_plan == [(1_000, 2_000), (5_000, 6_000)]


def test_build_cut_plan_trims_long_pauses_to_target_duration():
    issues = [make_issue("long_pause", 2_000, 4_000)]

    cut_plan = build_cut_plan(issues, duration_ms=10_000)

    kept_pause_ms = LONG_PAUSE_TARGET_MS
    assert cut_plan == [(2_150, 3_850)]
    assert (4_000 - 2_000) - (cut_plan[0][1] - cut_plan[0][0]) == kept_pause_ms


def test_build_keep_segments_returns_complement_of_cuts():
    segments = build_keep_segments(10_000, [(1_000, 2_000), (4_000, 4_500)])

    assert segments == [(0, 1_000), (2_000, 4_000), (4_500, 10_000)]


def test_build_ffmpeg_output_args_preserves_source_audio_format():
    with patch("app.services.export.probe_audio_metadata") as probe_audio_metadata:
        probe_audio_metadata.return_value = {
            "codec_name": "pcm_s24le",
            "sample_format": "s32",
            "sample_rate_hz": 48_000,
            "channels": 2,
            "bit_depth": 24,
            "duration_ms": 10_000,
        }

        args = build_ffmpeg_output_args(Path("chapter.wav"))

    assert args == ["-c:a", "pcm_s24le", "-ar", "48000", "-ac", "2"]
