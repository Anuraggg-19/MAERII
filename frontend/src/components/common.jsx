import React from "react";
import { safeUrl } from "../utils/workflow";
export function Loading({ children = "Loading…" }) {
  return (
    <div className="market-loading" role="status">
      <div className="spinner" />
      {children}
    </div>
  );
}
export function ErrorBox({ message, retry }) {
  return (
    <div className="error-box" role="alert">
      <p>{message}</p>
      {retry && (
        <button className="market-trigger" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function Empty({ title, children, action }) {
  return (
    <div className="journey-prompt">
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Tags({ items = [], className = "" }) {
  return items.length ? (
    <div className="tag-list">
      {items.map((x, i) => (
        <span className={"tag " + className} key={i}>
          {typeof x === "object" ? x.name : x}
        </span>
      ))}
    </div>
  ) : (
    <p className="empty-tag">No data available</p>
  );
}
export function Section({ title, children }) {
  return (
    <section className="section-card">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
export function List({ items = [] }) {
  return (
    <ul className="insight-list">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  );
}
export function ExternalLink({ url, children, ...props }) {
  const href = safeUrl(url);
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ) : (
    <span {...props}>{children}</span>
  );
}
export function EvidenceStamp({ data }) {
  return (
    <p className="evidence-stamp">
      {data.cached ? "Saved result" : "Result from this request"}
      {data._persistence?.created_at
        ? " · Recorded " + data._persistence.created_at
        : ""}
      {data.provider ? " · Provider: " + data.provider : ""}. Prices and
      estimates are not guaranteed current sales or earnings.
    </p>
  );
}
