import React from "react";

const TONE = { sys: "var(--accent)", ok: "var(--good)", info: "var(--ink-2)", err: "var(--crit)", warn: "var(--warn)" };

/* The live log. Timestamp, a three-letter tag, then the line. Scrolls itself
   to the newest entry; the prompt sits under it and does not blink when the
   process is busy. */
export function TerminalLog({ lines = [], prompt = "jarvis@os:~$", busy = false, height = 150, style, ...rest }) {
  const ref = React.useRef(null);
  React.useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [lines.length]);

  return (
    <div {...rest} style={{ fontFamily: "var(--font-mono)", fontSize: "var(--size-tick)", lineHeight: 1.5, ...style }}>
      <div ref={ref} style={{ height, overflowY: "auto", overscrollBehavior: "contain", scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent", display: "flex", flexDirection: "column", gap: "3px" }}>
        {lines.map((l, i) => (
          <div key={i} style={{ display: "flex", gap: "6px", alignItems: "flex-start" }}>
            <span style={{ color: "var(--ink-3)", flex: "none" }}>[{l.at}]</span>
            <span style={{ flex: "none", minWidth: "26px", color: TONE[l.tag] || "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{l.tag}</span>
            <span style={{ color: "var(--text-body)", minWidth: 0, wordBreak: "break-word" }}>{l.text}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "7px", alignItems: "center", marginTop: "6px", color: "var(--accent)" }}>
        <span>{prompt}</span>
        <span style={{ width: "6px", height: "11px", background: "var(--accent)", opacity: busy ? 1 : 0.45, animation: busy ? "none" : "hud-caret 1.1s steps(1,end) infinite" }} />
      </div>
    </div>
  );
}
