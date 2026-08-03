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
  renderBrains();
  renderTools();
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
    ["speak", window.speechSynthesis ? "this machine" : "missing"],
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
  meta.textContent = `${res.usage?.model || "model"} · read ${res.considered.length} notes`
                   + `${recalled} · ${res.seconds}s`;
  meta.title = res.recalled?.length ? res.recalled.join("\n") : "";
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
};

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

function speak(text) {
  if (VOICE.mute || !window.speechSynthesis || !text) return;
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(
    // Citation ids are for the eye, not the ear: "demo/notes/deposit-policy.md"
    // read aloud is unbearable. The chips below the answer carry them.
    text.replace(/\[[^\]\n]{3,120}\]/g, "").replace(/[*_#`]/g, "").replace(/\s+/g, " ").trim()
  );
  const voice = speechVoice();
  if (voice) { utterance.voice = voice; utterance.lang = voice.lang; }

  utterance.onstart = () => { state.level = 0.5; setReactor("speaking", voice?.name || ""); };
  utterance.onend = utterance.onerror = () => { state.level = 0; setReactor("idle"); };
  window.speechSynthesis.speak(utterance);
}

function stopSpeaking() {
  window.speechSynthesis?.cancel();
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

async function startListening() {
  // Synchronously, before any await. getUserMedia takes seconds the first time
  // while the permission prompt is up, and the button gives no feedback until
  // it resolves — so without this a second click builds a second capture chain
  // and the first becomes unreachable, its microphone never released.
  if (VOICE.recording || VOICE.starting) return;
  if (thinking) {
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
                  chunks: [], frames: 0, done: false };

    node.onaudioprocess = (event) => {
      if (rec.done) return;
      // If this chain is no longer the live one it is an orphan: let it bury
      // itself rather than keep a microphone open and a buffer growing.
      if (VOICE.recording !== rec) { releaseChain(rec); return; }

      const block = new Float32Array(event.inputBuffer.getChannelData(0));
      rec.chunks.push(block);
      rec.frames += block.length;

      let peak = 0;
      for (const v of block) peak = Math.max(peak, Math.abs(v));
      state.level = Math.min(1, peak * 3);

      if (rec.frames > VOICE.sampleRate * VOICE.maxSeconds) stopListening();
    };

    source.connect(node);
    node.connect(ctx.destination);
    VOICE.recording = rec;
    $("btn-mic").setAttribute("aria-pressed", "true");
    setReactor("listening", "click Mic again when done");
  } catch (err) {
    // Anything at all going wrong after the microphone opened must still hand
    // it back — the failure paths are exactly where a hot mic gets forgotten.
    stream?.getTracks().forEach((t) => t.stop());
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

$("btn-mic").addEventListener("click", () => {
  if (VOICE.recording) stopListening(); else startListening();
});

// ── memory ────────────────────────────────────────────────────────────────
//
// JARVIS writes these itself, after each question, deciding what was worth
// keeping. That is only acceptable if you can see everything it decided and
// throw any of it away — so this panel is not a nicety, it is the other half
// of letting it write at all.

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
