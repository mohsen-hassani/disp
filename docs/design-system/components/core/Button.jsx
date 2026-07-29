import React from "react";

export function Button({ children, variant = "primary", size = "md", disabled, onClick, type = "button" }) {
  const base = {
    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
    fontFamily: "var(--font-sans)", fontWeight: "var(--font-weight-medium)",
    borderRadius: "var(--radius-sm)", cursor: disabled ? "default" : "pointer",
    transition: "background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), opacity var(--duration-fast) var(--ease-standard)",
    opacity: disabled ? 0.5 : 1,
    border: "1px solid transparent",
    fontSize: size === "sm" ? "var(--text-sm)" : "var(--text-base)",
    padding: size === "sm" ? "6px 12px" : "10px 16px",
    minHeight: size === "sm" ? 32 : 44,
  };
  const variants = {
    primary: { background: "var(--color-accent)", color: "var(--color-accent-text)" },
    secondary: { background: "var(--color-surface-raised)", color: "var(--color-text)", borderColor: "var(--color-border)" },
    ghost: { background: "transparent", color: "var(--color-text)" },
    danger: { background: "var(--color-danger)", color: "var(--color-accent-text)" },
  };
  return (
    <button type={type} disabled={disabled} onClick={onClick} style={{ ...base, ...variants[variant] }}>
      {children}
    </button>
  );
}
