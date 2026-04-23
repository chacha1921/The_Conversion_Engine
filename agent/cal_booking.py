"""
Cal.com booking integration.
Creates real calendar events via Cal.com API.
Cal.com must be running locally via Docker Compose.
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

import httpx

_CALCOM_BASE = os.getenv("CALCOM_BASE_URL", "http://localhost:3000")
_CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
_DEFAULT_EVENT_TYPE_ID = int(os.getenv("CALCOM_EVENT_TYPE_ID", "1"))


def get_available_slots(
    event_type_id: int = _DEFAULT_EVENT_TYPE_ID,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """
    Fetch available booking slots from Cal.com.
    Returns list of slot dicts with 'time' and 'attendees'.
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
    except Exception as e:
        print(f"Cal.com slots error: {e}")
        return []


def book_slot(
    event_type_id: int = _DEFAULT_EVENT_TYPE_ID,
    start_time: str = "",            # ISO 8601
    prospect_name: str = "",
    prospect_email: str = "",
    sdr_email: str = "",
    notes: str = "",
    timezone_str: str = "UTC",
) -> Optional[dict]:
    """
    Book a discovery call slot on Cal.com.
    Both prospect and SDR emails must be included as attendees.
    Returns booking confirmation dict, or None on failure.
    """
    url = f"{_CALCOM_BASE}/api/v1/bookings"
    payload = {
        "apiKey": _CALCOM_API_KEY,
        "eventTypeId": event_type_id,
        "start": start_time,
        "timeZone": timezone_str,
        "language": "en",
        "metadata": {"source": "conversion_engine", "draft": True},
        "responses": {
            "name": prospect_name,
            "email": prospect_email,
            "notes": notes or "Discovery call booked via Conversion Engine",
            "guests": [sdr_email] if sdr_email else [],
        },
    }
    try:
        r = httpx.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Cal.com booking error: {e}")
        return None


def get_booking_link(
    event_type_slug: str = "discovery-call",
    prefill_name: str = "",
    prefill_email: str = "",
) -> str:
    """
    Generate a direct booking link with pre-filled fields.
    Used in SMS and email CTAs.
    """
    base = f"{_CALCOM_BASE}/{event_type_slug}"
    params = []
    if prefill_name:
        params.append(f"name={prefill_name.replace(' ', '+')}")
    if prefill_email:
        params.append(f"email={prefill_email}")
    return f"{base}?{'&'.join(params)}" if params else base
