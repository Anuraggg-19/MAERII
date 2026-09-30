"""Shared Ollama client for MAERII's primary local-LLM workflow."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

import requests

from . import config


class LocalLLMClient:
    """Call the configured Ollama model and parse JSON object responses."""

    provider = "local"

    def __init__(self) -> None:
        self.base_url = config.LOCAL_LLM_BASE_URL
        self.model = config.LOCAL_LLM_MODEL
        self.timeout = config.LOCAL_LLM_TIMEOUT_SECONDS
        self.last_metadata: dict[str, Any] = {}

    @property
    def is_configured(self) -> bool:
        return bool(config.LOCAL_LLM_ENABLED and self.base_url and self.model)

    def call(
        self,
        prompt: str,
        *,
        system: str = "Return valid JSON only.",
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> Optional[dict]:
        if not self.is_configured:
            return None

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": config.LLM_TEMPERATURE if temperature is None else temperature,
                "num_predict": max_tokens,
            },
        }
        for attempt in range(config.LLM_MAX_RETRIES):
            started = time.monotonic()
            try:
                response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()
                parsed = self.parse_json(((body.get("message") or {}).get("content") or "").strip())
                self.last_metadata = {
                    "model": body.get("model", self.model),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "prompt_eval_count": body.get("prompt_eval_count"),
                    "eval_count": body.get("eval_count"),
                }
                if parsed is not None:
                    return parsed
                print("  [LocalLLM] Non-JSON model response; retrying.")
            except (requests.RequestException, ValueError) as exc:
                print(f"  [LocalLLM] Attempt {attempt + 1} failed: {exc}")
                if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                    break
            if attempt < config.LLM_MAX_RETRIES - 1:
                time.sleep(min(2 * (attempt + 1), 8))
        return None

    def healthcheck(self) -> tuple[bool, str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            names = {model.get("name", "") for model in response.json().get("models", [])}
            if self.model in names:
                return True, f"Local model '{self.model}' is ready."
            return False, f"Ollama is reachable, but '{self.model}' is not installed."
        except requests.RequestException as exc:
            return False, f"Cannot reach Ollama at {self.base_url}: {exc}"

    @staticmethod
    def parse_json(raw_text: str) -> Optional[dict]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.IGNORECASE)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                value = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return None
        return value if isinstance(value, dict) else None
