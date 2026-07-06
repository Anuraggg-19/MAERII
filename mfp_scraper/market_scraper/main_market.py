"""
CLI entry point for the Market Intelligence module.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import config_market
from .market_pipeline import MarketIntelligencePipeline
from .market_validator import validate_market_outputs, print_market_validation_report, save_market_validation_report


def cmd_analyze_item(args):
    """Run market analysis for a single item."""
    _run_pipeline(single_item=args.item, args=args)


def cmd_analyze_batch(args):
    """Run market analysis in batch mode."""
    _run_pipeline(single_item=None, args=args)


def cmd_validate(args):
    """Validate current market outputs."""
    if not config_market.MARKET_DEMAND_PATH.exists():
        print("[FAIL] No market demand data found. Run --all first.")
        sys.exit(1)

    with open(config_market.MARKET_DEMAND_PATH, "r", encoding="utf-8") as handle:
        market_data = json.load(handle)
        
    market_products = []
    if config_market.MARKET_PRODUCTS_PATH.exists():
        with open(config_market.MARKET_PRODUCTS_PATH, "r", encoding="utf-8") as handle:
            market_products = json.load(handle)

    summary = validate_market_outputs(market_data, market_products)
    print_market_validation_report(summary)
    save_market_validation_report(summary)


def cmd_export(args):
    """Export market intelligence to CSV."""
    if not config_market.MARKET_DEMAND_PATH.exists():
        print("[FAIL] No market demand data found.")
        sys.exit(1)

    with open(config_market.MARKET_DEMAND_PATH, "r", encoding="utf-8") as handle:
        market_data = json.load(handle)

    output_path = config_market.DATA_DIR / f"market_demand_data.{args.export}"
    if args.export == "csv":
        _export_csv(market_data, output_path)
    else:
        print(f"[FAIL] Unknown export format: {args.export}")
        sys.exit(1)


def _run_pipeline(single_item: str | None, args):
    """Shared pipeline runner."""
    mode_label = "MARKET INTELLIGENCE PILOT" if single_item else "MARKET INTELLIGENCE BATCH"
    print("=" * 60)
    print(f"  {mode_label}")
    print("=" * 60)
    print(f"  Mode: {'APPLY (Writing to disk)' if args.apply else 'PREVIEW (Read-only)'}")
    if single_item:
        print(f"  Target: {single_item}")
    if args.limit:
        print(f"  Limit: {args.limit}")
    print(f"  Batch size: {args.batch_size}")

    pipeline = MarketIntelligencePipeline(apply_changes=args.apply)
    result = pipeline.run(
        single_item=single_item,
        resume_from=args.resume or 0,
        batch_size=args.batch_size,
        limit=args.limit or 0,
    )

    print(f"\n[OK] Market intelligence run complete. Run ID: {result['run_id']}")
    print(f"   Manifest: {config_market.MARKET_RUNS_DIR / result['run_id'] / 'manifest.json'}")
    print(f"   Preview:  {config_market.MARKET_RUNS_DIR / result['run_id'] / 'preview.json'}")
    print(f"   Validate: {config_market.MARKET_RUNS_DIR / result['run_id'] / 'validation.json'}")

    if result["items"]:
        print("\n" + "=" * 60)
        print("  SAMPLE RESULT (Market Summary)")
        print("=" * 60)
        sample = result["items"][0]
        print(f"  MFP: {sample.get('name')} (ID: {sample.get('mfp_id')})")
        print(json.dumps(sample.get("market_summary", {}), indent=2, ensure_ascii=False))


def _export_csv(items: list[dict], output_path: Path):
    """Export market analysis to a flat CSV."""
    flat_items = []
    for item in items:
        analysis = item.get("market_analysis", {})
        if analysis.get("status") in (None, "", "not_started"):
            continue

        summary = analysis.get("market_summary", {})
        competitor = analysis.get("competitor_analysis", {})

        flat = {
            "mfp_id": item.get("mfp_id"),
            "name": item.get("name"),
            "status": analysis.get("status"),
            "total_products_found": summary.get("total_products_found", 0),
            "avg_price": summary.get("avg_price", 0.0),
            "avg_rating": summary.get("avg_rating", 0.0),
            "total_reviews": summary.get("total_reviews", 0),
            "demand_score": summary.get("demand_score", 0.0),
            "trend": summary.get("trend", ""),
            "top_attributes": "; ".join(summary.get("top_attributes", [])),
            "top_brands": "; ".join(competitor.get("top_brands", [])),
            "market_gaps": "; ".join(competitor.get("market_gaps", [])),
            "price_positioning": competitor.get("price_positioning", ""),
        }
        flat_items.append(flat)

    if not flat_items:
        print("[FAIL] No analyzed items to export.")
        return

    fieldnames = list(flat_items[0].keys())
    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_items)

    print(f"[OK] Exported {len(flat_items)} market analysis records to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Module 2: Market Demand Intelligence Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m mfp_scraper.market_scraper --item "Wild Honey" --preview
  python -m mfp_scraper.market_scraper --all --preview --limit 5
  python -m mfp_scraper.market_scraper --all --apply
  python -m mfp_scraper.market_scraper --validate
  python -m mfp_scraper.market_scraper --export csv
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--item", type=str, help="Preview or apply market analysis for one item")
    group.add_argument("--all", action="store_true", help="Preview or apply market analysis for all items")
    group.add_argument("--validate", action="store_true", help="Validate existing market data outputs")
    group.add_argument("--export", type=str, choices=["csv"], help="Export market data to CSV")

    parser.add_argument(
        "--resume",
        type=int,
        default=0,
        help="Resume from filtered item index N for batch commands",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Items per batch (default 5 for market scraping)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of items to process",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply market analysis to canonical files. Default is preview-only.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Run in preview mode without writing to disk (default).",
    )

    args = parser.parse_args()

    if args.item:
        cmd_analyze_item(args)
    elif args.all:
        cmd_analyze_batch(args)
    elif args.validate:
        cmd_validate(args)
    elif args.export:
        cmd_export(args)


if __name__ == "__main__":
    main()
