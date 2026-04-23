"""
FastAPI application — entry point for the Conversion Engine.
Routes: email reply webhook, SMS inbound webhook, Cal.com booking webhook, health check.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .enrichment.pipeline import run as enrich
from .icp_classifier import classify
from .thread_store import store
from .email_handler import send as send_email, EmailMessage, handle_reply_webhook, register_handler
from .sms_handler import handle_inbound, send as send_sms, build_scheduling_sms
from .hubspot_mcp import upsert_contact, log_note, update_lead_status
from .cal_booking import get_booking_link, handle_booking_webhook

logger = logging.getLogger(__name__)

app = FastAPI(title="The Conversion Engine", version="0.1.0")

_SDR_EMAIL = os.getenv("SDR_EMAIL", "sdr@tenacious.io")


# ── Health ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ── Email reply webhook ─────────────────────────────────────────────────
@app.post("/webhooks/email")
async def email_webhook(request: Request):
    payload = await request.json()
    event = handle_reply_webhook(payload)

    from_email = event.get("from", "")
    body = event.get("text", "")

    # Look up thread by email (simplified: use email as both company+contact id)
    contact_id = from_email
    company_id = from_email.split("@")[-1].split(".")[0]

    thread = store.get_or_create(
        company_id=company_id,
        contact_id=contact_id,
        contact_email=from_email,
    )

    if thread.opted_out:
        return JSONResponse({"status": "opted_out"})

    thread.add(role="prospect", content=body, channel="email")
    store.save()

    # Log to HubSpot
    log_note(contact_id=from_email, note=f"Email reply received: {body[:500]}")

    # Provide Cal.com booking link in reply
    cal_link = get_booking_link(prefill_email=from_email)
    reply_body = (
        f"Thanks for your reply! To book a 30-minute discovery call, "
        f"use this link: {cal_link}"
    )
    send_email(EmailMessage(
        to=from_email,
        subject="Re: " + event.get("subject", ""),
        html=f"<p>{reply_body}</p>",
    ))
    thread.add(role="agent", content=reply_body, channel="email")
    store.save()

    return JSONResponse({"status": "ok"})


# ── SMS inbound webhook ─────────────────────────────────────────────────
@app.post("/webhooks/cal")
async def cal_webhook(request: Request):
    payload = await request.json()
    try:
        event = handle_booking_webhook(payload)
        return JSONResponse({"status": "ok", "event": event})
    except ValueError as e:
        logger.error("Cal.com webhook parse error: %s", e)
        raise HTTPException(status_code=422, detail=str(e))


# ── SMS inbound webhook ─────────────────────────────────────────────────
@app.post("/webhooks/sms")
async def sms_webhook(request: Request):
    payload = await request.json()
    event = handle_inbound(payload)

    from_phone = event.get("from", "")
    company_id = "sms-" + from_phone[-6:]  # last 6 digits as company proxy
    contact_id = from_phone

    if event["event_type"] == "sms_stop":
        store.mark_opted_out(company_id, contact_id)
        send_sms(to=from_phone, message=event["reply"])
        return JSONResponse({"status": "opted_out"})

    thread = store.get_or_create(
        company_id=company_id,
        contact_id=contact_id,
        contact_phone=from_phone,
    )
    if thread.opted_out:
        return JSONResponse({"status": "opted_out"})

    thread.add(role="prospect", content=event["text"], channel="sms")

    if event["event_type"] == "sms_help":
        send_sms(to=from_phone, message=event["reply"])
        thread.add(role="agent", content=event["reply"], channel="sms")
    else:
        # Channel hierarchy: SMS is secondary — only send scheduling link if there
        # is an existing email exchange in this thread (warm lead gate).
        has_prior_email = any(m.channel == "email" for m in thread.messages)
        if not has_prior_email:
            logger.info(
                "SMS from %s — no prior email exchange; suppressing scheduling link",
                from_phone,
            )
            ack = "Thanks for reaching out! We'll follow up by email shortly."
            send_sms(to=from_phone, message=ack)
            thread.add(role="agent", content=ack, channel="sms")
        else:
            cal_link = get_booking_link()
            reply = build_scheduling_sms(
                prospect_name="there",
                cal_link=cal_link,
            )
            send_sms(to=from_phone, message=reply)
            thread.add(role="agent", content=reply, channel="sms")

    store.save()
    return JSONResponse({"status": "ok"})


# ── Outreach trigger (internal use) ────────────────────────────────────
class OutreachRequest(BaseModel):
    company_name: str
    prospect_email: str
    prospect_name: str = "there"
    careers_url: str = ""
    press_release_url: str = ""


@app.post("/outreach/trigger")
async def trigger_outreach(req: OutreachRequest):
    """
    Trigger the full enrichment + classify + email pipeline for one prospect.
    """
    out_dir = f"data/briefs/{req.company_name.replace(' ', '_')}"
    brief, hiring_brief, gap_brief = enrich(
        company_name=req.company_name,
        careers_url=req.careers_url or None,
        press_release_url=req.press_release_url or None,
        output_dir=out_dir,
    )

    classification = classify(hiring_brief)

    # Write to HubSpot
    contact_id = upsert_contact(
        email=req.prospect_email,
        company_name=req.company_name,
        crunchbase_id=brief.crunchbase_id,
        segment=classification.segment_label,
        ai_maturity_score=hiring_brief.ai_maturity_score,
        enrichment_timestamp=datetime.now(timezone.utc),
    )

    if classification.abstain:
        return JSONResponse({
            "status": "abstained",
            "reason": "confidence below threshold",
            "segment": classification.segment_label,
        })

    # Build signal summary for email
    signal_parts = []
    if hiring_brief.funding_event and hiring_brief.funding_event.days_ago:
        signal_parts.append(
            f"you closed a {hiring_brief.funding_event.series or 'funding round'} "
            f"{hiring_brief.funding_event.days_ago} days ago"
        )
    if not hiring_brief.weak_signal:
        signal_parts.append(
            f"you have {hiring_brief.open_role_count} open engineering roles"
        )

    signal_summary = (
        f"I noticed that {', and '.join(signal_parts)}." if signal_parts
        else f"I came across {req.company_name} in our research."
    )

    gap_summary = ""
    if gap_brief.gap_practices:
        practice = gap_brief.gap_practices[0].practice
        gap_summary = (
            f"Companies in your sector at a similar stage are already doing: {practice}. "
            f"Worth a quick conversation about whether that gap matters to you."
        )

    from .email_handler import build_cold_email, send as send_email
    msg = build_cold_email(
        prospect_name=req.prospect_name,
        company_name=req.company_name,
        hiring_signal_summary=signal_summary,
        competitor_gap_summary=gap_summary,
        pitch_language=classification.pitch_language,
    )
    msg.to = req.prospect_email
    send_email(msg)

    thread = store.get_or_create(
        company_id=brief.crunchbase_id,
        contact_id=req.prospect_email,
        contact_email=req.prospect_email,
        segment=classification.segment_label,
    )
    thread.add(role="agent", content=msg.html, channel="email")
    store.save()

    return JSONResponse({
        "status": "sent",
        "segment": classification.segment_label,
        "confidence": classification.confidence,
        "crunchbase_id": brief.crunchbase_id,
        "hubspot_contact_id": contact_id,
        "ai_maturity_score": hiring_brief.ai_maturity_score,
        "weak_signal": hiring_brief.weak_signal,
    })
