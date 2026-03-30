from pathlib import Path
import sys
import types

from app.services.transcribe import (
    build_model_candidates,
    get_runtime_settings_for_mode,
    get_transcription_runtime_settings,
    transcribe_with_whisperx,
)


class FakeWord:
    def __init__(self, word: str, start: float, end: float, probability: float):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class FakeSegment:
    def __init__(self, text: str, start: float, end: float, words: list[FakeWord]):
        self.text = text
        self.start = start
        self.end = end
        self.words = words


class FakeInfo:
    language = "en"
    language_probability = 0.98


class FakeWhisperModel:
    def __init__(self, model_name: str, device: str, compute_type: str, local_files_only: bool):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.local_files_only = local_files_only

    def transcribe(self, audio_path: str, word_timestamps: bool, vad_filter: bool, **kwargs):
        assert audio_path.endswith(".wav")
        assert word_timestamps is True
        assert vad_filter is True

        segments = [
            FakeSegment(
                text="Hello world",
                start=0.0,
                end=1.0,
                words=[
                    FakeWord("Hello", 0.0, 0.4, 0.91),
                    FakeWord("world", 0.42, 0.9, 0.89),
                ],
            )
        ]
        return iter(segments), FakeInfo()


def test_transcribe_uses_faster_whisper_word_timestamps(monkeypatch):
    fake_module = types.SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.delenv("WHISPERX_PROFILE", raising=False)
    monkeypatch.delenv("WHISPERX_MODEL", raising=False)
    monkeypatch.delenv("WHISPERX_FALLBACK_MODEL", raising=False)
    monkeypatch.setenv("WHISPERX_DEVICE", "cpu")

    transcript = transcribe_with_whisperx(Path("chapter.wav"), manuscript_text="ignored")

    assert transcript["source"] == "faster-whisper-word-timestamps"
    assert transcript["text"] == "Hello world"
    assert transcript["language"] == "en"
    assert transcript["language_probability"] == 0.98
    assert transcript["warnings"] == []
    assert transcript["model"] == "medium"
    assert transcript["profile"] == "balanced"
    assert transcript["device"] == "cpu"
    assert transcript["decode_options"]["beam_size"] == 2
    assert transcript["decode_options"]["condition_on_previous_text"] is False
    assert transcript["words"] == [
        {"word": "Hello", "start": 0.0, "end": 0.4, "confidence": 0.91},
        {"word": "world", "start": 0.42, "end": 0.9, "confidence": 0.89},
    ]


def test_build_model_candidates_prefers_practical_cpu_defaults():
    assert build_model_candidates(None, "tiny", "balanced", "cpu") == ("medium", "small", "tiny", "large-v3")
    assert build_model_candidates(None, "tiny", "max_quality", "cpu") == ("large-v3", "medium", "small", "tiny")


def test_runtime_settings_honor_explicit_model(monkeypatch):
    monkeypatch.setenv("WHISPERX_PROFILE", "balanced")
    monkeypatch.setenv("WHISPERX_MODEL", "large-v3")
    monkeypatch.setenv("WHISPERX_DEVICE", "cpu")
    monkeypatch.setenv("WHISPERX_CPU_THREADS", "6")

    runtime = get_transcription_runtime_settings()

    assert runtime["profile"] == "balanced"
    assert runtime["model_names"][0] == "large-v3"
    assert runtime["cpu_threads"] == 6


def test_runtime_settings_for_mode_map_optimized_to_balanced(monkeypatch):
    monkeypatch.delenv("WHISPERX_MODEL", raising=False)
    monkeypatch.setenv("WHISPERX_DEVICE", "cpu")

    runtime = get_runtime_settings_for_mode("optimized")

    assert runtime["transcription_mode"] == "optimized"
    assert runtime["profile"] == "balanced"
    assert runtime["model_names"][0] == "medium"
