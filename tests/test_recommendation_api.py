"""API contract tests for the recommendation endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.server import app


CLIENT = TestClient(app)
PAYLOAD = {
    "artisan_skill_level": "Beginner",
    "budget_constraint": "Low",
    "production_time": "Quick turnaround",
    "region_context": "All listed regions",
    "market_context": {
        "market_summary": {"demand_score": 0.7},
        "top_products": [],
    },
}


def test_recommend_endpoint_returns_mocked_generation():
    expected = {
        "status": "complete",
        "mfp_id": 1,
        "recommendations": [{"product_name": "Example"}],
    }
    with patch("app.server.generate_recommendations", return_value=expected) as generate:
        response = CLIENT.post("/api/materials/1/recommend", json=PAYLOAD)

    assert response.status_code == 200
    assert response.json() == expected
    assert generate.call_args.kwargs["market_context"]["market_summary"] == {"demand_score": 0.7}


def test_recommend_endpoint_rejects_missing_market_evidence():
    payload = dict(PAYLOAD)
    payload["market_context"] = {"top_products": []}

    response = CLIENT.post("/api/materials/1/recommend", json=payload)

    assert response.status_code == 422


def test_recommend_endpoint_preserves_unknown_mfp_not_found():
    with patch("app.server.generate_recommendations", side_effect=LookupError("MFP item with id 999 not found")):
        response = CLIENT.post("/api/materials/999/recommend", json=PAYLOAD)

    assert response.status_code == 404
