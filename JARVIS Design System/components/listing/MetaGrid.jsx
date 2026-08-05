import React from "react";

/* Note metadata: uppercase keys, values that may wrap. Ruled top and bottom,
   never boxed. */
export function MetaGrid({ rows = [], style, ...rest }) {
  return (
    <ul
      {...rest}
      style={{
        listStyle: "none",
        margin: "0 0 var(--space-6)",
        padding: "var(--space-5) 0",
        borderTop: "1px solid var(--border-hairline)",
        borderBottom: "1px solid var(--border-hairline)",
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: "5px var(--space-6)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-fine)",
        ...style,
      }}
    >
      {rows.map(([k, v], i) => [
        <li key={"k" + i} style={{ color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--track-label)", fontSize: "var(--size-micro)" }}>{k}</li>,
        <li key={"v" + i} style={{ color: k === "warning" ? "var(--warn)" : "var(--text-body)", wordBreak: "break-word" }}>{v}</li>,
      ])}
    </ul>
  );
}
