"""
Data models, validation helpers, and scoring functions for market intelligence.
Follows Module 1 patterns: deterministic hashing, additive merging, confidence tracking.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from typing import Iterable, Optional


# ── Timestamp utility ───────────────────────────────────────────────────────

def utc_now_iso() -> str:
    """Return a stable UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ── Deterministic hashing (mirrors deep_models.stable_hash) ────────────────

def stable_hash(*parts: object) -> str:
    """Return a stable short hash from structured values."""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def make_product_id(url: str, title: str, price: float) -> str:
    """Generate a deterministic product ID from content."""
    return "mkp_" + stable_hash(url, title, price)


def make_source_id(mfp_id: int, query: str, source: str) -> str:
    """Generate a deterministic source record ID."""
    return "src_" + stable_hash(mfp_id, query, source)


# ── Price normalization ─────────────────────────────────────────────────────

_PRICE_PATTERN = re.compile(r"[\d,]+(?:\.\d{1,2})?")


def normalize_price(price_input) -> Optional[float]:
    """Parse price strings or values to float.

    Handles formats like: ₹599, Rs. 599.00, "1,299", 599.0, etc.
    Returns None if unparseable.
    """
    if price_input is None:
        return None
    if isinstance(price_input, (int, float)):
        value = float(price_input)
        return value if value >= 0 else None

    text = str(price_input).strip()
    if not text:
        return None

    match = _PRICE_PATTERN.search(text)
    if not match:
        return None

    try:
        value = float(match.group(0).replace(",", ""))
        return value if value >= 0 else None
    except ValueError:
        return None


# ── String helpers ──────────────────────────────────────────────────────────

def normalize_text(value: str) -> str:
    """Normalize text for dedupe and hashing."""
    return " ".join(str(value or "").strip().lower().split())


def dedupe_strings(values: Iterable[str]) -> list[str]:
    """Preserve order while deduping strings case-insensitively."""
    deduped = []
    seen = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


# ── Product normalization ───────────────────────────────────────────────────

def normalize_product(raw: dict) -> dict:
    """Clean and validate a raw scraped product into standard schema."""
    title = str(raw.get("title", "")).strip()
    url = str(raw.get("url") or raw.get("link") or "").strip()
    price = normalize_price(raw.get("price"))

    rating = raw.get("rating")
    if isinstance(rating, (int, float)):
        rating = round(float(rating), 1)
        if rating < 0 or rating > 5:
            rating = None
    else:
        try:
            rating = round(float(rating), 1) if rating else None
        except (ValueError, TypeError):
            rating = None

    review_count = raw.get("review_count") or raw.get("reviews") or raw.get("ratingCount")
    if isinstance(review_count, str):
        review_count = review_count.replace(",", "").strip()
        try:
            review_count = int(review_count)
        except ValueError:
            review_count = 0
    review_count = int(review_count or 0)

    product_id = make_product_id(url or title, title, price or 0.0)

    return {
        "product_id": product_id,
        "title": title,
        "url": url,
        "price": price,
        "currency": str(raw.get("currency", "INR")).strip().upper(),
        "rating": rating,
        "review_count": review_count,
        "seller": str(raw.get("seller") or raw.get("source") or "").strip(),
        "seller_type": _classify_seller(raw.get("seller") or raw.get("source") or ""),
        "category": str(raw.get("category", "")).strip(),
        "image_url": str(raw.get("imageUrl") or raw.get("image_url") or raw.get("thumbnail") or "").strip(),
        "source": _extract_source_domain(url),
        "attributes": _extract_attributes(raw),
        "extracted_at": utc_now_iso(),
        "confidence": 0.0,  # Set after LLM classification
    }


def _classify_seller(seller: str) -> str:
    """Classify seller type from name heuristics."""
    seller_lower = str(seller).lower()
    brand_hints = ("official", "store", "brand", "direct")
    marketplace_hints = ("amazon", "flipkart", "meesho", "jiomart")
    if any(hint in seller_lower for hint in brand_hints):
        return "brand"
    if any(hint in seller_lower for hint in marketplace_hints):
        return "marketplace"
    return "retail"


