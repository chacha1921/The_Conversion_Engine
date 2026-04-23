"""
SMS handler — Africa's Talking sandbox.
Secondary channel: warm leads only (after email reply).
Kill-switch enforced. STOP/HELP/UNSUB handled.
All outbound routed to staff sink during challenge week unless OUTBOUND_LIVE=true.
"""
from __future__ import annotations
import os
from typing import Optional

import africastalking

_AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
_AT_API_KEY = os.getenv("AT_API_KEY", "")
_AT_SHORTCODE = os.getenv("AT_SHORTCODE", "")
_STAFF_SINK_PHONE = os.getenv("STAFF_SINK_PHONE", "+254700000000")

_STOP_COMMANDS = {"stop", "unsubscribe", "unsub", "quit", "cancel", "end"}
_HELP_COMMANDS = {"help", "info", "?"}


def _init():
    africastalking.initialize(_AT_USERNAME, _AT_API_KEY)
    return africastalking.SMS


def send(to: str, message: str, company_id: str = "", contact_id: str = "") -> dict:
    """
    Send an SMS. Routes to staff sink unless OUTBOUND_LIVE=true.
    All messages tagged with draft metadata.
    """
    recipient = to if os.getenv("OUTBOUND_LIVE") else _STAFF_SINK_PHONE

    sms = _init()
    response = sms.send(
        message=f"[DRAFT] {message}",
        recipients=[recipient],
        sender_id=_AT_SHORTCODE or None,
    )
    return response


def handle_inbound(payload: dict) -> dict:
    """
    Process an inbound SMS webhook from Africa's Talking.
    Returns a structured event with opt-out flag and parsed intent.
    """
    text = (payload.get("text") or "").strip()
    from_number = payload.get("from", "")
    shortcode = payload.get("to", "")

    command = text.lower().strip()

    if command in _STOP_COMMANDS:
        return {
            "event_type": "sms_stop",
            "from": from_number,
            "text": text,
            "opted_out": True,
            "reply": "You have been unsubscribed. You will receive no further messages.",
        }

    if command in _HELP_COMMANDS:
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

    return {
        "event_type": "sms_reply",
        "from": from_number,
        "text": text,
        "opted_out": False,
        "reply": None,  # agent loop handles crafting the reply
    }


def build_scheduling_sms(
    prospect_name: str,
    cal_link: str,
    context: str = "",
) -> str:
    """
    Build a warm SMS for scheduling a discovery call.
    Only used after the prospect has already replied by email.
    """
    base = f"Hi {prospect_name}, quick follow-up — you can book a 30-min slot here: {cal_link}"
    if context:
        base = f"{context} {base}"
    return base
