"""Silero VAD speech boundary detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_vad_model = None
_vad_utils = None


def _load_vad_model():
    """Load Silero VAD model via torch.hub (cached after first load)."""
    global _vad_model, _vad_utils
    if _vad_model is not None:
        return _vad_model, _vad_utils

    try:
        import torch
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        _vad_model = model
        _vad_utils = utils
        return model, utils
    except Exception as exc:
        logger.warning("Failed to load Silero VAD: %s", exc)
        return None, None


def _load_audio_for_vad(audio_path: Path, target_sr: int = 16000) -> tuple[Any, int]:
    """Load audio at 16kHz for VAD processing."""
    try:
        import torch
        import torchaudio
        wav, sr = torchaudio.load(str(audio_path))
        if sr != target_sr:
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr)
            wav = resampler(wav)
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        return wav.squeeze(0), target_sr
    except ImportError:
        logger.warning("torchaudio not available — using numpy wav loader for VAD")
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sampwidth, np.int16)
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1)
        max_val = float(np.iinfo(dtype).max)
        data = data / max_val
        if framerate != target_sr:
            ratio = target_sr / framerate
            new_len = int(len(data) * ratio)
            indices = np.linspace(0, len(data) - 1, new_len)
            data = np.interp(indices, np.arange(len(data)), data)
        try:
            import torch
            return torch.from_numpy(data), target_sr
        except ImportError:
            return data, target_sr


def run_vad(audio_path: Path, min_speech_duration_ms: int = 250, min_silence_duration_ms: int = 100) -> list[dict[str, Any]]:
    """Run Silero VAD and return speech segments."""
    logger.info("Running VAD on: %s", audio_path)
    model, utils = _load_vad_model()

    if model is None:
        logger.warning("VAD model unavailable — returning empty segments")
        return []

    try:
        get_speech_timestamps = utils[0]
        wav, sr = _load_audio_for_vad(audio_path)

        speech_timestamps = get_speech_timestamps(
            wav,
            model,
            sampling_rate=sr,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
            return_seconds=False,
        )

        segments: list[dict[str, Any]] = []
        for ts in speech_timestamps:
            start_sample = ts["start"]
            end_sample = ts["end"]
            start_ms = int(start_sample * 1000 / sr)
            end_ms = int(end_sample * 1000 / sr)
            speech_prob = float(ts.get("speech_prob", 0.9))
            segments.append({
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speech_probability": round(speech_prob, 4),
            })

        logger.info("VAD found %d speech segments", len(segments))
        return segments

    except Exception as exc:
        logger.error("VAD processing failed: %s", exc)
        return []
