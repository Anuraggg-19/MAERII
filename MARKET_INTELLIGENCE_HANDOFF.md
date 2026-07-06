# Market Intelligence AI Module — Handoff & Integration Guide

> **Prepared for:** Market Demand Intelligence Engine Team (Module 2)  
> **Date:** 2026-06-14  
> **Status:** Ready for development  

This document provides **complete context** for building **Module 2 (Market Demand Intelligence)** of the MAERII platform. It covers the current state of Module 1 (Tribal Raw Material Knowledge Engine), the exact JSON schemas you'll work with, architecture patterns, and the specifications for the Market Intelligence module.

---

## 1. MAERII Ecosystem Overview

**MAERII** (Market Alignment Engine for Rural & Indigenous Innovation) is a 6-module platform connecting tribal producers with markets.

### Module Stack (Current & Future)
```
1. Tribal Raw Material Knowledge Engine   [✅ COMPLETE with Deep Enrichment]
   ↓
2. Market Demand Intelligence Engine      [🚀 THIS MODULE — You build this]
   ↓
3. Product Recommendation AI              [Future]
   ↓ (Cross-references 1 & 2)
4. Product Design Enhancement AI          [Future]
5. Quality Grading & Standardization      [Future]
6. AI Pricing Engine                      [Future]
```

Your module's job: **Analyze market trends and consumer demand to feed product recommendations.**

---

## 2. Module 1 Output: The Enriched MFP Dataset

### 2.1 Dataset Overview

**Location:** `data/enriched_mfp_data.json`  
**Items:** 87 Minor Forest Produce (MFP) materials  
**Format:** JSON array of MFP objects

**Sample item (simplified):**
```json
{
  "mfp_id": 2,
  "name": "Wild Honey",
  "scientific_name": "Apis mellifera",
  "category": "Forest Produce",
  "msp": 225.0,
  "unit": "kg",
  "applicability_raw": "All India",
  "states": ["Maharashtra", "Odisha", "Tamil Nadu", "Kerala"],
  "description": "Wild honey is a pure, raw natural sweetener with antimicrobial and medicinal properties...",
  "season": "March-June",
  "shelf_life": "12 months",
  "artisan_types": ["Honey Gatherer", "Honey Hunter"],
  "current_products": ["Raw Honey", "Liquid honey"],
  "potential_products": ["Royal Jelly", "Propolis", "Mead", "Honey Cosmetics"],
  "image_url": "https://cdn.shopify.com/s/files/1/...",
  "confidence": {
    "scientific_name": 1.0,
    "description": 0.9,
    "season": 0.8,
    "shelf_life": 0.7,
    "states": 0.85,
    "artisan_types": 0.9,
    "current_products": 0.9,
    "potential_products": 0.85,
    "image_url": 0.95
  }
}
```

### 2.2 Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `mfp_id` | Integer | Unique identifier | `2` |
| `name` | String | Common name | `"Wild Honey"` |
| `scientific_name` | String | Scientific name | `"Apis mellifera"` |
| `category` | String | MFP category (Forest Produce, Medicinal, etc.) | `"Forest Produce"` |
| `msp` | Float | Minimum Support Price (₹/kg) | `225.0` |
| `unit` | String | Price unit | `"kg"` |
| `states` | Array[String] | Indian states with tribal collection | `["Maharashtra", "Odisha"]` |
| `description` | String | Product description (LLM-generated) | `"Pure raw natural sweetener..."` |
| `season` | String | Collection/harvest season | `"March-June"` |
| `shelf_life` | String | Storage duration | `"12 months"` |
| `artisan_types` | Array[String] | Skill types involved | `["Honey Gatherer"]` |
| `current_products` | Array[String] | Existing products in market | `["Raw Honey", "Liquid honey"]` |
| `potential_products` | Array[String] | Value-added possibilities | `["Royal Jelly", "Mead"]` |
| `image_url` | String | Representative image | `"https://..."` |
| `confidence` | Object | Confidence scores per field | `{"name": 1.0, ...}` |

---

## 3. Optional Deep Enrichment Layer

Module 1 also includes an **optional deep enrichment layer** that adds supply chain intelligence. This is NOT required for your initial development but provides valuable context for relationship mapping later.

### 3.1 Deep Enrichment Structure

