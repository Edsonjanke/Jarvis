# Handoff: JARVIS console — v2

> This file is the implementation spec. It is written to be self-sufficient — a developer who
> was not in the conversation should be able to build the console from this document plus the
> stylesheet. Where it gives a number, that number is the source's, not a rounded approximation.

## Overview

JARVIS is a local-first assistant that indexes one person's own folders into a graph of typed
notes and answers questions **only** out of what it read, citing the note ids it used. The
operator is Edson, at EVO Soluções Industriais. It runs on localhost; the model key never
leaves the process.

v2 rebuilds the single-screen console as an instrument HUD: two rails of machine readouts
around a reactor lying in perspective, a full-bleed knowledge graph behind everything, and one
ask bar. It replaces v1 (blue accent, three floating translucent plates).

## About the design files

**The files in this bundle are design references written in HTML/JSX — prototypes of the
intended look and behaviour, not production code to copy in.** They run in the browser off
`unpkg` React + in-browser Babel, with fake data and `setTimeout` where the real product calls a
model. The job is to **recreate these designs in the target codebase's own environment** using
its established patterns. The real JARVIS is vanilla JS (`ui/index.html`, `ui/app.js`,
`ui/graph.js`, `ui/styles.css`) driving a Python agent (`agent/main.py`, `agent/brain.py`) — if
you are implementing there, port the CSS custom properties in `tokens/` verbatim and rewrite the
JSX as the plain DOM code that file already uses. If you are starting a new frontend, pick the
framework that fits and treat the JSX as the component contract.

**`styles.css` and everything under `tokens/` ARE production-ready** and should be adopted as-is.
They are the single source of truth for every value below.

## Fidelity

**High-fidelity.** Colours, type sizes (half-pixels included), spacing, motion durations and
state rules are final and come from the source's own `ui/styles.css`. Recreate them exactly.
Do not round values to a 4/8-px grid — if this document says 3px, it is 3px.

---

## Screens / views

There is one screen. It never scrolls; `html, body` are `overflow: hidden` and scrolling happens
inside a rail or a plate. Everything is `position: fixed`.

### 1. The field — `[data-hud-field]` on `<body>`

**Purpose:** the surface everything sits on.

- Background `--void #050908`, flat.
- `::before` paints, in one shorthand: a 46px grid (`--hud-grid`, 3.5% accent, 1px lines both
  axes) and `--hud-vignette`, a radial bloom `120% 90% at 50% 46%` running 5.5% → 1.8% → 0.
- `::after` paints the scanline: `repeating-linear-gradient(180deg, --hud-scan 0 1px, transparent 1px 3px)`.
- Both are `pointer-events: none` and carry no z-index.

### 2. Graph stage — `GraphStage.jsx`

**Purpose:** the vault, drawn as a force-directed graph; the only real imagery in the product.

- Full-bleed `<canvas position:fixed inset:0>`, transparent (`getContext("2d", {alpha:true})`,
  `clearRect` per frame), rendered at `opacity: 0.68` so the rails read over it.
- Insets so the graph never settles under a plate: `{left: 300, right: 300, top: 130, bottom: 150}`.
- Forces (all from `ui/graph.js`): repulsion 2000, cutoff 240, spring length 58, k 0.036,
  gravity 0.0105, damping 0.83, alpha decay 0.014, resting breath 0.0065 with an 11s global sway.
  450 pre-settle ticks before the first paint, then a 33ms interval (not rAF — rAF stops dead
  when the frame is off-screen).
