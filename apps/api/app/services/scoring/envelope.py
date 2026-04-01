"""SegmentScoringEnvelope — full scoring result for a single issue."""

from __future__ import annotations

from typing import Any


def build_envelope(
    issue: dict[str, Any],
    issue_index: int,
    detector_outputs: dict[str, Any],
    composite_scores: dict[str, Any],
    recommendation: dict[str, Any],
    derived_features: dict[str, Any],
    baseline_id: str,
) -> dict[str, Any]:
    """Build a SegmentScoringEnvelope dict."""
    return {
        "issue_id": issue.get("id"),
        "issue_index": issue_index,
        "scoring_version": "1.0.0",
        "detector_outputs": {
            name: output.to_dict() if hasattr(output, "to_dict") else output
            for name, output in detector_outputs.items()
        },
        "composite_scores": composite_scores,
        "recommendation": recommendation,
        "derived_features": derived_features,
        "mistake_score": composite_scores.get("mistake_candidate", {}).get("score", 0.0),
        "pickup_score": composite_scores.get("pickup_candidate", {}).get("score", 0.0),
        "performance_score": composite_scores.get("performance_quality", {}).get("score", 0.0),
        "splice_score": composite_scores.get("splice_readiness", {}).get("score", 0.0),
        "priority": recommendation.get("priority", "info"),
        "baseline_id": baseline_id,
    }
