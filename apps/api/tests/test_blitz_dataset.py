"""Tests for calibration dataset layer."""

from pathlib import Path

from app.services.scoring.calibration.dataset import (
    CalibrationDataset,
    LabeledSegment,
    GroundTruth,
    AltTakeGroup,
    AltTakeGroundTruth,
    make_clean_segment,
)


# --- GroundTruth ---

def test_ground_truth_defaults():
    gt = GroundTruth()
    assert gt.is_mistake is False
    assert gt.is_pickup is False
    assert gt.preferred_action == "no_action"


def test_ground_truth_roundtrip():
    gt = GroundTruth(is_mistake=True, priority="high", mistake_type="repetition")
    restored = GroundTruth.from_dict(gt.to_dict())
    assert restored.is_mistake is True
    assert restored.priority == "high"
    assert restored.mistake_type == "repetition"


# --- LabeledSegment ---

def test_make_clean_segment():
    seg = make_clean_segment("test_001", narrator_id="narrator_a")
    assert seg.segment_id == "test_001"
    assert seg.narrator_id == "narrator_a"
    assert seg.ground_truth.is_mistake is False
    assert seg.features["speech_rate_wps"] == 3.0
    assert seg.features["expected_text"] == seg.features["spoken_text"]


def test_labeled_segment_roundtrip():
    seg = make_clean_segment("seg_001")
    d = seg.to_dict()
    restored = LabeledSegment.from_dict(d)
    assert restored.segment_id == "seg_001"
    assert restored.features == seg.features


def test_labeled_segment_validate():
    seg = LabeledSegment(segment_id="", features={}, ground_truth=GroundTruth())
    errors = seg.validate()
    assert "missing segment_id" in errors
    assert "missing features" in errors

    good_seg = make_clean_segment("good")
    assert good_seg.validate() == []


# --- CalibrationDataset ---

def _make_dataset(n_mistakes=5, n_pickups=3, n_clean=10):
    segments = []
    for i in range(n_mistakes):
        seg = make_clean_segment(f"mistake_{i}", narrator_id="narrator_a")
        seg.ground_truth = GroundTruth(is_mistake=True, priority="high", preferred_action="review_mistake")
        segments.append(seg)
    for i in range(n_pickups):
        seg = make_clean_segment(f"pickup_{i}", narrator_id="narrator_b")
        seg.ground_truth = GroundTruth(is_pickup=True, priority="medium", preferred_action="likely_pickup")
        segments.append(seg)
    for i in range(n_clean):
        seg = make_clean_segment(f"clean_{i}", narrator_id="narrator_a" if i % 2 == 0 else "narrator_b")
        segments.append(seg)
    return CalibrationDataset(name="test", segments=segments)


def test_dataset_summary():
    ds = _make_dataset()
    summary = ds.summary()
    assert summary["total_segments"] == 18
    assert summary["mistakes"] == 5
    assert summary["pickups"] == 3
    assert summary["clean"] == 10
    assert summary["narrators"] == 2


def test_dataset_filter_by_narrator():
    ds = _make_dataset()
    filtered = ds.filter_by_narrator("narrator_a")
    assert all(s.narrator_id == "narrator_a" for s in filtered.segments)
    assert filtered.segment_count > 0


def test_dataset_filter_by_source():
    ds = _make_dataset()
    # All segments are synthetic by default from make_clean_segment
    filtered = ds.filter_by_source("synthetic")
    assert filtered.segment_count == ds.segment_count


def test_dataset_split_produces_three_sets():
    ds = _make_dataset(n_mistakes=10, n_pickups=10, n_clean=20)
    train, val, test = ds.split(train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)
    total = train.segment_count + val.segment_count + test.segment_count
    assert total == ds.segment_count


def test_dataset_split_stratified():
    ds = _make_dataset(n_mistakes=10, n_pickups=10, n_clean=20)
    train, val, test = ds.split(stratify=True)
    # Each split should have some representation of each class
    assert train.mistake_count > 0
    assert train.pickup_count > 0
    assert train.clean_count > 0


def test_dataset_split_deterministic():
    ds = _make_dataset()
    train1, _, _ = ds.split(seed=42)
    train2, _, _ = ds.split(seed=42)
    ids1 = [s.segment_id for s in train1.segments]
    ids2 = [s.segment_id for s in train2.segments]
    assert ids1 == ids2


def test_dataset_save_load(tmp_path):
    ds = _make_dataset()
    ds.save(tmp_path / "test_dataset.json")
    loaded = CalibrationDataset.load(tmp_path / "test_dataset.json")
    assert loaded.segment_count == ds.segment_count
    assert loaded.name == ds.name


def test_dataset_merge():
    ds1 = _make_dataset(n_mistakes=3, n_clean=5)
    ds2 = CalibrationDataset(
        name="extra",
        segments=[make_clean_segment(f"new_{i}") for i in range(3)],
    )
    merged = ds1.merge(ds2)
    assert merged.segment_count == ds1.segment_count + 3


def test_dataset_merge_deduplicates():
    ds1 = _make_dataset(n_clean=3)
    ds2 = CalibrationDataset(
        name="overlap",
        segments=[make_clean_segment("clean_0")],  # Same ID as ds1
    )
    merged = ds1.merge(ds2)
    assert merged.segment_count == ds1.segment_count  # No duplicate added


# --- AltTakeGroup ---

def test_alt_take_group_roundtrip():
    group = AltTakeGroup(
        group_id="group_1",
        manuscript_text="Hello world",
        takes=[
            {"take_id": "a", "segment_id": "seg_a", "features": {}},
            {"take_id": "b", "segment_id": "seg_b", "features": {}},
        ],
        ground_truth=AltTakeGroundTruth(
            chosen_take_id="b", ranking=["b", "a"], annotator="human",
        ),
    )
    d = group.to_dict()
    restored = AltTakeGroup.from_dict(d)
    assert restored.group_id == "group_1"
    assert restored.ground_truth.chosen_take_id == "b"
    assert len(restored.takes) == 2
