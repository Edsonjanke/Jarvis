import React from "react";
import { Icon } from "./Icon.jsx";

/* A square action in the rail grid: glyph over a two-line label. Outlined,
   never filled — pressed and hover resolve to the same accent triple, as
   every other control in this system does. */
export function Tile({ icon, label, active = false, disabled = false, onClick, title, style, ...rest }) {
  const [hot, setHot] = React.useState(false);
  const lit = (hot && !disabled) || active;
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      aria-pressed={active}
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      {...rest}
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "5px",
        minHeight: "var(--tile-h)", padding: "7px 3px",
        background: lit ? "var(--control-bg-active)" : "transparent",
        border: "1px solid " + (disabled ? "var(--control-border-disabled)" : lit ? "var(--control-border-active)" : "var(--control-border)"),
        borderStyle: disabled ? "dashed" : "solid",
        borderRadius: "var(--r)",
        color: disabled ? "var(--control-fg-disabled)" : lit ? "var(--control-fg-active)" : "var(--control-fg)",
        fontFamily: "var(--font-mono)", fontSize: "7.5px", letterSpacing: "0.06em", textTransform: "uppercase",
        lineHeight: 1.35, textAlign: "center", cursor: disabled ? "default" : "pointer",
        transition: "var(--transition-control)",
        ...style,
      }}
    >
      {icon ? <Icon name={icon} size={15} /> : null}
      <span>{label}</span>
    </button>
  );
}
