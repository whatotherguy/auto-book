from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlmodel import Session

from ..detection_config import (
    FALSE_START_CONFIDENCE_BY_SPAN,
    FALSE_START_MAX_SPAN,
    FALSE_START_MIN_SPAN,
    ISSUE_STATUS_APPROVED_CONFIDENCE_THRESHOLD,
    ISSUE_STATUS_PENDING_CONFIDENCE_THRESHOLD,
    LONG_PAUSE_MID_SENTENCE_CONFIDENCE,
    LONG_PAUSE_THRESHOLD_MS,
    LONG_PAUSE_SENTENCE_BOUNDARY_CONFIDENCE,
    MISSING_TEXT_CONFIDENCE,
    PICKUP_RESTART_CONFIDENCE,
    REPETITION_CONFIDENCE_BY_SPAN,
    REPETITION_MAX_SPAN,
    REPETITION_MIN_SPAN,
    UNCERTAIN_ALIGNMENT_CONFIDENCE,
)
from ..models import Issue
from .text_normalize import normalize_text

TokenLike = str | dict[str, Any]


def _token_text(token: TokenLike) -> str:
    if isinstance(token, dict):
        raw_text = token.get("normalized") or token.get("text") or ""
    else:
        raw_text = token
    return normalize_text(str(raw_text))


def _token_start_ms(token: TokenLike) -> int:
    if isinstance(token, dict):
        value = token.get("start_ms")
        if value is None and token.get("start") is not None:
            try:
                return int(float(token["start"]) * 1000)
            except (TypeError, ValueError):
                return 0
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0
    return 0


def _token_end_ms(token: TokenLike) -> int:
    if isinstance(token, dict):
        value = token.get("end_ms")
        if value is None and token.get("end") is not None:
            try:
                return int(float(token["end"]) * 1000)
            except (TypeError, ValueError):
                return 0
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0
    return 0


def _tokens_to_values(tokens: Sequence[TokenLike]) -> list[str]:
    return [_token_text(token) for token in tokens]


def _issue_context(tokens: Sequence[TokenLike], start_index: int, end_index: int, radius: int = 3) -> tuple[str, str]:
    before = _tokens_to_values(tokens[max(0, start_index - radius) : start_index])
    after = _tokens_to_values(tokens[end_index : min(len(tokens), end_index + radius)])
    return " ".join(token for token in before if token), " ".join(token for token in after if token)


def _make_issue(
    issue_type: str,
    start_ms: int,
    end_ms: int,
    confidence: float,
    expected_text: str,
    spoken_text: str,
    context_before: str = "",
    context_after: str = "",
    note: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "type": issue_type,
        "start_ms": int(start_ms),
        "end_ms": int(end_ms),
        "confidence": float(confidence),
        "expected_text": expected_text,
        "spoken_text": spoken_text,
        "context_before": context_before,
        "context_after": context_after,
    }
    if note is not None:
        issue["note"] = note
    return issue


def _default_issue_status(confidence: float) -> str:
    if confidence >= ISSUE_STATUS_APPROVED_CONFIDENCE_THRESHOLD:
        return "approved"
    return "needs_manual"


def _confidence_for_span(confidence_by_span: dict[int, float], span: int, default: float) -> float:
    return confidence_by_span.get(span, default)


def _raw_token_text(token: TokenLike) -> str:
    if isinstance(token, dict):
        return str(token.get("text") or token.get("normalized") or "")
    return str(token)


def _find_anchor_in_values(values: Sequence[str], anchor: Sequence[str], reference_index: int, window: int) -> int | None:
    if not anchor:
        return None

    anchor_list = list(anchor)
    n = len(anchor_list)
    start = max(0, reference_index - window)
    end = min(len(values) - n, reference_index + window)
    if end < start:
        return None

    for index in range(start, end + 1):
        if values[index : index + n] == anchor_list:
            return index

    return None


def _find_anchor_after_index(values: Sequence[str], anchor: Sequence[str], start_index: int, lookahead: int) -> int | None:
    if not anchor:
        return None

    anchor_list = list(anchor)
    n = len(anchor_list)
    end = min(len(values) - n, start_index + lookahead)
    for index in range(max(0, start_index), end + 1):
        if values[index : index + n] == anchor_list:
            return index

    return None


