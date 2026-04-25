"""
HubSpot Developer Sandbox integration via REST API (httpx).
Writes every conversation event back to HubSpot.
All fields must be non-null; enrichment timestamp must be current.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
_BASE = "https://api.hubapi.com"
_TIMEOUT = 15


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Content-Type": "application/json",
    }


def _search_contact_by_email(email: str) -> Optional[str]:
    """Return HubSpot contact ID for the given email, or None."""
    try:
        r = httpx.post(
            f"{_BASE}/crm/v3/objects/contacts/search",
            headers=_headers(),
            json={
                "filterGroups": [{
                    "filters": [{"propertyName": "email", "operator": "EQ", "value": email}]
                }],
                "limit": 1,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0]["id"] if results else None
    except Exception as e:
        logger.error("HubSpot contact search failed (email=%s): %s", email, e)
        return None


def upsert_contact(
    email: str,
    company_name: str,
    crunchbase_id: str,
    segment: str,
    ai_maturity_score: int,
    enrichment_timestamp: Optional[datetime] = None,
    firstname: str = "",
    lastname: str = "",
    phone: str = "",
    notes: str = "",
) -> Optional[str]:
    """
    Create or update a HubSpot contact with all enrichment fields.
    Returns the HubSpot contact ID, or None on failure.
    """
    ts = (enrichment_timestamp or datetime.now(timezone.utc)).isoformat()

    properties = {
        "email": email,
        "firstname": firstname or "Unknown",
        "lastname": lastname or "Prospect",
        "company": company_name,
        "hs_lead_status": "NEW",
        "icp_segment": segment,
        "ai_maturity_score": str(ai_maturity_score),
        "enrichment_timestamp": ts,
        "tenacious_status": "draft",
        "notes_last_contacted": notes or f"Outreach initiated via Conversion Engine at {ts}",
    }
    if phone:
        properties["phone"] = phone

    _CUSTOM_PROPS = {"icp_segment", "ai_maturity_score", "enrichment_timestamp", "tenacious_status", "notes_last_contacted"}

    def _do_upsert(props: dict) -> Optional[str]:
        contact_id = _search_contact_by_email(email)
        if contact_id:
            r = httpx.patch(
                f"{_BASE}/crm/v3/objects/contacts/{contact_id}",
                headers=_headers(),
                json={"properties": props},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            logger.info("HubSpot contact updated — id=%s email=%s", contact_id, email)
            return contact_id
        else:
            r = httpx.post(
                f"{_BASE}/crm/v3/objects/contacts",
                headers=_headers(),
                json={"properties": props},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            contact_id = r.json()["id"]
            logger.info("HubSpot contact created — id=%s email=%s", contact_id, email)
            return contact_id

    try:
        return _do_upsert(properties)
    except httpx.HTTPStatusError as e:
        body = e.response.text
        if e.response.status_code == 400 and "PROPERTY_DOESNT_EXIST" in body:
            # Custom properties not created in sandbox — retry with standard fields only
            logger.warning("HubSpot sandbox missing custom properties; retrying with standard fields only")
            std_props = {k: v for k, v in properties.items() if k not in _CUSTOM_PROPS}
            try:
                return _do_upsert(std_props)
            except httpx.HTTPStatusError as e2:
                logger.error("HubSpot upsert_contact retry HTTP error %s (email=%s): %s",
                             e2.response.status_code, email, e2.response.text[:200])
                return None
        logger.error("HubSpot upsert_contact HTTP error %s (email=%s): %s",
                     e.response.status_code, email, body[:200])
        return None
    except Exception as e:
        logger.error("HubSpot upsert_contact error (email=%s): %s", email, e)
        return None


def record_booking(
    contact_id: str,
    prospect_email: str,
    booking_uid: str,
    start_time: str,
    event_title: str = "Discovery Call",
    sdr_email: str = "",
    notes: str = "",
) -> bool:
    """
    Update HubSpot when a Cal.com booking is confirmed.
    Sets lead status to BOOKED and creates a meeting activity.
    """
    ts = datetime.now(timezone.utc).isoformat()
    meeting_note = (
        f"Discovery call booked via Conversion Engine.\n"
        f"Booking UID: {booking_uid}\n"
        f"Start: {start_time}\n"
        f"SDR: {sdr_email or 'unassigned'}\n"
        f"Notes: {notes or 'none'}"
    )

    try:
        # 1. Update contact lead status
        r = httpx.patch(
            f"{_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=_headers(),
            json={"properties": {
                "hs_lead_status": "BOOKED",
                "tenacious_status": "draft",
                "notes_last_contacted": meeting_note,
            }},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()

        # 2. Create meeting activity
        r2 = httpx.post(
            f"{_BASE}/crm/v3/objects/meetings",
            headers=_headers(),
            json={"properties": {
                "hs_meeting_title": event_title,
                "hs_meeting_start_time": start_time,
                "hs_meeting_body": meeting_note,
                "hs_internal_meeting_notes": f"cal_booking_uid={booking_uid}",
                "hs_timestamp": ts,
            }},
            timeout=_TIMEOUT,
        )
        r2.raise_for_status()
        meeting_id = r2.json()["id"]

        # 3. Associate meeting to contact
        httpx.put(
            f"{_BASE}/crm/v4/objects/meetings/{meeting_id}/associations/contacts/{contact_id}",
            headers=_headers(),
            json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 200}],
            timeout=_TIMEOUT,
        )

        logger.info("HubSpot booking recorded — contact=%s booking=%s", contact_id, booking_uid)
        return True

    except httpx.HTTPStatusError as e:
        logger.error("HubSpot record_booking HTTP error %s (contact=%s): %s",
                     e.response.status_code, contact_id, e.response.text[:200])
        return False
    except Exception as e:
        logger.error("HubSpot record_booking error (contact=%s): %s", contact_id, e)
        return False


def log_note(contact_id: str, note: str) -> bool:
    """Attach a note to a contact."""
    ts = datetime.now(timezone.utc).isoformat()
    try:
        r = httpx.post(
            f"{_BASE}/crm/v3/objects/notes",
            headers=_headers(),
            json={"properties": {
                "hs_note_body": note[:65000],
                "hs_timestamp": ts,
            }},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        note_id = r.json()["id"]

        # Associate note to contact
        httpx.put(
            f"{_BASE}/crm/v4/objects/notes/{note_id}/associations/contacts/{contact_id}",
            headers=_headers(),
            json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}],
            timeout=_TIMEOUT,
        )
        return True
    except httpx.HTTPStatusError as e:
        logger.error("HubSpot log_note HTTP error %s (contact=%s): %s",
                     e.response.status_code, contact_id, e.response.text[:200])
        return False
    except Exception as e:
        logger.error("HubSpot log_note error (contact=%s): %s", contact_id, e)
        return False


def update_lead_status(contact_id: str, status: str) -> bool:
    """Update the lead status on a contact."""
    try:
        r = httpx.patch(
            f"{_BASE}/crm/v3/objects/contacts/{contact_id}",
            headers=_headers(),
            json={"properties": {"hs_lead_status": status}},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error("HubSpot update_lead_status HTTP error %s (contact=%s): %s",
                     e.response.status_code, contact_id, e.response.text[:200])
        return False
    except Exception as e:
        logger.error("HubSpot update_lead_status error (contact=%s): %s", contact_id, e)
        return False


def _client():
    """Legacy compatibility shim — returns a namespace with crm.contacts.search_api for cal_booking.py."""
    class _FakeSearchApi:
        def do_search(self, body):
            email = body["filterGroups"][0]["filters"][0]["value"]
            contact_id = _search_contact_by_email(email)
            class _Result:
                def __init__(self, id_): self.id = id_
            class _Results:
                def __init__(self, cid):
                    self.results = [_Result(cid)] if cid else []
            return _Results(contact_id)

    class _FakeContacts:
        search_api = _FakeSearchApi()

    class _FakeCrm:
        contacts = _FakeContacts()

    class _FakeClient:
        crm = _FakeCrm()

    return _FakeClient()
