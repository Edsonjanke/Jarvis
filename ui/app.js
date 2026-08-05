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
  // The conversation in progress. Empty means the next question starts a new
  // one; the server hands back an id and this holds it until you clear it.
  thread: "",
  tools: null,
  skills: null,
  edit: null,
  // Pictures attached to the question being typed. Cleared once sent.
  images: [],
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
  renderBrains();
  renderTools();
  renderSkills();
  renderEdits();
  renderBrowse();
  renderVaultStats();
  rotateExamples();
  applyStageGating();
}

// ── inspector ─────────────────────────────────────────────────────────────

// What /api/file will hand back. Kept in step with FILE_TYPES in main.py —
// the server is the one that decides, this only avoids offering a link that
// would come back 403.
const OPENABLE = new Set(["pdf", "md", "markdown", "mdx", "txt", "text"]);

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

  // The document itself, not the text JARVIS pulled out of it. For a PDF
  // invoice those are very different things — the extractor flattens a layout
  // into a stream of words, and for a scan or an encrypted file it gets
  // nothing at all. Opening the page is the answer to "but what does it
  // actually say".
  const open = $("note-open");
  const ext = (note.rel || "").slice(((note.rel || "").lastIndexOf(".") + 1) || Infinity).toLowerCase();
  if (OPENABLE.has(ext)) {
    open.hidden = false;
    open.href = `/api/file?id=${encodeURIComponent(id)}`;
    open.textContent = ext === "pdf" ? "Abrir o PDF" : "Abrir o arquivo";
    // A note whose text came back empty is exactly the one worth opening,
    // so say so rather than leaving the reader to wonder.
    open.title = note.warning
      ? `${note.warning} — abra o arquivo para ver`
      : `abrir ${note.rel} numa aba nova`;
  } else {
    open.hidden = true;
    open.removeAttribute("href");
  }

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

// ── the brain ─────────────────────────────────────────────────────────────
//
// Which model answers. Switching is verified before it takes effect — the
// server sends one tiny question to the new brain first — so a model this
// account cannot use is refused here, in a picker, rather than three seconds
// into the next real question.

async function renderBrains(payload) {
  const list = $("brain-list");
  let data = payload;
  if (!data) {
    try {
      data = await fetch("/api/brain").then((r) => r.json());
    } catch {
      return;                       // the panel simply stays as it was
    }
  }
  if (data.error) { alert("warn", "Cérebro", data.error); return; }

  $("brain-now").textContent = data.brains.find((b) => b.current)?.label || "";
  list.replaceChildren();

  for (const brain of data.brains) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "brain-row";
    btn.setAttribute("aria-pressed", String(!!brain.current));
    btn.title = brain.id;

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = brain.label;

    const note = document.createElement("span");
    note.className = "brain-note";
    note.textContent = brain.note || "";

    btn.append(name, note);
    btn.addEventListener("click", () => switchBrain(brain, btn));
    li.appendChild(btn);
    list.appendChild(li);
  }
}

// ── ferramentas ───────────────────────────────────────────────────────────
//
// What JARVIS may reach outside your notes. Everything is off until you switch
// it on here, one named tool at a time — and it lives on the page rather than
// in a settings file because "it can read your Drive" is not something anyone
// should have to discover by reading JSON.
//
// A thing worth saying plainly: the claude.ai connectors do NOT reach this.
// They belong to the interactive login, not to the headless call JARVIS makes.
// A server has to be declared with its own token, which is why the rows below
// say what each one is still missing.

async function renderTools(payload) {
  const list = $("tool-list");
  if (!list) return;
  let data = payload;
  if (!data) {
    try {
      data = await fetch("/api/tools").then((r) => r.json());
    } catch {
      return;                         // the panel simply stays as it was
    }
  }
  if (data.error) { alert("warn", "Ferramentas", data.error); return; }
  state.tools = data;

  const now = $("tool-now");
  if (now) now.textContent = data.enabled ? data.allowed.length + " ligada(s)" : "nenhuma";

  list.replaceChildren();
  for (const server of data.servers || []) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "brain-row";
    // A server without a credential cannot be switched on, and saying so on
    // the button beats letting someone turn it on and watch nothing happen.
    btn.disabled = !server.authenticated;
    btn.setAttribute("aria-pressed", String(isOn(data, server.name)));

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = server.label;

    const note = document.createElement("span");
    note.className = "brain-note";
    note.textContent = server.authenticated
      ? (isOn(data, server.name) ? "ligada" : "desligada")
      : "falta " + server.needs;
    btn.title = server.authenticated ? server.name : server.needs;

    btn.append(name, note);
    btn.addEventListener("click", () => toggleTool(server));
    li.appendChild(btn);
    list.appendChild(li);
  }

  const note = $("tool-note");
  if (note) note.textContent = data.note || "";
}

// A server is on when at least one of its tools is in the allowlist. The
// allowlist is the truth — the server list is only how it is presented.
function isOn(data, server) {
  return (data.allowed || []).some((t) => t.split("__")[1] === server);
}

async function toggleTool(server) {
  if (toggleTool.busy) return;
  toggleTool.busy = true;
  document.querySelectorAll("#tool-list .brain-row").forEach((b) => (b.disabled = true));

  const current = state.tools?.allowed || [];
  const allowed = isOn(state.tools, server.name)
    ? current.filter((t) => t.split("__")[1] !== server.name)
    : current.concat(server.tools || []);

  let res;
  try {
    res = await fetch("/api/tools", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ allowed }),
    }).then((r) => r.json());
  } catch (err) {
    alert("crit", "Offline", `${err}`);
  }
  toggleTool.busy = false;
  renderTools(res);
}

