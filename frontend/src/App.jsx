import React, { useEffect, useRef, useState } from "react";
import { WorkspaceProvider, useWorkspace } from "./contexts/Workspace";
import { readPreference, writePreference } from "./utils/workflow";
import Sidebar from "./components/Sidebar";
import Overview from "./components/Overview";
import Products from "./components/Products";
import Market from "./components/Market";
import BusinessPlan from "./components/BusinessPlan";
import Assistant from "./components/assistant/Assistant";
import { Loading, ErrorBox, Empty } from "./components/common";

const tabs = [
  ["overview", "🌿", "Overview", "Material Story & Value"],
  ["categories", "🏭", "What to Make", "Products & Recipes"],
  ["market", "📊", "Market Prices", "Real Online Demand"],
  ["recommendations", "🎯", "Business Plan", "Your Earning Blueprint"],
];
function Layout() {
  const w = useWorkspace();
  const [theme, setTheme] = useState(() =>
    readPreference("maerii-theme", "dark"),
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const main = useRef(null);
  useEffect(() => {
    if (theme === "light")
      document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    writePreference("maerii-theme", theme);
  }, [theme]);
  useEffect(() => {
    if (main.current) main.current.scrollTop = 0;
  }, [w.selectedId, w.section]);
  function findMaterial() {
    setSidebarOpen(true);
    requestAnimationFrame(() =>
      document.getElementById("material-search")?.focus(),
    );
  }
  const detail = w.current.material?.data;
  return (
    <div className="react-app">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="app-container">
        {sidebarOpen && (
          <button
            className="sidebar-scrim mobile-only"
            aria-label="Close material list"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <Sidebar
          theme={theme}
          toggleTheme={() =>
            setTheme((t) => (t === "light" ? "dark" : "light"))
          }
          open={sidebarOpen}
          close={() => setSidebarOpen(false)}
        />
        <main
          className="main-content"
          id="main-content"
          ref={main}
          tabIndex="-1"
        >
          <div className="mobile-toolbar">
            <button className="plain-button" onClick={findMaterial}>
              ☰ Materials
            </button>
            <span>MAERII</span>
          </div>
          {!w.selectedId ? (
            <Empty title="Select a Material">
              Pick a forest produce from the list to discover what you can make,
              market prices, and business opportunities.
            </Empty>
          ) : (
            <>
              <nav className="detail-tabs" aria-label="Material sections">
                {tabs.map(([id, icon, label, subtitle]) => (
                  <button
                    className={
                      "detail-tab " + (w.section === id ? "active" : "")
                    }
                    key={id}
                    aria-pressed={w.section === id}
                    onClick={() => w.navigate(id)}
                  >
                    <span className="tab-icon">{icon}</span>
                    <span className="tab-label">{label}</span>
                    <span className="tab-subtitle">{subtitle}</span>
                  </button>
                ))}
              </nav>
              {w.busy("material") ? (
                <Loading>Loading material information…</Loading>
              ) : w.error("material") ? (
                <ErrorBox
                  message={w.error("material")}
                  retry={() => w.selectMaterial(w.selectedId)}
                />
              ) : (
                detail && (
                  <div key={w.selectedId}>
                    <section
                      className={
                        "tab-panel " +
                        (w.section === "overview" ? "active" : "")
                      }
                      hidden={w.section !== "overview"}
                      aria-label="Overview"
                    >
                      <Overview data={detail} />
                    </section>
                    <section
                      className={
                        "tab-panel " +
                        (w.section === "categories" ? "active" : "")
                      }
                      hidden={w.section !== "categories"}
                      aria-label="What to Make"
                    >
                      <Products />
                    </section>
                    <section
                      className={
                        "tab-panel " + (w.section === "market" ? "active" : "")
                      }
                      hidden={w.section !== "market"}
                      aria-label="Market Prices"
                    >
                      <Market />
                    </section>
                    <section
                      className={
                        "tab-panel " +
                        (w.section === "recommendations" ? "active" : "")
                      }
                      hidden={w.section !== "recommendations"}
                      aria-label="Business Plan"
                    >
                      <BusinessPlan />
                    </section>
                  </div>
                )
              )}
            </>
          )}
        </main>
      </div>
      <Assistant findMaterial={findMaterial} />
    </div>
  );
}
export default function App() {
  return (
    <WorkspaceProvider>
      <Layout />
    </WorkspaceProvider>
  );
}
