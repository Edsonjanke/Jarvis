import React from "react";

/* Present only when something is genuinely broken. Full-width bed at the top
   of the screen, stacked, never dismissible by decoration. */
const BED = {
  warn: { background: "var(--alert-warn-bg)", color: "var(--alert-warn-fg)" },
  crit: { background: "var(--alert-crit-bg)", color: "var(--alert-crit-fg)" },
  info: { background: "var(--alert-info-bg)", color: "var(--alert-info-fg)" },
};

export function Alert({ level = "warn", label, children, style, ...rest }) {
  return (
    <div
      {...rest}
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: "var(--space-4)",
        padding: "9px 18px",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-row)",
        borderBottom: "1px solid var(--border-hairline)",
        ...(BED[level] || BED.warn),
        ...style,
      }}
    >
      <b
        style={{
          fontWeight: "var(--weight-strong)",
          letterSpacing: "var(--track-label)",
          textTransform: "uppercase",
          fontSize: "var(--size-tick)",
          opacity: 0.75,
          flex: "none",
        }}
      >
        {label}
      </b>
      <span>{children}</span>
    </div>
  );
}
