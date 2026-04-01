"""Scoring configuration management: versioning, serialization, rollback."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ....detection_config import (
    CONTINUITY_WEIGHTS,
    MISTAKE_WEIGHTS,
    PERFORMANCE_WEIGHTS,
    PICKUP_WEIGHTS,
    TAKE_PREFERENCE_WEIGHTS,
)

# All 15 detectors
ALL_DETECTOR_NAMES = [
    "text_mismatch", "repeated_phrase", "skipped_text",
    "abnormal_pause", "restart_gap", "rushed_delivery",
    "click_transient", "clipping", "room_tone_shift", "punch_in_boundary",
    "flat_delivery", "weak_landing", "cadence_drift",
    "pickup_pattern", "continuity_mismatch",
]

DEFAULT_THRESHOLD = 0.3


@dataclass
class RecommendationThresholds:
    """Thresholds for editorial recommendation generation."""
    mistake_trigger: float = 0.5
    pickup_trigger: float = 0.6
    splice_trigger: float = 0.8
    splice_confidence_min: float = 0.7
    performance_trigger: float = 0.5
    ambiguity_min_composites: int = 2
    ambiguity_composite_threshold: float = 0.4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RecommendationThresholds:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class NormalizationSettings:
    """How composite weights are normalized."""
    strategy: str = "sum_to_one"  # "sum_to_one" | "max_normalize" | "raw"
    baseline_blend_ratio: float = 0.5  # Used when baseline is unstable
    min_stable_segments: int = 30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizationSettings:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ScoringConfig:
    """Complete scoring configuration — everything needed to reproduce a scoring run."""

    # Versioning
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_version: str | None = None
    config_hash: str = ""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Composite weights
    mistake_weights: dict[str, float] = field(default_factory=lambda: dict(MISTAKE_WEIGHTS))
    pickup_weights: dict[str, float] = field(default_factory=lambda: dict(PICKUP_WEIGHTS))
    performance_weights: dict[str, float] = field(default_factory=lambda: dict(PERFORMANCE_WEIGHTS))
    continuity_weights: dict[str, float] = field(default_factory=lambda: dict(CONTINUITY_WEIGHTS))
    take_preference_weights: dict[str, float] = field(default_factory=lambda: dict(TAKE_PREFERENCE_WEIGHTS))

    # Detector thresholds (per-detector trigger threshold)
    detector_thresholds: dict[str, float] = field(
        default_factory=lambda: {name: DEFAULT_THRESHOLD for name in ALL_DETECTOR_NAMES}
    )

    # Detector toggles (enable/disable individual detectors)
    detector_toggles: dict[str, bool] = field(
        default_factory=lambda: {name: True for name in ALL_DETECTOR_NAMES}
    )

    # Recommendation thresholds
    recommendation_thresholds: RecommendationThresholds = field(
        default_factory=RecommendationThresholds
    )

    # Normalization
    normalization: NormalizationSettings = field(default_factory=NormalizationSettings)

    def __post_init__(self) -> None:
        if not self.config_hash:
            self.config_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Deterministic hash of all scoring parameters (not metadata/timestamps)."""
        hashable = {
            "mistake_weights": sorted(self.mistake_weights.items()),
            "pickup_weights": sorted(self.pickup_weights.items()),
            "performance_weights": sorted(self.performance_weights.items()),
            "continuity_weights": sorted(self.continuity_weights.items()),
            "take_preference_weights": sorted(self.take_preference_weights.items()),
            "detector_thresholds": sorted(self.detector_thresholds.items()),
            "detector_toggles": sorted(self.detector_toggles.items()),
            "recommendation_thresholds": self.recommendation_thresholds.to_dict(),
            "normalization": self.normalization.to_dict(),
        }
        raw = json.dumps(hashable, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @property
    def composite_weights(self) -> dict[str, dict[str, float]]:
        """Return weights in the format expected by compute_all_composites()."""
        return {
            "mistake": dict(self.mistake_weights),
            "pickup": dict(self.pickup_weights),
            "performance": dict(self.performance_weights),
            "continuity": dict(self.continuity_weights),
        }

    @property
    def detector_configs(self) -> dict[str, dict[str, Any]]:
        """Return detector configs for run_all_detectors()."""
        configs: dict[str, dict[str, Any]] = {}
        for name in ALL_DETECTOR_NAMES:
            configs[name] = {
                "enabled": self.detector_toggles.get(name, True),
                "threshold": self.detector_thresholds.get(name, DEFAULT_THRESHOLD),
            }
        return configs

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "parent_version": self.parent_version,
            "config_hash": self.config_hash,
            "metadata": self.metadata,
            "mistake_weights": self.mistake_weights,
            "pickup_weights": self.pickup_weights,
            "performance_weights": self.performance_weights,
            "continuity_weights": self.continuity_weights,
            "take_preference_weights": self.take_preference_weights,
            "detector_thresholds": self.detector_thresholds,
            "detector_toggles": self.detector_toggles,
            "recommendation_thresholds": self.recommendation_thresholds.to_dict(),
            "normalization": self.normalization.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScoringConfig:
        """Deserialize from dict."""
        rec_thresh = d.get("recommendation_thresholds", {})
        norm = d.get("normalization", {})
        return cls(
            version=d.get("version", "1.0.0"),
            created_at=d.get("created_at", ""),
            parent_version=d.get("parent_version"),
            config_hash=d.get("config_hash", ""),
            metadata=d.get("metadata", {}),
            mistake_weights=d.get("mistake_weights", dict(MISTAKE_WEIGHTS)),
            pickup_weights=d.get("pickup_weights", dict(PICKUP_WEIGHTS)),
            performance_weights=d.get("performance_weights", dict(PERFORMANCE_WEIGHTS)),
            continuity_weights=d.get("continuity_weights", dict(CONTINUITY_WEIGHTS)),
            take_preference_weights=d.get("take_preference_weights", dict(TAKE_PREFERENCE_WEIGHTS)),
            detector_thresholds=d.get("detector_thresholds", {name: DEFAULT_THRESHOLD for name in ALL_DETECTOR_NAMES}),
            detector_toggles=d.get("detector_toggles", {name: True for name in ALL_DETECTOR_NAMES}),
            recommendation_thresholds=RecommendationThresholds.from_dict(rec_thresh) if rec_thresh else RecommendationThresholds(),
            normalization=NormalizationSettings.from_dict(norm) if norm else NormalizationSettings(),
        )

    def save(self, path: Path) -> Path:
        """Save config to a JSON file. Returns the file path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> ScoringConfig:
        """Load config from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def diff(self, other: ScoringConfig) -> dict[str, Any]:
        """Show differences between two configs."""
        changes: dict[str, Any] = {}
        for weight_name in ["mistake_weights", "pickup_weights", "performance_weights",
                            "continuity_weights", "take_preference_weights"]:
            self_w = getattr(self, weight_name)
            other_w = getattr(other, weight_name)
            diffs = {}
            for key in set(self_w) | set(other_w):
                sv = self_w.get(key, 0.0)
                ov = other_w.get(key, 0.0)
                if abs(sv - ov) > 1e-6:
                    diffs[key] = {"from": sv, "to": ov}
            if diffs:
                changes[weight_name] = diffs

        # Thresholds
        thresh_diffs = {}
        for name in ALL_DETECTOR_NAMES:
            sv = self.detector_thresholds.get(name, DEFAULT_THRESHOLD)
            ov = other.detector_thresholds.get(name, DEFAULT_THRESHOLD)
            if abs(sv - ov) > 1e-6:
                thresh_diffs[name] = {"from": sv, "to": ov}
        if thresh_diffs:
            changes["detector_thresholds"] = thresh_diffs

        # Toggles
        toggle_diffs = {}
        for name in ALL_DETECTOR_NAMES:
            sv = self.detector_toggles.get(name, True)
            ov = other.detector_toggles.get(name, True)
            if sv != ov:
                toggle_diffs[name] = {"from": sv, "to": ov}
        if toggle_diffs:
            changes["detector_toggles"] = toggle_diffs

        return changes

    def clone(self, **overrides: Any) -> ScoringConfig:
        """Create a copy with optional overrides. Sets parent_version for rollback chain."""
        d = self.to_dict()
        d["parent_version"] = self.version
        d["created_at"] = datetime.now(timezone.utc).isoformat()
        d["config_hash"] = ""  # Will be recomputed
        d.update(overrides)
        return ScoringConfig.from_dict(d)

    def to_production_format(self) -> dict[str, Any]:
        """Export in the format expected by the production CalibrationProfile model."""
        return {
            "weights_json": json.dumps(self.composite_weights),
            "thresholds_json": json.dumps(self.detector_thresholds),
            "metrics_json": json.dumps(self.metadata.get("evaluation_metrics", {})),
        }


class ConfigStore:
    """Manages a directory of versioned scoring configs."""

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, config: ScoringConfig, name: str | None = None) -> Path:
        """Save a config. Name defaults to config_hash."""
        filename = f"{name or config.config_hash}.json"
        return config.save(self.store_dir / filename)

    def load(self, name: str) -> ScoringConfig:
        """Load a config by name (with or without .json extension)."""
        if not name.endswith(".json"):
            name += ".json"
        return ScoringConfig.load(self.store_dir / name)

    def list_configs(self) -> list[dict[str, Any]]:
        """List all saved configs with summary info."""
        configs = []
        for p in sorted(self.store_dir.glob("*.json")):
            try:
                cfg = ScoringConfig.load(p)
                configs.append({
                    "name": p.stem,
                    "version": cfg.version,
                    "hash": cfg.config_hash,
                    "created_at": cfg.created_at,
                    "metadata": cfg.metadata,
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return configs

    def get_history(self, config: ScoringConfig) -> list[ScoringConfig]:
        """Walk the parent_version chain to reconstruct history."""
        history = [config]
        seen = {config.config_hash}
        current = config
        while current.parent_version:
            # Try to find parent by version
            parent = None
            for p in self.store_dir.glob("*.json"):
                try:
                    candidate = ScoringConfig.load(p)
                    if candidate.version == current.parent_version and candidate.config_hash not in seen:
                        parent = candidate
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
            if parent is None:
                break
            history.append(parent)
            seen.add(parent.config_hash)
            current = parent
        return history


def default_config() -> ScoringConfig:
    """Return a ScoringConfig with all production defaults."""
    return ScoringConfig()


def config_from_weights(
    mistake: dict[str, float] | None = None,
    pickup: dict[str, float] | None = None,
    performance: dict[str, float] | None = None,
    continuity: dict[str, float] | None = None,
    **metadata: Any,
) -> ScoringConfig:
    """Quick constructor for configs with custom weights."""
    return ScoringConfig(
        mistake_weights=mistake or dict(MISTAKE_WEIGHTS),
        pickup_weights=pickup or dict(PICKUP_WEIGHTS),
        performance_weights=performance or dict(PERFORMANCE_WEIGHTS),
        continuity_weights=continuity or dict(CONTINUITY_WEIGHTS),
        metadata=metadata,
    )
