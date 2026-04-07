"""Playback window computation for alt-take review.

This module computes editor-friendly playback bounds for alt-take audio samples.
Raw issue bounds (start_ms/end_ms) are detection boundaries, not human-friendly
playback windows. This module provides:

- content_start_ms / content_end_ms: the detected core phrase/problem region
- playback_start_ms / playback_end_ms: padded review window for listening

Playback windows are computed by:
1. Starting from the issue range (content bounds)
2. Expanding outward with configurable padding
3. Snapping to nearby VAD speech boundaries when possible
4. Avoiding clipping the spoken take
5. Clamping to audio file boundaries
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Sequence

logger = logging.getLogger(__name__)

# Default padding around the content region for playback (in milliseconds)
DEFAULT_PLAYBACK_PADDING_MS = 500

# Maximum padding to apply
MAX_PLAYBACK_PADDING_MS = 2000

# How close to a VAD boundary we'll snap (in milliseconds)
VAD_SNAP_THRESHOLD_MS = 300

# Minimum playback window duration
MIN_PLAYBACK_DURATION_MS = 500


def find_nearest_vad_boundary(
    target_ms: int,
    vad_segments: Sequence[dict[str, Any]],
    direction: Literal["before", "after"],
    max_distance_ms: int = VAD_SNAP_THRESHOLD_MS,
) -> int | None:
    """Find the nearest VAD speech boundary within max_distance_ms.

    Args:
        target_ms: The target time in milliseconds
        vad_segments: List of VAD segments with start_ms/end_ms
        direction: "before" to find boundaries before target (segment starts/ends),
                   "after" to find boundaries after target (segment starts/ends)
        max_distance_ms: Maximum distance to search for a boundary

    Returns:
        The VAD boundary time in ms, or None if no boundary found within range

    Raises:
        ValueError: If direction is not "before" or "after"
    """
    if direction not in ("before", "after"):
        raise ValueError(f"direction must be 'before' or 'after', got {direction!r}")

    if not vad_segments:
        return None

    best_boundary = None
    best_distance = max_distance_ms + 1

    for seg in vad_segments:
        seg_start = seg.get("start_ms", 0)
        seg_end = seg.get("end_ms", 0)

        if direction == "before":
            # Looking for a segment end that's before the target
            if seg_end <= target_ms:
                distance = target_ms - seg_end
                if distance <= max_distance_ms and distance < best_distance:
                    best_distance = distance
                    best_boundary = seg_end
            # Also consider segment start if it's before target
            if seg_start <= target_ms:
                distance = target_ms - seg_start
                if distance <= max_distance_ms and distance < best_distance:
                    best_distance = distance
                    best_boundary = seg_start
        else:  # direction == "after"
            # Looking for a segment start that's after the target
            if seg_start >= target_ms:
                distance = seg_start - target_ms
                if distance <= max_distance_ms and distance < best_distance:
                    best_distance = distance
                    best_boundary = seg_start
            # Also consider segment end if it's after target
            if seg_end >= target_ms:
                distance = seg_end - target_ms
                if distance <= max_distance_ms and distance < best_distance:
                    best_distance = distance
                    best_boundary = seg_end

    return best_boundary


def find_enclosing_vad_segment(
    start_ms: int,
    end_ms: int,
    vad_segments: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find the VAD segment that best encloses the given time range.

    Returns the segment with the most overlap with the given range.
    """
    if not vad_segments:
        return None

    best_segment = None
    best_overlap = 0

    for seg in vad_segments:
        seg_start = seg.get("start_ms", 0)
        seg_end = seg.get("end_ms", 0)

        overlap_start = max(start_ms, seg_start)
        overlap_end = min(end_ms, seg_end)
        overlap = max(0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_segment = seg

    return best_segment


def compute_playback_window(
    content_start_ms: int,
    content_end_ms: int,
    vad_segments: Sequence[dict[str, Any]] | None = None,
    audio_duration_ms: int | None = None,
    padding_ms: int = DEFAULT_PLAYBACK_PADDING_MS,
) -> tuple[int, int]:
    """Compute playback window bounds for a content region.

    Args:
        content_start_ms: Start of the detected content/issue region
        content_end_ms: End of the detected content/issue region
        vad_segments: Optional list of VAD speech segments
        audio_duration_ms: Optional total audio duration for clamping
        padding_ms: Padding to apply before/after content region

    Returns:
        Tuple of (playback_start_ms, playback_end_ms)

    Strategy:
    1. Apply padding to content bounds
    2. If VAD data available, try to snap to speech boundaries
    3. Ensure we don't clip the actual speech in the take
    4. Clamp to audio file boundaries
    5. Ensure minimum playback duration
    """
    # Clamp padding to reasonable limits
    padding_ms = min(max(padding_ms, 0), MAX_PLAYBACK_PADDING_MS)

    # Start with padded bounds
    playback_start = content_start_ms - padding_ms
    playback_end = content_end_ms + padding_ms

    # Try to snap to VAD boundaries for cleaner playback
    if vad_segments:
        # Find if there's a speech boundary near our padded start
        vad_snap_start = find_nearest_vad_boundary(
            playback_start, vad_segments, "before", VAD_SNAP_THRESHOLD_MS
        )
        if vad_snap_start is not None:
            # Snap to VAD boundary if it extends the window (earlier than padded start)
            # This ensures we include the full speech region
            playback_start = min(vad_snap_start, playback_start)

        # Find if there's a speech boundary near our padded end
        vad_snap_end = find_nearest_vad_boundary(
            playback_end, vad_segments, "after", VAD_SNAP_THRESHOLD_MS
        )
        if vad_snap_end is not None:
            # Snap to VAD boundary if it extends the window (later than padded end)
            # This ensures we include the full speech region
            playback_end = max(vad_snap_end, playback_end)

        # Additionally, ensure we include the full VAD segment if the content
        # is within a speech segment
        enclosing_seg = find_enclosing_vad_segment(
            content_start_ms, content_end_ms, vad_segments
        )
        if enclosing_seg:
            # Extend to include the full speech segment with padding
            seg_start = enclosing_seg.get("start_ms", content_start_ms)
            seg_end = enclosing_seg.get("end_ms", content_end_ms)
            playback_start = min(playback_start, seg_start)
            playback_end = max(playback_end, seg_end)

    # Clamp to audio boundaries
    playback_start = max(0, playback_start)
    if audio_duration_ms is not None:
        playback_end = min(playback_end, audio_duration_ms)

    # Ensure minimum duration
    current_duration = playback_end - playback_start
    if current_duration < MIN_PLAYBACK_DURATION_MS:
        needed = MIN_PLAYBACK_DURATION_MS - current_duration
        # Try to expand equally on both sides
        expand_each = needed // 2
        playback_start = max(0, playback_start - expand_each)
        playback_end = playback_end + (needed - expand_each)
        if audio_duration_ms is not None:
            playback_end = min(playback_end, audio_duration_ms)

    return (playback_start, playback_end)


def compute_take_playback_windows(
    issues: Sequence[dict[str, Any]],
    cluster_member_indices: Sequence[int],
    vad_segments: Sequence[dict[str, Any]] | None = None,
    audio_duration_ms: int | None = None,
    padding_ms: int = DEFAULT_PLAYBACK_PADDING_MS,
) -> list[dict[str, Any]]:
    """Compute playback windows for all takes in a cluster.

    Args:
        issues: All issues in the chapter
        cluster_member_indices: Indices into issues for cluster members
        vad_segments: Optional VAD segments
        audio_duration_ms: Optional total audio duration
        padding_ms: Padding for playback windows

    Returns:
        List of dicts with timing info for each member:
        {
            "issue_index": int,
            "content_start_ms": int,
            "content_end_ms": int,
            "playback_start_ms": int,
            "playback_end_ms": int,
        }
    """
    results = []

    for idx in cluster_member_indices:
        if idx < 0 or idx >= len(issues):
            logger.warning("Invalid issue index %d, skipping", idx)
            continue

        issue = issues[idx]
        content_start = issue.get("start_ms", 0)
        content_end = issue.get("end_ms", 0)

        playback_start, playback_end = compute_playback_window(
            content_start,
            content_end,
            vad_segments=vad_segments,
            audio_duration_ms=audio_duration_ms,
            padding_ms=padding_ms,
        )

        results.append({
            "issue_index": idx,
            "content_start_ms": content_start,
            "content_end_ms": content_end,
            "playback_start_ms": playback_start,
            "playback_end_ms": playback_end,
        })

    return results


def adjust_for_overlapping_takes(
    take_windows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adjust playback windows to avoid overlapping with adjacent takes.

    When takes are close together, we don't want playback of one take
    to bleed into the next. This trims playback windows to stop at
    the midpoint between adjacent takes.

    Args:
        take_windows: List of take window dicts (must have playback_* and content_* fields)

    Returns:
        Adjusted list of take window dicts
    """
    if len(take_windows) <= 1:
        return list(take_windows)

    # Sort by content start time
    sorted_windows = sorted(take_windows, key=lambda w: w.get("content_start_ms", 0))
    adjusted = []

    for i, window in enumerate(sorted_windows):
        adjusted_window = dict(window)

        # Check overlap with previous take
        if i > 0:
            prev_window = adjusted[i - 1]
            prev_content_end = prev_window.get("content_end_ms", 0)
            curr_content_start = window.get("content_start_ms", 0)

            # If our playback_start overlaps with prev's content, trim it
            if adjusted_window["playback_start_ms"] < prev_content_end:
                # Set playback start to midpoint between takes,
                # but never push it past our own content_start
                midpoint = (prev_content_end + curr_content_start) // 2
                adjusted_window["playback_start_ms"] = min(
                    midpoint,
                    curr_content_start  # Never skip past our content
                )

        # Check overlap with next take
        if i < len(sorted_windows) - 1:
            next_window = sorted_windows[i + 1]
            curr_content_end = window.get("content_end_ms", 0)
            next_content_start = next_window.get("content_start_ms", 0)

            # If our playback_end overlaps with next's content, trim it
            if adjusted_window["playback_end_ms"] > next_content_start:
                # Set playback end to midpoint between takes,
                # but never trim below our own content_end
                midpoint = (curr_content_end + next_content_start) // 2
                adjusted_window["playback_end_ms"] = max(
                    midpoint,
                    curr_content_end  # Never trim into our content
                )

        adjusted.append(adjusted_window)

    return adjusted
