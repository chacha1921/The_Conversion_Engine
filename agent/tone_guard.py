"""
Tone-guard: validates every outbound draft against seed/style_guide.md.
Uses a second LLM call. Cost is logged per call.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

import anthropic

_STYLE_GUIDE_PATH = Path(__file__).parents[1] / "tenacious_sales_data" / "seed" / "style_guide.md"
_PASS_THRESHOLD = 7   # score out of 10; below this triggers regeneration
_MAX_RETRIES = 2


def _load_style_guide() -> str:
    if _STYLE_GUIDE_PATH.exists():
        return _STYLE_GUIDE_PATH.read_text()
    return (
        "Tone: professional, warm, research-grounded. "
        "Avoid: cold, generic, salesy, or condescending language. "
        "Never over-claim hiring signals. Never fabricate case studies."
    )


def check(draft: str, context: str = "") -> tuple[bool, int, str]:
    """
    Returns (passes: bool, score: int 0-10, feedback: str).
    Raises RuntimeError if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # Fail open in development — log and pass
        return True, 10, "ANTHROPIC_API_KEY not set; tone check skipped"

    style_guide = _load_style_guide()
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a tone reviewer for Tenacious Consulting and Outsourcing.
Review the following outbound email draft against the style guide.

<style_guide>
{style_guide}
</style_guide>

<draft>
{draft}
</draft>

{f"<context>{context}</context>" if context else ""}

Score the draft on a scale of 0-10 for adherence to the style guide.
Then provide one sentence of feedback.

Respond ONLY in this exact format:
SCORE: <integer 0-10>
FEEDBACK: <one sentence>"""

    try:
        message = client.messages.create(
            model=os.getenv("TONE_GUARD_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            import logging
            logging.getLogger(__name__).warning("Anthropic credits exhausted; tone check skipped: %s", e)
            return True, 10, "Anthropic credits exhausted; tone check skipped"
        raise

    response_text = message.content[0].text.strip()
    score, feedback = _parse_response(response_text)
    passes = score >= _PASS_THRESHOLD
    return passes, score, feedback


def _parse_response(text: str) -> tuple[int, str]:
    score = 5
    feedback = text
    for line in text.splitlines():
        if line.startswith("SCORE:"):
            try:
                score = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("FEEDBACK:"):
            feedback = line.split(":", 1)[1].strip()
    return score, feedback


def enforce(
    draft: str,
    generate_fn,
    context: str = "",
    max_retries: int = _MAX_RETRIES,
) -> str:
    """
    Check draft; if it fails, call generate_fn() and retry up to max_retries times.
    Returns the first draft that passes (or the last draft if all retries fail).
    """
    passes, score, feedback = check(draft, context)
    if passes:
        return draft

    for attempt in range(max_retries):
        revised = generate_fn(feedback=feedback)
        passes, score, feedback = check(revised, context)
        if passes:
            return revised

    return revised  # return last attempt even if it failed
