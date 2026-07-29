import React from "react";
import { Icon } from "../core/Icon.jsx";

// Mobile only (below md/768px). Sits below toasts in stacking order.
export function BottomNav({ links }) {
  return (
    <nav style={{
      display: "flex", borderTop: "1px solid var(--color-border)", background: "var(--color-surface-raised)",
      position: "sticky", bottom: 0, zIndex: 30,
    }}>
      {links.map((l, i) => (
        <button key={i} onClick={l.onClick} style={{
          flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
          padding: "8px 4px 10px", minHeight: 56, border: "none", background: "transparent", cursor: "pointer",
          color: l.active ? "var(--color-accent)" : "var(--color-text-muted)",
        }}>
          <Icon name={l.icon} size={20} />
          <span style={{ fontSize: "var(--text-xs)" }}>{l.label}</span>
        </button>
      ))}
    </nav>
  );
}
