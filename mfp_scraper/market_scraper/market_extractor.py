"""
LLM-based product classification and market analysis.

Classifies scraped e-commerce products against the 87 MFP categories using
Groq/Gemini, then generates market summaries and competitor analysis.
Follows Module 1's DeepExtractor patterns for provider fallback and retry logic.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from . import config_market
from .market_models import (
    build_competitor_analysis,
    build_market_summary,
    calculate_confidence,
    calculate_demand_score,
    calculate_trend,
    dedupe_strings,
    utc_now_iso,
)


# ── Prompt Templates ────────────────────────────────────────────────────────

MARKET_CLASSIFICATION_PROMPT = """You are classifying e-commerce products into Indian Minor Forest Produce (MFP) categories.

Available MFP Categories:
{mfp_categories}

Target MFP context:
{target_mfp_context}

Task: For EACH product below, determine which MFP category it matches (if any),
and classify it as "raw", "derived", or "invalid".
- "raw" = the material sold in unprocessed/minimally-processed form (e.g., "Raw Bamboo Sticks 5kg", "Natural Honey 1kg")
- "derived" = a value-added product made FROM the material (e.g., "Bamboo Lamp Shade", "Honey Face Wash")
- "invalid" = the product has NO genuine connection to any MFP category (see rules below)

Products to classify:
{products_text}

Respond with valid JSON only:
{{
  "classifications": [
    {{
      "product_index": 0,
      "matched_mfp_ids": [2],
      "match_confidence": 0.9,
      "product_type": "raw",
      "matching_attributes": ["raw", "forest", "pure"],
      "reasoning": "Product is raw forest honey matching MFP #2 Wild Honey"
    }}
  ]
}}

Rules:
- Only match products that clearly relate to an MFP item
- Set match_confidence between 0.0 and 1.0
- A product can match multiple MFP IDs if it uses multiple raw materials
- If a product does not match any MFP, set matched_mfp_ids to empty list
- Be conservative — only match when confident
- The target context lists known product forms and search aliases. It helps
  identify legitimate target products, but never overrides the invalid rules.
- product_type MUST be "raw", "derived", or "invalid" for every classification

CRITICAL — classify as "invalid" if the product is ANY of the following:
1. Books, textbooks, e-books, PDFs, journals, research papers, or educational material
2. Completely unrelated items that appeared due to keyword overlap (e.g., "A4 Copier Paper" for a bamboo query, "Phone Case" for a neem query)
3. Heavy industrial machinery or lab equipment (unless the MFP specifically involves processing equipment)
4. Software, apps, or digital services
5. Generic office/stationery supplies with no real MFP connection
If classified as "invalid", set matched_mfp_ids to an empty list and match_confidence to 0.0.
"""

MARKET_ANALYSIS_PROMPT = """You are analyzing the e-commerce market for an Indian Minor Forest Produce (MFP) item.

MFP Item: {mfp_name} (ID: {mfp_id})
Category: {mfp_category}
Current Products: {current_products}
Potential Products: {potential_products}
Minimum Support Price (MSP): ₹{msp} per {unit}
Harvesting Season: {season}

Market Data (scraped from e-commerce platforms):
{market_data_text}

Analyze this market data and respond with valid JSON only:
{{
  "competitor_analysis": {{
    "top_brands": ["Brand1", "Brand2", "Brand3"],
    "market_gaps": ["Gap 1", "Gap 2"],
    "price_positioning": "budget|mid-range|premium|luxury"
  }},
  "demand_indicators": {{
    "trend_direction": "rising|stable|declining",
    "key_demand_drivers": ["driver1", "driver2"],
    "seasonal_patterns": "description of seasonality if apparent"
  }},
  "opportunities": ["opportunity 1", "opportunity 2"],
  "seasonal_demand": {{
    "peak_seasons": ["Diwali", "Christmas"],
    "seasonal_pattern": "Short description of demand seasonality",
    "off_season_strategy": "Suggestion for off-season revenue"
  }},
  "product_demand_match": {{
    "validated_products": ["products from Current/Potential list that have confirmed market demand"],
    "unvalidated_products": ["products from Current/Potential list with no market evidence"],
    "demand_alignment_score": 0.75
  }},
  "regional_market_fit": [
    {{"region": "Mumbai", "fit": "premium décor", "confidence": 0.8}},
    {{"region": "Bengaluru", "fit": "sustainable workspace items", "confidence": 0.7}},
    {{"region": "Europe", "fit": "handcrafted eco luxury", "confidence": 0.6}}
  ]
}}

