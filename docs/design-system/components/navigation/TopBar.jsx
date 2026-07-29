import React from "react";

export function TopBar({ userMenu, title = "DISP" }) {
  return (
    <header style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      height: 56, padding: "0 var(--space-4)", borderBottom: "1px solid var(--color-border)",
      background: "var(--color-surface-raised)", position: "sticky", top: 0, zIndex: 30,
    }}>
      <span style={{ fontWeight: "var(--font-weight-semibold)", fontSize: "var(--text-md)", letterSpacing: "var(--tracking-tight)" }}>{title}</span>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>{userMenu}</div>
    </header>
  );
}
