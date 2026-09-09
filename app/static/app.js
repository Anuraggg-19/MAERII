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
let marketComparisonCache = {}; // Comparison-only provider results per session
let openSourceMarketCache = {}; // Isolated SearXNG + Crawl4AI + Ollama experiment results
let categoryCache = {};  // Cache product categories per session
let recommendationCache = {};  // Session-only results keyed by constraints and market evidence
let currentFilter = "all"; // "all" | "raw" | "derived"
let currentSort = "confidence"; // default sort
let showMatchedOnly = false; // false = show all scraped, true = LLM matched only
let comparisonFilter = "all"; // all | both | serper | scrapingdog | enriched
let comparisonRelevanceFilter = "relevant"; // relevant | needs_review | irrelevant | all
let comparisonQuery = "all";
let openSourceFilter = "accepted";

// ── DOM refs ───────────────────────────────────────────────────────────────

const materialListEl = document.getElementById("materialList");
const searchInputEl = document.getElementById("searchInput");
const sidebarFooterEl = document.getElementById("sidebarFooter");
const mainContentEl = document.getElementById("mainContent");
const emptyStateEl = document.getElementById("emptyState");
const detailViewEl = document.getElementById("detailView");

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  loadMaterials();
  searchInputEl.addEventListener("input", filterMaterials);
});

// ── Theme Toggle ───────────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem("maerii-theme") || "dark";
  applyTheme(saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
  localStorage.setItem("maerii-theme", next);
}

