"""Product Enhancement AI service for the MAERII knowledge engine.

Given a specific product recommendation, generate comprehensive
enhancement guidance covering product design, marketing strategy,
packaging & labeling, and sales channel recommendations.

Like the recommendation service, results are session-only and not persisted.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from app.product_service import _LLMClient, _find_mfp_item


# ── Prompt ──────────────────────────────────────────────────────────────────

ENHANCEMENT_PROMPT = """You are an expert product designer, marketing strategist,
and packaging specialist for Indian tribal artisan products made from Minor
Forest Produce (MFP). Your goal is to help tribal products appeal to modern
urban and export customers while preserving cultural authenticity.

RAW MATERIAL:
{mfp_context}

PRODUCT TO ENHANCE:
{product_context}

CURRENT MARKET EVIDENCE:
{market_evidence}

Generate a comprehensive Product Enhancement plan with these EXACT sections.
Be highly specific — reference the actual product name, material, and market
data throughout. Do NOT give generic advice.

Return JSON only with this structure:
{{
  "product_design": {{
    "form_factor": "Describe the ideal physical form, dimensions, and shape for this specific product",
    "modernization_tips": [
      "Tip 1 — specific to this product",
      "Tip 2",
      "Tip 3"
    ],
    "color_palette": [
      {{"name": "Color name", "hex": "#XXXXXX", "usage": "Where to use this color"}},
      {{"name": "Color name", "hex": "#XXXXXX", "usage": "Where to use this color"}},
      {{"name": "Color name", "hex": "#XXXXXX", "usage": "Where to use this color"}},
      {{"name": "Color name", "hex": "#XXXXXX", "usage": "Where to use this color"}}
    ],
    "design_principles": [
      "Principle 1 specific to making this tribal product premium",
      "Principle 2",
      "Principle 3"
    ],
    "inspiration": "A short description of the design aesthetic (e.g., Scandinavian minimalism meets Gond tribal art)"
  }},
  "marketing_strategy": {{
    "target_segments": [
      {{"segment": "Segment name", "description": "Who they are", "approach": "How to reach them"}},
      {{"segment": "Segment name", "description": "Who they are", "approach": "How to reach them"}},
      {{"segment": "Segment name", "description": "Who they are", "approach": "How to reach them"}}
    ],
    "positioning": "One-line positioning statement for this product",
    "usp": "The unique selling proposition",
    "pricing_strategy": "Specific pricing advice based on market data",
    "storytelling_angle": "The cultural/artisan story to tell customers",
    "digital_marketing": [
      "Specific digital marketing tactic 1",
      "Specific digital marketing tactic 2",
      "Specific digital marketing tactic 3"
    ]
  }},
  "packaging": {{
    "material": "Recommended primary packaging material (eco-friendly preferred)",
    "secondary_packaging": "Outer packaging recommendation",
    "color_scheme": [
      {{"name": "Color name", "hex": "#XXXXXX", "usage": "How to use on packaging"}}
    ],
    "label_elements": [
      "Element 1 to include on the label (e.g., tribal art motif)",
      "Element 2 (e.g., QR code linking to artisan story)",
      "Element 3"
    ],
    "certifications": [
      {{"name": "Certification name (e.g., FSSAI, Organic India, GI Tag)", "why": "Why this certification matters for this product", "difficulty": "Easy/Medium/Hard to obtain"}},
      {{"name": "Certification", "why": "Reason", "difficulty": "Easy/Medium/Hard"}}
    ],
    "sustainability_notes": "Eco-friendly packaging approach specific to this product",
    "size_variants": [
      {{"size": "e.g., 50g trial pack", "price_range": "₹XX-₹XX", "target": "Who this size is for"}}
    ]
  }},
  "sales_channels": {{
    "online": [
      {{"platform": "Platform name", "why": "Why this platform suits this product", "setup_difficulty": "Easy/Medium/Hard"}}
    ],
    "offline": [
      {{"channel": "Channel type", "description": "Specific offline strategy"}}
    ],
    "b2b": [
      {{"buyer_type": "Type of B2B buyer", "approach": "How to reach them"}}
    ],
    "export": [
      {{"market": "Country/region", "potential": "High/Medium/Low", "requirements": "What is needed"}}
    ]
  }}
}}

