"""Resumable local-LLM persistence batch. Market tasks consume Serper credits."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from app.enhancement_service import generate_enhancement
from app.market_service import analyze_market_realtime
from app.product_service import _load_mfp_items, get_product_categories
from app.recommendation_service import generate_recommendations

TASKS = {"categories", "market", "recommendations", "marketing"}
CHECKPOINT = ROOT / "data" / "intelligence_backfill_checkpoint.json"

def load_done() -> set[str]:
    try:
        return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("completed", []))
    except (OSError, json.JSONDecodeError):
        return set()

def save_done(done: set[str]) -> None:
    CHECKPOINT.parent.mkdir(exist_ok=True)
    CHECKPOINT.write_text(json.dumps({"completed": sorted(done)}, indent=2), encoding="utf-8")

parser = argparse.ArgumentParser()
target = parser.add_mutually_exclusive_group(required=True)
target.add_argument("--all", action="store_true")
target.add_argument("--mfp-id", type=int)
parser.add_argument("--tasks", default="categories,market,recommendations,marketing")
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--resume", action="store_true")
args = parser.parse_args()
tasks = [task.strip() for task in args.tasks.split(",") if task.strip()]
if set(tasks) - TASKS:
    parser.error("tasks must be categories,market,recommendations,marketing")
ids = [item["mfp_id"] for item in _load_mfp_items()] if args.all else [args.mfp_id]
done = load_done() if args.resume else set()

for mfp_id in ids:
    market = None
    recommendations = None
    for task in tasks:
        key = f"{mfp_id}:{task}"
        if key in done:
            print(f"[skip] {key}")
            continue
        if args.dry_run:
            print(f"[plan] {key}" + (" (uses Serper credits)" if task == "market" else ""))
            continue
        if task == "categories":
            result = get_product_categories(mfp_id)
        elif task == "market":
            result = analyze_market_realtime(mfp_id)
            market = result if result.get("status") == "complete" else None
        elif task == "recommendations":
            if not market:
                print(f"[skip] {key}: requires successful market result in this run")
                continue
            evidence = {name: market.get(name) for name in ("market_summary", "competitor_analysis", "top_products", "product_demand_match", "regional_market_fit", "seasonal_demand")}
            result = generate_recommendations(mfp_id, "Intermediate", "Medium", "Moderate", "All listed regions", None, evidence)
            recommendations = result.get("recommendations") if result.get("status") == "complete" else None
        else:
            if not market or not recommendations:
                print(f"[skip] {key}: requires recommendations and market result in this run")
                continue
            evidence = {name: market.get(name) for name in ("market_summary", "competitor_analysis", "top_products")}
            for recommendation in recommendations:
                generate_enhancement(mfp_id, recommendation, evidence, fetch_related_examples=False)
            result = {"status": "complete"}
        if result.get("status") == "complete":
            done.add(key); save_done(done); print(f"[ok] {key}")
        else:
            print(f"[failed] {key}: {result.get('error', 'unknown error')}")
