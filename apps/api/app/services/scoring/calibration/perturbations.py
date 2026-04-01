"""Synthetic perturbation engine: 8 parameterized, seeded defect injection types.

Each perturbation operates on a feature dict (not audio), mutating values
to simulate realistic defects. All perturbations are reproducible via seed.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any

from .dataset import GroundTruth, LabeledSegment


@dataclass
class PerturbationSpec:
    """Specification for a single perturbation."""
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "params": self.params, "seed": self.seed}


# ---------------------------------------------------------------------------
# Individual perturbation implementations
# ---------------------------------------------------------------------------

def _inject_click(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate click/transient artifact in feature space."""
    intensity = params.get("intensity", rng.uniform(0.6, 1.0))
    features["has_click_marker"] = True
    features["click_marker_confidence"] = intensity
    features["crest_factor"] = max(features.get("crest_factor", 8.0), 12.0 + intensity * 6.0)
    features["zero_crossing_rate"] = max(features.get("zero_crossing_rate", 0.1), 0.3 + intensity * 0.2)
    features["onset_strength_max"] = max(features.get("onset_strength_max", 1.0), 3.0 + intensity * 3.0)
    features["spectral_centroid_hz"] = max(features.get("spectral_centroid_hz", 1500), 2000 + intensity * 2000)
    return features