Rules:
- color_palette MUST have exactly 4 colors with valid hex codes
- packaging.color_scheme MUST have at least 2 colors
- certifications should be realistic for Indian tribal products
- target_segments MUST have exactly 3 segments
- All recommendations must be actionable by tribal artisans or their cooperatives
- Reference actual market prices and competitors from the evidence when available
- sales_channels.online should include Indian platforms (Amazon India, Flipkart, Meesho, ONDC, Tribes India, etc.)
"""


class EnhancementGenerationError(RuntimeError):
    """Raised when the LLM cannot produce usable enhancement data."""


class EnhancementValidationError(ValueError):
    """Raised when the LLM output does not meet the expected schema."""


def _validate_enhancement(result: Any) -> dict:
    """Validate and sanitize LLM output for the enhancement schema."""
    if not isinstance(result, dict):
        raise EnhancementValidationError("Enhancement result must be a dict")

    required_sections = ("product_design", "marketing_strategy", "packaging", "sales_channels")
    for section in required_sections:
        if section not in result or not isinstance(result[section], dict):
            raise EnhancementValidationError(f"Missing or invalid section: {section}")

    pd = result["product_design"]
    if not isinstance(pd.get("color_palette"), list) or len(pd["color_palette"]) < 3:
        raise EnhancementValidationError("product_design.color_palette needs at least 3 colors")
    if not isinstance(pd.get("modernization_tips"), list) or len(pd["modernization_tips"]) < 2:
        raise EnhancementValidationError("product_design.modernization_tips needs at least 2 items")

    ms = result["marketing_strategy"]
    if not isinstance(ms.get("target_segments"), list) or len(ms["target_segments"]) < 2:
        raise EnhancementValidationError("marketing_strategy.target_segments needs at least 2 segments")

    pkg = result["packaging"]
    if not isinstance(pkg.get("certifications"), list) or len(pkg["certifications"]) < 1:
        raise EnhancementValidationError("packaging.certifications needs at least 1 certification")

    sc = result["sales_channels"]
    if not isinstance(sc.get("online"), list) or len(sc["online"]) < 1:
        raise EnhancementValidationError("sales_channels.online needs at least 1 platform")

    return result


def _build_enhancement_prompt(mfp_item: dict, recommendation: dict, market_context: dict) -> str:
    """Build the LLM prompt for product enhancement."""
    material_context = {
        "name": mfp_item.get("name"),
        "scientific_name": mfp_item.get("scientific_name"),
        "category": mfp_item.get("category"),
        "states": mfp_item.get("states", []),
        "season": mfp_item.get("season"),
        "material_properties": mfp_item.get("material_properties", {}),
    }

    product_context = {
        "product_name": recommendation.get("product_name"),
        "category_name": recommendation.get("category_name"),
        "pricing_unit": recommendation.get("pricing_unit", ""),
        "unit_cost_inr": recommendation.get("unit_cost_inr"),
        "expected_selling_price_inr": recommendation.get("expected_selling_price_inr"),
        "difficulty": recommendation.get("difficulty"),
        "target_customer_segment": recommendation.get("target_customer_segment"),
        "artisan_guide": recommendation.get("artisan_guide", []),
        "required_skills": recommendation.get("required_skills", []),
        "export_potential": recommendation.get("export_potential"),
    }

    market_evidence = {
        "market_summary": market_context.get("market_summary", {}),
        "competitor_analysis": market_context.get("competitor_analysis", {}),
        "top_products": (market_context.get("top_products") or [])[:10],
    }

    return ENHANCEMENT_PROMPT.format(
        mfp_context=json.dumps(material_context, ensure_ascii=False),
        product_context=json.dumps(product_context, ensure_ascii=False),
        market_evidence=json.dumps(market_evidence, ensure_ascii=False),
    )


def _fallback_enhancement(mfp_item: dict, recommendation: dict) -> dict:
    """Generate deterministic enhancement data when LLM is unavailable."""
    product_name = recommendation.get("product_name", "Product")
    material_name = mfp_item.get("name", "MFP Material")
    difficulty = recommendation.get("difficulty", "Medium")
    export_potential = recommendation.get("export_potential", "Medium")

    try:
        expected_price = float(recommendation.get("expected_selling_price_inr") or 300)
    except (TypeError, ValueError):
        expected_price = 300.0

    pricing_unit = str(recommendation.get("pricing_unit") or "").strip()
    unit_suffix = f" ({pricing_unit})" if pricing_unit else ""

    return {
        "product_design": {
            "form_factor": f"A compact, well-finished {product_name.lower()} made from {material_name}, designed for retail shelves and online listings with clear product visibility.",
            "modernization_tips": [
                f"Use minimalist, clean design to make {product_name} appeal to urban consumers",
                "Add a premium matte or kraft-paper finish for a contemporary artisan feel",
                "Include a small card or QR code telling the artisan's story",
            ],
            "color_palette": [
                {"name": "Forest Green", "hex": "#2D5016", "usage": "Primary brand color — represents the forest origin"},
                {"name": "Warm Cream", "hex": "#F5F0E1", "usage": "Background and label base color"},
                {"name": "Terracotta", "hex": "#C75B39", "usage": "Accent color for highlights and tribal motifs"},
                {"name": "Charcoal", "hex": "#2C2C2C", "usage": "Text and fine details"},
            ],
            "design_principles": [
                "Authenticity first — let the natural material texture and color shine through",
                "Premium minimalism — fewer design elements, higher perceived value",
                "Cultural storytelling — incorporate subtle tribal art motifs without overwhelming the design",
            ],
            "inspiration": f"Scandinavian minimalism meets Indian tribal heritage — clean lines, natural materials, warm earth tones that highlight the craftsmanship of {material_name}.",
        },
        "marketing_strategy": {
            "target_segments": [
                {"segment": "Urban Eco-Conscious Consumers", "description": "25-45 year olds in metro cities who prefer organic and sustainable products", "approach": "Instagram and Facebook ads targeting sustainable lifestyle interests"},
                {"segment": "Premium Gift Buyers", "description": "Customers looking for unique, handmade, story-driven gifts for festivals and occasions", "approach": "Feature in curated gift boxes on platforms like IGP, Qtrove"},
                {"segment": "Export/NRI Market", "description": "Indian diaspora and international buyers seeking authentic Indian artisan products", "approach": "Amazon Global, Etsy, and Indian embassy cultural events"},
            ],
            "positioning": f"Handcrafted {product_name} from tribal artisans — where forest heritage meets modern living.",
            "usp": f"100% natural {material_name}-based product, handmade by tribal artisans supporting forest-dependent livelihoods.",
            "pricing_strategy": f"Position at a 20-30% premium over mass-market alternatives. The artisan story and natural origin justify the premium. Start at ₹{expected_price:.0f}{unit_suffix} and test market response.",
            "storytelling_angle": f"Every {product_name} supports a tribal family's livelihood and preserves ancient forest knowledge passed down through generations.",
            "digital_marketing": [
                "Create short-form video content showing the artisan making the product (Instagram Reels, YouTube Shorts)",
                "Partner with sustainable lifestyle influencers for authentic product reviews",
                "Run targeted ads on Instagram with 'forest-to-home' narrative",
            ],
        },
        "packaging": {
            "material": "Recyclable kraft paper box with a seed-paper insert (plantable after use)",
            "secondary_packaging": "Corrugated cardboard mailer with printed tribal art pattern for shipping protection",
            "color_scheme": [
                {"name": "Kraft Brown", "hex": "#B8860B", "usage": "Primary packaging base"},
                {"name": "Forest Green", "hex": "#2D5016", "usage": "Brand logo and accent elements"},
                {"name": "Gold", "hex": "#D4A853", "usage": "Premium touches — borders, certification badges"},
            ],
            "label_elements": [
                "Tribal art motif border (Warli or Gond style based on region)",
                "QR code linking to artisan profile and product story video",
                f"'Made from {material_name}' origin badge with region name",
                "Weight, batch number, and manufacturing date",
                "Eco-friendly / handmade certification marks",
            ],
            "certifications": [
                {"name": "FSSAI License", "why": "Mandatory for any food/cosmetic product sold in India", "difficulty": "Medium"},
                {"name": "India Organic (NPOP)", "why": "Validates the natural, chemical-free origin — commands 15-25% price premium", "difficulty": "Medium"},
                {"name": "GI Tag (Geographical Indication)", "why": f"Protects and promotes the unique origin of {material_name} from specific tribal regions", "difficulty": "Hard"},
                {"name": "Forest Stewardship Council (FSC)", "why": "International recognition for sustainably sourced forest products", "difficulty": "Hard"},
            ],
            "sustainability_notes": "Use minimal packaging — biodegradable materials only. Include a note explaining the packaging is 100% compostable. Avoid plastic entirely.",
            "size_variants": [
                {"size": "Trial / Sample pack", "price_range": f"₹{max(30, int(expected_price * 0.45))}-₹{max(50, int(expected_price * 0.75))}", "target": "First-time buyers and online impulse purchases"},
                {"size": f"Standard pack{unit_suffix}", "price_range": f"₹{expected_price:.0f}-₹{expected_price * 1.35:.0f}", "target": "Regular consumers"},
                {"size": "Premium gift pack", "price_range": f"₹{expected_price * 1.8:.0f}-₹{expected_price * 2.8:.0f}", "target": "Gift buyers and festivals (Diwali, Christmas)"},
            ],
        },
        "sales_channels": {
            "online": [
                {"platform": "Amazon India", "why": "Largest e-commerce reach with Saheli/artisan programs", "setup_difficulty": "Medium"},
                {"platform": "Flipkart", "why": "Strong domestic reach, Samarth program for artisans", "setup_difficulty": "Medium"},
                {"platform": "Tribes India (TRIFED)", "why": "Government platform specifically for tribal products — credibility and support", "setup_difficulty": "Easy"},
                {"platform": "Meesho / ONDC", "why": "Growing social commerce platforms with lower commission rates", "setup_difficulty": "Easy"},
            ],
            "offline": [
                {"channel": "Urban Organic Stores", "description": "Stock in stores like Organic Tattva, Nature's Basket, and local organic shops in metros"},
                {"channel": "Exhibition & Melas", "description": "Participate in Surajkund Mela, Dilli Haat, and state-level tribal craft fairs"},
                {"channel": "Hotel & Resort Partnerships", "description": "Supply to eco-resorts and heritage hotels as room amenities or gift shop items"},
            ],
            "b2b": [
                {"buyer_type": "Organic & Natural Product Distributors", "approach": "Connect through trade shows like BioFach India, Natural Products Expo"},
                {"buyer_type": "Corporate Gift Companies", "approach": "Offer bulk customized packaging for Diwali/New Year corporate gifting season"},
            ],
            "export": [
                {"market": "EU & UK", "potential": "High" if export_potential == "High" else "Medium", "requirements": "EU organic certification, REACH compliance for cosmetics, proper labeling in English"},
                {"market": "USA", "potential": "Medium", "requirements": "FDA registration (for food/cosmetics), USDA organic if applicable"},
                {"market": "Japan & SE Asia", "potential": "Medium", "requirements": "JAS organic certification, local language labeling"},
            ],
        },
    }


def _extract_product_keywords(product_name: str, mfp_name: str) -> list[str]:
    """Extract distinctive search keywords from a product recommendation name."""
    stop_words = {
        "and", "the", "for", "with", "in", "of", "pack", "set", "pure",
        "natural", "organic", "raw", "grade", "refined", "crude", "item",
        "product", "products", "making", "based", "handcrafted", "traditional",
        "tribal", "fat", "powder"
    }
    mfp_words = set(re.findall(r"[a-zA-Z]{3,}", (mfp_name or "").lower()))
    words = re.findall(r"[a-zA-Z]{3,}", (product_name or "").lower())

    clean_words = []
    for w in words:
        if w in stop_words or w in mfp_words:
            continue
        clean_words.append(w)
        # Handle plurals
        if w.endswith("s") and len(w) > 4:
            clean_words.append(w[:-1])

    # Fallback to any non-stop words if everything got excluded
    if not clean_words:
        clean_words = [w for w in words if w not in stop_words]

    return list(dict.fromkeys(clean_words))


def _find_related_market_examples(
    mfp_name: str,
    recommendation: dict,
    market_context: dict,
    max_results: int = 2,
) -> list[dict]:
    """Find 1-2 product examples strictly related to the recommendation.

    1. First, search existing market_context products for keywords matching
       the specific recommendation (e.g. 'candle', 'soap', 'incense', etc.).
    2. If fewer than max_results matching products exist in market_context,
       search online via EcommerceClient for the specific product.
    3. Return only products with images that are genuinely relevant.
    """
    product_name = recommendation.get("product_name", "")
    keywords = _extract_product_keywords(product_name, mfp_name)

    matched: list[dict] = []
    seen_urls: set[str] = set()

    # Step 1: Check existing market_context products
    candidates = []
    if isinstance(market_context, dict):
        candidates.extend(market_context.get("top_products") or [])
        candidates.extend(market_context.get("all_products") or [])

    for p in candidates:
        if not isinstance(p, dict) or not p.get("image_url"):
            continue
        title = (p.get("title") or "").lower()
        if any(kw in title for kw in keywords):
            url = p.get("image_url")
            if url not in seen_urls:
                seen_urls.add(url)
                matched.append(p)
                if len(matched) >= max_results:
                    return matched

    # Step 2: Fetch from web if fewer than max_results found
    if len(matched) < max_results:
        try:
            from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient
            client = EcommerceClient()
            mfp_base = (mfp_name.split()[0] if mfp_name else "").strip()
            kw_str = " ".join(keywords[:2])
            queries_to_try = [
                f"{mfp_base} {kw_str}".strip() if kw_str else f"{mfp_base} {product_name}",
                f"{product_name} buy online India",
            ]
            for query in queries_to_try:
                if len(matched) >= max_results or not query:
                    break
                web_prods = client.search_products(query, num_results=5)
                for p in web_prods:
                    if not isinstance(p, dict) or not p.get("image_url"):
                        continue
                    title = (p.get("title") or "").lower()
                    if any(kw in title for kw in keywords) or not keywords:
                        url = p.get("image_url")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            matched.append(p)
                            if len(matched) >= max_results:
                                break
        except Exception as e:
            print(f"  [EnhancementService] Online example search error: {e}")

    return matched[:max_results]


def generate_enhancement(
    mfp_id: int,
    recommendation: dict,
    market_context: dict,
) -> dict:
    """Generate comprehensive product enhancement guidance.

    Primary path: LLM-powered with structured prompt.
    Fallback: deterministic template-based output.
    """
    start = time.time()

    mfp_item = _find_mfp_item(mfp_id)
    if not mfp_item:
        raise LookupError(f"MFP item with id {mfp_id} not found")

    if not isinstance(recommendation, dict) or not recommendation.get("product_name"):
        raise EnhancementValidationError("A valid recommendation object with product_name is required")

    fallback_used = False
    provider_name = "none"

    try:
        llm = _LLMClient()
        if llm.provider:
            prompt = _build_enhancement_prompt(mfp_item, recommendation, market_context)
            result = llm.call(prompt)
            if result:
                enhancement = _validate_enhancement(result)
                provider_name = llm.provider
            else:
                raise RuntimeError("LLM returned empty result")
        else:
            raise RuntimeError("No LLM provider configured")
    except Exception as llm_err:
        print(f"  [EnhancementService] LLM unavailable ({llm_err}), using fallback")
        fallback_used = True
        provider_name = "deterministic"
        enhancement = _fallback_enhancement(mfp_item, recommendation)

    # Find 1-2 product examples strictly related to this recommendation
    related_examples = _find_related_market_examples(
        mfp_name=mfp_item.get("name", ""),
        recommendation=recommendation,
        market_context=market_context,
        max_results=2,
    )

    return {
        "status": "complete",
        "mfp_id": mfp_id,
        "mfp_name": mfp_item.get("name"),
        "product_name": recommendation.get("product_name"),
        "enhancement": enhancement,
        "related_examples": related_examples,
        "elapsed_seconds": round(time.time() - start, 2),
        "provider": provider_name,
        "fallback_used": fallback_used,
    }

