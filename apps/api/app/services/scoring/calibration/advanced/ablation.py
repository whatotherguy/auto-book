"""Ablation testing: measure impact of removing individual detectors or detector groups."""

from __future__ import annotations

import copy
from typing import Any

from ..config import ScoringConfig, ALL_DETECTOR_NAMES
from ..optimizer import ablation_analysis
from ..simulation import run_simulation


# Detector categories for group ablation
DETECTOR_GROUPS = {
    "text": ["text_mismatch", "repeated_phrase", "skipped_text"],
    "timing": ["abnormal_pause", "restart_gap", "rushed_delivery"],
    "audio": ["click_transient", "clipping", "room_tone_shift", "punch_in_boundary"],
    "prosody": ["flat_delivery", "weak_landing", "cadence_drift"],
    "context": ["pickup_pattern", "continuity_mismatch"],
}


def run_single_ablation(
    config: ScoringConfig,
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ablate each detector individually and measure impact."""
    base_result = run_simulation(config, segments, baseline)

    ablated_results = {}
    for detector_name in ALL_DETECTOR_NAMES:
        if not config.detector_toggles.get(detector_name, True):
            continue  # Already disabled
        ablated_cfg = copy.deepcopy(config)
        ablated_cfg.detector_toggles[detector_name] = False
        ablated_cfg.config_hash = ablated_cfg._compute_hash()
        ablated_results[detector_name] = run_simulation(ablated_cfg, segments, baseline)

    return ablation_analysis(base_result, ablated_results)


def run_group_ablation(
    config: ScoringConfig,
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ablate each detector category group and measure impact."""
    base_result = run_simulation(config, segments, baseline)

    results = []
    for group_name, detector_names in DETECTOR_GROUPS.items():
        ablated_cfg = copy.deepcopy(config)
        for name in detector_names:
            ablated_cfg.detector_toggles[name] = False
        ablated_cfg.config_hash = ablated_cfg._compute_hash()

        ablated_result = run_simulation(ablated_cfg, segments, baseline)
        base_score = base_result.combined_score
        ablated_score = ablated_result.combined_score

        results.append({
            "group": group_name,
            "detectors": detector_names,
            "base_score": round(base_score, 4),
            "ablated_score": round(ablated_score, 4),
            "delta": round(base_score - ablated_score, 4),
            "impact": "positive" if (base_score - ablated_score) > 0.01
                      else ("negative" if (base_score - ablated_score) < -0.01 else "neutral"),
        })

    return sorted(results, key=lambda x: abs(x["delta"]), reverse=True)
