import React from "react";
import { Swatch } from "../listing/Swatch.jsx";

/* The note an answer stands on. The only pill-shaped thing in the product. */
export function Cite({ type = "other", title, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      {...rest}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        maxWidth: "240px",
        border: "1px solid " + (hover ? "var(--control-border-active)" : "var(--border-hairline)"),
        borderRadius: "var(--r-pill)",
        background: hover ? "var(--control-bg-active)" : "transparent",
        color: hover ? "var(--control-fg-active)" : "var(--text-body)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-fine)",
        padding: "var(--chip-pad)",
        cursor: "pointer",
        transition: "var(--transition-control)",
        ...style,
      }}
    >
      <Swatch type={type} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
    </button>
  );
}
