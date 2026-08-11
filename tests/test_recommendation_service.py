"""Focused contract tests for product recommendation generation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.recommendation_service import (
    RecommendationValidationError,
    _fallback_recommendations,
    _generate_validated_recommendations,
    build_recommendation_context,
    generate_recommendations,
    validate_constraints,
    validate_market_context,
    validate_recommendations,
)


MFP = {
    "mfp_id": 12,
    "name": "Test MFP",
    "msp": 50,
    "states": ["Madhya Pradesh"],
    "material_properties": {"workability": "high"},
    "artisan_types": ["Weaving"],
    "potential_products": ["Product One", "Product Two", "Product Three"],
}
MARKET_CONTEXT = {
    "market_summary": {"demand_score": 0.75, "avg_price": 350},
    "competitor_analysis": {"market_gaps": ["Gift-ready packaging"]},
    "top_products": [{"title": "Test MFP basket", "price": 400}],
}

# Categories with mixed difficulty levels for constraint testing
MIXED_CATEGORIES = [
    {"category_name": "Craft", "products": [
        {"name": "Simple Basket", "difficulty": "Easy", "market_potential": "high",
         "estimated_cost": "INR 50-100 per item",
         "manufacturing_process": ["Sort", "Weave", "Finish"]},
        {"name": "Decorative Tray", "difficulty": "Medium", "market_potential": "medium",
         "estimated_cost": "INR 100-150 per item",
         "manufacturing_process": ["Sort", "Shape", "Weave", "Finish"]},
        {"name": "Artisan Lamp", "difficulty": "Hard", "market_potential": "high",
         "estimated_cost": "INR 200-350 per item",
         "manufacturing_process": ["Sort", "Frame", "Weave", "Wire", "Finish"]},
    ]},
    {"category_name": "Food", "products": [
        {"name": "Herbal Tea", "difficulty": "Easy", "market_potential": "medium",
         "estimated_cost": "INR 30-60 per item",
         "manufacturing_process": ["Dry", "Grind", "Pack"]},
        {"name": "Premium Extract", "difficulty": "Hard", "market_potential": "high",
         "estimated_cost": "INR 500-800 per item",
         "manufacturing_process": ["Harvest", "Steam distil", "Filter", "Bottle", "Label", "Cure"]},
    ]},
]


def valid_llm_result():
    return {
        "recommendations": [
            {
                "product_name": "Product One",
                "category_name": "Craft",
                "rationale": "Uses the material and fills a market gap.",
                "unit_cost_inr": 100,
                "expected_selling_price_inr": 250,
                "demand_score": 78,
                "export_potential": "High",
                "difficulty": "Easy",
                "artisan_guide": ["Sort material", "Make product", "Package product"],
                "target_customer_segment": "Urban gift buyers",
            },
            {
                "product_name": "Product Two",
                "category_name": "Craft",
                "rationale": "Uses available artisan skills.",
                "unit_cost_inr": 120,
                "expected_selling_price_inr": 260,
                "demand_score": 65,
                "export_potential": "Medium",
                "difficulty": "Medium",
                "artisan_guide": ["Prepare", "Assemble", "Inspect"],
                "target_customer_segment": "Home decor buyers",
            },
            {
                "product_name": "Product Three",
                "category_name": "Craft",
                "rationale": "Builds on current market demand.",
                "unit_cost_inr": 80,
                "expected_selling_price_inr": 180,
                "demand_score": 70,
                "export_potential": "Low",
                "difficulty": "Hard",
                "artisan_guide": ["Grade", "Shape", "Finish"],
                "target_customer_segment": "Retail customers",
            },
        ]
    }


class FakeLLM:
    provider = "fake"

    def call(self, prompt):
        self.prompt = prompt
        return valid_llm_result()


class CorrectingLLM:
    provider = "fake"

    def __init__(self):
        self.calls = 0

    def call(self, prompt):
        self.calls += 1
        return {} if self.calls == 1 else valid_llm_result()


class FailingLLM:
    provider = "fake"

    def call(self, prompt):
        return {}


class RecommendationServiceTests(unittest.TestCase):
    def test_constraints_reject_unknown_region(self):
        with self.assertRaises(RecommendationValidationError):
            validate_constraints("Beginner", "Low", "Quick turnaround", "Goa", None, MFP)

    def test_market_context_requires_summary(self):
        with self.assertRaises(RecommendationValidationError):
            validate_market_context({"top_products": []})

    def test_context_includes_categories_constraints_and_market_evidence(self):
        prompt = build_recommendation_context(
            MFP, [{"category_name": "Craft", "products": []}],
            {"artisan_skill_level": "Beginner"}, MARKET_CONTEXT,
        )
        self.assertIn("Test MFP", prompt)
        self.assertIn("Gift-ready packaging", prompt)
        self.assertIn("artisan_skill_level", prompt)

    def test_malformed_llm_result_is_rejected(self):
        malformed = valid_llm_result()
        malformed["recommendations"][0]["artisan_guide"] = ["Only one step"]
        with self.assertRaises(RecommendationValidationError):
            validate_recommendations(malformed)

    def test_margin_is_calculated_on_server(self):
        recommendations = validate_recommendations(valid_llm_result())
        self.assertEqual(recommendations[0]["profit_margin_percent"], 60.0)
        self.assertNotIn("profit_margin_percent", valid_llm_result()["recommendations"][0])

    def test_generation_retries_an_invalid_llm_payload(self):
        llm = CorrectingLLM()
        result = _generate_validated_recommendations(llm, "test prompt")
        self.assertEqual(llm.calls, 2)
        self.assertEqual(len(result), 3)


class FallbackConstraintTests(unittest.TestCase):
    """Tests that the deterministic fallback actually respects artisan constraints."""

    def test_beginner_only_gets_easy_products(self):
        constraints = {"artisan_skill_level": "Beginner", "budget_constraint": "High", "production_time": "Long-term"}
        result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, constraints)
        # Products from the strict filtering pass (Pass 1) should all be Easy.
        # Pass 2 (relaxation) and Pass 3 (potential_products) may add non-Easy items
        # to ensure the minimum of 3 recommendations.
        strict_products = [r for r in result
                           if "constraint relaxation" not in r["rationale"]
                           and "known product opportunity" not in r["rationale"]
                           and "aligned to the current" not in r["rationale"]]
        for rec in strict_products:
            self.assertEqual(rec["difficulty"], "Easy",
                             f"Beginner got non-Easy product: {rec['product_name']} ({rec['difficulty']})")
        self.assertGreaterEqual(len(strict_products), 1, "Should have at least one strictly matched Easy product")

    def test_advanced_can_get_hard_products(self):
        constraints = {"artisan_skill_level": "Advanced", "budget_constraint": "High", "production_time": "Long-term"}
        result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, constraints)
        difficulties = {rec["difficulty"] for rec in result}
        self.assertTrue(
            difficulties & {"Medium", "Hard"},
            f"Advanced artisan should see Medium or Hard products, got: {difficulties}"
        )

    def test_different_constraints_yield_different_products(self):
        beginner_constraints = {"artisan_skill_level": "Beginner", "budget_constraint": "Low", "production_time": "Quick turnaround"}
        advanced_constraints = {"artisan_skill_level": "Advanced", "budget_constraint": "High", "production_time": "Long-term"}
        beginner_result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, beginner_constraints)
        advanced_result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, advanced_constraints)
        beginner_names = {r["product_name"] for r in beginner_result}
        advanced_names = {r["product_name"] for r in advanced_result}
        self.assertNotEqual(beginner_names, advanced_names,
                            "Beginner and Advanced should return different product sets")

    def test_quick_turnaround_excludes_long_processes(self):
        constraints = {"artisan_skill_level": "Advanced", "budget_constraint": "High", "production_time": "Quick turnaround"}
        result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, constraints)
        for rec in result:
            self.assertLessEqual(len(rec["artisan_guide"]), 5,
                                 f"Quick turnaround product has too many steps: {rec['product_name']}")

    def test_low_budget_keeps_costs_low(self):
        constraints = {"artisan_skill_level": "Advanced", "budget_constraint": "Low", "production_time": "Long-term"}
        result = _fallback_recommendations(MFP, MIXED_CATEGORIES, MARKET_CONTEXT, constraints)
        for rec in result:
            if "constraint relaxation" not in rec["rationale"]:
                self.assertLessEqual(rec["unit_cost_inr"], 250.0,
                                     f"Low budget product too expensive: {rec['product_name']} (INR {rec['unit_cost_inr']})")


class GenerateIntegrationTests(unittest.TestCase):
    """Tests the full generate_recommendations flow with LLM primary and fallback."""

    @patch("app.recommendation_service.get_cached_product_categories", return_value=MIXED_CATEGORIES)
    @patch("app.recommendation_service._find_mfp_item", return_value=MFP)
    def test_generates_valid_recommendations(self, find_mfp, categories):
        """Should produce valid recommendations via LLM or fallback."""
        result = generate_recommendations(
            12, "Beginner", "Low", "Quick turnaround",
            "All listed regions", None, MARKET_CONTEXT,
        )
        self.assertEqual(result["status"], "complete")
        self.assertIn(result["provider"], {"deterministic", "groq", "gemini", "together"})
        self.assertGreaterEqual(len(result["recommendations"]), 3)
        # Every recommendation must have the required fields
        for rec in result["recommendations"]:
            self.assertIn("product_name", rec)
            self.assertIn("unit_cost_inr", rec)
            self.assertIn("profit_margin_percent", rec)

    @patch("app.recommendation_service.get_cached_product_categories", return_value=MIXED_CATEGORIES)
    @patch("app.recommendation_service._find_mfp_item", return_value=MFP)
    def test_constraints_are_returned_in_response(self, find_mfp, categories):
        result = generate_recommendations(
            12, "Advanced", "High", "Long-term",
            "All listed regions", None, MARKET_CONTEXT,
        )
        self.assertEqual(result["constraints"]["artisan_skill_level"], "Advanced")
        self.assertEqual(result["constraints"]["budget_constraint"], "High")


if __name__ == "__main__":
    unittest.main()

