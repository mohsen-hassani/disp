import React from "react";
const { useState } = React;
import { Icon } from "../core/Icon.jsx";
import { Button } from "../core/Button.jsx";

// Secret fields never echo the real plaintext back from the server — "reveal" only
// ever un-masks the masked placeholder (e.g. a suffix hint). Replacing requires a new value.
export function SecretField({ label, maskedValue, helpText, onReplace }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
      <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--font-weight-medium)" }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          flex: 1, fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", padding: "10px 12px", minHeight: 44,
          borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)",
          background: "var(--color-surface-sunken)", color: "var(--color-text)",
          display: "flex", alignItems: "center", letterSpacing: revealed ? "normal" : "0.08em",
        }}>{revealed ? maskedValue : maskedValue.replace(/[^•]/g, m => m)}</span>
        <button aria-label={revealed ? "Hide" : "Show"} onClick={() => setRevealed(r => !r)} style={{
          width: 44, height: 44, borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)",
          background: "var(--color-surface-raised)", color: "var(--color-text)", cursor: "pointer",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}><Icon name={revealed ? "eye-off" : "eye"} size={18} /></button>
        {onReplace && <Button variant="secondary" size="sm" onClick={onReplace}>Replace</Button>}
      </div>
      {helpText && <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>{helpText}</span>}
    </div>
  );
}
