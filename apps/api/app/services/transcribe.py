from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..services.text_normalize import normalize_text
from ..utils.tokenization import tokenize

logger = logging.getLogger(__name__)

TranscribeProgressCallback = Callable[[str, int, str], None]

MODEL_CANDIDATES = ("large-v3", "medium", "small", "tiny")
PROFILE_CANDIDATES = {"balanced", "high_quality", "max_quality"}
MODE_TO_PROFILE = {
    "optimized": "balanced",
    "high_quality": "high_quality",
    "max_quality": "max_quality",
}


def build_placeholder_transcript(manuscript_text: str, duration_ms: int | None) -> dict:
    logger.warning(
        "WhisperX unavailable — returning placeholder transcript. Analysis results will be meaningless. Install faster-whisper to enable real transcription."
    )
    normalized_text = normalize_text(manuscript_text)
    tokens = tokenize(normalized_text)
    if not tokens:
        return {
            "text": "",
            "segments": [],
            "words": [],
            "source": "placeholder-empty",
            "warnings": ["No manuscript text available for placeholder transcript."],
            "is_placeholder": True,
        }

    safe_duration_ms = max(duration_ms or len(tokens) * 350, len(tokens) * 150)
    ms_per_token = max(safe_duration_ms // max(len(tokens), 1), 150)

    words = []
    cursor_ms = 0
    for index, token in enumerate(tokens):
        start_ms = cursor_ms
        end_ms = start_ms + ms_per_token
        cursor_ms = end_ms
        words.append(
            {
                "word": token,
                "start": round(start_ms / 1000, 3),
                "end": round(end_ms / 1000, 3),
                "confidence": 0.0,
                "source_word_index": index,
            }
        )

    return {
        "text": " ".join(tokens),
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": round(cursor_ms / 1000, 3),
                "text": " ".join(tokens),
            }
        ],
        "words": words,
        "source": "placeholder-manuscript-fallback",
        "warnings": ["WhisperX not available; generated placeholder transcript from manuscript text."],
        "is_placeholder": True,
    }


def build_initial_prompt(manuscript_text: str) -> str | None:
    normalized = " ".join(manuscript_text.split())
    if not normalized:
        return None

    prompt = normalized[:500].strip()
    return prompt or None


def parse_optional_int(raw_value: str | None) -> int | None:
    if raw_value is None or raw_value.strip() == "":
        return None

    return int(raw_value)


def build_model_candidates(configured_model_name: str | None, fallback_model_name: str, profile: str, device: str) -> tuple[str, ...]:
    if configured_model_name:
        model_names = (configured_model_name, *[name for name in MODEL_CANDIDATES if name != configured_model_name])
    elif profile == "max_quality":
        model_names = MODEL_CANDIDATES
    elif profile == "high_quality":
        model_names = ("medium", "small", "tiny", "large-v3") if device == "cpu" else MODEL_CANDIDATES
    else:
        model_names = ("medium", "small", "tiny", "large-v3") if device == "cpu" else ("large-v3", "medium", "small", "tiny")

    if fallback_model_name not in model_names:
        model_names = (*model_names, fallback_model_name)

    return model_names


def resolve_decode_options(profile: str, device: str) -> dict[str, Any]:
    cpu_defaults = {
        "beam_size": 2,
        "best_of": 1,
        "condition_on_previous_text": False,
    }
    quality_defaults = {
        "beam_size": 5,
        "best_of": 1,
        "condition_on_previous_text": True,
    }

    if profile == "max_quality":
        options = dict(quality_defaults)
    elif profile == "high_quality":
        options = dict(quality_defaults if device != "cpu" else {"beam_size": 4, "best_of": 1, "condition_on_previous_text": True})
    else:
        options = dict(cpu_defaults if device == "cpu" else {"beam_size": 5, "best_of": 1, "condition_on_previous_text": True})

    options["temperature"] = 0.0
    options["vad_filter"] = True
    options["word_timestamps"] = True
    return options


