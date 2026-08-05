import React from "react";
import { Eyebrow } from "./Eyebrow.jsx";

/* Section header inside a plate: an eyebrow on the left, one control or count
   on the right. There are no <h2>s in this product. */
export function PanelHead({ label, children, rule = false, style, ...rest }) {
  return (
    <header
      {...rest}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--space-3)",
        marginBottom: "var(--space-5)",
        paddingBottom: rule ? "var(--space-4)" : 0,
        borderBottom: rule ? "1px solid var(--border-hairline)" : "none",
        ...style,
      }}
    >
      <Eyebrow>{label}</Eyebrow>
      {children}
    </header>
  );
}