def _extract_source_domain(url: str) -> str:
    """Extract a clean domain from a URL."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _extract_attributes(raw: dict) -> list[dict]:
    """Extract product attributes from raw data."""
    attributes = []
    title_lower = str(raw.get("title", "")).lower()

    attribute_keywords = {
        "organic": ["organic", "certified organic"],
        "raw": ["raw", "unprocessed", "unrefined"],
        "pure": ["pure", "100% pure", "100%"],
        "natural": ["natural", "all natural"],
        "handmade": ["handmade", "hand made", "artisan", "handcrafted"],
        "tribal": ["tribal", "adivasi", "indigenous"],
        "forest": ["forest", "wild", "jungle"],
        "fair_trade": ["fair trade", "fairtrade"],
        "eco_friendly": ["eco", "sustainable", "biodegradable"],
    }

    for attr_name, keywords in attribute_keywords.items():
        if any(kw in title_lower for kw in keywords):
            attributes.append({"name": attr_name, "value": True})

    # Extract packaging/weight from title
    weight_match = re.search(
        r"(\d+)\s*(gm|gms|g|gram|grams|kg|kgs|ml|l|litre|liter|oz|piece|pcs|pack)",
        title_lower,
    )
    if weight_match:
        attributes.append({
            "name": "packaging",
            "value": f"{weight_match.group(1)}{weight_match.group(2)}",
        })

    return attributes


# ── Default schemas ─────────────────────────────────────────────────────────

def make_default_market_analysis() -> dict:
    """Return an empty market analysis skeleton for one MFP item."""
    return {
        "version": "v1",
        "status": "not_started",
        "last_analyzed_at": None,
        "search_queries": {
            "primary": "",
            "variations": [],
        },
        "market_products": [],
        "market_summary": {
            "total_products_found": 0,
            "avg_price": 0.0,
            "price_range": {"min": 0, "max": 0},
            "avg_rating": 0.0,
            "total_reviews": 0,
            "demand_score": 0.0,
            "trend": "stable",
            "top_attributes": [],
        },
        "competitor_analysis": {
            "top_brands": [],
            "market_gaps": [],
            "price_positioning": "unknown",
        },
        "confidence": {
            "product_count": 0.0,
            "pricing": 0.0,
            "demand_score": 0.0,
            "trend": 0.0,
        },
    }


# ── Demand scoring ──────────────────────────────────────────────────────────

def calculate_demand_score(products: list[dict], msp: float = 0.0) -> float:
    """Compute a demand score (0.0–1.0) from aggregated product signals.

    Weighted by:
      - review_volume (30%): normalized total review count
      - rating_quality (20%): average rating / 5.0
      - product_variety (20%): unique product count normalized
      - price_premium (15%): avg price vs. MSP
      - seller_diversity (15%): unique seller count normalized
    """
    if not products:
        return 0.0

    from . import config_market

    weights = config_market.DEMAND_SCORE_WEIGHTS

    # Review volume: log-scale normalization (cap at 10000 reviews)
    total_reviews = sum(p.get("review_count", 0) for p in products)
    import math
    review_score = min(math.log1p(total_reviews) / math.log1p(10000), 1.0)

    # Rating quality: average rating / 5.0
    ratings = [p["rating"] for p in products if p.get("rating") and p["rating"] > 0]
    rating_score = (statistics.mean(ratings) / 5.0) if ratings else 0.0

    # Product variety: normalized count (cap at 50)
    variety_score = min(len(products) / 50.0, 1.0)

    # Price premium: avg market price vs. MSP
    prices = [p["price"] for p in products if p.get("price") and p["price"] > 0]
    if prices and msp and msp > 0:
        avg_price = statistics.mean(prices)
        price_score = min(avg_price / (msp * 10), 1.0)  # 10x MSP = max score
    else:
        price_score = 0.3  # Neutral if no MSP data

    # Seller diversity: unique sellers normalized (cap at 20)
    unique_sellers = len({p.get("seller", "").lower() for p in products if p.get("seller")})
    seller_score = min(unique_sellers / 20.0, 1.0)

    score = (
        weights["review_volume"] * review_score
        + weights["rating_quality"] * rating_score
        + weights["product_variety"] * variety_score
        + weights["price_premium"] * price_score
        + weights["seller_diversity"] * seller_score
    )

    return round(min(max(score, 0.0), 1.0), 3)


def calculate_trend(products: list[dict]) -> str:
    """Infer trend direction from product signals.

    Uses review volume, rating quality, and stock availability as proxies.
    """
    if not products:
        return "stable"

    from . import config_market

    # High review counts + good ratings → rising
    total_reviews = sum(p.get("review_count", 0) for p in products)
    ratings = [p["rating"] for p in products if p.get("rating") and p["rating"] > 0]
    avg_rating = statistics.mean(ratings) if ratings else 0.0

    # Heuristic: rising if high engagement, declining if low
    import math
    engagement = min(math.log1p(total_reviews) / math.log1p(5000), 1.0)
    quality = avg_rating / 5.0 if avg_rating else 0.0
    signal = (engagement * 0.6) + (quality * 0.4)

    if signal >= config_market.TREND_THRESHOLDS["rising"]:
        return "rising"
    if signal >= config_market.TREND_THRESHOLDS["stable"]:
        return "stable"
    return "declining"


# ── Market summary builders ────────────────────────────────────────────────

def build_market_summary(products: list[dict]) -> dict:
    """Aggregate product list into market summary statistics.

    Uses IQR (Interquartile Range) filtering to exclude extreme price
    outliers before computing averages, so a single ₹50,000 item
    doesn't skew the market analysis.
    """
    if not products:
        return make_default_market_analysis()["market_summary"]

    raw_prices = [p["price"] for p in products if p.get("price") and p["price"] > 0]
    ratings = [p["rating"] for p in products if p.get("rating") and p["rating"] > 0]
    total_reviews = sum(p.get("review_count", 0) for p in products)

    # ── IQR price outlier removal ──────────────────────────────────────
    prices = _filter_price_outliers(raw_prices)

    # Top attributes
    attr_counts: dict[str, int] = {}
    for product in products:
        for attr in product.get("attributes", []):
            name = attr.get("name", "")
            if name and attr.get("value") is True:
                attr_counts[name] = attr_counts.get(name, 0) + 1
    top_attributes = sorted(attr_counts, key=attr_counts.get, reverse=True)[:8]

    return {
        "total_products_found": len(products),
        "avg_price": round(statistics.mean(prices), 2) if prices else 0.0,
        "price_range": {
            "min": round(min(prices), 2) if prices else 0,
            "max": round(max(prices), 2) if prices else 0,
        },
        "avg_rating": round(statistics.mean(ratings), 2) if ratings else 0.0,
        "total_reviews": total_reviews,
        "demand_score": 0.0,  # Set by pipeline
        "trend": "stable",     # Set by pipeline
        "top_attributes": top_attributes,
        "outliers_removed": len(raw_prices) - len(prices),
    }


def _filter_price_outliers(prices: list[float]) -> list[float]:
    """Remove extreme price outliers using IQR (Interquartile Range).

    Drops values below Q1 - 1.5*IQR and above Q3 + 1.5*IQR.
    Falls back to the original list if too few data points (<4).
    """
    if len(prices) < 4:
        return prices

    sorted_p = sorted(prices)
    n = len(sorted_p)
    q1 = sorted_p[n // 4]
    q3 = sorted_p[(3 * n) // 4]
    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    filtered = [p for p in prices if lower_bound <= p <= upper_bound]

    # Safety: never remove ALL prices — keep at least the original if filter is too aggressive
    return filtered if filtered else prices


def build_competitor_analysis(products: list[dict]) -> dict:
    """Extract competitive landscape from scraped products."""
    if not products:
        return make_default_market_analysis()["competitor_analysis"]

    # Top brands/sellers
    seller_counts: dict[str, int] = {}
    for p in products:
        seller = p.get("seller", "").strip()
        if seller:
            seller_counts[seller] = seller_counts.get(seller, 0) + 1
    top_brands = sorted(seller_counts, key=seller_counts.get, reverse=True)[:5]

    # Price positioning
    prices = [p["price"] for p in products if p.get("price") and p["price"] > 0]
    if prices:
        avg_price = statistics.mean(prices)
        if avg_price < 300:
            positioning = "budget"
        elif avg_price < 800:
            positioning = "mid-range"
        elif avg_price < 2000:
            positioning = "premium"
        else:
            positioning = "luxury"
    else:
        positioning = "unknown"

    # Market gaps (attributes rarely seen)
    attr_counts: dict[str, int] = {}
    for p in products:
        for attr in p.get("attributes", []):
            name = attr.get("name", "")
            if name:
                attr_counts[name] = attr_counts.get(name, 0) + 1
    total = len(products) or 1
    gaps = []
    potential_gaps = ["fair_trade", "eco_friendly", "tribal", "handmade", "organic"]
    for gap in potential_gaps:
        if attr_counts.get(gap, 0) / total < 0.15:
            gaps.append(gap.replace("_", " ").title() + " certification/labeling")

    return {
        "top_brands": top_brands,
        "market_gaps": gaps[:4],
        "price_positioning": positioning,
    }


# ── Confidence calculation ──────────────────────────────────────────────────

def calculate_confidence(products: list[dict]) -> dict:
    """Calculate confidence scores for market analysis fields."""
    if not products:
        return {"product_count": 0.0, "pricing": 0.0, "demand_score": 0.0, "trend": 0.0}

    # Product count confidence: more products → higher confidence
    count_conf = min(len(products) / 20.0, 1.0)

    # Pricing confidence: products with valid prices / total
    with_price = sum(1 for p in products if p.get("price") and p["price"] > 0)
    price_conf = with_price / len(products) if products else 0.0

    # Demand score confidence: based on review data availability
    with_reviews = sum(1 for p in products if p.get("review_count", 0) > 0)
    demand_conf = min(with_reviews / 10.0, 1.0)

    # Trend confidence: based on data richness
    trend_conf = min((count_conf + price_conf + demand_conf) / 3.0, 1.0)

    return {
        "product_count": round(count_conf, 3),
        "pricing": round(price_conf, 3),
        "demand_score": round(demand_conf, 3),
        "trend": round(trend_conf, 3),
    }


# ── Merge for incremental runs ─────────────────────────────────────────────

def merge_market_analysis(existing: Optional[dict], patch: dict) -> tuple[dict, bool]:
    """Merge a market analysis patch into existing data additively.

    Returns (merged_block, changed).
    """
    merged = copy.deepcopy(make_default_market_analysis())
    if isinstance(existing, dict):
        merged = _deep_update(merged, existing)

    before = copy.deepcopy(merged)
    if not patch:
        return merged, False

    # Merge products (dedupe by product_id)
    existing_ids = {p["product_id"] for p in merged.get("market_products", [])}
    for product in patch.get("market_products", []):
        if product.get("product_id") and product["product_id"] not in existing_ids:
            merged["market_products"].append(product)
            existing_ids.add(product["product_id"])

    # Overwrite summary and analysis if patch has them
    for key in ("market_summary", "competitor_analysis", "confidence", "search_queries"):
        if patch.get(key):
            merged[key] = patch[key]

    merged["version"] = patch.get("version", merged["version"])

    changed = merged != before
    if changed:
        merged["status"] = patch.get("status", "complete")
        merged["last_analyzed_at"] = patch.get("last_analyzed_at") or utc_now_iso()

    return merged, changed


def _deep_update(base: dict, overlay: dict) -> dict:
    """Recursively merge dictionaries."""
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
