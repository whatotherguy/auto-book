import json
from app.services.signal_fusion import (
    _find_signals_near,
    _build_audio_signals_flags,
    _build_prosody_features,
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
