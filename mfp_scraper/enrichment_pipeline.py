"""
Enrichment Pipeline -- orchestrates the full Search -> Fetch -> Extract -> Validate flow.
Supports batch processing with inter-batch auditing and logging.
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from . import config
from .seed_data import load_csv, load_seed_json, save_seed_json
from .search_client import SerperClient, build_search_queries, build_image_query
from .content_fetcher import aggregate_search_content
from .llm_extractor import GeminiExtractor, GroqExtractor
from .validator import validate_dataset, print_validation_report, save_report


# -- Setup file logger -------------------------------------------------------

def _setup_logger() -> logging.Logger:
    """Create a timestamped file logger for the enrichment run."""
    log_dir = config.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"enrichment_run_{timestamp}.log"

    logger = logging.getLogger("mfp_enrichment")
    logger.setLevel(logging.DEBUG)

    # File handler -- captures everything
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler -- only INFO+
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    # Don't add console handler -- we use print() for console output
    # to avoid double-printing with tqdm

    logger.info(f"Enrichment run started at {timestamp}")
    logger.info(f"Log file: {log_file}")

    return logger


class EnrichmentPipeline:
    """Orchestrates the full MFP data enrichment pipeline."""

    def __init__(self):
        self.search_client = SerperClient()
        if config.GROQ_API_KEY:
            self.extractor = GroqExtractor()
        else:
            self.extractor = GeminiExtractor()
        self.enrichment_sources = {}  # Track sources per item
        self.logger = _setup_logger()

        # Per-item tracking for batch audits
        self._batch_results = []  # list of dicts with per-item outcome

    def enrich_single(self, item: dict, verbose: bool = True) -> dict:
        """
        Enrich a single MFP item with all missing attributes.
        Returns the enriched item dict.
        """
        name = item["name"]
        mfp_id = item["mfp_id"]
        start_time = time.time()
        item_log = {
            "mfp_id": mfp_id,
            "name": name,
            "status": "PENDING",
            "fields_before": 0,
            "fields_after": 0,
            "fields_gained": 0,
            "search_results": 0,
            "content_chars": 0,
            "llm_model_used": None,
            "error": None,
            "duration_seconds": 0,
        }

        if verbose:
            print(f"\n{'-' * 50}")
            print(f"  Enriching: {name} (ID: {mfp_id})")
            print(f"{'-' * 50}")

        self.logger.info(f"--- START: {name} (mfp_id={mfp_id}) ---")

        # Count fields before enrichment
        item_log["fields_before"] = self._count_filled(item)

        # Step 1: Build search queries for this item
        queries = build_search_queries(item)
        if verbose:
            print(f"  -> {len(queries)} search queries planned")
        self.logger.debug(f"  Queries: {list(queries.keys())}")

        # Step 2: Run searches and aggregate content
        all_search_results = []
        all_source_urls = []

        for field, query in queries.items():
            if verbose:
                print(f"  [SEARCH] {field}...")
            self.logger.debug(f"  Searching: {field} -> {query}")
            results = self.search_client.search(query)
            all_search_results.extend(results)
            all_source_urls.extend([r["link"] for r in results if r.get("link")])

        item_log["search_results"] = len(all_search_results)
        if verbose:
            print(f"  -> Found {len(all_search_results)} search results")
        self.logger.info(f"  Found {len(all_search_results)} search results")

        # Step 3: Fetch and aggregate content from top pages
        if verbose:
            print(f"  [FETCH] Fetching page content...")

        # Deduplicate URLs
        unique_results = []
        seen_urls = set()
        for r in all_search_results:
            url = r.get("link", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        source_text = aggregate_search_content(unique_results, max_pages=4)
        item_log["content_chars"] = len(source_text)

        if verbose:
            print(f"  -> Aggregated {len(source_text)} chars of content")
        self.logger.info(f"  Aggregated {len(source_text)} chars from {len(unique_results)} unique URLs")

        # Step 4: LLM extraction
        if verbose:
            print(f"  [LLM] Extracting structured data via LLM...")

        extracted = self.extractor.extract(item, source_text)

        if extracted is None:
            if verbose:
                print(f"  [FAIL] Extraction failed for {name}")
            self.logger.error(f"  LLM extraction FAILED for {name}")
            item_log["status"] = "FAILED"
            item_log["error"] = "LLM extraction returned None"
            item_log["duration_seconds"] = round(time.time() - start_time, 1)
            self._batch_results.append(item_log)
            return item

        # Step 5: Merge extracted data into item
        enriched = self._merge(item, extracted)

        # Step 6: Find an image
        if verbose:
            print(f"  [IMAGE] Searching for image...")
        enriched = self._find_image(enriched)

        # Track sources
        self.enrichment_sources[item["mfp_id"]] = {
            "name": name,
            "source_urls": list(seen_urls)[:10],
            "search_queries": queries,
            "confidence": extracted.get("confidence", {}),
        }

        # Count fields after enrichment
        item_log["fields_after"] = self._count_filled(enriched)
        item_log["fields_gained"] = item_log["fields_after"] - item_log["fields_before"]
        item_log["status"] = "SUCCESS"
        item_log["duration_seconds"] = round(time.time() - start_time, 1)

        if verbose:
            print(f"  [DONE] {item_log['fields_after']}/{len(config.TARGET_FIELDS)} fields populated (+{item_log['fields_gained']} new)")

        self.logger.info(
            f"  SUCCESS: {item_log['fields_after']}/{len(config.TARGET_FIELDS)} fields "
            f"(+{item_log['fields_gained']} new) in {item_log['duration_seconds']}s"
        )

        self._batch_results.append(item_log)
        return enriched

    def _count_filled(self, item: dict) -> int:
        """Count how many target fields are non-null/non-empty."""
        return sum(
            1 for f in config.TARGET_FIELDS
            if item.get(f) is not None
            and item.get(f) != ""
            and item.get(f) != []
        )

    def _merge(self, original: dict, extracted: dict) -> dict:
        """
        Merge extracted data into the original item.
        """
        merged = dict(original)

        if not merged.get("scientific_name") and extracted.get("scientific_name"):
            merged["scientific_name"] = extracted["scientific_name"]

        if extracted.get("description"):
            merged["description"] = extracted["description"]

        if extracted.get("season"):
            merged["season"] = extracted["season"]

        if extracted.get("shelf_life"):
            merged["shelf_life"] = extracted["shelf_life"]

        if not merged.get("states") and extracted.get("states"):
            merged["states"] = extracted["states"]
        elif merged.get("states") and extracted.get("states"):
            existing = set(merged["states"])
            for state in extracted["states"]:
                existing.add(state)
            merged["states"] = sorted(existing)

        for field in ["artisan_types", "current_products", "potential_products"]:
            if extracted.get(field):
                merged[field] = extracted[field]

        merged["confidence"] = extracted.get("confidence", {})

        return merged

    def _find_image(self, item: dict) -> dict:
        """Search for an appropriate image for the item."""
        query = build_image_query(item)
        results = self.search_client.search_images(query, num_results=3)

        if results:
            for r in results:
                url = r.get("imageUrl", "")
                if url and url.startswith("http"):
                    item["image_url"] = url
                    break

        return item

    # =========================================================================
    #  BATCH PROCESSING
    # =========================================================================

    def run(
        self,
        items: Optional[list[dict]] = None,
        resume_from: int = 0,
        single_item: Optional[str] = None,
        batch_size: int = 0,
    ) -> list[dict]:
        """
        Run the full enrichment pipeline.

        Args:
            items: List of seed items. If None, loads from CSV.
            resume_from: Index to resume from (for interrupted runs).
            single_item: If provided, only enrich this specific item name.
            batch_size: Process N items at a time, then pause for audit.
                        0 = no batching (process all at once).
        """
        # Load items
        if items is None:
            try:
                items = load_seed_json()
                print(f"Loaded {len(items)} items from seed JSON")
                self.logger.info(f"Loaded {len(items)} items from seed JSON")
            except FileNotFoundError:
                print("Seed JSON not found. Loading from CSV...")
                items = load_csv()
                save_seed_json(items)

        # Filter to single item if requested
        if single_item:
            items = [
                i for i in items
                if single_item.lower() in i["name"].lower()
            ]
            if not items:
                print(f"[FAIL] No item found matching '{single_item}'")
                return []
            print(f"Enriching single item: {items[0]['name']}")

        # Resume support
        if resume_from > 0:
            print(f"Resuming from item #{resume_from}")
            self.logger.info(f"Resuming from item #{resume_from}")

        # Load existing enriched data if resuming
        enriched_items = []
        if resume_from > 0 and config.ENRICHED_JSON_PATH.exists():
            with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as f:
                enriched_items = json.load(f)
            print(f"  Loaded {len(enriched_items)} previously enriched items")

        # Determine processing range
        items_to_process = items[resume_from:]
        total = len(items_to_process)

        if batch_size > 0:
            print(f"\n  Batch mode: {batch_size} items per batch")
            print(f"  Total items to process: {total}")
            print(f"  Estimated batches: {(total + batch_size - 1) // batch_size}")
            self.logger.info(f"Batch mode: size={batch_size}, total={total}")

        # Process items (with optional batching)
        global_idx = resume_from
        batch_num = 0
        interrupted = False

        while global_idx < resume_from + total:
            # Determine batch boundaries
            if batch_size > 0:
                batch_end = min(global_idx + batch_size, resume_from + total)
                batch_num += 1
                batch_items = items[global_idx:batch_end]

                print(f"\n{'=' * 60}")
                print(f"  BATCH {batch_num}: Items #{global_idx + 1} to #{batch_end}")
                print(f"  ({len(batch_items)} items in this batch)")
                print(f"{'=' * 60}")
                self.logger.info(f"=== BATCH {batch_num}: items {global_idx+1}-{batch_end} ===")
            else:
                batch_end = resume_from + total
                batch_items = items[global_idx:batch_end]

            # Reset batch results tracker
            self._batch_results = []

            # Process this batch
            for i, item in enumerate(
                tqdm(batch_items, desc=f"Batch {batch_num}" if batch_size > 0 else "Enriching",
                     unit="item"),
            ):
                try:
                    enriched = self.enrich_single(item)

                    # Update or append
                    existing_idx = next(
                        (j for j, e in enumerate(enriched_items)
                         if e["mfp_id"] == enriched["mfp_id"]),
                        None,
                    )
                    if existing_idx is not None:
                        enriched_items[existing_idx] = enriched
                    else:
                        enriched_items.append(enriched)

                    # Save progress after each item (crash recovery)
                    self._save_progress(enriched_items)

                except KeyboardInterrupt:
                    actual_idx = global_idx + i
                    print(f"\n\n[!] Interrupted at item #{actual_idx}. Progress saved.")
                    print(f"  Resume with: --resume {actual_idx}")
                    self.logger.warning(f"INTERRUPTED at item #{actual_idx}")
                    self._save_progress(enriched_items)
                    interrupted = True
                    break

                except Exception as e:
                    self.logger.error(f"EXCEPTION enriching '{item['name']}': {e}")
                    print(f"\n  [FAIL] Error enriching '{item['name']}': {e}")

                    # Record failure
                    self._batch_results.append({
                        "mfp_id": item["mfp_id"],
                        "name": item["name"],
                        "status": "ERROR",
                        "error": str(e),
                    })
                    enriched_items.append(item)  # Keep original on failure
                    continue

            if interrupted:
                break

            # Save after batch
            self._save_progress(enriched_items)
            self._save_sources()

            # Print batch audit
            self._print_batch_audit(batch_num if batch_size > 0 else 1)
            self._save_batch_audit(batch_num if batch_size > 0 else 0)

            # Move to next batch
            global_idx = batch_end

            # If batch mode and more items remain, ask to continue
            if batch_size > 0 and global_idx < resume_from + total:
                remaining = resume_from + total - global_idx
                print(f"\n  {remaining} items remaining.")
                print(f"  Resume index if you stop now: --resume {global_idx}")

                try:
                    answer = input("\n  Continue to next batch? [Y/n]: ").strip().lower()
                    if answer in ("n", "no", "q", "quit", "stop"):
                        print(f"\n[OK] Paused. Resume later with: --resume {global_idx}")
                        self.logger.info(f"User paused at item #{global_idx}")
                        break
                except (EOFError, KeyboardInterrupt):
                    print(f"\n[OK] Paused. Resume later with: --resume {global_idx}")
                    break

        # Final save
        self._save_progress(enriched_items)
        self._save_sources()

        # Final validation
        print("\n" + "=" * 60)
        print("  FINAL VALIDATION")
        print("=" * 60)
        summary = validate_dataset(enriched_items)
        print_validation_report(summary)
        save_report(summary)

        self.logger.info(f"Run complete. {len(enriched_items)} items in dataset.")

        return enriched_items

    # =========================================================================
    #  BATCH AUDIT
    # =========================================================================

    def _print_batch_audit(self, batch_num: int):
        """Print a detailed audit report after each batch."""
        results = self._batch_results
        if not results:
            return

        total = len(results)
        success = sum(1 for r in results if r.get("status") == "SUCCESS")
        failed = sum(1 for r in results if r.get("status") in ("FAILED", "ERROR"))

        avg_duration = 0
        durations = [r.get("duration_seconds", 0) for r in results if r.get("duration_seconds")]
        if durations:
            avg_duration = sum(durations) / len(durations)

        total_fields_gained = sum(r.get("fields_gained", 0) for r in results)

        print(f"\n{'~' * 60}")
        print(f"  BATCH {batch_num} AUDIT REPORT")
        print(f"{'~' * 60}")
        print(f"  Items processed:     {total}")
        print(f"  Successful:          {success}")
        print(f"  Failed:              {failed}")
        print(f"  Avg time per item:   {avg_duration:.1f}s")
        print(f"  Total fields gained: {total_fields_gained}")

        # Per-item summary table
        print(f"\n  {'ID':<5} {'Name':<30} {'Status':<8} {'Fields':<12} {'Time':<7}")
        print(f"  {'-'*5} {'-'*30} {'-'*8} {'-'*12} {'-'*7}")

        for r in results:
            name = r["name"][:29]
            status = r.get("status", "?")
            if status == "SUCCESS":
                status_str = "[OK]"
            elif status == "FAILED":
                status_str = "[FAIL]"
            else:
                status_str = "[ERR]"

            fields = f"{r.get('fields_after', '?')}/9 (+{r.get('fields_gained', 0)})"
            duration = f"{r.get('duration_seconds', 0):.0f}s"

            print(f"  {r['mfp_id']:<5} {name:<30} {status_str:<8} {fields:<12} {duration:<7}")

        # Show failures in detail
        failures = [r for r in results if r.get("status") in ("FAILED", "ERROR")]
        if failures:
            print(f"\n  FAILURES ({len(failures)}):")
            for r in failures:
                print(f"    - {r['name']}: {r.get('error', 'Unknown error')}")

        print(f"{'~' * 60}")

        # Log to file
        self.logger.info(f"Batch {batch_num} audit: {success}/{total} success, {failed} failed")
        for r in results:
            self.logger.info(
                f"  {r['mfp_id']:>3} | {r['name']:<30} | {r.get('status'):<8} | "
                f"fields={r.get('fields_after', '?')}/9 | {r.get('duration_seconds', 0):.1f}s"
            )

    def _save_batch_audit(self, batch_num: int):
        """Save batch audit to a JSON file."""
        audit_dir = config.DATA_DIR / "audits"
        audit_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = audit_dir / f"batch_{batch_num}_{timestamp}.json"

        audit_data = {
            "batch_number": batch_num,
            "timestamp": timestamp,
            "total_items": len(self._batch_results),
            "successful": sum(1 for r in self._batch_results if r.get("status") == "SUCCESS"),
            "failed": sum(1 for r in self._batch_results if r.get("status") in ("FAILED", "ERROR")),
            "items": self._batch_results,
        }

        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Batch audit saved to {audit_file}")
        self.logger.info(f"Batch audit saved to {audit_file}")

    # =========================================================================
    #  FILE I/O
    # =========================================================================

    def _save_progress(self, items: list[dict]):
        """Save enriched items to JSON (for crash recovery)."""
        config.ENRICHED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.ENRICHED_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

    def _save_sources(self):
        """Save enrichment source tracking data."""
        sources_path = config.DATA_DIR / "enrichment_sources.json"
        with open(sources_path, "w", encoding="utf-8") as f:
            json.dump(self.enrichment_sources, f, indent=2, ensure_ascii=False)
        print(f"[OK] Source tracking saved to {sources_path}")
