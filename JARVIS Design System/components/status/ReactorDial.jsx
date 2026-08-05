import React from "react";

/* The reactor. Twelve index marks like a dial face, a 64-bin polar level meter
   with phosphor decay, and one arc that carries state: a slow crawl at idle, a
   fast sweep when live. Driven on a timer, not requestAnimationFrame — RAF
   stops dead in a backgrounded tab. */
const BINS = 64;
const TAU = Math.PI * 2;
const LIVE = ["listening", "thinking", "speaking"];

export function ReactorDial({ state = "idle", level = 0, sub = "", size = 176, style, ...rest }) {
  const ref = React.useRef(null);
  const bins = React.useRef(new Float32Array(BINS));
  const sweep = React.useRef(0);
  const live = LIVE.indexOf(state) >= 0;
  const liveRef = React.useRef(live);
  const levelRef = React.useRef(level);
  liveRef.current = live;
  levelRef.current = level;
  const speaking = state === "speaking";
  const speakRef = React.useRef(speaking);
  speakRef.current = speaking;

  React.useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");

    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== size * dpr) { canvas.width = size * dpr; canvas.height = size * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2, cy = size / 2, k = size / 176;
      const css = getComputedStyle(document.documentElement);
      const accent = css.getPropertyValue("--accent").trim() || "#93b4ff";
      const idle = css.getPropertyValue("--ink-3").trim() || "#5f6874";
      const on = liveRef.current;
      const colour = on ? accent : idle;

      ctx.strokeStyle = idle;
      ctx.lineWidth = 1;
      for (let i = 0; i < 12; i++) {
        const angle = (i / 12) * TAU - Math.PI / 2;
        const long = i % 3 === 0;
        ctx.globalAlpha = long ? 0.36 : 0.16;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * 84 * k, cy + Math.sin(angle) * 84 * k);
        ctx.lineTo(cx + Math.cos(angle) * (long ? 74 : 79) * k, cy + Math.sin(angle) * (long ? 74 : 79) * k);
        ctx.stroke();
      }

      const rIn = 56 * k, rOut = 79 * k;
      for (let i = 0; i < BINS; i++) {
        bins.current[i] *= 0.9;
        const angle = (i / BINS) * TAU - Math.PI / 2;
        const len = 1.5 + bins.current[i] * (rOut - rIn);
        ctx.strokeStyle = colour;
        ctx.globalAlpha = 0.2 + bins.current[i] * 0.75;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * rIn, cy + Math.sin(angle) * rIn);
        ctx.lineTo(cx + Math.cos(angle) * (rIn + len), cy + Math.sin(angle) * (rIn + len));
        ctx.stroke();
      }

      ctx.globalAlpha = on ? 0.5 : 0.2;
      ctx.strokeStyle = colour;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, 46 * k, 0, TAU);
      ctx.stroke();

      const t = performance.now() / (on ? 800 : 6000);
      const head = t % TAU;
      ctx.strokeStyle = colour;
      ctx.globalAlpha = on ? 1 : 0.55;
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      if (on) { ctx.shadowColor = accent; ctx.shadowBlur = 10; }
      ctx.beginPath();
      ctx.arc(cx, cy, 46 * k, head, head + (on ? 1.35 : 0.5));
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.lineCap = "butt";
      ctx.globalAlpha = 1;
    };

    const tick = () => {
      if (!liveRef.current) {
        sweep.current = (sweep.current + 0.6) % BINS;
        const at = Math.floor(sweep.current);
        bins.current[at] = Math.max(bins.current[at], 0.22);
      } else {
        const spread = speakRef.current ? 0.5 : 1;
        for (let i = 0; i < BINS; i++) {
          bins.current[i] = Math.max(bins.current[i], Math.random() * levelRef.current * spread);
        }
      }
      draw();
    };

    const id = setInterval(tick, 33);
    tick();
    return () => clearInterval(id);
  }, [size]);

  return (
    <div
      {...rest}
      style={{
        position: "relative",
        display: "grid",
        placeItems: "center",
        margin: "4px auto var(--space-9)",
        width: size + "px",
        height: size + "px",
        ...style,
      }}
    >
      <canvas ref={ref} aria-hidden="true" style={{ position: "absolute", inset: 0, width: size + "px", height: size + "px" }} />
      <div style={{ position: "relative", display: "grid", placeItems: "center", gap: "4px", textAlign: "center", pointerEvents: "none" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "var(--size-key)", letterSpacing: "var(--track-state)",
          textTransform: "uppercase", color: live ? "var(--accent)" : "var(--text-body)",
        }}>{state}</span>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: "var(--size-micro)", letterSpacing: "0.08em",
          color: "var(--text-muted)", maxWidth: Math.round(size * 0.74) + "px",
        }}>{sub}</span>
      </div>
    </div>
  );
}
