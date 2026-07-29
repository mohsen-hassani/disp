import React from "react";
import { Icon } from "../core/Icon.jsx";

export function OfflineBanner({ showingSavedData }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, padding: "8px 16px",
      background: "var(--color-surface-sunken)", color: "var(--color-text-muted)",
      borderBottom: "1px solid var(--color-border)", fontSize: "var(--text-sm)",
    }}>
      <Icon name="wifi-off" size={16} />
      <span>You're offline.{showingSavedData ? " Showing saved data." : ""}</span>
    </div>
  );
}
