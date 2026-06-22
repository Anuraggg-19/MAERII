"""
Focused extractor for additive deep enrichment fields.
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

from . import config
from .deep_models import (
    classify_source,
    dedupe_strings,
    make_default_deep_enrichment,
    normalize_quantity_record,
    quantity_record_key,
    source_priority,
)


DEEP_EXTRACTION_PROMPT = """You are extracting additive deep-enrichment fields for Indian Minor Forest Produce.

Material:
- Name: {item_name}
- Scientific name: {scientific_name}
- Category: {category}
- Existing states: {states}

Task:
Extract ONLY these fields from the source dossier below:
1. availability.band: one of unknown, low, medium, high
2. availability.quantity_records: numeric collection / procurement / production / yield records only
3. geography.districts: Specific Indian districts where the material is found, collected, or produced
4. geography.clusters: Named livelihood, processing, tribal, or Van Dhan clusters

Rules:
- Do not infer exact numeric values if the source does not state them.
- Prefer official, institutional, biodiversity, and research sources.
- Do not include whole states in the districts list (e.g. do not put "Odisha", put the district like "Koraput").
- Extract any districts and clusters reasonably supported by the text.
- Return evidence entries for every non-empty field you populate.
- Use only source URLs that already appear in the dossier.

Respond with valid JSON only:
{{
  "availability": {{
    "band": "unknown|low|medium|high",
    "quantity_records": [
      {{
        "value": 0,
        "unit": "tonnes|kg|quintals",
        "year": 2024,
        "scope": "short phrase",
        "metric_type": "collection|procurement|production|yield"
      }}
    ]
  }},
  "geography": {{
    "districts": [],
    "clusters": []
  }},
  "confidence": {{
    "availability": 0.0,
    "geography": 0.0
  }},
  "evidence": [
    {{
      "attribute_group": "availability|geography",
      "attribute_name": "band|quantity_records|districts|clusters",
      "value": "short string or object summary",
      "source_url": "one dossier url",
      "snippet": "short supporting excerpt",
      "confidence": 0.0
    }}
  ]
}}

