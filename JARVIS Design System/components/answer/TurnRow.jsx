import React from "react";

/* One past question. Reopening it also puts you back in its conversation, so
   the next question continues from there. */
export function TurnRow({ when, question, meta, onOpen, onDelete, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      {...rest}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto auto",
        gap: "var(--space-3)",
        alignItems: "baseline",
        padding: "var(--space-2) 0",
        borderTop: "1px solid rgba(255,255,255,0.05)",
        fontFamily: "var(--font-mono)",
        ...style,
      }}
    >
      <span style={{ fontSize: "var(--size-tick)", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>{when}</span>
      <button
        type="button"
        onClick={onOpen}
        style={{ textAlign: "left", border: 0, background: "transparent", color: "var(--text-strong)", font: "inherit", fontSize: "var(--size-base)", cursor: "pointer", padding: 0 }}
      >
        {question}
      </button>
      <span style={{ fontSize: "var(--size-tick)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>{meta}</span>
      {onDelete ? (
        <button
          type="button"
          onClick={onDelete}
          style={{
            font: "inherit", fontSize: "var(--size-tick)", letterSpacing: "var(--track-label)", textTransform: "uppercase",
            color: "var(--control-fg)", background: "transparent", border: "1px solid var(--control-border)",
            borderRadius: "var(--r)", padding: "var(--ghost-pad)", cursor: "pointer",
            opacity: hover ? 1 : 0, transition: "opacity var(--t-row)",
          }}
        >
          Apagar
        </button>
      ) : null}
    </div>
  );
}
