"""Scoring engine interface: clean adapter between harness and production scoring pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..baseline import build_chapter_baseline
from ..composite import compute_all_composites
from ..derived_features import compute_derived_features
from ..detector_registry import run_all_detectors
from ..recommendations import generate_recommendation
from .config import ScoringConfig


@dataclass
class ScoringResult:
    """Result of scoring a single segment."""
    segment_id: str = ""
    detector_outputs: dict[str, Any] = field(default_factory=dict)
    composite_scores: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)
    derived_features: dict[str, Any] = field(default_factory=dict)

    @property
    def mistake_score(self) -> float:
        return self.composite_scores.get("mistake_candidate", {}).get("score", 0.0)

    @property
    def pickup_score(self) -> float:
        return self.composite_scores.get("pickup_candidate", {}).get("score", 0.0)

    @property
    def performance_score(self) -> float:
        return self.composite_scores.get("performance_quality", {}).get("score", 0.0)

    @property
    def continuity_score(self) -> float:
        return self.composite_scores.get("continuity_fit", {}).get("score", 0.0)

    @property
    def splice_score(self) -> float:
        return self.composite_scores.get("splice_readiness", {}).get("score", 0.0)

    @property
    def action(self) -> str:
        return self.recommendation.get("action", "no_action")

    @property
    def priority(self) -> str:
        return self.recommendation.get("priority", "info")

    @property
    def is_flagged(self) -> bool:
        """Whether this segment was flagged for any human review."""
        return self.action not in ("no_action", "safe_auto_cut")

    def to_prediction(self, config: ScoringConfig) -> dict[str, Any]:
        """Convert to prediction dict for metric evaluation."""
        thresh = config.recommendation_thresholds
        return {
            "is_mistake": self.mistake_score > thresh.mistake_trigger,
            "is_pickup": self.pickup_score > thresh.pickup_trigger,
            "priority": self.priority,
            "action": self.action,
            "safe_to_auto_cut": self.splice_score > thresh.splice_trigger,
            "needs_review": self.is_flagged,
            "mistake_score": self.mistake_score,
            "pickup_score": self.pickup_score,
            "performance_score": self.performance_score,
            "splice_score": self.splice_score,
        }


class ScoringEngineInterface:
    """Adapter that connects the calibration harness to the production scoring pipeline.

    Allows the harness to:
    - Inject different weight sets per run
    - Adjust thresholds dynamically
    - Enable/disable detectors
    - Use different normalization strategies
    """

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()

    def build_baseline(self, segments: list[dict[str, Any]]) -> dict[str, Any]:
        """Build chapter baseline from segment features.

        Adapts segment feature dicts to the format expected by build_chapter_baseline.
        """
        dummy_issues = []
        prosody_map: dict[int, dict] = {}

        for i, seg in enumerate(segments):
            # Build minimal issue record for baseline extraction
            prosody = {}
            for key in ["speech_rate_wps", "f0_mean_hz", "f0_std_hz", "pause_before_ms"]:
                if key in seg:
                    prosody[key] = seg[key]

            audio = {}
            for key in ["rms_db", "spectral_centroid_hz"]:
                if key in seg:
                    audio[key] = seg[key]

            dummy_issues.append({
                "prosody_features_json": "{}",
                "audio_features_json": "{}",
            })
            if prosody:
                prosody_map[i] = prosody

        baseline = build_chapter_baseline(dummy_issues, [], [])

        # Override baseline with actual feature statistics if we have enough data
        if len(segments) >= 3:
            _update_baseline_from_features(baseline, segments)

        return baseline

    def score_segment(
        self,
        features: dict[str, Any],
        baseline: dict[str, Any],
    ) -> ScoringResult:
        """Score a single segment using the current config."""
        derived = compute_derived_features(features, baseline)

        detector_outputs = run_all_detectors(
            features, derived, self.config.detector_configs,
        )

        composites = compute_all_composites(
            detector_outputs, self.config.composite_weights,
        )

        recommendation = generate_recommendation(composites)

        return ScoringResult(
            detector_outputs={name: out.to_dict() for name, out in detector_outputs.items()},
            composite_scores=composites,
            recommendation=recommendation,
            derived_features=derived,
        )

    def score_batch(
        self,
        segments: list[dict[str, Any]],
        baseline: dict[str, Any] | None = None,
    ) -> list[ScoringResult]:
        """Score a batch of segments. Builds baseline from batch if not provided."""
        if baseline is None:
            baseline = self.build_baseline(segments)

        results = []
        for seg in segments:
            result = self.score_segment(seg, baseline)
            results.append(result)
        return results

    def score_with_config(
        self,
        config: ScoringConfig,
        segments: list[dict[str, Any]],
        baseline: dict[str, Any] | None = None,
    ) -> list[ScoringResult]:
        """Score segments with a specific config (temporary swap)."""
        original = self.config
        self.config = config
        try:
            return self.score_batch(segments, baseline)
        finally:
            self.config = original


def _update_baseline_from_features(baseline: dict, segments: list[dict]) -> None:
    """Update baseline statistics from actual segment features."""
    import statistics

    def _stat(values: list[float]) -> tuple[float, float]:
        if len(values) < 2:
            return (values[0] if values else 0.0, 1.0)
        return (statistics.mean(values), max(statistics.stdev(values), 0.01))

    rates = [s["speech_rate_wps"] for s in segments if s.get("speech_rate_wps")]
    if rates:
        baseline["mean_speech_rate"], baseline["std_speech_rate"] = _stat(rates)

    rms_vals = [s["rms_db"] for s in segments if s.get("rms_db") is not None]
    if rms_vals:
        baseline["mean_rms_db"], baseline["std_rms_db"] = _stat(rms_vals)

    f0_vals = [s["f0_mean_hz"] for s in segments if s.get("f0_mean_hz") is not None]
    if f0_vals:
        baseline["mean_f0"], baseline["std_f0"] = _stat(f0_vals)

    f0_std_vals = [s["f0_std_hz"] for s in segments if s.get("f0_std_hz") is not None]
    if f0_std_vals:
        baseline["mean_f0_std"], baseline["std_f0_std"] = _stat(f0_std_vals)

    centroid_vals = [s["spectral_centroid_hz"] for s in segments if s.get("spectral_centroid_hz")]
    if centroid_vals:
        baseline["mean_spectral_centroid"], baseline["std_spectral_centroid"] = _stat(centroid_vals)

    pause_vals = [s["pause_before_ms"] for s in segments if s.get("pause_before_ms") is not None]
    if pause_vals:
        baseline["mean_pause"], baseline["std_pause"] = _stat(pause_vals)

    baseline["sample_count"] = len(segments)
    baseline["is_stable"] = len(segments) >= 30
