"""run_scoring_pipeline() — main entry point for the scoring engine."""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from sqlmodel import Session, select

from .baseline import build_chapter_baseline
from .composite import compute_all_composites
from .derived_features import compute_derived_features
from .detector_registry import run_all_detectors
from .envelope import build_envelope
from .features import extract_raw_features
from .recommendations import generate_recommendation
from .take_ranking import rank_alternate_takes

logger = logging.getLogger(__name__)


def _load_calibration_weights(session: Session | None) -> dict[str, dict[str, float]] | None:
    """Load active CalibrationProfile weights if available."""
    if session is None:
        return None
    try:
        from ...models import CalibrationProfile
        profile = session.exec(
            select(CalibrationProfile).where(CalibrationProfile.is_default == True)
        ).first()
        if profile and profile.weights_json:
            return json.loads(profile.weights_json)
    except Exception as exc:
        logger.debug("No calibration profile loaded: %s", exc)
    return None


def run_scoring_pipeline(
    issue_records: list[dict[str, Any]],
    audio_signals: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
    prosody_map: list[dict[str, Any]],
    manuscript_tokens: Sequence,
    spoken_tokens: Sequence,
    alignment: dict[str, Any],
    alt_take_clusters: list[dict[str, Any]],
    chapter: Any = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """Run the full scoring pipeline on all issues.

    Returns a dict with:
      - enriched_issues: updated issue records with scoring data
      - alt_take_clusters: updated clusters with rankings
      - envelopes: list of SegmentScoringEnvelope dicts
      - baseline: chapter baseline stats
    """
    logger.info("Running scoring pipeline on %d issues", len(issue_records))

    # Load calibration weights
    weights = _load_calibration_weights(session)

    # Step 1: Build adaptive baseline
    baseline = build_chapter_baseline(issue_records, prosody_map, audio_signals)
    baseline_id = f"chapter_{getattr(chapter, 'id', 'unknown')}"

    # Step 2-3: Extract features and derived features for all issues
    all_features: list[dict[str, Any]] = []
    for idx, issue in enumerate(issue_records):
        features = extract_raw_features(
            issue=issue,
            issue_index=idx,
            spoken_tokens=spoken_tokens,
            manuscript_tokens=manuscript_tokens,
            alignment=alignment,
            prosody_map=prosody_map,
            audio_signals=audio_signals,
            vad_segments=vad_segments,
            total_issues=len(issue_records),
        )
        all_features.append(features)

    all_derived: list[dict[str, Any]] = []
    for idx, features in enumerate(all_features):
        prev_features = all_features[idx - 1] if idx > 0 else None
        next_features = all_features[idx + 1] if idx < len(all_features) - 1 else None
        derived = compute_derived_features(features, baseline, prev_features, next_features)
        all_derived.append(derived)

    # Step 4-5: Run detectors and compute composite scores
    envelopes: list[dict[str, Any]] = []
    issue_envelopes: dict[int, dict[str, Any]] = {}  # For take ranking

    # Build alt-take membership lookup
    alt_take_membership: dict[int, tuple[dict, int]] = {}  # issue_index -> (cluster, member_count)
    for cluster in alt_take_clusters:
        member_count = len(cluster.get("members", []))
        for member in cluster.get("members", []):
            alt_take_membership[member.get("issue_index", -1)] = (cluster, member_count)

    for idx, (issue, features, derived) in enumerate(zip(issue_records, all_features, all_derived)):
        # Run 15 detectors
        detector_outputs = run_all_detectors(features, derived)

        # Compute 5 composite scores
        composite_scores = compute_all_composites(detector_outputs, weights)

        # Get alt-take context
        alt_info = alt_take_membership.get(idx)
        alt_cluster_id = None
        alt_member_count = 0
        if alt_info:
            alt_cluster_id = alt_info[0].get("id")
            alt_member_count = alt_info[1]

        # Generate recommendation
        recommendation = generate_recommendation(
            composite_scores,
            alt_take_cluster_id=alt_cluster_id,
            alt_take_member_count=alt_member_count,
        )

        # Build envelope
        envelope = build_envelope(
            issue=issue,
            issue_index=idx,
            detector_outputs=detector_outputs,
            composite_scores=composite_scores,
            recommendation=recommendation,
            derived_features=derived,
            baseline_id=baseline_id,
        )
        envelopes.append(envelope)
        issue_envelopes[idx] = envelope
        if issue.get("id"):
            issue_envelopes[issue["id"]] = envelope

        # Enrich issue record with scoring data
        issue["composite_scores"] = composite_scores
        issue["recommendation"] = recommendation
        issue["priority"] = recommendation.get("priority", "info")

        # Set model_action from recommendation (do NOT set editor_decision - that's user-only)
        issue["model_action"] = recommendation.get("model_action", "review")
        # Note: We deliberately do NOT set editor_decision here.
        # The model may suggest actions via model_action, but editor_decision is user-only.

    # Step 6: Rank alt-takes
    for cluster in alt_take_clusters:
        ranking = rank_alternate_takes(cluster, issue_envelopes)
        cluster["ranking"] = ranking
        if ranking.get("preferred_take_issue_id"):
            cluster["preferred_issue_id"] = ranking["preferred_take_issue_id"]

    logger.info("Scoring pipeline complete: %d envelopes, %d clusters ranked",
                len(envelopes), len(alt_take_clusters))

    return {
        "enriched_issues": issue_records,
        "alt_take_clusters": alt_take_clusters,
        "envelopes": envelopes,
        "baseline": baseline,
    }
