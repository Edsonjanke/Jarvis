import React from "react";

/* Outlined, never filled: on a dark instrument panel a filled button reads as
   a web page, an etched one reads as hardware. Hover and pressed resolve to
   the same accent triple; disabled keeps its label and takes a dashed border. */
export function Button({ size = "key", pressed, disabled, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const lit = (hover && !disabled) || pressed;

  return (
    <button
      type="button"
      {...rest}
      disabled={disabled}
      aria-pressed={pressed === undefined ? undefined : String(!!pressed)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        font: "inherit",
        fontFamily: "var(--font-mono)",
        fontSize: size === "ghost" ? "var(--size-tick)" : "var(--size-key)",
        letterSpacing: "var(--track-label)",
        textTransform: "uppercase",
        padding: size === "ghost" ? "var(--ghost-pad)" : "var(--key-pad)",
        borderRadius: "var(--r)",
        background: disabled ? "transparent" : lit ? "var(--control-bg-active)" : "transparent",
        color: disabled ? "var(--control-fg-disabled)" : lit ? "var(--control-fg-active)" : "var(--control-fg)",
        border: "1px solid " + (disabled ? "var(--control-border-disabled)" : lit ? "var(--control-border-active)" : "var(--control-border)"),
        borderStyle: disabled ? "dashed" : "solid",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "var(--transition-control)",
        ...style,
      }}
    >
      {children}
    </button>
  );
}
