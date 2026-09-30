// Additive schema: existing Material nodes and graph data remain untouched.
CREATE CONSTRAINT intelligence_run_id_unique IF NOT EXISTS
FOR (r:IntelligenceRun) REQUIRE r.run_id IS UNIQUE;

CREATE INDEX intelligence_run_lookup IF NOT EXISTS
FOR (r:IntelligenceRun) ON (r.task, r.created_at);
