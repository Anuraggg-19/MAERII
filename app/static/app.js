/**
 * MAERII Knowledge Engine — Frontend Application
 *
 * Handles:
 *  - Loading material list from /api/materials
 *  - Search filtering
 *  - Loading material detail from /api/materials/{id}
 *  - Triggering real-time market analysis from /api/materials/{id}/market
 */

// ── State ──────────────────────────────────────────────────────────────────

let allMaterials = [];
let activeMfpId = null;
let marketCache = {};  // Cache market results per session

// ── DOM refs ───────────────────────────────────────────────────────────────

const materialListEl = document.getElementById("materialList");
const searchInputEl = document.getElementById("searchInput");
const sidebarFooterEl = document.getElementById("sidebarFooter");
const mainContentEl = document.getElementById("mainContent");
const emptyStateEl = document.getElementById("emptyState");
const detailViewEl = document.getElementById("detailView");

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadMaterials();
  searchInputEl.addEventListener("input", filterMaterials);
});

// ── API helpers ─────────────────────────────────────────────────────────────

async function api(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

// ── Material List ──────────────────────────────────────────────────────────

async function loadMaterials() {
  try {
    const data = await api("/api/materials");
    allMaterials = data.materials;
    renderMaterialList(allMaterials);
    sidebarFooterEl.textContent = `${allMaterials.length} materials loaded`;
  } catch (e) {
    sidebarFooterEl.textContent = "Failed to load";
    materialListEl.innerHTML = `<div style="padding:16px;color:#ef4444;font-size:12px;">
      Error: ${e.message}<br><br>Ensure Neo4j is running and the server is started.</div>`;
  }
}

function renderMaterialList(materials) {
  materialListEl.innerHTML = materials.map(m => `
    <div class="material-item ${m.mfp_id === activeMfpId ? 'active' : ''}"
         data-id="${m.mfp_id}"
         onclick="selectMaterial(${m.mfp_id})">
      <div class="mat-name">${m.name}</div>
      <div class="mat-meta">MSP: ₹${m.msp || '—'}/${m.unit || 'kg'} · ${m.category || ''}</div>
    </div>
  `).join("");
}

function filterMaterials() {
  const q = searchInputEl.value.toLowerCase().trim();
  if (!q) {
    renderMaterialList(allMaterials);
    return;
  }
  const filtered = allMaterials.filter(m =>
    m.name.toLowerCase().includes(q) ||
    (m.scientific_name || "").toLowerCase().includes(q) ||
    (m.category || "").toLowerCase().includes(q)
  );
  renderMaterialList(filtered);
}

// ── Material Detail ────────────────────────────────────────────────────────

async function selectMaterial(mfpId) {
  activeMfpId = mfpId;

  // Update sidebar active state
  document.querySelectorAll(".material-item").forEach(el => {
    el.classList.toggle("active", parseInt(el.dataset.id) === mfpId);
  });

  // Show loading
  emptyStateEl.classList.add("hidden");
  detailViewEl.classList.remove("hidden");
  detailViewEl.innerHTML = `<div class="market-loading"><div class="spinner"></div><p>Loading material data...</p></div>`;

  try {
    const data = await api(`/api/materials/${mfpId}`);
    renderDetail(data);
  } catch (e) {
    detailViewEl.innerHTML = `<div class="error-box">Failed to load material: ${e.message}</div>`;
  }
}

function renderDetail(data) {
  const m = data.material;
  const g = data.graph;

  const html = `
    <!-- Header -->
    <div class="detail-header">
      <h1>${m.name}</h1>
      ${m.scientific_name ? `<div class="sci-name">${m.scientific_name}</div>` : ''}
      ${m.description ? `<div class="description">${m.description}</div>` : ''}
    </div>

    <!-- Info Chips -->
    <div class="info-chips">
      <div class="chip highlight">
        <span class="chip-label">MSP</span>
        <span class="chip-value">₹${m.msp || '—'}/${m.unit || 'kg'}</span>
      </div>
      ${m.category ? `<div class="chip"><span class="chip-label">Category</span><span class="chip-value">${m.category}</span></div>` : ''}
      ${m.season ? `<div class="chip"><span class="chip-label">Season</span><span class="chip-value">${m.season}</span></div>` : ''}
      ${m.shelf_life ? `<div class="chip"><span class="chip-label">Shelf Life</span><span class="chip-value">${m.shelf_life}</span></div>` : ''}
      ${m.availability_band && m.availability_band !== 'unknown' ? `<div class="chip"><span class="chip-label">Availability</span><span class="chip-value">${m.availability_band}</span></div>` : ''}
    </div>

    <!-- Knowledge Graph Sections -->
    <div class="section-grid">
      ${renderSection('📍 States', g.states, 'state')}
      ${renderSection('🛠 Skills / Artisan Types', g.skills, 'skill')}
      ${renderSection('📦 Current Products', g.current_products, 'product')}
      ${renderSection('💡 Potential Products', g.potential_products, 'potential')}
      ${renderSection('🗺 Districts', g.districts, 'district')}
      ${renderSection('🏘 Clusters', g.clusters, 'cluster')}
    </div>

    <!-- Market Analysis Section -->
    <div class="market-section">
      <h2>📊 Real-Time Market Analysis</h2>
      <div id="marketPanel">
        ${marketCache[m.mfp_id]
          ? renderMarketResults(marketCache[m.mfp_id])
          : `<button class="market-trigger" onclick="fetchMarket(${m.mfp_id})" id="marketBtn">
               🔍 Fetch Live Market Data
             </button>`
        }
      </div>
    </div>
  `;

  detailViewEl.innerHTML = html;
}

function renderSection(title, items, tagClass) {
  const content = items && items.length > 0
    ? `<div class="tag-list">${items.map(i =>
        `<span class="tag ${tagClass}">${i.name}</span>`
      ).join("")}</div>`
    : `<span class="empty-tag">No data available</span>`;

  return `
    <div class="section-card">
      <h3>${title}</h3>
      ${content}
    </div>
  `;
}

// ── Market Analysis ────────────────────────────────────────────────────────

async function fetchMarket(mfpId) {
  const panel = document.getElementById("marketPanel");
  const btn = document.getElementById("marketBtn");

  // Show loading state
  panel.innerHTML = `
    <div class="market-loading">
      <div class="spinner"></div>
      <p>Analyzing live market data...</p>
      <div class="substep">Searching e-commerce platforms via Serper API, then classifying with Llama 3.3</div>
      <div class="substep" style="margin-top:8px;">This typically takes 20–40 seconds</div>
    </div>
  `;

  try {
    const data = await api(`/api/materials/${mfpId}/market`, { method: "POST" });
    marketCache[mfpId] = data;
    panel.innerHTML = renderMarketResults(data);
  } catch (e) {
    panel.innerHTML = `<div class="error-box">Market analysis failed: ${e.message}</div>
      <button class="market-trigger" onclick="fetchMarket(${mfpId})" style="margin-top:12px">🔄 Retry</button>`;
  }
}

function renderMarketResults(data) {
  if (data.status === "no_results") {
    return `<div class="error-box" style="border-color:var(--amber);color:var(--amber);background:var(--amber-bg);">
      No e-commerce products found for this material. The item may not be widely sold online.
    </div>`;
  }

  const s = data.market_summary || {};
  const c = data.competitor_analysis || {};
  const products = data.top_products || [];

  // Determine trend color
  const trend = s.trend || "stable";
  const trendArrow = trend === "rising" ? "↑" : trend === "declining" ? "↓" : "→";

  // Demand bar color
  const demandScore = s.demand_score || 0;
  let demandColor;
  if (demandScore >= 0.65) demandColor = "var(--green)";
  else if (demandScore >= 0.35) demandColor = "var(--amber)";
  else demandColor = "var(--red)";

  let html = `
    <div class="market-results">

      <!-- Stats row -->
      <div class="market-stats">
        <div class="stat-card">
          <div class="stat-value">${data.products_found || 0}</div>
          <div class="stat-label">Products Found</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.products_matched || 0}</div>
          <div class="stat-label">Matched</div>
        </div>
        <div class="stat-card">
          <div class="stat-value price">₹${Math.round(s.avg_price || 0)}</div>
          <div class="stat-label">Avg Price</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${s.avg_rating || '—'} ★</div>
          <div class="stat-label">Avg Rating</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${s.total_reviews || 0}</div>
          <div class="stat-label">Total Reviews</div>
        </div>
        <div class="stat-card">
          <div class="stat-value"><span class="trend-badge ${trend}">${trendArrow} ${trend}</span></div>
          <div class="stat-label">Trend</div>
        </div>
      </div>

      <!-- Demand Score Bar -->
      <div class="demand-bar-container">
        <div class="demand-label">
          <span>Demand Score</span>
          <span style="font-weight:700;color:${demandColor}">${(demandScore * 100).toFixed(1)}%</span>
        </div>
        <div class="demand-bar">
          <div class="demand-fill" style="width:${demandScore * 100}%;background:${demandColor}"></div>
        </div>
      </div>

      <!-- Competitor & Gaps -->
      <div class="section-grid">
  `;

  // Top brands
  if (c.top_brands && c.top_brands.length > 0) {
    html += `<div class="section-card">
      <h3>🏷 Top Sellers</h3>
      <div class="tag-list">${c.top_brands.map(b => `<span class="tag">${b}</span>`).join("")}</div>
      ${c.price_positioning ? `<div style="margin-top:10px;font-size:12px;color:var(--text-muted);">Positioning: <strong style="color:var(--text-secondary)">${c.price_positioning}</strong></div>` : ''}
    </div>`;
  }

  // Market gaps
  if (c.market_gaps && c.market_gaps.length > 0) {
    html += `<div class="section-card">
      <h3>🎯 Market Gaps</h3>
      <ul class="insight-list">${c.market_gaps.map(g => `<li>${g}</li>`).join("")}</ul>
    </div>`;
  }

  // LLM Insights
  if (c.llm_insights && c.llm_insights.length > 0) {
    html += `<div class="section-card">
      <h3>💡 Opportunities</h3>
      <ul class="insight-list">${c.llm_insights.map(i => `<li>${i}</li>`).join("")}</ul>
    </div>`;
  }

  // Demand drivers
  if (c.demand_drivers && c.demand_drivers.length > 0) {
    html += `<div class="section-card">
      <h3>📈 Demand Drivers</h3>
      <ul class="insight-list">${c.demand_drivers.map(d => `<li>${d}</li>`).join("")}</ul>
    </div>`;
  }

  // Top attributes
  if (s.top_attributes && s.top_attributes.length > 0) {
    html += `<div class="section-card">
      <h3>🏅 Top Attributes</h3>
      <div class="tag-list">${s.top_attributes.map(a =>
        `<span class="tag product">${a}</span>`
      ).join("")}</div>
    </div>`;
  }

  html += `</div>`;  // close section-grid

  // Product table
  if (products.length > 0) {
    html += `
      <div class="section-card" style="margin-top:16px;">
        <h3>🛒 Top Market Products</h3>
        <div style="overflow-x:auto;">
          <table class="product-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Price</th>
                <th>Rating</th>
                <th>Reviews</th>
                <th>Seller</th>
                <th>Platform</th>
              </tr>
            </thead>
            <tbody>
              ${products.map(p => `
                <tr>
                  <td>${p.url
                    ? `<a href="${p.url}" target="_blank" class="product-link">${p.title}</a>`
                    : `<span class="product-link">${p.title}</span>`
                  }</td>
                  <td class="price">${p.price ? '₹' + Math.round(p.price) : '—'}</td>
                  <td class="rating">${p.rating ? p.rating + ' ★' : '—'}</td>
                  <td>${p.review_count || 0}</td>
                  <td>${p.seller || '—'}</td>
                  <td>${p.source || '—'}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Elapsed time
  html += `
      <div style="margin-top:16px;font-size:11px;color:var(--text-muted);text-align:right;">
        Analysis completed in ${data.elapsed_seconds || '?'}s · Provider: ${data.provider || 'unknown'}
        · ${data.products_found || 0} scraped, ${data.products_matched || 0} matched
      </div>
    </div>
  `;

  return html;
}
