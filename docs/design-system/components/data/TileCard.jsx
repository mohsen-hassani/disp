import React from "react";
import { Icon } from "../core/Icon.jsx";
import { IconButton } from "../core/IconButton.jsx";

export function TileItem({ primary, secondary, badge }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 0" }}>
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{primary}</span>
        {secondary && <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>{secondary}</span>}
      </div>
      {badge}
    </div>
  );
}

export function TileCard({ title, icon, children, actions, onRefresh, state = "default" }) {
  return (
    <div style={{
      background: "var(--color-surface-raised)", border: "1px solid var(--color-border)",
      borderRadius: "var(--radius-md)", padding: "var(--space-4)", display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name={icon} size={18} />
          <span style={{ fontWeight: "var(--font-weight-medium)", fontSize: "var(--text-base)" }}>{title}</span>
        </div>
        {onRefresh && <IconButton label="Refresh" size="sm" onClick={onRefresh}><Icon name="refresh-cw" size={15} /></IconButton>}
      </div>
      <div style={{ borderTop: "1px solid var(--color-border)", marginTop: 2 }}>
        {state === "loading" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "10px 0" }}>
            <span style={{ display: "block", height: 14, width: "70%", borderRadius: "var(--radius-sm)", background: "var(--color-surface-sunken)" }} />
            <span style={{ display: "block", height: 14, width: "45%", borderRadius: "var(--radius-sm)", background: "var(--color-surface-sunken)" }} />
          </div>
        ) : children}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, marginTop: 4 }}>{actions}</div>}
    </div>
  );
}
