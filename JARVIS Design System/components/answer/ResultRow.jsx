import React from "react";
import { Swatch } from "../listing/Swatch.jsx";

/* An instant file hit: title and location on one line, the matching text
   under it in the proportional face. */
export function ResultRow({ type = "other", title, where, snippet, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      {...rest}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: 0,
        background: hover ? "rgba(255,255,255,0.05)" : "transparent",
        color: "var(--text-body)",
        fontFamily: "var(--font-mono)",
        padding: "9px var(--space-4)",
        borderRadius: "var(--r)",
        cursor: "pointer",
        transition: "var(--transition-row)",
        ...style,
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "4px" }}>
        <Swatch type={type} />
        <span style={{ color: "var(--text-strong)", fontSize: "var(--size-base)" }}>{title}</span>
        <span style={{ color: "var(--text-muted)", fontSize: "var(--size-tick)", marginLeft: "auto" }}>{where}</span>
      </span>
      <span style={{ display: "block", fontFamily: "var(--font-sans)", fontSize: "var(--size-row)", lineHeight: "var(--lh-row)", color: "var(--text-muted)" }}>
        {snippet}
      </span>
    </button>
  );
}
