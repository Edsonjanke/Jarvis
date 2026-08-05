/* Centre stage — greeting, the reactor with the vault's four headline
   figures pinned around it, and the ask bar. Everything the operator types
   happens here; the rails only report. */
const { Reactor, Icon, AnswerBlock, Cite, ResultRow, Button } = window.JARVISDesignSystem_ad8200;

const readout = (label, value, pos) => (
  <div key={label} style={{ position: "absolute", maxWidth: "46%", ...pos }}>
    <div style={{ fontSize: "8px", letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--text-label)", whiteSpace: "nowrap" }}>{label}</div>
    <div style={{ fontSize: "15px", color: "var(--accent)", textShadow: "var(--hud-glow-soft)", marginTop: "4px", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{value}</div>
  </div>
);

function CenterStage({ greeting, phase, level, query, onQuery, onSubmit, results, onOpen, answer, onCite, onClear, vaultStats }) {
  const inputRef = React.useRef(null);
  const stageRef = React.useRef(null);
  const [focus, setFocus] = React.useState(false);
  const [dial, setDial] = React.useState(0);
  const busy = phase === "thinking";
  const showResults = !busy && !answer && query.trim().length > 1 && results.length > 0;

  /* The reactor is the one thing here that must never collide with a rail or
     the greeting, so it is measured rather than fixed — and re-measured after
     every render, because opening the answer panel steals the stage's height
     without any window resize. */
  const fit = React.useCallback(() => {
    const el = stageRef.current;
    if (!el) return;
    const next = Math.max(0, Math.min(420, el.clientWidth - 24, el.clientHeight - 8));
    setDial((d) => (Math.abs(d - next) < 2 ? d : next));
  }, []);

  React.useLayoutEffect(fit);

  React.useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    window.addEventListener("resize", fit);
    return () => { ro.disconnect(); window.removeEventListener("resize", fit); };
  }, [fit]);

  return (
    <div style={{
      position: "fixed", zIndex: 2, top: 0, bottom: 0,
      left: "calc(var(--rail-w) + var(--rail-gutter) * 2)", right: "calc(var(--rail-w) + var(--rail-gutter) * 2)",
      display: "flex", flexDirection: "column", alignItems: "center", pointerEvents: "none",
    }}>
      <div style={{ marginTop: "58px", display: "flex", gap: "13px", alignItems: "flex-start", pointerEvents: "auto" }}>
        <span style={{ width: "26px", height: "26px", flex: "none", border: "1px solid var(--accent-line)", borderRadius: "var(--r)", background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ width: "9px", height: "9px", background: "var(--accent)", boxShadow: "var(--hud-glow)" }} />
        </span>
        <div>
          <div style={{ fontSize: "19px", letterSpacing: "0.02em", color: "var(--accent)", textShadow: "var(--hud-glow-soft)" }}>{greeting}</div>
          <div style={{ fontFamily: "var(--font-sans)", fontSize: "var(--size-base)", color: "var(--text-body)", marginTop: "3px" }}>
            Pergunte qualquer coisa sobre o que está no vault.
          </div>
        </div>
      </div>

      <div ref={stageRef} style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", width: "100%", minHeight: 0, overflow: "hidden" }}>
        <div style={{ position: "relative", width: dial, height: dial, flex: "none" }}>
          <Reactor size={dial} state={phase === "idle" ? "idle" : "thinking"} level={level} style={{ position: "absolute", inset: 0 }} />
          {dial >= 260 ? (
            <>
              {readout("Índice", vaultStats.notes + " notas", { left: 0, top: "19%" })}
              {readout("Cobertura", "93%", { right: 0, top: "19%", textAlign: "right" })}
              {readout("Vínculos", vaultStats.links, { left: 0, bottom: "19%" })}
              {readout("Varredura", "0,4s", { right: 0, bottom: "19%", textAlign: "right" })}
            </>
          ) : null}
        </div>
      </div>

      <div style={{ width: "min(var(--ask-w), 100%)", paddingBottom: "26px", pointerEvents: "auto" }}>
        {answer ? (
          <div style={{
            marginBottom: "12px", maxHeight: "34vh", overflowY: "auto", overscrollBehavior: "contain",
            scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent",
            background: "var(--surface-panel)", backdropFilter: "var(--blur-panel)", WebkitBackdropFilter: "var(--blur-panel)",
            border: "1px solid var(--border-hairline)", borderTopColor: "var(--border-lit)", borderRadius: "var(--r)", padding: "var(--pad)",
          }}>
            <AnswerBlock kind={answer.kind} meta={answer.meta} body={answer.body}>
              {answer.citations.map((id) => (
                <Cite key={id} type={answer.types[id]} title={answer.titles[id]} onClick={() => onCite(id)} />
              ))}
            </AnswerBlock>
            <div style={{ marginTop: "12px", display: "flex", gap: "6px" }}>
              <Button size="ghost" onClick={onClear}>nova conversa</Button>
            </div>
          </div>
        ) : null}

        {showResults ? (
          <div style={{
            marginBottom: "12px", maxHeight: "30vh", overflowY: "auto", overscrollBehavior: "contain",
            scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent",
            background: "var(--surface-panel)", backdropFilter: "var(--blur-panel)", WebkitBackdropFilter: "var(--blur-panel)",
            border: "1px solid var(--border-hairline)", borderTopColor: "var(--border-lit)", borderRadius: "var(--r)", padding: "10px var(--pad)",
          }}>
            {results.map((r) => (
              <ResultRow key={r.id} type={r.type} title={r.title} where={r.rel} snippet={r.snippet} onClick={() => onOpen(r.id)} />
            ))}
          </div>
        ) : null}

        <div style={{ display: "flex", justifyContent: "center", marginBottom: "10px" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "7px", fontSize: "var(--size-tick)", letterSpacing: "0.16em", textTransform: "uppercase", color: busy ? "var(--accent)" : "var(--text-label)" }}>
            <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: busy ? "var(--accent)" : "var(--good)", boxShadow: "var(--hud-glow-soft)" }} />
            {busy ? "pensando…" : "sistemas operacionais"}
          </span>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
          style={{
            display: "flex", alignItems: "center", gap: "10px", height: "var(--ask-h)", padding: "0 12px 0 14px",
            background: "var(--surface-raised)", backdropFilter: "var(--blur-panel)", WebkitBackdropFilter: "var(--blur-panel)",
            border: "1px solid " + (focus ? "var(--accent-line)" : "var(--border-hairline)"),
            borderRadius: "var(--r)", transition: "border-color var(--t-field) linear",
          }}
        >
          <Icon name="mic" size={14} style={{ color: "var(--ink-3)" }} />
          <span style={{ width: "1px", height: "18px", background: "var(--hairline)", flex: "none" }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            onFocus={() => setFocus(true)}
            onBlur={() => setFocus(false)}
            placeholder="O que vamos construir hoje?"
            aria-label="Pergunta"
            disabled={busy}
            style={{
              flex: 1, minWidth: 0, background: "transparent", border: 0, outline: "none",
              color: "var(--text-strong)", fontFamily: "var(--font-mono)", fontSize: "13.5px", letterSpacing: "0.01em",
            }}
          />
          <button type="submit" disabled={busy || !query.trim()} aria-label="Enviar" style={{
            display: "flex", alignItems: "center", justifyContent: "center", width: "28px", height: "28px",
            background: "transparent", border: "1px solid " + (query.trim() && !busy ? "var(--accent-line)" : "var(--control-border)"),
            borderRadius: "var(--r)", color: query.trim() && !busy ? "var(--accent)" : "var(--control-fg-disabled)",
            cursor: query.trim() && !busy ? "pointer" : "default", transition: "var(--transition-control)",
          }}><Icon name="arrow-right" size={14} /></button>
        </form>
      </div>
    </div>
  );
}

Object.assign(window, { CenterStage });
