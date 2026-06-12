"""
Enrichment Pipeline -- orchestrates the full Search -> Fetch -> Extract -> Validate flow.
"""

import json
import time
from pathlib import Path
from typing import Optional
from tqdm import tqdm

from . import config
from .seed_data import load_csv, load_seed_json, save_seed_json
from .search_client import SerperClient, build_search_queries, build_image_query
from .content_fetcher import aggregate_search_content
from .llm_extractor import GeminiExtractor
from .validator import validate_dataset, print_validation_report, save_report


class EnrichmentPipeline:
    """Orchestrates the full MFP data enrichment pipeline."""

    def __init__(self):
        self.search_client = SerperClient()
        self.extractor = GeminiExtractor()
        self.enrichment_sources = {}  # Track sources per item

    def enrich_single(self, item: dict, verbose: bool = True) -> dict:
        """
        Enrich a single MFP item with all missing attributes.
        Returns the enriched item dict.
        """
        name = item["name"]
        if verbose:
            print(f"\n{'-' * 50}")
            print(f"  Enriching: {name}")
            print(f"{'-' * 50}")

        # Step 1: Build search queries for this item
        queries = build_search_queries(item)
        if verbose:
            print(f"  -> {len(queries)} search queries planned")

        # Step 2: Run searches and aggregate content
        all_search_results = []
        all_source_urls = []

        for field, query in queries.items():
            if verbose:
                print(f"  [SEARCH] {field}...")
            results = self.search_client.search(query)
            all_search_results.extend(results)
            all_source_urls.extend([r["link"] for r in results if r.get("link")])

        if verbose:
            print(f"  -> Found {len(all_search_results)} search results")

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

        if verbose:
            print(f"  -> Aggregated {len(source_text)} chars of content")

        # Step 4: LLM extraction
        if verbose:
            print(f"  [LLM] Extracting structured data via LLM...")

        extracted = self.extractor.extract(item, source_text)

        if extracted is None:
            if verbose:
                print(f"  [FAIL] Extraction failed for {name}")
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

        if verbose:
            filled = sum(
                1 for f in config.TARGET_FIELDS
                if enriched.get(f) is not None
                and enriched.get(f) != ""
                and enriched.get(f) != []
            )
            print(f"  [DONE] {filled}/{len(config.TARGET_FIELDS)} fields populated")

        return enriched

    def _merge(self, original: dict, extracted: dict) -> dict:
        """
        Merge extracted data into the original item.
        Rules:
        - Don't overwrite existing non-null values (unless extracted has higher quality)
        - For scientific_name: keep original if it exists
        - For states: merge with existing, prefer extracted if original was empty
        """
        merged = dict(original)

        # Scientific name: keep original if present, otherwise use extracted
        if not merged.get("scientific_name") and extracted.get("scientific_name"):
            merged["scientific_name"] = extracted["scientific_name"]

        # Description: always take extracted (it's always missing from CSV)
        if extracted.get("description"):
            merged["description"] = extracted["description"]

        # Season
        if extracted.get("season"):
            merged["season"] = extracted["season"]

        # Shelf life
        if extracted.get("shelf_life"):
            merged["shelf_life"] = extracted["shelf_life"]

        # States: if original was empty (i.e., "All India"), use extracted
        if not merged.get("states") and extracted.get("states"):
            merged["states"] = extracted["states"]
        elif merged.get("states") and extracted.get("states"):
            # Merge: keep originals, add any new ones from extraction
            existing = set(merged["states"])
            for state in extracted["states"]:
                existing.add(state)
            merged["states"] = sorted(existing)

        # List fields: always take extracted (they're empty in seed data)
        for field in ["artisan_types", "current_products", "potential_products"]:
            if extracted.get(field):
                merged[field] = extracted[field]

        # Confidence scores
        merged["confidence"] = extracted.get("confidence", {})

        return merged

    def _find_image(self, item: dict) -> dict:
        """Search for an appropriate image for the item."""
        query = build_image_query(item)
        results = self.search_client.search_images(query, num_results=3)

        if results:
            # Pick the first result with a valid-looking image URL
            for r in results:
                url = r.get("imageUrl", "")
                if url and url.startswith("http"):
                    item["image_url"] = url
                    break

        return item

    def run(
        self,
        items: Optional[list[dict]] = None,
        resume_from: int = 0,
        single_item: Optional[str] = None,
    ) -> list[dict]:
        """
        Run the full enrichment pipeline.

        Args:
            items: List of seed items. If None, loads from CSV.
            resume_from: Index to resume from (for interrupted runs).
            single_item: If provided, only enrich this specific item name.
        """
        # Load items
        if items is None:
            try:
                items = load_seed_json()
                print(f"Loaded {len(items)} items from seed JSON")
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

        # Load existing enriched data if resuming
        enriched_items = []
        if resume_from > 0 and config.ENRICHED_JSON_PATH.exists():
            with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as f:
                enriched_items = json.load(f)
            print(f"  Loaded {len(enriched_items)} previously enriched items")

        # Process items
        total = len(items)
        for idx, item in enumerate(
            tqdm(items[resume_from:], desc="Enriching MFP items", unit="item"),
            start=resume_from,
        ):
            try:
                enriched = self.enrich_single(item)

                # Update or append
                existing_idx = next(
                    (i for i, e in enumerate(enriched_items)
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
                print(f"\n\n[!] Interrupted at item #{idx}. Progress saved.")
                print(f"  Resume with: --resume {idx}")
                self._save_progress(enriched_items)
                break

            except Exception as e:
                print(f"\n  [FAIL] Error enriching '{item['name']}': {e}")
                enriched_items.append(item)  # Keep original on failure
                continue

        # Final save
        self._save_progress(enriched_items)
        self._save_sources()

        # Validate
        print("\nRunning validation...")
        summary = validate_dataset(enriched_items)
        print_validation_report(summary)
        save_report(summary)

        return enriched_items

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
