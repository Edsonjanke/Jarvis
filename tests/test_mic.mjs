/* The two defects the adversarial review confirmed, pinned.
 *
 * ui/app.js cannot run here — there is no browser — so the voice functions are
 * extracted from the real file and run against fake Web Audio objects. That is
 * enough to reproduce both bugs, and both failed before the fix.
 */
import { readFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

const SRC = readFileSync(new URL("../ui/app.js", import.meta.url), "utf8");

// ── fakes ────────────────────────────────────────────────────────────────
let liveTracks = 0;
let openContexts = 0;
const log = [];

class FakeTrack { stop() { liveTracks--; this.stopped = true; } }
class FakeStream {
  constructor() { this.tracks = [new FakeTrack()]; liveTracks++; }
  getTracks() { return this.tracks; }
}
class FakeNode {
  constructor() { this.onaudioprocess = null; }
  connect() {} disconnect() {}
}
class FakeContext {
  constructor(opts) { this.sampleRate = opts?.sampleRate ?? 48000; openContexts++; }
  createMediaStreamSource() { return new FakeNode(); }
  createScriptProcessor() { return new FakeNode(); }
  close() { openContexts--; return Promise.resolve(); }
}

let permissionDelay = 300;
const globalsForVoice = {
  navigator: { mediaDevices: { getUserMedia: () => new Promise((res) => setTimeout(() => res(new FakeStream()), permissionDelay)) } },
  window: { AudioContext: FakeContext, speechSynthesis: null },
  AudioContext: FakeContext,
  state: { level: 0, reactor: "idle" },
  setReactor: (s) => { globalsForVoice.state.reactor = s; },
  hint: (t) => log.push(["hint", t]),
  alert: (lvl, label, msg) => log.push(["alert", `${label}: ${msg}`]),
  stopSpeaking: () => {},
  $: () => ({ setAttribute() {}, textContent: "" }),
  fetch: async () => ({ json: async () => ({ text: "uma pergunta" }) }),
  think: (...a) => log.push(["think", a[1]?.q]),
  input: { value: "" },
};

// ── extract the real functions ───────────────────────────────────────────
function grab(name) {
  const re = new RegExp(`(?:async )?function ${name}\\s*\\(`);
  const at = SRC.search(re);
  if (at === -1) throw new Error(`${name} not found in app.js`);
  let i = SRC.indexOf("{", at), depth = 0;
  for (let j = i; j < SRC.length; j++) {
    if (SRC[j] === "{") depth++;
    else if (SRC[j] === "}" && --depth === 0) return SRC.slice(at, j + 1);
  }
  throw new Error(`${name} not closed`);
}

const VOICE_DECL = SRC.slice(SRC.indexOf("const VOICE = {"), SRC.indexOf("};", SRC.indexOf("const VOICE = {")) + 2);
const body = [
  // `thinking` must be a live binding the harness can flip between calls, not
  // a value copied in at construction time.
  "let thinking = false;",
  VOICE_DECL,
  grab("releaseChain"),
  grab("startListening"),
  grab("stopListening"),
  grab("encodeWav"),
  grab("toBase64"),
  grab("fold"),
  grab("afterWakeWord"),
  grab("detectSpeech"),
  grab("freshVad"),
  grab("sendSegment"),
  "return { VOICE, startListening, stopListening, releaseChain, encodeWav,"
  + " fold, afterWakeWord, detectSpeech, freshVad,"
  + " setThinking: (v) => { thinking = v; } };",
].join("\n\n");

const names = Object.keys(globalsForVoice);
const make = new Function(...names, "btoa", body);
const V = make(...names.map((n) => globalsForVoice[n]), (s) => Buffer.from(s, "binary").toString("base64"));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
function check(label, ok, detail = "") {
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${label}${detail ? "  " + detail : ""}`);
  if (!ok) failures++;
}

// ── 1. double click during the permission prompt ─────────────────────────
console.log("\n1. two clicks while getUserMedia is still pending");
liveTracks = 0; openContexts = 0;
V.startListening();
await sleep(50);
V.startListening();          // the second click, before the first resolved
await sleep(500);

check("only one capture chain exists", liveTracks === 1 && openContexts === 1,
      `tracks=${liveTracks} contexts=${openContexts}`);

await V.stopListening();
await sleep(50);
check("stopping releases the microphone", liveTracks === 0, `tracks=${liveTracks}`);
check("and closes the audio context", openContexts === 0, `contexts=${openContexts}`);

// ── 2. an orphan can never kill a later recording ────────────────────────
console.log("\n2. an orphaned chain buries itself instead of the live one");
liveTracks = 0; openContexts = 0;
await V.startListening();
await sleep(50);
const orphan = V.VOICE.recording;
V.VOICE.recording = null;             // simulate an orphan by any means
await V.startListening();
await sleep(50);
const live = V.VOICE.recording;
check("a new recording started", !!live && live !== orphan);

// the orphan gets one more audio block
orphan.node.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096), length: 4096 } });
check("the orphan released itself", orphan.done === true);
check("the live recording survived", V.VOICE.recording === live);
await V.stopListening();
await sleep(50);
check("no microphone left open", liveTracks === 0, `tracks=${liveTracks}`);

// ── 3. the mic is refused while a question is running ────────────────────
console.log("\n3. the mic while a question is already in flight");
liveTracks = 0; openContexts = 0;
log.length = 0;
V.setThinking(true);
await V.startListening();
await sleep(400);
check("no microphone was opened", liveTracks === 0, `tracks=${liveTracks}`);
check("and the user was told why", log.some(([k, t]) => k === "hint" && /Finish the current/.test(t)),
      JSON.stringify(log[0] || null));
V.setThinking(false);

// ── 4. the WAV encoder produces a real WAV ───────────────────────────────
console.log("\n4. the WAV bytes");
const samples = new Float32Array(16000);
for (let i = 0; i < samples.length; i++) samples[i] = Math.sin((2 * Math.PI * 440 * i) / 16000) * 0.8;
const wav = V.encodeWav(samples, 16000);
const dv = new DataView(wav.buffer);
const tag = (at) => String.fromCharCode(...wav.subarray(at, at + 4));
check("RIFF header", tag(0) === "RIFF", tag(0));
check("WAVE format", tag(8) === "WAVE", tag(8));
check("fmt chunk", tag(12) === "fmt ", tag(12));
check("data chunk", tag(36) === "data", tag(36));
check("PCM", dv.getUint16(20, true) === 1);
check("mono", dv.getUint16(22, true) === 1);
check("16 kHz", dv.getUint32(24, true) === 16000);
check("byte rate = rate*2", dv.getUint32(28, true) === 32000);
check("block align 2", dv.getUint16(32, true) === 2);
check("16 bits", dv.getUint16(34, true) === 16);
check("data length", dv.getUint32(40, true) === samples.length * 2);
check("file size field", dv.getUint32(4, true) === 36 + samples.length * 2);
check("total bytes", wav.length === 44 + samples.length * 2, String(wav.length));
// the sine should swing near full scale in both directions
let min = 0, max = 0;
for (let i = 0; i < samples.length; i++) {
  const v = dv.getInt16(44 + i * 2, true);
  min = Math.min(min, v); max = Math.max(max, v);
}
check("signal is present and signed", min < -20000 && max > 20000, `${min}..${max}`);

const outPath = join(tmpdir(), "jarvis-from_js.wav");
const { writeFileSync } = await import("fs");
writeFileSync(outPath, wav);
console.log(`  wrote ${outPath} for the Python wave module to verify`);

// ── always-on: the detector ──────────────────────────────────────────────
//
// The whole promise of "Sempre" is that silence never leaves the machine.
// That promise is this function, so it is fed real blocks of real audio.

console.log("\nsempre-ligado: quem decide o que sobe");
const RATE = 16000, BLOCK = 4096, BLOCK_MS = (BLOCK / RATE) * 1000;

function noise(level = 0.002) {
  const b = new Float32Array(BLOCK);
  for (let i = 0; i < BLOCK; i++) b[i] = (Math.random() * 2 - 1) * level;
  return b;
}
function speech(level = 0.25) {
  const b = new Float32Array(BLOCK);
  for (let i = 0; i < BLOCK; i++) b[i] = Math.sin((2 * Math.PI * 180 * i) / RATE) * level;
  return b;
}
/** Feed a script of blocks; return every segment the detector emitted. */
function run(script) {
  const vad = V.freshVad();
  const out = [];
  for (const block of script) {
    const seg = V.detectSpeech(vad, block, RATE);
    if (seg) out.push(seg);
  }
  return out;
}
const times = (n, f) => Array.from({ length: n }, f);
const CAL = Math.ceil(V.VOICE.calibrateMs / BLOCK_MS) + 1;

// silence alone
check("silêncio não gera segmento nenhum",
  run(times(CAL + 60, () => noise())).length === 0);

// one utterance, then a pause
let segs = run([
  ...times(CAL, () => noise()),
  ...times(8, () => speech()),          // ~2s of speech
  ...times(6, () => noise()),           // ~1.5s of silence > hangover
]);
check("fala seguida de pausa gera exatamente um segmento", segs.length === 1, String(segs.length));
check("o segmento tem áudio suficiente pra transcrever",
  segs[0] && segs[0].length * BLOCK / RATE > 1.5, segs[0] ? `${(segs[0].length*BLOCK/RATE).toFixed(2)}s` : "—");
check("o segmento inclui o pre-roll (não começa no meio da palavra)",
  segs[0].length > 8, `${segs[0].length} blocos para 8 de fala`);

// a pause between words must not split the sentence
segs = run([
  ...times(CAL, () => noise()),
  ...times(5, () => speech()),
  ...times(2, () => noise()),           // ~0.5s — shorter than the hangover
  ...times(5, () => speech()),
  ...times(6, () => noise()),
]);
check("pausa curta entre palavras não parte a frase em duas",
  segs.length === 1, `${segs.length} segmentos`);

// a door, a cough, a chair
segs = run([...times(CAL, () => noise()), speech(), ...times(6, () => noise())]);
check("estalo curto é descartado, não vira upload", segs.length === 0, `${segs.length}`);

// a noisy room must not be permanently "talking"
check("sala barulhenta não fica falando sozinha",
  run(times(CAL + 60, () => noise(0.02))).length === 0);

// a long monologue must be cut, not buffered forever
segs = run([...times(CAL, () => noise()), ...times(200, () => speech())]);
check("fala muito longa é cortada no teto, não cresce sem limite",
  segs.length >= 1 && segs[0].length * BLOCK / RATE <= V.VOICE.maxSeconds + 1,
  segs[0] ? `${(segs[0].length*BLOCK/RATE).toFixed(1)}s` : "—");

// ── always-on: the wake word ─────────────────────────────────────────────
console.log("\nsempre-ligado: a palavra que decide se vira pergunta");

check("sem a palavra, o transcrito é descartado",
  V.afterWakeWord("qual é a política de depósito?") === null);
check("com a palavra, sobra a pergunta",
  V.afterWakeWord("Jarvis, qual é a política de depósito?") === "qual é a política de depósito?",
  JSON.stringify(V.afterWakeWord("Jarvis, qual é a política de depósito?")));
check("acento na palavra não impede (Járvis)",
  V.afterWakeWord("Járvis, quanto está em atraso?") === "quanto está em atraso?");
check("maiúscula não importa",
  V.afterWakeWord("JARVIS me diga as faturas") === "me diga as faturas");
check("o que veio antes da palavra é jogado fora",
  V.afterWakeWord("então eu disse pra ele, jarvis: qual é o total?") === "qual é o total?",
  JSON.stringify(V.afterWakeWord("então eu disse pra ele, jarvis: qual é o total?")));
check("só o nome, sem pergunta, devolve vazio (não null)",
  V.afterWakeWord("jarvis?") === "");
check("a pergunta devolvida mantém os acentos",
  V.afterWakeWord("jarvis, política de depósito é qual?").includes("política"));

// fold has to be length-preserving, or the slice above lands in the wrong place
console.log("\nsempre-ligado: a dobra de acentos preserva o comprimento");
for (const s of ["depósito", "Járvis", "não", "AÇÃO", "abc", "Ünïcödé", "日本語"]) {
  check(`"${s}" mantém o comprimento`, V.fold(s).length === s.length,
    `${s.length} -> ${V.fold(s).length}`);
}
check("acentos realmente caem", V.fold("Depósito Não") === "deposito nao", V.fold("Depósito Não"));

console.log();
if (failures) { console.log(`${failures} FAILED`); process.exit(1); }
console.log("OK — reentry, orphan safety, in-flight refusal, a valid WAV, "
  + "and only speech addressed to JARVIS ever leaves the machine.");
