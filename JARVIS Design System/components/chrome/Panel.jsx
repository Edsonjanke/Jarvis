import React from "react";

/* The floating plate. Translucent, blurred, hairline border with a lit top
   edge. Three of these float over the canvas; nothing else in the product is
   a surface. */
export function Panel({ side = "free", children, scroll = true, style, ...rest }) {
  const fixed = {
    left:  { position: "fixed", zIndex: 3, top: "var(--gutter)", left: "var(--gutter)", width: "var(--panel-left-w)", bottom: "var(--panel-bottom)" },
    right: { position: "fixed", zIndex: 3, top: "var(--gutter)", right: "var(--gutter)", width: "var(--panel-right-w)", bottom: "var(--panel-bottom)" },
    free:  {},
  }[side] || {};

  return (
    <aside
      {...rest}
      style={{
        background: "var(--surface-panel)",
        backdropFilter: "var(--blur-panel)",
        WebkitBackdropFilter: "var(--blur-panel)",
        border: "1px solid var(--border-hairline)",
        borderTopColor: "var(--border-lit)",
        borderRadius: "var(--r)",
        padding: "var(--pad)",
        color: "var(--text-body)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-base)",
        overflowY: scroll ? "auto" : "visible",
        overscrollBehavior: "contain",
        scrollbarWidth: "thin",
        scrollbarColor: "var(--ink-3) transparent",
        ...fixed,
        ...style,
      }}
    >
      {children}
    </aside>
  );
}
