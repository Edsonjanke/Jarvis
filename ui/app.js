/* app.js — wiring. Fetches the index, drives the graph, the inspector, the
 * filter panel and the reactor.
 *
 * Stage 3: graph, search and conversation. Voice and memory are not connected,
 * and the controls that need them say so rather than failing quietly.
 *
 * The ask bar does two things at once and they do not collide: typing runs the
 * instant file search, Enter sends the question to the model.
 */

import { Graph } from "/graph.js";

const $ = (id) => document.getElementById(id);
const STAGE = Number(document.documentElement.dataset.stage || "2");

// The reactor is driven on a timer, not requestAnimationFrame: RAF stops dead
// in a backgrounded tab, and in stage 4 this same loop reads the microphone.
const REACTOR_MS = 33;

const state = {
  health: null,
  graph: null,
  nodes: new Map(),
  hidden: new Set(),
  focused: null,
  pathAnchor: null,
  reactor: "idle",
  level: 0,
};

// ── alerts ────────────────────────────────────────────────────────────────

function alert(level, label, message) {
  const host = $("alerts");
  const row = document.createElement("div");
  row.className = "alert";
  row.dataset.level = level;
  row.innerHTML = "<b></b><span></span>";
  row.querySelector("b").textContent = label;
  row.querySelector("span").textContent = message;
  host.appendChild(row);
  host.hidden = false;
}

// ── boot ──────────────────────────────────────────────────────────────────

const graph = new Graph($("stage"));

async function boot() {
  let health, payload;
  try {
    [health, payload] = await Promise.all([
      fetch("/api/health").then((r) => r.json()),
      fetch("/api/graph").then((r) => r.json()),
    ]);
  } catch (err) {
    alert("crit", "Offline", `The JARVIS server is not answering. ${err}`);
    return;
  }

  state.health = health;
  state.graph = payload;
  state.nodes = new Map(payload.nodes.map((n) => [n.id, n]));

  for (const problem of payload.problems || []) alert("crit", "Vault", problem);
  if (!payload.nodes.length) {
    alert("crit", "Empty", "Nothing was indexed. That is a failure, not an empty result.");
  }
  if (payload.skipped?.length) {
    alert("warn", "Skipped", `${payload.skipped.length} files were not indexed. `
      + payload.skipped.slice(0, 2).map((s) => s.reason).join("; "));
  }
  if (health.stage_note) alert("info", `Stage ${health.stage}`, health.stage_note);

  graph.resize();
  graph.setData(payload);
  graph.start();

  renderTypes();
  renderHubs();
  renderVaultStats();
  rotateExamples();
  applyStageGating();
}

// ── inspector ─────────────────────────────────────────────────────────────

async function openNote(id) {
  state.focused = id;
  graph.setFocus(id);

  let note;
  try {
    note = await fetch(`/api/note?id=${encodeURIComponent(id)}`).then((r) => r.json());
  } catch {
    alert("warn", "Read", `Could not load ${id}.`);
    return;
  }
  if (note.error) { alert("warn", "Read", note.error); return; }

  $("inspector-empty").hidden = true;
  $("inspector-note").hidden = false;
  $("clear-focus").hidden = false;

  $("note-swatch").style.background = graph.colourFor(note.type);
  $("note-kind").textContent = note.type;
  $("note-title").textContent = note.title;
  $("note-path").textContent = `${note.root}/${note.rel}`;

  const meta = $("note-meta");
  meta.replaceChildren();
  const rows = [
    ["links", String(note.degree)],
    ["size", `${(note.size / 1024).toFixed(1)} kB`],
    ["changed", new Date(note.mtime * 1000).toISOString().slice(0, 10)],
  ];
  for (const [key, value] of Object.entries(note.meta || {})) {
    if (["title", "type", "tags"].includes(key)) continue;
    rows.push([key, Array.isArray(value) ? value.join(", ") : String(value)]);
  }
  if (note.tags?.length) rows.push(["tags", note.tags.join(" ")]);
  if (note.warning) rows.push(["warning", note.warning]);
  for (const [key, value] of rows) {
    const k = document.createElement("li");
    k.className = "k";
    k.textContent = key;
    const v = document.createElement("li");
    v.className = "v";
    v.textContent = value;
    meta.append(k, v);
  }

  $("note-body").textContent = note.text?.trim() || note.warning || "(no text)";

  const links = $("note-links");
  links.replaceChildren();
  $("link-count").textContent = note.links.length ? `(${note.links.length})` : "(none)";
  for (const link of note.links) {
    links.appendChild(rowButton(link.title, link.type, link.direction === "out" ? "→" : "←",
      () => openNote(link.id)));
  }

  $("inspector").scrollTop = 0;
}

