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
   ```

3. Place your MFP CSV file as `MFP_List_87_Items_Split.csv` in the project root.

## Usage

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
└── main.py                  # CLI entry point
```

## API Keys Required

- **Serper.dev** — [https://serper.dev](https://serper.dev) (free tier: 2500 queries)
- **Google Gemini** — [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free tier available)
