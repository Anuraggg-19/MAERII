"""
Market-specific configuration constants for Module 2.
Imports shared API keys and paths from the parent config module.
"""

from __future__ import annotations

from .. import config

# ── Shared API keys (from parent config) ────────────────────────────────────
SERPER_API_KEY = config.SERPER_API_KEY
GEMINI_API_KEY = config.GEMINI_API_KEY
GROQ_API_KEY = config.GROQ_API_KEY
TOGETHER_API_KEY = config.TOGETHER_API_KEY

# ── LLM model lists (same as Module 1 for consistency) ──────────────────────
GEMINI_MODELS = config.GEMINI_MODELS
GROQ_MODELS = config.GROQ_MODELS
TOGETHER_MODELS = config.TOGETHER_MODELS
LLM_TEMPERATURE = config.LLM_TEMPERATURE
LLM_MAX_RETRIES = config.LLM_MAX_RETRIES

# ── File paths ──────────────────────────────────────────────────────────────
DATA_DIR = config.DATA_DIR
ENRICHED_JSON_PATH = config.ENRICHED_JSON_PATH

MARKET_DEMAND_PATH = DATA_DIR / "market_demand_data.json"
MARKET_PRODUCTS_PATH = DATA_DIR / "market_products.json"
MARKET_ANALYSIS_LOG_PATH = DATA_DIR / "market_analysis_log.json"
MARKET_SOURCES_PATH = DATA_DIR / "market_sources.json"
MARKET_RUNS_DIR = DATA_DIR / "market_runs"
MARKET_BACKUPS_DIR = DATA_DIR / "market_backups"

# ── Serper API endpoints ────────────────────────────────────────────────────
SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
SERPER_SEARCH_URL = config.SERPER_SEARCH_URL

# ── Search configuration ───────────────────────────────────────────────────
# Per MFP: search MFP name + top 2 current_products + top 2 potential_products
# = up to 5 queries per MFP item
MAX_SEARCH_QUERIES_PER_MFP = 6
SHOPPING_RESULTS_PER_QUERY = 20
WEB_RESULTS_PER_QUERY = 5

# ── Rate limiting ──────────────────────────────────────────────────────────
ECOMMERCE_DELAY_SECONDS = 2.0      # Delay between e-commerce API calls
LLM_DELAY_SECONDS = 4.0             # Delay between LLM calls
FETCH_TIMEOUT_SECONDS = 15          # Timeout for HTTP requests

# ── Product caps ───────────────────────────────────────────────────────────
MAX_PRODUCTS_PER_MFP = 50           # Cap on products to store per MFP item
MAX_PRODUCTS_FOR_LLM = 40           # Max products to send to LLM for analysis

# ── Market analysis constants ──────────────────────────────────────────────
DEMAND_SCORE_WEIGHTS = {
    "review_volume": 0.30,           # Higher review counts → higher demand
    "rating_quality": 0.20,          # Higher ratings → market validation
    "product_variety": 0.20,         # More unique products → broader market
    "price_premium": 0.15,           # Higher prices over MSP → value potential
    "seller_diversity": 0.15,        # More sellers → competitive market
}

# Demand score thresholds for trend classification
TREND_THRESHOLDS = {
    "rising": 0.65,
    "stable": 0.35,
    "declining": 0.0,
}
