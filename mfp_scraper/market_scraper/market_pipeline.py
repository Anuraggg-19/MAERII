"""
Market intelligence pipeline orchestrator.
Handles preview/apply modes, batching, LLM execution, and atomic writes.
Follows Module 1's DeepEnrichmentPipeline architecture.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

from ..rollback import (
    atomic_write_json,
    create_run_id,
    read_json,
    snapshot_outputs,
    write_manifest,
)
from . import config_market
from .ecommerce_client import EcommerceClient
from .market_extractor import MarketExtractor
from .market_models import (
    build_competitor_analysis,
    build_market_summary,
    calculate_confidence,
    calculate_demand_score,
    calculate_trend,
    make_default_market_analysis,
    make_source_id,
    merge_market_analysis,
    utc_now_iso,
)
from .market_validator import save_market_validation_report, validate_market_outputs


class MarketIntelligencePipeline:
    """Orchestrates e-commerce scraping and LLM classification."""

    def __init__(self, apply_changes: bool = False):
        self.apply_changes = apply_changes
        self.run_id = create_run_id(prefix="market")

        # Initialize clients
        try:
            self.ecommerce_client = EcommerceClient()
        except ValueError as e:
            print(f"Warning: {e}")
            self.ecommerce_client = None

        self.extractor = MarketExtractor()

    def run(
        self,
        single_item: Optional[str] = None,
        resume_from: int = 0,
        batch_size: int = 10,
        limit: int = 0,
    ) -> dict:
        """Run preview or apply mode for market intelligence."""
        # 1. Load data
        mfp_items = self._load_mfp_items()
        market_data = self._load_market_data()
        market_products = self._load_market_products()
        market_sources = self._load_market_sources()

        # Build indexes
        market_index = {item["mfp_id"]: idx for idx, item in enumerate(market_data)}
        product_index = {p["product_id"]: p for p in market_products}
        source_index = {s["source_id"]: s for s in market_sources}

        working_data = copy.deepcopy(market_data)

        # 2. Select target items
        selected_mfps = self._select_items(mfp_items, single_item, resume_from, limit)
        if not selected_mfps:
            raise ValueError("No items matched the selection criteria.")

        # 3. Setup run manifest
        manifest = {
            "run_id": self.run_id,
            "mode": "market_item" if single_item else "market_batch",
            "applied": self.apply_changes,
            "started_at": utc_now_iso(),
            "completed_at": None,
            "item_ids": [item["mfp_id"] for item in selected_mfps],
            "batch_size": batch_size,
            "resume_index": resume_from,
            "backup_paths": {},
            "output_paths": self._get_output_paths(),
            "status": "running",
            "errors": [],
            "provider": self.extractor.describe_provider(),
            "processed_item_ids": [],
            "last_committed_index": -1,
        }

        if self.apply_changes:
            # Note: snapshot_outputs from rollback.py expects specific outputs.
            # For this module we do custom backups here to be safe.
            manifest["backup_paths"] = self._snapshot_market_outputs()

        self._write_manifest(manifest)

        # 4. Processing loop
        preview_results = []
        batch_results = []
        commit_every = batch_size if batch_size and batch_size > 0 else len(selected_mfps)

        for filtered_index, mfp_item in enumerate(selected_mfps):
            actual_index = resume_from + filtered_index
            try:
                result = self._analyze_item(mfp_item, mfp_items)
                preview_results.append(result["preview"])
                batch_results.append((mfp_item["mfp_id"], result))
                manifest["processed_item_ids"].append(mfp_item["mfp_id"])

                if self.apply_changes and len(batch_results) >= commit_every:
                    self._commit_batch(
                        working_data,
                        market_index,
                        product_index,
                        source_index,
                        batch_results,
                        mfp_items,
                    )
                    batch_results = []
                    manifest["last_committed_index"] = actual_index
                    self._write_manifest(manifest)

            except Exception as exc:
                manifest["errors"].append({
                    "mfp_id": mfp_item["mfp_id"],
                    "name": mfp_item["name"],
                    "error": str(exc),
                })
                manifest["status"] = "failed"
                self._write_manifest(manifest)
                if self.apply_changes:
                    raise

        # Commit final batch
        if self.apply_changes and batch_results:
            self._commit_batch(
                working_data,
                market_index,
                product_index,
                source_index,
                batch_results,
                mfp_items,
            )
            manifest["last_committed_index"] = resume_from + len(selected_mfps) - 1

        # 5. Validation and Completion
        if self.apply_changes:
            simulated_data = working_data
            simulated_products = list(product_index.values())
        else:
            simulated_data, simulated_products, _ = self._simulate_outputs(
                market_data, market_products, market_sources, preview_results, mfp_items
            )

        validation = validate_market_outputs(simulated_data, simulated_products)
        save_market_validation_report(validation, config_market.MARKET_RUNS_DIR / self.run_id / "validation.json")

        manifest["completed_at"] = utc_now_iso()
        manifest["status"] = "complete" if not manifest["errors"] else manifest["status"]
        self._write_manifest(manifest)

        self._write_preview({
            "run_id": self.run_id,
            "mode": manifest["mode"],
            "applied": self.apply_changes,
            "items": preview_results,
            "validation": validation,
        })

        return {
            "run_id": self.run_id,
            "manifest": manifest,
            "validation": validation,
            "items": preview_results,
        }

    # ── Item Processing ─────────────────────────────────────────────────────

    def _analyze_item(self, mfp_item: dict, all_mfp_items: list[dict]) -> dict:
        """Fetch, classify, and analyze market data for a single MFP."""
        mfp_id = mfp_item["mfp_id"]

        # 1. Fetch raw products
        if not self.ecommerce_client:
            return self._build_empty_result(mfp_id, mfp_item["name"])

        fetch_result = self.ecommerce_client.fetch_products_for_mfp(mfp_item)
        queries = fetch_result["queries"]
        raw_products = fetch_result["products"]

        # 2. LLM Classification
        classified_products = self.extractor.classify_products(
            raw_products, all_mfp_items, target_mfp_id=mfp_id
        )

        # Filter products that matched this MFP
        matched_products = [
            p for p in classified_products
            if mfp_id in p.get("matched_mfp_ids", [])
        ]

        # 3. Market Analysis
        summary = build_market_summary(matched_products)
        competitor_analysis = build_competitor_analysis(matched_products)
        confidence = calculate_confidence(matched_products)

        summary["demand_score"] = calculate_demand_score(matched_products, mfp_item.get("msp", 0.0))
        summary["trend"] = calculate_trend(matched_products)

        # Ask LLM for deeper insights if available
        llm_analysis = self.extractor.analyze_market(mfp_item, matched_products)
        if llm_analysis:
            if "competitor_analysis" in llm_analysis:
                # Merge LLM competitor insights, preferring computed data for facts
                ca = llm_analysis["competitor_analysis"]
                if "market_gaps" in ca:
                    competitor_analysis["market_gaps"] = list(set(competitor_analysis["market_gaps"] + ca["market_gaps"]))[:5]
                if "price_positioning" in ca:
                    competitor_analysis["price_positioning"] = ca["price_positioning"]
                competitor_analysis["llm_insights"] = llm_analysis.get("opportunities", [])
                competitor_analysis["demand_drivers"] = llm_analysis.get("demand_indicators", {}).get("key_demand_drivers", [])

        # 4. Build Patch
        patch = {
            "version": "v1",
            "status": "complete" if matched_products else "partial",
            "search_queries": {
                "primary": queries[0]["query"] if queries else "",
                "variations": [q["query"] for q in queries[1:]],
            },
            "market_products": matched_products,
            "market_summary": summary,
            "competitor_analysis": competitor_analysis,
            "confidence": confidence,
            "last_analyzed_at": utc_now_iso(),
        }

        # Source tracking records
        sources = self._build_sources(mfp_id, matched_products, queries)

        preview = {
            "mfp_id": mfp_id,
            "name": mfp_item["name"],
            "status": patch["status"],
            "provider": self.extractor.describe_provider(),
            "queries": queries,
            "products_found": len(raw_products),
            "products_matched": len(matched_products),
            "market_summary": summary,
            "competitor_analysis": competitor_analysis,
        }

        return {
            "mfp_id": mfp_id,
            "patch": patch,
            "all_products": classified_products,
            "sources": sources,
            "preview": preview,
        }

    def _build_empty_result(self, mfp_id: int, name: str) -> dict:
        """Return an empty structure if scraping is disabled."""
        return {
            "mfp_id": mfp_id,
            "patch": make_default_market_analysis(),
            "all_products": [],
            "sources": [],
            "preview": {
                "mfp_id": mfp_id,
                "name": name,
                "status": "not_started",
                "error": "No ecommerce client available",
            },
        }

    def _build_sources(self, mfp_id: int, products: list[dict], queries: list[dict]) -> list[dict]:
        """Build provenance tracking records."""
        sources = []
        for q in queries:
            query_str = q["query"]
            # Find URLs that came from this query (simplified: just log the query intent)
            sources.append({
                "source_id": make_source_id(mfp_id, query_str, "serper_shopping"),
                "mfp_id": mfp_id,
                "query": query_str,
                "provider": "serper",
                "result_count": q["result_count"],
                "retrieved_at": utc_now_iso(),
            })
        return sources

    # ── State Management ────────────────────────────────────────────────────

    def _load_mfp_items(self) -> list[dict]:
        """Load enriched dataset from Module 1."""
        if not config_market.ENRICHED_JSON_PATH.exists():
            raise FileNotFoundError(f"Run Module 1 base enrichment first. Missing: {config_market.ENRICHED_JSON_PATH}")
        return read_json(config_market.ENRICHED_JSON_PATH, [])

    def _load_market_data(self) -> list[dict]:
        return read_json(config_market.MARKET_DEMAND_PATH, [])

    def _load_market_products(self) -> list[dict]:
        return read_json(config_market.MARKET_PRODUCTS_PATH, [])

    def _load_market_sources(self) -> list[dict]:
        return read_json(config_market.MARKET_SOURCES_PATH, [])

    def _select_items(
        self,
        mfp_items: list[dict],
        single_item: Optional[str],
        resume_from: int,
        limit: int,
    ) -> list[dict]:
        """Filter target items."""
        selected = mfp_items
        if single_item:
            selected = [item for item in mfp_items if single_item.lower() in item["name"].lower()]
        if resume_from > 0:
            selected = selected[resume_from:]
        if limit and limit > 0:
            selected = selected[:limit]
        return selected

    def _commit_batch(
        self,
        working_data: list[dict],
        market_index: dict[int, int],
        product_index: dict[str, dict],
        source_index: dict[str, dict],
        batch_results: list[tuple[int, dict]],
        mfp_items: list[dict],
    ):
        """Apply patch to working data and write atomically."""
        for mfp_id, result in batch_results:
            # 1. Update Market Demand Data
            if mfp_id not in market_index:
                # Create skeleton if new
                item_name = next((i["name"] for i in mfp_items if i["mfp_id"] == mfp_id), f"MFP {mfp_id}")
                new_entry = {
                    "mfp_id": mfp_id,
                    "name": item_name,
                    "market_analysis": make_default_market_analysis()
                }
                working_data.append(new_entry)
                market_index[mfp_id] = len(working_data) - 1

            idx = market_index[mfp_id]
            existing_analysis = working_data[idx].get("market_analysis")
            merged_analysis, _ = merge_market_analysis(existing_analysis, result["patch"])
            working_data[idx]["market_analysis"] = merged_analysis

            # 2. Update Products
            for product in result["all_products"]:
                pid = product["product_id"]
                if pid not in product_index:
                    product_index[pid] = product
                else:
                    # Merge matched MFP IDs
                    existing_ids = set(product_index[pid].get("matched_mfp_ids", []))
                    existing_ids.update(product.get("matched_mfp_ids", []))
                    product_index[pid]["matched_mfp_ids"] = list(existing_ids)
                    product_index[pid]["confidence"] = max(
                        product_index[pid].get("confidence", 0.0),
                        product.get("confidence", 0.0)
                    )

            # 3. Update Sources
            for source in result["sources"]:
                source_index[source["source_id"]] = source

        # Write to disk
        atomic_write_json(config_market.MARKET_DEMAND_PATH, working_data)
        atomic_write_json(config_market.MARKET_PRODUCTS_PATH, list(product_index.values()))
        atomic_write_json(config_market.MARKET_SOURCES_PATH, list(source_index.values()))

    def _simulate_outputs(
        self,
        market_data: list[dict],
        market_products: list[dict],
        market_sources: list[dict],
        preview_results: list[dict],
        mfp_items: list[dict],
    ):
        """Build in-memory state for preview validation."""
        sim_data = copy.deepcopy(market_data)
        sim_products = {p["product_id"]: p for p in market_products}
        sim_sources = {s["source_id"]: s for s in market_sources}

        market_index = {item["mfp_id"]: idx for idx, item in enumerate(sim_data)}

        for result in preview_results:
            mfp_id = result["mfp_id"]

            if mfp_id not in market_index:
                item_name = next((i["name"] for i in mfp_items if i["mfp_id"] == mfp_id), f"MFP {mfp_id}")
                new_entry = {
                    "mfp_id": mfp_id,
                    "name": item_name,
                    "market_analysis": make_default_market_analysis()
                }
                sim_data.append(new_entry)
                market_index[mfp_id] = len(sim_data) - 1

            idx = market_index[mfp_id]
            # Create a mock patch from preview data
            patch = {
                "version": "v1",
                "status": result["status"],
                "market_summary": result["market_summary"],
                "competitor_analysis": result["competitor_analysis"],
            }
            merged, _ = merge_market_analysis(sim_data[idx].get("market_analysis"), patch)
            sim_data[idx]["market_analysis"] = merged

        return sim_data, list(sim_products.values()), list(sim_sources.values())

    # ── File I/O Helpers ────────────────────────────────────────────────────

    def _get_output_paths(self) -> dict[str, str]:
        return {
            "market_demand_data": str(config_market.MARKET_DEMAND_PATH),
            "market_products": str(config_market.MARKET_PRODUCTS_PATH),
            "market_sources": str(config_market.MARKET_SOURCES_PATH),
        }

    def _snapshot_market_outputs(self) -> dict[str, str]:
        """Backup market outputs before apply run."""
        backup_dir = config_market.MARKET_BACKUPS_DIR / self.run_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        outputs = {
            "market_demand_data": config_market.MARKET_DEMAND_PATH,
            "market_products": config_market.MARKET_PRODUCTS_PATH,
            "market_sources": config_market.MARKET_SOURCES_PATH,
        }

        defaults = {
            "market_demand_data": [],
            "market_products": [],
            "market_sources": [],
        }

        backup_paths = {}
        import shutil
        for key, path in outputs.items():
            backup_path = backup_dir / path.name
            if path.exists():
                shutil.copy2(path, backup_path)
            else:
                atomic_write_json(backup_path, defaults[key])
            backup_paths[key] = str(backup_path)

        return backup_paths

    def _write_manifest(self, manifest: dict):
        run_dir = config_market.MARKET_RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(run_dir / "manifest.json", manifest)

    def _write_preview(self, payload: dict):
        run_dir = config_market.MARKET_RUNS_DIR / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(run_dir / "preview.json", payload)
