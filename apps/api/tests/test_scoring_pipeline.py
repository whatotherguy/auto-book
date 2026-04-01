import json
from app.services.scoring.baseline import build_chapter_baseline, _safe_mean, _safe_std
from app.services.scoring.composite import compute_all_composites, compute_mistake_candidate
from app.services.scoring.derived_features import compute_derived_features, _z_score
from app.services.scoring.detector_registry import run_all_detectors, ALL_DETECTORS
from app.services.scoring.envelope import build_envelope
from app.services.scoring.features import extract_raw_features
from app.services.scoring.recommendations import generate_recommendation
from app.services.scoring.take_ranking import rank_alternate_takes


# --- Baseline ---

def test_safe_mean_empty():
    assert _safe_mean([], 5.0) == 5.0


def test_safe_mean_values():
    assert _safe_mean([2.0, 4.0, 6.0], 0.0) == 4.0


def test_safe_std_empty():
    assert _safe_std([], 1.0) == 1.0


def test_safe_std_single():
    assert _safe_std([5.0], 1.0) == 1.0


def test_build_chapter_baseline_returns_expected_keys():
    issues = [
        {"prosody_features_json": json.dumps({"speech_rate_wps": 3.0, "f0_mean_hz": 150.0, "f0_std_hz": 20.0, "pause_before_ms": 200}),
         "audio_features_json": json.dumps({"rms_db": -18.0, "spectral_centroid_hz": 1500.0})},
        {"prosody_features_json": json.dumps({"speech_rate_wps": 3.5, "f0_mean_hz": 160.0, "f0_std_hz": 22.0, "pause_before_ms": 300}),
         "audio_features_json": json.dumps({"rms_db": -20.0, "spectral_centroid_hz": 1600.0})},
    ]
    baseline = build_chapter_baseline(issues, [], [])
    assert "mean_speech_rate" in baseline
    assert "std_speech_rate" in baseline
    assert "mean_f0" in baseline
    assert "sample_count" in baseline
    assert baseline["sample_count"] == 2


# --- Derived features ---

def test_z_score_basic():
    assert _z_score(10.0, 5.0, 2.5) == 2.0


def test_z_score_zero_std():
    assert _z_score(10.0, 5.0, 0.0) == 0.0


def test_compute_derived_features_keys():
    features = {"speech_rate_wps": 4.0, "f0_mean_hz": 160.0, "f0_std_hz": 25.0,
                "rms_db": -15.0, "spectral_centroid_hz": 1800.0, "pause_before_ms": 300}
    baseline = {"mean_speech_rate": 3.0, "std_speech_rate": 0.5, "mean_f0": 150.0, "std_f0": 20.0,
                "mean_f0_std": 20.0, "std_f0_std": 5.0, "mean_rms_db": -20.0, "std_rms_db": 5.0,
                "mean_spectral_centroid": 1500.0, "std_spectral_centroid": 300.0, "mean_pause": 200.0, "std_pause": 100.0}
    derived = compute_derived_features(features, baseline)
    assert "z_speech_rate" in derived
    assert "z_f0_mean" in derived
    assert "z_rms_db" in derived
    assert "delta_rms_db_prev" in derived


# --- Detector registry ---

def test_all_detectors_count():
    assert len(ALL_DETECTORS) == 15


def test_run_all_detectors_returns_all():
    features = {
        "expected_text": "hello", "spoken_text": "hello", "whisper_word_confidence": 1.0,
        "issue_type": "substitution", "confidence": 0.8,
        "start_ms": 100, "end_ms": 500, "pause_before_ms": 100, "pause_after_ms": 50,
        "has_silence_gap": False, "silence_gap_ms": 0, "has_click_marker": False,
        "click_marker_confidence": 0.0, "has_abrupt_cutoff": False, "has_onset_burst": False,
        "restart_pattern_detected": False, "speech_rate_wps": 3.0,
        "f0_std_hz": 20.0, "f0_mean_hz": 150.0, "rms_db": -20.0, "crest_factor": 12.0,
        "energy_contour": [], "is_first_sentence": False, "is_last_sentence": False,
    }
    derived = {"z_speech_rate": 0.0, "z_f0_mean": 0.0, "z_f0_std": 0.0,
               "z_rms_db": 0.0, "z_spectral_centroid": 0.0, "z_pause_before": 0.0,
               "delta_rms_db_prev": 0.0, "delta_f0_prev": 0.0,
               "delta_speech_rate_prev": 0.0, "delta_speech_rate_next": 0.0}
    results = run_all_detectors(features, derived)
    assert len(results) == 15
    for name, output in results.items():
        assert hasattr(output, "score")
        assert hasattr(output, "triggered")
        assert 0 <= output.score <= 1.0


# --- Composite scores ---

def test_compute_all_composites_keys():
    from app.services.scoring.detector_output import DetectorOutput
    outputs = {name: DetectorOutput(detector_name=name, score=0.5, confidence=0.7, triggered=True)
               for name, _ in ALL_DETECTORS}
    composites = compute_all_composites(outputs)
    assert "mistake_candidate" in composites
    assert "pickup_candidate" in composites
    assert "performance_quality" in composites
    assert "continuity_fit" in composites
    assert "splice_readiness" in composites
    for key, value in composites.items():
        assert "score" in value
        assert 0 <= value["score"] <= 1.0


# --- Recommendations ---

