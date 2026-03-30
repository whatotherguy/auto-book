from __future__ import annotations

from typing import TypedDict


class TokenRecord(TypedDict, total=False):
    index: int
    text: str
    normalized: str
    start_ms: int | None
    end_ms: int | None
    confidence: float | None
    source_word_index: int | None


def tokenize(text: str) -> list[str]:
    return [token for token in text.split(" ") if token]


def build_text_token_records(text: str) -> list[TokenRecord]:
    tokens = tokenize(text)
    return [
        {
            "index": index,
            "text": token,
            "normalized": token,
        }
        for index, token in enumerate(tokens)
    ]
