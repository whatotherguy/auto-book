from __future__ import annotations

import math
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from .audio import probe_audio_metadata


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dbfs(value: float) -> float:
    if value <= 0:
        return -120.0
    return round(20 * math.log10(value), 2)


def pcm24_to_float32(raw_bytes: bytes, channels: int) -> np.ndarray:
    data = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
    ints = (
        data[:, 0].astype(np.int32)
        | (data[:, 1].astype(np.int32) << 8)
        | (data[:, 2].astype(np.int32) << 16)
    )
    negative = ints & 0x800000
    ints = ints - (negative << 1)
    samples = ints.astype(np.float32) / 8388608.0
    return samples.reshape(-1, channels)


def read_wav_samples(audio_path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            frame_count = wav_file.getnframes()
            raw_frames = wav_file.readframes(frame_count)

        if sample_width == 1:
            samples = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            samples = samples.reshape(-1, channels)
        elif sample_width == 2:
            samples = np.frombuffer(raw_frames, dtype="<i2").astype(np.float32) / 32768.0
            samples = samples.reshape(-1, channels)
        elif sample_width == 3:
            samples = pcm24_to_float32(raw_frames, channels)
        elif sample_width == 4:
            samples = np.frombuffer(raw_frames, dtype="<i4").astype(np.float32) / 2147483648.0
            samples = samples.reshape(-1, channels)
        else:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    except (wave.Error, EOFError, OSError, ValueError):
        metadata = probe_audio_metadata(audio_path)
        channels = metadata.get("channels")
        sample_rate = metadata.get("sample_rate_hz")
        duration_ms = metadata.get("duration_ms") or 0
        if not channels or not sample_rate:
            raise ValueError("Unable to decode WAV audio for ACX analysis")

        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(audio_path),
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-",
        ]
        try:
            result = subprocess.run(command, capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            raise ValueError(f"Unable to decode WAV audio: {exc}") from exc

        samples = np.frombuffer(result.stdout, dtype="<f4")
        if samples.size == 0:
            raise ValueError("Unable to decode WAV audio for ACX analysis")

        samples = samples.reshape(-1, channels)
        frame_count = samples.shape[0]
        sample_width = metadata.get("bit_depth")
        sample_width = max((sample_width or 32) // 8, 1)

        return {
            "samples": samples,
            "channels": channels,
            "sample_rate_hz": sample_rate,
            "sample_width_bytes": sample_width,
            "frame_count": frame_count,
            "duration_ms": duration_ms or int((frame_count / sample_rate) * 1000),
        }

    return {
        "samples": samples,
        "channels": channels,
        "sample_rate_hz": sample_rate,
        "sample_width_bytes": sample_width,
        "frame_count": frame_count,
        "duration_ms": int((frame_count / sample_rate) * 1000) if sample_rate else 0,
    }


def estimate_noise_floor_dbfs(mono_samples: np.ndarray, sample_rate_hz: int) -> tuple[float | None, str]:
    if mono_samples.size == 0 or sample_rate_hz <= 0:
        return None, "No audio samples available."

    window_size = max(int(sample_rate_hz * 0.05), 1)
    window_count = mono_samples.size // window_size
    if window_count == 0:
        return None, "Audio too short for noise-floor estimation."

    trimmed = mono_samples[: window_count * window_size]
    windows = trimmed.reshape(window_count, window_size)
    window_rms = np.sqrt(np.mean(np.square(windows), axis=1))
    db_values = np.array([dbfs(float(value)) for value in window_rms], dtype=np.float32)
    quiet_windows = db_values[db_values < -40.0]
    minimum_quiet_windows = max(10, math.ceil(window_count * 0.02))

    if quiet_windows.size >= minimum_quiet_windows:
        return round(float(np.percentile(quiet_windows, 20)), 2), "Estimated from quiet 50 ms windows."

    return (
        round(float(np.percentile(db_values, 10)), 2),
        "Estimated from the 10th percentile of all windows because there were too few quiet windows; floor estimate may be unreliable and manual review is recommended.",
    )


def add_check(
    checks: list[dict[str, Any]],
    suggestions: list[str],
    *,
    name: str,
    status: str,
    actual: str,
    target: str,
    summary: str,
    suggestion: str | None = None,
) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "actual": actual,
            "target": target,
            "summary": summary,
            "suggestion": suggestion,
        }
    )
    if suggestion:
        suggestions.append(suggestion)


