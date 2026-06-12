"""
Content fetcher — fetches web pages and extracts clean text for LLM processing.
"""

import time
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional

from . import config


# Tags that typically contain useful content
CONTENT_TAGS = ["p", "li", "td", "th", "h1", "h2", "h3", "h4", "dd", "dt"]

# Tags to remove entirely
NOISE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "iframe", "noscript", "svg", "button",
]


def fetch_page_text(url: str, max_chars: int = 5000) -> Optional[str]:
    """
    Fetch a web page and extract clean text content.
    Returns up to max_chars of cleaned text, or None on failure.
    """
    try:
        resp = requests.get(
            url,
            timeout=config.FETCH_TIMEOUT_SECONDS,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        resp.raise_for_status()

        # Skip non-HTML content
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise elements
        for tag in soup.find_all(NOISE_TAGS):
            tag.decompose()

        # Extract text from content tags
        texts = []
        for tag in soup.find_all(CONTENT_TAGS):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) > 20:  # Skip very short fragments
                texts.append(text)

        if not texts:
            # Fallback: get all text from body
            body = soup.find("body")
            if body:
                texts = [body.get_text(separator="\n", strip=True)]

        full_text = "\n".join(texts)

        # Clean up whitespace
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        full_text = re.sub(r" {2,}", " ", full_text)

        return full_text[:max_chars] if full_text else None

    except Exception as e:
        # Silently skip failed fetches — they're expected for some URLs
        return None


def fetch_multiple(urls: list[str], max_chars_per_page: int = 4000) -> str:
    """
    Fetch multiple URLs and combine their text.
    Returns aggregated text with source markers.
    """
    all_texts = []

    for url in urls:
        time.sleep(config.FETCH_DELAY_SECONDS)
        text = fetch_page_text(url, max_chars=max_chars_per_page)
        if text:
            all_texts.append(f"[Source: {url}]\n{text}")

    return "\n\n---\n\n".join(all_texts) if all_texts else ""


def aggregate_search_content(search_results: list[dict], max_pages: int = 3) -> str:
    """
    Given search results (with 'link' and 'snippet' keys),
    fetch the top pages and combine with snippets for a rich text context.
    """
    # Start with snippets (always available, no fetch needed)
    snippets = []
    for r in search_results:
        if r.get("snippet"):
            snippets.append(r["snippet"])

    snippet_text = "Search snippets:\n" + "\n".join(snippets) if snippets else ""

    # Fetch top pages for deeper content
    urls = [r["link"] for r in search_results if r.get("link")][:max_pages]
    page_text = fetch_multiple(urls)

    # Combine
    parts = [p for p in [snippet_text, page_text] if p]
    return "\n\n---\n\n".join(parts)