def get_transcription_runtime_settings() -> dict[str, Any]:
    profile = os.getenv("WHISPERX_PROFILE", "balanced").strip().lower() or "balanced"
    if profile not in PROFILE_CANDIDATES:
        logger.warning("Unknown WHISPERX_PROFILE '%s'; using balanced.", profile)
        profile = "balanced"

    device = os.getenv("WHISPERX_DEVICE", "cpu").strip().lower() or "cpu"
    compute_type = os.getenv("WHISPERX_COMPUTE_TYPE", "int8").strip() or "int8"
    configured_model_name = os.getenv("WHISPERX_MODEL")
    fallback_model_name = os.getenv("WHISPERX_FALLBACK_MODEL", "tiny").strip() or "tiny"
    cpu_threads = parse_optional_int(os.getenv("WHISPERX_CPU_THREADS"))
    num_workers = parse_optional_int(os.getenv("WHISPERX_NUM_WORKERS"))

    return {
        "profile": profile,
        "device": device,
        "compute_type": compute_type,
        "configured_model_name": configured_model_name,
        "fallback_model_name": fallback_model_name,
        "model_names": build_model_candidates(configured_model_name, fallback_model_name, profile, device),
        "decode_options": resolve_decode_options(profile, device),
        "cpu_threads": cpu_threads,
        "num_workers": num_workers,
    }


def get_runtime_settings_for_mode(transcription_mode: str | None) -> dict[str, Any]:
    if not transcription_mode:
        runtime = get_transcription_runtime_settings()
        runtime["transcription_mode"] = "optimized"
        return runtime

    profile_override = MODE_TO_PROFILE.get(transcription_mode, transcription_mode)
    runtime = get_transcription_runtime_settings()
    if profile_override in PROFILE_CANDIDATES:
        runtime["profile"] = profile_override
        runtime["model_names"] = build_model_candidates(
            runtime["configured_model_name"],
            runtime["fallback_model_name"],
            profile_override,
            runtime["device"],
        )
        runtime["decode_options"] = resolve_decode_options(profile_override, runtime["device"])
    runtime["transcription_mode"] = transcription_mode
    return runtime


