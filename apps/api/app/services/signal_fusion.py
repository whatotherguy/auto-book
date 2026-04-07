"""Signal fusion: merge audio signals, VAD, and prosody into enriched issue records."""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from ..detection_config import (
    NON_SPEECH_MARKER_CONFIDENCE,
    NON_SPEECH_MARKER_IS_SECONDARY,
    PICKUP_CANDIDATE_BASE_CONFIDENCE,
    PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY,
    PICKUP_CANDIDATE_SILENCE_BOOST_MS,
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
    """Get aggregated prosody features for all tokens overlapping a time range.

    Aggregation rules:
    - duration_ms: sum of overlapping token durations
    - speech_rate_wps: mean across overlapping entries
    - f0_mean_hz: mean of available per-token means (None if none present)
    - f0_std_hz: mean of available per-token stds (None if none present)
    - f0_contour: concatenated contours (empty list if unsupported)
    - energy_contour: concatenated contours (empty list if unsupported)
    - pause_before_ms: value from the first overlapping entry
    - pause_after_ms: value from the last overlapping entry
    """
    matching: list[dict] = []
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
            matching.append(prosody_map[i])

    if not matching:
        return None

    if len(matching) == 1:
        return matching[0]

    # Aggregate over all overlapping entries
    duration_ms = sum(p.get("duration_ms", 0) for p in matching)

    # Duration-weighted mean: equivalent to total_words / total_duration_s, because
    # per-token speech_rate_wps = word_count / (duration_ms / 1000).
    weighted_rate_sum = sum(
        p["speech_rate_wps"] * p.get("duration_ms", 0)
        for p in matching
        if p.get("speech_rate_wps") is not None
    )
    rate_duration_sum = sum(
        p.get("duration_ms", 0)
        for p in matching
        if p.get("speech_rate_wps") is not None
    )
    speech_rate_wps = weighted_rate_sum / rate_duration_sum if rate_duration_sum > 0 else 0.0

    f0_means = [p["f0_mean_hz"] for p in matching if p.get("f0_mean_hz") is not None]
    f0_mean_hz = sum(f0_means) / len(f0_means) if f0_means else None

    f0_stds = [p["f0_std_hz"] for p in matching if p.get("f0_std_hz") is not None]
    f0_std_hz = sum(f0_stds) / len(f0_stds) if f0_stds else None

    f0_contour: list = []
    for p in matching:
        f0_contour.extend(p.get("f0_contour") or [])

    energy_contour: list = []
    for p in matching:
        energy_contour.extend(p.get("energy_contour") or [])

    pause_before_ms = matching[0].get("pause_before_ms", 0)
    pause_after_ms = matching[-1].get("pause_after_ms", 0)

    return {
        "duration_ms": duration_ms,
        "speech_rate_wps": speech_rate_wps,
        "f0_mean_hz": f0_mean_hz,
        "f0_std_hz": f0_std_hz,
        "f0_contour": f0_contour,
        "energy_contour": energy_contour,
        "pause_before_ms": pause_before_ms,
        "pause_after_ms": pause_after_ms,
    }


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
    """Detect pickup candidates from VAD + audio signals without text match.
    
    CORROBORATION-FIRST LOGIC:
    Pickup candidates from pure audio signals are treated as secondary issues
    unless they meet stricter thresholds. This reduces false positives from
    technically plausible but editorially non-useful signal artifacts.
    
    Requirements for PRIMARY pickup_candidate:
    - DUAL_SIGNAL: Both click and cutoff detected, OR
    - HIGH_CONFIDENCE: Confidence >= PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY
    
    Otherwise, the issue is marked is_secondary=True and given lower priority.
    """
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
        has_onset = any(s["signal_type"] == "onset_burst" for s in nearby_clicks)

        # Require at least one strong nearby signal for consideration.
        # Dual signals are handled later as a confidence boost.
        if not (has_click or has_cutoff):
            continue

        # Check not already covered by existing issue
        already_covered = any(
            es <= seg["start_ms"] <= ee or es <= seg["end_ms"] <= ee
            for es, ee in existing_ranges
        )
        if already_covered:
            continue

        # TIGHTENED CONFIDENCE CALCULATION
        # Base confidence is lower, but dual signals can push it higher
        confidence = PICKUP_CANDIDATE_BASE_CONFIDENCE
        corroboration_reasons: list[str] = []
        
        # DUAL_SIGNAL requirement: both click AND cutoff = stronger evidence
        has_dual_signal = has_click and has_cutoff
        if has_dual_signal:
            confidence += 0.25  # Significant boost for dual signals
            corroboration_reasons.append("dual_signal")
        elif has_click:
            confidence += 0.10  # Reduced from 0.15 for single click
            corroboration_reasons.append("click_only")
        elif has_cutoff:
            confidence += 0.10  # Reduced from 0.15 for single cutoff
            corroboration_reasons.append("cutoff_only")
        
        # Additional onset burst is corroborating evidence
        if has_onset:
            confidence += 0.08
            corroboration_reasons.append("onset_burst")
        
        # TIGHTENED: Silence must be longer for a boost
        if gap_before > PICKUP_CANDIDATE_SILENCE_BOOST_MS:
            # Long silence (>800ms) gets full 0.10 boost for stronger evidence
            confidence += 0.10
            corroboration_reasons.append("long_silence")
        elif gap_before > 500:
            # Intermediate silence (500-800ms): partial boost (0.05)
            # Less evidence of intentional pickup than longer silence
            confidence += 0.05
            corroboration_reasons.append("medium_silence")

        # CORROBORATION-FIRST: Determine if this is a primary or secondary issue
        # Pure signal artifacts without strong evidence are secondary/low-priority
        is_secondary = True
        demotion_reason = None
        
        if has_dual_signal:
            # Dual signals = strong corroboration, can be primary
            is_secondary = False
        elif confidence >= PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY:
            # High confidence from other factors = can be primary
            is_secondary = False
        else:
            # Pure single-signal artifact = secondary (low priority)
            # Note: Text-based issues (repetition, pickup_restart, substitution) are
            # detected separately in detect.py and have text corroboration built-in.
            # Here we only have audio signals, so we require either dual signals
            # or very high confidence to promote to primary.
            demotion_reason = (
                "Pure signal artifact without corroborating evidence. "
                f"Confidence {confidence:.2f} < {PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY:.2f} threshold. "
                f"Requires dual signals (click+cutoff) OR confidence ≥{PICKUP_CANDIDATE_MIN_CONFIDENCE_FOR_PRIMARY} for primary status."
            )

        note = f"VAD gap={gap_before}ms, click={has_click}, cutoff={has_cutoff}"
        if corroboration_reasons:
            note += f", corroboration=[{', '.join(corroboration_reasons)}]"
        if demotion_reason:
            note += f". SECONDARY: {demotion_reason}"

        new_issues.append({
            "type": "pickup_candidate",
            "start_ms": seg["start_ms"],
            "end_ms": seg["end_ms"],
            "confidence": min(1.0, round(confidence, 4)),
            "expected_text": "",
            "spoken_text": "",
            "context_before": "",
            "context_after": "",
            "note": note,
            "status": "needs_manual",
            # NEW: Mark secondary issues explicitly
            "is_secondary": is_secondary,
        })

    return new_issues


def _detect_non_speech_markers(audio_signals: list[dict], vad_segments: list[dict]) -> list[dict]:
    """Detect non-speech markers (clicks/claps outside speech regions).
    
    NON-SPEECH MARKER DEMOTION:
    Non-speech markers are useful for debugging and specialized review,
    but are NOT editorially useful enough to deserve equal prominence.
    They are treated as SECONDARY issues by default:
    - Available in the full issue list for completeness
    - Lower visibility in editor-facing views
    - Do not trigger high-priority recommendations
    
    Rationale: A click/clap outside speech doesn't directly affect narration
    quality. Editors typically only care if it interferes with usable audio.
    """
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
            note = f"Non-speech click/marker: {sig.get('note', '')}"
            if NON_SPEECH_MARKER_IS_SECONDARY:
                note += " SECONDARY: Non-speech markers are low-priority by default."
            
            new_issues.append({
                "type": "non_speech_marker",
                "start_ms": sig["start_ms"],
                "end_ms": sig["end_ms"],
                "confidence": sig["confidence"],
                "expected_text": "",
                "spoken_text": "",
                "context_before": "",
                "context_after": "",
                "note": note,
                "status": "needs_manual",
                # NEW: Mark as secondary by default (configurable via NON_SPEECH_MARKER_IS_SECONDARY)
                "is_secondary": NON_SPEECH_MARKER_IS_SECONDARY,
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
