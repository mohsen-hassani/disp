import React from "react";

export function IconButton({ children, label, variant = "ghost", size = "md", onClick }) {
  const dim = size === "sm" ? 32 : 44;
  return (
    <button aria-label={label} title={label} onClick={onClick} style={{
      width: dim, height: dim, display: "inline-flex", alignItems: "center", justifyContent: "center",
      borderRadius: "var(--radius-sm)", cursor: "pointer",
      background: variant === "secondary" ? "var(--color-surface-raised)" : "transparent",
      border: variant === "secondary" ? "1px solid var(--color-border)" : "1px solid transparent",
      color: "var(--color-text)",
      transition: "background var(--duration-fast) var(--ease-standard)",
    }}>
      {children}
    </button>
  );
}
