"""
Validator -- cross-validates extracted data and generates quality reports.
"""

import json
from pathlib import Path
from typing import Optional

from . import config


def validate_item(item: dict) -> dict:
    """
    Validate a single enriched item. Returns a report dict with:
    - completeness: fraction of target fields that are non-null/non-empty
    - missing_fields: list of missing/empty fields
    - low_confidence_fields: fields with confidence < 0.6
    - issues: list of detected problems
    """
    report = {
        "mfp_id": item["mfp_id"],
        "name": item["name"],
        "completeness": 0.0,
        "missing_fields": [],
        "low_confidence_fields": [],
        "issues": [],
    }

    filled = 0
    total = len(config.TARGET_FIELDS)

    for field in config.TARGET_FIELDS:
        value = item.get(field)
        if value is None or value == "" or value == []:
            report["missing_fields"].append(field)
        else:
            filled += 1

    report["completeness"] = round(filled / total, 2) if total > 0 else 0.0

    # Check confidence scores
    confidence = item.get("confidence", {})
    for field, score in confidence.items():
        if isinstance(score, (int, float)) and score < 0.6:
            report["low_confidence_fields"].append(
                {"field": field, "score": score}
            )

    # Specific validations
    if item.get("states") and len(item["states"]) > 15:
        report["issues"].append(
            "Too many states listed -- may not be specific enough"
        )

    if item.get("states") and not item["states"]:
        report["issues"].append("States still empty after enrichment")

    if item.get("description") and len(item.get("description", "")) < 15:
        report["issues"].append("Description is suspiciously short")

    if item.get("current_products") and item.get("potential_products"):
        overlap = set(item["current_products"]) & set(item["potential_products"])
        if overlap:
            report["issues"].append(
                f"Overlap between current and potential products: {overlap}"
            )

    return report


def validate_dataset(items: list[dict]) -> dict:
    """
    Validate the full enriched dataset. Returns summary report.
    """
    reports = [validate_item(item) for item in items]

    # Summary stats
    total = len(items)
    fully_complete = sum(1 for r in reports if r["completeness"] == 1.0)
    avg_completeness = (
        sum(r["completeness"] for r in reports) / total if total else 0
    )

    # Field-level coverage
    field_coverage = {}
    for field in config.TARGET_FIELDS:
        filled = sum(
            1 for item in items
            if item.get(field) is not None
            and item.get(field) != ""
            and item.get(field) != []
        )
        field_coverage[field] = f"{filled}/{total}"

    # Items needing human review
    needs_review = [
        r for r in reports
        if r["completeness"] < 0.7
        or r["low_confidence_fields"]
        or r["issues"]
    ]

    summary = {
        "total_items": total,
        "fully_complete": fully_complete,
        "average_completeness": round(avg_completeness, 2),
        "field_coverage": field_coverage,
        "items_needing_review": len(needs_review),
        "review_items": [
            {
                "name": r["name"],
                "completeness": r["completeness"],
                "missing": r["missing_fields"],
                "low_confidence": r["low_confidence_fields"],
                "issues": r["issues"],
            }
            for r in needs_review
        ],
        "all_reports": reports,
    }

    return summary


def print_validation_report(summary: dict):
    """Print a human-readable validation report."""
    print("\n" + "=" * 60)
    print("  ENRICHMENT VALIDATION REPORT")
    print("=" * 60)

    print(f"\n  Total items:          {summary['total_items']}")
    print(f"  Fully complete:       {summary['fully_complete']}")
    print(f"  Avg completeness:     {summary['average_completeness']:.0%}")
    print(f"  Items needing review: {summary['items_needing_review']}")

    print("\n  Field Coverage:")
    for field, coverage in summary["field_coverage"].items():
        print(f"    {field:25s} {coverage}")

    if summary["review_items"]:
        print(f"\n  Items Flagged for Review ({len(summary['review_items'])}):")
        for item in summary["review_items"][:10]:  # Show top 10
            print(f"\n    * {item['name']} (completeness: {item['completeness']:.0%})")
            if item["missing"]:
                print(f"      Missing: {', '.join(item['missing'])}")
            if item["low_confidence"]:
                lc = [f"{x['field']}({x['score']:.1f})" for x in item["low_confidence"]]
                print(f"      Low confidence: {', '.join(lc)}")
            if item["issues"]:
                for issue in item["issues"]:
                    print(f"      [!] {issue}")

    print("\n" + "=" * 60)


def save_report(summary: dict, path: Optional[Path] = None):
    """Save validation report to JSON."""
    path = path or config.ENRICHMENT_LOG_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[OK] Validation report saved to {path}")
