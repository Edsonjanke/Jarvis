import React from "react";

/* v2's panel. Not a box — a labelled rule across the top whose right end
   cuts away on a diagonal, with the content hanging beneath it. Set foot to
   close the block with a mirrored rule. */
export function HudFrame({ label, right, foot = false, children, style, ...rest }) {
  const rule = (flip) => (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--hud-frame-gap)", pointerEvents: "none" }}>
      {!flip && <span style={{ width: "var(--hud-rule)", height: "var(--hud-cap)", background: "var(--hud-line)", flex: "none" }} />}
      {!flip && label && (
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "var(--size-tick)", letterSpacing: "var(--track-eyebrow)",
          textTransform: "uppercase", color: "var(--text-label)", whiteSpace: "nowrap", flex: "none",
        }}>{label}</span>
      )}
      <span style={{ flex: 1, height: "var(--hud-rule)", background: flip ? "var(--hud-line-dim)" : "var(--hud-line)" }} />
      {right && !flip ? (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--size-tick)", letterSpacing: "0.06em", color: "var(--text-muted)", flex: "none" }}>{right}</span>
      ) : null}
      <span style={{
        width: "var(--hud-cut)", height: "var(--hud-cut-drop)", flex: "none",
        background: `linear-gradient(to bottom ${flip ? "left" : "right"}, transparent calc(50% - 0.5px), ${flip ? "var(--hud-line-dim)" : "var(--hud-line)"} calc(50% - 0.5px), ${flip ? "var(--hud-line-dim)" : "var(--hud-line)"} calc(50% + 0.5px), transparent calc(50% + 0.5px))`,
      }} />
    </div>
  );

  return (
    <section {...rest} style={{ fontFamily: "var(--font-mono)", color: "var(--text-body)", ...style }}>
      {rule(false)}
      <div style={{ padding: "var(--hud-body-pad)" }}>{children}</div>
      {foot ? rule(true) : null}
    </section>
  );
}
