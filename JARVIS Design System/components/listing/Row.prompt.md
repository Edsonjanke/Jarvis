Every list of notes in the inspector is a stack of these inside a plain `<ul>` with no bullets.

```jsx
<Row type="client" label="Harrow & Vane" tail={9} onClick={() => open(id)} />
<Row type="invoice" label="Fatura 4471" dir="→" />
<Row type="note" label="Deposit policy" step={2} />
```

Hover is a wash plus a lift from `--ink-2` to `--ink`, 110ms, colour only — do not add translation, scale or a border.
