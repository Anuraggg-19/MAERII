"""
Additive deep-enrichment pipeline with preview, apply, batching, and rollback safety.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

from . import config
from .content_fetcher import fetch_search_documents
from .deep_extractor import DeepExtractor
from .deep_models import (
    build_relationship_summary,
    classify_source,
    clone_item_without_deep,
    dataset_source_url,
    make_default_deep_enrichment,
    make_edge_id,
    make_evidence_id,
    merge_deep_enrichment,
    print_deep_validation_report,
    save_deep_validation_report,
    source_sort_key,
    utc_now_iso,
    validate_deep_outputs,
)
from .rollback import (
    atomic_write_json,
    create_run_id,
    output_paths,
    read_json,
    snapshot_outputs,
    write_manifest,
    write_preview,
)
from .search_client import SerperClient


class DeepEnrichmentPipeline:
    """Preview and apply additive deep enrichment without touching existing enriched fields."""

    def __init__(self, apply_changes: bool = False):
        self.apply_changes = apply_changes
        self.extractor = DeepExtractor()
        self.run_id = create_run_id(prefix="deep")
        self.output_paths = output_paths()

        try:
            self.search_client = SerperClient()
        except ValueError:
            self.search_client = None

    def run(
        self,
        single_item: Optional[str] = None,
        resume_from: int = 0,
        batch_size: int = 10,
        limit: int = 0,
    ) -> dict:
        """Run preview or apply mode for a single item or a selected batch."""
        items = self._load_items()
        evidence_store = read_json(config.DEEP_ENRICHMENT_EVIDENCE_PATH, {})
        relationships = read_json(config.MATERIAL_RELATIONSHIPS_PATH, [])
        relationship_index = {edge["edge_id"]: edge for edge in relationships if edge.get("edge_id")}
        original_items = copy.deepcopy(items)
        working_items = copy.deepcopy(items)

        selected = self._select_items(items, single_item=single_item, resume_from=resume_from, limit=limit)
        if not selected:
            raise ValueError("No items matched the requested deep-enrichment selection.")

        manifest = {
            "run_id": self.run_id,
            "mode": "deep_item" if single_item else "deep_batch",
            "applied": self.apply_changes,
            "started_at": utc_now_iso(),
            "completed_at": None,
            "item_ids": [item["mfp_id"] for item in selected],
            "batch_size": batch_size,
            "resume_index": resume_from,
            "backup_paths": {},
            "output_paths": {key: str(path) for key, path in self.output_paths.items()},
            "status": "running",
            "errors": [],
            "provider": self.extractor.describe_provider(),
            "search_enabled": self.search_client is not None,
            "processed_item_ids": [],
            "last_committed_index": -1,
        }

        if self.apply_changes:
            manifest["backup_paths"] = snapshot_outputs(self.run_id)

        write_manifest(self.run_id, manifest)

        preview_results = []
        batch_results = []
        commit_every = batch_size if batch_size and batch_size > 0 else len(selected)

        for filtered_index, item in enumerate(selected):
            actual_index = resume_from + filtered_index
            print(f"\n  [{actual_index + 1}/{len(items)}] Deep enriching: {item['name']}...")
            try:
                result = self.deep_enrich_item(item)
                preview_results.append(result["preview"])
                batch_results.append((item["mfp_id"], result))
                manifest["processed_item_ids"].append(item["mfp_id"])

                if self.apply_changes and len(batch_results) >= commit_every:
                    self._commit_batch(
                        working_items,
                        evidence_store,
                        relationship_index,
                        original_items,
                        batch_results,
                    )
                    batch_results = []
                    manifest["last_committed_index"] = actual_index
                    write_manifest(self.run_id, manifest)
                elif not self.apply_changes:
                    # Continuously save preview data so it isn't lost if terminated early
                    write_preview(self.run_id, {
                        "run_id": self.run_id,
                        "mode": manifest["mode"],
                        "applied": False,
                        "items": preview_results,
                        "validation": "Partial run - validation not yet calculated",
                    })

            except Exception as exc:
                manifest["errors"].append({
                    "mfp_id": item["mfp_id"],
                    "name": item["name"],
                    "error": str(exc),
                })
                manifest["status"] = "failed"
                write_manifest(self.run_id, manifest)
                if self.apply_changes:
                    raise

        if self.apply_changes and batch_results:
            self._commit_batch(
                working_items,
                evidence_store,
                relationship_index,
                original_items,
                batch_results,
            )
            manifest["last_committed_index"] = resume_from + len(selected) - 1

        simulated_items = working_items if self.apply_changes else self._simulate_items(original_items, preview_results)
        simulated_relationships = list(relationship_index.values()) if self.apply_changes else self._simulate_relationships(relationships, preview_results)
        simulated_evidence = evidence_store if self.apply_changes else self._simulate_evidence_store(evidence_store, preview_results)

        validation = validate_deep_outputs(simulated_items, simulated_evidence, simulated_relationships)
        validation_path = config.DEEP_RUNS_DIR / self.run_id / "validation.json"
        save_deep_validation_report(validation, validation_path)

        manifest["completed_at"] = utc_now_iso()
        manifest["status"] = "complete" if not manifest["errors"] else manifest["status"]
        write_manifest(self.run_id, manifest)

        preview_payload = {
            "run_id": self.run_id,
            "mode": manifest["mode"],
            "applied": self.apply_changes,
            "items": preview_results,
            "validation": validation,
        }
        write_preview(self.run_id, preview_payload)

        return {
            "run_id": self.run_id,
            "manifest": manifest,
            "validation": validation,
            "items": preview_results,
        }

    def deep_enrich_item(self, item: dict) -> dict:
        """Build additive deep enrichment for a single existing enriched item."""
        print("    - Searching for deep evidence...")
        search_results = self._collect_search_results(item)
        print(f"    - Fetching {len(search_results)} documents...")
        documents = self._collect_documents(search_results)
        print("    - Extracting insights via LLM...")
        extracted = self.extractor.extract(item, documents)

        evidence_records = self._build_evidence_records(item, extracted.get("evidence", []))
        evidence_refs = [record["evidence_id"] for record in evidence_records]

        patch = {
            "version": "v1",
            "status": extracted.get("status", "partial"),
            "availability": extracted.get("availability", {}),
            "geography": extracted.get("geography", {}),
            "confidence": {
                "availability": extracted.get("confidence", {}).get("availability", 0.0),
                "geography": extracted.get("confidence", {}).get("geography", 0.0),
                "relationships": 0.0,
            },
            "evidence_refs": evidence_refs,
        }

        relationship_summary = build_relationship_summary(item, patch)
        patch["relationship_summary"] = relationship_summary
        patch["confidence"]["relationships"] = 1.0 if any(relationship_summary.values()) else 0.0

        relationship_records, relationship_evidence = self._build_relationship_records(
            item,
            relationship_summary,
            evidence_records,
        )

        all_evidence = evidence_records + relationship_evidence
        patch["evidence_refs"] = [record["evidence_id"] for record in all_evidence]

        merged_block, changed = merge_deep_enrichment(item.get("deep_enrichment"), patch)

        preview = {
            "mfp_id": item["mfp_id"],
            "name": item["name"],
            "status": merged_block.get("status"),
            "changed": changed,
            "provider": self.extractor.describe_provider(),
            "search_queries": self._build_search_queries(item),
            "documents": documents,
            "deep_enrichment": merged_block,
            "evidence_records": all_evidence,
            "relationship_edges": relationship_records,
        }

        return {
            "mfp_id": item["mfp_id"],
            "patch": patch,
            "merged_block": merged_block,
            "changed": changed,
            "documents": documents,
            "evidence_records": all_evidence,
            "relationship_edges": relationship_records,
            "preview": preview,
        }

    def _load_items(self) -> list[dict]:
        """Load the canonical enriched dataset."""
        if not config.ENRICHED_JSON_PATH.exists():
            raise FileNotFoundError(
                f"Canonical dataset not found at {config.ENRICHED_JSON_PATH}. Run the base enrichment first."
            )
        return read_json(config.ENRICHED_JSON_PATH, [])

    def _select_items(
        self,
        items: list[dict],
        single_item: Optional[str],
        resume_from: int,
        limit: int,
    ) -> list[dict]:
        """Select target items from the existing enriched dataset."""
        selected = items
        if single_item:
            selected = [item for item in items if single_item.lower() in item["name"].lower()]
        if resume_from > 0:
            selected = selected[resume_from:]
        if limit and limit > 0:
            selected = selected[:limit]
        return selected

    def _build_search_queries(self, item: dict) -> dict[str, str]:
        """Build targeted search queries for deep enrichment."""
        name_query = f"{item['name']} {item.get('scientific_name') or ''}".strip()
        return {
            "quantity": f'"{item["name"]}" India annual production OR collection OR yield tonnes',
            "geography": f'"{item["name"]}" major producing districts India',
            "relationships": f'"{item["name"]}" tribal value addition processing products',
        }

    def _collect_search_results(self, item: dict) -> list[dict]:
        """Collect and rank search results for deep enrichment."""
        queries = self._build_search_queries(item)
        all_results = []

        if not self.search_client:
            return all_results

        for query_type, query in queries.items():
            results = self.search_client.search(query, num_results=config.SEARCH_RESULTS_PER_QUERY)
            for result in results:
                if not result.get("link"):
                    continue
                result_copy = dict(result)
                result_copy["query_type"] = query_type
                result_copy["source_type"] = classify_source(result_copy.get("link", ""))
                all_results.append(result_copy)

        deduped = {}
        for result in all_results:
            link = result.get("link", "")
            if not link or link in deduped:
                continue
            deduped[link] = result

        ranked = sorted(deduped.values(), key=source_sort_key)
        return ranked[: max(config.DEEP_FETCH_MAX_DOCS, config.SEARCH_RESULTS_PER_QUERY)]

    def _collect_documents(self, search_results: list[dict]) -> list[dict]:
        """Fetch top search results into structured documents."""
        documents = fetch_search_documents(
            search_results,
            max_pages=config.DEEP_FETCH_MAX_DOCS,
            max_chars_per_page=config.DEEP_FETCH_MAX_CHARS,
        )

        documents_by_url = {doc["url"]: doc for doc in documents if doc.get("url")}
        for result in search_results:
            link = result.get("link")
            if link in documents_by_url:
                documents_by_url[link]["source_type"] = result.get("source_type", classify_source(link))
                documents_by_url[link]["query_type"] = result.get("query_type")
                continue

            if result.get("snippet"):
                documents_by_url[link] = {
                    "url": link,
                    "title": result.get("title", ""),
                    "snippet": result.get("snippet", ""),
                    "content_type": "snippet",
                    "text": result.get("snippet", ""),
                    "source_type": result.get("source_type", classify_source(link)),
                    "query_type": result.get("query_type"),
                }

        return sorted(documents_by_url.values(), key=lambda doc: (source_sort_key({"link": doc.get("url", ""), "title": doc.get("title", "")})))

    def _build_evidence_records(self, item: dict, evidence_list: list[dict]) -> list[dict]:
        """Normalize extracted evidence into sidecar records."""
        records = []
        for record in evidence_list:
            evidence_id = make_evidence_id(
                item["mfp_id"],
                record.get("attribute_group", ""),
                record.get("attribute_name", ""),
                record.get("value"),
                record.get("source_url", ""),
                record.get("snippet", ""),
            )
            records.append({
                "evidence_id": evidence_id,
                "mfp_id": item["mfp_id"],
                "attribute_group": record.get("attribute_group", ""),
                "attribute_name": record.get("attribute_name", ""),
                "value": record.get("value"),
                "source_url": record.get("source_url", ""),
                "source_type": classify_source(record.get("source_url", "")),
                "snippet": record.get("snippet", ""),
                "retrieved_at": utc_now_iso(),
                "confidence": round(float(record.get("confidence", 0.0) or 0.0), 3),
            })
        return records

    def _build_relationship_records(
        self,
        item: dict,
        relationship_summary: dict,
        extracted_evidence: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Build graph-ready edges and synthetic evidence for dataset-derived relationships."""
        evidence_by_value = {}
        for record in extracted_evidence:
            evidence_by_value[(record["attribute_name"], json.dumps(record["value"], sort_keys=True, ensure_ascii=False, default=str))] = record["evidence_id"]

        synthetic_evidence = []
        edges = []

        def ensure_dataset_evidence(field_name: str, value: str, attribute_name: str) -> str:
            source_url = dataset_source_url(item, field_name)
            snippet = f"Derived from existing canonical field '{field_name}' for {item['name']}."
            evidence_id = make_evidence_id(
                item["mfp_id"],
                "relationship",
                attribute_name,
                value,
                source_url,
                snippet,
            )
            synthetic_evidence.append({
                "evidence_id": evidence_id,
                "mfp_id": item["mfp_id"],
                "attribute_group": "relationship",
                "attribute_name": attribute_name,
                "value": value,
                "source_url": source_url,
                "source_type": "existing_dataset",
                "snippet": snippet,
                "retrieved_at": utc_now_iso(),
                "confidence": 1.0,
            })
            return evidence_id

        for state in item.get("states", []):
            evidence_id = ensure_dataset_evidence("states", state, "state")
            edges.append(self._build_edge(item["mfp_id"], "available_in", "state", state, evidence_id, 1.0))

        for district in relationship_summary.get("related_regions", []):
            if district in item.get("states", []):
                continue
            evidence_id = evidence_by_value.get(("districts", json.dumps(district, sort_keys=True, ensure_ascii=False)))
            if evidence_id:
                edges.append(self._build_edge(item["mfp_id"], "available_in", "district", district, evidence_id, 0.7))

        for cluster in item.get("deep_enrichment", {}).get("geography", {}).get("clusters", []):
            evidence_id = evidence_by_value.get(("clusters", json.dumps(cluster, sort_keys=True, ensure_ascii=False)))
            if evidence_id:
                edges.append(self._build_edge(item["mfp_id"], "linked_to", "cluster", cluster, evidence_id, 0.7))

        for cluster in relationship_summary.get("related_regions", []):
            if "cluster" not in cluster.lower() and "van dhan" not in cluster.lower():
                continue
            evidence_id = evidence_by_value.get(("clusters", json.dumps(cluster, sort_keys=True, ensure_ascii=False)))
            if evidence_id:
                edges.append(self._build_edge(item["mfp_id"], "linked_to", "cluster", cluster, evidence_id, 0.7))

        for skill in item.get("artisan_types", []):
            evidence_id = ensure_dataset_evidence("artisan_types", skill, "skill")
            edges.append(self._build_edge(item["mfp_id"], "processed_by", "skill", skill, evidence_id, 1.0))

        for product in item.get("current_products", []):
            evidence_id = ensure_dataset_evidence("current_products", product, "current_product")
            edges.append(self._build_edge(item["mfp_id"], "used_for_product", "current_product", product, evidence_id, 1.0))

        for product in item.get("potential_products", []):
            evidence_id = ensure_dataset_evidence("potential_products", product, "potential_product")
            edges.append(self._build_edge(item["mfp_id"], "could_enable_product", "potential_product", product, evidence_id, 1.0))

        category = item.get("category")
        if category:
            evidence_id = ensure_dataset_evidence("category", category, "material_group")
            edges.append(self._build_edge(item["mfp_id"], "belongs_to_group", "material_group", category, evidence_id, 1.0))

        deduped_edges = {edge["edge_id"]: edge for edge in edges}
        deduped_evidence = {record["evidence_id"]: record for record in synthetic_evidence}
        return list(deduped_edges.values()), list(deduped_evidence.values())

    def _build_edge(
        self,
        source_mfp_id: int,
        edge_type: str,
        target_type: str,
        target_value: str,
        evidence_id: str,
        confidence: float,
    ) -> dict:
        """Build a normalized relationship edge."""
        edge_id = make_edge_id(source_mfp_id, edge_type, target_type, target_value, evidence_id)
        return {
            "edge_id": edge_id,
            "source_mfp_id": source_mfp_id,
            "edge_type": edge_type,
            "target_type": target_type,
            "target_value": target_value,
            "evidence_id": evidence_id,
            "confidence": round(confidence, 3),
        }

    def _commit_batch(
        self,
        working_items: list[dict],
        evidence_store: dict,
        relationship_index: dict,
        original_items: list[dict],
        batch_results: list[tuple[int, dict]],
    ):
        """Apply one additive batch and write canonical outputs atomically."""
        item_index = {item["mfp_id"]: idx for idx, item in enumerate(working_items)}

        for mfp_id, result in batch_results:
            idx = item_index[mfp_id]
            original_item = working_items[idx]
            updated_item = copy.deepcopy(original_item)
            updated_item["deep_enrichment"] = result["merged_block"]

            if clone_item_without_deep(updated_item) != clone_item_without_deep(original_item):
                raise RuntimeError(f"Top-level fields changed unexpectedly for item {mfp_id}")

            working_items[idx] = updated_item

            for record in result["evidence_records"]:
                evidence_store[record["evidence_id"]] = record

            for edge in result["relationship_edges"]:
                relationship_index[edge["edge_id"]] = edge

        atomic_write_json(config.ENRICHED_JSON_PATH, working_items)
        atomic_write_json(config.DEEP_ENRICHMENT_EVIDENCE_PATH, evidence_store)
        atomic_write_json(config.MATERIAL_RELATIONSHIPS_PATH, list(relationship_index.values()))

    def _simulate_items(self, original_items: list[dict], previews: list[dict]) -> list[dict]:
        """Build an in-memory view of what preview mode would write."""
        simulated = copy.deepcopy(original_items)
        index = {item["mfp_id"]: idx for idx, item in enumerate(simulated)}
        for preview in previews:
            idx = index[preview["mfp_id"]]
            simulated[idx]["deep_enrichment"] = preview["deep_enrichment"]
        return simulated

    def _simulate_evidence_store(self, current_store: dict, previews: list[dict]) -> dict:
        """Build an in-memory evidence store for preview validation."""
        simulated = dict(current_store)
        for preview in previews:
            for record in preview["evidence_records"]:
                simulated[record["evidence_id"]] = record
        return simulated

    def _simulate_relationships(self, current_relationships: list[dict], previews: list[dict]) -> list[dict]:
        """Build an in-memory relationship list for preview validation."""
        index = {edge["edge_id"]: edge for edge in current_relationships if edge.get("edge_id")}
        for preview in previews:
            for edge in preview["relationship_edges"]:
                index[edge["edge_id"]] = edge
        return list(index.values())


def validate_current_deep_outputs() -> dict:
    """Validate the canonical deep-enrichment outputs currently on disk."""
    items = read_json(config.ENRICHED_JSON_PATH, [])
    evidence = read_json(config.DEEP_ENRICHMENT_EVIDENCE_PATH, {})
    relationships = read_json(config.MATERIAL_RELATIONSHIPS_PATH, [])
    summary = validate_deep_outputs(items, evidence, relationships)
    print_deep_validation_report(summary)
    save_deep_validation_report(summary, config.DATA_DIR / "deep_enrichment_validation.json")
    return summary
