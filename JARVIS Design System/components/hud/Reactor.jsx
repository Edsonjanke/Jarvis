import React from "react";

/* v2's reactor. Concentric rings around a triangle core, drawn on canvas.
   v1's ReactorDial was a single bezel with one state arc; this is the
   reference's stack — a tick bezel, gapped rings, an arc pair and a slow
   orbit — and it still carries state only: idle crawls, thinking sweeps.

   Runs on the same 33ms interval the rest of this system uses rather than
   requestAnimationFrame, which stops dead when the frame is off screen. */
const RINGS = [
  { r: 0.115, w: 1, a: 0.42, gaps: 0, spin: 0 },
  { r: 0.175, w: 1, a: 0.20, gaps: 3, spin: 0.10, gapArc: 0.30 },
  { r: 0.245, w: 1, a: 0.30, ticks: 48, tick: 4 },
  { r: 0.325, w: 1.4, a: 0.16, gaps: 2, spin: -0.06, gapArc: 0.55 },
  { r: 0.395, w: 1, a: 0.10, ticks: 96, tick: 2.5 },
  { r: 0.475, w: 1, a: 0.13, gaps: 4, spin: 0.04, gapArc: 0.18 },
  { r: 0.60, w: 1, a: 0.07, gaps: 0 },
];

export function Reactor({ size = 420, state = "idle", level = 0.5, tilt = 0.46, style, ...rest }) {
  const ref = React.useRef(null);
  const live = React.useRef({ state, level, tilt });
  live.current = { state, level, tilt };
  const RS = 0.78; /* the ring stack fills 94% of the box, corners left free for readouts */

  React.useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const css = getComputedStyle(document.documentElement);
    const accent = css.getPropertyValue("--accent").trim() || "#3ce88f";
    const rgb = (css.getPropertyValue("--accent-rgb").trim() || "60,232,143").replace(/\s/g, "");
    const dots = Array.from({ length: 26 }, (_, i) => ({
      a: (i / 26) * Math.PI * 2 + i * 0.7,
      r: 0.035 + ((i * 37) % 100) / 100 * 0.10,
      s: 0.15 + ((i * 53) % 100) / 100 * 0.5,
    }));
    let t = 0, raf = null;

    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const s = canvas.clientWidth || size;
      if (canvas.width !== Math.round(s * dpr)) { canvas.width = Math.round(s * dpr); canvas.height = Math.round(s * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, s, s);
      const cx = s / 2, cy = s / 2;
      const busy = live.current.state !== "idle";
      const lv = Math.max(0, Math.min(1, live.current.level));
      const ty = Math.max(0.12, Math.min(1, live.current.tilt));
      const rate = busy ? 4.2 : 1;
      const gain = 0.55 + lv * 0.45 + (busy ? 0.25 : 0);

      /* The whole stack lies on a plane seen at an angle: every ring is an
         ellipse of the same radius squashed to `tilt` vertically, and every
         mark sits on that plane. Only the core stands upright. */
      const px = (a, R) => cx + Math.cos(a) * R;
      const py = (a, R) => cy + Math.sin(a) * R * ty;

      for (const ring of RINGS) {
        const R = ring.r * s * RS;
        ctx.lineWidth = ring.w;
        ctx.strokeStyle = `rgba(${rgb},${ring.a * gain})`;
        if (ring.ticks) {
          for (let i = 0; i < ring.ticks; i++) {
            const a = (i / ring.ticks) * Math.PI * 2 + t * 0.00004 * rate;
            const major = i % 4 === 0;
            const len = major ? ring.tick * 1.9 : ring.tick;
            ctx.beginPath();
            ctx.moveTo(px(a, R), py(a, R));
            ctx.lineTo(px(a, R + len), py(a, R + len));
            ctx.stroke();
          }
        } else if (ring.gaps) {
          const step = (Math.PI * 2) / ring.gaps;
          const arc = step * (1 - ring.gapArc);
          for (let i = 0; i < ring.gaps; i++) {
            const a0 = i * step + t * 0.00012 * ring.spin * rate * 12;
            ctx.beginPath();
            ctx.ellipse(cx, cy, R, R * ty, 0, a0, a0 + arc);
            ctx.stroke();
          }
        } else {
          ctx.beginPath(); ctx.ellipse(cx, cy, R, R * ty, 0, 0, Math.PI * 2); ctx.stroke();
        }
      }

      /* the state arc — a crawl at idle, a sweep when the model is working */
      const period = busy ? 800 : 6000;
      const head = ((t % period) / period) * Math.PI * 2;
      const arcR = 0.245 * s * RS;
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = accent;
      ctx.shadowColor = accent;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.ellipse(cx, cy, arcR, arcR * ty, 0, head, head + (busy ? 1.15 : 0.42));
      ctx.stroke();
      ctx.shadowBlur = 0;

      /* drifting motes, on the same plane */
      for (const d of dots) {
        const a = d.a + t * 0.00022 * d.s * rate;
        const R = d.r * s * RS * (1 + Math.sin(t * 0.0006 + d.a) * 0.08);
        ctx.fillStyle = `rgba(${rgb},${0.30 + Math.sin(t * 0.001 + d.a) * 0.18})`;
        ctx.beginPath();
        ctx.arc(px(a, R), py(a, R), 1.15, 0, Math.PI * 2);
        ctx.fill();
      }

      /* core: a soft bloom and the triangle */
      const bloom = ctx.createRadialGradient(cx, cy, 0, cx, cy, 0.09 * s);
      bloom.addColorStop(0, `rgba(${rgb},${0.30 * gain})`);
      bloom.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = bloom;
      ctx.beginPath(); ctx.arc(cx, cy, 0.09 * s, 0, Math.PI * 2); ctx.fill();

      const tri = 0.035 * s;
      const spin = t * 0.00008 * rate;
      ctx.fillStyle = accent;
      ctx.shadowColor = accent;
      ctx.shadowBlur = 16;
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const a = spin + (i / 3) * Math.PI * 2;
        const x = cx + Math.cos(a) * tri, y = cy + Math.sin(a) * tri;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath(); ctx.fill();
      ctx.shadowBlur = 0;
    };

    const loop = setInterval(() => { t += 33; draw(); }, 33);
    draw();
    return () => { clearInterval(loop); if (raf) cancelAnimationFrame(raf); };
  }, [size]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={"Reator — " + state}
      style={{ width: size, height: size, display: "block", ...style }}
      {...rest}
    />
  );
}
