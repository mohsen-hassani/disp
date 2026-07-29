import React from "react";

export function Avatar({ name, size = 32 }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join("");
  return (
    <span style={{
      width: size, height: size, borderRadius: "var(--radius-full)",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      background: "var(--color-accent)", color: "var(--color-accent-text)",
      fontSize: size * 0.4, fontWeight: "var(--font-weight-semibold)", flex: "0 0 auto",
    }}>{initials || "?"}</span>
  );
}
