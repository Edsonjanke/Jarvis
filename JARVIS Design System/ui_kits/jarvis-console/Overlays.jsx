/* The two overlays. Both are plates — the one place v2 still uses v1's
   translucent panel recipe, because they sit on top of the graph rather
   than on the field. */
const { HudFrame, MetaGrid, Row, BrainRow, Button, Eyebrow, PanelNote, OpenLink, TerminalLog, Icon } = window.JARVISDesignSystem_ad8200;

const PLATE = {
  position: "fixed", zIndex: 6, top: "var(--rail-gutter)",
  background: "var(--surface-panel)", backdropFilter: "var(--blur-panel)", WebkitBackdropFilter: "var(--blur-panel)",
  border: "1px solid var(--border-hairline)", borderTopColor: "var(--border-lit)", borderRadius: "var(--r)",
  padding: "var(--pad)", maxHeight: "min(72vh, calc(100vh - var(--rail-gutter) * 2))",
  overflowY: "auto", overscrollBehavior: "contain", scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent",
  fontFamily: "var(--font-mono)", fontSize: "var(--size-base)", color: "var(--text-body)",
};

function CloseX({ onClick }) {
  return (
    <button type="button" onClick={onClick} aria-label="Fechar" style={{
      position: "absolute", top: "10px", right: "10px", width: "20px", height: "20px", display: "flex",
      alignItems: "center", justifyContent: "center", background: "transparent", border: "1px solid var(--control-border)",
      borderRadius: "var(--r)", color: "var(--control-fg)", cursor: "pointer", transition: "var(--transition-control)",
    }}><Icon name="x" size={11} /></button>
  );
}

function Inspector({ note, links, path, hubs, onOpen, onClose }) {
  if (!note) return null;
  return (
    <div style={{ ...PLATE, left: "calc(var(--rail-w) + var(--rail-gutter) * 2)", width: "334px" }}>
      <CloseX onClick={onClose} />
      <HudFrame label="Inspector" right={note.type}>
        <div style={{ display: "flex", gap: "9px", alignItems: "baseline", paddingRight: "22px" }}>
          <span style={{ width: "var(--swatch)", height: "var(--swatch)", borderRadius: "50%", flex: "none", background: "var(--t-" + note.type + ", var(--t-other))", transform: "translateY(2px)" }} />
          <span style={{ fontSize: "var(--size-title)", color: "var(--text-strong)", lineHeight: 1.25 }}>{note.title}</span>
        </div>
        <div style={{ marginTop: "6px", fontSize: "var(--size-tick)", color: "var(--ink-3)" }}>{note.rel}</div>
        {note.meta && Object.keys(note.meta).length ? (
          <div style={{ marginTop: "11px" }}><MetaGrid rows={Object.entries(note.meta)} /></div>
        ) : null}
        {note.warning ? <div style={{ marginTop: "10px", color: "var(--warn)" }}><PanelNote>{note.warning}</PanelNote></div> : null}
        {note.body ? (
          <p style={{ margin: "12px 0 0", fontFamily: "var(--font-sans)", fontSize: "var(--size-prose)", lineHeight: 1.55, color: "var(--text-strong)", maxHeight: "var(--scroll-note)", overflowY: "auto", textWrap: "pretty" }}>{note.body}</p>
        ) : null}
        <div style={{ marginTop: "12px" }}><OpenLink href={"file:///vault/" + note.rel} title="abre fora do JARVIS">Abrir o arquivo</OpenLink></div>
      </HudFrame>

      <div style={{ marginTop: "16px" }}>
        <HudFrame label="Vínculos" right={String(links.length)}>
          {links.length ? links.map((l) => (
            <Row key={l.id} type={l.type} label={l.title} dir={l.dir} onClick={() => onOpen(l.id)} />
          )) : <PanelNote>Nenhum vínculo.</PanelNote>}
        </HudFrame>
      </div>

      {path && path.length ? (
        <div style={{ marginTop: "16px" }}>
          <HudFrame label="Caminho mais curto" right={path.length - 1 + " passos"}>
            {path.map((p, i) => <Row key={p.id} type={p.type} label={p.title} step={i + 1} onClick={() => onOpen(p.id)} />)}
          </HudFrame>
        </div>
      ) : null}

      <div style={{ marginTop: "16px" }}>
        <HudFrame label="Maiores hubs" foot>
          {hubs.map((h) => <Row key={h.id} type={h.type} label={h.title} tail={h.degree} onClick={() => onOpen(h.id)} />)}
        </HudFrame>
      </div>
    </div>
  );
}

function SidePanel({ id, vault, brain, onBrain, tools, onTool, edits, onUndo, log, onClose }) {
  if (!id) return null;
  const wrap = (label, right, children) => (
    <div style={{ ...PLATE, right: "calc(var(--rail-w) + var(--rail-gutter) * 2)", width: "300px" }}>
      <CloseX onClick={onClose} />
      <HudFrame label={label} right={right} foot>{children}</HudFrame>
    </div>
  );

  if (id === "cerebro") {
    return wrap("Cérebro", "modelo", (
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {vault.brains.map((b) => <BrainRow key={b.id} name={b.label} note={b.note} pressed={b.id === brain} onClick={() => onBrain(b.id)} />)}
      </div>
    ));
  }
  if (id === "ferramentas") {
    return wrap("Ferramentas", "fora do vault", (
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {tools.map((t) => (
          <BrainRow
            key={t.name}
            name={t.label}
            note={t.authenticated ? (t.on ? "ligada" : "desligada") : "falta " + t.needs}
            pressed={t.on}
            disabled={!t.authenticated}
            onClick={() => t.authenticated && onTool(t.name)}
          />
        ))}
      </div>
    ));
  }
  if (id === "alteracoes") {
    return wrap("Alterações", edits.length + " no disco", (
      <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
        <PanelNote>Cópias em .jarvis/undo. Nada é sobrescrito sem uma.</PanelNote>
        {edits.map((e) => (
          <div key={e.id} style={{ display: "flex", flexDirection: "column", gap: "4px", paddingBottom: "8px", borderBottom: "1px solid var(--hairline)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "var(--size-tick)" }}>
              <span style={{ color: "var(--text-body)" }}>{e.action}</span>
              <span style={{ color: "var(--ink-3)" }}>{e.when}</span>
            </div>
            <div style={{ fontSize: "var(--size-tick)", color: "var(--text-strong)", wordBreak: "break-all" }}>{e.path}</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "var(--size-tick)", color: "var(--ink-3)" }}>{e.before} → {e.after} bytes</span>
              <Button size="ghost" disabled={e.undone} title={e.undone ? "já desfeito" : undefined} onClick={() => onUndo(e.id)}>
                {e.undone ? "desfeito" : "desfazer"}
              </Button>
            </div>
          </div>
        ))}
      </div>
    ));
  }
  if (id === "habilidades") {
    return wrap("Habilidades", "como você trabalha", (
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        {vault.skills.map((s) => (
          <BrainRow key={s.name} name={s.name} note={s.problem ? "⚠ " + s.problem : s.description} pressed={s.always} disabled={!!s.problem} />
        ))}
      </div>
    ));
  }
  return wrap("Terminal", "sessão", <TerminalLog lines={log} height={280} />);
}

Object.assign(window, { Inspector, SidePanel });
