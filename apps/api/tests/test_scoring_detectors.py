from app.services.scoring.detectors.text import (
    detect_text_mismatch,
    detect_repeated_phrase,
    detect_skipped_text,
    _levenshtein_ratio,
    _token_overlap,
)
from app.services.scoring.detectors.timing import (
    detect_abnormal_pause,
    detect_restart_gap,
    detect_rushed_delivery,
)
from app.services.scoring.detectors.audio import (
    detect_click_transient,
    detect_clipping,
    detect_room_tone_shift,
    detect_punch_in_boundary,
)
from app.services.scoring.detectors.prosody import (
    detect_flat_delivery,
    detect_weak_landing,
    detect_cadence_drift,
)
from app.services.scoring.detectors.context import (
    detect_pickup_pattern,
    detect_continuity_mismatch,
)


# --- Text detectors ---

def test_levenshtein_ratio_identical():
    assert _levenshtein_ratio("hello", "hello") == 0.0


def test_levenshtein_ratio_completely_different():
    ratio = _levenshtein_ratio("abc", "xyz")
    assert ratio == 1.0


def test_levenshtein_ratio_empty():
    assert _levenshtein_ratio("", "") == 0.0
    assert _levenshtein_ratio("hello", "") == 1.0


def test_token_overlap_identical():
    assert _token_overlap("the big house", "the big house") == 1.0


def test_token_overlap_none():
    assert _token_overlap("alpha bravo", "charlie delta") == 0.0


def test_text_mismatch_high_score_for_mismatch():
    features = {"expected_text": "the quick brown fox", "spoken_text": "completely different words here", "whisper_word_confidence": 1.0}
    output = detect_text_mismatch(features, {})
    assert output.score > 0.5
    assert output.triggered is True


def test_text_mismatch_low_score_for_match():
    features = {"expected_text": "the quick brown fox", "spoken_text": "the quick brown fox", "whisper_word_confidence": 1.0}
    output = detect_text_mismatch(features, {})
    assert output.score < 0.1


def test_repeated_phrase_detects_repetition():
    features = {"spoken_text": "hello world hello world something else", "issue_type": "repetition", "confidence": 0.9}
    output = detect_repeated_phrase(features, {})
    assert output.score > 0.5
    assert output.triggered is True


def test_skipped_text_detects_missing():
    features = {"expected_text": "this is the missing passage of text", "spoken_text": "", "issue_type": "missing_text", "confidence": 0.72}
    output = detect_skipped_text(features, {})
    assert output.score > 0.5
    assert output.triggered is True


# --- Timing detectors ---

def test_abnormal_pause_long_pause():
    features = {"issue_type": "long_pause", "start_ms": 1000, "end_ms": 4000, "pause_before_ms": 0, "pause_after_ms": 0}
    derived = {"z_pause_before": 0.0}
    output = detect_abnormal_pause(features, derived)
    assert output.score > 0.3
    assert output.triggered is True


def test_abnormal_pause_normal():
    features = {"issue_type": "substitution", "start_ms": 100, "end_ms": 200, "pause_before_ms": 100, "pause_after_ms": 50}
    derived = {"z_pause_before": 0.5}
    output = detect_abnormal_pause(features, derived)
    assert output.score < 0.3


def test_restart_gap_pickup():
    features = {"issue_type": "pickup_restart", "pause_before_ms": 800, "has_silence_gap": True, "silence_gap_ms": 500}
    output = detect_restart_gap(features, {})
    assert output.score >= 0.5


def test_rushed_delivery_fast_rate():
    features = {"speech_rate_wps": 7.0}
    derived = {"z_speech_rate": 3.0}
    output = detect_rushed_delivery(features, derived)
    assert output.score > 0.3
    assert output.triggered is True


# --- Audio detectors ---

def test_click_transient_present():
    features = {"has_click_marker": True, "click_marker_confidence": 0.9}
    output = detect_click_transient(features, {})
    assert output.score == 0.9
    assert output.triggered is True


def test_click_transient_absent():
    features = {"has_click_marker": False, "click_marker_confidence": 0.0}
    output = detect_click_transient(features, {})
    assert output.score == 0.0
    assert output.triggered is False


def test_clipping_near_zero_dbfs():
    features = {"rms_db": -1.0, "crest_factor": 2.0}
    output = detect_clipping(features, {})
    assert output.score > 0.5


def test_clipping_normal_levels():
    features = {"rms_db": -20.0, "crest_factor": 12.0}
    output = detect_clipping(features, {})
    assert output.score == 0.0


def test_room_tone_shift_large_delta():
    derived = {"z_rms_db": 3.0, "z_spectral_centroid": 0.0, "delta_rms_db_prev": 8.0}
    output = detect_room_tone_shift({}, derived)
    assert output.score > 0.3


def test_punch_in_boundary_cutoff_and_onset():
    features = {"has_abrupt_cutoff": True, "has_onset_burst": True, "has_click_marker": False, "restart_pattern_detected": False}
    output = detect_punch_in_boundary(features, {})
    assert output.score >= 0.7


# --- Prosody detectors ---

def test_flat_delivery_low_f0_std():
    features = {"f0_std_hz": 3.0, "speech_rate_wps": 3.0}
    derived = {"z_f0_std": -2.5}
    output = detect_flat_delivery(features, derived)
    assert output.score > 0.5


def test_flat_delivery_normal():
    features = {"f0_std_hz": 25.0, "speech_rate_wps": 3.0}
    derived = {"z_f0_std": 0.0}
    output = detect_flat_delivery(features, derived)
    assert output.score < 0.3


def test_weak_landing_energy_drop():
    features = {"energy_contour": [0.1, 0.1, 0.1, 0.1, 0.01, 0.005, 0.002, 0.001], "is_last_sentence": False}
    output = detect_weak_landing(features, {})
    assert output.score > 0.3


def test_cadence_drift_outlier():
    derived = {"z_speech_rate": 2.5, "delta_speech_rate_prev": 2.0, "delta_speech_rate_next": 2.0}
    output = detect_cadence_drift({}, derived)
    assert output.score > 0.3


# --- Context detectors ---

def test_pickup_pattern_detected():
    features = {"issue_type": "pickup_restart", "restart_pattern_detected": True,
                "has_click_marker": True, "has_silence_gap": True, "pause_before_ms": 500}
    output = detect_pickup_pattern(features, {})
    assert output.score >= 0.6
    assert output.triggered is True


def test_continuity_mismatch_large_deltas():
    derived = {"delta_rms_db_prev": 8.0, "delta_f0_prev": 50.0, "delta_speech_rate_prev": 3.0}
    features = {"is_first_sentence": False, "is_last_sentence": False}
    output = detect_continuity_mismatch(features, derived)
    assert output.score > 0.3
    assert output.triggered is True


def test_continuity_mismatch_edge_reduced():
    derived = {"delta_rms_db_prev": 8.0, "delta_f0_prev": 50.0, "delta_speech_rate_prev": 3.0}
    features = {"is_first_sentence": True, "is_last_sentence": False}
    output_edge = detect_continuity_mismatch(features, derived)
    features_mid = {"is_first_sentence": False, "is_last_sentence": False}
    output_mid = detect_continuity_mismatch(features_mid, derived)
    assert output_edge.score < output_mid.score
