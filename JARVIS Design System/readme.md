# JARVIS Design System

The design system for **JARVIS** — a local-first assistant that reads one person's own
files and answers out of them, with the vault drawn as a knowledge graph.

Built by reading the source at `Jarvis/` (mounted local folder, read-only):

| Source | What it gave |
| --- | --- |
| `Jarvis/ui/styles.css` (693 lines) | Every token in this system. Colours, type, spacing, motion, the panel recipe. |
| `Jarvis/ui/index.html` | The screen's structure — three floating plates over a full-bleed canvas. |
| `Jarvis/ui/app.js` (1,810 lines) | Component behaviour, states, and all interface copy. |
| `Jarvis/ui/graph.js` (649 lines) | The canvas graph: forces, colours, labels, glow, dim, pulses. |
| `Jarvis/JARVIS.md` | Standing instructions — the operator's voice, in pt-BR. |
| `Jarvis/skills/cobranca.md` | A skill file; the writing standard for guidance copy. |
| `Jarvis/agent/main.py`, `agent/brain.py` | Capability model, alert copy, the answer's ground rules. |
| `Jarvis/data/generate.py` | The demo vault profile — the sample content used in the UI kit. |

No Figma file, no design spec and no brand book were provided. Where this system states a
rule, it is a rule read out of that code, not one invented for it.

**v2 (agosto/2026).** The operator supplied a reference screenshot of an instrument-HUD console
(`uploads/pasted-1785878040107-0.png`) and asked for the JARVIS interface rebuilt against it.
Three things changed, and only three:

1. **The accent went from `#93b4ff` to `#3ce88f`**, and every neutral picked up its hue. The
   seven taxonomy colours were not touched — they were searched, not chosen.
2. **The panel became a frame.** v1's four-sided translucent plate is replaced on the field by
   `HudFrame`: a labelled rule with a diagonal cut, nothing boxed. Plates survive only for
   overlays that float over the graph.
3. **The machine reports on itself.** Load, core, memory, network, weather, scheduled work and
   a live terminal now sit in two rails around a reactor. The content is the real product's —
   the vault, the graph, the brain, the tools, the disk edits — not the reference's demo data.

Everything else in this document still holds. The copy rules, the motion rules, the control
recipe and the "say what is missing, never what is fine" standard are unchanged.

---

## The product

One person, one machine, one screen. JARVIS indexes folders on disk into a graph of typed
notes, then answers questions **only** out of what it read, citing the note ids it used.
The operator is **Edson**, at **EVO Soluções Industriais** — machining, production planning,
shop floor. It runs on localhost; the model key never leaves the process.

The interface is a single view, not a set of pages:

- **The canvas** — a force-directed graph of the vault, full-bleed behind everything. Click a
  node to read it; shift-click a second to trace the shortest path between them.
- **Inspector** (left, 342px) — the selected note: type, title, path, metadata, the extracted
  text, its links, the shortest path, the top hubs.
- **Status** (right, 268px) — the reactor dial, type filters with counts, and the pickers for
  Cérebro (which model), Ferramentas (what it may reach outside the vault), Habilidades (how
  you work), Alterações (what it changed on disk, with undo), and the vault readout.
- **Ask bar** (bottom, centred) — typing runs an instant file search, Enter sends the question
  to the model. The answer opens above the field with its citations as chips.
- **Alerts** (top, full width) — present only when something is genuinely broken.

There are five capability stages; a control that is not wired yet stays visible, disabled, and
its tooltip says which step wires it.

---

## CONTENT FUNDAMENTALS

**Two languages, on purpose.** The original layer is English (`Inspector`, `Types`, `Top hubs`,
`Shortest path`, `Brief`, `Plan`, `Mic`, `Mute`, `Memory`). Everything added later is Brazilian
Portuguese (`Cérebro`, `Ferramentas`, `Habilidades`, `Alterações`, `Histórico`, `Reindexar`,
`Sempre`, `Desfazer`, `Apagar`, `nova conversa`). Do not "fix" this into one language: the split
is the product's own history, and the operator reads both. New operator-facing strings — the
ones Edson reads while working — are written in pt-BR.

**Machine states are lowercase.** `idle`, `listening`, `thinking`, `speaking`, `ask`, `find`,
`lendo…`, `testando…`, `nenhuma`, `desligada`, `ligada`, `desfeito`. Never Title Case, never a
full stop.

