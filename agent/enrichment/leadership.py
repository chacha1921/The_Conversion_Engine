"""
Leadership change detection.
Checks for new CTO / VP Engineering appointments within 90 days
using Playwright to scrape public press releases and Crunchbase people data.
"""
from __future__ import annotations
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from playwright.async_api import async_playwright

from .models import LeadershipChange

_WINDOW_DAYS = 90
_TARGET_ROLES = [
    "cto", "chief technology officer",
    "vp engineering", "vp of engineering",
    "head of engineering", "chief architect",
]


async def _scrape_text(url: str, timeout_ms: int = 12000) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            text = await page.inner_text("body")
            await browser.close()
            return text
    except Exception:
        return ""


def _parse_date(text: str) -> Optional[datetime]:
    patterns = [
        r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                raw = m.group(0).replace("/", "-")
                return datetime.fromisoformat(raw.replace(",", "")).replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def check_from_text(text: str, company_name: str) -> Optional[LeadershipChange]:
    """
    Given arbitrary text (press release, blog post), extract a leadership change
    for the company within _WINDOW_DAYS.
    """
    text_lower = text.lower()
    company_lower = company_name.lower()

    if company_lower not in text_lower:
        return None

    # Check if any target role is mentioned near an appointment verb
    appointment_verbs = ["appointed", "joins", "named", "hired", "welcomes", "promotes"]
    role_found = None
    for role in _TARGET_ROLES:
        if role in text_lower:
            role_found = role
            break

    if role_found is None:
        return None

    verb_found = any(v in text_lower for v in appointment_verbs)
    if not verb_found:
        return None

    # Try to extract date
    event_date = _parse_date(text)
    days_ago = None
    if event_date:
        days_ago = (datetime.now(timezone.utc) - event_date).days
        if days_ago > _WINDOW_DAYS:
            return None  # outside window

    # Try to extract a name: look for "Name appointed as CTO"
    name = None
    pattern = r"([A-Z][a-z]+ [A-Z][a-z]+)(?:\s+\w+)?\s+(?:appointed|joins|named|hired)"
    m = re.search(pattern, text)
    if m:
        name = m.group(1)

    return LeadershipChange(
        name=name,
        role=role_found,
        date=event_date.strftime("%Y-%m-%d") if event_date else None,
        days_ago=days_ago,
    )


def check_sync(company_name: str, press_release_url: Optional[str] = None) -> Optional[LeadershipChange]:
    if press_release_url:
        text = asyncio.run(_scrape_text(press_release_url))
        return check_from_text(text, company_name)
    return None
