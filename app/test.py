from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://127.0.0.1:7687",
    auth=("neo4j", "Neo4j123")
)

try:
    driver.verify_connectivity()
    print("SUCCESS")
except Exception as e:
    print("FAILED:", e)

driver.close()