"""Web data via the Firecrawl REST API (news, filings, research pages).

Requires FIRECRAWL_API_KEY in .env — see FIRECRAWL.md for setup.
"""

import requests

from core.config import FIRECRAWL_API_KEY, FIRECRAWL_API_URL


class FirecrawlError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not FIRECRAWL_API_KEY:
        raise FirecrawlError("FIRECRAWL_API_KEY is not set (see FIRECRAWL.md)")
    return {"Authorization": f"Bearer {FIRECRAWL_API_KEY}"}


def scrape(url: str, only_main_content: bool = True, timeout: int = 60) -> str:
    """Scrape a URL to clean markdown."""
    resp = requests.post(
        f"{FIRECRAWL_API_URL}/scrape",
        headers=_headers(),
        json={"url": url, "onlyMainContent": only_main_content, "formats": ["markdown"]},
        timeout=timeout,
    )
    if not resp.ok:
        raise FirecrawlError(f"scrape failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json().get("data", {}).get("markdown", "")


def search(query: str, limit: int = 5, timeout: int = 60) -> list[dict]:
    """Search the web; returns a list of {title, url, description} dicts."""
    resp = requests.post(
        f"{FIRECRAWL_API_URL}/search",
        headers=_headers(),
        json={"query": query, "limit": limit},
        timeout=timeout,
    )
    if not resp.ok:
        raise FirecrawlError(f"search failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json().get("data", {}).get("web", [])
