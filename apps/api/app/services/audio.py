from __future__ import annotations

import json
import subprocess
import shutil
import wave
from pathlib import Path


AudioMetadata = dict[str, int | str | None]


def copy_audio_to_working(source_path: Path, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path


def probe_audio_metadata(audio_path: Path) -> AudioMetadata:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels,bits_per_sample,duration,codec_name,sample_fmt",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout or "{}")
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to probe audio file: {exc}") from exc

    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    format_info = payload.get("format") or {}

    def to_int(value: object) -> int | None:
        if value in (None, "", "N/A"):
            return None
        try:
            return int(float(str(value)))
        except ValueError:
            return None

    duration_seconds = stream.get("duration") or format_info.get("duration")
    duration_ms = None
    if duration_seconds not in (None, "", "N/A"):
        try:
            duration_ms = int(float(str(duration_seconds)) * 1000)
        except ValueError:
            duration_ms = None

    return {
        "codec_name": stream.get("codec_name"),
        "sample_format": stream.get("sample_fmt"),
        "sample_rate_hz": to_int(stream.get("sample_rate")),
        "channels": to_int(stream.get("channels")),
        "bit_depth": to_int(stream.get("bits_per_sample")),
        "duration_ms": duration_ms,
    }


def read_wav_duration_ms(audio_path: Path | None) -> int | None:
    if audio_path is None or not audio_path.exists():
        return None

    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
    except (wave.Error, EOFError, OSError):
        metadata = probe_audio_metadata(audio_path)
        duration_ms = metadata.get("duration_ms")
        if duration_ms is None:
            raise ValueError("Invalid WAV file: unable to determine duration")
        return duration_ms

    if frame_rate <= 0:
        raise ValueError("Invalid WAV file: frame rate is zero or negative")

    return int((frame_count / frame_rate) * 1000)
