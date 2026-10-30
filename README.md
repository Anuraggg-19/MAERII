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

## Run the Web Application

Run commands from the project root using the same Python environment in which you installed `requirements.txt`. Keep the application's API keys and existing Neo4j/Aura connection settings in the root `.env`; example files are documentation, not runtime configuration.

```powershell
python -m uvicorn app.server:app --reload --port 8000
```

Open <http://localhost:8000>. Restart the server after changing environment variables, and refresh the browser after changing frontend assets.

## Multilingual Website Assistant

The optional assistant helps users navigate MAERII and understand material information, product categories, market results, recommendations, and marketing/branding results already displayed to them. It is disabled by default and has independent provider settings: enabling it does not switch the primary application's LLM provider.

### Features and boundaries

- Language-first onboarding with remembered English, Hindi, or Marathi preference and language switching.
- A catalogue of 25 guided question types, context-ranked suggestions, and scoped custom questions.
- Template/database-first answers; Gemini explanations when needed, with evidence references and validation.
- Sarvam translation for dynamic answers and on-demand Listen/Stop/Replay speech. Audio never autoplays; microphone input is not included.
- Session-scoped answer, translation, and audio caches, with usage limits and graceful provider-failure messages.
- No assistant-triggered scraping, category generation, recommendation generation, or marketing generation. Users initiate those operations through the existing application.

The assistant can explain only results delivered to its current anonymous session. Open the relevant material and sections after enabling it; old or another session's results are not automatically attached. Language selection applies to the assistant, not the entire website.

### Configuration

Append these settings to the **root `.env`**, preserving existing application settings. Do not put real credentials in tracked `.env.example` files.

```dotenv
ASSISTANT_ENABLED=true
ASSISTANT_TRIAL_CONFIRMED=false
ASSISTANT_GEMINI_MODEL=gemini-3.5-flash-lite
SARVAM_API_KEY=your_sarvam_key_here
ASSISTANT_SPEECH_MODEL=bulbul:v3
ASSISTANT_SPEECH_VOICE=shubh
ASSISTANT_DAILY_GENERATIONS=20
ASSISTANT_TRIAL_DAILY_CALLS=100
ASSISTANT_TRIAL_DAILY_CHARACTERS=10000
ASSISTANT_SECURE_COOKIE=false
```

The assistant reuses `GEMINI_API_KEY` unless you supply a separate `ASSISTANT_GEMINI_API_KEY`. The configured Gemini model must be available to your account.

Set `ASSISTANT_TRIAL_CONFIRMED=true` only after confirming that your Gemini and Sarvam accounts use the intended free/trial access without paid overage. The application cannot verify your billing plan or guarantee zero charges. Shared trial ceilings are 100 provider requests and 10,000 Sarvam input characters per UTC day by default; these are usage controls, not monetary budgets. There are additional per-session limits and no automatic provider retries.

Local HTTP testing uses `ASSISTANT_SECURE_COOKIE=false`; HTTPS deployment requires secure cookies and a separate deployment/security review. Restart the server after configuration changes.

### Persistence

The assistant requires reachable Neo4j/Aura storage with permission to create the `maerii_assistant_key` uniqueness constraint and write assistant-owned `AssistantRecord` nodes. These store session records, authorised result snapshots, caches, usage accounting, and feedback without changing existing `Material` or `IntelligenceRun` nodes.

Anonymous sessions last 24 hours. Audio files live under `data/assistant_audio` and are served through session-authorised endpoints, not public static files. If assistant storage is unavailable, assistant requests fail closed rather than making unaccounted provider calls.

### Check and test

```powershell
# Configuration and connectivity diagnostics
python scripts/check_assistant.py

# Optional: one real Gemini check after confirming trial billing
python scripts/check_assistant.py --live-gemini

# Automated tests (provider mocks do not consume trial credits)
python -m pip install -r requirements-assistant-dev.txt
python -m pytest tests -q
node --check app/static/assistant.js
node tests/test_recommendation_cache.js
```

For a manual check, choose a language, open a material and its existing results, and ask a suggested question. Template answers do not test Gemini. Use the simplify-result question or a relevant custom question and check whether the API response reports `mode: gemini` rather than a fallback. Repeat a successful question with unchanged context and language to check `cache_hit: true`. Test translated answers and Listen separately with real Sarvam credentials.

See the runbook for the additional jsdom interaction test and cleanup procedure. `python scripts/cleanup_assistant.py` performs a dry run; `--apply` explicitly removes expired assistant-owned records/audio.

### Current release limitations

This is a restricted-trial implementation, not a public multi-user release. Hindi/Marathi wording requires fluent-speaker review; real Sarvam translation/audio validation and browser visual/accessibility review remain release gates. Evidence checks reduce hallucinations but do not guarantee every generated statement is correct. Authentication, deployment ownership controls, and paid-use budgeting require further work before broader deployment.

To disable the assistant, set `ASSISTANT_ENABLED=false` and restart. Its launcher and response capture are disabled without changing the primary workflows.

### Assistant code and documentation

| Location | Purpose |
| --- | --- |
| `app/assistant/` | Routes, question catalogue, context handling, providers, validation, caches, and quotas |
| `app/static/assistant.js` and `assistant.css` | Chat interface and language/audio controls |
| `tests/assistant/` | Backend and DOM interaction tests |
| `scripts/check_assistant.py` | Configuration and optional live Gemini checks |
| `scripts/cleanup_assistant.py` | Expired assistant-data maintenance |
| [Chatbot runbook](docs/CHATBOT_RUNBOOK.md) | Setup, live testing, limits, persistence, and rollback |
| [Implementation specification](docs/CHATBOT_IMPLEMENTATION_SPECIFICATION.md) | Requirements, architecture, and implementation details |
| [Local model runbook](docs/LOCAL_GPT_OSS_RUNBOOK.md) | Separate primary-workflow local-model setup |

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
