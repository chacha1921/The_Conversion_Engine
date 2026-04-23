"""
HubSpot Developer Sandbox integration via MCP (9 tools).
Writes every conversation event back to HubSpot.
All fields must be non-null; enrichment timestamp must be current.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import hubspot
from hubspot.crm.contacts import SimplePublicObjectInput
from hubspot.crm.contacts.exceptions import ApiException

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")


def _client() -> hubspot.Client:
    return hubspot.Client.create(access_token=_TOKEN)


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
    client = _client()
    ts = (enrichment_timestamp or datetime.now(timezone.utc)).isoformat()

    properties = {
        "email": email,
        "firstname": firstname or "Unknown",
        "lastname": lastname or "Prospect",
        "company": company_name,
        "phone": phone or "",
        "hs_lead_status": "NEW",
        "crunchbase_id": crunchbase_id,
        "icp_segment": segment,
        "ai_maturity_score": str(ai_maturity_score),
        "enrichment_timestamp": ts,
        "notes_last_contacted": notes or f"Outreach initiated via Conversion Engine at {ts}",
    }
    properties = {k: v for k, v in properties.items() if v not in ("", None)}

    try:
        search_result = client.crm.contacts.search_api.do_search({
            "filterGroups": [{
                "filters": [{"propertyName": "email", "operator": "EQ", "value": email}]
            }],
            "limit": 1,
        })
        if search_result.results:
            contact_id = search_result.results[0].id
            client.crm.contacts.basic_api.update(
                contact_id=contact_id,
                simple_public_object_input=SimplePublicObjectInput(properties=properties),
            )
            logger.info("HubSpot contact updated — id=%s email=%s", contact_id, email)
            return contact_id
        else:
            result = client.crm.contacts.basic_api.create(
                simple_public_object_input=SimplePublicObjectInput(properties=properties)
            )
            logger.info("HubSpot contact created — id=%s email=%s", result.id, email)
            return result.id
    except ApiException as e:
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
    Sets lead status to BOOKED, records meeting date and booking details.
    This is the synchronisation point between Cal.com and HubSpot.
    """
    client = _client()
    ts = datetime.now(timezone.utc).isoformat()
    meeting_note = (
        f"Discovery call booked via Conversion Engine.\n"
        f"Booking UID: {booking_uid}\n"
        f"Start: {start_time}\n"
        f"SDR: {sdr_email or 'unassigned'}\n"
        f"Notes: {notes or 'none'}"
    )

    try:
        # 1. Update lead status and meeting timestamp on the contact
        client.crm.contacts.basic_api.update(
            contact_id=contact_id,
            simple_public_object_input=SimplePublicObjectInput(properties={
                "hs_lead_status": "BOOKED",
                "hs_latest_meeting_activity_timestamp": ts,
                "notes_last_contacted": meeting_note,
            }),
        )

        # 2. Create a meeting activity linked to the contact
        meeting = client.crm.objects.basic_api.create(
            object_type="meetings",
            simple_public_object_input=SimplePublicObjectInput(properties={
                "hs_meeting_title": event_title,
                "hs_meeting_start_time": start_time,
                "hs_meeting_body": meeting_note,
                "hs_internal_meeting_notes": f"cal_booking_uid={booking_uid}",
                "hs_timestamp": ts,
            }),
        )

        # 3. Associate the meeting with the contact
        client.crm.objects.associations_api.create(
            object_type="meetings",
            object_id=meeting.id,
            to_object_type="contacts",
            to_object_id=contact_id,
            association_type="meeting_event_to_contact",
        )

        logger.info(
            "HubSpot booking recorded — contact=%s booking=%s start=%s",
            contact_id, booking_uid, start_time,
        )
        return True

    except ApiException as e:
        logger.error("HubSpot record_booking error (contact=%s): %s", contact_id, e)
        return False


def log_email_activity(
    contact_id: str,
    subject: str,
    body: str,
    direction: str = "OUTBOUND",
) -> bool:
    """Log an email activity against a contact."""
    client = _client()
    try:
        client.crm.objects.basic_api.create(
            object_type="emails",
            simple_public_object_input=SimplePublicObjectInput(properties={
                "hs_email_subject": subject,
                "hs_email_text": body[:5000],
                "hs_email_direction": direction,
                "hs_timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        )
        return True
    except ApiException as e:
        logger.error("HubSpot log_email_activity error (contact=%s): %s", contact_id, e)
        return False


def log_note(contact_id: str, note: str) -> bool:
    """Attach a note to a contact."""
    client = _client()
    try:
        client.crm.objects.basic_api.create(
            object_type="notes",
            simple_public_object_input=SimplePublicObjectInput(properties={
                "hs_note_body": note,
                "hs_timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        )
        return True
    except ApiException as e:
        logger.error("HubSpot log_note error (contact=%s): %s", contact_id, e)
        return False


def update_lead_status(contact_id: str, status: str) -> bool:
    """Update the lead status on a contact (e.g. 'QUALIFIED', 'BOOKED')."""
    client = _client()
    try:
        client.crm.contacts.basic_api.update(
            contact_id=contact_id,
            simple_public_object_input=SimplePublicObjectInput(
                properties={"hs_lead_status": status}
            ),
        )
        return True
    except ApiException as e:
        logger.error("HubSpot update_lead_status error (contact=%s status=%s): %s", contact_id, status, e)
        return False