- **Node radius** `clamp(3.4 + √degree × 2.35, 3.4, 17)`.
- **Node rendering (v2's "lit sphere"):** drawn in two passes.
  1. `globalCompositeOperation = "lighter"`: a halo, `createRadialGradient(x, y, r*0.5, x, y, r*2.1)`
     at 20% → 6% → 0 of the node's own colour (`r*3.0` and the same stops when hovered).
     Nodes with `r > 11` (and any hovered/focused node) also get a four-point flare: a horizontal
     and a vertical line of length `r*3.2` (`r*4.2` hovered), `lineWidth max(0.5, r*0.10) / scale`,
     drawn with a linear gradient 0 → 18% → 0.
  2. `source-over`: the body, `createRadialGradient(x - r*0.34, y - r*0.38, r*0.08, x, y, r)`
     running `mix(colour, white, 0.78)` → `mix(colour, white, 0.16)` at 0.38 → `mix(colour, black, 0.34)`.
     The offset highlight is what makes it read as a sphere.
- **Edges** 1px at `rgba(--accent-rgb, 0.14)`. A traced path is `0.95` at 1.6px; an edge touching
  the hovered node is `0.40`. Everything unrelated to a spotlight drops to `alpha 0.10`.
- **Pulse:** every 3.4s a dot walks a random edge over 1.5s, `rgba(accent, 0.5·sin(πt))`, radius 1.9/scale.
- **Labels:** 11px mono on a `--plate` background, placed in the first free slot of eight around
  the node, dropped on collision. In v2 the console passes `sparseLabels`, which suppresses every
  label except hovered / focused / on-path — the reactor owns the centre of the screen.
- **Interaction:** drag a node (it pins while held), drag the background to pan, wheel to zoom
  (0.15–6×), click to select, shift-click a second node to trace the shortest path (BFS).

### 3. Left rail — `RailLeft.jsx`

`position: fixed; left/top/bottom: var(--rail-gutter) (16px); width: var(--rail-w) (286px)`,
`display: flex; flex-direction: column; gap: var(--rail-gap) (14px)`, scrolls internally.
Five `HudFrame` sections, top to bottom:

| Section | Content |
| --- | --- |
| `STATUS DO SISTEMA` (right: `local`) | Four `Meter` rows — CPU, RAM, GPU, Disco. Values drift ±3.5 every 2.4s; `tone="warn"` above 88. |
| `NÚCLEO DE IA` | Four key/value rows (modelo, modo, raciocínio, resposta) + a full-width outlined `trocar cérebro` toggle that reveals three `BrainRow`s. |
| `BANCO DE MEMÓRIA` | One `RadialGauge` at 62% with a three-row `StatList` beside it. |
| `REDE` | `StatList` — nós do vault, vínculos, entrada, saída. Counts derive from the vault, never hardcoded. |
| `FEED AO VIVO` (`foot`) | Five rows: time · event · tail. Tail is `--warn` for a refusal, `--accent` for a write, `--ink-3` otherwise. Rows take the `--wash` hover. |

### 4. Centre stage — `CenterStage.jsx`

`position: fixed; top/bottom: 0; left/right: calc(var(--rail-w) + var(--rail-gutter)*2)`,
column flex, `pointer-events: none` on the wrapper (children re-enable it).

- **Greeting**, 58px from the top: a 26×26 outlined square holding a 9×9 accent block with
  `--hud-glow`, then `BOA NOITE, EDSON` at 19px `--accent` with `--hud-glow-soft`, and under it
  `Pergunte qualquer coisa sobre o que está no vault.` at 12.5px in the **proportional** face.
  The greeting switches on the hour: madrugada < 5, dia < 12, tarde < 18, noite.
- **Reactor**, `flex: 1` centred. Its size is **measured, never fixed**:
  `min(420, stage.clientWidth - 24, stage.clientHeight - 8)`, recomputed in a
  `useLayoutEffect` with no dependency array (the answer panel steals height without firing a
  window resize) plus a `ResizeObserver`. Four corner readouts — Índice / Cobertura / Vínculos /
  Varredura — sit at `19%` from the top and bottom edges and are **dropped entirely below 260px**
  rather than clipped. Stage is `overflow: hidden`.
- **Answer panel**, above the ask bar when an answer exists: a plate (see Overlays), `max-height: 34vh`.
- **Result list**, above the ask bar while the query is ≥ 2 chars and no answer is open: same
  plate, `max-height: 30vh`, up to six `ResultRow`s.
- **Status line:** a 5px dot + `SISTEMAS OPERACIONAIS` (`--good`) or `PENSANDO…` (`--accent`),
  10px, `letter-spacing: 0.16em`, uppercase.
- **Ask bar:** 46px tall, `--surface-raised` + `--blur-panel`, 1px hairline that crossfades to
  `--accent-line` over 140ms on focus-within, `border-radius: 3px`. Left: a 14px `mic` glyph in
  `--ink-3`, then a 1px × 18px divider. Input is 13.5px mono, transparent, no outline,
  placeholder `O que vamos construir hoje?`. Right: a 28×28 outlined submit button with an
  `arrow-right` glyph, which only takes the accent border/colour when the field is non-empty.

### 5. Right rail — `RailRight.jsx`

Mirror of the left rail (`right: var(--rail-gutter)`). Five sections:

| Section | Content |
| --- | --- |
| `CLIMA` (right: city) | A 26px `cloud-rain` glyph over a 20px temperature, a four-row key/value block, the sky in uppercase 10px, then a five-column week strip (8px). |
| `TAREFAS AGENDADAS` | Four columns: a 17px figure over a 7.5px uppercase label. The failure column is `--crit` and takes no glow. |
| `AÇÕES RÁPIDAS` | Five `Tile`s in `repeat(5, minmax(0,1fr))`, gap 5px. |
| `ATALHOS` | Five `Tile`s in **three** columns (the labels are long — Ferramentas, Alterações, Habilidades). |
| `TERMINAL` (`foot`, right: `ocupado` while thinking) | `TerminalLog`, height 132. |

### 6. Overlays — `Overlays.jsx`

Two plates, and **only one may be open at a time** — opening a note closes the side panel and
opening a side panel clears the selected note. They are pinned to the same band and would
otherwise collide below ~1270px.

The plate recipe (the one place v2 still uses v1's chrome, because these float *over* the graph):
`background: --surface-panel; backdrop-filter: blur(20px) saturate(0.85); border: 1px solid
--border-hairline with border-top-color --border-lit; border-radius: 3px; padding: 16px;
max-height: min(72vh, 100vh - 32px)`. A 20×20 outlined close button sits at top 10 / right 10.

- **Inspector** (`left: calc(rail-w + gutter*2)`, width 334): the type dot + 19px title, the path
  in 10px `--ink-3`, a `MetaGrid`, the warning line if the file yielded no text, the body in the
  **proportional** face at 13.5px / 1.55 with `max-height: 30vh`, an `Abrir o arquivo` link, then
  three more frames — Vínculos, Caminho mais curto (numbered steps), Maiores hubs.
- **SidePanel** (mirrored `right:`, width 300), one of five: Cérebro (three `BrainRow`s),
  Ferramentas (a server with no credential is disabled and its note reads `falta <ENV_VAR>`),
  Alterações (`Cópias em .jarvis/undo. Nada é sobrescrito sem uma.` then edit cards with a
  `desfazer` button that latches to `desfeito`), Habilidades, Terminal (full log, height 280).

---

## Interactions & behaviour

| Trigger | Result |
| --- | --- |
| Type ≥ 2 chars | Instant search over note titles and bodies, six hits max, each with a `…snippet…` around the match. No debounce; it is a local index. |
| Enter / submit | `phase = "thinking"`, log line `consulta: <q>`, reactor arc goes from a 6s crawl to a 0.8s sweep. After 1500ms the answer opens with its citation chips, a log line `resposta pronta · N citações · 4,1s`, and a feed entry. |
| Click a citation chip / result row | Opens that note in the Inspector, clears the traced path, closes any side panel. |
| Click a node | Same. |
| Shift-click a second node | BFS shortest path; logs `caminho traçado — N passos`, or `warn` + `nenhum caminho entre as duas notas`. |
| Click `Voz` | Refused: `err` log `falta ELEVENLABS_API_KEY — nada foi ligado`, feed entry `Ação recusada`. No state change. |
| Click `Reindexar` | `sys` log, feed entry, then an `ok` log 1200ms later. |
| Click `Silêncio` / `Analisar` | Latches; logs `<label>: ligado|desligado`. |
| Click `Treinar` | Nothing — the tile is `disabled` and its tooltip reads `a etapa 5 liga isto`. |
| Toggle a tool | Only if authenticated. Logs the new state. |
| `desfazer` an edit | Marks it `undone` (irreversible), logs `desfeito — <path>`, adds a feed entry. |
| `nova conversa` | Clears the answer and the query, logs `nova conversa`. |

**Motion.** Colour crossfades only: 110ms rows, 120ms controls, 140ms field border, `linear` —
no curve is named anywhere in the source. Nothing bounces, slides, scales or translates.
`prefers-reduced-motion` cuts every duration to 1ms. The only continuous motion is the graph's
sway/pulse and the reactor.

**Controls are outlined, never filled.** Rest: transparent, hairline border, `--ink-2` label,
uppercase. Hover **and** pressed resolve to the same accent triple (`--accent` text,
`--accent-line` border, `--accent-soft` fill); pressed is expressed with `aria-pressed="true"`,
not a different colour. Disabled keeps the label, drops to `--ink-3`, and switches to a **dashed**
border. Focus is `2px solid var(--accent)` at `outline-offset: 2px`, `:focus-visible` only.

---

## State management

All state lives in `JarvisConsole.jsx`; the rails report, the stage asks, the overlays read.

```
metrics      four {key,label,value}, drifted ±3.5 every 2400ms
feed         newest first, capped at 7
log          appended, capped at 40
brain        model id
tools        [{name,label,authenticated,needs,on}]
edits        [{id,when,path,action,before,after,undone}]
quickState   {silencio, analisar}
openPanel    null | "terminal"|"cerebro"|"ferramentas"|"alteracoes"|"habilidades"
focused      note id | null          ← mutually exclusive with openPanel
anchor       note id, the shift-click origin
pathIds      Set<id> | null
query        string
phase        "idle" | "thinking"
answer       {kind, meta, body, citations, titles, types} | null
level        0–1, drifts ±0.1 every 2400ms, drives reactor brightness
```

Derived, never stored: search results, the focused note's links, the path node list, the hubs.

**Data the real implementation must supply:** the vault index (nodes, edges, bodies, per-type
counts, hubs), the model list, the tool servers with their credential state, the skill files, the
edit journal, and the answer stream. `vault.js` and `telemetry.js` in this bundle are fixtures.

---

## Design tokens

Adopt `styles.css` and `tokens/` directly. The values, for reference:

**Colour** — `--void #050908` · surface `rgba(8,17,13,.74)` · surface-2 `rgba(11,23,18,.86)` ·
hairline `rgba(120,255,190,.10)` · hairline-up `rgba(120,255,190,.20)` · wash `rgba(120,255,190,.055)` ·
plate `rgba(4,9,7,.74)`. Ink `#cdf3de / #7fb99a / #4d7a64`. **Accent `#3ce88f`**, soft `.14`,
line `.40`. Status `--warn #fab219`, `--crit #ff5a52`, `--good #3ce88f`.

**Node taxonomy — do not hand-edit.** These were searched in OKLCH for the lowest-chroma set that
still clears every all-pairs contrast gate on this exact surface (worst CVD ΔE 9.5 protan, all
≥ 3:1 against `--void`): client `#cf7777`, project `#1c63b0`, meeting `#7f5605`, invoice `#618b09`,
person `#954c76`, note `#18a6b5`, reference `#7f7ee4`, other `#7c848f`.

**Type** — mono `"Cascadia Mono", "Cascadia Code", Consolas, ui-monospace, monospace`;
prose `"Source Sans 3", "Segoe UI", system-ui, sans-serif`. Sizes 9.5 / 10 / 10.5 / 11 / 11.5 /
12.5 / 13 / 13.5 / 19px — half-pixels are intentional. Tracking: title −0.01em, name 0.04em,
label 0.1em, eyebrow 0.17em, mode 0.18em, state 0.24em. Line-height 1.25 tight / 1.5 rows /
1.65 prose.

**Space** — radius `--r 3px` on everything, `--r-inner 2px`, `--r-pill 999px` for citation chips
only. Panel padding 16px, gutter 20px, row gap 9px, rows padded `5px 6px` and bled `−6px`.
Scale 4 / 6 / 8 / 10 / 12 / 14 / 16 / 20 / 22px.

**HUD (v2)** — rail 286px, rail gutter 16px, rail gap 14px, tile height 44px, tile gap 5px,
meter height 4px with 3px segments, gauge stroke 3px, reactor 420px, ask bar 640×46px.
Frame: rule 1px, diagonal cut 9×7px, opening cap 1×6px, label gap 9px.
`--hud-line rgba(accent,.30)`, `--hud-line-dim rgba(accent,.13)`.
Glow `0 0 9px rgba(accent,.42)` and `0 0 6px rgba(accent,.22)` — **reserved for live numbers and
the reactor, never for labels or prose.**

**Shadows: there are none.** Depth is translucency + blur + a lit top border. The only inner
shadow in the system is `inset 2px 0 0 var(--accent)` on a selected picker row.

**Cards: there are none.** Content sits in a frame or a plate, separated by hairline rules and
eyebrow labels. If you find yourself drawing a rounded box with a drop shadow, you have left
this system.

---

## Assets

- `assets/fonts/CascadiaCode.ttf` — Microsoft, SIL OFL 1.1, variable 200–700. Served under both
  `Cascadia Code` and `Cascadia Mono` so the first entry in `--font-mono` resolves.
- **Prose face is a substitution.** The source stack led with *Segoe UI Variable Text*, which is
  proprietary, ships with Windows and has no webfont. On the operator's instruction that name was
  dropped; **Source Sans 3** (Google Fonts, OFL) is the face, pulled by the `@import` at the top
  of `tokens/fonts.css`. Self-host it if the target has no network at build time.
- `assets/icons/*.svg` — **thirteen Lucide glyphs, also a flagged substitution.** The JARVIS
  source contains no icon set at all: no SVG, no sprite, no icon font, and a blank favicon
  (`href="data:,"`). v1 used coloured dots, a 6×1px dash and three unicode arrows. v2's tile grids
  needed glyphs, so Lucide (MIT, 1.5px stroke, round caps, 24px box) stands in. The path data is
  copied into `components/hud/Icon.jsx` — **no CDN at runtime.** If JARVIS ever gets its own
  glyphs, replace `GLYPHS` and nothing else changes.
- **There is no logo.** Set the brand name in the mono face, uppercase, `letter-spacing: 0.16em`.
  Do not draw a mark.
- No photographs, no illustrations, no patterns, no imagery of any kind. The graph is the only
  picture in this product.

---

## Screenshots

Captured from the running prototype at 924×540, in `screenshots/`:

| File | State |
| --- | --- |
| `01-repouso.png` | Idle. Greeting, reactor crawling, both rails, terminal. |
| `02-busca-instantanea.png` | Query typed — the instant file search open above the ask bar. |
| `03-resposta-com-citacoes.png` | Answer open with its accounting line and citation chips; reactor sweeping; the answer panel has taken the stage's height and the reactor has shrunk to fit. |
| `04-inspector-da-nota.png` | Inspector open on a cited note — title, path, metadata, body in the proportional face, links. |
| `05-painel-ferramentas.png` | Ferramentas side panel; an unauthenticated server is disabled and names its missing credential. |
| `06-painel-alteracoes.png` | Alterações — the disk journal with `desfazer`, and the `Cópias em .jarvis/undo` note. |
| `07-painel-cerebro.png` | Cérebro — the model picker, current row carrying the inset accent edge. |
| `08-painel-terminal.png` | Terminal side panel, full session log. |

Read them as evidence of behaviour, not as the spec — the numbers above are the spec.

---

## Files in this bundle

This is the whole design system. Everything a Claude Code session needs is at the root:

```
styles.css                    the one stylesheet to link — @imports only
tokens/                       colour, type, space, hud, motion, effects, base
readme.md                     the full design guide (content, visual, iconography)
HANDOFF.md                    this file — the implementation spec
SKILL.md                      makes this folder usable as a Claude Code Agent Skill
guidelines/*.card.html        30 foundation specimens, each openable in a browser
components/
  hud/                        the v2 primitives — HudFrame Meter RadialGauge Tile
                              Reactor TerminalLog Icon
  chrome/                     Panel PanelHead Eyebrow Alert PanelNote OpenLink
  controls/                   Button AskField SearchInput ThreadBar
  listing/                    Swatch Row TypeRow MetaGrid StatList BrainRow
  answer/                     AnswerBlock Cite ResultRow TurnRow FactRow
  status/                     ReactorDial (v1's small dial — superseded on the
                              console by Reactor, kept for small panels)
  …each with a .d.ts contract and a .prompt.md
ui_kits/jarvis-console/       the running prototype — open index.html in a browser
  index.html  README.md  JarvisConsole.jsx  RailLeft.jsx  RailRight.jsx
  CenterStage.jsx  Overlays.jsx  GraphStage.jsx  vault.js  telemetry.js
templates/jarvis-console/     the console shell as a starting point
screenshots/                  the eight states above
assets/fonts/CascadiaCode.ttf
assets/icons/*.svg
_ds_bundle.js                 generated — the compiled component library the
                              prototype and the specimen cards load. Do not edit.
thumbnail.html                the system's tile
```

`ui_kits/jarvis-console/index.html` is the thing to look at first — it runs offline apart from
the React/Babel CDN tags, with no build step.

## Using this as a Claude Code skill

Drop the folder into `.claude/skills/jarvis-design/` (the `SKILL.md` front-matter is already
written for it) and invoke it. It will read `readme.md`, then design against these rules.

Two reading orders, depending on the job:

- **Designing something new in the brand** — `SKILL.md` → `readme.md` → the `.prompt.md` next to
  each component you need → `guidelines/*.card.html` when you want to see a value rather than
  read it.
- **Implementing the console in a real codebase** — this file top to bottom, then
  `ui_kits/jarvis-console/README.md` for which source file each region was rebuilt from, then
  the JSX itself.

## The three rules that override anything else here

1. **Luminance says "look here", hue says "what it is."** One accent, carrying state only. The
   seven node colours carry taxonomy and are never borrowed as state; the status trio is never
   borrowed as a category.
2. **Mono is the machine's voice; the proportional face is the human's.** The only proportional
   text in the product is writing a person or the model produced — a note body, an answer, a
   search snippet, a remembered fact.
3. **Say what is missing, never what is fine.** There is no success toast in this product, no
   "Salvo!", no green check. Silence means working. Every message that exists names a failure,
   an absence or a warning — and names its fix.
