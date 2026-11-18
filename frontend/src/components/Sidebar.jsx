import React, { useState } from "react";
import { useWorkspace } from "../contexts/Workspace";
import { broadCategory, materialIcon } from "../utils/workflow";
import { ErrorBox, Loading } from "./common";

export default function Sidebar({ theme, toggleTheme, open, close }) {
  const w = useWorkspace();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const q = query.trim().toLowerCase();
  const list = w.materials.filter(
    (m) =>
      (filter === "all" || broadCategory(m.category) === filter) &&
      (!q ||
        [m.name, m.scientific_name, m.category].some((x) =>
          (x || "").toLowerCase().includes(q),
        )),
  );
  return (
    <aside
      className={"sidebar " + (open ? "sidebar-open" : "")}
      aria-label="Materials"
    >
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <h1>MAERII</h1>
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={
              "Switch to " + (theme === "light" ? "dark" : "light") + " theme"
            }
          >
            {theme === "light" ? "🌙" : "☀️"}
          </button>
          <button
            className="mobile-only plain-button"
            onClick={close}
            aria-label="Close material list"
          >
            ×
          </button>
        </div>
        <div className="subtitle">Forest Produce Business Guide</div>
      </div>
      <div className="search-container">
        <input
          id="material-search"
          className="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search materials…"
          aria-label="Search materials"
          autoComplete="off"
        />
      </div>
      <div className="sidebar-category-pills">
        {[
          ["all", "🌐 All"],
          ["forest", "🌲 Forest Produce"],
          ["agriculture", "🌾 Agriculture"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={"sidebar-pill " + (filter === id ? "active" : "")}
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
          >
            {label}{" "}
            <span className="pill-count">
              {
                w.materials.filter(
                  (m) => id === "all" || broadCategory(m.category) === id,
                ).length
              }
            </span>
          </button>
        ))}
      </div>
      <div className="material-list">
        {w.listLoading ? (
          <Loading />
        ) : w.listError ? (
          <ErrorBox message={w.listError} retry={w.loadMaterials} />
        ) : list.length ? (
          list.map((m) => (
            <button
              key={m.mfp_id}
              className={
                "material-item material-button " +
                (w.selectedId === m.mfp_id ? "active" : "")
              }
              aria-pressed={w.selectedId === m.mfp_id}
              onClick={() => {
                w.selectMaterial(m.mfp_id);
                close();
              }}
            >
              <span className="mat-name">
                {materialIcon(m.category)} {m.name}
              </span>
              <span className="mat-meta">
                MSP: ₹{m.msp || "—"}/{m.unit || "kg"} · {m.category || ""}
              </span>
            </button>
          ))
        ) : (
          <p className="empty-products">No matching materials.</p>
        )}
      </div>
      <div className="sidebar-footer">
        {list.length} of {w.materials.length} materials
      </div>
    </aside>
  );
}
