"""Tests covering the match_ratio computation fix in build_alignment
(previously created a second SequenceMatcher for short chapters)."""

from app.services.align import build_alignment, build_manuscript_tokens


def test_match_ratio_perfect_match():
    ms_tokens = build_manuscript_tokens("the quick brown fox")
    sp_tokens = build_manuscript_tokens("the quick brown fox")
    # build_spoken_tokens normally adds timing; simulate with build_manuscript_tokens.
    result = build_alignment(ms_tokens, sp_tokens)
    # Perfect match: all tokens are equal → ratio should be 1.0.
    assert result["match_ratio"] == 1.0


def test_match_ratio_no_match():
    ms_tokens = build_manuscript_tokens("alpha bravo charlie")
    sp_tokens = build_manuscript_tokens("delta echo foxtrot")
    result = build_alignment(ms_tokens, sp_tokens)
    # No tokens match → ratio should be 0.0.
    assert result["match_ratio"] == 0.0


def test_match_ratio_partial_match():
    ms_tokens = build_manuscript_tokens("the quick brown fox")
    # "the" and "fox" match; "quick" and "brown" do not.
    sp_tokens = build_manuscript_tokens("the slow red fox")
    result = build_alignment(ms_tokens, sp_tokens)
    # 2 equal tokens out of 4 on each side → ratio between 0 and 1.
    assert 0.0 < result["match_ratio"] < 1.0


def test_match_ratio_is_a_float_between_zero_and_one():
    ms_tokens = build_manuscript_tokens("hello world this is a test")
    sp_tokens = build_manuscript_tokens("hello world this is a test")
    result = build_alignment(ms_tokens, sp_tokens)
    assert isinstance(result["match_ratio"], float)
    assert 0.0 <= result["match_ratio"] <= 1.0


def test_match_ratio_empty_spoken_tokens():
    ms_tokens = build_manuscript_tokens("hello world")
    result = build_alignment(ms_tokens, [])
    # No spoken tokens → ratio is 0 (avoid division by zero).
    assert result["match_ratio"] == 0.0
