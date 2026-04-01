from app.services.scoring.derived_features import compute_derived_features


BASELINE = {
    "mean_speech_rate": 3.0,
    "std_speech_rate": 0.5,
    "mean_f0": 150.0,
    "std_f0": 30.0,
    "mean_f0_std": 20.0,
    "std_f0_std": 10.0,
    "mean_rms_db": -20.0,
    "std_rms_db": 5.0,
    "mean_spectral_centroid": 1500.0,
    "std_spectral_centroid": 500.0,
    "mean_pause": 200.0,
    "std_pause": 150.0,
}


def test_z_scores_at_mean():
    features = {"speech_rate_wps": 3.0, "rms_db": -20.0, "pause_before_ms": 200.0}
    derived = compute_derived_features(features, BASELINE)
    assert derived["z_speech_rate"] == 0.0
    assert derived["z_rms_db"] == 0.0
    assert derived["z_pause_before"] == 0.0


def test_z_scores_positive():
    features = {"speech_rate_wps": 4.0}  # 2 std above mean
    derived = compute_derived_features(features, BASELINE)
    assert derived["z_speech_rate"] == 2.0


def test_z_scores_negative():
    features = {"speech_rate_wps": 2.0}  # 2 std below mean
    derived = compute_derived_features(features, BASELINE)
    assert derived["z_speech_rate"] == -2.0


def test_f0_none_returns_zero():
    features = {"f0_mean_hz": None, "f0_std_hz": None}
    derived = compute_derived_features(features, BASELINE)
    assert derived["z_f0_mean"] == 0.0
    assert derived["z_f0_std"] == 0.0


def test_deltas_with_prev():
    features = {"rms_db": -15.0, "f0_mean_hz": 160.0, "speech_rate_wps": 3.5}
    prev = {"rms_db": -20.0, "f0_mean_hz": 150.0, "speech_rate_wps": 3.0}
    derived = compute_derived_features(features, BASELINE, prev_features=prev)
    assert derived["delta_rms_db_prev"] == 5.0
    assert derived["delta_f0_prev"] == 10.0
    assert derived["delta_speech_rate_prev"] == 0.5


def test_deltas_without_prev_uses_baseline():
    features = {"rms_db": -15.0, "f0_mean_hz": 160.0, "speech_rate_wps": 3.5}
    derived = compute_derived_features(features, BASELINE)
    assert derived["delta_rms_db_prev"] == 5.0  # -15 - (-20)
    assert derived["delta_f0_prev"] == 10.0  # 160 - 150


def test_delta_next():
    features = {"speech_rate_wps": 3.5}
    next_feat = {"speech_rate_wps": 2.5}
    derived = compute_derived_features(features, BASELINE, next_features=next_feat)
    assert derived["delta_speech_rate_next"] == 1.0


def test_delta_next_uses_baseline_when_missing():
    features = {"speech_rate_wps": 3.5}
    derived = compute_derived_features(features, BASELINE)
    assert derived["delta_speech_rate_next"] == 0.5  # 3.5 - 3.0


def test_zero_std_returns_zero():
    bad_baseline = {**BASELINE, "std_speech_rate": 0.0}
    features = {"speech_rate_wps": 5.0}
    derived = compute_derived_features(features, bad_baseline)
    assert derived["z_speech_rate"] == 0.0
