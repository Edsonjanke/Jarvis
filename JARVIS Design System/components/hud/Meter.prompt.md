A labelled load bar with its value at the end; the v2 way to show any 0–100 reading.

```jsx
<Meter label="CPU" value={17} />
<Meter label="Rede" value={62} display="2.4 TB/s" />
<Meter label="Disco" value={94} tone="warn" />
```

`segmented` (default true) cuts the fill into 3px ticks. `tone` only leaves `accent` when a real threshold is crossed — a bar is not coloured for decoration.
