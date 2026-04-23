"""
Email handler — Resend (primary) with MailerSend fallback.
Kill-switch: OUTBOUND_LIVE env var must be set to route to real recipients.
All Tenacious-branded content tagged draft:true in metadata.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

import resend

_STAFF_SINK = os.getenv("STAFF_SINK_EMAIL", "sink@program-staff.internal")


@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str
    reply_to: Optional[str] = None
    metadata: Optional[dict] = None


def send(msg: EmailMessage) -> dict:
    """
    Send an email. Routes to staff sink unless OUTBOUND_LIVE=true.
    Returns Resend API response dict.
    """
    resend.api_key = os.getenv("RESEND_API_KEY", "")

    recipient = msg.to
    if not os.getenv("OUTBOUND_LIVE"):
        recipient = _STAFF_SINK

    meta = msg.metadata or {}
    meta.setdefault("draft", True)
    meta.setdefault("generated_by", "conversion_engine")
    meta.setdefault("approved", False)

    params: resend.Emails.SendParams = {
        "from": os.getenv("EMAIL_FROM", "outreach@tenacious.io"),
        "to": [recipient],
        "subject": msg.subject,
        "html": msg.html,
        "reply_to": msg.reply_to,
        "tags": [{"name": k, "value": str(v)} for k, v in meta.items()],
    }
    return resend.Emails.send(params)


def build_cold_email(
    prospect_name: str,
    company_name: str,
    hiring_signal_summary: str,
    competitor_gap_summary: str,
    pitch_language: str,
    sender_name: str = "Tenacious Consulting",
) -> EmailMessage:
    """
    Build a signal-grounded cold email using the hiring brief and gap brief.
    """
    subject = f"Quick question about {company_name}'s engineering growth"

    html = f"""
<p>Hi {prospect_name},</p>

<p>{hiring_signal_summary}</p>

<p>{competitor_gap_summary}</p>

<p>{pitch_language}</p>

<p>Worth a 30-minute conversation? Happy to work around your schedule.</p>

<p>Best,<br>{sender_name}</p>

<p style="color:#999;font-size:11px;">
  This message is AI-assisted and marked as draft pending review.
  Reply UNSUBSCRIBE to stop receiving messages.
</p>
"""
    return EmailMessage(
        to="",  # set by caller
        subject=subject,
        html=html,
        metadata={"draft": True, "email_type": "cold_outreach"},
    )


def handle_reply_webhook(payload: dict) -> dict:
    """
    Process an inbound reply webhook from Resend.
    Returns structured event for the agent loop.
    """
    return {
        "event_type": "email_reply",
        "from": payload.get("from", ""),
        "subject": payload.get("subject", ""),
        "text": payload.get("text", ""),
        "html": payload.get("html", ""),
        "message_id": payload.get("message_id", ""),
    }
