"""Editorial recommendation engine — deterministic rules from composite scores."""

from __future__ import annotations

from typing import Any

# Map internal recommendation actions to editor-facing model_action values
_ACTION_TO_MODEL_ACTION = {
    "safe_auto_cut": "safe_cut",
    "alt_take_available": "compare_takes",
    "likely_pickup": "review",
    "review_mistake": "review",
    "manual_review_required": "review",
    "no_action": "ignore",
    # NEW: Secondary issues get lower visibility
    "secondary_signal": "ignore",
}


def map_action_to_model_action(action: str) -> str:
    """Convert internal recommendation action to editor-facing model_action."""
    return _ACTION_TO_MODEL_ACTION.get(action, "review")


def generate_recommendation(
    composite_scores: dict[str, Any],
    alt_take_cluster_id: int | None = None,
    alt_take_member_count: int = 0,
    is_secondary: bool = False,
    issue_type: str | None = None,
) -> dict[str, Any]:
    """Generate an editorial recommendation from composite scores.
    
    CORROBORATION-FIRST LOGIC:
    - Secondary issues (is_secondary=True) are demoted to low priority
    - This prevents pure signal artifacts from cluttering the editor's view
    - Secondary issues remain available for debugging and specialized review
    
    Priority order for PRIMARY issues:
    1. Splice readiness (safe auto-cut)
    2. Alt-take clusters
    3. Pickup candidates (with text/signal corroboration)
    4. Mistake candidates (text mismatch, repetition)
    5. Ambiguous multi-signal cases
    
    SECONDARY issues get "secondary_signal" action and "info" priority.
    """
    # CORROBORATION-FIRST: Handle secondary issues early
    # Secondary issues are available but have lower visibility
    if is_secondary:
        # Build appropriate reasoning based on issue type
        if issue_type == "non_speech_marker":
            reasoning_text = (
                f"Secondary {issue_type} issue. "
                "Non-speech markers are low-priority by default configuration. "
                "Available for specialized review but not prioritized."
            )
        else:
            reasoning_text = (
                f"Secondary {issue_type or 'signal'} issue. "
                "Pure audio signal without corroborating evidence or below confidence threshold. "
                "Available for specialized review but not prioritized."
            )
        
        return _make_recommendation(
            action="secondary_signal",
            priority="info",
            reasoning=reasoning_text,
            confidence=0.5,
            ambiguity=[],
            is_secondary=True,
        )
    
    mistake = composite_scores.get("mistake_candidate", {})
    pickup = composite_scores.get("pickup_candidate", {})
    splice = composite_scores.get("splice_readiness", {})

    mistake_score = mistake.get("score", 0.0)
    pickup_score = pickup.get("score", 0.0)
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

    # NOTE: performance_quality is intentionally NOT used for editorial decision routing.
    # It remains available for alt-take ranking and debugging, but does not trigger
    # editor-facing actions since it is ambiguous and not directly actionable.

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
    is_secondary: bool = False,
) -> dict[str, Any]:
    return {
        "action": action,
        # model_action is the editor-facing action value
        "model_action": map_action_to_model_action(action),
        "priority": priority,
        "reasoning": reasoning,
        "confidence": round(confidence, 4),
        "related_issue_ids": related_issue_ids or [],
        "ambiguity_flags": ambiguity or [],
        # NEW: Expose is_secondary for downstream filtering
        "is_secondary": is_secondary,
    }