async function switchBrain(brain, btn) {
  if (brain.current || switchBrain.busy) return;
  switchBrain.busy = true;
  const was = btn.querySelector(".brain-note").textContent;
  btn.querySelector(".brain-note").textContent = "testando…";
  document.querySelectorAll(".brain-row").forEach((b) => (b.disabled = true));

  let res;
  try {
    res = await fetch("/api/brain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: brain.id }),
    }).then((r) => r.json());
  } catch (err) {
    alert("crit", "Offline", `${err}`);
  }
  document.querySelectorAll(".brain-row").forEach((b) => (b.disabled = false));
  switchBrain.busy = false;

  if (!res || res.error) {
    btn.querySelector(".brain-note").textContent = was;
    if (res?.error) alert("warn", "Cérebro", res.error);
    return;
  }
  renderBrains(res);
  // The health payload was fetched at boot, so the model row beneath would
  // otherwise keep naming the brain we just switched away from.
  if (state.health?.model) state.health.model.name = res.model;
  renderVaultStats();
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
    ["listen", h.voice.listen.available ? h.voice.listen.model : "missing"],
    ["speak", h.voice.speak?.engine === "edge-tts"
      ? `${h.voice.speak.voice} ${h.voice.speak.rate}/${h.voice.speak.pitch}`
      : window.speechSynthesis ? "this machine" : "missing"],
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
  // Research is the slow one — it searches, then opens the first pages — and
  // "Reading the vault…" for fifteen seconds reads as a hang. Say what it is
  // actually doing.
  hint(kind === "research" ? "Buscando na web e abrindo as páginas…"
                           : "Reading the vault…");

  let res;
  try {
    res = await fetch(`/api/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The conversation so far. Sending it is what makes "and of those,
      // which are PARINOX?" answerable — without it every question is asked
      // of a JARVIS that has never spoken to you before.
      body: JSON.stringify({
        ...payload,
        thread: state.thread || "",
        images: kind === "ask"
          ? state.images.map(({ media_type, data }) => ({ media_type, data }))
          : [],
      }),
    }).then((r) => r.json());
  } catch (err) {
    $("results").hidden = true;
    alert("crit", "Offline", `The JARVIS server is not answering. ${err}`);
    return stopThinking();
  }

  if (res.error) {
    hint(res.error);
    alert("warn", kind === "brief" ? "Brief" : kind === "plan" ? "Plan"
                : kind === "research" ? "Web" : "Ask", res.error);
    return stopThinking();
  }

  // Carry the thread on. The server starts a new one when we send none, so
  // this is also how the very first question gets an id at all.
  if (res.thread) { state.thread = res.thread; showThread(); }

  // The pictures went with the question and belong to it. Leaving them
  // attached would silently send them again with the next one.
  if (state.images.length) { state.images = []; renderAttachments(); }

  renderAnswer(res);
  stopThinking();
  // After stopThinking, so its setReactor("idle") cannot land on top of the
  // speaking state that speak() sets when the utterance actually starts.
  speak(res.answer);
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
  // Say when memory shaped the answer. Silently using remembered facts would
  // make an answer harder to account for than it needs to be.
  const recalled = res.recalled?.length
    ? ` · ${res.recalled.length} remembered`
    : "";
  // Same argument for skills and standing instructions: something that shaped
  // the answer and that you cannot see is something you cannot check.
  const shaped = res.skills?.length ? ` · ${res.skills.join(", ")}` : "";
  const standing = res.instructions?.length ? " · JARVIS.md" : "";
  meta.textContent = `${res.usage?.model || "model"} · read ${res.considered.length} notes`
                   + `${recalled}${shaped}${standing} · ${res.seconds}s`;
  meta.title = [
    ...(res.recalled || []),
    ...(res.skills || []).map((s) => `habilidade: ${s}`),
    ...(res.instructions || []).map((s) => `instruções: ${s}`),
  ].join("\n");
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
    // "Unsourced" used to cover two very different things, and flattening them
    // was making the warning useless. An answer that says up front "general
    // knowledge, not in your notes" is doing exactly what it should — warning
    // about it teaches Edson to ignore the warning. What still deserves the
    // red line is an answer that cited nothing and did not say why.
    const general = /conhecimento geral|general knowledge/i.test(res.answer || "");
    const none = document.createElement("span");
    none.className = general ? "answer-note" : "answer-warn";
    none.textContent = general
      ? "Conhecimento geral, não vem das suas notas — ele avisou."
      : "Nenhuma nota citada — trate como não verificado.";
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

// "research" mode rather than "search": it opens the first pages, because a
// figure lives inside a page and not in a snippet. That costs seconds, and the
// seconds are the point of the button.
$("btn-web").addEventListener("click",
  () => think("research", { q: input.value, mode: "research" }, input.value));

// ── voice ─────────────────────────────────────────────────────────────────
//
// Two halves, and they are not symmetrical.
//
// Speaking is done here, by the browser, out of the voices already installed
// on this machine. That is free, has no quota, works offline, and the audio
// never leaves the room.
//
// Listening goes to the server, which sends it to ElevenLabs. Their
// speech-to-text costs nothing on this account, and doing it there means the
// key stays server-side and this works in Firefox too — the browser's own
// SpeechRecognition is Chrome-only and ships the recording to Google.
//
// We capture raw PCM and encode a WAV ourselves rather than use MediaRecorder,
// which produces webm/opus. The docs promise "all major formats" without
// naming that one, and a format proven to work beats a format assumed to.

const VOICE = {
  sampleRate: 16000,      // what speech-to-text wants; smaller upload too
  maxSeconds: 30,
  mute: false,
  starting: false,        // set synchronously, so a second click cannot race in
  recording: null,        // the live capture chain, or null

  // -- always-on ------------------------------------------------------------
  //
  // "Sempre" leaves the microphone open. What that does NOT mean is that a
  // microphone open to the room is a microphone streaming to the internet:
  // the detector below runs here, on your machine, and only a stretch of
  // audio it judged to be speech is ever uploaded. Silence never leaves.
  //
  // Then the wake word decides again, after transcription: no "jarvis" in
  // what you said, no question asked, and the text is dropped where it stands.
  awake: false,
  wakeWord: "jarvis",
  busy: false,            // one segment in flight at a time

  calibrateMs: 1000,      // learn this room's noise before judging anything
  startMs: 250,           // sustained sound this long is someone talking
  hangoverMs: 800,        // silence this long is someone having finished
  preRollMs: 300,         // kept back, so a segment does not start mid-word
  minSpeechMs: 400,       // shorter than this is a cough, a door, a chair
};

/** Lowercase and strip accents, one character in and one character out.
 *
 * Length-preserving on purpose, exactly like _fold in vault.py: the wake word
 * is found in the folded text and the question is then sliced out of the
 * ORIGINAL by that same offset. "Jarvis, qual é a política?" has to keep its
 * accents in the question it forwards.
 */
function fold(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    let f = ch.toLowerCase();
    if (f.length !== 1) f = ch;                   // İ lowercases to two chars
    f = f.normalize("NFD").replace(/[̀-ͯ]/g, "");
    out += f.length === 1 ? f : ch;
  }
  return out;
}

/** The question after the wake word, or null when it was not said.
 *
 * Anything before the wake word is dropped too. Half a sentence of something
 * else, then "jarvis, what is the deposit policy" — the first half was not
 * addressed to it and is not its business.
 */
function afterWakeWord(text) {
  const at = fold(text).indexOf(VOICE.wakeWord);
  if (at < 0) return null;
  return text.slice(at + VOICE.wakeWord.length).replace(/^[\s,.:;!?"'…—–-]+/, "").trim();
}

// -- speaking --------------------------------------------------------------

function speechVoice() {
  const wanted = (state.health?.voice?.language || "").toLowerCase();
  const voices = window.speechSynthesis?.getVoices() || [];
  if (!voices.length) return null;
  if (!wanted) return null;                      // let the browser choose
  const tag = wanted.replace("_", "-");
  const lang = tag.split("-")[0];
  return voices.find((v) => v.lang.toLowerCase().replace("_", "-") === tag)
      || voices.find((v) => v.lang.toLowerCase().startsWith(lang))
      || null;
}

// The line JARVIS actually reads aloud.
//
// The rule: **the eye gets addresses, the ear gets prose.** It was already here
// for citation ids — "demo/notes/deposit-policy.md" read aloud is unbearable —
// and the browser broke it, because every answer about a page carries its URL.
// "agá tê tê pê ês dois pontos barra barra dábliu dábliu dábliu ponto youtube
// ponto com barra results interrogação search underline query igual rock" is
// forty seconds of noise for something the screen already shows.
//
// So three things never reach the voice: fenced blocks (a dump of page text),
// code spans holding an address or a path, and bare URLs. Everything stays on
// screen — nothing is hidden, only unspoken.
function speakable(text) {
  return text
    .replace(/```[\s\S]*?```/g, " ")                    // page dumps
    .replace(/`[^`\n]*(?:https?:\/\/|www\.|\/)[^`\n]*`/g, " ")   // addresses, paths
    .replace(/\[[^\]\n]{3,120}\]/g, " ")                // citation ids
    .replace(/https?:\/\/\S+|\bwww\.\S+/g, " ")         // bare URLs
    .replace(/[*_#`]/g, "")
    .replace(/\s+([.,;:!?])/g, "$1")                    // no " ." where a URL was
    .replace(/\s+/g, " ")
    .trim();
}