If present, each item contains:
```json
{
  "mfp_id": 2,
  "deep_enrichment": {
    "version": "v1",
    "status": "partial|complete|not_started",
    "availability": {
      "band": "unknown|low|medium|high",
      "quantity_records": [
        {
          "value": 5000,
          "unit": "tonnes",
          "year": 2024,
          "scope": "Maharashtra annual collection",
          "metric_type": "collection|procurement|production|yield"
        }
      ]
    },
    "geography": {
      "districts": ["Yavatmal", "Amravati"],
      "clusters": ["Van Dhan Vikas Kendra - Yavatmal"]
    },
    "relationship_summary": {
      "related_regions": ["Maharashtra", "Karnataka"],
      "related_products": ["Honey Cosmetics", "Mead"],
      "related_skills": ["Beekeeping", "Processing"],
      "related_material_groups": ["Forest Produce"]
    },
    "confidence": {
      "availability": 0.8,
      "geography": 0.7,
      "relationships": 0.6
    },
    "evidence_refs": ["evi_abc123", "evi_def456"],
    "last_updated_at": "2026-06-14T10:30:00Z"
  }
}
```

**For Module 2 development:** You can safely ignore `deep_enrichment` initially. It exists for supply chain analysis in later phases.

---

## 4. Architecture Patterns from Module 1 (For Reference)

Your Module 2 implementation should follow similar patterns for consistency:

### 4.1 Pipeline Design Pattern
```
┌─────────────────────────────────┐
│  Data Source (e.commerce APIs)  │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│  Search/Fetch Layer             │
│  (Async + Rate Limiting)         │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│  Extraction Layer               │
│  (LLM-based Classification)     │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│  Validation + Confidence        │
└────────────┬────────────────────┘
             ↓
┌─────────────────────────────────┐
│  Atomic Write + Audit Logs      │
└─────────────────────────────────┘
```

### 4.2 Key Module 1 Design Decisions to Replicate

1. **Atomic JSON Writes:** Use temp files + replace pattern (see [rollback.py](mfp_scraper/rollback.py)) for crash safety
2. **Multi-Provider LLM Fallback:** Support Together AI, Groq, Gemini. Gracefully handle quota exhaustion.
3. **Deterministic Hashing:** Generate IDs from content hashes for idempotency (see `stable_hash()` in [deep_models.py](mfp_scraper/deep_models.py))
4. **Confidence Scores:** Attach confidence per field extracted
5. **Evidence Trails:** Keep source URLs and snippets for every extraction
6. **Audit Logs:** Record metadata about each enrichment run (start time, provider, model, errors)
7. **Batch Processing + Resume:** Support `--resume-from` index for interrupted runs
8. **Preview + Apply:** Separate preview mode (no writes) from apply mode (write to disk)

---

## 5. Your Task: Module 2 (Market Demand Intelligence)

### 5.1 High-Level Objectives

Your module should:

1. **Scrape market data** from e-commerce platforms for product trends
2. **Extract market attributes** (price, rating, demand, trends, category)
3. **Apply LLM classification** to map products to a standardized taxonomy
4. **Generate demand signals** for each MFP category
5. **Output structured JSON** that bridges with Module 1 for recommendations

### 5.2 Input & Output

**Input:**
- The 87 MFP items from Module 1 (read from `data/enriched_mfp_data.json`)
- E-commerce search queries derived from MFP `current_products` and `potential_products`

**Output:**
- **`data/market_demand_data.json`**: Market trend intelligence keyed by MFP ID
- **`data/market_products.json`**: Mapped market products with demand scores
- **`data/market_analysis_log.json`**: Per-item analysis report (similar to `enrichment_log.json`)
- **`data/market_sources.json`**: Provenance tracking (which e-commerce URLs, which items)

### 5.3 Recommended Data Schema for Market Demand

