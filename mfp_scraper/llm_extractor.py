"""
LLM Extractor — uses Google Gemini to extract structured fields from raw text.
Uses the new google.genai SDK (not the deprecated google.generativeai).
"""

import json
import time
import re
from typing import Optional

from google import genai
from google.genai import types

from . import config


# -- Extraction prompt template ----------------------------------------------

EXTRACTION_PROMPT = """You are a data extraction specialist for Indian Minor Forest Produce (MFP).

Given the following information gathered from the internet about "{item_name}" (Category: {category}), extract the requested fields accurately.

IMPORTANT RULES:
1. Only extract information that is explicitly stated or strongly implied in the source text.
2. For "states", list ONLY the Indian states where this item is ACTUALLY collected by tribal communities. Do NOT list all states. Focus on states with significant tribal collection activity. Typically 3-8 states.
3. For "artisan_types", describe the types of tribal people who collect/process this (e.g., "Honey Gatherer", "Leaf Collector", "Gum Tapper", "Seed Collector").
4. For "current_products", list products CURRENTLY being made from this raw material.
5. For "potential_products", list HIGHER-VALUE products that COULD be made but often aren't yet (value-addition opportunities).
6. For "season", provide the harvesting/collection months (e.g., "March-June" or "October-February").
7. For "shelf_life", provide ONLY a short duration value like "18 months" or "6-12 months" or "2 years". Do NOT write full sentences. Just the number and unit.
8. For "description", write a concise 1-2 sentence description of what this forest produce is and why it's important.
9. For "scientific_name", provide only if found in the text and if the current value is missing.

EXISTING DATA (do NOT overwrite unless improving):
- Name: {item_name}
- Scientific Name: {existing_scientific_name}
- Category: {category}
- MSP: Rs.{msp}/kg
- Known States: {existing_states}

SOURCE TEXT:
{source_text}

Respond with ONLY a valid JSON object (no markdown, no explanation) with these fields:
{{
  "scientific_name": "<botanical name or null if not found>",
  "description": "<1-2 sentence description>",
  "season": "<collection/harvesting months, e.g., March-June>",
  "shelf_life": "<duration only, e.g., 18 months>",
  "states": ["<state1>", "<state2>", ...],
  "artisan_types": ["<type1>", "<type2>", ...],
  "current_products": ["<product1>", "<product2>", ...],
  "potential_products": ["<product1>", "<product2>", ...],
  "confidence": {{
    "scientific_name": <0.0-1.0>,
    "description": <0.0-1.0>,
    "season": <0.0-1.0>,
    "shelf_life": <0.0-1.0>,
    "states": <0.0-1.0>,
    "artisan_types": <0.0-1.0>,
    "current_products": <0.0-1.0>,
    "potential_products": <0.0-1.0>
  }}
}}
"""