def _inject_silence_expansion(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate expanded silence (long pause / gap)."""
    factor = params.get("factor", rng.uniform(2.0, 5.0))
    base_pause = features.get("pause_before_ms", 200)
    expanded = int(base_pause * factor)
    features["pause_before_ms"] = max(expanded, 1500)
    features["has_silence_gap"] = True
    features["silence_gap_ms"] = features["pause_before_ms"]
    return features


def _inject_silence_compression(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate compressed silence (unnaturally short gaps)."""
    factor = params.get("factor", rng.uniform(0.05, 0.3))
    base_pause = features.get("pause_before_ms", 200)
    features["pause_before_ms"] = max(10, int(base_pause * factor))
    features["pause_after_ms"] = max(10, int(features.get("pause_after_ms", 200) * factor))
    return features


def _inject_repeated_phrase(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate repeated phrase / false start."""
    spoken = features.get("spoken_text", "The quick brown fox")
    words = spoken.split()
    n_repeats = params.get("n_repeats", 1)
    span = params.get("span_words", min(3, len(words)))

    if words and span > 0:
        repeat_start = rng.randint(0, max(0, len(words) - span))
        repeat_words = words[repeat_start:repeat_start + span]
        for _ in range(n_repeats):
            insert_pos = repeat_start + span
            for i, w in enumerate(repeat_words):
                words.insert(insert_pos + i, w)

    features["spoken_text"] = " ".join(words)
    features["issue_type"] = "repetition"
    features["confidence"] = rng.uniform(0.80, 0.96)
    return features


def _inject_restart(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate pickup/restart pattern."""
    gap_ms = params.get("gap_ms", rng.randint(300, 2000))
    has_click = params.get("has_click", rng.random() > 0.4)

    features["issue_type"] = "pickup_restart"
    features["confidence"] = rng.uniform(0.65, 0.85)
    features["pause_before_ms"] = gap_ms
    features["has_silence_gap"] = True
    features["silence_gap_ms"] = gap_ms
    features["restart_pattern_detected"] = True

    if has_click:
        features["has_click_marker"] = True
        features["click_marker_confidence"] = rng.uniform(0.5, 0.9)
        features["has_abrupt_cutoff"] = True

    return features


def _inject_pacing_change(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate speech rate anomaly (rushed or slow)."""
    rate_factor = params.get("rate_factor", rng.choice([
        rng.uniform(0.4, 0.6),   # Very slow
        rng.uniform(1.6, 2.5),   # Very fast
    ]))
    base_rate = features.get("speech_rate_wps", 3.0)
    features["speech_rate_wps"] = base_rate * rate_factor
    # Adjust duration inversely
    base_duration = features.get("duration_ms", 3000)
    features["duration_ms"] = int(base_duration / rate_factor)
    return features


def _inject_gain_shift(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate gain/energy shift (recording level change)."""
    db_delta = params.get("db_delta", rng.choice([
        rng.uniform(-12, -6),  # Significant drop
        rng.uniform(3, 8),     # Significant boost
    ]))
    base_rms = features.get("rms_db", -20.0)
    features["rms_db"] = max(-60.0, min(0.0, base_rms + db_delta))

    # Adjust crest factor — boosted signal has lower crest factor
    if db_delta > 0:
        features["crest_factor"] = max(2.0, features.get("crest_factor", 8.0) - db_delta * 0.5)

    return features


def _inject_clipping(features: dict, rng: random.Random, params: dict) -> dict:
    """Simulate clipping (signal exceeding digital ceiling)."""
    severity = params.get("severity", rng.uniform(0.5, 1.0))
    # Clipped audio: high RMS, low crest factor
    features["rms_db"] = -3.0 + severity * 2.5  # Range: -3.0 to -0.5 dBFS
    features["crest_factor"] = max(1.5, 6.0 - severity * 4.0)  # Range: 6.0 to 2.0
    features["has_onset_burst"] = severity > 0.7
    return features


# ---------------------------------------------------------------------------
# Perturbation registry
# ---------------------------------------------------------------------------

PERTURBATION_TYPES: dict[str, Any] = {
    "click_injection": _inject_click,
    "silence_expansion": _inject_silence_expansion,
    "silence_compression": _inject_silence_compression,
    "repeated_phrase": _inject_repeated_phrase,
    "restart_simulation": _inject_restart,
    "pacing_change": _inject_pacing_change,
    "gain_shift": _inject_gain_shift,
    "clipping_simulation": _inject_clipping,
}


def apply_perturbation(
    features: dict[str, Any],
    spec: PerturbationSpec,
) -> dict[str, Any]:
    """Apply a single perturbation to a feature dict. Returns mutated copy."""
    perturbed = copy.deepcopy(features)
    rng = random.Random(spec.seed)

    if spec.type == "combined":
        # Apply 2-3 random perturbation types
        types = list(PERTURBATION_TYPES.keys())
        n = rng.randint(2, 3)
        chosen = rng.sample(types, k=min(n, len(types)))
        for t in chosen:
            sub_spec = PerturbationSpec(type=t, params=spec.params, seed=spec.seed + hash(t))
            sub_rng = random.Random(sub_spec.seed)
            perturbed = PERTURBATION_TYPES[t](perturbed, sub_rng, sub_spec.params)
        return perturbed

    func = PERTURBATION_TYPES.get(spec.type)
    if func is None:
        raise ValueError(f"Unknown perturbation type: {spec.type}")

    return func(perturbed, rng, spec.params)


def ground_truth_for_perturbation(perturbation_type: str) -> GroundTruth:
    """Return expected ground truth labels for a perturbation type."""
    mapping = {
        "click_injection": GroundTruth(
            is_mistake=False, is_pickup=False, needs_review=True,
            preferred_action="manual_review_required", priority="medium",
            mistake_type="none", annotator="synthetic",
        ),
        "silence_expansion": GroundTruth(
            is_mistake=False, is_pickup=True, needs_review=True,
            preferred_action="likely_pickup", priority="medium",
            mistake_type="none", annotator="synthetic",
        ),
        "silence_compression": GroundTruth(
            is_mistake=False, is_pickup=False, needs_review=False,
            preferred_action="no_action", priority="low",
            mistake_type="none", annotator="synthetic",
        ),
        "repeated_phrase": GroundTruth(
            is_mistake=True, is_pickup=False, needs_review=True,
            preferred_action="review_mistake", priority="high",
            mistake_type="repetition", annotator="synthetic",
        ),
        "restart_simulation": GroundTruth(
            is_mistake=False, is_pickup=True, needs_review=True,
            preferred_action="likely_pickup", priority="high",
            mistake_type="none", annotator="synthetic",
        ),
        "pacing_change": GroundTruth(
            is_mistake=False, is_pickup=False, needs_review=True,
            preferred_action="review_mistake", priority="low",
            mistake_type="none", annotator="synthetic",
        ),
        "gain_shift": GroundTruth(
            is_mistake=False, is_pickup=False, needs_review=True,
            preferred_action="manual_review_required", priority="medium",
            mistake_type="none", annotator="synthetic",
        ),
        "clipping_simulation": GroundTruth(
            is_mistake=False, is_pickup=False, needs_review=True,
            preferred_action="manual_review_required", priority="medium",
            mistake_type="none", annotator="synthetic",
        ),
        "combined": GroundTruth(
            is_mistake=True, is_pickup=False, needs_review=True,
            preferred_action="manual_review_required", priority="high",
            mistake_type="none", annotator="synthetic",
        ),
    }
    return mapping.get(perturbation_type, GroundTruth())


def generate_synthetic_dataset(
    base_features: list[dict[str, Any]],
    n_per_type: int = 10,
    seed: int = 42,
    include_clean: bool = True,
    perturbation_types: list[str] | None = None,
) -> list[LabeledSegment]:
    """Generate a synthetic dataset from base features with all perturbation types.

    Args:
        base_features: Clean feature dicts to use as templates.
        n_per_type: Number of synthetic segments per perturbation type.
        seed: Master seed for reproducibility.
        include_clean: Whether to include unperturbed clean segments.
        perturbation_types: Subset of types to use (None = all).

    Returns:
        List of LabeledSegment with synthetic ground truth.
    """
    rng = random.Random(seed)
    types = perturbation_types or list(PERTURBATION_TYPES.keys()) + ["combined"]
    segments: list[LabeledSegment] = []

    # Clean segments
    if include_clean and base_features:
        for i, feat in enumerate(base_features):
            segments.append(LabeledSegment(
                segment_id=f"synthetic_clean_{i}",
                features=copy.deepcopy(feat),
                ground_truth=GroundTruth(
                    is_mistake=False, is_pickup=False, needs_review=False,
                    preferred_action="no_action", priority="info",
                    annotator="synthetic",
                ),
                source="synthetic",
                perturbation_type="clean",
            ))

    # Perturbed segments
    for p_type in types:
        for i in range(n_per_type):
            if not base_features:
                break
            base = rng.choice(base_features)
            seg_seed = rng.randint(0, 2**31)
            spec = PerturbationSpec(type=p_type, seed=seg_seed)
            perturbed = apply_perturbation(base, spec)

            segments.append(LabeledSegment(
                segment_id=f"synthetic_{p_type}_{i}",
                features=perturbed,
                ground_truth=ground_truth_for_perturbation(p_type),
                source="synthetic",
                perturbation_type=p_type,
            ))

    return segments


# ---------------------------------------------------------------------------
# Session drift simulation (progressive degradation)
# ---------------------------------------------------------------------------

def apply_session_drift(
    features: dict[str, Any],
    session_position: float,  # 0.0 = start of session, 1.0 = end
    drift_intensity: float = 1.0,
    seed: int = 42,
) -> dict[str, Any]:
    """Simulate narrator fatigue by progressively degrading features.

    As session_position increases (0→1), apply subtle degradation:
    - Speech rate slows slightly
    - F0 variation decreases (flatter delivery)
    - Energy drops
    - Pauses get longer
    """
    rng = random.Random(seed + int(session_position * 1000))
    drifted = copy.deepcopy(features)
    t = session_position * drift_intensity

    # Speech rate decreases 0-15%
    rate = drifted.get("speech_rate_wps", 3.0)
    drifted["speech_rate_wps"] = rate * (1.0 - t * 0.15 + rng.gauss(0, 0.02))

    # F0 variation decreases (flatter)
    f0_std = drifted.get("f0_std_hz", 25.0)
    drifted["f0_std_hz"] = max(5.0, f0_std * (1.0 - t * 0.3 + rng.gauss(0, 0.03)))

    # Energy drops 0-4 dB
    rms = drifted.get("rms_db", -20.0)
    drifted["rms_db"] = rms - t * 4.0 + rng.gauss(0, 0.5)

    # Pauses get longer 0-40%
    pause = drifted.get("pause_before_ms", 200)
    drifted["pause_before_ms"] = int(pause * (1.0 + t * 0.4 + rng.gauss(0, 0.05)))

    return drifted


def apply_noise_degradation(
    features: dict[str, Any],
    noise_level: float,  # 0.0 = clean, 1.0 = very noisy
    seed: int = 42,
) -> dict[str, Any]:
    """Simulate varying recording quality by adding noise characteristics.

    Higher noise_level → lower SNR, higher spectral centroid, lower confidence.
    """
    rng = random.Random(seed)
    noisy = copy.deepcopy(features)

    # RMS noise floor rises
    noisy["rms_db"] = noisy.get("rms_db", -20.0) + noise_level * 6.0

    # Spectral centroid shifts up (noise adds high frequency energy)
    noisy["spectral_centroid_hz"] = noisy.get("spectral_centroid_hz", 1500) + noise_level * 800

    # ZCR increases with noise
    noisy["zero_crossing_rate"] = min(0.5, noisy.get("zero_crossing_rate", 0.1) + noise_level * 0.15)

    # Whisper confidence decreases
    noisy["whisper_word_confidence"] = max(0.3, noisy.get("whisper_word_confidence", 0.95) - noise_level * 0.4)

    # F0 extraction becomes less reliable
    if rng.random() < noise_level * 0.5:
        noisy["f0_mean_hz"] = None
        noisy["f0_std_hz"] = None

    return noisy