```json
{
  "mfp_id": 2,
  "name": "Wild Honey",
  "market_analysis": {
    "version": "v1",
    "status": "complete|partial|not_started",
    "last_analyzed_at": "2026-06-14T10:30:00Z",
    "search_queries": {
      "primary": "Wild Honey",
      "variations": ["Raw Honey", "Organic Honey", "Forest Honey"]
    },
    "market_products": [
      {
        "product_id": "mkp_1",
        "title": "100% Pure Raw Wild Forest Honey - 500g",
        "url": "https://amazon.in/...",
        "price": 599.0,
        "currency": "INR",
        "rating": 4.5,
        "review_count": 1250,
        "seller_type": "brand|retail|marketplace",
        "category": "Food & Groceries > Honey",
        "demand_indicators": {
          "reviews_per_month": 45,
          "stock_status": "in_stock|low_stock|out_of_stock",
          "bestseller_rank": 15,
          "price_trend": "stable|increasing|decreasing",
          "trend_direction": "rising|stable|declining"
        },
        "attributes": [
          {"name": "organic", "value": true},
          {"name": "raw", "value": true},
          {"name": "packaging", "value": "500g"}
        ],
        "source": "amazon.in",
        "extracted_at": "2026-06-14T10:30:00Z",
        "confidence": 0.85
      }
    ],
    "market_summary": {
      "total_products_found": 342,
      "avg_price": 549.5,
      "price_range": {"min": 199, "max": 2999},
      "avg_rating": 4.2,
      "total_reviews": 45000,
      "demand_score": 0.87,
      "trend": "rising",
      "top_attributes": ["organic", "raw", "forest", "100% pure"]
    },
    "competitor_analysis": {
      "top_brands": ["Dabur", "Patanjali", "Tribal Harvest"],
      "market_gaps": ["Sustainable packaging", "Fair trade certification"],
      "price_positioning": "mid-range"
    },
    "confidence": {
      "product_count": 0.9,
      "pricing": 0.88,
      "demand_score": 0.82,
      "trend": 0.75
    }
  }
}
```

### 5.4 Mapping Market Products to MFP Categories

Your module must classify market products to MFP-derived categories using LLM. For each market product:

1. Extract title, description, category, price, attributes
2. Send to LLM with prompt like:
   ```
   Classify this product into one or more MFP categories:
   
   Title: "100% Pure Raw Wild Forest Honey"
   Price: 599 INR
   Existing MFP categories: [Honey, Lac, Bamboo, ...]
   
   Return JSON with:
   - matched_mfp_ids: [2]
   - match_confidence: 0.9
   - reasoning: "Pure raw forest honey matches 'Wild Honey' (mfp_id=2)"
   ```
3. Store result with source URL and confidence
4. Aggregate by MFP for demand signals

---

## 6. Technical Specifications

### 6.1 Recommended Tech Stack

Follow Module 1's stack for consistency:

| Component | Choice |
|-----------|--------|
| Language | Python 3.11 |
| LLM Provider | Together AI (`meta-llama/Llama-3.3-70B-Instruct-Turbo`) |
| LLM Fallbacks | Groq, Google Gemini |
| Search/Scraping | Serper API (or direct e-commerce APIs: Amazon, Etsy) |
| Scraping | `requests` + `beautifulsoup4` |
| Config | `python-dotenv` + `.env.example` |
| CLI | `argparse` with batch processing |
| File I/O | `pathlib.Path` + atomic writes |

### 6.2 File Structure

Create a parallel structure for Module 2:

```
mfp_scraper/
  market_scraper/          ← NEW: Market Intelligence submodule
    __init__.py
    config_market.py       ← Market-specific constants
    ecommerce_client.py    ← Scraper for Amazon, Etsy, etc.
    market_extractor.py    ← LLM-based product classification
    market_pipeline.py     ← Orchestrator (similar to deep_pipeline.py)
    market_models.py       ← Data models + validation
    market_validator.py    ← Completeness + quality checks
    main_market.py         ← CLI entry point
data/
  market_demand_data.json  ← Primary output (87 items with market analysis)
  market_products.json     ← Sidecar: All scraped market products
  market_analysis_log.json ← Per-item validation report
  market_sources.json      ← Provenance tracking
  market_runs/             ← Run artifacts (manifests, previews)
```

### 6.3 CLI Interface (Proposed)

```bash
# Test with single MFP
python -m mfp_scraper.market_scraper --item "Wild Honey" --preview

# Scrape all MFPs (preview mode)
python -m mfp_scraper.market_scraper --all --preview

# Apply to all (write output)
python -m mfp_scraper.market_scraper --all --apply

# Resume from checkpoint
python -m mfp_scraper.market_scraper --all --apply --resume-from 25

# Validate current outputs
python -m mfp_scraper.market_scraper --validate

# Export for Module 3 consumption
python -m mfp_scraper.market_scraper --export --format csv
```

### 6.4 Rate Limiting & API Management

Follow Module 1 patterns:

```python
# config_market.py
ECOMMERCE_DELAY_SECONDS = 2.0       # Delay between scrapes
LLM_DELAY_SECONDS = 4.0              # Delay between LLM calls
MAX_PRODUCTS_PER_MFP = 50            # Cap on products to fetch per item

# In market_pipeline.py
def _rate_limit(self):
    elapsed = time.time() - self._last_call_time
    if elapsed < config_market.ECOMMERCE_DELAY_SECONDS:
        time.sleep(config_market.ECOMMERCE_DELAY_SECONDS - elapsed)
    self._last_call_time = time.time()
```

