"""
Data models and helpers for additive deep enrichment.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from . import config


DATASET_SOURCE_PREFIX = "dataset://enriched_mfp_data.json"

SOURCE_PRIORITIES = {
    "official": 0,
    "institutional": 1,
    "research": 2,
    "supporting": 3,
    "existing_dataset": 4,
    "unknown": 5,
}

OFFICIAL_DOMAIN_HINTS = (
    "gov.in",
    "nic.in",
)

INSTITUTIONAL_DOMAIN_HINTS = (
    "gbif.org",
    "powo.science.kew.org",
    "indiabiodiversity.org",
    "icfre.org",
    "icfre.gov.in",
    "icar.gov.in",
    "nmpb.nic.in",
)

RESEARCH_DOMAIN_HINTS = (
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "researchgate.net",
    "sciencedirect.com",
    "springer.com",
    "mdpi.com",
    "academia.edu",
    "frontiersin.org",
)

QUANTITY_RECORD_KEYS = ("value", "unit", "year", "scope", "metric_type")


def utc_now_iso() -> str:
    """Return a stable UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_default_deep_enrichment() -> dict:
    """Default additive enrichment block for a material record."""
    return {
        "version": "v1",
        "status": "not_started",
        "availability": {
            "band": "unknown",
            "quantity_records": [],
        },
        "geography": {
            "districts": [],
            "clusters": [],
        },
        "relationship_summary": {
            "related_regions": [],
            "related_products": [],
            "related_skills": [],
            "related_material_groups": [],
        },
        "confidence": {
            "availability": 0.0,
            "geography": 0.0,
            "relationships": 0.0,
        },
        "evidence_refs": [],
        "last_updated_at": None,
    }


def clone_item_without_deep(item: dict) -> dict:
    """Return a copy of an item without the additive block for integrity checks."""
    cloned = copy.deepcopy(item)
    cloned.pop("deep_enrichment", None)
    return cloned


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


def classify_source(url: str) -> str:
    """Classify a source URL into a coarse trust bucket."""
    if not url:
        return "unknown"
    if url.startswith(DATASET_SOURCE_PREFIX):
        return "existing_dataset"

    netloc = urlparse(url).netloc.lower()
    if any(netloc.endswith(hint) or hint in netloc for hint in OFFICIAL_DOMAIN_HINTS):
        return "official"
    if any(hint in netloc for hint in INSTITUTIONAL_DOMAIN_HINTS):
        return "institutional"
    if any(hint in netloc for hint in RESEARCH_DOMAIN_HINTS):
        return "research"
    return "supporting"


def source_priority(url: str) -> int:
    """Return a smaller number for stronger sources."""
    return SOURCE_PRIORITIES.get(classify_source(url), SOURCE_PRIORITIES["unknown"])


def source_sort_key(result: dict) -> tuple[int, str]:
    """Sort search results with trust first and then URL/title for stability."""
    url = result.get("link") or result.get("url") or ""
    title = result.get("title", "")
    return (source_priority(url), normalize_text(title or url))


def stable_hash(*parts: object) -> str:
    """Return a stable short hash from structured values."""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def make_evidence_id(
    mfp_id: int,
    attribute_group: str,
    attribute_name: str,
    value: object,
    source_url: str,
    snippet: str,
) -> str:
    """Generate a deterministic evidence id."""
    return "evi_" + stable_hash(mfp_id, attribute_group, attribute_name, value, source_url, snippet)


def make_edge_id(
    source_mfp_id: int,
    edge_type: str,
    target_type: str,
    target_value: str,
    evidence_id: str,
) -> str:
    """Generate a deterministic relationship edge id."""
    return "edge_" + stable_hash(source_mfp_id, edge_type, target_type, target_value, evidence_id)


def dataset_source_url(item: dict, field_name: str) -> str:
    """Build a synthetic source URL for evidence derived from the existing dataset."""
    return f"{DATASET_SOURCE_PREFIX}#mfp_id={item['mfp_id']}&field={field_name}"


def normalize_quantity_record(record: dict) -> dict:
    """Normalize a quantity record into a stable additive shape."""
    value = record.get("value")
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        try:
            value = float(value)
        except ValueError:
            pass

    year = record.get("year")
    if isinstance(year, str):
        year = year.strip()
        if year.isdigit():
            year = int(year)

    normalized = {
        "value": value,
        "unit": str(record.get("unit", "")).strip() or None,
        "year": year if isinstance(year, int) else None,
        "scope": str(record.get("scope", "")).strip() or None,
        "metric_type": str(record.get("metric_type", "")).strip().lower() or None,
    }
    return normalized


def quantity_record_key(record: dict) -> tuple:
    """Return a stable dedupe key for quantity records."""
    normalized = normalize_quantity_record(record)
    return tuple(normalized.get(key) for key in QUANTITY_RECORD_KEYS)


