import React from "react";

/* Opening the real document. Deliberately not styled as a primary action —
   the extracted text is still the fast path; this is for when you need to see
   the page itself. */
export function OpenLink({ children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <a
      target="_blank"
      rel="noopener noreferrer"
      {...rest}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-block",
        margin: "2px 0 10px",
        padding: "5px var(--space-4)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-fine)",
        color: "var(--accent)",
        background: "var(--accent-soft)",
        borderRadius: "var(--r)",
        textDecoration: "none",
        filter: hover ? "var(--lift-hover)" : "none",
        ...style,
      }}
    >
      {children}
      <span style={{ opacity: 0.6 }}> ↗</span>
    </a>
  );
}
