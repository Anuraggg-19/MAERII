"""
CLI entry point for the MFP Knowledge Engine.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import config
from .deep_pipeline import DeepEnrichmentPipeline, validate_current_deep_outputs
from .enrichment_pipeline import EnrichmentPipeline
from .rollback import rollback_run
from .seed_data import load_seed_json, prepare_seed_data
from .validator import print_validation_report, save_report, validate_dataset


def cmd_prepare(args):
    """Parse CSV into seed JSON."""
    print("=" * 50)
    print("  STEP 1: Preparing Seed Data from CSV")
    print("=" * 50)
    items = prepare_seed_data()
    print(f"\n[OK] Seed data ready with {len(items)} items.")
    print(f"   File: {config.SEED_JSON_PATH}")


def cmd_enrich_single(args):
    """Enrich a single item with the original pipeline."""
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
    """Enrich all items with the original pipeline."""
    print("=" * 50)
    print("  ENRICHING ALL MFP ITEMS")
    print("=" * 50)

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
    """Validate the original enriched dataset."""
    if not config.ENRICHED_JSON_PATH.exists():
        print("[FAIL] No enriched data found. Run --all first.")
        sys.exit(1)

    with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as handle:
        items = json.load(handle)

    summary = validate_dataset(items)
    print_validation_report(summary)
    save_report(summary)


def cmd_export(args):
    """Export enriched data to CSV."""
    if not config.ENRICHED_JSON_PATH.exists():
        print("[FAIL] No enriched data found. Run --all first.")
        sys.exit(1)

    with open(config.ENRICHED_JSON_PATH, "r", encoding="utf-8") as handle:
        items = json.load(handle)

    output_path = config.DATA_DIR / f"enriched_mfp_data.{args.export}"
    if args.export == "csv":
        _export_csv(items, output_path)
    else:
        print(f"[FAIL] Unknown format: {args.export}")
        sys.exit(1)


def cmd_deep_item(args):
    """Run additive deep enrichment for one existing enriched item."""
    _run_deep_pipeline(single_item=args.deep_item, args=args)


def cmd_deep_batch(args):
    """Run additive deep enrichment in selected-item batch mode."""
    _run_deep_pipeline(single_item=None, args=args)


def cmd_deep_validate(args):
    """Validate canonical additive deep-enrichment outputs."""
    summary = validate_current_deep_outputs()
    print(f"\n[OK] Deep validation written to {config.DATA_DIR / 'deep_enrichment_validation.json'}")
    return summary


def cmd_rollback(args):
    """Rollback canonical deep-enrichment outputs to a previous run snapshot."""
    manifest = rollback_run(args.rollback)
    print(f"[OK] Rollback complete from run {manifest['restored_from_run_id']}")
    print(f"   Recovery manifest: {config.DEEP_RUNS_DIR / manifest['run_id'] / 'manifest.json'}")


def _run_deep_pipeline(single_item: str | None, args):
    """Shared deep-enrichment runner used by single-item and batch commands."""
    mode_label = "DEEP ENRICHMENT PILOT" if single_item else "DEEP ENRICHMENT BATCH"
    print("=" * 60)
    print(f"  {mode_label}")
    print("=" * 60)
    print(f"  Mode: {'APPLY' if args.apply else 'PREVIEW'}")
    if single_item:
        print(f"  Target: {single_item}")
    if args.limit:
        print(f"  Limit: {args.limit}")
    print(f"  Batch size: {args.batch_size}")

    pipeline = DeepEnrichmentPipeline(apply_changes=args.apply)
    result = pipeline.run(
        single_item=single_item,
        resume_from=args.resume or 0,
        batch_size=args.batch_size,
        limit=args.limit or 0,
    )

    print(f"\n[OK] Deep enrichment run complete. Run ID: {result['run_id']}")
    print(f"   Manifest: {config.DEEP_RUNS_DIR / result['run_id'] / 'manifest.json'}")
    print(f"   Preview:  {config.DEEP_RUNS_DIR / result['run_id'] / 'preview.json'}")
    print(f"   Validate: {config.DEEP_RUNS_DIR / result['run_id'] / 'validation.json'}")

    if result["items"]:
        print("\n" + "=" * 60)
        print("  SAMPLE RESULT")
        print("=" * 60)
        print(json.dumps(result["items"][0]["deep_enrichment"], indent=2, ensure_ascii=False))


def _export_csv(items: list[dict], output_path: Path):
    """Export enriched items to a flat CSV."""
    flat_items = []
    for item in items:
        flat = dict(item)
        for field in ["states", "artisan_types", "current_products", "potential_products"]:
            if isinstance(flat.get(field), list):
                flat[field] = "; ".join(flat[field])
        flat.pop("confidence", None)
        flat.pop("applicability_raw", None)
        flat.pop("msp_notes", None)
        flat_items.append(flat)

    if not flat_items:
        print("[FAIL] No items to export.")
        return

    fieldnames = list(flat_items[0].keys())
    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_items)

    print(f"[OK] Exported {len(flat_items)} items to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="MFP Knowledge Engine -- Base and deep additive enrichment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m mfp_scraper.main --prepare
  python -m mfp_scraper.main --item "Wild Honey"
  python -m mfp_scraper.main --all --batch-size 15
  python -m mfp_scraper.main --deep-item "Wild Honey"
  python -m mfp_scraper.main --deep-item "Wild Honey" --apply
  python -m mfp_scraper.main --deep-batch --limit 5 --batch-size 2
  python -m mfp_scraper.main --deep-batch --limit 5 --batch-size 2 --apply
  python -m mfp_scraper.main --deep-validate
  python -m mfp_scraper.main --rollback deep_20260614T120000Z
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true", help="Parse CSV into structured seed JSON")
    group.add_argument("--item", type=str, help="Enrich a single item by name (original pipeline)")
    group.add_argument("--all", action="store_true", help="Enrich all items (original pipeline)")
    group.add_argument("--validate", action="store_true", help="Validate existing base enriched data")
    group.add_argument("--export", type=str, choices=["csv"], help="Export enriched data to the specified format")
    group.add_argument("--deep-item", type=str, help="Preview or apply additive deep enrichment for one item")
    group.add_argument("--deep-batch", action="store_true", help="Preview or apply additive deep enrichment in batch mode")
    group.add_argument("--deep-validate", action="store_true", help="Validate additive deep-enrichment outputs")
    group.add_argument("--rollback", type=str, help="Rollback deep-enrichment outputs from a prior run id")

    parser.add_argument(
        "--resume",
        type=int,
        default=0,
        help="Resume from filtered item index N for batch commands",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Items per batch (0 = process all selected items before one commit)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of selected items for deep batch or pilot runs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deep enrichment to canonical files. Default is preview-only.",
    )

    args = parser.parse_args()

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
    elif args.deep_item:
        cmd_deep_item(args)
    elif args.deep_batch:
        cmd_deep_batch(args)
    elif args.deep_validate:
        cmd_deep_validate(args)
    elif args.rollback:
        cmd_rollback(args)


if __name__ == "__main__":
    main()
