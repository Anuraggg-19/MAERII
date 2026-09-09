"""Isolated open-source market experiment: SearXNG + Crawl4AI + Ollama.

This module never calls Serper, Gemini, Groq, normal market analysis, scoring,
or recommendations. It reads an already-generated product-category cache only
to make its experiment queries representative; it never generates or changes
those categories.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from app.market_service import _find_mfp_item
from app.product_service import get_cached_product_categories
from mfp_scraper import config
from mfp_scraper.market_scraper.comparison_relevance import apply_query_overrides, build_profile, label_products
from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient
from mfp_scraper.market_scraper.market_models import normalize_product, utc_now_iso


class OpenSourcePipelineError(RuntimeError):
    """A local open-source service is unavailable or returned invalid data."""


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        value = response.json()
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _dedupe_urls(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output, seen = [], set()
    for item in items:
        url = str(item.get("url", "")).strip()
        try:
            parsed = urlsplit(url)
            key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
        except ValueError:
            key = url.lower()
        if not url or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


_MARKETPLACE_DOMAINS = ("amazon.", "flipkart.", "indiamart.", "etsy.", "meesho.", "jiomart.")
_INFORMATIONAL_SIGNALS = (
    "researchgate", "pmc.", "wikipedia", "facebook.", "instagram.", "youtube.",
    ".gov/", "/about", "/services/", "publication", "scientific", "research paper",
    "journal", "study", "cultivation", "farmer",
)


def _candidate_quality_score(candidate: dict[str, Any]) -> int:
    """Rank likely retail pages ahead of articles without excluding fallback results."""
    url = str(candidate.get("url", "")).lower()
    text = " ".join(str(candidate.get(key, "")) for key in ("title", "snippet")).lower()
    score = 0
    if any(domain in url for domain in _MARKETPLACE_DOMAINS):
        score += 12
    if any(segment in url for segment in ("/product", "/products/", "/shop/", "/item/", "/p/")):
        score += 8
    if any(word in text for word in ("buy ", "shop ", "price", "for sale", "in stock", "latest price")):
        score += 5
    if "₹" in text or "rs." in text or "inr" in text:
        score += 3
    if any(signal in url or signal in text for signal in _INFORMATIONAL_SIGNALS):
        score -= 20
    return score


def _select_balanced_candidates(search_runs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Choose comparable coverage from every query before taking extra URLs.

    A general web engine commonly returns articles before product pages. Each
    query is therefore quality-ranked, then sampled round-robin so one broad
    query cannot consume the complete crawling budget.
    """
    per_query = []
    for run in search_runs:
        ranked = sorted(run.get("candidates", []), key=_candidate_quality_score, reverse=True)
        per_query.append(_dedupe_urls(ranked))

    selected, seen = [], set()
    position = 0
    while len(selected) < limit:
        added = False
        for candidates in per_query:
            if position >= len(candidates) or len(selected) >= limit:
                continue
            candidate = candidates[position]
            unique = _dedupe_urls([*selected, candidate])
            if len(unique) > len(selected):
                selected.append(candidate)
                added = True
        if not added:
            break
        position += 1
    return selected