def test_recommendation_no_action():
    composites = {
        "mistake_candidate": {"score": 0.1, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "pickup_candidate": {"score": 0.1, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "performance_quality": {"score": 0.8, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "continuity_fit": {"score": 0.9, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": 0.3, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
    }
    rec = generate_recommendation(composites)
    assert rec["action"] == "no_action"
    assert rec["priority"] == "info"


def test_recommendation_safe_auto_cut():
    composites = {
        "mistake_candidate": {"score": 0.1, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "pickup_candidate": {"score": 0.1, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "performance_quality": {"score": 0.8, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "continuity_fit": {"score": 0.9, "confidence": 0.9, "components": {}, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": 0.9, "confidence": 0.8, "components": {}, "reasons": [], "ambiguity_flags": []},
    }
    rec = generate_recommendation(composites)
    assert rec["action"] == "safe_auto_cut"
    assert rec["priority"] == "low"


def test_recommendation_review_mistake():
    composites = {
        "mistake_candidate": {"score": 0.85, "confidence": 0.9, "components": {}, "reasons": ["text mismatch"], "ambiguity_flags": []},
        "pickup_candidate": {"score": 0.1, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
        "performance_quality": {"score": 0.5, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "continuity_fit": {"score": 0.5, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": 0.3, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
    }
    rec = generate_recommendation(composites)
    assert rec["action"] == "review_mistake"
    assert rec["priority"] == "critical"


def test_recommendation_likely_pickup():
    composites = {
        "mistake_candidate": {"score": 0.2, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
        "pickup_candidate": {"score": 0.75, "confidence": 0.8, "components": {}, "reasons": ["pickup pattern"], "ambiguity_flags": []},
        "performance_quality": {"score": 0.6, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "continuity_fit": {"score": 0.6, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": 0.4, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
    }
    rec = generate_recommendation(composites)
    assert rec["action"] == "likely_pickup"


def test_recommendation_alt_take():
    composites = {
        "mistake_candidate": {"score": 0.2, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
        "pickup_candidate": {"score": 0.2, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
        "performance_quality": {"score": 0.6, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "continuity_fit": {"score": 0.6, "confidence": 0.7, "components": {}, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": 0.4, "confidence": 0.5, "components": {}, "reasons": [], "ambiguity_flags": []},
    }
    rec = generate_recommendation(composites, alt_take_member_count=3)
    assert rec["action"] == "alt_take_available"
    assert rec["priority"] == "medium"


# --- Take ranking ---

def test_rank_alternate_takes_empty():
    cluster = {"id": 1, "members": []}
    ranking = rank_alternate_takes(cluster, {})
    assert ranking["ranked_takes"] == []
    assert ranking["preferred_take_issue_id"] is None


def test_rank_alternate_takes_two_members():
    cluster = {"id": 1, "members": [
        {"issue_id": 10, "issue_index": 0, "take_order": 0},
        {"issue_id": 11, "issue_index": 1, "take_order": 1},
    ]}
    envelopes = {
        0: {"composite_scores": {
            "mistake_candidate": {"score": 0.8},
            "performance_quality": {"score": 0.5},
            "continuity_fit": {"score": 0.5},
            "splice_readiness": {"score": 0.5},
        }},
        1: {"composite_scores": {
            "mistake_candidate": {"score": 0.1},
            "performance_quality": {"score": 0.9},
            "continuity_fit": {"score": 0.8},
            "splice_readiness": {"score": 0.7},
        }},
    }
    ranking = rank_alternate_takes(cluster, envelopes)
    assert len(ranking["ranked_takes"]) == 2
    # Issue 11 should be preferred (lower mistake, higher quality)
    assert ranking["preferred_take_issue_id"] == 11
    assert ranking["ranked_takes"][0]["rank"] == 1


# --- Feature extraction ---

def test_extract_raw_features_keys():
    issue = {"type": "substitution", "confidence": 0.8, "start_ms": 100, "end_ms": 500,
             "expected_text": "hello world", "spoken_text": "hi world",
             "audio_features_json": "{}", "audio_signals_json": "{}", "prosody_features_json": "{}"}
    features = extract_raw_features(
        issue=issue, issue_index=0, spoken_tokens=[], manuscript_tokens=[],
        alignment={"matches": []}, prosody_map=[], audio_signals=[], vad_segments=[], total_issues=1,
    )
    assert "issue_type" in features
    assert "expected_text" in features
    assert "rms_db" in features
    assert "speech_rate_wps" in features
    assert "is_first_sentence" in features
    assert features["is_first_sentence"] is True
    assert features["is_last_sentence"] is True


# --- Envelope ---

def test_build_envelope_structure():
    from app.services.scoring.detector_output import DetectorOutput
    outputs = {"text_mismatch": DetectorOutput(detector_name="text_mismatch", score=0.5)}
    composites = {"mistake_candidate": {"score": 0.5}}
    rec = {"action": "review_mistake", "priority": "high", "reasoning": "test"}
    envelope = build_envelope(
        issue={"id": 1}, issue_index=0, detector_outputs=outputs,
        composite_scores=composites, recommendation=rec,
        derived_features={"z_speech_rate": 1.0}, baseline_id="test",
    )
    assert envelope["issue_id"] == 1
    assert envelope["scoring_version"] == "1.0.0"
    assert envelope["priority"] == "high"
    assert envelope["baseline_id"] == "test"