function rowButton(label, type, tail, onClick) {
  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "row";
  const dir = document.createElement("span");
  dir.className = "dir";
  dir.textContent = tail || "";
  const dot = document.createElement("span");
  dot.className = "swatch";
  dot.style.background = graph.colourFor(type);
  const text = document.createElement("span");
  text.className = "label";
  text.textContent = label;
  btn.append(dir, dot, text);
  btn.addEventListener("click", onClick);
  li.appendChild(btn);
  return li;
}

function closeNote() {
  state.focused = null;
  state.pathAnchor = null;
  graph.setFocus(null);
  $("inspector-note").hidden = true;
  $("path-panel").hidden = true;
  $("inspector-empty").hidden = false;
  $("clear-focus").hidden = true;
}

// ── shortest path ─────────────────────────────────────────────────────────

async function tracePath(fromId, toId) {
  const res = await fetch(`/api/path?a=${encodeURIComponent(fromId)}&b=${encodeURIComponent(toId)}`)
    .then((r) => r.json());
  const panel = $("path-panel");
  const list = $("path-list");
  list.replaceChildren();

  if (!res.found) {
    graph.setPath([]);
    panel.hidden = false;
    const li = document.createElement("li");
    li.className = "muted";
    li.style.padding = "6px 0";
    li.textContent = "No route between those two.";
    list.appendChild(li);
    return;
  }

  graph.setPath(res.path);
  panel.hidden = false;
  res.path.forEach((id, i) => {
    const node = state.nodes.get(id);
    list.appendChild(rowButton(res.titles[i], node?.type || "other", "", () => openNote(id)));
  });
}

// ── filter panel ──────────────────────────────────────────────────────────

function renderTypes() {
  const list = $("type-list");
  list.replaceChildren();
  const counts = state.graph.counts || {};
  const biggest = Math.max(1, ...Object.values(counts));

  for (const [type, n] of Object.entries(counts)) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "type-row";
    btn.setAttribute("aria-pressed", "true");

    const dot = document.createElement("span");
    dot.className = "swatch";
    dot.style.background = graph.colourFor(type);

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = type;

    const num = document.createElement("span");
    num.className = "n";
    num.textContent = n;

    const wrap = document.createElement("span");
    wrap.style.flex = "1";
    const bar = document.createElement("span");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = `${(n / biggest) * 100}%`;
    fill.style.background = graph.colourFor(type);
    bar.appendChild(fill);
    wrap.append(name, bar);

    btn.append(dot, wrap, num);
    btn.addEventListener("click", () => {
      const on = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", String(!on));
      if (on) state.hidden.add(type); else state.hidden.delete(type);
      graph.setHidden(state.hidden);
    });
    li.appendChild(btn);
    list.appendChild(li);
  }
}

$("filter-all").addEventListener("click", () => {
  state.hidden.clear();
  graph.setHidden(state.hidden);
  document.querySelectorAll(".type-row").forEach((b) => b.setAttribute("aria-pressed", "true"));
});

function renderHubs() {
  const list = $("hub-list");
  list.replaceChildren();
  for (const id of state.graph.hubs || []) {
    const node = state.nodes.get(id);
    if (!node) continue;
    const li = rowButton(node.title, node.type, "", () => { openNote(id); graph.centreOn(id); });
    li.querySelector(".row").appendChild(Object.assign(document.createElement("span"), {
      className: "tail", textContent: `${node.degree}`,
    }));
    list.appendChild(li);
  }
}

