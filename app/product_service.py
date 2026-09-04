"""
Hybrid Product Categorization Service for the MAERII Knowledge Engine.

Generates structured product categories with manufacturing processes and
required artisan skills for a given MFP item, using real-time LLM calls
backed by a persistent local file cache.

Architecture:
  1. Check persistent cache (data/.cache_product_categories.json)
  2. On miss → load MFP context from enriched_mfp_data.json
  3. Call LLM (Groq → Gemini fallback) to generate categories
  4. Save result to cache file + return to caller

Cache survives server restarts (Ctrl+C). Core enriched data is never mutated.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mfp_scraper import config as scraper_config


# ── Paths ───────────────────────────────────────────────────────────────────

ENRICHED_PATH = PROJECT_ROOT / "data" / "enriched_mfp_data.json"
CACHE_PATH = PROJECT_ROOT / "data" / ".cache_product_categories.json"


# ── Prompt Template ─────────────────────────────────────────────────────────

CATEGORIZATION_PROMPT = """You are an expert in Indian Minor Forest Produce (MFP) value chains, tribal livelihoods, and artisan product development.

MFP Material:
  Name: {name}
  Scientific Name: {scientific_name}
  Category: {category}
  Season: {season}
  Shelf Life: {shelf_life}
  States: {states}
  Material Properties: strength={strength}, flexibility={flexibility}, texture={texture}, water_resistance={water_resistance}, biodegradability={biodegradability}, workability={workability}

Known Products (current): {current_products}
Known Products (potential): {potential_products}
Artisan Types: {artisan_types}

Task: Group all the known and potential products into 2–5 logical commercial product categories. For each category, list the specific products it contains. For each product, provide:
1. A realistic step-by-step manufacturing process (4–7 steps) that tribal artisans would follow to create the product from the raw MFP material.
2. The specific skills that artisans must possess or learn to execute that manufacturing process.
3. A difficulty rating (Easy, Medium, or Hard) reflecting the equipment and expertise required.
4. An estimated production cost range in Indian Rupees.
5. Market potential (low, medium, or high).

Respond with valid JSON only:
{{
  "product_categories": [
    {{
      "category_name": "Oils & Extracts",
      "products": [
        {{
          "name": "Cold-Pressed Oil",
          "difficulty": "Medium",
          "estimated_cost": "₹80-120 per litre",
          "market_potential": "high",
          "manufacturing_process": [
            "Harvest and collect seeds/fruits",
            "Sun-dry for 2-3 days to reduce moisture",
            "Clean, sort, and grade the dried material",
            "Crush using wooden mortar or mechanical grinder",
            "Cold-press using oil expeller machine",
            "Filter through muslin cloth and settle for 24 hours",
            "Bottle in dark glass containers for storage"
          ],
          "required_skills": [
            "Seed identification and quality grading",
            "Oil expeller machine operation",
            "Quality testing (moisture, purity checks)",
            "Hygienic bottling and packaging"
          ]
        }}
      ]
    }}
  ]
}}

