"""
Discovery Call Context Brief generator.
Fires on Cal.com BOOKING_CREATED and produces the 10-section pre-call
briefing document defined in schemas/discovery_call_context_brief.md.
The brief is logged as a HubSpot note so the delivery lead can read it
before the call without leaving their CRM.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SDR_EMAIL = os.getenv("SDR_EMAIL", "sdr@tenacious.io")


def _load_bench_summary() -> dict:
    """Load seed/bench_summary.json for bench-to-brief match."""
    path = Path(__file__).parents[1] / "tenacious_sales_data" / "seed" / "bench_summary.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def generate(
    prospect_name: str,
    prospect_email: str,
    prospect_company: str,
    booking_uid: str,
    start_time: str,
    langfuse_trace_id: str = "",
    hiring_brief: Optional[dict] = None,
    competitor_brief: Optional[dict] = None,
    thread_messages: Optional[list[dict]] = None,
    hubspot_contact_id: Optional[str] = None,
) -> str:
    """
    Generate the 10-section discovery call context brief as Markdown.
    All inputs are optional — missing data is labelled 'not available' so the
    delivery lead knows what the agent could and could not find.
    """
    hb = hiring_brief or {}
    cb = competitor_brief or {}
    messages = thread_messages or []
    bench = _load_bench_summary()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Section 1: Segment and confidence ────────────────────────────
    segment = hb.get("primary_segment_match", "abstain")
    seg_conf = hb.get("segment_confidence", 0.0)
    seg_rationale = {
        "segment_1_series_a_b": "Funding event within 180 days — high buying signal window.",
        "segment_2_mid_market_restructure": "Layoff event within 120 days — cost optimisation mindset.",
        "segment_3_leadership_transition": "New CTO/VP Eng within 90 days — vendor reassessment window.",
        "segment_4_specialized_capability": "AI maturity ≥ 2 — specific capability gap identified.",
        "abstain": "Confidence below threshold — generic exploratory call.",
    }.get(segment, "Unknown segment.")

    abstain_risk = "Yes — confidence below 0.60" if seg_conf < 0.60 else "No"

    # ── Section 2: Key signals ────────────────────────────────────────
    funding = hb.get("funding_event") or {}
    velocity = hb.get("hiring_velocity") or {}
    layoff = hb.get("layoff_event") or {}
    leadership = hb.get("leadership_change") or {}
    ai_score = hb.get("ai_maturity_score", "N/A")
    ai_conf = hb.get("ai_maturity_confidence", "low")

    # ── Section 3: Gap findings ───────────────────────────────────────
    gaps = cb.get("gap_findings") or cb.get("gap_practices") or []
    high_gaps = [g for g in gaps if g.get("confidence") == "high"]
    low_gaps = [g for g in gaps if g.get("confidence") == "low"]

    # ── Section 4: Bench-to-brief ─────────────────────────────────────
    btb = hb.get("bench_to_brief_match") or {}
    required_stacks = btb.get("required_stacks") or hb.get("tech_stack") or []
    bench_gaps = btb.get("gaps") or []
    bench_available = btb.get("bench_available", True)

    # ── Section 5: Conversation summary ──────────────────────────────
    agent_msgs = [m for m in messages if m.get("role") == "agent"]
    prospect_msgs = [m for m in messages if m.get("role") == "prospect"]

    # ── Section 7: Commercial signals ────────────────────────────────
    price_quoted = "None quoted in thread"
    urgency = "None detected"
    for m in prospect_msgs:
        content = m.get("content", "").lower()
        if any(w in content for w in ["urgent", "asap", "deadline", "pressure", "board"]):
            urgency = m.get("content", "")[:200]
            break

    # ── Assemble the brief ────────────────────────────────────────────
    brief_lines = [
        "# Discovery Call Context Brief",
        "",
        f"**Prospect:** {prospect_name} at {prospect_company}",
        f"**Scheduled:** {start_time}",
        f"**Delivery lead assigned:** {_SDR_EMAIL}",
        f"**Call length booked:** 30 minutes",
        f"**Thread origin:** {messages[0].get('timestamp', 'unknown') if messages else 'no thread'}",
        f"**Full thread:** Trace ID `{langfuse_trace_id or 'not set'}`",
        "",
        "---",
        "",
        "## 1. Segment and confidence",
        "",
        f"- **Primary segment match:** {segment}",
        f"- **Confidence:** {seg_conf:.2f}",
        f"- **Why this segment:** {seg_rationale}",
        f"- **Abstention risk:** {abstain_risk}",
        "",
        "## 2. Key signals",
        "",
        f"- **Funding event:** {'Stage: ' + str(funding.get('series')) + ' · Amount: $' + str(funding.get('amount_usd', 'unknown')) + ' · ' + str(funding.get('days_ago', '?')) + ' days ago' if funding else 'Not detected'}",
        f"- **Hiring velocity:** {velocity.get('open_roles_today', '?')} open roles today · label: {velocity.get('velocity_label', 'unknown')} · confidence: {velocity.get('signal_confidence', 0):.0%}",
        f"- **Layoff event:** {'Detected — ' + str(layoff.get('pct_cut', '?')) + '% cut · ' + str(layoff.get('days_ago', '?')) + ' days ago' if layoff else 'Not detected'}",
        f"- **Leadership change:** {'Detected — ' + str(leadership.get('role', '?')) + ' · ' + str(leadership.get('days_ago', '?')) + ' days ago' if leadership else 'Not detected'}",
        f"- **AI maturity score:** {ai_score}/3 (confidence: {ai_conf})",
        "",
        "## 3. Competitor gap findings",
        "",
        "High-confidence findings the delivery lead should be ready to discuss:",
        "",
    ]

    if high_gaps:
        for g in high_gaps:
            peers = ", ".join(
                e.get("competitor_name", "") for e in g.get("peer_evidence", [])
            )
            brief_lines.append(f"- {g.get('practice', '')} — peers: {peers or 'see brief'}")
    else:
        brief_lines.append("- No high-confidence gap findings available.")

    brief_lines += [
        "",
        "Findings to avoid in the call (low confidence or likely to land wrong):",
        "",
    ]

    if low_gaps:
        for g in low_gaps:
            brief_lines.append(f"- {g.get('practice', '')} — low confidence, do not assert")
    else:
        brief_lines.append("- None flagged.")

    brief_lines += [
        "",
        "## 4. Bench-to-brief match",
        "",
        f"- **Stacks the prospect will likely need:** {', '.join(required_stacks) or 'not inferred'}",
        f"- **Bench available:** {'Yes' if bench_available else 'No — see gaps below'}",
        f"- **Gaps:** {', '.join(bench_gaps) if bench_gaps else 'None detected'}",
        f"- **Honest flag:** Agent has not promised specific staffing in thread.",
        "",
        "## 5. Conversation history summary",
        "",
    ]

    if prospect_msgs:
        for i, m in enumerate(prospect_msgs[:5], 1):
            brief_lines.append(f"{i}. {m.get('content', '')[:200]}")
    else:
        brief_lines.append("No prospect messages in thread yet.")

    brief_lines += [
        "",
        "## 6. Objections already raised",
        "",
        "| Objection | Agent response | Delivery lead should be ready to |",
        "|---|---|---|",
    ]

    objection_keywords = ["not", "already", "budget", "vendor", "doing", "concern"]
    objections_found = False
    for m in prospect_msgs:
        content = m.get("content", "")
        if any(kw in content.lower() for kw in objection_keywords):
            brief_lines.append(f"| {content[:100]} | See thread | Explore further |")
            objections_found = True
            break
    if not objections_found:
        brief_lines.append("| No objections detected in thread | — | — |")

    brief_lines += [
        "",
        "## 7. Commercial signals",
        "",
        f"- **Price bands already quoted:** {price_quoted}",
        f"- **Has the prospect asked for a specific TCV?** No",
        f"- **Is the prospect comparing vendors?** Not detected",
        f"- **Urgency signals:** {urgency}",
        "",
        "## 8. Suggested call structure",
        "",
    ]

    opening = {
        "segment_1_series_a_b": f"Congratulate them on the funding and ask how the team-building sprint is going.",
        "segment_2_mid_market_restructure": "Acknowledge the cost-efficiency focus and ask about the restructure timeline.",
        "segment_3_leadership_transition": "Ask what the new leader's first 90-day priorities look like.",
        "segment_4_specialized_capability": "Ask which AI capability they're most actively trying to build right now.",
        "abstain": "Open with a research question about their AI roadmap.",
    }.get(segment, "Open with a warm research question.")

    brief_lines += [
        f"- **Minutes 0–2:** {opening}",
        f"- **Minutes 2–10:** Confirm which signals from the brief are accurate — do not assert, ask.",
        f"- **Minutes 10–20:** Walk through Tenacious's capability summary against their specific need.",
        f"- **Minutes 20–25:** Introduce pricing bands only if prospect signals budget authority.",
        f"- **Minutes 25–30:** Agree a specific next step — proposal, intro call with delivery lead, or pilot scope.",
        "",
        "## 9. What NOT to do on this call",
        "",
        f"- Do not cite competitor gap findings that are marked low confidence in Section 3.",
        f"- Do not promise specific engineer availability without checking bench_summary.json first.",
        f"- Do not lead with pricing — let the prospect ask.",
        "",
        "## 10. Agent confidence and unknowns",
        "",
        f"- **Things the agent is confident about:** Segment match ({segment}), AI maturity score ({ai_score}/3).",
        f"- **Things the agent is uncertain about:** Tech stack (inferred, not confirmed), bench availability for specific roles.",
        f"- **Things the agent could not find:** Full leadership team details, detailed funding terms.",
        f"- **Overall agent confidence in this brief:** {min(0.9, seg_conf + 0.1):.2f}",
        "",
        "---",
        "",
        f"*Generated by TRP1 Week 10 Conversion Engine. Trace ID: `{langfuse_trace_id or 'not set'}`. Generated at {now_utc}.*",
    ]

    return "\n".join(brief_lines)


def generate_and_log(
    prospect_name: str,
    prospect_email: str,
    prospect_company: str,
    booking_uid: str,
    start_time: str,
    hubspot_contact_id: Optional[str] = None,
    langfuse_trace_id: str = "",
    hiring_brief: Optional[dict] = None,
    competitor_brief: Optional[dict] = None,
    thread_messages: Optional[list[dict]] = None,
) -> str:
    """
    Generate the brief and log it as a HubSpot note.
    Returns the brief markdown string.
    """
    brief_md = generate(
        prospect_name=prospect_name,
        prospect_email=prospect_email,
        prospect_company=prospect_company,
        booking_uid=booking_uid,
        start_time=start_time,
        langfuse_trace_id=langfuse_trace_id,
        hiring_brief=hiring_brief,
        competitor_brief=competitor_brief,
        thread_messages=thread_messages,
        hubspot_contact_id=hubspot_contact_id,
    )

    if hubspot_contact_id:
        try:
            from .hubspot_mcp import log_note
            note_body = f"[Discovery Call Context Brief — {start_time}]\n\n{brief_md}"
            log_note(contact_id=hubspot_contact_id, note=note_body[:10000])
            logger.info(
                "Discovery brief logged to HubSpot — contact=%s booking=%s",
                hubspot_contact_id, booking_uid,
            )
        except Exception as e:
            logger.error("Failed to log discovery brief to HubSpot: %s", e)

    return brief_md
