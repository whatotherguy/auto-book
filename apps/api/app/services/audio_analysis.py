"""Audio signal analysis: RMS, ZCR, spectral centroid, onset detection, click/cutoff detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from ..detection_config import (
    ABRUPT_CUTOFF_RMS_DROP_FACTOR,
    CLICK_CREST_FACTOR_THRESHOLD,
    CLICK_MAX_DURATION_MS,
    CLICK_MIN_DURATION_MS,
    CLICK_ONSET_STRENGTH_THRESHOLD,
    CLICK_SPECTRAL_CENTROID_MIN_HZ,
    CLICK_ZCR_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _load_audio(audio_path: Path, sr: int = 22050) -> tuple[np.ndarray, int]:
    """Load audio file as mono float32 numpy array."""
    try:
        import librosa
        y, sr_out = librosa.load(str(audio_path), sr=sr, mono=True)
        return y, sr_out
    except ImportError:
        logger.warning("librosa not installed — using basic wav loading")
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1)
        max_val = float(np.iinfo(dtype).max)
        data = data / max_val
        return data, framerate


def _compute_rms_db(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute RMS energy in dB per frame."""
    n_frames = 1 + (len(y) - frame_length) // hop_length
    rms = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_length
        frame = y[start:start + frame_length]
        rms[i] = np.sqrt(np.mean(frame ** 2))
    rms = np.maximum(rms, 1e-10)
    return 20 * np.log10(rms)


def _compute_zcr(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute zero-crossing rate per frame."""
    n_frames = 1 + (len(y) - frame_length) // hop_length
    zcr = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_length
        frame = y[start:start + frame_length]
        zcr[i] = np.mean(np.abs(np.diff(np.sign(frame)))) / 2
    return zcr


def _compute_spectral_centroid(y: np.ndarray, sr: int, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute spectral centroid per frame."""
    try:
        import librosa
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=frame_length, hop_length=hop_length)
        return centroid[0]
    except ImportError:
        n_frames = 1 + (len(y) - frame_length) // hop_length
        freqs = np.fft.rfftfreq(frame_length, d=1.0 / sr)
        centroid = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop_length
            frame = y[start:start + frame_length]
            spectrum = np.abs(np.fft.rfft(frame))
            total = spectrum.sum()
            if total > 0:
                centroid[i] = np.sum(freqs * spectrum) / total
        return centroid


