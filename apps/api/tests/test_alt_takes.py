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


def test_cluster_members_have_timing_fields():
    """Test that cluster members include content and playback timing fields."""
    issues = [
        {"type": "repetition", "start_ms": 1000, "end_ms": 2000,
         "confidence": 0.9, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
        {"type": "repetition", "start_ms": 3000, "end_ms": 4000,
         "confidence": 0.85, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
    ]
    manuscript_tokens = [{"text": "hello"}, {"text": "world"}]
    spoken_tokens = [
        {"text": "hello", "start_ms": 1000, "end_ms": 1500},
        {"text": "world", "start_ms": 1500, "end_ms": 2000},
        {"text": "hello", "start_ms": 3000, "end_ms": 3500},
        {"text": "world", "start_ms": 3500, "end_ms": 4000},
    ]
    alignment = {"matches": [
        {"op": "equal", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 0, "spoken_end": 2},
        {"op": "insert", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 2, "spoken_end": 4},
    ]}

    clusters = detect_alt_takes(
        issues, manuscript_tokens, spoken_tokens, alignment, [],
        audio_duration_ms=10000
    )

    assert len(clusters) >= 1
    for member in clusters[0]["members"]:
        # Check all required timing fields exist
        assert "issue_index" in member
        assert "take_order" in member
        assert "content_start_ms" in member
        assert "content_end_ms" in member
        assert "playback_start_ms" in member
        assert "playback_end_ms" in member

        # Content bounds should match issue start/end
        idx = member["issue_index"]
        assert member["content_start_ms"] == issues[idx]["start_ms"]
        assert member["content_end_ms"] == issues[idx]["end_ms"]

        # Playback bounds should include content and padding
        assert member["playback_start_ms"] <= member["content_start_ms"]
        assert member["playback_end_ms"] >= member["content_end_ms"]


def test_playback_windows_use_vad():
    """Test that playback windows snap to VAD boundaries when available."""
    issues = [
        {"type": "repetition", "start_ms": 1000, "end_ms": 2000,
         "confidence": 0.9, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
        {"type": "repetition", "start_ms": 5000, "end_ms": 6000,
         "confidence": 0.85, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
    ]
    manuscript_tokens = [{"text": "hello"}, {"text": "world"}]
    spoken_tokens = [
        {"text": "hello", "start_ms": 1000, "end_ms": 1500},
        {"text": "world", "start_ms": 1500, "end_ms": 2000},
        {"text": "hello", "start_ms": 5000, "end_ms": 5500},
        {"text": "world", "start_ms": 5500, "end_ms": 6000},
    ]
    alignment = {"matches": [
        {"op": "equal", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 0, "spoken_end": 2},
        {"op": "insert", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 2, "spoken_end": 4},
    ]}

    # VAD segment that encompasses first issue
    vad_segments = [
        {"start_ms": 900, "end_ms": 2100, "speech_probability": 0.95},
        {"start_ms": 4900, "end_ms": 6100, "speech_probability": 0.95},
    ]

    clusters = detect_alt_takes(
        issues, manuscript_tokens, spoken_tokens, alignment, [],
        vad_segments=vad_segments,
        audio_duration_ms=10000
    )

    assert len(clusters) >= 1
    # First member should have playback extending to VAD bounds
    first_member = clusters[0]["members"][0]
    assert first_member["playback_start_ms"] <= 900
    assert first_member["playback_end_ms"] >= 2100


def test_playback_clamped_to_audio_duration():
    """Test that playback bounds are clamped to audio file duration."""
    issues = [
        {"type": "repetition", "start_ms": 9500, "end_ms": 10000,
         "confidence": 0.9, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
        {"type": "repetition", "start_ms": 8000, "end_ms": 8500,
         "confidence": 0.85, "expected_text": "hello world", "spoken_text": "hello world",
         "context_before": "", "context_after": "", "status": "approved",
         "prosody_features_json": "{}"},
    ]
    manuscript_tokens = [{"text": "hello"}, {"text": "world"}]
    spoken_tokens = [
        {"text": "hello", "start_ms": 8000, "end_ms": 8200},
        {"text": "world", "start_ms": 8200, "end_ms": 8500},
        {"text": "hello", "start_ms": 9500, "end_ms": 9700},
        {"text": "world", "start_ms": 9700, "end_ms": 10000},
    ]
    alignment = {"matches": [
        {"op": "equal", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 0, "spoken_end": 2},
        {"op": "insert", "manuscript_start": 0, "manuscript_end": 2, "spoken_start": 2, "spoken_end": 4},
    ]}

    clusters = detect_alt_takes(
        issues, manuscript_tokens, spoken_tokens, alignment, [],
        audio_duration_ms=10000
    )

    assert len(clusters) >= 1
    # Find the member at the end of the file
    for member in clusters[0]["members"]:
        assert member["playback_end_ms"] <= 10000
