The square icon action used in v2's "Ações rápidas" and "Atalhos" grids — five per row, `display:grid` with `gap: var(--tile-gap)`.

```jsx
<div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:"var(--tile-gap)"}}>
  <Tile icon="mic" label="Voz" active={listening} onClick={toggle} />
  <Tile icon="scan-line" label="Reindexar" onClick={reindex} />
  <Tile icon="brain-circuit" label="Treinar" disabled title="etapa 5" />
</div>
```

A tile that is not wired stays visible and `disabled` — its border goes dashed and the tooltip names the step that wires it. Nothing scales or moves on press.