**Labels are uppercase and tracked wide.** `INSPECTOR`, `SHORTEST PATH`, `CÉREBRO`. Ten pixels,
0.17em, `--ink-3`. They are section markers, not headings.

**Sentences are declarative and short.** They name the thing and stop:

> Nothing selected.
> Click a node to read it. Shift-click a second to trace the shortest path between them.
> Nothing was indexed. That is a failure, not an empty result.
> No note was cited — treat this as unsourced.
> Cut off at the token limit — the answer above is incomplete.
> Cópias em .jarvis/undo. Nada é sobrescrito sem uma.

**Say what is missing, never what is fine.** There is no success toast in this product, no
"Saved!", no green check. Silence means working. The only messages that exist are failures,
absences and warnings — and each one names the fix: `falta ELEVENLABS_API_KEY`,
`o arquivo não existia antes — desfazer o remove`, `Type the goal first, then press Plan.`

**Second person, imperative, no hedging.** "Allow it in the address bar and try again."
"Finish the current question first." No "please", no "oops", no "we". The product does not
apologise and does not use the first person plural. JARVIS itself is a name, not a persona:
it never says "I think" in the interface.

**Numbers carry their date and their source.** From `JARVIS.md`: every value comes from a
document with a date — say which. A number without a date cannot be checked or acted on.
An estimate presented as fact is the one expensive error.

**Meta lines are `·`-separated fragments, never sentences:**
`sonnet-4.6 · read 14 notes · 2 remembered · cobranca · JARVIS.md · 4.1s`

**Never used:** emoji, exclamation marks, marketing verbs ("powerful", "seamless"), progress
prose ("Hang tight…"), or capitalised product nouns. The single glyph in the whole interface
that behaves like an emoji is `⚠`, prefixed to a skill file that failed to load.

---

## VISUAL FOUNDATIONS

**The direction, in the source's own words:** an instrument panel, not a dashboard. A dark
field with signal on it. **Luminance says "look here"; hue says "what it is."**

**Colour.** One accent (`--accent #3ce88f`, phosphor green) and it carries *state only* — focus,
traced path, active reactor, current selection. v2 changed the accent from the v1 blue
`#93b4ff` and gave every neutral a green cast, so the whole field reads as one lit instrument;
ink is `#cdf3de / #7fb99a / #4d7a64` and hairlines are `rgba(120,255,190,…)` rather than white. Seven node colours carry *taxonomy* and are never reused as
state; they were searched in OKLCH for the lowest-chroma set that still clears every all-pairs
contrast gate on this exact surface (worst CVD ΔE 9.5, all ≥ 3:1) and must not be hand-edited.
Status (`--warn`, `--crit`, `--good`) is reserved and never borrowed as a category. Mean chroma
of the type colours is deliberately low — the accent is brighter than all of them.

**Background.** `#050908`, full-bleed. v2 added exactly three things on top of it, all painted
from `[data-hud-field]` so no element in the tree carries them: a 46px grid at 3.5% accent, a
3px scanline at 2.2%, and one radial bloom at 5.5% behind the reactor. Nothing else. There are
still no photographs, no illustrations, no patterns and no imagery of any kind in this product,
and the graph remains the only real thing behind the instruments (drawn at `opacity .55` in v2
so the rails read over it).

**Type.** Mono is the interface's voice; the proportional face appears *only* where the
operator's own prose is shown — the note body, the answer body, a search snippet, a remembered
fact. The machine speaks in mono; the human doesn't. Sizes run 9.5–13.5px with one 19px title.
Half-pixel sizes are intentional; do not round them to a grid.

**Spacing.** 16px panel padding, 20px gutter to the viewport edge, 9px row gap, rows padded
5px 6px and bled −6px so the hover wash reaches the panel's inner edge. Panel widths are fixed
(342 / 268 / min(720px, 100vw−40px)); the canvas is inset by 382/308/56/132 so the graph never
settles under a plate.

**Layout rules.** Everything is `position: fixed`. The page never scrolls — `html, body` are
`overflow: hidden`; scrolling happens inside a panel, with a thin `--ink-3` scrollbar. The three
plates float; the canvas fills the viewport under them.

