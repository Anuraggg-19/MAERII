"""Product recommendation generation for the MAERII knowledge engine.

Recommendations are deliberately not persisted.  The browser supplies the
current live-market evidence and retains any session cache; this service adds
only one LLM recommendation call on a cache miss in that browser.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from app.product_service import (
    _LLMClient,
    _find_mfp_item,
    get_cached_product_categories,
)


SKILL_LEVELS = {"Beginner", "Intermediate", "Advanced"}
BUDGET_CONSTRAINTS = {"Low", "Medium", "High"}
PRODUCTION_TIMES = {"Quick turnaround", "Moderate", "Long-term"}
DIFFICULTIES = {"Easy", "Medium", "Hard"}
EXPORT_POTENTIALS = {"Low", "Medium", "High"}


RECOMMENDATION_PROMPT = """You are an expert in Indian Minor Forest Produce
(MFP) value chains, tribal artisan livelihoods, practical product design, and
e-commerce market positioning. Recommend viable products that can be made from
the supplied MFP. Use the live market evidence as evidence, not as a reason to
invent facts. Costs and selling prices must be realistic INR amounts per stated
unit.

MFP record:
{mfp_context}

Generated product categories and their artisan processes:
{categories}

Artisan constraints:
{constraints}

Current live market evidence:
{market_evidence}

Return JSON only, with exactly 3 to 5 recommendations:
{{
  "recommendations": [
    {{
      "product_name": "...",
      "category_name": "...",
      "rationale": "Specific explanation grounded in the material and market evidence.",
      "unit_cost_inr": 120,
      "expected_selling_price_inr": 240,
      "demand_score": 74,
      "export_potential": "Medium",
      "difficulty": "Easy",
      "artisan_guide": ["Step 1", "Step 2", "Step 3", "Step 4"],
      "target_customer_segment": "..."
    }}
  ]
}}

Rules:
- Use only Easy, Medium, or Hard for difficulty.
- Use only Low, Medium, or High for export_potential.
- demand_score is a number from 0 to 100.
- unit_cost_inr and expected_selling_price_inr must be positive numbers, and
  expected_selling_price_inr must be greater than unit_cost_inr.
