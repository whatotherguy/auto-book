"""Signal fusion: merge audio signals, VAD, and prosody into enriched issue records."""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from ..detection_config import (
    NON_SPEECH_MARKER_CONFIDENCE,
    PICKUP_CANDIDATE_BASE_CONFIDENCE,
    PICKUP_CLICK_PROXIMITY_MS,
    PICKUP_SILENCE_BEFORE_MS,
)

logger = logging.getLogger(__name__)


def _find_signals_near(audio_signals: list[dict], start_ms: int, end_ms: int, proximity_ms: int = 500) -> list[dict]:
    """Find audio signals within proximity of a time range."""
    return [
        s for s in audio_signals
        if s["start_ms"] <= end_ms + proximity_ms and s["end_ms"] >= start_ms - proximity_ms
    ]


def _find_vad_gap_before(vad_segments: list[dict], start_ms: int, max_gap_ms: int = 1000) -> int:
    """Find silence gap duration before a given timestamp using VAD segments."""
    closest_end = 0
    for seg in vad_segments:
        if seg["end_ms"] <= start_ms:
            closest_end = max(closest_end, seg["end_ms"])
    return max(0, start_ms - closest_end)


def _get_prosody_for_range(prosody_map: list[dict], spoken_tokens: list, start_ms: int, end_ms: int) -> dict | None:
    """Get prosody features for tokens overlapping a time range."""
    for i, token in enumerate(spoken_tokens):
        t_start = token.get("start_ms", 0)
        if token.get("start") is not None and t_start == 0:
            try:
                t_start = int(float(token["start"]) * 1000)
            except (TypeError, ValueError):
                pass
        t_end = token.get("end_ms", 0)
        if token.get("end") is not None and t_end == 0:
            try:
                t_end = int(float(token["end"]) * 1000)
            except (TypeError, ValueError):
                pass
        if t_start <= end_ms and t_end >= start_ms and i < len(prosody_map):
            return prosody_map[i]
    return None


def _build_audio_features(audio_signals: list[dict], start_ms: int, end_ms: int) -> dict:
    """Build AudioFeatures dict from nearby audio signals."""
    nearby = _find_signals_near(audio_signals, start_ms, end_ms, proximity_ms=200)
    rms_values = [s["rms_db"] for s in nearby if s.get("rms_db") is not None]
    centroid_values = [s["spectral_centroid_hz"] for s in nearby if s.get("spectral_centroid_hz") is not None]
    zcr_values = [s["zero_crossing_rate"] for s in nearby if s.get("zero_crossing_rate") is not None]
    onset_values = [s["onset_strength"] for s in nearby if s.get("onset_strength") is not None]
    bw_values = [s["bandwidth_hz"] for s in nearby if s.get("bandwidth_hz") is not None]

    return {
        "rms_db": sum(rms_values) / len(rms_values) if rms_values else 0.0,
        "rms_db_contour": rms_values[:50],
        "spectral_centroid_hz": sum(centroid_values) / len(centroid_values) if centroid_values else 0.0,
        "zero_crossing_rate": sum(zcr_values) / len(zcr_values) if zcr_values else 0.0,
        "onset_strength_max": max(onset_values) if onset_values else 0.0,
        "onset_strength_mean": sum(onset_values) / len(onset_values) if onset_values else 0.0,
        "bandwidth_hz": sum(bw_values) / len(bw_values) if bw_values else 0.0,
        "crest_factor": 0.0,
    }


def _build_audio_signals_flags(audio_signals: list[dict], start_ms: int, end_ms: int) -> dict:
    """Build AudioSignals flags dict for nearby signals."""
    nearby = _find_signals_near(audio_signals, start_ms, end_ms, proximity_ms=PICKUP_CLICK_PROXIMITY_MS)
    clicks = [s for s in nearby if s["signal_type"] == "click_marker"]
    cutoffs = [s for s in nearby if s["signal_type"] == "abrupt_cutoff"]
    silence_gaps = [s for s in nearby if s["signal_type"] == "silence_gap"]
    onset_bursts = [s for s in nearby if s["signal_type"] == "onset_burst"]

    has_click = len(clicks) > 0
    click_conf = max((s["confidence"] for s in clicks), default=0.0)
    has_cutoff = len(cutoffs) > 0
    has_silence = len(silence_gaps) > 0
    silence_ms = max((s["end_ms"] - s["start_ms"] for s in silence_gaps), default=0)
    has_onset = len(onset_bursts) > 0

    restart_pattern = (has_click or has_cutoff) and has_silence

    return {
        "has_click_marker": has_click,
        "click_marker_confidence": round(click_conf, 4),
        "has_abrupt_cutoff": has_cutoff,
        "has_silence_gap": has_silence,
        "silence_gap_ms": silence_ms,
        "has_onset_burst": has_onset,
        "restart_pattern_detected": restart_pattern,
    }