**Transparency and blur.** Every floating surface is the same recipe: `rgba(12,14,17,.74)` with
`backdrop-filter: blur(20px) saturate(0.85)`, a `#fff/.075` hairline border, and a brighter
`#fff/.14` top border so the plate catches an edge light. `--surface-2` (.86) is used where text
input happens and the field must sit slightly more solid than a panel.

**Shadows.** There are none in the DOM. Depth is translucency + blur + a lit top edge. Glow
exists in exactly one place — nodes on the canvas, `shadowBlur` 16 hovered / 9 focused — and it
marks state, never decoration. The one inner shadow in the system is `inset 2px 0 0 accent` on
the selected brain row.

**Borders and corners.** 1px hairlines only, at 7.5% white. `--r: 3px` on everything —
panels, buttons, rows, fields, plates. `--r-pill: 999px` exists for one component, the citation
chip. Nothing else is round except the 9px taxonomy dots.

**Cards.** There are no cards. Content sits in a panel, separated by hairline rules and
eyebrow labels. If you find yourself drawing a rounded box with a shadow, you have left this
system.

**Controls are outlined, never filled.** "On a dark instrument panel a filled button reads as a
web page; an etched one reads as hardware." Rest: transparent, hairline border, `--ink-2` label,
uppercase, 0.1em. Hover *and* pressed resolve to the same accent triple — `--accent` text,
`--accent-line` border, `--accent-soft` fill; pressed is expressed with `aria-pressed="true"`,
not with a different colour. Disabled keeps the label, drops to `--ink-3`, and switches to a
**dashed** border. Nothing scales, nothing translates, nothing shrinks on press.

**Hover.** Rows take a `#fff/.045` wash and lift their text from `--ink-2` to `--ink`. Chips and
buttons take the accent triple. A link uses `filter: brightness(1.25)`. A switched-off filter
row drops to `opacity: .36` and its bar goes grey. Nothing moves.

**Focus.** `2px solid var(--accent)` at `outline-offset: 2px`, radius 2px, on `:focus-visible`
only. A field shows focus by turning its border `--accent-line` over 140ms.

**Motion.** Colour crossfades at 110/120/140ms, linear — no curve is named anywhere in the
source. Nothing bounces, slides, or fades in from off-screen. The only continuous motion is the
graph's own: an 11s global sway, a faint pulse walking a random link every 3.4s, and the reactor
arc (0.8s sweep live, 6s crawl idle). `prefers-reduced-motion` cuts every duration to 1ms.

**The graph's own vocabulary.** Node radius = `3.4 + √degree × 2.35`, capped at 17. Edges are
white at 5.5% alpha; a traced path is accent at 95% and 1.6px. Hovering anything drops
everything unrelated to `alpha 0.10`. Labels are 11px mono on a `rgba(7,8,9,.72)` plate, placed
in the first of eight free slots around a node, and dropped when they would collide — except
for the five biggest hubs, which are always labelled.

---

## ICONOGRAPHY

**There is no icon set, and adding one would be a change to the brand, not an implementation
detail.** The source contains no SVG, no icon font, no sprite sheet, and not one raster image.
The favicon is literally `href="data:,"` — a blank.

What does the work instead:

- **Coloured dots.** A 9px circle in a node-type colour is the only "icon" in the product. It
  appears in the inspector header, in every list row, in search hits, and on citation chips.
- **A 6×1px dash.** The `::before` of `.eyebrow`, in `currentColor`. It marks every section.
- **Bars.** A 2px filled bar under a type row gives its share of the vault.
- **Three unicode glyphs, used sparingly.** `→` / `←` for link direction, `↗` appended by
  `.note-open::after` for "opens outside", `⚠` for a skill file that failed to load.
- **`·`** as the separator in every meta line.
- **The reactor** — a canvas dial with a twelve-mark bezel, a 64-bin polar level meter with
  phosphor decay, and one arc that carries state. It is the product's only ornament, and it is
  drawn, not an asset.

**v2 added one, and it is a flagged substitution.** The tile grids (`Ações rápidas`, `Atalhos`)
need glyphs, and the source has none, so **Lucide** (`lucide-static` off unpkg, 1.5px stroke,
round caps, 24px box) stands in via the `Icon` component — masked to `currentColor` so a glyph
takes the same state colour as the control around it. This is the closest match to the
reference's line weight; **if JARVIS ever gets its own glyphs, replace the CDN base in
`components/hud/Icon.jsx` and nothing else changes.** Use `Icon` only in tile grids and the ask
bar — do not sprinkle it through lists, headings or panels, which still use dots and dashes.