function applyTheme(theme) {
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  // Update button icon
  const btn = document.getElementById("themeToggle");
  if (btn) btn.textContent = theme === "light" ? "🌙" : "☀️";
}

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
    <!-- Tab Navigation -->
    <div class="detail-tabs">
      <button class="detail-tab active" onclick="switchTab('overview', this)">📋 Overview</button>
      <button class="detail-tab" onclick="switchTab('categories', this)">🏭 Categories</button>
      <button class="detail-tab" onclick="switchTab('market', this)">📊 Market</button>
      <button class="detail-tab" onclick="switchTab('recommendations', this)">🎯 Recommendations</button>
    </div>

    <!-- Tab 1: Overview -->
    <div class="tab-panel active" id="tab-overview">
      <div class="detail-header">
        <h1>${m.name}</h1>
        ${m.scientific_name ? `<div class="sci-name">${m.scientific_name}</div>` : ''}
        ${m.description ? `<div class="description">${m.description}</div>` : ''}
      </div>
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
      ${renderMaterialScores(m)}
      <div class="section-grid">
        ${renderSection('📍 States', g.states, 'state')}
        ${renderSection('🛠 Skills / Artisan Types', g.skills, 'skill')}
        ${renderSection('📦 Current Products', g.current_products, 'product')}
        ${renderSection('💡 Potential Products', g.potential_products, 'potential')}
        ${renderSection('🗺 Districts', g.districts, 'district')}
        ${renderSection('🏘 Clusters', g.clusters, 'cluster')}
      </div>
    </div>

    <!-- Tab 2: Product Categories & Processes -->
    <div class="tab-panel" id="tab-categories">
      <div class="market-section">
        <h2>🏭 Product Categories & Manufacturing Processes</h2>
        <div id="categoryPanel">
          ${categoryCache[m.mfp_id]
            ? renderCategoryResults(categoryCache[m.mfp_id])
            : `<button class="market-trigger" onclick="fetchCategories(${m.mfp_id})" id="categoryBtn">
                 🔬 Generate Product Categories & Processes
               </button>`
          }
        </div>
      </div>
    </div>

    <!-- Tab 3: Market Analysis -->
    <div class="tab-panel" id="tab-market">
      <div class="market-section" id="marketSection">
        <h2>📊 Real-Time Market Analysis</h2>
        <div id="marketPanel">
          ${categoryCache[m.mfp_id]
            ? (marketCache[m.mfp_id]
                ? renderMarketResults(marketCache[m.mfp_id])
                : renderMarketActions(m.mfp_id, true))
            : `<div class="market-locked">
                 <span class="lock-icon">🔒</span>
                 <p>Generate Product Categories first to unlock market analysis.</p>
                 <div class="substep">Market scraping uses the generated categories to search for relevant products across each category.</div>
               </div>${renderMarketActions(m.mfp_id, false)}`
          }
        </div>
      </div>
    </div>

    <!-- Tab 4: Recommendations -->
    <div class="tab-panel" id="tab-recommendations">
      <div class="market-section" id="recommendationSection">
        <h2>Product Recommendations</h2>
        <div id="recommendationPanel">
          ${renderRecommendationPanel(m.mfp_id, g.states || [])}
        </div>
      </div>
    </div>
  `;

  detailViewEl.innerHTML = html;
}

// ── Tab Switching ──────────────────────────────────────────────────────────

function switchTab(tabName, btnEl) {
  // Update tab buttons
  document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
  btnEl.classList.add('active');

  // Update tab panels
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('tab-' + tabName);
  if (panel) panel.classList.add('active');

  // Scroll main content to top
  mainContentEl.scrollTop = 0;
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
    invalidateRecommendationCache(mfpId);
    panel.innerHTML = renderMarketResults(data);
    const recommendationPanel = document.getElementById("recommendationPanel");
    if (recommendationPanel) recommendationPanel.innerHTML = renderRecommendationPanel(mfpId, getActiveMaterialStates());
  } catch (e) {
    panel.innerHTML = `<div class="error-box">Market analysis failed: ${e.message}</div>
      <button class="market-trigger" onclick="fetchMarket(${mfpId})" style="margin-top:12px">🔄 Retry</button>`;
  }
}

function renderMarketActions(mfpId, categoriesReady) {
  const marketAction = categoriesReady
    ? `<button class="market-trigger" onclick="fetchMarket(${mfpId})" id="marketBtn">🔍 Fetch Live Market Data</button>
       <div class="substep">Uses Serper listings and LLM market analysis.</div>`
    : '';
  return `<div class="market-action-row">
    <div class="market-action">${marketAction}</div>
    ${renderComparisonLauncher(mfpId)}
    ${renderOpenSourceLauncher(mfpId)}
  </div>`;
}

function renderComparisonLauncher(mfpId, compact = false) {
  return `<div class="market-action comparison-action${compact ? ' comparison-action-compact' : ''}">
    <button class="market-trigger comparison-trigger" onclick="fetchMarketComparison(${mfpId})">⚖ Compare Data Sources</button>
    <div class="substep">Serper versus Scrapingdog, including destination-page detail. Does not affect scores or recommendations.</div>
  </div>`;
}

function renderOpenSourceLauncher(mfpId, compact = false) {
  return `<div class="market-action open-source-action${compact ? ' comparison-action-compact' : ''}">
    <button class="market-trigger open-source-trigger" onclick="fetchOpenSourceMarket(${mfpId})">🌿 Compare Open-Source Pipeline</button>
    <div class="substep">SearXNG discovery, Crawl4AI page extraction, and local Ollama classification. Never changes production data.</div>
  </div>`;
}

async function fetchOpenSourceMarket(mfpId) {
  const panel = document.getElementById("marketPanel");
  if (!panel) return;
  panel.innerHTML = `<div class="market-loading"><div class="spinner"></div><p>Running the open-source market experiment...</p>
    <div class="substep">Discovering URLs with SearXNG, crawling pages with Crawl4AI, then classifying with your local Ollama model.</div>
    <div class="substep" style="margin-top:8px;">This can take a while on a local model and does not alter Serper, Gemini, scores, or recommendations.</div></div>`;
  try {
    const data = await api(`/api/materials/${mfpId}/market/open-source`, { method: "POST" });
    openSourceMarketCache[mfpId] = data;
    openSourceFilter = "accepted";
    panel.innerHTML = renderOpenSourceMarket(data, marketCache[mfpId]);
  } catch (e) {
    panel.innerHTML = `<div class="error-box">Open-source experiment failed: ${escapeHtml(e.message)}</div>
      <button class="market-trigger open-source-trigger" onclick="fetchOpenSourceMarket(${mfpId})" style="margin-top:12px">🔄 Retry open-source experiment</button>`;
  }
}

async function fetchMarketComparison(mfpId) {
  const panel = document.getElementById("marketPanel");
  if (!panel) return;
  panel.innerHTML = `<div class="market-loading">
    <div class="spinner"></div><p>Comparing product data sources...</p>
    <div class="substep">Searching both providers, then enriching a limited set of Scrapingdog destination pages.</div>
    <div class="substep" style="margin-top:8px;">This is comparison-only and does not change your market analysis.</div>
  </div>`;
  try {
    const data = await api(`/api/materials/${mfpId}/market/compare`, { method: "POST" });
    marketComparisonCache[mfpId] = data;
    comparisonFilter = "all";
    comparisonRelevanceFilter = "relevant";
    comparisonQuery = "all";
    panel.innerHTML = renderMarketComparison(data);
  } catch (e) {
    panel.innerHTML = `<div class="error-box">Source comparison failed: ${escapeHtml(e.message)}</div>
      <button class="market-trigger comparison-trigger" onclick="fetchMarketComparison(${mfpId})" style="margin-top:12px">🔄 Retry comparison</button>`;
  }
}

function comparisonProducts(data, selectedQuery = comparisonQuery) {
  const products = [];
  (data.queries || []).forEach(run => {
    if (selectedQuery !== "all" && run.query !== selectedQuery) return;
    ["serper", "scrapingdog"].forEach(provider => {
      (run[provider]?.products || []).forEach(product => products.push({ ...product, comparison_provider: provider, comparison_query: run.query }));
    });
  });
  const deduped = [];
  const seen = new Set();
  products.forEach(product => {
    const key = `${product.comparison_provider}:${product.product_id || `${product.title}|${product.seller}|${product.price}`}`;
    if (!seen.has(key)) { seen.add(key); deduped.push(product); }
  });
  const keysByProvider = { serper: new Set(), scrapingdog: new Set() };
  deduped.forEach(product => keysByProvider[product.comparison_provider].add(`${String(product.title || '').toLowerCase()}|${String(product.seller || '').toLowerCase()}|${product.price ?? ''}`));
  return deduped.map(product => ({ ...product, comparison_status: keysByProvider[product.comparison_provider === 'serper' ? 'scrapingdog' : 'serper'].has(`${String(product.title || '').toLowerCase()}|${String(product.seller || '').toLowerCase()}|${product.price ?? ''}`) ? 'both' : product.comparison_provider }));
}

function renderMarketComparison(data) {
  const overall = data.overall_comparison || {};
  const destination = data.scrapingdog_destination_pages || {};
  const relevance = data.relevance_filter || {};
  const products = comparisonProducts(data);
  const bothCount = products.filter(product => product.comparison_status === 'both').length;
  const enrichedCount = products.filter(product => product.destination_page?.status === 'complete').length;
  const queryOptions = (data.queries || []).map(run => `<option value="${escapeHtml(run.query)}" ${comparisonQuery === run.query ? 'selected' : ''}>${escapeHtml(run.query)}</option>`).join('');
  const completeness = destination.field_completeness || {};
  const addedFields = Object.entries(completeness).filter(([, value]) => value > 0).map(([field, value]) => `<span class="tag product">${escapeHtml(field.replaceAll('_', ' '))} ${Math.round(value * 100)}%</span>`).join('') || '<span class="empty-tag">No completed destination pages yet</span>';
  const relevanceCount = status => products.filter(product => (product.relevance?.status || 'needs_review') === status).length;
  return `<div class="comparison-results">
    <div class="comparison-heading"><div><h3>⚖ Source Comparison</h3><p>Raw product discovery comparison only. It never changes market scores, LLM matching, or recommendations.</p></div>
      <button class="match-toggle" onclick="returnToMarketActions(${data.mfp_id})">← Back to Market</button></div>
    <div class="market-stats comparison-stats">
      ${comparisonStat(overall.serper_unique_products || 0, 'Serper listings')}
      ${comparisonStat(overall.scrapingdog_unique_products || 0, 'Scrapingdog listings')}
      ${comparisonStat(`${overall.overlap_percentage || 0}%`, 'Provider overlap')}
      ${comparisonStat(overall.serper_only?.length || 0, 'Serper only')}
      ${comparisonStat(overall.scrapingdog_only?.length || 0, 'Scrapingdog only')}
      ${comparisonStat(`${destination.completed || 0}/${destination.attempted || 0}`, 'Destination pages')}
    </div>
    <div class="comparison-insight"><strong>What Scrapingdog adds:</strong> ${destination.completed || 0} retailer pages scraped. ${destination.errors ? `${destination.errors} failed. ` : ''} ${destination.skipped ? `${destination.skipped} skipped because no retailer link was available. ` : ''}Only relevant listings are sent to destination scraping first; uncertain listings are used only if needed, and rejected listings are never scraped.<div class="tag-list inline">${addedFields}</div></div>
    <div class="comparison-controls">
      <label>Query <select class="sort-select" onchange="setComparisonQuery(this.value, ${data.mfp_id})"><option value="all">All queries</option>${queryOptions}</select></label>
      <div class="filter-tabs comparison-filter-tabs">
        ${comparisonFilterButton('all', `All (${products.length})`, data.mfp_id)}
        ${comparisonFilterButton('both', `Both (${bothCount})`, data.mfp_id)}
        ${comparisonFilterButton('serper', `Serper only (${overall.serper_only?.length || 0})`, data.mfp_id)}
        ${comparisonFilterButton('scrapingdog', `Scrapingdog only (${overall.scrapingdog_only?.length || 0})`, data.mfp_id)}
        ${comparisonFilterButton('enriched', `Destination enriched (${enrichedCount})`, data.mfp_id)}
      </div>
    </div>
    <div class="relevance-controls">
      <div><strong>Relevance view</strong><span>${relevance.enabled ? 'Local rules only — no LLM classification.' : 'Filtering disabled.'}</span></div>
      <div class="filter-tabs comparison-filter-tabs">
        ${comparisonRelevanceFilterButton('relevant', `Relevant (${relevanceCount('relevant')})`, data.mfp_id)}
        ${comparisonRelevanceFilterButton('needs_review', `Needs review (${relevanceCount('needs_review')})`, data.mfp_id)}
        ${comparisonRelevanceFilterButton('irrelevant', `Rejected (${relevanceCount('irrelevant')})`, data.mfp_id)}
        ${comparisonRelevanceFilterButton('all', `All raw (${products.length})`, data.mfp_id)}
      </div>
      ${relevance.manual_profile_applied ? '<small>A targeted ambiguity profile is active for this material. Raw provider listings are still retained.</small>' : ''}
    </div>
    <div class="comparison-product-grid">${renderComparisonProducts(products)}</div>
    <div class="comparison-footer">Saved comparison: ${escapeHtml((data.comparison_file || '').split(/[\\/]/).pop() || 'session result')}</div>
  </div>`;
}

function comparisonStat(value, label) { return `<div class="stat-card"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div>`; }
function comparisonFilterButton(value, label, mfpId) { return `<button class="filter-tab ${comparisonFilter === value ? 'active' : ''}" onclick="setComparisonFilter('${value}', ${mfpId})">${label}</button>`; }
function comparisonRelevanceFilterButton(value, label, mfpId) { return `<button class="filter-tab ${comparisonRelevanceFilter === value ? 'active' : ''}" onclick="setComparisonRelevanceFilter('${value}', ${mfpId})">${label}</button>`; }

function renderComparisonProducts(products) {
  const filtered = products.filter(product => {
    const providerMatch = comparisonFilter === 'all' || product.comparison_status === comparisonFilter || (comparisonFilter === 'enriched' && product.destination_page?.status === 'complete');
    const relevanceMatch = comparisonRelevanceFilter === 'all' || (product.relevance?.status || 'needs_review') === comparisonRelevanceFilter;
    return providerMatch && relevanceMatch;
  });
  if (!filtered.length) return '<div class="empty-products">No products match this comparison filter.</div>';
  return filtered.map(product => {
    const page = product.destination_page?.product_page;
    const destination = product.destination_page || {};
    const image = page?.image_urls?.[0] || product.image_url;
    const sourceBadge = product.comparison_status === 'both' ? '<span class="comparison-badge both">Found by both</span>' : `<span class="comparison-badge ${product.comparison_provider}">${product.comparison_provider === 'serper' ? 'Serper only' : 'Scrapingdog only'}</span>`;
    const pageBadge = destination.status === 'complete' ? '<span class="comparison-badge enriched">✓ Destination scraped</span>' : '';
    const relevanceStatus = product.relevance?.status || 'needs_review';
    const relevanceLabel = relevanceStatus === 'relevant' ? 'Relevant' : relevanceStatus === 'irrelevant' ? 'Rejected' : relevanceStatus === 'not_evaluated' ? 'Not evaluated' : 'Needs review';
    const relevanceBadge = `<span class="comparison-badge relevance ${escapeHtml(relevanceStatus)}">${relevanceLabel}</span>`;
    const relevanceReason = product.relevance?.reason ? `<div class="relevance-reason">${escapeHtml(product.relevance.reason)}</div>` : '';
    const details = destination.status === 'complete' ? `<details class="destination-details"><summary>View destination-page details</summary><div class="destination-detail-grid">
      ${comparisonDetail('Brand', page.brand)}${comparisonDetail('Availability', page.availability)}${comparisonDetail('SKU', page.sku)}${comparisonDetail('Page price', page.price ? `${page.currency || ''} ${page.price}` : '')}
    </div>${page.description ? `<p>${escapeHtml(page.description)}</p>` : ''}${page.attributes?.length ? `<div class="tag-list inline">${page.attributes.map(attribute => `<span class="tag product">${escapeHtml(attribute.name)}: ${escapeHtml(attribute.value)}</span>`).join('')}</div>` : ''}${destination.destination_url ? `<a class="destination-link" target="_blank" rel="noopener" href="${escapeHtml(destination.destination_url)}">Open retailer page ↗</a>` : ''}</details>` : '';
    return `<article class="comparison-product-card ${destination.status === 'complete' ? 'has-destination' : ''}">
      ${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(product.title)}" class="product-image" onerror="this.remove()">` : '<div class="product-image no-image">📦</div>'}
      <div class="card-body"><div class="comparison-badges">${sourceBadge}${relevanceBadge}${pageBadge}</div>
      ${product.url ? `<a href="${escapeHtml(product.url)}" target="_blank" rel="noopener" class="card-title">${escapeHtml(product.title)}</a>` : `<div class="card-title">${escapeHtml(product.title)}</div>`}
      <div class="card-price-row"><span class="card-price">${product.price != null ? `₹${Math.round(product.price)}` : '—'}</span>${product.rating ? `<span class="card-rating">${escapeHtml(product.rating)} ★</span>` : ''}</div>
      <div class="card-meta"><span>${escapeHtml(product.seller || 'Unknown seller')}</span><span class="card-source">Rank ${escapeHtml(product.provider_rank || '—')}</span></div>${relevanceReason}${details}</div></article>`;
  }).join('');
}
function comparisonDetail(label, value) { return value ? `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>` : ''; }
function setComparisonFilter(filter, mfpId) { comparisonFilter = filter; const panel = document.getElementById('marketPanel'); if (panel && marketComparisonCache[mfpId]) panel.innerHTML = renderMarketComparison(marketComparisonCache[mfpId]); }
function setComparisonRelevanceFilter(filter, mfpId) { comparisonRelevanceFilter = filter; const panel = document.getElementById('marketPanel'); if (panel && marketComparisonCache[mfpId]) panel.innerHTML = renderMarketComparison(marketComparisonCache[mfpId]); }
function setComparisonQuery(query, mfpId) { comparisonQuery = query; comparisonFilter = 'all'; const panel = document.getElementById('marketPanel'); if (panel && marketComparisonCache[mfpId]) panel.innerHTML = renderMarketComparison(marketComparisonCache[mfpId]); }
function setOpenSourceFilter(filter, mfpId) { openSourceFilter = filter; const panel = document.getElementById('marketPanel'); if (panel && openSourceMarketCache[mfpId]) panel.innerHTML = renderOpenSourceMarket(openSourceMarketCache[mfpId], marketCache[mfpId]); }

function renderOpenSourceMarket(data, production) {
  const summary = data.summary || {};
  const products = data.products || [];
  const accepted = products.filter(product => ['raw', 'derived'].includes(product.local_classification?.status)).length;
  const productionReady = production?.status === 'complete';
  const filter = product => {
    const relevance = product.relevance?.status || 'needs_review';
    const classification = product.local_classification?.status || 'not_classified';
    if (openSourceFilter === 'accepted') return ['raw', 'derived'].includes(classification);
    if (openSourceFilter === 'relevant') return relevance === 'relevant';
    if (openSourceFilter === 'rejected') return relevance === 'irrelevant' || classification === 'invalid';
    return true;
  };
  const visible = products.filter(filter);
  const productCards = visible.length ? visible.map(product => {
    const relevance = product.relevance?.status || 'needs_review';
    const classification = product.local_classification || {};
    const state = classification.status || 'not_classified';
    const label = state === 'raw' ? 'Raw material' : state === 'derived' ? 'Derived product' : state === 'invalid' ? 'Invalid' : 'Not classified';
    return `<article class="comparison-product-card ${state === 'raw' || state === 'derived' ? 'has-destination' : ''}">
      ${product.image_url ? `<img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.title)}" class="product-image" onerror="this.remove()">` : '<div class="product-image no-image">📦</div>'}
      <div class="card-body"><div class="comparison-badges"><span class="comparison-badge open-source">Open source</span><span class="comparison-badge relevance ${escapeHtml(relevance)}">${escapeHtml(relevance.replaceAll('_', ' '))}</span><span class="comparison-badge local-classification ${escapeHtml(state)}">${escapeHtml(label)}</span></div>
      <a href="${escapeHtml(product.url)}" target="_blank" rel="noopener" class="card-title">${escapeHtml(product.title)}</a>
      <div class="card-price-row"><span class="card-price">${product.price != null ? `₹${Math.round(product.price)}` : '—'}</span>${product.rating ? `<span class="card-rating">${escapeHtml(product.rating)} ★</span>` : ''}</div>
      <div class="card-meta"><span>${escapeHtml(product.seller || product.source || 'Unknown seller')}</span><span class="card-source">${escapeHtml(product.extraction_method || 'page extract')}</span></div>
      ${product.relevance?.reason ? `<div class="relevance-reason">Relevance: ${escapeHtml(product.relevance.reason)}</div>` : ''}
      ${classification.reason ? `<div class="relevance-reason">Local model: ${escapeHtml(classification.reason)}</div>` : ''}</div></article>`;
  }).join('') : '<div class="empty-products">No products match this experiment filter.</div>';
  return `<div class="comparison-results open-source-results">
    <div class="comparison-heading"><div><h3>🌿 Open-Source Pipeline Experiment</h3><p>SearXNG open-web discovery → Crawl4AI product-page extraction → local Ollama classification. This is not Google Shopping data.</p></div><button class="match-toggle" onclick="returnToMarketActions(${data.mfp_id})">← Back to Market</button></div>
    <div class="pipeline-comparison-grid"><section><h4>Current production baseline</h4>${productionReady ? `<strong>${production.products_matched || 0} matched products</strong><span>Serper + configured cloud LLM</span>` : '<strong>Not loaded</strong><span>Run “Fetch Live Market Data” first to populate this browser-only baseline.</span>'}</section><section><h4>Open-source experiment</h4><strong>${accepted} accepted products</strong><span>${escapeHtml(data.pipeline?.discovery || 'SearXNG')} + ${escapeHtml(data.pipeline?.crawler || 'Crawl4AI')} + ${escapeHtml(data.pipeline?.classifier || 'Ollama')}</span></section></div>
    <div class="market-stats comparison-stats">
      ${comparisonStat(summary.discovered_urls || 0, 'URLs discovered')}${comparisonStat(`${summary.crawl_completed || 0}/${(summary.crawl_completed || 0) + (summary.crawl_failed || 0)}`, 'Pages crawled')}${comparisonStat(summary.products_extracted || 0, 'Products extracted')}${comparisonStat(accepted, 'Raw / derived')}${comparisonStat(summary.rejected || 0, 'Rejected')}${comparisonStat(`${Math.round((summary.ollama?.latency_ms || 0) / 1000)}s`, 'Local LLM time')}
    </div>
    <div class="comparison-insight"><strong>Experiment boundary:</strong> ${escapeHtml(data.note || '')}${summary.ollama?.error ? `<br><strong>Ollama warning:</strong> ${escapeHtml(summary.ollama.error)}` : ''}</div>
    <div class="filter-tabs comparison-filter-tabs open-source-filters">${openSourceFilterButton('accepted', `Accepted (${accepted})`, data.mfp_id)}${openSourceFilterButton('relevant', `Relevant (${summary.relevant || 0})`, data.mfp_id)}${openSourceFilterButton('rejected', `Rejected (${summary.rejected || 0})`, data.mfp_id)}${openSourceFilterButton('all', `All extracted (${products.length})`, data.mfp_id)}</div>
    <div class="comparison-product-grid">${productCards}</div>
    <div class="comparison-footer">Saved experiment: ${escapeHtml((data.comparison_file || '').split(/[\\/]/).pop() || 'session result')}</div>
  </div>`;
}

function openSourceFilterButton(value, label, mfpId) { return `<button class="filter-tab ${openSourceFilter === value ? 'active' : ''}" onclick="setOpenSourceFilter('${value}', ${mfpId})">${label}</button>`; }
function returnToMarketActions(mfpId) { const panel = document.getElementById('marketPanel'); if (panel) panel.innerHTML = marketCache[mfpId] ? renderMarketResults(marketCache[mfpId]) : renderMarketActions(mfpId, Boolean(categoryCache[mfpId])); }

function renderMarketResults(data) {
  if (data.status === "no_results") {
    return `${renderComparisonLauncher(data.mfp_id, true)}${renderOpenSourceLauncher(data.mfp_id, true)}
      <div class="error-box" style="border-color:var(--amber);color:var(--amber);background:var(--amber-bg);">
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
      ${renderComparisonLauncher(data.mfp_id, true)}
      ${renderOpenSourceLauncher(data.mfp_id, true)}

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

