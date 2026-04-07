import json
from app.services.signal_fusion import (
    _find_signals_near,
    _build_audio_signals_flags,
    _build_prosody_features,
    _get_prosody_for_range,
    _detect_pickup_candidates,
    _detect_non_speech_markers,
    enrich_issues,
)


def test_find_signals_near_within_range():
    signals = [
        {"start_ms": 100, "end_ms": 150, "signal_type": "click_marker"},
        {"start_ms": 5000, "end_ms": 5050, "signal_type": "click_marker"},
    ]
    near = _find_signals_near(signals, 80, 200, proximity_ms=100)
    assert len(near) == 1
    assert near[0]["start_ms"] == 100


def test_find_signals_near_nothing_close():
    signals = [{"start_ms": 5000, "end_ms": 5050, "signal_type": "click_marker"}]
    near = _find_signals_near(signals, 100, 200, proximity_ms=100)
    assert len(near) == 0


def test_build_audio_signals_flags_with_click():
    signals = [
        {"start_ms": 100, "end_ms": 150, "signal_type": "click_marker", "confidence": 0.85,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    flags = _build_audio_signals_flags(signals, 100, 200)
    assert flags["has_click_marker"] is True
    assert flags["click_marker_confidence"] == 0.85


def test_build_audio_signals_flags_empty():
    flags = _build_audio_signals_flags([], 100, 200)
    assert flags["has_click_marker"] is False
    assert flags["has_abrupt_cutoff"] is False
    assert flags["restart_pattern_detected"] is False


def test_build_prosody_features_none():
    result = _build_prosody_features(None)
    assert result["duration_ms"] == 0
    assert result["f0_mean_hz"] is None


def test_build_prosody_features_with_data():
    prosody = {
        "duration_ms": 500,
        "speech_rate_wps": 3.2,
        "f0_mean_hz": 142.0,
        "f0_std_hz": 15.0,
        "f0_contour": [140.0, 145.0],
        "energy_contour": [0.01, 0.02],
        "pause_before_ms": 200,
        "pause_after_ms": 100,
    }
    result = _build_prosody_features(prosody)
    assert result["speech_rate_wps"] == 3.2
    assert result["f0_mean_hz"] == 142.0


def test_detect_pickup_candidates():
    audio_signals = [
        {"start_ms": 950, "end_ms": 1000, "signal_type": "click_marker", "confidence": 0.9,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 500, "speech_probability": 0.95},
        {"start_ms": 1000, "end_ms": 2000, "speech_probability": 0.95},
    ]
    issues = _detect_pickup_candidates(audio_signals, vad_segments, [], [])
    assert len(issues) >= 1
    assert issues[0]["type"] == "pickup_candidate"


def test_detect_non_speech_markers():
    audio_signals = [
        {"start_ms": 5000, "end_ms": 5050, "signal_type": "click_marker", "confidence": 0.95,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None, "note": ""},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 3000, "speech_probability": 0.95},
    ]
    markers = _detect_non_speech_markers(audio_signals, vad_segments)
    assert len(markers) == 1
    assert markers[0]["type"] == "non_speech_marker"


def test_enrich_issues_adds_json_fields():
    issues = [
        {"type": "repetition", "start_ms": 100, "end_ms": 500,
         "confidence": 0.9, "expected_text": "hello", "spoken_text": "hello hello",
         "context_before": "", "context_after": "", "status": "approved"},
    ]
    enriched = enrich_issues(issues, [], [], [], [], [], {})
    assert "audio_features_json" in enriched[0]
    assert "audio_signals_json" in enriched[0]
    assert "prosody_features_json" in enriched[0]
    # Verify they're valid JSON
    json.loads(enriched[0]["audio_features_json"])
    json.loads(enriched[0]["audio_signals_json"])
    json.loads(enriched[0]["prosody_features_json"])


# === CORROBORATION-FIRST TESTS ===

def test_detect_pickup_candidates_single_click_is_secondary():
    """Single click marker without cutoff should be marked as secondary."""
    audio_signals = [
        {"start_ms": 950, "end_ms": 1000, "signal_type": "click_marker", "confidence": 0.9,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 500, "speech_probability": 0.95},
        {"start_ms": 1000, "end_ms": 2000, "speech_probability": 0.95},
    ]
    issues = _detect_pickup_candidates(audio_signals, vad_segments, [], [])
    assert len(issues) == 1
    # Single click without cutoff should be secondary (lower confidence)
    assert issues[0]["is_secondary"] is True
    assert "click_only" in issues[0]["note"]


def test_detect_pickup_candidates_dual_signal_is_primary():
    """Click + cutoff (dual signals) should be marked as primary."""
    audio_signals = [
        {"start_ms": 950, "end_ms": 1000, "signal_type": "click_marker", "confidence": 0.9,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
        {"start_ms": 960, "end_ms": 1010, "signal_type": "abrupt_cutoff", "confidence": 0.85,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 500, "speech_probability": 0.95},
        {"start_ms": 1000, "end_ms": 2000, "speech_probability": 0.95},
    ]
    issues = _detect_pickup_candidates(audio_signals, vad_segments, [], [])
    assert len(issues) == 1
    # Dual signals = strong corroboration = primary
    assert issues[0]["is_secondary"] is False
    assert "dual_signal" in issues[0]["note"]
    # Confidence should be higher due to dual signals
    assert issues[0]["confidence"] >= 0.65


def test_detect_pickup_candidates_accumulated_evidence_still_secondary():
    """Single signal with long silence and onset burst shows accumulating evidence.
    
    Note: With click (0.10) + onset_burst (0.08) + long_silence (0.10) = 0.28 boosts
    Total confidence = 0.40 (base) + 0.28 = 0.68
    This is still BELOW the primary threshold (0.75), so it remains secondary.
    
    However, this demonstrates how multiple corroborating signals accumulate.
    A dual signal (click + cutoff) would be needed for primary status without
    very high confidence from other sources.
    """
    audio_signals = [
        {"start_ms": 1450, "end_ms": 1500, "signal_type": "click_marker", "confidence": 0.9,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
        {"start_ms": 1460, "end_ms": 1510, "signal_type": "onset_burst", "confidence": 0.8,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 400, "speech_probability": 0.95},
        # Gap of 1100ms (> 800ms threshold for long_silence boost)
        {"start_ms": 1500, "end_ms": 2000, "speech_probability": 0.95},
    ]
    issues = _detect_pickup_candidates(audio_signals, vad_segments, [], [])
    assert len(issues) == 1
    # Verify corroboration signals are noted
    assert "long_silence" in issues[0]["note"]
    assert "onset_burst" in issues[0]["note"]
    # Without dual signals, this remains secondary (0.68 < 0.75 threshold)
    assert issues[0]["is_secondary"] is True
    # But confidence is boosted by the accumulating evidence
    assert issues[0]["confidence"] >= 0.65


def test_detect_non_speech_markers_is_secondary():
    """Non-speech markers should always be marked as secondary."""
    audio_signals = [
        {"start_ms": 5000, "end_ms": 5050, "signal_type": "click_marker", "confidence": 0.95,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None, "note": "test marker"},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 3000, "speech_probability": 0.95},
    ]
    markers = _detect_non_speech_markers(audio_signals, vad_segments)
    assert len(markers) == 1
    assert markers[0]["is_secondary"] is True
    assert "SECONDARY" in markers[0]["note"]


def test_detect_pickup_candidate_note_explains_demotion():
    """Demoted pickup candidates should have note explaining why."""
    audio_signals = [
        {"start_ms": 950, "end_ms": 1000, "signal_type": "abrupt_cutoff", "confidence": 0.9,
         "rms_db": None, "spectral_centroid_hz": None, "zero_crossing_rate": None,
         "onset_strength": None, "bandwidth_hz": None},
    ]
    vad_segments = [
        {"start_ms": 0, "end_ms": 500, "speech_probability": 0.95},
        {"start_ms": 1000, "end_ms": 2000, "speech_probability": 0.95},
    ]
    issues = _detect_pickup_candidates(audio_signals, vad_segments, [], [])
    assert len(issues) == 1
    assert issues[0]["is_secondary"] is True
    # Note should explain the demotion reason
    assert "Pure signal artifact" in issues[0]["note"]
    assert "corroborating evidence" in issues[0]["note"]


# === PROSODY RANGE AGGREGATION TESTS ===

def _make_token(start_ms: int, end_ms: int) -> dict:
    return {"start_ms": start_ms, "end_ms": end_ms}


def test_get_prosody_for_range_no_overlap_returns_none():
    """No overlapping tokens → None (fallback)."""
    tokens = [_make_token(0, 500)]
    prosody_map = [{"duration_ms": 500, "speech_rate_wps": 2.0, "f0_mean_hz": 120.0,
                    "f0_std_hz": 10.0, "f0_contour": [], "energy_contour": [],
                    "pause_before_ms": 0, "pause_after_ms": 0}]
    result = _get_prosody_for_range(prosody_map, tokens, 1000, 1500)
    assert result is None


def test_get_prosody_for_range_single_overlap_returns_entry():
    """Single overlapping token → returns that entry directly (no aggregation overhead)."""
    tokens = [_make_token(100, 400), _make_token(500, 900)]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 3.0, "f0_mean_hz": 130.0,
         "f0_std_hz": 12.0, "f0_contour": [130.0], "energy_contour": [0.01],
         "pause_before_ms": 50, "pause_after_ms": 30},
        {"duration_ms": 400, "speech_rate_wps": 2.5, "f0_mean_hz": 140.0,
         "f0_std_hz": 8.0, "f0_contour": [140.0], "energy_contour": [0.02],
         "pause_before_ms": 20, "pause_after_ms": 10},
    ]
    result = _get_prosody_for_range(prosody_map, tokens, 100, 400)
    assert result is prosody_map[0]


