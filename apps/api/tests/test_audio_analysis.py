import numpy as np
from pathlib import Path
from unittest.mock import patch
from app.services.audio_analysis import (
    _compute_rms_db,
    _compute_zcr,
    _detect_silence_gaps,
    _detect_abrupt_cutoffs,
    _frame_to_ms,
    analyze_audio_signals,
)


def test_compute_rms_db_returns_array():
    y = np.random.randn(8000).astype(np.float32)
    rms = _compute_rms_db(y, frame_length=2048, hop_length=512)
    assert len(rms) > 0
    assert all(np.isfinite(rms))


def test_compute_rms_db_silent_signal():
    y = np.zeros(4096, dtype=np.float32)
    rms = _compute_rms_db(y, frame_length=2048, hop_length=512)
    # Silent signal should have very low RMS (near floor)
    assert all(v < -60 for v in rms)


def test_compute_zcr_returns_array():
    y = np.random.randn(8000).astype(np.float32)
    zcr = _compute_zcr(y, frame_length=2048, hop_length=512)
    assert len(zcr) > 0
    assert all(0 <= v <= 1 for v in zcr)


def test_frame_to_ms():
    assert _frame_to_ms(0, 22050, 512) == 0
    ms = _frame_to_ms(10, 22050, 512)
    assert ms > 0
    assert isinstance(ms, int)


def test_detect_silence_gaps_finds_silence():
    # Create signal with a silent gap in the middle
    sr = 22050
    loud = np.random.randn(sr).astype(np.float32) * 0.5
    silent = np.zeros(sr, dtype=np.float32)
    y = np.concatenate([loud, silent, loud])
    rms = _compute_rms_db(y, hop_length=512)
    gaps = _detect_silence_gaps(rms, sr, hop_length=512, silence_threshold_db=-40.0, min_gap_ms=200)
    assert len(gaps) >= 1
    assert gaps[0]["signal_type"] == "silence_gap"


def test_detect_silence_gaps_no_silence():
    y = np.random.randn(22050).astype(np.float32) * 0.5
    rms = _compute_rms_db(y, hop_length=512)
    gaps = _detect_silence_gaps(rms, 22050, hop_length=512)
    # Continuous noise should produce no silence gaps
    assert len(gaps) == 0


def test_detect_abrupt_cutoffs():
    # Create an abrupt drop in RMS
    rms = np.array([-10.0, -10.0, -10.0, -50.0, -50.0])
    cutoffs = _detect_abrupt_cutoffs(rms, sr=22050, hop_length=512)
    assert len(cutoffs) >= 1
    assert cutoffs[0]["signal_type"] == "abrupt_cutoff"


def test_detect_abrupt_cutoffs_smooth_signal():
    rms = np.linspace(-20, -25, 20)
    cutoffs = _detect_abrupt_cutoffs(rms, sr=22050, hop_length=512)
    assert len(cutoffs) == 0


def test_analyze_audio_signals_returns_list(tmp_path):
    import wave
    import struct

    # Create a minimal WAV file
    wav_path = tmp_path / "test.wav"
    sr = 22050
    duration_sec = 1
    n_samples = sr * duration_sec
    samples = [int(32767 * np.sin(2 * np.pi * 440 * t / sr)) for t in range(n_samples)]

    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))

    signals = analyze_audio_signals(wav_path, sr=sr)
    assert isinstance(signals, list)
    for sig in signals:
        assert "signal_type" in sig
        assert "start_ms" in sig
        assert "end_ms" in sig
        assert "confidence" in sig
        assert sig["signal_type"] in ("click_marker", "abrupt_cutoff", "silence_gap", "onset_burst")
