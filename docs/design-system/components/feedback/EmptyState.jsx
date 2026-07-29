import React from "react";
import { Icon } from "../core/Icon.jsx";

// Terse, factual copy — no illustration, no encouragement-flavored copy.
export function EmptyState({ icon = "inbox", title, description, action }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 8,
      padding: "var(--space-8) var(--space-4)", color: "var(--color-text-muted)",
    }}>
      <span style={{
        width: 40, height: 40, borderRadius: "var(--radius-md)", background: "var(--color-surface-sunken)",
        display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 4,
      }}><Icon name={icon} size={20} /></span>
      <span style={{ color: "var(--color-text)", fontWeight: "var(--font-weight-medium)", fontSize: "var(--text-base)" }}>{title}</span>
      {description && <span style={{ fontSize: "var(--text-sm)", maxWidth: "32ch" }}>{description}</span>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}