def test_get_prosody_for_range_aggregates_multiple_tokens():
    """Multiple overlapping tokens → aggregated values returned."""
    tokens = [_make_token(0, 300), _make_token(300, 600), _make_token(600, 900)]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 2.0, "f0_mean_hz": 100.0,
         "f0_std_hz": 10.0, "f0_contour": [100.0, 105.0], "energy_contour": [0.01],
         "pause_before_ms": 50, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 4.0, "f0_mean_hz": 120.0,
         "f0_std_hz": 20.0, "f0_contour": [120.0, 115.0], "energy_contour": [0.02],
         "pause_before_ms": 0, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 3.0, "f0_mean_hz": 110.0,
         "f0_std_hz": 15.0, "f0_contour": [110.0], "energy_contour": [0.03],
         "pause_before_ms": 0, "pause_after_ms": 80},
    ]
    result = _get_prosody_for_range(prosody_map, tokens, 0, 900)
    assert result is not None

    # duration_ms should be sum
    assert result["duration_ms"] == 900

    # speech_rate_wps should be mean of [2.0, 4.0, 3.0]
    assert abs(result["speech_rate_wps"] - 3.0) < 1e-9

    # f0_mean_hz should be mean of [100, 120, 110]
    assert abs(result["f0_mean_hz"] - 110.0) < 1e-9

    # f0_std_hz should be mean of [10, 20, 15]
    assert abs(result["f0_std_hz"] - 15.0) < 1e-9

    # contours should be concatenated
    assert result["f0_contour"] == [100.0, 105.0, 120.0, 115.0, 110.0]
    assert result["energy_contour"] == [0.01, 0.02, 0.03]

    # pause_before from first, pause_after from last
    assert result["pause_before_ms"] == 50
    assert result["pause_after_ms"] == 80


