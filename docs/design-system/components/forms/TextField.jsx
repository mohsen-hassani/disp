import React from "react";

export function TextField({ label, value, onChange, type = "text", placeholder, helpText, error, disabled }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
      <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--font-weight-medium)" }}>{label}</span>
      <input
        type={type} value={value} placeholder={placeholder} disabled={disabled}
        onChange={e => onChange && onChange(e.target.value)}
        style={{
          font: "inherit", fontSize: "var(--text-base)", padding: "10px 12px", minHeight: 44,
          borderRadius: "var(--radius-sm)", border: `1px solid ${error ? "var(--color-danger)" : "var(--color-border)"}`,
          background: "var(--color-surface-raised)", color: "var(--color-text)",
          outline: "none", transition: "border-color var(--duration-fast) var(--ease-standard)",
        }}
      />
      {error ? (
        <span style={{ fontSize: "var(--text-xs)", color: "var(--color-danger)" }}>{error}</span>
      ) : helpText ? (
        <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>{helpText}</span>
      ) : null}
    </label>
  );
}
