The ask bar's field — one per screen, centred at the bottom, 720px max.

```jsx
<AskField mode="ask" value={q} onChange={setQ} onSubmit={ask} placeholder="Client health board" />
```

It sits on `--surface-2` (slightly more solid than a panel) and shows focus by turning its border `--accent-line` over 140ms — never by growing, glowing or changing background. The placeholder is a real example from the user's own vault, not instructional text.
