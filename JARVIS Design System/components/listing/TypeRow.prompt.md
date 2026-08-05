The filter list in the right panel — one row per note type found in the vault.

```jsx
<TypeRow type="project" count={31} share={1} on={!hidden.has("project")} onClick={toggle} />
<TypeRow type="invoice" count={12} share={0.39} on={false} />
```

Share is measured against the largest type so the biggest bar is always full. An off row is dimmed rather than hidden — the count still has to be readable.