Rules:
- Categories should be logically distinct (e.g., "Food & Beverages", "Personal Care", "Handicrafts", "Medicinal & Health")
- Every product must have at least 4 manufacturing steps
- Manufacturing steps must be specific and realistic for tribal artisan contexts (no industrial factory equipment unless the product truly requires it)
- Required skills must be actionable and specific (not generic like "good hands")
- Be practical about difficulty — if it needs expensive machinery, mark it Hard
- Cost estimates should reflect Indian rural economics
- Do NOT invent fictional products — only include products that are realistically manufacturable from this specific MFP material
"""


# ── Enriched Data Loader ────────────────────────────────────────────────────

_mfp_items_cache: Optional[list[dict]] = None


def _load_mfp_items() -> list[dict]:
    """Load the enriched MFP dataset (cached after first call)."""
    global _mfp_items_cache
    if _mfp_items_cache is None:
        with open(ENRICHED_PATH, "r", encoding="utf-8") as f:
            _mfp_items_cache = json.load(f)
    return _mfp_items_cache


def _find_mfp_item(mfp_id: int) -> Optional[dict]:
    """Find a single MFP item by ID."""
    for item in _load_mfp_items():
        if item.get("mfp_id") == mfp_id:
            return item
    return None


# ── Persistent File Cache ───────────────────────────────────────────────────

_category_cache: dict[int, dict] = {}
_cache_loaded = False


def _load_cache():
    """Load the persistent cache from disk into memory (once at startup)."""
    global _category_cache, _cache_loaded
    if _cache_loaded:
        return
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Keys in JSON are strings; convert to int
            _category_cache = {int(k): v for k, v in raw.items()}
            print(f"  [ProductService] Loaded {len(_category_cache)} cached categories from disk")
        except Exception as e:
            print(f"  [ProductService] Cache load failed ({e}), starting fresh")
            _category_cache = {}
    _cache_loaded = True


def _save_cache():
    """Persist the in-memory cache to disk."""
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_category_cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  [ProductService] Cache save failed: {e}")


def get_cached_product_categories(mfp_id: int) -> Optional[list[dict]]:
    """Return previously generated categories without starting a new LLM call.

    Recommendation generation must build on the category step the user has
    already completed.  Keeping this separate from ``get_product_categories``
    prevents a direct recommendation request from silently generating new
    categories.
    """
    _load_cache()
    cached = _category_cache.get(mfp_id)
    if not cached:
        return None
    categories = cached.get("product_categories")
    return categories if isinstance(categories, list) and categories else None


# ── LLM Provider Logic ─────────────────────────────────────────────────────

import threading

class _LLMClient:
    """Lightweight LLM caller with Groq → Gemini fallback.

    Reuses the same provider pattern as MarketExtractor.
    """
    _last_call_time = 0.0
    _exhausted_models: set[str] = set()
    _lock = threading.Lock()

    def __init__(self):
        self.provider: Optional[str] = None
        self.client = None
        self._initialize_provider()

    def _initialize_provider(self):
        """Choose an available LLM provider (Groq → Gemini)."""
        groq_key = scraper_config.GROQ_API_KEY
        gemini_key = scraper_config.GEMINI_API_KEY

        if groq_key:
            try:
                import groq
                self.client = groq.Groq(api_key=groq_key)
                self.provider = "groq"
                return
            except Exception:
                pass

        if gemini_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=gemini_key)
                self.provider = "gemini"
                return
            except Exception:
                pass

    def _rate_limit(self):
        """Enforce a minimum delay between LLM calls."""
        with _LLMClient._lock:
            elapsed = time.time() - _LLMClient._last_call_time
            delay = 4.0
            if elapsed < delay:
                time.sleep(delay - elapsed)
            _LLMClient._last_call_time = time.time()

    def call(self, prompt: str) -> Optional[dict]:
        """Call the LLM and return parsed JSON, or None on failure."""
        if not self.provider:
            return None

        if self.provider == "groq":
            return self._call_groq(prompt)
        return self._call_gemini(prompt)

    def _call_groq(self, prompt: str) -> Optional[dict]:
        """Call Groq API for JSON output."""
        models = scraper_config.GROQ_MODELS

        for model_name in models:
            if model_name in _LLMClient._exhausted_models:
                continue

            for attempt in range(3):
                try:
                    self._rate_limit()
                    response = self.client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a product categorization assistant for tribal forest produce. Return valid JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=4096,
                        response_format={"type": "json_object"},
                    )
                    raw_text = response.choices[0].message.content.strip()
                    return self._parse_response(raw_text)

                except Exception as exc:
                    error_str = str(exc)
                    print(f"  [_call_groq] error: {error_str}")
                    if "429" in error_str or "rate limit" in error_str.lower():
                        retry_match = re.search(r"Please try again in ([\d\.]+)s", error_str)
                        retry_secs = float(retry_match.group(1)) + 1 if retry_match else 10
                        time.sleep(retry_secs)
                        continue
                    if "quota" in error_str.lower() or "exceeded" in error_str.lower():
                        _LLMClient._exhausted_models.add(model_name)
                        break
                    if attempt >= 2:
                        break
                    time.sleep(3 * (attempt + 1))

        # Fallback to Gemini if Groq fails
        if scraper_config.GEMINI_API_KEY and self.provider == "groq":
            try:
                from google import genai
                self.client = genai.Client(api_key=scraper_config.GEMINI_API_KEY)
                self.provider = "gemini"
                return self._call_gemini(prompt)
            except Exception:
                pass

        return None

    def _call_gemini(self, prompt: str) -> Optional[dict]:
        """Call Gemini API for JSON output."""
        from google.genai import types

        models = scraper_config.GEMINI_MODELS

        for model_name in models:
            if model_name in _LLMClient._exhausted_models:
                continue

            for attempt in range(3):
                try:
                    self._rate_limit()
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            max_output_tokens=4096,
                            response_mime_type="application/json",
                        ),
                    )
                    raw_text = response.text.strip() if response.text else ""
                    return self._parse_response(raw_text)

                except Exception as exc:
                    error_str = str(exc)
                    print(f"  [_call_gemini] error: {error_str}")
                    if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                        if attempt >= 2:
                            _LLMClient._exhausted_models.add(model_name)
                            break
                        time.sleep(8)
                        continue
                    if attempt >= 2:
                        break
                    time.sleep(3 * (attempt + 1))

        return None

    @staticmethod
    def _parse_response(raw_text: str) -> Optional[dict]:
        """Parse JSON from LLM response with markdown fence fallback."""
        if not raw_text:
            return None

        # Try direct parse
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw_text, flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.MULTILINE)
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            return None


# ── Public API ──────────────────────────────────────────────────────────────

def get_product_categories(mfp_id: int, refresh: bool = False) -> dict:
    """Generate or retrieve product categories for an MFP item.

    Args:
        mfp_id: The MFP identifier.
        refresh: If True, bypasses cache and regenerates from LLM.

    Returns:
        A dict with status, mfp_id, mfp_name, product_categories, cached, elapsed_seconds.
    """
    _load_cache()
    start_time = time.time()

    # 1. Find the MFP item
    mfp_item = _find_mfp_item(mfp_id)
    if not mfp_item:
        return {
            "status": "error",
            "error": f"MFP item with id {mfp_id} not found.",
        }

    # 2. Check cache (unless refresh requested)
    if not refresh and mfp_id in _category_cache:
        cached_data = _category_cache[mfp_id]
        return {
            "status": "complete",
            "mfp_id": mfp_id,
            "mfp_name": mfp_item["name"],
            "product_categories": cached_data.get("product_categories", []),
            "cached": True,
            "elapsed_seconds": round(time.time() - start_time, 2),
        }

    # 3. Build prompt from MFP context
    mat_props = mfp_item.get("material_properties", {})

    prompt = CATEGORIZATION_PROMPT.format(
        name=mfp_item.get("name", ""),
        scientific_name=mfp_item.get("scientific_name", "Unknown"),
        category=mfp_item.get("category", "Forest Produce"),
        season=mfp_item.get("season", "Year-round"),
        shelf_life=mfp_item.get("shelf_life", "Unknown"),
        states=", ".join(mfp_item.get("states", [])) or "All India",
        strength=mat_props.get("strength", "unknown"),
        flexibility=mat_props.get("flexibility", "unknown"),
        texture=mat_props.get("texture", "unknown"),
        water_resistance=mat_props.get("water_resistance", "unknown"),
        biodegradability=mat_props.get("biodegradability", "unknown"),
        workability=mat_props.get("workability", "unknown"),
        current_products=", ".join(mfp_item.get("current_products", [])) or "None listed",
        potential_products=", ".join(mfp_item.get("potential_products", [])) or "None listed",
        artisan_types=", ".join(mfp_item.get("artisan_types", [])) or "General artisan",
    )

    # 4. Call LLM
    llm = _LLMClient()
    if not llm.provider:
        return {
            "status": "error",
            "error": "No LLM provider available. Set GROQ_API_KEY or GEMINI_API_KEY in .env",
        }

    print(f"  [ProductService] Generating categories for MFP {mfp_id}: {mfp_item['name']}...")
    result = llm.call(prompt)

    if not result or "product_categories" not in result:
        return {
            "status": "error",
            "error": "LLM failed to generate valid product categories. Try again.",
        }

    categories = result["product_categories"]

    # 5. Save to persistent cache
    _category_cache[mfp_id] = {
        "product_categories": categories,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": llm.provider,
    }
    _save_cache()

    elapsed = round(time.time() - start_time, 2)
    print(f"  [ProductService] Generated {len(categories)} categories in {elapsed}s (cached to disk)")

    return {
        "status": "complete",
        "mfp_id": mfp_id,
        "mfp_name": mfp_item["name"],
        "product_categories": categories,
        "cached": False,
        "elapsed_seconds": elapsed,
    }
