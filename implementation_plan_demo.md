# MAERII Knowledge Engine — Working Demo Implementation Plan

## Goal

Build a working demo where a user can **select a raw material** and instantly see all its knowledge (Module 1) plus trigger **real-time market analysis** (Module 2). No auth, no deployment — local machine only.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Frontend (Browser)                      │
│         Vanilla HTML / CSS / JS                      │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Material  │  │   Detail     │  │  Market Panel │  │
│  │ Selector  │→ │   View       │→ │  (Real-time)  │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (fetch)
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Backend                         │
│                                                      │
│  /api/materials          → List all 87 MFPs          │
│  /api/materials/{id}     → Full detail + graph       │
│  /api/materials/{id}/market → Real-time market data  │
│                                                      │
│  ┌────────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  Neo4j     │  │  Serper  │  │  Groq (Llama 3.3)│ │
│  │  Driver    │  │  API     │  │  API             │ │
│  └────────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| **Backend** | FastAPI (Python) | You already have all code in Python. FastAPI is lightweight, async-capable, and has auto-generated Swagger docs for testing |
| **Database** | Neo4j (via `neo4j` Python driver) | Already set up with 87 Materials + 1,259 relationships |
| **Market Search** | Serper API (existing key) | Real-time Google Shopping results |
| **Market LLM** | Groq API → Llama 3.3 (existing key) | Real-time product classification + market analysis |
| **Frontend** | Vanilla HTML + CSS + JS | Simple, no build step, no framework overhead |
| **Serving** | FastAPI serves static files | Single `python` command runs everything |

### New Dependencies (pip install)

```
fastapi
uvicorn
neo4j
```

The rest (`requests`, `groq`, `python-dotenv`) you already have.

---

## API Design

### `GET /api/materials`
Returns the full list of 87 MFPs for the selector/search.

```json
[
  {
    "mfp_id": 1,
    "name": "Tamarind (with seeds)",
    "category": "Forest Produce",
    "msp": 36.0,
    "scientific_name": "Tamarindus indica",
    "availability_band": "medium",
    "demand_score": 0.677
  },
  ...
]
```

### `GET /api/materials/{mfp_id}`
Returns full detail for one material — all Module 1 data + graph neighbors from Neo4j.

```json
{
  "material": {
    "mfp_id": 1,
    "name": "Tamarind (with seeds)",
    "scientific_name": "Tamarindus indica",
    "description": "...",
    "category": "Forest Produce",
    "msp": 36.0,
    "unit": "kg",
    "season": "March-April",
    "shelf_life": "9-12 months",
    "availability_band": "medium"
  },
  "graph": {
    "states": ["Tamil Nadu", "Madhya Pradesh", ...],
    "skills": ["Fruit Collector", "Pod Collector", ...],
    "current_products": ["pulp", "powder", "seasoning", ...],
    "potential_products": ["seed derivatives", ...],
    "material_group": "Forest Produce",
    "districts": [...],
    "clusters": [...]
  }
}
```

### `POST /api/materials/{mfp_id}/market`
**Real-time.** Triggers Serper search + Groq LLM classification. Returns market analysis in ~20-30 seconds.

```json
{
  "status": "complete",
  "products_found": 38,
  "products_matched": 25,
  "market_summary": {
    "avg_price": 774.26,
    "price_range": {"min": 20.0, "max": 16800.0},
    "avg_rating": 3.8,
    "total_reviews": 11,
    "demand_score": 0.677,
    "trend": "stable",
    "top_attributes": ["natural", "organic", "raw"]
  },
  "competitor_analysis": {
    "top_brands": ["Amazon.in", "Meesho", ...],
    "market_gaps": ["Tribal certification", ...],
    "price_positioning": "mid-range"
  },
  "top_products": [
    {"title": "...", "price": 599, "rating": 4.5, "seller": "..."},
    ...
  ]
}
```

---

## File Structure

