import React from "react";
import { Icon } from "../core/Icon.jsx";

export function Menu({ open, items, onClose, align = "right" }) {
  if (!open) return null;
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
      <div style={{
        position: "absolute", top: "calc(100% + 6px)", [align]: 0, minWidth: 200,
        background: "var(--color-surface-raised)", border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-overlay)", padding: 6, zIndex: 50,
      }}>
        {items.map((item, i) => (
          <button key={i} onClick={() => { item.onClick && item.onClick(); onClose(); }} style={{
            display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "8px 10px",
            background: "transparent", border: "none", borderRadius: "var(--radius-sm)", cursor: "pointer",
            fontSize: "var(--text-sm)", color: item.danger ? "var(--color-danger)" : "var(--color-text)",
            textAlign: "left",
          }}>
            {item.icon && <Icon name={item.icon} size={16} />}
            {item.label}
          </button>
        ))}
      </div>
    </>
  );
}
