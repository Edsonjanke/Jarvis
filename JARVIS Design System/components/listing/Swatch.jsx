import React from "react";

/* The only icon in the product: a 9px dot in a node-type colour. Hue says
   what a thing is; it never carries state. */
const TYPES = ["client", "project", "meeting", "invoice", "person", "note", "reference"];
export function typeColour(type) {
  return TYPES.indexOf(type) >= 0 ? "var(--t-" + type + ")" : "var(--t-other)";
}

export function Swatch({ type = "other", colour, size = 9, style, ...rest }) {
  return (
    <span
      {...rest}
      style={{
        width: size + "px",
        height: size + "px",
        borderRadius: "50%",
        background: colour || typeColour(type),
        flex: "none",
        display: "inline-block",
        ...style,
      }}
    />
  );
}
