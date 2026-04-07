"""Tests for take_windows playback window computation."""

from app.services.take_windows import (
    compute_playback_window,
    compute_take_playback_windows,
    find_nearest_vad_boundary,
    find_enclosing_vad_segment,
    adjust_for_overlapping_takes,
    DEFAULT_PLAYBACK_PADDING_MS,
    MIN_PLAYBACK_DURATION_MS,
)


class TestFindNearestVadBoundary:
    def test_no_vad_segments(self):
        result = find_nearest_vad_boundary(1000, [], "before")
        assert result is None

    def test_find_boundary_before(self):
        vad_segments = [
            {"start_ms": 0, "end_ms": 500},
            {"start_ms": 1000, "end_ms": 1500},
        ]
        # Looking for boundary before 600 - should find 500
        result = find_nearest_vad_boundary(600, vad_segments, "before", max_distance_ms=200)
        assert result == 500

    def test_find_boundary_after(self):
        vad_segments = [
            {"start_ms": 0, "end_ms": 500},
            {"start_ms": 1000, "end_ms": 1500},
        ]
        # Looking for boundary after 900 - should find 1000
        result = find_nearest_vad_boundary(900, vad_segments, "after", max_distance_ms=200)
        assert result == 1000

    def test_no_boundary_within_range(self):
        vad_segments = [
            {"start_ms": 0, "end_ms": 500},
            {"start_ms": 2000, "end_ms": 2500},
        ]
        # Looking for boundary after 1000 - nothing within 200ms
        result = find_nearest_vad_boundary(1000, vad_segments, "after", max_distance_ms=200)
        assert result is None


class TestFindEnclosingVadSegment:
    def test_no_vad_segments(self):
        result = find_enclosing_vad_segment(100, 200, [])
        assert result is None

    def test_content_within_segment(self):
        vad_segments = [
            {"start_ms": 0, "end_ms": 500},
            {"start_ms": 1000, "end_ms": 2000},
        ]
        result = find_enclosing_vad_segment(1100, 1800, vad_segments)
        assert result == {"start_ms": 1000, "end_ms": 2000}

    def test_content_spanning_segments(self):
        vad_segments = [
            {"start_ms": 0, "end_ms": 500},
            {"start_ms": 400, "end_ms": 900},  # Overlapping segment
        ]
        result = find_enclosing_vad_segment(300, 600, vad_segments)
        # Should return the one with more overlap
        assert result is not None


class TestComputePlaybackWindow:
    def test_basic_padding(self):
        start, end = compute_playback_window(1000, 2000, padding_ms=500)
        assert start == 500
        assert end == 2500

    def test_clamp_to_zero(self):
        start, end = compute_playback_window(200, 500, padding_ms=500)
        assert start == 0
        assert end >= 500

    def test_clamp_to_audio_duration(self):
        start, end = compute_playback_window(
            9500, 10000, audio_duration_ms=10000, padding_ms=500
        )
        assert end == 10000

    def test_minimum_duration_enforced(self):
        # Tiny content region
        start, end = compute_playback_window(1000, 1050, padding_ms=100)
        assert end - start >= MIN_PLAYBACK_DURATION_MS

    def test_vad_snap_to_speech_boundary(self):
        vad_segments = [
            {"start_ms": 950, "end_ms": 2050},  # Speech segment around content
        ]
        start, end = compute_playback_window(
            1000, 2000, vad_segments=vad_segments, padding_ms=200
        )
        # Should snap to include the full VAD segment
        assert start <= 950
        assert end >= 2050

    def test_no_vad_uses_padding(self):
        start, end = compute_playback_window(1000, 2000, vad_segments=None, padding_ms=300)
        assert start == 700
        assert end == 2300


class TestComputeTakePlaybackWindows:
    def test_single_take(self):
        issues = [
            {"start_ms": 1000, "end_ms": 2000},
        ]
        results = compute_take_playback_windows(
            issues, [0], padding_ms=DEFAULT_PLAYBACK_PADDING_MS
        )
        assert len(results) == 1
        assert results[0]["issue_index"] == 0
        assert results[0]["content_start_ms"] == 1000
        assert results[0]["content_end_ms"] == 2000
        assert results[0]["playback_start_ms"] < 1000
        assert results[0]["playback_end_ms"] > 2000

    def test_multiple_takes(self):
        issues = [
            {"start_ms": 1000, "end_ms": 2000},
            {"start_ms": 5000, "end_ms": 6000},
            {"start_ms": 10000, "end_ms": 11000},
        ]
        results = compute_take_playback_windows(issues, [0, 1, 2], padding_ms=500)
        assert len(results) == 3
        for r in results:
            assert "content_start_ms" in r
            assert "content_end_ms" in r
            assert "playback_start_ms" in r
            assert "playback_end_ms" in r

    def test_invalid_index_skipped(self):
        issues = [{"start_ms": 1000, "end_ms": 2000}]
        results = compute_take_playback_windows(issues, [0, 99], padding_ms=500)
        assert len(results) == 1

    def test_with_vad_segments(self):
        issues = [
            {"start_ms": 1000, "end_ms": 2000},
        ]
        vad_segments = [
            {"start_ms": 900, "end_ms": 2100},
        ]
        results = compute_take_playback_windows(
            issues, [0], vad_segments=vad_segments, padding_ms=500
        )
        assert len(results) == 1
        # Should extend to include VAD segment
        assert results[0]["playback_start_ms"] <= 900
        assert results[0]["playback_end_ms"] >= 2100


