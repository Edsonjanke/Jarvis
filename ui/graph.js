/* graph.js — force-directed knowledge graph on a 2D canvas.
 *
 * Canvas, not SVG: SVG needs a DOM node per element and stalls past ~1,500
 * nodes. Repulsion uses a uniform spatial grid with a hard distance cutoff, so
 * cost stays near-linear in node count instead of O(n^2).
 *
 * Layout is deterministic — seeded by note id — so the same vault produces the
 * same picture every launch.
 */

// ── tuning ────────────────────────────────────────────────────────────────
const REPULSION   = 2000;   // inverse-square strength between nearby nodes
const CUTOFF      = 240;    // world units past which repulsion is simply not computed
const SPRING_LEN  = 58;     // rest length of a link
const SPRING_K    = 0.036;  // link stiffness
const GRAVITY     = 0.0105; // pull toward the centre, keeps the graph on screen
const DAMPING     = 0.83;
const ALPHA_DECAY = 0.014;
const BREATH      = 0.0065; // alpha floor — the graph never fully stops moving
const BREATH_MS   = 11000;  // period of the slow global sway
const PRESETTLE   = 450;    // ticks run before the first paint — a full anneal, not a nudge
const PRESETTLE_MS = 420;   // ...but never block the main thread longer than this
const SEP_CELL    = 2 * 17 + 4;  // collision grid cell: 2 * R_MAX + gap, nothing larger
const DENSITY_N   = 150;    // node count the force constants were tuned against

const PULSE_EVERY = 3400;   // ms between idle pulses
const PULSE_MS    = 1500;   // ms for one pulse to travel its link

const R_MIN = 3.4, R_MAX = 17;
const LABEL_MIN_R  = 6.5;   // below this on-screen radius a node is unlabelled unless hovered
const LABEL_PAD    = 4;
const LABEL_CAP    = 26;    // hard ceiling, so a dense zoom-out never turns to mush
const DIM          = 0.10;  // everything unrelated drops to this when hovering

/* The panels float over the canvas, so the geometric centre of the canvas is
   not the centre of what you can actually see. Everything that centres or
   frames the graph works against this inset box instead. */
const INSETS = { left: 382, right: 308, top: 56, bottom: 132 };
const NARROW = 860;

const TYPE_VARS = {
  client: "--t-client", project: "--t-project", meeting: "--t-meeting",
  invoice: "--t-invoice", person: "--t-person", note: "--t-note",
  reference: "--t-reference",
};

// Deterministic hash → the layout is identical on every load.
function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967296;
}

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

export class Graph {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.nodes = [];
    this.edges = [];
    this.byId = new Map();

    this.scale = 1;
    this.tx = 0;
    this.ty = 0;

    this.hovered = null;
    this.focused = null;
    this.pathIds = new Set();
    this.pathEdges = new Set();
    this.hidden = new Set();     // type names switched off in the filter panel

    this.alpha = 1;
    this.pulses = [];
    this.lastPulse = 0;
    this.running = false;
    this.handlers = {};

    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.colours = this._readColours();

