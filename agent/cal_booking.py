"""
Cal.com booking integration.
Creates real calendar events via Cal.com API.
On booking confirmation, automatically syncs to HubSpot via record_booking().
Cal.com must be running locally via Docker Compose.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_CALCOM_BASE = os.getenv("CALCOM_BASE_URL", "http://localhost:3000")
_CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
_DEFAULT_EVENT_TYPE_ID = int(os.getenv("CALCOM_EVENT_TYPE_ID", "1"))
_SDR_EMAIL = os.getenv("SDR_EMAIL", "sdr@tenacious.io")


def get_available_slots(
    event_type_id: int = _DEFAULT_EVENT_TYPE_ID,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Fetch available booking slots from Cal.com.
    Returns list of slot dicts, or empty list on failure.
    """
    if not start_date:
        start_date = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"{_CALCOM_BASE}/api/v1/slots"
    params = {
        "apiKey": _CALCOM_API_KEY,
        "eventTypeId": event_type_id,
        "startTime": start_date,
        "endTime": end_date or start_date,
    }
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("slots", {})
    except httpx.HTTPStatusError as e:
        logger.error("Cal.com slots HTTP error %s: %s", e.response.status_code, e)
        return []
    except httpx.RequestError as e:
        logger.error("Cal.com slots connection error: %s", e)
        return []
    except Exception as e:
        logger.error("Cal.com slots unexpected error: %s", e)
        return []


def book_slot(
    event_type_id: int = _DEFAULT_EVENT_TYPE_ID,
    start_time: str = "",
    prospect_name: str = "",
    prospect_email: str = "",
    sdr_email: str = "",
    notes: str = "",
    timezone_str: str = "UTC",
) -> Optional[dict]:
    """
    Book a discovery call slot on Cal.com.
    Both prospect and SDR emails are included as attendees.
    Returns booking confirmation dict, or None on failure.
    """
    if not start_time:
        logger.error("book_slot called without start_time")
        return None
    if not prospect_email:
        logger.error("book_slot called without prospect_email")
        return None

    url = f"{_CALCOM_BASE}/api/v1/bookings"
    payload = {
        "apiKey": _CALCOM_API_KEY,
        "eventTypeId": event_type_id,
        "start": start_time,
        "timeZone": timezone_str,
        "language": "en",
        "metadata": {"source": "conversion_engine", "draft": True},
        "responses": {
            "name": prospect_name or prospect_email.split("@")[0],
            "email": prospect_email,
            "notes": notes or "Discovery call booked via Conversion Engine",
            "guests": [sdr_email or _SDR_EMAIL],
        },
    }
    try:
        r = httpx.post(url, json=payload, timeout=15)
        r.raise_for_status()
        booking = r.json()
        logger.info(
            "Cal.com booking created — uid=%s start=%s prospect=%s",
            booking.get("uid"), start_time, prospect_email,
        )
        return booking
    except httpx.HTTPStatusError as e:
        logger.error("Cal.com booking HTTP error %s: %s", e.response.status_code, e)
        return None
    except httpx.RequestError as e:
        logger.error("Cal.com booking connection error: %s", e)
        return None
    except Exception as e:
        logger.error("Cal.com booking unexpected error: %s", e)
        return None


def handle_booking_webhook(payload: dict, hubspot_contact_id: Optional[str] = None) -> dict:
    """
    Parse a Cal.com booking webhook and sync the confirmed booking to HubSpot.

    Cal.com fires this when a booking is CREATED, RESCHEDULED, or CANCELLED.
    On BOOKING_CREATED: calls hubspot_mcp.record_booking() to set lead status
    BOOKED and create a meeting activity — keeping both systems in sync.

    Returns a structured event dict. Raises ValueError on invalid payload.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"Cal.com webhook payload must be a dict, got {type(payload)}")

    trigger = payload.get("triggerEvent", "")
    booking_data = payload.get("payload", payload)  # some Cal.com versions nest under "payload"

    uid = booking_data.get("uid", "")
    start_time = booking_data.get("startTime", "")
    title = booking_data.get("title", "Discovery Call")
    attendees = booking_data.get("attendees", [])
    organizer = booking_data.get("organizer", {})

    prospect_email = ""
    prospect_name = ""
    for a in attendees:
        email = a.get("email", "")
        if email and email != organizer.get("email", ""):
            prospect_email = email
            prospect_name = a.get("name", "")
            break

    event = {
        "event_type": "booking_created" if "CREATED" in trigger.upper() else trigger.lower(),
        "booking_uid": uid,
        "start_time": start_time,
        "title": title,
        "prospect_email": prospect_email,
        "prospect_name": prospect_name,
        "hubspot_synced": False,
    }

    # ── Sync to HubSpot ───────────────────────────────────────────────
    if "CREATED" in trigger.upper() or trigger == "":
        contact_id = hubspot_contact_id or _lookup_hubspot_contact(prospect_email)
        if contact_id:
            from .hubspot_mcp import record_booking
            synced = record_booking(
                contact_id=contact_id,
                prospect_email=prospect_email,
                booking_uid=uid,
                start_time=start_time,
                event_title=title,
                sdr_email=organizer.get("email", _SDR_EMAIL),
                notes=booking_data.get("additionalNotes", ""),
            )
            event["hubspot_synced"] = synced
            if synced:
                logger.info(
                    "Cal.com → HubSpot sync complete — contact=%s booking=%s",
                    contact_id, uid,
                )
            else:
                logger.warning(
                    "Cal.com → HubSpot sync failed — contact=%s booking=%s",
                    contact_id, uid,
                )

            # ── Generate and log discovery call context brief ─────────
            try:
                from .discovery_brief import generate_and_log
                generate_and_log(
                    prospect_name=prospect_name,
                    prospect_email=prospect_email,
                    prospect_company=title,
                    booking_uid=uid,
                    start_time=start_time,
                    hubspot_contact_id=contact_id,
                )
                event["discovery_brief_logged"] = True
                logger.info(
                    "Discovery brief generated and logged — contact=%s booking=%s",
                    contact_id, uid,
                )
            except Exception as e:
                logger.error("Discovery brief generation failed: %s", e)
                event["discovery_brief_logged"] = False
        else:
            logger.warning(
                "Cal.com booking confirmed but no HubSpot contact found for %s",
                prospect_email,
            )

    return event


def _lookup_hubspot_contact(email: str) -> Optional[str]:
    """Look up a HubSpot contact ID by email. Returns None if not found."""
    if not email:
        return None
    try:
        from .hubspot_mcp import _client
        from hubspot.crm.contacts.exceptions import ApiException
        client = _client()
        result = client.crm.contacts.search_api.do_search({
            "filterGroups": [{
                "filters": [{"propertyName": "email", "operator": "EQ", "value": email}]
            }],
            "limit": 1,
        })
        if result.results:
            return result.results[0].id
    except Exception as e:
        logger.error("HubSpot contact lookup failed (email=%s): %s", email, e)
    return None


def get_booking_link(
    event_type_slug: str = "discovery-call",
    prefill_name: str = "",
    prefill_email: str = "",
) -> str:
    """Generate a direct booking link with pre-filled fields for SMS/email CTAs."""
    base = f"{_CALCOM_BASE}/{event_type_slug}"
    params = []
    if prefill_name:
        params.append(f"name={prefill_name.replace(' ', '+')}")
    if prefill_email:
        params.append(f"email={prefill_email}")
    return f"{base}?{'&'.join(params)}" if params else base
