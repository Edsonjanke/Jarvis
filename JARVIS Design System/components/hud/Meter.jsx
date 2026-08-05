import React from "react";

/* A labelled bar with a value at the end. Segmented by default — the bar is
   cut into 3px ticks, which is how the reference panel reads a load. */
export function Meter({ label, value = 0, display, tone = "accent", segmented = true, style, ...rest }) {
  const pct = Math.max(0, Math.min(100, value));
  const colour = tone === "warn" ? "var(--warn)" : tone === "crit" ? "var(--crit)" : tone === "muted" ? "var(--ink-3)" : "var(--accent)";
  return (
    <div {...rest} style={{ display: "flex", alignItems: "center", gap: "9px", padding: "3px 0", fontFamily: "var(--font-mono)", fontSize: "var(--size-tick)", ...style }}>
      <span style={{ width: "var(--meter-label-w)", flex: "none", color: "var(--text-label)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</span>
      <span style={{ flex: 1, height: "var(--meter-h)", background: "var(--wash)", position: "relative", overflow: "hidden" }}>
        <span style={{
          position: "absolute", inset: 0, right: (100 - pct) + "%", background: colour,
          transition: "right 400ms linear",
          ...(segmented ? { WebkitMaskImage: "repeating-linear-gradient(90deg, #000 0 var(--meter-seg), transparent var(--meter-seg) calc(var(--meter-seg) + 2px))", maskImage: "repeating-linear-gradient(90deg, #000 0 var(--meter-seg), transparent var(--meter-seg) calc(var(--meter-seg) + 2px))" } : null),
        }} />
      </span>
      <span style={{ flex: "none", minWidth: "30px", textAlign: "right", color: "var(--text-strong)", fontVariantNumeric: "tabular-nums" }}>
        {display !== undefined ? display : pct + "%"}
      </span>
    </div>
  );
}
