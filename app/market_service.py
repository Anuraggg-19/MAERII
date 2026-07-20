"""
Real-time market analysis service for the MAERII demo.

Wraps the existing market_scraper module to provide on-demand
market intelligence for a single MFP item. No data is persisted —
results live only in the API response.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient
from mfp_scraper.market_scraper.market_extractor import MarketExtractor
from mfp_scraper.market_scraper.market_models import (
    build_competitor_analysis,
    build_market_summary,
    calculate_confidence,
    calculate_demand_score,
    calculate_trend,
)


# ── Enriched data loader (for LLM context) ──────────────────────────────────

_mfp_items_cache: Optional[list[dict]] = None

def _load_mfp_items() -> list[dict]:
    """Load the enriched MFP dataset (cached after first call)."""
    global _mfp_items_cache
    if _mfp_items_cache is None:
        enriched_path = PROJECT_ROOT / "data" / "enriched_mfp_data.json"
        with open(enriched_path, "r", encoding="utf-8") as f:
            _mfp_items_cache = json.load(f)
    return _mfp_items_cache


def _find_mfp_item(mfp_id: int) -> Optional[dict]:
    """Find a single MFP item by ID from the enriched dataset."""
    for item in _load_mfp_items():
        if item.get("mfp_id") == mfp_id:
            return item
    return None


# ── Real-time market analysis ────────────────────────────────────────────────

def analyze_market_realtime(mfp_id: int) -> dict:
    """Run real-time market analysis for a single MFP item.

    Steps:
      1. Fetch products from Serper Shopping API
      2. Classify products against MFP categories via LLM
      3. Calculate demand score, trend, competitor analysis
      4. Return structured result (not persisted)

    Returns a dict with status, market_summary, competitor_analysis,
    top_products, and timing info.
    """
    start_time = time.time()

    mfp_item = _find_mfp_item(mfp_id)
    if not mfp_item:
        return {
            "status": "error",
            "error": f"MFP item with id {mfp_id} not found in enriched dataset.",
        }

    all_mfp_items = _load_mfp_items()

    # 1. Fetch products
    try:
        client = EcommerceClient()
    except ValueError as e:
        return {
            "status": "error",
            "error": f"Serper API not configured: {e}",
        }

    fetch_result = client.fetch_products_for_mfp(mfp_item)
    queries = fetch_result["queries"]
    raw_products = fetch_result["products"]

    if not raw_products:
        return {
            "status": "no_results",
            "queries": queries,
            "products_found": 0,
            "products_matched": 0,
            "market_summary": None,
            "competitor_analysis": None,
            "top_products": [],
            "elapsed_seconds": round(time.time() - start_time, 1),
        }

    # 2. LLM Classification
    extractor = MarketExtractor()
    classified_products = extractor.classify_products(
        raw_products, all_mfp_items, target_mfp_id=mfp_id
    )

    matched_products = [
        p for p in classified_products
        if mfp_id in p.get("matched_mfp_ids", [])
    ]

    # 3. Market Analysis
    summary = build_market_summary(matched_products)
    competitor_analysis = build_competitor_analysis(matched_products)
    confidence = calculate_confidence(matched_products)

    msp = mfp_item.get("msp", 0.0)
    summary["demand_score"] = calculate_demand_score(matched_products, msp)
    summary["trend"] = calculate_trend(matched_products)

    # 4. LLM deeper insights
    llm_analysis = extractor.analyze_market(mfp_item, matched_products)
    if llm_analysis:
        ca = llm_analysis.get("competitor_analysis", {})
        if "market_gaps" in ca:
            combined_gaps = list(set(
                competitor_analysis.get("market_gaps", []) + ca["market_gaps"]
            ))
            competitor_analysis["market_gaps"] = combined_gaps[:5]
        if "price_positioning" in ca:
            competitor_analysis["price_positioning"] = ca["price_positioning"]

        competitor_analysis["llm_insights"] = llm_analysis.get("opportunities", [])
        competitor_analysis["demand_drivers"] = (
            llm_analysis.get("demand_indicators", {}).get("key_demand_drivers", [])
        )

    # 5. Build top products for display (limit to 10)
    top_products = sorted(
        matched_products,
        key=lambda p: (p.get("confidence", 0), p.get("review_count", 0)),
        reverse=True,
    )[:10]

    display_products = []
    for p in top_products:
        display_products.append({
            "title": p.get("title", ""),
            "price": p.get("price"),
            "rating": p.get("rating"),
            "review_count": p.get("review_count", 0),
            "seller": p.get("seller", ""),
            "source": p.get("source", ""),
            "url": p.get("url", ""),
            "image_url": p.get("image_url", ""),
            "attributes": [
                a["name"] for a in p.get("attributes", [])
                if a.get("value") is True
            ],
            "confidence": p.get("confidence", 0),
        })

    elapsed = round(time.time() - start_time, 1)

    return {
        "status": "complete",
        "mfp_id": mfp_id,
        "mfp_name": mfp_item["name"],
        "queries": queries,
        "products_found": len(raw_products),
        "products_matched": len(matched_products),
        "market_summary": summary,
        "competitor_analysis": competitor_analysis,
        "confidence": confidence,
        "top_products": display_products,
        "elapsed_seconds": elapsed,
        "provider": extractor.describe_provider(),
    }