function getActiveMaterialStates() {
  return [...document.querySelectorAll('.section-card .tag.state')]
    .map(el => el.textContent.trim()).filter(Boolean);
}

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function stableStringify(value) {
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort()
      .map(key => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function recommendationEvidence(market) {
  return {
    market_summary: market.market_summary || {},
    competitor_analysis: market.competitor_analysis || {},
    top_products: market.top_products || [],
    product_demand_match: market.product_demand_match || {},
    regional_market_fit: market.regional_market_fit || [],
    seasonal_demand: market.seasonal_demand || {}
  };
}

function recommendationCacheKey(mfpId, constraints, market) {
  return String(mfpId) + ':' + stableStringify({
    constraints,
    market_context: recommendationEvidence(market)
  });
}

function invalidateRecommendationCache(mfpId) {
  const prefix = String(mfpId) + ':';
  Object.keys(recommendationCache).forEach(key => {
    if (key.startsWith(prefix)) delete recommendationCache[key];
  });
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.substring(0, len) + '…' : str;
}

// ── Product Categories ─────────────────────────────────────────────────────

function renderRecommendationPanel(mfpId, states) {
  if (!categoryCache[mfpId] || !marketCache[mfpId] || marketCache[mfpId].status !== 'complete') {
    const message = !categoryCache[mfpId]
      ? 'Generate Product Categories first to unlock recommendations.'
      : 'Fetch live market data first to unlock recommendations.';
    return '<div class="market-locked"><span class="lock-icon">Locked</span><p>' + message + '</p><div class="substep">Recommendations combine the generated processes with the current market analysis.</div></div>';
  }
  const uniqueStates = [...new Set(states)].sort();
  return '<form class="recommendation-form" onsubmit="submitRecommendations(event, ' + mfpId + ')">' +
    '<div class="recommendation-controls">' +
      '<label>Skill level<select name="artisan_skill_level"><option>Beginner</option><option>Intermediate</option><option>Advanced</option></select></label>' +
      '<label>Budget<select name="budget_constraint"><option>Low</option><option>Medium</option><option>High</option></select></label>' +
      '<label>Production time<select name="production_time"><option>Quick turnaround</option><option>Moderate</option><option>Long-term</option></select></label>' +
      '<label>Region<select name="region_context"><option>All listed regions</option>' + uniqueStates.map(state => '<option>' + escapeHtml(state) + '</option>').join('') + '</select></label>' +
    '</div><label class="motif-field">Cultural motifs (optional)<input name="cultural_motifs" maxlength="280" placeholder="e.g., Gond patterns, local storytelling"></label>' +
    '<button class="market-trigger" type="submit">Generate recommendations</button></form><div id="recommendationResults"></div>';
}

async function submitRecommendations(event, mfpId) {
  event.preventDefault();
  const form = event.currentTarget;
  const market = marketCache[mfpId];
  if (!market) return;
  const formData = new FormData(form);
  const constraints = {
    artisan_skill_level: formData.get('artisan_skill_level'),
    budget_constraint: formData.get('budget_constraint'),
    production_time: formData.get('production_time'),
    region_context: formData.get('region_context'),
    cultural_motifs: (formData.get('cultural_motifs') || '').trim() || null
  };
  const results = document.getElementById('recommendationResults');
  const key = recommendationCacheKey(mfpId, constraints, market);
  if (recommendationCache[key]) {
    results.innerHTML = renderRecommendationResults(recommendationCache[key], true);
    return;
  }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  results.innerHTML = '<div class="market-loading"><div class="spinner"></div><p>Generating product recommendations...</p></div>';
  try {
    const data = await api('/api/materials/' + mfpId + '/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...constraints, market_context: recommendationEvidence(market) })
    });
    recommendationCache[key] = data;
    results.innerHTML = renderRecommendationResults(data, false);
  } catch (error) {
    results.innerHTML = '<div class="error-box">Recommendation generation failed: ' + escapeHtml(error.message) + '</div>';
  } finally {
    button.disabled = false;
  }
}

function renderRecommendationResults(data, fromCache) {
  const recommendations = data.recommendations || [];
  if (!recommendations.length) return '<div class="error-box">No recommendations were returned.</div>';
  const cards = recommendations.map((item, index) => {
    const guideId = 'artisan-guide-' + data.mfp_id + '-' + index;
    const guide = (item.artisan_guide || []).map(step => '<li>' + escapeHtml(step) + '</li>').join('');
    const skills = (item.required_skills || []).map(s => '<span class="skill-chip">' + escapeHtml(s) + '</span>').join('');
    const skillsSection = skills ? '<div class="recommendation-skills"><div class="process-section-title">🛠 Required Skills</div><div class="skill-chips">' + skills + '</div></div>' : '';
    return '<article class="recommendation-card">' +
      '<div class="recommendation-card-header"><div><h3>' + escapeHtml(item.product_name) + '</h3><span>' + escapeHtml(item.category_name) + '</span></div><span class="diff-badge diff-' + String(item.difficulty || '').toLowerCase() + '">' + escapeHtml(item.difficulty) + '</span></div>' +
      '<p>' + escapeHtml(item.rationale) + '</p>' +
      '<div class="recommendation-metrics"><div><strong>INR ' + Number(item.unit_cost_inr).toFixed(2) + '</strong><span>Unit cost</span></div><div><strong>INR ' + Number(item.expected_selling_price_inr).toFixed(2) + '</strong><span>Expected price</span></div><div><strong>' + Number(item.profit_margin_percent).toFixed(1) + '%</strong><span>Margin</span></div><div><strong>' + Number(item.demand_score).toFixed(0) + '/100</strong><span>Demand</span></div></div>' +
      skillsSection +
      '<div class="recommendation-tags"><span class="pot-badge pot-' + String(item.export_potential || '').toLowerCase() + '">' + escapeHtml(item.export_potential) + ' export</span><span>' + escapeHtml(item.target_customer_segment) + '</span></div>' +
      '<button class="guide-toggle" type="button" onclick="document.getElementById(\'' + guideId + '\').classList.toggle(\'hidden\')">Artisan guide</button><ol class="artisan-guide hidden" id="' + guideId + '">' + guide + '</ol></article>';
  }).join('');
  return '<div class="recommendation-result-header">' + (fromCache ? 'Session result' : 'New recommendations') + '</div><div class="recommendation-grid">' + cards + '</div>';
}

async function fetchCategories(mfpId, forceRefresh = false) {
  const panel = document.getElementById("categoryPanel");

  panel.innerHTML = `
    <div class="market-loading">
      <div class="spinner"></div>
      <p>Generating product categories & manufacturing processes...</p>
      <div class="substep">Analyzing material properties with LLM — typically takes 3-6 seconds</div>
    </div>
  `;

  try {
    const url = `/api/materials/${mfpId}/categories` + (forceRefresh ? '?refresh=true' : '');
    const data = await api(url, { method: "POST" });
    categoryCache[mfpId] = data;
    if (forceRefresh) invalidateRecommendationCache(mfpId);
    panel.innerHTML = renderCategoryResults(data);

    // Unlock the market section now that categories exist
    const marketPanel = document.getElementById("marketPanel");
    if (marketPanel && !marketCache[mfpId]) {
      marketPanel.innerHTML = renderMarketActions(mfpId, true);
    }
    const recommendationPanel = document.getElementById("recommendationPanel");
    if (recommendationPanel) recommendationPanel.innerHTML = renderRecommendationPanel(mfpId, getActiveMaterialStates());
  } catch (e) {
    panel.innerHTML = `<div class="error-box">Product categorization failed: ${e.message}</div>
      <button class="market-trigger" onclick="fetchCategories(${mfpId})" style="margin-top:12px">🔄 Retry</button>`;
  }
}

function renderCategoryResults(data) {
  const categories = data.product_categories || [];
  if (!categories.length) {
    return `<div class="error-box" style="border-color:var(--amber);color:var(--amber);background:var(--amber-bg);">
      No product categories could be generated for this material.
    </div>`;
  }

  const cachedBadge = data.cached
    ? '<span class="cache-badge">⚡ Cached</span>'
    : `<span class="cache-badge fresh">✨ Generated in ${data.elapsed_seconds}s</span>`;

  const refreshBtn = `<button class="refresh-btn" onclick="fetchCategories(${data.mfp_id}, true)" title="Regenerate with LLM">🔄</button>`;

  let html = `
    <div class="category-header">
      <div class="category-stats">
        <span class="stat-chip">${categories.length} Categories</span>
        <span class="stat-chip">${categories.reduce((a, c) => a + (c.products || []).length, 0)} Products</span>
        ${cachedBadge}
      </div>
      ${refreshBtn}
    </div>
    <div class="category-accordion">
  `;

  categories.forEach((cat, catIdx) => {
    const products = cat.products || [];
    const catIcon = getCategoryIcon(cat.category_name);

    html += `
      <div class="accordion-item" id="catAccordion${catIdx}">
        <button class="accordion-header" onclick="toggleAccordion('catAccordion${catIdx}')">
          <div class="accordion-title">
            <span class="cat-icon">${catIcon}</span>
            <span class="cat-name">${cat.category_name}</span>
            <span class="cat-count">${products.length} product${products.length !== 1 ? 's' : ''}</span>
          </div>
          <span class="accordion-arrow">▸</span>
        </button>
        <div class="accordion-body">
          ${products.map(p => renderProductProcess(p)).join('')}
        </div>
      </div>
    `;
  });

  html += '</div>';
  return html;
}

function renderProductProcess(product) {
  const diffClass = product.difficulty === 'Easy' ? 'diff-easy'
    : product.difficulty === 'Hard' ? 'diff-hard' : 'diff-medium';

  const potentialClass = product.market_potential === 'high' ? 'pot-high'
    : product.market_potential === 'low' ? 'pot-low' : 'pot-medium';

  const steps = product.manufacturing_process || [];
  const skills = product.required_skills || [];

  return `
    <div class="process-card">
      <div class="process-header">
        <div class="process-title">${product.name}</div>
        <div class="process-badges">
          <span class="diff-badge ${diffClass}">${product.difficulty || 'Medium'}</span>
          <span class="pot-badge ${potentialClass}">${(product.market_potential || 'medium').charAt(0).toUpperCase() + (product.market_potential || 'medium').slice(1)} Demand</span>
        </div>
      </div>
      ${product.estimated_cost ? `<div class="process-cost">💰 Est. Cost: ${product.estimated_cost}</div>` : ''}

      <div class="process-section">
        <div class="process-section-title">📋 Manufacturing Process</div>
        <div class="process-timeline">
          ${steps.map((step, i) => `
            <div class="timeline-step">
              <div class="timeline-marker">
                <div class="timeline-number">${i + 1}</div>
                ${i < steps.length - 1 ? '<div class="timeline-line"></div>' : ''}
              </div>
              <div class="timeline-content">${step}</div>
            </div>
          `).join('')}
        </div>
      </div>

      <div class="process-section">
        <div class="process-section-title">🛠 Required Skills</div>
        <div class="skill-chips">
          ${skills.map(s => `<span class="skill-chip">${s}</span>`).join('')}
        </div>
      </div>
    </div>
  `;
}

function toggleAccordion(id) {
  const item = document.getElementById(id);
  if (!item) return;
  item.classList.toggle('open');
}

function getCategoryIcon(name) {
  const n = (name || '').toLowerCase();
  if (n.includes('oil') || n.includes('extract')) return '🫒';
  if (n.includes('food') || n.includes('beverage') || n.includes('culinar')) return '🍽️';
  if (n.includes('personal') || n.includes('cosmetic') || n.includes('soap') || n.includes('care')) return '🧴';
  if (n.includes('handicraft') || n.includes('craft') || n.includes('art')) return '🎨';
  if (n.includes('medicin') || n.includes('health') || n.includes('ayurved') || n.includes('herbal')) return '💊';
  if (n.includes('textile') || n.includes('fiber') || n.includes('fabric')) return '🧶';
  if (n.includes('construction') || n.includes('material') || n.includes('bio')) return '🏗️';
  return '📦';
}
