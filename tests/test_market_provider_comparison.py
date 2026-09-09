"""Contract tests for the isolated Serper/Scrapingdog comparison path."""

from __future__ import annotations

from unittest.mock import patch

from app.market_comparison_service import (
    MarketProviderComparison,
    _compare_products,
    _sanitize_for_storage,
)


def product(title: str, url: str, seller: str, price: float, rank: int) -> dict:
    return {
        "title": title,
        "url": url,
        "seller": seller,
        "price": price,
        "provider_rank": rank,
        "review_count": 0,
        "rating": None,
        "image_url": "",
    }


class StubClient:
    def __init__(self, api_key: str, responses: dict[str, list[dict]]):
        self.api_key = api_key
        self.responses = responses

    def search_shopping(self, query, num_results):
        return {
            "products": self.responses.get(query, []),
            "latency_ms": 12.0,
            "error": None,
            "raw_payload": {"results": self.responses.get(query, [])},
        }

    def enrich_destination(self, product):
        return {
            "status": "complete",
            "destination_url": "https://retailer.test/product",
            "latency_ms": 8.0,
            "product_page": {"name": product["title"], "description": "Full destination-page detail"},
        }


class RecordingStubClient(StubClient):
    def __init__(self, api_key: str, responses: dict[str, list[dict]]):
        super().__init__(api_key, responses)
        self.calls = []

    def search_shopping(self, query, num_results):
        self.calls.append(query)
        return super().search_shopping(query, num_results)


def test_comparison_uses_url_then_title_seller_price_overlap():
    serper = [
        product("Mahua oil", "https://shop.test/oil?utm_source=x", "Seller A", 100, 1),
        product("Mahua soap", "https://shop.test/soap", "Seller B", 150, 2),
    ]
    scrapingdog = [
        product("Mahua oil", "https://shop.test/oil", "Seller A", 100, 3),
        product("Mahua soap", "https://different.test/item", "Seller B", 150, 1),
        product("Mahua cake", "https://shop.test/cake", "Seller C", 90, 2),
    ]

    comparison = _compare_products(serper, scrapingdog)

    assert comparison["exact_url_overlap"] == 1
    assert comparison["approximate_product_overlap"] == 1
    assert comparison["total_overlap"] == 2
    assert len(comparison["scrapingdog_only"]) == 1


def test_sanitizer_removes_api_key_from_nested_links():
    payload = _sanitize_for_storage({"link": "https://api.test/path?api_key=secret&query=mahua", "api_key": "secret"})

    assert payload["api_key"] == "[REDACTED]"
    assert "api_key" not in payload["link"]
    assert "query=mahua" in payload["link"]


def test_comparison_writes_a_separate_file_and_never_calls_the_market_path(tmp_path):
    query = "Mahua seed buy online India"
    serper = StubClient("serper-key", {query: [product("Mahua oil", "https://shop.test/oil", "Seller", 100, 1)]})
    scrapingdog = StubClient("dog-key", {query: [product("Mahua oil", "https://shop.test/oil", "Seller", 100, 1)]})

    with (
        patch("app.market_comparison_service.config_market.MARKET_COMPARISON_MODE", True),
        patch("app.market_comparison_service.config_market.MARKET_COMPARISONS_DIR", tmp_path),
        patch("app.market_comparison_service.config_market.MARKET_COMPARISON_DESTINATION_LIMIT", 1),
        patch("app.market_comparison_service._find_mfp_item", return_value={"mfp_id": 12, "name": "Mahua seed", "current_products": [], "potential_products": []}),
        patch("app.market_comparison_service.EcommerceClient.build_search_queries", return_value=[query]),
    ):
        result = MarketProviderComparison(serper, scrapingdog).compare(12)

    assert result["mode"] == "comparison_only"
    assert result["overall_comparison"]["total_overlap"] == 1
    assert result["scrapingdog_destination_pages"]["completed"] == 1
    assert (tmp_path / next(tmp_path.iterdir()).name).exists()


def test_comparison_sends_the_same_overridden_query_to_both_providers(tmp_path):
    final_query = "Rangeeni lac natural resin Kerria lacca buy online India"
    serper = RecordingStubClient("serper-key", {final_query: []})
    scrapingdog = RecordingStubClient("dog-key", {final_query: []})

    with (
        patch("app.market_comparison_service.config_market.MARKET_COMPARISON_MODE", True),
        patch("app.market_comparison_service.config_market.MARKET_COMPARISONS_DIR", tmp_path),
        patch("app.market_comparison_service._find_mfp_item", return_value={"mfp_id": 10, "name": "Rangeeni Lac", "scientific_name": "Kerria lacca", "current_products": ["Shellac"], "potential_products": []}),
        patch("app.market_comparison_service.EcommerceClient.build_search_queries", return_value=["Rangeeni Lac buy online India"]),
    ):
        result = MarketProviderComparison(serper, scrapingdog).compare(10)

    assert serper.calls == [final_query]
    assert scrapingdog.calls == [final_query]
    assert result["queries"][0]["original_query"] == "Rangeeni Lac buy online India"
    assert result["queries"][0]["query"] == final_query