// Antonio, "modo jarvis" — pt-BR-AntonioNeural at -8% rate, -12Hz pitch.
//
// Edson picked it by listening to the samples in amostras/, and it is a real
// step up from the voices Windows ships. The cost is that the sentence leaves
// the machine: edge-tts synthesises on Microsoft's servers, and what JARVIS
// says out loud is his vault read back. The browser voice below stays as the
// fallback, and it is the local one — JARVIS_SPEAK=0 makes it the only one.
let jarvisAudio = null;

// "Is JARVIS talking right now?" — asked by always-on listening so the mic does
// not record his own voice and answer himself. It has to know about both
// engines: with only the speechSynthesis check, Antonio spoke and the mic
// listened straight through him.
function isSpeaking() {
  return Boolean(window.speechSynthesis?.speaking)
      || Boolean(jarvisAudio && !jarvisAudio.paused && !jarvisAudio.ended);
}

async function speakAntonio(text) {
  const res = await fetch("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.status);

  stopSpeaking();
  const url = URL.createObjectURL(await res.blob());
  const audio = new Audio(url);
  jarvisAudio = audio;
  state.level = 0.5;
  setReactor("speaking", state.health?.voice?.speak?.voice || "Antonio");
  // Revoked on every exit path: a blob per answer, never freed, is a leak that
  // only shows up after an hour of talking.
  const done = () => {
    URL.revokeObjectURL(url);
    if (jarvisAudio === audio) jarvisAudio = null;
    state.level = 0;
    setReactor("idle");
  };
  audio.onended = done;
  audio.onerror = done;
  await audio.play();
}

function speak(text) {
  if (VOICE.mute || !text) return;
  const line = speakable(text);
  if (!line) return;

  if (state.health?.voice?.speak?.engine === "edge-tts") {
    // Falling back is not failing quietly: the local voice still says the
    // sentence, and the reason lands in the alert strip so a dead network
    // never turns into a JARVIS that simply stopped talking.
    speakAntonio(line).catch((err) => {
      alert("warn", "Voz", `Antonio indisponível (${err}); falando com a voz local.`);
      speakLocal(line);
    });
    return;
  }
  speakLocal(line);
}

function speakLocal(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(
    text);   // already cleaned by speakable()
  const voice = speechVoice();
  if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }

  utterance.onstart = () => { state.level = 0.5; setReactor("speaking", voice?.name || ""); };
  utterance.onend = utterance.onerror = () => { state.level = 0; setReactor("idle"); };
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  window.speechSynthesis?.cancel();
  // Both engines, always. Muting while Antonio is mid-sentence has to stop
  // Antonio, not just the voice that happens to be the default today.
  if (jarvisAudio) { jarvisAudio.pause(); jarvisAudio = null; }
  if (state.reactor === "speaking") { state.level = 0; setReactor("idle"); }
}

// getVoices() is empty until the list loads, so re-read it when it arrives.
window.speechSynthesis?.addEventListener?.("voiceschanged", () => {});

// -- listening -------------------------------------------------------------

