"""
Content fetcher for HTML and PDF sources used during enrichment.
"""

from io import BytesIO
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from . import config


CONTENT_TAGS = ["p", "li", "td", "th", "h1", "h2", "h3", "h4", "dd", "dt"]

NOISE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "iframe", "noscript", "svg", "button",
]

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None


def _request_headers() -> dict[str, str]:
    """Return shared browser-like headers for fetch requests."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }


def _clean_text(text: str, max_chars: int) -> Optional[str]:
    """Normalize whitespace and cap extracted content."""
    cleaned = re.sub(r"\n{3,}", "\n\n", text or "")
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    if not cleaned:
        return None
    return cleaned[:max_chars]


def _extract_pdf_text(resp: requests.Response, max_chars: int) -> Optional[str]:
    """Extract text from a PDF response when pypdf is available."""
    if PdfReader is None:
        return None

    try:
        reader = PdfReader(BytesIO(resp.content))
        parts = []
        remaining = max_chars

        for page in reader.pages:
            if remaining <= 0:
                break
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue
            chunk = page_text[:remaining]
            parts.append(chunk)
            remaining -= len(chunk)

        return _clean_text("\n".join(parts), max_chars=max_chars)
    except Exception:
        return None


def fetch_document_text(url: str, max_chars: int = 5000) -> Optional[dict]:
    """
    Fetch a document and return structured content.
    Supports HTML and PDF documents.
    """
    try:
        resp = requests.get(
            url,
            timeout=config.FETCH_TIMEOUT_SECONDS,
            headers=_request_headers(),
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            pdf_text = _extract_pdf_text(resp, max_chars=max_chars)
            if not pdf_text:
                return None
            return {
                "url": url,
                "content_type": "pdf",
                "text": pdf_text,
            }

        if "html" not in content_type:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(NOISE_TAGS):
            tag.decompose()

        texts = []
        for tag in soup.find_all(CONTENT_TAGS):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) > 20:
                texts.append(text)

        if not texts:
            body = soup.find("body")
            if body:
                texts = [body.get_text(separator="\n", strip=True)]

        cleaned = _clean_text("\n".join(texts), max_chars=max_chars)
        if not cleaned:
            return None

        return {
            "url": url,
            "content_type": "html",
            "text": cleaned,
        }
    except Exception:
        return None


def fetch_page_text(url: str, max_chars: int = 5000) -> Optional[str]:
    """
    Fetch a web page and extract clean text content.
    Returns HTML-only text for compatibility with the original pipeline.
    """
    doc = fetch_document_text(url, max_chars=max_chars)
    if not doc or doc.get("content_type") != "html":
        return None
    return doc.get("text")


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


def fetch_search_documents(
    search_results: list[dict],
    max_pages: int = 4,
    max_chars_per_page: int = 4000,
) -> list[dict]:
    """
    Fetch structured documents for the top search results.
    """
    documents = []
    seen_urls = set()

    for result in search_results:
        url = result.get("link")
        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        if len(documents) >= max_pages:
            break

        time.sleep(config.FETCH_DELAY_SECONDS)
        doc = fetch_document_text(url, max_chars=max_chars_per_page)
        if not doc:
            continue

        documents.append({
            "url": url,
            "title": result.get("title", ""),
            "snippet": result.get("snippet", ""),
            "content_type": doc.get("content_type", "unknown"),
            "text": doc.get("text", ""),
        })

    return documents


def aggregate_search_content(search_results: list[dict], max_pages: int = 3) -> str:
    """
    Given search results, fetch the top pages and combine with snippets.
    """
    snippets = []
    for result in search_results:
        if result.get("snippet"):
            snippets.append(result["snippet"])

    snippet_text = "Search snippets:\n" + "\n".join(snippets) if snippets else ""

    urls = [result["link"] for result in search_results if result.get("link")][:max_pages]
    page_text = fetch_multiple(urls)

    parts = [part for part in [snippet_text, page_text] if part]
    return "\n\n---\n\n".join(parts)
