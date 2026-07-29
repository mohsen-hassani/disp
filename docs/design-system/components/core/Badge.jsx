import React from "react";

export function Badge({ children, tone = "neutral" }) {
  const tones = {
    neutral: { background: "var(--color-surface-sunken)", color: "var(--color-text-muted)", border: "var(--color-border)" },
    success: { background: "color-mix(in oklch, var(--color-success) 16%, var(--color-surface-raised))", color: "var(--color-success)", border: "transparent" },
    warning: { background: "color-mix(in oklch, var(--color-warning) 16%, var(--color-surface-raised))", color: "var(--color-warning)", border: "transparent" },
    danger: { background: "color-mix(in oklch, var(--color-danger) 16%, var(--color-surface-raised))", color: "var(--color-danger)", border: "transparent" },
    accent: { background: "color-mix(in oklch, var(--color-accent) 16%, var(--color-surface-raised))", color: "var(--color-accent)", border: "transparent" },
  };
  const t = tones[tone];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px",
      fontSize: "var(--text-xs)", fontWeight: "var(--font-weight-medium)",
      borderRadius: "var(--radius-full)", background: t.background, color: t.color,
      border: `1px solid ${t.border}`, lineHeight: 1.4,
    }}>{children}</span>
  );
}
