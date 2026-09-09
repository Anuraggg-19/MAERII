"""Deterministic market-product relevance labels.

It derives a conservative baseline from each MFP's enriched metadata, with
small manual profiles only for demonstrated search-term collisions. Callers
decide whether a label is display-only or an early rejection guard.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PROFILE_PATH = Path(__file__).with_name("comparison_relevance_profiles.json")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def _phrases(values: list[object], minimum_words: int = 1) -> list[str]:
    seen: set[str] = set()
    phrases: list[str] = []
    for value in values:
        phrase = _normalise(value)
        if not phrase or len(phrase.split()) < minimum_words or phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
    return phrases


@lru_cache(maxsize=1)
def _profiles() -> dict[str, Any]:
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"version": 1, "profiles": {}}


def build_profile(mfp_item: dict[str, Any]) -> dict[str, Any]:
    """Build an MFP profile from existing data plus an optional override."""
    stored = _profiles()
    override = stored.get("profiles", {}).get(str(mfp_item.get("mfp_id")), {})
    related = mfp_item.get("deep_enrichment", {}).get("relationship_summary", {}).get("related_products", [])
    material_name = _normalise(mfp_item.get("name"))
    scientific_name = _normalise(mfp_item.get("scientific_name"))
    product_terms = _phrases(
        list(mfp_item.get("current_products", []))
        + list(mfp_item.get("potential_products", []))
        + list(related if isinstance(related, list) else [])
    )
    # Product phrases are useful when they contain enough context ("sal seed
    # oil"), but one-word phrases such as "oil" are too generic to prove a
    # result belongs to the target material.
    product_terms = [term for term in product_terms if len(term.split()) > 1]
    strong_terms = _phrases([material_name, scientific_name])
    return {
        "version": stored.get("version", 1),
        "mfp_id": mfp_item.get("mfp_id"),
        "manual_profile": bool(override),
        "positive_terms": _phrases(list(override.get("positive_terms", [])) + strong_terms + product_terms),
        "strong_terms": _phrases(list(override.get("positive_terms", [])) + strong_terms),
        "negative_terms": _phrases(list(override.get("negative_terms", []))),
        "query_overrides": dict(override.get("query_overrides", {})),
    }


def apply_query_overrides(queries: list[str], profile: dict[str, Any]) -> list[str]:
    """Use an override only for a known ambiguous query, preserving order."""
    overrides = {_normalise(source): target for source, target in profile.get("query_overrides", {}).items()}
    changed: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = overrides.get(_normalise(query), query)
        key = _normalise(value)
        if key and key not in seen:
            seen.add(key)
            changed.append(value)
    return changed


def _matches(text: str, terms: list[str]) -> list[str]:
    padded = f" {text} "
    return [term for term in terms if f" {term} " in padded]


def label_product(product: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable label without modifying or removing the product."""
    text = _normalise(" ".join(str(product.get(field, "")) for field in ("title", "seller", "source")))
    positives = _matches(text, profile.get("positive_terms", []))
    strong = _matches(text, profile.get("strong_terms", []))
    negatives = _matches(text, profile.get("negative_terms", []))
    if negatives and not strong:
        status = "irrelevant"
        reason = f"Matched exclusion signal: {negatives[0]}; no target-material signal found."
    elif strong and negatives:
        status = "needs_review"
        reason = f"Matched both target and exclusion signals: {strong[0]} / {negatives[0]}."
    elif strong:
        status = "relevant"
        reason = f"Matched target-material signal: {strong[0]}."
    elif positives:
        status = "relevant"
        reason = f"Matched known product form: {positives[0]}."
    else:
        # No automatic rejection for ordinary MFPs. This protects materials
        # with incomplete enrichment data and leaves uncertain listings visible
        # in the explicit review/raw views.
        status = "needs_review"
        reason = "No strong material signal found in the listing metadata."
    return {
        "status": status,
        "matched_terms": positives[:8],
        "exclusion_terms": negatives[:8],
        "reason": reason,
    }


def label_products(products: list[dict[str, Any]], profile: dict[str, Any], enabled: bool) -> None:
    """Attach labels in place; source product fields stay intact."""
    for product in products:
        product["relevance"] = (
            label_product(product, profile)
            if enabled
            else {"status": "not_evaluated", "matched_terms": [], "exclusion_terms": [], "reason": "Comparison relevance filtering is disabled."}
        )
