"""Enhanced dataset layer for calibration: labeled segments, alt-take comparisons, splitting."""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GroundTruth:
    """Ground truth labels for a single segment."""
    is_mistake: bool = False
    is_pickup: bool = False
    needs_review: bool = False
    safe_to_auto_cut: bool = False
    preferred_action: str = "no_action"
    priority: str = "info"
    mistake_type: str = "none"  # text_mismatch|repetition|skipped|none
    annotator: str = "synthetic"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_mistake": self.is_mistake,
            "is_pickup": self.is_pickup,
            "needs_review": self.needs_review,
            "safe_to_auto_cut": self.safe_to_auto_cut,
            "preferred_action": self.preferred_action,
            "priority": self.priority,
            "mistake_type": self.mistake_type,
            "annotator": self.annotator,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GroundTruth:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LabeledSegment:
    """A segment with features and ground truth labels."""
    segment_id: str
    features: dict[str, Any]
    ground_truth: GroundTruth
    source: str = "real"  # real | synthetic
    narrator_id: str = ""
    session_id: str = ""
    derived_features: dict[str, Any] = field(default_factory=dict)
    detector_outputs: dict[str, Any] = field(default_factory=dict)
    perturbation_type: str = ""  # Set if synthetic

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "features": self.features,
            "ground_truth": self.ground_truth.to_dict(),
            "source": self.source,
            "narrator_id": self.narrator_id,
            "session_id": self.session_id,
            "derived_features": self.derived_features,
            "detector_outputs": self.detector_outputs,
            "perturbation_type": self.perturbation_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LabeledSegment:
        gt = d.get("ground_truth", {})
        return cls(
            segment_id=d.get("segment_id", ""),
            features=d.get("features", {}),
            ground_truth=GroundTruth.from_dict(gt) if isinstance(gt, dict) else GroundTruth(),
            source=d.get("source", "real"),
            narrator_id=d.get("narrator_id", ""),
            session_id=d.get("session_id", ""),
            derived_features=d.get("derived_features", {}),
            detector_outputs=d.get("detector_outputs", {}),
            perturbation_type=d.get("perturbation_type", ""),
        )

    def validate(self) -> list[str]:
        """Validate segment, returning list of errors."""
        errors = []
        if not self.segment_id:
            errors.append("missing segment_id")
        if not self.features:
            errors.append("missing features")
        return errors


@dataclass
class AltTakeGroundTruth:
    """Ground truth for an alt-take comparison group."""
    chosen_take_id: str = ""
    ranking: list[str] = field(default_factory=list)
    annotator: str = "synthetic"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen_take_id": self.chosen_take_id,
            "ranking": self.ranking,
            "annotator": self.annotator,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AltTakeGroundTruth:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AltTakeGroup:
    """A group of alternate takes for comparison evaluation."""
    group_id: str
    manuscript_text: str
    takes: list[dict[str, Any]]  # Each: {take_id, segment_id, features, composite_scores}
    ground_truth: AltTakeGroundTruth = field(default_factory=AltTakeGroundTruth)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "manuscript_text": self.manuscript_text,
            "takes": self.takes,
            "ground_truth": self.ground_truth.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AltTakeGroup:
        gt = d.get("ground_truth", {})
        return cls(
            group_id=d.get("group_id", ""),
            manuscript_text=d.get("manuscript_text", ""),
            takes=d.get("takes", []),
            ground_truth=AltTakeGroundTruth.from_dict(gt) if isinstance(gt, dict) else AltTakeGroundTruth(),
        )


