"""
Email handler — Resend (primary) with MailerSend fallback.
Kill-switch: OUTBOUND_LIVE env var must be set to route to real recipients.
All Tenacious-branded content tagged draft:true in metadata.
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

import resend
from resend.exceptions import ResendError

logger = logging.getLogger(__name__)

_STAFF_SINK = os.getenv("STAFF_SINK_EMAIL", "sink@program-staff.internal")

# ── Handler registry ───────────────────────────────────────────────────
# Callers register callbacks here instead of polling returned dicts.
# Example:
#   @on_email_event("email_reply")
#   def handle_reply(event): ...
_handlers: dict[str, list[Callable[[dict], None]]] = {}


def on_email_event(event_type: str):
    """Decorator to register a handler for a specific email event type."""
    def decorator(fn: Callable[[dict], None]):
        _handlers.setdefault(event_type, []).append(fn)
        return fn
    return decorator


def register_handler(event_type: str, fn: Callable[[dict], None]) -> None:
    """Register a handler function for the given event type."""
    _handlers.setdefault(event_type, []).append(fn)


def _dispatch(event: dict) -> None:
    """Fire all registered handlers for this event's type."""
    for fn in _handlers.get(event.get("event_type", ""), []):
        try:
            fn(event)
        except Exception as e:
            logger.error("Email event handler %s raised: %s", fn.__name__, e)


# ── Data model ─────────────────────────────────────────────────────────
@dataclass
class EmailMessage:
    to: str
    subject: str
    html: str
    reply_to: Optional[str] = None
    metadata: Optional[dict] = field(default_factory=dict)


@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None   # "auth" | "rate_limit" | "invalid" | "unknown"


# ── Send ───────────────────────────────────────────────────────────────
def send(msg: EmailMessage) -> SendResult:
    """
    Send an email. Routes to staff sink unless OUTBOUND_LIVE=true.
    Returns a SendResult — never raises.
    """
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        logger.warning("RESEND_API_KEY not set — email not sent")
        return SendResult(success=False, error="RESEND_API_KEY not configured", error_type="auth")

    resend.api_key = api_key
    recipient = msg.to if os.getenv("OUTBOUND_LIVE") else _STAFF_SINK

    meta = dict(msg.metadata or {})
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

    try:
        response = resend.Emails.send(params)
        message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info("Email sent to %s — id=%s", recipient, message_id)
        return SendResult(success=True, message_id=str(message_id))
    except ResendError as e:
        error_type = _classify_resend_error(e)
        logger.error("Resend error (%s): %s", error_type, e)
        return SendResult(success=False, error=str(e), error_type=error_type)
    except Exception as e:
        logger.error("Unexpected send error: %s", e)
        return SendResult(success=False, error=str(e), error_type="unknown")


def _classify_resend_error(e: Exception) -> str:
    msg = str(e).lower()
    if "unauthorized" in msg or "api_key" in msg:
        return "auth"
    if "rate" in msg or "429" in msg:
        return "rate_limit"
    if "invalid" in msg or "422" in msg or "400" in msg:
        return "invalid"
    return "unknown"


# ── Webhook ────────────────────────────────────────────────────────────
_REQUIRED_REPLY_FIELDS = {"from", "subject"}
_VALID_EVENT_TYPES = {"email.delivered", "email.bounced", "email.complained", "email.opened", "email.clicked"}


def handle_reply_webhook(payload: dict) -> dict:
    """
    Parse and validate an inbound Resend webhook payload.
    Dispatches to registered handlers. Returns a structured event dict.
    Raises ValueError on invalid payload.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"Webhook payload must be a dict, got {type(payload)}")

    # Resend wraps delivery events under payload["type"] + payload["data"]
    resend_type = payload.get("type", "")
    if resend_type in _VALID_EVENT_TYPES:
        event = _parse_delivery_event(resend_type, payload.get("data", {}))
        _dispatch(event)
        return event

    # Plain reply webhook (email forwarded back as reply)
    missing = _REQUIRED_REPLY_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(f"Webhook payload missing required fields: {missing}")

    from_addr = payload.get("from", "").strip()
    if not from_addr or "@" not in from_addr:
        raise ValueError(f"Invalid 'from' address in webhook: {from_addr!r}")

    event = {
        "event_type": "email_reply",
        "from": from_addr,
        "subject": payload.get("subject", "").strip(),
        "text": payload.get("text", "").strip(),
        "html": payload.get("html", "").strip(),
        "message_id": payload.get("message_id", "").strip(),
    }
    _dispatch(event)
    return event


def _parse_delivery_event(resend_type: str, data: dict) -> dict:
    type_map = {
        "email.delivered": "email_delivered",
        "email.bounced": "email_bounce",
        "email.complained": "email_complaint",
        "email.opened": "email_opened",
        "email.clicked": "email_clicked",
    }
    event_type = type_map.get(resend_type, resend_type)

    if event_type == "email_bounce":
        logger.warning("Email bounced — to=%s reason=%s", data.get("to"), data.get("reason"))
    elif event_type == "email_complaint":
        logger.warning("Spam complaint — to=%s", data.get("to"))

    return {
        "event_type": event_type,
        "message_id": data.get("email_id", ""),
        "to": data.get("to", ""),
        "reason": data.get("reason", ""),
        "raw": data,
    }


# ── Email builder ──────────────────────────────────────────────────────
def build_cold_email(
    prospect_name: str,
    company_name: str,
    hiring_signal_summary: str,
    competitor_gap_summary: str,
    pitch_language: str,
    sender_name: str = "Tenacious Consulting",
) -> EmailMessage:
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
        to="",
        subject=subject,
        html=html,
        metadata={"draft": True, "email_type": "cold_outreach"},
    )
