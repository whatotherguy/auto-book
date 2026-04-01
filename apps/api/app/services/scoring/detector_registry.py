"""Detector registry: ALL_DETECTORS list and run_all_detectors()."""

from __future__ import annotations

from typing import Callable, Optional

from .detector_output import DetectorOutput
from .detectors.text import detect_text_mismatch, detect_repeated_phrase, detect_skipped_text
from .detectors.timing import detect_abnormal_pause, detect_restart_gap, detect_rushed_delivery
from .detectors.audio import detect_click_transient, detect_clipping, detect_room_tone_shift, detect_punch_in_boundary
from .detectors.prosody import detect_flat_delivery, detect_weak_landing, detect_cadence_drift
from .detectors.context import detect_pickup_pattern, detect_continuity_mismatch

DetectorFunc = Callable[[dict, dict, Optional[dict]], DetectorOutput]

ALL_DETECTORS: list[tuple[str, DetectorFunc]] = [
    # Text detectors
    ("text_mismatch", detect_text_mismatch),
    ("repeated_phrase", detect_repeated_phrase),
    ("skipped_text", detect_skipped_text),
    # Timing detectors
    ("abnormal_pause", detect_abnormal_pause),
    ("restart_gap", detect_restart_gap),
    ("rushed_delivery", detect_rushed_delivery),
    # Audio detectors
    ("click_transient", detect_click_transient),
    ("clipping", detect_clipping),
    ("room_tone_shift", detect_room_tone_shift),
    ("punch_in_boundary", detect_punch_in_boundary),
    # Prosody detectors
    ("flat_delivery", detect_flat_delivery),
    ("weak_landing", detect_weak_landing),
    ("cadence_drift", detect_cadence_drift),
    # Context detectors
    ("pickup_pattern", detect_pickup_pattern),
    ("continuity_mismatch", detect_continuity_mismatch),
]


def run_all_detectors(
    features: dict,
    derived: dict,
    detector_configs: dict[str, dict] | None = None,
) -> dict[str, DetectorOutput]:
    """Run all 15 detectors and return a dict of name -> DetectorOutput."""
    configs = detector_configs or {}
    results: dict[str, DetectorOutput] = {}

    for name, func in ALL_DETECTORS:
        config = configs.get(name)
        if config and not config.get("enabled", True):
            continue
        results[name] = func(features, derived, config)

    return results
