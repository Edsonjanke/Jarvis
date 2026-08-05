The v2 section frame — a labelled rule with a diagonal cut at its right end; use it anywhere v1 would have used `Panel` + `Eyebrow`.

```jsx
<HudFrame label="Status do sistema" right="local" foot>
  <Meter label="CPU" value={17} />
  <Meter label="RAM" value={39} />
</HudFrame>
```

`label` sets the uppercase marker, `right` adds a small readout at the far end of the rule, `foot` closes the block with a mirrored (dimmer) rule. The frame draws no background — put it directly on the field, or over a `--surface-panel` plate if it must sit on top of the graph.
