"""
Generate a Neo4j Cypher import script from the MAERII Knowledge Engine datasets.

Reads:
  - data/enriched_mfp_data.json      (87 MFP items)
  - data/material_relationships.json  (1,259 relationship edges)

Produces:
  - scripts/neo4j_import.cypher       (ready to paste into Neo4j Browser)

Usage:
  python scripts/generate_neo4j_import.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path


# ── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENRICHED_PATH = DATA_DIR / "enriched_mfp_data.json"
RELATIONSHIPS_PATH = DATA_DIR / "material_relationships.json"
OUTPUT_PATH = PROJECT_ROOT / "scripts" / "neo4j_import.cypher"


def escape_cypher(value: str) -> str:
    """Escape single quotes and backslashes for Cypher string literals."""
    if not isinstance(value, str):
        return str(value)
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")


def sanitize_label(value: str) -> str:
    """Clean a string for use as a short display label."""
    clean = re.sub(r"[^\w\s\-/().,]", "", value)
    return clean.strip()[:120]


def generate_cypher():
    """Main generation function."""
    print("[1/5] Loading datasets...")
    with open(ENRICHED_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    with open(RELATIONSHIPS_PATH, "r", encoding="utf-8") as f:
        edges = json.load(f)

    print(f"       Loaded {len(items)} items, {len(edges)} edges.")

    # ── Collect unique nodes ────────────────────────────────────────────────
    print("[2/5] Extracting unique nodes...")
    states = set()
    skills = set()
    current_products = set()
    potential_products = set()
    material_groups = set()
    districts = set()
    clusters = set()

    for edge in edges:
        target_type = edge.get("target_type", "")
        target_value = edge.get("target_value", "").strip()
        if not target_value:
            continue

        if target_type == "state":
            states.add(target_value)
        elif target_type == "skill":
            skills.add(target_value)
        elif target_type == "current_product":
            current_products.add(target_value)
        elif target_type == "potential_product":
            potential_products.add(target_value)
        elif target_type == "material_group":
            material_groups.add(target_value)
        elif target_type == "district":
            districts.add(target_value)
        elif target_type == "cluster":
            clusters.add(target_value)

    all_products = current_products | potential_products

    print(f"       States: {len(states)}, Skills: {len(skills)}, Products: {len(all_products)}, Groups: {len(material_groups)}, Districts: {len(districts)}, Clusters: {len(clusters)}")

    # ── Build Cypher ────────────────────────────────────────────────────────
    lines = []

    # Header
    lines.append("// =============================================================")
    lines.append("// MAERII Raw Material Knowledge Engine — Neo4j Import Script")
    lines.append(f"// Generated from {len(items)} MFP items and {len(edges)} relationship edges")
    lines.append("// =============================================================")
    lines.append("")

    # ── Step 0: Clean slate ─────────────────────────────────────────────────
    lines.append("// -- STEP 0: Clear existing data (run this ONCE on a fresh DB) --")
    lines.append("MATCH (n) DETACH DELETE n;")
    lines.append("")

    # ── Step 1: Constraints & Indexes ───────────────────────────────────────
    print("[3/5] Generating constraints & indexes...")
    lines.append("// -- STEP 1: Create constraints and indexes --")
    constraints = [
        ("Material",      "mfp_id"),
        ("State",         "name"),
        ("Skill",         "name"),
        ("Product",       "name"),
        ("MaterialGroup", "name"),
        ("District",      "name"),
        ("Cluster",       "name"),
    ]
    for label, prop in constraints:
        lines.append(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE;")
    lines.append("")

    # ── Step 2: Create Material nodes ───────────────────────────────────────
    print("[4/5] Generating node creation statements...")
    lines.append("// -- STEP 2: Create Material nodes --")
    for item in items:
        mfp_id = item["mfp_id"]
        name = escape_cypher(item["name"])
        sci = escape_cypher(item.get("scientific_name") or "")
        cat = escape_cypher(item.get("category") or "")
        msp = item.get("msp") or 0
        unit = escape_cypher(item.get("unit") or "")
        desc = escape_cypher((item.get("description") or "")[:300])
        season = escape_cypher(item.get("season") or "")
        shelf = escape_cypher(item.get("shelf_life") or "")

        # Deep enrichment availability
        deep = item.get("deep_enrichment", {})
        avail = deep.get("availability", {})
        band = escape_cypher(avail.get("band", "unknown"))

        lines.append(
            f"CREATE (:Material {{mfp_id: {mfp_id}, name: '{name}', "
            f"scientific_name: '{sci}', category: '{cat}', "
            f"msp: {msp}, unit: '{unit}', "
            f"description: '{desc}', "
            f"season: '{season}', shelf_life: '{shelf}', "
            f"availability_band: '{band}'}});"
        )
    lines.append("")

    # ── Step 3: Create auxiliary nodes ───────────────────────────────────────
    lines.append("// -- STEP 3: Create State nodes --")
    for s in sorted(states):
        lines.append(f"CREATE (:State {{name: '{escape_cypher(s)}'}});")
    lines.append("")

    lines.append("// -- STEP 4: Create Skill nodes --")
    for s in sorted(skills):
        lines.append(f"CREATE (:Skill {{name: '{escape_cypher(s)}'}});")
    lines.append("")

    lines.append("// -- STEP 5: Create Product nodes --")
    for p in sorted(all_products):
        label = sanitize_label(p)
        lines.append(f"CREATE (:Product {{name: '{escape_cypher(p)}', label: '{escape_cypher(label)}'}});")
    lines.append("")

    lines.append("// -- STEP 6: Create MaterialGroup nodes --")
    for g in sorted(material_groups):
        lines.append(f"CREATE (:MaterialGroup {{name: '{escape_cypher(g)}'}});")
    lines.append("")

    if districts:
        lines.append("// -- STEP 7: Create District nodes --")
        for d in sorted(districts):
            lines.append(f"CREATE (:District {{name: '{escape_cypher(d)}'}});")
        lines.append("")

    if clusters:
        lines.append("// -- STEP 8: Create Cluster nodes --")
        for c in sorted(clusters):
            lines.append(f"CREATE (:Cluster {{name: '{escape_cypher(c)}'}});")
        lines.append("")

    # ── Step 4: Create relationships ────────────────────────────────────────
    print("[5/5] Generating relationship statements...")
    lines.append("// -- STEP 9: Create relationships --")

    # Map edge_type + target_type → (Neo4j relationship type, target node label)
    edge_mapping = {
        ("available_in", "state"):           ("AVAILABLE_IN",         "State"),
        ("available_in", "district"):        ("AVAILABLE_IN",         "District"),
        ("processed_by", "skill"):           ("PROCESSED_BY",         "Skill"),
        ("used_for_product", "current_product"):    ("USED_FOR_PRODUCT",     "Product"),
        ("could_enable_product", "potential_product"): ("COULD_ENABLE_PRODUCT", "Product"),
        ("belongs_to_group", "material_group"):     ("BELONGS_TO_GROUP",     "MaterialGroup"),
        ("linked_to", "cluster"):            ("LINKED_TO",            "Cluster"),
        ("linked_to", "district"):           ("LINKED_TO",            "District"),
    }

    for edge in edges:
        mfp_id = edge.get("source_mfp_id")
        edge_type = edge.get("edge_type", "")
        target_type = edge.get("target_type", "")
        target_value = edge.get("target_value", "").strip()
        confidence = edge.get("confidence", 0)
        evidence_id = escape_cypher(edge.get("evidence_id", ""))

        key = (edge_type, target_type)
        mapping = edge_mapping.get(key)

        if not mapping or not target_value:
            continue

        rel_type, target_label = mapping
        match_prop = "mfp_id" if target_label == "Material" else "name"
        match_val = f"{mfp_id}" if target_label == "Material" else f"'{escape_cypher(target_value)}'"

        lines.append(
            f"MATCH (m:Material {{mfp_id: {mfp_id}}}), (t:{target_label} {{{match_prop}: {match_val}}}) "
            f"CREATE (m)-[:{rel_type} {{confidence: {confidence}, evidence_id: '{evidence_id}'}}]->(t);"
        )

    lines.append("")
    lines.append("// -- IMPORT COMPLETE --")
    lines.append(f"// Total nodes created: {len(items)} Materials + {len(states)} States + {len(skills)} Skills + {len(all_products)} Products + {len(material_groups)} Groups + {len(districts)} Districts + {len(clusters)} Clusters")
    lines.append(f"// Total relationships created: {len(edges)}")
    lines.append("// Run ':schema' in Neo4j Browser to verify constraints.")
    lines.append("// Run 'MATCH (n) RETURN labels(n), count(n)' to verify node counts.")

    # ── Write output ────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n[OK] Cypher script written to: {OUTPUT_PATH}")
    print(f"     Total lines: {len(lines)}")
    print(f"     Paste into Neo4j Browser to import.")


if __name__ == "__main__":
    generate_cypher()
