"""
Seed data loader — reads the 87 MFP items from CSV and produces structured seed JSON.
"""

import csv
import json
import re
from pathlib import Path
from typing import Optional

from . import config


def _parse_msp(raw: str) -> dict:
    """
    Parse MSP value which may be a simple number or a complex string like
    '3200 / 1500 (per Thousand)'.
    Returns {"value": <number>, "unit": "kg", "notes": <optional string>}.
    """
    raw = raw.strip()
    if not raw:
        return {"value": None, "unit": "kg", "notes": ""}

    # Handle complex MSP like "3200 / 1500 (per Thousand)"
    if "/" in raw and "per" in raw.lower():
        return {"value": None, "unit": "kg", "notes": raw}

    # Try to extract just the number
    match = re.search(r"[\d.]+", raw)
    if match:
        try:
            return {"value": float(match.group()), "unit": "kg", "notes": ""}
        except ValueError:
            pass

    return {"value": None, "unit": "kg", "notes": raw}


def _parse_applicability(raw: str) -> list[str]:
    """
    Parse the Applicability column.
    - 'All India' → empty list (to be resolved by scraper)
    - 'N.E.States' → NE state list
    - 'Jharkhand' → ['Jharkhand']
    - 'Odisha, Chhattisgarh, ...' → split list
    """
    raw = raw.strip().strip('"')

    if raw.lower() == "all india":
        return []  # Will be resolved during enrichment

    if raw.lower() in ("n.e.states", "n.e. states", "ne states"):
        return list(config.NE_STATES)

    # Split by comma and clean
    states = [s.strip() for s in raw.replace("&", ",").split(",")]
    return [s for s in states if s]


def _clean_scientific_name(raw: str) -> Optional[str]:
    """Clean scientific name — fix missing spaces, strip noise."""
    raw = raw.strip()
    if not raw:
        return None

    # Remove parenthetical notes like "(Seeds)", "(Dry)", "(Raw)"
    cleaned = re.sub(r"\s*\(.*?\)\s*", "", raw).strip()

    # Fix cases where genus+species are concatenated without space
    # e.g., "Shorearobusta" → "Shorea robusta"
    # Pattern: lowercase followed by uppercase suggests missing space
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)

    return cleaned if cleaned else None


def _expand_category(code: str) -> str:
    """Map category code to full name."""
    code = code.strip()
    return config.CATEGORY_MAP.get(code, code)


def load_csv(csv_path: Optional[Path] = None) -> list[dict]:
    """
    Load the MFP CSV file and return a list of seed item dicts.
    Each item has: mfp_id, name, scientific_name, msp, unit, category, states
    """
    csv_path = csv_path or config.CSV_PATH

    items = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            name = row.get("Name of MFPs", "").strip()
            if not name:
                continue

            msp_data = _parse_msp(row.get("MSP Rates (in Rs. Per Kg.)", ""))
            scientific_name = _clean_scientific_name(
                row.get("Scientific Name", "")
            )
            category = _expand_category(row.get("Category", ""))
            states = _parse_applicability(row.get("Applicability", ""))
            applicability_raw = row.get("Applicability", "").strip()

            item = {
                "mfp_id": idx,
                "name": name,
                "scientific_name": scientific_name,
                "category": category,
                "msp": msp_data["value"],
                "unit": msp_data["unit"],
                "msp_notes": msp_data["notes"] if msp_data["notes"] else None,
                "applicability_raw": applicability_raw,
                "states": states,
                # Fields to be enriched by scraper:
                "description": None,
                "season": None,
                "shelf_life": None,
                "artisan_types": [],
                "current_products": [],
                "potential_products": [],
                "image_url": None,
            }
            items.append(item)

    return items


def save_seed_json(items: list[dict], output_path: Optional[Path] = None):
    """Save seed items to JSON file."""
    output_path = output_path or config.SEED_JSON_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {len(items)} seed items to {output_path}")


def load_seed_json(path: Optional[Path] = None) -> list[dict]:
    """Load seed items from JSON file."""
    path = path or config.SEED_JSON_PATH
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_seed_data():
    """Full pipeline: CSV → cleaned seed JSON."""
    print("Loading CSV...")
    items = load_csv()
    print(f"  Found {len(items)} items")

    # Stats
    have_sci_name = sum(1 for i in items if i["scientific_name"])
    have_states = sum(1 for i in items if i["states"])
    all_india = sum(1 for i in items if i["applicability_raw"].lower() == "all india")

    print(f"  Scientific names present: {have_sci_name}/{len(items)}")
    print(f"  Specific states: {have_states}/{len(items)}")
    print(f"  'All India' (needs resolution): {all_india}/{len(items)}")

    save_seed_json(items)
    return items


if __name__ == "__main__":
    prepare_seed_data()