def merge_quantity_records(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge quantity records without duplicates while preserving order."""
    merged = []
    seen = set()

    for record in list(existing or []) + list(new or []):
        normalized = normalize_quantity_record(record)
        if normalized["value"] in (None, ""):
            continue
        key = quantity_record_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)

    return merged


def build_relationship_summary(item: dict, deep_block: dict) -> dict:
    """Build a compact relationship summary from existing and new additive fields."""
    geography = deep_block.get("geography", {}) if isinstance(deep_block, dict) else {}
    regions = dedupe_strings(
        list(item.get("states", []))
        + list(geography.get("districts", []))
        + list(geography.get("clusters", []))
    )
    products = dedupe_strings(
        list(item.get("current_products", []))
        + list(item.get("potential_products", []))
    )
    skills = dedupe_strings(item.get("artisan_types", []))
    material_groups = dedupe_strings([item.get("category", "")])

    return {
        "related_regions": regions,
        "related_products": products,
        "related_skills": skills,
        "related_material_groups": material_groups,
    }


def merge_deep_enrichment(existing: dict | None, patch: dict) -> tuple[dict, bool]:
    """Merge a deep enrichment patch into an existing block additively."""
    merged = copy.deepcopy(make_default_deep_enrichment())
    if isinstance(existing, dict):
        merged = _deep_update(merged, existing)

    before = copy.deepcopy(merged)

    patch = patch or {}
    availability = patch.get("availability", {})
    geography = patch.get("geography", {})
    confidence = patch.get("confidence", {})
    relationship_summary = patch.get("relationship_summary", {})

    if availability:
        band = str(availability.get("band", "")).strip().lower()
        if band in {"unknown", "low", "medium", "high"}:
            merged["availability"]["band"] = band
        merged["availability"]["quantity_records"] = merge_quantity_records(
            merged["availability"].get("quantity_records", []),
            availability.get("quantity_records", []),
        )

    if geography:
        merged["geography"]["districts"] = dedupe_strings(
            list(merged["geography"].get("districts", []))
            + list(geography.get("districts", []))
        )
        merged["geography"]["clusters"] = dedupe_strings(
            list(merged["geography"].get("clusters", []))
            + list(geography.get("clusters", []))
        )

    if relationship_summary:
        for key in ("related_regions", "related_products", "related_skills", "related_material_groups"):
            merged["relationship_summary"][key] = dedupe_strings(
                list(merged["relationship_summary"].get(key, []))
                + list(relationship_summary.get(key, []))
            )

    if confidence:
        for key in ("availability", "geography", "relationships"):
            value = confidence.get(key)
            if isinstance(value, (int, float)):
                merged["confidence"][key] = round(max(float(value), merged["confidence"].get(key, 0.0)), 3)

    merged["evidence_refs"] = dedupe_strings(
        list(merged.get("evidence_refs", [])) + list(patch.get("evidence_refs", []))
    )

    changed = merged != before
    if changed:
        merged["status"] = patch.get("status") or _derive_status(merged)
        merged["last_updated_at"] = patch.get("last_updated_at") or utc_now_iso()
    else:
        merged["status"] = merged.get("status", "not_started")

    return merged, changed


def validate_deep_outputs(items: list[dict], evidence_store: dict, relationships: list[dict]) -> dict:
    """Validate additive deep-enrichment outputs and sidecars."""
    item_ids = {item["mfp_id"] for item in items}
    evidence_ids = set(evidence_store.keys())

    invalid_refs = []
    invalid_edges = []
    deep_items = 0
    coverage = {
        "availability_band": 0,
        "quantity_records": 0,
        "districts": 0,
        "clusters": 0,
        "relationship_summary": 0,
    }

    for item in items:
        deep = item.get("deep_enrichment")
        if not isinstance(deep, dict):
            continue
        deep_items += 1

        if deep.get("availability", {}).get("band") not in (None, "", "unknown"):
            coverage["availability_band"] += 1
        if deep.get("availability", {}).get("quantity_records"):
            coverage["quantity_records"] += 1
        if deep.get("geography", {}).get("districts"):
            coverage["districts"] += 1
        if deep.get("geography", {}).get("clusters"):
            coverage["clusters"] += 1
        if any(deep.get("relationship_summary", {}).values()):
            coverage["relationship_summary"] += 1

        for evidence_id in deep.get("evidence_refs", []):
            if evidence_id not in evidence_ids:
                invalid_refs.append({
                    "mfp_id": item["mfp_id"],
                    "missing_evidence_id": evidence_id,
                })

    for edge in relationships:
        if edge.get("source_mfp_id") not in item_ids:
            invalid_edges.append({"edge_id": edge.get("edge_id"), "reason": "unknown source_mfp_id"})
            continue
        if edge.get("evidence_id") not in evidence_ids:
            invalid_edges.append({"edge_id": edge.get("edge_id"), "reason": "unknown evidence_id"})

    return {
        "total_items": len(items),
        "items_with_deep_enrichment": deep_items,
        "coverage": coverage,
        "evidence_records": len(evidence_store),
        "relationship_edges": len(relationships),
        "invalid_evidence_refs": invalid_refs,
        "invalid_relationship_edges": invalid_edges,
    }


def print_deep_validation_report(summary: dict):
    """Print a human-friendly deep-enrichment validation report."""
    print("\n" + "=" * 60)
    print("  DEEP ENRICHMENT VALIDATION REPORT")
    print("=" * 60)
    print(f"\n  Total items:                {summary['total_items']}")
    print(f"  Items with deep enrichment: {summary['items_with_deep_enrichment']}")
    print(f"  Evidence records:           {summary['evidence_records']}")
    print(f"  Relationship edges:         {summary['relationship_edges']}")

    print("\n  Coverage:")
    for key, value in summary["coverage"].items():
        print(f"    {key:25s} {value}/{summary['total_items']}")

    print(f"\n  Invalid evidence refs:      {len(summary['invalid_evidence_refs'])}")
    print(f"  Invalid relationship edges: {len(summary['invalid_relationship_edges'])}")


def save_deep_validation_report(summary: dict, path: Path):
    """Persist a deep validation summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _deep_update(base: dict, overlay: dict) -> dict:
    """Recursively merge dictionaries."""
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _derive_status(merged: dict) -> str:
    """Infer deep-enrichment status from merged content."""
    has_quantity = bool(merged["availability"].get("quantity_records"))
    has_geo = bool(merged["geography"].get("districts") or merged["geography"].get("clusters"))
    has_relationships = any(merged["relationship_summary"].values())

    if has_quantity and has_geo and has_relationships:
        return "complete"
    if has_quantity or has_geo or has_relationships:
        return "partial"
    return "not_started"
