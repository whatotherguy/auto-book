from app.detection_config import (
    CLICK_CREST_FACTOR_THRESHOLD,
    CLICK_SPECTRAL_CENTROID_MIN_HZ,
    CLICK_ZCR_THRESHOLD,
    ABRUPT_CUTOFF_RMS_DROP_FACTOR,
    PICKUP_SILENCE_BEFORE_MS,
    ALT_TAKE_MAX_GAP_MS,
    ALT_TAKE_MIN_TEXT_OVERLAP,
    ALT_TAKE_MIN_CLUSTER_SIZE,
    MISTAKE_WEIGHTS,
    PICKUP_WEIGHTS,
    PERFORMANCE_WEIGHTS,
    CONTINUITY_WEIGHTS,
    TAKE_PREFERENCE_WEIGHTS,
)


def test_click_thresholds_positive():
    assert CLICK_CREST_FACTOR_THRESHOLD > 0
    assert CLICK_SPECTRAL_CENTROID_MIN_HZ > 0
    assert CLICK_ZCR_THRESHOLD > 0


def test_abrupt_cutoff_threshold():
    assert ABRUPT_CUTOFF_RMS_DROP_FACTOR == 6.0


def test_pickup_silence_threshold():
    assert PICKUP_SILENCE_BEFORE_MS == 300


def test_alt_take_config():
    assert ALT_TAKE_MAX_GAP_MS == 15000
    assert 0 < ALT_TAKE_MIN_TEXT_OVERLAP <= 1.0
    assert ALT_TAKE_MIN_CLUSTER_SIZE >= 2


def test_mistake_weights_sum_to_one():
    total = sum(MISTAKE_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01


def test_pickup_weights_sum_to_one():
    total = sum(PICKUP_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01


def test_performance_weights_all_negative():
    assert all(v < 0 for v in PERFORMANCE_WEIGHTS.values())


def test_continuity_weights_all_negative():
    assert all(v < 0 for v in CONTINUITY_WEIGHTS.values())


def test_take_preference_weights_sum_to_one():
    total = sum(TAKE_PREFERENCE_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01
