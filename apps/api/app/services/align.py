from __future__ import annotations

from difflib import SequenceMatcher

from ..services.text_normalize import normalize_for_alignment
from ..utils.tokenization import TokenRecord, tokenize

# ---------------------------------------------------------------------------
# Spelling-variant normalization
# ---------------------------------------------------------------------------

_SPELLING_VARIANTS = {
    "grey": "gray", "towards": "toward", "amongst": "among",
    "whilst": "while", "colour": "color", "favour": "favor",
    "honour": "honor", "neighbour": "neighbor", "theatre": "theater",
    "centre": "center", "defence": "defense", "licence": "license",
    "analyse": "analyze", "recognise": "recognize", "realise": "realize",
    "organisation": "organization", "apologise": "apologize",
    "cancelled": "canceled", "travelled": "traveled", "focussed": "focused",
    "judgement": "judgment",
}


def _normalize_variant(word: str) -> str:
    return _SPELLING_VARIANTS.get(word, word)


# ---------------------------------------------------------------------------
# Fuzzy near-match (Levenshtein distance <= 1)
# ---------------------------------------------------------------------------

def _is_near_match(a: str, b: str) -> bool:
    if len(a) < 4 or len(b) < 4:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        # Check for single substitution
        return sum(ca != cb for ca, cb in zip(a, b)) <= 1
    # Check for single insertion/deletion
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    diffs = 0
    si = li = 0
    while si < len(short) and li < len(long_):
        if short[si] != long_[li]:
            diffs += 1
            if diffs > 1:
                return False
            li += 1
        else:
            si += 1
            li += 1
    return True


def _tokens_match(a: str, b: str) -> bool:
    """Return True if two tokens are an exact match or a near-match."""
    if a == b:
        return True
    return _is_near_match(a, b)


# ---------------------------------------------------------------------------
# Token builders
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Windowed alignment constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = 400        # tokens per alignment window
WINDOW_OVERLAP = 40      # token overlap for anchor matching
MIN_ANCHOR_RUN = 3       # minimum consecutive equal tokens to count as an anchor


# ---------------------------------------------------------------------------
# Single-pass alignment (core SequenceMatcher + near-match refinement)
# ---------------------------------------------------------------------------

def _align_single_pass(
    manuscript_values: list[str],
    spoken_values: list[str],
) -> list[dict]:
    """Run SequenceMatcher on two value lists and return match dicts with
    *local* indices (relative to the slices passed in)."""

    matcher = SequenceMatcher(
        a=manuscript_values, b=spoken_values, autojunk=False,
    )
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

    # Post-process: upgrade 1-to-1 "replace" ops to "equal" when the words
    # are near-matches (edit distance <= 1).
    refined_matches: list[dict] = []
    for match in matches:
        if (
            match["op"] == "replace"
            and match["manuscript_end"] - match["manuscript_start"] == 1
            and match["spoken_end"] - match["spoken_start"] == 1
            and _is_near_match(
                manuscript_values[match["manuscript_start"]],
                spoken_values[match["spoken_start"]],
            )
        ):
            match = {**match, "op": "equal"}
        refined_matches.append(match)

    return refined_matches


# ---------------------------------------------------------------------------
# Windowed alignment helpers
# ---------------------------------------------------------------------------

def _find_splice_point(
    prev_matches: list[dict],
    next_matches: list[dict],
    overlap_start: int,
) -> int:
    """Find the spoken index where we should splice between two windows.

    Looks for the first run of >= MIN_ANCHOR_RUN consecutive "equal" tokens
    in the overlap zone from the new window's matches.
    """
    best_splice = overlap_start
    best_run = 0

    for match in next_matches:
        if match["op"] == "equal" and match["spoken_start"] >= overlap_start:
            run_length = match["spoken_end"] - match["spoken_start"]
            if run_length >= MIN_ANCHOR_RUN and run_length > best_run:
                best_run = run_length
                best_splice = match["spoken_start"]
                break  # Use the first good anchor

    return best_splice


