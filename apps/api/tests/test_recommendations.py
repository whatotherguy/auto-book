from app.services.scoring.recommendations import generate_recommendation


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
    assert rec["priority"] == "low"


def test_alt_take_available():
    rec = generate_recommendation(_scores(), alt_take_member_count=3)
    assert rec["action"] == "alt_take_available"
    assert rec["priority"] == "medium"


def test_likely_pickup_high():
    rec = generate_recommendation(_scores(pickup=0.85))
    assert rec["action"] == "likely_pickup"
    assert rec["priority"] == "high"


def test_likely_pickup_medium():
    rec = generate_recommendation(_scores(pickup=0.65))
    assert rec["action"] == "likely_pickup"
    assert rec["priority"] == "medium"


def test_review_mistake_critical():
    rec = generate_recommendation(_scores(mistake=0.9))
    assert rec["action"] == "review_mistake"
    assert rec["priority"] == "critical"


def test_review_mistake_high():
    rec = generate_recommendation(_scores(mistake=0.6))
    assert rec["action"] == "review_mistake"
    assert rec["priority"] == "high"


def test_low_performance():
    rec = generate_recommendation(_scores(performance=0.3))
    assert rec["action"] == "review_mistake"
    assert rec["priority"] == "low"


def test_no_action():
    rec = generate_recommendation(_scores(performance=0.7))
    assert rec["action"] == "no_action"
    assert rec["priority"] == "info"
    assert rec["confidence"] == 0.9


def test_priority_order_splice_over_pickup():
    """Splice readiness check comes before pickup."""
    rec = generate_recommendation(_scores(pickup=0.9, splice=0.9, splice_conf=0.8))
    assert rec["action"] == "safe_auto_cut"


def test_priority_order_alt_take_over_pickup():
    """Alt-take check comes before pickup."""
    rec = generate_recommendation(_scores(pickup=0.9), alt_take_member_count=2)
    assert rec["action"] == "alt_take_available"


def test_priority_order_pickup_over_mistake():
    """Pickup check comes before mistake."""
    rec = generate_recommendation(_scores(pickup=0.7, mistake=0.6))
    assert rec["action"] == "likely_pickup"


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
    assert "priority" in rec
    assert "reasoning" in rec
    assert "confidence" in rec
    assert "related_issue_ids" in rec
    assert "ambiguity_flags" in rec
