"""OpenAI Whisper API transcription backend.

Provides cloud-based transcription for users without a local GPU.
Requires OPENAI_API_KEY to be set. Falls back gracefully on failure.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# OpenAI Whisper API limit is 25MB. We chunk at 20 minutes to stay safely under.
CHUNK_DURATION_SECONDS = 1200  # 20 minutes
CHUNK_OVERLAP_SECONDS = 5     # 5 second overlap for stitching


def is_whisper_api_available() -> bool:
    """Check if the OpenAI API key is configured."""
    from ..config import settings
    return bool(settings.openai_api_key)


def _split_audio_into_chunks(audio_path: Path, chunk_duration: int = CHUNK_DURATION_SECONDS) -> list[dict[str, Any]]:
    """Split a WAV file into chunks using ffmpeg. Returns list of {path, offset_seconds}."""
    from ..services.audio import probe_audio_metadata

    metadata = probe_audio_metadata(audio_path)
    duration_ms = metadata.get("duration_ms") or 0
    duration_seconds = duration_ms / 1000

    if duration_seconds <= chunk_duration:
        return [{"path": audio_path, "offset_seconds": 0.0, "is_temp": False}]

    chunks = []
    temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    offset = 0.0
    chunk_index = 0

    while offset < duration_seconds:
        chunk_path = Path(temp_dir) / f"chunk_{chunk_index:03d}.wav"
        # Include overlap from previous chunk for stitching
        actual_start = max(0, offset - CHUNK_OVERLAP_SECONDS) if chunk_index > 0 else 0
        actual_duration = chunk_duration + (CHUNK_OVERLAP_SECONDS if chunk_index > 0 else 0)

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(audio_path),
            "-ss", f"{actual_start:.3f}",
            "-t", f"{actual_duration:.3f}",
            "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(chunk_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.warning("Failed to create audio chunk %d: %s", chunk_index, result.stderr)
            break

        chunks.append({
            "path": chunk_path,
            "offset_seconds": actual_start,
            "is_temp": True,
        })
        offset += chunk_duration
        chunk_index += 1

    return chunks


def _transcribe_chunk_via_api(
    chunk_path: Path,
    api_key: str,
    language: str = "en",
    prompt: str | None = None,
) -> dict[str, Any]:
    """Transcribe a single audio chunk via the OpenAI Whisper API."""
    import httpx

    with open(chunk_path, "rb") as audio_file:
        files = {"file": (chunk_path.name, audio_file, "audio/wav")}
        data: dict[str, str] = {
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
            "language": language,
        }
        if prompt:
            data["prompt"] = prompt[:224]  # Whisper prompt limit

        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=300.0,
        )

    if response.status_code != 200:
        raise RuntimeError(f"Whisper API returned {response.status_code}: {response.text[:500]}")

    return response.json()


def _merge_chunk_results(chunk_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple chunk transcription results into a single transcript."""
    all_words = []
    all_segments = []
    all_text_parts = []

    for chunk in chunk_results:
        offset = chunk["offset_seconds"]
        result = chunk["result"]

        for word in result.get("words", []):
            all_words.append({
                "word": word.get("word", ""),
                "start": round(float(word.get("start", 0)) + offset, 3),
                "end": round(float(word.get("end", 0)) + offset, 3),
                "confidence": 0.85,  # Whisper API doesn't return per-word confidence
            })

        for segment in result.get("segments", []):
            all_segments.append({
                "id": len(all_segments),
                "start": round(float(segment.get("start", 0)) + offset, 3),
                "end": round(float(segment.get("end", 0)) + offset, 3),
                "text": segment.get("text", "").strip(),
            })

        text = result.get("text", "")
        if text:
            all_text_parts.append(text.strip())

    # Deduplicate words in overlap regions (by timestamp proximity)
    if len(chunk_results) > 1:
        all_words = _dedupe_overlapping_words(all_words)

    return {
        "text": " ".join(all_text_parts),
        "words": all_words,
        "segments": all_segments,
    }


def _dedupe_overlapping_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate words from chunk overlap regions."""
    if not words:
        return words

    # Sort by start time
    words.sort(key=lambda w: w["start"])
    deduped = [words[0]]

    for word in words[1:]:
        prev = deduped[-1]
        # If two words start within 100ms of each other and have the same text, skip duplicate
        if abs(word["start"] - prev["start"]) < 0.1 and word["word"].strip().lower() == prev["word"].strip().lower():
            continue
        deduped.append(word)

    return deduped


def transcribe_with_whisper_api(
    audio_path: Path,
    manuscript_text: str = "",
    duration_ms: int | None = None,
    progress_callback: Optional[Any] = None,
) -> dict[str, Any]:
    """Transcribe audio using the OpenAI Whisper API with automatic chunking."""
    from ..config import settings
    from .transcribe import build_initial_prompt

    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured. Set OPENAI_API_KEY in .env to use Whisper API transcription.")

    if progress_callback:
        progress_callback("transcribing", 38, "Preparing audio for Whisper API")

    chunks = _split_audio_into_chunks(audio_path)
    initial_prompt = build_initial_prompt(manuscript_text)

    chunk_results = []
    for index, chunk in enumerate(chunks):
        if progress_callback:
            pct = 38 + int((index / max(len(chunks), 1)) * 17)
            progress_callback("transcribing", pct, f"Transcribing chunk {index + 1}/{len(chunks)} via Whisper API")

        try:
            result = _transcribe_chunk_via_api(
                chunk["path"],
                api_key=api_key,
                prompt=initial_prompt,
            )
            chunk_results.append({
                "offset_seconds": chunk["offset_seconds"],
                "result": result,
            })
        finally:
            # Clean up temp files
            if chunk.get("is_temp") and chunk["path"].exists():
                chunk["path"].unlink(missing_ok=True)

    if not chunk_results:
        raise RuntimeError("Whisper API returned no results for any audio chunk")

    merged = _merge_chunk_results(chunk_results)

    if progress_callback:
        progress_callback("transcribing", 55, "Finalizing Whisper API transcription")

    warnings = []
    if len(chunks) > 1:
        warnings.append(f"Audio was split into {len(chunks)} chunks for API transcription. Word timestamps near chunk boundaries may be less precise.")

    return {
        "text": merged["text"],
        "segments": merged["segments"],
        "words": merged["words"],
        "source": "openai-whisper-api",
        "model": "whisper-1",
        "transcription_mode": "whisper_api",
        "profile": "api",
        "device": "cloud",
        "compute_type": "api",
        "warnings": warnings,
        "is_placeholder": False,
    }
