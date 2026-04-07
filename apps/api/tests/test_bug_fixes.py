"""Tests covering the three bug fixes:

1. persist_issue_models must save triage_verdict and triage_reason.
2. detect_alignment_issues must use enumerate (not list.index) for match lookup.
3. parse_optional_int must handle non-integer strings without raising.
"""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Issue
from app.services.detect import detect_alignment_issues, persist_issue_models
from app.services.transcribe import parse_optional_int


# ---------------------------------------------------------------------------
# Bug 1: triage fields persisted by persist_issue_models
# ---------------------------------------------------------------------------

def test_persist_issue_models_stores_triage_verdict_and_reason():
    """Triage annotations added by triage_issues() must survive DB round-trip."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    issue_records = [
        {
            "type": "repetition",
            "start_ms": 100,
            "end_ms": 300,
            "confidence": 0.9,
            "expected_text": "alpha beta",
            "spoken_text": "alpha beta alpha beta",
            "context_before": "",
            "context_after": "",
            "triage_verdict": "keep",
            "triage_reason": "Genuine repetition error.",
        },
        {
            "type": "uncertain_alignment",
            "start_ms": 400,
            "end_ms": 500,
            "confidence": 0.58,
            "expected_text": "gamma",
            "spoken_text": "gamma",
            "context_before": "",
            "context_after": "",
            "triage_verdict": "dismiss",
            "triage_reason": "Likely narrator ad-lib.",
        },
    ]

    with Session(engine) as session:
        persist_issue_models(session, chapter_id=42, issue_records=issue_records)
        issues = session.exec(select(Issue).order_by(Issue.id)).all()

    assert issues[0].triage_verdict == "keep"
    assert issues[0].triage_reason == "Genuine repetition error."
    assert issues[1].triage_verdict == "dismiss"
    assert issues[1].triage_reason == "Likely narrator ad-lib."


def test_persist_issue_models_handles_missing_triage_fields():
    """Issues without triage annotations must persist with NULL triage fields."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    issue_records = [
        {
            "type": "repetition",
            "start_ms": 100,
            "end_ms": 300,
            "confidence": 0.9,
            "expected_text": "alpha",
            "spoken_text": "alpha alpha",
            "context_before": "",
            "context_after": "",
            # No triage_verdict or triage_reason
        },
    ]

    with Session(engine) as session:
        persist_issue_models(session, chapter_id=1, issue_records=issue_records)
        issues = session.exec(select(Issue)).all()

    assert issues[0].triage_verdict is None
    assert issues[0].triage_reason is None


# ---------------------------------------------------------------------------
# Bug 2: detect_alignment_issues uses enumerate, not list.index
# ---------------------------------------------------------------------------

def _timed(text: str) -> list[dict]:
    return [
        {
            "text": w,
            "normalized": w,
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 500,
        }
        for i, w in enumerate(text.split())
    ]


def test_detect_alignment_issues_boosted_confidence_with_flanking_equals():
    """A 5-token delete flanked by equal ops must receive boosted confidence (0.88)."""
    manuscript_tokens = _timed("alpha beta gamma delta epsilon zeta eta theta")
    spoken_tokens = _timed("alpha beta eta theta")

    # Alignment: equal(alpha beta) + delete(gamma delta epsilon zeta eta?) …
    # Let's build a precise alignment dict with the flanking pattern.
    matches = [
        {
            "op": "equal",
            "manuscript_start": 0, "manuscript_end": 2,
            "spoken_start": 0, "spoken_end": 2,
            "manuscript_text": "alpha beta", "spoken_text": "alpha beta",
        },
        {
            "op": "delete",
            "manuscript_start": 2, "manuscript_end": 7,
            "spoken_start": 2, "spoken_end": 2,
            "manuscript_text": "gamma delta epsilon zeta eta", "spoken_text": "",
        },
        {
            "op": "equal",
            "manuscript_start": 7, "manuscript_end": 8,
            "spoken_start": 2, "spoken_end": 3,
            "manuscript_text": "theta", "spoken_text": "theta",
        },
    ]
    alignment = {"matches": matches}

    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)

    missing = [i for i in issues if i["type"] == "missing_text"]
    assert missing, "expected a missing_text issue"
    assert missing[0]["confidence"] == 0.88, (
        f"Expected boosted confidence 0.88 for large flanked delete, got {missing[0]['confidence']}"
    )


def test_detect_alignment_issues_duplicate_delete_ops_get_correct_index():
    """Two consecutive delete ops with the same manuscript span should each be handled
    independently — the fix using enumerate ensures this instead of list.index()
    returning the first occurrence for both."""
    manuscript_tokens = _timed("a b c d e f g h i j")
    spoken_tokens = _timed("a b i j")

    # Two 'delete' ops separated by an 'equal' — duplicate-shaped ops.
    matches = [
        {
            "op": "equal",
            "manuscript_start": 0, "manuscript_end": 2,
            "spoken_start": 0, "spoken_end": 2,
            "manuscript_text": "a b", "spoken_text": "a b",
        },
        {
            "op": "delete",
            "manuscript_start": 2, "manuscript_end": 6,
            "spoken_start": 2, "spoken_end": 2,
            "manuscript_text": "c d e f", "spoken_text": "",
        },
        {
            "op": "delete",
            "manuscript_start": 6, "manuscript_end": 8,
            "spoken_start": 2, "spoken_end": 2,
            "manuscript_text": "g h", "spoken_text": "",
        },
        {
            "op": "equal",
            "manuscript_start": 8, "manuscript_end": 10,
            "spoken_start": 2, "spoken_end": 4,
            "manuscript_text": "i j", "spoken_text": "i j",
        },
    ]
    alignment = {"matches": matches}

    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)

    missing = [i for i in issues if i["type"] == "missing_text"]
    # Should find two distinct missing_text issues, not just one
    assert len(missing) == 2, f"expected 2 missing_text issues, got {len(missing)}"


# ---------------------------------------------------------------------------
# Bug 3: parse_optional_int handles invalid strings gracefully
# ---------------------------------------------------------------------------

def test_parse_optional_int_returns_none_for_none():
    assert parse_optional_int(None) is None


def test_parse_optional_int_returns_none_for_empty_string():
    assert parse_optional_int("") is None
    assert parse_optional_int("   ") is None


def test_parse_optional_int_returns_int_for_valid_string():
    assert parse_optional_int("4") == 4
    assert parse_optional_int("0") == 0


def test_parse_optional_int_returns_none_for_float_string():
    """A float string like '1.5' used to raise ValueError; must now return None."""
    result = parse_optional_int("1.5")
    assert result is None


def test_parse_optional_int_returns_none_for_non_numeric_string():
    """An alphabetic string used to raise ValueError; must now return None."""
    result = parse_optional_int("abc")
    assert result is None