SOURCE DOSSIER:
{source_text}
"""

QUANTITY_PATTERN = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>metric tonnes?|mt|tonnes?|tons?|kgs?|kilograms?|quintals?|qtl)\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")

DISTRICT_PATTERNS = [
    re.compile(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2}) district\b"),
    re.compile(r"\bdistricts? of ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2})\b"),
    re.compile(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,2}) forest division\b"),
]

CLUSTER_PATTERNS = [
    re.compile(r"\b(Van Dhan(?: Vikas)? Kendra(?: cluster)?[^.,;\n]*)", re.IGNORECASE),
    re.compile(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,4} cluster)\b"),
]

QUANTITY_KEYWORDS = ("procurement", "production", "collection", "collected", "yield", "harvest")


class DeepExtractor:
    """Extract deep enrichment fields using heuristics with optional LLM refinement."""

    def __init__(self):
        self.provider = None
        self.client = None
        self._last_call_time = 0.0
        self.exhausted_models = set()
        self._initialize_provider()

    def describe_provider(self) -> str:
        """Return the active extraction provider."""
        return self.provider or "heuristic"

    def extract(self, item: dict, documents: list[dict]) -> dict:
        """
        Extract additive deep fields.
        Falls back to conservative heuristics if remote extraction is unavailable.
        """
        heuristic = self._extract_heuristics(item, documents)
        if not documents or not self.provider:
            return heuristic

        llm_result = self._extract_with_provider(item, documents)
        if not llm_result:
            return heuristic

        return self._merge_results(heuristic, llm_result)

    def _initialize_provider(self):
        """Choose an available remote provider if possible."""
        if config.GROQ_API_KEY:
            try:
                import groq

                self.client = groq.Groq(api_key=config.GROQ_API_KEY)
                self.provider = "groq"
                return
            except Exception:
                self.client = None

        if config.GEMINI_API_KEY:
            try:
                from google import genai

                self.client = genai.Client(api_key=config.GEMINI_API_KEY)
                self.provider = "gemini"
                return
            except Exception:
                self.client = None

    def _rate_limit(self):
        """Enforce delay between LLM calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < config.LLM_DELAY_SECONDS:
            time.sleep(config.LLM_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    def _extract_with_provider(self, item: dict, documents: list[dict]) -> Optional[dict]:
        """Use the active remote provider for focused extraction."""
        dossier = self._build_source_dossier(documents)
        if not dossier.strip():
            return None

        prompt = DEEP_EXTRACTION_PROMPT.format(
            item_name=item["name"],
            scientific_name=item.get("scientific_name") or "Unknown",
            category=item.get("category") or "Unknown",
            states=", ".join(item.get("states", [])) or "Not specified",
            source_text=dossier[:12000],
        )

        if self.provider == "groq":
            return self._extract_groq(prompt, documents)
        if self.provider == "gemini":
            return self._extract_gemini(prompt, documents)
        return None

    def _extract_groq(self, prompt: str, documents: list[dict]) -> Optional[dict]:
        """Run focused extraction via Groq."""
        for model_name in config.GROQ_MODELS:
            if model_name in self.exhausted_models:
                continue

            for attempt in range(config.LLM_MAX_RETRIES):
                try:
                    self._rate_limit()
                    response = self.client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a precise extraction assistant. Return valid JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=config.LLM_TEMPERATURE,
                        max_tokens=4096,
                        response_format={"type": "json_object"},
                    )
                    raw_text = response.choices[0].message.content.strip()
                    parsed = self._parse_response(raw_text, documents)
                    if parsed is not None:
                        return parsed
                except Exception as exc:
                    error_str = str(exc)
                    if "429" in error_str or "rate limit" in error_str.lower():
                        retry_match = re.search(r"Please try again in ([\d\.]+)s", error_str)
                        retry_secs = float(retry_match.group(1)) + 1 if retry_match else 10
                        print(f"      [!] Groq ({model_name}) rate limited, waiting {retry_secs:.1f}s...")
                        time.sleep(retry_secs)
                        continue
                    if attempt >= config.LLM_MAX_RETRIES - 1:
                        print(f"      [!] Groq ({model_name}) attempt {attempt + 1} failed: {exc}")
                        break
                    print(f"      [!] Groq ({model_name}) attempt {attempt + 1} failed, retrying...")
                    time.sleep(3 * (attempt + 1))
        return None

    def _extract_gemini(self, prompt: str, documents: list[dict]) -> Optional[dict]:
        """Run focused extraction via Gemini."""
        from google.genai import types

        for model_name in config.GEMINI_MODELS:
            if model_name in self.exhausted_models:
                continue

            for attempt in range(config.LLM_MAX_RETRIES):
                try:
                    self._rate_limit()
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=config.LLM_TEMPERATURE,
                            max_output_tokens=4096,
                            response_mime_type="application/json",
                        ),
                    )
                    raw_text = response.text.strip() if response.text else ""
                    parsed = self._parse_response(raw_text, documents)
                    if parsed is not None:
                        return parsed
                except Exception as exc:
                    error_str = str(exc)
                    if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                        if attempt >= config.LLM_MAX_RETRIES - 1:
                            print(f"      [!] Gemini ({model_name}) exhausted.")
                            self.exhausted_models.add(model_name)
                            break
                        print(f"      [!] Gemini ({model_name}) rate limited, waiting 8s...")
                        time.sleep(8)
                        continue
                    if attempt >= config.LLM_MAX_RETRIES - 1:
                        print(f"      [!] Gemini ({model_name}) attempt {attempt + 1} failed: {exc}")
                        break
                    print(f"      [!] Gemini ({model_name}) attempt {attempt + 1} failed, retrying...")
                    time.sleep(3 * (attempt + 1))
        return None

    def _parse_response(self, raw_text: str, documents: list[dict]) -> Optional[dict]:
        """Parse JSON returned by the remote model and normalize it."""
        cleaned = raw_text.strip()
        if not cleaned:
            return None

        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            cleaned = match.group(1).strip() if match else cleaned.replace("```", "").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1:
                return None
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return None

        if not isinstance(data, dict):
            return None

        return self._normalize_result(data, documents)

    def _build_source_dossier(self, documents: list[dict]) -> str:
        """Build a bounded dossier text for the model."""
        chunks = []
        remaining = 12000
        sorted_docs = sorted(documents, key=lambda doc: (source_priority(doc.get("url", "")), doc.get("title", "")))

        for index, doc in enumerate(sorted_docs[: config.DEEP_FETCH_MAX_DOCS], start=1):
            excerpt = (doc.get("text") or doc.get("snippet") or "").strip()
            if not excerpt:
                continue
            block = (
                f"[Doc {index}]\n"
                f"URL: {doc.get('url', '')}\n"
                f"Source Type: {doc.get('source_type', 'unknown')}\n"
                f"Title: {doc.get('title', '')}\n"
                f"Snippet: {doc.get('snippet', '')}\n"
                f"Excerpt: {excerpt[:1400]}\n"
            )
            if len(block) > remaining:
                block = block[:remaining]
            chunks.append(block)
            remaining -= len(block)
            if remaining <= 0:
                break

        return "\n\n".join(chunks)

    def _extract_heuristics(self, item: dict, documents: list[dict]) -> dict:
        """Conservative heuristic extraction from structured documents."""
        quantity_records, quantity_evidence = self._extract_quantity_records(documents)
        districts, district_evidence = self._extract_districts(item, documents)
        clusters, cluster_evidence = self._extract_clusters(documents)

        documents_with_signal = sum(
            1 for doc in documents if classify_source(doc.get("url", "")) in {"official", "institutional", "research"}
        )

        if quantity_records and len(quantity_records) >= 2:
            band = "high"
        elif quantity_records:
            band = "medium"
        elif documents_with_signal > 0:
            band = "low"
        else:
            band = "unknown"

        evidence = []
        if band != "unknown" and documents:
            primary = sorted(documents, key=lambda doc: source_priority(doc.get("url", "")))[0]
            evidence.append({
                "attribute_group": "availability",
                "attribute_name": "band",
                "value": band,
                "source_url": primary.get("url", ""),
                "snippet": (primary.get("snippet") or primary.get("text") or "")[:300],
                "confidence": 0.45 if quantity_records else 0.3,
            })

        evidence.extend(quantity_evidence)
        evidence.extend(district_evidence)
        evidence.extend(cluster_evidence)

        confidence = {
            "availability": 0.7 if quantity_records else (0.35 if band == "low" else 0.0),
            "geography": 0.65 if districts or clusters else 0.0,
        }

        result = {
            "availability": {
                "band": band,
                "quantity_records": quantity_records,
            },
            "geography": {
                "districts": districts,
                "clusters": clusters,
            },
            "confidence": confidence,
            "evidence": evidence,
            "status": "partial" if any([quantity_records, districts, clusters]) else "not_started",
        }
        return self._normalize_result(result, documents)

    def _extract_quantity_records(self, documents: list[dict]) -> tuple[list[dict], list[dict]]:
        """Extract conservative numeric quantity signals from strong sources."""
        records = []
        evidence = []
        seen = set()

        for doc in sorted(documents, key=lambda candidate: source_priority(candidate.get("url", ""))):
            if classify_source(doc.get("url", "")) not in {"official", "institutional", "research"}:
                continue

            haystack = "\n".join(filter(None, [doc.get("title"), doc.get("snippet"), doc.get("text")]))
            for match in QUANTITY_PATTERN.finditer(haystack):
                window_start = max(0, match.start() - 120)
                window_end = min(len(haystack), match.end() + 120)
                window = haystack[window_start:window_end]
                if not any(keyword in window.lower() for keyword in QUANTITY_KEYWORDS):
                    continue

                value_text = match.group("value").replace(",", "")
                try:
                    value = float(value_text)
                except ValueError:
                    continue

                unit = self._normalize_unit(match.group("unit"))
                year_match = YEAR_PATTERN.search(window)
                record = normalize_quantity_record({
                    "value": value,
                    "unit": unit,
                    "year": int(year_match.group(1)) if year_match else None,
                    "scope": (doc.get("title") or doc.get("snippet") or "source evidence")[:120],
                    "metric_type": self._detect_metric_type(window),
                })
                key = quantity_record_key(record)
                if key in seen:
                    continue

                seen.add(key)
                records.append(record)
                evidence.append({
                    "attribute_group": "availability",
                    "attribute_name": "quantity_records",
                    "value": {
                        key_name: record.get(key_name)
                        for key_name in ("value", "unit", "year", "scope", "metric_type")
                    },
                    "source_url": doc.get("url", ""),
                    "snippet": window.strip()[:300],
                    "confidence": 0.75 if classify_source(doc.get("url", "")) in {"official", "institutional"} else 0.55,
                })
                if len(records) >= 3:
                    break
            if len(records) >= 3:
                break

        return records, evidence

    def _extract_districts(self, item: dict, documents: list[dict]) -> tuple[list[str], list[dict]]:
        """Extract explicit district references conservatively."""
        known_states = {name.lower() for name in config.TRIBAL_STATES}
        districts = []
        evidence = []
        seen = set()

        for doc in documents:
            text = "\n".join(filter(None, [doc.get("title"), doc.get("snippet"), doc.get("text")]))
            for pattern in DISTRICT_PATTERNS:
                for match in pattern.finditer(text):
                    district = str(match.group(1)).strip(" ,.;:")
                    if not district or district.lower() in known_states:
                        continue
                    key = district.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    districts.append(district)
                    evidence.append({
                        "attribute_group": "geography",
                        "attribute_name": "districts",
                        "value": district,
                        "source_url": doc.get("url", ""),
                        "snippet": match.group(0)[:300],
                        "confidence": 0.7 if classify_source(doc.get("url", "")) in {"official", "institutional"} else 0.5,
                    })
                    if len(districts) >= 8:
                        return dedupe_strings(districts), evidence

        return dedupe_strings(districts), evidence

    def _extract_clusters(self, documents: list[dict]) -> tuple[list[str], list[dict]]:
        """Extract named clusters conservatively."""
        clusters = []
        evidence = []
        seen = set()

        for doc in documents:
            text = "\n".join(filter(None, [doc.get("title"), doc.get("snippet"), doc.get("text")]))
            for pattern in CLUSTER_PATTERNS:
                for match in pattern.finditer(text):
                    cluster = " ".join(match.group(1).strip(" ,.;:").split())
                    if len(cluster) < 6:
                        continue
                    key = cluster.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    clusters.append(cluster)
                    evidence.append({
                        "attribute_group": "geography",
                        "attribute_name": "clusters",
                        "value": cluster,
                        "source_url": doc.get("url", ""),
                        "snippet": match.group(0)[:300],
                        "confidence": 0.75 if classify_source(doc.get("url", "")) in {"official", "institutional"} else 0.55,
                    })
                    if len(clusters) >= 6:
                        return dedupe_strings(clusters), evidence

        return dedupe_strings(clusters), evidence

    def _merge_results(self, heuristic: dict, llm_result: dict) -> dict:
        """Merge remote extraction into the heuristic baseline conservatively."""
        merged = make_default_deep_enrichment()
        merged["availability"]["band"] = llm_result.get("availability", {}).get(
            "band",
            heuristic.get("availability", {}).get("band", "unknown"),
        )
        merged["availability"]["quantity_records"] = self._merge_quantity_results(
            heuristic.get("availability", {}).get("quantity_records", []),
            llm_result.get("availability", {}).get("quantity_records", []),
        )
        merged["geography"]["districts"] = dedupe_strings(
            list(heuristic.get("geography", {}).get("districts", []))
            + list(llm_result.get("geography", {}).get("districts", []))
        )
        merged["geography"]["clusters"] = dedupe_strings(
            list(heuristic.get("geography", {}).get("clusters", []))
            + list(llm_result.get("geography", {}).get("clusters", []))
        )
        merged["confidence"] = {
            "availability": round(max(
                heuristic.get("confidence", {}).get("availability", 0.0),
                llm_result.get("confidence", {}).get("availability", 0.0),
            ), 3),
            "geography": round(max(
                heuristic.get("confidence", {}).get("geography", 0.0),
                llm_result.get("confidence", {}).get("geography", 0.0),
            ), 3),
        }
        merged["evidence"] = self._merge_evidence_lists(
            heuristic.get("evidence", []),
            llm_result.get("evidence", []),
        )
        merged["status"] = "partial" if any([
            merged["availability"]["quantity_records"],
            merged["geography"]["districts"],
            merged["geography"]["clusters"],
        ]) else heuristic.get("status", "not_started")
        return self._normalize_result(merged, [])

    def _merge_quantity_results(self, baseline: list[dict], overlay: list[dict]) -> list[dict]:
        """Merge quantity results with deterministic dedupe."""
        merged = []
        seen = set()
        for record in list(baseline or []) + list(overlay or []):
            normalized = normalize_quantity_record(record)
            key = quantity_record_key(normalized)
            if normalized["value"] in (None, "") or key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return merged

    def _merge_evidence_lists(self, baseline: list[dict], overlay: list[dict]) -> list[dict]:
        """Merge evidence records without duplicates."""
        merged = []
        seen = set()
        for record in list(baseline or []) + list(overlay or []):
            key = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
            if key in seen:
                continue
            seen.add(key)
            merged.append(record)
        return merged

    def _normalize_result(self, data: dict, documents: list[dict]) -> dict:
        """Normalize result structures and drop invalid evidence references."""
        availability = data.get("availability", {}) if isinstance(data.get("availability"), dict) else {}
        geography = data.get("geography", {}) if isinstance(data.get("geography"), dict) else {}
        confidence = data.get("confidence", {}) if isinstance(data.get("confidence"), dict) else {}
        evidence = data.get("evidence", []) if isinstance(data.get("evidence"), list) else []

        valid_urls = {doc.get("url", "") for doc in documents if doc.get("url")} if documents else set()

        quantity_records = []
        seen_quantity = set()
        for record in availability.get("quantity_records", []):
            normalized = normalize_quantity_record(record)
            key = quantity_record_key(normalized)
            if normalized["value"] in (None, "") or key in seen_quantity:
                continue
            seen_quantity.add(key)
            quantity_records.append(normalized)

        districts = dedupe_strings(geography.get("districts", []))
        clusters = dedupe_strings(geography.get("clusters", []))

        normalized_evidence = []
        for record in evidence:
            if not isinstance(record, dict):
                continue
            source_url = str(record.get("source_url", "")).strip()
            if valid_urls and source_url and source_url not in valid_urls:
                continue
            attribute_group = str(record.get("attribute_group", "")).strip()
            attribute_name = str(record.get("attribute_name", "")).strip()
            if attribute_group not in {"availability", "geography"}:
                continue
            if attribute_name not in {"band", "quantity_records", "districts", "clusters"}:
                continue
            normalized_evidence.append({
                "attribute_group": attribute_group,
                "attribute_name": attribute_name,
                "value": record.get("value"),
                "source_url": source_url,
                "snippet": str(record.get("snippet", "")).strip()[:300],
                "confidence": float(record.get("confidence", 0.0) or 0.0),
            })

        band = str(availability.get("band", "unknown")).strip().lower()
        if band not in {"unknown", "low", "medium", "high"}:
            band = "unknown"

        return {
            "availability": {
                "band": band,
                "quantity_records": quantity_records,
            },
            "geography": {
                "districts": districts,
                "clusters": clusters,
            },
            "confidence": {
                "availability": round(float(confidence.get("availability", 0.0) or 0.0), 3),
                "geography": round(float(confidence.get("geography", 0.0) or 0.0), 3),
            },
            "evidence": normalized_evidence,
            "status": data.get("status", "partial" if any([quantity_records, districts, clusters]) else "not_started"),
        }

    def _detect_metric_type(self, text: str) -> str:
        """Infer the metric type from nearby quantity context."""
        lowered = text.lower()
        for keyword in ("procurement", "production", "collection", "yield"):
            if keyword in lowered:
                return keyword
        return "collection"

    def _normalize_unit(self, unit: str) -> str:
        """Normalize quantity units into a compact shape."""
        lowered = unit.lower().strip()
        if lowered in {"mt", "metric tonne", "metric tonnes", "tonne", "tonnes", "ton", "tons"}:
            return "tonnes"
        if lowered in {"kg", "kgs", "kilogram", "kilograms"}:
            return "kg"
        if lowered in {"quintal", "quintals", "qtl"}:
            return "quintals"
        return lowered
