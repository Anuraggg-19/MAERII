# AI Context — MAERII Project & Knowledge Engine

> **Last updated:** 2026-06-14T15:30 IST  
> **Status:** MODULE 1 COMPLETE WITH DEEP ENRICHMENT LAYER — 87/87 MFP items enriched + optional deep analysis  

This document provides the complete context for the **MAERII** project. It is intended to get any new AI agent or IDE instantly up to speed on both the big-picture vision and the granular technical implementation of the codebase.

---

## 1. Project Vision: What is MAERII?

**MAERII** (Market Alignment Engine for Rural & Indigenous Innovation) is an AI-driven platform designed to empower tribal communities and artisans. It acts as an intelligent digital bridge connecting tribal producers (who have raw materials and traditional skills) with urban and export markets.

The platform solves systemic issues like information disparity, dependence on middlemen, and lack of value-addition by actively analyzing, recommending, grading, and pricing products.

### The Six Core AI Modules
The MAERII ecosystem is built on 6 interconnected modules:
1. **Tribal Raw Material Knowledge Engine:** Catalogs existing resources (bamboo, honey, lac), geographic clusters, and artisan skills. *(This is what we just built!)*
2. **Market Demand Intelligence Engine:** Analyzes real-time consumer trends.
3. **Product Recommendation AI:** Bridges #1 and #2 (e.g., "You have bamboo + weaving skills → make bamboo lamp shades").
4. **Product Design Enhancement AI:** Modernizes traditional designs for urban appeal.
5. **Quality Grading & Standardization:** Assesses products against market standards.
6. **AI Pricing Engine:** Recommends optimal pricing based on grade, cost, and market.

*(For a deeper dive into the entity relationships and use cases, refer to `maerii_deep_dive.md` and `candidate_screening_architecture.md`)*.

---

## 2. Current Implementation: The Knowledge Engine Scraper

We have successfully built the foundation for **Module #1 (Tribal Raw Material Knowledge Engine)**. 

We created an autonomous Python data pipeline that takes 87 raw Minor Forest Produce (MFP) items from a basic TRIFED government CSV and enriches them with high-fidelity, structured intelligence using web scraping and LLMs.

### Tech Stack
- **Language:** Python 3.11
- **LLM Provider:** Together AI (`meta-llama/Llama-3.3-70B-Instruct-Turbo`) via the `openai` SDK.
- **Fallbacks:** Groq and Google Gemini (`google-genai` SDK)
- **Search:** Serper.dev REST API (web search + image search)
- **Scraping:** `requests` + `beautifulsoup4`
- **Config:** `python-dotenv` loading from `.env.example`
- **CLI:** `argparse` with batch processing and crash recovery

### Architecture Pattern
```
seed_data.py (Parses CSV) → seed JSON
                               ↓
enrichment_pipeline.py (Orchestrator, Batching, Auditing)
                               ↓
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
        search_client    content_fetcher    llm_extractor
        (Serper API)     (BeautifulSoup)    (Together AI)
                               ↓
                  validator.py → enrichment_log.json
                               ↓
                  enriched_mfp_data.json (FINAL KNOWLEDGE GRAPH)
```

---

## 3. Final Output & Progress Stats

The pipeline successfully enriched all 87 items. The primary output is `data/enriched_mfp_data.json`.

**Final Validation Report Stats:**
- **Total items:** 87
- **Fully complete (9/9 fields):** 66 items
- **Average completeness:** 96%

**Field Coverage:**
- `scientific_name`: 85/87
- `description`: 87/87
- `season`: 77/87
- `shelf_life`: 72/87
- `states`: 85/87
- `artisan_types`: 87/87
- `current_products`: 87/87
- `potential_products`: 81/87
- `image_url`: 87/87

