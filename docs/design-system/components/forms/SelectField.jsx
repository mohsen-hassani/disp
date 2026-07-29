import React from "react";
import { Icon } from "../core/Icon.jsx";

export function SelectField({ label, value, options, onChange, helpText }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
      <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--font-weight-medium)" }}>{label}</span>
      <span style={{ position: "relative", display: "block" }}>
        <select value={value} onChange={e => onChange && onChange(e.target.value)} style={{
          font: "inherit", fontSize: "var(--text-base)", padding: "10px 36px 10px 12px", minHeight: 44, width: "100%",
          borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)",
          background: "var(--color-surface-raised)", color: "var(--color-text)",
          appearance: "none", outline: "none",
        }}>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "var(--color-text-muted)", pointerEvents: "none" }}>
          <Icon name="chevron-down" size={16} />
        </span>
      </span>
      {helpText && <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>{helpText}</span>}
    </label>
  );
}
