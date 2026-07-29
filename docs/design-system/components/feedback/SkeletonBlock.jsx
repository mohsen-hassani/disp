import React from "react";

// Static muted block — no shimmer animation per motion spec.
export function SkeletonBlock({ width = "100%", height = 16 }) {
  return <span style={{ display: "block", width, height, borderRadius: "var(--radius-sm)", background: "var(--color-surface-sunken)" }} />;
}