class SearxngDiscoveryClient:
    """Open-web discovery. This intentionally is not a Google Shopping proxy."""

    def search(self, query: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            response = requests.get(
                f"{config.SEARXNG_BASE_URL}/search",
                params={"q": query, "format": "json", "categories": "general", "language": "en-IN", "safesearch": 1},
                timeout=config.OPEN_SOURCE_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = _safe_json(response)
            candidates = []
            for item in payload.get("results", [])[: config.OPEN_SOURCE_RESULTS_PER_QUERY]:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                candidates.append({
                    "url": str(item["url"]), "title": str(item.get("title", "")),
                    "snippet": str(item.get("content", "")), "query": query,
                })
            return {"candidates": candidates, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": None}
        except requests.RequestException as exc:
            detail = getattr(getattr(exc, "response", None), "text", "")[:300]
            return {"candidates": [], "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": detail or str(exc)}


def _jsonld_products(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [product for item in value for product in _jsonld_products(item)]
    if not isinstance(value, dict):
        return []
    item_type = value.get("@type", [])
    types = item_type if isinstance(item_type, list) else [item_type]
    products = [value] if "Product" in types else []
    for key in ("@graph", "mainEntity", "itemListElement"):
        products.extend(_jsonld_products(value.get(key)))
    return products


def _extract_page_product(html: str, url: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Use portable product metadata first; no LLM is needed on well-formed pages."""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            products.extend(_jsonld_products(json.loads(script.get_text(strip=True))))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    product = products[0] if products else {}
    offers = product.get("offers", {}) if isinstance(product, dict) else {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    rating = product.get("aggregateRating", {}) if isinstance(product, dict) else {}
    image = product.get("image", "") if isinstance(product, dict) else ""
    if isinstance(image, list):
        image = next((entry for entry in image if isinstance(entry, str)), "")
    title = str(product.get("name", "") if isinstance(product, dict) else "") or (soup.title.get_text(" ", strip=True) if soup.title else fallback.get("title", ""))
    description = str(product.get("description", "") if isinstance(product, dict) else "")
    if not description:
        description = str((soup.select_one('meta[name="description"]') or {}).get("content", ""))
    return normalize_product({
        "title": title[:300], "url": url, "price": offers.get("price") if isinstance(offers, dict) else None,
        "currency": offers.get("priceCurrency", "INR") if isinstance(offers, dict) else "INR",
        "rating": rating.get("ratingValue") if isinstance(rating, dict) else None,
        "reviews": rating.get("reviewCount") if isinstance(rating, dict) else 0,
        "seller": (offers.get("seller", {}) or {}).get("name", "") if isinstance(offers, dict) and isinstance(offers.get("seller"), dict) else urlsplit(url).netloc,
        "image_url": image, "category": product.get("category", "") if isinstance(product, dict) else "",
    }) | {
        "description": description[:1500], "sku": str(product.get("sku", ""))[:150] if isinstance(product, dict) else "",
        "brand": str((product.get("brand", {}) or {}).get("name", "") if isinstance(product, dict) and isinstance(product.get("brand"), dict) else product.get("brand", ""))[:150] if isinstance(product, dict) else "",
        "extraction_method": "json_ld" if product else "page_metadata",
        "discovery_query": fallback.get("query", ""),
    }


async def _crawl_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
    except ImportError as exc:
        raise OpenSourcePipelineError("Crawl4AI is not installed. Run: pip install -r requirements.txt, then crawl4ai-setup.") from exc
    browser = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=config.OPEN_SOURCE_REQUEST_TIMEOUT_SECONDS * 1000,
        word_count_threshold=1,
    )
    pages = []
    async with AsyncWebCrawler(config=browser) as crawler:
        for candidate in candidates:
            started = time.perf_counter()
            try:
                result = await crawler.arun(candidate["url"], config=run_config)
                if not getattr(result, "success", False):
                    pages.append({**candidate, "status": "error", "error": str(getattr(result, "error_message", "Crawl failed")), "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
                    continue
                html = getattr(result, "html", "") or getattr(result, "cleaned_html", "") or ""
                pages.append({**candidate, "status": "complete", "html": html, "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
            except Exception as exc:  # Crawl4AI wraps browser/network errors differently by version.
                pages.append({**candidate, "status": "error", "error": str(exc)[:300], "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
    return pages


def _classify_with_ollama(products: list[dict[str, Any]], mfp_item: dict[str, Any]) -> dict[str, Any]:
    """Classify small compact batches so a local model is not overwhelmed."""
    candidates = [product for product in products if product.get("relevance", {}).get("status") != "irrelevant"][: config.OPEN_SOURCE_MAX_CLASSIFICATIONS]
    if not candidates:
        return {"classified": 0, "latency_ms": 0.0, "error": None}
    schema = {
        "type": "object", "properties": {"classifications": {"type": "array", "items": {"type": "object", "properties": {
            "index": {"type": "integer"}, "product_type": {"type": "string", "enum": ["raw", "derived", "invalid"]},
            "confidence": {"type": "number"}, "reason": {"type": "string"},
        }, "required": ["index", "product_type", "confidence", "reason"]}}}, "required": ["classifications"]
    }
    started = time.perf_counter()
    classified, errors = 0, []
    batch_size = max(1, config.OPEN_SOURCE_CLASSIFICATION_BATCH_SIZE)
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset:offset + batch_size]
        records = [{"index": index, "title": p["title"], "seller": p.get("seller", ""), "description": p.get("description", "")[:220], "url": p["url"]} for index, p in enumerate(batch)]
        prompt = (
            "Classify each listing for this Indian MFP. Return raw if it is the material, derived if genuinely made from it, "
            "or invalid if it is informational, a service, or unrelated. Be conservative.\n"
            f"MFP: {mfp_item.get('name')} | Scientific name: {mfp_item.get('scientific_name', '')} | "
            f"Known products: {', '.join(mfp_item.get('current_products', [])[:12])}\nListings:\n{json.dumps(records, ensure_ascii=False)}"
        )
        try:
            response = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={"model": config.OLLAMA_MODEL, "stream": False, "format": schema, "options": {"temperature": 0}, "messages": [{"role": "user", "content": prompt}]},
                timeout=config.OPEN_SOURCE_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            message = _safe_json(response).get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            output = json.loads(content)
            for entry in output.get("classifications", []):
                index = entry.get("index")
                if isinstance(index, int) and 0 <= index < len(batch):
                    batch[index]["local_classification"] = {
                        "status": entry.get("product_type", "invalid"), "confidence": float(entry.get("confidence", 0)), "reason": str(entry.get("reason", ""))[:500],
                        "model": config.OLLAMA_MODEL,
                    }
                    classified += 1
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc)[:200])
    return {"classified": classified, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": "; ".join(errors) or None}


def _save(result: dict[str, Any]) -> Path:
    config.OPEN_SOURCE_COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", result["mfp_name"].lower()).strip("-") or str(result["mfp_id"])
    path = config.OPEN_SOURCE_COMPARISONS_DIR / f"{result['retrieved_at'].replace(':', '-')}_{result['mfp_id']}_{slug}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_open_source_market_experiment(mfp_id: int) -> dict[str, Any]:
    """Run the fully local/open-source experiment and save only its own report."""
    if not config.OPEN_SOURCE_MARKET_MODE:
        raise OpenSourcePipelineError("Open-source market experiment is disabled. Set OPEN_SOURCE_MARKET_MODE=true in .env.")
    if config.OPEN_SOURCE_DISCOVERY_PROVIDER != "searxng":
        raise OpenSourcePipelineError("Only the self-hosted SearXNG discovery adapter is currently supported.")
    mfp_item = _find_mfp_item(mfp_id)
    if not mfp_item:
        raise LookupError(f"MFP item with id {mfp_id} not found in enriched dataset.")

    profile = build_profile(mfp_item)
    category_context = get_cached_product_categories(mfp_id)
    raw_queries = EcommerceClient(api_key="open-source-experiment").build_search_queries(mfp_item, category_context=category_context)
    queries = apply_query_overrides(raw_queries, profile)
    discovery_client = SearxngDiscoveryClient()
    runs = []
    for query in queries:
        run = discovery_client.search(query)
        runs.append({"query": query, **run, "candidate_count": len(run["candidates"])})
    candidates = _select_balanced_candidates(runs, config.OPEN_SOURCE_MAX_URLS)
    if not candidates and any(run["error"] for run in runs):
        raise OpenSourcePipelineError("SearXNG discovery failed. Ensure SearXNG is running at SEARXNG_BASE_URL and its JSON format is enabled.")

    pages = asyncio.run(_crawl_candidates(candidates))
    products = [_extract_page_product(page["html"], page["url"], page) for page in pages if page["status"] == "complete" and page.get("html")]
    label_products(products, profile, True)
    classification = _classify_with_ollama(products, mfp_item)
    for product in products:
        product.setdefault("local_classification", {"status": "not_classified", "confidence": 0.0, "reason": "Not sent to local classifier.", "model": config.OLLAMA_MODEL})

    result = {
        "status": "complete", "mode": "open_source_experiment", "mfp_id": mfp_id, "mfp_name": mfp_item.get("name", ""), "retrieved_at": utc_now_iso(),
        "pipeline": {"discovery": "SearXNG", "crawler": "Crawl4AI", "classifier": f"Ollama / {config.OLLAMA_MODEL}"},
        "queries": [{key: value for key, value in run.items() if key != "candidates"} for run in runs], "discovered_candidates": candidates, "crawl_pages": [{key: value for key, value in page.items() if key != "html"} for page in pages],
        "products": products,
        "summary": {
            "queries": len(queries), "discovered_urls": len(candidates), "crawl_completed": sum(page["status"] == "complete" for page in pages),
            "crawl_failed": sum(page["status"] == "error" for page in pages), "products_extracted": len(products),
            "relevant": sum(p["relevance"]["status"] == "relevant" for p in products), "needs_review": sum(p["relevance"]["status"] == "needs_review" for p in products),
            "rejected": sum(p["relevance"]["status"] == "irrelevant" for p in products),
            "raw_or_derived": sum(p["local_classification"]["status"] in {"raw", "derived"} for p in products), "invalid": sum(p["local_classification"]["status"] == "invalid" for p in products),
            "ollama": classification,
        },
        "note": "Open-web discovery experiment only. It uses cached categories only to form representative test queries; it does not generate or change categories and does not use Google Shopping, Serper, Gemini, Groq, normal market scoring, or recommendations.",
    }
    result["comparison_file"] = str(_save(result))
    return result