def _build_prosody_features(prosody: dict | None) -> dict:
    """Build ProsodyFeatures from a prosody map entry."""
    if prosody is None:
        return {
            "duration_ms": 0,
            "speech_rate_wps": 0.0,
            "f0_mean_hz": None,
            "f0_std_hz": None,
            "f0_contour": [],
            "energy_contour": [],
            "pause_before_ms": 0,
            "pause_after_ms": 0,
        }
    return {
        "duration_ms": prosody.get("duration_ms", 0),
        "speech_rate_wps": prosody.get("speech_rate_wps", 0.0),
        "f0_mean_hz": prosody.get("f0_mean_hz"),
        "f0_std_hz": prosody.get("f0_std_hz"),
        "f0_contour": prosody.get("f0_contour", []),
        "energy_contour": prosody.get("energy_contour", []),
        "pause_before_ms": prosody.get("pause_before_ms", 0),
        "pause_after_ms": prosody.get("pause_after_ms", 0),
    }


def _detect_pickup_candidates(
    audio_signals: list[dict],
    vad_segments: list[dict],
    spoken_tokens: list,
    issue_records: list[dict],
) -> list[dict]:
    """Detect pickup candidates from VAD + audio signals without text match."""
    new_issues: list[dict] = []
    existing_ranges = [(i["start_ms"], i["end_ms"]) for i in issue_records]

    for i, seg in enumerate(vad_segments):
        if i == 0:
            continue
        gap_before = _find_vad_gap_before(vad_segments[:i+1], seg["start_ms"])
        if gap_before < PICKUP_SILENCE_BEFORE_MS:
            continue

        nearby_clicks = _find_signals_near(audio_signals, seg["start_ms"], seg["start_ms"], PICKUP_CLICK_PROXIMITY_MS)
        has_click = any(s["signal_type"] == "click_marker" for s in nearby_clicks)
        has_cutoff = any(s["signal_type"] == "abrupt_cutoff" for s in nearby_clicks)

        if not (has_click or has_cutoff):
            continue

        # Check not already covered by existing issue
        already_covered = any(
            es <= seg["start_ms"] <= ee or es <= seg["end_ms"] <= ee
            for es, ee in existing_ranges
        )
        if already_covered:
            continue

        confidence = PICKUP_CANDIDATE_BASE_CONFIDENCE
        if has_click:
            confidence += 0.15
        if has_cutoff:
            confidence += 0.15
        if gap_before > 500:
            confidence += 0.10

        new_issues.append({
            "type": "pickup_candidate",
            "start_ms": seg["start_ms"],
            "end_ms": seg["end_ms"],
            "confidence": min(1.0, round(confidence, 4)),
            "expected_text": "",
            "spoken_text": "",
            "context_before": "",
            "context_after": "",
            "note": f"VAD gap={gap_before}ms, click={has_click}, cutoff={has_cutoff}",
            "status": "needs_manual",
        })

    return new_issues


def _detect_non_speech_markers(audio_signals: list[dict], vad_segments: list[dict]) -> list[dict]:
    """Detect non-speech markers (clicks/claps outside speech regions)."""
    new_issues: list[dict] = []
    for sig in audio_signals:
        if sig["signal_type"] != "click_marker":
            continue
        if sig["confidence"] < NON_SPEECH_MARKER_CONFIDENCE:
            continue
        in_speech = any(
            v["start_ms"] <= sig["start_ms"] <= v["end_ms"]
            for v in vad_segments
        )
        if not in_speech:
            new_issues.append({
                "type": "non_speech_marker",
                "start_ms": sig["start_ms"],
                "end_ms": sig["end_ms"],
                "confidence": sig["confidence"],
                "expected_text": "",
                "spoken_text": "",
                "context_before": "",
                "context_after": "",
                "note": f"Non-speech click/marker: {sig.get('note', '')}",
                "status": "needs_manual",
            })
    return new_issues


def enrich_issues(
    issue_records: list[dict[str, Any]],
    audio_signals: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
    prosody_map: list[dict[str, Any]],
    spoken_tokens: Sequence,
    manuscript_tokens: Sequence,
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Enrich existing issue records with signal features and add new signal-based issues."""
    logger.info("Enriching %d issues with signal data", len(issue_records))

    # Enrich existing issues
    for issue in issue_records:
        start_ms = issue.get("start_ms", 0)
        end_ms = issue.get("end_ms", 0)

        issue["audio_features_json"] = json.dumps(
            _build_audio_features(audio_signals, start_ms, end_ms)
        )
        issue["audio_signals_json"] = json.dumps(
            _build_audio_signals_flags(audio_signals, start_ms, end_ms)
        )
        prosody = _get_prosody_for_range(prosody_map, list(spoken_tokens), start_ms, end_ms)
        issue["prosody_features_json"] = json.dumps(
            _build_prosody_features(prosody)
        )

    # Detect new pickup candidates
    pickup_candidates = _detect_pickup_candidates(
        audio_signals, vad_segments, list(spoken_tokens), issue_records
    )
    for pc in pickup_candidates:
        pc["audio_signals_json"] = json.dumps(
            _build_audio_signals_flags(audio_signals, pc["start_ms"], pc["end_ms"])
        )
    issue_records.extend(pickup_candidates)

    # Detect non-speech markers
    non_speech = _detect_non_speech_markers(audio_signals, vad_segments)
    issue_records.extend(non_speech)

    logger.info("Enrichment complete: %d total issues (%d pickup candidates, %d non-speech markers)",
                len(issue_records), len(pickup_candidates), len(non_speech))
    return issue_records