### Target JSON Schema — Base Enrichment
Every item in the enriched output includes base fields (Phase 1):
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
  "description": "Wild honey is a pure, raw...",
  "season": "March-June",
  "shelf_life": "12 months",
  "artisan_types": ["Honey Gatherer", "Honey Hunter"],
  "current_products": ["Raw Honey", "Liquid honey"],
  "potential_products": ["Royal Jelly", "Propolis", "Mead"],
  "image_url": "https://cdn.shopify.com/...",
  "confidence": {
    "description": 0.9,
    "shelf_life": 0.9,
    "...": 1.0
  }
}
```

---

## 3b. Deep Enrichment Layer (Phase 2 — Optional Additive)

A secondary, **optional** enrichment layer was added that provides **additive, graph-structured intelligence** without modifying base fields. This layer enables relationship inference and supply chain analysis.

### What Deep Enrichment Adds

The deep enrichment pipeline (`deep_pipeline.py`, `deep_extractor.py`, `deep_models.py`) adds the following to each item:

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

### Deep Enrichment Architecture

The deep layer consists of:

1. **Deep Extractor** (`deep_extractor.py`):
   - Fetches contextual web documents using Serper
   - Extracts availability bands and quantity records from documents
   - Identifies explicit district and cluster references
   - Falls back to heuristic extraction if LLM is unavailable
   - Supports multi-provider extraction (Groq, Gemini, Together AI)

2. **Deep Models** (`deep_models.py`):
   - Defines the `deep_enrichment` block schema
   - Implements conservative source prioritization (Official → Institutional → Research → Supporting)
   - Provides deterministic evidence and relationship ID generation
   - Handles additive merging without overwriting base fields
   - Implements validation reporting for integrity checks

3. **Deep Pipeline** (`deep_pipeline.py`):
   - Orchestrates preview and apply modes
   - Supports batch processing, resumption, and single-item enrichment
   - Maintains run manifests and validation reports
   - Enables non-destructive exploration before applying changes

4. **Rollback & Snapshots** (`rollback.py`):
   - Creates atomic backups before deep enrichment runs
   - Enables safe rollback to prior versions
   - Persists run manifests and preview outputs
   - Implements deterministic run IDs for reproducibility

### Deep Enrichment Output Files

When applied, the pipeline generates:
- **`data/enriched_mfp_data.json`**: Updated with `deep_enrichment` block for each item
- **`data/deep_enrichment_evidence.json`**: Evidence records keyed by evidence_id
  ```json
  {
    "evi_abc123": {
      "evidence_id": "evi_abc123",
      "mfp_id": 2,
      "attribute_group": "availability|geography",
      "attribute_name": "band|quantity_records|districts|clusters",
      "value": "high|[5000, tonnes]",
      "source_url": "https://...",
      "source_classification": "official|institutional|research|supporting",
      "snippet": "In Maharashtra, annual honey collection reaches 5000 tonnes",
      "confidence": 0.85,
      "extracted_at": "2026-06-14T10:30:00Z"
    }
  }
  ```
- **`data/material_relationships.json`**: Graph edges for supply chain relationships
  ```json
  {
    "edge_id": "edge_xyz789",
    "source_mfp_id": 2,
    "source_name": "Wild Honey",
    "edge_type": "collected_in|processed_in|made_from|has_artisan",
    "target_type": "region|cluster|product|skill",
    "target_value": "Maharashtra",
    "confidence": 0.75,
    "evidence_id": "evi_abc123",
    "created_at": "2026-06-14T10:30:00Z"
  }
  ```
- **`data/deep_enrichment_runs/{run_id}/`**: Run artifacts including manifest.json, preview.json, validation.json

### Running Deep Enrichment

```bash
# Preview mode (no changes)
python -m mfp_scraper.main --deep --preview

# Apply to single item
python -m mfp_scraper.main --deep --item "Wild Honey" --apply

# Apply to batch
python -m mfp_scraper.main --deep --apply --batch-size 10

# Resume from last checkpoint
python -m mfp_scraper.main --deep --apply --resume-from 25

# Validate current outputs
python -m mfp_scraper.main --deep --validate

# Rollback to prior run
python -m mfp_scraper.main --deep --rollback deep_20260614_105538
```

### Key Design Principles

1. **Additive Only:** Deep enrichment never modifies or removes base fields. All changes are isolated to the `deep_enrichment` block.
2. **Conservative Extraction:** Prefers official/institutional sources; avoids inference and speculation.
3. **Deterministic & Reproducible:** Evidence IDs and relationship edges are generated from content hashes, ensuring idempotent runs.
4. **Preview Before Apply:** Preview mode allows validation without persisting changes; atomic snapshots enable safe rollback.
5. **Evidence Trails:** Every extracted value carries source URL, snippet, and confidence score for traceability.
```

---

## 4. Key Engineering Decisions & Gotchas

If you are a new AI taking over this codebase, be aware of the following technical decisions we made during development:

