import React from "react";
import { Button } from "./Button.jsx";

/* "This question will be read alongside the last one" changes what you should
   type, so the indicator sits in the button row rather than in a panel. */
export function ThreadBar({ label = "conversa em andamento", onNew, style, ...rest }) {
  return (
    <span
      {...rest}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-3)",
        marginLeft: "var(--space-2)",
        padding: "4px var(--space-3)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-tick)",
        color: "var(--accent)",
        background: "var(--accent-soft)",
        borderRadius: "var(--r)",
        ...style,
      }}
    >
      {label}
      <Button size="ghost" onClick={onNew}>nova conversa</Button>
    </span>
  );
}
