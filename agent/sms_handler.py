"""
SMS handler — Africa's Talking sandbox.
Secondary channel: warm leads only (after email reply).
Kill-switch enforced. STOP/HELP/UNSUB handled.
All outbound routed to staff sink during challenge week unless OUTBOUND_LIVE=true.
"""
from __future__ import annotations
import logging
import os
from typing import Optional

import africastalking

logger = logging.getLogger(__name__)

_AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
_AT_API_KEY = os.getenv("AT_API_KEY", "")
_AT_SHORTCODE = os.getenv("AT_SHORTCODE", "")
_STAFF_SINK_PHONE = os.getenv("STAFF_SINK_PHONE", "+254700000000")

_STOP_COMMANDS = {"stop", "unsubscribe", "unsub", "quit", "cancel", "end"}
_HELP_COMMANDS = {"help", "info", "?"}

_REQUIRED_INBOUND_FIELDS = {"from", "text"}


def _init():
    if not _AT_API_KEY:
        raise EnvironmentError("AT_API_KEY is not set — Africa's Talking cannot be initialised")
    africastalking.initialize(_AT_USERNAME, _AT_API_KEY)
    return africastalking.SMS


# ── Send ───────────────────────────────────────────────────────────────
def send(to: str, message: str, company_id: str = "", contact_id: str = "") -> dict:
    """
    Send an SMS. Routes to staff sink unless OUTBOUND_LIVE=true.
    Returns a result dict with 'success' and optional 'error'.
    Never raises.
    """
    if not to:
        logger.warning("sms.send called with empty recipient — skipping")
        return {"success": False, "error": "empty recipient"}

    recipient = to if os.getenv("OUTBOUND_LIVE") else _STAFF_SINK_PHONE

    try:
        sms = _init()
        response = sms.send(
            message=f"[DRAFT] {message}",
            recipients=[recipient],
            sender_id=_AT_SHORTCODE or None,
        )
        # Africa's Talking returns {"SMSMessageData": {"Recipients": [...]}}
        recipients_data = (
            response.get("SMSMessageData", {}).get("Recipients", [])
            if isinstance(response, dict) else []
        )
        failed = [r for r in recipients_data if r.get("statusCode") not in (100, 101)]
        if failed:
            logger.warning("SMS partial failure — failed recipients: %s", failed)
            return {"success": False, "error": f"provider rejected: {failed}", "raw": response}

        logger.info("SMS sent to %s (routed=%s)", to, recipient)
        return {"success": True, "raw": response}

    except EnvironmentError as e:
        logger.error("SMS config error: %s", e)
        return {"success": False, "error": str(e), "error_type": "config"}
    except Exception as e:
        logger.error("Africa's Talking send error (to=%s): %s", recipient, e)
        return {"success": False, "error": str(e), "error_type": "provider"}


# ── Inbound webhook ────────────────────────────────────────────────────
def handle_inbound(payload: dict) -> dict:
    """
    Parse and validate an inbound SMS webhook from Africa's Talking.
    Returns a structured event dict. Raises ValueError on invalid payload.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"SMS webhook payload must be a dict, got {type(payload)}")

    missing = _REQUIRED_INBOUND_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(f"SMS webhook missing required fields: {missing}")

    try:
        text = str(payload.get("text") or "").strip()
        from_number = str(payload.get("from") or "").strip()
    except Exception as e:
        raise ValueError(f"Failed to parse SMS webhook fields: {e}") from e

    if not from_number:
        raise ValueError("SMS webhook 'from' field is empty")

    command = text.lower().strip()

    if command in _STOP_COMMANDS:
        logger.info("STOP received from %s", from_number)
        return {
            "event_type": "sms_stop",
            "from": from_number,
            "text": text,
            "opted_out": True,
            "reply": "You have been unsubscribed. You will receive no further messages.",
        }

    if command in _HELP_COMMANDS:
        logger.info("HELP received from %s", from_number)
        return {
            "event_type": "sms_help",
            "from": from_number,
            "text": text,
            "opted_out": False,
            "reply": (
                "Reply STOP to unsubscribe. "
                "This is an automated outreach from Tenacious Consulting. "
                "Questions? Email hello@tenacious.io"
            ),
        }

    logger.info("SMS reply received from %s: %r", from_number, text[:80])
    return {
        "event_type": "sms_reply",
        "from": from_number,
        "text": text,
        "opted_out": False,
        "reply": None,
    }


# ── Message builder ────────────────────────────────────────────────────
def build_scheduling_sms(
    prospect_name: str,
    cal_link: str,
    context: str = "",
) -> str:
    base = f"Hi {prospect_name}, quick follow-up — you can book a 30-min slot here: {cal_link}"
    if context:
        base = f"{context} {base}"
    return base
