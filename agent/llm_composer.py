"""
LLM email composer — OpenRouter (dev tier) with seed RAG.
Injects hiring_signal_brief + competitor_gap_brief + seed materials
into context so the LLM writes a signal-grounded, style-compliant email.
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parents[1] / "tenacious_sales_data" / "seed"
_DEV_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-thinking")


def _read(relative: str) -> str:
    try:
        return (_SEED_DIR / relative).read_text()
    except Exception:
        return ""


def _bench_summary_text() -> str:
    try:
        data = json.loads((_SEED_DIR / "bench_summary.json").read_text())
        stacks = data.get("stacks", {})
        lines = [f"  {k}: {v.get('available_engineers', 0)} available" for k, v in stacks.items()]
        lines.append(f"  Total on bench: {data.get('total_engineers_on_bench', '?')}")
        return "\n".join(lines)
    except Exception:
        return "  bench_summary unavailable"


def compose_cold_email(
    prospect_name: str,
    company_name: str,
    segment: str,
    pitch_language: str,
    hiring_brief: dict,
    gap_brief: dict,
    feedback: str = "",
) -> tuple[str, str, dict]:
    """
    Compose a signal-grounded cold email via LLM.
    Returns (subject, plain_text_body, usage_dict).
    Falls back to a template if the LLM call fails.
    """
    style_guide = _read("style_guide.md")[:2500]
    cold_template = _read("email_sequences/cold.md")[:2000]
    pricing = _read("pricing_sheet.md")[:1200]
    bench = _bench_summary_text()

    open_roles = hiring_brief.get("open_role_count", 0)
    ai_score = hiring_brief.get("ai_maturity_score", 0)

    signal_lines: list[str] = []
    fe = hiring_brief.get("funding_event") or {}
    if fe and fe.get("days_ago"):
        signal_lines.append(
            f"Closed {fe.get('series', 'a funding round')} "
            f"${fe.get('amount_usd', '?')} {fe['days_ago']} days ago"
        )
    le = hiring_brief.get("layoff_event") or {}
    if le and le.get("days_ago"):
        signal_lines.append(
            f"Laid off ~{le.get('pct_cut', '?')}% of staff {le['days_ago']} days ago"
        )
    lc = hiring_brief.get("leadership_change") or {}
    if lc and lc.get("days_ago"):
        signal_lines.append(
            f"New {lc.get('role', 'tech leader')} joined {lc['days_ago']} days ago"
        )
    signal_lines.append(f"{open_roles} open engineering roles detected (AI maturity: {ai_score}/3)")

    gaps = gap_brief.get("gap_findings") or gap_brief.get("gap_practices") or []
    gap_text = ""
    if gaps:
        g = gaps[0]
        gap_text = g.get("practice", "") if isinstance(g, dict) else str(g)

    _SEGMENT_LABELS = {
        "segment_1_series_a_b": "recently funded Series A/B",
        "segment_2_mid_market_restructure": "mid-market restructuring",
        "segment_3_leadership_transition": "engineering leadership transition",
        "segment_4_specialized_capability": "specialized capability gap",
        "abstain": "exploratory (low confidence)",
    }
    segment_label = _SEGMENT_LABELS.get(segment, segment)

    system = f"""You are a B2B outreach writer for Tenacious Consulting and Outsourcing.
Write a single cold email (Email 1 of 3) that is signal-grounded and follows the style guide exactly.

STYLE GUIDE:
{style_guide}

EMAIL TEMPLATE STRUCTURE (follow structure, do not copy verbatim):
{cold_template}

BENCH AVAILABILITY (never commit beyond these numbers):
{bench}

PRICING (quote bands only; route custom requests to humans):
{pricing}

HARD RULES:
- Body max 120 words
- First name only in salutation; never "Hi there" or "Dear"
- Subject line first word must be one of: Request / Follow-up / Context / Note / Question
- Sentence 1: one verifiable fact from signals. No fabrication.
- No service menus. One specific Tenacious capability only.
- If open_roles < 5, do NOT use words like "scaling rapidly" or "aggressive hiring"
- Never promise capacity beyond bench numbers above
- End with one clear call to action (30-minute call)

OUTPUT FORMAT — return exactly two labelled lines then the body:
SUBJECT: <subject line>
BODY:
<email body, plain text, no HTML>"""

    user = f"""Prospect: {prospect_name} at {company_name}
Segment: {segment_label}
Pitch language: {pitch_language}

Signals:
{chr(10).join(f'- {s}' for s in signal_lines)}

Top competitor gap: {gap_text or 'not identified — write exploratory opener'}
{f"REVISION NEEDED — previous draft rejected. Feedback: {feedback}. Rewrite fixing this." if feedback else ""}"""

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set — using template fallback")
        return _template_fallback(prospect_name, company_name, pitch_language)

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=_DEV_MODEL,
            max_tokens=450,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_headers={
                "HTTP-Referer": "https://github.com/chalielijalem/conversion-engine",
                "X-Title": "TRP1-Week10-Conversion-Engine",
            },
        )
        latency = round(time.time() - t0, 2)
        raw = resp.choices[0].message.content or ""
        usage = {
            "model": _DEV_MODEL,
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            "latency_seconds": latency,
        }
        subject, body = _parse_output(raw, company_name)
        logger.info("LLM email composed — model=%s tokens=%s latency=%ss",
                    _DEV_MODEL, usage.get("completion_tokens"), latency)
        return subject, body, usage
    except Exception as e:
        logger.error("LLM composition failed: %s", e)
        subject, body, _ = _template_fallback(prospect_name, company_name, pitch_language)
        return subject, body, {
            "model": _DEV_MODEL,
            "latency_seconds": round(time.time() - t0, 2),
            "error": str(e),
        }


def _parse_output(raw: str, company_name: str) -> tuple[str, str]:
    subject = f"Context: {company_name}'s engineering growth"
    body = raw
    lines = raw.strip().splitlines()
    body_lines: list[str] = []
    in_body = False
    for line in lines:
        if line.startswith("SUBJECT:"):
            subject = line[len("SUBJECT:"):].strip()
        elif line.startswith("BODY:"):
            in_body = True
            rest = line[len("BODY:"):].strip()
            if rest:
                body_lines.append(rest)
        elif in_body:
            body_lines.append(line)
    if body_lines:
        body = "\n".join(body_lines).strip()
    return subject, body


def _template_fallback(
    prospect_name: str,
    company_name: str,
    pitch_language: str,
) -> tuple[str, str, dict]:
    subject = f"Context: {company_name}'s engineering growth"
    body = (
        f"Hi {prospect_name},\n\n"
        f"{pitch_language}\n\n"
        f"Worth a 30-minute conversation?\n\n"
        f"Best,\nTenacious Consulting"
    )
    return subject, body, {"model": "template_fallback", "prompt_tokens": 0, "completion_tokens": 0}
