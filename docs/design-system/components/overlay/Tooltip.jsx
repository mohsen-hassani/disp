import React from "react";
const { useState } = React;

export function Tooltip({ label, children }) {
  const [show, setShow] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)} onBlur={() => setShow(false)}>
      {children}
      {show && (
        <span role="tooltip" style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)",
          background: "var(--color-text)", color: "var(--color-surface)", fontSize: "var(--text-xs)",
          padding: "4px 8px", borderRadius: "var(--radius-sm)", whiteSpace: "nowrap",
          boxShadow: "var(--shadow-overlay)", zIndex: 60,
        }}>{label}</span>
      )}
    </span>
  );
}
