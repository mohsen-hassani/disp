import React from "react";

export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--color-border)" }}>
      {tabs.map((t, i) => (
        <button key={i} onClick={() => onChange(i)} style={{
          padding: "10px 4px", marginRight: 20, background: "none", border: "none", cursor: "pointer",
          fontSize: "var(--text-sm)", fontWeight: "var(--font-weight-medium)",
          color: active === i ? "var(--color-text)" : "var(--color-text-muted)",
          borderBottom: active === i ? "2px solid var(--color-accent)" : "2px solid transparent",
          marginBottom: -1, transition: "color var(--duration-fast) var(--ease-standard)",
        }}>{t}</button>
      ))}
    </div>
  );
}
