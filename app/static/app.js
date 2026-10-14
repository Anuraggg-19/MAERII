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
let categoryCache = {};  // Cache product categories per session
let recommendationCache = {};  // Session-only results keyed by constraints and market evidence
let enhancementCache = {};  // Session-only enhancement results keyed by mfpId:productName
let currentFilter = "all"; // "all" | "raw" | "derived"
let currentSort = "confidence"; // default sort
let showMatchedOnly = false; // false = show all scraped, true = LLM matched only
let activeCategoryFilter = 'all';
let activeEquipFilter = 'all';

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
    renderCategoryPills();
    renderMaterialList(allMaterials);
    sidebarFooterEl.textContent = `${allMaterials.length} materials loaded`;
  } catch (e) {
    sidebarFooterEl.textContent = "Failed to load";
    materialListEl.innerHTML = `<div style="padding:16px;color:#ef4444;font-size:12px;">
      Error: ${e.message}<br><br>Ensure Neo4j is running and the server is started.</div>`;
  }
}

function getMaterialCategoryIcon(category) {
  if (!category) return '🌿';
  const c = category.toLowerCase();
  if (c.includes('gum') || c.includes('resin')) return '💧';
  if (c.includes('seed') || c.includes('oil')) return '🌰';
  if (c.includes('honey') || c.includes('wax')) return '🍯';
  if (c.includes('leaf') || c.includes('leaves') || c.includes('herb')) return '🌿';
  if (c.includes('bamboo') || c.includes('wood') || c.includes('cane')) return '🪵';
  if (c.includes('flower')) return '🌸';
  if (c.includes('fruit') || c.includes('berry')) return '🫐';
  if (c.includes('bark') || c.includes('fiber')) return '🧶';
  if (c.includes('mushroom') || c.includes('fungi')) return '🍄';
  return '🌿';
}

function getMaterialBroadCategory(category) {
  const c = (category || '').toLowerCase();
  if (c.includes('agri')) return 'agriculture';
  return 'forest';
}

function renderCategoryPills() {
  const pillsContainer = document.getElementById('categoryPills');
  if (!pillsContainer) return;

  const totalCount = allMaterials.length;
  const forestCount = allMaterials.filter(m => getMaterialBroadCategory(m.category) === 'forest').length;
  const agriCount = allMaterials.filter(m => getMaterialBroadCategory(m.category) === 'agriculture').length;

  pillsContainer.innerHTML = `
    <button class="sidebar-pill ${activeCategoryFilter === 'all' ? 'active' : ''}" onclick="filterByCategory('all')">
      🌐 All <span class="pill-count">${totalCount}</span>
    </button>
    <button class="sidebar-pill ${activeCategoryFilter === 'forest' ? 'active' : ''}" onclick="filterByCategory('forest')">
      🌲 Forest Produce <span class="pill-count">${forestCount}</span>
    </button>
    <button class="sidebar-pill ${activeCategoryFilter === 'agriculture' ? 'active' : ''}" onclick="filterByCategory('agriculture')">
      🌾 Agriculture <span class="pill-count">${agriCount}</span>
    </button>
  `;
}

function filterByCategory(cat) {
  activeCategoryFilter = cat;
  renderCategoryPills();
  filterMaterials();
}

function renderMaterialList(materials) {
  materialListEl.innerHTML = materials.map(m => `
    <div class="material-item ${m.mfp_id === activeMfpId ? 'active' : ''}"
         data-id="${m.mfp_id}"
         onclick="selectMaterial(${m.mfp_id})">
      <div class="mat-name"><span class="mat-icon">${getMaterialCategoryIcon(m.category)}</span> ${m.name}</div>
      <div class="mat-meta">MSP: ₹${m.msp || '—'}/${m.unit || 'kg'} · ${m.category || ''}</div>
    </div>
  `).join("");
}

