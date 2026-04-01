"""Editorial recommendation engine — deterministic rules from composite scores."""

from __future__ import annotations

from typing import Any


def generate_recommendation(
    composite_scores: dict[str, Any],
    alt_take_cluster_id: int | None = None,
    alt_take_member_count: int = 0,
) -> dict[str, Any]:
    """Generate an editorial recommendation from composite scores."""
    mistake = composite_scores.get("mistake_candidate", {})
    pickup = composite_scores.get("pickup_candidate", {})
    performance = composite_scores.get("performance_quality", {})
    splice = composite_scores.get("splice_readiness", {})

    mistake_score = mistake.get("score", 0.0)
    pickup_score = pickup.get("score", 0.0)
    performance_score = performance.get("score", 0.0)
    splice_score = splice.get("score", 0.0)
    splice_confidence = splice.get("confidence", 0.0)

    # Collect all ambiguity flags
    all_ambiguity = []
    for comp in composite_scores.values():
        if isinstance(comp, dict):
            all_ambiguity.extend(comp.get("ambiguity_flags", []))

    # Deterministic rules (priority order)
    if splice_score > 0.8 and splice_confidence > 0.7:
        return _make_recommendation(
            action="safe_auto_cut",
            priority="low",
            reasoning=f"Splice readiness {splice_score:.2f} with high confidence. Safe for automatic cut.",
            confidence=splice_confidence,
            ambiguity=all_ambiguity,
        )

    if alt_take_member_count >= 2:
        return _make_recommendation(
            action="alt_take_available",
            priority="medium",
            reasoning=f"Part of alt-take cluster with {alt_take_member_count} takes. Review preferred selection.",
            confidence=0.8,
            ambiguity=all_ambiguity,
        )

    if pickup_score > 0.6:
        priority = "high" if pickup_score > 0.8 else "medium"
        return _make_recommendation(
            action="likely_pickup",
            priority=priority,
            reasoning=f"Pickup candidate score {pickup_score:.2f}. {'; '.join(pickup.get('reasons', [])[:2])}",
            confidence=pickup.get("confidence", 0.7),
            ambiguity=all_ambiguity,
        )

    if mistake_score > 0.5:
        priority = "critical" if mistake_score > 0.8 else "high"
        return _make_recommendation(
            action="review_mistake",
            priority=priority,
            reasoning=f"Mistake candidate score {mistake_score:.2f}. {'; '.join(mistake.get('reasons', [])[:2])}",
            confidence=mistake.get("confidence", 0.7),
            ambiguity=all_ambiguity,
        )

    # Check for ambiguous signals
    triggered_composites = sum(
        1 for comp in composite_scores.values()
        if isinstance(comp, dict) and comp.get("score", 0) > 0.4
    )
    if triggered_composites >= 2 and all_ambiguity:
        return _make_recommendation(
            action="manual_review_required",
            priority="medium",
            reasoning=f"Ambiguous signals: {triggered_composites} composites active. {'; '.join(all_ambiguity[:2])}",
            confidence=0.5,
            ambiguity=all_ambiguity,
        )

    if performance_score < 0.5:
        return _make_recommendation(
            action="review_mistake",
            priority="low",
            reasoning=f"Performance quality {performance_score:.2f} below threshold.",
            confidence=performance.get("confidence", 0.5),
            ambiguity=all_ambiguity,
        )

    return _make_recommendation(
        action="no_action",
        priority="info",
        reasoning="No significant issues detected.",
        confidence=0.9,
        ambiguity=all_ambiguity,
    )


def _make_recommendation(
    action: str,
    priority: str,
    reasoning: str,
    confidence: float,
    ambiguity: list[str] | None = None,
    related_issue_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "priority": priority,
        "reasoning": reasoning,
        "confidence": round(confidence, 4),
        "related_issue_ids": related_issue_ids or [],
        "ambiguity_flags": ambiguity or [],
    }