function encodeWav(samples, rate) {
  // 16-bit mono PCM in a 44-byte RIFF header. Nothing exotic — this is the
  // format the server is proven to transcribe.
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const ascii = (at, s) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };

  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVEfmt ");
  view.setUint32(16, 16, true);         // PCM header size
  view.setUint16(20, 1, true);          // format: PCM
  view.setUint16(22, 1, true);          // channels: mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);   // byte rate
  view.setUint16(32, 2, true);          // block align
  view.setUint16(34, 16, true);         // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

function toBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** Decide, block by block, whether someone is talking.
 *
 * Energy against a noise floor learned from this room in the first second —
 * a fixed threshold works in one room and in no other. Two timers turn that
 * into an utterance: sound has to hold for startMs before it counts as speech
 * starting, and silence has to hold for hangoverMs before it counts as speech
 * ending. Without the second one, every pause between words ends the sentence.
 *
 * Returns the finished segment when one just closed, otherwise null.
 */
function detectSpeech(vad, block, rate) {
  const ms = (block.length / rate) * 1000;

  let sum = 0;
  for (const v of block) sum += v * v;
  const rms = Math.sqrt(sum / block.length);

  // The room first. Judging before we know what quiet sounds like here would
  // make a noisy room permanently "talking" and a silent one deaf.
  if (vad.calibratedMs < VOICE.calibrateMs) {
    vad.calibratedMs += ms;
    vad.floor = vad.floor ? vad.floor * 0.9 + rms * 0.1 : rms;
    return null;
  }

  // The absolute term matters: in a truly silent room the floor approaches
  // zero, and a purely relative threshold would then trigger on nothing.
  const loud = rms > Math.max(vad.floor * 3, 0.012);

  if (loud) { vad.voicedMs += ms; vad.quietMs = 0; }
  else      { vad.quietMs += ms; if (!vad.open) vad.voicedMs = 0; }

  if (!vad.open) {
    // Keep the last fraction of a second in hand. By the time we are sure
    // someone is talking they are already a syllable in, and a segment that
    // starts mid-word transcribes as a different word.
    vad.preRoll.push(block);
    vad.preRollMs += ms;
    while (vad.preRollMs > VOICE.preRollMs && vad.preRoll.length > 1) {
      vad.preRollMs -= (vad.preRoll.shift().length / rate) * 1000;
    }
    if (vad.voicedMs >= VOICE.startMs) {
      vad.open = true;
      vad.segment = vad.preRoll.slice();
      vad.segmentMs = vad.preRollMs;
      vad.preRoll = []; vad.preRollMs = 0;
    }
    return null;
  }

  vad.segment.push(block);
  vad.segmentMs += ms;

  const ended = vad.quietMs >= VOICE.hangoverMs;
  const tooLong = vad.segmentMs >= VOICE.maxSeconds * 1000;
  if (!ended && !tooLong) return null;

  const segment = vad.segment;
  const spoken = vad.segmentMs - (ended ? vad.quietMs : 0);
  vad.open = false;
  vad.segment = []; vad.segmentMs = 0;
  vad.voicedMs = 0; vad.quietMs = 0;

  // A door closing clears the energy threshold and nothing else. Uploading it
  // would spend a request to be told it was a door.
  return spoken >= VOICE.minSpeechMs ? segment : null;
}

function freshVad() {
  return { floor: 0, calibratedMs: 0, voicedMs: 0, quietMs: 0,
           open: false, segment: [], segmentMs: 0, preRoll: [], preRollMs: 0 };
}

/** Shut a capture chain down and give the microphone back. Idempotent. */
function releaseChain(rec) {
  if (!rec || rec.done) return;
  rec.done = true;
  rec.node.onaudioprocess = null;
  try { rec.source.disconnect(); rec.node.disconnect(); } catch { /* already gone */ }
  // Without this the tab keeps showing the recording indicator and the
  // microphone stays live — in a tool whose whole premise is that audio does
  // not leave the room, a hot mic is the worst thing to leak.
  rec.stream.getTracks().forEach((t) => t.stop());
  rec.ctx.close().catch(() => {});
}

/** One detected utterance: transcribe it, and ask only if it was addressed here. */
async function sendSegment(rec, blocks) {
  if (VOICE.busy) return;
  VOICE.busy = true;

  const total = blocks.reduce((n, b) => n + b.length, 0);
  const samples = new Float32Array(total);
  let at = 0;
  for (const b of blocks) { samples.set(b, at); at += b.length; }

  setReactor("thinking", "transcribing");
  let heard;
  try {
    heard = await fetch("/api/listen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio: toBase64(encodeWav(samples, rec.rate)) }),
    }).then((r) => r.json());
  } catch {
    VOICE.busy = false;
    if (VOICE.recording === rec) setReactor("listening", `diga "${VOICE.wakeWord}"`);
    return;                                   // stay listening; do not shout
  }
  VOICE.busy = false;

  // The chain may have been switched off while that was in the air.
  if (VOICE.recording !== rec || !rec.always) return;

  if (heard.error) {
    setReactor("listening", `diga "${VOICE.wakeWord}"`);
    hint(heard.error);
    return;
  }

  const question = afterWakeWord(heard.text || "");
  if (question === null) {
    // Not addressed to JARVIS. It is dropped here and now — not shown, not
    // stored, not put in the box. Overhearing is the cost of always-on, and
    // acting on what it overheard would be the thing that makes it unusable.
    setReactor("listening", `diga "${VOICE.wakeWord}"`);
    return;
  }
  if (!question) {
    // Just the name, nothing after it.
    setReactor("listening", "pode perguntar");
    hint("Ouvi você me chamar — faça a pergunta.");
    return;
  }

  input.value = question;
  if (thinking) {
    setReactor("listening", `diga "${VOICE.wakeWord}"`);
    hint(`Ouvi "${question}" — outra pergunta já estava rodando. Está na caixa.`);
    return;
  }
  await think("ask", { q: question }, question);
  // think() resolves when the text lands; the answer is still being read out
  // loud after that. Going straight back to "listening" here would wipe the
  // speaking indicator off the reactor mid-sentence.
  if (VOICE.recording === rec && !isSpeaking()) {
    setReactor("listening", `diga "${VOICE.wakeWord}"`);
  }
}