function filterMaterials() {
  const q = searchInputEl.value.toLowerCase().trim();
  const filtered = allMaterials.filter(m => {
    const matchSearch = !q || m.name.toLowerCase().includes(q) ||
      (m.scientific_name || "").toLowerCase().includes(q) ||
      (m.category || "").toLowerCase().includes(q);
    const broadCat = getMaterialBroadCategory(m.category);
    const matchCategory = activeCategoryFilter === 'all' || broadCat === activeCategoryFilter;
    return matchSearch && matchCategory;
  });
  renderMaterialList(filtered);
  if (sidebarFooterEl) {
    sidebarFooterEl.textContent = `${filtered.length} of ${allMaterials.length} materials`;
  }
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
      <button class="detail-tab active" onclick="switchTab('overview', this)">
        <span class="tab-icon">🌿</span>
        <span class="tab-label">Overview</span>
        <span class="tab-subtitle">Material Story & Value</span>
      </button>
      <button class="detail-tab" onclick="switchTab('categories', this)">
        <span class="tab-icon">🏭</span>
        <span class="tab-label">What to Make</span>
        <span class="tab-subtitle">Products & Recipes</span>
      </button>
      <button class="detail-tab" onclick="switchTab('market', this)">
        <span class="tab-icon">📊</span>
        <span class="tab-label">Market Prices</span>
        <span class="tab-subtitle">Real Online Demand</span>
      </button>
      <button class="detail-tab" onclick="switchTab('recommendations', this)">
        <span class="tab-icon">🎯</span>
        <span class="tab-label">Business Plan</span>
        <span class="tab-subtitle">Your Earning Blueprint</span>
      </button>
    </div>

    <!-- Tab 1: Overview -->
    <div class="tab-panel active" id="tab-overview">
      <div class="detail-header">
        <h1>${m.name}</h1>
        ${m.scientific_name ? `<div class="sci-name">${m.scientific_name}</div>` : ''}
        ${m.description ? `<div class="description">${m.description}</div>` : ''}
      </div>
      <div class="at-a-glance-card">
        <div class="at-a-glance-item">
          <span class="at-a-glance-icon">🌿</span>
          <div>
            <div class="at-a-glance-label">What is it?</div>
            <div class="at-a-glance-text">${m.description || m.name + ' — a Minor Forest Produce item collected by tribal communities.'}</div>
          </div>
        </div>
        <div class="at-a-glance-item">
          <span class="at-a-glance-icon">💰</span>
          <div>
            <div class="at-a-glance-label">Government Floor Price (MSP)</div>
            <div class="at-a-glance-text">₹${m.msp || '—'} per ${m.unit || 'kg'} — This is the minimum the government guarantees to pay collectors.</div>
          </div>
        </div>
        ${m.season ? `<div class="at-a-glance-item">
          <span class="at-a-glance-icon">📅</span>
          <div>
            <div class="at-a-glance-label">Best Collection Season</div>
            <div class="at-a-glance-text">${m.season}</div>
          </div>
        </div>` : ''}
        ${g.current_products && g.current_products.length > 0 ? `<div class="at-a-glance-item">
          <span class="at-a-glance-icon">🚀</span>
          <div>
            <div class="at-a-glance-label">Opportunity</div>
            <div class="at-a-glance-text">This material can be processed into ${g.current_products.length + (g.potential_products ? g.potential_products.length : 0)} different products for higher earnings.</div>
          </div>
        </div>` : ''}
      </div>
      ${m.msp ? `<div class="value-multiplier-banner">
        <div class="vm-stage">
          <div class="vm-label">Collector MSP</div>
          <div class="vm-price msp">₹${m.msp}/${m.unit || 'kg'}</div>
        </div>
        <div class="vm-arrow">→</div>
        <div class="vm-stage">
          <div class="vm-label">Potential Value After Processing</div>
          <div class="vm-price market">₹${Math.round(m.msp * 8)}–${Math.round(m.msp * 15)}/${m.unit || 'kg'}</div>
        </div>
        <div class="vm-multiplier">🚀 8–15x Value</div>
      </div>` : ''}
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
            : `<div class="journey-prompt">
                 <span class="journey-prompt-icon">✨</span>
                 <div class="journey-prompt-title">Discover What Products You Can Make</div>
                 <div class="journey-prompt-desc">Our AI will analyze this raw material and show you all the products you can create from it, with step-by-step instructions.</div>
                 <button class="market-trigger" onclick="fetchCategories(${m.mfp_id})" id="categoryBtn" style="margin-top:16px">
                   ✨ Show Me What I Can Make
                 </button>
               </div>`
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
                : `<button class="market-trigger" onclick="fetchMarket(${m.mfp_id})" id="marketBtn">
                     🔍 Fetch Live Market Data
                   </button>
                   <div class="substep" style="margin-top:8px;text-align:center;font-size:12px;color:var(--text-muted);">
                     Will search for real online product prices across the ${(categoryCache[m.mfp_id].product_categories || []).length} product types discovered
                   </div>`)
            : `<div class="journey-prompt">
                 <span class="journey-prompt-icon">🏭</span>
                 <div class="journey-prompt-title">First, Explore What You Can Make</div>
                 <div class="journey-prompt-desc">Go to the "What to Make" tab to discover all the products this material can become. Once done, you'll unlock real-time market prices here.</div>
               </div>`
          }
        </div>
      </div>
    </div>

    <!-- Tab 4: Recommendations -->
    <div class="tab-panel" id="tab-recommendations">
      <div class="market-section" id="recommendationSection" style="margin-top:0;padding-top:0;">
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
    const propertyDescriptions = {
      strength: { icon: '💪', title: 'Strength', descriptions: { high: 'Very strong — ideal for durable items like furniture and tools', medium: 'Moderate strength — good for baskets, trays, and home decor', low: 'Lightweight — best for decorative and packaging items' }},
      flexibility: { icon: '🤸', title: 'Flexibility', descriptions: { high: 'Very flexible — easy to bend and weave into shapes', medium: 'Somewhat flexible — can be shaped with gentle effort', low: 'Rigid — holds its shape well, good for structural items' }},
      texture: { icon: '✋', title: 'Texture', descriptions: { smooth: 'Smooth finish — naturally pleasing to touch', rough: 'Textured surface — gives a rustic, handmade feel', medium: 'Medium texture — versatile for many product types' }},
      water_resistance: { icon: '💧', title: 'Water Resistant', descriptions: { high: 'Yes — can handle moisture and outdoor use', medium: 'Partial — needs some protection from water', low: 'No — must keep dry, store indoors' }},
      biodegradability: { icon: '🌱', title: 'Eco-Friendly', descriptions: { high: '100% biodegradable & compostable', medium: 'Mostly eco-friendly with minimal processing', low: 'May need some chemical treatment' }},
      workability: { icon: '🛠️', title: 'Ease of Crafting', descriptions: { high: 'Very easy — can be shaped with basic hand tools at home', easy: 'Very easy — can be shaped with basic hand tools at home', medium: 'Moderate — needs some practice and basic workshop tools', moderate: 'Moderate — needs some practice and basic workshop tools', low: 'Skilled — requires training and specialized equipment', difficult: 'Skilled — requires training and specialized equipment' }}
    };
    
    const propList = ['strength', 'flexibility', 'texture', 'water_resistance', 'biodegradability', 'workability']
      .filter(key => m[key])
      .map(key => {
        const info = propertyDescriptions[key];
        const val = m[key].toLowerCase();
        const desc = (info.descriptions[val] || m[key]);
        return `<div class="human-prop">
          <span class="human-prop-icon">${info.icon}</span>
          <div class="human-prop-content">
            <div class="human-prop-title">${info.title}</div>
            <div class="human-prop-desc">${desc}</div>
          </div>
        </div>`;
      });
    
    if (propList.length > 0) {
      html += `<div class="score-card wide">
        <div class="score-header">⚙ What This Material Is Like</div>
        <div class="human-props-grid">${propList.join('')}</div>
      </div>`;
    }
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
      <p>Finding product prices from online stores...</p>
      <div class="substep">Scanning Amazon, Flipkart, and other stores for real prices</div>
      <div class="substep" style="margin-top:8px;">This usually takes about 30 seconds — please wait</div>
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

      <!-- Market Temp -->
      ${(() => {
        const tempLevel = demandScore >= 0.65 ? 'hot' : demandScore >= 0.35 ? 'warm' : 'cool';
        const tempEmoji = tempLevel === 'hot' ? '🔥' : tempLevel === 'warm' ? '🌤️' : '❄️';
        const tempText = tempLevel === 'hot' ? 'High Demand!' : tempLevel === 'warm' ? 'Moderate Demand' : 'Low Demand';
        const tempDesc = tempLevel === 'hot' 
          ? 'Customers are actively searching for and buying this online. Great opportunity!'
          : tempLevel === 'warm'
          ? 'Steady interest online. Good potential with the right product and pricing.'
          : 'Limited online demand currently. Consider niche positioning or local markets.';
        return `<div class="market-temp-card">
          <div class="temp-meter ${tempLevel}">${tempEmoji}</div>
          <div class="temp-info">
            <div class="temp-status ${tempLevel}">${tempText}</div>
            <div class="temp-desc">${tempDesc}</div>
          </div>
        </div>`;
      })()}

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
      <h3>🏷 Who's Selling This Online</h3>
      <div class="tag-list">${c.top_brands.map(b => `<span class="tag">${b}</span>`).join("")}</div>
      ${c.price_positioning ? `<div style="margin-top:10px;font-size:12px;color:var(--text-muted);">Positioning: <strong style="color:var(--text-secondary)">${c.price_positioning}</strong></div>` : ''}
    </div>`;
  }

  // Market gaps
  if (c.market_gaps && c.market_gaps.length > 0) {
    html += `<div class="section-card">
      <h3>💡 What Buyers Are Looking For</h3>
      <ul class="insight-list">${c.market_gaps.map(g => `<li>${g}</li>`).join("")}</ul>
    </div>`;
  }

  // LLM Insights
  if (c.llm_insights && c.llm_insights.length > 0) {
    html += `<div class="section-card">
      <h3>🌟 Why People Are Buying This</h3>
      <ul class="insight-list">${c.llm_insights.map(i => `<li>${i}</li>`).join("")}</ul>
    </div>`;
  }

  // Demand drivers
  if (c.demand_drivers && c.demand_drivers.length > 0) {
    html += `<div class="section-card">
      <h3>📈 What's Driving Demand</h3>
      <ul class="insight-list">${c.demand_drivers.map(d => `<li>${d}</li>`).join("")}</ul>
    </div>`;
  }

  // Top attributes
  if (s.top_attributes && s.top_attributes.length > 0) {
    html += `<div class="section-card">
      <h3>⭐ What Customers Value Most</h3>
      <div class="tag-list">${s.top_attributes.map(a =>
        `<span class="tag product">${a}</span>`
      ).join("")}</div>
    </div>`;
  }

  // Seasonal Demand
  if (data.seasonal_demand) {
    const sd = data.seasonal_demand;
    html += `<div class="section-card">
      <h3>📅 When Do People Buy This?</h3>
      ${sd.peak_seasons && sd.peak_seasons.length > 0 ? `<div class="tag-list">${sd.peak_seasons.map(s => `<span class="tag season">${s}</span>`).join('')}</div>` : ''}
      ${sd.seasonal_pattern ? `<p class="insight-text">${sd.seasonal_pattern}</p>` : ''}
      ${sd.off_season_strategy ? `<p class="insight-text muted">💡 Off-season: ${sd.off_season_strategy}</p>` : ''}
    </div>`;
  }

  // Product-Demand Match
  if (data.product_demand_match) {
    const pdm = data.product_demand_match;
    html += `<div class="section-card">
      <h3>✅ How Well Do Current Products Match Demand?</h3>
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
      <h3>🌍 Where Does This Sell Best?</h3>
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
        Market scan completed in ${data.elapsed_seconds || '?'} seconds · Found ${data.products_found || 0} products, ${data.products_matched || 0} direct matches
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
    ? `Show All Products (${totalScraped})`
    : `Show Best Matches Only (${totalMatched})`;
  const toggleClass = showMatchedOnly ? '' : 'active';

  let html = `
    <div class="product-section" style="margin-top:16px;">
      <div class="product-header-row">
        <h3>🛒 Products Available Online</h3>
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
      ? '<span class="match-badge matched friendly-badge direct">🌟 Direct Match</span>'
      : '<span class="match-badge unmatched friendly-badge related">💡 Related</span>';

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
    const isNoCat = !categoryCache[mfpId];
    const stepName = isNoCat ? 'What to Make' : 'Market Prices';
    const icon = isNoCat ? '🏭' : '📊';
    return `<div class="journey-prompt">
      <span class="journey-prompt-icon">${icon}</span>
      <div class="journey-prompt-title">Complete the "${stepName}" Step First</div>
      <div class="journey-prompt-desc">${isNoCat 
        ? 'Discover what products you can make from this material, then get market data, and finally receive your custom business plan.'
        : 'Fetch live market data first so recommendations can include real pricing and demand information.'}</div>
    </div>`;
  }
  
  const uniqueStates = [...new Set(states)].sort();

  // Region-to-motif mapping for smart cultural motif suggestions
  const regionMotifs = {
    'Madhya Pradesh': 'Gond art patterns',
    'Maharashtra': 'Warli art patterns',
    'Rajasthan': 'Mandana / Phad art',
    'Odisha': 'Pattachitra / Saura art',
    'Jharkhand': 'Sohrai / Khovar art',
    'Chhattisgarh': 'Pithora / Dhokra patterns',
    'Gujarat': 'Rogan / Ahir embroidery motifs',
    'West Bengal': 'Patachitra / Kantha motifs',
    'Andhra Pradesh': 'Cheriyal / Nirmal art',
    'Telangana': 'Cheriyal scroll motifs',
    'Karnataka': 'Lambani / Mysore motifs',
    'Tamil Nadu': 'Kolam / Tanjore motifs',
    'Kerala': 'Mural / Theyyam motifs',
    'Assam': 'Muga silk / Jaapi motifs',
    'Nagaland': 'Naga tribal motifs',
    'Meghalaya': 'Khasi / Garo motifs',
    'Manipur': 'Meitei / Moirang motifs',
    'Mizoram': 'Puan / Mizo motifs',
    'Tripura': 'Risa / Tripuri motifs',
    'Arunachal Pradesh': 'Monpa / Apatani motifs',
    'Sikkim': 'Lepcha / Bhutia motifs',
    'Himachal Pradesh': 'Chamba Rumal / Kinnauri motifs',
    'Uttarakhand': 'Aipan art patterns',
    'Bihar': 'Madhubani art patterns',
    'Jammu & Kashmir': 'Pashmina / Papier-mâché motifs',
    'Punjab': 'Phulkari motifs',
    'Goa': 'Kunbi motifs',
  };

  const regionOptions = uniqueStates.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
  
  return `
    <div id="wizardFormWrapper">
    <form class="wizard-form wizard-command-center" onsubmit="submitRecommendations(event, ${mfpId})">
      <div class="wizard-layout-split">
        <!-- Left Column: The 4 Questions -->
        <div class="wizard-left-panel">
          <div class="wizard-panel-header">
            <span class="wizard-panel-title-icon">⚙️</span>
            <div>
              <div class="wizard-panel-title">Artisan & Production Preferences</div>
              <div class="wizard-panel-subtitle">Customize the business model for your community or enterprise</div>
            </div>
          </div>

          <div class="wizard-grid-2x2">
            <!-- Question 1: Skill -->
            <div class="wizard-step-group">
              <div class="wizard-step-title">
                <span class="wizard-step-number">1</span>
                Who is making the product?
              </div>
              <div class="wizard-card-options">
                <label class="wizard-card-option selected" onclick="selectWizardOption(this, 'skill', 'Beginner')">
                  <input type="radio" name="artisan_skill_level" value="Beginner" checked style="display:none">
                  <span class="wizard-card-icon">👩‍🌾</span>
                  <span class="wizard-card-text">Beginner</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'skill', 'Intermediate')">
                  <input type="radio" name="artisan_skill_level" value="Intermediate" style="display:none">
                  <span class="wizard-card-icon">👨‍🎨</span>
                  <span class="wizard-card-text">Intermediate</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'skill', 'Advanced')">
                  <input type="radio" name="artisan_skill_level" value="Advanced" style="display:none">
                  <span class="wizard-card-icon">🏆</span>
                  <span class="wizard-card-text">Advanced</span>
                </label>
              </div>
            </div>

            <!-- Question 2: Budget -->
            <div class="wizard-step-group">
              <div class="wizard-step-title">
                <span class="wizard-step-number">2</span>
                Starting capital / budget?
              </div>
              <div class="wizard-card-options">
                <label class="wizard-card-option selected" onclick="selectWizardOption(this, 'budget', 'Under ₹5K')">
                  <input type="radio" name="budget_constraint" value="Low" checked style="display:none">
                  <span class="wizard-card-icon">🌱</span>
                  <span class="wizard-card-text">Under ₹5K</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'budget', '₹5K–25K')">
                  <input type="radio" name="budget_constraint" value="Medium" style="display:none">
                  <span class="wizard-card-icon">🌿</span>
                  <span class="wizard-card-text">₹5K–25K</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'budget', 'Over ₹25K')">
                  <input type="radio" name="budget_constraint" value="High" style="display:none">
                  <span class="wizard-card-icon">🌳</span>
                  <span class="wizard-card-text">Over ₹25K</span>
                </label>
              </div>
            </div>

            <!-- Question 3: Turnaround -->
            <div class="wizard-step-group">
              <div class="wizard-step-title">
                <span class="wizard-step-number">3</span>
                Production speed needed?
              </div>
              <div class="wizard-card-options">
                <label class="wizard-card-option selected" onclick="selectWizardOption(this, 'speed', 'Quick')">
                  <input type="radio" name="production_time" value="Quick turnaround" checked style="display:none">
                  <span class="wizard-card-icon">⚡</span>
                  <span class="wizard-card-text">Quick</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'speed', 'Moderate')">
                  <input type="radio" name="production_time" value="Moderate" style="display:none">
                  <span class="wizard-card-icon">📅</span>
                  <span class="wizard-card-text">Moderate</span>
                </label>
                <label class="wizard-card-option" onclick="selectWizardOption(this, 'speed', 'Long-term')">
                  <input type="radio" name="production_time" value="Long-term" style="display:none">
                  <span class="wizard-card-icon">🏗️</span>
                  <span class="wizard-card-text">Long-term</span>
                </label>
              </div>
            </div>

            <!-- Question 4: Region & Cultural Motifs -->
            <div class="wizard-step-group">
              <div class="wizard-step-title">
                <span class="wizard-step-number">4</span>
                Target region & cultural motifs
              </div>
              <div class="wizard-region-box">
                ${uniqueStates.length > 0 ? `
                <select class="wizard-region-dropdown" name="region_context" id="regionDropdown_${mfpId}" onchange="updateMotifSuggestion(this)">
                  <option value="All listed regions">🗺️ All Listed Regions</option>
                  ${regionOptions}
                </select>` : '<input type="hidden" name="region_context" value="All listed regions">'}

                <div class="wizard-motif-row" id="motifRow_${mfpId}">
                  <label class="wizard-motif-toggle">
                    <input type="checkbox" id="motifCheckbox_${mfpId}" name="include_motifs" onchange="toggleMotifInput(${mfpId})">
                    <span class="motif-toggle-label" id="motifLabel_${mfpId}">Include local tribal art motifs in designs?</span>
                  </label>
                  <input type="hidden" name="cultural_motifs" id="motifValue_${mfpId}" value="">
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Column: Business Plan Launch Panel -->
        <div class="wizard-right-panel">
          <div class="wizard-summary-badge">⚡ AI Feasibility Engine</div>
          <div class="wizard-summary-heading">Ready to Plan?</div>
          <div class="wizard-summary-desc">We will tailor product suggestions, equipment requirements, and profit calculations based on your selected criteria:</div>

          <div class="wizard-live-summary">
            <div class="summary-pill"><span class="summary-pill-label">Skill</span><strong id="summaryPillSkill">Beginner</strong></div>
            <div class="summary-pill"><span class="summary-pill-label">Budget</span><strong id="summaryPillBudget">Under ₹5K</strong></div>
            <div class="summary-pill"><span class="summary-pill-label">Timeline</span><strong id="summaryPillSpeed">Quick</strong></div>
            <div class="summary-pill"><span class="summary-pill-label">Region</span><strong id="summaryPillRegion">All Regions</strong></div>
          </div>

          <div class="wizard-perks-list">
            <div class="perk-item">✓ Live e-commerce demand benchmarks</div>
            <div class="perk-item">✓ Step-by-step artisan guides</div>
            <div class="perk-item">✓ Monthly profit calculator & margins</div>
          </div>

          <button class="blueprint-cta-btn wizard-side-btn" type="submit">
            🎯 Generate My Business Plan
          </button>
          <div class="wizard-sub-hint">⚡ Generates in ~5 seconds</div>
        </div>
      </div>
    </form>
    </div>
    <div id="recommendationResults"></div>`;
}

// Map region selection to cultural motif suggestion
function updateMotifSuggestion(dropdown) {
  const mfpId = dropdown.id.replace('regionDropdown_', '');
  const region = dropdown.value;
  const label = document.getElementById('motifLabel_' + mfpId);
  const checkbox = document.getElementById('motifCheckbox_' + mfpId);
  const hiddenInput = document.getElementById('motifValue_' + mfpId);
  const pillRegion = document.getElementById('summaryPillRegion');
  if (pillRegion) pillRegion.textContent = region === 'All listed regions' ? 'All Regions' : region;
  
  const regionMotifs = {
    'Madhya Pradesh': 'Gond art patterns',
    'Maharashtra': 'Warli art patterns',
    'Rajasthan': 'Mandana / Phad art',
    'Odisha': 'Pattachitra / Saura art',
    'Jharkhand': 'Sohrai / Khovar art',
    'Chhattisgarh': 'Pithora / Dhokra patterns',
    'Gujarat': 'Rogan / Ahir embroidery motifs',
    'West Bengal': 'Patachitra / Kantha motifs',
    'Andhra Pradesh': 'Cheriyal / Nirmal art',
    'Telangana': 'Cheriyal scroll motifs',
    'Karnataka': 'Lambani / Mysore motifs',
    'Tamil Nadu': 'Kolam / Tanjore motifs',
    'Kerala': 'Mural / Theyyam motifs',
    'Bihar': 'Madhubani art patterns',
    'Uttarakhand': 'Aipan art patterns',
    'Himachal Pradesh': 'Chamba Rumal / Kinnauri motifs',
    'Assam': 'Muga silk / Jaapi motifs',
  };

  const motif = regionMotifs[region];
  if (motif) {
    label.textContent = `Include ${motif} in your product designs?`;
    if (checkbox.checked) hiddenInput.value = motif;
  } else {
    label.textContent = 'Include local tribal art motifs in designs?';
    if (checkbox.checked) hiddenInput.value = 'Traditional tribal designs';
  }
}

function toggleMotifInput(mfpId) {
  const checkbox = document.getElementById('motifCheckbox_' + mfpId);
  const hiddenInput = document.getElementById('motifValue_' + mfpId);
  const dropdown = document.getElementById('regionDropdown_' + mfpId);

  if (checkbox.checked) {
    const regionMotifs = {
      'Madhya Pradesh': 'Gond art patterns', 'Maharashtra': 'Warli art patterns',
      'Rajasthan': 'Mandana / Phad art', 'Odisha': 'Pattachitra / Saura art',
      'Jharkhand': 'Sohrai / Khovar art', 'Chhattisgarh': 'Pithora / Dhokra patterns',
      'Gujarat': 'Rogan / Ahir embroidery motifs', 'West Bengal': 'Patachitra / Kantha motifs',
      'Bihar': 'Madhubani art patterns', 'Uttarakhand': 'Aipan art patterns',
    };
    const region = dropdown ? dropdown.value : '';
    hiddenInput.value = regionMotifs[region] || 'Traditional tribal designs';
  } else {
    hiddenInput.value = '';
  }
}

function selectWizardOption(label, type, text) {
  const group = label.closest('.wizard-card-options');
  group.querySelectorAll('.wizard-card-option').forEach(opt => opt.classList.remove('selected'));
  label.classList.add('selected');
  label.querySelector('input').checked = true;

  if (type === 'skill') {
    const el = document.getElementById('summaryPillSkill');
    if (el) el.textContent = text;
  } else if (type === 'budget') {
    const el = document.getElementById('summaryPillBudget');
    if (el) el.textContent = text;
  } else if (type === 'speed') {
    const el = document.getElementById('summaryPillSpeed');
    if (el) el.textContent = text;
  }
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
  const formWrapper = document.getElementById('wizardFormWrapper');
  const key = recommendationCacheKey(mfpId, constraints, market);
  if (recommendationCache[key]) {
    if (formWrapper) formWrapper.style.display = 'none';
    results.innerHTML = renderRecommendationResults(recommendationCache[key], true);
    return;
  }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;margin-right:8px;display:inline-block;vertical-align:middle"></div> Creating your plan...';
  results.innerHTML = '<div class="market-loading"><div class="spinner"></div><p>Creating your custom business plan...</p></div>';
  try {
    const data = await api('/api/materials/' + mfpId + '/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...constraints, market_context: recommendationEvidence(market) })
    });
    recommendationCache[key] = data;
    if (formWrapper) formWrapper.style.display = 'none';
    results.innerHTML = renderRecommendationResults(data, false);
  } catch (error) {
    results.innerHTML = '<div class="error-box">Recommendation generation failed: ' + escapeHtml(error.message) + '</div>';
    button.disabled = false;
    button.innerHTML = '🎯 Generate My Business Plan';
  }
}

function showWizardAgain() {
  const formWrapper = document.getElementById('wizardFormWrapper');
  const results = document.getElementById('recommendationResults');
  if (formWrapper) formWrapper.style.display = '';
  if (results) results.innerHTML = '';
}

function renderRecommendationResults(data, fromCache) {
  const recommendations = data.recommendations || [];
  if (!recommendations.length) return '<div class="error-box">No recommendations were returned.</div>';
  const cards = recommendations.map((item, index) => {
    const guideId = 'artisan-guide-' + data.mfp_id + '-' + index;
    const guide = (item.artisan_guide || []).map(step => '<li>' + escapeHtml(step) + '</li>').join('');
    const skills = (item.required_skills || []).map(s => '<span class="skill-chip">' + escapeHtml(s) + '</span>').join('');
    const skillsSection = skills ? '<div class="recommendation-skills"><div class="process-section-title">🛠 Required Skills</div><div class="skill-chips">' + skills + '</div></div>' : '';

    // Demand label (High / Medium / Low)
    const demandLabel = item.demand_label || 'Medium';
    const demandClass = demandLabel === 'High' ? 'demand-high' : demandLabel === 'Low' ? 'demand-low' : 'demand-medium';

    // Product origin badge
    const originLabel = item.product_origin === 'Existing Product' ? 'Existing Product' : '✨ New Product Idea';
    const originClass = item.product_origin === 'Existing Product' ? 'origin-existing' : 'origin-ai';
    const originIcon = item.product_origin === 'Existing Product' ? '📦' : '✨';

    // Pricing unit badge & subtitle
    const pricingUnit = item.pricing_unit || '';
    const unitBadge = pricingUnit ? '<span class="pricing-unit-badge">⚖️ ' + escapeHtml(pricingUnit) + '</span>' : '';
    const unitSubtitle = pricingUnit ? '<br><em class="metric-unit">(' + escapeHtml(pricingUnit) + ')</em>' : '';

    return '<article class="recommendation-card clickable-rec" onclick="openEnhancementModal(' + data.mfp_id + ', ' + index + ')" data-rec-index="' + index + '">' +
      '<div class="rec-click-hint"><span>✨ Open Full Business Blueprint</span></div>' +
      '<div class="recommendation-card-header"><div><h3>' + escapeHtml(item.product_name) + '</h3>' +
      '<div class="rec-badge-row">' +
        '<span class="product-origin-badge ' + originClass + '">' + originIcon + ' ' + escapeHtml(originLabel) + '</span>' +
        unitBadge +
      '</div>' +
      '<span>' + escapeHtml(item.category_name) + '</span></div>' +
      '<span class="diff-badge diff-' + String(item.difficulty || '').toLowerCase() + '">' + escapeHtml(item.difficulty) + '</span></div>' +
      '<p>' + escapeHtml(item.rationale) + '</p>' +
      '<div class="recommendation-metrics">' +
        '<div><strong>INR ' + Number(item.unit_cost_inr).toFixed(2) + '</strong><span>Making Cost' + unitSubtitle + '</span></div>' +
        '<div><strong>INR ' + Number(item.expected_selling_price_inr).toFixed(2) + '</strong><span>Selling Price' + unitSubtitle + '</span></div>' +
        '<div><strong>' + Number(item.profit_margin_percent).toFixed(1) + '%</strong><span>Your Profit %</span></div>' +
        '<div><strong><span class="demand-badge ' + demandClass + '">' + escapeHtml(demandLabel) + '</span></strong><span>Buyer Demand</span></div>' +
      '</div>' +
      skillsSection +
      '<div class="recommendation-tags"><span class="pot-badge pot-' + String(item.export_potential || '').toLowerCase() + '">' + escapeHtml(item.export_potential) + ' export</span><span>' + escapeHtml(item.target_customer_segment) + '</span></div>' +
      '<div style="display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap;">' +
        '<button class="calc-income-btn" type="button" onclick="event.stopPropagation();selectProductForCalc(' + index + ')">📊 Calculate Monthly Income</button>' +
        '<button class="guide-toggle" type="button" style="margin-top:0" onclick="event.stopPropagation();document.getElementById(\'' + guideId + '\').classList.toggle(\'hidden\')">Artisan guide</button>' +
      '</div>' +
      '<ol class="artisan-guide hidden" id="' + guideId + '">' + guide + '</ol></article>';
  }).join('');
  
  // Store recommendations data on window for modal & calculator access
  window._lastRecommendationData = data;
  
  const firstRec = recommendations[0];
  const optionsHtml = recommendations.map((item, idx) => `
    <option value="${idx}">📦 ${escapeHtml(item.product_name)} (Cost: ₹${Math.round(item.unit_cost_inr)} | Price: ₹${Math.round(item.expected_selling_price_inr)})</option>
  `).join('');

  const profitCalcHtml = `
    <div class="profit-calc-section" id="profitCalcSection">
      <div class="profit-calc-header">
        <div class="profit-calc-title">💰 Monthly Income Calculator</div>
        <div class="profit-select-box">
          <span class="profit-select-label">Product:</span>
          <select class="profit-product-select" id="profitProductSelect" onchange="updateProfitCalc()">
            ${optionsHtml}
          </select>
        </div>
      </div>
      <div class="profit-selected-banner" id="profitSelectedBanner">
        ${renderProfitBanner(firstRec)}
      </div>
      <div class="profit-slider-row">
        <span class="profit-slider-label">If you produce & sell this many units per month:</span>
        <input type="range" class="profit-slider" id="profitSlider" min="10" max="500" value="50" step="10" oninput="updateProfitCalc()">
        <span class="profit-unit-count" id="profitUnitCount">50</span>
      </div>
      <div class="profit-result-grid" id="profitResultGrid">
        ${renderProfitResults(firstRec, 50)}
      </div>
    </div>
  `;
  
  return '<div class="rec-results-top-bar"><button class="rec-regenerate-btn" onclick="showWizardAgain()">🔄 Change Preferences & Regenerate</button></div><div class="recommendation-grid">' + cards + '</div>' + profitCalcHtml;
}

function renderProfitBanner(rec) {
  if (!rec) return '';
  const unitCost = Math.round(rec.unit_cost_inr || 0);
  const sellingPrice = Math.round(rec.expected_selling_price_inr || 0);
  const profitPerUnit = sellingPrice - unitCost;
  const unitSuffix = rec.pricing_unit ? ` (${rec.pricing_unit})` : '';
  return `<span>Calculating for: <strong>📦 ${escapeHtml(rec.product_name)}</strong></span>` +
    `<span>Making Cost: <strong>₹${unitCost}${unitSuffix}</strong></span>` +
    `<span>Selling Price: <strong>₹${sellingPrice}${unitSuffix}</strong></span>` +
    `<span>Profit per Unit: <strong style="color:var(--green)">+₹${profitPerUnit}</strong></span>`;
}

function selectProductForCalc(index) {
  const selectEl = document.getElementById('profitProductSelect');
  if (selectEl) {
    selectEl.value = index;
    updateProfitCalc();
  }
  const section = document.getElementById('profitCalcSection');
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function renderProfitResults(rec, units) {
  const cost = (rec.unit_cost_inr || 0) * units;
  const revenue = (rec.expected_selling_price_inr || 0) * units;
  const profit = revenue - cost;
  return `
    <div class="profit-result-item">
      <div class="profit-result-label">Monthly Cost</div>
      <div class="profit-result-value cost">₹${Math.round(cost).toLocaleString('en-IN')}</div>
    </div>
    <div class="profit-result-item">
      <div class="profit-result-label">Monthly Revenue</div>
      <div class="profit-result-value revenue">₹${Math.round(revenue).toLocaleString('en-IN')}</div>
    </div>
    <div class="profit-result-item highlight">
      <div class="profit-result-label">Monthly Net Profit 🎉</div>
      <div class="profit-result-value profit">₹${Math.round(profit).toLocaleString('en-IN')}</div>
    </div>
  `;
}

function updateProfitCalc() {
  const slider = document.getElementById('profitSlider');
  const countEl = document.getElementById('profitUnitCount');
  const gridEl = document.getElementById('profitResultGrid');
  const selectEl = document.getElementById('profitProductSelect');
  const bannerEl = document.getElementById('profitSelectedBanner');
  if (!slider || !countEl || !gridEl) return;
  const units = parseInt(slider.value);
  countEl.textContent = units;
  const data = window._lastRecommendationData;
  const idx = selectEl ? (parseInt(selectEl.value) || 0) : 0;
  if (data && data.recommendations && data.recommendations[idx]) {
    const rec = data.recommendations[idx];
    gridEl.innerHTML = renderProfitResults(rec, units);
    if (bannerEl) bannerEl.innerHTML = renderProfitBanner(rec);
  }
}

async function fetchCategories(mfpId, forceRefresh = false) {
  const panel = document.getElementById("categoryPanel");

  panel.innerHTML = `
    <div class="market-loading">
      <div class="spinner"></div>
      <p>Discovering all the products you can make...</p>
      <div class="substep">Our AI is studying this material — just a few seconds</div>
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
      const catCount = (data.product_categories || []).length;
      marketPanel.innerHTML = `<button class="market-trigger" onclick="fetchMarket(${mfpId})" id="marketBtn">
           🔍 Fetch Live Market Data
         </button>
         <div class="substep" style="margin-top:8px;text-align:center;font-size:12px;color:var(--text-muted);">
           Will search for products across the ${catCount} categories generated above
         </div>`;
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
    <div class="equipment-filter-bar">
      <button class="equip-option active" onclick="filterEquipment('all', this)">
        <span class="equip-icon">📋</span> All Products
      </button>
      <button class="equip-option" onclick="filterEquipment('easy', this)">
        <span class="equip-icon">🏠</span> Home / Hand Tools
      </button>
      <button class="equip-option" onclick="filterEquipment('medium', this)">
        <span class="equip-icon">🔧</span> Small Workshop
      </button>
      <button class="equip-option" onclick="filterEquipment('hard', this)">
        <span class="equip-icon">🏭</span> Commercial Scale
      </button>
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

