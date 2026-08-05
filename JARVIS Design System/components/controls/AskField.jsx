import React from "react";

/* The ask bar's field. It does two things at once and they do not collide:
   typing runs the instant file search, Enter sends the question to the model. */
export function AskField({ mode = "ask", value, onChange, onSubmit, placeholder, hint = "enter", style, ...rest }) {
  const [focus, setFocus] = React.useState(false);

  return (
    <div
      {...rest}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-5)",
        padding: "0 var(--field-pad-x)",
        height: "var(--field-h)",
        background: "var(--surface-raised)",
        backdropFilter: "var(--blur-panel)",
        WebkitBackdropFilter: "var(--blur-panel)",
        border: "1px solid " + (focus ? "var(--edge-lit)" : "var(--border-hairline)"),
        borderTopColor: focus ? "var(--edge-lit)" : "var(--border-lit)",
        borderRadius: "var(--r)",
        transition: "border-color var(--t-field)",
        ...style,
      }}
    >
      <span
        style={{
          fontSize: "var(--size-micro)",
          letterSpacing: "var(--track-mode)",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          borderRight: "1px solid var(--border-hairline)",
          paddingRight: "var(--space-5)",
          flex: "none",
        }}
      >
        {mode}
      </span>
      <input
        type="text"
        autoComplete="off"
        spellCheck={false}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange && onChange(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onSubmit) { e.preventDefault(); onSubmit(value); }
        }}
        style={{
          flex: 1,
          minWidth: 0,
          background: "transparent",
          border: 0,
          outline: 0,
          color: "var(--text-strong)",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--size-input)",
        }}
      />
      <span
        style={{
          fontSize: "var(--size-micro)",
          letterSpacing: "var(--track-label)",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          flex: "none",
        }}
        aria-hidden="true"
      >
        {hint}
      </span>
    </div>
  );
}