def _build_windowed_alignment(
    manuscript_values: list[str],
    spoken_values: list[str],
    manuscript_tokens: list[TokenRecord],
    spoken_tokens: list[TokenRecord],
) -> list[dict]:
    """Split the token lists into overlapping windows, align each
    independently, then stitch via anchor overlap."""

    all_matches: list[dict] = []
    step = WINDOW_SIZE - WINDOW_OVERLAP
    manuscript_cursor = 0

    # Generous manuscript window: proportional to spoken window, with margin
    manuscript_window_ratio = max(
        len(manuscript_values) / max(len(spoken_values), 1), 0.5,
    )

    for spoken_start in range(0, len(spoken_values), step):
        spoken_end = min(spoken_start + WINDOW_SIZE, len(spoken_values))
        spoken_window = spoken_values[spoken_start:spoken_end]

        # Estimate manuscript range for this window
        ms_start = manuscript_cursor
        ms_end = min(
            int(ms_start + len(spoken_window) * manuscript_window_ratio * 1.5),
            len(manuscript_values),
        )
        # For the last window, take everything remaining
        if spoken_end >= len(spoken_values):
            ms_end = len(manuscript_values)
        ms_window = manuscript_values[ms_start:ms_end]

        # Align this window
        window_matches = _align_single_pass(ms_window, spoken_window)

        # Translate local indices back to global
        for match in window_matches:
            match["manuscript_start"] += ms_start
            match["manuscript_end"] += ms_start
            match["spoken_start"] += spoken_start
            match["spoken_end"] += spoken_start
            match["manuscript_text"] = " ".join(
                manuscript_values[match["manuscript_start"]:match["manuscript_end"]],
            )
            match["spoken_text"] = " ".join(
                spoken_values[match["spoken_start"]:match["spoken_end"]],
            )

        if all_matches and window_matches:
            # Find anchor point in overlap region to splice cleanly
            splice_index = _find_splice_point(
                all_matches, window_matches, spoken_start,
            )
            # Remove matches from previous window that extend past splice
            while all_matches and all_matches[-1]["spoken_end"] > splice_index:
                all_matches.pop()
            # Remove matches from new window before splice
            window_matches = [
                m for m in window_matches if m["spoken_start"] >= splice_index
            ]

        all_matches.extend(window_matches)

        # Advance manuscript cursor based on the last match that consumed
        # spoken tokens. Trailing "delete" ops (manuscript-only) would
        # overshoot the cursor into territory the next window still needs.
        for m in reversed(window_matches):
            if m["spoken_end"] > m["spoken_start"]:
                manuscript_cursor = m["manuscript_end"]
                break

    return all_matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_alignment(
    manuscript_tokens: list[TokenRecord],
    spoken_tokens: list[TokenRecord],
) -> dict:
    # Normalize spelling variants before running the sequence matcher
    manuscript_values = [
        _normalize_variant(token["normalized"]) for token in manuscript_tokens
    ]
    spoken_values = [
        _normalize_variant(token["normalized"]) for token in spoken_tokens
    ]

    # Choose single-pass or windowed alignment based on input size
    if (
        len(manuscript_values) <= WINDOW_SIZE
        and len(spoken_values) <= WINDOW_SIZE
    ):
        matches = _align_single_pass(manuscript_values, spoken_values)
        # Compute match_ratio from the matches already in hand — avoids a
        # redundant second SequenceMatcher construction.
        equal_count = sum(
            m["spoken_end"] - m["spoken_start"]
            for m in matches
            if m["op"] == "equal"
        )
        total = len(manuscript_values) + len(spoken_values)
        match_ratio = round(2 * equal_count / total if total else 0.0, 4)
    else:
        matches = _build_windowed_alignment(
            manuscript_values, spoken_values,
            manuscript_tokens, spoken_tokens,
        )
        # Compute match_ratio as fraction of spoken tokens in "equal" opcodes
        equal_spoken_count = sum(
            m["spoken_end"] - m["spoken_start"]
            for m in matches
            if m["op"] == "equal"
        )
        match_ratio = round(
            equal_spoken_count / max(len(spoken_values), 1), 4,
        )

    return {
        "manuscript_tokens": manuscript_tokens,
        "spoken_tokens": spoken_tokens,
        "matches": matches,
        "match_ratio": match_ratio,
        "notes": [],
    }
