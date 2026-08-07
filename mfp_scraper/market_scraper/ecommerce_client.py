"""
E-commerce data fetcher using Serper Shopping Search API.

Searches for MFP-derived products on e-commerce platforms via Serper's
shopping and web search endpoints. Normalizes results into a standard
product schema for downstream LLM classification.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from . import config_market
from .market_models import normalize_product, utc_now_iso


class EcommerceClient:
    """Fetch e-commerce product data via Serper Shopping + Web Search APIs."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config_market.SERPER_API_KEY
        if not self.api_key:
            raise ValueError(
                "SERPER_API_KEY not set. Add it to your .env file.\n"
                "Get a free key at https://serper.dev"
            )
        self.headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        self._last_call_time = 0.0

    def _rate_limit(self):
        """Enforce delay between API calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < config_market.ECOMMERCE_DELAY_SECONDS:
            time.sleep(config_market.ECOMMERCE_DELAY_SECONDS - elapsed)
        self._last_call_time = time.time()

    # ── Public API ──────────────────────────────────────────────────────────

    def search_products(self, query: str, num_results: int = 0) -> list[dict]:
        """Search for products using Serper Shopping API.

        Returns a list of normalized product dicts.
        Falls back to web search if shopping returns nothing.
        """
        num_results = num_results or config_market.SHOPPING_RESULTS_PER_QUERY

        products = self._search_shopping(query, num_results)
        if not products:
            products = self._search_web_products(query, num_results)

        return products

    def fetch_products_for_mfp(self, mfp_item: dict, category_context: Optional[list[dict]] = None) -> dict:
        """Fetch all market products for a single MFP item.

        Executes every planned query, then selects unique products round-robin
        across the query result sets. This prevents broad searches from filling
        the cap before category-specific searches (such as lampshades) run.

        Returns:
            {
                "queries": [{"query": str, "result_count": int}, ...],
                "products": [normalized product dicts],
            }
        """
        query_plan = self._build_query_plan(mfp_item, category_context=category_context)
        seen_ids = set()
        seen_titles = set()
        query_log = []
        grouped_products: list[list[dict]] = []

        for plan_item in query_plan:
            query = plan_item["query"]
            products = self.search_products(query)
            new_count = 0
            unique_products = []
            for product in products:
                pid = product.get("product_id", "")
                title = product.get("title", "").strip().lower()

                # Deduplicate by ID and strict Title match
                if pid and pid not in seen_ids and title not in seen_titles:
                    seen_ids.add(pid)
                    if title:
                        seen_titles.add(title)
                    unique_products.append(product)
                    new_count += 1

            query_log.append({"query": query, "result_count": new_count})
            grouped_products.append(unique_products)

        # Retain products fairly across every query instead of taking the first
        # 50 in query order. Each non-empty category query gets a chance to
        # contribute before additional results from broad searches are used.
        all_products = []
        offsets = [0] * len(grouped_products)
        while len(all_products) < config_market.MAX_PRODUCTS_PER_MFP:
            made_progress = False
            for index, products in enumerate(grouped_products):
                if offsets[index] >= len(products):
                    continue
                all_products.append(products[offsets[index]])
                offsets[index] += 1
                made_progress = True
                if len(all_products) >= config_market.MAX_PRODUCTS_PER_MFP:
                    break
            if not made_progress:
                break

        return {
            "queries": query_log,
            "products": all_products,
        }

    @staticmethod
    def _get_search_name(raw_name: str) -> str:
        """Extract a short, search-friendly name from an MFP name.

        Many MFP names have multiple forms separated by / or in parentheses.
        For search, we want the shortest recognizable term.

        Examples:
          'Forest Cinnamon (Dalchini)' -> 'Dalchini'
          'Pipla/Uchithi (Dried berry)' -> 'Pipla'
          'Palash / Flame of the Forest' -> 'Palash'
          'Cane (Rattan)' -> 'Rattan Cane'
          'Wild Honey' -> 'Wild Honey'
        """
        import re
        name = raw_name.strip()

        # Extract parenthesized term — often the local/common name
        paren_match = re.search(r'\(([^)]+)\)', name)
        base_name = re.sub(r'\s*\([^)]*\)', '', name).strip()

        # If there's a slash, take the first part (usually shorter/common)
        if '/' in base_name:
            parts = [p.strip() for p in base_name.split('/')]
            base_name = min(parts, key=len) if parts else base_name

        # If we found a parenthesized term, prefer it if it's a single
        # recognizable word (like "Dalchini", "Rattan")
        if paren_match:
            paren_term = paren_match.group(1).strip()
            # Skip descriptive parentheticals like "Dried berry", "Reeling/Un-Reeling"
            if len(paren_term.split()) <= 2 and '/' not in paren_term:
                # Use both for better coverage: "Rattan Cane", "Dalchini"
                if len(base_name.split()) > 2:
                    return paren_term  # Just "Dalchini" is better than "Forest Cinnamon"
                return f"{paren_term} {base_name}"  # "Rattan Cane"

        return base_name

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Remove characters that break Serper API calls."""
        import re
        cleaned = re.sub(r'[()[\]{}/\\"]', ' ', query)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def build_search_queries(self, mfp_item: dict, category_context: Optional[list[dict]] = None) -> list[str]:
        """Build targeted search queries for an MFP item.

        Strategy:
        1. Always search for the raw material.
        2. If AI product categories are provided, distribute queries evenly across
           the distinct categories (1-2 products per category) to ensure diverse
           market representations rather than one product type dominating.
        3. Fall back to current and potential products if no category context is provided.
        """
        return [
            plan_item["query"]
            for plan_item in self._build_query_plan(mfp_item, category_context=category_context)
        ]

    def _build_query_plan(self, mfp_item: dict, category_context: Optional[list[dict]] = None) -> list[dict]:
        """Create a capped query plan that gives every category a primary query.

        The raw-material query is retained for backward-compatible broad
        coverage. When generated categories are available, their first product
        is scheduled before any second product from another category. With the
        configured maximum of five generated categories plus one raw query,
        this guarantees at least one targeted query per category.
        """
        name = self._get_search_name(mfp_item.get("name", ""))
        raw_query = self._sanitize_query(f"{name} buy online India")
        primary_queries: list[dict] = []
        expansion_queries: list[dict] = []

        # Category-driven queries: schedule every category's first product
        # before considering a second product from any category.
        if category_context and isinstance(category_context, list) and len(category_context) > 0:
            for cat in category_context:
                if not isinstance(cat, dict):
                    continue
                products = cat.get("products", [])
                if not isinstance(products, list):
                    continue
                category_name = str(cat.get("category_name", "")).strip()
                product_names = []
                for product in products:
                    product_name = product.get("name", "") if isinstance(product, dict) else str(product)
                    product_name = product_name.strip()
                    if product_name:
                        product_names.append(product_name)

                for index, product_name in enumerate(product_names):
                    query = self._sanitize_query(f"{name} {product_name} buy online India")
                    plan_item = {
                        "query": query,
                        "category_name": category_name,
                        "product_name": product_name,
                    }
                    if index == 0:
                        primary_queries.append(plan_item)
                    else:
                        expansion_queries.append(plan_item)
        else:
            # Fallback to current and potential products from MFP item
            for product in (
                list(mfp_item.get("current_products", []))
                + list(mfp_item.get("potential_products", []))
            ):
                product_name = str(product).strip()
                if product_name:
                    expansion_queries.append({
                        "query": self._sanitize_query(f"{name} {product_name} buy online India"),
                        "category_name": "",
                        "product_name": product_name,
                    })

        # Keep the existing raw search, then guarantee category primaries before
        # spending the remaining query budget on additional category products.
        query_plan = [{
            "query": raw_query,
            "category_name": "",
            "product_name": "",
        }] + primary_queries + expansion_queries

        # Deduplicate and cap while retaining the earliest (highest-priority)
        # representative of a repeated query.
        seen = set()
        deduped: list[dict] = []
        for plan_item in query_plan:
            key = plan_item["query"].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(plan_item)

        return deduped[: config_market.MAX_SEARCH_QUERIES_PER_MFP]

    # ── Private search methods ──────────────────────────────────────────────

    def _search_shopping(self, query: str, num_results: int) -> list[dict]:
        """Hit Serper Shopping endpoint and normalize results."""
        self._rate_limit()

        try:
            resp = requests.post(
                config_market.SERPER_SHOPPING_URL,
                headers=self.headers,
                json={
                    "q": query,
                    "num": num_results,
                    "gl": "in",  # India
                    "hl": "en",
                },
                timeout=config_market.FETCH_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()

            products = []
            for item in data.get("shopping", [])[:num_results]:
                raw = {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "price": item.get("price", ""),
                    "rating": item.get("rating"),
                    "review_count": item.get("ratingCount", 0),
                    "source": item.get("source", ""),
                    "seller": item.get("source", ""),
                    "imageUrl": item.get("imageUrl") or item.get("thumbnail", ""),
                    "category": "",
                    "currency": "INR",
                }
                product = normalize_product(raw)
                if product["title"]:
                    products.append(product)

            return products

        except requests.RequestException as exc:
            print(f"  [!] Shopping search error for '{query}': {exc}")
            return []

    def _search_web_products(self, query: str, num_results: int) -> list[dict]:
        """Fallback: use regular web search with e-commerce site filters."""
        self._rate_limit()

        ecommerce_query = f"{query} site:amazon.in OR site:flipkart.com OR site:meesho.com"

        try:
            resp = requests.post(
                config_market.SERPER_SEARCH_URL,
                headers=self.headers,
                json={
                    "q": ecommerce_query,
                    "num": num_results,
                    "gl": "in",
                    "hl": "en",
                },
                timeout=config_market.FETCH_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()

            products = []
            for item in data.get("organic", [])[:num_results]:
                link = item.get("link", "")
                # Only include actual e-commerce links
                if not any(domain in link.lower() for domain in ("amazon", "flipkart", "meesho", "jiomart")):
                    continue

                raw = {
                    "title": item.get("title", ""),
                    "url": link,
                    "price": self._extract_price_from_snippet(item.get("snippet", "")),
                    "rating": None,
                    "review_count": 0,
                    "source": link,
                    "seller": "",
                    "imageUrl": "",
                    "category": "",
                    "currency": "INR",
                }
                product = normalize_product(raw)
                if product["title"]:
                    products.append(product)

            return products

        except requests.RequestException as exc:
            print(f"  [!] Web search error for '{query}': {exc}")
            return []

    def _extract_price_from_snippet(self, snippet: str) -> Optional[str]:
        """Try to extract a price from a search snippet."""
        import re
        match = re.search(r"₹\s*[\d,]+(?:\.\d{1,2})?|Rs\.?\s*[\d,]+(?:\.\d{1,2})?", snippet)
        return match.group(0) if match else None