async function startListening(always = false) {
  // Synchronously, before any await. getUserMedia takes seconds the first time
  // while the permission prompt is up, and the button gives no feedback until
  // it resolves — so without this a second click builds a second capture chain
  // and the first becomes unreachable, its microphone never released.
  if (VOICE.recording || VOICE.starting) return;
  if (thinking && !always) {
    hint("Finish the current question first.");
    return;
  }
  VOICE.starting = true;
  stopSpeaking();

  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });

    const ctx = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: VOICE.sampleRate,
    });
    const source = ctx.createMediaStreamSource(stream);
    const node = ctx.createScriptProcessor(4096, 1, 1);
    // rate is read now, not at stop time: closing the context first would make
    // it unreadable, and the WAV header has to state the truth.
    const rec = { stream, ctx, node, source, rate: ctx.sampleRate,
                  chunks: [], frames: 0, done: false,
                  always, vad: always ? freshVad() : null };

    node.onaudioprocess = (event) => {
      if (rec.done) return;
      // If this chain is no longer the live one it is an orphan: let it bury
      // itself rather than keep a microphone open and a buffer growing.
      if (VOICE.recording !== rec) { releaseChain(rec); return; }

      const block = new Float32Array(event.inputBuffer.getChannelData(0));

      let peak = 0;
      for (const v of block) peak = Math.max(peak, Math.abs(v));
      state.level = Math.min(1, peak * 3);

      if (rec.always) {
        // It must not hear itself. Its own answer coming out of the speakers
        // contains the word "jarvis" often enough, and one reply triggering
        // the next is a loop with your subscription on the other end.
        if (isSpeaking() || VOICE.busy || thinking) {
          rec.vad = freshVad();       // and recalibrate, the room just changed
          state.level = 0;
          return;
        }
        const segment = detectSpeech(rec.vad, block, rec.rate);
        if (segment) sendSegment(rec, segment);
        return;
      }

      rec.chunks.push(block);
      rec.frames += block.length;
      if (rec.frames > VOICE.sampleRate * VOICE.maxSeconds) stopListening();
    };

    source.connect(node);
    node.connect(ctx.destination);
    VOICE.recording = rec;
    if (always) {
      VOICE.awake = true;
      $("btn-wake").setAttribute("aria-pressed", "true");
      setReactor("listening", `diga "${VOICE.wakeWord}"`);
    } else {
      $("btn-mic").setAttribute("aria-pressed", "true");
      setReactor("listening", "click Mic again when done");
    }
  } catch (err) {
    // Anything at all going wrong after the microphone opened must still hand
    // it back — the failure paths are exactly where a hot mic gets forgotten.
    stream?.getTracks().forEach((t) => t.stop());
    VOICE.awake = false;
    $("btn-wake")?.setAttribute("aria-pressed", "false");
    alert("warn", "Microphone",
      err?.name === "NotAllowedError"
        ? "Permission for the microphone was refused. Allow it in the address bar and try again."
        : `The microphone could not be opened. ${err}`);
  } finally {
    VOICE.starting = false;
  }
}

async function stopListening() {
  const rec = VOICE.recording;
  if (!rec || rec.done) return;
  VOICE.recording = null;
  releaseChain(rec);

  $("btn-mic").setAttribute("aria-pressed", "false");
  state.level = 0;

  // Always-on already sent whatever was worth sending, utterance by utterance.
  // What is left in the buffer is the room, and switching off is not a
  // question — so nothing is uploaded on the way out.
  if (rec.always) {
    VOICE.awake = false;
    $("btn-wake").setAttribute("aria-pressed", "false");
    setReactor("idle");
    return;
  }

  const total = rec.chunks.reduce((n, c) => n + c.length, 0);
  if (total < rec.rate * 0.4) {
    setReactor("idle");
    hint("That was too short — hold the question a moment longer.");
    return;
  }

  const samples = new Float32Array(total);
  let at = 0;
  for (const chunk of rec.chunks) { samples.set(chunk, at); at += chunk.length; }

  setReactor("thinking", "transcribing");
  hint("Transcribing…");
  let heard;
  try {
    heard = await fetch("/api/listen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio: toBase64(encodeWav(samples, rec.rate)) }),
    }).then((r) => r.json());
  } catch (err) {
    setReactor("idle");
    alert("crit", "Offline", `The JARVIS server is not answering. ${err}`);
    return;
  }

  if (heard.error) {
    setReactor("idle");
    hint(heard.error);
    alert("warn", "Microphone", heard.error);
    return;
  }

  input.value = heard.text;

  // A typed question could have been sent while we were transcribing, and
  // think() refuses silently when one is already running. Say so, rather than
  // leaving the reactor reading "transcribing" until the other answer lands
  // and gets mistaken for a reply to this one.
  if (thinking) {
    setReactor("idle");
    hint(`Heard "${heard.text}" — a question was already running, so it was not sent. `
       + `It is in the box; press Enter when the other one finishes.`);
    return;
  }
  think("ask", { q: heard.text }, heard.text);
}

// ── reindexar ─────────────────────────────────────────────────────────────
//
// /api/reindex has existed since stage 1 and nothing on the page ever called
// it, so changing which folders JARVIS reads meant restarting the server. It
// re-reads .env first, which is the whole point: edit JARVIS_VAULTS, press
// this, and the graph is your folders — no terminal.

async function reindex() {
  if (reindex.busy) return;
  reindex.busy = true;
  const btn = $("btn-reindex");
  const was = btn.textContent;
  btn.textContent = "lendo…";
  btn.disabled = true;

  let res;
  try {
    res = await fetch("/api/reindex", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }).then((r) => r.json());
  } catch (err) {
    alert("crit", "Offline", `O servidor não respondeu. ${err}`);
  }
  btn.textContent = was;
  btn.disabled = false;
  reindex.busy = false;
  if (!res) return;

  if (res.error) { alert("warn", "Reindexar", res.error); return; }

  // Everything downstream reads from the payload, so pull it fresh rather
  // than patching counts by hand and letting the two drift.
  await boot();
  hint(`${res.notes} notas lidas em ${res.seconds}s.`);
}

$("btn-reindex").addEventListener("click", reindex);

