import React from "react";
import { Icon } from "../core/Icon.jsx";

export function Toast({ message, tone = "neutral", actionLabel, onAction, onDismiss }) {
  const accent = tone === "success" ? "var(--color-success)" : tone === "danger" ? "var(--color-danger)" : "var(--color-text-muted)";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", maxWidth: 380,
      background: "var(--color-surface-raised)", color: "var(--color-text)",
      borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-overlay)", border: "1px solid var(--color-border)",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: accent, flex: "0 0 auto" }} />
      <span style={{ flex: 1, fontSize: "var(--text-sm)" }}>{message}</span>
      {actionLabel && <button onClick={onAction} style={{ background: "none", border: "none", color: "var(--color-accent)", fontWeight: "var(--font-weight-medium)", fontSize: "var(--text-sm)", cursor: "pointer" }}>{actionLabel}</button>}
      {onDismiss && <button aria-label="Dismiss" onClick={onDismiss} style={{ background: "none", border: "none", color: "var(--color-text-muted)", cursor: "pointer", display: "flex" }}><Icon name="x" size={16}/></button>}
    </div>
  );
}
