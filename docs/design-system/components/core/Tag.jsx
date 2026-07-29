import React from "react";
import { Icon } from "./Icon.jsx";

export function Tag({ children, onRemove }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 8px 4px 10px",
      fontSize: "var(--text-sm)", borderRadius: "var(--radius-sm)",
      background: "var(--color-surface-sunken)", color: "var(--color-text)",
      border: "1px solid var(--color-border)",
    }}>
      {children}
      {onRemove && (
        <button onClick={onRemove} aria-label={`Remove ${children}`} style={{
          display: "inline-flex", border: "none", background: "transparent", cursor: "pointer",
          color: "var(--color-text-muted)", padding: 0,
        }}><Icon name="x" size={14} /></button>
      )}
    </span>
  );
}
