# MFP Knowledge Engine — Data Enrichment Scraper

An AI-powered pipeline that enriches the 87 TRIFED Minor Forest Produce (MFP) items with structured data by searching the web and extracting attributes via LLM.

## What It Does

Takes a base list of 87 MFP items (name, MSP, category) and enriches each with:
- Scientific name
- Description
- Harvesting season
- Shelf life
- States where tribal communities collect it
- Artisan/gatherer types
- Current products made from it
- Potential value-added products
- Image URL

## Architecture

```
Seed Data (CSV) → Web Search (Serper API) → Content Fetch → LLM Extraction (Gemini) → Validated JSON
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root:
   ```
   SERPER_API_KEY=your_serper_key_here
   GEMINI_API_KEY=your_gemini_key_here
   LLM_PROVIDER_ORDER=gemini,groq
   GEMINI_MODELS=gemini-3.6-flash
   # Optional Groq fallback; configure a model as well as the key.
   GROQ_MODELS=
   ```

3. Place your MFP CSV file as `MFP_List_87_Items_Split.csv` in the project root.

## Usage

### Optional: fully open-source market experiment

This is a separate evaluation path and never changes the normal Serper/Gemini
market workflow, categories, scores, recommendations, or saved production data.
It uses self-hosted SearXNG for open-web URL discovery, Crawl4AI for browser
page extraction, and a local Ollama model for classification.

1. Install the project requirements and Crawl4AI browser runtime:

   ```bash
   pip install -r requirements.txt
   crawl4ai-setup
   ```

2. Start a self-hosted SearXNG instance with JSON responses enabled at
   `http://localhost:8080`, and start Ollama with a downloaded model:

   ```bash
   ollama run qwen3:8b
   ```

3. Add the following to `.env` and restart the server:

   ```env
   OPEN_SOURCE_MARKET_MODE=true
   SEARXNG_BASE_URL=http://localhost:8080
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen3:8b
   ```

4. In a material's Market tab, first run **Fetch Live Market Data** if you
   want the browser to show the production baseline, then click
   **Compare Open-Source Pipeline**. Reports are saved separately under
   `data/open_source_comparisons/`.

SearXNG provides open-web results, not Google Shopping results. The experiment
therefore compares end-to-end discovery/extraction/classification behaviour,
not identical search indexes.

### Optional: compare Serper and Scrapingdog Shopping results

Set `SCRAPINGDOG_API_KEY` and `MARKET_COMPARISON_MODE=true` in `.env`, then call
`POST /api/materials/{mfp_id}/market/compare`. This isolated endpoint runs the
same raw product queries against both Shopping APIs, then uses Scrapingdog's
Google Immersive Product and webpage-scraping APIs for a bounded number of
retailer destination pages. It stores timestamped results under
`data/market_comparisons/` and does not alter normal market analysis, scores,
LLM classification, or recommendations. Set
`MARKET_COMPARISON_STORE_RAW=true` only for short-lived debugging; stored data
is sanitized to remove API-key parameters.

Comparison results also have a local, deterministic relevance label by default
(`MARKET_COMPARISON_RELEVANCE_FILTER=true`). It uses each MFP's existing name,
scientific name, and known product forms; it does not call an LLM or remove raw
provider listings. The comparison UI defaults to relevant products and exposes
Needs review, Rejected, and All raw views. Only confirmed ambiguity profiles,
such as the `Lac`/`lace` collision, have targeted exclusion terms or safer
query overrides. Both providers always receive the same final query.

```bash
# Step 1: Parse CSV into structured seed JSON
python -m mfp_scraper.main --prepare

# Step 2: Test with a single item
python -m mfp_scraper.main --item "Wild Honey"

# Step 3: Enrich all 87 items
python -m mfp_scraper.main --all

# Resume if interrupted
python -m mfp_scraper.main --all --resume 25

# Validate enriched data
python -m mfp_scraper.main --validate

# Export to CSV
python -m mfp_scraper.main --export csv
```

## Module 2: Market Demand Intelligence

Extracts market signals and classifications from e-commerce for enriched MFPs.
*Note: Requires `SERPER_API_KEY` for Google Shopping search.*

```bash
# Test on a single item (Preview mode)
python -m mfp_scraper.market_scraper --item "Wild Honey" --preview

# Run batch for first 5 items (Preview mode)
python -m mfp_scraper.market_scraper --all --preview --limit 5

# Full apply run on all items
python -m mfp_scraper.market_scraper --all --apply

# Validate outputs
python -m mfp_scraper.market_scraper --validate

# Export market data
python -m mfp_scraper.market_scraper --export csv
```

## Project Structure

```
mfp_scraper/
├── __init__.py              # Package init
├── config.py                # API keys, settings, constants
├── seed_data.py             # CSV loader and parser
├── search_client.py         # Serper.dev API wrapper
├── content_fetcher.py       # Web page content extraction
├── llm_extractor.py         # Gemini LLM structured extraction
├── enrichment_pipeline.py   # Full pipeline orchestrator
├── validator.py             # Data quality validation
├── main.py                  # CLI entry point
│
└── market_scraper/          # MODULE 2: Market Intelligence
    ├── config_market.py     
    ├── ecommerce_client.py  
    ├── market_extractor.py  
    ├── market_models.py     
    ├── market_pipeline.py   
    ├── market_validator.py  
    └── main_market.py       
```

## API Keys Required

- **Serper.dev** — [https://serper.dev](https://serper.dev) (free tier: 2500 queries)
- **Google Gemini** — [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free tier available)
