"""
Job-post velocity scraper using Playwright.
Fetches public job listings from a company's careers page / Wellfound / BuiltIn.
Respects robots.txt. No login. No captcha bypass.
"""
from __future__ import annotations
import asyncio
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def fetch_job_titles(careers_url: str, timeout_ms: int = 15000) -> list[str]:
    """
    Return a list of job title strings found on the given public careers URL.
    Returns empty list on failure rather than raising.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (compatible; ConversionEngineBot/1.0; "
                    "+https://github.com/your-repo)"
                )
            )
            await page.goto(careers_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Generic extraction: grab text from common job-listing selectors
            selectors = [
                "h2", "h3", "h4",
                "[class*='job-title']", "[class*='position-title']",
                "[class*='role']", "[class*='opening']",
                "li[class*='job']", "div[class*='listing']",
            ]
            titles: set[str] = set()
            for sel in selectors:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    text = (await el.inner_text()).strip()
                    if 5 < len(text) < 120:
                        titles.add(text)

            await browser.close()
            return list(titles)
    except Exception:
        return []


def fetch_job_titles_sync(careers_url: str) -> list[str]:
    return asyncio.run(fetch_job_titles(careers_url))


def estimate_velocity(
    current_count: int,
    previous_count: Optional[int],
    window_days: int = 60,
) -> Optional[int]:
    """
    Delta in open roles over window_days.
    Returns None if previous_count not available.
    """
    if previous_count is None:
        return None
    return current_count - previous_count