function filterEquipment(level, btn) {
  activeEquipFilter = level;
  document.querySelectorAll('.equip-option').forEach(el => el.classList.remove('active'));
  if(btn) btn.classList.add('active');

  // Normalize difficulty: map various LLM strings to our 3 buckets
  function normalizeDifficulty(raw) {
    const d = (raw || 'medium').toLowerCase().trim();
    if (d === 'easy' || d === 'beginner' || d === 'simple' || d === 'basic') return 'easy';
    if (d === 'hard' || d === 'difficult' || d === 'advanced' || d === 'complex' || d === 'expert') return 'hard';
    return 'medium'; // medium, moderate, intermediate, or anything else
  }

  // Filter individual process-cards
  document.querySelectorAll('.process-card').forEach(card => {
    const cardDiff = normalizeDifficulty(card.dataset.difficulty);
    if (level === 'all' || cardDiff === level) {
      card.style.display = '';
    } else {
      card.style.display = 'none';
    }
  });

  // Handle accordion parents: hide categories with zero visible products, expand those with visible ones
  document.querySelectorAll('.accordion-item').forEach(accordion => {
    const body = accordion.querySelector('.accordion-body');
    if (!body) return;
    const visibleCards = body.querySelectorAll('.process-card:not([style*="display: none"])');
    const totalCards = body.querySelectorAll('.process-card');

    if (visibleCards.length === 0) {
      // Hide entire accordion section when no products match the filter
      accordion.style.display = 'none';
    } else {
      accordion.style.display = '';
      // Auto-expand accordion if a filter is active (so user can see results immediately)
      if (level !== 'all') {
        accordion.classList.add('open');
      }
      // Update the product count badge
      const countEl = accordion.querySelector('.cat-count');
      if (countEl) {
        if (level === 'all') {
          countEl.textContent = `${totalCards.length} product${totalCards.length !== 1 ? 's' : ''}`;
        } else {
          countEl.textContent = `${visibleCards.length} of ${totalCards.length} product${totalCards.length !== 1 ? 's' : ''}`;
        }
      }
    }
  });
}