$("btn-mic").addEventListener("click", () => {
  if (VOICE.recording) stopListening(); else startListening(false);
});

$("btn-wake").addEventListener("click", () => {
  const live = VOICE.recording;
  if (live?.always) { stopListening(); return; }   // off
  // A push-to-talk recording is in progress: hand that question in — it was
  // deliberately recorded and dropping it silently would be worse — and then
  // switch on. Pressing "Sempre" has to end with always-on actually on.
  if (live) stopListening();
  startListening(true);
});

// ── memory ────────────────────────────────────────────────────────────────
//
// JARVIS writes these itself, after each question, deciding what was worth
// keeping. That is only acceptable if you can see everything it decided and
// throw any of it away — so this panel is not a nicety, it is the other half
// of letting it write at all.

// ── olhos ─────────────────────────────────────────────────────────────────
//
// Paste a screenshot, or drag a photo onto the page, and it goes with your
// question. A supplier's quote that arrived as a WhatsApp photograph, a bank
// statement someone screenshotted, a scanned invoice the text extractor could
// make nothing of — all of it was invisible until now.
//
// Scaled down here, before it is sent, and that is not only about bandwidth: a
// 4000-pixel phone photo costs many times the tokens of a 1568-pixel one and
// reads no better. The long edge is capped at what the model actually uses.

const IMAGE_MAX_EDGE = 1568;      // beyond this the model gains nothing
const IMAGE_MAX_COUNT = 4;
const IMAGE_QUALITY = 0.85;

/** A File or Blob, scaled and re-encoded. Returns {media_type, data, url}. */
async function prepareImage(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, IMAGE_MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();

  // JPEG for photographs and screenshots alike. PNG of a screenshot is often
  // smaller, but re-encoding to one type keeps the server's allowlist short
  // and the size predictable.
  const url = canvas.toDataURL("image/jpeg", IMAGE_QUALITY);
  return {
    media_type: "image/jpeg",
    data: url.slice(url.indexOf(",") + 1),
    url,
    label: file.name || `imagem ${w}×${h}`,
  };
}

async function attachImages(files) {
  const pictures = [...files].filter((f) => f && f.type.startsWith("image/"));
  if (!pictures.length) return;

  const room = IMAGE_MAX_COUNT - state.images.length;
  if (room <= 0) {
    hint(`No máximo ${IMAGE_MAX_COUNT} imagens por pergunta.`);
    return;
  }
  for (const file of pictures.slice(0, room)) {
    try {
      state.images.push(await prepareImage(file));
    } catch (err) {
      alert("warn", "Imagem", `Não consegui ler ${file.name || "a imagem"}. ${err}`);
    }
  }
  if (pictures.length > room) {
    hint(`Anexei ${room}; o limite é ${IMAGE_MAX_COUNT} por pergunta.`);
  }
  renderAttachments();
}

function renderAttachments() {
  const strip = $("attachments");
  if (!strip) return;
  strip.replaceChildren();
  strip.hidden = !state.images.length;

  state.images.forEach((image, index) => {
    const wrap = document.createElement("span");
    wrap.className = "attachment";

    const thumb = document.createElement("img");
    thumb.src = image.url;
    thumb.alt = image.label;
    thumb.title = `${image.label} · ${(image.data.length * 3 / 4 / 1024).toFixed(0)} kB`;

    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "attachment-drop";
    drop.textContent = "×";
    drop.title = "tirar esta imagem";
    drop.addEventListener("click", () => {
      state.images.splice(index, 1);
      renderAttachments();
    });

    wrap.append(thumb, drop);
    strip.appendChild(wrap);
  });
}

// ── alterações no vault ───────────────────────────────────────────────────
//
// JARVIS can now change files you made — files it did not create and cannot
// recreate. Your own Evo-SI audit says there is no backup of anything, so the
// undo journal is not a nicety here, it is the backup.
//
// Which makes this panel load-bearing rather than decorative: a write you did
// not see happen is the only unacceptable kind. Everything that changed is
// listed, with its size before and after, and a button that puts it back.

async function renderEdits(payload) {
  const list = $("edit-list");
  if (!list) return;
  let data = payload;
  if (!data) {
    try {
      data = await fetch("/api/edit").then((r) => r.json());
    } catch {
      return;
    }
  }
  if (data.error) { alert("warn", "Alterações", data.error); return; }
  state.edit = data;

  const now = $("edit-now");
  if (now) {
    const live = (data.changes || []).filter((c) => !c.undone).length;
    now.textContent = live ? `${live}` : "nenhuma";
  }

  const modes = $("edit-modes");
  modes.replaceChildren();
  for (const m of data.modes || []) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "brain-row";
    btn.setAttribute("aria-pressed", String(m === data.mode));
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = m;
    const note = document.createElement("span");
    note.className = "brain-note";
    note.textContent = {
      manual: "propõe e espera você",
      auto: "escreve; apagar ainda pergunta",
      skip: "escreve; apagar ainda pergunta",
    }[m] || "";
    btn.append(name, note);
    btn.addEventListener("click", () => setEditMode(m));
    li.appendChild(btn);
    modes.appendChild(li);
  }

  list.replaceChildren();
  for (const change of (data.changes || []).slice(0, 20)) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "turn";

    const when = document.createElement("span");
    when.className = "fact-when";
    when.textContent = new Date(change.when * 1000).toLocaleString();

    const what = document.createElement("span");
    what.className = "turn-q";
    what.textContent = (change.path || "").split(/[\\/]/).pop();
    what.title = change.path;

    const meta = document.createElement("span");
    meta.className = "turn-meta";
    meta.textContent = change.undone
      ? "desfeito"
      : `${change.action} · ${change.size_before} → ${change.size_after} b`;

    row.append(when, what, meta);

    if (!change.undone) {
      const back = document.createElement("button");
      back.type = "button";
      back.className = "ghost fact-drop";
      back.textContent = "Desfazer";
      back.title = change.had_backup
        ? "restaura os bytes anteriores"
        : "o arquivo não existia antes — desfazer o remove";
      back.addEventListener("click", async () => {
        back.disabled = true;
        try {
          const out = await fetch("/api/undo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: change.id }),
          }).then((r) => r.json());
          if (out.error) { alert("warn", "Desfazer", out.error); back.disabled = false; return; }
          renderEdits(out);
          boot();                       // the index changed under us
        } catch (err) {
          alert("crit", "Offline", `${err}`);
          back.disabled = false;
        }
      });
      row.appendChild(back);
    }

    li.appendChild(row);
    list.appendChild(li);
  }

  const note = $("edit-note");
  if (note) {
    note.textContent = (data.changes || []).length
      ? `Cópias em ${data.undo_dir}. Nada é sobrescrito sem uma.`
      : `Pode escrever ${(data.writeable || []).join(", ")} dentro de `
        + `${(data.roots || []).join(", ") || "(nenhuma pasta)"}. Apagar sempre pergunta.`;
  }
}

