"""Tests for advanced calibration features: ablation groups, narrator profiles."""

from app.services.scoring.calibration.config import ScoringConfig
from app.services.scoring.calibration.dataset import (
    CalibrationDataset,
    GroundTruth,
    make_clean_segment,
)
from app.services.scoring.calibration.advanced.ablation import (
    DETECTOR_GROUPS,
    run_single_ablation,
    run_group_ablation,
)
from app.services.scoring.calibration.advanced.narrator import (
    NarratorProfile,
    select_narrator_config,
)


def _make_segments():
    segments = []
    for i in range(5):
        seg = make_clean_segment(f"mistake_{i}")
        seg.features["spoken_text"] = "The quick brown fax"
        seg.features["issue_type"] = "substitution"
        seg.ground_truth = GroundTruth(is_mistake=True, priority="high")
        segments.append(seg.to_dict())
    for i in range(8):
        segments.append(make_clean_segment(f"clean_{i}").to_dict())
    return segments


def _get_baseline():
    from app.services.scoring.baseline import build_chapter_baseline
    segs = _make_segments()
    return build_chapter_baseline(
        [{"prosody_features_json": "{}", "audio_features_json": "{}"}] * len(segs),
        [], [],
    )


# --- Detector groups ---

def test_detector_groups_cover_all():
    all_detectors = set()
    for detectors in DETECTOR_GROUPS.values():
        all_detectors.update(detectors)
    assert len(all_detectors) == 15


def test_detector_groups_categories():
    assert "text" in DETECTOR_GROUPS
    assert "timing" in DETECTOR_GROUPS
    assert "audio" in DETECTOR_GROUPS
    assert "prosody" in DETECTOR_GROUPS
    assert "context" in DETECTOR_GROUPS


# --- Single ablation ---

def test_single_ablation_runs():
    segments = _make_segments()
    baseline = _get_baseline()
    results = run_single_ablation(ScoringConfig(), segments, baseline)
    assert len(results) > 0
    for entry in results:
        assert "detector" in entry
        assert "delta" in entry
        assert "base_score" in entry
        assert "ablated_score" in entry


def test_single_ablation_sorted_by_impact():
    segments = _make_segments()
    baseline = _get_baseline()
    results = run_single_ablation(ScoringConfig(), segments, baseline)
    deltas = [abs(r["delta"]) for r in results]
    assert deltas == sorted(deltas, reverse=True)


# --- Group ablation ---

def test_group_ablation_runs():
    segments = _make_segments()
    baseline = _get_baseline()
    results = run_group_ablation(ScoringConfig(), segments, baseline)
    assert len(results) == len(DETECTOR_GROUPS)
    for entry in results:
        assert "group" in entry
        assert "detectors" in entry
        assert "delta" in entry


# --- Narrator profile ---

def test_narrator_profile_to_dict():
    profile = NarratorProfile(
        narrator_id="narrator_a",
        config=ScoringConfig(),
        segment_count=50,
    )
    d = profile.to_dict()
    assert d["narrator_id"] == "narrator_a"
    assert d["segment_count"] == 50
    assert "config" in d


def test_select_narrator_config_known():
    profiles = {
        "narrator_a": NarratorProfile(
            narrator_id="narrator_a",
            config=ScoringConfig(metadata={"narrator": "a"}),
        ),
    }
    cfg = select_narrator_config("narrator_a", profiles)
    assert cfg.metadata.get("narrator") == "a"


def test_select_narrator_config_fallback():
    fallback = ScoringConfig(metadata={"fallback": True})
    cfg = select_narrator_config("unknown", {}, fallback_config=fallback)
    assert cfg.metadata.get("fallback") is True


def test_select_narrator_config_default():
    cfg = select_narrator_config("unknown", {})
    # Should return a default ScoringConfig
    assert isinstance(cfg, ScoringConfig)
