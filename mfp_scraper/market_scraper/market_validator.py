"""
Validation and quality reporting for market intelligence outputs.
Follows Module 1's validator.py patterns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from . import config_market


# ── Single item validation ──────────────────────────────────────────────────

def validate_market_item(item: dict) -> dict:
    """Validate a single MFP item's market analysis.

    Returns a report dict with completeness score, issues, and flags.
    """
    report = {
        "mfp_id": item.get("mfp_id"),
        "name": item.get("name", ""),
        "completeness": 0.0,
        "issues": [],
        "warnings": [],
    }

    analysis = item.get("market_analysis")
    if not analysis or not isinstance(analysis, dict):
        report["issues"].append("Missing market_analysis block")
        return report

    # Check required fields
    required_checks = {
        "status": analysis.get("status") not in (None, "", "not_started"),
        "last_analyzed_at": bool(analysis.get("last_analyzed_at")),
        "market_products": bool(analysis.get("market_products")),
        "market_summary": bool(analysis.get("market_summary")),
        "competitor_analysis": bool(analysis.get("competitor_analysis")),
        "confidence": bool(analysis.get("confidence")),
        "search_queries": bool(analysis.get("search_queries")),
    }

    filled = sum(1 for v in required_checks.values() if v)
    total = len(required_checks)
    report["completeness"] = round(filled / total, 2) if total > 0 else 0.0

    # Report missing fields
    for field, present in required_checks.items():
        if not present:
            report["issues"].append(f"Missing or empty: {field}")

    # Validate products
    products = analysis.get("market_products", [])
    if products:
        _validate_products(products, report)

    # Validate market summary
    summary = analysis.get("market_summary", {})
    if summary:
        _validate_summary(summary, report)

    # Validate confidence scores
    confidence = analysis.get("confidence", {})
    if confidence:
        _validate_confidence(confidence, report)

    return report


def _validate_products(products: list[dict], report: dict):
    """Validate individual product entries."""
    seen_ids = set()
    for i, product in enumerate(products):
        pid = product.get("product_id", "")

        # Check for duplicate IDs
        if pid in seen_ids:
            report["warnings"].append(f"Duplicate product_id: {pid}")
        seen_ids.add(pid)

        # Check required product fields
        if not product.get("title"):
            report["issues"].append(f"Product {i}: missing title")

        # Validate price
        price = product.get("price")
        if price is not None and (not isinstance(price, (int, float)) or price < 0):
            report["issues"].append(f"Product {i}: invalid price ({price})")

        # Validate URL
        url = product.get("url", "")
        if url and not _is_valid_url(url):
            report["warnings"].append(f"Product {i}: malformed URL")

        # Validate rating
        rating = product.get("rating")
        if rating is not None:
            if not isinstance(rating, (int, float)) or rating < 0 or rating > 5:
                report["warnings"].append(f"Product {i}: rating out of range ({rating})")

        # Validate confidence
        conf = product.get("confidence", 0)
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            report["warnings"].append(f"Product {i}: confidence out of [0,1] ({conf})")


def _validate_summary(summary: dict, report: dict):
    """Validate market summary statistics."""
    demand_score = summary.get("demand_score", 0)
    if not isinstance(demand_score, (int, float)) or demand_score < 0 or demand_score > 1:
        report["issues"].append(f"Invalid demand_score: {demand_score}")

    avg_price = summary.get("avg_price", 0)
    if isinstance(avg_price, (int, float)) and avg_price < 0:
        report["issues"].append(f"Negative avg_price: {avg_price}")

    trend = summary.get("trend", "")
    if trend not in ("rising", "stable", "declining"):
        report["warnings"].append(f"Unknown trend value: {trend}")


def _validate_confidence(confidence: dict, report: dict):
    """Validate confidence score ranges."""
    for field, score in confidence.items():
        if not isinstance(score, (int, float)):
            report["warnings"].append(f"Non-numeric confidence for {field}: {score}")
        elif score < 0 or score > 1:
            report["warnings"].append(f"Confidence out of [0,1] for {field}: {score}")


def _is_valid_url(url: str) -> bool:
    """Check if a URL is well-formed."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


# ── Full dataset validation ─────────────────────────────────────────────────

