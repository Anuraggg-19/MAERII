"""
Atomic JSON persistence, run manifests, and rollback helpers.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import config
from .deep_models import utc_now_iso


def create_run_id(prefix: str = "deep") -> str:
    """Create a run id suitable for directories and manifests."""
    return f"{prefix}_{utc_now_iso().replace(':', '').replace('-', '')}"


def read_json(path: Path, default):
    """Read JSON from disk or return a deep-copyable default."""
    if not path.exists():
        return json.loads(json.dumps(default))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, payload):
    """Write JSON safely using a temp file and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(serialized)

    with open(temp_path, "r", encoding="utf-8") as handle:
        json.load(handle)

    temp_path.replace(path)


def snapshot_outputs(run_id: str) -> dict:
    """Snapshot canonical and sidecar outputs before an apply run."""
    backup_dir = config.BACKUPS_DIR / run_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    outputs = output_paths()
    defaults = {
        "enriched_mfp_data": [],
        "deep_enrichment_evidence": {},
        "material_relationships": [],
    }

    backup_paths = {}
    for key, path in outputs.items():
        backup_path = backup_dir / path.name
        if path.exists():
            shutil.copy2(path, backup_path)
        else:
            atomic_write_json(backup_path, defaults[key])
        backup_paths[key] = str(backup_path)

    return backup_paths


def output_paths() -> dict[str, Path]:
    """Return the canonical JSON outputs managed by deep enrichment."""
    return {
        "enriched_mfp_data": config.ENRICHED_JSON_PATH,
        "deep_enrichment_evidence": config.DEEP_ENRICHMENT_EVIDENCE_PATH,
        "material_relationships": config.MATERIAL_RELATIONSHIPS_PATH,
    }


def write_manifest(run_id: str, manifest: dict):
    """Persist a manifest for a deep-enrichment run."""
    run_dir = config.DEEP_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "manifest.json", manifest)


def write_preview(run_id: str, payload: dict):
    """Persist preview output for a non-apply run."""
    run_dir = config.DEEP_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "preview.json", payload)


def rollback_run(target_run_id: str) -> dict:
    """Restore canonical outputs from a prior backup snapshot."""
    backup_dir = config.BACKUPS_DIR / target_run_id
    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup directory not found for run '{target_run_id}'")

    outputs = output_paths()
    restored = {}
    for key, path in outputs.items():
        backup_path = backup_dir / path.name
        if not backup_path.exists():
            raise FileNotFoundError(f"Missing backup file for '{key}' in run '{target_run_id}'")

        payload = read_json(backup_path, None)
        atomic_write_json(path, payload)
        restored[key] = str(path)

    rollback_run_id = create_run_id(prefix="rollback")
    manifest = {
        "run_id": rollback_run_id,
        "mode": "rollback",
        "applied": True,
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "item_ids": [],
        "batch_size": 0,
        "resume_index": 0,
        "backup_paths": {},
        "output_paths": restored,
        "status": "complete",
        "errors": [],
        "restored_from_run_id": target_run_id,
    }
    write_manifest(rollback_run_id, manifest)
    return manifest