def _detect_repeated_windows(
    tokens: Sequence[TokenLike],
    *,
    issue_type: str,
    min_span: int,
    max_span: int,
    confidence_by_span: dict[int, float],
    start_offset: int = 0,
) -> list[dict[str, Any]]:
    values = _tokens_to_values(tokens)
    issues: list[dict[str, Any]] = []
    index = 0
    upper_span = min(max_span, len(values) // 2)

    while index <= len(values) - 2 * min_span:
        best_span = None
        for span in range(upper_span, min_span - 1, -1):
            if index + 2 * span > len(values):
                continue
            if values[index : index + span] == values[index + span : index + 2 * span]:
                best_span = span
                break

        if best_span is None:
            index += 1
            continue

        repeat_index = index
        while repeat_index + 2 * best_span <= len(values) and values[repeat_index : repeat_index + best_span] == values[
            repeat_index + best_span : repeat_index + 2 * best_span
        ]:
            first = tokens[repeat_index : repeat_index + best_span]
            second = tokens[repeat_index + best_span : repeat_index + 2 * best_span]
            start_ms = _token_start_ms(first[0]) if first else 0
            if start_ms == 0 and first and not isinstance(first[0], dict):
                start_ms = (repeat_index + start_offset) * 500

            end_ms = _token_end_ms(second[-1]) if second else start_ms
            if end_ms == 0 and second and not isinstance(second[-1], dict):
                end_ms = (repeat_index + 2 * best_span + start_offset) * 500

            context_before, context_after = _issue_context(tokens, repeat_index, repeat_index + 2 * best_span)
            phrase = " ".join(values[repeat_index : repeat_index + best_span])
            confidence = _confidence_for_span(confidence_by_span, best_span, 0.8)

            issues.append(
                _make_issue(
                    issue_type,
                    start_ms,
                    end_ms,
                    confidence,
                    expected_text=phrase,
                    spoken_text=" ".join(values[repeat_index : repeat_index + 2 * best_span]),
                    context_before=context_before,
                    context_after=context_after,
                )
            )

            repeat_index += best_span

        index = repeat_index + best_span

    return issues


def detect_false_starts(tokens: Sequence[TokenLike], token_limit: int = 100) -> list[dict[str, Any]]:
    return _detect_repeated_windows(
        tokens[:token_limit],
        issue_type="false_start",
        min_span=FALSE_START_MIN_SPAN,
        max_span=FALSE_START_MAX_SPAN,
        confidence_by_span=FALSE_START_CONFIDENCE_BY_SPAN,
    )


def detect_repetition(
    tokens: Sequence[TokenLike],
    start_offset: int = 0,
    min_span: int = REPETITION_MIN_SPAN,
    max_span: int = REPETITION_MAX_SPAN,
) -> list[dict[str, Any]]:
    return _detect_repeated_windows(
        tokens[start_offset:],
        issue_type="repetition",
        min_span=min_span,
        max_span=max_span,
        confidence_by_span=REPETITION_CONFIDENCE_BY_SPAN,
        start_offset=start_offset,
    )


def _sentence_boundary_indices(manuscript_tokens: Sequence[TokenLike]) -> set[int]:
    boundary_indices: set[int] = set()
    for index, token in enumerate(manuscript_tokens):
        raw_text = _raw_token_text(token)
        if raw_text.endswith((".", "!", "?", "—")):
            boundary_indices.add(index)
    return boundary_indices


def _manuscript_index_for_spoken_index(
    spoken_index: int,
    alignment: dict[str, Any] | None,
) -> int | None:
    matches = (alignment or {}).get("matches", [])
    for match in matches:
        spoken_start = int(match.get("spoken_start", 0))
        spoken_end = int(match.get("spoken_end", spoken_start))
        if spoken_index < spoken_start or spoken_index >= spoken_end:
            continue

        manuscript_start = int(match.get("manuscript_start", 0))
        manuscript_end = int(match.get("manuscript_end", manuscript_start))
        manuscript_span = max(0, manuscript_end - manuscript_start)

        if manuscript_span == 0:
            return manuscript_start

        offset = spoken_index - spoken_start
        return manuscript_start + min(offset, manuscript_span - 1)

    return None


def _sentence_boundary_indices_for_alignment(manuscript_tokens: Sequence[TokenLike]) -> set[int]:
    boundary_indices: set[int] = set()
    for index, token in enumerate(manuscript_tokens):
        raw_text = _raw_token_text(token)
        if raw_text.endswith((".", "!", "?", "\u2014")):
            boundary_indices.add(index)
    return boundary_indices


def detect_long_pauses(
    spoken_tokens: Sequence[TokenLike],
    threshold_ms: int = LONG_PAUSE_THRESHOLD_MS,
    manuscript_tokens: Sequence[TokenLike] | None = None,
    alignment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    values = _tokens_to_values(spoken_tokens)
    issues: list[dict[str, Any]] = []
    sentence_boundaries = (
        _sentence_boundary_indices_for_alignment(manuscript_tokens or []) if manuscript_tokens and alignment else set()
    )

    for index in range(len(spoken_tokens) - 1):
        current_end = _token_end_ms(spoken_tokens[index])
        next_start = _token_start_ms(spoken_tokens[index + 1])
        pause_ms = next_start - current_end

        if pause_ms < threshold_ms:
            continue

        confidence = LONG_PAUSE_MID_SENTENCE_CONFIDENCE
        note = None

        if manuscript_tokens is not None and alignment is not None:
            manuscript_index = _manuscript_index_for_spoken_index(index, alignment)
            if manuscript_index is not None and manuscript_index in sentence_boundaries:
                confidence = LONG_PAUSE_SENTENCE_BOUNDARY_CONFIDENCE
                note = "Pause follows sentence boundary — may be intentional."

        context_before, context_after = _issue_context(spoken_tokens, index, index + 1)
        issues.append(
            _make_issue(
                "long_pause",
                current_end,
                next_start,
                confidence,
                expected_text="",
                spoken_text=f"{values[index]} {values[index + 1]}".strip(),
                context_before=context_before,
                context_after=context_after,
                note=note,
            )
        )

    return issues


def detect_pickup_restarts(
    manuscript_tokens: Sequence[TokenLike],
    spoken_tokens: Sequence[TokenLike],
    alignment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    # NOTE: This checks for repeated anchor text in the token stream but does not verify
    # the audio content. Two unrelated sentences with the same opening words will be
    # flagged. Review pickup_restart issues with extra scrutiny.
    issues: list[dict[str, Any]] = []
    spoken_values = _tokens_to_values(spoken_tokens)
    manuscript_values = _tokens_to_values(manuscript_tokens)

    if not spoken_values or not manuscript_values:
        return issues

    opcodes = (alignment or {}).get("matches", [])
    for opcode in opcodes:
        if opcode.get("op") != "insert":
            continue

        start = int(opcode.get("spoken_start", 0))
        end = int(opcode.get("spoken_end", 0))
        inserted = spoken_values[start:end]
        if len(inserted) < 2:
            continue

        max_anchor = min(6, len(inserted), len(manuscript_values))
        for anchor_len in range(max_anchor, 1, -1):
            anchor = inserted[:anchor_len]
            manuscript_index = _find_anchor_in_values(manuscript_values, anchor, int(opcode.get("manuscript_start", 0)), 50)
            if manuscript_index is None:
                continue

            repeat_index = _find_anchor_after_index(spoken_values, anchor, end, 150)
            if repeat_index is None:
                continue

            start_ms = _token_start_ms(spoken_tokens[start]) if start < len(spoken_tokens) else 0
            repeat_end_index = repeat_index + anchor_len - 1
            end_ms = _token_end_ms(spoken_tokens[repeat_end_index]) if repeat_end_index < len(spoken_tokens) else start_ms
            context_before, context_after = _issue_context(spoken_tokens, start, repeat_index + anchor_len)
            issues.append(
                _make_issue(
                    "pickup_restart",
                    start_ms,
                    end_ms,
                    PICKUP_RESTART_CONFIDENCE,
                    expected_text=" ".join(anchor),
                    spoken_text=" ".join(spoken_values[start : repeat_index + anchor_len]),
                    context_before=context_before,
                    context_after=context_after,
                    note=f"Repeated anchor matched manuscript index {manuscript_index} and was re-read in spoken text.",
                )
            )
            break

    return issues


def _range_from_spoken_span(spoken_tokens: Sequence[TokenLike], start_index: int, end_index: int) -> tuple[int, int]:
    if start_index < len(spoken_tokens):
        start_ms = _token_end_ms(spoken_tokens[start_index - 1]) if start_index > 0 else _token_start_ms(spoken_tokens[start_index])
    else:
        start_ms = 0

    if end_index < len(spoken_tokens):
        end_ms = _token_start_ms(spoken_tokens[end_index])
    else:
        end_ms = _token_end_ms(spoken_tokens[-1]) if spoken_tokens else 0

    if end_ms < start_ms:
        end_ms = start_ms

    return start_ms, end_ms


def detect_alignment_issues(
    manuscript_tokens: Sequence[TokenLike],
    spoken_tokens: Sequence[TokenLike],
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    matches = alignment.get("matches", [])
    pickup_issues = detect_pickup_restarts(manuscript_tokens, spoken_tokens, alignment)

    for match in matches:
        op = match.get("op")
        manuscript_start = int(match.get("manuscript_start", 0))
        manuscript_end = int(match.get("manuscript_end", manuscript_start))
        spoken_start = int(match.get("spoken_start", 0))
        spoken_end = int(match.get("spoken_end", spoken_start))

        if op == "delete":
            start_ms, end_ms = _range_from_spoken_span(spoken_tokens, spoken_start, spoken_end)
            context_before, context_after = _issue_context(manuscript_tokens, manuscript_start, manuscript_end)
            span_length = manuscript_end - manuscript_start
            # Check flanking matches for confidence boosting
            boosted_confidence = MISSING_TEXT_CONFIDENCE
            if span_length >= 5:
                match_index = matches.index(match)
                prev_is_equal = match_index > 0 and matches[match_index - 1].get("op") == "equal"
                next_is_equal = match_index < len(matches) - 1 and matches[match_index + 1].get("op") == "equal"
                if prev_is_equal and next_is_equal:
                    boosted_confidence = 0.88
            issues.append(
                _make_issue(
                    "missing_text",
                    start_ms,
                    end_ms,
                    boosted_confidence,
                    expected_text=str(match.get("manuscript_text", "")),
                    spoken_text="",
                    context_before=context_before,
                    context_after=context_after,
                )
            )
            continue

        if op == "replace":
            start_ms = _token_start_ms(spoken_tokens[spoken_start]) if spoken_start < len(spoken_tokens) else 0
            end_token_index = spoken_end - 1
            end_ms = _token_end_ms(spoken_tokens[end_token_index]) if spoken_end > spoken_start and end_token_index < len(spoken_tokens) else start_ms
            context_before, context_after = _issue_context(spoken_tokens, spoken_start, spoken_end)
            confidence = 0.88 if (manuscript_end - manuscript_start == 1 and spoken_end - spoken_start == 1) else 0.82
            issues.append(
                _make_issue(
                    "substitution",
                    start_ms,
                    end_ms,
                    confidence,
                    expected_text=str(match.get("manuscript_text", "")),
                    spoken_text=" ".join(_tokens_to_values(spoken_tokens[spoken_start:spoken_end])),
                    context_before=context_before,
                    context_after=context_after,
                )
            )
            continue

        if op == "insert":
            inserted_spoken = " ".join(_tokens_to_values(spoken_tokens[spoken_start:spoken_end]))
            context_before, context_after = _issue_context(spoken_tokens, spoken_start, spoken_end)
            confidence = UNCERTAIN_ALIGNMENT_CONFIDENCE
            issue_type = "uncertain_alignment"

            if spoken_end - spoken_start >= 2:
                if any(
                    issue["start_ms"] <= _token_start_ms(spoken_tokens[spoken_start])
                    and issue["end_ms"] >= _token_end_ms(spoken_tokens[spoken_end - 1])
                    for issue in pickup_issues
                ):
                    issue_type = "pickup_restart"
                    confidence = PICKUP_RESTART_CONFIDENCE

            issues.append(
                _make_issue(
                    issue_type,
                    _token_start_ms(spoken_tokens[spoken_start]) if spoken_start < len(spoken_tokens) else 0,
                    _token_end_ms(spoken_tokens[spoken_end - 1]) if spoken_end - 1 < len(spoken_tokens) and spoken_end > spoken_start else 0,
                    confidence,
                    expected_text=str(match.get("manuscript_text", "")),
                    spoken_text=inserted_spoken,
                    context_before=context_before,
                    context_after=context_after,
                )
            )

    issues.extend(detect_false_starts(spoken_tokens, token_limit=100))
    issues.extend(detect_repetition(spoken_tokens, start_offset=100))
    issues.extend(detect_long_pauses(spoken_tokens, manuscript_tokens=manuscript_tokens, alignment=alignment))

    # Filter repetitions that match manuscript (intentional literary repetition)
    manuscript_values = _tokens_to_values(manuscript_tokens)
    manuscript_text_joined = " ".join(manuscript_values)
    filtered_issues = []
    for issue in issues:
        if issue["type"] == "repetition":
            phrase = issue.get("expected_text", "")
            repeated = f"{phrase} {phrase}"
            if repeated and repeated in manuscript_text_joined:
                issue["type"] = "uncertain_alignment"
                issue["confidence"] = min(issue["confidence"], 0.50)
                issue["note"] = "Repetition matches manuscript text \u2014 may be intentional."
        filtered_issues.append(issue)
    issues = filtered_issues

    return _dedupe_issues(issues)


def _dedupe_issues(issues: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []

    for issue in issues:
        key = (
            issue.get("type"),
            issue.get("start_ms"),
            issue.get("end_ms"),
            issue.get("expected_text", ""),
            issue.get("spoken_text", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    return deduped


def build_issue_records(
    chapter: Any,
    transcript: dict[str, Any],
    manuscript_tokens: Sequence[TokenLike],
    spoken_tokens: Sequence[TokenLike],
    alignment: dict[str, Any],
    audio_signals: list[dict[str, Any]] | None = None,
    vad_segments: list[dict[str, Any]] | None = None,
    prosody_map: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    issues = detect_alignment_issues(manuscript_tokens, spoken_tokens, alignment)
    for issue in issues:
        issue["chapter_id"] = getattr(chapter, "id", None)
        issue["status"] = _default_issue_status(float(issue.get("confidence", 0.0)))
    return issues


def persist_issue_models(session: Session, chapter_id: int, issue_records: Sequence[dict[str, Any]]) -> None:
    for issue_record in issue_records:
        confidence = float(issue_record.get("confidence", 0.0))
        status = str(issue_record.get("status") or _default_issue_status(confidence))
        # Get model_action from the issue record (set by scoring pipeline)
        model_action = issue_record.get("model_action")
        issue = Issue(
            chapter_id=chapter_id,
            type=str(issue_record.get("type", "uncertain_alignment")),
            start_ms=int(issue_record.get("start_ms", 0)),
            end_ms=int(issue_record.get("end_ms", 0)),
            confidence=confidence,
            expected_text=str(issue_record.get("expected_text", "")),
            spoken_text=str(issue_record.get("spoken_text", "")),
            context_before=str(issue_record.get("context_before", "")),
            context_after=str(issue_record.get("context_after", "")),
            note=issue_record.get("note"),
            status=status,
            model_action=model_action,
            audio_features_json=issue_record.get("audio_features_json"),
            audio_signals_json=issue_record.get("audio_signals_json"),
            prosody_features_json=issue_record.get("prosody_features_json"),
            alt_take_cluster_id=issue_record.get("alt_take_cluster_id"),
        )
        session.add(issue)
        # Store the DB id back on the record for downstream use
        session.flush()
        issue_record["id"] = issue.id
    session.commit()
