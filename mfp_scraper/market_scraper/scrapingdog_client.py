"""Read-only Scrapingdog Google Shopping client used only for comparisons."""

from __future__ import annotations

import time
import json
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from . import config_market
from .market_models import normalize_product


class ScrapingdogShoppingClient:
    """Fetch normalized Google Shopping listings without affecting market data."""

    provider = "scrapingdog"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config_market.SCRAPINGDOG_API_KEY
        if not self.api_key:
            raise ValueError("SCRAPINGDOG_API_KEY not set. Add it to your .env file.")
        self._last_call_time = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < config_market.ECOMMERCE_DELAY_SECONDS:
            time.sleep(config_market.ECOMMERCE_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    @staticmethod
    def _usable_image(value: object) -> str:
        """Do not expose large base64 thumbnails in comparison API responses."""
        image = str(value or "").strip()
        return image if image.startswith(("https://", "http://")) else ""

    def search_shopping(self, query: str, num_results: int) -> dict[str, Any]:
        """Return a comparison-safe response; never log the API-key URL."""
        self._rate_limit()
        started = time.perf_counter()
        try:
            response = requests.get(
                config_market.SCRAPINGDOG_SHOPPING_URL,
                params={
                    "api_key": self.api_key,
                    "query": query,
                    "country": "in",
                    "language": "en",
                    "domain": "google.co.in",
                    "page": 0,
                },
                timeout=config_market.FETCH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            products = []
            for index, item in enumerate(payload.get("shopping_results", [])[:num_results], start=1):
                product = normalize_product({
                    "title": item.get("title", ""),
                    "url": item.get("product_link", ""),
                    "price": item.get("price", item.get("extracted_price")),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews", 0),
                    "seller": item.get("source", ""),
                    "source": item.get("source", ""),
                    "thumbnail": self._usable_image(item.get("thumbnail", "")),
                    "currency": "INR",
                })
                if product["title"]:
                    product.update({
                        "provider": self.provider,
                        "provider_product_id": str(item.get("product_id", "")),
                        "provider_rank": item.get("position") or index,
                        "query": query,
                        "immersive_page_token": self._page_token(item.get("scrapingdog_immersive_product_link", "")),
                    })
                    products.append(product)
            return {
                "provider": self.provider,
                "products": products,
                "raw_payload": payload,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": None,
            }
        except (requests.RequestException, ValueError) as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                try:
                    detail = response.text.strip()[:500]
                except Exception:
                    detail = ""
            return {
                "provider": self.provider,
                "products": [],
                "raw_payload": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": detail or str(exc),
            }

    @staticmethod
    def _page_token(value: object) -> str:
        try:
            return parse_qs(urlparse(str(value or "")).query).get("page_token", [""])[0]
        except ValueError:
            return ""

    def enrich_destination(self, product: dict) -> dict[str, Any]:
        """Fetch a retailer destination page through Immersive Product metadata.

        Google Shopping links point to Google, not necessarily the shop. The
        immersive call supplies retailer offer links, after which the generic
        Scrapingdog endpoint fetches the selected retailer page.
        """
        token = product.get("immersive_page_token", "")
        if not token:
            return {"status": "skipped", "reason": "No immersive product token was returned."}

        started = time.perf_counter()
        try:
            immersive_response = requests.get(
                config_market.SCRAPINGDOG_IMMERSIVE_PRODUCT_URL,
                params={"api_key": self.api_key, "page_token": token, "country": "in", "language": "en"},
                timeout=config_market.FETCH_TIMEOUT_SECONDS,
            )
            immersive_response.raise_for_status()
            destination_url = self._first_retailer_url(immersive_response.json())
            if not destination_url:
                return {"status": "skipped", "reason": "No retailer destination URL in immersive product data."}

            page_response = requests.get(
                config_market.SCRAPINGDOG_SCRAPE_URL,
                params={
                    "api_key": self.api_key,
                    "url": destination_url,
                    "dynamic": str(config_market.MARKET_COMPARISON_DESTINATION_DYNAMIC).lower(),
                },
                timeout=60,
            )
            page_response.raise_for_status()
            extracted = self._extract_product_page(page_response.text, destination_url)
            return {
                "status": "complete",
                "destination_url": destination_url,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "product_page": extracted,
            }
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            response = getattr(exc, "response", None)
            detail = ""
            if response is not None:
                try:
                    detail = response.text.strip()[:500]
                except Exception:
                    detail = ""
            return {
                "status": "error",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": detail or str(exc),
            }

    @staticmethod
    def _first_retailer_url(payload: Any) -> str:
        """Find the first non-Google HTTP offer link in known nested data."""
        if isinstance(payload, dict):
            for key in ("stores", "offers", "sellers", "merchant_offers"):
                if key in payload:
                    found = ScrapingdogShoppingClient._first_retailer_url(payload[key])
                    if found:
                        return found
            for value in payload.values():
                found = ScrapingdogShoppingClient._first_retailer_url(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = ScrapingdogShoppingClient._first_retailer_url(item)
                if found:
                    return found
        elif isinstance(payload, str) and payload.startswith(("https://", "http://")):
            host = urlparse(payload).netloc.lower()
            if host and "google." not in host and "scrapingdog.com" not in host:
                return payload
        return ""

    @staticmethod
    def _extract_product_page(html: str, destination_url: str) -> dict[str, Any]:
        """Extract stable product fields from JSON-LD and standard metadata."""
        soup = BeautifulSoup(html, "html.parser")
        products = []
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                products.extend(ScrapingdogShoppingClient._find_jsonld_products(json.loads(script.get_text(strip=True))))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        product = products[0] if products else {}
        offers = product.get("offers", {}) if isinstance(product, dict) else {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        rating = product.get("aggregateRating", {}) if isinstance(product, dict) else {}
        images = product.get("image", []) if isinstance(product, dict) else []
        if isinstance(images, str):
            images = [images]
        attributes = product.get("additionalProperty", []) if isinstance(product, dict) else []
        if isinstance(attributes, dict):
            attributes = [attributes]
        return {
            "page_title": (soup.title.get_text(" ", strip=True) if soup.title else "")[:300],
            "name": str(product.get("name", ""))[:300],
            "description": str(product.get("description", ""))[:1500],
            "sku": str(product.get("sku", ""))[:150],
            "brand": str((product.get("brand", {}) or {}).get("name", "") if isinstance(product.get("brand"), dict) else product.get("brand", ""))[:150],
            "price": offers.get("price") if isinstance(offers, dict) else None,
            "currency": str(offers.get("priceCurrency", "")) if isinstance(offers, dict) else "",
            "availability": str(offers.get("availability", "")) if isinstance(offers, dict) else "",
            "rating": rating.get("ratingValue") if isinstance(rating, dict) else None,
            "review_count": rating.get("reviewCount") if isinstance(rating, dict) else None,
            "image_urls": [str(image) for image in images if isinstance(image, str) and image.startswith(("https://", "http://"))][:5],
            "attributes": [
                {"name": str(item.get("name", ""))[:120], "value": str(item.get("value", ""))[:300]}
                for item in attributes if isinstance(item, dict) and item.get("name")
            ][:20],
            "destination_url": destination_url,
        }

    @staticmethod
    def _find_jsonld_products(value: Any) -> list[dict]:
        if isinstance(value, list):
            return [product for item in value for product in ScrapingdogShoppingClient._find_jsonld_products(item)]
        if not isinstance(value, dict):
            return []
        item_type = value.get("@type", [])
        types = item_type if isinstance(item_type, list) else [item_type]
        products = [value] if "Product" in types else []
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in value:
                products.extend(ScrapingdogShoppingClient._find_jsonld_products(value[key]))
        return products
