"""Alt-take clustering: group overlapping manuscript-span issues into clusters.

This module groups issues that cover the same manuscript text span into
alt-take clusters for comparison by the editor. Each cluster member includes:

- issue_index / issue_id: reference to the original issue
- take_order: position in chronological order
- content_start_ms / content_end_ms: detected core phrase bounds (issue start/end)
- playback_start_ms / playback_end_ms: padded review window for listening

The playback bounds are computed by the take_windows module to provide
editor-friendly audio sample windows that:
- Include padding around the detected content
- Snap to VAD speech boundaries when possible
- Avoid clipping the spoken take
- Handle edge cases (file boundaries, overlapping takes)
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ..detection_config import (
    ALT_TAKE_MAX_GAP_MS,
    ALT_TAKE_MIN_CLUSTER_SIZE,
    ALT_TAKE_MIN_TEXT_OVERLAP,
    PERFORMANCE_VARIANT_F0_DIFF_HZ,
    PERFORMANCE_VARIANT_RATE_DIFF,
)
from .take_windows import (
    compute_take_playback_windows,
    adjust_for_overlapping_takes,
)

logger = logging.getLogger(__name__)


def _token_text(token) -> str:
    if isinstance(token, dict):
        return str(token.get("normalized") or token.get("text") or "")
    return str(token)


def _manuscript_range_for_issue(
    issue: dict[str, Any],
    manuscript_tokens: Sequence,
    spoken_tokens: Sequence,
    alignment: dict[str, Any],
) -> tuple[int, int] | None:
    """Find manuscript token range for an issue based on alignment."""
    matches = alignment.get("matches", [])
    start_ms = issue.get("start_ms", 0)
    end_ms = issue.get("end_ms", 0)

    best_start = None
    best_end = None

    for match in matches:
        spoken_start = int(match.get("spoken_start", 0))
        spoken_end = int(match.get("spoken_end", spoken_start))

        if spoken_start >= len(spoken_tokens) or spoken_end > len(spoken_tokens):
            continue

        t_start = 0
        t_end = 0
        if spoken_start < len(spoken_tokens):
            tok = spoken_tokens[spoken_start]
            if isinstance(tok, dict):
                t_start = tok.get("start_ms", 0)
                if t_start == 0 and tok.get("start") is not None:
                    try:
                        t_start = int(float(tok["start"]) * 1000)
                    except (TypeError, ValueError):
                        pass
        if spoken_end > 0 and spoken_end - 1 < len(spoken_tokens):
            tok = spoken_tokens[spoken_end - 1]
            if isinstance(tok, dict):
                t_end = tok.get("end_ms", 0)
                if t_end == 0 and tok.get("end") is not None:
                    try:
                        t_end = int(float(tok["end"]) * 1000)
                    except (TypeError, ValueError):
                        pass

        if t_start <= end_ms and t_end >= start_ms:
            ms = int(match.get("manuscript_start", 0))
            me = int(match.get("manuscript_end", ms))
            if best_start is None or ms < best_start:
                best_start = ms
            if best_end is None or me > best_end:
                best_end = me

    if best_start is not None and best_end is not None:
        return best_start, best_end
    return None


def _text_overlap(text_a: str, text_b: str) -> float:
    """Compute word overlap ratio between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def _detect_performance_variants(cluster_issues: list[dict], prosody_map: list[dict]) -> list[dict]:
    """Detect performance variants within a cluster (same text, different prosody)."""
    import json
    variants = []
    for i, issue_a in enumerate(cluster_issues):
        for j, issue_b in enumerate(cluster_issues):
            if j <= i:
                continue

            prosody_a_json = issue_a.get("prosody_features_json", "{}")
            prosody_b_json = issue_b.get("prosody_features_json", "{}")
            try:
                prosody_a = json.loads(prosody_a_json) if isinstance(prosody_a_json, str) else prosody_a_json
                prosody_b = json.loads(prosody_b_json) if isinstance(prosody_b_json, str) else prosody_b_json
            except (json.JSONDecodeError, TypeError):
                continue

            rate_a = prosody_a.get("speech_rate_wps", 0)
            rate_b = prosody_b.get("speech_rate_wps", 0)
            f0_a = prosody_a.get("f0_mean_hz")
            f0_b = prosody_b.get("f0_mean_hz")

            rate_diff = abs(rate_a - rate_b) if rate_a and rate_b else 0
            f0_diff = abs(f0_a - f0_b) if f0_a and f0_b else 0

            text_a = issue_a.get("spoken_text", "") or issue_a.get("expected_text", "")
            text_b = issue_b.get("spoken_text", "") or issue_b.get("expected_text", "")
            overlap = _text_overlap(text_a, text_b)

            if overlap >= ALT_TAKE_MIN_TEXT_OVERLAP and (
                rate_diff >= PERFORMANCE_VARIANT_RATE_DIFF
                or f0_diff >= PERFORMANCE_VARIANT_F0_DIFF_HZ
            ):
                variants.append((i, j))

    return variants


