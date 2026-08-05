import React from "react";

/* A picker row with a reason under it: which model, which tool server, which
   skill, which edit mode. The second line says why it can or cannot be used. */
export function BrainRow({ name, note, pressed, disabled, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const interactive = !!onClick && !disabled;

  return (
    <button
      type="button"
      {...rest}
      disabled={disabled}
      aria-pressed={String(!!pressed)}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: 0,
        borderRadius: "var(--r)",
        padding: "var(--space-2) var(--space-3)",
        fontFamily: "var(--font-mono)",
        background: pressed ? "var(--accent-soft)" : hover && interactive ? "rgba(255,255,255,0.05)" : "transparent",
        boxShadow: pressed ? "var(--edge-inset)" : "none",
        color: "var(--text-muted)",
        opacity: disabled ? 0.5 : 1,
        cursor: interactive ? "pointer" : "default",
        transition: "var(--transition-row)",
        ...style,
      }}
    >
      <span style={{ display: "block", fontSize: "var(--size-base)", color: pressed ? "var(--accent)" : "var(--text-muted)" }}>{name}</span>
      <span style={{ display: "block", fontSize: "var(--size-tick)", color: "var(--text-muted)" }}>{note}</span>
    </button>
  );
}
