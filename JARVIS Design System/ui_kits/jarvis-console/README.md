# JARVIS console — v2

The whole product in one screen. This is the official console; v1 (blue accent, three floating
plates) has been replaced.

## Layout

| Region | File | Rebuilt from |
| --- | --- | --- |
| Field, grid, scanline, bloom | `index.html` + `tokens/base.css` | new in v2 (reference screenshot) |
| Graph, full-bleed behind everything | `GraphStage.jsx` | `Jarvis/ui/graph.js` |
| Left rail — load, núcleo, memória, rede, feed | `RailLeft.jsx` | `Jarvis/agent/main.py` (capability model), new readouts |
| Centre — greeting, reactor, ask bar, answer | `CenterStage.jsx` | `Jarvis/ui/index.html`, `Jarvis/ui/app.js` |
| Right rail — clima, tarefas, ações, atalhos, terminal | `RailRight.jsx` | new in v2 (reference screenshot) |
| Inspector + side panels | `Overlays.jsx` | `Jarvis/ui/app.js` (inspector, cérebro, ferramentas, alterações, habilidades) |
| State | `JarvisConsole.jsx` | `Jarvis/ui/app.js` |
| Demo vault | `vault.js` | `Jarvis/data/generate.py` |
| Machine readouts | `telemetry.js` | new in v2 — fixed values, drifted a few points on a 2.4s timer |

## What works

- **Click a node** on the graph to open it in the inspector. **Shift-click a second** to trace
  the shortest path; the traced edges go accent and the path is listed in the inspector.
- **Type in the ask bar** — two characters run an instant file search over titles and bodies,
  six hits max, each with the line it matched on.
- **Enter** sends the question. The reactor's state arc goes from a 6s crawl to a 0.8s sweep,
  the terminal logs the query, and after 1.5s the answer opens above the field with its
  citations as chips. Clicking a chip opens that note.
- **Ações rápidas** — Voz is refused (`falta ELEVENLABS_API_KEY`, logged as an error, no state
  change), Silêncio and Analisar latch, Reindexar runs and logs, Treinar is disabled with a
  tooltip naming the step that wires it.
- **Atalhos** open the side panels: Cérebro (switch model), Ferramentas (toggle what may reach
  outside the vault; an unauthenticated server cannot be switched on), Alterações (undo a disk
  edit — once), Habilidades, Terminal (the full log).
- **Trocar cérebro** is also reachable inline from the Núcleo de IA frame.

## What is faked

The vault is 44 fixed notes. The answer is one canned response from `vault.js`. Weather,
scheduled jobs and the load bars are invented readouts — plausible, not live. Nothing writes to
disk and nothing calls a model.
