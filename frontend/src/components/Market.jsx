import React, { useState } from "react";
import { useWorkspace } from "../contexts/Workspace";
import { sortProducts, safeUrl } from "../utils/workflow";
import {
  Loading,
  ErrorBox,
  Empty,
  Section,
  List,
  Tags,
  ExternalLink,
  EvidenceStamp,
} from "./common";

export function ProductCard({ product: p }) {
  const [failed, setFailed] = useState(false);
  return (
    <article
      className={"product-card " + (p.is_matched ? "" : "unmatched-card")}
    >
      {safeUrl(p.image_url) && !failed ? (
        <img
          loading="lazy"
          src={safeUrl(p.image_url)}
          alt={p.title || "Product"}
          className="product-image"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="product-image no-image">📦</div>
      )}
      <div className="card-body">
        <div className="card-title-row">
          <span
            className={
              "type-badge " + (p.product_type === "raw" ? "raw" : "derived")
            }
          >
            {p.product_type === "raw" ? "Raw" : "Derived"}
          </span>
          <ExternalLink url={p.url} className="card-title">
            {p.title?.length > 60 ? p.title.slice(0, 60) + "…" : p.title}
          </ExternalLink>
        </div>
        <div className="card-price-row">
          <span className="card-price">
            {p.price ? "₹" + Math.round(p.price) : "—"}
          </span>
          {!!p.price_per_gram && (
            <span className="per-gram-price">₹{p.price_per_gram}/g</span>
          )}
          <span
            className={
              "match-badge friendly-badge " +
              (p.is_matched ? "direct" : "related")
            }
          >
            {p.is_matched ? "🌟 Direct Match" : "💡 Related"}
          </span>
        </div>
        <div className="card-meta">
          {!!p.rating && <span className="card-rating">{p.rating} ★</span>}
          {p.review_count > 0 && (
            <span className="card-reviews">({p.review_count})</span>
          )}
          <span className="card-source">{p.source || p.seller || ""}</span>
        </div>
      </div>
    </article>
  );
}
export default function Market() {
  const w = useWorkspace();
  const [matched, setMatched] = useState(false),
    [filter, setFilter] = useState("all"),
    [sort, setSort] = useState("confidence");
  const data = w.current.market?.data;
  if (!w.current.categories)
    return (
      <Empty
        title="First, Explore What You Can Make"
        action={
          <button
            className="market-trigger"
            onClick={() => w.navigate("categories")}
          >
            Open What to Make
          </button>
        }
      >
        Discover product categories before searching market prices.
      </Empty>
    );
  if (w.busy("market"))
    return (
      <Loading>
        Finding product prices and analysing market evidence. This can take
        several minutes…
      </Loading>
    );
  const s = data?.market_summary || {},
    c = data?.competitor_analysis || {},
    demand = s.demand_score || 0;
  const products = matched
    ? data?.top_products || []
    : data?.all_products || [];
  const display = sortProducts(products, filter, sort);
  return (
    <div className="market-section">
      <h2>📊 Real-Time Market Analysis</h2>
      {w.error("market") && (
        <ErrorBox message={w.error("market")} retry={w.market} />
      )}
      {!data ? (
        <Empty
          title="Explore real online product prices"
          action={
            <button className="market-trigger" onClick={w.market}>
              🔍 Fetch Live Market Data
            </button>
          }
        >
          Search across{" "}
          {(w.current.categories?.data.product_categories || []).length}{" "}
          discovered categories.
        </Empty>
      ) : data.status === "no_results" ? (
        <Empty title="No e-commerce products found">
          This material may not be widely sold online.
        </Empty>
      ) : (
        <>
          <div className="market-temp-card">
            <div
              className={
                "temp-meter " +
                (demand >= 0.65 ? "hot" : demand >= 0.35 ? "warm" : "cool")
              }
            >
              {demand >= 0.65 ? "🔥" : demand >= 0.35 ? "🌤️" : "❄️"}
            </div>
            <div className="temp-info">
              <h3>
                {demand >= 0.65
                  ? "High Demand Signal"
                  : demand >= 0.35
                    ? "Moderate Demand Signal"
                    : "Low Demand Signal"}
              </h3>
              <p className="temp-desc">
                Based on the recorded market analysis; listings and reviews do
                not establish actual sales.
              </p>
            </div>
          </div>
          <div className="market-stats">
            {[
              [data.products_found || 0, "Products Found"],
              [data.products_matched || 0, "Matched"],
              ["₹" + Math.round(s.avg_price || 0), "Avg Price"],
              [(s.avg_rating || "—") + " ★", "Avg Rating"],
              [s.total_reviews || 0, "Total Reviews"],
              [s.trend || "stable", "Trend"],
            ].map(([v, label]) => (
              <div className="stat-card" key={label}>
                <div className="stat-value">{v}</div>
                <div className="stat-label">{label}</div>
              </div>
            ))}
          </div>
          <div className="demand-bar-container">
            <div className="demand-label">
              <span>Demand Score</span>
              <strong>{(demand * 100).toFixed(1)}%</strong>
            </div>
            <div className="demand-bar">
              <div
                className="demand-fill"
                style={{
                  width: demand * 100 + "%",
                  background:
                    demand >= 0.65
                      ? "var(--green)"
                      : demand >= 0.35
                        ? "var(--amber)"
                        : "var(--red)",
                }}
              />
            </div>
          </div>
          <div className="section-grid">
            {c.top_brands?.length > 0 && (
              <Section title="🏷 Who’s Selling This Online">
                <Tags items={c.top_brands} />
                {c.price_positioning && (
                  <p>Positioning: {c.price_positioning}</p>
                )}
              </Section>
            )}
            {[
              ["💡 Market Gaps", c.market_gaps],
              ["🌟 Market Insights", c.llm_insights],
              ["📈 Demand Drivers", c.demand_drivers],
            ]
              .filter((x) => x[1]?.length)
              .map(([title, items]) => (
                <Section title={title} key={title}>
                  <List items={items} />
                </Section>
              ))}
            {!!s.top_attributes?.length && (
              <Section title="⭐ What Customers Value Most">
                <Tags items={s.top_attributes} />
              </Section>
            )}
            {data.seasonal_demand && (
              <Section title="📅 When Do People Buy This?">
                <Tags items={data.seasonal_demand.peak_seasons || []} />
                <p>{data.seasonal_demand.seasonal_pattern}</p>
                <p>{data.seasonal_demand.off_season_strategy}</p>
              </Section>
            )}
            {data.product_demand_match && (
              <Section title="✅ Current Products and Demand">
                {data.product_demand_match.demand_alignment_score != null && (
                  <p>
                    Alignment:{" "}
                    {(
                      data.product_demand_match.demand_alignment_score * 100
                    ).toFixed(0)}
                    %
                  </p>
                )}
                <h4>Validated</h4>
                <Tags
                  items={data.product_demand_match.validated_products || []}
                />
                <h4>Unvalidated</h4>
                <Tags
                  items={data.product_demand_match.unvalidated_products || []}
                />
              </Section>
            )}
            {!!data.regional_market_fit?.length && (
              <Section title="🌍 Regional Market Fit">
                <div className="regional-grid">
                  {data.regional_market_fit.map((r, i) => (
                    <div className="regional-item" key={i}>
                      <strong>{r.region}</strong>
                      <span>{r.fit}</span>
                      {r.confidence != null && (
                        <span>{(r.confidence * 100).toFixed(0)}%</span>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
          <div className="product-section">
            <div className="product-header-row">
              <h3>🛒 Products Available Online</h3>
              <button
                className="match-toggle"
                aria-pressed={matched}
                onClick={() => setMatched(!matched)}
              >
                {matched
                  ? `Show All Products (${data.all_products?.length || 0})`
                  : `Show Best Matches Only (${data.top_products?.length || 0})`}
              </button>
            </div>
            <div className="filter-bar">
              <div className="filter-tabs">
                {["all", "raw", "derived"].map((f) => (
                  <button
                    className={"filter-tab " + (filter === f ? "active" : "")}
                    key={f}
                    aria-pressed={filter === f}
                    onClick={() => setFilter(f)}
                  >
                    {f} (
                    {
                      products.filter(
                        (p) => f === "all" || p.product_type === f,
                      ).length
                    }
                    )
                  </button>
                ))}
              </div>
              <select
                className="sort-select"
                aria-label="Sort market products"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
              >
                {[
                  ["confidence", "Relevance"],
                  ["price_asc", "Price: Low → High"],
                  ["price_desc", "Price: High → Low"],
                  ["pergram_asc", "Per-gram: Low → High"],
                  ["pergram_desc", "Per-gram: High → Low"],
                  ["rating_desc", "Rating: High → Low"],
                  ["reviews_desc", "Reviews: Most → Least"],
                  ["name_asc", "Name: A → Z"],
                ].map(([id, label]) => (
                  <option value={id} key={id}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="product-grid">
              {display.map((p, i) => (
                <ProductCard key={(p.url || p.title) + i} product={p} />
              ))}
            </div>
            {!display.length && <Empty title="No products match this filter" />}
          </div>
          <EvidenceStamp data={data} />
          <p className="evidence-stamp">
            Analysis completed in {data.elapsed_seconds || "?"} seconds ·{" "}
            {data.products_found || 0} found, {data.products_matched || 0}{" "}
            matched.
          </p>
        </>
      )}
    </div>
  );
}