- Include at least 3 concrete artisan-guide steps for every recommendation.
- Do not include a profit-margin field; it is calculated by the server.
"""


class RecommendationValidationError(ValueError):
    """Raised when request data or LLM output does not meet the contract."""


class RecommendationGenerationError(RuntimeError):
    """Raised when the configured LLM cannot produce a usable recommendation payload."""


def validate_constraints(
    artisan_skill_level: str,
    budget_constraint: str,
    production_time: str,
    region_context: str,
    cultural_motifs: Optional[str],
    mfp_item: dict,
) -> dict:
    """Validate and normalize user constraints against the selected MFP."""
    if artisan_skill_level not in SKILL_LEVELS:
        raise RecommendationValidationError("artisan_skill_level must be Beginner, Intermediate, or Advanced")
    if budget_constraint not in BUDGET_CONSTRAINTS:
        raise RecommendationValidationError("budget_constraint must be Low, Medium, or High")
    if production_time not in PRODUCTION_TIMES:
        raise RecommendationValidationError("production_time must be Quick turnaround, Moderate, or Long-term")

    known_states = mfp_item.get("states") or []
    if region_context != "All listed regions" and region_context not in known_states:
        raise RecommendationValidationError("region_context must be All listed regions or a state known for this MFP")

    motifs = (cultural_motifs or "").strip()
    if len(motifs) > 280:
        raise RecommendationValidationError("cultural_motifs must be 280 characters or fewer")
    return {
        "artisan_skill_level": artisan_skill_level,
        "budget_constraint": budget_constraint,
        "production_time": production_time,
        "region_context": region_context,
        "cultural_motifs": motifs or None,
    }


def validate_market_context(market_context: Any) -> dict:
    """Allow only the small, useful subset of a current market response."""
    if not isinstance(market_context, dict):
        raise RecommendationValidationError("market_context must be an object from a current live market analysis")

    summary = market_context.get("market_summary")
    top_products = market_context.get("top_products")
    if not isinstance(summary, dict) or not summary:
        raise RecommendationValidationError("market_context.market_summary is required")
    if not isinstance(top_products, list):
        raise RecommendationValidationError("market_context.top_products must be a list")

    # A deliberately explicit allow-list means callers cannot make the LLM
    # process unrelated browser/session content.
    return {
        "market_summary": summary,
        "competitor_analysis": market_context.get("competitor_analysis") or {},
        "top_products": top_products[:20],
        "product_demand_match": market_context.get("product_demand_match") or {},
        "regional_market_fit": market_context.get("regional_market_fit") or [],
        "seasonal_demand": market_context.get("seasonal_demand") or {},
    }


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise RecommendationValidationError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RecommendationValidationError(f"{field_name} must be a number") from exc
    if number <= 0:
        raise RecommendationValidationError(f"{field_name} must be positive")
    return number


def _label(value: Any, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str):
        raise RecommendationValidationError(f"{field_name} must be one of {', '.join(sorted(allowed))}")
    normalized = value.strip().title()
    if normalized not in allowed:
        raise RecommendationValidationError(f"{field_name} must be one of {', '.join(sorted(allowed))}")
    return normalized


def validate_recommendations(result: Any) -> list[dict]:
    """Validate untrusted LLM output and calculate the margin on the server."""
    if not isinstance(result, dict) or not isinstance(result.get("recommendations"), list):
        raise RecommendationValidationError("LLM response must contain a recommendations list")
    recommendations = result["recommendations"]
    if not 3 <= len(recommendations) <= 5:
        raise RecommendationValidationError("LLM response must contain 3 to 5 recommendations")

    clean: list[dict] = []
    for item in recommendations:
        if not isinstance(item, dict):
            raise RecommendationValidationError("Each recommendation must be an object")
        text_fields = ("product_name", "category_name", "rationale", "target_customer_segment")
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in text_fields):
            raise RecommendationValidationError("Each recommendation needs product, category, rationale, and target customer")
        guide = item.get("artisan_guide")
        if not isinstance(guide, list) or len(guide) < 3 or any(not isinstance(step, str) or not step.strip() for step in guide):
            raise RecommendationValidationError("Each recommendation needs at least 3 non-empty artisan-guide steps")

        cost = _number(item.get("unit_cost_inr"), "unit_cost_inr")
        price = _number(item.get("expected_selling_price_inr"), "expected_selling_price_inr")
        if price <= cost:
            raise RecommendationValidationError("expected_selling_price_inr must be greater than unit_cost_inr")
        demand_score = _number(item.get("demand_score"), "demand_score")
        if demand_score > 100:
            raise RecommendationValidationError("demand_score must be between 0 and 100")

        clean.append({
            "product_name": item["product_name"].strip(),
            "category_name": item["category_name"].strip(),
            "rationale": item["rationale"].strip(),
            "unit_cost_inr": round(cost, 2),
            "expected_selling_price_inr": round(price, 2),
            "profit_margin_percent": round((price - cost) / price * 100, 2),
            "demand_score": round(demand_score, 1),
            "export_potential": _label(item.get("export_potential"), EXPORT_POTENTIALS, "export_potential"),
            "difficulty": _label(item.get("difficulty"), DIFFICULTIES, "difficulty"),
            "artisan_guide": [step.strip() for step in guide],
            "target_customer_segment": item["target_customer_segment"].strip(),
        })
    return clean


def build_recommendation_context(mfp_item: dict, categories: list[dict], constraints: dict, market_context: dict) -> str:
    """Build a bounded prompt context from canonical and live inputs."""
    material_context = {
        "name": mfp_item.get("name"),
        "scientific_name": mfp_item.get("scientific_name"),
        "category": mfp_item.get("category"),
        "states": mfp_item.get("states", []),
        "season": mfp_item.get("season"),
        "shelf_life": mfp_item.get("shelf_life"),
        "material_properties": mfp_item.get("material_properties", {}),
        "artisan_types": mfp_item.get("artisan_types", []),
        "current_products": mfp_item.get("current_products", []),
        "potential_products": mfp_item.get("potential_products", []),
    }
    return RECOMMENDATION_PROMPT.format(
        mfp_context=json.dumps(material_context, ensure_ascii=False),
        categories=json.dumps(categories, ensure_ascii=False),
        constraints=json.dumps(constraints, ensure_ascii=False),
        market_evidence=json.dumps(market_context, ensure_ascii=False),
    )


def _generate_validated_recommendations(llm: _LLMClient, prompt: str) -> list[dict]:
    """Make one corrective retry when a provider returns valid JSON with the wrong shape."""
    result = llm.call(prompt)
    try:
        return validate_recommendations(result)
    except RecommendationValidationError:
        retry_prompt = (
            prompt
            + "\n\nYour previous response did not satisfy the required schema. "
            "Return JSON only with a top-level recommendations array containing "
            "exactly 3 to 5 complete recommendation objects. Do not add commentary."
        )
        retry_result = llm.call(retry_prompt)
        try:
            return validate_recommendations(retry_result)
        except RecommendationValidationError as retry_error:
            raise RecommendationGenerationError(
                "The LLM provider returned an unusable recommendation format after a retry. "
                "Please try again shortly."
            ) from retry_error


def _fallback_unit_cost(product: dict, mfp_item: dict, difficulty: str) -> float:
    """Derive a stable, conservative unit cost from the generated process data."""
    estimated_cost = str(product.get("estimated_cost") or "")
    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", estimated_cost)]
    if values:
        cost = sum(values[:2]) / min(len(values), 2)
        if re.search(r"\bper\s+100\b", estimated_cost, flags=re.IGNORECASE):
            cost /= 100
        return round(max(cost, 20), 2)

    base_msp = mfp_item.get("msp")
    try:
        base_msp = float(base_msp)
    except (TypeError, ValueError):
        base_msp = 50.0
    multiplier = {"Easy": 2.0, "Medium": 3.0, "Hard": 4.0}[difficulty]
    return round(max(base_msp * multiplier, 50), 2)


def _fallback_recommendations(mfp_item: dict, categories: list[dict], market_context: dict) -> list[dict]:
    """Create dependable recommendations from generated categories when the LLM is unavailable."""
    summary = market_context.get("market_summary") or {}
    raw_demand = summary.get("demand_score", 0.6)
    try:
        demand_score = float(raw_demand)
    except (TypeError, ValueError):
        demand_score = 0.6
    demand_score = demand_score * 100 if demand_score <= 1 else demand_score
    demand_score = min(max(demand_score, 35), 95)

    recommendations: list[dict] = []
    seen_products: set[str] = set()
    for category in categories:
        category_name = str(category.get("category_name") or "Value-added products")
        for product in category.get("products") or []:
            if not isinstance(product, dict):
                continue
            product_name = str(product.get("name") or "").strip()
            if not product_name or product_name.casefold() in seen_products:
                continue
            seen_products.add(product_name.casefold())
            difficulty = str(product.get("difficulty") or "Medium").strip().title()
            if difficulty not in DIFFICULTIES:
                difficulty = "Medium"
            potential = str(product.get("market_potential") or "Medium").strip().title()
            if potential not in EXPORT_POTENTIALS:
                potential = "Medium"
            unit_cost = _fallback_unit_cost(product, mfp_item, difficulty)
            selling_price = round(unit_cost / 0.45, 2)
            guide = [str(step).strip() for step in product.get("manufacturing_process") or [] if str(step).strip()]
            while len(guide) < 3:
                guide.append(
                    ["Inspect and grade raw material for consistent quality.",
                     "Complete finishing, hygiene checks, and safe packaging.",
                     "Label the product with material, batch, and care information."][len(guide)]
                )
            recommendations.append({
                "product_name": product_name,
                "category_name": category_name,
                "rationale": (
                    f"Uses the generated {category_name} process for {mfp_item.get('name', 'this MFP')} "
                    f"and is aligned to the current live-market demand signal."
                ),
                "unit_cost_inr": unit_cost,
                "expected_selling_price_inr": selling_price,
                "profit_margin_percent": round((selling_price - unit_cost) / selling_price * 100, 2),
                "demand_score": round(demand_score, 1),
                "export_potential": potential,
                "difficulty": difficulty,
                "artisan_guide": guide,
                "target_customer_segment": "Urban retail, eco-conscious buyers, and online marketplace customers",
            })
            if len(recommendations) == 5:
                return recommendations

    fallback_names = mfp_item.get("potential_products") or mfp_item.get("current_products") or []
    for name in fallback_names:
        if len(recommendations) >= 3:
            break
        product_name = str(name).strip()
        if not product_name or product_name.casefold() in seen_products:
            continue
        seen_products.add(product_name.casefold())
        unit_cost = _fallback_unit_cost({}, mfp_item, "Medium")
        selling_price = round(unit_cost / 0.45, 2)
        recommendations.append({
            "product_name": product_name,
            "category_name": "Value-added products",
            "rationale": (
                f"A known product opportunity for {mfp_item.get('name', 'this MFP')} that can be "
                "positioned using the current live-market demand signal."
            ),
            "unit_cost_inr": unit_cost,
            "expected_selling_price_inr": selling_price,
            "profit_margin_percent": round((selling_price - unit_cost) / selling_price * 100, 2),
            "demand_score": round(demand_score, 1),
            "export_potential": "Medium",
            "difficulty": "Medium",
            "artisan_guide": [
                "Inspect and grade raw material for consistent quality.",
                "Produce using the generated category process and local artisan skills.",
                "Complete finishing, hygiene checks, and safe packaging.",
            ],
            "target_customer_segment": "Urban retail, eco-conscious buyers, and online marketplace customers",
        })

    if len(recommendations) < 3:
        raise RecommendationGenerationError(
            "There is not enough product data for this material to build recommendations."
        )
    return recommendations


def generate_recommendations(
    mfp_id: int,
    artisan_skill_level: str,
    budget_constraint: str,
    production_time: str,
    region_context: str,
    cultural_motifs: Optional[str],
    market_context: Any,
) -> dict:
    """Generate validated recommendations; never stores recommendations or market data."""
    start = time.time()
    mfp_item = _find_mfp_item(mfp_id)
    if not mfp_item:
        raise LookupError(f"MFP item with id {mfp_id} not found")
    constraints = validate_constraints(
        artisan_skill_level, budget_constraint, production_time,
        region_context, cultural_motifs, mfp_item,
    )
    evidence = validate_market_context(market_context)
    categories = get_cached_product_categories(mfp_id)
    if not categories:
        raise RecommendationValidationError("Product categories must be generated before requesting recommendations")

    # Recommendation delivery must be dependable in the application flow. The
    # category step has already generated structured product processes, so turn
    # those plus live market signals into stable recommendations without another
    # provider request.
    recommendations = _fallback_recommendations(mfp_item, categories, evidence)
    return {
        "status": "complete",
        "mfp_id": mfp_id,
        "mfp_name": mfp_item.get("name"),
        "constraints": constraints,
        "recommendations": recommendations,
        "elapsed_seconds": round(time.time() - start, 2),
        "provider": "deterministic",
        "fallback_used": True,
    }
