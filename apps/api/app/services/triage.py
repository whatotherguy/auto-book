"""LLM-powered issue triage for reducing false positives.

Sends detected issues with their manuscript context to an LLM to classify
whether each issue is a genuine narration error or a likely false positive.
Completely optional — requires an API key and fails gracefully.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """You are an expert audiobook production engineer reviewing detected narration issues.

For each issue, you will see:
- The issue type and confidence score
- The expected text (from the manuscript) and spoken text (from the transcript)
- Context before and after the issue

Your job is to classify each issue as:
- "keep" — This is a genuine narration error that should be reviewed by the engineer
- "dismiss" — This is likely a false positive (acceptable narrator ad-lib, alignment artifact, intentional variation, etc.)
- "uncertain" — Not enough context to decide; keep for manual review

Respond with a JSON array of objects, one per issue, each with:
- "index": the issue index (0-based)
- "verdict": "keep", "dismiss", or "uncertain"
- "reason": a short explanation (1 sentence)

Be conservative: when in doubt, use "keep" or "uncertain". Never dismiss missing_text issues with 5+ words or high-confidence repetitions."""


def is_triage_available() -> bool:
    """Check if any LLM provider is configured for triage."""
    from ..config import settings
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return True
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return True
    return False


def _build_triage_prompt(issues: Sequence[dict[str, Any]], manuscript_text: str) -> str:
    """Build the user prompt containing issues to triage."""
    lines = [f"Manuscript excerpt (first 2000 chars):\n{manuscript_text[:2000]}\n\n---\n\nIssues to triage:\n"]

    for index, issue in enumerate(issues):
        lines.append(f"Issue {index}:")
        lines.append(f"  Type: {issue.get('type', 'unknown')}")
        lines.append(f"  Confidence: {issue.get('confidence', 0):.2f}")
        lines.append(f"  Expected: \"{issue.get('expected_text', '')}\"")
        lines.append(f"  Spoken: \"{issue.get('spoken_text', '')}\"")
        lines.append(f"  Before: \"{issue.get('context_before', '')}\"")
        lines.append(f"  After: \"{issue.get('context_after', '')}\"")
        lines.append("")

    lines.append(f"\nClassify all {len(issues)} issues. Return JSON only.")
    return "\n".join(lines)


def _call_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI GPT-4o for triage."""
    import httpx

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=120.0,
    )

    if response.status_code != 200:
        raise RuntimeError(f"OpenAI API returned {response.status_code}: {response.text[:500]}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, api_key: str) -> str:
    """Call Anthropic Claude for triage."""
    import httpx

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "system": TRIAGE_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=120.0,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Anthropic API returned {response.status_code}: {response.text[:500]}")

    data = response.json()
    # Claude returns content as a list of blocks
    content_blocks = data.get("content", [])
    return "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")


def _parse_triage_response(raw_response: str, issue_count: int) -> list[dict[str, str]]:
    """Parse the LLM's JSON response into verdict records."""
    try:
        parsed = json.loads(raw_response)
        # Handle both {"issues": [...]} and bare [...]
        if isinstance(parsed, dict):
            verdicts = parsed.get("issues") or parsed.get("results") or parsed.get("verdicts") or []
        elif isinstance(parsed, list):
            verdicts = parsed
        else:
            return []

        result = []
        for v in verdicts:
            if not isinstance(v, dict):
                continue
            result.append({
                "index": int(v.get("index", -1)),
                "verdict": str(v.get("verdict", "uncertain")),
                "reason": str(v.get("reason", "")),
            })
        return result
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse triage response: %s", exc)
        return []


def triage_issues(
    issues: Sequence[dict[str, Any]],
    manuscript_text: str,
) -> list[dict[str, Any]]:
    """Run LLM triage on detected issues. Returns the issues list with triage annotations.

    Each issue gets:
    - "triage_verdict": "keep", "dismiss", or "uncertain"
    - "triage_reason": explanation from the LLM

    On failure, all issues are returned unchanged (no triage annotations).
    Issues are processed in batches of 30 to stay within context limits.
    """
    from ..config import settings

    if not is_triage_available():
        logger.info("LLM triage not available (no API key configured)")
        return list(issues)

    BATCH_SIZE = 30
    all_verdicts: dict[int, dict[str, str]] = {}

    try:
        for batch_start in range(0, len(issues), BATCH_SIZE):
            batch = list(issues[batch_start:batch_start + BATCH_SIZE])
            prompt = _build_triage_prompt(batch, manuscript_text)

            if settings.llm_provider == "openai":
                raw = _call_openai(prompt, settings.openai_api_key)
            elif settings.llm_provider == "anthropic":
                raw = _call_anthropic(prompt, settings.anthropic_api_key)
            else:
                break

            verdicts = _parse_triage_response(raw, len(batch))
            for v in verdicts:
                global_index = batch_start + v["index"]
                if 0 <= global_index < len(issues):
                    all_verdicts[global_index] = v
    except Exception as exc:
        logger.warning("LLM triage failed (continuing without triage): %s", exc)
        return list(issues)

    # Annotate issues with triage results
    result = []
    dismissed_count = 0
    for index, issue in enumerate(issues):
        issue = dict(issue)  # copy
        if index in all_verdicts:
            verdict = all_verdicts[index]
            issue["triage_verdict"] = verdict["verdict"]
            issue["triage_reason"] = verdict["reason"]
            if verdict["verdict"] == "dismiss":
                dismissed_count += 1
        else:
            issue["triage_verdict"] = "uncertain"
            issue["triage_reason"] = "Not evaluated by LLM"
        result.append(issue)

    logger.info("LLM triage: %d/%d issues dismissed as likely false positives", dismissed_count, len(issues))
    return result