Rules:
- Be concise and specific to the Indian market context.
- For seasonal_demand, consider Indian festivals (Diwali, Holi, Navratri, Pongal, Christmas) and seasonal cycles.
- For product_demand_match, cross-reference the Current/Potential products lists against what you see in the market data.
- For regional_market_fit, suggest 3-5 regions (Indian cities or export markets) with product-market fit.
"""


class MarketExtractor:
    """Extract market intelligence using LLM classification and analysis."""

    def __init__(self):
        self.provider = None
        self.client = None
        self._last_call_time = 0.0
        self.exhausted_models: set[str] = set()
        self._initialize_provider()

    def describe_provider(self) -> str:
        """Return the active LLM provider name."""
        return self.provider or "none"

    # ── Public API ──────────────────────────────────────────────────────────

    def classify_products(
        self,
        products: list[dict],
        mfp_items: list[dict],
        target_mfp_id: int,
        target_category_context: Optional[list[dict]] = None,
        classify_all_batches: bool = False,
    ) -> list[dict]:
        """Classify scraped products against MFP categories via LLM.

        Returns products with updated confidence and matched_mfp_ids fields.
        Falls back to keyword matching if no LLM is available.
        """
        if not products:
            return []

        # Always apply keyword classification first
        products = self._keyword_classify(products, mfp_items, target_mfp_id)

        if not self.provider:
            return products

        # The live endpoint opts into classifying every retained result so late
        # category-specific products are not absent from the matched-only view.
        # Other callers retain the existing single-batch behaviour by default.
        batch_size = config_market.MAX_PRODUCTS_FOR_LLM
        classification_limit = len(products) if classify_all_batches else min(len(products), batch_size)
        for batch_start in range(0, classification_limit, batch_size):
            batch = products[batch_start: batch_start + batch_size]
            llm_results = self._llm_classify(
                batch,
                mfp_items,
                target_mfp_id=target_mfp_id,
                target_category_context=target_category_context,
            )

            if not llm_results:
                continue

            # LLM product indices are local to this batch; offset them before
            # applying classifications to the original product list.
            for classification in llm_results:
                local_index = classification.get("product_index", -1)
                if not isinstance(local_index, int):
                    continue
                index = batch_start + local_index
                if not 0 <= index < len(products):
                    continue

                product_type = classification.get("product_type", "derived")

                # Reject invalid products entirely
                if product_type == "invalid":
                    products[index]["product_type"] = "invalid"
                    products[index]["matched_mfp_ids"] = []
                    products[index]["confidence"] = 0.0
                    products[index]["llm_reasoning"] = classification.get("reasoning", "Classified as invalid")
                    continue

                matched_ids = classification.get("matched_mfp_ids", [])
                conf = float(classification.get("match_confidence", 0.0))
                if matched_ids:
                    products[index]["matched_mfp_ids"] = matched_ids
                    products[index]["confidence"] = round(max(
                        products[index].get("confidence", 0.0), conf
                    ), 3)
                    products[index]["matching_attributes"] = classification.get(
                        "matching_attributes", []
                    )
                    products[index]["llm_reasoning"] = classification.get("reasoning", "")
                    products[index]["product_type"] = product_type

        # Remove invalid products completely — they should never appear in the UI
        products = [p for p in products if p.get("product_type") != "invalid"]

        return products

    def analyze_market(self, mfp_item: dict, products: list[dict]) -> Optional[dict]:
        """Generate market analysis summary for an MFP item via LLM.

        Returns competitor analysis and demand indicators, or None if LLM unavailable.
        """
        if not self.provider or not products:
            return None

        # Build market data summary for prompt
        market_text = self._build_market_data_text(products[:15])

        prompt = MARKET_ANALYSIS_PROMPT.format(
            mfp_name=mfp_item.get("name", ""),
            mfp_id=mfp_item.get("mfp_id", ""),
            mfp_category=mfp_item.get("category", ""),
            current_products=", ".join(mfp_item.get("current_products", [])),
            potential_products=", ".join(mfp_item.get("potential_products", [])),
            msp=mfp_item.get("msp", 0),
            unit=mfp_item.get("unit", "kg"),
            season=mfp_item.get("season", "Year-round"),
            market_data_text=market_text,
        )

        result = self._call_llm(prompt)
        if not result:
            return None

        return result

    # ── Provider initialization ─────────────────────────────────────────────

    def _initialize_provider(self):
        """Choose an available LLM provider (Groq → Gemini fallback)."""
        if config_market.GROQ_API_KEY:
            try:
                import groq
                self.client = groq.Groq(api_key=config_market.GROQ_API_KEY)
                self.provider = "groq"
                return
            except Exception:
                self.client = None

        if config_market.GEMINI_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=config_market.GEMINI_API_KEY)
                self.provider = "gemini"
                return
            except Exception:
                self.client = None

    def _rate_limit(self):
        """Enforce delay between LLM calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < config_market.LLM_DELAY_SECONDS:
            time.sleep(config_market.LLM_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    # ── LLM classification ──────────────────────────────────────────────────

    def _llm_classify(
        self,
        products: list[dict],
        mfp_items: list[dict],
        target_mfp_id: int,
        target_category_context: Optional[list[dict]] = None,
    ) -> Optional[list[dict]]:
        """Batch classify products via LLM."""
        # Build MFP category list for prompt
        mfp_categories = "\n".join(
            f"- MFP ID {item['mfp_id']}: {item['name']} ({', '.join(item.get('current_products', [])[:2])})"
            for item in mfp_items
        )

        # Build products text
        products_text = "\n".join(
            f"[Product {i}] Title: \"{p['title']}\" | Price: {p.get('price', 'N/A')} INR | "
            f"Seller: {p.get('seller', 'N/A')} | Source: {p.get('source', 'N/A')}"
            for i, p in enumerate(products)
        )

        if target_category_context is None:
            target_mfp_context = "No additional target-specific vocabulary supplied."
        else:
            target_item = next(
                (item for item in mfp_items if item.get("mfp_id") == target_mfp_id),
                None,
            )
            target_products: list[str] = []
            if target_item:
                target_products.extend(target_item.get("current_products", []))
                target_products.extend(target_item.get("potential_products", []))
            for category in target_category_context:
                if not isinstance(category, dict):
                    continue
                for product in category.get("products", []):
                    product_name = product.get("name", "") if isinstance(product, dict) else str(product)
                    if product_name:
                        target_products.append(product_name)

            target_mfp_context = (
                f"Target MFP ID {target_mfp_id}: {target_item.get('name', '') if target_item else ''}\n"
                f"Known target product forms: {', '.join(dedupe_strings(target_products)) or 'None listed'}"
            )

        prompt = MARKET_CLASSIFICATION_PROMPT.format(
            mfp_categories=mfp_categories,
            target_mfp_context=target_mfp_context,
            products_text=products_text,
        )

        result = self._call_llm(prompt)
        if not result:
            return None

        return result.get("classifications", [])

    def _keyword_classify(
        self,
        products: list[dict],
        mfp_items: list[dict],
        target_mfp_id: int,
    ) -> list[dict]:
        """Fallback keyword-based classification.

        Matches product titles against MFP names, current products, and potential products.
        """
        # Build keyword index for the target MFP
        target_item = None
        for item in mfp_items:
            if item["mfp_id"] == target_mfp_id:
                target_item = item
                break

        if not target_item:
            return products

        keywords = set()
        keywords.add(target_item["name"].lower())
        for product_name in target_item.get("current_products", []):
            keywords.add(product_name.lower())
        for product_name in target_item.get("potential_products", []):
            keywords.add(product_name.lower())
        # Add individual words from product names (3+ chars)
        expanded = set()
        for kw in keywords:
            for word in kw.split():
                if len(word) >= 3:
                    expanded.add(word)
        keywords.update(expanded)

        for product in products:
            title_lower = product.get("title", "").lower()
            matched_keywords = [kw for kw in keywords if kw in title_lower]
            if matched_keywords:
                product["matched_mfp_ids"] = product.get("matched_mfp_ids", [])
                if target_mfp_id not in product["matched_mfp_ids"]:
                    product["matched_mfp_ids"].append(target_mfp_id)
                # Confidence based on keyword match density
                match_ratio = min(len(matched_keywords) / 3.0, 1.0)
                keyword_conf = round(0.4 + (match_ratio * 0.3), 3)  # 0.4 to 0.7
                product["confidence"] = max(product.get("confidence", 0.0), keyword_conf)
                product["matching_attributes"] = product.get("matching_attributes", [])
                product["matching_attributes"].extend(matched_keywords[:5])
                product["matching_attributes"] = dedupe_strings(product["matching_attributes"])

        return products

    # ── LLM call dispatchers ────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> Optional[dict]:
        """Route LLM call to the active provider."""
        if self.provider == "groq":
            return self._call_groq(prompt)
        if self.provider == "gemini":
            return self._call_gemini(prompt)
        return None

    def _call_groq(self, prompt: str) -> Optional[dict]:
        """Call Groq for JSON-structured extraction."""
        for model_name in config_market.GROQ_MODELS:
            if model_name in self.exhausted_models:
                continue

            for attempt in range(config_market.LLM_MAX_RETRIES):
                try:
                    self._rate_limit()
                    response = self.client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a market analysis assistant. Return valid JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=config_market.LLM_TEMPERATURE,
                        max_tokens=4096,
                        response_format={"type": "json_object"},
                    )
                    raw_text = response.choices[0].message.content.strip()
                    parsed = self._parse_response(raw_text)
                    if parsed is not None:
                        return parsed

                except Exception as exc:
                    error_str = str(exc)
                    if "429" in error_str or "rate limit" in error_str.lower():
                        retry_match = re.search(r"Please try again in ([\d\.]+)s", error_str)
                        retry_secs = float(retry_match.group(1)) + 1 if retry_match else 10
                        time.sleep(retry_secs)
                        continue
                    if "quota" in error_str.lower() or "exceeded" in error_str.lower():
                        self.exhausted_models.add(model_name)
                        break
                    if attempt >= config_market.LLM_MAX_RETRIES - 1:
                        break
                    time.sleep(3 * (attempt + 1))

        return None

    def _call_gemini(self, prompt: str) -> Optional[dict]:
        """Call Gemini for JSON-structured extraction."""
        from google.genai import types

        for model_name in config_market.GEMINI_MODELS:
            if model_name in self.exhausted_models:
                continue

            for attempt in range(config_market.LLM_MAX_RETRIES):
                try:
                    self._rate_limit()
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=config_market.LLM_TEMPERATURE,
                            max_output_tokens=4096,
                            response_mime_type="application/json",
                        ),
                    )
                    raw_text = response.text.strip() if response.text else ""
                    parsed = self._parse_response(raw_text)
                    if parsed is not None:
                        return parsed

                except Exception as exc:
                    error_str = str(exc)
                    if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                        if attempt >= config_market.LLM_MAX_RETRIES - 1:
                            self.exhausted_models.add(model_name)
                            break
                        time.sleep(8)
                        continue
                    if attempt >= config_market.LLM_MAX_RETRIES - 1:
                        break
                    time.sleep(3 * (attempt + 1))

        return None

    # ── Response parsing ────────────────────────────────────────────────────

    def _parse_response(self, raw_text: str) -> Optional[dict]:
        """Parse JSON from LLM response with fallbacks for markdown fences."""
        cleaned = raw_text.strip()
        if not cleaned:
            return None

        # Strip markdown code fences
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            cleaned = match.group(1).strip() if match else cleaned.replace("```", "").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON object
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1:
                return None
            try:
                return json.loads(cleaned[start: end + 1])
            except json.JSONDecodeError:
                return None

    def _build_market_data_text(self, products: list[dict]) -> str:
        """Build a concise market data summary for the analysis prompt."""
        lines = []
        for i, p in enumerate(products, 1):
            price_str = f"₹{p['price']}" if p.get("price") else "N/A"
            rating_str = f"{p['rating']}★" if p.get("rating") else "N/A"
            reviews_str = f"{p.get('review_count', 0)} reviews"
            attrs = ", ".join(a["name"] for a in p.get("attributes", []) if a.get("value") is True)

            lines.append(
                f"{i}. \"{p['title']}\" | {price_str} | {rating_str} ({reviews_str}) | "
                f"Seller: {p.get('seller', 'N/A')} | Attrs: {attrs or 'none'}"
            )

        return "\n".join(lines)