def transcribe_with_faster_whisper(
    audio_path: Path,
    manuscript_text: str = "",
    duration_ms: int | None = None,
    progress_callback: Optional[TranscribeProgressCallback] = None,
    transcription_mode: str | None = None,
) -> dict:
    from faster_whisper import WhisperModel  # type: ignore

    runtime = get_runtime_settings_for_mode(transcription_mode)
    profile = runtime["profile"]
    device = runtime["device"]
    compute_type = runtime["compute_type"]
    model_names = runtime["model_names"]
    decode_options = runtime["decode_options"]
    cpu_threads = runtime["cpu_threads"]
    num_workers = runtime["num_workers"]

    model_load_warnings: list[str] = []
    model = None
    active_model_name = None
    last_model_error: Exception | None = None
    for index, model_name in enumerate(model_names):
        try:
            if progress_callback:
                progress_callback("loading_model", 38, f"Loading {model_name}")
            model_kwargs: dict[str, Any] = {
                "device": device,
                "compute_type": compute_type,
                "local_files_only": True,
            }
            if cpu_threads is not None:
                model_kwargs["cpu_threads"] = cpu_threads
            if num_workers is not None:
                model_kwargs["num_workers"] = num_workers

            model = WhisperModel(model_name, **model_kwargs)
            active_model_name = model_name
            if index > 0:
                model_load_warnings.append(
                    f"Model '{model_names[0]}' was unavailable; used cached fallback model '{model_name}' instead."
                )
            break
        except Exception as exc:
            last_model_error = exc

    if model is None or active_model_name is None:
        raise RuntimeError(f"Unable to load any Whisper model: {last_model_error}")

    if progress_callback:
        progress_callback("transcribing", 40, f"Running transcription with {active_model_name} ({profile})")

    initial_prompt = build_initial_prompt(manuscript_text)
    transcribe_kwargs = dict(decode_options)
    transcribe_kwargs["initial_prompt"] = initial_prompt

    segment_iter, info = model.transcribe(str(audio_path), **transcribe_kwargs)

    segments = []
    words = []
    transcript_parts: list[str] = []
    last_progress_update = 0.0
    total_duration_seconds = max((duration_ms or 0) / 1000, 1.0)

    def report_segment_progress(segment_end: float) -> None:
        nonlocal last_progress_update
        if not progress_callback:
            return

        now = time.monotonic()
        if now - last_progress_update < 1.0 and segment_end < total_duration_seconds:
            return

        last_progress_update = now
        progress = min(55, 40 + int((min(segment_end, total_duration_seconds) / total_duration_seconds) * 15))
        progress_callback("transcribing", progress, f"Transcribing {progress}%")

    for segment in segment_iter:
        segment_text = (segment.text or "").strip()
        if segment_text:
            transcript_parts.append(segment_text)

        report_segment_progress(float(segment.end or 0))

        segments.append(
            {
                "id": len(segments),
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": segment_text,
            }
        )

        for word in getattr(segment, "words", []) or []:
            token_text = (word.word or "").strip()
            if not token_text:
                continue

            word_payload = {
                "word": token_text,
                "start": round(float(word.start or segment.start), 3),
                "end": round(float(word.end or segment.end), 3),
                "confidence": float(word.probability or 0.0),
            }
            words.append(word_payload)

    warnings: list[str] = list(model_load_warnings)
    if device == "cpu" and active_model_name == "large-v3":
        warnings.append(
            "Using large-v3 on CPU will be very slow for long chapters. Prefer profile=balanced or set WHISPERX_MODEL=medium unless you need maximum quality."
        )
    if not words:
        warnings.append("Faster-whisper returned no word timestamps; analysis may be less precise.")

    if manuscript_text and not transcript_parts:
        warnings.append("Transcription returned no spoken text for this audio file.")

    if progress_callback:
        progress_callback("transcribing", 55, "Finalizing transcription")

    return {
        "text": " ".join(part for part in transcript_parts if part).strip(),
        "segments": segments,
        "words": words,
        "source": "faster-whisper-word-timestamps",
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "model": active_model_name,
        "transcription_mode": runtime["transcription_mode"],
        "profile": profile,
        "device": device,
        "compute_type": compute_type,
        "decode_options": {
            "beam_size": decode_options["beam_size"],
            "best_of": decode_options["best_of"],
            "condition_on_previous_text": decode_options["condition_on_previous_text"],
            "vad_filter": decode_options["vad_filter"],
            "word_timestamps": decode_options["word_timestamps"],
            "temperature": decode_options["temperature"],
        },
        "warnings": warnings,
        "is_placeholder": False,
    }


def transcribe_with_whisperx(
    audio_path: Path | None,
    manuscript_text: str = "",
    duration_ms: int | None = None,
    progress_callback: Optional[TranscribeProgressCallback] = None,
    transcription_mode: str | None = None,
) -> dict:
    """
    Prefer a real WhisperX run when available, otherwise fall back to a
    deterministic placeholder transcript so the rest of the review pipeline
    remains inspectable offline.
    """
    if audio_path is None:
        return build_placeholder_transcript(manuscript_text, duration_ms)

    try:
        return transcribe_with_faster_whisper(
            audio_path,
            manuscript_text=manuscript_text,
            duration_ms=duration_ms,
            progress_callback=progress_callback,
            transcription_mode=transcription_mode,
        )
    except Exception as exc:
        transcript = build_placeholder_transcript(manuscript_text, duration_ms)
        transcript.setdefault("warnings", []).append(f"Audio transcription failed: {exc}")
        return transcript
