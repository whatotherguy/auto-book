"""SegmentLabel and LabeledDataset for calibration ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_labeled_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    """Load a labeled dataset from a JSON file.

    Each label has:
      - segment_id: str (unique identifier)
      - features: dict (raw feature catalog)
      - ground_truth: dict with:
          - is_mistake: bool
          - is_pickup: bool
          - priority: str ("critical" | "high" | "medium" | "low" | "info")
          - preferred_action: str
    """
    labels_file = dataset_path / "labels.json"
    if not labels_file.exists():
        return []

    data = json.loads(labels_file.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("segments", [])


def save_labeled_dataset(dataset_path: Path, segments: list[dict[str, Any]]) -> None:
    """Save a labeled dataset."""
    dataset_path.mkdir(parents=True, exist_ok=True)
    labels_file = dataset_path / "labels.json"
    labels_file.write_text(json.dumps(segments, indent=2), encoding="utf-8")


def validate_label(label: dict[str, Any]) -> list[str]:
    """Validate a segment label, returning list of errors."""
    errors = []
    if "segment_id" not in label:
        errors.append("missing segment_id")
    gt = label.get("ground_truth", {})
    if not isinstance(gt, dict):
        errors.append("ground_truth must be a dict")
    else:
        if "is_mistake" not in gt:
            errors.append("ground_truth.is_mistake required")
        if "is_pickup" not in gt:
            errors.append("ground_truth.is_pickup required")
    if "features" not in label:
        errors.append("missing features dict")
    return errors
