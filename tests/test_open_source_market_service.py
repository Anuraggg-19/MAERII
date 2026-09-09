"""Focused no-network tests for the isolated open-source experiment helpers."""

from app.open_source_market_service import _dedupe_urls, _extract_page_product, _select_balanced_candidates
from mfp_scraper.market_scraper.market_extractor import MarketExtractor


def test_open_source_extractor_uses_jsonld_product_metadata():
    html = """
    <html><head><title>Fallback title</title>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Pure Mahua Oil",
     "description":"Cold pressed", "sku":"MO-42", "brand":{"name":"Forest Co"},
     "image":"https://images.example/oil.jpg",
     "offers":{"@type":"Offer","price":"299","priceCurrency":"INR"},
     "aggregateRating":{"ratingValue":"4.6","reviewCount":"21"}}
    </script></head><body></body></html>
    """

    product = _extract_page_product(html, "https://retailer.example/mahua-oil", {"query": "Mahua seed oil"})

    assert product["title"] == "Pure Mahua Oil"
    assert product["price"] == 299.0
    assert product["brand"] == "Forest Co"
    assert product["extraction_method"] == "json_ld"


def test_open_source_url_dedupe_removes_tracking_variants_by_path():
    candidates = _dedupe_urls([
        {"url": "https://retailer.example/item?utm_source=a"},
        {"url": "https://retailer.example/item?ref=b"},
        {"url": "https://retailer.example/other"},
    ])

    assert len(candidates) == 2


def test_open_source_candidate_selection_represents_each_query_before_extras():
    runs = [
        {"candidates": [{"url": "https://research.example/a", "title": "Research paper"}, {"url": "https://shop.example/product-a", "title": "Buy product"}]},
        {"candidates": [{"url": "https://shop.example/product-b", "title": "Buy product"}, {"url": "https://shop.example/product-c", "title": "Buy product"}]},
    ]

    selected = _select_balanced_candidates(runs, 2)

    assert len(selected) == 2
    assert selected[0]["url"] == "https://shop.example/product-a"
    assert selected[1]["url"] == "https://shop.example/product-b"


def test_keyword_matching_does_not_treat_lace_as_lac():
    extractor = MarketExtractor()
    items = [{"mfp_id": 10, "name": "Rangeeni Lac", "current_products": [], "potential_products": []}]
    products = [
        {"title": "Designer Lace Lingerie", "matched_mfp_ids": [], "confidence": 0.0},
        {"title": "Natural Lac Resin", "matched_mfp_ids": [], "confidence": 0.0},
    ]

    classified = extractor._keyword_classify(products, items, 10)

    assert classified[0]["matched_mfp_ids"] == []
    assert classified[1]["matched_mfp_ids"] == [10]
