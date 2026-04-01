"""Tests for calibration config management: ScoringConfig, versioning, serialization."""

import json
from pathlib import Path

from app.services.scoring.calibration.config import (
    ScoringConfig,
    ConfigStore,
    RecommendationThresholds,
    NormalizationSettings,
    ALL_DETECTOR_NAMES,
    DEFAULT_THRESHOLD,
    default_config,
    config_from_weights,
)


# --- ScoringConfig basics ---

def test_default_config_has_all_detectors():
    cfg = default_config()
    for name in ALL_DETECTOR_NAMES:
        assert name in cfg.detector_thresholds
        assert name in cfg.detector_toggles
        assert cfg.detector_toggles[name] is True


def test_default_config_hash_is_deterministic():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    assert cfg1.config_hash == cfg2.config_hash
    assert len(cfg1.config_hash) == 12


def test_config_hash_changes_with_weights():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    cfg2.mistake_weights["text_mismatch"] = 0.99
    cfg2.config_hash = cfg2._compute_hash()
    assert cfg1.config_hash != cfg2.config_hash


def test_composite_weights_format():
    cfg = ScoringConfig()
    cw = cfg.composite_weights
    assert "mistake" in cw
    assert "pickup" in cw
    assert "performance" in cw
    assert "continuity" in cw
    assert "text_mismatch" in cw["mistake"]


def test_detector_configs_format():
    cfg = ScoringConfig()
    dc = cfg.detector_configs
    assert "text_mismatch" in dc
    assert dc["text_mismatch"]["enabled"] is True
    assert dc["text_mismatch"]["threshold"] == DEFAULT_THRESHOLD


def test_detector_configs_respects_toggles():
    cfg = ScoringConfig()
    cfg.detector_toggles["text_mismatch"] = False
    dc = cfg.detector_configs
    assert dc["text_mismatch"]["enabled"] is False


# --- Serialization ---

def test_to_dict_roundtrip():
    cfg = ScoringConfig(metadata={"test": True})
    d = cfg.to_dict()
    restored = ScoringConfig.from_dict(d)
    assert restored.config_hash == cfg.config_hash
    assert restored.mistake_weights == cfg.mistake_weights
    assert restored.metadata == cfg.metadata


def test_save_load_roundtrip(tmp_path):
    cfg = ScoringConfig(metadata={"narrator": "test"})
    path = cfg.save(tmp_path / "test_config.json")
    loaded = ScoringConfig.load(path)
    assert loaded.config_hash == cfg.config_hash
    assert loaded.metadata == cfg.metadata


def test_to_production_format():
    cfg = ScoringConfig()
    prod = cfg.to_production_format()
    assert "weights_json" in prod
    assert "thresholds_json" in prod
    weights = json.loads(prod["weights_json"])
    assert "mistake" in weights


# --- Diff ---

def test_diff_identical_configs():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    assert cfg1.diff(cfg2) == {}


def test_diff_detects_weight_changes():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    cfg2.mistake_weights["text_mismatch"] = 0.99
    diff = cfg1.diff(cfg2)
    assert "mistake_weights" in diff
    assert "text_mismatch" in diff["mistake_weights"]


def test_diff_detects_threshold_changes():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    cfg2.detector_thresholds["text_mismatch"] = 0.5
    diff = cfg1.diff(cfg2)
    assert "detector_thresholds" in diff


def test_diff_detects_toggle_changes():
    cfg1 = ScoringConfig()
    cfg2 = ScoringConfig()
    cfg2.detector_toggles["text_mismatch"] = False
    diff = cfg1.diff(cfg2)
    assert "detector_toggles" in diff


# --- Clone ---

def test_clone_preserves_weights():
    cfg = ScoringConfig()
    cloned = cfg.clone()
    assert cloned.mistake_weights == cfg.mistake_weights
    assert cloned.parent_version == cfg.version


def test_clone_with_overrides():
    cfg = ScoringConfig()
    cloned = cfg.clone(metadata={"custom": True})
    assert cloned.metadata == {"custom": True}


# --- ConfigStore ---

def test_config_store_save_load(tmp_path):
    store = ConfigStore(tmp_path / "configs")
    cfg = ScoringConfig(metadata={"test": True})
    path = store.save(cfg, "test_v1")
    loaded = store.load("test_v1")
    assert loaded.config_hash == cfg.config_hash


def test_config_store_list(tmp_path):
    store = ConfigStore(tmp_path / "configs")
    store.save(ScoringConfig(metadata={"a": 1}), "config_a")
    store.save(ScoringConfig(metadata={"b": 2}), "config_b")
    configs = store.list_configs()
    assert len(configs) == 2
    names = {c["name"] for c in configs}
    assert "config_a" in names
    assert "config_b" in names


# --- RecommendationThresholds ---

def test_recommendation_thresholds_defaults():
    rt = RecommendationThresholds()
    assert rt.mistake_trigger == 0.5
    assert rt.pickup_trigger == 0.6


def test_recommendation_thresholds_roundtrip():
    rt = RecommendationThresholds(mistake_trigger=0.7)
    restored = RecommendationThresholds.from_dict(rt.to_dict())
    assert restored.mistake_trigger == 0.7


# --- Convenience constructors ---

def test_config_from_weights():
    cfg = config_from_weights(
        mistake={"text_mismatch": 0.5, "repeated_phrase": 0.5},
        note="custom",
    )
    assert cfg.mistake_weights["text_mismatch"] == 0.5
    assert cfg.metadata["note"] == "custom"
