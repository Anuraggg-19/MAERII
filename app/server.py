"""
FastAPI server for the MAERII Knowledge Engine demo.

Endpoints:
  GET  /api/materials            → list all 87 MFP items (from Neo4j)
  GET  /api/materials/{mfp_id}   → full detail + graph neighbors (from Neo4j)
  POST /api/materials/{mfp_id}/market → real-time market analysis (Serper + LLM)

Static frontend served at /
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.neo4j_client import list_materials, get_material_detail, get_graph_data, close_driver
from app.market_service import analyze_market_realtime

# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MAERII Knowledge Engine",
    description="Raw Material Knowledge Engine — Demo API",
    version="0.1.0",
)


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
    to Serper (shopping search) and Groq (LLM classification).
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
