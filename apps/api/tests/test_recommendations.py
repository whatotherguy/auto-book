from app.services.scoring.recommendations import generate_recommendation, map_action_to_model_action


def _scores(mistake=0.0, pickup=0.0, performance=0.5, splice=0.0, splice_conf=0.0):
    """Helper to build composite_scores dict."""
    return {
        "mistake_candidate": {"score": mistake, "confidence": 0.8, "reasons": [], "ambiguity_flags": []},
        "pickup_candidate": {"score": pickup, "confidence": 0.8, "reasons": [], "ambiguity_flags": []},
        "performance_quality": {"score": performance, "confidence": 0.8, "reasons": [], "ambiguity_flags": []},
        "splice_readiness": {"score": splice, "confidence": splice_conf, "reasons": [], "ambiguity_flags": []},
    }


def test_safe_auto_cut():
    rec = generate_recommendation(_scores(splice=0.9, splice_conf=0.8))
    assert rec["action"] == "safe_auto_cut"
    assert rec["model_action"] == "safe_cut"
    assert rec["priority"] == "low"


def test_alt_take_available():
    rec = generate_recommendation(_scores(), alt_take_member_count=3)
    assert rec["action"] == "alt_take_available"
    assert rec["model_action"] == "compare_takes"
    assert rec["priority"] == "medium"


def test_likely_pickup_high():
    rec = generate_recommendation(_scores(pickup=0.85))
    assert rec["action"] == "likely_pickup"
    assert rec["model_action"] == "review"
    assert rec["priority"] == "high"


def test_likely_pickup_medium():
    rec = generate_recommendation(_scores(pickup=0.65))
    assert rec["action"] == "likely_pickup"
    assert rec["model_action"] == "review"
    assert rec["priority"] == "medium"


def test_review_mistake_critical():
    rec = generate_recommendation(_scores(mistake=0.9))
    assert rec["action"] == "review_mistake"
    assert rec["model_action"] == "review"
    assert rec["priority"] == "critical"


def test_review_mistake_high():
    rec = generate_recommendation(_scores(mistake=0.6))
    assert rec["action"] == "review_mistake"
    assert rec["model_action"] == "review"
    assert rec["priority"] == "high"


def test_no_action():
    # Low performance should NOT cause a review_mistake action anymore
    rec = generate_recommendation(_scores(performance=0.3))
    assert rec["action"] == "no_action"
    assert rec["model_action"] == "ignore"
    assert rec["priority"] == "info"
    assert rec["confidence"] == 0.9


def test_no_action_with_good_performance():
    rec = generate_recommendation(_scores(performance=0.7))
    assert rec["action"] == "no_action"
    assert rec["model_action"] == "ignore"
    assert rec["priority"] == "info"
    assert rec["confidence"] == 0.9


def test_priority_order_splice_over_pickup():
    """Splice readiness check comes before pickup."""
    rec = generate_recommendation(_scores(pickup=0.9, splice=0.9, splice_conf=0.8))
    assert rec["action"] == "safe_auto_cut"
    assert rec["model_action"] == "safe_cut"


def test_priority_order_alt_take_over_pickup():
    """Alt-take check comes before pickup."""
    rec = generate_recommendation(_scores(pickup=0.9), alt_take_member_count=2)
    assert rec["action"] == "alt_take_available"
    assert rec["model_action"] == "compare_takes"


def test_priority_order_pickup_over_mistake():
    """Pickup check comes before mistake."""
    rec = generate_recommendation(_scores(pickup=0.7, mistake=0.6))
    assert rec["action"] == "likely_pickup"
    assert rec["model_action"] == "review"


def test_ambiguity_propagated():
    scores = _scores(mistake=0.5, pickup=0.5)
    scores["mistake_candidate"]["ambiguity_flags"] = ["many_detectors_triggered"]
    scores["pickup_candidate"]["ambiguity_flags"] = ["low_confidence_detectors: foo"]
    # Multiple composites active + ambiguity → manual review
    rec = generate_recommendation(scores)
    assert len(rec["ambiguity_flags"]) >= 1


def test_recommendation_fields():
    rec = generate_recommendation(_scores())
    assert "action" in rec
    assert "model_action" in rec
    assert "priority" in rec
    assert "reasoning" in rec
    assert "confidence" in rec
    assert "related_issue_ids" in rec
    assert "ambiguity_flags" in rec
    # NEW: is_secondary field should be present
    assert "is_secondary" in rec


# Tests for the action to model_action mapping
def test_map_action_to_model_action():
    assert map_action_to_model_action("safe_auto_cut") == "safe_cut"
    assert map_action_to_model_action("alt_take_available") == "compare_takes"
    assert map_action_to_model_action("likely_pickup") == "review"
    assert map_action_to_model_action("review_mistake") == "review"
    assert map_action_to_model_action("manual_review_required") == "review"
    assert map_action_to_model_action("no_action") == "ignore"
    # NEW: secondary_signal maps to ignore
    assert map_action_to_model_action("secondary_signal") == "ignore"
    # Unknown action defaults to review
    assert map_action_to_model_action("unknown_action") == "review"


# === CORROBORATION-FIRST TESTS ===

def test_secondary_issue_gets_demoted():
    """Secondary issues should get secondary_signal action and info priority."""
    rec = generate_recommendation(
        _scores(pickup=0.9, mistake=0.8),  # Would normally be high priority
        is_secondary=True,
        issue_type="pickup_candidate"
    )
    assert rec["action"] == "secondary_signal"
    assert rec["model_action"] == "ignore"
    assert rec["priority"] == "info"
    assert rec["is_secondary"] is True
    assert "Secondary" in rec["reasoning"]


def test_secondary_non_speech_marker_demoted():
    """Non-speech markers should be demoted via is_secondary."""
    rec = generate_recommendation(
        _scores(pickup=0.2, mistake=0.1),
        is_secondary=True,
        issue_type="non_speech_marker"
    )
    assert rec["action"] == "secondary_signal"
    assert rec["model_action"] == "ignore"
    assert rec["priority"] == "info"
    assert "non_speech_marker" in rec["reasoning"]


def test_secondary_overrides_all_other_priorities():
    """is_secondary=True should take precedence over all other logic."""
    # Even with high mistake and pickup scores, secondary should win
    rec = generate_recommendation(
        _scores(mistake=0.95, pickup=0.95, splice=0.95, splice_conf=0.95),
        alt_take_member_count=5,  # Would normally trigger alt_take_available
        is_secondary=True,
        issue_type="pickup_candidate"
    )
    assert rec["action"] == "secondary_signal"
    assert rec["priority"] == "info"


def test_non_secondary_issue_normal_processing():
    """Non-secondary issues should follow normal recommendation logic."""
    rec = generate_recommendation(
        _scores(mistake=0.85),  # > 0.8 for critical priority
        is_secondary=False,
        issue_type="substitution"
    )
    assert rec["action"] == "review_mistake"
    assert rec["priority"] == "critical"  # mistake > 0.8 = critical
    assert rec["is_secondary"] is False


def test_default_is_secondary_false():
    """Without is_secondary parameter, issues are treated as primary."""
    rec = generate_recommendation(_scores(pickup=0.7))
    assert rec["is_secondary"] is False
    assert rec["action"] == "likely_pickup"
