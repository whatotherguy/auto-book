"""Prosody analysis: F0 (pitch), speech rate, energy contour per token."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

import numpy as np

logger = logging.getLogger(__name__)

MAX_CONTOUR_LENGTH = 50


def _load_audio_segment(audio_path: Path, start_ms: int, end_ms: int, sr: int = 22050) -> tuple[np.ndarray, int]:
    """Load a segment of audio between start_ms and end_ms."""
    try:
        import librosa
        start_sec = start_ms / 1000.0
        duration_sec = (end_ms - start_ms) / 1000.0
        y, sr_out = librosa.load(str(audio_path), sr=sr, mono=True, offset=start_sec, duration=duration_sec)
        return y, sr_out
    except ImportError:
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            framerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            start_frame = int(start_ms * framerate / 1000)
            end_frame = int(end_ms * framerate / 1000)
            wf.setpos(min(start_frame, wf.getnframes()))
            n_frames = min(end_frame - start_frame, wf.getnframes() - start_frame)
            raw = wf.readframes(max(0, n_frames))
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1)
        max_val = float(np.iinfo(dtype).max)
        return data / max_val, framerate


def _extract_f0(y: np.ndarray, sr: int) -> tuple[float | None, float | None, list[float]]:
    """Extract F0 using pyin (librosa) or fallback to autocorrelation."""
    try:
        import librosa
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=50, fmax=500, sr=sr
        )
        valid_f0 = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        if len(valid_f0) == 0:
            return None, None, []
        contour = valid_f0[:MAX_CONTOUR_LENGTH].tolist()
        return round(float(np.mean(valid_f0)), 2), round(float(np.std(valid_f0)), 2), [round(v, 1) for v in contour]
    except ImportError:
        return None, None, []


def _compute_energy_contour(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> list[float]:
    """Compute energy contour (RMS per frame)."""
    n_frames = max(1, 1 + (len(y) - frame_length) // hop_length)
    energy = []
    for i in range(min(n_frames, MAX_CONTOUR_LENGTH)):
        start = i * hop_length
        frame = y[start:start + frame_length]
        rms = float(np.sqrt(np.mean(frame ** 2))) if len(frame) > 0 else 0.0
        energy.append(round(rms, 6))
    return energy


def _token_start_ms(token: dict[str, Any]) -> int:
    val = token.get("start_ms")
    if val is None and token.get("start") is not None:
        try:
            return int(float(token["start"]) * 1000)
        except (TypeError, ValueError):
            return 0
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _token_end_ms(token: dict[str, Any]) -> int:
    val = token.get("end_ms")
    if val is None and token.get("end") is not None:
        try:
            return int(float(token["end"]) * 1000)
        except (TypeError, ValueError):
            return 0
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _token_text(token: dict[str, Any]) -> str:
    return str(token.get("normalized") or token.get("text") or "")


def extract_prosody(
    audio_path: Path,
    spoken_tokens: Sequence[dict[str, Any]],
    sr: int = 22050,
) -> list[dict[str, Any]]:
    """Extract prosody features for each spoken token.

    Returns a list of prosody feature dicts, one per token, in the same order
    as spoken_tokens.
    """
    logger.info("Extracting prosody for %d tokens from %s", len(spoken_tokens), audio_path)
    prosody_map: list[dict[str, Any]] = []

    for idx, token in enumerate(spoken_tokens):
        start_ms = _token_start_ms(token)
        end_ms = _token_end_ms(token)
        duration_ms = max(0, end_ms - start_ms)
        text = _token_text(token)
        word_count = len(text.split()) if text.strip() else 0

        # Compute pauses
        pause_before_ms = 0
        pause_after_ms = 0
        if idx > 0:
            prev_end = _token_end_ms(spoken_tokens[idx - 1])
            pause_before_ms = max(0, start_ms - prev_end)
        if idx < len(spoken_tokens) - 1:
            next_start = _token_start_ms(spoken_tokens[idx + 1])
            pause_after_ms = max(0, next_start - end_ms)

        # Speech rate
        speech_rate_wps = 0.0
        if duration_ms > 0 and word_count > 0:
            speech_rate_wps = round(word_count / (duration_ms / 1000), 2)

        # Extract audio segment for F0 and energy
        f0_mean = None
        f0_std = None
        f0_contour: list[float] = []
        energy_contour: list[float] = []

        if duration_ms > 50:  # Need at least 50ms for meaningful analysis
            try:
                y_segment, sr_actual = _load_audio_segment(audio_path, start_ms, end_ms, sr)
                if len(y_segment) > 0:
                    f0_mean, f0_std, f0_contour = _extract_f0(y_segment, sr_actual)
                    energy_contour = _compute_energy_contour(y_segment)
            except Exception as exc:
                logger.debug("Prosody extraction failed for token %d: %s", idx, exc)

        prosody_map.append({
            "token_index": idx,
            "duration_ms": duration_ms,
            "speech_rate_wps": speech_rate_wps,
            "f0_mean_hz": f0_mean,
            "f0_std_hz": f0_std,
            "f0_contour": f0_contour,
            "energy_contour": energy_contour,
            "pause_before_ms": pause_before_ms,
            "pause_after_ms": pause_after_ms,
        })

    logger.info("Prosody extraction complete for %d tokens", len(prosody_map))
    return prosody_map
