"""
Configuration module — loads API keys from .env file and defines constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# -- Load environment variables ----------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent

# Try .env first, fall back to .env.example
_env_path = PROJECT_ROOT / ".env"
if not _env_path.exists():
    _env_path = PROJECT_ROOT / ".env.example"
load_dotenv(_env_path)


SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── File paths ──────────────────────────────────────────────────────────────
CSV_PATH = PROJECT_ROOT / "MFP_List_87_Items_Split.csv"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

SEED_JSON_PATH = DATA_DIR / "seed_mfp_list.json"
ENRICHED_JSON_PATH = DATA_DIR / "enriched_mfp_data.json"
ENRICHMENT_LOG_PATH = DATA_DIR / "enrichment_log.json"

# ── Serper API settings ─────────────────────────────────────────────────────
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_IMAGES_URL = "https://google.serper.dev/images"
SEARCH_RESULTS_PER_QUERY = 5  # Top N results to fetch per search

# -- LLM settings ------------------------------------------------------------
# Models to try in order (falls back if quota is exhausted)
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
GEMINI_MODEL = GEMINI_MODELS[0]  # Primary model
LLM_TEMPERATURE = 0.2  # Low temperature for factual extraction
LLM_MAX_RETRIES = 5

# ── Rate limiting ───────────────────────────────────────────────────────────
SEARCH_DELAY_SECONDS = 1.5   # Delay between search API calls
FETCH_DELAY_SECONDS = 1.0    # Delay between web page fetches
LLM_DELAY_SECONDS = 4.0      # Delay between LLM calls (generous for free tier)
FETCH_TIMEOUT_SECONDS = 10   # Timeout for fetching web pages

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
