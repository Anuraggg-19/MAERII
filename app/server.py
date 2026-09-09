"""
FastAPI server for the MAERII Knowledge Engine demo.

Endpoints:
  GET  /api/materials              → list all 115 MFP items (from Neo4j)
  GET  /api/materials/{mfp_id}     → full detail + graph neighbors (from Neo4j)
  POST /api/materials/{mfp_id}/market     → real-time market analysis (Serper + LLM)
  POST /api/materials/{mfp_id}/market/compare → isolated Serper vs Scrapingdog comparison
  POST /api/materials/{mfp_id}/categories → product categories, processes & skills (LLM + cache)

Static frontend served at /
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.neo4j_client import list_materials, get_material_detail, get_graph_data, close_driver
from app.market_service import analyze_market_realtime
from app.market_comparison_service import compare_market_providers
from app.open_source_market_service import OpenSourcePipelineError, run_open_source_market_experiment
from app.product_service import get_product_categories
from app.recommendation_service import (
    RecommendationGenerationError,
    RecommendationValidationError,
    generate_recommendations,
)

# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MAERII Knowledge Engine",
    description="Raw Material Knowledge Engine — Demo API",
    version="0.1.0",
)


class MarketContextRequest(BaseModel):
    """Only the current market evidence needed for recommendation generation."""

    market_summary: dict = Field(...)
    competitor_analysis: dict = Field(default_factory=dict)
    top_products: list[dict] = Field(default_factory=list)
    product_demand_match: dict = Field(default_factory=dict)
    regional_market_fit: list = Field(default_factory=list)
    seasonal_demand: Any = None


class RecommendationRequest(BaseModel):
    artisan_skill_level: str
    budget_constraint: str
    production_time: str
    region_context: str
    cultural_motifs: Optional[str] = None
    market_context: MarketContextRequest


# ── API Routes ───────────────────────────────────────────────────────────────

@app.get("/api/materials")
def api_list_materials():
    """List all 87 MFP items with core properties."""
    try:
        materials = list_materials()
        return {"count": len(materials), "materials": materials}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")


@app.get("/api/materials/{mfp_id}")
def api_get_material(mfp_id: int):
    """Get full detail for one MFP item + knowledge graph neighbors."""
    try:
        result = get_material_detail(mfp_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Material with mfp_id {mfp_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")


@app.get("/api/materials/{mfp_id}/graph")
def api_get_graph(mfp_id: int):
    """Get knowledge graph data (nodes + edges) for visualization."""
    try:
        result = get_graph_data(mfp_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No graph data for mfp_id {mfp_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j query failed: {e}")


@app.post("/api/materials/{mfp_id}/market")
def api_market_analysis(mfp_id: int):
    """Run real-time market analysis for one MFP item.

    This call takes 20-40 seconds as it makes live API calls
    to Serper (shopping search) and the configured LLM (Gemini by default).
    """
    try:
        result = analyze_market_realtime(mfp_id)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Market analysis failed: {e}")


@app.post("/api/materials/{mfp_id}/market/compare")
def api_compare_market_providers(mfp_id: int):
    """Compare raw Google Shopping results without changing market analysis."""
    try:
        return compare_market_providers(mfp_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Market provider comparison failed: {exc}")


@app.post("/api/materials/{mfp_id}/market/open-source")
def api_open_source_market_experiment(mfp_id: int):
    """Run the fully open-source market experiment without touching production."""
    try:
        return run_open_source_market_experiment(mfp_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OpenSourcePipelineError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Open-source market experiment failed: {exc}")


@app.post("/api/materials/{mfp_id}/categories")
def api_product_categories(mfp_id: int, refresh: bool = False):
    """Generate product categories with manufacturing processes and skills.

    First call takes 3-6 seconds (LLM generation).
    Subsequent calls return instantly from persistent cache.
    Pass ?refresh=true to force re-generation.
    """
    try:
        result = get_product_categories(mfp_id, refresh=refresh)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Product categorization failed: {e}")


@app.post("/api/materials/{mfp_id}/recommend")
def api_recommend_products(mfp_id: int, request: RecommendationRequest):
    """Generate product recommendations from completed categories and live market evidence."""
    try:
        return generate_recommendations(
            mfp_id=mfp_id,
            artisan_skill_level=request.artisan_skill_level,
            budget_constraint=request.budget_constraint,
            production_time=request.production_time,
            region_context=request.region_context,
            cultural_motifs=request.cultural_motifs,
            market_context=request.market_context.dict(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RecommendationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RecommendationGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {exc}")


# ── Static Files (Frontend) ─────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


# Mount static assets (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("shutdown")
def shutdown():
    close_driver()


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  MAERII Knowledge Engine — Demo Server")
    print("  http://localhost:8000")
    print("=" * 50)
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=True)