function renderVaultStats() {
  const dl = $("vault-stats");
  dl.replaceChildren();
  const h = state.health;
  const rows = [
    ["mode", h.demo ? "demo" : "live"],
    ["notes", String(h.notes)],
    ["links", String(state.graph.edges.length)],
    ["indexed in", `${state.graph.build_seconds}s`],
    ["model", h.model.available ? h.model.name : "missing"],
    ["voice", h.voice.available ? "elevenlabs" : "missing"],
  ];
  for (const [key, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    if (value === "missing") dd.style.color = "var(--warn)";
    dl.append(dt, dd);
  }
}

// ── ask bar ───────────────────────────────────────────────────────────────

const input = $("ask-input");
let searchTimer = null;

function examples() {
  const hubs = (state.graph?.hubs || [])
    .map((id) => state.nodes.get(id)?.title)
    .filter(Boolean)
    .slice(0, 4);
  return [...hubs, "who links to what", "anything about pricing"];
}

function rotateExamples() {
  const pool = examples();
  if (!pool.length) return;
  let i = 0;
  const set = () => { input.placeholder = pool[i % pool.length]; i++; };
  set();
  setInterval(() => { if (document.activeElement !== input && !input.value) set(); }, 6000);
}

async function runSearch(query) {
  const box = $("results");
  if (!query.trim()) { box.hidden = true; box.replaceChildren(); return; }

  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=8`)
    .then((r) => r.json());

  box.replaceChildren();
  if (!res.hits.length) {
    const empty = document.createElement("div");
    empty.className = "result snip";
    empty.textContent = `No file matches "${query}".`;
    box.appendChild(empty);
    box.hidden = false;
    return;
  }

  for (const hit of res.hits) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "result";

    const head = document.createElement("div");
    head.className = "head";
    const dot = document.createElement("span");
    dot.className = "swatch";
    dot.style.background = graph.colourFor(hit.type);
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = hit.title;
    const where = document.createElement("span");
    where.className = "where";
    where.textContent = hit.rel;
    head.append(dot, title, where);

    const snip = document.createElement("div");
    snip.className = "snip";
    snip.textContent = hit.snippet;

    btn.append(head, snip);
    btn.addEventListener("click", () => {
      openNote(hit.id);
      graph.centreOn(hit.id);
      box.hidden = true;
      input.blur();
    });
    box.appendChild(btn);
  }
  box.hidden = false;
}

input.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(input.value), 160);
});
input.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { input.value = ""; runSearch(""); input.blur(); }
  if (ev.key === "Enter" && STAGE >= 3) {
    ev.preventDefault();
    clearTimeout(searchTimer);          // don't let the search overwrite the answer
    think("ask", { q: input.value }, input.value);
  }
});

$("ask-hint").textContent = "enter";

// ── asking ────────────────────────────────────────────────────────────────

// One at a time. A second question while the first is in flight would race to
// write the same panel, and the loser would look like a dropped answer.
let thinking = false;

async function think(kind, payload, label) {
  if (thinking) return;
  if (kind !== "brief" && !String(label || "").trim()) {
    hint(kind === "plan" ? "Type the goal first, then press Plan." : "Type a question first.");
    return;
  }

  thinking = true;
  setReactor("thinking", kind);
  state.level = 0.55;
  hint(`Reading the vault…`);

  let res;
  try {
    res = await fetch(`/api/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json());
  } catch (err) {
    $("results").hidden = true;
    alert("crit", "Offline", `The JARVIS server is not answering. ${err}`);
    return stopThinking();
  }

  if (res.error) {
    hint(res.error);
    alert("warn", kind === "brief" ? "Brief" : kind === "plan" ? "Plan" : "Ask", res.error);
    return stopThinking();
  }

  renderAnswer(res);
  stopThinking();
}

function stopThinking() {
  thinking = false;
  state.level = 0;
  setReactor("idle");
}

