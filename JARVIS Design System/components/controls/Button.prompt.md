The product's one control. Use `size="key"` in the ask bar's action row and `size="ghost"` inline in a panel header or a list row.

```jsx
<Button size="key" onClick={brief}>Brief</Button>
<Button size="key" pressed={awake} onClick={toggleWake}>Sempre</Button>
<Button size="key" disabled title="wired in step 5, with memory">Memory</Button>
<Button size="ghost" onClick={clearFilters}>All</Button>
```

Labels are one word where possible and keep the product's mixed languages: Brief, Plan, Mic, Mute, Memory, Sempre, Histórico, Reindexar, Desfazer, Apagar. Never fill a button with a solid colour, and never use one for a destructive action without the word on it.