function renderProductProcess(product) {
  const diffClass = product.difficulty === 'Easy' ? 'diff-easy'
    : product.difficulty === 'Hard' ? 'diff-hard' : 'diff-medium';

  const potentialClass = product.market_potential === 'high' ? 'pot-high'
    : product.market_potential === 'low' ? 'pot-low' : 'pot-medium';

  const steps = product.manufacturing_process || [];
  const skills = product.required_skills || [];

  return `
    <div class="process-card" data-difficulty="${(product.difficulty || 'Medium').toLowerCase()}">
      <div class="process-header">
        <div class="process-title">${product.name}</div>
        <div class="process-badges">
          <span class="diff-badge ${diffClass}">${product.difficulty || 'Medium'}</span>
          <span class="pot-badge ${potentialClass}">${(product.market_potential || 'medium').charAt(0).toUpperCase() + (product.market_potential || 'medium').slice(1)} Demand</span>
        </div>
      </div>
      <div class="recipe-meta-row">
        <div class="recipe-meta-item">
          <span class="recipe-meta-icon">⏱️</span>
          <div><span class="recipe-meta-label">Difficulty</span><br><span class="recipe-meta-value">${product.difficulty === 'Easy' ? 'Beginner-friendly' : product.difficulty === 'Hard' ? 'Needs training & equipment' : 'Some practice needed'}</span></div>
        </div>
        <div class="recipe-meta-item">
          <span class="recipe-meta-icon">📊</span>
          <div><span class="recipe-meta-label">Market Demand</span><br><span class="recipe-meta-value">${(product.market_potential || 'medium').charAt(0).toUpperCase() + (product.market_potential || 'medium').slice(1)}</span></div>
        </div>
        ${product.estimated_cost ? `<div class="recipe-meta-item">
          <span class="recipe-meta-icon">💰</span>
          <div><span class="recipe-meta-label">Est. Cost</span><br><span class="recipe-meta-value">${product.estimated_cost}</span></div>
        </div>` : ''}
      </div>

      <div class="process-section">
        <div class="process-section-title">📋 Step-by-Step Process (Recipe)</div>
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
        <div class="process-section-title">🛠 Skills & Tools Needed</div>
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

// ── Product Enhancement AI Modal ───────────────────────────────────────────

function openEnhancementModal(mfpId, recIndex) {
  const data = window._lastRecommendationData;
  if (!data || !data.recommendations || !data.recommendations[recIndex]) return;

  const recommendation = data.recommendations[recIndex];
  const productName = recommendation.product_name;
  const cacheKey = mfpId + ':' + productName;

  // Create modal overlay
  let overlay = document.getElementById('enhancementOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'enhancementOverlay';
    overlay.className = 'enhancement-overlay';
    document.body.appendChild(overlay);
  }

  overlay.classList.add('active');
  document.body.style.overflow = 'hidden';

  // Show loading
  overlay.innerHTML = `
    <div class="enhancement-modal">
      <div class="enhancement-modal-header">
        <div class="enhancement-title-area">
          <span class="enhancement-ai-badge">✨ Product Enhancement AI</span>
          <h2>${escapeHtml(productName)}</h2>
          <span class="enhancement-subtitle">${escapeHtml(recommendation.category_name)} · ${escapeHtml(recommendation.difficulty)} difficulty · Expected: INR ${Number(recommendation.expected_selling_price_inr).toFixed(2)}${recommendation.pricing_unit ? ' (' + escapeHtml(recommendation.pricing_unit) + ')' : ''}</span>
        </div>
        <button class="enhancement-close" onclick="closeEnhancementModal()" title="Close (Esc)">✕</button>
      </div>
      <div class="enhancement-modal-body">
        <div class="market-loading">
          <div class="spinner"></div>
          <p>Building your detailed business blueprint...</p>
          <div class="substep">Creating design ideas, packaging suggestions, and sales strategies</div>
        </div>
      </div>
    </div>
  `;

  // Check cache
  if (enhancementCache[cacheKey]) {
    renderEnhancementContent(enhancementCache[cacheKey], recommendation, mfpId);
    return;
  }

  // Fetch from API
  fetchEnhancement(mfpId, recommendation, cacheKey);
}

async function fetchEnhancement(mfpId, recommendation, cacheKey) {
  const market = marketCache[mfpId];
  const marketContext = market ? recommendationEvidence(market) : {
    market_summary: {}, competitor_analysis: {}, top_products: [],
    product_demand_match: {}, regional_market_fit: [], seasonal_demand: {}
  };

  try {
    const data = await api('/api/materials/' + mfpId + '/enhance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recommendation, market_context: marketContext })
    });
    enhancementCache[cacheKey] = data;
    renderEnhancementContent(data, recommendation, mfpId);
  } catch (error) {
    const body = document.querySelector('.enhancement-modal-body');
    if (body) {
      body.innerHTML = '<div class="error-box" style="margin:20px;">Enhancement generation failed: ' + escapeHtml(error.message) + '</div>';
    }
  }
}

function renderEnhancementContent(data, recommendation, mfpId) {
  const body = document.querySelector('.enhancement-modal-body');
  if (!body) return;

  const e = (data && data.enhancement) ? data.enhancement : (data || {});
  const pd = e.product_design || {};
  const ms = e.marketing_strategy || {};
  const pkg = e.packaging || {};
  const sc = e.sales_channels || {};

  const productName = recommendation ? recommendation.product_name : 'Product';
  const mfpObj = allMaterials.find(m => m.mfp_id === mfpId) || {};
  const mfpName = data.mfp_name || mfpObj.name || 'Forest Produce';

  const relatedExamples = (data.related_examples && data.related_examples.length > 0)
    ? data.related_examples
    : [];

  body.innerHTML = `
    <div class="enhancement-tabs">
      <button class="enh-tab active" onclick="switchEnhancementTab('design', this)">🎨 Look & Feel</button>
      <button class="enh-tab" onclick="switchEnhancementTab('marketing', this)">📢 How to Sell</button>
      <button class="enh-tab" onclick="switchEnhancementTab('packaging', this)">📦 Packaging Ideas</button>
      <button class="enh-tab" onclick="switchEnhancementTab('sales', this)">🏪 Where to Sell</button>
      <button class="enh-tab" onclick="switchEnhancementTab('examples', this)">📸 Examples${relatedExamples.length > 0 ? ' (' + relatedExamples.length + ')' : ''}</button>
    </div>

    <!-- Design Tab -->
    <div class="enh-panel active" id="enh-design">
      ${renderDesignTab(pd, recommendation, mfpName)}
    </div>

    <!-- Marketing Tab -->
    <div class="enh-panel" id="enh-marketing">
      ${renderMarketingTab(ms, recommendation, mfpName)}
    </div>

    <!-- Packaging Tab -->
    <div class="enh-panel" id="enh-packaging">
      ${renderPackagingTab(pkg, recommendation, mfpName)}
    </div>

    <!-- Sales Tab -->
    <div class="enh-panel" id="enh-sales">
      ${renderSalesTab(sc, recommendation, mfpName)}
    </div>

    <!-- Market Examples Tab -->
    <div class="enh-panel" id="enh-examples">
      ${renderMarketExamplesTab(relatedExamples, productName)}
    </div>

    <div class="enhancement-footer">
      <button class="print-handout-btn" onclick="window.print()" title="Print this blueprint">🖨️ Print Business Handout</button>
      <span>Generated in ${data.elapsed_seconds || '?'}s${data.fallback_used ? ' (fallback mode)' : ''}</span>
    </div>
  `;
}

function renderDesignTab(pd, recommendation, mfpName) {
  const productName = recommendation ? recommendation.product_name : 'Product';
  const rawMfp = mfpName || 'Forest Material';

  const defaultColors = [
    { name: 'Forest Green', hex: '#1E5138', usage: 'Primary brand color — represents forest origin' },
    { name: 'Warm Cream', hex: '#F5F0E1', usage: 'Background and label base color' },
    { name: 'Terracotta', hex: '#C2593F', usage: 'Accent highlights and tribal motifs' },
    { name: 'Charcoal', hex: '#2C2C2C', usage: 'Typography and clear borders' }
  ];
  const colorList = (pd.color_palette && pd.color_palette.length > 0) ? pd.color_palette : defaultColors;
  const colorsHtml = colorList.map(c => `
    <div class="color-swatch-card">
      <div class="color-swatch" style="background:${c.hex || '#1E5138'}"></div>
      <div class="color-info">
        <strong>${escapeHtml(c.name || 'Color')}</strong>
        <span class="color-hex">${escapeHtml(c.hex || '')}</span>
        <span class="color-usage">${escapeHtml(c.usage || 'Brand accent')}</span>
      </div>
    </div>
  `).join('');

  const defaultTips = [
    `Use clean, minimalist labeling to highlight the natural purity of ${rawMfp}.`,
    `Incorporate a matte kraft-paper texture finish for a premium tactile feel.`,
    `Include a small story card or QR code highlighting the tribal artisan's craftsmanship.`
  ];
  const tipList = (pd.modernization_tips && pd.modernization_tips.length > 0) ? pd.modernization_tips : defaultTips;
  const tipsHtml = tipList.map(t => `<li>${escapeHtml(t)}</li>`).join('');

  const defaultPrinciples = [
    `Authenticity first — let the natural texture and raw quality of ${rawMfp} shine through.`,
    `Premium minimalism — clean layouts command a higher perceived retail price.`,
    `Cultural heritage — incorporate subtle regional tribal motifs without overwhelming the modern design.`
  ];
  const principleList = (pd.design_principles && pd.design_principles.length > 0) ? pd.design_principles : defaultPrinciples;
  const principlesHtml = principleList.map(p => `<li>${escapeHtml(p)}</li>`).join('');

  const inspiration = pd.inspiration || `Scandinavian minimalism meets Indian tribal heritage — clean lines, natural materials, and warm earth tones that highlight the craftsmanship of ${rawMfp}.`;
  const formFactor = pd.form_factor || `A compact, ergonomic ${productName.toLowerCase()} designed for retail display, easy handling, and gift packaging.`;

  return `
    <div class="enh-section">
      <h3>🎯 What Should It Look Like?</h3>
      <div class="enh-inspiration-card">
        <p>${escapeHtml(inspiration)}</p>
      </div>
    </div>

    <div class="enh-section">
      <h3>📐 Shape & Form Factor</h3>
      <p class="enh-description">${escapeHtml(formFactor)}</p>
    </div>

    <div class="enh-section">
      <h3>🎨 Suggested Color Palette</h3>
      <div class="color-palette-grid">${colorsHtml}</div>
    </div>

    <div class="enh-two-col">
      <div class="enh-section">
        <h3>✨ How to Make It Modern</h3>
        <ul class="enh-tip-list">${tipsHtml}</ul>
      </div>
      <div class="enh-section">
        <h3>📌 Key Design Rules</h3>
        <ul class="enh-tip-list">${principlesHtml}</ul>
      </div>
    </div>
  `;
}

