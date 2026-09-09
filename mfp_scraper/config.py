"""
Configuration module — loads API keys from .env file and defines constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# -- Load environment variables ----------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent

# Only load the real local environment file.  Example files are documentation,
# never a source of credentials at runtime.
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
SCRAPINGDOG_API_KEY = os.getenv("SCRAPINGDOG_API_KEY", "")


def _bool_from_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _nonnegative_int_from_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _models_from_env(name: str, defaults: tuple[str, ...]) -> list[str]:
    """Read a comma-separated model list without silently enabling a provider."""
    value = os.getenv(name, "").strip()
    if not value:
        return list(defaults)
    return [model.strip() for model in value.split(",") if model.strip()]


def _provider_order_from_env() -> list[str]:
    """Return a validated provider order, keeping Gemini as the primary LLM."""
    configured = os.getenv("LLM_PROVIDER_ORDER", "gemini,groq")
    valid = {"gemini", "groq"}
    order = [provider.strip().lower() for provider in configured.split(",")]
    return [provider for provider in order if provider in valid] or ["gemini", "groq"]

# ── File paths ──────────────────────────────────────────────────────────────
CSV_PATH = PROJECT_ROOT / "MFP_List_87_Items_Split.csv"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SEED_JSON_PATH = DATA_DIR / "seed_mfp_list.json"
ENRICHED_JSON_PATH = DATA_DIR / "enriched_mfp_data.json"
ENRICHMENT_LOG_PATH = DATA_DIR / "enrichment_log.json"
DEEP_ENRICHMENT_EVIDENCE_PATH = DATA_DIR / "deep_enrichment_evidence.json"
MATERIAL_RELATIONSHIPS_PATH = DATA_DIR / "material_relationships.json"
DEEP_RUNS_DIR = DATA_DIR / "deep_enrichment_runs"
BACKUPS_DIR = DATA_DIR / "backups"
OPEN_SOURCE_COMPARISONS_DIR = DATA_DIR / "open_source_comparisons"

# Market Demand Module Output Paths
MARKET_DEMAND_PATH = DATA_DIR / "market_demand_data.json"
MARKET_PRODUCTS_PATH = DATA_DIR / "market_products.json"
MARKET_ANALYSIS_LOG_PATH = DATA_DIR / "market_analysis_log.json"
MARKET_SOURCES_PATH = DATA_DIR / "market_sources.json"
MARKET_RUNS_DIR = DATA_DIR / "market_runs"
MARKET_BACKUPS_DIR = DATA_DIR / "market_backups"

# ── Serper API settings ─────────────────────────────────────────────────────
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_IMAGES_URL = "https://google.serper.dev/images"
SEARCH_RESULTS_PER_QUERY = 5  # Top N results to fetch per search

# -- LLM settings ------------------------------------------------------------
# Models to try in order (falls back if quota is exhausted).
# Gemini 3.6 Flash is the current stable replacement for the retired Gemini 2.x
# Flash models and supports the JSON output used by this project.
GEMINI_MODELS = _models_from_env("GEMINI_MODELS", ("gemini-3.6-flash",))

# Keep Groq opt-in: an API key with no configured model must not take over a
# request and then fail before Gemini is tried.
GROQ_MODELS = _models_from_env("GROQ_MODELS", ())

TOGETHER_MODELS = _models_from_env("TOGETHER_MODELS", (
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
))

LLM_PROVIDER_ORDER = _provider_order_from_env()
MARKET_COMPARISON_MODE = _bool_from_env("MARKET_COMPARISON_MODE")
MARKET_COMPARISON_STORE_RAW = _bool_from_env("MARKET_COMPARISON_STORE_RAW")
MARKET_COMPARISON_RELEVANCE_FILTER = _bool_from_env("MARKET_COMPARISON_RELEVANCE_FILTER", True)
MARKET_COMPARISON_DESTINATION_LIMIT = _nonnegative_int_from_env("MARKET_COMPARISON_DESTINATION_LIMIT", 5)
MARKET_COMPARISON_DESTINATION_CANDIDATE_LIMIT = _nonnegative_int_from_env("MARKET_COMPARISON_DESTINATION_CANDIDATE_LIMIT", 15)
MARKET_COMPARISON_DESTINATION_DYNAMIC = _bool_from_env("MARKET_COMPARISON_DESTINATION_DYNAMIC", True)

# -- Isolated open-source market experiment ---------------------------------
# This stack is intentionally separate from the Serper/Gemini production path.
OPEN_SOURCE_MARKET_MODE = _bool_from_env("OPEN_SOURCE_MARKET_MODE")
OPEN_SOURCE_DISCOVERY_PROVIDER = os.getenv("OPEN_SOURCE_DISCOVERY_PROVIDER", "searxng").strip().lower()
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b").strip()
OPEN_SOURCE_RESULTS_PER_QUERY = _nonnegative_int_from_env("OPEN_SOURCE_RESULTS_PER_QUERY", 5)
OPEN_SOURCE_MAX_URLS = _nonnegative_int_from_env("OPEN_SOURCE_MAX_URLS", 18)
OPEN_SOURCE_MAX_CLASSIFICATIONS = _nonnegative_int_from_env("OPEN_SOURCE_MAX_CLASSIFICATIONS", 20)
OPEN_SOURCE_CLASSIFICATION_BATCH_SIZE = _nonnegative_int_from_env("OPEN_SOURCE_CLASSIFICATION_BATCH_SIZE", 3)
OPEN_SOURCE_REQUEST_TIMEOUT_SECONDS = _nonnegative_int_from_env("OPEN_SOURCE_REQUEST_TIMEOUT_SECONDS", 45)


def configured_llm_providers() -> list[str]:
    """Return providers that have both credentials and at least one model."""
    ready = {
        "gemini": bool(GEMINI_API_KEY and GEMINI_MODELS),
        "groq": bool(GROQ_API_KEY and GROQ_MODELS),
    }
    return [provider for provider in LLM_PROVIDER_ORDER if ready[provider]]

GEMINI_MODEL = GEMINI_MODELS[0] if GEMINI_MODELS else ""  # Primary model
LLM_TEMPERATURE = 0.2  # Low temperature for factual extraction
LLM_MAX_RETRIES = 5

# ── Rate limiting ───────────────────────────────────────────────────────────
SEARCH_DELAY_SECONDS = 1.5   # Delay between search API calls
FETCH_DELAY_SECONDS = 1.0    # Delay between web page fetches
LLM_DELAY_SECONDS = 4.0      # Delay between LLM calls (generous for free tier)
FETCH_TIMEOUT_SECONDS = 10   # Timeout for fetching web pages
DEEP_FETCH_MAX_CHARS = 6000
DEEP_FETCH_MAX_DOCS = 6

# ── Category mapping ────────────────────────────────────────────────────────
CATEGORY_MAP = {
    "F": "Forest Produce",
    "A": "Agriculture",
    "P": "Processed",
    "M": "Medicinal",
    "H": "Horticulture",
    "FP": "Forest Produce / Processed",
    "F/P": "Forest Produce / Processed",
    "AP": "Agriculture / Processed",
    "F/H": "Forest Produce / Horticulture",
    "F/M": "Forest Produce / Medicinal",
}

# ── Target schema for enrichment ────────────────────────────────────────────
TARGET_FIELDS = [
    "scientific_name",
    "description",
    "season",
    "shelf_life",
    "states",
    "artisan_types",
    "current_products",
    "potential_products",
    "image_url",
]

# ── States of India with significant tribal populations ─────────────────────
# Used to resolve "All India" to specific tribal-relevant states
TRIBAL_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Himachal Pradesh",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
]

NE_STATES = [
    "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
]