1. **The Great LLM Migration (Together AI):** We initially used Gemini 2.5 Flash, then migrated to Groq, and finally settled on **Together AI** (`meta-llama/Llama-3.3-70B-Instruct-Turbo`). The free tiers for Gemini and Groq were too restrictive (daily limits and strict RPM token limits). Together AI provides a $5 credit pool which effortlessly processed the dataset without limits. The pipeline still natively supports Groq and Gemini as fallbacks if `TOGETHER_API_KEY` is missing.
2. **LLM Exhaustion Memory:** `llm_extractor.py` implements a `self.exhausted_models` `set()`. If an API returns a hard daily quota error, the model is permanently marked as exhausted for the lifecycle of the script, preventing infinite 5x retry loops.
3. **JSON Output Enforcement:** We use `response_format={"type": "json_object"}` for Together/Groq, and `response_mime_type="application/json"` for Gemini. We also implemented a custom fallback parser in `_parse_response` that strips markdown fences and matches bracket depth just in case the LLM hallucinates markdown.
4. **"All India" State Resolution:** `seed_data.py` translates TRIFED's vague CSV values like "All India" into an empty list. The LLM is then prompted to find the *actual* 3-8 specific states where tribal collection occurs, rather than just returning 28 states.
5. **Shelf Life formatting:** The LLM is explicitly instructed via `EXTRACTION_PROMPT` to output short durations (e.g., "18 months") instead of full sentences.
6. **Windows Compatibility:** All file paths use `pathlib.Path`. The codebase runs in a Windows environment (`powershell`).

---

## 5. File Map

### Core Engine (`mfp_scraper/`)
- `__init__.py`: Package init.
- `config.py`: All constants, API keys, paths, and provider model arrays (`TOGETHER_MODELS`, `GROQ_MODELS`, `GEMINI_MODELS`).
- `seed_data.py`: CSV loader (`load_csv`, `prepare_seed_data`).
- `search_client.py`: Serper.dev API wrapper for web and image search.
- `content_fetcher.py`: Web page fetching and HTML sanitization.
- `llm_extractor.py`: Multi-provider LLM extraction for base enrichment.
- `enrichment_pipeline.py`: Orchestrator for base enrichment with batching, auditing, resume.
- **`deep_extractor.py`**: Deep extraction from documents (availability, geography, relationships).
- **`deep_models.py`**: Data models, merging logic, and validation for deep layer.
- **`deep_pipeline.py`**: Deep enrichment orchestrator with preview/apply/rollback modes.
- **`rollback.py`**: Atomic file operations, run snapshots, and rollback helpers.
- `validator.py`: Data quality checks and completeness scoring.
- `main.py`: CLI entry point with commands for all modes.

### Project Root & Data
- `.env.example`: Where API keys are stored (`TOGETHER_API_KEY`, `SERPER_API_KEY`, etc.).
- `data/enriched_mfp_data.json`: The final 87-item knowledge base (optionally with `deep_enrichment` block).
- `data/enrichment_log.json`: Per-item validation report from base enrichment.
- `data/enrichment_sources.json`: Provenance tracking for base fields.
- **`data/deep_enrichment_evidence.json`**: Sidecar file for deep extraction evidence.
- **`data/material_relationships.json`**: Graph edges for relationships extracted in deep layer.
- `data/logs/` & `data/audits/`: Base enrichment run artifacts.
- **`data/deep_enrichment_runs/{run_id}/`**: Deep enrichment run artifacts (manifest, preview, validation).

---

## 6. Next Steps for MAERII

Now that Module 1 (The Knowledge Engine) has both foundational data and optional deep enrichment capabilities, the next phases are:

### Immediate Next Phase: Module 2 (Market Demand Intelligence)
Build a mirror pipeline to analyze market trends and consumer demand:
- Scrape e-commerce platforms (Amazon, Etsy, Flipkart, local marketplaces)
- Extract product attributes: price, rating, demand signals, trending categories
- Apply LLM to classify market-facing products into taxonomy
- Generate demand forecast and trend indices for each MFP
- Merge with Module 1 to generate product recommendations ("You have bamboo → market wants bamboo lighting")

See **`MARKET_INTELLIGENCE_HANDOFF.md`** for detailed specifications and JSON schema for integration.

### Future Phases
1. **Module 3 — Product Recommendation AI:** Bridge Module 1 and 2 using graph traversal.
2. **Module 4 — Product Design Enhancement:** Modernize traditional designs using generative AI.
3. **Module 5 — Quality Grading & Standardization:** Assess products against market standards.
4. **Module 6 — AI Pricing Engine:** Recommend optimal pricing based on grade, cost, and market.
5. **Database Integration:** Migrate JSON outputs to Neo4j or MongoDB for real-time graph queries.
6. **API Development:** Build FastAPI backend to serve knowledge graph to frontend.