### 6.5 LLM Prompt Template (for Classification)

```python
MARKET_CLASSIFICATION_PROMPT = """
You are classifying e-commerce products into Indian Minor Forest Produce (MFP) categories.

Available MFP Categories:
- MFP ID 2: Wild Honey (honey, honeycomb)
- MFP ID 5: Bamboo (crafts, furniture, textiles)
- MFP ID 12: Lac (resins, dyes, crafts)
- ... (87 total)

Task: Classify the product below into matching MFP categories by ID.

Product Title: {product_title}
Product Description: {product_description}
Category: {product_category}
Price: {product_price} INR
Attributes: {product_attributes}

Respond with valid JSON only:
{{
  "matched_mfp_ids": [2, 15],
  "match_confidence": 0.87,
  "matching_attributes": ["raw", "forest", "pure"],
  "reasoning": "Product is raw forest honey matching MFP #2"
}}
"""
```

### 6.6 Output Validation Rules

Similar to Module 1 (`validator.py`), implement:

```python
def validate_market_outputs(market_data: list[dict], market_products: list[dict]) -> dict:
    """Validate market demand outputs."""
    return {
        "total_mfps": len(market_data),
        "mfps_with_market_analysis": sum(1 for m in market_data if m.get("market_analysis")),
        "total_products_scraped": len(market_products),
        "avg_products_per_mfp": len(market_products) / len(market_data),
        "coverage": {
            "demand_scores": sum(1 for m in market_data if m.get("market_analysis", {}).get("market_summary", {}).get("demand_score")),
            "pricing_data": sum(1 for m in market_data if m.get("market_analysis", {}).get("market_summary", {}).get("avg_price")),
            "competitor_analysis": sum(1 for m in market_data if m.get("market_analysis", {}).get("competitor_analysis")),
        }
    }
```

---

## 7. Integration Checkpoint: Bridging Modules 1 & 2

### 7.1 For Module 3 (Product Recommendation)

Once Module 2 is complete, Module 3 will use both outputs:

```python
def recommend_products(mfp_id: int) -> list[dict]:
    """
    Given an MFP, recommend market products.
    Bridges Module 1 and Module 2.
    """
    # Load from Module 1
    mfp = load_mfp(mfp_id)  # from enriched_mfp_data.json
    
    # Load from Module 2
    market_analysis = load_market_analysis(mfp_id)  # from market_demand_data.json
    
    # Score & rank
    candidates = market_analysis["market_products"]
    scored = [
        {
            "product": c,
            "score": calculate_fit(mfp, c),
            "reason": "High demand + matches current_products"
        }
        for c in candidates
    ]
    
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:10]
```

### 7.2 Dependency: Module 2 → Module 1 (Read-Only)

Your module:
- **READS:** `data/enriched_mfp_data.json` (to get MFP names, categories, current/potential products)
- **WRITES:** `data/market_demand_data.json`, `data/market_products.json`, etc. (does NOT modify Module 1 data)

---

## 8. Known Gotchas & Best Practices

### 8.1 Things Module 1 Learned

1. **LLM Quota Management:** Together AI free tier provides $5. Groq has daily limits. Always track exhausted models and skip them.

2. **JSON Output Enforcement:** Force models to return JSON:
   ```python
   response = client.chat.completions.create(
       ...,
       response_format={"type": "json_object"},  # For Groq/Together
   )
   # For Gemini: response_mime_type="application/json"
   ```

3. **Atomic File Writes:** Never write directly. Use temp file + replace:
   ```python
   def atomic_write_json(path: Path, payload):
       temp_path = path.with_suffix(".tmp")
       with open(temp_path, "w") as f:
           json.dump(payload, f)
       temp_path.replace(path)  # Atomic on most filesystems
   ```

4. **Deterministic IDs:** For reproducibility and deduping, use content hashes:
   ```python
   product_id = "mkp_" + stable_hash(url, title, price)
   ```

5. **Rate Limiting:** Respect API limits or you'll get blocked mid-run. Build in delays:
   ```python
   time.sleep(config_market.ECOMMERCE_DELAY_SECONDS)
   ```

6. **Windows Compatibility:** Use `pathlib.Path` everywhere, not string paths.

### 8.2 Data Quality Checks

