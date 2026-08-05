repo: Edsonjanke/Jarvis
branch: main

## Last sync

date: 2026-08-04T00:00:00Z

### Updated in this project
- Console rebuilt as v2: instrument HUD with two instrument rails and a central reactor.
- Accent retoned from `#93b4ff` to phosphor green `#3ce88f` across every token.
- New `components/hud/` family: HudFrame, Meter, RadialGauge, Tile, Reactor, TerminalLog, Icon.
- v1 console (blue accent, three floating plates) removed — v2 replaces it.

Note: this project was built from the mounted local folder `Jarvis/`, not from a GitHub
fetch, so no commit sha is recorded. Run a sync to pin one.

## Screen map

| Screen | Repo files |
| --- | --- |
| `ui_kits/jarvis-console/index.html` | `ui/index.html` |
| `ui_kits/jarvis-console/GraphStage.jsx` | `ui/graph.js` |
| `ui_kits/jarvis-console/JarvisConsole.jsx` | `ui/app.js` |
| `ui_kits/jarvis-console/CenterStage.jsx` | `ui/app.js`, `ui/index.html` |
| `ui_kits/jarvis-console/Overlays.jsx` | `ui/app.js` |
| `ui_kits/jarvis-console/vault.js` | `data/generate.py` |
| `tokens/*.css` | `ui/styles.css` |
| `components/**` | `ui/styles.css`, `ui/app.js` |
