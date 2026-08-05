import React from "react";
import { Swatch } from "./Swatch.jsx";

/* The list row: direction, dot, label, tail. Bleeds 6px past the panel padding
   so its hover wash reaches the inner edge. Rows never move. */
export function Row({ type = "other", label, tail, dir, step, selected, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const lit = hover || selected;

  return (
    <button
      type="button"
      {...rest}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--row-gap)",
        width: "100%",
        padding: "var(--row-pad-y) var(--row-pad-x)",
        margin: "0 calc(-1 * var(--row-pad-x))",
        border: 0,
        borderRadius: "var(--r)",
        background: lit ? "var(--surface-hover)" : "transparent",
        color: lit ? "var(--text-strong)" : "var(--text-body)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-row)",
        textAlign: "left",
        cursor: "pointer",
        transition: "var(--transition-row)",
        ...style,
      }}
    >
      {dir ? <span style={{ color: "var(--ink-3)", fontSize: "9px", width: "12px", flex: "none" }}>{dir}</span> : null}
      {step !== undefined ? <span style={{ color: "var(--ink-3)", fontSize: "9.5px", width: "12px", flex: "none" }}>{step}</span> : null}
      <Swatch type={type} />
      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      {tail !== undefined && tail !== null ? (
        <span style={{ color: "var(--ink-3)", fontSize: "var(--size-tick)", flex: "none" }}>{tail}</span>
      ) : null}
    </button>
  );
}
