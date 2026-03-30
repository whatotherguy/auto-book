from app.services.align import build_alignment, build_manuscript_tokens
from app.services.detect import _sentence_boundary_indices_for_alignment, detect_long_pauses


REQUIRED_FIELDS = (
    "type",
    "start_ms",
    "end_ms",
    "confidence",
    "expected_text",
    "spoken_text",
    "context_before",
    "context_after",
)


def assert_required_fields(issue):
    for field in REQUIRED_FIELDS:
        assert field in issue
        assert issue[field] is not None


def test_no_long_pause_below_threshold():
    issues = detect_long_pauses(
        [
            {"normalized": "hello", "start_ms": 0, "end_ms": 250},
            {"normalized": "world", "start_ms": 750, "end_ms": 1000},
        ],
        threshold_ms=1000,
    )

    assert issues == []


def test_sentence_boundary_helper_marks_punctuation_and_em_dash():
    manuscript_tokens = [
        {"text": "hello.", "normalized": "hello"},
        {"text": "wait!", "normalized": "wait"},
        {"text": "question?", "normalized": "question"},
        {"text": "pause—", "normalized": "pause"},
        {"text": "plain", "normalized": "plain"},
    ]

    assert _sentence_boundary_indices_for_alignment(manuscript_tokens) == {0, 1, 2, 3}


def test_long_pause_at_boundary():
    manuscript_tokens = build_manuscript_tokens("hello world. next")
    spoken_tokens = [
        {"text": "hello", "normalized": "hello", "start_ms": 0, "end_ms": 250},
        {"text": "world", "normalized": "world", "start_ms": 1250, "end_ms": 1500},
        {"text": "next", "normalized": "next", "start_ms": 3500, "end_ms": 3750},
    ]
    alignment = build_alignment(manuscript_tokens, spoken_tokens)

    issues = detect_long_pauses(
        spoken_tokens,
        threshold_ms=1000,
        manuscript_tokens=manuscript_tokens,
        alignment=alignment,
    )

    issue = next(issue for issue in issues if issue["type"] == "long_pause" and issue["start_ms"] == 1500)
    assert issue["type"] == "long_pause"
    assert issue["confidence"] == 0.6
    assert issue["note"] == "Pause follows sentence boundary — may be intentional."


def test_long_pause_mid_sentence_high_confidence():
    manuscript_tokens = build_manuscript_tokens("hello world next")
    spoken_tokens = [
        {"text": "hello", "normalized": "hello", "start_ms": 0, "end_ms": 250},
        {"text": "world", "normalized": "world", "start_ms": 1250, "end_ms": 1500},
        {"text": "next", "normalized": "next", "start_ms": 3500, "end_ms": 3750},
    ]
    alignment = build_alignment(manuscript_tokens, spoken_tokens)

    issues = detect_long_pauses(
        spoken_tokens,
        threshold_ms=1000,
        manuscript_tokens=manuscript_tokens,
        alignment=alignment,
    )

    issue = next(issue for issue in issues if issue["type"] == "long_pause" and issue["start_ms"] == 1500)
    assert issue["confidence"] == 0.85
    assert "note" not in issue


def test_long_pause_after_em_dash_boundary():
    manuscript_tokens = build_manuscript_tokens("hello world— next")
    spoken_tokens = [
        {"text": "hello", "normalized": "hello", "start_ms": 0, "end_ms": 250},
        {"text": "world", "normalized": "world", "start_ms": 1250, "end_ms": 1500},
        {"text": "next", "normalized": "next", "start_ms": 3500, "end_ms": 3750},
    ]
    alignment = build_alignment(manuscript_tokens, spoken_tokens)

    issues = detect_long_pauses(
        spoken_tokens,
        threshold_ms=1000,
        manuscript_tokens=manuscript_tokens,
        alignment=alignment,
    )

    issue = next(issue for issue in issues if issue["type"] == "long_pause" and issue["start_ms"] == 1500)
    assert issue["confidence"] == 0.6
    assert issue["note"] == "Pause follows sentence boundary — may be intentional."


def test_long_pause_without_alignment_uses_mid_sentence_confidence():
    issues = detect_long_pauses(
        [
            {"normalized": "hello", "start_ms": 0, "end_ms": 250},
            {"normalized": "world", "start_ms": 1250, "end_ms": 1500},
        ],
        threshold_ms=1000,
    )

    issue = next(issue for issue in issues if issue["type"] == "long_pause")
    assert issue["type"] == "long_pause"
    assert issue["confidence"] == 0.85


def test_long_pause_required_fields():
    issues = detect_long_pauses(
        [
            {"normalized": "hello", "start_ms": 0, "end_ms": 250},
            {"normalized": "world", "start_ms": 1250, "end_ms": 1500},
        ],
        threshold_ms=1000,
    )

    issue = next(issue for issue in issues if issue["type"] == "long_pause")
    assert_required_fields(issue)
