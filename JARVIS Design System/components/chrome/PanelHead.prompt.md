Titles a section inside a Panel — use it instead of a heading tag anywhere in JARVIS.

```jsx
<PanelHead label="Types">
  <Button size="ghost" onClick={showAll}>All</Button>
</PanelHead>
```

The right slot takes exactly one thing: a ghost Button, or a muted count (`<span style={{color:"var(--ink-3)",fontSize:"var(--size-tick)"}}>sonnet-4.6</span>`). Pass `rule` when the section below needs separating from the one above.
