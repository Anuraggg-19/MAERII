"""Tests for destination-page enrichment used only by market comparison."""

from mfp_scraper.market_scraper.scrapingdog_client import ScrapingdogShoppingClient


def test_retailer_url_comes_from_immersive_store_data_not_google_link():
    url = ScrapingdogShoppingClient._first_retailer_url({
        "product_link": "https://www.google.com/shopping/product/123",
        "stores": [{"name": "Retailer", "link": "https://retailer.example/products/mahua-oil"}],
    })

    assert url == "https://retailer.example/products/mahua-oil"


def test_destination_page_extracts_jsonld_product_details():
    html = """
    <html><head><title>Mahua Oil | Retailer</title>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Pure Mahua Oil",
     "description":"Cold pressed oil", "sku":"MO-1", "brand":{"name":"Forest Co"},
     "image":["https://images.example/oil.jpg"],
     "offers":{"@type":"Offer","price":"299","priceCurrency":"INR","availability":"https://schema.org/InStock"},
     "aggregateRating":{"ratingValue":"4.6","reviewCount":"21"},
     "additionalProperty":{"name":"Volume","value":"250 ml"}}
    </script></head><body></body></html>
    """

    product = ScrapingdogShoppingClient._extract_product_page(html, "https://retailer.example/products/mahua-oil")

    assert product["name"] == "Pure Mahua Oil"
    assert product["price"] == "299"
    assert product["availability"].endswith("InStock")
    assert product["attributes"] == [{"name": "Volume", "value": "250 ml"}]
