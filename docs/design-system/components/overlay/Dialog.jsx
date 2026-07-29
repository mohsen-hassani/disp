import React from "react";
import { IconButton } from "../core/IconButton.jsx";
import { Icon } from "../core/Icon.jsx";

export function Dialog({ open, title, children, onClose, footer }) {
  if (!open) return null;
  return (
    <div style={{
      position: "absolute", inset: 0, background: "rgba(13,15,18,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 50,
      transition: "opacity var(--duration-overlay) var(--ease-standard)",
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        width: "100%", maxWidth: 440, background: "var(--color-surface-raised)", color: "var(--color-text)",
        borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-overlay)", border: "1px solid var(--color-border)",
        display: "flex", flexDirection: "column", maxHeight: "85vh",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 16px 12px" }}>
          <span style={{ fontSize: "var(--text-lg)", fontWeight: "var(--font-weight-semibold)" }}>{title}</span>
          <IconButton label="Close" onClick={onClose}><Icon name="x" size={18} /></IconButton>
        </div>
        <div style={{ padding: "0 16px 16px", overflowY: "auto" }}>{children}</div>
        {footer && <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "12px 16px", borderTop: "1px solid var(--color-border)" }}>{footer}</div>}
      </div>
    </div>
  );
}
