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


def _get_thermal_settings() -> dict[str, Any]:
    """Read thermal protection settings from environment."""
    return {
        "enabled": os.getenv("GPU_THERMAL_PROTECTION", "true").strip().lower() in ("true", "1", "yes"),
        "warning_temp": int(os.getenv("GPU_TEMP_WARNING", "78")),
        "critical_temp": int(os.getenv("GPU_TEMP_CRITICAL", "85")),
        "cooldown_seconds": int(os.getenv("GPU_COOLDOWN_SECONDS", "30")),
        "poll_interval": int(os.getenv("GPU_THERMAL_POLL_INTERVAL", "10")),
    }

# ---------------------------------------------------------------------------
# GPU auto-detection (cached after first call)
# ---------------------------------------------------------------------------

_gpu_status: dict[str, Any] | None = None


def detect_gpu() -> dict[str, Any]:
    """Detect CUDA GPU availability. Cached after first call."""
    global _gpu_status
    if _gpu_status is not None:
        return _gpu_status

    result: dict[str, Any] = {
        "available": False,
        "device": "cpu",
        "compute_type": "int8",
        "name": None,
        "vram_gb": None,
    }

    try:
        import torch

        if torch.cuda.is_available():
            result["available"] = True
            result["device"] = "cuda"
            result["name"] = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            result["vram_gb"] = round(vram_bytes / (1024**3), 1)
            # Choose compute type based on VRAM
            if result["vram_gb"] >= 8:
                result["compute_type"] = "float16"
            elif result["vram_gb"] >= 4:
                result["compute_type"] = "int8_float16"
            else:
                result["compute_type"] = "int8"
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("GPU detection failed: %s", exc)

    _gpu_status = result
    return result

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

    # Extract proper nouns and uncommon words for Whisper vocabulary priming
    words = manuscript_text.split()
    unique_words: list[str] = []
    seen: set[str] = set()
    for word in words:
        cleaned = word.strip(".,!?;:\"'()[]")
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        # Include capitalized words (likely proper nouns) and long words (likely domain-specific)
        if (len(cleaned) > 1 and cleaned[0].isupper() and not cleaned.isupper()) or len(cleaned) >= 8:
            unique_words.append(cleaned)

    vocab_hint = " ".join(unique_words[:30])  # Up to 30 unique vocabulary words
    context = normalized[:400].strip()

    prompt = f"{vocab_hint}. {context}" if vocab_hint else context
    # Whisper prompt limit is roughly 224 tokens (~1000 chars)
    return prompt[:1000].strip() or None


def parse_optional_int(raw_value: str | None) -> int | None:
    if raw_value is None or raw_value.strip() == "":
        return None

    return int(raw_value)


