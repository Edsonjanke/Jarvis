import React from "react";

/* The secondary field: filtering a list that is already on screen. */
export function SearchInput({ value, onChange, onSubmit, placeholder, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <input
      type="search"
      {...rest}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange && onChange(e.target.value)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      onKeyDown={(e) => { if (e.key === "Enter" && onSubmit) onSubmit(e.currentTarget.value); }}
      style={{
        width: "100%",
        margin: "var(--space-2) 0 var(--space-4)",
        padding: "7px 9px",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--size-base)",
        color: "var(--text-strong)",
        background: "rgba(255, 255, 255, 0.04)",
        border: "1px solid " + (focus ? "var(--accent)" : "rgba(255, 255, 255, 0.08)"),
        borderRadius: "var(--r)",
        outline: "none",
        ...style,
      }}
    />
  );
}