function hint(text) {
  const box = $("results");
  box.replaceChildren();
  const row = document.createElement("div");
  row.className = "result snip";
  row.textContent = text;
  box.appendChild(row);
  box.hidden = false;
}

function renderAnswer(res) {
  const box = $("results");
  box.replaceChildren();

  const wrap = document.createElement("div");
  wrap.className = "answer";

  const head = document.createElement("div");
  head.className = "answer-head";
  const kind = document.createElement("span");
  kind.className = "eyebrow";
  kind.textContent = res.kind;
  const meta = document.createElement("span");
  meta.className = "answer-meta";
  meta.textContent = `${res.usage?.model || "model"} · read ${res.considered.length} notes · ${res.seconds}s`;
  head.append(kind, meta);

  const body = document.createElement("div");
  body.className = "answer-body";
  body.textContent = res.answer;

  wrap.append(head, body);

  if (res.usage?.truncated) {
    const cut = document.createElement("div");
    cut.className = "answer-warn";
    cut.textContent = "Cut off at the token limit — the answer above is incomplete.";
    wrap.appendChild(cut);
  }

  const cites = document.createElement("div");
  cites.className = "cites";
  const label = document.createElement("span");
  label.className = "eyebrow";
  label.textContent = res.citations.length ? "Sources" : "";
  cites.appendChild(label);

  if (!res.citations.length) {
    const none = document.createElement("span");
    none.className = "answer-warn";
    none.textContent = "No note was cited — treat this as unsourced.";
    cites.appendChild(none);
  }

  for (const cite of res.citations) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "cite";
    chip.title = cite.id;
    const dot = document.createElement("span");
    dot.className = "swatch";
    dot.style.background = graph.colourFor(cite.type);
    const text = document.createElement("span");
    text.textContent = cite.title;
    chip.append(dot, text);
    chip.addEventListener("click", () => { openNote(cite.id); graph.centreOn(cite.id); });
    cites.appendChild(chip);
  }
  wrap.appendChild(cites);

  box.appendChild(wrap);
  box.hidden = false;

  // Light every cited note at once, so the answer has a shape on the graph.
  graph.setPath(res.citations.map((c) => c.id));
}

$("btn-brief").addEventListener("click", () => think("brief", {}, "brief"));
$("btn-plan").addEventListener("click", () => think("plan", { goal: input.value }, input.value));

// ── stage gating: a control that cannot work says which step wires it ─────

function applyStageGating() {
  const why = {
    3: "wired in step 3, with the tools",
    4: "wired in step 4, with voice",
    5: "wired in step 5, with memory",
  };
  for (const btn of document.querySelectorAll("[data-stage-min]")) {
    const need = Number(btn.dataset.stageMin);
    if (need > STAGE) {
      btn.disabled = true;
      btn.title = why[need] || `not available until step ${need}`;
    }
  }
  $("ask-mode").textContent = STAGE >= 3 ? "ask" : "find";
  input.setAttribute("aria-label", STAGE >= 3 ? "Ask JARVIS" : "Search your files");
}

// ── reactor ───────────────────────────────────────────────────────────────

const reactorCanvas = $("reactor");
const rctx = reactorCanvas.getContext("2d");
const BINS = 64;
const bins = new Float32Array(BINS);
let sweep = 0;

