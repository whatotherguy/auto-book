from __future__ import annotations

from difflib import SequenceMatcher

from ..services.text_normalize import normalize_for_alignment
from ..utils.tokenization import TokenRecord, tokenize


def build_manuscript_tokens(manuscript_text: str) -> list[TokenRecord]:
    tokens = manuscript_text.split()
    return [
        {
            "index": index,
            "text": token,
            "normalized": normalize_for_alignment(token),
        }
        for index, token in enumerate(tokens)
    ]


def build_spoken_tokens(transcript: dict) -> list[TokenRecord]:
    words = transcript.get("words", [])
    spoken_tokens: list[TokenRecord] = []

    for index, word in enumerate(words):
        raw_text = str(word.get("word", ""))
        token_text = normalize_for_alignment(raw_text)
        for normalized in tokenize(token_text):
            confidence = word.get("confidence")
            if confidence is None:
                confidence = word.get("score")
            spoken_tokens.append(
                {
                    "index": len(spoken_tokens),
                    "text": raw_text,
                    "normalized": normalized,
                    "start_ms": int(float(word.get("start", 0)) * 1000),
                    "end_ms": int(float(word.get("end", 0)) * 1000),
                    "confidence": float(confidence or 0.0),
                    "source_word_index": index,
                }
            )

    return spoken_tokens


def build_alignment(manuscript_tokens: list[TokenRecord], spoken_tokens: list[TokenRecord]) -> dict:
    manuscript_values = [token["normalized"] for token in manuscript_tokens]
    spoken_values = [token["normalized"] for token in spoken_tokens]

    matcher = SequenceMatcher(a=manuscript_values, b=spoken_values, autojunk=False)
    opcodes = matcher.get_opcodes()

    matches = [
        {
            "op": tag,
            "manuscript_start": i1,
            "manuscript_end": i2,
            "spoken_start": j1,
            "spoken_end": j2,
            "manuscript_text": " ".join(manuscript_values[i1:i2]),
            "spoken_text": " ".join(spoken_values[j1:j2]),
        }
        for tag, i1, i2, j1, j2 in opcodes
    ]

    return {
        "manuscript_tokens": manuscript_tokens,
        "spoken_tokens": spoken_tokens,
        "matches": matches,
        "match_ratio": round(matcher.ratio(), 4),
        "notes": [],
    }
