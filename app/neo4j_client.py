"""
Neo4j client for the MAERII Knowledge Engine demo.

Provides Cypher queries to fetch Module 1 data:
- Material listing (all 87 MFPs)
- Material detail + graph neighbors (states, skills, products, districts, clusters)

Ignores all Module 2 (Market*) nodes/relationships.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional

from neo4j import GraphDatabase


# ── Connection ───────────────────────────────────────────────────────────────

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Neo4j123")

_driver: Optional[GraphDatabase.driver] = None


def get_driver():
    """Lazy-initialise and return the Neo4j driver (singleton)."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def session():
    """Yield a Neo4j session, auto-closing after use."""
    driver = get_driver()
    s = driver.session()
    try:
        yield s
    finally:
        s.close()


# ── Queries ──────────────────────────────────────────────────────────────────

def list_materials() -> list[dict]:
    """Return all 87 Materials with core properties for the sidebar list."""
    query = """
    MATCH (m:Material)
    OPTIONAL MATCH (m)-[:BELONGS_TO_GROUP]->(g:MaterialGroup)
    RETURN m.mfp_id       AS mfp_id,
           m.name          AS name,
           m.scientific_name AS scientific_name,
           m.category       AS category,
           m.msp            AS msp,
           m.unit           AS unit,
           m.availability_band AS availability_band,
           g.name           AS material_group
    ORDER BY m.mfp_id
    """
    with session() as s:
        result = s.run(query)
        return [dict(record) for record in result]


def get_material_detail(mfp_id: int) -> Optional[dict]:
    """Return full material detail + all graph neighbors for one MFP item."""

    # 1. Core material properties
    mat_query = """
    MATCH (m:Material {mfp_id: $mfp_id})
    RETURN m.mfp_id         AS mfp_id,
           m.name            AS name,
           m.scientific_name AS scientific_name,
           m.category        AS category,
           m.msp             AS msp,
           m.unit            AS unit,
           m.description     AS description,
           m.season          AS season,
           m.shelf_life      AS shelf_life,
           m.availability_band AS availability_band
    """

    # 2. Graph neighbors — one query per relationship type
    states_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:AVAILABLE_IN]->(s:State)
    RETURN s.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, s.name
    """

    skills_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:PROCESSED_BY]->(s:Skill)
    RETURN s.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, s.name
    """

    current_products_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:USED_FOR_PRODUCT]->(p:Product)
    RETURN p.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, p.name
    """

    potential_products_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:COULD_ENABLE_PRODUCT]->(p:Product)
    RETURN p.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, p.name
    """

    group_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:BELONGS_TO_GROUP]->(g:MaterialGroup)
    RETURN g.name AS name
    """

    districts_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:AVAILABLE_IN]->(d:District)
    RETURN d.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, d.name
    """

    clusters_query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r:LINKED_TO]->(c:Cluster)
    RETURN c.name AS name, r.confidence AS confidence
    ORDER BY r.confidence DESC, c.name
    """

    with session() as s:
        # Core material
        mat_result = s.run(mat_query, mfp_id=mfp_id)
        mat_record = mat_result.single()
        if mat_record is None:
            return None
        material = dict(mat_record)

        # Graph neighbors
        def collect(query):
            return [dict(r) for r in s.run(query, mfp_id=mfp_id)]

        graph = {
            "states": collect(states_query),
            "skills": collect(skills_query),
            "current_products": collect(current_products_query),
            "potential_products": collect(potential_products_query),
            "material_group": None,
            "districts": collect(districts_query),
            "clusters": collect(clusters_query),
        }

        # Material group (single value)
        group_result = s.run(group_query, mfp_id=mfp_id)
        group_record = group_result.single()
        if group_record:
            graph["material_group"] = group_record["name"]

    return {"material": material, "graph": graph}


def get_graph_data(mfp_id: int) -> Optional[dict]:
    """Return nodes and edges for graph visualization of one MFP item."""

    query = """
    MATCH (m:Material {mfp_id: $mfp_id})-[r]->(n)
    WHERE NOT n:MarketProduct AND NOT n:Seller AND NOT n:Platform
          AND NOT n:MarketAttribute AND NOT n:MarketGap
    RETURN m.name AS source_name,
           m.mfp_id AS source_id,
           type(r) AS rel_type,
           r.confidence AS confidence,
           labels(n)[0] AS target_label,
           n.name AS target_name
    """

    with session() as s:
        result = s.run(query, mfp_id=mfp_id)
        records = [dict(r) for r in result]

    if not records:
        return None

    # Build nodes and edges for the frontend
    nodes = [{"id": f"material_{mfp_id}", "label": records[0]["source_name"], "type": "Material"}]
    edges = []
    seen_nodes = {f"material_{mfp_id}"}

    for r in records:
        node_id = f"{r['target_label']}_{r['target_name']}"
        if node_id not in seen_nodes:
            nodes.append({
                "id": node_id,
                "label": r["target_name"],
                "type": r["target_label"],
            })
            seen_nodes.add(node_id)

        edges.append({
            "from": f"material_{mfp_id}",
            "to": node_id,
            "label": r["rel_type"].replace("_", " ").title(),
            "confidence": r["confidence"],
        })

    return {"nodes": nodes, "edges": edges}