def test_get_prosody_for_range_partial_overlap():
    """Only a subset of tokens overlap the query range; aggregate only those."""
    tokens = [_make_token(0, 300), _make_token(300, 600), _make_token(600, 900)]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 2.0, "f0_mean_hz": 100.0,
         "f0_std_hz": 10.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 4.0, "f0_mean_hz": 120.0,
         "f0_std_hz": 20.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 3.0, "f0_mean_hz": 110.0,
         "f0_std_hz": 15.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
    ]
    # Query starts at 301ms, so only tokens 1 (300–600) and 2 (600–900) overlap
    result = _get_prosody_for_range(prosody_map, tokens, 301, 900)
    assert result is not None
    assert result["duration_ms"] == 600
    assert abs(result["speech_rate_wps"] - 3.5) < 1e-9
    assert abs(result["f0_mean_hz"] - 115.0) < 1e-9


def test_get_prosody_for_range_missing_f0_handled():
    """Tokens without f0 data → f0 fields are None in aggregate."""
    tokens = [_make_token(0, 300), _make_token(300, 600)]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 2.0, "f0_mean_hz": None,
         "f0_std_hz": None, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 4.0, "f0_mean_hz": None,
         "f0_std_hz": None, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
    ]
    result = _get_prosody_for_range(prosody_map, tokens, 0, 600)
    assert result is not None
    assert result["f0_mean_hz"] is None
    assert result["f0_std_hz"] is None