**Assets.** `assets/fonts/CascadiaCode.ttf` is the only binary in this system. There is no logo
— see the *Wordmark* card: set the name in the mono face, uppercase, 0.16em, and do not draw a
mark.

---

## FONTS — one from the source, one substituted

- **Mono — Cascadia Code**, variable 200–700, shipped here as `assets/fonts/CascadiaCode.ttf`
  (Microsoft, SIL OFL 1.1). The source's stack prefers locally-installed *Cascadia Mono* (same
  design, ligatures off) and falls back to Consolas; both are kept in `--font-mono`.
- **Prose — Source Sans 3** (Google Fonts, OFL). The source's stack led with **Segoe UI
  Variable Text**, which is proprietary, ships with Windows and has no webfont. On the
  operator's instruction that name was dropped from `--font-sans` — Source Sans 3 is now the
  face, not a fallback: humanist, low contrast, open apertures, close in colour on a dark
  field. `"Segoe UI"` is kept one step behind so Windows machines land somewhere familiar.

---

## Intentional additions

Nothing in `components/` exists that the source does not define; every component is a
class in `ui/styles.css` with behaviour in `app.js`. Two shaping decisions worth naming:

- **`Button`** merges the source's `.key` and `.ghost`, which share one rule set and differ only
  in padding and size, into one component with `size="key" | "ghost"`.
- **`ReactorDial`** is a React wrapper around the canvas drawing loop in `app.js`
  (`drawReactor`/`reactorTick`), which the source keeps as loose functions rather than a class.

**The `components/hud/` family is v2 and has no counterpart in `Jarvis/ui/`.** It exists because
the operator asked for the instrument-HUD shell (the reference screenshot in `uploads/`), and it
replaces — not supplements — v1's plate chrome on the console. `HudFrame` supersedes
`Panel` + `Eyebrow` for sections on the field; `Panel` is still correct for overlays that float
*over* the graph. `Reactor` supersedes `ReactorDial` on the console stage; `ReactorDial` stays
for anything that needs the small single-bezel dial. `Meter`, `RadialGauge`, `Tile`,
`TerminalLog` and `Icon` are new: the machine-side readouts the reference calls for.

---

## Index

**Foundations**
- `styles.css` — the entry point consumers link. `@import`s only.
- `tokens/fonts.css` · `color.css` · `type.css` · `space.css` · `motion.css` · `effects.css` · `base.css`
- `guidelines/*.card.html` — 21 specimen cards (Colors, Type, Spacing, Brand)
- `assets/fonts/CascadiaCode.ttf`

**Components** — `window.JARVISDesignSystem_ad8200.<Name>`
- `components/hud/` (v2) — `HudFrame`, `Meter`, `RadialGauge`, `Tile`, `Reactor`, `TerminalLog`, `Icon`
- `components/chrome/` — `Panel`, `PanelHead`, `Eyebrow`, `Alert`, `PanelNote`, `OpenLink`
- `components/controls/` — `Button`, `AskField`, `SearchInput`, `ThreadBar`
- `components/listing/` — `Swatch`, `Row`, `TypeRow`, `MetaGrid`, `StatList`, `BrainRow`
- `components/answer/` — `AnswerBlock`, `Cite`, `ResultRow`, `TurnRow`, `FactRow`
- `components/status/` — `ReactorDial`

**UI kit**
- `ui_kits/jarvis-console/` — **v2, the official console.** The whole product, click-through:
  select a node, shift-click a second to trace the path, search as you type, ask, read the
  answer's citations, switch the brain, toggle a tool, undo a vault edit, reindex, watch the
  terminal. v1 (blue accent, three floating plates) has been replaced. `README.md` in that
  folder lists which source file each region was rebuilt from.

**Template**
- `templates/jarvis-console/` — the console shell as a starting point for new work.

**Skill**
- `SKILL.md` — makes this folder usable as an Agent Skill.
- `HANDOFF.md` — the implementation spec for rebuilding the console in a real codebase:
  every token, every measurement, every state transition, plus the screenshot index.
- `screenshots/` — eight captured states of the running console.
