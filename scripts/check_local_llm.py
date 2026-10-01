"""Check the configured Ollama model before running MAERII backfills."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from mfp_scraper import config
from mfp_scraper.local_llm import LocalLLMClient

client = LocalLLMClient()
ready, message = client.healthcheck()
print(message)
if not ready:
    raise SystemExit(1)
result = client.call('{"health":"ok"}', system='Return exactly {"health":"ok"}.', max_tokens=512)
if result != {"health": "ok"}:
    print("Model failed the JSON smoke test.")
    raise SystemExit(2)
print(f"JSON smoke test passed for {config.LOCAL_LLM_MODEL}.")
