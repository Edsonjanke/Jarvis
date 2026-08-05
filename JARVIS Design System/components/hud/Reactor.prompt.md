The centrepiece of the v2 console — concentric rings lying on a plane seen in perspective, around a triangle core that stands upright. Drawn on canvas. Exactly one per screen, dead centre, with readouts pinned around it.

```jsx
<Reactor size={420} state={thinking ? "thinking" : "idle"} level={0.62} />
<Reactor size={188} tilt={1} />   {/* head-on, for a small panel */}
```

`state` is the only thing that changes its motion: `idle` crawls the state arc once per 6s, anything else sweeps it at 0.8s. `level` raises the brightness of the whole stack — it is a reading, not a speed. `tilt` squashes the ring plane vertically; 0.46 is the console's perspective, 1 is head-on.

Do not add a second reactor, and do not use it as a loading spinner in a panel.