def _compute_spectral_bandwidth(y: np.ndarray, sr: int, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute spectral bandwidth per frame."""
    try:
        import librosa
        bw = librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=frame_length, hop_length=hop_length)
        return bw[0]
    except ImportError:
        centroid = _compute_spectral_centroid(y, sr, frame_length, hop_length)
        n_frames = len(centroid)
        freqs = np.fft.rfftfreq(frame_length, d=1.0 / sr)
        bw = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop_length
            frame = y[start:start + frame_length]
            spectrum = np.abs(np.fft.rfft(frame))
            total = spectrum.sum()
            if total > 0:
                bw[i] = np.sqrt(np.sum(spectrum * (freqs - centroid[i]) ** 2) / total)
        return bw


def _compute_onset_strength(y: np.ndarray, sr: int, hop_length: int = 512) -> np.ndarray:
    """Compute onset strength envelope."""
    try:
        import librosa
        return librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    except ImportError:
        rms = _compute_rms_db(y, hop_length=hop_length)
        diff = np.diff(rms, prepend=rms[0])
        return np.maximum(diff, 0)


def _frame_to_ms(frame_index: int, sr: int, hop_length: int = 512) -> int:
    return int(frame_index * hop_length * 1000 / sr)


def _detect_clicks(
    y: np.ndarray,
    sr: int,
    rms_db: np.ndarray,
    zcr: np.ndarray,
    centroid: np.ndarray,
    onset_strength: np.ndarray,
    hop_length: int = 512,
) -> list[dict[str, Any]]:
    """Detect click/transient markers using multi-feature thresholding."""
    signals: list[dict[str, Any]] = []
    n_frames = min(len(rms_db), len(zcr), len(centroid), len(onset_strength))

    rms_linear = 10 ** (rms_db[:n_frames] / 20)
    peak_amplitude = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_length
        frame = np.abs(y[start:start + 2048]) if start + 2048 <= len(y) else np.abs(y[start:])
        peak_amplitude[i] = frame.max() if len(frame) > 0 else 0

    crest_factor = np.zeros(n_frames)
    valid = rms_linear > 1e-10
    crest_factor[valid] = 20 * np.log10(peak_amplitude[valid] / rms_linear[valid])

    for i in range(n_frames):
        if (
            crest_factor[i] >= CLICK_CREST_FACTOR_THRESHOLD
            and zcr[i] >= CLICK_ZCR_THRESHOLD
            and centroid[i] >= CLICK_SPECTRAL_CENTROID_MIN_HZ
            and onset_strength[i] >= CLICK_ONSET_STRENGTH_THRESHOLD
        ):
            start_ms = _frame_to_ms(i, sr, hop_length)
            end_ms = start_ms + CLICK_MAX_DURATION_MS
            duration_ms = end_ms - start_ms
            if duration_ms < CLICK_MIN_DURATION_MS:
                continue

            confidence = min(1.0, (crest_factor[i] / CLICK_CREST_FACTOR_THRESHOLD) * 0.5
                             + (onset_strength[i] / CLICK_ONSET_STRENGTH_THRESHOLD) * 0.3
                             + (centroid[i] / CLICK_SPECTRAL_CENTROID_MIN_HZ) * 0.2)

            signals.append({
                "signal_type": "click_marker",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": round(confidence, 4),
                "rms_db": round(float(rms_db[i]), 2),
                "spectral_centroid_hz": round(float(centroid[i]), 1),
                "zero_crossing_rate": round(float(zcr[i]), 4),
                "onset_strength": round(float(onset_strength[i]), 4),
                "bandwidth_hz": None,
                "note": f"crest={crest_factor[i]:.1f}dB",
            })

    return signals


def _detect_abrupt_cutoffs(
    rms_db: np.ndarray,
    sr: int,
    hop_length: int = 512,
) -> list[dict[str, Any]]:
    """Detect abrupt cutoffs where RMS drops sharply."""
    signals: list[dict[str, Any]] = []
    for i in range(1, len(rms_db)):
        drop = rms_db[i - 1] - rms_db[i]
        if drop >= ABRUPT_CUTOFF_RMS_DROP_FACTOR:
            start_ms = _frame_to_ms(i - 1, sr, hop_length)
            end_ms = _frame_to_ms(i, sr, hop_length)
            confidence = min(1.0, drop / (ABRUPT_CUTOFF_RMS_DROP_FACTOR * 2))
            signals.append({
                "signal_type": "abrupt_cutoff",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": round(confidence, 4),
                "rms_db": round(float(rms_db[i]), 2),
                "spectral_centroid_hz": None,
                "zero_crossing_rate": None,
                "onset_strength": None,
                "bandwidth_hz": None,
                "note": f"drop={drop:.1f}dB",
            })
    return signals


def _detect_silence_gaps(
    rms_db: np.ndarray,
    sr: int,
    hop_length: int = 512,
    silence_threshold_db: float = -40.0,
    min_gap_ms: int = 200,
) -> list[dict[str, Any]]:
    """Detect silence gaps in the audio."""
    signals: list[dict[str, Any]] = []
    in_silence = False
    silence_start = 0

    for i in range(len(rms_db)):
        if rms_db[i] < silence_threshold_db:
            if not in_silence:
                in_silence = True
                silence_start = i
        else:
            if in_silence:
                start_ms = _frame_to_ms(silence_start, sr, hop_length)
                end_ms = _frame_to_ms(i, sr, hop_length)
                if end_ms - start_ms >= min_gap_ms:
                    signals.append({
                        "signal_type": "silence_gap",
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "confidence": 0.95,
                        "rms_db": round(float(np.mean(rms_db[silence_start:i])), 2),
                        "spectral_centroid_hz": None,
                        "zero_crossing_rate": None,
                        "onset_strength": None,
                        "bandwidth_hz": None,
                        "note": f"gap={end_ms - start_ms}ms",
                    })
                in_silence = False

    return signals


def _detect_onset_bursts(
    onset_strength: np.ndarray,
    sr: int,
    hop_length: int = 512,
    threshold_factor: float = 3.0,
) -> list[dict[str, Any]]:
    """Detect sudden onset bursts (potential punch-in points)."""
    signals: list[dict[str, Any]] = []
    mean_onset = float(np.mean(onset_strength))
    std_onset = float(np.std(onset_strength))
    threshold = mean_onset + threshold_factor * std_onset

    for i in range(len(onset_strength)):
        if onset_strength[i] >= threshold:
            start_ms = _frame_to_ms(i, sr, hop_length)
            end_ms = start_ms + 50
            confidence = min(1.0, float(onset_strength[i]) / (threshold * 1.5))
            signals.append({
                "signal_type": "onset_burst",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": round(confidence, 4),
                "rms_db": None,
                "spectral_centroid_hz": None,
                "zero_crossing_rate": None,
                "onset_strength": round(float(onset_strength[i]), 4),
                "bandwidth_hz": None,
                "note": f"strength={onset_strength[i]:.2f} (threshold={threshold:.2f})",
            })

    return signals


def analyze_audio_signals(audio_path: Path, sr: int = 22050) -> list[dict[str, Any]]:
    """Main entry point: analyze audio and return all detected signals."""
    logger.info("Analyzing audio signals: %s", audio_path)
    y, sr = _load_audio(audio_path, sr=sr)

    hop_length = 512
    rms_db = _compute_rms_db(y, hop_length=hop_length)
    zcr = _compute_zcr(y, hop_length=hop_length)
    centroid = _compute_spectral_centroid(y, sr, hop_length=hop_length)
    onset_strength = _compute_onset_strength(y, sr, hop_length=hop_length)

    signals: list[dict[str, Any]] = []
    signals.extend(_detect_clicks(y, sr, rms_db, zcr, centroid, onset_strength, hop_length))
    signals.extend(_detect_abrupt_cutoffs(rms_db, sr, hop_length))
    signals.extend(_detect_silence_gaps(rms_db, sr, hop_length))
    signals.extend(_detect_onset_bursts(onset_strength, sr, hop_length))

    signals.sort(key=lambda s: s["start_ms"])
    logger.info("Audio analysis found %d signals", len(signals))
    return signals