def test_get_prosody_for_range_float_timestamps():
    """Tokens using float 'start'/'end' keys (seconds) are resolved correctly."""
    tokens = [
        {"start": "0.1", "end": "0.4"},   # 100–400 ms
        {"start": "0.4", "end": "0.8"},   # 400–800 ms
    ]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 2.0, "f0_mean_hz": 130.0,
         "f0_std_hz": 5.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
        {"duration_ms": 400, "speech_rate_wps": 3.0, "f0_mean_hz": 150.0,
         "f0_std_hz": 7.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 0},
    ]
    result = _get_prosody_for_range(prosody_map, tokens, 100, 800)
    assert result is not None
    assert result["duration_ms"] == 700
    assert abs(result["speech_rate_wps"] - 2.5) < 1e-9
    assert abs(result["f0_mean_hz"] - 140.0) < 1e-9


def test_enrich_issues_prosody_aggregates_multiple_tokens():
    """enrich_issues correctly aggregates prosody across multiple spanning tokens."""
    tokens = [
        {"start_ms": 0, "end_ms": 300},
        {"start_ms": 300, "end_ms": 600},
    ]
    prosody_map = [
        {"duration_ms": 300, "speech_rate_wps": 2.0, "f0_mean_hz": 100.0,
         "f0_std_hz": 10.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 50, "pause_after_ms": 0},
        {"duration_ms": 300, "speech_rate_wps": 4.0, "f0_mean_hz": 120.0,
         "f0_std_hz": 20.0, "f0_contour": [], "energy_contour": [],
         "pause_before_ms": 0, "pause_after_ms": 80},
    ]
    issues = [
        {"type": "repetition", "start_ms": 0, "end_ms": 600,
         "confidence": 0.9, "expected_text": "hello", "spoken_text": "hello hello",
         "context_before": "", "context_after": "", "status": "approved"},
    ]
    enriched = enrich_issues(issues, [], [], prosody_map, tokens, [], {})
    pf = json.loads(enriched[0]["prosody_features_json"])
    assert pf["duration_ms"] == 600
    assert abs(pf["speech_rate_wps"] - 3.0) < 1e-9
    assert abs(pf["f0_mean_hz"] - 110.0) < 1e-9
    assert pf["pause_before_ms"] == 50
    assert pf["pause_after_ms"] == 80
