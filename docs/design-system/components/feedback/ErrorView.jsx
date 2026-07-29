import React from "react";
import { Icon } from "../core/Icon.jsx";
import { Button } from "../core/Button.jsx";

export function ErrorView({ title = "Something went wrong", message, onRetry, fullPage }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 8,
      padding: fullPage ? "var(--space-12) var(--space-4)" : "var(--space-6) var(--space-4)",
      justifyContent: fullPage ? "center" : undefined, minHeight: fullPage ? "60vh" : undefined,
    }}>
      <span style={{
        width: 40, height: 40, borderRadius: "var(--radius-md)",
        background: "color-mix(in oklch, var(--color-danger) 14%, var(--color-surface-raised))",
        color: "var(--color-danger)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 4,
      }}><Icon name="triangle-alert" size={20} /></span>
      <span style={{ fontWeight: "var(--font-weight-medium)", fontSize: "var(--text-base)" }}>{title}</span>
      <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text-muted)", maxWidth: "40ch" }}>{message}</span>
      {onRetry && <div style={{ marginTop: 8 }}><Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button></div>}
    </div>
  );
}
