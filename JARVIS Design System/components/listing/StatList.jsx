import React from "react";

/* The vault readout. Right-aligned, tabular, and honest: a capability that is
   absent says "missing" in --warn rather than being left out. */
export function StatList({ rows = [], style, ...rest }) {
  return (
    <dl
      {...rest}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "5px var(--space-5)",
        margin: "var(--space-4) 0 0",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-key)",
        ...style,
      }}
    >
      {rows.map(([k, v], i) => [
        <dt key={"k" + i} style={{ color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--track-label)", fontSize: "var(--size-micro)" }}>{k}</dt>,
        <dd key={"v" + i} style={{ margin: 0, textAlign: "right", fontVariantNumeric: "tabular-nums", color: v === "missing" ? "var(--warn)" : "var(--text-body)" }}>{v}</dd>,
      ])}
    </dl>
  );
}