def validate_market_outputs(market_data: list[dict], market_products: list[dict]) -> dict:
    """Validate the complete market demand outputs.

    Returns a summary report compatible with Module 1 validation patterns.
    """
    item_reports = [validate_market_item(item) for item in market_data]

    total = len(market_data)
    with_analysis = sum(
        1 for item in market_data
        if item.get("market_analysis", {}).get("status") not in (None, "", "not_started")
    )
    fully_complete = sum(1 for r in item_reports if r["completeness"] == 1.0)
    avg_completeness = (
        sum(r["completeness"] for r in item_reports) / total if total else 0.0
    )

    # Coverage metrics
    coverage = {
        "demand_scores": sum(
            1 for item in market_data
            if item.get("market_analysis", {}).get("market_summary", {}).get("demand_score", 0) > 0
        ),
        "pricing_data": sum(
            1 for item in market_data
            if item.get("market_analysis", {}).get("market_summary", {}).get("avg_price", 0) > 0
        ),
        "competitor_analysis": sum(
            1 for item in market_data
            if item.get("market_analysis", {}).get("competitor_analysis", {}).get("top_brands")
        ),
        "products_with_confidence": sum(
            1 for p in market_products if p.get("confidence", 0) > 0.5
        ),
    }

    # Items needing review
    needs_review = [
        r for r in item_reports
        if r["completeness"] < 0.7 or r["issues"]
    ]

    # Product-level stats
    total_products = len(market_products)
    products_with_price = sum(1 for p in market_products if p.get("price") and p["price"] > 0)
    products_with_rating = sum(1 for p in market_products if p.get("rating") and p["rating"] > 0)
    unique_product_ids = len({p.get("product_id", "") for p in market_products})

    return {
        "total_mfps": total,
        "mfps_with_market_analysis": with_analysis,
        "fully_complete": fully_complete,
        "average_completeness": round(avg_completeness, 2),
        "coverage": coverage,
        "total_products_scraped": total_products,
        "unique_product_ids": unique_product_ids,
        "products_with_price": products_with_price,
        "products_with_rating": products_with_rating,
        "avg_products_per_mfp": round(total_products / total, 1) if total else 0,
        "items_needing_review": len(needs_review),
        "review_items": [
            {
                "name": r["name"],
                "completeness": r["completeness"],
                "issues": r["issues"],
                "warnings": r["warnings"],
            }
            for r in needs_review[:15]
        ],
        "all_reports": item_reports,
    }


# ── Reporting ───────────────────────────────────────────────────────────────

def print_market_validation_report(summary: dict):
    """Print a human-friendly market validation report."""
    print("\n" + "=" * 60)
    print("  MARKET INTELLIGENCE VALIDATION REPORT")
    print("=" * 60)

    print(f"\n  Total MFP items:             {summary['total_mfps']}")
    print(f"  With market analysis:        {summary['mfps_with_market_analysis']}")
    print(f"  Fully complete:              {summary['fully_complete']}")
    print(f"  Average completeness:        {summary['average_completeness']:.0%}")

    print(f"\n  Products scraped:            {summary['total_products_scraped']}")
    print(f"  Unique product IDs:          {summary['unique_product_ids']}")
    print(f"  Products with price:         {summary['products_with_price']}")
    print(f"  Products with rating:        {summary['products_with_rating']}")
    print(f"  Avg products per MFP:        {summary['avg_products_per_mfp']}")

    print("\n  Coverage:")
    for key, value in summary["coverage"].items():
        print(f"    {key:30s} {value}/{summary['total_mfps']}")

    print(f"\n  Items needing review:        {summary['items_needing_review']}")

    if summary["review_items"]:
        print(f"\n  Flagged Items ({len(summary['review_items'])}):")
        for item in summary["review_items"][:10]:
            print(f"\n    * {item['name']} (completeness: {item['completeness']:.0%})")
            for issue in item["issues"][:3]:
                print(f"      [!] {issue}")
            for warning in item["warnings"][:2]:
                print(f"      [~] {warning}")

    print("\n" + "=" * 60)


def save_market_validation_report(summary: dict, path: Optional[Path] = None):
    """Persist market validation report to JSON."""
    path = path or config_market.MARKET_ANALYSIS_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, indent=2, ensure_ascii=False, fp=handle)
    print(f"[OK] Validation report saved to {path}")