def analyze_acx_audio(audio_path: Path) -> dict[str, Any]:
    if not audio_path.exists():
        raise FileNotFoundError("Audio file not found")
    if audio_path.suffix.lower() != ".wav":
        raise ValueError("ACX preflight currently supports WAV source files in this app")

    audio = read_wav_samples(audio_path)
    samples = audio["samples"]
    mono_samples = samples.mean(axis=1) if audio["channels"] > 1 else samples[:, 0]

    peak_value = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms_value = float(np.sqrt(np.mean(np.square(mono_samples)))) if mono_samples.size else 0.0
    peak_dbfs = dbfs(peak_value)
    rms_dbfs = dbfs(rms_value)
    noise_floor_dbfs, noise_floor_note = estimate_noise_floor_dbfs(mono_samples, audio["sample_rate_hz"])
    clipped_sample_count = int(np.sum(np.abs(samples) >= 0.999))

    checks: list[dict[str, Any]] = []
    suggestions: list[str] = []

    peak_status = "pass" if peak_dbfs <= -3.0 else "fail"
    add_check(
        checks,
        suggestions,
        name="peak_level",
        status=peak_status,
        actual=f"{peak_dbfs} dBFS",
        target="<= -3.0 dBFS",
        summary="Peak level for ACX submission.",
        suggestion="Reduce limiting or master peak output to below -3 dBFS." if peak_status == "fail" else None,
    )

    rms_status = "pass" if -23.0 <= rms_dbfs <= -18.0 else "fail"
    add_check(
        checks,
        suggestions,
        name="rms_level",
        status=rms_status,
        actual=f"{rms_dbfs} dBFS",
        target="-23.0 to -18.0 dBFS",
        summary="Overall loudness window for ACX submission.",
        suggestion=(
            "Adjust compression and gain staging so the mastered chapter lands between -23 and -18 dBFS RMS."
            if rms_status == "fail"
            else None
        ),
    )

    if noise_floor_dbfs is None:
        add_check(
            checks,
            suggestions,
            name="noise_floor",
            status="warn",
            actual="unavailable",
            target="<= -60.0 dBFS",
            summary=noise_floor_note,
            suggestion="Check room tone manually; there was not enough data for a reliable estimate.",
        )
    else:
        noise_status = "pass" if noise_floor_dbfs <= -60.0 else "fail"
        if "manual review recommended" in noise_floor_note.lower() and noise_status == "pass":
            noise_status = "warn"
        add_check(
            checks,
            suggestions,
            name="noise_floor",
            status=noise_status,
            actual=f"{noise_floor_dbfs} dBFS",
            target="<= -60.0 dBFS",
            summary=noise_floor_note,
            suggestion=(
                "Reduce room noise, HVAC, or broadband hiss before mastering to get below -60 dBFS."
                if noise_status == "fail"
                else "Listen to room tone manually before relying on this estimated noise-floor pass."
                if noise_status == "warn"
                else None
            ),
        )

    clipping_status = "pass" if clipped_sample_count == 0 else "fail"
    add_check(
        checks,
        suggestions,
        name="clipping",
        status=clipping_status,
        actual=str(clipped_sample_count),
        target="0 clipped samples",
        summary="Potential digital clipping count.",
        suggestion="Repair clipped peaks or revisit the recording/master chain to remove clipping." if clipping_status == "fail" else None,
    )

    sample_rate_status = "pass" if audio["sample_rate_hz"] == 44100 else "warn"
    add_check(
        checks,
        suggestions,
        name="sample_rate",
        status=sample_rate_status,
        actual=f"{audio['sample_rate_hz']} Hz",
        target="44,100 Hz final delivery",
        summary="ACX final delivery expects 44.1 kHz. Raw source can still be workable for editing.",
        suggestion="Export the final mastered ACX files at 44.1 kHz." if sample_rate_status == "warn" else None,
    )

    channel_status = "pass" if audio["channels"] in {1, 2} else "fail"
    add_check(
        checks,
        suggestions,
        name="channels",
        status=channel_status,
        actual=str(audio["channels"]),
        target="Mono or stereo with consistent channel layout",
        summary="Channel layout sanity check.",
        suggestion="Downmix or correct the channel layout before final mastering." if channel_status == "fail" else None,
    )

    bit_depth = audio["sample_width_bytes"] * 8
    add_check(
        checks,
        suggestions,
        name="source_format",
        status="info",
        actual=f"WAV, {bit_depth}-bit",
        target="Final ACX delivery is 192 kbps CBR MP3",
        summary="This source file is suitable for editing; final ACX delivery format is checked after mastering.",
    )

    checks.append(
        {
            "check": "cross_chapter_consistency",
            "passed": None,
            "value": None,
            "threshold": "<=20dB variation across all chapters",
            "note": "Cross-chapter consistency requires comparing all chapters. Review manually before ACX submission.",
        }
    )

    unique_suggestions = list(dict.fromkeys(suggestions))
    passes_acx = all(check["status"] != "fail" for check in checks if check["name"] in {"peak_level", "rms_level", "noise_floor", "clipping"})

    return {
        "measured_at": utc_now_iso(),
        "file_path": str(audio_path.resolve()),
        "passes_acx": passes_acx,
        "format": {
            "container": "wav",
            "sample_rate_hz": audio["sample_rate_hz"],
            "channels": audio["channels"],
            "bit_depth": bit_depth,
            "duration_ms": audio["duration_ms"],
        },
        "levels": {
            "peak_dbfs": peak_dbfs,
            "rms_dbfs": rms_dbfs,
            "estimated_noise_floor_dbfs": noise_floor_dbfs,
            "noise_floor_note": noise_floor_note,
            "clipped_sample_count": clipped_sample_count,
        },
        "checks": checks,
        "fix_suggestions": unique_suggestions,
        "notes": [
            "ACX format requirements like 192 kbps CBR MP3 apply to final mastered delivery, not raw narration WAVs.",
            "Noise floor is an estimate intended as a mastering handoff signal, not a final compliance guarantee.",
        ],
    }
