/* Left rail — the machine's own vital signs, top to bottom: load, the core
   that is answering, what it is holding in memory, the vault's shape, and
   the last things that happened. */
const { HudFrame, Meter, RadialGauge, StatList, BrainRow } = window.JARVISDesignSystem_ad8200;

const kv = (k, v, tone) => (
  <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "8px", padding: "2px 0", fontSize: "var(--size-tick)" }}>
    <span style={{ color: "var(--text-label)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{k}</span>
    <span style={{ color: tone || "var(--text-strong)", fontVariantNumeric: "tabular-nums" }}>{v}</span>
  </div>
);

function RailLeft({ metrics, brains, brain, onBrain, memory, network, feed, onOpenFeed }) {
  const [openBrains, setOpenBrains] = React.useState(false);
  const current = brains.find((b) => b.id === brain) || brains[0];

  return (
    <div style={{
      position: "fixed", zIndex: 4, left: "var(--rail-gutter)", top: "var(--rail-gutter)", bottom: "var(--rail-gutter)",
      width: "var(--rail-w)", display: "flex", flexDirection: "column", gap: "var(--rail-gap)",
      overflowY: "auto", overscrollBehavior: "contain", scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent",
    }}>
      <HudFrame label="Status do sistema" right="local">
        {metrics.map((m) => <Meter key={m.key} label={m.label} value={m.value} tone={m.value > 88 ? "warn" : "accent"} />)}
      </HudFrame>

      <HudFrame label="Núcleo de IA" right={openBrains ? "trocar" : null}>
        <div>
          {kv("modelo", current.label, "var(--accent)")}
          {kv("modo", "ask")}
          {kv("raciocínio", "87%")}
          {kv("resposta", "4,1s")}
        </div>
        <button
          type="button"
          onClick={() => setOpenBrains((v) => !v)}
          style={{
            marginTop: "7px", width: "100%", padding: "4px 6px", background: "transparent",
            border: "1px solid var(--control-border)", borderRadius: "var(--r)", color: "var(--control-fg)",
            fontFamily: "var(--font-mono)", fontSize: "8px", letterSpacing: "0.14em", textTransform: "uppercase",
            cursor: "pointer", transition: "var(--transition-control)",
          }}
        >{openBrains ? "fechar cérebro" : "trocar cérebro"}</button>
        {openBrains ? (
          <div style={{ marginTop: "7px", display: "flex", flexDirection: "column", gap: "2px" }}>
            {brains.map((b) => (
              <BrainRow key={b.id} name={b.label} note={b.note} pressed={b.id === brain} onClick={() => { onBrain(b.id); setOpenBrains(false); }} />
            ))}
          </div>
        ) : null}
      </HudFrame>

      <HudFrame label="Banco de memória">
        <RadialGauge value={memory.pct} label="memória" caption={<StatList rows={memory.rows} />} />
      </HudFrame>

      <HudFrame label="Rede">
        <StatList rows={network} />
      </HudFrame>

      <HudFrame label="Feed ao vivo" foot>
        <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
          {feed.map((f, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onOpenFeed && onOpenFeed(f)}
              style={{
                display: "flex", gap: "8px", alignItems: "baseline", width: "100%", textAlign: "left",
                padding: "var(--row-pad-y) var(--row-pad-x)", margin: "0 calc(var(--row-pad-x) * -1)",
                background: "transparent", border: 0, borderRadius: "var(--r)", cursor: "pointer",
                fontFamily: "var(--font-mono)", fontSize: "var(--size-tick)", transition: "var(--transition-row)",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--wash)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              <span style={{ color: "var(--ink-3)", flex: "none" }}>{f.at}</span>
              <span style={{ color: "var(--text-body)", flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.what}</span>
              <span style={{ flex: "none", color: f.tone === "warn" ? "var(--warn)" : f.tone === "accent" ? "var(--accent)" : "var(--ink-3)", maxWidth: "96px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.tail}</span>
            </button>
          ))}
        </div>
      </HudFrame>
    </div>
  );
}

Object.assign(window, { RailLeft });