MATERIAL_SCORES_PROMPT = """You are an expert in Indian Minor Forest Produce (MFP) analyzing material properties.

Material:
- Name: {item_name}
- Scientific name: {scientific_name}
- Category: {category}
- Current products: {current_products}
- Description: {description}

Analyze this SPECIFIC material and return a JSON with three sections.

SECTION 1 — Material Properties:
Consider what products can actually be made from this material. Be precise:
- strength: how structurally strong is the raw material? (seeds/powders = low, wood/bamboo = high, fibers = medium)
- flexibility: can it bend without breaking? (resins/seeds = low, leaves/fibers = high, gums = medium)
- texture: the dominant surface feel of the raw material
- water_resistance: does it resist moisture? (leaves/flowers = low, resins/lac = high, seeds = medium)
- biodegradability: how fast does it decompose? (leaves/flowers = high and fast, resins/lac = low and slow, seeds = medium)
- workability: how easy is it to process into products? (powders/gums = easy, hard seeds = difficult, leaves = moderate)

SECTION 2 — Sustainability Score:
CRITICAL: Do NOT give every material the same score. Use this rubric:

0.90-1.0: Fast-regenerating, abundant, zero-harm harvesting (e.g., fallen leaves, shed bark)
0.75-0.89: Renewable but needs moderate management (e.g., tree-borne seeds with annual cycles)
0.60-0.74: Renewable but harvesting can stress the source (e.g., gum tapping, resin extraction that wounds trees)
0.45-0.59: Slow-regenerating or harvesting has ecological side effects (e.g., wild honey disturbs bee colonies)
0.30-0.44: Overharvested or threatened species, or significant processing pollution
0.15-0.29: Critically threatened or highly destructive harvesting

Consider these differentiating factors:
- Does harvesting DAMAGE or KILL the source organism? (tapping gum wounds trees → lower score)
- Is the material from a FALLEN/SHED part or must it be actively extracted?
- How FAST does the source regenerate? (annual seeds vs. slow-growing trees)
- Is the species THREATENED or overharvested in any region?
- Does PROCESSING require chemicals or energy? (lac processing needs heat → lower)
- Is the material CULTIVATED or purely wild-collected?

SECTION 3 — Durability Analysis:
How long do FINISHED PRODUCTS made from this material typically last?
- Perishable food products (honey, dried fruits) → lifespan is shelf life
- Non-food products (lac crafts, bamboo items) → lifespan is product durability
- Seeds used for oil extraction → lifespan refers to the oil's shelf life

Respond with valid JSON only:
{{
  "material_properties": {{
    "strength": "low|medium|high",
    "flexibility": "low|medium|high",
    "texture": "smooth|coarse|fibrous|granular|waxy|powdery|resinous",
    "water_resistance": "low|medium|high",
    "biodegradability": "low|medium|high",
    "workability": "easy|moderate|difficult"
  }},
  "sustainability_score": {{
    "overall": 0.0,
    "renewability": "low|medium|high",
    "biodegradability": "low|medium|high",
    "harvesting_impact": "low|medium|high",
    "reasoning": "1-2 sentence explanation of why this specific score"
  }},
  "durability_analysis": {{
    "lifespan_rating": "low|medium|high",
    "estimated_lifespan": "< 6 months|6-12 months|1-2 years|3-5 years|5+ years",
    "factors": ["factor1", "factor2"]
  }},
  "confidence": {{
    "material_properties": 0.0,
    "sustainability_score": 0.0,
    "durability_analysis": 0.0
  }}
}}

IMPORTANT RULES:
- Each material MUST get a DIFFERENT sustainability score. No two materials are equally sustainable.
- The overall score must reflect the specific harvesting method and ecological impact of THIS material.
- Do NOT default to 0.85 or any other generic value.
- Return ONLY valid JSON, no explanation outside the JSON.
"""



