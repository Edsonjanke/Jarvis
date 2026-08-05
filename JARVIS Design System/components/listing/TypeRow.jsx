import React from "react";
import { Swatch, typeColour } from "./Swatch.jsx";

/* A filter and a histogram in one row: switch a type off and the graph drops
   it; the bar shows its share of the vault. */
export function TypeRow({ type, name, count, share = 0, on = true, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);

  return (
    <button
      type="button"
      {...rest}
      aria-pressed={String(!!on)}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--row-gap)",
        width: "100%",
        padding: "var(--row-pad-x)",
        margin: "0 calc(-1 * var(--row-pad-x))",
        border: 0,
        borderRadius: "var(--r)",
        background: hover ? "var(--surface-hover)" : "transparent",
        color: "var(--text-body)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-row)",
        opacity: on ? 1 : "var(--dim-filter)",
        cursor: "pointer",
        transition: "background-color var(--t-row), opacity var(--t-row)",
        ...style,
      }}
    >
      <Swatch type={type} />
      <span style={{ flex: 1 }}>
        <span style={{ display: "block", textTransform: "capitalize", letterSpacing: "var(--track-name)", textAlign: "left" }}>
          {name || type}
        </span>
        <span style={{ display: "block", width: "100%", height: "var(--bar-h)", background: "var(--wash-2)", borderRadius: "1px", overflow: "hidden", marginTop: "3px" }}>
          <span style={{ display: "block", height: "100%", width: Math.round(share * 100) + "%", background: on ? typeColour(type) : "var(--ink-3)" }} />
        </span>
      </span>
      <span style={{ color: "var(--ink-3)", fontSize: "var(--size-key)", fontVariantNumeric: "tabular-nums" }}>{count}</span>
    </button>
  );
}
