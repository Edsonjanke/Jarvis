import React from "react";

/* Ten uppercase pixels behind a 6x1px dash. The only ornament in the product. */
export function Eyebrow({ children, count, style, ...rest }) {
  return (
    <span
      {...rest}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "7px",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-tick)",
        letterSpacing: "var(--track-eyebrow)",
        textTransform: "uppercase",
        color: "var(--text-label)",
        ...style,
      }}
    >
      <span style={{ width: "6px", height: "1px", background: "currentColor", flex: "none" }} />
      {children}
      {count !== undefined && count !== null ? (
        <span style={{ letterSpacing: 0, color: "var(--ink-3)" }}>{count}</span>
      ) : null}
    </span>
  );
}
