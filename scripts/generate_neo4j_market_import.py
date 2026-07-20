"""
Generate Neo4j Cypher import for Module 2 (Market Intelligence) data.

Reads:
  - data/market_demand_data.json   (87 items with market analysis)
  - data/market_products.json      (3,759 scraped products)

Produces:
  - scripts/neo4j_market_import.cypher

Usage:
  python scripts/generate_neo4j_market_import.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MARKET_DEMAND_PATH = DATA_DIR / "market_demand_data.json"
MARKET_PRODUCTS_PATH = DATA_DIR / "market_products.json"
OUTPUT_PATH = PROJECT_ROOT / "scripts" / "neo4j_market_import.cypher"


def escape_cypher(value: str) -> str:
    if not isinstance(value, str):
        return str(value)
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")


def truncate(value: str, max_len: int = 120) -> str:
    clean = re.sub(r"[^\w\s\-/().,₹&]", "", str(value))
    return clean.strip()[:max_len]


def generate():
    print("[1/5] Loading market data...")
    with open(MARKET_DEMAND_PATH, "r", encoding="utf-8") as f:
        market_items = json.load(f)
    with open(MARKET_PRODUCTS_PATH, "r", encoding="utf-8") as f:
        all_products = json.load(f)

    # Only keep products that matched at least one MFP
    matched_products = [p for p in all_products if p.get("matched_mfp_ids")]
    print(f"       {len(market_items)} market items, {len(matched_products)} matched products (of {len(all_products)} total)")

    lines = []
    lines.append("// =============================================================")
    lines.append("// MAERII Module 2: Market Intelligence — Neo4j Import")
    lines.append(f"// {len(market_items)} items, {len(matched_products)} matched products")
    lines.append("// =============================================================")
    lines.append("")

    # ── Step 1: New constraints ─────────────────────────────────────────────
    print("[2/5] Generating constraints...")
    lines.append("// -- STEP 1: New constraints for market nodes --")
    lines.append("CREATE CONSTRAINT IF NOT EXISTS FOR (n:MarketProduct) REQUIRE n.product_id IS UNIQUE;")
    lines.append("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Seller) REQUIRE n.name IS UNIQUE;")
    lines.append("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Platform) REQUIRE n.name IS UNIQUE;")
    lines.append("CREATE CONSTRAINT IF NOT EXISTS FOR (n:MarketAttribute) REQUIRE n.name IS UNIQUE;")
    lines.append("")

    # ── Step 2: Update Material nodes with market properties ────────────────
    print("[3/5] Generating Material updates with market data...")
    lines.append("// -- STEP 2: Add market properties to existing Material nodes --")
    for item in market_items:
        mfp_id = item.get("mfp_id")
        ma = item.get("market_analysis", {})
        if ma.get("status") in (None, "", "not_started"):
            continue

        summary = ma.get("market_summary", {})
        competitor = ma.get("competitor_analysis", {})

        demand_score = summary.get("demand_score", 0.0)
        trend = escape_cypher(summary.get("trend", "unknown"))
        avg_price = summary.get("avg_price", 0.0)
        price_min = summary.get("price_range", {}).get("min", 0)
        price_max = summary.get("price_range", {}).get("max", 0)
        avg_rating = summary.get("avg_rating", 0.0)
        total_reviews = summary.get("total_reviews", 0)
        total_products = summary.get("total_products_found", 0)
        positioning = escape_cypher(competitor.get("price_positioning", "unknown"))

        lines.append(
            f"MATCH (m:Material {{mfp_id: {mfp_id}}}) "
            f"SET m.demand_score = {demand_score}, "
            f"m.market_trend = '{trend}', "
            f"m.avg_market_price = {avg_price}, "
            f"m.market_price_min = {price_min}, "
            f"m.market_price_max = {price_max}, "
            f"m.avg_rating = {avg_rating}, "
            f"m.total_reviews = {total_reviews}, "
            f"m.total_products_found = {total_products}, "
            f"m.price_positioning = '{positioning}';"
        )
    lines.append("")

    # ── Step 3: Create Platform nodes ───────────────────────────────────────
    print("[4/5] Generating platform, seller, and attribute nodes...")
    platforms = set()
    sellers = set()
    attributes = set()

    for p in matched_products:
        source = p.get("source", "").strip()
        if source:
            platforms.add(source)
        seller = p.get("seller", "").strip()
        if seller and len(seller) < 100:
            sellers.add(seller)
        for attr in p.get("attributes", []):
            name = attr.get("name", "").strip()
            if name and attr.get("value") is True:
                attributes.add(name)

    lines.append("// -- STEP 3: Create Platform nodes --")
    for platform in sorted(platforms):
        lines.append(f"CREATE (:Platform {{name: '{escape_cypher(platform)}'}});")
    lines.append("")

    lines.append("// -- STEP 4: Create Seller nodes (top sellers only) --")
    # Count seller frequency and only create top sellers to keep graph manageable
    seller_counts = {}
    for p in matched_products:
        s = p.get("seller", "").strip()
        if s and len(s) < 100:
            seller_counts[s] = seller_counts.get(s, 0) + 1
    # Keep sellers that appear 2+ times
    top_sellers = {s for s, count in seller_counts.items() if count >= 2}
    for seller in sorted(top_sellers):
        lines.append(f"CREATE (:Seller {{name: '{escape_cypher(seller)}'}});")
    lines.append("")

    lines.append("// -- STEP 5: Create MarketAttribute nodes --")
    for attr in sorted(attributes):
        lines.append(f"CREATE (:MarketAttribute {{name: '{escape_cypher(attr)}'}});")
    lines.append("")

    # ── Step 4: Create MarketProduct nodes + relationships ──────────────────
    print("[5/5] Generating product nodes and relationships...")
    lines.append("// -- STEP 6: Create MarketProduct nodes --")

    # To keep the graph manageable, only import products with confidence >= 0.5
    quality_products = [p for p in matched_products if p.get("confidence", 0) >= 0.5]
    print(f"       Importing {len(quality_products)} high-confidence products (of {len(matched_products)} matched)")

    for p in quality_products:
        pid = escape_cypher(p["product_id"])
        title = escape_cypher(truncate(p.get("title", ""), 150))
        price = p.get("price") or 0
        rating = p.get("rating") or 0
        reviews = p.get("review_count", 0)
        conf = p.get("confidence", 0)
        seller_type = escape_cypher(p.get("seller_type", ""))

        lines.append(
            f"CREATE (:MarketProduct {{product_id: '{pid}', title: '{title}', "
            f"price: {price}, rating: {rating}, review_count: {reviews}, "
            f"confidence: {conf}, seller_type: '{seller_type}'}});"
        )
    lines.append("")

    # ── Relationships: MarketProduct → Material ─────────────────────────────
    lines.append("// -- STEP 7: Link MarketProducts to Materials --")
    for p in quality_products:
        pid = escape_cypher(p["product_id"])
        for mfp_id in p.get("matched_mfp_ids", []):
            conf = p.get("confidence", 0)
            lines.append(
                f"MATCH (mp:MarketProduct {{product_id: '{pid}'}}), "
                f"(m:Material {{mfp_id: {mfp_id}}}) "
                f"CREATE (m)-[:HAS_MARKET_PRODUCT {{confidence: {conf}}}]->(mp);"
            )
    lines.append("")

    # ── Relationships: MarketProduct → Seller ───────────────────────────────
    lines.append("// -- STEP 8: Link MarketProducts to Sellers --")
    for p in quality_products:
        seller = p.get("seller", "").strip()
        if seller and seller in top_sellers:
            pid = escape_cypher(p["product_id"])
            lines.append(
                f"MATCH (mp:MarketProduct {{product_id: '{pid}'}}), "
                f"(s:Seller {{name: '{escape_cypher(seller)}'}}) "
                f"CREATE (mp)-[:SOLD_BY]->(s);"
            )
    lines.append("")

    # ── Relationships: MarketProduct → Platform ─────────────────────────────
    lines.append("// -- STEP 9: Link MarketProducts to Platforms --")
    for p in quality_products:
        source = p.get("source", "").strip()
        if source:
            pid = escape_cypher(p["product_id"])
            lines.append(
                f"MATCH (mp:MarketProduct {{product_id: '{pid}'}}), "
                f"(pl:Platform {{name: '{escape_cypher(source)}'}}) "
                f"CREATE (mp)-[:LISTED_ON]->(pl);"
            )
    lines.append("")

    # ── Relationships: MarketProduct → MarketAttribute ──────────────────────
    lines.append("// -- STEP 10: Link MarketProducts to Attributes --")
    for p in quality_products:
        pid = escape_cypher(p["product_id"])
        for attr in p.get("attributes", []):
            name = attr.get("name", "").strip()
            if name and attr.get("value") is True:
                lines.append(
                    f"MATCH (mp:MarketProduct {{product_id: '{pid}'}}), "
                    f"(a:MarketAttribute {{name: '{escape_cypher(name)}'}}) "
                    f"CREATE (mp)-[:HAS_ATTRIBUTE]->(a);"
                )
    lines.append("")

    # ── Market gap relationships ────────────────────────────────────────────
    lines.append("// -- STEP 11: Link Materials to market gaps --")
    for item in market_items:
        mfp_id = item.get("mfp_id")
        ma = item.get("market_analysis", {})
        gaps = ma.get("competitor_analysis", {}).get("market_gaps", [])
        for gap in gaps[:3]:  # Top 3 gaps per material
            gap_clean = escape_cypher(truncate(gap, 80))
            lines.append(
                f"MATCH (m:Material {{mfp_id: {mfp_id}}}) "
                f"MERGE (g:MarketGap {{name: '{gap_clean}'}}) "
                f"CREATE (m)-[:HAS_MARKET_GAP]->(g);"
            )
    lines.append("")

    lines.append("// -- IMPORT COMPLETE --")
    lines.append(f"// Material nodes updated with market properties: {len(market_items)}")
    lines.append(f"// MarketProduct nodes created: {len(quality_products)}")
    lines.append(f"// Seller nodes: {len(top_sellers)}, Platform nodes: {len(platforms)}, Attribute nodes: {len(attributes)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[OK] Market Cypher written to: {OUTPUT_PATH}")
    print(f"     Total lines: {len(lines)}")


if __name__ == "__main__":
    generate()
