from pathlib import Path
import wave

from app.services.acx import analyze_acx_audio


def write_wave(path: Path, amplitude: int, sample_rate: int = 44100, seconds: float = 1.0) -> None:
    frame_count = int(sample_rate * seconds)
    frames = bytearray()
    for _ in range(frame_count):
        frames.extend(int(amplitude).to_bytes(2, "little", signed=True))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))


def write_wave_segments(path: Path, segments: list[tuple[int, float]], sample_rate: int = 44100) -> None:
    frames = bytearray()
    for amplitude, seconds in segments:
        frame_count = int(sample_rate * seconds)
        for _ in range(frame_count):
            frames.extend(int(amplitude).to_bytes(2, "little", signed=True))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))


def test_analyze_acx_audio_flags_hot_file(tmp_path: Path):
    target = tmp_path / "hot.wav"
    write_wave(target, amplitude=30000)

    report = analyze_acx_audio(target)

    assert report["levels"]["peak_dbfs"] > -3.0
    assert any(check["name"] == "peak_level" and check["status"] == "fail" for check in report["checks"])


def test_analyze_acx_audio_accepts_reasonable_sample_rate(tmp_path: Path):
    target = tmp_path / "clean.wav"
    write_wave(target, amplitude=2000)

    report = analyze_acx_audio(target)

    assert report["format"]["sample_rate_hz"] == 44100
    assert any(check["name"] == "sample_rate" and check["status"] == "pass" for check in report["checks"])


def test_analyze_acx_audio_uses_fallback_noise_floor_when_quiet_windows_are_sparse(tmp_path: Path):
    target = tmp_path / "sparse_quiet.wav"
    write_wave_segments(target, [(0, 0.45), (2000, 0.55)])

    report = analyze_acx_audio(target)

    noise_floor_check = next(check for check in report["checks"] if check["name"] == "noise_floor")

    assert noise_floor_check["summary"].startswith("Estimated from the 10th percentile of all windows")
    assert "may be unreliable" in noise_floor_check["summary"]
    assert noise_floor_check["actual"] != "unavailable"


def test_analyze_acx_audio_includes_cross_chapter_consistency_note(tmp_path: Path):
    target = tmp_path / "clean.wav"
    write_wave(target, amplitude=2000)

    report = analyze_acx_audio(target)

    assert report["checks"][-1] == {
        "name": "cross_chapter_consistency",
        "status": "info",
        "actual": "N/A",
        "target": "<=20dB variation across all chapters",
        "summary": "Cross-chapter consistency requires comparing all chapters. Review manually before ACX submission.",
        "suggestion": None,
    }
