from app.services.alt_takes import detect_alt_takes, _text_overlap


def test_text_overlap_identical():
    assert _text_overlap("the big house", "the big house") == 1.0


def test_text_overlap_partial():
    overlap = _text_overlap("the big house", "the big tree")
    assert 0.3 < overlap < 0.8


def test_text_overlap_no_match():
    overlap = _text_overlap("alpha bravo", "charlie delta")
    assert overlap == 0.0


def test_text_overlap_empty():
    assert _text_overlap("", "hello") == 0.0
    assert _text_overlap("hello", "") == 0.0


def test_detect_alt_takes_no_issues():
    clusters = detect_alt_takes([], [], [], {"matches": []}, [])
    assert clusters == []


def test_detect_alt_takes_single_issue():
    issues = [
        {"type": "repetition", "start_ms": 100, "end_ms": 500,
         "confidence": 0.9, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved"},
    ]
    manuscript_tokens = [{"text": "hello"}, {"text": "world"}]
    spoken_tokens = [
        {"text": "hello", "start_ms": 100, "end_ms": 300},
        {"text": "world", "start_ms": 300, "end_ms": 500},
    ]
    alignment = {"matches": [
        {"op": "equal", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 0, "spoken_end": 2},
    ]}
    clusters = detect_alt_takes(issues, manuscript_tokens, spoken_tokens, alignment, [])
    # Single issue can't form a cluster (min size = 2)
    assert len(clusters) == 0


def test_detect_alt_takes_two_overlapping():
    issues = [
        {"type": "repetition", "start_ms": 100, "end_ms": 500,
         "confidence": 0.9, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
        {"type": "repetition", "start_ms": 600, "end_ms": 1000,
         "confidence": 0.85, "expected_text": "hello world", "spoken_text": "hello world again",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
    ]
    manuscript_tokens = [{"text": "hello"}, {"text": "world"}]
    spoken_tokens = [
        {"text": "hello", "start_ms": 100, "end_ms": 200},
        {"text": "world", "start_ms": 200, "end_ms": 500},
        {"text": "hello", "start_ms": 600, "end_ms": 700},
        {"text": "world", "start_ms": 700, "end_ms": 1000},
    ]
    alignment = {"matches": [
        {"op": "equal", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 0, "spoken_end": 2},
        {"op": "insert", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 2, "spoken_end": 4},
    ]}
    clusters = detect_alt_takes(issues, manuscript_tokens, spoken_tokens, alignment, [])
    assert len(clusters) >= 1
    assert len(clusters[0]["members"]) >= 2
