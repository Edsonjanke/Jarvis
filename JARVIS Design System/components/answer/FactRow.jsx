import React from "react";

/* Something JARVIS decided was worth keeping. It writes these itself, which is
   only acceptable if you can see all of them and throw any of them away. */
export function FactRow({ when, text, onForget, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      {...rest}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: "var(--space-4)",
        padding: "7px var(--space-4)",
        borderRadius: "var(--r)",
        background: hover ? "rgba(255,255,255,0.05)" : "transparent",
        fontFamily: "var(--font-mono)",
        ...style,
      }}
    >
      <span style={{ flex: "none", fontSize: "var(--size-tick)", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>{when}</span>
      <span style={{ flex: 1, fontFamily: "var(--font-sans)", fontSize: "var(--size-base)", lineHeight: "var(--lh-row)", color: "var(--text-body)" }}>{text}</span>
      {onForget ? (
        <button
          type="button"
          onClick={onForget}
          style={{
            flex: "none", font: "inherit", fontSize: "var(--size-tick)", letterSpacing: "var(--track-label)", textTransform: "uppercase",
            color: "var(--control-fg)", background: "transparent", border: "1px solid var(--control-border)",
            borderRadius: "var(--r)", padding: "var(--ghost-pad)", cursor: "pointer",
            opacity: hover ? 1 : 0, transition: "opacity var(--t-row)",
          }}
        >
          Forget
        </button>
      ) : null}
    </div>
  );
}
