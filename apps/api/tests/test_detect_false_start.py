from app.services.detect import detect_false_starts


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


def test_false_start_two_token_repeat():
    issues = detect_false_starts(["he", "said", "he", "said", "something"])

    issue = next(issue for issue in issues if issue["type"] == "false_start")
    assert issue["type"] == "false_start"


def test_false_start_three_token_repeat():
    issues = detect_false_starts(["the", "old", "man", "the", "old", "man", "walked"])

    issue = next(issue for issue in issues if issue["type"] == "false_start")
    assert issue["type"] == "false_start"


def test_no_false_start_no_repeat():
    issues = detect_false_starts(["alpha", "bravo", "charlie", "delta"])

    assert all(issue["type"] != "false_start" for issue in issues)


def test_false_start_has_required_fields():
    issues = detect_false_starts(["he", "said", "he", "said", "something"])

    issue = next(issue for issue in issues if issue["type"] == "false_start")
    assert_required_fields(issue)


def test_false_start_confidence_range():
    issues = detect_false_starts(["he", "said", "he", "said", "something"])

    issue = next(issue for issue in issues if issue["type"] == "false_start")
    assert 0.0 <= issue["confidence"] <= 1.0


def test_false_start_detects_longer_phrase_restart():
    issues = detect_false_starts("the big house the big house".split())

    issue = next(issue for issue in issues if issue["type"] == "false_start")
    assert issue["expected_text"] == "the big house"


def test_false_start_only_scans_the_opening_tokens():
    tokens = [f"lead{i}" for i in range(30)] + ["late", "late", "late", "late"]

    issues = detect_false_starts(tokens, token_limit=30)

    assert all(issue["type"] != "false_start" for issue in issues)
