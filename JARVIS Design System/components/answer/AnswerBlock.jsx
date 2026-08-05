import React from "react";
import { Eyebrow } from "../chrome/Eyebrow.jsx";

/* An answer, with the notes it stands on. The body is the one place in the
   ask bar where the proportional face appears — a model writing prose is
   standing in for the person, not for the machine. */
export function AnswerBlock({ kind = "ask", meta, metaTitle, body, truncated, children, style, ...rest }) {
  return (
    <div {...rest} style={{ padding: "var(--space-4)", ...style }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)", marginBottom: "var(--space-3)" }}>
        <Eyebrow>{kind}</Eyebrow>
        <span title={metaTitle} style={{ fontSize: "var(--size-tick)", color: "var(--text-muted)", marginLeft: "auto" }}>{meta}</span>
      </div>
      <div style={{ fontFamily: "var(--font-sans)", fontSize: "var(--size-base)", lineHeight: "var(--lh-prose)", color: "var(--text-body)", whiteSpace: "pre-wrap" }}>
        {body}
      </div>
      {truncated ? (
        <div style={{ fontSize: "var(--size-fine)", color: "var(--warn)", marginTop: "var(--space-3)" }}>
          Cut off at the token limit — the answer above is incomplete.
        </div>
      ) : null}
      {children ? (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap", marginTop: "var(--space-5)", paddingTop: "var(--space-4)", borderTop: "1px solid var(--border-hairline)" }}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
