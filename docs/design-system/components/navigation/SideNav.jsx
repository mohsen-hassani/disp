import React from "react";
import { Icon } from "../core/Icon.jsx";

// Appears at md+ (768px); below that, use BottomNav instead.
export function SideNav({ links }) {
  return (
    <nav style={{
      width: 220, flex: "0 0 auto", padding: "var(--space-4) var(--space-2)",
      borderRight: "1px solid var(--color-border)", display: "flex", flexDirection: "column", gap: 2,
    }}>
      {links.map((l, i) => (
        <button key={i} onClick={l.onClick} style={{
          display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: "var(--radius-sm)",
          border: "none", cursor: "pointer", textAlign: "left", fontSize: "var(--text-sm)",
          background: l.active ? "var(--color-surface-sunken)" : "transparent",
          color: l.active ? "var(--color-text)" : "var(--color-text-muted)",
          fontWeight: l.active ? "var(--font-weight-medium)" : "var(--font-weight-regular)",
        }}>
          <Icon name={l.icon} size={18} />
          {l.label}
        </button>
      ))}
    </nav>
  );
}