async function setEditMode(mode) {
  try {
    const out = await fetch("/api/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "mode", mode }),
    }).then((r) => r.json());
    if (out.error) { alert("warn", "Alterações", out.error); return; }
    renderEdits(out);
  } catch (err) {
    alert("crit", "Offline", `${err}`);
  }
}

// ── navegador ─────────────────────────────────────────────────────────────
//
// This panel is the whole safety story now. Edson lifted "never send" and then
// "never spend", so nothing here is a gate — which makes *seeing* what the
// browser did the only thing standing between an unwanted action and never
// finding out about it. Hence the spend count in the header: not decoration,
// the one number you would want at a glance.

async function renderBrowse(payload) {
  const list = $("browse-list");
  if (!list) return;
  let data = payload;
  if (!data) {
    try {
      data = await fetch("/api/browse").then((r) => r.json());
    } catch {
      return;
    }
  }
  if (data.error) { alert("warn", "Navegador", data.error); return; }
  state.browse = data;

  const now = $("browse-now");
  if (now) {
    now.textContent = !data.available ? "indisponível"
      : data.spent ? `${data.spent} gasto${data.spent > 1 ? "s" : ""}`
      : data.open ? "aberto" : "fechado";
  }

  list.replaceChildren();
  for (const act of (data.recent || []).slice().reverse()) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "turn";

    const when = document.createElement("span");
    when.className = "fact-when";
    when.textContent = new Date(act.when * 1000).toLocaleTimeString();

    const what = document.createElement("span");
    what.className = "turn-q";
    what.textContent = `${act.what} ${act.target}`.slice(0, 60);
    what.title = act.url || act.target;

    const meta = document.createElement("span");
    meta.className = "turn-meta";
    // The class is the point. `spend` is spelled out in full so it cannot be
    // skimmed past; the others stay quiet.
    meta.textContent = act.ok
      ? (act.kind === "spend" ? "GASTO" : act.kind)
      : `falhou · ${act.detail || ""}`.slice(0, 40);
    if (act.kind === "spend") meta.style.color = "var(--t-client)";

    row.append(when, what, meta);
    li.appendChild(row);
    list.appendChild(li);
  }

  const note = $("browse-note");
  if (note) {
    note.textContent = !data.available
      ? data.reason
      : `Perfil em ${data.profile}. Ler é livre, enviar e gastar estão `
        + `liberados e ficam no diário. Senha você digita na janela — o JARVIS `
        + `não tem as suas.`;
  }
}

// ── habilidades ───────────────────────────────────────────────────────────
//
// The vault holds what is true; a skill holds how you work. That an invoice is
// R$ 6.226,95 belongs in a note — that you always check the borderô before
// chasing a supplier is not in any document, and until now had to be retyped
// into every question.
//
// The panel exists mostly to show failures. A skill file with no `description`
// never matches anything, and without this you would believe an instruction
// was in effect when it was not.

async function renderSkills(payload) {
  const list = $("skill-list");
  if (!list) return;
  let data = payload;
  if (!data) {
    try {
      data = await fetch("/api/skills").then((r) => r.json());
    } catch {
      return;                          // the panel simply stays as it was
    }
  }
  if (data.error) { alert("warn", "Habilidades", data.error); return; }
  state.skills = data;

  const now = $("skill-now");
  if (now) now.textContent = data.skills.length ? `${data.skills.length}` : "nenhuma";

  list.replaceChildren();
  for (const skill of data.skills) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "brain-row";
    row.setAttribute("aria-pressed", String(!!skill.always));

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = skill.name;

    const note = document.createElement("span");
    note.className = "brain-note";
    note.textContent = skill.problem
      ? "⚠ " + skill.problem
      : (skill.always ? "sempre · " : "") + (skill.description || "").slice(0, 60);
    row.title = skill.path;

    row.append(name, note);
    li.appendChild(row);
    list.appendChild(li);
  }

  const note = $("skill-note");
  if (note) {
    const ins = data.instructions || {};
    note.textContent = ins.sources?.length
      ? `${ins.file} em ${ins.sources.length} lugar(es), ${ins.chars} caracteres, em toda resposta.`
      : `Nenhum ${ins.file || "JARVIS.md"}. Crie um na raiz do projeto para instruções permanentes.`;
  }
}

// ── histórico ─────────────────────────────────────────────────────────────
//
// Until this existed every question was an isolated call and the answer was
// gone the moment it left the screen. Two things come out of keeping them.
//
// One: you can look up what you asked last week and compare. Two, and bigger:
// a question can refer to the previous one. That is the difference between a
// search box and a working session.
//
// It is also the most personal thing JARVIS stores — an answer about your
// accounts payable quotes your accounts payable — so, like the memory panel,
// every turn is visible and every turn can be thrown away.

function showThread() {
  const bar = $("thread-bar");
  if (!bar) return;
  bar.hidden = !state.thread;
  const label = $("thread-label");
  if (label) label.textContent = state.thread ? "conversa em andamento" : "";
}

function newThread() {
  state.thread = "";
  showThread();
  hint("Conversa nova — a próxima pergunta começa do zero.");
}

