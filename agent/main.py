"""
FastAPI application — entry point for the Conversion Engine.
Routes: email reply webhook, SMS inbound webhook, Cal.com booking webhook, health check.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

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
from .llm_composer import compose_cold_email
from .tone_guard import enforce as tone_enforce

logger = logging.getLogger(__name__)

app = FastAPI(title="The Conversion Engine", version="0.1.0")

# ── Langfuse client (optional — graceful no-op if keys missing) ─────────
def _make_langfuse():
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=pk,
            secret_key=sk,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as e:
        logger.warning("Langfuse init failed: %s", e)
        return None

_langfuse = _make_langfuse()

_SEGMENT_MAP: dict[str, str] = {
    "recently_funded_series_a_b": "segment_1_series_a_b",
    "mid_market_restructuring": "segment_2_mid_market_restructure",
    "engineering_leadership_transition": "segment_3_leadership_transition",
    "specialized_capability_gap": "segment_4_specialized_capability",
    "unknown": "abstain",
}


def _segment_to_schema_key(segment_label: str) -> str:
    return _SEGMENT_MAP.get(segment_label, "abstain")

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
    Full enrichment + classify + LLM compose + tone-guard + send pipeline.
    Every step is traced to Langfuse.
    """
    trace_id = str(uuid.uuid4())
    trace = None
    if _langfuse:
        trace = _langfuse.trace(
            name="outreach_trigger",
            id=trace_id,
            user_id=req.prospect_email,
            input={"company": req.company_name, "email": req.prospect_email},
            metadata={"careers_url": req.careers_url},
        )

    # ── Enrichment ────────────────────────────────────────────────────
    out_dir = f"data/briefs/{req.company_name.replace(' ', '_')}"
    _span_enrich = trace.span(name="enrichment", input={"company": req.company_name}) if trace else None
    brief, hiring_brief, gap_brief = enrich(
        company_name=req.company_name,
        careers_url=req.careers_url or None,
        press_release_url=req.press_release_url or None,
        output_dir=out_dir,
    )
    if _span_enrich:
        _span_enrich.end(output={
            "ai_maturity": hiring_brief.ai_maturity_score,
            "open_roles": hiring_brief.open_role_count,
            "weak_signal": hiring_brief.weak_signal,
        })

    # ── Classification ────────────────────────────────────────────────
    _span_classify = trace.span(name="classify") if trace else None
    classification = classify(hiring_brief)
    hiring_brief.primary_segment_match = _segment_to_schema_key(classification.segment_label)
    hiring_brief.segment_confidence = classification.confidence
    with open(os.path.join(out_dir, "hiring_signal_brief.json"), "w") as _f:
        _f.write(hiring_brief.model_dump_json(indent=2))
    if _span_classify:
        _span_classify.end(output={
            "segment": classification.segment_label,
            "confidence": classification.confidence,
            "abstain": classification.abstain,
        })

    # ── HubSpot upsert ────────────────────────────────────────────────
    contact_id = upsert_contact(
        email=req.prospect_email,
        company_name=req.company_name,
        crunchbase_id=brief.crunchbase_id,
        segment=classification.segment_label,
        ai_maturity_score=hiring_brief.ai_maturity_score,
        enrichment_timestamp=datetime.now(timezone.utc),
    )

    if classification.abstain:
        if trace:
            trace.update(output={"status": "abstained"})
            _langfuse.flush()
        return JSONResponse({
            "status": "abstained",
            "reason": "confidence below threshold",
            "segment": classification.segment_label,
            "trace_id": trace_id,
        })

    # ── LLM email composition ─────────────────────────────────────────
    hiring_dict = hiring_brief.model_dump()
    gap_dict = gap_brief.model_dump()

    subject, body, usage = compose_cold_email(
        prospect_name=req.prospect_name,
        company_name=req.company_name,
        segment=hiring_brief.primary_segment_match,
        pitch_language=classification.pitch_language,
        hiring_brief=hiring_dict,
        gap_brief=gap_dict,
    )

    if trace:
        trace.generation(
            name="email_compose",
            model=usage.get("model", "unknown"),
            input={"segment": hiring_brief.primary_segment_match, "company": req.company_name},
            output={"subject": subject, "body": body[:300]},
            usage={
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
            },
        )

    # ── Tone guard ────────────────────────────────────────────────────
    _span_tone = trace.span(name="tone_guard", input={"draft_length": len(body)}) if trace else None

    def _regenerate(feedback: str = "") -> str:
        _, new_body, _ = compose_cold_email(
            prospect_name=req.prospect_name,
            company_name=req.company_name,
            segment=hiring_brief.primary_segment_match,
            pitch_language=classification.pitch_language,
            hiring_brief=hiring_dict,
            gap_brief=gap_dict,
            feedback=feedback,
        )
        return new_body

    body = tone_enforce(
        draft=body,
        generate_fn=_regenerate,
        context=f"Segment: {hiring_brief.primary_segment_match}. Company: {req.company_name}.",
    )

    if _span_tone:
        _span_tone.end(output={"final_length": len(body)})

    # ── Send email ────────────────────────────────────────────────────
    html_body = body.replace("\n\n", "</p><p>").replace("\n", "<br>")
    html_body = f"<p>{html_body}</p>"
    html_body += (
        '<p style="color:#999;font-size:11px;">'
        'This message is AI-assisted and marked draft pending review. '
        'Reply UNSUBSCRIBE to stop.</p>'
    )

    msg = EmailMessage(
        to=req.prospect_email,
        subject=subject,
        html=html_body,
        metadata={"draft": True, "email_type": "cold_outreach", "trace_id": trace_id},
    )

    _span_send = trace.span(name="email_send") if trace else None
    result = send_email(msg)
    if _span_send:
        _span_send.end(output={"success": result.success, "message_id": result.message_id})

    # ── Thread store ──────────────────────────────────────────────────
    thread = store.get_or_create(
        company_id=brief.crunchbase_id,
        contact_id=req.prospect_email,
        contact_email=req.prospect_email,
        segment=classification.segment_label,
    )
    thread.add(role="agent", content=body, channel="email")
    store.save()

    if trace:
        trace.update(output={
            "status": "sent",
            "segment": classification.segment_label,
            "email_sent": result.success,
        })
        _langfuse.flush()

    return JSONResponse({
        "status": "sent" if result.success else "send_failed",
        "segment": classification.segment_label,
        "confidence": classification.confidence,
        "crunchbase_id": brief.crunchbase_id,
        "hubspot_contact_id": contact_id,
        "ai_maturity_score": hiring_brief.ai_maturity_score,
        "weak_signal": hiring_brief.weak_signal,
        "trace_id": trace_id,
        "email_message_id": result.message_id,
        "llm_model": usage.get("model"),
        "llm_tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
    })
