import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useWorkspace } from "../contexts/Workspace";
import { Loading, ErrorBox, EvidenceStamp, Empty } from "./common";
import { ProductCard } from "./Market";

export function StructuredValue({ value }) {
  if (value == null || value === "")
    return <p className="empty-tag">Not provided in this result.</p>;
  if (Array.isArray(value))
    return (
      <ul className="blueprint-values">
        {value.map((v, i) => (
          <li key={i}>
            <StructuredValue value={v} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <dl className="blueprint-fields">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt>{k.replaceAll("_", " ")}</dt>
            <dd>
              {k === "hex" && /^#[0-9a-f]{6}$/i.test(String(v)) ? (
                <span className="blueprint-swatch" style={{ background: v }} />
              ) : null}
              <StructuredValue value={v} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <p>{String(value)}</p>;
}
const tabs = [
  ["product_design", "Look & Feel"],
  ["marketing_strategy", "How to Sell"],
  ["packaging", "Packaging Ideas"],
  ["sales_channels", "Where to Sell"],
  ["examples", "Market Examples"],
];
const labels = {
  inspiration: "What Should It Look Like?",
  form_factor: "Shape & Form Factor",
  color_palette: "Suggested Color Palette",
  modernization_tips: "How to Make It Modern",
  design_principles: "Key Design Rules",
  positioning: "Positioning",
  usp: "What Makes Your Product Special",
  pricing_strategy: "Pricing Strategy",
  target_segments: "Who Will Buy This?",
  storytelling_angle: "Your Product Story",
  digital_marketing: "Online Promotion Ideas",
  material: "Primary Packaging",
  secondary_packaging: "Secondary Packaging",
  color_scheme: "Package Look",
  label_elements: "What Goes on the Label",
  certifications: "Certificates & Trust Marks",
  size_variants: "Pack Sizes & Pricing",
  sustainability_notes: "Eco-Friendly Points",
  online: "Sell Online Here",
  offline: "Sell In-Person Here",
  b2b: "Sell to Businesses",
  export: "International Opportunities",
};

export default function Blueprint({ recommendation, close }) {
  const w = useWorkspace();
  const [tab, setTab] = useState("product_design");
  const dialog = useRef(null);
  const data = w.current.marketing?.data;
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current?.querySelector("button")?.focus();
    return () => previous?.focus();
  }, []);
  function keys(e) {
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
    }
    if (e.key === "Tab") {
      const nodes = [
        ...dialog.current.querySelectorAll(
          'button,a[href],select,input,[tabindex="0"]',
        ),
      ].filter((x) => !x.disabled);
      const first = nodes[0],
        last = nodes.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      }
      if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
  }
  const enhancement = data?.enhancement || data || {};
  return createPortal(
    <div
      className="enhancement-overlay active"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="enhancement-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="blueprint-title"
        onKeyDown={keys}
        ref={dialog}
      >
        <header className="enhancement-modal-header">
          <div className="enhancement-title-area">
            <span className="enhancement-ai-badge">Product Enhancement AI</span>
            <h2 id="blueprint-title">{recommendation.product_name}</h2>
            <p className="enhancement-subtitle">
              {recommendation.category_name} · {recommendation.difficulty} ·
              Expected: INR{" "}
              {Number(recommendation.expected_selling_price_inr).toFixed(2)}{" "}
              {recommendation.pricing_unit}
            </p>
          </div>
          <button
            className="enhancement-close"
            aria-label="Close business blueprint"
            onClick={close}
          >
            ×
          </button>
        </header>
        <div className="enhancement-modal-body">
          {w.busy("marketing") ? (
            <Loading>Building your detailed business blueprint…</Loading>
          ) : w.error("marketing") ? (
            <ErrorBox
              message={w.error("marketing")}
              retry={() => w.enhance(recommendation)}
            />
          ) : data ? (
            <>
              <nav className="enhancement-tabs" aria-label="Blueprint sections">
                {tabs.map(([id, label]) => (
                  <button
                    key={id}
                    className={"enh-tab " + (tab === id ? "active" : "")}
                    aria-pressed={tab === id}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </nav>
              {tab === "examples" ? (
                <div className="enh-section">
                  <h3>Market Product Examples</h3>
                  <div className="examples-grid">
                    {(data.related_examples || []).slice(0, 2).map((p, i) => (
                      <ProductCard key={i} product={p} />
                    ))}
                  </div>
                  {!data.related_examples?.length && (
                    <Empty title="No direct market examples found">
                      Missing examples do not establish low competition or high
                      demand.
                    </Empty>
                  )}
                </div>
              ) : (
                <div className="blueprint-grid">
                  {Object.entries(enhancement[tab] || {}).map(
                    ([key, value]) => (
                      <section className="enh-section" key={key}>
                        <h3>{labels[key] || key.replaceAll("_", " ")}</h3>
                        <StructuredValue value={value} />
                      </section>
                    ),
                  )}
                  {!Object.keys(enhancement[tab] || {}).length && (
                    <Empty title="No information provided for this section" />
                  )}
                </div>
              )}
              <EvidenceStamp data={data} />
              <p className="evidence-stamp">
                Generated business guidance requires validation. Certificates,
                pricing and market opportunities are not independently verified
                here.
              </p>
            </>
          ) : (
            <Empty title="Blueprint not available yet" />
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}
