import React from "react";

/* Why a thing is unavailable, or where the backups went. Small, dim, and on
   the page rather than hidden in a title attribute where only a mouse finds it. */
export function PanelNote({ children, style, ...rest }) {
  return (
    <p
      {...rest}
      style={{
        margin: "var(--space-2) var(--space-3) 0",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-tick)",
        lineHeight: 1.45,
        color: "var(--text-muted)",
        opacity: 0.75,
        ...style,
      }}
    >
      {children}
    </p>
  );
}
