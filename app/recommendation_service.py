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


# Maps user-facing skill level to allowed difficulty values for filtering
_SKILL_DIFFICULTY_MAP: dict[str, set[str]] = {
    "Beginner": {"Easy"},
    "Intermediate": {"Easy", "Medium"},
    "Advanced": {"Easy", "Medium", "Hard"},
}

# Budget-tier cost ceiling (INR) for the deterministic fallback
_BUDGET_COST_CEILING: dict[str, float] = {
    "Low": 250.0,
    "Medium": 800.0,
    "High": float("inf"),
}

# Market-potential sort priority (higher = better)
_POTENTIAL_RANK: dict[str, int] = {"High": 3, "Medium": 2, "Low": 1}


RECOMMENDATION_PROMPT = """You are an expert in Indian Minor Forest Produce
(MFP) value chains, tribal artisan livelihoods, practical product design, and
e-commerce market positioning.

Your task is to recommend 3-5 VIABLE PRODUCT IDEAS that a tribal artisan can
make from the supplied raw material, given their SPECIFIC constraints below.
Each recommendation must be a concrete, actionable business opportunity — NOT
just a repeat of the product categories listed above.

MFP record:
{mfp_context}

Generated product categories and their artisan processes (reference only):
{categories}

Artisan constraints (CRITICAL — you MUST obey these):
{constraints}

Current live market evidence:
{market_evidence}

CONSTRAINT RULES — follow these strictly:
1. Skill level:
   - Beginner: ONLY recommend products with difficulty "Easy" and 4 or fewer
     process steps. No complex techniques.
   - Intermediate: recommend "Easy" or "Medium" difficulty products.
   - Advanced: recommend any difficulty, prefer "Medium" or "Hard" with
     higher-value outputs.
2. Budget constraint:
   - Low: unit_cost_inr MUST be under 250. Prioritize products needing
     minimal tools and locally available inputs.
   - Medium: unit_cost_inr between 100 and 800. Balance investment vs return.
   - High: recommend premium, export-grade products with higher investment
     and margins.
3. Production time:
   - Quick turnaround: products with 4 or fewer manufacturing steps. No
     extended curing, drying, or fermentation.
   - Moderate: standard processes acceptable.
   - Long-term: complex, high-value products with extended processing are
     encouraged.
4. Region: prioritize products with regional market fit and locally available
   skills. Reference the MFP states data.
5. Cultural motifs: if provided, explicitly incorporate the motif into
   product design (e.g., "Gond patterns" means suggest painted/carved items).

ANTI-DUPLICATION RULE:
Do NOT just list the same products from the categories section. Instead,
recommend the best 3-5 product ideas that specifically match THESE artisan
constraints. You may reference or build upon category products, but each
recommendation must explain WHY it suits this particular artisan's situation
(skill, budget, timeline). The output should feel like personalized business
advice, not a category index.

Return JSON only, with exactly 3 to 5 recommendations:
{{
  "recommendations": [
    {{
      "product_name": "...",
      "category_name": "...",
      "rationale": "Explain WHY this product is ideal for this artisan's specific skill level, budget, and timeline. Reference market evidence where possible.",
      "pricing_unit": "per 100g bar",
      "unit_cost_inr": 20,
      "expected_selling_price_inr": 65,
      "demand_score": 74,
      "export_potential": "Medium",
      "difficulty": "Easy",
      "artisan_guide": ["Step 1", "Step 2", "Step 3", "Step 4"],
      "required_skills": ["Skill 1", "Skill 2", "Skill 3"],
      "target_customer_segment": "..."
    }}
  ]
}}

Rules:
- Use only Easy, Medium, or Hard for difficulty.
- Use only Low, Medium, or High for export_potential.
- pricing_unit must explicitly mention what the price applies to (e.g. "per 100g bar", "per litre", "per kg", "per piece", "per 50g jar", "per 250g pack").
- unit_cost_inr must reflect realistic artisan production cost FOR THAT SPECIFIC UNIT (raw material + labor + tools).
- expected_selling_price_inr must be a REALISTIC retail selling price FOR THAT SAME UNIT. It must reflect realistic artisan gross margins (typically 40% to 75% profit margin, meaning selling price is 1.6x to 3.5x unit cost). Never output industrial machine prices, bulk ton prices, or tens of thousands of rupees for individual consumer items like soaps, oils, or candles.
- demand_score is a number from 0 to 100 reflecting REALISTIC, DIFFERENTIATED
  market demand for EACH specific product. Do NOT give similar scores to all
  products. Base each score on:
  (a) How many matching/similar products appear in the live market evidence
  (b) The price range and review counts of those matched products
  (c) The market trend (growing/stable/declining) from the market summary
  (d) Seasonal relevance and regional fit
- Include at least 3 concrete artisan-guide steps for every recommendation.
- required_skills must list 2-5 specific artisan skills needed (e.g., "Wood carving", "Natural dyeing", "Resin processing").
- Do not include a profit-margin field; it is calculated by the server.
- CRITICAL: Every product MUST have meaningfully different demand_score and
  unit_cost_inr values. If two products have identical scores, you have failed.
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


def _infer_pricing_unit(product_name: str, category_name: str = "") -> str:
    """Infer an intuitive pricing unit (e.g., 'per 100g bar', 'per litre', 'per kg') from product name."""
    name = (product_name + " " + category_name).lower()
    if any(k in name for k in ["soap", "bathing bar"]):
        return "per 100g bar"
    if any(k in name for k in ["oil", "varnish", "liquid", "extract", "juice", "beverage", "biodiesel", "lubricant", "syrup", "tincture"]):
        return "per litre"
    if any(k in name for k in ["balm", "butter", "cream", "paste", "lotion", "ointment", "gel", "scrub"]):
        return "per 50g jar"
    if any(k in name for k in ["candle", "dia", "diya"]):
        return "per candle"
    if any(k in name for k in ["tea", "coffee", "infusion"]):
        return "per 250g pack"
    if any(k in name for k in ["powder", "cake", "feed", "flour", "grain", "seed", "resin", "lac", "shellac", "dye", "fertilizer", "manure", "compost", "briquette"]):
        return "per kg"
    if any(k in name for k in ["basket", "tray", "lamp", "plate", "box", "bangle", "toy", "craft", "mat", "pot", "bowl", "ornament", "artefact", "item"]):
        return "per piece"
    if any(k in name for k in ["fabric", "rope", "yarn", "thread", "textile"]):
        return "per metre"
    return "per unit"


def _extract_pricing_unit(estimated_cost: str, product_name: str = "", category_name: str = "") -> str:
    """Extract pricing unit from category estimated_cost string, or fall back to keyword inference."""
    if estimated_cost:
        m = re.search(r"\bper\s+([a-zA-Z0-9\s/().-]+)", estimated_cost, flags=re.IGNORECASE)
        if m:
            raw_unit = m.group(1).strip().rstrip(".,;").lower()
            if "kilogram" in raw_unit or raw_unit == "kg":
                return "per kg"
            if "liter" in raw_unit or "litre" in raw_unit:
                return "per litre"
            if "item" in raw_unit or "piece" in raw_unit or "pc" in raw_unit:
                if "soap" in product_name.lower():
                    return "per 100g bar"
                if "candle" in product_name.lower():
                    return "per candle"
                return "per piece"
            if "100g bar" in raw_unit or "bar" in raw_unit:
                return "per 100g bar"
            if "50g jar" in raw_unit or "jar" in raw_unit:
                return "per 50g jar"
            if "candle" in raw_unit:
                return "per candle"
            return f"per {raw_unit}"
    return _infer_pricing_unit(product_name, category_name)


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

        pricing_unit = str(item.get("pricing_unit") or "").strip()
        if not pricing_unit:
            pricing_unit = _infer_pricing_unit(item.get("product_name", ""), item.get("category_name", ""))

        cost = _number(item.get("unit_cost_inr"), "unit_cost_inr")
        price = _number(item.get("expected_selling_price_inr"), "expected_selling_price_inr")
        if price <= cost:
            raise RecommendationValidationError("expected_selling_price_inr must be greater than unit_cost_inr")

        # Sanity check: prevent unrealistic pricing hallucinations (> 5x cost or > 78% margin)
        if price > cost * 5.0 or (price - cost) / price > 0.78:
            price = round(cost * 2.7, 2)

        demand_score = _number(item.get("demand_score"), "demand_score")
        if demand_score > 100:
            raise RecommendationValidationError("demand_score must be between 0 and 100")

        raw_skills = item.get("required_skills") or []
        if not isinstance(raw_skills, list):
            raw_skills = []
        skills = [s.strip() for s in raw_skills if isinstance(s, str) and s.strip()]

        clean.append({
            "product_name": item["product_name"].strip(),
            "category_name": item["category_name"].strip(),
            "rationale": item["rationale"].strip(),
            "pricing_unit": pricing_unit,
            "unit_cost_inr": round(cost, 2),
            "expected_selling_price_inr": round(price, 2),
            "profit_margin_percent": round((price - cost) / price * 100, 2),
            "demand_score": round(demand_score, 1),
            "export_potential": _label(item.get("export_potential"), EXPORT_POTENTIALS, "export_potential"),
            "difficulty": _label(item.get("difficulty"), DIFFICULTIES, "difficulty"),
            "artisan_guide": [step.strip() for step in guide],
            "required_skills": skills,
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


def _fallback_unit_cost(
    product: dict, mfp_item: dict, difficulty: str, product_name: str = ""
) -> tuple[float, str]:
    """Derive a realistic unit cost and pricing unit from process complexity and material cost.

    Uses multiple signals:
      - estimated_cost from the category product (e.g. '₹15-25 per 100g bar')
      - MSP of the raw material as a base
      - Number of manufacturing steps (labour cost proxy)
      - Difficulty level (skill premium)
      - Number of required skills (complexity premium)
    """
    name = product_name or str(product.get("name") or "")
    category = str(product.get("category_name") or "")
    estimated_cost = str(product.get("estimated_cost") or "")
    pricing_unit = _extract_pricing_unit(estimated_cost, name, category)

    # Try the category-provided estimated_cost first
    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", estimated_cost)]
    if values:
        cost = sum(values[:2]) / min(len(values), 2)
        # Only divide by 100 if explicitly stated for 100 items/pieces/units (not 100g or 100ml)
        if re.search(r"\bper\s+100\s*(?:units?|pieces?|pcs?|items?)\b", estimated_cost, flags=re.IGNORECASE):
            cost /= 100
        return round(max(cost, 10.0), 2), pricing_unit

    # Build cost from components
    base_msp = mfp_item.get("msp")
    try:
        base_msp = float(base_msp)
    except (TypeError, ValueError):
        base_msp = 50.0

    # Scale raw material component appropriately for smaller units
    unit_lower = pricing_unit.lower()
    if any(k in unit_lower for k in ["100g", "50g", "bar", "jar", "candle", "piece", "item"]):
        raw_material_cost = base_msp * 0.25
    elif any(k in unit_lower for k in ["litre", "liter", "kg", "kilogram"]):
        raw_material_cost = base_msp * 1.1
    else:
        raw_material_cost = base_msp * 0.6

    num_steps = len(product.get("manufacturing_process") or [])
    labour_per_step = {"Easy": 8, "Medium": 16, "Hard": 28}.get(difficulty, 16)
    labour_cost = max(num_steps, 2) * labour_per_step

    num_skills = len(product.get("required_skills") or [])
    skill_premium = num_skills * 8

    equipment_cost = {"Easy": 6, "Medium": 18, "Hard": 40}.get(difficulty, 18)

    total = raw_material_cost + labour_cost + skill_premium + equipment_cost
    return round(max(total, 15.0), 2), pricing_unit


def _calculate_selling_price(
    unit_cost: float,
    product_name: str,
    budget: str,
    difficulty: str,
    export_potential: str,
    product_index: int,
    market_context: dict,
) -> float:
    """Calculate a realistic, grounded retail selling price for the specific product and unit.

    Never anchors to a global raw-material market average (which often contains expensive
    industrial machinery or bulk tons).
    Instead:
      1. Checks for specific retail market listings for this specific product keyword.
      2. Applies a grounded cost-plus artisan margin model (typically 42% - 72% margin):
         - Low budget (local market): 44% - 52% margin
         - Medium budget (craft/regional): 52% - 62% margin
         - High budget (premium retail/export): 60% - 72% margin
    """
    top_products = market_context.get("top_products") or []
    all_products = market_context.get("all_products") or []
    candidate_products = top_products + all_products

    # Extract clean keywords from product name (e.g. "soap", "oil", "candle", "cake", "balm")
    stopwords = {"and", "for", "the", "with", "herbal", "organic", "natural", "pure", "seed", "extract", "products"}
    keywords = [
        w.lower() for w in re.findall(r"[A-Za-z]{3,}", product_name)
        if w.lower() not in stopwords
    ]

    specific_retail_prices = []
    for p in candidate_products:
        title = (p.get("title") or "").lower()
        try:
            price = float(p.get("price") or 0)
        except (TypeError, ValueError):
            continue
        # Check if product title matches at least one specific keyword
        if any(kw in title for kw in keywords):
            # Retail price sanity check: retail items are between 1.2x and 4.5x unit_cost, and < 4000 INR
            if 1.2 * unit_cost <= price <= max(unit_cost * 4.5, 3000):
                specific_retail_prices.append(price)

    if specific_retail_prices:
        # Use median of specific retail prices
        specific_retail_prices.sort()
        mid = len(specific_retail_prices) // 2
        median_price = (
            specific_retail_prices[mid]
            if len(specific_retail_prices) % 2 != 0
            else (specific_retail_prices[mid - 1] + specific_retail_prices[mid]) / 2
        )
        variation = 0.94 + (product_index % 5) * 0.03
        selling_price = round(median_price * variation, 2)
        if selling_price >= unit_cost * 1.35:
            return selling_price

    # Grounded cost-plus margin model
    base_margin = {"Low": 0.46, "Medium": 0.56, "High": 0.65}.get(budget, 0.56)

    # Premium adjustments
    if export_potential == "High":
        base_margin += 0.05
    elif export_potential == "Low":
        base_margin -= 0.03

    if difficulty == "Hard":
        base_margin += 0.04
    elif difficulty == "Easy":
        base_margin -= 0.03

    # Small per-product variation to prevent identical selling prices
    variation = ((product_index * 3) % 7 - 3) * 0.015  # -0.045 to +0.045
    margin = max(0.38, min(0.72, base_margin + variation))

    selling_price = round(unit_cost / (1.0 - margin), 2)
    return selling_price


def _fallback_recommendations(
    mfp_item: dict,
    categories: list[dict],
    market_context: dict,
    constraints: Optional[dict] = None,
) -> list[dict]:
    """Create constraint-filtered recommendations from generated categories.

    When the LLM is unavailable, this deterministic path still respects
    artisan constraints by:
      1. Filtering products whose difficulty exceeds the artisan's skill level
      2. Filtering products whose estimated cost exceeds the budget tier ceiling
      3. Filtering products with too many steps for the production time
      4. Sorting remaining products by market potential (high -> low)
      5. Adjusting selling-price margins by budget tier
    """
    summary = market_context.get("market_summary") or {}
    raw_demand = summary.get("demand_score", 0.5)
    try:
        base_demand = float(raw_demand)
    except (TypeError, ValueError):
        base_demand = 0.5
    base_demand = base_demand * 100 if base_demand <= 1 else base_demand
    base_demand = min(max(base_demand, 20), 90)

    # Extract market trend signal
    trend = str(summary.get("trend") or summary.get("market_trend") or "stable").lower()
    trend_modifier = {"growing": 10, "rising": 10, "stable": 0, "declining": -12, "saturated": -8}.get(trend, 0)

    # Extract matched product count and avg price from market data for demand calibration
    matched_count = 0
    matched_avg_price = 0
    top_products = market_context.get("top_products") or []
    if top_products:
        prices = [float(p.get("price") or 0) for p in top_products if p.get("price")]
        matched_count = len(top_products)
        matched_avg_price = sum(prices) / len(prices) if prices else 0

    # Extract constraint filters (default to widest when absent)
    skill = (constraints or {}).get("artisan_skill_level", "Advanced")
    budget = (constraints or {}).get("budget_constraint", "High")
    production_time = (constraints or {}).get("production_time", "Long-term")
    allowed_difficulties = _SKILL_DIFFICULTY_MAP.get(skill, {"Easy", "Medium", "Hard"})
    cost_ceiling = _BUDGET_COST_CEILING.get(budget, float("inf"))
    max_steps = 4 if production_time == "Quick turnaround" else 100

    # Margin multiplier varies by budget tier
    margin_divisor = {"Low": 0.55, "Medium": 0.45, "High": 0.35}.get(budget, 0.45)

    # Collect all candidate products
    candidates: list[dict] = []
    seen_products: set[str] = set()
    product_index = 0  # running counter for genuine differentiation

    def _compute_demand_score(product: dict, potential: str, difficulty: str, steps: list) -> float:
        """Compute a realistic, differentiated demand score per product.

        Factors:
          - base market demand from live data
          - market trend (growing/declining)
          - market_potential of this specific product (High/Medium/Low)
          - difficulty (easier products have broader market appeal)
          - number of manufacturing steps (simpler = more accessible demand)
          - whether similar products appeared in matched market listings
          - product index to break ties between otherwise similar products
        """
        nonlocal product_index
        product_index += 1

        score = base_demand
        score += trend_modifier

        # Market potential is the strongest differentiator
        potential_bonus = {"High": 18, "Medium": 0, "Low": -15}.get(potential, 0)
        score += potential_bonus

        # Easier products have broader consumer appeal
        diff_bonus = {"Easy": 8, "Medium": 0, "Hard": -10}.get(difficulty, 0)
        score += diff_bonus

        # Fewer steps = more scalable = slightly more demand
        step_modifier = max(-12, min(5, 7 - len(steps) * 2))
        score += step_modifier

        # If we have matched market products, more matches = higher demand signal
        if matched_count > 0:
            match_bonus = min(12, matched_count * 2)
            score += match_bonus
        else:
            score -= 5  # no market validation available

        # Use product_index to create genuine spread between products
        # This distributes scores by ±(3-8) points in a deterministic zigzag
        index_spread = ((product_index * 7 + 3) % 17) - 8  # range -8 to +8
        score += index_spread

        return round(max(15, min(95, score)), 1)

    def _extract_product(product: dict, category_name: str, relaxed: bool = False):
        """Parse a single category product into a recommendation candidate."""
        if not isinstance(product, dict):
            return None
        product_name = str(product.get("name") or "").strip()
        if not product_name or product_name.casefold() in seen_products:
            return None

        difficulty = str(product.get("difficulty") or "Medium").strip().title()
        if difficulty not in DIFFICULTIES:
            difficulty = "Medium"
        potential = str(product.get("market_potential") or "Medium").strip().title()
        if potential not in EXPORT_POTENTIALS:
            potential = "Medium"
        unit_cost, pricing_unit = _fallback_unit_cost(product, mfp_item, difficulty, product_name)
        steps = [str(s).strip() for s in product.get("manufacturing_process") or [] if str(s).strip()]

        # Constraint filters (skipped for relaxed pass)
        if not relaxed:
            if difficulty not in allowed_difficulties:
                return None
            if unit_cost > cost_ceiling:
                return None
            if len(steps) > max_steps:
                return None

        seen_products.add(product_name.casefold())

        local_demand = _compute_demand_score(product, potential, difficulty, steps)

        selling_price = _calculate_selling_price(
            unit_cost, product_name, budget, difficulty, potential, product_index, market_context
        )
        
        while len(steps) < 3:
            steps.append(
                ["Inspect and grade raw material for consistent quality.",
                 "Complete finishing, hygiene checks, and safe packaging.",
                 "Label the product with material, batch, and care information."][len(steps)]
            )
        rationale = (
            f"Suitable for {skill.lower()}-level artisans with {budget.lower()} budget. "
            f"Uses the {category_name} process for {mfp_item.get('name', 'this MFP')} "
            f"and aligns with current live-market demand."
        ) if not relaxed else (
            f"Included despite constraint relaxation — a viable product for "
            f"{mfp_item.get('name', 'this MFP')} with current market demand."
        )
        skills = [str(s).strip() for s in product.get("required_skills") or [] if str(s).strip()]
        return {
            "product_name": product_name,
            "category_name": category_name,
            "rationale": rationale,
            "pricing_unit": pricing_unit,
            "unit_cost_inr": unit_cost,
            "expected_selling_price_inr": selling_price,
            "profit_margin_percent": round((selling_price - unit_cost) / selling_price * 100, 2),
            "demand_score": round(local_demand, 1),
            "export_potential": potential,
            "difficulty": difficulty,
            "artisan_guide": steps,
            "required_skills": skills,
            "target_customer_segment": "Urban retail, eco-conscious buyers, and online marketplace customers",
            "_potential_rank": _POTENTIAL_RANK.get(potential, 2),
        }

    # Pass 1: strict constraint filtering
    for category in categories:
        category_name = str(category.get("category_name") or "Value-added products")
        for product in category.get("products") or []:
            candidate = _extract_product(product, category_name, relaxed=False)
            if candidate:
                candidates.append(candidate)

    # Sort: highest market potential first, then lowest cost
    candidates.sort(key=lambda c: (-c["_potential_rank"], c["unit_cost_inr"]))

    # Pass 2: if too few candidates, relax constraints and add more
    if len(candidates) < 3:
        for category in categories:
            category_name = str(category.get("category_name") or "Value-added products")
            for product in category.get("products") or []:
                candidate = _extract_product(product, category_name, relaxed=True)
                if candidate:
                    candidates.append(candidate)
                # Relax only enough to return the minimum useful set. Filling
                # all five slots with out-of-constraint products makes very
                # different artisan inputs produce identical recommendations.
                if len(candidates) >= 3:
                    break
            if len(candidates) >= 3:
                break

    # Pass 3: also try potential_products from the enriched data
    if len(candidates) < 3:
        fallback_names = mfp_item.get("potential_products") or mfp_item.get("current_products") or []
        for name in fallback_names:
            if len(candidates) >= 3:
                break
            product_name = str(name).strip()
            if not product_name or product_name.casefold() in seen_products:
                continue
            seen_products.add(product_name.casefold())
            difficulty = skill if skill in DIFFICULTIES else "Medium"
            dummy_product = {"manufacturing_process": [], "required_skills": []}
            unit_cost, pricing_unit = _fallback_unit_cost(dummy_product, mfp_item, difficulty, product_name=product_name)
            local_demand = _compute_demand_score(dummy_product, "Medium", difficulty, [])

            selling_price = _calculate_selling_price(
                unit_cost, product_name, budget, difficulty, "Medium", product_index, market_context
            )

            candidates.append({
                "product_name": product_name,
                "category_name": "Value-added products",
                "rationale": (
                    f"A known product opportunity for {mfp_item.get('name', 'this MFP')} "
                    f"that matches a {skill.lower()}-level artisan with a {budget.lower()} budget. "
                    "Aligned to the current live-market demand signal."
                ),
                "pricing_unit": pricing_unit,
                "unit_cost_inr": unit_cost,
                "expected_selling_price_inr": selling_price,
                "profit_margin_percent": round((selling_price - unit_cost) / selling_price * 100, 2),
                "demand_score": round(local_demand, 1),
                "export_potential": "Medium",
                "difficulty": difficulty,
                "artisan_guide": [
                    "Inspect and grade raw material for consistent quality.",
                    "Produce using standard category processes and local artisan skills.",
                    "Complete finishing, hygiene checks, and safe packaging.",
                ],
                "required_skills": [],
                "target_customer_segment": "Urban retail, eco-conscious buyers, and online marketplace customers",
                "_potential_rank": 2,
            })

    if len(candidates) < 3:
        raise RecommendationGenerationError(
            "There is not enough product data for this material to build recommendations."
        )

    # Strip internal sort key before returning
    result = candidates[:5]
    for r in result:
        r.pop("_potential_rank", None)
    return result


def _classify_demand_label(recommendations: list[dict]) -> None:
    """Convert numeric demand_score to a High/Medium/Low label.

    Strategy: rank all recommendations by demand_score, then assign labels
    using relative positioning so there is genuine differentiation:
      - Top ~30% -> High
      - Middle ~40% -> Medium
      - Bottom ~30% -> Low
    For 3-5 recommendations, this guarantees not all get the same label.
    Additional factors that push toward Low even if the score is decent:
      - difficulty == Hard (limits consumer accessibility)
      - export_potential == Low
    """
    if not recommendations:
        return

    # Sort indices by demand_score descending
    scored = sorted(
        enumerate(recommendations),
        key=lambda pair: pair[1].get("demand_score", 0),
        reverse=True,
    )
    n = len(scored)

    for rank, (idx, rec) in enumerate(scored):
        raw_score = rec.get("demand_score", 50)
        difficulty = rec.get("difficulty", "Medium")
        export = rec.get("export_potential", "Medium")

        # Base label from rank position
        if n <= 3:
            # With 3 items: 1 High, 1 Medium, 1 Low
            if rank == 0:
                label = "High"
            elif rank == n - 1:
                label = "Low"
            else:
                label = "Medium"
        else:
            # With 4-5 items: top 1-2 High, middle Medium, bottom 1-2 Low
            if rank == 0:
                label = "High"
            elif rank >= n - 1:
                label = "Low"
            elif raw_score >= 70:
                label = "High"
            elif raw_score < 45:
                label = "Low"
            else:
                label = "Medium"

        # Penalty: Hard difficulty products rarely have mass-market High demand
        if label == "High" and difficulty == "Hard" and raw_score < 80:
            label = "Medium"

        # Penalty: Low export potential with mediocre score -> downgrade
        if label == "Medium" and export == "Low" and raw_score < 55:
            label = "Low"

        # Ensure at least one is not High (prevent all-High)
        recommendations[idx]["demand_label"] = label

    # Final safety: guarantee at least 2 distinct labels
    labels = [r["demand_label"] for r in recommendations]
    if len(set(labels)) == 1 and len(labels) >= 2:
        # All same label — force spread
        lowest_idx = scored[-1][0]
        highest_idx = scored[0][0]
        if labels[0] == "High":
            recommendations[lowest_idx]["demand_label"] = "Low"
            if len(labels) >= 3:
                mid_idx = scored[len(scored) // 2][0]
                recommendations[mid_idx]["demand_label"] = "Medium"
        elif labels[0] == "Low":
            recommendations[highest_idx]["demand_label"] = "High"
            if len(labels) >= 3:
                mid_idx = scored[len(scored) // 2][0]
                recommendations[mid_idx]["demand_label"] = "Medium"
        else:  # all Medium
            recommendations[highest_idx]["demand_label"] = "High"
            recommendations[lowest_idx]["demand_label"] = "Low"
    elif len(set(labels)) == 2 and len(labels) >= 4:
        # Only 2 labels with 4+ items — try to add a third
        label_counts = {}
        for l in labels:
            label_counts[l] = label_counts.get(l, 0) + 1
        # If the majority label has 3+ items, downgrade/upgrade one
        majority = max(label_counts, key=label_counts.get)
        if label_counts[majority] >= 3:
            if majority == "High":
                # Downgrade the lowest-scoring "High" to "Medium"
                for rank_idx in range(len(scored) - 1, -1, -1):
                    idx = scored[rank_idx][0]
                    if recommendations[idx]["demand_label"] == "High":
                        recommendations[idx]["demand_label"] = "Medium"
                        break
            elif majority == "Low":
                # Upgrade the highest-scoring "Low" to "Medium"
                for rank_idx in range(len(scored)):
                    idx = scored[rank_idx][0]
                    if recommendations[idx]["demand_label"] == "Low":
                        recommendations[idx]["demand_label"] = "Medium"
                        break


def _classify_product_origin(recommendations: list[dict], mfp_item: dict) -> None:
    """Tag each recommendation as 'Existing Product' or 'AI Recommendation'.

    Checks the recommendation product_name against the MFP item's
    current_products and potential_products lists using fuzzy substring
    matching (case-insensitive).
    """
    current = [str(p).lower().strip() for p in mfp_item.get("current_products") or []]
    potential = [str(p).lower().strip() for p in mfp_item.get("potential_products") or []]
    known_products = current + potential

    for rec in recommendations:
        rec_name = (rec.get("product_name") or "").lower().strip()
        is_existing = False

        for known in known_products:
            # Normalize simple plurals: "soaps" -> "soap", "candles" -> "candle"
            known_norm = known.rstrip("s") if known.endswith("s") and len(known) > 3 else known
            rec_norm = rec_name.rstrip("s") if rec_name.endswith("s") and len(rec_name) > 3 else rec_name

            # Fuzzy: check if the known product name appears inside the
            # recommendation name, or vice versa.  For example:
            #   known="candles", rec_name="mahua fat candles" -> match
            #   known="soaps", rec_name="herbal mahua soap" -> match (via singular)
            #   known="mahua seed oil", rec_name="cold-pressed mahua seed oil" -> match
            if known in rec_name or rec_name in known:
                is_existing = True
                break
            if known_norm in rec_norm or rec_norm in known_norm:
                is_existing = True
                break
            # Also check individual significant words (>3 chars)
            known_words = [w for w in known.split() if len(w) > 3]
            rec_words = [w for w in rec_name.split() if len(w) > 3]
            # Singularized word check
            known_words_norm = [w.rstrip("s") if w.endswith("s") and len(w) > 4 else w for w in known_words]
            rec_words_norm = [w.rstrip("s") if w.endswith("s") and len(w) > 4 else w for w in rec_words]
            # If all significant words from the known product appear
            # in the recommendation name, it's likely the same product
            if known_words_norm and all(kw in rec_norm for kw in known_words_norm):
                is_existing = True
                break
            if rec_words_norm and all(rw in known_norm for rw in rec_words_norm):
                is_existing = True
                break

        rec["product_origin"] = "Existing Product" if is_existing else "AI Recommendation"


def generate_recommendations(
    mfp_id: int,
    artisan_skill_level: str,
    budget_constraint: str,
    production_time: str,
    region_context: str,
    cultural_motifs: Optional[str],
    market_context: Any,
) -> dict:
    """Generate constraint-aware recommendations via LLM, with deterministic fallback.

    Primary path: build a grounded prompt including material properties,
    cached product categories, live market evidence, and artisan constraints,
    then call the LLM to produce personalized business-plan-style
    recommendations.

    Fallback path: if no LLM provider is configured or the call fails,
    deterministically filter and rank the cached category products by
    constraint alignment (skill->difficulty, budget->cost ceiling,
    time->step count).
    """
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

    # --- Primary path: LLM-powered recommendations ---
    fallback_used = False
    provider_name = "none"
    try:
        llm = _LLMClient()
        if llm.provider:
            prompt = build_recommendation_context(mfp_item, categories, constraints, evidence)
            recommendations = _generate_validated_recommendations(llm, prompt)
            provider_name = llm.provider
        else:
            raise RuntimeError("No LLM provider configured")
    except Exception as llm_err:
        # --- Fallback path: deterministic constraint-filtered recommendations ---
        print(f"  [RecommendationService] LLM unavailable ({llm_err}), using constraint-filtered fallback")
        fallback_used = True
        provider_name = "deterministic"
        recommendations = _fallback_recommendations(mfp_item, categories, evidence, constraints)

    # --- Post-processing: add demand label and product origin ---
    _classify_demand_label(recommendations)
    _classify_product_origin(recommendations, mfp_item)

    return {
        "status": "complete",
        "mfp_id": mfp_id,
        "mfp_name": mfp_item.get("name"),
        "constraints": constraints,
        "recommendations": recommendations,
        "elapsed_seconds": round(time.time() - start, 2),
        "provider": provider_name,
        "fallback_used": fallback_used,
    }
