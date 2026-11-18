import React, { useRef, useState } from "react";
import { useWorkspace } from "../contexts/Workspace";
import { monthlyIncome } from "../utils/workflow";
import { Empty, Loading, ErrorBox, EvidenceStamp, Tags } from "./common";
import Blueprint from "./Blueprint";

// Preserve the legacy distinction between checking motifs and changing region.
const toggleMotifs = {
  "Madhya Pradesh": "Gond art patterns",
  Maharashtra: "Warli art patterns",
  Rajasthan: "Mandana / Phad art",
  Odisha: "Pattachitra / Saura art",
  Jharkhand: "Sohrai / Khovar art",
  Chhattisgarh: "Pithora / Dhokra patterns",
  Gujarat: "Rogan / Ahir embroidery motifs",
  "West Bengal": "Patachitra / Kantha motifs",
  Bihar: "Madhubani art patterns",
  Uttarakhand: "Aipan art patterns",
};
const changeMotifs = {
  ...toggleMotifs,
  "Andhra Pradesh": "Cheriyal / Nirmal art",
  Telangana: "Cheriyal scroll motifs",
  Karnataka: "Lambani / Mysore motifs",
  "Tamil Nadu": "Kolam / Tanjore motifs",
  Kerala: "Mural / Theyyam motifs",
  "Himachal Pradesh": "Chamba Rumal / Kinnauri motifs",
  Assam: "Muga silk / Jaapi motifs",
};
const options = [
  [
    "artisan_skill_level",
    "Who is making the product?",
    [
      ["Beginner", "Beginner"],
      ["Intermediate", "Intermediate"],
      ["Advanced", "Advanced"],
    ],
  ],
  [
    "budget_constraint",
    "Starting capital / budget?",
    [
      ["Low", "Under ₹5K"],
      ["Medium", "₹5K–25K"],
      ["High", "Over ₹25K"],
    ],
  ],
  [
    "production_time",
    "Production speed needed?",
    [
      ["Quick turnaround", "Quick"],
      ["Moderate", "Moderate"],
      ["Long-term", "Long-term"],
    ],
  ],
];
export default function BusinessPlan() {
  const w = useWorkspace();
  const [constraints, setConstraints] = useState({
    artisan_skill_level: "Beginner",
    budget_constraint: "Low",
    production_time: "Quick turnaround",
    region_context: "All listed regions",
    cultural_motifs: null,
  });
  const [motifs, setMotifs] = useState(false),
    [editing, setEditing] = useState(false),
    [blueprint, setBlueprint] = useState(null);
  const [calcIndex, setCalcIndex] = useState(0),
    [units, setUnits] = useState(50);
  const calc = useRef(null);
  const data = w.current.recommendations?.data;
  const recommendations = data?.recommendations || [];
  const states = [
    ...new Set(
      (w.current.material?.data.graph?.states || []).map((s) =>
        typeof s === "string" ? s : s.name,
      ),
    ),
  ]
    .filter(Boolean)
    .sort();
  const rec = recommendations[calcIndex] || recommendations[0];
  const income = rec ? monthlyIncome(rec, units) : null;
  if (!w.current.categories || w.current.market?.data.status !== "complete")
    return (
      <Empty
        title={
          "Complete " +
          (!w.current.categories ? "What to Make" : "Market Prices") +
          " first"
        }
        action={
          <button
            className="market-trigger"
            onClick={() =>
              w.navigate(!w.current.categories ? "categories" : "market")
            }
          >
            Open prerequisite section
          </button>
        }
      >
        Your business plan needs product categories and market evidence.
      </Empty>
    );
  async function submit(event) {
    event.preventDefault();
    const response = await w.recommend(constraints);
    if (response) {
      setEditing(false);
      setCalcIndex(0);
    }
  }
  return (
    <div className="market-section">
      {(!data || editing) && (
        <form className="wizard-form wizard-command-center" onSubmit={submit}>
          <div className="wizard-layout-split">
            <div className="wizard-left-panel">
              <header className="wizard-panel-header">
                <h2 className="wizard-panel-title">
                  Artisan & Production Preferences
                </h2>
              </header>
              <div className="wizard-grid-2x2">
                {options.map(([key, title, choices], i) => (
                  <fieldset className="wizard-step-group" key={key}>
                    <legend className="wizard-step-title">
                      {i + 1}. {title}
                    </legend>
                    <div className="wizard-card-options">
                      {choices.map(([value, label]) => (
                        <label
                          className={
                            "wizard-card-option " +
                            (constraints[key] === value ? "selected" : "")
                          }
                          key={value}
                        >
                          <input
                            type="radio"
                            name={key}
                            value={value}
                            checked={constraints[key] === value}
                            onChange={() =>
                              setConstraints((c) => ({ ...c, [key]: value }))
                            }
                          />
                          <span className="wizard-card-text">{label}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                ))}
                <fieldset className="wizard-step-group">
                  <legend className="wizard-step-title">
                    4. Target region & cultural motifs
                  </legend>
                  <label htmlFor="region-choice">Target region</label>
                  <select
                    id="region-choice"
                    className="wizard-region-dropdown"
                    value={constraints.region_context}
                    onChange={(e) =>
                      setConstraints((c) => ({
                        ...c,
                        region_context: e.target.value,
                        cultural_motifs: motifs
                          ? changeMotifs[e.target.value] ||
                            "Traditional tribal designs"
                          : null,
                      }))
                    }
                  >
                    <option>All listed regions</option>
                    {states.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <label className="wizard-motif-toggle">
                    <input
                      type="checkbox"
                      checked={motifs}
                      onChange={(e) => {
                        setMotifs(e.target.checked);
                        setConstraints((c) => ({
                          ...c,
                          cultural_motifs: e.target.checked
                            ? toggleMotifs[c.region_context] ||
                              "Traditional tribal designs"
                            : null,
                        }));
                      }}
                    />
                    Include{" "}
                    {changeMotifs[constraints.region_context] ||
                      "local tribal art motifs"}{" "}
                    in designs?
                  </label>
                </fieldset>
              </div>
            </div>
            <aside className="wizard-right-panel">
              <span className="wizard-summary-badge">
                AI Feasibility Engine
              </span>
              <h3 className="wizard-summary-heading">Ready to Plan?</h3>
              <p className="wizard-summary-desc">
                Product suggestions, equipment requirements and estimates based
                on your choices.
              </p>
              <div className="wizard-live-summary">
                {options.map(([key, , choices]) => (
                  <div className="summary-pill" key={key}>
                    {choices.find((x) => x[0] === constraints[key])?.[1]}
                  </div>
                ))}
                <div className="summary-pill">{constraints.region_context}</div>
              </div>
              <button
                className="blueprint-cta-btn wizard-side-btn"
                disabled={w.busy("recommendations")}
                type="submit"
              >
                {w.busy("recommendations")
                  ? "Creating your plan…"
                  : "🎯 Generate My Business Plan"}
              </button>
            </aside>
          </div>
        </form>
      )}
      {w.error("recommendations") && (
        <ErrorBox message={w.error("recommendations")} />
      )}
      {w.busy("recommendations") && (
        <Loading>Creating your custom business plan…</Loading>
      )}
      {data && !editing && (
        <>
          <div className="rec-results-top-bar">
            <button
              className="rec-regenerate-btn"
              onClick={() => setEditing(true)}
            >
              ↻ Change Preferences & Regenerate
            </button>
          </div>
          <div className="recommendation-grid">
            {recommendations.map((item, index) => (
              <article className="recommendation-card" key={index}>
                <div className="recommendation-card-header">
                  <div>
                    <h3>{item.product_name}</h3>
                    <p>{item.category_name}</p>
                    <div className="rec-badge-row">
                      <span className="product-origin-badge">
                        {item.product_origin === "Existing Product"
                          ? "📦 Existing Product"
                          : "✨ New Product Idea"}
                      </span>
                      {item.pricing_unit && (
                        <span className="pricing-unit-badge">
                          {item.pricing_unit}
                        </span>
                      )}
                    </div>
                  </div>
                  <span
                    className={
                      "diff-badge diff-" + String(item.difficulty).toLowerCase()
                    }
                  >
                    {item.difficulty}
                  </span>
                </div>
                <p>{item.rationale}</p>
                <div className="recommendation-metrics">
                  {[
                    [
                      "INR " + Number(item.unit_cost_inr).toFixed(2),
                      "Making Cost",
                    ],
                    [
                      "INR " +
                        Number(item.expected_selling_price_inr).toFixed(2),
                      "Selling Price",
                    ],
                    [
                      Number(item.profit_margin_percent).toFixed(1) + "%",
                      "Your Profit %",
                    ],
                    [item.demand_label || "Medium", "Buyer Demand"],
                  ].map(([v, label]) => (
                    <div key={label}>
                      <strong>{v}</strong>
                      <span>
                        {label}
                        {item.pricing_unit && label.includes("Cost")
                          ? ` (${item.pricing_unit})`
                          : ""}
                      </span>
                    </div>
                  ))}
                </div>
                <h4>Required Skills</h4>
                <Tags items={item.required_skills || []} />
                <div className="recommendation-tags">
                  <span>{item.export_potential} export</span>
                  <span>{item.target_customer_segment}</span>
                </div>
                <div className="rec-actions">
                  <button
                    className="blueprint-cta-btn"
                    disabled={w.busy("marketing")}
                    onClick={() => {
                      setBlueprint(item);
                      w.enhance(item);
                    }}
                  >
                    Open Full Business Blueprint
                  </button>
                  <button
                    className="calc-income-btn"
                    onClick={() => {
                      setCalcIndex(index);
                      calc.current?.scrollIntoView({ block: "center" });
                    }}
                  >
                    Calculate Monthly Income
                  </button>
                </div>
                <details className="artisan-details">
                  <summary>Artisan guide</summary>
                  <ol className="artisan-guide">
                    {(item.artisan_guide || []).map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                </details>
              </article>
            ))}
          </div>
          {!recommendations.length && (
            <Empty title="No recommendations were returned" />
          )}
          {rec && (
            <section className="profit-calc-section" ref={calc}>
              <div className="profit-calc-header">
                <h3 className="profit-calc-title">
                  💰 Monthly Income Calculator
                </h3>
                <select
                  className="profit-product-select"
                  aria-label="Calculator product"
                  value={calcIndex}
                  onChange={(e) => setCalcIndex(Number(e.target.value))}
                >
                  {recommendations.map((r, i) => (
                    <option value={i} key={i}>
                      {r.product_name} (Cost: ₹{Math.round(r.unit_cost_inr)} |
                      Price: ₹{Math.round(r.expected_selling_price_inr)})
                    </option>
                  ))}
                </select>
              </div>
              <div className="profit-selected-banner">
                <span>
                  Calculating for: <strong>{rec.product_name}</strong>
                </span>
                <span>Making Cost: ₹{Math.round(rec.unit_cost_inr || 0)}</span>
                <span>
                  Selling Price: ₹
                  {Math.round(rec.expected_selling_price_inr || 0)}
                </span>
                <span>
                  Profit per Unit: ₹
                  {Math.round(rec.expected_selling_price_inr || 0) -
                    Math.round(rec.unit_cost_inr || 0)}{" "}
                  {rec.pricing_unit && `(${rec.pricing_unit})`}
                </span>
              </div>
              <label className="profit-slider-row">
                If you produce and sell this many units per month:
                <input
                  className="profit-slider"
                  type="range"
                  min="10"
                  max="500"
                  step="10"
                  value={units}
                  onChange={(e) => setUnits(Number(e.target.value))}
                />
                <output className="profit-unit-count">{units}</output>
              </label>
              <div className="profit-result-grid">
                {[
                  ["cost", "Monthly Cost"],
                  ["revenue", "Monthly Revenue"],
                  ["profit", "Monthly Net Profit"],
                ].map(([key, label]) => (
                  <div className="profit-result-item" key={key}>
                    <div className="profit-result-label">{label}</div>
                    <div className={"profit-result-value " + key}>
                      ₹{Math.round(income[key]).toLocaleString("en-IN")}
                    </div>
                  </div>
                ))}
              </div>
              <p className="evidence-stamp">
                Scenario estimate assuming all entered units sell at the
                displayed price; not guaranteed earnings.
              </p>
            </section>
          )}
          <EvidenceStamp data={data} />
        </>
      )}
      {blueprint && (
        <Blueprint
          recommendation={blueprint}
          close={() => {
            setBlueprint(null);
            w.setProduct(null);
          }}
        />
      )}
    </div>
  );
}
