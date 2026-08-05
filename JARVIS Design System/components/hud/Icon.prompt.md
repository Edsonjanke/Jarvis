A Lucide glyph drawn inline with `stroke: currentColor`, so it takes the same state colour as the control around it.

```jsx
<Icon name="mic" />
<Icon name="database" size={13} strokeWidth={1.5} />
```

**This is a flagged substitution.** The JARVIS source has no icon set — no SVG, no sprite, no icon font. v1 used coloured dots, a 6×1px dash and three unicode arrows and nothing else. Use `Icon` only where v2 genuinely needs a glyph (the tile grids, the ask bar); do not sprinkle it through lists or headings.

The set shipped here is thirteen glyphs, copied into `components/hud/Icon.jsx` and `assets/icons/`: `mic`, `volume-x`, `scan-line`, `file-search`, `brain-circuit`, `square-terminal`, `database`, `network`, `workflow`, `settings`, `cloud-rain`, `arrow-right`, `x`. Add more by copying the path data from `lucide-static` into `GLYPHS` — do not link a CDN, and do not draw your own.
