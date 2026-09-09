"""Regression tests for deterministic, comparison-only relevance labels."""

from mfp_scraper.market_scraper.comparison_relevance import (
    apply_query_overrides,
    build_profile,
    label_product,
)


RANGEENI = {
    "mfp_id": 10,
    "name": "Rangeeni Lac",
    "scientific_name": "Kerria lacca",
    "current_products": ["Lac resin", "Shellac", "Lac dye", "Lac wax"],
    "potential_products": ["Value-added lac products"],
    "deep_enrichment": {"relationship_summary": {"related_products": ["Lac resin", "Shellac"]}},
}


def test_rangeeni_profile_replaces_only_the_known_ambiguous_query():
    profile = build_profile(RANGEENI)

    queries = apply_query_overrides(
        ["Rangeeni Lac buy online India", "Rangeeni Lac Shellac buy online India"],
        profile,
    )

    assert queries == [
        "Rangeeni lac natural resin Kerria lacca buy online India",
        "Rangeeni Lac Shellac buy online India",
    ]


def test_rangeeni_rejects_textile_lace_and_keeps_valid_lac_bangles():
    profile = build_profile(RANGEENI)

    textile = label_product({"title": "Fancy designer sequence work lace", "seller": "Craft Store"}, profile)
    bangles = label_product({"title": "Traditional natural lac bangles", "seller": "Artisan"}, profile)

    assert textile["status"] == "irrelevant"
    assert "exclusion signal" in textile["reason"]
    assert bangles["status"] == "relevant"


def test_rangeeni_rejects_a_lehenga_without_a_lac_material_signal():
    profile = build_profile(RANGEENI)

    lehenga = label_product({"title": "Meenakari Pink Lehenga Set", "seller": "Fashion Store"}, profile)

    assert lehenga["status"] == "irrelevant"
    assert "lehenga" in lehenga["exclusion_terms"]


def test_generic_mfp_does_not_reject_uncertain_products_without_manual_profile():
    profile = build_profile({"mfp_id": 6, "name": "Mahua seed", "scientific_name": "Madhuca longifolia", "current_products": [], "potential_products": []})

    label = label_product({"title": "Unknown marketplace item", "seller": "Seller"}, profile)

    assert label["status"] == "needs_review"
