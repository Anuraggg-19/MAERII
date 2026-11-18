// Calculation and request parity with app/static/app.js; no model logic here.
export function stableStringify(value) {
  if (Array.isArray(value))
    return "[" + value.map(stableStringify).join(",") + "]";
  if (value && typeof value === "object")
    return (
      "{" +
      Object.keys(value)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + stableStringify(value[k]))
        .join(",") +
      "}"
    );
  return JSON.stringify(value);
}
export function recommendationEvidence(market) {
  return {
    market_summary: market.market_summary || {},
    competitor_analysis: market.competitor_analysis || {},
    top_products: market.top_products || [],
    product_demand_match: market.product_demand_match || {},
    regional_market_fit: market.regional_market_fit || [],
    seasonal_demand: market.seasonal_demand || {},
  };
}
export function recommendationCacheKey(id, constraints, market) {
  return (
    String(id) +
    ":" +
    stableStringify({
      constraints,
      market_context: recommendationEvidence(market),
    })
  );
}
export function monthlyIncome(rec, units) {
  const cost = (rec.unit_cost_inr || 0) * units;
  const revenue = (rec.expected_selling_price_inr || 0) * units;
  return { cost, revenue, profit: revenue - cost };
}
export function broadCategory(category) {
  return (category || "").toLowerCase().includes("agri")
    ? "agriculture"
    : "forest";
}
export function materialIcon(category) {
  const c = (category || "").toLowerCase();
  for (const [terms, icon] of [
    [["gum", "resin"], "💧"],
    [["seed", "oil"], "🌰"],
    [["honey", "wax"], "🍯"],
    [["leaf", "leaves", "herb"], "🌿"],
    [["bamboo", "wood", "cane"], "🪵"],
    [["flower"], "🌸"],
    [["fruit", "berry"], "🫐"],
    [["bark", "fiber"], "🧶"],
    [["mushroom", "fungi"], "🍄"],
  ]) {
    if (terms.some((t) => c.includes(t))) return icon;
  }
  return "🌿";
}
export function normalizeDifficulty(raw) {
  const d = (raw || "medium").toLowerCase().trim();
  if (["easy", "beginner", "simple", "basic"].includes(d)) return "easy";
  if (["hard", "difficult", "advanced", "complex", "expert"].includes(d))
    return "hard";
  return "medium";
}
export function sortProducts(products, filter, sort) {
  return products
    .filter((p) => filter === "all" || p.product_type === filter)
    .sort((a, b) => {
      switch (sort) {
        case "price_asc":
          return (a.price || 9999999) - (b.price || 9999999);
        case "price_desc":
          return (b.price || 0) - (a.price || 0);
        case "pergram_asc":
          return (a.price_per_gram || 9999999) - (b.price_per_gram || 9999999);
        case "pergram_desc":
          return (b.price_per_gram || 0) - (a.price_per_gram || 0);
        case "rating_desc":
          return (b.rating || 0) - (a.rating || 0);
        case "reviews_desc":
          return (b.review_count || 0) - (a.review_count || 0);
        case "name_asc":
          return (a.title || "").localeCompare(b.title || "");
        default:
          return (b.confidence || 0) - (a.confidence || 0);
      }
    });
}
export function safeUrl(value) {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export function readPreference(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}
export function writePreference(key, value) {
  try {
    value == null
      ? localStorage.removeItem(key)
      : localStorage.setItem(key, value);
  } catch {
    /* Storage can be disabled. */
  }
}
