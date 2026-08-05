/* JARVIS console — v2. Same product as v1 (one vault, one graph, one ask
   bar); the shell is the instrument HUD instead of three plates.

   State lives here and nowhere else: the rails report, the stage asks, the
   overlays read. */
const { useState, useEffect, useRef, useMemo, useCallback } = React;
const V = window.VAULT, T = window.TELEMETRY;

const BY_ID = new Map(V.nodes.map((n) => [n.id, n]));
const NEIGH = new Map(V.nodes.map((n) => [n.id, []]));
V.edges.forEach((e) => { NEIGH.get(e.source).push(e.target); NEIGH.get(e.target).push(e.source); });

function shortestPath(a, b) {
  if (!a || !b || a === b) return null;
  const prev = new Map([[a, null]]);
  const queue = [a];
  while (queue.length) {
    const cur = queue.shift();
    if (cur === b) break;
    for (const next of NEIGH.get(cur) || []) {
      if (prev.has(next)) continue;
      prev.set(next, cur); queue.push(next);
    }
  }
  if (!prev.has(b)) return null;
  const out = [];
  for (let cur = b; cur !== null; cur = prev.get(cur)) out.unshift(cur);
  return out;
}

const clock = () => new Date().toLocaleTimeString("pt-BR", { hour12: false });
const hhmm = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const greetingFor = (h) => (h < 5 ? "BOA MADRUGADA, EDSON" : h < 12 ? "BOM DIA, EDSON" : h < 18 ? "BOA TARDE, EDSON" : "BOA NOITE, EDSON");
const drift = (v) => Math.max(4, Math.min(97, Math.round(v + (Math.random() - 0.5) * 7)));