class GeminiExtractor:
    """Uses Google Gemini (google.genai SDK) to extract structured data from text."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=self.api_key)
        self._last_call_time = 0
        self.exhausted_models = set()

    def _rate_limit(self):
        """Enforce delay between LLM calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < config.LLM_DELAY_SECONDS:
            time.sleep(config.LLM_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    def extract(self, item: dict, source_text: str) -> Optional[dict]:
        """
        Extract structured fields from source text for a given MFP item.
        Returns extracted data dict with confidence scores, or None on failure.
        Tries multiple Gemini models if quota is exhausted on one.
        """
        if not source_text or len(source_text.strip()) < 50:
            print(f"  [!] Insufficient source text for '{item['name']}'")
            return None

        prompt = EXTRACTION_PROMPT.format(
            item_name=item["name"],
            category=item.get("category", "Unknown"),
            existing_scientific_name=item.get("scientific_name") or "Not available",
            msp=item.get("msp") or "N/A",
            existing_states=", ".join(item.get("states", [])) or "Not specified",
            source_text=source_text[:12000],  # Cap input size
        )

        # Try each model in the fallback list
        for model_name in config.GEMINI_MODELS:
            if model_name in self.exhausted_models:
                continue
                
            result = self._try_model(model_name, prompt, item["name"])
            if result is not None:
                return result

        print(f"  [FAIL] All models exhausted for '{item['name']}'")
        return None

    def _try_model(self, model_name: str, prompt: str, item_name: str) -> Optional[dict]:
        """Try extracting with a specific model, with retries."""
        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                self._rate_limit()

                # Build config — force JSON output for reliable parsing
                gen_config = types.GenerateContentConfig(
                    temperature=config.LLM_TEMPERATURE,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                )

                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=gen_config,
                )

                raw_text = response.text.strip() if response.text else ""
                if not raw_text:
                    print(f"  [!] {model_name}: empty response (attempt {attempt + 1})")
                    continue

                result = self._parse_response(raw_text, model_name)
                if result is not None:
                    print(f"  [OK] Extracted via {model_name}")
                    return result

            except Exception as e:
                error_str = str(e)

                # If quota exhausted, try next model immediately
                if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    # Parse retry delay from error if available
                    retry_match = re.search(r"retryDelay.*?(\d+)", error_str)
                    retry_secs = int(retry_match.group(1)) if retry_match else 10

                    # If daily quota is exhausted, skip to next model permanently
                    if "limit: 0" in error_str or "quota" in error_str.lower():
                        print(f"  [!] {model_name}: daily quota exhausted, marking as permanently exhausted...")
                        self.exhausted_models.add(model_name)
                        return None  # Signal to try next model

                    print(f"  [!] {model_name}: rate limited, waiting {retry_secs}s (attempt {attempt + 1})...")
                    time.sleep(retry_secs + 2)
                    continue

                # If model not found, skip immediately
                if "NOT_FOUND" in error_str or "404" in error_str:
                    print(f"  [!] {model_name}: model not available, trying next...")
                    return None

                print(f"  [!] {model_name} attempt {attempt + 1} failed for '{item_name}': {e}")
                if attempt < config.LLM_MAX_RETRIES - 1:
                    time.sleep(5 * (attempt + 1))

        return None


    def _parse_response(self, raw_text: str, model_name: str = "") -> Optional[dict]:
        """Parse LLM response text into a structured dict."""
        # Remove markdown code fences if present
        cleaned = raw_text
        if "```" in cleaned:
            # Extract content between code fences
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            if fence_match:
                cleaned = fence_match.group(1).strip()
            else:
                cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()

        # Try direct JSON parse first
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return self._validate_extraction(data)
        except json.JSONDecodeError:
            pass

        # Try to find the outermost JSON object using bracket matching
        start = cleaned.find("{")
        if start != -1:
            depth = 0
            end = start
            for i in range(start, len(cleaned)):
                if cleaned[i] == "{":
                    depth += 1
                elif cleaned[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            json_str = cleaned[start:end]
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    return self._validate_extraction(data)
            except json.JSONDecodeError:
                pass

        # Debug: show first and last 200 chars of what we got
        preview_head = cleaned[:200].replace("\n", " ")
        preview_tail = cleaned[-200:].replace("\n", " ")
        print(f"  [!] Could not parse LLM response as JSON (model: {model_name}, len={len(cleaned)})")
        print(f"      Head: {preview_head}")
        print(f"      Tail: ...{preview_tail}")
        return None

    def _validate_extraction(self, data: dict) -> dict:
        """Ensure extracted data has the expected structure."""
        # Ensure list fields are lists
        for field in ["states", "artisan_types", "current_products", "potential_products"]:
            if field in data and not isinstance(data[field], list):
                data[field] = [data[field]] if data[field] else []

        # Ensure string fields are strings or None
        for field in ["scientific_name", "description", "season", "shelf_life"]:
            if field in data and data[field] is not None:
                data[field] = str(data[field]).strip()
                if data[field].lower() in ("null", "none", "n/a", "not found", "not available", ""):
                    data[field] = None

        # Ensure confidence scores exist
        if "confidence" not in data:
            data["confidence"] = {f: 0.5 for f in config.TARGET_FIELDS if f != "image_url"}

        return data

    def extract_material_scores(self, item: dict) -> Optional[dict]:
        """Extract material properties, sustainability, and durability scores via LLM.

        Does NOT require source text — uses the LLM's own knowledge of the material.
        """
        prompt = MATERIAL_SCORES_PROMPT.format(
            item_name=item["name"],
            scientific_name=item.get("scientific_name") or "Unknown",
            category=item.get("category", "Unknown"),
            current_products=", ".join(item.get("current_products", [])[:8]) or "None listed",
            description=item.get("description") or "No description available",
        )

        for model_name in config.GEMINI_MODELS:
            if model_name in self.exhausted_models:
                continue
            result = self._try_model(model_name, prompt, item["name"])
            if result is not None:
                return self._validate_scores(result)

        print(f"  [FAIL] All models exhausted for scores of '{item['name']}'")
        return None

    def _validate_scores(self, data: dict) -> dict:
        """Validate the material scores structure."""
        # Ensure sub-dicts exist
        if "material_properties" not in data or not isinstance(data["material_properties"], dict):
            data["material_properties"] = {
                "strength": "medium", "flexibility": "medium", "texture": "coarse",
                "water_resistance": "low", "biodegradability": "high", "workability": "moderate",
            }
        if "sustainability_score" not in data or not isinstance(data["sustainability_score"], dict):
            data["sustainability_score"] = {
                "overall": 0.5, "renewability": "medium",
                "biodegradability": "medium", "harvesting_impact": "medium",
            }
        else:
            # Ensure overall is a float
            try:
                data["sustainability_score"]["overall"] = float(data["sustainability_score"].get("overall", 0.5))
            except (ValueError, TypeError):
                data["sustainability_score"]["overall"] = 0.5

        if "durability_analysis" not in data or not isinstance(data["durability_analysis"], dict):
            data["durability_analysis"] = {
                "lifespan_rating": "medium", "estimated_lifespan": "1-2 years", "factors": [],
            }
        if "factors" not in data["durability_analysis"] or not isinstance(data["durability_analysis"]["factors"], list):
            data["durability_analysis"]["factors"] = []

        return data


class GroqExtractor(GeminiExtractor):
    """Uses Groq to extract structured data from text. Inherits parsing logic from GeminiExtractor."""

    def __init__(self, api_key: Optional[str] = None):
        import groq
        self.api_key = api_key or config.GROQ_API_KEY
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Add it to your .env file. "
                "Get a free key at https://console.groq.com/keys"
            )
        self.client = groq.Groq(api_key=self.api_key)
        self._last_call_time = 0
        self.exhausted_models = set()

    def extract(self, item: dict, source_text: str) -> Optional[dict]:
        """Override: use GROQ_MODELS instead of GEMINI_MODELS."""
        if not source_text or len(source_text.strip()) < 50:
            print(f"  [!] Insufficient source text for '{item['name']}'")
            return None

        prompt = EXTRACTION_PROMPT.format(
            item_name=item["name"],
            category=item.get("category", "Unknown"),
            existing_scientific_name=item.get("scientific_name") or "Not available",
            msp=item.get("msp") or "N/A",
            existing_states=", ".join(item.get("states", [])) or "Not specified",
            source_text=source_text[:12000],
        )

        for model_name in config.GROQ_MODELS:
            if model_name in self.exhausted_models:
                continue

            result = self._try_model(model_name, prompt, item["name"])
            if result is not None:
                return result

        print(f"  [FAIL] All Groq models exhausted for '{item['name']}'")
        return None

    def _try_model(self, model_name: str, prompt: str, item_name: str) -> Optional[dict]:
        """Try extracting with a specific Groq model, with retries."""
        for attempt in range(config.LLM_MAX_RETRIES):
            try:
                self._rate_limit()

                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a precise data extraction AI. Always output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=config.LLM_TEMPERATURE,
                    max_tokens=8192,
                    response_format={"type": "json_object"},
                )

                raw_text = response.choices[0].message.content.strip()
                if not raw_text:
                    print(f"  [!] {model_name}: empty response (attempt {attempt + 1})")
                    continue

                result = self._parse_response(raw_text, model_name)
                if result is not None:
                    print(f"  [OK] Extracted via {model_name}")
                    return result

            except Exception as e:
                error_str = str(e)

                if "rate limit" in error_str.lower() or "429" in error_str:
                    # Groq rate limit errors usually tell you exactly how long to wait
                    retry_match = re.search(r"Please try again in ([\d\.]+)s", error_str)
                    retry_secs = float(retry_match.group(1)) + 1 if retry_match else 10

                    print(f"  [!] Groq ({model_name}) rate limited, waiting {retry_secs:.1f}s (attempt {attempt + 1})...")
                    time.sleep(retry_secs)
                    continue

                print(f"  [!] {model_name} attempt {attempt + 1} failed for '{item_name}': {e}")
                if attempt < config.LLM_MAX_RETRIES - 1:
                    time.sleep(5 * (attempt + 1))

        return None

    def extract_material_scores(self, item: dict) -> Optional[dict]:
        """Override: use GROQ_MODELS for material score extraction."""
        prompt = MATERIAL_SCORES_PROMPT.format(
            item_name=item["name"],
            scientific_name=item.get("scientific_name") or "Unknown",
            category=item.get("category", "Unknown"),
            current_products=", ".join(item.get("current_products", [])[:8]) or "None listed",
            description=item.get("description") or "No description available",
        )

        for model_name in config.GROQ_MODELS:
            if model_name in self.exhausted_models:
                continue
            result = self._try_model(model_name, prompt, item["name"])
            if result is not None:
                return self._validate_scores(result)

        print(f"  [FAIL] All Groq models exhausted for scores of '{item['name']}'")
        return None