def detect_alt_takes(
    issue_records: list[dict[str, Any]],
    manuscript_tokens: Sequence,
    spoken_tokens: Sequence,
    alignment: dict[str, Any],
    prosody_map: list[dict[str, Any]],
    vad_segments: Sequence[dict[str, Any]] | None = None,
    audio_duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Group overlapping manuscript-span issues into alt-take clusters.

    Each cluster member includes:
    - issue_index / issue_id: reference to the original issue
    - take_order: position in chronological order
    - content_start_ms / content_end_ms: detected core phrase bounds
    - playback_start_ms / playback_end_ms: padded review window for listening

    Args:
        issue_records: List of detected issues
        manuscript_tokens: Tokenized manuscript text
        spoken_tokens: Tokenized spoken/transcribed text
        alignment: Alignment between manuscript and spoken tokens
        prosody_map: Prosody features per token
        vad_segments: Optional VAD speech segments for playback window snapping
        audio_duration_ms: Optional audio duration for clamping playback bounds

    Returns:
        List of alt-take cluster dicts with members containing timing info
    """
    logger.info("Detecting alt-takes from %d issues", len(issue_records))

    # Map each issue to its manuscript range
    issue_ranges: list[tuple[int, dict, tuple[int, int] | None]] = []
    for idx, issue in enumerate(issue_records):
        ms_range = _manuscript_range_for_issue(issue, manuscript_tokens, spoken_tokens, alignment)
        issue_ranges.append((idx, issue, ms_range))

    # Filter to issues with manuscript ranges
    ranged_issues = [(idx, issue, r) for idx, issue, r in issue_ranges if r is not None]

    # Sort by manuscript start
    ranged_issues.sort(key=lambda x: x[2][0])

    # Cluster overlapping ranges within time proximity
    clusters: list[list[tuple[int, dict, tuple[int, int]]]] = []
    for item in ranged_issues:
        idx, issue, (ms_start, ms_end) = item
        placed = False

        for cluster in clusters:
            for _, c_issue, (cs, ce) in cluster:
                # Check manuscript overlap
                overlap_start = max(ms_start, cs)
                overlap_end = min(ms_end, ce)
                if overlap_end > overlap_start:
                    # Check time proximity
                    time_gap = abs(issue.get("start_ms", 0) - c_issue.get("end_ms", 0))
                    if time_gap <= ALT_TAKE_MAX_GAP_MS:
                        # Check text overlap
                        text_a = issue.get("spoken_text", "") or issue.get("expected_text", "")
                        text_b = c_issue.get("spoken_text", "") or c_issue.get("expected_text", "")
                        if _text_overlap(text_a, text_b) >= ALT_TAKE_MIN_TEXT_OVERLAP:
                            cluster.append(item)
                            placed = True
                            break
            if placed:
                break

        if not placed:
            clusters.append([item])

    # Build cluster records, filtering to minimum size
    alt_take_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        if len(cluster) < ALT_TAKE_MIN_CLUSTER_SIZE:
            continue

        ms_starts = [r[0] for _, _, r in cluster]
        ms_ends = [r[1] for _, _, r in cluster]
        ms_text_parts = []
        for s, e in zip(ms_starts, ms_ends):
            for ti in range(s, min(e, len(manuscript_tokens))):
                ms_text_parts.append(_token_text(manuscript_tokens[ti]))

        ms_text = " ".join(dict.fromkeys(ms_text_parts))  # deduplicate preserving order

        # Mark performance variants
        cluster_issues = [issue for _, issue, _ in cluster]
        variants = _detect_performance_variants(cluster_issues, prosody_map)
        for i, j in variants:
            if cluster_issues[i].get("type") not in ("performance_variant", "alt_take"):
                cluster_issues[i]["type"] = "performance_variant"
            if cluster_issues[j].get("type") not in ("performance_variant", "alt_take"):
                cluster_issues[j]["type"] = "performance_variant"

        # Mark remaining as alt_take
        for _, issue, _ in cluster:
            if issue.get("type") not in ("performance_variant",):
                issue["type"] = "alt_take"

        # Get sorted cluster members by time
        sorted_cluster = sorted(cluster, key=lambda x: x[1].get("start_ms", 0))
        cluster_member_indices = [idx for idx, _, _ in sorted_cluster]

        # Compute playback windows for all cluster members
        playback_windows = compute_take_playback_windows(
            issue_records,
            cluster_member_indices,
            vad_segments=vad_segments,
            audio_duration_ms=audio_duration_ms,
        )

        # Adjust for overlapping takes
        playback_windows = adjust_for_overlapping_takes(playback_windows)

        # Build member list with timing info
        members = []
        for order, (idx, issue, _) in enumerate(sorted_cluster):
            # Find the corresponding playback window
            window = next(
                (w for w in playback_windows if w["issue_index"] == idx),
                None
            )

            member = {
                "issue_index": idx,
                "issue_id": issue.get("id"),
                "take_order": order,
                # Content bounds = raw issue timing (detected core phrase)
                "content_start_ms": issue.get("start_ms", 0),
                "content_end_ms": issue.get("end_ms", 0),
            }

            # Add playback bounds if computed
            if window:
                member["playback_start_ms"] = window["playback_start_ms"]
                member["playback_end_ms"] = window["playback_end_ms"]
            else:
                # Fallback: use content bounds as playback bounds
                member["playback_start_ms"] = member["content_start_ms"]
                member["playback_end_ms"] = member["content_end_ms"]

            members.append(member)

        confidence = min(1.0, len(cluster) * 0.3 + 0.2)

        alt_take_clusters.append({
            "manuscript_start_idx": min(ms_starts),
            "manuscript_end_idx": max(ms_ends),
            "manuscript_text": ms_text[:500],
            "preferred_issue_id": None,
            "confidence": round(confidence, 4),
            "members": members,
        })

    logger.info("Found %d alt-take clusters", len(alt_take_clusters))
    return alt_take_clusters