function drawReactor() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const size = 176;
  if (reactorCanvas.width !== size * dpr) {
    reactorCanvas.width = size * dpr;
    reactorCanvas.height = size * dpr;
  }
  rctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  rctx.clearRect(0, 0, size, size);

  const cx = size / 2, cy = size / 2;
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim();
  const idle = css.getPropertyValue("--ink-3").trim();
  const live = state.reactor !== "idle";
  const colour = live ? accent : idle;
  const TAU = Math.PI * 2;

  // Bezel: twelve index marks, like a dial face. Static, so the moving parts
  // have something to move against.
  rctx.strokeStyle = idle;
  rctx.lineWidth = 1;
  for (let i = 0; i < 12; i++) {
    const angle = (i / 12) * TAU - Math.PI / 2;
    const long = i % 3 === 0;
    rctx.globalAlpha = long ? 0.36 : 0.16;
    rctx.beginPath();
    rctx.moveTo(cx + Math.cos(angle) * 84, cy + Math.sin(angle) * 84);
    rctx.lineTo(cx + Math.cos(angle) * (long ? 74 : 79), cy + Math.sin(angle) * (long ? 74 : 79));
    rctx.stroke();
  }

  // Outer polar level meter, phosphor decay so bins fade rather than snap.
  const rIn = 56, rOut = 79;
  for (let i = 0; i < BINS; i++) {
    bins[i] *= 0.90;
    const angle = (i / BINS) * TAU - Math.PI / 2;
    const len = 1.5 + bins[i] * (rOut - rIn);
    rctx.strokeStyle = colour;
    rctx.globalAlpha = 0.2 + bins[i] * 0.75;
    rctx.lineWidth = 2;
    rctx.beginPath();
    rctx.moveTo(cx + Math.cos(angle) * rIn, cy + Math.sin(angle) * rIn);
    rctx.lineTo(cx + Math.cos(angle) * (rIn + len), cy + Math.sin(angle) * (rIn + len));
    rctx.stroke();
  }

  // Inner rim.
  rctx.globalAlpha = live ? 0.5 : 0.2;
  rctx.strokeStyle = colour;
  rctx.lineWidth = 1;
  rctx.beginPath();
  rctx.arc(cx, cy, 46, 0, TAU);
  rctx.stroke();

  // One arc carries the state: a slow crawl at idle, a fast sweep when live.
  const t = performance.now() / (live ? 800 : 6000);
  const head = t % TAU;
  const arc = live ? 1.35 : 0.5;
  const grad = rctx.createLinearGradient(cx - 46, cy - 46, cx + 46, cy + 46);
  grad.addColorStop(0, colour);
  grad.addColorStop(1, colour);
  rctx.strokeStyle = grad;
  rctx.globalAlpha = live ? 1 : 0.55;
  rctx.lineWidth = 2.5;
  rctx.lineCap = "round";
  if (live) { rctx.shadowColor = accent; rctx.shadowBlur = 10; }
  rctx.beginPath();
  rctx.arc(cx, cy, 46, head, head + arc);
  rctx.stroke();
  rctx.shadowBlur = 0;
  rctx.lineCap = "butt";
  rctx.globalAlpha = 1;
}

function reactorTick() {
  if (state.reactor === "idle") {
    // One faint bin walks the ring — proof of life, nothing more.
    sweep = (sweep + 0.6) % BINS;
    bins[Math.floor(sweep)] = Math.max(bins[Math.floor(sweep)], 0.22);
  } else {
    const spread = state.reactor === "speaking" ? 0.5 : 1;
    for (let i = 0; i < BINS; i++) {
      const jitter = Math.random() * state.level * spread;
      bins[i] = Math.max(bins[i], jitter);
    }
  }
  drawReactor();
}

function setReactor(next, sub = "") {
  state.reactor = next;
  $("reactor-state").textContent = next;
  $("reactor-state").dataset.state = next;
  $("reactor-sub").textContent = sub;
}

setInterval(reactorTick, REACTOR_MS);

// ── graph events ──────────────────────────────────────────────────────────

graph.on("select", (node, shift) => {
  if (!node) { closeNote(); return; }
  if (shift && state.focused && state.focused !== node.id) {
    tracePath(state.focused, node.id);
    return;
  }
  graph.clearPath();
  $("path-panel").hidden = true;
  openNote(node.id);
});

$("clear-focus").addEventListener("click", closeNote);

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { closeNote(); $("results").hidden = true; }
  if (ev.key === "/" && document.activeElement !== input) { ev.preventDefault(); input.focus(); }
});

// ── go ────────────────────────────────────────────────────────────────────

// Local single-user tool: having the graph reachable from the console is worth
// more than the hygiene of hiding it.
window.jarvis = { graph, state, setReactor, openNote, tracePath };

setReactor("idle");
boot();