def build_model_candidates(configured_model_name: str | None, fallback_model_name: str, profile: str, device: str) -> tuple[str, ...]:
    if device == "cuda":
        # GPU is fast enough for large models even in balanced mode
        if configured_model_name:
            model_names = (configured_model_name, *[n for n in MODEL_CANDIDATES if n != configured_model_name])
        else:
            model_names = MODEL_CANDIDATES  # large-v3 first
    elif configured_model_name:
        model_names = (configured_model_name, *[name for name in MODEL_CANDIDATES if name != configured_model_name])
    elif profile == "max_quality":
        model_names = MODEL_CANDIDATES
    elif profile == "high_quality":
        model_names = ("medium", "small", "tiny", "large-v3")
    else:
        model_names = ("medium", "small", "tiny", "large-v3")

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

    raw_device = os.getenv("WHISPERX_DEVICE", "auto").strip().lower() or "auto"
    raw_compute_type = os.getenv("WHISPERX_COMPUTE_TYPE", "").strip()

    if raw_device == "auto":
        gpu = detect_gpu()
        device = gpu["device"]  # "cuda" or "cpu"
        compute_type = raw_compute_type or gpu["compute_type"]
    else:
        device = raw_device
        compute_type = raw_compute_type or ("float16" if device == "cuda" else "int8")
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
    cancel_check: Optional[Callable[[], bool]] = None,
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

    # --- Thermal protection setup (GPU only) ---
    thermal_guard = None
    if device == "cuda":
        from .gpu_thermal import ThermalGuard, read_gpu_temperature

        thermal_cfg = _get_thermal_settings()
        if thermal_cfg["enabled"]:
            # Pre-flight temp check: warn if already warm before starting
            pre_temp = read_gpu_temperature()
            if pre_temp is not None and pre_temp >= thermal_cfg["warning_temp"]:
                logger.warning(
                    "GPU already at %d°C before transcription starts (warning threshold: %d°C).",
                    pre_temp, thermal_cfg["warning_temp"],
                )
                if progress_callback:
                    progress_callback("thermal_warning", 36, f"GPU already warm ({pre_temp}°C). Thermal protection active.")

            thermal_guard = ThermalGuard(
                warning_temp=thermal_cfg["warning_temp"],
                critical_temp=thermal_cfg["critical_temp"],
                cooldown_seconds=thermal_cfg["cooldown_seconds"],
                poll_interval=thermal_cfg["poll_interval"],
                enabled=True,
                progress_callback=progress_callback,
            )

    model_load_warnings: list[str] = []
    model = None
    active_model_name = None
    last_model_error: Exception | None = None
    for index, model_name in enumerate(model_names):
        for local_only in (True, False):
            try:
                if progress_callback:
                    label = f"Loading {model_name}" + ("" if local_only else " (downloading)")
                    progress_callback("loading_model", 38, label)
                model_kwargs: dict[str, Any] = {
                    "device": device,
                    "compute_type": compute_type,
                    "local_files_only": local_only,
                }
                if cpu_threads is not None:
                    model_kwargs["cpu_threads"] = cpu_threads
                if num_workers is not None:
                    model_kwargs["num_workers"] = num_workers

                model = WhisperModel(model_name, **model_kwargs)
                active_model_name = model_name
                break
            except Exception as exc:
                last_model_error = exc
        if model is not None:
            if index > 0:
                model_load_warnings.append(
                    f"Model '{model_names[0]}' was unavailable; used fallback model '{model_name}' instead."
                )
            break

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
    segments_since_thermal_check = 0

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

        # Thermal check every ~20 segments to avoid polling too frequently
        segments_since_thermal_check += 1
        if thermal_guard and segments_since_thermal_check >= 20:
            segments_since_thermal_check = 0
            thermal_guard.check_and_throttle(cancel_check=cancel_check)

    warnings: list[str] = list(model_load_warnings)
    if device == "cpu" and active_model_name == "large-v3":
        warnings.append(
            "Using large-v3 on CPU will be very slow for long chapters. Prefer profile=balanced or set WHISPERX_MODEL=medium unless you need maximum quality."
        )
    if not words:
        warnings.append("Faster-whisper returned no word timestamps; analysis may be less precise.")

    if manuscript_text and not transcript_parts:
        warnings.append("Transcription returned no spoken text for this audio file.")

    # Report thermal stats
    if thermal_guard and thermal_guard.total_cooldown_seconds > 0:
        warnings.append(
            f"Thermal protection paused transcription for {thermal_guard.total_cooldown_seconds:.0f}s total "
            f"(peak GPU temp: {thermal_guard.peak_temp}°C)."
        )

    if progress_callback:
        progress_callback("transcribing", 55, "Finalizing transcription")

    result = {
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
        "gpu_name": detect_gpu().get("name") if device == "cuda" else None,
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

    if thermal_guard:
        result["thermal_stats"] = {
            "peak_temp_c": thermal_guard.peak_temp,
            "total_cooldown_seconds": thermal_guard.total_cooldown_seconds,
        }

    return result


def transcribe_with_whisperx(
    audio_path: Path | None,
    manuscript_text: str = "",
    duration_ms: int | None = None,
    progress_callback: Optional[TranscribeProgressCallback] = None,
    transcription_mode: str | None = None,
    cache_path: Path | None = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    Prefer a real WhisperX run when available, otherwise fall back to a
    deterministic placeholder transcript so the rest of the review pipeline
    remains inspectable offline.

    If *cache_path* points to an existing transcript JSON file, load and
    return it instead of re-transcribing (unless the cached result is a
    placeholder or has no words).
    """
    if audio_path is None:
        return build_placeholder_transcript(manuscript_text, duration_ms)

    # Determine if Whisper API backend is requested
    from ..config import settings as app_settings
    wants_api = transcription_mode == "whisper_api" or app_settings.transcription_backend == "whisper_api"

    # Check for cached transcript (skip cache if backend changed)
    if cache_path is not None and cache_path.exists():
        try:
            import json
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if not cached.get("is_placeholder") and cached.get("words"):
                cached_source = cached.get("source", "")
                cached_is_api = "api" in cached_source.lower()
                if wants_api == cached_is_api:
                    logger.info("Using cached transcript from %s", cache_path)
                    cached.setdefault("warnings", []).append("Loaded from cached transcript.")
                    return cached
                else:
                    logger.info("Cached transcript source (%s) doesn't match requested backend (api=%s), re-transcribing", cached_source, wants_api)
        except (json.JSONDecodeError, OSError):
            pass  # Fall through to fresh transcription

    if wants_api:
        from .transcribe_api import is_whisper_api_available, transcribe_with_whisper_api
        if is_whisper_api_available():
            try:
                return transcribe_with_whisper_api(
                    audio_path,
                    manuscript_text=manuscript_text,
                    duration_ms=duration_ms,
                    progress_callback=progress_callback,
                )
            except Exception as exc:
                logger.warning("Whisper API transcription failed, falling back to local: %s", exc)
                # Fall through to local transcription

    try:
        return transcribe_with_faster_whisper(
            audio_path,
            manuscript_text=manuscript_text,
            duration_ms=duration_ms,
            progress_callback=progress_callback,
            transcription_mode=transcription_mode,
            cancel_check=cancel_check,
        )
    except Exception as exc:
        transcript = build_placeholder_transcript(manuscript_text, duration_ms)
        transcript.setdefault("warnings", []).append(f"Audio transcription failed: {exc}")
        return transcript
