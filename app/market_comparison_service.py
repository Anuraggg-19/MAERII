"""Side-by-side Serper and Scrapingdog Shopping comparison workflow.

This module deliberately does not call LLMs, alter market scores, or write to
the production market files. It is an evaluation-only path.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mfp_scraper.market_scraper import config_market
from mfp_scraper.market_scraper.comparison_relevance import (
    apply_query_overrides,
    build_profile,
    label_products,
)
from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient
from mfp_scraper.market_scraper.market_models import normalize_text, utc_now_iso
from mfp_scraper.market_scraper.scrapingdog_client import ScrapingdogShoppingClient
from mfp_scraper.market_scraper.serper_comparison_client import SerperShoppingComparisonClient

from app.market_service import _find_mfp_item


_SECRET_KEY_NAMES = {"api_key", "apikey", "key", "token", "authorization", "x-api-key"}
_TRACKING_QUERY_NAMES = {"gclid", "fbclid", "msclkid", "ref", "ref_", "tag", "source"}


def _normalise_url(url: str) -> str:
    """Remove URL fragments and tracking fields before exact-overlap checks."""
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        query = [
            (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_NAMES
        ]
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(query), ""))
    except ValueError:
        return url.strip().lower()


def _fallback_product_key(product: dict) -> tuple[str, str, Optional[float]]:
    price = product.get("price")
    return (normalize_text(product.get("title", "")), normalize_text(product.get("seller", "")), price)


def _product_field_completeness(products: list[dict]) -> dict[str, float]:
    count = len(products)
    fields = {
        "title": lambda product: bool(product.get("title")),
        "url": lambda product: bool(product.get("url")),
        "price": lambda product: product.get("price") is not None,
        "seller": lambda product: bool(product.get("seller")),
        "rating": lambda product: product.get("rating") is not None,
        "review_count": lambda product: bool(product.get("review_count")),
        "image": lambda product: bool(product.get("image_url")),
    }
    if not count:
        return {field: 0.0 for field in fields}
    return {
        field: round(sum(check(product) for product in products) / count, 3)
        for field, check in fields.items()
    }


def _dedupe_products(products: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for product in products:
        key = _normalise_url(product.get("url", "")) or _fallback_product_key(product)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(product)
    return deduped


def _compare_products(serper: list[dict], scrapingdog: list[dict]) -> dict[str, Any]:
    """Measure URL-first overlap, then title/seller/price overlap for unmatched products."""
    serper = _dedupe_products(serper)
    scrapingdog = _dedupe_products(scrapingdog)
    dog_by_url = defaultdict(list)
    for index, product in enumerate(scrapingdog):
        if url := _normalise_url(product.get("url", "")):
            dog_by_url[url].append(index)

    matched_serper = set()
    matched_dog = set()
    exact_pairs = []
    for serper_index, product in enumerate(serper):
        url = _normalise_url(product.get("url", ""))
        candidates = dog_by_url.get(url, []) if url else []
        dog_index = next((candidate for candidate in candidates if candidate not in matched_dog), None)
        if dog_index is not None:
            matched_serper.add(serper_index)
            matched_dog.add(dog_index)
            exact_pairs.append((serper_index, dog_index))

    dog_by_fallback = defaultdict(list)
    for dog_index, product in enumerate(scrapingdog):
        if dog_index not in matched_dog:
            dog_by_fallback[_fallback_product_key(product)].append(dog_index)

    approximate_pairs = []
    for serper_index, product in enumerate(serper):
        if serper_index in matched_serper:
            continue
        candidates = dog_by_fallback.get(_fallback_product_key(product), [])
        dog_index = next((candidate for candidate in candidates if candidate not in matched_dog), None)
        if dog_index is not None:
            matched_serper.add(serper_index)
            matched_dog.add(dog_index)
            approximate_pairs.append((serper_index, dog_index))

    overlap = len(matched_serper)
    union = len(serper) + len(scrapingdog) - overlap
    all_pairs = exact_pairs + approximate_pairs
    rank_deltas = [
        abs(int(serper[left].get("provider_rank") or 0) - int(scrapingdog[right].get("provider_rank") or 0))
        for left, right in all_pairs
    ]
    return {
        "serper_unique_products": len(serper),
        "scrapingdog_unique_products": len(scrapingdog),
        "exact_url_overlap": len(exact_pairs),
        "approximate_product_overlap": len(approximate_pairs),
        "total_overlap": overlap,
        "overlap_percentage": round(overlap / union * 100, 1) if union else 0.0,
        "serper_only": [serper[index] for index in range(len(serper)) if index not in matched_serper],
        "scrapingdog_only": [scrapingdog[index] for index in range(len(scrapingdog)) if index not in matched_dog],
        "average_rank_difference_for_overlaps": round(sum(rank_deltas) / len(rank_deltas), 2) if rank_deltas else None,
        "field_completeness": {
            "serper": _product_field_completeness(serper),
            "scrapingdog": _product_field_completeness(scrapingdog),
        },
    }


def _destination_summary(products: list[dict]) -> dict[str, Any]:
    """Summarize what destination-page scraping added beyond shopping listings."""
    pages = [product.get("destination_page", {}) for product in products if product.get("destination_page")]
    complete = [page for page in pages if page.get("status") == "complete"]
    fields = ("name", "description", "sku", "brand", "price", "currency", "availability", "rating", "review_count", "image_urls", "attributes")
    return {
        "configured_limit": config_market.MARKET_COMPARISON_DESTINATION_LIMIT,
        "configured_candidate_limit": config_market.MARKET_COMPARISON_DESTINATION_CANDIDATE_LIMIT,
        "attempted": len(pages),
        "completed": len(complete),
        "skipped": sum(page.get("status") == "skipped" for page in pages),
        "errors": sum(page.get("status") == "error" for page in pages),
        "field_completeness": {
            field: round(sum(bool(page.get("product_page", {}).get(field)) for page in complete) / len(complete), 3)
            if complete else 0.0
            for field in fields
        },
    }


def _relevance_summary(products: list[dict]) -> dict[str, int]:
    """Count labels without removing any provider-returned products."""
    summary = {"relevant": 0, "needs_review": 0, "irrelevant": 0, "not_evaluated": 0}
    for product in products:
        status = product.get("relevance", {}).get("status", "not_evaluated")
        summary[status if status in summary else "not_evaluated"] += 1
    return summary


def _sanitize_for_storage(value: Any) -> Any:
    """Remove credentials from values such as Scrapingdog immersive links."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SECRET_KEY_NAMES else _sanitize_for_storage(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_for_storage(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        try:
            parsed = urlsplit(value)
            query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in _SECRET_KEY_NAMES]
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
        except ValueError:
            return value
    return value


