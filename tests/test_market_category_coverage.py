"""Regression tests for fair category coverage in live market search."""

from __future__ import annotations

import unittest

from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient
from mfp_scraper.market_scraper.market_extractor import MarketExtractor


def make_product(product_id: str, title: str) -> dict:
    return {
        "product_id": product_id,
        "title": title,
        "url": f"https://example.test/{product_id}",
        "confidence": 0.0,
    }


class StubEcommerceClient(EcommerceClient):
    """Network-free client that records all generated searches."""

    def __init__(self, products_by_query: dict[str, list[dict]]):
        self.products_by_query = products_by_query
        self.calls: list[str] = []

    def search_products(self, query: str, num_results: int = 0) -> list[dict]:
        self.calls.append(query)
        return self.products_by_query.get(query, [])


class StubMarketExtractor(MarketExtractor):
    """LLM-free classifier that exposes the batch behaviour for assertions."""

    def __init__(self):
        self.provider = "stub"
        self.batch_sizes: list[int] = []
        self.prompts: list[dict] = []

    def _keyword_classify(self, products, mfp_items, target_mfp_id):
        return products

    def _llm_classify(self, products, mfp_items, target_mfp_id, target_category_context=None):
        self.batch_sizes.append(len(products))
        self.prompts.append({
            "target_mfp_id": target_mfp_id,
            "target_category_context": target_category_context,
        })
        classifications = []
        for index, product in enumerate(products):
            classifications.append({
                "product_index": index,
                "matched_mfp_ids": [target_mfp_id],
                "match_confidence": 0.9,
                "product_type": "invalid" if product["title"] == "Invalid listing" else "derived",
                "matching_attributes": ["target product"],
            })
        return classifications


class EcommerceCategoryCoverageTests(unittest.TestCase):
    def test_bamboo_ornamental_query_runs_and_its_product_survives_early_volume(self):
        mfp = {"name": "Bamboo Brooms"}
        categories = [
            {"category_name": "Home and Garden", "products": [{"name": "Bamboo Brooms"}]},
            {
                "category_name": "Handicrafts",
                "products": [{"name": "Fiber Crafts"}, {"name": "Ornamental plants"}],
            },
            {"category_name": "Paper", "products": [{"name": "Paper products"}]},
        ]
        client = StubEcommerceClient({})
        queries = client.build_search_queries(mfp, categories)
        ornamental_query = "Bamboo Brooms Ornamental plants buy online India"
        self.assertIn(ornamental_query, queries)

        products_by_query = {
            query: [make_product(f"{index}-{item}", f"{query} {item}") for item in range(20)]
            for index, query in enumerate(queries)
        }
        products_by_query[ornamental_query] = [make_product("ornamental", "Bamboo ornamental plant")]
        client = StubEcommerceClient(products_by_query)

        result = client.fetch_products_for_mfp(mfp, categories)

        self.assertEqual(client.calls, queries)
        self.assertLessEqual(len(result["products"]), 50)
        self.assertIn("Bamboo ornamental plant", [product["title"] for product in result["products"]])

    def test_cane_lampshade_query_runs_before_the_global_cap_is_applied(self):
        mfp = {"name": "Cane (Rattan)"}
        categories = [
            {
                "category_name": "Furniture",
                "products": [{"name": "Cane Chair"}, {"name": "Cane Lampshade"}],
            },
            {
                "category_name": "Handicrafts",
                "products": [{"name": "Cane Basket"}, {"name": "Cane Walking Stick"}],
            },
            {
                "category_name": "Eco Products",
                "products": [{"name": "Cane Phone Stand"}, {"name": "Cane Bag"}],
            },
        ]
        client = StubEcommerceClient({})
        queries = client.build_search_queries(mfp, categories)
        lampshade_query = "Rattan Cane Cane Lampshade buy online India"
        self.assertIn(lampshade_query, queries)

        products_by_query = {
            query: [make_product(f"{index}-{item}", f"{query} {item}") for item in range(20)]
            for index, query in enumerate(queries)
        }
        products_by_query[lampshade_query] = [make_product("lampshade", "Handwoven cane lampshade")]
        client = StubEcommerceClient(products_by_query)

        result = client.fetch_products_for_mfp(mfp, categories)

        self.assertEqual(client.calls, queries)
        self.assertIn("Handwoven cane lampshade", [product["title"] for product in result["products"]])


class LlmBatchCoverageTests(unittest.TestCase):
    def test_existing_callers_keep_the_single_batch_default(self):
        extractor = StubMarketExtractor()
        products = [make_product(str(index), f"Product {index}") for index in range(45)]

        extractor.classify_products(
            products,
            [{"mfp_id": 88, "name": "Cane (Rattan)", "current_products": [], "potential_products": []}],
            target_mfp_id=88,
        )

        self.assertEqual(extractor.batch_sizes, [40])

    def test_all_retained_products_are_classified_in_bounded_batches(self):
        extractor = StubMarketExtractor()
        products = [make_product(str(index), f"Product {index}") for index in range(45)]
        products[40]["title"] = "Invalid listing"
        category_context = [{"category_name": "Furniture", "products": [{"name": "Cane Lampshade"}]}]

        classified = extractor.classify_products(
            products,
            [{"mfp_id": 88, "name": "Cane (Rattan)", "current_products": [], "potential_products": []}],
            target_mfp_id=88,
            target_category_context=category_context,
            classify_all_batches=True,
        )

        self.assertEqual(extractor.batch_sizes, [40, 5])
        self.assertEqual(len(classified), 44)
        self.assertTrue(all(88 in product["matched_mfp_ids"] for product in classified))
        self.assertEqual(extractor.prompts[1]["target_category_context"], category_context)


if __name__ == "__main__":
    unittest.main()
