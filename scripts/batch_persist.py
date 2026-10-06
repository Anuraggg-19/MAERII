"""
Gentle batch persistence — processes a configurable number of MFP items
one-at-a-time with a cooldown pause between each to go easy on hardware.

Usage:
    # Process the next 5 unfinished MFP items (default pause 12s)
    python scripts/batch_persist.py --count 5

    # Process 10, with a 20-second cooldown between each
    python scripts/batch_persist.py --count 10 --pause 20

    # Dry-run to see which IDs would be picked up
    python scripts/batch_persist.py --count 5 --dry-run

    # Only run specific tasks (e.g. just categories and market)
    python scripts/batch_persist.py --count 5 --tasks categories,market

    # Start from a specific MFP ID instead of picking up where you left off
    python scripts/batch_persist.py --count 5 --start-from 20
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.enhancement_service import generate_enhancement
from app.market_service import analyze_market_realtime
from app.product_service import _load_mfp_items, get_product_categories
from app.recommendation_service import generate_recommendations

ALL_TASKS = ["categories", "market", "recommendations", "marketing"]
CHECKPOINT = ROOT / "data" / "intelligence_backfill_checkpoint.json"


# ── Checkpoint helpers (shared format with backfill_mfp_intelligence.py) ────

def load_done() -> set[str]:
    try:
        return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("completed", []))
    except (OSError, json.JSONDecodeError):
        return set()


def save_done(done: set[str]) -> None:
    CHECKPOINT.parent.mkdir(exist_ok=True)
    CHECKPOINT.write_text(json.dumps({"completed": sorted(done)}, indent=2), encoding="utf-8")


def is_mfp_fully_done(mfp_id: int, tasks: list[str], done: set[str]) -> bool:
    """True if every requested task for this MFP ID is already in the checkpoint."""
    return all(f"{mfp_id}:{t}" in done for t in tasks)


def process_one(mfp_id: int, tasks: list[str], done: set[str], dry_run: bool) -> tuple[int, int]:
    """Run all requested tasks for a single MFP ID. Returns (ok_count, fail_count).

    Task pipeline per MFP ID (same as backfill_mfp_intelligence.py):
      1. categories  → get_product_categories()
      2. market      → analyze_market_realtime()
      3. recommendations → generate_recommendations() [needs market]
      4. marketing   → generate_enhancement() for each recommendation [needs market + recommendations]
    """
    ok, fail = 0, 0
    market = None
    recommendations = None

    for task in tasks:
        key = f"{mfp_id}:{task}"
        if key in done:
            print(f"  [skip]  {key}")
            continue
        if dry_run:
            credit_note = " (uses Serper credits)" if task == "market" else ""
            print(f"  [plan]  {key}{credit_note}")
            ok += 1
            continue

        # ── Execute task (identical logic to backfill_mfp_intelligence.py) ──
        if task == "categories":
            result = get_product_categories(mfp_id)

        elif task == "market":
            result = analyze_market_realtime(mfp_id)
            market = result if result.get("status") == "complete" else None

        elif task == "recommendations":
            if not market:
                print(f"  [skip]  {key}: requires successful market result in this run")
                continue
            evidence = {name: market.get(name) for name in ("market_summary", "competitor_analysis", "top_products", "product_demand_match", "regional_market_fit", "seasonal_demand")}
            result = generate_recommendations(mfp_id, "Intermediate", "Medium", "Moderate", "All listed regions", None, evidence)
            recommendations = result.get("recommendations") if result.get("status") == "complete" else None

        elif task == "marketing":
            if not market or not recommendations:
                print(f"  [skip]  {key}: requires recommendations and market result in this run")
                continue
            evidence = {name: market.get(name) for name in ("market_summary", "competitor_analysis", "top_products")}
            for recommendation in recommendations:
                generate_enhancement(mfp_id, recommendation, evidence, fetch_related_examples=False)
            result = {"status": "complete"}

        # ── Record outcome ──────────────────────────────────────────
        if result.get("status") == "complete":
            done.add(key)
            save_done(done)
            print(f"  [ok]    {key}")
            ok += 1
        else:
            print(f"  [FAIL]  {key}: {result.get('error', 'unknown error')}")
            fail += 1

    return ok, fail


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Process N MFP items sequentially with a cooldown between each.",
    )
    parser.add_argument(
        "--count", "-n", type=int, required=True,
        help="How many MFP items to process in this batch.",
    )
    parser.add_argument(
        "--pause", type=int, default=12,
        help="Seconds to wait between MFP items (default: 12).",
    )
    parser.add_argument(
        "--tasks", default="categories,market,recommendations,marketing",
        help="Comma-separated tasks to run (default: all four).",
    )
    parser.add_argument(
        "--start-from", type=int, default=None,
        help="Start processing from this MFP ID (default: pick up where checkpoint left off).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without actually running anything.",
    )
    args = parser.parse_args()

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    valid = set(ALL_TASKS)
    if set(tasks) - valid:
        parser.error(f"Invalid tasks. Choose from: {', '.join(ALL_TASKS)}")

    # Load all MFP IDs and the checkpoint
    all_ids = [item["mfp_id"] for item in _load_mfp_items()]
    done = load_done()

    # Filter to IDs that still have work to do
    if args.start_from is not None:
        all_ids = [i for i in all_ids if i >= args.start_from]
    pending = [i for i in all_ids if not is_mfp_fully_done(i, tasks, done)]

    # Take only the requested count
    batch = pending[: args.count]

    if not batch:
        print("✅ Nothing to do — all items are already complete!")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(batch)} MFP item(s): {batch}")
    print(f"Tasks: {tasks} | Pause: {args.pause}s between items\n")

    total_ok, total_fail = 0, 0

    for i, mfp_id in enumerate(batch):
        print(f"── MFP {mfp_id} ({i + 1}/{len(batch)}) ──")
        ok, fail = process_one(mfp_id, tasks, done, args.dry_run)
        total_ok += ok
        total_fail += fail

        # Cooldown between items (skip after the last one)
        if i < len(batch) - 1 and not args.dry_run:
            print(f"  💤 Cooling down {args.pause}s …\n")
            time.sleep(args.pause)
        else:
            print()

    print(f"Done! ✅ {total_ok} ok | ❌ {total_fail} failed")


if __name__ == "__main__":
    main()