class TestAdjustForOverlappingTakes:
    def test_single_take_unchanged(self):
        windows = [
            {
                "issue_index": 0,
                "content_start_ms": 1000,
                "content_end_ms": 2000,
                "playback_start_ms": 500,
                "playback_end_ms": 2500,
            }
        ]
        result = adjust_for_overlapping_takes(windows)
        assert result == windows

    def test_non_overlapping_unchanged(self):
        windows = [
            {
                "issue_index": 0,
                "content_start_ms": 1000,
                "content_end_ms": 2000,
                "playback_start_ms": 500,
                "playback_end_ms": 2500,
            },
            {
                "issue_index": 1,
                "content_start_ms": 5000,
                "content_end_ms": 6000,
                "playback_start_ms": 4500,
                "playback_end_ms": 6500,
            },
        ]
        result = adjust_for_overlapping_takes(windows)
        assert len(result) == 2
        # Should be unchanged since they don't overlap
        assert result[0]["playback_end_ms"] == 2500
        assert result[1]["playback_start_ms"] == 4500

    def test_overlapping_trimmed(self):
        windows = [
            {
                "issue_index": 0,
                "content_start_ms": 1000,
                "content_end_ms": 2000,
                "playback_start_ms": 500,
                "playback_end_ms": 2800,  # Extends into next content
            },
            {
                "issue_index": 1,
                "content_start_ms": 2500,
                "content_end_ms": 3500,
                "playback_start_ms": 1800,  # Extends into prev content
                "playback_end_ms": 4000,
            },
        ]
        result = adjust_for_overlapping_takes(windows)
        assert len(result) == 2
        # First take's playback_end should be trimmed
        assert result[0]["playback_end_ms"] <= 2500
        # Second take's playback_start should be trimmed
        assert result[1]["playback_start_ms"] >= 2000

    def test_overlapping_trimmed_to_midpoint(self):
        """Verify overlapping takes are trimmed to midpoint between content regions."""
        windows = [
            {
                "issue_index": 0,
                "content_start_ms": 1000,
                "content_end_ms": 2000,
                "playback_start_ms": 500,
                "playback_end_ms": 3000,  # Overlaps with next content
            },
            {
                "issue_index": 1,
                "content_start_ms": 2600,
                "content_end_ms": 3600,
                "playback_start_ms": 1500,  # Overlaps with prev content
                "playback_end_ms": 4100,
            },
        ]
        result = adjust_for_overlapping_takes(windows)
        # Midpoint between 2000 and 2600 is 2300
        # First take's playback_end: max(2300, 2000) = 2300
        assert result[0]["playback_end_ms"] == 2300
        # Second take's playback_start: min(2300, 2600) = 2300
        assert result[1]["playback_start_ms"] == 2300

    def test_overlapping_respects_content_bounds(self):
        """When midpoint would cut into content, respect content bounds."""
        windows = [
            {
                "issue_index": 0,
                "content_start_ms": 1000,
                "content_end_ms": 2400,  # Content ends close to next
                "playback_start_ms": 500,
                "playback_end_ms": 3000,
            },
            {
                "issue_index": 1,
                "content_start_ms": 2500,  # Content starts close to prev
                "content_end_ms": 3500,
                "playback_start_ms": 2000,
                "playback_end_ms": 4000,
            },
        ]
        result = adjust_for_overlapping_takes(windows)
        # Midpoint = (2400 + 2500) / 2 = 2450
        # First take's playback_end: max(2450, 2400) = 2450
        assert result[0]["playback_end_ms"] == 2450
        # Second take's playback_start: min(2450, 2500) = 2450
        assert result[1]["playback_start_ms"] == 2450


class TestEdgeCases:
    def test_zero_duration_content(self):
        """Content with zero duration should still get minimum playback window."""
        start, end = compute_playback_window(1000, 1000, padding_ms=0)
        assert end - start >= MIN_PLAYBACK_DURATION_MS

    def test_content_at_file_start(self):
        """Content at the very beginning of the file."""
        start, end = compute_playback_window(0, 500, padding_ms=500)
        assert start == 0
        assert end > 500

    def test_content_at_file_end(self):
        """Content at the very end of the file."""
        start, end = compute_playback_window(
            9500, 10000, audio_duration_ms=10000, padding_ms=500
        )
        assert end == 10000
        assert start < 9500

    def test_very_short_audio(self):
        """Audio file shorter than minimum playback duration."""
        start, end = compute_playback_window(
            100, 200, audio_duration_ms=300, padding_ms=500
        )
        assert start == 0
        assert end == 300  # Clamped to audio duration

    def test_empty_issue_list(self):
        """Empty issues list."""
        results = compute_take_playback_windows([], [], padding_ms=500)
        assert results == []

    def test_missing_vad_handled(self):
        """Missing VAD data should not crash."""
        start, end = compute_playback_window(
            1000, 2000, vad_segments=None, padding_ms=500
        )
        assert start == 500
        assert end == 2500
