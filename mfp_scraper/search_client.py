"""
Search client — wrapper around Serper.dev API for web search and image search.
"""

import time
import requests
from typing import Optional

from . import config


class SerperClient:
    """Wrapper around Serper.dev search API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.SERPER_API_KEY
        if not self.api_key:
            raise ValueError(
                "SERPER_API_KEY not set. Add it to your .env file."
            )
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        self._last_call_time = 0

    def _rate_limit(self):
        """Enforce delay between API calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < config.SEARCH_DELAY_SECONDS:
            time.sleep(config.SEARCH_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    @staticmethod
    def _request_error_details(exc: requests.RequestException) -> str:
        """Expose Serper's actionable error message while keeping keys private."""
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        try:
            body = response.text.strip()
        except Exception:
            body = ""
        if body:
            return f"HTTP {response.status_code}: {body[:500]}"
        return f"HTTP {response.status_code}: {exc}"

    def search(self, query: str, num_results: int = None) -> list[dict]:
        """
        Perform a web search and return list of results.
        Each result: {"title": str, "link": str, "snippet": str}
        """
        num_results = num_results or config.SEARCH_RESULTS_PER_QUERY
        self._rate_limit()

        try:
            resp = requests.post(
                config.SERPER_SEARCH_URL,
                headers=self.headers,
                json={"q": query, "num": num_results},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            # Also include knowledge graph if available
            kg = data.get("knowledgeGraph", {})
            if kg:
                kg_text = kg.get("description", "")
                if kg_text:
                    results.insert(0, {
                        "title": kg.get("title", "Knowledge Graph"),
                        "link": kg.get("website", ""),
                        "snippet": kg_text,
                        "is_knowledge_graph": True,
                    })

            return results

        except requests.RequestException as e:
            print(f"  [!] Search error for '{query}': {self._request_error_details(e)}")
            return []

    def search_images(self, query: str, num_results: int = 3) -> list[dict]:
        """
        Search for images. Returns list of {"title": str, "imageUrl": str, "link": str}
        """
        self._rate_limit()

        try:
            resp = requests.post(
                config.SERPER_IMAGES_URL,
                headers=self.headers,
                json={"q": query, "num": num_results},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("images", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "imageUrl": item.get("imageUrl", ""),
                    "link": item.get("link", ""),
                })
            return results

        except requests.RequestException as e:
            print(f"  [!] Image search error for '{query}': {self._request_error_details(e)}")
            return []


def build_search_queries(item: dict) -> dict[str, str]:
    """
    Build targeted search queries for each attribute that needs enrichment.
    Returns a dict of {field_name: search_query}.
    """
    name = item["name"]
    sci_name = item.get("scientific_name") or ""

    # Use scientific name in queries when available for better precision
    name_query = f"{name} {sci_name}".strip()

    queries = {}

    # Scientific name (only if missing)
    if not item.get("scientific_name"):
        queries["scientific_name"] = (
            f"{name} scientific name botanical name plant species"
        )

    # Description, season, shelf life — combined query for efficiency
    queries["general_info"] = (
        f"{name_query} India minor forest produce description "
        f"harvesting season months shelf life storage"
    )

    # States where tribals collect this
    if not item.get("states"):
        queries["states"] = (
            f"{name_query} India tribal collection states regions "
            f"where found gathered forest produce"
        )

    # Artisan types
    queries["artisan_types"] = (
        f"{name_query} India tribal gatherer collector processor "
        f"artisan who collects harvests"
    )

    # Current and potential products
    queries["products"] = (
        f"{name_query} value added products uses India tribal "
        f"processed goods potential products commercial"
    )

    return queries


def build_image_query(item: dict) -> str:
    """Build an image search query for the item."""
    name = item["name"]
    sci_name = item.get("scientific_name") or ""
    return f"{name} {sci_name} India forest produce".strip()
