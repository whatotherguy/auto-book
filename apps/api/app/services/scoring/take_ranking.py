"""Alt-take comparison and ranking."""

from __future__ import annotations

from typing import Any

from ...detection_config import TAKE_PREFERENCE_WEIGHTS


def rank_alternate_takes(
    cluster: dict[str, Any],
    issue_envelopes: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Rank alternate takes within a cluster by composite scores."""
    members = cluster.get("members", [])
    if not members:
        return {
            "cluster_id": cluster.get("id"),
            "ranked_takes": [],
            "preferred_take_issue_id": None,
            "selection_reasons": [],
            "confidence": 0.0,
        }

    ranked_takes: list[dict[str, Any]] = []
    for member in members:
        issue_id = member.get("issue_id")
        issue_index = member.get("issue_index", 0)
        envelope = issue_envelopes.get(issue_id) or issue_envelopes.get(issue_index, {})
        composites = envelope.get("composite_scores", {})

        mistake = composites.get("mistake_candidate", {})
        performance = composites.get("performance_quality", {})
        continuity = composites.get("continuity_fit", {})
        splice = composites.get("splice_readiness", {})

        text_accuracy = 1.0 - mistake.get("score", 0.5)
        perf_quality = performance.get("score", 0.5)
        cont_fit = continuity.get("score", 0.5)
        splice_ready = splice.get("score", 0.5)

        total_score = (
            text_accuracy * TAKE_PREFERENCE_WEIGHTS["text_accuracy"]
            + perf_quality * TAKE_PREFERENCE_WEIGHTS["performance_quality"]
            + cont_fit * TAKE_PREFERENCE_WEIGHTS["continuity_fit"]
            + splice_ready * TAKE_PREFERENCE_WEIGHTS["splice_readiness"]
        )

        reasons = []
        if text_accuracy > 0.8:
            reasons.append("high_text_accuracy")
        # NOTE: Performance quality is used for ranking internally but not surfaced
        # to editors as a reason since it's ambiguous and not directly actionable.
        if cont_fit > 0.8:
            reasons.append("good_continuity")

        ranked_takes.append({
            "issue_id": issue_id,
            "issue_index": issue_index,
            "rank": 0,
            "total_score": round(total_score, 4),
            "performance_quality": round(perf_quality, 4),
            "continuity_fit": round(cont_fit, 4),
            "text_accuracy": round(text_accuracy, 4),
            "splice_readiness": round(splice_ready, 4),
            "reasons": reasons,
        })

    # Sort by total score descending
    ranked_takes.sort(key=lambda t: t["total_score"], reverse=True)
    for i, take in enumerate(ranked_takes):
        take["rank"] = i + 1

    preferred_id = ranked_takes[0]["issue_id"] if ranked_takes else None
    selection_reasons = ranked_takes[0]["reasons"] if ranked_takes else []

    # Confidence based on gap between top two
    confidence = 0.9
    if len(ranked_takes) >= 2:
        gap = ranked_takes[0]["total_score"] - ranked_takes[1]["total_score"]
        if gap < 0.05:
            confidence = 0.5
            selection_reasons.append("close_call")
        elif gap < 0.15:
            confidence = 0.7

    return {
        "cluster_id": cluster.get("id"),
        "ranked_takes": ranked_takes,
        "preferred_take_issue_id": preferred_id,
        "selection_reasons": selection_reasons,
        "confidence": round(confidence, 4),
    }
