import React from "react";
import { Tags, Section } from "./common";

const properties = {
  strength: [
    "💪",
    "Strength",
    {
      high: "Very strong — ideal for durable items like furniture and tools",
      medium: "Moderate strength — good for baskets, trays, and home decor",
      low: "Lightweight — best for decorative and packaging items",
    },
  ],
  flexibility: [
    "🤸",
    "Flexibility",
    {
      high: "Very flexible — easy to bend and weave into shapes",
      medium: "Somewhat flexible — can be shaped with gentle effort",
      low: "Rigid — holds its shape well, good for structural items",
    },
  ],
  texture: [
    "✋",
    "Texture",
    {
      smooth: "Smooth finish — naturally pleasing to touch",
      rough: "Textured surface — gives a rustic, handmade feel",
      medium: "Medium texture — versatile for many product types",
    },
  ],
  water_resistance: [
    "💧",
    "Water Resistant",
    {
      high: "Yes — can handle moisture and outdoor use",
      medium: "Partial — needs some protection from water",
      low: "No — must keep dry, store indoors",
    },
  ],
  biodegradability: [
    "🌱",
    "Eco-Friendly",
    {
      high: "100% biodegradable & compostable",
      medium: "Mostly eco-friendly with minimal processing",
      low: "May need some chemical treatment",
    },
  ],
  workability: [
    "🛠️",
    "Ease of Crafting",
    {
      high: "Very easy — can be shaped with basic hand tools at home",
      easy: "Very easy — can be shaped with basic hand tools at home",
      medium: "Moderate — needs some practice and basic workshop tools",
      moderate: "Moderate — needs some practice and basic workshop tools",
      low: "Skilled — requires training and specialized equipment",
      difficult: "Skilled — requires training and specialized equipment",
    },
  ],
};
export default function Overview({ data }) {
  const m = data.material,
    g = data.graph || {};
  const pct = Math.round((parseFloat(m.sustainability_score) || 0) * 100);
  return (
    <>
      <header className="detail-header">
        <h1>{m.name}</h1>
        {m.scientific_name && <p className="sci-name">{m.scientific_name}</p>}
        {m.description && <p className="description">{m.description}</p>}
      </header>
      <div className="at-a-glance-card">
        {[
          [
            "🌿",
            "What is it?",
            m.description ||
              m.name +
                " — a Minor Forest Produce item collected by tribal communities.",
          ],
          [
            "💰",
            "Government Floor Price (MSP)",
            `₹${m.msp || "—"} per ${m.unit || "kg"}`,
          ],
          ["📅", "Best Collection Season", m.season],
          [
            "🚀",
            "Opportunity",
            g.current_products?.length
              ? `This material can be processed into ${g.current_products.length + (g.potential_products?.length || 0)} different products.`
              : null,
          ],
        ]
          .filter((x) => x[2])
          .map(([icon, label, value]) => (
            <div className="at-a-glance-item" key={label}>
              <span className="at-a-glance-icon">{icon}</span>
              <div>
                <div className="at-a-glance-label">{label}</div>
                <div className="at-a-glance-text">{value}</div>
              </div>
            </div>
          ))}
      </div>
      {!!m.msp && (
        <>
          <div className="value-multiplier-banner">
            <div className="vm-stage">
              <div className="vm-label">Collector MSP</div>
              <div className="vm-price msp">
                ₹{m.msp}/{m.unit || "kg"}
              </div>
            </div>
            <div className="vm-arrow">→</div>
            <div className="vm-stage">
              <div className="vm-label">
                Illustrative value after processing
              </div>
              <div className="vm-price market">
                ₹{Math.round(m.msp * 8)}–{Math.round(m.msp * 15)}/
                {m.unit || "kg"}
              </div>
            </div>
            <div className="vm-multiplier">8–15× illustration</div>
          </div>
          <p className="evidence-stamp">
            Fixed illustration from the original interface, not a measured
            market price or guaranteed return.
          </p>
        </>
      )}
      <div className="info-chips">
        {[
          ["MSP", `₹${m.msp || "—"}/${m.unit || "kg"}`],
          ["Category", m.category],
          ["Season", m.season],
          ["Shelf Life", m.shelf_life],
          [
            "Availability",
            m.availability_band !== "unknown" && m.availability_band,
          ],
        ]
          .filter((x) => x[1])
          .map(([label, v]) => (
            <div className="chip" key={label}>
              <span className="chip-label">{label}</span>
              <span className="chip-value">{v}</span>
            </div>
          ))}
      </div>
      <div className="scores-section">
        {m.sustainability_score != null && (
          <div className="score-card">
            <h3 className="score-header">🌿 Sustainability Score</h3>
            <div className="score-gauge">
              <div
                className="gauge-circle"
                style={{
                  "--pct": pct,
                  "--color":
                    pct >= 70
                      ? "var(--green)"
                      : pct >= 40
                        ? "var(--amber)"
                        : "var(--red)",
                }}
              >
                <span className="gauge-value">{pct}%</span>
              </div>
            </div>
          </div>
        )}
        {m.durability_rating != null && (
          <div className="score-card">
            <h3 className="score-header">🛡 Durability</h3>
            <div className="durability-info">
              <span
                className={
                  "durability-badge badge-" +
                  (m.durability_rating === "high"
                    ? "green"
                    : m.durability_rating === "medium"
                      ? "amber"
                      : "red")
                }
              >
                {m.durability_rating}
              </span>
              <span className="lifespan-text">{m.estimated_lifespan}</span>
            </div>
          </div>
        )}
        {m.strength != null && (
          <div className="score-card wide">
            <h3 className="score-header">⚙ What This Material Is Like</h3>
            <div className="human-props-grid">
              {Object.entries(properties)
                .filter(([key]) => m[key])
                .map(([key, [icon, title, descriptions]]) => (
                  <div className="human-prop" key={key}>
                    <span className="human-prop-icon">{icon}</span>
                    <div>
                      <div className="human-prop-title">{title}</div>
                      <div className="human-prop-desc">
                        {descriptions[String(m[key]).toLowerCase()] || m[key]}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
      <div className="section-grid">
        {[
          ["📍 States", "states", "state"],
          ["🛠 Skills / Artisan Types", "skills", "skill"],
          ["📦 Current Products", "current_products", "product"],
          ["💡 Potential Products", "potential_products", "potential"],
          ["🗺 Districts", "districts", "district"],
          ["🏘 Clusters", "clusters", "cluster"],
        ].map(([title, key, cls]) => (
          <Section title={title} key={key}>
            <Tags items={g[key] || []} className={cls} />
          </Section>
        ))}
      </div>
    </>
  );
}
