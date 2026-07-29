import React from "react";

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 10, cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.5 : 1 }}>
      <span onClick={() => !disabled && onChange(!checked)} role="switch" aria-checked={checked} style={{
        width: 40, height: 24, borderRadius: "var(--radius-full)", position: "relative", flex: "0 0 auto",
        background: checked ? "var(--color-accent)" : "var(--color-surface-sunken)",
        border: "1px solid " + (checked ? "transparent" : "var(--color-border)"),
        transition: "background var(--duration-fast) var(--ease-standard)",
      }}>
        <span style={{
          position: "absolute", top: 2, left: checked ? 18 : 2, width: 18, height: 18, borderRadius: "50%",
          background: "var(--color-surface-raised)", transition: "left var(--duration-fast) var(--ease-standard)",
          boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
        }} />
      </span>
      {label && <span style={{ fontSize: "var(--text-base)" }}>{label}</span>}
    </label>
  );
}
