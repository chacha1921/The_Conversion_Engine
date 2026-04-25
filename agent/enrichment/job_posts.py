"""
Job-post velocity scraper using Playwright.
Fetches public job listings from a company's careers page / Wellfound / BuiltIn.
Respects robots.txt. No login. No captcha bypass.
Rate limit: 2s between requests to the same domain per policy/data_handling_policy.md Rule 4.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_USER_AGENT = "TRP1-Week10-Research (trainee@trp1.example)"
_CRAWL_DELAY_S = 2.0  # Rule 4: at least 2s between requests to same domain


def _robots_allows(url: str) -> bool:
    """Return True if robots.txt permits our user-agent to fetch this URL."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # If robots.txt is unreachable, default to allowing (common for small sites)
        return True
    return rp.can_fetch(_USER_AGENT, url)


async def fetch_job_titles(careers_url: str, timeout_ms: int = 15000) -> list[str]:
    """
    Return a list of job title strings found on the given public careers URL.
    Checks robots.txt first; returns empty list if disallowed or on failure.
    """
    if not _robots_allows(careers_url):
        logger.warning("robots.txt disallows scraping %s — skipping", careers_url)
        return []

    await asyncio.sleep(_CRAWL_DELAY_S)  # Rule 4: rate limit per domain

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=_USER_AGENT)
            await page.goto(careers_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

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
            logger.info("Fetched %d job titles from %s", len(titles), careers_url)
            return list(titles)
    except Exception as e:
        logger.error("Job post scrape failed (%s): %s", careers_url, e)
        return []


def fetch_job_titles_sync(careers_url: str) -> list[str]:
    return asyncio.run(fetch_job_titles(careers_url))


def velocity_label(current: int, previous: Optional[int]) -> str:
    """Categorise hiring velocity change per the official schema enum."""
    if previous is None:
        return "insufficient_signal"
    if current == 0 and previous == 0:
        return "insufficient_signal"
    if previous == 0:
        return "tripled_or_more"
    ratio = current / previous
    if ratio >= 3.0:
        return "tripled_or_more"
    if ratio >= 1.8:
        return "doubled"
    if ratio >= 1.1:
        return "increased_modestly"
    if ratio >= 0.9:
        return "flat"
    return "declined"


def estimate_velocity(
    current_count: int,
    previous_count: Optional[int],
    window_days: int = 60,
) -> Optional[int]:
    """Delta in open roles over window_days. Returns None if previous_count unavailable."""
    if previous_count is None:
        return None
    return current_count - previous_count
