"""Quick test of the Neo4j connection."""
import sys
sys.path.insert(0, ".")

from app.neo4j_client import list_materials

try:
    materials = list_materials()
    print(f"SUCCESS: Got {len(materials)} materials")
    if materials:
        print(f"  First: {materials[0]}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
