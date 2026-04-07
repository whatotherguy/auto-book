from app.services.scoring.take_ranking import rank_alternate_takes


def _envelope(mistake=0.3, performance=0.7, continuity=0.6, splice=0.5):
    return {
        "composite_scores": {
            "mistake_candidate": {"score": mistake},
            "performance_quality": {"score": performance},
            "continuity_fit": {"score": continuity},
            "splice_readiness": {"score": splice},
        }
    }


def test_rank_empty_cluster():
    result = rank_alternate_takes({"id": 1, "members": []}, {})
    assert result["ranked_takes"] == []
    assert result["preferred_take_issue_id"] is None
    assert result["confidence"] == 0.0


def test_rank_single_take():
    cluster = {"id": 1, "members": [{"issue_id": 10, "issue_index": 0}]}
    envelopes = {10: _envelope(mistake=0.1, performance=0.9)}
    result = rank_alternate_takes(cluster, envelopes)
    assert len(result["ranked_takes"]) == 1
    assert result["preferred_take_issue_id"] == 10
    assert result["ranked_takes"][0]["rank"] == 1
    assert result["confidence"] == 0.9


def test_rank_two_takes_clear_winner():
    cluster = {
        "id": 1,
        "members": [
            {"issue_id": 10, "issue_index": 0},
            {"issue_id": 20, "issue_index": 1},
        ],
    }
    envelopes = {
        10: _envelope(mistake=0.1, performance=0.95, continuity=0.9, splice=0.8),
        20: _envelope(mistake=0.8, performance=0.3, continuity=0.3, splice=0.2),
    }
    result = rank_alternate_takes(cluster, envelopes)
    assert result["preferred_take_issue_id"] == 10
    assert result["ranked_takes"][0]["issue_id"] == 10
    assert result["ranked_takes"][0]["rank"] == 1
    assert result["ranked_takes"][1]["rank"] == 2
    assert result["confidence"] > 0.7


def test_rank_close_call_low_confidence():
    cluster = {
        "id": 1,
        "members": [
            {"issue_id": 10, "issue_index": 0},
            {"issue_id": 20, "issue_index": 1},
        ],
    }
    # Nearly identical scores
    envelopes = {
        10: _envelope(mistake=0.3, performance=0.7, continuity=0.6, splice=0.5),
        20: _envelope(mistake=0.3, performance=0.69, continuity=0.6, splice=0.5),
    }
    result = rank_alternate_takes(cluster, envelopes)
    assert result["confidence"] <= 0.5
    assert "close_call" in result["selection_reasons"]


def test_rank_reasons_populated():
    # NOTE: good_performance was removed from user-facing reasons because
    # performance quality is ambiguous and not directly actionable.
    cluster = {"id": 1, "members": [{"issue_id": 10, "issue_index": 0}]}
    envelopes = {10: _envelope(mistake=0.1, performance=0.8, continuity=0.9)}
    result = rank_alternate_takes(cluster, envelopes)
    take = result["ranked_takes"][0]
    assert "high_text_accuracy" in take["reasons"]
    assert "good_continuity" in take["reasons"]
    # performance_quality is still used for ranking but not surfaced as a reason
    assert "good_performance" not in take["reasons"]


def test_rank_missing_envelope_uses_defaults():
    cluster = {"id": 1, "members": [{"issue_id": 10, "issue_index": 0}]}
    result = rank_alternate_takes(cluster, {})
    assert len(result["ranked_takes"]) == 1
    # Defaults to 0.5 for all scores
    take = result["ranked_takes"][0]
    assert take["text_accuracy"] == 0.5
    assert take["performance_quality"] == 0.5


def test_rank_three_takes_sorted():
    cluster = {
        "id": 1,
        "members": [
            {"issue_id": 10, "issue_index": 0},
            {"issue_id": 20, "issue_index": 1},
            {"issue_id": 30, "issue_index": 2},
        ],
    }
    envelopes = {
        10: _envelope(mistake=0.5, performance=0.5),  # Worst
        20: _envelope(mistake=0.1, performance=0.9),  # Best
        30: _envelope(mistake=0.3, performance=0.7),  # Middle
    }
    result = rank_alternate_takes(cluster, envelopes)
    ids = [t["issue_id"] for t in result["ranked_takes"]]
    assert ids[0] == 20  # Best first
    assert result["ranked_takes"][0]["rank"] == 1
    assert result["ranked_takes"][1]["rank"] == 2
    assert result["ranked_takes"][2]["rank"] == 3