class MarketProviderComparison:
    """Run a Shopping-only, non-production comparison for one MFP."""

    def __init__(
        self,
        serper_client: Optional[SerperShoppingComparisonClient] = None,
        scrapingdog_client: Optional[ScrapingdogShoppingClient] = None,
    ):
        if not config_market.MARKET_COMPARISON_MODE:
            raise ValueError("Market comparison is disabled. Set MARKET_COMPARISON_MODE=true in .env.")
        self.serper_client = serper_client or SerperShoppingComparisonClient()
        self.scrapingdog_client = scrapingdog_client or ScrapingdogShoppingClient()

    def compare(self, mfp_id: int) -> dict[str, Any]:
        mfp_item = _find_mfp_item(mfp_id)
        if not mfp_item:
            raise LookupError(f"MFP item with id {mfp_id} not found in enriched dataset.")

        # Existing query construction is reused, but no LLM-generated category
        # context is requested. A small, deterministic query override is allowed
        # only for known spelling collisions (e.g. Lac -> lace), and is sent to
        # both providers identically.
        query_builder = EcommerceClient(api_key=self.serper_client.api_key)
        original_queries = query_builder.build_search_queries(mfp_item)
        relevance_profile = build_profile(mfp_item)
        queries = apply_query_overrides(original_queries, relevance_profile)
        original_query_by_final_query = {}
        for original_query in original_queries:
            final_query = apply_query_overrides([original_query], relevance_profile)[0]
            original_query_by_final_query.setdefault(final_query, original_query)
        query_runs = []
        all_serper = []
        all_scrapingdog = []
        for query in queries:
            serper_result = self.serper_client.search_shopping(query, config_market.SHOPPING_RESULTS_PER_QUERY)
            dog_result = self.scrapingdog_client.search_shopping(query, config_market.SHOPPING_RESULTS_PER_QUERY)
            # Labels are comparison-only metadata. The full returned product
            # remains in the response and saved JSON even when irrelevant.
            label_products(serper_result["products"], relevance_profile, config_market.MARKET_COMPARISON_RELEVANCE_FILTER)
            label_products(dog_result["products"], relevance_profile, config_market.MARKET_COMPARISON_RELEVANCE_FILTER)
            all_serper.extend(serper_result["products"])
            all_scrapingdog.extend(dog_result["products"])
            query_runs.append({
                "query": query,
                "original_query": original_query_by_final_query.get(query, query),
                "serper_result": serper_result,
                "scrapingdog_result": dog_result,
                "raw_provider_payloads": (
                    _sanitize_for_storage({"serper": serper_result["raw_payload"], "scrapingdog": dog_result["raw_payload"]})
                    if config_market.MARKET_COMPARISON_STORE_RAW else None
                ),
            })

        # Destination scraping is paid and comparison-only. Relevant products
        # are preferred; uncertain items are used only if there are not enough
        # relevant candidates. Explicitly irrelevant products are retained in
        # raw output but never consume destination-scraping credits.
        dog_candidates = _dedupe_products(all_scrapingdog)
        if config_market.MARKET_COMPARISON_RELEVANCE_FILTER:
            relevant = [item for item in dog_candidates if item.get("relevance", {}).get("status") == "relevant"]
            review = [item for item in dog_candidates if item.get("relevance", {}).get("status") == "needs_review"]
            dog_candidates = relevant + review
        completed_destination_pages = 0
        for product in dog_candidates[: config_market.MARKET_COMPARISON_DESTINATION_CANDIDATE_LIMIT]:
            product["destination_page"] = self.scrapingdog_client.enrich_destination(product)
            if product["destination_page"].get("status") == "complete":
                completed_destination_pages += 1
            if completed_destination_pages >= config_market.MARKET_COMPARISON_DESTINATION_LIMIT:
                break

        for run in query_runs:
            serper_result = run.pop("serper_result")
            dog_result = run.pop("scrapingdog_result")
            run["serper"] = {key: serper_result[key] for key in ("products", "latency_ms", "error")}
            run["scrapingdog"] = {key: dog_result[key] for key in ("products", "latency_ms", "error")}
            run["comparison"] = _compare_products(serper_result["products"], dog_result["products"])

        result = {
            "status": "complete",
            "mode": "comparison_only",
            "mfp_id": mfp_id,
            "mfp_name": mfp_item.get("name", ""),
            "retrieved_at": utc_now_iso(),
            "search_settings": {"country": "in", "language": "en", "page": 0, "max_results_per_query": config_market.SHOPPING_RESULTS_PER_QUERY},
            "relevance_filter": {
                "enabled": config_market.MARKET_COMPARISON_RELEVANCE_FILTER,
                "profile_version": relevance_profile["version"],
                "manual_profile_applied": relevance_profile["manual_profile"],
                "labels": {"serper": _relevance_summary(all_serper), "scrapingdog": _relevance_summary(all_scrapingdog)},
                "destination_candidate_policy": "relevant_first_then_needs_review; irrelevant listings are never destination-scraped",
            },
            "queries": query_runs,
            "overall_comparison": _compare_products(all_serper, all_scrapingdog),
            "scrapingdog_destination_pages": _destination_summary(_dedupe_products(all_scrapingdog)),
            "provider_summary": {
                "serper": {"total_latency_ms": round(sum(run["serper"]["latency_ms"] for run in query_runs), 1), "errors": [run["serper"]["error"] for run in query_runs if run["serper"]["error"]]},
                "scrapingdog": {"total_latency_ms": round(sum(run["scrapingdog"]["latency_ms"] for run in query_runs), 1), "errors": [run["scrapingdog"]["error"] for run in query_runs if run["scrapingdog"]["error"]]},
            },
        }
        result["comparison_file"] = str(self._save(result))
        return result

    @staticmethod
    def _save(result: dict[str, Any]) -> Path:
        config_market.MARKET_COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", result["mfp_name"].lower()).strip("-") or str(result["mfp_id"])
        timestamp = result["retrieved_at"].replace(":", "-")
        path = config_market.MARKET_COMPARISONS_DIR / f"{timestamp}_{result['mfp_id']}_{slug}.json"
        path.write_text(json.dumps(_sanitize_for_storage(result), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def compare_market_providers(mfp_id: int) -> dict[str, Any]:
    """Convenience entry point for the comparison-only API route."""
    return MarketProviderComparison().compare(mfp_id)