Before outputting, validate:
- No null values in required fields
- URLs are well-formed
- Prices are non-negative
- Confidence scores in [0, 1]
- IDs are deterministic (re-runs produce same IDs)
- Evidence URLs are accessible (optional, but good to check)

### 8.3 Testing Strategy

```bash
# Test single MFP (quick)
python -m mfp_scraper.market_scraper --item "Wild Honey" --preview --limit 5

# Dry-run on 10 MFPs
python -m mfp_scraper.market_scraper --all --preview --batch-size 10

# Full run on all 87
python -m mfp_scraper.market_scraper --all --apply

# Validate outputs
python -m mfp_scraper.market_scraper --validate
```

---

## 9. Example Workflow

### 9.1 Input: Single MFP from Module 1
```json
{
  "mfp_id": 2,
  "name": "Wild Honey",
  "current_products": ["Raw Honey", "Liquid honey"],
  "potential_products": ["Royal Jelly", "Propolis", "Mead", "Honey Cosmetics"],
  "states": ["Maharashtra", "Odisha", "Tamil Nadu"]
}
```

### 9.2 Your Module Processes This:

1. **Generate search queries** from `current_products` + `potential_products`:
   - "Raw Honey India"
   - "Liquid Honey India"
   - "Honey Cosmetics India"
   - "Organic Honey India"

2. **Scrape e-commerce APIs** (Amazon, Etsy, Flipkart):
   - Collect ~50 products per query
   - Extract: title, price, rating, category, attributes, URL

3. **Classify products** via LLM:
   ```json
   {
     "title": "100% Pure Raw Wild Forest Honey",
     "matched_mfp_ids": [2],
     "confidence": 0.92
   }
   ```

4. **Aggregate & analyze**:
   - Average price: ₹549.50
   - Average rating: 4.2 stars
   - Demand score: 0.87 (rising trend)
   - Top 3 brands: Dabur, Patanjali, Tribal Harvest

5. **Output to disk**:
   ```json
   {
     "mfp_id": 2,
     "name": "Wild Honey",
     "market_analysis": {
       "market_products": [...],
       "market_summary": {...},
       "confidence": {...}
     }
   }
   ```

---

## 10. Success Criteria

Your module is **complete & ready for handoff** when:

- [ ] All 87 MFPs have market analysis
- [ ] Average data quality score ≥ 85%
- [ ] Confidence scores attached to all extractions
- [ ] E-commerce sources tracked (URLs stored)
- [ ] Deterministic product IDs (re-runs produce same output)
- [ ] LLM classification achieves ≥ 80% accuracy (spot-check 10 items)
- [ ] `--validate` command reports 0 errors
- [ ] `data/market_demand_data.json` integrates cleanly with Module 1
- [ ] CLI supports preview, apply, resume, validate, export modes
- [ ] Audit logs capture all runs with timestamps and provider info
- [ ] README.md + docstrings document usage

---

## 11. Contact & Support

- **Module 1 Code Location:** `mfp_scraper/`
- **Reference for Best Practices:** [deep_pipeline.py](mfp_scraper/deep_pipeline.py), [deep_models.py](mfp_scraper/deep_models.py)
- **Config Template:** [config.py](mfp_scraper/config.py)
- **Atomic I/O Reference:** [rollback.py](mfp_scraper/rollback.py)

---

## Appendix A: Full Field Reference for Module 1 Items

```python
# All 87 items follow this schema
item = {
    "mfp_id": int,                         # 1–87
    "name": str,                           # Common name
    "scientific_name": str,                # Latin binomial
    "category": str,                       # Forest Produce, Medicinal, etc.
    "msp": float,                          # Minimum support price (₹)
    "unit": str,                           # "kg", "piece", "litre", etc.
    "msp_notes": str or None,              # Additional context
    "applicability_raw": str,              # Raw from CSV: "All India", etc.
    "states": [str],                       # Refined: specific states
    "description": str,                    # LLM-generated (0.7–0.9 confidence)
    "season": str,                         # Harvest season (0.8–1.0 confidence)
    "shelf_life": str,                     # Storage duration (0.7–0.9 confidence)
    "artisan_types": [str],                # Skills (0.9 confidence)
    "current_products": [str],             # Existing products (0.9 confidence)
    "potential_products": [str],           # Value-added options (0.8–0.9 confidence)
    "image_url": str,                      # Representative image (0.95 confidence)
    "confidence": {                        # Per-field confidence (0–1)
        "field_name": float,
        ...
    }
}
```

---

**End of Handoff Document**

Good luck with Module 2! Feel free to reference Module 1 code patterns and reach out with integration questions.
