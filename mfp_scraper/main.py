"""
CLI entry point for the MFP Knowledge Engine Data Enrichment Scraper.

Usage:
    python -m mfp_scraper.main --prepare           # Parse CSV -> seed JSON
    python -m mfp_scraper.main --item "Wild Honey"  # Enrich a single item (for testing)
    python -m mfp_scraper.main --all                # Enrich all 87 items (10 per batch)
    python -m mfp_scraper.main --all --batch-size 15 # Custom batch size
    python -m mfp_scraper.main --all --batch-size 0  # No batching (process all at once)
    python -m mfp_scraper.main --resume 15          # Resume from item #15
    python -m mfp_scraper.main --validate           # Validate existing enriched data
    python -m mfp_scraper.main --export csv         # Export enriched data to CSV
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import config
from .seed_data import prepare_seed_data, load_seed_json
from .enrichment_pipeline import EnrichmentPipeline
from .validator import validate_dataset, print_validation_report, save_report


def cmd_prepare(args):
    """Parse CSV into seed JSON."""
    print("=" * 50)
    print("  STEP 1: Preparing Seed Data from CSV")
    print("=" * 50)
    items = prepare_seed_data()
    print(f"\n[OK] Seed data ready with {len(items)} items.")
    print(f"   File: {config.SEED_JSON_PATH}")


def cmd_enrich_single(args):
    """Enrich a single item (for testing)."""
    print("=" * 50)
    print(f"  ENRICHING: {args.item}")
    print("=" * 50)

    pipeline = EnrichmentPipeline()
    results = pipeline.run(single_item=args.item)

    if results:
        print("\n" + "=" * 50)
        print("  RESULT")
        print("=" * 50)
        print(json.dumps(results[0], indent=2, ensure_ascii=False))


def cmd_enrich_all(args):
    """Enrich all 87 items."""
    print("=" * 50)
    print("  ENRICHING ALL MFP ITEMS")
    print("=" * 50)

    # Ensure seed data exists
    if not config.SEED_JSON_PATH.exists():
        print("Seed data not found. Preparing from CSV first...\n")
        prepare_seed_data()

    pipeline = EnrichmentPipeline()
    results = pipeline.run(
        resume_from=args.resume or 0,
        batch_size=args.batch_size,
    )

    print(f"\n[OK] Enrichment complete! {len(results)} items processed.")
    print(f"   Output: {config.ENRICHED_JSON_PATH}")


def cmd_validate(args):
    """Validate existing enriched data."""
    if not config.ENRICHED_JSON_PATH.exists():
        print("[FAIL] No enriched data found. Run --all first.")
        sys.exit(1)

    with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    summary = validate_dataset(items)
    print_validation_report(summary)
    save_report(summary)


def cmd_export(args):
    """Export enriched data to CSV."""
    if not config.ENRICHED_JSON_PATH.exists():
        print("[FAIL] No enriched data found. Run --all first.")
        sys.exit(1)

    with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    output_path = config.DATA_DIR / f"enriched_mfp_data.{args.format}"

    if args.format == "csv":
        _export_csv(items, output_path)
    else:
        print(f"[FAIL] Unknown format: {args.format}")
        sys.exit(1)


def _export_csv(items: list[dict], output_path: Path):
    """Export enriched items to a flat CSV."""
    # Flatten list fields for CSV
    flat_items = []
    for item in items:
        flat = dict(item)
        for field in ["states", "artisan_types", "current_products", "potential_products"]:
            if isinstance(flat.get(field), list):
                flat[field] = "; ".join(flat[field])
        # Remove nested confidence dict
        flat.pop("confidence", None)
        flat.pop("applicability_raw", None)
        flat.pop("msp_notes", None)
        flat_items.append(flat)

    if not flat_items:
        print("[FAIL] No items to export.")
        return

    fieldnames = list(flat_items[0].keys())
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_items)

    print(f"[OK] Exported {len(flat_items)} items to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="MFP Knowledge Engine -- Data Enrichment Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m mfp_scraper.main --prepare            # Step 1: Parse CSV
  python -m mfp_scraper.main --item "Wild Honey"   # Step 2: Test with one item
  python -m mfp_scraper.main --all                 # Step 3: Run full enrichment (10/batch)
  python -m mfp_scraper.main --all --batch-size 15  # Custom batch size
  python -m mfp_scraper.main --validate            # Check data quality
  python -m mfp_scraper.main --export csv          # Export to CSV
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--prepare",
        action="store_true",
        help="Parse CSV into structured seed JSON",
    )
    group.add_argument(
        "--item",
        type=str,
        help="Enrich a single item by name (for testing)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Enrich all 87 MFP items",
    )
    group.add_argument(
        "--validate",
        action="store_true",
        help="Validate existing enriched data",
    )
    group.add_argument(
        "--export",
        type=str,
        choices=["csv"],
        help="Export enriched data to the specified format",
    )

    parser.add_argument(
        "--resume",
        type=int,
        default=0,
        help="Resume enrichment from item number N (used with --all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of items to process per batch (default: 10, 0 = no batching)",
    )

    args = parser.parse_args()

    # Dispatch
    if args.prepare:
        cmd_prepare(args)
    elif args.item:
        cmd_enrich_single(args)
    elif args.all:
        cmd_enrich_all(args)
    elif args.validate:
        cmd_validate(args)
    elif args.export:
        cmd_export(args)


if __name__ == "__main__":
    main()
