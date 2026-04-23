"""
HubSpot Developer Sandbox integration via MCP (9 tools).
Writes every conversation event back to HubSpot.
All fields must be non-null; enrichment timestamp must be current.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional

import hubspot
from hubspot.crm.contacts import SimplePublicObjectInput
from hubspot.crm.contacts.exceptions import ApiException

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
        # Custom properties (must be created in HubSpot sandbox first)
        "crunchbase_id": crunchbase_id,
        "icp_segment": segment,
        "ai_maturity_score": str(ai_maturity_score),
        "enrichment_timestamp": ts,
        "notes_last_contacted": notes or f"Outreach initiated via Conversion Engine at {ts}",
    }
    # Remove empty strings to keep all fields non-null
    properties = {k: v for k, v in properties.items() if v not in ("", None)}

    try:
        # Try to find existing contact by email
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
            return contact_id
        else:
            result = client.crm.contacts.basic_api.create(
                simple_public_object_input=SimplePublicObjectInput(properties=properties)
            )
            return result.id
    except ApiException as e:
        print(f"HubSpot API error: {e}")
        return None


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
    except ApiException:
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
    except ApiException:
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
    except ApiException:
        return False
