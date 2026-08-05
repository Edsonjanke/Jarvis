A filter over a list that is already open. Distinct from AskField: this one never talks to the model.

```jsx
<SearchInput value={q} onChange={setQ} onSubmit={showHistory} placeholder="buscar no que você já perguntou…" />
```

Unlike AskField it has a filled bed (`#fff/.04`) and takes a solid `--accent` border on focus.
