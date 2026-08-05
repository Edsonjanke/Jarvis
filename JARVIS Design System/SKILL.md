---
name: jarvis-design
description: Use this skill to generate well-branded interfaces and assets for JARVIS, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for protoyping.
user-invocable: true
---

Read the `readme.md` file within this skill, and explore the other available files.
If you are implementing the console in a real codebase rather than designing something new,
read `HANDOFF.md` instead — it is the full implementation spec, with `screenshots/` as evidence.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## What is here

- `readme.md` — the design guide: product context, content fundamentals, visual foundations, iconography, and an index of everything else.
- `styles.css` — the one stylesheet to link. It `@import`s every token file and the fonts.
- `tokens/` — colour, type, space, hud, motion, effects, base.
- `assets/fonts/CascadiaCode.ttf` — the interface face. There is no logo; set the name in type.
- `assets/icons/` — thirteen Lucide glyphs, a flagged substitution: the source ships no icon set.
- `guidelines/*.card.html` — foundation specimens, each one openable in a browser.
- `components/<group>/` — the React primitives, each with a `.d.ts` contract and a `.prompt.md`.
  `components/hud/` is the v2 set: `HudFrame`, `Meter`, `RadialGauge`, `Tile`, `Reactor`,
  `TerminalLog`, `Icon`.
- `ui_kits/jarvis-console/` — the whole product (v2), click-through, built from those primitives.

## The three rules that matter most

1. **Luminance says "look here", hue says "what it is."** One accent, and it carries state only.
   The seven node colours carry taxonomy and are never reused as state.
2. **Mono is the machine's voice; the proportional face is the human's.** The only proportional
   text is writing the person or the model produced.
3. **Say what is missing, never what is fine.** No success states, no toasts, no green checks.
   Silence means working.
