"""RawFeatureCatalog extraction — build feature dict per issue for scoring."""

from __future__ import annotations

import json
from typing import Any, Sequence


def extract_raw_features(
    issue: dict[str, Any],
    issue_index: int,
    spoken_tokens: Sequence,
    manuscript_tokens: Sequence,
    alignment: dict[str, Any],
    prosody_map: list[dict[str, Any]],
    audio_signals: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
    total_issues: int,
) -> dict[str, Any]:
    """Extract the RawFeatureCatalog for a single issue."""
    features: dict[str, Any] = {}

    # Basic issue features
    features["issue_type"] = issue.get("type", "")
    features["confidence"] = issue.get("confidence", 0.0)
    features["start_ms"] = issue.get("start_ms", 0)
    features["end_ms"] = issue.get("end_ms", 0)
    features["duration_ms"] = features["end_ms"] - features["start_ms"]
    features["expected_text"] = issue.get("expected_text", "")
    features["spoken_text"] = issue.get("spoken_text", "")

    # Alignment operation
    features["alignment_op"] = _get_alignment_op(issue, alignment)

    # Text features
    expected = features["expected_text"]
    spoken = features["spoken_text"]
    expected_words = expected.split() if expected else []
    spoken_words = spoken.split() if spoken else []
    features["expected_word_count"] = len(expected_words)
    features["spoken_word_count"] = len(spoken_words)
    features["word_count_ratio"] = len(spoken_words) / max(1, len(expected_words))

    # Audio features from enrichment
    try:
        audio_features = json.loads(issue.get("audio_features_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        audio_features = {}
    features["rms_db"] = audio_features.get("rms_db", 0.0)
    features["spectral_centroid_hz"] = audio_features.get("spectral_centroid_hz", 0.0)
    features["zero_crossing_rate"] = audio_features.get("zero_crossing_rate", 0.0)
    features["onset_strength_max"] = audio_features.get("onset_strength_max", 0.0)
    features["onset_strength_mean"] = audio_features.get("onset_strength_mean", 0.0)
    features["bandwidth_hz"] = audio_features.get("bandwidth_hz", 0.0)
    features["crest_factor"] = audio_features.get("crest_factor", 0.0)

    # Audio signal flags
    try:
        signal_flags = json.loads(issue.get("audio_signals_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        signal_flags = {}
    features["has_click_marker"] = signal_flags.get("has_click_marker", False)
    features["click_marker_confidence"] = signal_flags.get("click_marker_confidence", 0.0)
    features["has_abrupt_cutoff"] = signal_flags.get("has_abrupt_cutoff", False)
    features["has_silence_gap"] = signal_flags.get("has_silence_gap", False)
    features["silence_gap_ms"] = signal_flags.get("silence_gap_ms", 0)
    features["has_onset_burst"] = signal_flags.get("has_onset_burst", False)
    features["restart_pattern_detected"] = signal_flags.get("restart_pattern_detected", False)

    # Prosody features
    try:
        prosody = json.loads(issue.get("prosody_features_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        prosody = {}
    features["speech_rate_wps"] = prosody.get("speech_rate_wps", 0.0)
    features["f0_mean_hz"] = prosody.get("f0_mean_hz")
    features["f0_std_hz"] = prosody.get("f0_std_hz")
    features["f0_contour"] = prosody.get("f0_contour", [])
    features["energy_contour"] = prosody.get("energy_contour", [])
    features["pause_before_ms"] = prosody.get("pause_before_ms", 0)
    features["pause_after_ms"] = prosody.get("pause_after_ms", 0)

    # Context features
    features["is_first_sentence"] = issue_index == 0
    features["is_last_sentence"] = issue_index == total_issues - 1

    # Whisper confidence (if available)
    features["whisper_word_confidence"] = issue.get("whisper_word_confidence", 1.0)

    return features


def _get_alignment_op(issue: dict[str, Any], alignment: dict[str, Any]) -> str:
    """Get the alignment operation for the issue's time range."""
    matches = alignment.get("matches", [])
    issue_type = issue.get("type", "")

    type_to_op = {
        "missing_text": "delete",
        "substitution": "replace",
        "uncertain_alignment": "insert",
        "pickup_restart": "insert",
        "false_start": "insert",
        "repetition": "equal",
    }

    return type_to_op.get(issue_type, "unknown")