@dataclass
class CalibrationDataset:
    """A complete calibration dataset with segments and alt-take groups."""
    name: str = ""
    description: str = ""
    segments: list[LabeledSegment] = field(default_factory=list)
    alt_take_groups: list[AltTakeGroup] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def mistake_count(self) -> int:
        return sum(1 for s in self.segments if s.ground_truth.is_mistake)

    @property
    def pickup_count(self) -> int:
        return sum(1 for s in self.segments if s.ground_truth.is_pickup)

    @property
    def clean_count(self) -> int:
        return sum(1 for s in self.segments
                   if not s.ground_truth.is_mistake and not s.ground_truth.is_pickup)

    @property
    def narrator_ids(self) -> set[str]:
        return {s.narrator_id for s in self.segments if s.narrator_id}

    def summary(self) -> dict[str, Any]:
        """Dataset statistics."""
        return {
            "name": self.name,
            "total_segments": self.segment_count,
            "mistakes": self.mistake_count,
            "pickups": self.pickup_count,
            "clean": self.clean_count,
            "synthetic": sum(1 for s in self.segments if s.source == "synthetic"),
            "real": sum(1 for s in self.segments if s.source == "real"),
            "narrators": len(self.narrator_ids),
            "alt_take_groups": len(self.alt_take_groups),
        }

    def filter_by_narrator(self, narrator_id: str) -> CalibrationDataset:
        """Return a new dataset filtered to a single narrator."""
        return CalibrationDataset(
            name=f"{self.name}_narrator_{narrator_id}",
            segments=[s for s in self.segments if s.narrator_id == narrator_id],
            alt_take_groups=[g for g in self.alt_take_groups],  # Keep all alt-takes for now
        )

    def filter_by_source(self, source: str) -> CalibrationDataset:
        """Filter to real or synthetic segments only."""
        return CalibrationDataset(
            name=f"{self.name}_{source}",
            segments=[s for s in self.segments if s.source == source],
            alt_take_groups=self.alt_take_groups if source == "real" else [],
        )

    def split(
        self,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
        stratify: bool = True,
    ) -> tuple[CalibrationDataset, CalibrationDataset, CalibrationDataset]:
        """Split into train/val/test sets. Optionally stratified by ground truth labels."""
        rng = random.Random(seed)

        if stratify:
            # Group by label category for stratified split
            buckets: dict[str, list[LabeledSegment]] = {
                "mistake": [], "pickup": [], "clean": [],
            }
            for s in self.segments:
                if s.ground_truth.is_mistake:
                    buckets["mistake"].append(s)
                elif s.ground_truth.is_pickup:
                    buckets["pickup"].append(s)
                else:
                    buckets["clean"].append(s)

            train_segs: list[LabeledSegment] = []
            val_segs: list[LabeledSegment] = []
            test_segs: list[LabeledSegment] = []

            for bucket_segs in buckets.values():
                rng.shuffle(bucket_segs)
                n = len(bucket_segs)
                n_train = int(n * train_ratio)
                n_val = int(n * val_ratio)
                train_segs.extend(bucket_segs[:n_train])
                val_segs.extend(bucket_segs[n_train:n_train + n_val])
                test_segs.extend(bucket_segs[n_train + n_val:])
        else:
            all_segs = list(self.segments)
            rng.shuffle(all_segs)
            n = len(all_segs)
            n_train = int(n * train_ratio)
            n_val = int(n * val_ratio)
            train_segs = all_segs[:n_train]
            val_segs = all_segs[n_train:n_train + n_val]
            test_segs = all_segs[n_train + n_val:]

        return (
            CalibrationDataset(name=f"{self.name}_train", segments=train_segs),
            CalibrationDataset(name=f"{self.name}_val", segments=val_segs),
            CalibrationDataset(name=f"{self.name}_test", segments=test_segs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "segments": [s.to_dict() for s in self.segments],
            "alt_take_groups": [g.to_dict() for g in self.alt_take_groups],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationDataset:
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            segments=[LabeledSegment.from_dict(s) for s in d.get("segments", [])],
            alt_take_groups=[AltTakeGroup.from_dict(g) for g in d.get("alt_take_groups", [])],
        )

    def save(self, path: Path) -> None:
        """Save dataset to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CalibrationDataset:
        """Load dataset from JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def merge(self, other: CalibrationDataset) -> CalibrationDataset:
        """Merge two datasets, deduplicating by segment_id."""
        existing_ids = {s.segment_id for s in self.segments}
        new_segs = [s for s in other.segments if s.segment_id not in existing_ids]
        existing_groups = {g.group_id for g in self.alt_take_groups}
        new_groups = [g for g in other.alt_take_groups if g.group_id not in existing_groups]
        return CalibrationDataset(
            name=f"{self.name}+{other.name}",
            segments=list(self.segments) + new_segs,
            alt_take_groups=list(self.alt_take_groups) + new_groups,
        )


def make_clean_segment(
    segment_id: str,
    narrator_id: str = "",
    speech_rate_wps: float = 3.0,
    rms_db: float = -20.0,
    f0_mean_hz: float = 150.0,
    f0_std_hz: float = 25.0,
) -> LabeledSegment:
    """Create a clean (no-defect) labeled segment with typical features."""
    return LabeledSegment(
        segment_id=segment_id,
        narrator_id=narrator_id,
        source="synthetic",
        features={
            "expected_text": "The quick brown fox jumps over the lazy dog",
            "spoken_text": "The quick brown fox jumps over the lazy dog",
            "issue_type": "equal",
            "confidence": 0.95,
            "duration_ms": 3000,
            "start_ms": 0,
            "end_ms": 3000,
            "alignment_op": "equal",
            "word_count_expected": 9,
            "word_count_spoken": 9,
            "word_count_ratio": 1.0,
            "whisper_word_confidence": 0.95,
            "speech_rate_wps": speech_rate_wps,
            "f0_mean_hz": f0_mean_hz,
            "f0_std_hz": f0_std_hz,
            "f0_contour": [],
            "energy_contour": [],
            "pause_before_ms": 200,
            "pause_after_ms": 200,
            "rms_db": rms_db,
            "spectral_centroid_hz": 1500,
            "zero_crossing_rate": 0.1,
            "onset_strength_max": 1.0,
            "onset_strength_mean": 0.5,
            "bandwidth_hz": 2000,
            "crest_factor": 8.0,
            "has_click_marker": False,
            "click_marker_confidence": 0.0,
            "has_abrupt_cutoff": False,
            "has_silence_gap": False,
            "silence_gap_ms": 0,
            "has_onset_burst": False,
            "restart_pattern_detected": False,
            "is_first_sentence": False,
            "is_last_sentence": False,
        },
        ground_truth=GroundTruth(
            is_mistake=False,
            is_pickup=False,
            needs_review=False,
            safe_to_auto_cut=False,
            preferred_action="no_action",
            priority="info",
        ),
    )