function renderMarketingTab(ms, recommendation, mfpName) {
  const productName = recommendation ? recommendation.product_name : 'Product';
  const rawMfp = mfpName || 'Forest Produce';
  const expectedPrice = recommendation ? (recommendation.expected_selling_price_inr || 300) : 300;

  const positioning = ms.positioning || `Handcrafted ${productName} from tribal artisans — where forest heritage meets modern living.`;
  const usp = ms.usp || `100% natural ${rawMfp}-based product, sustainably harvested and crafted by local tribal communities.`;
  const pricing = ms.pricing_strategy || `Position at a 20–30% premium over mass synthetic alternatives. Price around ₹${Math.round(expectedPrice)} to highlight organic purity.`;

  const defaultSegments = [
    { segment: "Urban Eco-Conscious Consumers", description: "25–45 year olds in metro cities seeking organic, chemical-free lifestyle products", approach: "Instagram & social media storytelling focusing on eco-friendly lifestyle" },
    { segment: "Premium Gift Buyers", description: "Shoppers seeking unique, handcrafted, story-driven gifts for festivals and celebrations", approach: "Featured hampers on curated gifting portals and corporate gift sets" },
    { segment: "Export & NRI Market", description: "Indian diaspora and international buyers seeking authentic Indian craft heritage", approach: "Amazon Global, Etsy, and tribal craft export exhibitions" }
  ];
  const segmentList = (ms.target_segments && ms.target_segments.length > 0) ? ms.target_segments : defaultSegments;
  const segmentsHtml = segmentList.map(s => `
    <div class="segment-card">
      <div class="segment-header">
        <h4>${escapeHtml(s.segment || 'Customer Segment')}</h4>
      </div>
      <p class="segment-desc">${escapeHtml(s.description || '')}</p>
      <div class="segment-approach">
        <span class="approach-label">📍 Approach:</span>
        <span>${escapeHtml(s.approach || '')}</span>
      </div>
    </div>
  `).join('');

  const story = ms.storytelling_angle || `Every ${productName} supports a tribal family's livelihood and preserves centuries of traditional forest knowledge passed down through generations.`;

  const defaultTactics = [
    `Create short video reels showing tribal artisans harvesting and making ${productName}.`,
    `Partner with sustainable lifestyle creators for authentic unboxing reviews.`,
    `Run targeted social media ads with 'forest-to-home' visual narrative.`
  ];
  const tacticList = (ms.digital_marketing && ms.digital_marketing.length > 0) ? ms.digital_marketing : defaultTactics;
  const tacticsHtml = tacticList.map(t => `<li>${escapeHtml(t)}</li>`).join('');

  return `
    <div class="enh-section">
      <h3>💡 What Makes Your Product Special</h3>
      <div class="enh-highlight-card">
        <div class="highlight-row"><span class="highlight-label">Positioning</span><p>${escapeHtml(positioning)}</p></div>
        <div class="highlight-row"><span class="highlight-label">USP</span><p>${escapeHtml(usp)}</p></div>
        <div class="highlight-row"><span class="highlight-label">Pricing</span><p>${escapeHtml(pricing)}</p></div>
      </div>
    </div>

    <div class="enh-section">
      <h3>🎯 Who Will Buy This?</h3>
      <div class="segments-grid">${segmentsHtml}</div>
    </div>

    <div class="enh-section">
      <h3>📖 Your Product Story</h3>
      <div class="enh-story-card">
        <p>${escapeHtml(story)}</p>
      </div>
    </div>

    <div class="enh-section">
      <h3>📱 Online Promotion Ideas</h3>
      <ul class="enh-tip-list">${tacticsHtml}</ul>
    </div>
  `;
}