function JarvisConsoleV2() {
  const [metrics, setMetrics] = useState(T.system);
  const [feed, setFeed] = useState(T.feed);
  const [log, setLog] = useState(T.log);
  const [brain, setBrain] = useState(V.brains.find((b) => b.current).id);
  const [tools, setTools] = useState(V.tools);
  const [edits, setEdits] = useState(V.edits);
  const [quickState, setQuickState] = useState({ silencio: false, analisar: false });
  const [openPanel, setOpenPanel] = useState(null);
  const [focused, setFocused] = useState(null);
  const [anchor, setAnchor] = useState(null);
  const [pathIds, setPathIds] = useState(null);
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState("idle");
  const [answer, setAnswer] = useState(null);
  const [level, setLevel] = useState(0.5);
  const timer = useRef(null);

  const push = useCallback((tag, text) => setLog((l) => [...l.slice(-40), { at: clock(), tag, text }]), []);
  const note = useCallback((what, tail, tone) => setFeed((f) => [{ at: hhmm(), what, tail, tone }, ...f].slice(0, 7)), []);

  useEffect(() => {
    const id = setInterval(() => {
      setMetrics((m) => m.map((x) => ({ ...x, value: drift(x.value) })));
      setLevel((l) => Math.max(0.25, Math.min(1, l + (Math.random() - 0.5) * 0.2)));
    }, 2400);
    return () => clearInterval(id);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const out = [];
    for (const n of V.nodes) {
      const body = (V.bodies[n.id] || {}).body || "";
      const inTitle = n.title.toLowerCase().includes(q);
      const at = body.toLowerCase().indexOf(q);
      if (!inTitle && at < 0) continue;
      out.push({
        id: n.id, title: n.title, type: n.type, rel: n.rel,
        snippet: at >= 0 ? "…" + body.slice(Math.max(0, at - 34), at + 78).trim() + "…" : undefined,
      });
      if (out.length === 6) break;
    }
    return out;
  }, [query]);

  const open = useCallback((id) => {
    setFocused(id); setAnchor(id); setPathIds(null); setOpenPanel(null);
  }, []);

  const onSelect = useCallback((node, shift) => {
    if (!node) { setFocused(null); setPathIds(null); return; }
    if (shift && anchor && anchor !== node.id) {
      const p = shortestPath(anchor, node.id);
      setFocused(node.id);
      setPathIds(p ? new Set(p) : null);
      push(p ? "ok" : "warn", p ? "caminho traçado — " + (p.length - 1) + " passos" : "nenhum caminho entre as duas notas");
      return;
    }
    open(node.id);
  }, [anchor, open, push]);

  const ask = useCallback(() => {
    const q = query.trim();
    if (!q) return;
    setPhase("thinking"); setAnswer(null);
    push("info", "consulta: " + q);
    timer.current = setTimeout(() => {
      const a = V.answers.ask;
      const titles = {}, types = {};
      a.citations.forEach((id) => { const n = BY_ID.get(id); titles[id] = n ? n.title : id; types[id] = n ? n.type : "other"; });
      setAnswer({ ...a, titles, types });
      setPhase("idle");
      push("ok", "resposta pronta · " + a.citations.length + " citações · 4,1s");
      note("Resposta gerada", a.citations.length + " citações", "accent");
    }, 1500);
  }, [query, push, note]);

  const onQuick = useCallback((q) => {
    if (q.disabled) return;
    if (q.blocked) { push("err", q.note + " — nada foi ligado"); note("Ação recusada", q.label, "warn"); return; }
    if (q.id === "reindexar") {
      push("sys", "reindexando " + V.nodes.length + " notas…");
      note("Índice atualizado", "em curso");
      timer.current = setTimeout(() => { push("ok", "índice pronto — " + V.nodes.length + " notas, " + V.edges.length + " vínculos"); }, 1200);
      return;
    }
    setQuickState((s) => {
      const next = { ...s, [q.id]: !s[q.id] };
      push("info", q.label.toLowerCase() + ": " + (next[q.id] ? "ligado" : "desligado"));
      return next;
    });
  }, [push, note]);

  const onTool = useCallback((name) => setTools((ts) => ts.map((t) => {
    if (t.name !== name) return t;
    push("info", t.label + ": " + (t.on ? "desligada" : "ligada"));
    return { ...t, on: !t.on };
  })), [push]);

  const onUndo = useCallback((id) => setEdits((es) => es.map((e) => {
    if (e.id !== id || e.undone) return e;
    push("ok", "desfeito — " + e.path);
    note("Alteração desfeita", e.path.split("/").pop());
    return { ...e, undone: true };
  })), [push, note]);

  const focusedNote = focused ? { ...BY_ID.get(focused), ...(V.bodies[focused] || {}) } : null;
  const links = focused ? (NEIGH.get(focused) || []).map((id) => ({ ...BY_ID.get(id), dir: "→" })) : [];
  const pathNodes = pathIds ? Array.from(pathIds).map((id) => BY_ID.get(id)) : null;
  const hubs = V.hubs.map((id) => BY_ID.get(id));

  return (
    <>
      <GraphStage
        nodes={V.nodes} edges={V.edges} hidden={new Set()}
        focused={focused} pathIds={pathIds} onSelect={onSelect} opacity={0.68} sparseLabels
      />
      <RailLeft
        metrics={metrics} brains={V.brains} brain={brain} onBrain={(id) => { setBrain(id); push("info", "cérebro: " + id); }}
        memory={T.memory} network={T.network} feed={feed}
      />
      <CenterStage
        greeting={greetingFor(new Date().getHours())}
        phase={phase} level={level}
        query={query} onQuery={(v) => { setQuery(v); if (answer) setAnswer(null); }}
        onSubmit={ask} results={results} onOpen={open}
        answer={answer} onCite={open} onClear={() => { setAnswer(null); setQuery(""); push("sys", "nova conversa"); }}
        vaultStats={{ notes: V.nodes.length, links: V.edges.length }}
      />
      <RailRight
        weather={T.weather} jobs={T.jobs}
        quick={T.quick} quickState={quickState} onQuick={onQuick}
        shortcuts={T.shortcuts} onShortcut={(id) => setOpenPanel((p) => {
          const next = p === id ? null : id;
          if (next) { setFocused(null); setPathIds(null); }
          return next;
        })}
        openPanel={openPanel} log={log} busy={phase === "thinking"}
      />
      <Inspector
        note={focusedNote} links={links} path={pathNodes} hubs={hubs}
        onOpen={open} onClose={() => { setFocused(null); setPathIds(null); }}
      />
      <SidePanel
        id={openPanel} vault={V} brain={brain} onBrain={(id) => { setBrain(id); push("info", "cérebro: " + id); }}
        tools={tools} onTool={onTool} edits={edits} onUndo={onUndo} log={log}
        onClose={() => setOpenPanel(null)}
      />
    </>
  );
}

Object.assign(window, { JarvisConsoleV2 });