async function showHistory(query = "") {
  let res;
  try {
    res = await fetch(`/api/history?limit=60&q=${encodeURIComponent(query)}`)
      .then((r) => r.json());
  } catch (err) {
    alert("crit", "Offline", `O servidor não respondeu. ${err}`);
    return;
  }
  if (res.error) { alert("warn", "Histórico", res.error); return; }

  const box = $("results");
  box.replaceChildren();

  const head = document.createElement("div");
  head.className = "answer-head";
  const label = document.createElement("span");
  label.className = "eyebrow";
  label.textContent = "histórico";
  const meta = document.createElement("span");
  meta.className = "answer-meta";
  meta.textContent = `${res.turns.length} turnos · ${res.threads.length} conversas · ${res.where}`;
  head.append(label, meta);
  box.appendChild(head);

  const search = document.createElement("input");
  search.type = "search";
  search.className = "history-search";
  search.placeholder = "buscar no que você já perguntou…";
  search.value = query;
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") showHistory(search.value);
  });
  box.appendChild(search);

  if (!res.turns.length) {
    const empty = document.createElement("div");
    empty.className = "result snip";
    empty.textContent = query
      ? `Nada encontrado para "${query}".`
      : "Nada ainda. Isto se enche conforme você pergunta.";
    box.appendChild(empty);
    box.hidden = false;
    return;
  }

  for (const turn of res.turns) {
    const row = document.createElement("div");
    row.className = "turn";

    const when = document.createElement("span");
    when.className = "fact-when";
    when.textContent = new Date(turn.when * 1000).toLocaleString();

    const q = document.createElement("button");
    q.type = "button";
    q.className = "turn-q";
    q.textContent = turn.question || `(${turn.kind})`;
    q.title = "reabrir esta resposta";
    q.addEventListener("click", () => {
      renderAnswer(turn);
      // Reopening a turn puts you back in its conversation, so the next
      // question continues from there rather than starting over.
      state.thread = turn.thread;
      showThread();
    });

    const meta2 = document.createElement("span");
    meta2.className = "turn-meta";
    meta2.textContent = `${turn.citations.length} citações`
      + (turn.usage?.output_tokens ? ` · ${turn.usage.output_tokens} tokens` : "")
      + (turn.model ? ` · ${turn.model}` : "");

    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "ghost fact-drop";
    drop.textContent = "Apagar";
    drop.title = "apagar este turno do histórico";
    drop.addEventListener("click", async () => {
      drop.disabled = true;
      try {
        const out = await fetch("/api/history/forget", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: turn.id }),
        }).then((r) => r.json());
        if (out.error) { alert("warn", "Histórico", out.error); drop.disabled = false; return; }
        showHistory(query);
      } catch (err) {
        alert("crit", "Offline", `${err}`);
        drop.disabled = false;
      }
    });

    row.append(when, q, meta2, drop);
    box.appendChild(row);
  }
  box.hidden = false;
}

async function showMemory() {
  let res;
  try {
    res = await fetch("/api/memory").then((r) => r.json());
  } catch (err) {
    alert("crit", "Offline", `The JARVIS server is not answering. ${err}`);
    return;
  }

  const box = $("results");
  box.replaceChildren();

  const head = document.createElement("div");
  head.className = "answer-head";
  const label = document.createElement("span");
  label.className = "eyebrow";
  label.textContent = "remembered";
  const meta = document.createElement("span");
  meta.className = "answer-meta";
  meta.textContent = `${res.facts.length} of ${res.limit} · ${res.where}`;
  head.append(label, meta);
  box.appendChild(head);

  if (!res.facts.length) {
    const empty = document.createElement("div");
    empty.className = "result snip";
    empty.textContent = "Nothing yet. This fills as you ask things.";
    box.appendChild(empty);
    box.hidden = false;
    return;
  }

  for (const fact of res.facts) {
    const row = document.createElement("div");
    row.className = "fact";

    const when = document.createElement("span");
    when.className = "fact-when";
    when.textContent = new Date(fact.recorded * 1000).toISOString().slice(0, 10);

    const text = document.createElement("span");
    text.className = "fact-text";
    text.textContent = fact.text;

    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "ghost fact-drop";
    drop.textContent = "Forget";
    drop.title = `Delete ${fact.name}.md`;
    drop.addEventListener("click", async () => {
      drop.disabled = true;
      try {
        const out = await fetch("/api/forget", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: fact.name }),
        }).then((r) => r.json());
        if (out.error) { alert("warn", "Memory", out.error); drop.disabled = false; return; }
        showMemory();
      } catch (err) {
        alert("crit", "Offline", `${err}`);
        drop.disabled = false;
      }
    });

    row.append(when, text, drop);
    box.appendChild(row);
  }
  box.hidden = false;
}

$("btn-memory").addEventListener("click", showMemory);
$("btn-history").addEventListener("click", () => showHistory());

// Three ways in, because the picture arrives three ways: pasted from a
// screenshot tool, dragged from a folder, or picked from a phone's downloads.
$("btn-image").addEventListener("click", () => $("image-input").click());
$("image-input").addEventListener("change", (e) => {
  attachImages(e.target.files);
  e.target.value = "";            // so the same file can be picked twice
});

window.addEventListener("paste", (e) => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.some((f) => f.type.startsWith("image/"))) {
    e.preventDefault();
    attachImages(files);
  }
});

// Dropping anywhere on the page, not only on the bar — a target you have to
// aim at is a target you miss.
window.addEventListener("dragover", (e) => {
  if ([...(e.dataTransfer?.types || [])].includes("Files")) {
    e.preventDefault();
    document.body.classList.add("dropping");
  }
});
window.addEventListener("dragleave", (e) => {
  if (!e.relatedTarget) document.body.classList.remove("dropping");
});
window.addEventListener("drop", (e) => {
  if (!e.dataTransfer?.files?.length) return;
  e.preventDefault();
  document.body.classList.remove("dropping");
  attachImages(e.dataTransfer.files);
});
$("btn-new-thread").addEventListener("click", newThread);

$("btn-mute").addEventListener("click", () => {
  VOICE.mute = !VOICE.mute;
  $("btn-mute").setAttribute("aria-pressed", String(VOICE.mute));
  $("btn-mute").textContent = VOICE.mute ? "Unmute" : "Mute";
  if (VOICE.mute) stopSpeaking();
});

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
