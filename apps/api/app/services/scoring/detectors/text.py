"""Text-based detectors: TextMismatch, RepeatedPhrase, SkippedText."""

from __future__ import annotations

from ..detector_output import DetectorOutput


def _levenshtein_ratio(a: str, b: str) -> float:
    """Simple Levenshtein distance ratio (0=identical, 1=completely different)."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    len_a, len_b = len(a), len(b)
    matrix = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        prev = matrix[:]
        matrix[0] = i
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[j] = min(prev[j] + 1, matrix[j - 1] + 1, prev[j - 1] + cost)
    max_len = max(len_a, len_b)
    return matrix[len_b] / max_len if max_len > 0 else 0.0


def _token_overlap(expected: str, spoken: str) -> float:
    """Word overlap ratio between expected and spoken text."""
    expected_words = set(expected.lower().split())
    spoken_words = set(spoken.lower().split())
    if not expected_words or not spoken_words:
        return 0.0
    return len(expected_words & spoken_words) / max(len(expected_words), len(spoken_words))


def detect_text_mismatch(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect text mismatches between expected and spoken text."""
    expected = features.get("expected_text", "")
    spoken = features.get("spoken_text", "")
    whisper_conf = features.get("whisper_word_confidence", 1.0)

    if not expected and not spoken:
        return DetectorOutput(detector_name="text_mismatch")

    lev_ratio = _levenshtein_ratio(expected.lower(), spoken.lower())
    overlap = _token_overlap(expected, spoken)

    score = lev_ratio * 0.6 + (1.0 - overlap) * 0.4
    score *= min(1.0, whisper_conf)  # Scale by transcription confidence

    # Short segments get reduced score
    word_count = len(spoken.split()) if spoken else 0
    if word_count <= 2:
        score *= 0.7

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="text_mismatch",
        score=min(1.0, score),
        confidence=whisper_conf,
        reasons=[f"levenshtein_ratio={lev_ratio:.2f}", f"token_overlap={overlap:.2f}"],
        features_used={"levenshtein_ratio": lev_ratio, "token_overlap": overlap, "word_count": word_count},
        triggered=triggered,
    )


def detect_repeated_phrase(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect repeated phrases in the spoken text."""
    spoken = features.get("spoken_text", "")
    issue_type = features.get("issue_type", "")

    score = 0.0
    reasons = []

    if issue_type in ("repetition", "false_start"):
        score = features.get("confidence", 0.8)
        reasons.append(f"detected_as={issue_type}")

    # Check for repeated words within the spoken text
    words = spoken.lower().split()
    if len(words) >= 4:
        half = len(words) // 2
        for span in range(half, 1, -1):
            for i in range(len(words) - 2 * span + 1):
                if words[i:i + span] == words[i + span:i + 2 * span]:
                    score = max(score, 0.7)
                    reasons.append(f"repeated_span={span}_words")
                    break
            if score >= 0.7:
                break

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="repeated_phrase",
        score=min(1.0, score),
        confidence=0.9 if issue_type in ("repetition", "false_start") else 0.7,
        reasons=reasons,
        features_used={"issue_type": issue_type, "word_count": len(words)},
        triggered=triggered,
    )


def detect_skipped_text(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect skipped/missing manuscript text."""
    issue_type = features.get("issue_type", "")
    expected = features.get("expected_text", "")
    spoken = features.get("spoken_text", "")

    score = 0.0
    reasons = []

    if issue_type == "missing_text":
        expected_words = len(expected.split()) if expected else 0
        score = min(1.0, 0.5 + expected_words * 0.05)
        reasons.append(f"missing_words={expected_words}")
    elif expected and not spoken.strip():
        score = 0.6
        reasons.append("empty_spoken_text")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="skipped_text",
        score=min(1.0, score),
        confidence=features.get("confidence", 0.7),
        reasons=reasons,
        features_used={"issue_type": issue_type, "expected_word_count": len(expected.split()) if expected else 0},
        triggered=triggered,
    )