function renderPackagingTab(pkg, recommendation, mfpName) {
  const productName = recommendation ? recommendation.product_name : 'Product';
  const rawMfp = mfpName || 'Forest Produce';
  const expectedPrice = recommendation ? (recommendation.expected_selling_price_inr || 300) : 300;

  const material = pkg.material || `Recyclable unbleached kraft paper box with a plantable seed-paper insert.`;
  const secondary = pkg.secondary_packaging || `Corrugated cardboard mailer box with printed tribal art pattern for shipping protection.`;

  const defaultPkgColors = [
    { name: 'Kraft Brown', hex: '#B8860B', usage: 'Primary box base material' },
    { name: 'Forest Green', hex: '#1E5138', usage: 'Brand logo and organic trust mark' },
    { name: 'Warm Gold', hex: '#D4A853', usage: 'Border accents and quality seals' }
  ];
  const pkgColorList = (pkg.color_scheme && pkg.color_scheme.length > 0) ? pkg.color_scheme : defaultPkgColors;
  const pkgColorsHtml = pkgColorList.map(c => `
    <div class="color-swatch-card compact">
      <div class="color-swatch" style="background:${c.hex || '#B8860B'}"></div>
      <div class="color-info">
        <strong>${escapeHtml(c.name || 'Color')}</strong>
        <span class="color-usage">${escapeHtml(c.usage || 'Packaging accent')}</span>
      </div>
    </div>
  `).join('');

  const defaultLabels = [
    `Traditional regional tribal art motif border (Warli / Gond style)`,
    `QR code linking to artisan video and origin story`,
    `'Made from Pure ${rawMfp}' origin badge`,
    `Net weight, batch number, MRP, and FSSAI mark`
  ];
  const labelList = (pkg.label_elements && pkg.label_elements.length > 0) ? pkg.label_elements : defaultLabels;
  const labelsHtml = labelList.map(l => `<li>${escapeHtml(l)}</li>`).join('');

  const defaultCerts = [
    { name: "FSSAI License / Registration", why: "Mandatory for food, herbal & cosmetic products sold in India", difficulty: "Medium" },
    { name: "India Organic (NPOP)", why: "Validates natural chemical-free origin — commands 15–20% price premium", difficulty: "Medium" },
    { name: "Craft Mark / Tribal GI Tag", why: `Protects and authenticates tribal origin of ${rawMfp}`, difficulty: "Easy" }
  ];
  const certList = (pkg.certifications && pkg.certifications.length > 0) ? pkg.certifications : defaultCerts;
  const certsHtml = certList.map(c => {
    const diffClass = (c.difficulty || '').toLowerCase() === 'easy' ? 'cert-easy'
      : (c.difficulty || '').toLowerCase() === 'hard' ? 'cert-hard' : 'cert-medium';
    return `<div class="cert-card">
      <div class="cert-header">
        <span class="cert-name">${escapeHtml(c.name || 'Certification')}</span>
        <span class="cert-diff ${diffClass}">${escapeHtml(c.difficulty || 'Medium')}</span>
      </div>
      <p class="cert-why">${escapeHtml(c.why || 'Validates quality')}</p>
    </div>`;
  }).join('');

  const defaultSizes = [
    { size: "Sample / Trial Pack", price_range: `₹${Math.round(expectedPrice * 0.5)}–₹${Math.round(expectedPrice * 0.7)}`, target: "First-time buyers & online trial orders" },
    { size: "Standard Retail Pack", price_range: `₹${Math.round(expectedPrice)}–₹${Math.round(expectedPrice * 1.3)}`, target: "Regular daily consumers" },
    { size: "Premium Gift Hamper", price_range: `₹${Math.round(expectedPrice * 1.8)}–₹${Math.round(expectedPrice * 2.5)}`, target: "Festive gifting & corporate orders" }
  ];
  const sizeList = (pkg.size_variants && pkg.size_variants.length > 0) ? pkg.size_variants : defaultSizes;
  const sizesHtml = sizeList.map(s => `
    <div class="size-variant-card">
      <div class="size-name">${escapeHtml(s.size || '')}</div>
      <div class="size-price">${escapeHtml(s.price_range || '')}</div>
      <div class="size-target">${escapeHtml(s.target || '')}</div>
    </div>
  `).join('');

  const ecoNotes = pkg.sustainability_notes || `100% plastic-free packaging. Use compostable jute twine, paper tape, and biodegradable mailers.`;

  return `
    <div class="enh-two-col">
      <div class="enh-section">
        <h3>📦 What to Pack It In</h3>
        <div class="enh-info-card">
          <div class="info-row"><span class="info-label">Primary</span><span>${escapeHtml(material)}</span></div>
          <div class="info-row"><span class="info-label">Secondary</span><span>${escapeHtml(secondary)}</span></div>
        </div>
      </div>
      <div class="enh-section">
        <h3>🎨 Package Look</h3>
        <div class="color-palette-grid compact">${pkgColorsHtml}</div>
      </div>
    </div>

    <div class="enh-section">
      <h3>🏷️ What Goes on the Label</h3>
      <ul class="enh-checklist">${labelsHtml}</ul>
    </div>

    <div class="enh-section">
      <h3>📜 Certificates & Trust Marks</h3>
      <div class="certs-grid">${certsHtml}</div>
    </div>

    <div class="enh-section">
      <h3>📏 Pack Sizes & Pricing</h3>
      <div class="size-grid">${sizesHtml}</div>
    </div>

    <div class="enh-section">
      <h3>🌱 Eco-Friendly Points</h3>
      <div class="enh-story-card green">
        <p>${escapeHtml(ecoNotes)}</p>
      </div>
    </div>
  `;
}

