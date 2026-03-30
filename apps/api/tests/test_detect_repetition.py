from app.services.detect import detect_repetition


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


def test_no_repetition_no_issue():
    issues = detect_repetition(["one", "two", "three", "four"], min_span=2, max_span=3)

    assert issues == []


def test_repetition_required_fields():
    issues = detect_repetition(["the", "door", "the", "door"], min_span=2, max_span=2)

    issue = next(issue for issue in issues if issue["type"] == "repetition")
    assert_required_fields(issue)


def test_repetition_long_span():
    tokens = [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "tail",
    ]

    issues = detect_repetition(tokens, min_span=9, max_span=9)

    issue = next(issue for issue in issues if issue["type"] == "repetition")
    assert issue["end_ms"] > issue["start_ms"]
    assert len(issue["spoken_text"].split()) >= 9


def test_repetition_applies_start_offset_to_absolute_timestamps():
    tokens = [f"lead{i}" for i in range(30)] + ["alpha", "beta", "alpha", "beta", "tail"]

    issues = detect_repetition(tokens, start_offset=30, min_span=2, max_span=2)

    issue = next(issue for issue in issues if issue["type"] == "repetition")
    assert issue["start_ms"] == 15000
    assert issue["end_ms"] == 17000


def test_repetition_emits_each_chained_repeat():
    issues = detect_repetition(["a", "b", "a", "b", "a", "b", "tail"], min_span=2, max_span=2)

    repetition_issues = [issue for issue in issues if issue["type"] == "repetition"]
    assert len(repetition_issues) == 2
    assert [issue["start_ms"] for issue in repetition_issues] == [0, 1000]
