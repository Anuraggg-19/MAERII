"""Regression tests for LLM selection and actionable Serper failures."""

from unittest.mock import patch

import requests

from mfp_scraper import config
from mfp_scraper.market_scraper.ecommerce_client import EcommerceClient


def test_gemini_is_the_default_primary_provider():
    with (
        patch.object(config, "GEMINI_API_KEY", "gemini-key"),
        patch.object(config, "GEMINI_MODELS", ["gemini-3.6-flash"]),
        patch.object(config, "GROQ_API_KEY", "groq-key"),
        patch.object(config, "GROQ_MODELS", []),
        patch.object(config, "LLM_PROVIDER_ORDER", ["gemini", "groq"]),
    ):
        assert config.configured_llm_providers() == ["gemini"]


def test_gemini_falls_back_to_groq_only_when_a_groq_model_is_configured():
    with (
        patch.object(config, "GEMINI_API_KEY", "gemini-key"),
        patch.object(config, "GEMINI_MODELS", ["gemini-3.6-flash"]),
        patch.object(config, "GROQ_API_KEY", "groq-key"),
        patch.object(config, "GROQ_MODELS", ["llama-3.3-70b-versatile"]),
        patch.object(config, "LLM_PROVIDER_ORDER", ["gemini", "groq"]),
    ):
        assert config.configured_llm_providers() == ["gemini", "groq"]


def test_serper_http_error_is_returned_to_the_market_service():
    response = requests.Response()
    response.status_code = 400
    response.url = "https://google.serper.dev/shopping"
    response._content = b'{"message":"Missing query parameter","statusCode":400}'

    client = EcommerceClient(api_key="test-key")
    with patch("mfp_scraper.market_scraper.ecommerce_client.requests.post", return_value=response):
        result = client.fetch_products_for_mfp({"name": "Mahua seed"})

    assert result["products"] == []
    assert result["errors"]
    assert "Missing query parameter" in result["errors"][0]