function renderSalesTab(sc, recommendation, mfpName) {
  const productName = recommendation ? recommendation.product_name : 'Product';

  const defaultOnline = [
    { platform: "Tribes India (TRIFED)", why: "Government portal specifically for tribal artisans with zero listing fees", setup_difficulty: "Easy" },
    { platform: "Amazon Karigar / Saheli", why: "Dedicated e-commerce storefront for Indian artisans with high buyer reach", setup_difficulty: "Medium" },
    { platform: "ONDC Network", why: "Government direct-to-consumer digital commerce network with direct payments", setup_difficulty: "Easy" },
    { platform: "Flipkart Samarth", why: "National marketplace program supporting rural handicraft clusters", setup_difficulty: "Medium" }
  ];
  const onlineList = (sc.online && sc.online.length > 0) ? sc.online : defaultOnline;
  const onlineHtml = onlineList.map(p => {
    const diffClass = (p.setup_difficulty || '').toLowerCase() === 'easy' ? 'cert-easy'
      : (p.setup_difficulty || '').toLowerCase() === 'hard' ? 'cert-hard' : 'cert-medium';
    return `<div class="channel-card">
      <div class="channel-header">
        <h4>${escapeHtml(p.platform || 'Platform')}</h4>
        <span class="cert-diff ${diffClass}">${escapeHtml(p.setup_difficulty || 'Medium')}</span>
      </div>
      <p>${escapeHtml(p.why || '')}</p>
    </div>`;
  }).join('');

  const defaultOffline = [
    { channel: "State Tribal Crafts Expos", description: "Participate in Surajkund Mela, Dilli Haat, and Saras Melas for direct sales and publicity." },
    { channel: "Urban Wellness & Organic Stores", description: "Place trial stock in metro organic stores and natural product outlets." },
    { channel: "Heritage Resorts & Spas", description: "Supply customized gift packs to eco-resorts as luxury guest souvenirs." }
  ];
  const offlineList = (sc.offline && sc.offline.length > 0) ? sc.offline : defaultOffline;
  const offlineHtml = offlineList.map(c => `
    <div class="channel-card">
      <h4>${escapeHtml(c.channel || 'Channel')}</h4>
      <p>${escapeHtml(c.description || '')}</p>
    </div>
  `).join('');

  const defaultB2b = [
    { buyer_type: "Corporate Gift Aggregators", approach: "Offer bulk customized hampers for Diwali and Corporate hampers." },
    { buyer_type: "Organic Product Distributors", approach: "Connect through trade meets like BioFach India and Sarvodaya fairs." }
  ];
  const b2bList = (sc.b2b && sc.b2b.length > 0) ? sc.b2b : defaultB2b;
  const b2bHtml = b2bList.map(b => `
    <div class="channel-card">
      <h4>${escapeHtml(b.buyer_type || 'Buyer Type')}</h4>
      <p>${escapeHtml(b.approach || '')}</p>
    </div>
  `).join('');

  const defaultExport = [
    { market: "EU & UK", potential: "High", requirements: "Organic certification, REACH eco-compliance, English eco-labeling" },
    { market: "USA & Canada", potential: "Medium", requirements: "FDA product listing, USDA organic recognition" },
    { market: "Middle East & SE Asia", potential: "Medium", requirements: "Halal / Organic declaration, local language tags" }
  ];
  const exportList = (sc.export && sc.export.length > 0) ? sc.export : defaultExport;
  const exportHtml = exportList.map(e => {
    const potClass = (e.potential || '').toLowerCase() === 'high' ? 'pot-high'
      : (e.potential || '').toLowerCase() === 'low' ? 'pot-low' : 'pot-medium';
    return `<div class="channel-card">
      <div class="channel-header">
        <h4>${escapeHtml(e.market || 'Market')}</h4>
        <span class="pot-badge ${potClass}">${escapeHtml(e.potential || 'Medium')} potential</span>
      </div>
      <p>${escapeHtml(e.requirements || '')}</p>
    </div>`;
  }).join('');

  return `
    <div class="enh-section">
      <h3>🛒 Sell Online Here</h3>
      <div class="channels-grid">${onlineHtml}</div>
    </div>

    <div class="enh-section">
      <h3>🏬 Sell In-Person Here</h3>
      <div class="channels-grid">${offlineHtml}</div>
    </div>

    <div class="enh-section">
      <h3>🏢 Sell to Businesses</h3>
      <div class="channels-grid">${b2bHtml}</div>
    </div>

    <div class="enh-section">
      <h3>🌍 International Opportunities</h3>
      <div class="channels-grid">${exportHtml}</div>
    </div>
  `;
}

