/**
 * MAERII Knowledge Engine — Frontend Application
 *
 * Handles:
 *  - Loading material list from /api/materials
 *  - Search filtering
 *  - Loading material detail from /api/materials/{id}
 *  - Triggering real-time market analysis from /api/materials/{id}/market
 *  - Product image cards with raw/derived tabs, sorting, and per-gram price
 */

// ── State ──────────────────────────────────────────────────────────────────

let allMaterials = [];
let activeMfpId = null;
let marketCache = {};  // Cache market results per session
let currentFilter = "all"; // "all" | "raw" | "derived"
let currentSort = "confidence"; // default sort
let showMatchedOnly = false; // false = show all scraped, true = LLM matched only

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

    <!-- Material Scores (if available) -->
    ${renderMaterialScores(m)}

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

// ── Material Scores ────────────────────────────────────────────────────────

function renderMaterialScores(m) {
  const hasSustainability = m.sustainability_score != null;
  const hasDurability = m.durability_rating != null;
  const hasProperties = m.strength != null;

  if (!hasSustainability && !hasDurability && !hasProperties) return '';

  let html = '<div class="scores-section">';

  // Sustainability Score gauge
  if (hasSustainability) {
    const score = parseFloat(m.sustainability_score) || 0;
    const pct = Math.round(score * 100);
    let color;
    if (pct >= 70) color = 'var(--green)';
    else if (pct >= 40) color = 'var(--amber)';
    else color = 'var(--red)';

    html += `
      <div class="score-card">
        <div class="score-header">🌿 Sustainability Score</div>
        <div class="score-gauge">
          <div class="gauge-circle" style="--pct: ${pct}; --color: ${color}">
            <span class="gauge-value">${pct}%</span>
          </div>
        </div>
      </div>
    `;
  }

  // Durability Badge
  if (hasDurability) {
    const rating = m.durability_rating || 'N/A';
    const lifespan = m.estimated_lifespan || '';
    const ratingClass = rating === 'high' ? 'badge-green' : rating === 'medium' ? 'badge-amber' : 'badge-red';

    html += `
      <div class="score-card">
        <div class="score-header">🛡 Durability</div>
        <div class="durability-info">
          <span class="durability-badge ${ratingClass}">${rating}</span>
          ${lifespan ? `<span class="lifespan-text">${lifespan}</span>` : ''}
        </div>
      </div>
    `;
  }

  // Material Properties chips
  if (hasProperties) {
    const props = [
      { label: 'Strength', value: m.strength },
      { label: 'Flexibility', value: m.flexibility },
      { label: 'Texture', value: m.texture },
      { label: 'Water Resist.', value: m.water_resistance },
      { label: 'Biodegradable', value: m.biodegradability },
      { label: 'Workability', value: m.workability },
    ].filter(p => p.value);

    html += `
      <div class="score-card wide">
        <div class="score-header">⚙ Material Properties</div>
        <div class="property-chips">
          ${props.map(p => `<div class="property-chip">
            <span class="prop-label">${p.label}</span>
            <span class="prop-value prop-${p.value}">${p.value}</span>
          </div>`).join('')}
        </div>
      </div>
    `;
  }

  html += '</div>';
  return html;
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

  // Show loading state
  panel.innerHTML = `
    <div class="market-loading">
      <div class="spinner"></div>
      <p>Analyzing live market data...</p>
      <div class="substep">Searching e-commerce platforms via Serper API, then classifying with LLM</div>
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

  // Seasonal Demand
  if (data.seasonal_demand) {
    const sd = data.seasonal_demand;
    html += `<div class="section-card">
      <h3>📅 Seasonal Demand</h3>
      ${sd.peak_seasons && sd.peak_seasons.length > 0 ? `<div class="tag-list">${sd.peak_seasons.map(s => `<span class="tag season">${s}</span>`).join('')}</div>` : ''}
      ${sd.seasonal_pattern ? `<p class="insight-text">${sd.seasonal_pattern}</p>` : ''}
      ${sd.off_season_strategy ? `<p class="insight-text muted">💡 Off-season: ${sd.off_season_strategy}</p>` : ''}
    </div>`;
  }

  // Product-Demand Match
  if (data.product_demand_match) {
    const pdm = data.product_demand_match;
    html += `<div class="section-card">
      <h3>✅ Product-Demand Match</h3>
      ${pdm.demand_alignment_score != null ? `<div class="demand-bar-container" style="margin-bottom:12px;">
        <div class="demand-label"><span>Alignment</span><span style="font-weight:700">${(pdm.demand_alignment_score * 100).toFixed(0)}%</span></div>
        <div class="demand-bar"><div class="demand-fill" style="width:${pdm.demand_alignment_score * 100}%;background:var(--accent)"></div></div>
      </div>` : ''}
      ${pdm.validated_products && pdm.validated_products.length > 0 ? `<div style="margin-bottom:8px;"><span class="mini-label">✅ Validated:</span> <div class="tag-list inline">${pdm.validated_products.map(p => `<span class="tag product">${p}</span>`).join('')}</div></div>` : ''}
      ${pdm.unvalidated_products && pdm.unvalidated_products.length > 0 ? `<div><span class="mini-label">⚠ Unvalidated:</span> <div class="tag-list inline">${pdm.unvalidated_products.map(p => `<span class="tag potential">${p}</span>`).join('')}</div></div>` : ''}
    </div>`;
  }

  // Regional Market Fit
  if (data.regional_market_fit && data.regional_market_fit.length > 0) {
    html += `<div class="section-card">
      <h3>🌍 Regional Market Fit</h3>
      <div class="regional-grid">
        ${data.regional_market_fit.map(r => `
          <div class="regional-item">
            <span class="regional-name">${r.region}</span>
            <span class="regional-fit">${r.fit}</span>
            ${r.confidence != null ? `<span class="regional-conf">${(r.confidence * 100).toFixed(0)}%</span>` : ''}
          </div>
        `).join('')}
      </div>
    </div>`;
  }

  html += `</div>`;  // close section-grid

  // Product cards with filter/sort controls
  const allProds = data.all_products || [];
  const matchedProds = data.top_products || [];
  const displayProds = showMatchedOnly ? matchedProds : allProds;
  if (allProds.length > 0) {
    html += renderProductCards(displayProds, data, allProds.length, matchedProds.length);
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

// ── Product Cards ──────────────────────────────────────────────────────────

function renderProductCards(products, data, totalScraped, totalMatched) {
  const rawCount = products.filter(p => p.product_type === "raw").length;
  const derivedCount = products.filter(p => p.product_type === "derived").length;

  const toggleLabel = showMatchedOnly
    ? `Show All Scraped (${totalScraped})`
    : `Show LLM Matched Only (${totalMatched})`;
  const toggleClass = showMatchedOnly ? '' : 'active';

  let html = `
    <div class="product-section" style="margin-top:16px;">
      <div class="product-header-row">
        <h3>🛒 Market Products</h3>
        <button class="match-toggle ${toggleClass}" onclick="toggleMatchedView(${data.mfp_id})" id="matchToggleBtn">
          ${toggleLabel}
        </button>
      </div>

      <!-- Filter/Sort Controls -->
      <div class="filter-bar">
        <div class="filter-tabs">
          <button class="filter-tab ${currentFilter === 'all' ? 'active' : ''}" onclick="setFilter('all', ${data.mfp_id})">All (${products.length})</button>
          <button class="filter-tab ${currentFilter === 'raw' ? 'active' : ''}" onclick="setFilter('raw', ${data.mfp_id})">Raw (${rawCount})</button>
          <button class="filter-tab ${currentFilter === 'derived' ? 'active' : ''}" onclick="setFilter('derived', ${data.mfp_id})">Derived (${derivedCount})</button>
        </div>
        <select class="sort-select" onchange="setSort(this.value, ${data.mfp_id})" id="sortSelect">
          <option value="confidence" ${currentSort === 'confidence' ? 'selected' : ''}>Relevance</option>
          <option value="price_asc" ${currentSort === 'price_asc' ? 'selected' : ''}>Price: Low → High</option>
          <option value="price_desc" ${currentSort === 'price_desc' ? 'selected' : ''}>Price: High → Low</option>
          <option value="pergram_asc" ${currentSort === 'pergram_asc' ? 'selected' : ''}>Per-gram: Low → High</option>
          <option value="pergram_desc" ${currentSort === 'pergram_desc' ? 'selected' : ''}>Per-gram: High → Low</option>
          <option value="rating_desc" ${currentSort === 'rating_desc' ? 'selected' : ''}>Rating: High → Low</option>
          <option value="reviews_desc" ${currentSort === 'reviews_desc' ? 'selected' : ''}>Reviews: Most → Least</option>
          <option value="name_asc" ${currentSort === 'name_asc' ? 'selected' : ''}>Name: A → Z</option>
        </select>
      </div>

      <!-- Product Grid -->
      <div class="product-grid" id="productGrid">
        ${renderFilteredProducts(products)}
      </div>
    </div>
  `;

  return html;
}

function renderFilteredProducts(products) {
  // Filter
  let filtered = products;
  if (currentFilter !== "all") {
    filtered = products.filter(p => p.product_type === currentFilter);
  }

  // Sort
  filtered = [...filtered].sort((a, b) => {
    switch (currentSort) {
      case "price_asc": return (a.price || 9999999) - (b.price || 9999999);
      case "price_desc": return (b.price || 0) - (a.price || 0);
      case "pergram_asc": return (a.price_per_gram || 9999999) - (b.price_per_gram || 9999999);
      case "pergram_desc": return (b.price_per_gram || 0) - (a.price_per_gram || 0);
      case "rating_desc": return (b.rating || 0) - (a.rating || 0);
      case "reviews_desc": return (b.review_count || 0) - (a.review_count || 0);
      case "name_asc": return (a.title || "").localeCompare(b.title || "");
      default: return (b.confidence || 0) - (a.confidence || 0);
    }
  });

  if (filtered.length === 0) {
    return `<div class="empty-products">No ${currentFilter} products found</div>`;
  }

  return filtered.map(p => {
    const typeBadge = p.product_type === "raw"
      ? '<span class="type-badge raw">Raw</span>'
      : '<span class="type-badge derived">Derived</span>';

    const priceHtml = p.price
      ? `<span class="card-price">₹${Math.round(p.price)}</span>`
      : '<span class="card-price muted">—</span>';

    const perGramHtml = p.price_per_gram
      ? `<span class="per-gram-price">₹${p.price_per_gram}/g</span>`
      : '';

    const ratingHtml = p.rating
      ? `<span class="card-rating">${p.rating} ★</span>`
      : '';

    const reviewsHtml = p.review_count > 0
      ? `<span class="card-reviews">(${p.review_count})</span>`
      : '';

    const imgSrc = p.image_url || '';
    const imgHtml = imgSrc
      ? `<img src="${imgSrc}" alt="${p.title}" class="product-image" onerror="this.onerror=null;this.src='';this.classList.add('no-image');this.alt='No image';">`
      : `<div class="product-image no-image">📦</div>`;

    const matchedBadge = p.is_matched
      ? '<span class="match-badge matched">✓ Matched</span>'
      : '<span class="match-badge unmatched">Unmatched</span>';

    return `
      <div class="product-card ${p.is_matched ? '' : 'unmatched-card'}">
        ${imgHtml}
        <div class="card-body">
          <div class="card-title-row">
            ${typeBadge}
            ${p.url
              ? `<a href="${p.url}" target="_blank" class="card-title">${truncate(p.title, 60)}</a>`
              : `<span class="card-title">${truncate(p.title, 60)}</span>`
            }
          </div>
          <div class="card-price-row">
            ${priceHtml}
            ${perGramHtml}
            ${matchedBadge}
          </div>
          <div class="card-meta">
            ${ratingHtml}${reviewsHtml}
            <span class="card-source">${p.source || p.seller || ''}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function getActiveProducts(mfpId) {
  const data = marketCache[mfpId];
  if (!data) return [];
  return showMatchedOnly ? (data.top_products || []) : (data.all_products || []);
}

function toggleMatchedView(mfpId) {
  showMatchedOnly = !showMatchedOnly;
  const data = marketCache[mfpId];
  if (data) {
    // Re-render the entire product section
    const panel = document.getElementById("marketPanel");
    if (panel) panel.innerHTML = renderMarketResults(data);
  }
}

function setFilter(filter, mfpId) {
  currentFilter = filter;
  const products = getActiveProducts(mfpId);
  document.getElementById("productGrid").innerHTML = renderFilteredProducts(products);
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.classList.toggle('active', tab.textContent.toLowerCase().startsWith(filter));
  });
}

function setSort(sort, mfpId) {
  currentSort = sort;
  const products = getActiveProducts(mfpId);
  document.getElementById("productGrid").innerHTML = renderFilteredProducts(products);
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.substring(0, len) + '…' : str;
}
