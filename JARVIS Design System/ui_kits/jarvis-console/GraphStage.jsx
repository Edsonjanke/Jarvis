/* GraphStage — the canvas graph, ported from Jarvis/ui/graph.js.
   Same forces, same colours, same label placement, same dim/glow rules;
   the spatial-grid optimisation is dropped because 44 nodes do not need it. */
const { useRef, useEffect } = React;

const REPULSION = 2000, CUTOFF = 240, SPRING_LEN = 58, SPRING_K = 0.036;
const GRAVITY = 0.0105, DAMPING = 0.83, ALPHA_DECAY = 0.014, BREATH = 0.0065;
const BREATH_MS = 11000, PRESETTLE = 450, R_MIN = 3.4, R_MAX = 17;
const LABEL_MIN_R = 6.5, LABEL_PAD = 4, LABEL_CAP = 26, DIM = 0.1;
const PULSE_EVERY = 3400, PULSE_MS = 1500;
const INSETS = { left: 300, right: 300, top: 130, bottom: 150 };
const TYPES = ["client", "project", "meeting", "invoice", "person", "note", "reference"];

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967296;
}
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

function GraphStage({ nodes, edges, hidden, focused, pathIds, onSelect, onHover, opacity = 1, sparseLabels = false }) {
  const ref = useRef(null);
  const sim = useRef(null);
  const props = useRef({});
  props.current = { hidden, focused, pathIds, onSelect, onHover, sparseLabels };

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d", { alpha: true });
    const css = getComputedStyle(document.documentElement);
    const colour = { other: css.getPropertyValue("--t-other").trim() };
    TYPES.forEach((t) => { colour[t] = css.getPropertyValue("--t-" + t).trim(); });
    const accent = css.getPropertyValue("--accent").trim();
    const accentRgb = (css.getPropertyValue("--accent-rgb").trim() || "60,232,143").replace(/\s/g, "");
    const plateC = css.getPropertyValue("--plate").trim() || "rgba(4,9,7,.74)";
    const ink3 = css.getPropertyValue("--ink-3").trim();
    const colourFor = (t) => colour[t] || colour.other;

    /* Nodes are drawn as lit spheres, not flat dots: a wide halo, a body whose
       highlight sits up and to the left, and a cross flare on the hubs. Hue is
       still taxonomy and nothing else — only the rendering changed. */
    const rgbOf = (hex) => {
      const h = hex.replace("#", "");
      const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
      return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
    };
    const mix = (hex, target, k) => {
      const [r, g, b] = rgbOf(hex);
      return "rgb(" + Math.round(r + (target - r) * k) + "," + Math.round(g + (target - g) * k) + "," + Math.round(b + (target - b) * k) + ")";
    };
    const soft = (hex, a) => {
      const [r, g, b] = rgbOf(hex);
      return "rgba(" + r + "," + g + "," + b + "," + a + ")";
    };

    const size = () => ({ w: canvas.clientWidth || 1, h: canvas.clientHeight || 1 });
    const view = () => {
      const { w, h } = size();
      const x = INSETS.left, y = INSETS.top;
      const vw = Math.max(160, w - INSETS.left - INSETS.right);
      const vh = Math.max(160, h - INSETS.top - INSETS.bottom);
      return { x, y, w: vw, h: vh, cx: x + vw / 2, cy: y + vh / 2 };
    };

    const v = view();
    const n = Math.max(1, nodes.length);
    const spread = Math.min(v.w, v.h) * 0.42;
    const pts = nodes.map((raw, i) => {
      const seed = hash(raw.id);
      const angle = i * 2.399963 + seed * 0.9;
      const radius = Math.sqrt((i + 0.5) / n) * spread;
      return {
        ...raw,
        x: v.cx + Math.cos(angle) * radius, y: v.cy + Math.sin(angle) * radius,
        vx: 0, vy: 0, fixed: false,
        r: clamp(R_MIN + Math.sqrt(raw.degree || 0) * 2.35, R_MIN, R_MAX),
      };
    });
    const byId = new Map(pts.map((p) => [p.id, p]));
    const links = edges.map((e) => ({ a: byId.get(e.source), b: byId.get(e.target) })).filter((e) => e.a && e.b);
    const state = { pts, links, byId, alpha: 1, scale: 1, tx: 0, ty: 0, hovered: null, pulses: [], lastPulse: 0 };
    sim.current = state;

    const visible = (p) => !(props.current.hidden || new Set()).has(p.type);
    const edgeKey = (a, b) => (a < b ? a + "\u0000" + b : b + "\u0000" + a);

    function tick(stepScale) {
      const active = state.pts.filter(visible);
      if (!active.length) return;
      state.alpha += (BREATH - state.alpha) * ALPHA_DECAY;
      const a = state.alpha * (stepScale || 1);
      const sway = 1 + Math.sin((performance.now() / BREATH_MS) * Math.PI * 2) * 0.03;

      for (let i = 0; i < active.length; i++) {
        for (let j = i + 1; j < active.length; j++) {
          const p = active[i], q = active[j];
          let dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy;
          if (d2 > CUTOFF * CUTOFF) continue;
          if (d2 < 0.01) { dx = (hash(p.id) - 0.5) * 0.5; dy = (hash(q.id) - 0.5) * 0.5; d2 = dx * dx + dy * dy + 0.01; }
          const d = Math.sqrt(d2);
          const force = (REPULSION * a * ((p.r * q.r) / 36)) / d2;
          p.vx += (dx / d) * force; p.vy += (dy / d) * force;
          q.vx -= (dx / d) * force; q.vy -= (dy / d) * force;
        }
      }
      const rest = SPRING_LEN * sway;
      for (const { a: p, b: q } of state.links) {
        if (!visible(p) || !visible(q)) continue;
        const dx = q.x - p.x, dy = q.y - p.y;
        const d = Math.hypot(dx, dy) || 0.01;
        const f = (d - rest) * SPRING_K * a;
        p.vx += (dx / d) * f; p.vy += (dy / d) * f;
        q.vx -= (dx / d) * f; q.vy -= (dy / d) * f;
      }
      const c = view();
      for (const p of active) {
        p.vx += (c.cx - p.x) * GRAVITY * a;
        p.vy += (c.cy - p.y) * GRAVITY * a;
        if (p.fixed) { p.vx = 0; p.vy = 0; continue; }
        p.vx *= DAMPING; p.vy *= DAMPING;
        p.x += p.vx; p.y += p.vy;
      }
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 0; i < active.length; i++) {
          for (let j = i + 1; j < active.length; j++) {
            const p = active[i], q = active[j];
            const min = p.r + q.r + 2.5;
            const dx = q.x - p.x, dy = q.y - p.y, d2 = dx * dx + dy * dy;
            if (d2 >= min * min || d2 === 0) continue;
            const d = Math.sqrt(d2), shift = ((min - d) / d) * 0.5;
            if (!q.fixed) { q.x += dx * shift; q.y += dy * shift; }
            if (!p.fixed) { p.x -= dx * shift; p.y -= dy * shift; }
          }
        }
      }
    }

    function fit(margin) {
      const shown = state.pts.filter(visible);
      if (!shown.length) return;
      const q = (vals, p) => vals[clamp(Math.round((vals.length - 1) * p), 0, vals.length - 1)];
      const xs = shown.map((p) => p.x).sort((a, b) => a - b);
      const ys = shown.map((p) => p.y).sort((a, b) => a - b);
      const pad = Math.max(...shown.map((p) => p.r));
      const minX = q(xs, 0.01) - pad, maxX = q(xs, 0.99) + pad;
      const minY = q(ys, 0.01) - pad, maxY = q(ys, 0.99) + pad;
      const c = view();
      const sx = (c.w - margin * 2) / Math.max(1, maxX - minX);
      const sy = (c.h - margin * 2) / Math.max(1, maxY - minY);
      state.scale = clamp(Math.min(sx, sy), 0.15, 2.4);
      state.tx = c.cx - ((minX + maxX) / 2) * state.scale;
      state.ty = c.cy - ((minY + maxY) / 2) * state.scale;
    }

    function draw() {
      const { w, h } = size();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== Math.round(w * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.save();
      ctx.translate(state.tx, state.ty);
      ctx.scale(state.scale, state.scale);

      const path = props.current.pathIds || new Set();
      const pathEdges = new Set();
      const list = Array.from(path);
      for (let i = 0; i < list.length - 1; i++) pathEdges.add(edgeKey(list[i], list[i + 1]));
      const spotlight = state.hovered || props.current.focused;
      const lit = new Set();
      if (spotlight) {
        for (const { a, b } of state.links) {
          if (a.id === spotlight) lit.add(b.id);
          if (b.id === spotlight) lit.add(a.id);
        }
      }
      const isLit = (id) => !spotlight || id === spotlight || lit.has(id);

      for (const { a, b } of state.links) {
        if (!visible(a) || !visible(b)) continue;
        const onPath = pathEdges.has(edgeKey(a.id, b.id));
        const touched = spotlight && (a.id === spotlight || b.id === spotlight);
        let alpha = 0.14, rgb = accentRgb;
        if (onPath) { alpha = 0.95; rgb = accentRgb; }
        else if (touched) { alpha = 0.40; rgb = accentRgb; }
        else if (spotlight) { alpha = 0.14 * DIM; }
        ctx.strokeStyle = "rgba(" + rgb + "," + alpha + ")";
        ctx.lineWidth = (onPath ? 1.6 : 1) / state.scale;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }

      for (const pulse of state.pulses) {
        const { a, b } = pulse.edge;
        if (!visible(a) || !visible(b)) continue;
        const fade = Math.sin(pulse.t * Math.PI);
        ctx.fillStyle = "rgba(" + accentRgb + "," + 0.5 * fade * (spotlight ? DIM : 1) + ")";
        ctx.beginPath();
        ctx.arc(a.x + (b.x - a.x) * pulse.t, a.y + (b.y - a.y) * pulse.t, 1.9 / state.scale, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.globalCompositeOperation = "lighter";
      for (const p of state.pts) {
        if (!visible(p)) continue;
        const hot = p.id === state.hovered;
        const focus = p.id === props.current.focused;
        const onPath = path.has(p.id);
        const dim = isLit(p.id) || onPath ? 1 : DIM;
        const r = p.r * (hot ? 1.32 : 1);
        const col = colourFor(p.type);
        const halo = ctx.createRadialGradient(p.x, p.y, r * 0.5, p.x, p.y, r * (hot ? 3.0 : 2.1));
        halo.addColorStop(0, soft(col, 0.20 * dim));
        halo.addColorStop(0.42, soft(col, 0.06 * dim));
        halo.addColorStop(1, soft(col, 0));
        ctx.fillStyle = halo;
        ctx.beginPath(); ctx.arc(p.x, p.y, r * (hot ? 3.0 : 2.1), 0, Math.PI * 2); ctx.fill();

        /* the four-point flare the biggest hubs carry */
        if (p.r > 11 || hot || focus) {
          const reach = r * (hot ? 4.2 : 3.2);
          ctx.lineWidth = Math.max(0.5, r * 0.10) / state.scale;
          for (const [dx, dy] of [[1, 0], [0, 1]]) {
            const flare = ctx.createLinearGradient(p.x - dx * reach, p.y - dy * reach, p.x + dx * reach, p.y + dy * reach);
            flare.addColorStop(0, soft(col, 0));
            flare.addColorStop(0.5, soft(col, 0.18 * dim));
            flare.addColorStop(1, soft(col, 0));
            ctx.strokeStyle = flare;
            ctx.beginPath();
            ctx.moveTo(p.x - dx * reach, p.y - dy * reach);
            ctx.lineTo(p.x + dx * reach, p.y + dy * reach);
            ctx.stroke();
          }
        }
      }
      ctx.globalCompositeOperation = "source-over";

      for (const p of state.pts) {
        if (!visible(p)) continue;
        const hot = p.id === state.hovered;
        const focus = p.id === props.current.focused;
        const onPath = path.has(p.id);
        ctx.globalAlpha = isLit(p.id) || onPath ? 1 : DIM;
        const r = p.r * (hot ? 1.32 : 1);
        const col = colourFor(p.type);
        const body = ctx.createRadialGradient(p.x - r * 0.34, p.y - r * 0.38, r * 0.08, p.x, p.y, r);
        body.addColorStop(0, mix(col, 255, 0.78));
        body.addColorStop(0.38, mix(col, 255, 0.16));
        body.addColorStop(1, mix(col, 0, 0.34));
        ctx.fillStyle = body;
        ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
        if (focus || onPath) {
          ctx.strokeStyle = accent;
          ctx.lineWidth = (focus ? 2 : 1.4) / state.scale;
          ctx.beginPath(); ctx.arc(p.x, p.y, r + 4 / state.scale, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
      ctx.restore();
      labels(spotlight, isLit, path);
    }

    function labels(spotlight, isLit, path) {
      const { w, h } = size();
      ctx.font = "11px " + getComputedStyle(document.body).getPropertyValue("--font-mono");
      ctx.textBaseline = "middle";
      const candidates = state.pts.filter(visible).sort((a, b) => b.r - a.r);
      const obstacles = [];
      for (const p of candidates) {
        const sr = p.r * state.scale;
        if (sr < 6) continue;
        obstacles.push({ x: p.x * state.scale + state.tx - sr, y: p.y * state.scale + state.ty - sr, w: sr * 2, h: sr * 2 });
      }
      const hits = (box) => obstacles.some((o) => box.x < o.x + o.w && box.x + box.w > o.x && box.y < o.y + o.h && box.y + box.h > o.y);
      const always = new Set(candidates.slice(0, 5).map((p) => p.id));
      let drawn = 0;
      for (const p of candidates) {
        const hot = p.id === state.hovered;
        const focus = p.id === props.current.focused;
        const onPath = path.has(p.id);
        const forced = hot || focus || onPath || (!props.current.sparseLabels && always.has(p.id));
        if (!forced && props.current.sparseLabels) continue;
        if (!forced && (p.r * state.scale < LABEL_MIN_R || drawn >= LABEL_CAP)) continue;
        const sx = p.x * state.scale + state.tx, sy = p.y * state.scale + state.ty;
        if (sx < -120 || sx > w + 120 || sy < -30 || sy > h + 30) continue;
        const text = p.title.length > 30 ? p.title.slice(0, 29) + "…" : p.title;
        const tw = ctx.measureText(text).width;
        const sr = p.r * state.scale, off = sr + 8;
        const slots = [
          [sx + off, sy], [sx - off - tw, sy], [sx - tw / 2, sy + off + 5], [sx - tw / 2, sy - off - 5],
          [sx + off * 0.72, sy - off * 0.72 - 4], [sx - off * 0.72 - tw, sy - off * 0.72 - 4],
          [sx + off * 0.72, sy + off * 0.72 + 4], [sx - off * 0.72 - tw, sy + off * 0.72 + 4],
        ];
        let box = null;
        for (const [x, y] of slots) {
          const trial = { x: x - LABEL_PAD, y: y - 8, w: tw + LABEL_PAD * 2, h: 16 };
          if (!hits(trial)) { box = trial; break; }
        }
        if (!box) { if (!forced) continue; box = { x: sx + sr + 7 - LABEL_PAD, y: sy - 8, w: tw + LABEL_PAD * 2, h: 16 }; }
        obstacles.push(box); drawn++;
        ctx.globalAlpha = spotlight && !isLit(p.id) && !onPath ? DIM : 1;
        ctx.fillStyle = plateC;
        ctx.fillRect(box.x, box.y, box.w, box.h);
        ctx.fillStyle = hot || focus || onPath ? accent : ink3;
        ctx.fillText(text, box.x + LABEL_PAD, box.y + 8.5);
        ctx.globalAlpha = 1;
      }
    }

    for (let i = 0; i < PRESETTLE; i++) tick(1);
    fit(46);
    draw();

    /* The product drives this with requestAnimationFrame. Here it runs on the
       same 33ms timer the reactor uses, for the same reason the reactor gives:
       RAF stops dead when the frame is not on screen, and this kit is often
       previewed inside one that isn't. */
    let last = performance.now();
    const frame = () => {
      const now = performance.now();
      const dt = Math.min(64, now - last); last = now;
      tick(1);
      if (now - state.lastPulse > PULSE_EVERY && state.links.length) {
        const vis = state.links.filter((e) => visible(e.a) && visible(e.b));
        if (vis.length) state.pulses.push({ edge: vis[Math.floor(Math.random() * vis.length)], t: 0 });
        state.lastPulse = now;
      }
      for (const p of state.pulses) p.t += dt / PULSE_MS;
      state.pulses = state.pulses.filter((p) => p.t < 1);
      draw();
    };
    const loop = setInterval(frame, 33);

    const nodeAt = (px, py) => {
      const x = (px - state.tx) / state.scale, y = (py - state.ty) / state.scale;
      let best = null, bestD = Infinity;
      for (const p of state.pts) {
        if (!visible(p)) continue;
        const d = Math.hypot(p.x - x, p.y - y);
        const reach = Math.max(p.r + 5 / state.scale, 9 / state.scale);
        if (d < reach && d < bestD) { best = p; bestD = d; }
      }
      return best;
    };

    let panning = false, dragging = null, lastX = 0, lastY = 0, moved = 0;
    const down = (ev) => {
      canvas.setPointerCapture(ev.pointerId);
      lastX = ev.offsetX; lastY = ev.offsetY; moved = 0;
      const p = nodeAt(ev.offsetX, ev.offsetY);
      if (p) { dragging = p; p.fixed = true; } else { panning = true; canvas.style.cursor = "grabbing"; }
    };
    const move = (ev) => {
      const dx = ev.offsetX - lastX, dy = ev.offsetY - lastY;
      lastX = ev.offsetX; lastY = ev.offsetY; moved += Math.abs(dx) + Math.abs(dy);
      if (dragging) { dragging.x += dx / state.scale; dragging.y += dy / state.scale; state.alpha = Math.max(state.alpha, 0.12); return; }
      if (panning) { state.tx += dx; state.ty += dy; return; }
      const p = nodeAt(ev.offsetX, ev.offsetY);
      const id = p ? p.id : null;
      if (id !== state.hovered) {
        state.hovered = id;
        canvas.style.cursor = id ? "pointer" : "grab";
        if (props.current.onHover) props.current.onHover(p);
      }
    };
    const up = (ev) => {
      const wasClick = moved < 5;
      const p = nodeAt(ev.offsetX, ev.offsetY);
      if (dragging) { dragging.fixed = false; dragging = null; }
      if (panning) { panning = false; canvas.style.cursor = "grab"; }
      try { canvas.releasePointerCapture(ev.pointerId); } catch (e) { /* gone */ }
      if (!wasClick) return;
      if (props.current.onSelect) props.current.onSelect(p || null, ev.shiftKey);
    };
    const wheel = (ev) => {
      ev.preventDefault();
      const factor = Math.exp(-ev.deltaY * 0.0016);
      const next = clamp(state.scale * factor, 0.15, 6);
      const k = next / state.scale;
      state.tx = ev.offsetX - (ev.offsetX - state.tx) * k;
      state.ty = ev.offsetY - (ev.offsetY - state.ty) * k;
      state.scale = next;
    };
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("wheel", wheel, { passive: false });
    const onResize = () => fit(46);
    window.addEventListener("resize", onResize);

    return () => {
      clearInterval(loop);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("wheel", wheel);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-label="Knowledge graph. Use the inspector panel to read notes."
      style={{ position: "fixed", inset: 0, width: "100%", height: "100%", display: "block", touchAction: "none", cursor: "grab", opacity }}
    />
  );
}

Object.assign(window, { GraphStage });
