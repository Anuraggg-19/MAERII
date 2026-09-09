"""Serper Google Shopping client isolated from the production market workflow."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

from . import config_market
from .market_models import normalize_product


class SerperShoppingComparisonClient:
    """Fetch Shopping-only Serper data for a fair provider comparison."""

    provider = "serper"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config_market.SERPER_API_KEY
        if not self.api_key:
            raise ValueError("SERPER_API_KEY not set. Add it to your .env file.")
        self._last_call_time = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < config_market.ECOMMERCE_DELAY_SECONDS:
            time.sleep(config_market.ECOMMERCE_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    def search_shopping(self, query: str, num_results: int) -> dict[str, Any]:
        self._rate_limit()
        started = time.perf_counter()
        try:
            response = requests.post(
                config_market.SERPER_SHOPPING_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num_results, "gl": "in", "hl": "en"},
                timeout=config_market.FETCH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            products = []
            for index, item in enumerate(payload.get("shopping", [])[:num_results], start=1):
                product = normalize_product({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "price": item.get("price", ""),
                    "rating": item.get("rating"),
                    "ratingCount": item.get("ratingCount", 0),
                    "seller": item.get("source", ""),
                    "source": item.get("source", ""),
                    "imageUrl": item.get("imageUrl") or item.get("thumbnail", ""),
                    "currency": "INR",
                })
                if product["title"]:
                    product.update({
                        "provider": self.provider,
                        "provider_product_id": str(item.get("productId", item.get("id", ""))),
                        "provider_rank": item.get("position") or index,
                        "query": query,
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
