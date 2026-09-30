"""Versioned Neo4j storage for categories, market, recommendation, and enhancement runs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.neo4j_client import session


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def save_run(mfp_id: int, task: str, payload: dict[str, Any], *, provider: str, metadata: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Save an immutable completed run; degrade safely while Neo4j is offline."""
    run_id = str(uuid.uuid4())
    try:
        with session() as database:
            record = database.run(
                """
                MATCH (m:Material {mfp_id: $mfp_id})
                CREATE (r:IntelligenceRun {
                    run_id: $run_id, task: $task, provider: $provider,
                    created_at: $created_at, status: 'complete',
                    payload_json: $payload_json, metadata_json: $metadata_json
                })
                CREATE (m)-[:HAS_INTELLIGENCE_RUN]->(r)
                RETURN r.run_id AS run_id
                """,
                mfp_id=mfp_id, run_id=run_id, task=task, provider=provider,
                created_at=_now(), payload_json=json.dumps(payload, ensure_ascii=False),
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            ).single()
        return record["run_id"] if record else None
    except Exception as exc:
        print(f"  [IntelligenceStore] Persistence skipped: {exc}")
        return None


def latest_payload(mfp_id: int, task: str) -> Optional[dict[str, Any]]:
    """Return the newest persisted result, including minimal run metadata."""
    try:
        with session() as database:
            record = database.run(
                """
                MATCH (:Material {mfp_id: $mfp_id})-[:HAS_INTELLIGENCE_RUN]->(r:IntelligenceRun {task: $task, status: 'complete'})
                RETURN r.payload_json AS payload_json, r.run_id AS run_id,
                       r.provider AS provider, r.created_at AS created_at
                ORDER BY r.created_at DESC LIMIT 1
                """, mfp_id=mfp_id, task=task,
            ).single()
        if not record:
            return None
        payload = json.loads(record["payload_json"])
        if isinstance(payload, dict):
            payload.setdefault("_persistence", {
                "run_id": record["run_id"], "provider": record["provider"], "created_at": record["created_at"],
            })
            return payload
    except Exception as exc:
        print(f"  [IntelligenceStore] Read skipped: {exc}")
    return None
