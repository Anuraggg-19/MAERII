import React, { useState } from "react";
import { useWorkspace } from "../contexts/Workspace";
import { normalizeDifficulty } from "../utils/workflow";
import { Loading, ErrorBox, Empty, EvidenceStamp, Tags } from "./common";

export default function Products() {
  const w = useWorkspace();
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState({});
  const data = w.current.categories?.data;
  if (w.busy("categories"))
    return <Loading>Discovering products and manufacturing processes…</Loading>;
  return (
    <div className="market-section">
      <h2>🏭 Product Categories & Manufacturing Processes</h2>
      {w.error("categories") && (
        <ErrorBox
          message={w.error("categories")}
          retry={() => w.categories()}
        />
      )}
      {!data ? (
        <Empty
          title="Discover What Products You Can Make"
          action={
            <button className="market-trigger" onClick={() => w.categories()}>
              ✨ Show Me What I Can Make
            </button>
          }
        >
          Explore products, step-by-step instructions and required skills.
        </Empty>
      ) : (
        <>
          <div className="category-header">
            <div className="category-stats">
              <span className="stat-chip">
                {(data.product_categories || []).length} Categories
              </span>
              <span className="stat-chip">
                {(data.product_categories || []).reduce(
                  (sum, c) => sum + (c.products?.length || 0),
                  0,
                )}{" "}
                Products
              </span>
              <span className={"cache-badge " + (data.cached ? "" : "fresh")}>
                {data.cached
                  ? "Cached"
                  : `Generated in ${data.elapsed_seconds}s`}
              </span>
            </div>
            <button
              className="refresh-btn"
              onClick={() => w.categories(true)}
              aria-label="Regenerate product categories"
            >
              ↻
            </button>
          </div>
          <div className="equipment-filter-bar">
            {[
              ["all", "All Products"],
              ["easy", "Home / Hand Tools"],
              ["medium", "Small Workshop"],
              ["hard", "Commercial Scale"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={"equip-option " + (filter === id ? "active" : "")}
                aria-pressed={filter === id}
                onClick={() => {
                  setFilter(id);
                  if (id !== "all")
                    setExpanded(
                      Object.fromEntries(
                        (data.product_categories || []).map((_, i) => [
                          i,
                          true,
                        ]),
                      ),
                    );
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="category-accordion">
            {(data.product_categories || []).map((category, index) => {
              const products = (category.products || []).filter(
                (p) =>
                  filter === "all" ||
                  normalizeDifficulty(p.difficulty) === filter,
              );
              if (!products.length) return null;
              return (
                <section
                  className={
                    "accordion-item " + (expanded[index] ? "open" : "")
                  }
                  key={index}
                >
                  <button
                    className="accordion-header"
                    aria-expanded={!!expanded[index]}
                    onClick={() =>
                      setExpanded((p) => ({ ...p, [index]: !p[index] }))
                    }
                  >
                    <span className="accordion-title">
                      <span className="cat-icon">📦</span>
                      <span className="cat-name">{category.category_name}</span>
                      <span className="cat-count">
                        {filter === "all"
                          ? products.length
                          : `${products.length} of ${category.products.length}`}{" "}
                        products
                      </span>
                    </span>
                    <span className="accordion-arrow">▸</span>
                  </button>
                  <div className="accordion-body">
                    {products.map((p, i) => (
                      <article className="process-card" key={i}>
                        <div className="process-header">
                          <h3 className="process-title">{p.name}</h3>
                          <div className="process-badges">
                            <span
                              className={
                                "diff-badge diff-" +
                                normalizeDifficulty(p.difficulty)
                              }
                            >
                              {p.difficulty || "Medium"}
                            </span>
                            <span
                              className={
                                "pot-badge pot-" +
                                (p.market_potential || "medium")
                              }
                            >
                              {p.market_potential || "medium"} Demand
                            </span>
                          </div>
                        </div>
                        <div className="recipe-meta-row">
                          <div>
                            Difficulty:{" "}
                            {p.difficulty === "Easy"
                              ? "Beginner-friendly"
                              : p.difficulty === "Hard"
                                ? "Needs training & equipment"
                                : "Some practice needed"}
                          </div>
                          {p.estimated_cost && (
                            <div>Estimated cost: {p.estimated_cost}</div>
                          )}
                        </div>
                        <h4 className="process-section-title">
                          📋 Step-by-Step Process (Recipe)
                        </h4>
                        <ol className="process-timeline">
                          {(p.manufacturing_process || []).map((step, j) => (
                            <li className="timeline-step" key={j}>
                              <span className="timeline-number">{j + 1}</span>
                              <div className="timeline-content">{step}</div>
                            </li>
                          ))}
                        </ol>
                        <h4 className="process-section-title">
                          🛠 Skills & Tools Needed
                        </h4>
                        <Tags items={p.required_skills || []} />
                      </article>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
          {!(data.product_categories || []).some((c) =>
            (c.products || []).some(
              (p) =>
                filter === "all" ||
                normalizeDifficulty(p.difficulty) === filter,
            ),
          ) && <Empty title="No products match this filter" />}
          <EvidenceStamp data={data} />
        </>
      )}
    </div>
  );
}
