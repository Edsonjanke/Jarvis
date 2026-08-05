import React from "react";

/* A ring gauge with its value in the middle. Stroke is a dasharray, so the
   arc animates by colour crossfade only — nothing rotates. */
export function RadialGauge({ value = 0, size = 54, label, caption, style, ...rest }) {
  const pct = Math.max(0, Math.min(100, value));
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div {...rest} style={{ display: "flex", alignItems: "center", gap: "11px", fontFamily: "var(--font-mono)", ...style }}>
      <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
        <svg width={size} height={size} style={{ display: "block", transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--wash-2)" strokeWidth="var(--gauge-stroke)" />
          <circle
            cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth="var(--gauge-stroke)"
            strokeDasharray={`${(c * pct) / 100} ${c}`} strokeLinecap="butt"
            style={{ transition: "stroke-dasharray 400ms linear" }}
          />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "1px" }}>
          <span style={{ fontSize: "var(--size-base)", color: "var(--accent)", textShadow: "var(--hud-glow-soft)", fontVariantNumeric: "tabular-nums" }}>{pct}%</span>
          {label ? <span style={{ fontSize: "8px", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-muted)" }}>{label}</span> : null}
        </div>
      </div>
      {caption ? <div style={{ flex: 1, minWidth: 0 }}>{caption}</div> : null}
    </div>
  );
}