```
MAERII/
├── app/                          ← NEW: Demo application
│   ├── server.py                 ← FastAPI backend (single file)
│   ├── neo4j_client.py           ← Neo4j query helper
│   ├── market_service.py         ← Real-time market analysis service
│   └── static/                   ← Frontend files
│       ├── index.html
│       ├── style.css
│       └── app.js
├── mfp_scraper/                  ← Existing (unchanged)
├── data/                         ← Existing (unchanged)
└── scripts/                      ← Existing (unchanged)
```

> [!IMPORTANT]
> The `app/` directory is completely separate from `mfp_scraper/`. It reuses the existing market scraper logic by importing from `mfp_scraper.market_scraper`, but does NOT modify any existing code.

---

## Frontend Layout (Single Page)

```
┌──────────────────────────────────────────────────┐
│  MAERII Knowledge Engine                    🔍    │  ← Header + search
├──────────────────────────────────────────────────┤
│                                                    │
│  ┌─────────┐  ┌────────────────────────────────┐  │
│  │ Material │  │  DETAIL VIEW                   │  │
│  │ List     │  │                                │  │
│  │          │  │  Name, Sci Name, Category, MSP │  │
│  │ [Search] │  │  Season, Shelf Life            │  │
│  │          │  │                                │  │
│  │ Tamarind │  │  ┌─States──┐ ┌─Products──────┐ │  │
│  │ Honey    │  │  │ TN, MP  │ │ pulp, powder  │ │  │
│  │ Gum K... │  │  │ AP, MH  │ │ seasoning     │ │  │
│  │ Karanj   │  │  └─────────┘ └───────────────┘ │  │
│  │ Sal seed │  │                                │  │
│  │ Mahua    │  │  ┌─Skills────────────────────┐ │  │
│  │ ...      │  │  │ Fruit Collector, Pod ...  │ │  │
│  │          │  │  └───────────────────────────┘ │  │
│  │          │  │                                │  │
│  │          │  │  [ 🔍 Fetch Market Analysis ]  │  │
│  │          │  │                                │  │
│  │          │  │  ┌─Market Panel──────────────┐ │  │
│  │          │  │  │ Demand: 0.67 | Trend: ↑   │ │  │
│  │          │  │  │ Avg Price: ₹774           │ │  │
│  │          │  │  │ Top Sellers: Amazon, ...   │ │  │
│  │          │  │  │ Gaps: Tribal cert, ...     │ │  │
│  │          │  │  └───────────────────────────┘ │  │
│  └─────────┘  └────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

- Dark theme, clean typography
- Left sidebar: scrollable list of 87 materials with search filter
- Right panel: detail view that loads from Neo4j instantly
- Market analysis appears only when user clicks the button (takes ~20-30s with a loading spinner)

---

## Execution Order

### Phase 1: Backend (server + Neo4j queries)
1. `app/neo4j_client.py` — Connect to Neo4j, write Cypher queries for listing and detail
2. `app/market_service.py` — Thin wrapper around existing `market_scraper` for single-item real-time analysis
3. `app/server.py` — FastAPI app with 3 endpoints + static file serving

### Phase 2: Frontend
4. `app/static/style.css` — Dark theme design system
5. `app/static/index.html` — Page structure
6. `app/static/app.js` — Fetch calls, DOM updates, search filtering, market loading

### Phase 3: Test & Polish
7. Run the server, test all 3 endpoints
8. Polish loading states, error handling

---

## How to Run (Final Command)

```powershell
cd MAERII
python -m app.server
```

Opens at `http://localhost:8000` — one command, everything works.

---

## Open Questions

> [!IMPORTANT]
> **Neo4j Credentials**: What password did you set for your Neo4j database? The backend needs it to connect. (Default username is `neo4j`, default bolt URL is `bolt://localhost:7687`).

> [!IMPORTANT]
> **Market Module Neo4j Status**: You mentioned the 12k-line market Cypher import is not yet complete. The frontend will work fine without it — the real-time market panel fetches fresh data on-demand regardless. Should I skip/remove the market data from Neo4j entirely and only keep Module 1 data in the graph?