function renderMarketExamplesTab(productsWithImages, productName = '') {
  if (!productsWithImages || !productsWithImages.length) {
    return `<div class="enh-empty-examples">
      <span class="empty-icon">📸</span>
      <p>No direct market examples found for "${escapeHtml(productName || 'this product')}".</p>
      <div class="substep">This is an emerging product niche with minimal direct commercial competition — a high-opportunity craft product!</div>
    </div>`;
  }

  const cards = productsWithImages.slice(0, 2).map(p =>
    `<div class="example-card">
      <img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.title || '')}" class="example-image" onerror="this.onerror=null;this.parentElement.style.display='none';">
      <div class="example-info">
        <div class="example-title">${escapeHtml(truncate(p.title || '', 55))}</div>
        <div class="example-meta">
          ${p.price ? '<span class="example-price">₹' + Math.round(p.price) + '</span>' : ''}
          ${p.rating ? '<span class="example-rating">' + p.rating + ' ★</span>' : ''}
          ${p.seller || p.source ? '<span class="example-source">' + escapeHtml(p.seller || p.source) + '</span>' : ''}
        </div>
      </div>
    </div>`
  ).join('');

  return `
    <div class="enh-section">
      <h3>📸 Market Product Examples</h3>
      <p class="enh-description">Targeted commercial products matching <strong>${escapeHtml(productName)}</strong> for packaging, design, and pricing inspiration.</p>
      <div class="examples-grid">${cards}</div>
    </div>
  `;
}

function switchEnhancementTab(tabName, btnEl) {
  document.querySelectorAll('.enh-tab').forEach(t => t.classList.remove('active'));
  btnEl.classList.add('active');
  document.querySelectorAll('.enh-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('enh-' + tabName);
  if (panel) panel.classList.add('active');
}

function closeEnhancementModal() {
  const overlay = document.getElementById('enhancementOverlay');
  if (overlay) {
    overlay.classList.remove('active');
    setTimeout(() => { overlay.innerHTML = ''; }, 300);
  }
  document.body.style.overflow = '';
}

// Close on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeEnhancementModal();
});

