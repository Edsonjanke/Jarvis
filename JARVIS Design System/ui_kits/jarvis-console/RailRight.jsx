/* Right rail — the world outside the vault (weather, scheduled work), the
   things you can press, and the log. */
const { HudFrame, Tile, TerminalLog, Icon } = window.JARVISDesignSystem_ad8200;

function RailRight({ weather, jobs, quick, quickState, onQuick, shortcuts, onShortcut, openPanel, log, busy }) {
  return (
    <div style={{
      position: "fixed", zIndex: 4, right: "var(--rail-gutter)", top: "var(--rail-gutter)", bottom: "var(--rail-gutter)",
      width: "var(--rail-w)", display: "flex", flexDirection: "column", gap: "var(--rail-gap)",
      overflowY: "auto", overscrollBehavior: "contain", scrollbarWidth: "thin", scrollbarColor: "var(--ink-3) transparent",
    }}>
      <HudFrame label="Clima" right={weather.city}>
        <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
          <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", paddingTop: "2px" }}>
            <Icon name="cloud-rain" size={26} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: "20px", color: "var(--text-strong)", textShadow: "var(--hud-glow-soft)", lineHeight: 1 }}>{weather.temp}°</span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            {weather.rows.map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "var(--size-tick)", padding: "1px 0" }}>
                <span style={{ color: "var(--text-label)" }}>{k}</span>
                <span style={{ color: "var(--text-body)" }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: "8px", fontSize: "var(--size-tick)", color: "var(--text-label)", textTransform: "uppercase", letterSpacing: "0.1em" }}>{weather.sky}</div>
        <div style={{ marginTop: "7px", display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: "4px" }}>
          {weather.week.map(([d, t]) => (
            <div key={d} style={{ textAlign: "center", fontSize: "8px", color: "var(--ink-3)", letterSpacing: "0.06em" }}>
              <div style={{ textTransform: "uppercase" }}>{d}</div>
              <div style={{ color: "var(--text-body)", marginTop: "3px" }}>{t}</div>
            </div>
          ))}
        </div>
      </HudFrame>

      <HudFrame label="Tarefas agendadas">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: "4px" }}>
          {jobs.map(([n, label], i) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "17px", color: i === 3 ? "var(--crit)" : "var(--accent)", textShadow: i === 3 ? "none" : "var(--hud-glow-soft)", lineHeight: 1.1 }}>{n}</div>
              <div style={{ fontSize: "7.5px", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-label)", marginTop: "3px" }}>{label}</div>
            </div>
          ))}
        </div>
      </HudFrame>

      <HudFrame label="Ações rápidas">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: "var(--tile-gap)" }}>
          {quick.map((q) => (
            <Tile
              key={q.id}
              icon={q.icon}
              label={q.label}
              active={!!quickState[q.id]}
              disabled={q.disabled}
              title={q.title || q.note}
              onClick={() => onQuick(q)}
            />
          ))}
        </div>
      </HudFrame>

      <HudFrame label="Atalhos">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "var(--tile-gap)" }}>
          {shortcuts.map((s) => (
            <Tile key={s.id} icon={s.icon} label={s.label} active={openPanel === s.id} onClick={() => onShortcut(s.id)} />
          ))}
        </div>
      </HudFrame>

      <HudFrame label="Terminal" right={busy ? "ocupado" : null} foot>
        <TerminalLog lines={log} busy={busy} height={132} />
      </HudFrame>
    </div>
  );
}

Object.assign(window, { RailRight });