    this._bind();
  }

  on(event, fn) { (this.handlers[event] ||= []).push(fn); return this; }
  _emit(event, ...args) { (this.handlers[event] || []).forEach((fn) => fn(...args)); }

  _readColours() {
    const css = getComputedStyle(document.documentElement);
    const out = { other: css.getPropertyValue("--t-other").trim() || "#7c848f" };
    for (const [type, name] of Object.entries(TYPE_VARS)) {
      out[type] = css.getPropertyValue(name).trim() || out.other;
    }
    out.accent = css.getPropertyValue("--accent").trim() || "#93b4ff";
    out.void = css.getPropertyValue("--void").trim() || "#070809";
    out.ink = css.getPropertyValue("--ink").trim() || "#dfe4ea";
    out.ink3 = css.getPropertyValue("--ink-3").trim() || "#5f6874";
    return out;
  }

  colourFor(type) { return this.colours[type] || this.colours.other; }

  // ── data ────────────────────────────────────────────────────────────────

  setData({ nodes, edges }) {
    const view = this._viewport();
    const n = Math.max(1, nodes.length);
    const spread = Math.min(view.w, view.h) * 0.42;

    this.nodes = nodes.map((raw, i) => {
      // Golden-angle spiral seeded per id: spread, stable, no initial overlap.
      const seed = hash(raw.id);
      const angle = i * 2.399963 + seed * 0.9;
      const radius = Math.sqrt((i + 0.5) / n) * spread;
      return {
        ...raw,
        x: view.cx + Math.cos(angle) * radius,
        y: view.cy + Math.sin(angle) * radius,
        vx: 0, vy: 0,
        r: clamp(R_MIN + Math.sqrt(raw.degree || 0) * 2.35, R_MIN, R_MAX),
        fixed: false,
      };
    });

    this.byId = new Map(this.nodes.map((node) => [node.id, node]));
    this.edges = edges
      .map((e) => ({ a: this.byId.get(e.source), b: this.byId.get(e.target) }))
      .filter((e) => e.a && e.b);

    this.adjacency = new Map(this.nodes.map((node) => [node.id, new Set()]));
    for (const { a, b } of this.edges) {
      this.adjacency.get(a.id).add(b.id);
      this.adjacency.get(b.id).add(a.id);
    }

    /* Anneal before the first paint, but on a wall-clock budget. A fixed tick
       count is fine at 142 notes and freezes the tab for ten seconds at 1,500. */
    this.alpha = 1;
    const budget = this.reduced ? PRESETTLE_MS * 2 : PRESETTLE_MS;
    const deadline = performance.now() + budget;
    const maxTicks = this.reduced ? 900 : PRESETTLE;
    for (let i = 0; i < maxTicks; i++) {
      this._tick(1);
      if ((i & 7) === 7 && performance.now() > deadline) break;
    }
    if (this.reduced) this.alpha = 0;
    this.fit();

    // It keeps settling visibly after the first paint; re-frame once it has.
    if (!this.reduced) setTimeout(() => this.fit(), 2600);
  }

  setHidden(hiddenTypes) {
    this.hidden = new Set(hiddenTypes);
    this.alpha = Math.max(this.alpha, 0.32);   // let the survivors relax
  }

  isVisible(node) { return !this.hidden.has(node.type); }

  setFocus(id) {
    this.focused = id && this.byId.has(id) ? id : null;
    if (!this.focused) this.clearPath();
    this._draw();
  }

  setPath(ids) {
    this.pathIds = new Set(ids);
    this.pathEdges = new Set();
    for (let i = 0; i < ids.length - 1; i++) {
      this.pathEdges.add(this._edgeKey(ids[i], ids[i + 1]));
    }
    this._draw();
  }

  clearPath() { this.pathIds = new Set(); this.pathEdges = new Set(); }

  _edgeKey(a, b) { return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`; }

  centreOn(id) {
    const node = this.byId.get(id);
    if (!node) return;
    const view = this._viewport();
    this.scale = clamp(Math.max(this.scale, 1.35), 0.15, 6);
    this.tx = view.cx - node.x * this.scale;
    this.ty = view.cy - node.y * this.scale;
    this._draw();
  }

  // ── simulation ──────────────────────────────────────────────────────────

  _tick(stepScale = 1) {
    const active = this.nodes.filter((node) => this.isVisible(node));
    if (!active.length) return;

    this.alpha += (BREATH - this.alpha) * ALPHA_DECAY;
    const a = this.alpha * stepScale;

    // Slow sway so a settled graph still reads as alive rather than a JPEG.
    const sway = this.reduced ? 1 : 1 + Math.sin(performance.now() / BREATH_MS * Math.PI * 2) * 0.03;

    // Uniform grid, cell = cutoff. Each node only consults its 3x3 neighbourhood.
    const grid = new Map();
    const cell = CUTOFF;
    for (const node of active) {
      const key = `${Math.floor(node.x / cell)},${Math.floor(node.y / cell)}`;
      (grid.get(key) || grid.set(key, []).get(key)).push(node);
    }

    for (const node of active) {
      const gx = Math.floor(node.x / cell), gy = Math.floor(node.y / cell);
      for (let ox = -1; ox <= 1; ox++) {
        for (let oy = -1; oy <= 1; oy++) {
          const bucket = grid.get(`${gx + ox},${gy + oy}`);
          if (!bucket) continue;
          for (const other of bucket) {
            if (other === node) continue;
            let dx = node.x - other.x, dy = node.y - other.y;
            let d2 = dx * dx + dy * dy;
            if (d2 > CUTOFF * CUTOFF) continue;
            if (d2 < 0.01) {                       // exactly coincident: nudge apart
              dx = (hash(node.id) - 0.5) * 0.5;
              dy = (hash(other.id) - 0.5) * 0.5;
              d2 = dx * dx + dy * dy + 0.01;
            }
            const d = Math.sqrt(d2);
            // Weight by radius: a hub is physically bigger and must claim more
            // room, or the most-connected nodes pile into an unreadable blob.
            const mass = (node.r * other.r) / 36;
            const force = (REPULSION * a * mass) / d2;
            node.vx += (dx / d) * force;
            node.vy += (dy / d) * force;
          }
        }
      }
    }

    const rest = SPRING_LEN * sway;
    for (const { a: p, b: q } of this.edges) {
      if (!this.isVisible(p) || !this.isVisible(q)) continue;
      const dx = q.x - p.x, dy = q.y - p.y;
      const d = Math.hypot(dx, dy) || 0.01;
      const force = (d - rest) * SPRING_K * a;
      const fx = (dx / d) * force, fy = (dy / d) * force;
      p.vx += fx; p.vy += fy;
      q.vx -= fx; q.vy -= fy;
    }

    /* Gravity has to weaken as the graph grows, or a big vault is squeezed into
       the same area, density climbs, and every node's cutoff neighbourhood
       fills up — which turns the grid's near-linear cost superlinear. Letting
       the layout spread with sqrt(n) keeps nodes-per-cell roughly constant. */
    const gravity = GRAVITY * Math.sqrt(DENSITY_N / Math.max(DENSITY_N, active.length));
    const view = this._viewport();
    for (const node of active) {
      node.vx += (view.cx - node.x) * gravity * a;
      node.vy += (view.cy - node.y) * gravity * a;
      if (node.fixed) { node.vx = 0; node.vy = 0; continue; }
      node.vx *= DAMPING;
      node.vy *= DAMPING;
      node.x += node.vx;
      node.y += node.vy;
    }

    this._separate(active);
  }

  /* Hard separation: circles are not allowed to overlap, full stop. Forces
     alone leave hubs sitting on each other, which is exactly the case where
     you most need to read the labels. Two passes converges in practice.
     Uses its own fine grid — reusing the repulsion grid meant scanning a
     720px neighbourhood to answer a 37px question, and it dominated the tick. */
  _separate(active) {
    const GAP = 2.5;
    const cell = SEP_CELL;
    const grid = new Map();
    for (const node of active) {
      const key = `${Math.floor(node.x / cell)},${Math.floor(node.y / cell)}`;
      let bucket = grid.get(key);
      if (!bucket) { bucket = []; grid.set(key, bucket); }
      bucket.push(node);
    }
    for (let pass = 0; pass < 2; pass++) {
      for (const node of active) {
        const gx = Math.floor(node.x / cell), gy = Math.floor(node.y / cell);
        for (let ox = -1; ox <= 1; ox++) {
          for (let oy = -1; oy <= 1; oy++) {
            const bucket = grid.get(`${gx + ox},${gy + oy}`);
            if (!bucket) continue;
            for (const other of bucket) {
              if (other === node) continue;
              const min = node.r + other.r + GAP;
              const dx = other.x - node.x, dy = other.y - node.y;
              const d2 = dx * dx + dy * dy;
              if (d2 >= min * min || d2 === 0) continue;
              const d = Math.sqrt(d2);
              const shift = ((min - d) / d) * 0.5;
              const px = dx * shift, py = dy * shift;
              if (!other.fixed) { other.x += px; other.y += py; }
              if (!node.fixed) { node.x -= px; node.y -= py; }
            }
          }
        }
      }
    }
  }

  // ── rendering ───────────────────────────────────────────────────────────

  _size() {
    return { width: this.canvas.clientWidth || 1, height: this.canvas.clientHeight || 1 };
  }

  /* The rectangle not covered by the floating panels. */
  _viewport() {
    const { width, height } = this._size();
    if (width < NARROW) return { x: 0, y: 0, w: width, h: height * 0.5, cx: width / 2, cy: height * 0.25 };
    const x = INSETS.left;
    const y = INSETS.top;
    const w = Math.max(160, width - INSETS.left - INSETS.right);
    const h = Math.max(160, height - INSETS.top - INSETS.bottom);
    return { x, y, w, h, cx: x + w / 2, cy: y + h / 2 };
  }

  /* Frame the whole graph inside the visible rectangle. */
  fit(margin = 46) {
    const shown = this.nodes.filter((node) => this.isVisible(node));
    if (!shown.length) return;

    // Trim the extreme 1% each way. One straggler mid-flight should not shrink
    // the whole graph to a dot; it catches up within a second either way.
    const q = (values, p) => values[clamp(Math.round((values.length - 1) * p), 0, values.length - 1)];
    const xs = shown.map((n) => n.x).sort((a, b) => a - b);
    const ys = shown.map((n) => n.y).sort((a, b) => a - b);
    const pad = Math.max(...shown.map((n) => n.r));
    const minX = q(xs, 0.01) - pad, maxX = q(xs, 0.99) + pad;
    const minY = q(ys, 0.01) - pad, maxY = q(ys, 0.99) + pad;

    const view = this._viewport();
    const sx = (view.w - margin * 2) / Math.max(1, maxX - minX);
    const sy = (view.h - margin * 2) / Math.max(1, maxY - minY);
    this.scale = clamp(Math.min(sx, sy), 0.15, 2.4);
    this.tx = view.cx - ((minX + maxX) / 2) * this.scale;
    this.ty = view.cy - ((minY + maxY) / 2) * this.scale;
    this._draw();
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const { width, height } = this._size();
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._draw();
  }

  _toWorld(px, py) {
    return { x: (px - this.tx) / this.scale, y: (py - this.ty) / this.scale };
  }

  _relatedTo(id) {
    const set = this.adjacency.get(id);
    return set ? set : new Set();
  }

  _draw() {
    const ctx = this.ctx;
    const { width, height } = this._size();
    ctx.fillStyle = this.colours.void;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(this.tx, this.ty);
    ctx.scale(this.scale, this.scale);

    const spotlight = this.hovered || this.focused;
    const lit = spotlight ? this._relatedTo(spotlight) : null;
    const isLit = (id) => !spotlight || id === spotlight || lit.has(id);

    // ── edges ──
    ctx.lineWidth = 1 / this.scale;
    for (const { a, b } of this.edges) {
      if (!this.isVisible(a) || !this.isVisible(b)) continue;
      const onPath = this.pathEdges.has(this._edgeKey(a.id, b.id));
      const touched = spotlight && (a.id === spotlight || b.id === spotlight);
      let alpha = 0.055;
      let colour = "255,255,255";
      if (onPath) { alpha = 0.95; colour = "147,180,255"; }
      else if (touched) { alpha = 0.34; colour = "147,180,255"; }
      else if (spotlight) { alpha = 0.055 * DIM; }
      ctx.strokeStyle = `rgba(${colour},${alpha})`;
      ctx.lineWidth = (onPath ? 1.6 : 1) / this.scale;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    // ── idle pulses: a faint dot walking a random link ──
    for (const pulse of this.pulses) {
      const { a, b } = pulse.edge;
      if (!this.isVisible(a) || !this.isVisible(b)) continue;
      const t = pulse.t;
      const fade = Math.sin(t * Math.PI);              // in and out, no pop
      ctx.fillStyle = `rgba(147,180,255,${0.5 * fade * (spotlight ? DIM : 1)})`;
      ctx.beginPath();
      ctx.arc(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 1.9 / this.scale, 0, Math.PI * 2);
      ctx.fill();
    }

    // ── nodes ──
    for (const node of this.nodes) {
      if (!this.isVisible(node)) continue;
      const hot = node.id === this.hovered;
      const focus = node.id === this.focused;
      const onPath = this.pathIds.has(node.id);
      const alpha = isLit(node.id) || onPath ? 1 : DIM;
      const r = node.r * (hot ? 1.32 : 1);

      ctx.globalAlpha = alpha;
      if (hot || focus) {
        // Glow lives here and nowhere else — it marks state, not decoration.
        ctx.shadowColor = this.colours.accent;
        ctx.shadowBlur = (hot ? 16 : 9) / this.scale;
      }
      ctx.fillStyle = this.colourFor(node.type);
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      if (focus || onPath) {
        ctx.strokeStyle = this.colours.accent;
        ctx.lineWidth = (focus ? 2 : 1.4) / this.scale;
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 4 / this.scale, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    ctx.restore();
    this._drawLabels(spotlight, isLit);
  }

  /* Most-connected first, and any label whose box hits one already placed is
     dropped. Without this the hub cluster turns to mush. */
  _drawLabels(spotlight, isLit) {
    const ctx = this.ctx;
    const { width, height } = this._size();
    ctx.font = "11px " + getComputedStyle(document.body).getPropertyValue("--mono");
    ctx.textBaseline = "middle";

    const candidates = this.nodes
      .filter((node) => this.isVisible(node))
      .sort((a, b) => b.r - a.r);

    /* Obstacles are other labels plus the nodes big enough to matter. Treating
       every 3px dot as an obstacle sounds right and in practice suppresses
       every label in the cluster — the dark plate behind the text covers a
       small dot acceptably, but never another label or a hub. */
    const obstacles = [];
    for (const node of candidates) {
      const sr = node.r * this.scale;
      if (sr < 6) continue;
      obstacles.push({
        x: node.x * this.scale + this.tx - sr,
        y: node.y * this.scale + this.ty - sr,
        w: sr * 2, h: sr * 2,
      });
    }
    const hits = (box) => obstacles.some((p) =>
      box.x < p.x + p.w && box.x + box.w > p.x && box.y < p.y + p.h && box.y + box.h > p.y);

    // The biggest hubs always get a label. They are the ones you scan for, and
    // they are also the ones most likely to be walled in by their own links.
    const alwaysLabel = new Set(candidates.slice(0, 5).map((n) => n.id));

    let drawn = 0;
    for (const node of candidates) {
      const hot = node.id === this.hovered;
      const focus = node.id === this.focused;
      const onPath = this.pathIds.has(node.id);
      const forced = hot || focus || onPath || alwaysLabel.has(node.id);
      if (!forced && (node.r * this.scale < LABEL_MIN_R || drawn >= LABEL_CAP)) continue;

      const sx = node.x * this.scale + this.tx;
      const sy = node.y * this.scale + this.ty;
      if (sx < -120 || sx > width + 120 || sy < -30 || sy > height + 30) continue;

      const text = node.title.length > 30 ? node.title.slice(0, 29) + "…" : node.title;
      const w = ctx.measureText(text).width;
      const sr = node.r * this.scale;

      // Eight slots around the node; first clear one wins, none clear and it
      // is skipped unless the node is forced.
      const off = sr + 8;
      const slots = [
        [sx + off, sy],
        [sx - off - w, sy],
        [sx - w / 2, sy + off + 5],
        [sx - w / 2, sy - off - 5],
        [sx + off * 0.72, sy - off * 0.72 - 4],
        [sx - off * 0.72 - w, sy - off * 0.72 - 4],
        [sx + off * 0.72, sy + off * 0.72 + 4],
        [sx - off * 0.72 - w, sy + off * 0.72 + 4],
      ];
      let box = null;
      for (const [x, y] of slots) {
        const trial = { x: x - LABEL_PAD, y: y - 8, w: w + LABEL_PAD * 2, h: 16 };
        if (!hits(trial)) { box = trial; break; }
      }
      if (!box) {
        if (!forced) continue;
        box = { x: sx + sr + 7 - LABEL_PAD, y: sy - 8, w: w + LABEL_PAD * 2, h: 16 };
      }

      obstacles.push(box);
      drawn++;
      const x = box.x + LABEL_PAD;
      const y = box.y + 8;

      const dim = spotlight && !isLit(node.id) && !onPath;
      ctx.globalAlpha = dim ? DIM : 1;
      // A dark plate behind the text so labels stay readable over dense edges.
      ctx.fillStyle = "rgba(7,8,9,0.72)";
      ctx.fillRect(box.x, box.y, box.w, box.h);
      ctx.fillStyle = hot || focus || onPath ? this.colours.accent : this.colours.ink3;
      ctx.fillText(text, x, y + 0.5);
      ctx.globalAlpha = 1;
    }
  }

  // ── loop ────────────────────────────────────────────────────────────────

  start() {
    if (this.running) return;
    this.running = true;
    let last = performance.now();
    const frame = (now) => {
      if (!this.running) return;
      const dt = Math.min(64, now - last);
      last = now;

      this._tick();

      if (!this.reduced) {
        if (now - this.lastPulse > PULSE_EVERY && this.edges.length) {
          const visible = this.edges.filter((e) => this.isVisible(e.a) && this.isVisible(e.b));
          if (visible.length) {
            this.pulses.push({ edge: visible[Math.floor(Math.random() * visible.length)], t: 0 });
          }
          this.lastPulse = now;
        }
        for (const pulse of this.pulses) pulse.t += dt / PULSE_MS;
        this.pulses = this.pulses.filter((p) => p.t < 1);
      }

      this._draw();
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  stop() { this.running = false; }

  // ── input ───────────────────────────────────────────────────────────────

  _nodeAt(px, py) {
    const { x, y } = this._toWorld(px, py);
    let best = null, bestD = Infinity;
    for (const node of this.nodes) {
      if (!this.isVisible(node)) continue;
      const d = Math.hypot(node.x - x, node.y - y);
      const reach = Math.max(node.r + 5 / this.scale, 9 / this.scale);
      if (d < reach && d < bestD) { best = node; bestD = d; }
    }
    return best;
  }

  _bind() {
    const canvas = this.canvas;
    let panning = false, draggingNode = null;
    let lastX = 0, lastY = 0, movedBy = 0;

    canvas.addEventListener("pointerdown", (ev) => {
      canvas.setPointerCapture(ev.pointerId);
      lastX = ev.offsetX; lastY = ev.offsetY; movedBy = 0;
      const node = this._nodeAt(ev.offsetX, ev.offsetY);
      if (node) { draggingNode = node; node.fixed = true; }
      else { panning = true; canvas.classList.add("dragging"); }
    });

    canvas.addEventListener("pointermove", (ev) => {
      const dx = ev.offsetX - lastX, dy = ev.offsetY - lastY;
      lastX = ev.offsetX; lastY = ev.offsetY;
      movedBy += Math.abs(dx) + Math.abs(dy);

      if (draggingNode) {
        draggingNode.x += dx / this.scale;
        draggingNode.y += dy / this.scale;
        this.alpha = Math.max(this.alpha, 0.12);
        return;
      }
      if (panning) { this.tx += dx; this.ty += dy; return; }

      const node = this._nodeAt(ev.offsetX, ev.offsetY);
      const id = node ? node.id : null;
      if (id !== this.hovered) {
        this.hovered = id;
        canvas.classList.toggle("over-node", !!id);
        this._emit("hover", node);
        this._draw();
      }
    });

    const release = (ev) => {
      if (draggingNode) { draggingNode.fixed = false; draggingNode = null; }
      if (panning) { panning = false; canvas.classList.remove("dragging"); }
      try { canvas.releasePointerCapture(ev.pointerId); } catch { /* already gone */ }
    };
    canvas.addEventListener("pointerup", (ev) => {
      const wasClick = movedBy < 5;
      const node = this._nodeAt(ev.offsetX, ev.offsetY);
      release(ev);
      if (!wasClick) return;
      if (node) this._emit("select", node, ev.shiftKey);
      else this._emit("select", null, false);
    });
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("pointerleave", () => {
      if (this.hovered) { this.hovered = null; this._emit("hover", null); this._draw(); }
    });

    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const factor = Math.exp(-ev.deltaY * 0.0016);
      const next = clamp(this.scale * factor, 0.15, 6);
      const k = next / this.scale;
      this.tx = ev.offsetX - (ev.offsetX - this.tx) * k;
      this.ty = ev.offsetY - (ev.offsetY - this.ty) * k;
      this.scale = next;
      this._draw();
    }, { passive: false });

    window.addEventListener("resize", () => this.resize());
  }
}
