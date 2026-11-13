/* GD&T Drafter — browser editor. The server renders; this file edits the document.
   Coordinates: "paper" = sheet millimetres, y up. "model" = a view's own 2-D
   coordinates in model millimetres (paper = origin + scale * model). */
(() => {
  "use strict";

  const PX = 96 / 25.4;            // CSS px per mm at zoom 1
  const DIM_GAP0 = 10, DIM_STEP = 8;
  const BOX = 7, TRI = 3.6;        // datum symbol sizes (paper mm), as in render.py
  const SNAP_PX = 9;               // pick radius on screen
  const ORTHO = ["front", "top", "bottom", "left", "right", "rear"];

  const CHARS = [
    ["position", "Position"], ["flatness", "Flatness"], ["straightness", "Straightness"],
    ["circularity", "Circularity"], ["cylindricity", "Cylindricity"], ["profile_line", "Profile of a line"],
    ["profile_surface", "Profile of a surface"], ["parallelism", "Parallelism"], ["perpendicularity", "Perpendicularity"],
    ["angularity", "Angularity"], ["concentricity", "Concentricity / coaxiality"], ["symmetry", "Symmetry"],
    ["circular_runout", "Circular runout"], ["total_runout", "Total runout"],
  ];
  const CHAR_NAME = Object.fromEntries(CHARS);
  const CHAR_GLYPH = {
    position: "⌖", flatness: "⏥", straightness: "⏤", circularity: "○", cylindricity: "⌭", profile_line: "⌒",
    profile_surface: "⌓", parallelism: "∥", perpendicularity: "⟂", angularity: "∠", concentricity: "◎",
    symmetry: "⌯", circular_runout: "↗", total_runout: "⌰",
  };
  const NO_DATUM = new Set(["flatness", "straightness", "circularity", "cylindricity"]);
  const TOL_MODES = [
    ["none", "General (from note)"], ["basic", "Basic / theoretically exact"], ["sym", "Symmetric ±"],
    ["dev", "Deviations (+ / −)"], ["limits", "Limits"], ["ref", "Reference ( )"],
  ];
  const TITLE_FIELDS = [
    ["title", "Title"], ["drawing_no", "Drawing number"], ["company", "Company"], ["material", "Material"],
    ["finish", "Finish"], ["mass", "Mass"], ["drawn_by", "Drawn by"], ["checked_by", "Checked by"],
    ["approved_by", "Approved by"], ["date", "Date"], ["revision", "Revision"], ["sheet_no", "Sheet"],
  ];
  const VIEW_NAMES = { front: "Front", top: "Top", bottom: "Bottom", left: "Left side", right: "Right side", rear: "Rear", iso: "Isometric" };
  const SCALES = [[10, "10:1"], [5, "5:1"], [2, "2:1"], [1, "1:1"], [0.5, "1:2"], [0.2, "1:5"], [0.1, "1:10"], [0.05, "1:20"], [0.02, "1:50"], [0.01, "1:100"]];
  const LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ";

  const S = {
    sid: null, doc: null, sheet: { W: 420, H: 297 }, views: {}, viewScales: {}, viewOrigins: {},
    pick: {}, align: {}, geomKey: null, sel: null, hist: [], fut: [], zoom: 1, pan: { x: 0, y: 0 },
    tool: "select", dimOrient: "auto",
    tolForm: { char: "position", tol: "", dia: true, mod: "", datums: [["", ""], ["", ""], ["", ""]], extra: "" },
    datumLetter: "A",
  };
  // per-tool transient state
  let T = {};

  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, "");
      else if (v !== false && v != null) e.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) e.append(kid.nodeType ? kid : document.createTextNode(kid));
    return e;
  };

  // ------------------------------------------------------------------ vector helpers
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const mul = (a, k) => [a[0] * k, a[1] * k];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
  const len = (a) => Math.hypot(a[0], a[1]);
  const unit = (a) => { const l = len(a) || 1; return [a[0] / l, a[1] / l]; };
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const canon = (u) => (u[0] < -1e-9 || (Math.abs(u[0]) <= 1e-9 && u[1] < 0)) ? [-u[0], -u[1]] : u;
  const segDist = (p, a, b) => {
    const d = sub(b, a), L2 = dot(d, d);
    const t = L2 < 1e-24 ? 0 : Math.max(0, Math.min(1, dot(sub(p, a), d) / L2));
    return len(sub(p, add(a, mul(d, t))));
  };
  const closestOnSeg = (p, a, b) => {
    const d = sub(b, a), L2 = dot(d, d);
    const t = L2 < 1e-24 ? 0 : Math.max(0, Math.min(1, dot(sub(p, a), d) / L2));
    return add(a, mul(d, t));
  };
  const deg = (r) => r * 180 / Math.PI;
  const rad = (d) => d * Math.PI / 180;

  function fmt(v, dec) {
    if (dec == null) dec = S.doc ? +S.doc.settings.decimals : 2;
    let s = (+v).toFixed(dec);
    if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
    return s === "-0" ? "0" : s;
  }

  // ------------------------------------------------------------------ server
  async function api(path, body) {
    const opts = { method: "POST" };
    if (body instanceof Blob || body instanceof ArrayBuffer) {
      opts.body = body;
      opts.headers = { "Content-Type": "application/octet-stream" };
    } else if (body !== undefined) {
      opts.body = JSON.stringify(body);
      opts.headers = { "Content-Type": "application/json" };
    }
    const r = await fetch(path, opts);
    const ct = r.headers.get("Content-Type") || "";
    if (!r.ok) {
      let msg = "Request failed (" + r.status + ")";
      if (ct.includes("json")) msg = (await r.json()).error || msg;
      throw new Error(msg);
    }
    return ct.includes("json") ? r.json() : r;
  }

  let busyTimer = null;
  function busy(on, text) {
    clearTimeout(busyTimer);
    if (on) {
      $("busyText").textContent = text || "Working";
      busyTimer = setTimeout(() => { $("busy").hidden = false; }, 200);
    } else {
      $("busy").hidden = true;
    }
  }

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 4200);
  }

  async function guard(fn, text) {
    busy(true, text);
    try { return await fn(); }
    catch (e) { toast(e.message || String(e)); }
    finally { busy(false); }
  }

  // ------------------------------------------------------------------ state
  function applyState(st, keepView) {
    const first = !S.sid || st.sid !== S.sid;
    S.sid = st.sid;
    S.doc = st.doc;
    if (st.part) S.part = st.part;
    if (st.bodies) S.bodies = st.bodies;
    S.sheet = st.sheet;
    S.views = st.views;
    S.viewScales = st.view_scales || {};
    S.viewOrigins = st.view_origins || {};
    S.align = st.align || {};
    if (st.pick) S.pick = st.pick;
    S.geomKey = st.geom_key;
    S.scaleLabel = st.scale_label;
    if (S.sel && !findSel(S.sel)) S.sel = null;
    if (st.new_id) S.sel = st.new_id;
    drawSheet(st.svg);
    $("empty").hidden = true;
    $("status").hidden = false;
    for (const b of document.querySelectorAll("[data-fmt], #saveProj")) b.disabled = false;
    history.replaceState(null, "", "#sid=" + st.sid);
    renderAll();
    if (first || !keepView) fit();
    refreshOverlay();
  }

  function snapshot() { return JSON.stringify(S.doc); }
  function pushHist() {
    S.hist.push(snapshot());
    if (S.hist.length > 150) S.hist.shift();
    S.fut = [];
    updateUndo();
  }
  function updateUndo() {
    $("undo").disabled = !S.hist.length;
    $("redo").disabled = !S.fut.length;
  }

  async function rerender(full) {
    const st = await api("/api/render", { sid: S.sid, doc: S.doc, full: !!full, geom_key: S.geomKey });
    applyState(st, true);
  }

  async function commit(mutate, full) {
    if (!S.doc) return;
    pushHist();
    mutate(S.doc);
    await guard(() => rerender(full), "Updating");
  }

  async function action(name, args, confirmText, noHistory) {
    if (confirmText && !confirm(confirmText)) { renderAll(); return; }
    if (!noHistory) pushHist();
    await guard(async () => {
      const st = await api("/api/action", { sid: S.sid, doc: S.doc, action: name, args: args || {}, geom_key: S.geomKey });
      applyState(st, true);
    }, "Updating");
  }

  async function undo() {
    if (!S.hist.length) return;
    S.fut.push(snapshot());
    S.doc = JSON.parse(S.hist.pop());
    updateUndo();
    await guard(() => rerender(), "Updating");
  }
  async function redo() {
    if (!S.fut.length) return;
    S.hist.push(snapshot());
    S.doc = JSON.parse(S.fut.pop());
    updateUndo();
    await guard(() => rerender(), "Updating");
  }

  const findAnn = (id) => S.doc && S.doc.annotations.find(a => a.id === id);
  const findView = (id) => S.doc && S.doc.views.find(v => v.id === id);
  const findSel = (sel) => String(sel).startsWith("view:") ? findView(sel.slice(5)) : findAnn(sel);
  const viewScale = (vid) => (S.viewScales && S.viewScales[vid]) || 1;
  const toModel = (vid, P) => { const o = S.viewOrigins[vid], s = viewScale(vid); return [(P[0] - o[0]) / s, (P[1] - o[1]) / s]; };
  const toPaper = (vid, q) => { const o = S.viewOrigins[vid], s = viewScale(vid); return [o[0] + q[0] * s, o[1] + q[1] * s]; };
  const viewLabel = (v) => v.type === "section" ? `Section ${v.letter}-${v.letter}` : (VIEW_NAMES[v.type] || v.id);
  const viewName = (vid) => { const v = findView(vid); return v ? viewLabel(v) : vid; };

  // ------------------------------------------------------------------ opening files
  function resetSession() { S.hist = []; S.fut = []; S.sel = null; S.pick = {}; S.geomKey = null; updateUndo(); }

  async function openStep(file) {
    resetSession();
    await guard(async () => {
      const std = S.doc ? S.doc.settings.standard : "ISO";
      const buf = await file.arrayBuffer();
      const st = await api("/api/open?name=" + encodeURIComponent(file.name) + "&standard=" + std, buf);
      S.sid = null;
      applyState(st, false);
      setTool("select");
    }, "Reading geometry and projecting views");
  }

  async function openProject(file) {
    resetSession();
    await guard(async () => {
      let data;
      try { data = JSON.parse(await file.text()); }
      catch { throw new Error("That file is not valid JSON. Choose a .gdt.json project saved from GD&T Drafter."); }
      const st = await api("/api/project", data);
      S.sid = null;
      applyState(st, false);
      setTool("select");
    }, "Opening project");
  }

  async function openSample(name) {
    resetSession();
    await guard(async () => {
      const st = await api("/api/sample", { name });
      S.sid = null;
      applyState(st, false);
      setTool("select");
    }, "Reading geometry and projecting views");
  }

  function openAny(file) {
    if (!file) return;
    if (/\.json$/i.test(file.name)) openProject(file); else openStep(file);
  }

  async function download(resp, fallback) {
    const blob = await resp.blob();
    const cd = resp.headers.get("Content-Disposition") || "";
    const m = /filename="([^"]+)"/.exec(cd);
    const a = el("a", { href: URL.createObjectURL(blob), download: m ? m[1] : fallback });
    document.body.append(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  async function exportAs(fmtName) {
    await guard(async () => {
      const r = await api("/api/export", { sid: S.sid, doc: S.doc, format: fmtName });
      await download(r, "drawing." + fmtName);
      toast("Exported " + fmtName.toUpperCase() + ".");
    }, "Exporting " + fmtName.toUpperCase());
  }

  async function saveProject() {
    await guard(async () => {
      await rerender(false);
      const r = await fetch("/api/project?sid=" + S.sid);
      if (!r.ok) throw new Error("Could not save the project.");
      await download(r, "drawing.gdt.json");
      toast("Project saved. Open it again with “Open project”.");
    }, "Saving");
  }

  // ------------------------------------------------------------------ sheet, pan & zoom
  function drawSheet(svgText) {
    const box = $("sheet");
    box.innerHTML = svgText;
    const svg = box.querySelector("svg");
    svg.setAttribute("width", S.sheet.W * PX);
    svg.setAttribute("height", S.sheet.H * PX);
    box.style.width = S.sheet.W * PX + "px";
    box.style.height = S.sheet.H * PX + "px";
    markSelection();
  }

  function applyTransform() {
    $("stage").style.transform = `translate(${S.pan.x}px, ${S.pan.y}px) scale(${S.zoom})`;
    $("stZoom").textContent = Math.round(S.zoom * 100) + "%";
  }

  function fit() {
    const m = $("mat").getBoundingClientRect();
    const w = S.sheet.W * PX, h = S.sheet.H * PX;
    S.zoom = Math.max(0.1, Math.min((m.width - 48) / w, (m.height - 80) / h));
    S.pan.x = (m.width - w * S.zoom) / 2;
    S.pan.y = (m.height - 36 - h * S.zoom) / 2;
    applyTransform();
  }

  function zoomAt(factor, cx, cy) {
    const z = Math.max(0.1, Math.min(16, S.zoom * factor));
    const k = z / S.zoom;
    S.pan.x = cx - (cx - S.pan.x) * k;
    S.pan.y = cy - (cy - S.pan.y) * k;
    S.zoom = z;
    applyTransform();
  }

  function paperFromEvent(ev) {
    const r = $("sheet").getBoundingClientRect();
    const mmPx = PX * S.zoom;
    return [(ev.clientX - r.left) / mmPx, S.sheet.H - (ev.clientY - r.top) / mmPx];
  }

  function groupOf(id) { return document.querySelector(`#sheet g[data-id="${CSS.escape(id)}"]`); }

  function markSelection() {
    for (const g of document.querySelectorAll("#sheet g.sel")) g.classList.remove("sel");
    if (!S.sel) return;
    const a = findAnn(S.sel);
    const g = groupOf(a && a.attach ? a.attach : S.sel);
    if (g) g.classList.add("sel");
  }

  function select(id) {
    S.sel = id;
    markSelection();
    renderProps();
    renderAnnList();
    renderViewList();
  }

  // ------------------------------------------------------------------ overlay (previews, hover)
  function overlay() {
    let svg = $("sheet").querySelector("svg.overlay");
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "overlay");
      $("sheet").append(svg);
    }
    svg.setAttribute("width", S.sheet.W * PX);
    svg.setAttribute("height", S.sheet.H * PX);
    svg.setAttribute("viewBox", `0 0 ${S.sheet.W} ${S.sheet.H}`);
    return svg;
  }

  const OV = {
    parts: [],
    Y(y) { return S.sheet.H - y; },
    line(a, b, cls) { this.parts.push(`<line class="${cls}" x1="${a[0]}" y1="${this.Y(a[1])}" x2="${b[0]}" y2="${this.Y(b[1])}"/>`); },
    poly(pts, cls, closed) {
      const s = pts.map(p => `${p[0]},${this.Y(p[1])}`).join(" ");
      this.parts.push(`<${closed ? "polygon" : "polyline"} class="${cls}" points="${s}"/>`);
    },
    circle(c, r, cls) { this.parts.push(`<circle class="${cls}" cx="${c[0]}" cy="${this.Y(c[1])}" r="${r}"/>`); },
    arc(c, r, a0, a1, cls) {
      const sweep = ((a1 - a0) % 360 + 360) % 360 || 360;
      const p0 = add(c, mul([Math.cos(rad(a0)), Math.sin(rad(a0))], r));
      const p1 = add(c, mul([Math.cos(rad(a0 + sweep)), Math.sin(rad(a0 + sweep))], r));
      if (sweep >= 359.9) { this.circle(c, r, cls); return; }
      this.parts.push(`<path class="${cls}" d="M${p0[0]} ${this.Y(p0[1])} A${r} ${r} 0 ${sweep > 180 ? 1 : 0} 0 ${p1[0]} ${this.Y(p1[1])}"/>`);
    },
    text(p, s, h, rot = 0, anchor = "middle") {
      const tr = rot ? ` transform="rotate(${-rot} ${p[0]} ${this.Y(p[1])})"` : "";
      const t = String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
      this.parts.push(`<text class="pvtext" x="${p[0]}" y="${this.Y(p[1])}" font-size="${h / 0.718}" text-anchor="${anchor}"${tr}>${t}</text>`);
    },
    arrow(tip, from, size = 3) {
      const u = unit(sub(tip, from)), b = sub(tip, mul(u, size)), hw = size * 0.18;
      this.poly([tip, [b[0] - u[1] * hw, b[1] + u[0] * hw], [b[0] + u[1] * hw, b[1] - u[0] * hw]], "pvfill", true);
    },
    flush() { overlay().innerHTML = this.parts.join(""); this.parts = []; },
  };

  // ------------------------------------------------------------------ picking
  function viewsUnder(P, margin = 4) {
    const out = [];
    for (const [vid, r] of Object.entries(S.views || {})) {
      if (P[0] >= r[0] - margin && P[0] <= r[2] + margin && P[1] >= r[1] - margin && P[1] <= r[3] + margin) out.push(vid);
    }
    return out;
  }

  /** Nearest pickable entity: points (vertices, centres) first, then edges. */
  function hitTest(P, opts = {}) {
    const tolP = SNAP_PX / (PX * S.zoom);
    let bestPt = null, bestEdge = null;
    for (const [vid, E] of Object.entries(S.pick || {})) {
      if (opts.view && vid !== opts.view) continue;
      const r = S.views[vid];
      if (!r || P[0] < r[0] - tolP * 3 || P[0] > r[2] + tolP * 3 || P[1] < r[1] - tolP * 3 || P[1] > r[3] + tolP * 3) continue;
      const sc = viewScale(vid), q = toModel(vid, P), tol = tolP / sc;
      if (!opts.edgesOnly) {
        for (const v of E.verts) {
          const d = len(sub(q, v));
          if (d < tol && (!bestPt || d * sc < bestPt.d)) bestPt = { view: vid, t: "pt", p: v, c: 0, d: d * sc };
        }
        for (const c of E.centers) {
          const d = len(sub(q, c));
          if (d < tol && (!bestPt || d * sc < bestPt.d)) bestPt = { view: vid, t: "pt", p: [c[0], c[1]], c: c[2], ctr: true, d: d * sc };
        }
      }
      if (opts.pointsOnly) continue;
      const consider = (ent, d, hidden) => {
        // a real edge under the pointer beats a centre line; hidden edges rank a little lower
        const rank = hidden === 2 ? d * sc + tolP * 0.3 : d * sc * (hidden ? 1.5 : 1);
        if (d < tol && (!bestEdge || rank < bestEdge.rank)) { ent.rank = rank; ent.d = d * sc; ent.view = vid; bestEdge = ent; }
      };
      for (const L of E.lines) consider({ t: "line", a: [L[0], L[1]], b: [L[2], L[3]], hidden: L[4] }, segDist(q, [L[0], L[1]], [L[2], L[3]]), L[4]);
      for (const C of E.circles) consider({ t: "circle", c: [C[0], C[1]], r: C[2], hidden: C[3] }, Math.abs(len(sub(q, [C[0], C[1]])) - C[2]), C[3]);
      for (const A of E.arcs) {
        const ang = ((deg(Math.atan2(q[1] - A[1], q[0] - A[0])) - A[3]) % 360 + 360) % 360;
        const sweep = ((A[4] - A[3]) % 360 + 360) % 360;
        if (ang <= sweep + 2) consider({ t: "arc", c: [A[0], A[1]], r: A[2], a0: A[3], a1: A[4], hidden: A[5] }, Math.abs(len(sub(q, [A[0], A[1]])) - A[2]), A[5]);
      }
      for (const [pts, hidden] of E.polys) {
        let d = Infinity;
        for (let i = 0; i + 1 < pts.length; i++) d = Math.min(d, segDist(q, pts[i], pts[i + 1]));
        consider({ t: "poly", pts, hidden }, d, hidden);
      }
    }
    // a vertex/centre wins only when the pointer is clearly nearer to it than to an edge
    // (and on a short arc the end points must not swallow the whole arc)
    if (bestPt && bestEdge) {
      let bias = 4 / (PX * S.zoom);
      if (bestEdge.t === "arc" && !bestPt.ctr) {
        const sweep = ((bestEdge.a1 - bestEdge.a0) % 360 + 360) % 360;
        bias = Math.min(bias, rad(sweep) * bestEdge.r * viewScale(bestEdge.view) / 6);
      }
      return bestPt.d - bias <= bestEdge.d ? bestPt : bestEdge;
    }
    return bestPt || bestEdge;
  }

  const sameEnt = (a, b) => a && b && a.view === b.view && a.t === b.t && JSON.stringify([a.p, a.a, a.b, a.c, a.r]) === JSON.stringify([b.p, b.a, b.b, b.c, b.r]);

  function drawEnt(ent, cls = "hov") {
    if (!ent) return;
    const P = (q) => toPaper(ent.view, q), s = viewScale(ent.view);
    if (ent.t === "pt") {
      const p = P(ent.p);
      OV.circle(p, cls === "hov" ? 0.9 : 0.8, cls === "hov" ? "hovpt" : "pickedpt");
      OV.circle(p, 2.2, cls === "hov" ? "hovring" : "picked");
    } else if (ent.t === "line") OV.line(P(ent.a), P(ent.b), cls === "hov" ? "hov" : "picked");
    else if (ent.t === "circle") OV.circle(P(ent.c), ent.r * s, cls === "hov" ? "hov" : "picked");
    else if (ent.t === "arc") OV.arc(P(ent.c), ent.r * s, ent.a0, ent.a1, cls === "hov" ? "hov" : "picked");
    else if (ent.t === "poly") OV.poly(ent.pts.map(P), cls === "hov" ? "hov" : "picked");
  }

  const entToRef = (e) => e.t === "line" ? { t: "l", a: e.a, b: e.b } : (e.t === "pt" ? { t: "p", p: e.p, c: e.c || 0 } : { t: "p", p: e.c, c: e.r });

  // ------------------------------------------------------------------ dimension geometry (mirrors render.py)
  function refPaper(vid, r) {
    return r.t === "l" ? { t: "l", A: toPaper(vid, r.a), B: toPaper(vid, r.b) }
      : { t: "p", P: toPaper(vid, r.p), rad: (r.c || 0) * viewScale(vid) };
  }

  function ldimCalc(vid, refs, orient, off, cursor) {
    const R = refs.map(r => refPaper(vid, r));
    const L = R.find(r => r.t === "l");
    let u;
    if (orient === "h") u = [1, 0];
    else if (orient === "v") u = [0, 1];
    else if (L) { const t = unit(sub(L.B, L.A)); u = [-t[1], t[0]]; }
    else u = unit(sub(R[1].P, R[0].P));
    u = canon(u);
    const n = [-u[1], u[0]];
    const f = R.map(r => { const M = r.t === "l" ? mid(r.A, r.B) : r.P; return { s: dot(M, u), nn: dot(M, n), r }; });
    const baseN = (f[0].nn + f[1].nn) / 2;
    if (cursor) off = dot(cursor, n) - baseN;
    const td = baseN + (off || 0);
    const at = (s, t) => add(mul(u, s), mul(n, t));
    const exts = [];
    for (const F of f) {
      let tn;
      if (F.r.t === "l") {
        const ta = dot(F.r.A, n), tb = dot(F.r.B, n), lo = Math.min(ta, tb), hi = Math.max(ta, tb);
        if (td >= lo && td <= hi) continue;
        tn = td > hi ? hi : lo;
      } else tn = dot(F.r.P, n);
      const sg = td > tn ? 1 : -1;
      exts.push([at(F.s, tn + sg * 1), at(F.s, td + sg * 2)]);
    }
    return { u, n, DA: at(f[0].s, td), DB: at(f[1].s, td), exts, off, value: Math.abs(f[1].s - f[0].s) / viewScale(vid) };
  }

  function sector(C, d1, d2, P) {
    const ap = ((deg(Math.atan2(P[1] - C[1], P[0] - C[0]))) % 360 + 360) % 360;
    let best = null;
    for (const r1 of [d1, mul(d1, -1)]) for (const r2 of [d2, mul(d2, -1)]) {
      const t1 = (deg(Math.atan2(r1[1], r1[0])) + 360) % 360, t2 = (deg(Math.atan2(r2[1], r2[0])) + 360) % 360;
      for (const [a0, a1] of [[t1, t2], [t2, t1]]) {
        const sw = ((a1 - a0) % 360 + 360) % 360;
        if (sw <= 180 + 1e-9 && ((ap - a0) % 360 + 360) % 360 <= sw + 1e-9 && (!best || sw < best[2])) best = [a0, a1, sw];
      }
    }
    return best;
  }

  function adimCalc(vid, refs, P) {
    const [L1, L2] = refs.map(r => refPaper(vid, r));
    const d1 = unit(sub(L1.B, L1.A)), d2 = unit(sub(L2.B, L2.A));
    const den = d1[0] * d2[1] - d1[1] * d2[0];
    if (Math.abs(den) < 1e-6) return null;
    const t = ((L2.A[0] - L1.A[0]) * d2[1] - (L2.A[1] - L1.A[1]) * d2[0]) / den;
    const C = add(L1.A, mul(d1, t));
    const R = Math.max(len(sub(P, C)), 4);
    const sec = sector(C, d1, d2, P);
    return sec && { C, R, a0: sec[0], a1: sec[1], value: sec[2] };
  }

  function autoOrient(vid, refs, cursor) {
    const [A, B] = refs.map(r => toPaper(vid, r.p));
    const x0 = Math.min(A[0], B[0]), x1 = Math.max(A[0], B[0]), y0 = Math.min(A[1], B[1]), y1 = Math.max(A[1], B[1]);
    if (Math.abs(A[1] - B[1]) < 1e-6) return "h";
    if (Math.abs(A[0] - B[0]) < 1e-6) return "v";
    const inX = cursor[0] >= x0 && cursor[0] <= x1, inY = cursor[1] >= y0 && cursor[1] <= y1;
    if (inX && !inY) return "h";
    if (inY && !inX) return "v";
    if (!inX && !inY) return "al";
    return T.lastOrient || "al";
  }

  function drawLdimPreview(vid, g, prefix) {
    for (const [a, b] of g.exts) OV.line(a, b, "pv");
    OV.line(g.DA, g.DB, "pv");
    OV.arrow(g.DA, g.DB);
    OV.arrow(g.DB, g.DA);
    const h = +S.doc.settings.text_height;
    const ang = deg(Math.atan2(g.u[1], g.u[0]));
    OV.text(add(mid(g.DA, g.DB), mul(g.n, 1.2)), (prefix || "") + fmt(g.value), h, ang);
  }

  // ------------------------------------------------------------------ tools
  const TOOL_TIPS = {
    select: "Click to select, drag to move. Drag empty space to pan, scroll to zoom.",
    dim: "Pick vertices, edges or circle centres. Esc cancels the current dimension.",
    datum: "Click an edge or circle, or a dimension of a feature of size.",
    tol: "Set the frame, then click an edge, circle, dimension or hole callout.",
    note: "Click on the sheet where the note goes.",
    section: "Click points of the cutting line on a view; double-click or Enter to finish.",
  };

  function setTool(name) {
    S.tool = name;
    T = { stage: 0 };
    for (const b of document.querySelectorAll("#tools button")) b.setAttribute("aria-pressed", String(b.dataset.tool === name));
    const mat = $("mat");
    mat.className = mat.className.replace(/\btool-\w+/g, "").trim() + " tool-" + name;
    if (name === "datum") S.datumLetter = nextDatumLetter();
    renderToolOpts();
    $("tip").textContent = TOOL_TIPS[name] || "";
    clearTargets();
    refreshOverlay();
  }

  function nextDatumLetter() {
    const used = new Set((S.doc ? S.doc.annotations : []).filter(a => a.kind === "datum").map(a => a.letter));
    for (const ch of LETTERS) if (!used.has(ch)) return ch;
    return "Z";
  }

  function datumLetters() {
    const s = new Set((S.doc ? S.doc.annotations : []).filter(a => a.kind === "datum").map(a => a.letter).filter(Boolean));
    return [...s].sort();
  }

  function setStep(text) { const e = $("toolStep"); if (e) e.textContent = text; }

  function dimStepText() {
    if (T.stage === 0) return "1. Click a vertex, edge, centre line, circle centre or circle.";
    if (T.stage === 1) return T.first.t === "line"
      ? (T.first.hidden === 2 ? "2. Click a vertex, edge, centre or another centre line to measure to."
        : "2. Click a second item, the same edge again for its length, or empty space to place the edge length.")
      : "2. Click a vertex, edge or centre to measure to.";
    return "3. Move to position the dimension and click to place it.";
  }

  function renderToolOpts() {
    const box = $("toolOpts");
    box.innerHTML = "";
    if (!S.doc) return;
    const t = S.tool;
    if (t === "dim") {
      box.append(el("p", { class: "step", id: "toolStep", text: dimStepText() }));
      const chips = el("div", { class: "chips", role: "group", "aria-label": "Direction for point-to-point dimensions" });
      for (const [v, lab] of [["auto", "Auto"], ["h", "Horizontal"], ["v", "Vertical"], ["al", "Aligned"]]) {
        chips.append(el("button", { "aria-pressed": String(S.dimOrient === v), onclick: () => { S.dimOrient = v; renderToolOpts(); refreshOverlay(); }, text: lab }));
      }
      box.append(el("div", { class: "field" }, "Point to point", chips));
      box.append(el("p", { class: "hint", text: "Two parallel edges, or a point and an edge, give the perpendicular distance. Two edges at an angle give the angle. A circle or arc gives its diameter or radius. Centre lines pick like edges." }));
    } else if (t === "datum") {
      box.append(el("p", { class: "step", id: "toolStep", text: "Click the datum feature." }));
      box.append(el("label", {}, "Letter", el("input", { type: "text", maxlength: "2", value: S.datumLetter, style: "width:70px",
        oninput: (e) => { S.datumLetter = (e.target.value || "A").toUpperCase(); } })));
    } else if (t === "tol") {
      box.append(el("p", { class: "step", id: "toolStep", text: "Set the frame, then click the feature." }));
      const F = S.tolForm;
      const pickc = el("div", { class: "charpick", role: "group", "aria-label": "Characteristic" });
      for (const [k, name] of CHARS) {
        pickc.append(el("button", { title: name, "aria-label": name, "aria-pressed": String(F.char === k),
          onclick: () => { F.char = k; if (NO_DATUM.has(k)) F.datums = [["", ""], ["", ""], ["", ""]]; F.dia = ["position", "concentricity"].includes(k) ? true : (NO_DATUM.has(k) ? false : F.dia); renderToolOpts(); },
          html: charIcon(k) }));
      }
      box.append(el("div", { class: "field" }, CHAR_NAME[F.char], pickc));
      const tolInput = el("input", { type: "number", step: "0.001", min: "0", id: "tolValue", value: F.tol, placeholder: "e.g. 0.05",
        oninput: (e) => { F.tol = e.target.value; } });
      box.append(el("div", { class: "grid2" },
        el("label", {}, "Tolerance (mm)", tolInput),
        el("label", {}, "Material condition", el("select", { onchange: (e) => { F.mod = e.target.value; } },
          [["", "None"], ["M", "Ⓜ MMC"], ["L", "Ⓛ LMC"]].map(([v, l]) => el("option", { value: v, text: l, selected: F.mod === v }))))));
      box.append(el("label", { class: "check-inline" }, el("input", { type: "checkbox", checked: F.dia, onchange: (e) => { F.dia = e.target.checked; } }), "Diametral zone ⌀"));
      if (!NO_DATUM.has(F.char)) {
        const letters = datumLetters();
        const row = el("div", { class: "datumrefs" });
        ["Primary", "Secondary", "Tertiary"].forEach((lab, i) => {
          row.append(el("label", {}, lab, el("select", { onchange: (e) => { F.datums[i] = [e.target.value, ""]; } },
            [["", "—"], ...letters.map(l => [l, l])].map(([v, l]) => el("option", { value: v, text: l, selected: (F.datums[i] || [""])[0] === v })))));
        });
        box.append(el("div", { class: "field" }, "Datum references", row));
        if (!letters.length) box.append(el("p", { class: "hint", text: "No datums yet. Add them with the Datum tool and they appear here." }));
      }
    } else if (t === "note") {
      box.append(el("p", { class: "step", id: "toolStep", text: "Click where the note goes. Type its text in the Selection panel." }));
    } else if (t === "section") {
      box.append(el("p", { class: "step", id: "toolStep", text: T.stage === 1 ? "Move to the side you look from, then click." : "Click points of the cutting line on a front, top, side or rear view." }));
      box.append(el("p", { class: "hint", text: "Two points give a straight section; more points give a stepped one. Lines snap to vertices, centres, horizontal and vertical." }));
      box.append(el("div", { class: "row-btns" },
        el("button", { onclick: finishSectionLine, disabled: !(T.pts && T.pts.length >= 2) || T.stage === 1, text: "Finish line" }),
        el("button", { onclick: () => setTool("section"), text: "Start over" })));
    }
  }

  function charIcon(k) {
    const s = (body) => `<svg viewBox="0 0 10 10" width="18" height="18" fill="none" stroke="currentColor" stroke-width="0.8" stroke-linecap="round" aria-hidden="true">${body}</svg>`;
    switch (k) {
      case "position": return s('<circle cx="5" cy="5" r="2.6"/><path d="M1 5h8M5 1v8"/>');
      case "flatness": return s('<path d="M1 7.5h6l2-5H3z"/>');
      case "straightness": return s('<path d="M1 5h8"/>');
      case "circularity": return s('<circle cx="5" cy="5" r="3.8"/>');
      case "cylindricity": return s('<circle cx="5" cy="5" r="2.8"/><path d="M2.4 8.8 4.8 1.2M5.2 8.8 7.6 1.2"/>');
      case "profile_line": return s('<path d="M1.2 7.5a3.8 3.8 0 0 1 7.6 0"/>');
      case "profile_surface": return s('<path d="M1.2 7.5a3.8 3.8 0 0 1 7.6 0z"/>');
      case "parallelism": return s('<path d="M2 9 5 1M5 9l3-8"/>');
      case "perpendicularity": return s('<path d="M1 9h8M5 9V1"/>');
      case "angularity": return s('<path d="M1 9h8M1 9l7-6"/>');
      case "concentricity": return s('<circle cx="5" cy="5" r="3.8"/><circle cx="5" cy="5" r="1.8"/>');
      case "symmetry": return s('<path d="M1 5h8M2.5 2h5M2.5 8h5"/>');
      case "circular_runout": return s('<path d="M2 9l5-7"/><path d="M5 1.5h2.6v2.6" />');
      case "total_runout": return s('<path d="M1 9h4.5M1 9l3-6M5 9l3-6"/><path d="M2.6 2.6h1.6v1.6M6.6 2.6h1.6v1.6"/>');
    }
    return s("");
  }

  function clearTargets() { for (const g of document.querySelectorAll("#sheet g.target")) g.classList.remove("target"); }

  /** Annotation under the pointer that a datum/frame can attach to. */
  function attachTarget(ev) {
    // pointer capture retargets events to the mat, so look up what is under the pointer
    const hit = document.elementFromPoint(ev.clientX, ev.clientY);
    const g = hit && hit.closest && hit.closest("#sheet g[data-id]");
    if (!g) return null;
    const a = findAnn(g.getAttribute("data-id"));
    return a && ["ldim", "callout"].includes(a.kind) ? a : null;
  }

  function refreshOverlay(P, ev) {
    if (!S.doc) return;
    if (P) T.cursor = P;
    P = T.cursor;
    const tool = S.tool;
    if (tool === "dim") dimOverlay(P);
    else if (tool === "datum" || tool === "tol") attachOverlay(P, ev);
    else if (tool === "section") sectionOverlay(P);
    else if (T.guides) { for (const g of T.guides) OV.line(g[0], g[1], "guide"); }
    OV.flush();
  }

  // --- dimension tool
  function dimOverlay(P) {
    if (T.stage < 2 && P) {
      T.hover = hitTest(P, { view: T.stage === 1 ? T.first.view : null });
      if (T.hover && T.hover.t === "poly") T.hover = null;
      drawEnt(T.hover, "hov");
    }
    if (T.first) drawEnt(T.first, "picked");
    if (T.second) drawEnt(T.second, "picked");
    if (T.stage === 2 && P) {
      const vid = T.view;
      if (T.kind === "ldim") {
        let orient = T.orient;
        if (orient === "pp") orient = S.dimOrient === "auto" ? autoOrient(vid, T.refs, P) : S.dimOrient;
        T.curOrient = orient;
        if (orient !== "perp") T.lastOrient = orient;
        const g = ldimCalc(vid, T.refs, orient, 0, P);
        T.off = g.off;
        drawLdimPreview(vid, g, T.prefix);
      } else if (T.kind === "adim") {
        const g = adimCalc(vid, T.refs, P);
        if (g) {
          OV.arc(g.C, g.R, g.a0, g.a1, "pv");
          const h = +S.doc.settings.text_height, m = rad(g.a0 + (((g.a1 - g.a0) % 360 + 360) % 360) / 2);
          OV.text(add(g.C, mul([Math.cos(m), Math.sin(m)], g.R + 2.5 + h * 0.7)), fmt(g.value) + "°", h);
        }
      } else if (T.kind === "callout") {
        const e = T.first;
        const A = calloutFoot(e, P);
        OV.line(A, P, "pv");
        OV.arrow(A, P);
        OV.text(add(P, [P[0] >= A[0] ? 1 : -1, 1]), (e.t === "arc" ? "R" : "⌀") + fmt(e.t === "arc" ? e.r : 2 * e.r), +S.doc.settings.text_height, 0, P[0] >= A[0] ? "start" : "end");
      }
    }
  }

  function dimClick(P) {
    if (T.stage === 0) {
      const h = T.hover;
      if (!h) { toast("Click on a vertex, edge, circle centre or circle in a front, top, side or section view."); return; }
      if (h.t === "circle" || h.t === "arc") {
        Object.assign(T, { first: h, view: h.view, kind: "callout", stage: 2 });
      } else {
        Object.assign(T, { first: h, view: h.view, stage: 1 });
      }
    } else if (T.stage === 1) {
      const h = T.hover, f = T.first;
      if (!h || sameEnt(h, f)) {
        if (f.t !== "line" || f.hidden === 2) { if (!h) toast("Click a second vertex, edge, centre or centre line in the same view."); return; }
        Object.assign(T, { kind: "ldim", refs: [{ t: "p", p: f.a, c: 0 }, { t: "p", p: f.b, c: 0 }], orient: "pp", stage: 2 });
        if (!h) { refreshOverlay(P); return finishDim(); }
      } else {
        const a = entToRef(f), b = entToRef(h);
        T.second = h;
        if (a.t === "l" && b.t === "l") {
          const d1 = unit(sub(a.b, a.a)), d2 = unit(sub(b.b, b.a));
          if (Math.abs(d1[0] * d2[1] - d1[1] * d2[0]) < Math.sin(rad(0.5))) Object.assign(T, { kind: "ldim", refs: [a, b], orient: "perp" });
          else Object.assign(T, { kind: "adim", refs: [a, b] });
        } else if (a.t === "l" || b.t === "l") Object.assign(T, { kind: "ldim", refs: [a, b], orient: "perp" });
        else {
          if (len(sub(a.p, b.p)) < 1e-9) { toast("Pick two different points."); return; }
          Object.assign(T, { kind: "ldim", refs: [a, b], orient: "pp" });
        }
        T.stage = 2;
      }
    } else {
      finishDim();
      return;
    }
    setStep(dimStepText());
    refreshOverlay(P);
  }

  async function finishDim() {
    const vid = T.view, P = T.cursor;
    let args;
    if (T.kind === "ldim") args = { kind: "ldim", view: vid, refs: T.refs, orient: T.curOrient || (T.orient === "pp" ? "al" : T.orient), off: T.off || 0 };
    else if (T.kind === "adim") args = { kind: "adim", view: vid, refs: T.refs, pick: toModel(vid, P) };
    T = { stage: 0, lastOrient: T.lastOrient };
    setStep(dimStepText());
    if (args) await action("add_dim", args);
  }

  /** Where a radius/diameter leader touches: towards the cursor, kept on the arc itself. */
  function calloutFoot(e, P) {
    const c = toPaper(e.view, e.c), r = e.r * viewScale(e.view);
    let ang = deg(Math.atan2(P[1] - c[1], P[0] - c[0]));
    if (e.t === "arc") {
      const sweep = ((e.a1 - e.a0) % 360 + 360) % 360, rel = ((ang - e.a0) % 360 + 360) % 360;
      if (rel > sweep) {
        const opp = ((ang + 180 - e.a0) % 360 + 360) % 360;      // cursor on the centre side of a fillet
        if (opp <= sweep) ang += 180;
        else ang = rel - sweep < 360 - rel ? e.a1 : e.a0;
      }
    }
    return add(c, [r * Math.cos(rad(ang)), r * Math.sin(rad(ang))]);
  }

  async function finishCallout(P) {
    const e = T.first;
    const Ap = calloutFoot(e, P);
    const anchor = toModel(e.view, Ap);
    const off = sub(P, Ap);
    T = { stage: 0 };
    setStep(dimStepText());
    await action("add_callout", { view: e.view, center: e.c, r: e.r, arc: e.t === "arc", anchor, off });
  }

  // --- datum & tolerance tools
  function attachOverlay(P, ev) {
    if (T.stage === 0) {
      clearTargets();
      T.target = ev ? attachTarget(ev) : T.target;
      if (T.target) {
        const g = groupOf(T.target.id);
        if (g) g.classList.add("target");
        T.hover = null;
      } else if (P) {
        T.hover = hitTest(P, { edgesOnly: true });
        if (T.hover && T.hover.t === "poly") T.hover = null;
        drawEnt(T.hover, "hov");
      }
      return;
    }
    // stage 1: placing a leader-attached symbol
    const e = T.ent, A = toPaper(e.view, T.anchor);
    drawEnt(e, "picked");
    if (!P) return;
    if (S.tool === "datum") {
      const d = datumDir(e, A, P);
      const along = Math.abs(dot(sub(P, A), d));
      const L = Math.max(2, along - TRI - BOX / 2);
      drawDatumPreview(A, d, L, S.datumLetter);
    } else {
      OV.line(A, P, "pv");
      OV.arrow(A, P);
      const w = 30, h = 2 * +S.doc.settings.text_height;
      const x = P[0] >= A[0] ? P[0] : P[0] - w;
      OV.poly([[x, P[1] - h / 2], [x + w, P[1] - h / 2], [x + w, P[1] + h / 2], [x, P[1] + h / 2]], "pvbox", true);
      OV.text([x + w / 2, P[1] - h * 0.18], `${CHAR_GLYPH[S.tolForm.char]} ${S.tolForm.dia ? "⌀" : ""}${S.tolForm.tol || "?"}`, h * 0.45);
    }
  }

  function datumDir(e, A, P) {
    let d;
    if (e.t === "line") {
      const a = toPaper(e.view, e.a), b = toPaper(e.view, e.b), t = unit(sub(b, a));
      d = [-t[1], t[0]];
    } else {
      d = unit(sub(A, toPaper(e.view, e.c)));
    }
    return dot(sub(P, A), d) >= 0 ? d : mul(d, -1);
  }

  function drawDatumPreview(base, d, L, letter) {
    const t = [-d[1], d[0]];
    const apex = add(base, mul(d, TRI));
    OV.poly([add(base, mul(t, 2.2)), sub(base, mul(t, 2.2)), apex], "pvfill", true);
    const end = add(apex, mul(d, L));
    OV.line(apex, end, "pv");
    const c = add(end, mul(d, BOX / 2));
    OV.poly([[c[0] - BOX / 2, c[1] - BOX / 2], [c[0] + BOX / 2, c[1] - BOX / 2], [c[0] + BOX / 2, c[1] + BOX / 2], [c[0] - BOX / 2, c[1] + BOX / 2]], "pvbox", true);
    OV.text([c[0], c[1] - 1.7], letter, 3.5);
  }

  function anchorOn(e, P) {
    const q = toModel(e.view, P);
    if (e.t === "line") return closestOnSeg(q, e.a, e.b);
    return add(e.c, mul(unit(sub(q, e.c)), e.r));
  }

  function tolFrameFromForm() {
    const F = S.tolForm;
    const v = parseFloat(F.tol);
    if (!(v > 0)) {
      toast("Enter the tolerance value first.");
      const inp = $("tolValue");
      if (inp) inp.focus();
      return null;
    }
    return { kind: "fcf", char: F.char, tol: v, dia: !!F.dia, mod: F.mod || "", extra: F.extra || "",
      datums: NO_DATUM.has(F.char) ? [] : F.datums.filter(r => r && r[0]).map(r => [r[0], r[1] || ""]) };
  }

  function attachClick(P, ev) {
    const tool = S.tool;
    if (T.stage === 0) {
      const target = attachTarget(ev);
      if (target) {
        if (tool === "datum") {
          const letter = S.datumLetter || nextDatumLetter();
          commit(doc => { doc.annotations.push({ id: "u" + Date.now(), kind: "datum", view: target.view, attach: target.id, letter, len: 4, dir: [0, -1], anchor: null, slide: 0, auto: false, placed: true }); })
            .then(() => { S.datumLetter = nextDatumLetter(); renderToolOpts(); });
        } else {
          const fr = tolFrameFromForm();
          if (!fr) return;
          commit(doc => { doc.annotations.push(Object.assign(fr, { id: "u" + Date.now(), view: target.view, attach: target.id, anchor: null, off: null, auto: false, placed: true })); });
        }
        clearTargets();
        return;
      }
      const e = T.hover;
      if (!e) { toast(tool === "datum" ? "Click an edge, a circle, or a dimension." : "Click an edge, a circle, a dimension or a hole callout."); return; }
      if (tool === "tol" && !tolFrameFromForm()) return;
      Object.assign(T, { ent: e, anchor: anchorOn(e, P), stage: 1 });
      setStep(tool === "datum" ? "Move out from the feature and click to place the symbol." : "Move to where the frame goes and click.");
      refreshOverlay(P);
      return;
    }
    const e = T.ent, A = toPaper(e.view, T.anchor);
    if (tool === "datum") {
      const d = datumDir(e, A, P);
      const L = Math.max(2, Math.abs(dot(sub(P, A), d)) - TRI - BOX / 2);
      const letter = S.datumLetter || nextDatumLetter();
      const a = { id: "u" + Date.now(), kind: "datum", view: e.view, anchor: T.anchor, dir: d, len: L, slide: 0, letter, auto: false, placed: true };
      T = { stage: 0 };
      commit(doc => { doc.annotations.push(a); }).then(() => { S.datumLetter = nextDatumLetter(); renderToolOpts(); });
    } else {
      const fr = tolFrameFromForm();
      if (!fr) return;
      const a = Object.assign(fr, { id: "u" + Date.now(), view: e.view, anchor: T.anchor, off: sub(P, A), attach: null, auto: false, placed: true });
      T = { stage: 0 };
      setStep("Set the frame, then click the feature.");
      commit(doc => { doc.annotations.push(a); });
    }
  }

  // --- note tool
  function noteClick(P) {
    const id = "n" + Date.now();
    commit(doc => {
      doc.annotations.push({ id, kind: "note", pos: [P[0], P[1]], lines: ["NOTE"], h: +doc.settings.text_height, auto: false, placed: true });
    }).then(() => {
      setTool("select");
      select(id);
      const ta = document.querySelector("#props textarea");
      if (ta) { ta.focus(); ta.select(); }
    });
  }

  // --- section tool
  function sectionSnap(P) {
    const view = T.view;
    const vid = view || (hitTest(P, { pointsOnly: true }) || {}).view ||
      viewsUnder(P, 8).find(v => { const m = findView(v); return m && ORTHO.includes(m.type); });
    if (!vid) return null;
    let q = toModel(vid, P);
    const prev = T.pts && T.pts.length ? T.pts[T.pts.length - 1] : null;
    let lock = null;
    if (prev) {
      const d = sub(q, prev), a = Math.abs(deg(Math.atan2(d[1], d[0]))) % 180;
      if (a < 8 || a > 172) { q = [q[0], prev[1]]; lock = 1; }
      else if (Math.abs(a - 90) < 8) { q = [prev[0], q[1]]; lock = 0; }
    }
    // snap to a vertex or centre, but never at the cost of the horizontal/vertical lock
    const h = hitTest(toPaper(vid, q), { view: vid, pointsOnly: true });
    let snapped = false;
    if (h && (lock === null || Math.abs(h.p[lock] - prev[lock]) < 1e-6)) { q = h.p; snapped = true; }
    else if (h && lock !== null) { q = lock === 1 ? [h.p[0], prev[1]] : [prev[0], h.p[1]]; snapped = true; }
    return { view: vid, q, snapped };
  }

  function sectionOverlay(P) {
    const pts = (T.pts || []).map(q => toPaper(T.view, q));
    if (T.stage === 0 && P) {
      const s = sectionSnap(P);
      T.snap = s;
      if (s) {
        const sp = toPaper(s.view, s.q);
        if (s.snapped) { OV.circle(sp, 0.9, "hovpt"); OV.circle(sp, 2.2, "hovring"); }
        if (pts.length) OV.line(pts[pts.length - 1], sp, "pv");
      }
    }
    if (pts.length >= 2) OV.poly(pts, "hov");
    for (const p of pts) OV.circle(p, 0.7, "pickedpt");
    if (T.stage === 1 && P && pts.length >= 2) {
      const u = unit(sub(pts[1], pts[0])), n = [-u[1], u[0]];
      const d = dot(sub(P, pts[0]), n) >= 0 ? n : mul(n, -1);
      T.dir = d;
      const asme = S.doc.settings.standard === "ASME";
      for (const E of [pts[0], pts[pts.length - 1]]) {
        const tail = asme ? E : sub(E, mul(d, 10)), tip = asme ? add(E, mul(d, 10)) : E;
        OV.line(tail, tip, "pv");
        OV.arrow(tip, tail);
      }
    }
  }

  function sectionClick(P) {
    if (T.stage === 1) {
      const d = T.dir;
      if (!d) return;
      const args = { parent: T.view, pts: T.pts, dir: d };
      setTool("select");
      action("add_section", args);
      return;
    }
    const s = T.snap || sectionSnap(P);
    if (!s) { toast("Start the cutting line on a front, top, side or rear view."); return; }
    if (!T.view) {
      const m = findView(s.view);
      if (!m || !ORTHO.includes(m.type)) { toast("Start the cutting line on a front, top, side or rear view."); return; }
      T.view = s.view;
      T.pts = [];
    }
    const last = T.pts[T.pts.length - 1];
    if (last && len(sub(last, s.q)) < 1e-6) return;
    T.pts.push(s.q);
    renderToolOpts();
    refreshOverlay(P);
  }

  function finishSectionLine() {
    if (S.tool !== "section" || !T.pts || T.pts.length < 2) { toast("Click at least two points first."); return; }
    T.stage = 1;
    renderToolOpts();
    refreshOverlay();
  }

  // ------------------------------------------------------------------ pointer handling
  let drag = null;

  function onPointerDown(ev) {
    if (!S.doc) return;
    if (ev.button === 1 || ev.button === 2) {
      drag = { mode: "pan", x0: ev.clientX, y0: ev.clientY, px: S.pan.x, py: S.pan.y, moved: true };
      $("mat").setPointerCapture(ev.pointerId);
      ev.preventDefault();
      return;
    }
    if (ev.button !== 0) return;
    const mat = $("mat");
    if (S.tool === "select") {
      const g = ev.target.closest && ev.target.closest("#sheet g[data-id]");
      const id = g && g.getAttribute("data-id");
      if (id && id.startsWith("view:") && findView(id.slice(5))) {
        select(id);
        startViewDrag(ev, id.slice(5));
      } else if (id && id.startsWith("cut:")) {
        select("view:" + id.slice(4));
        drag = { mode: "none", x0: ev.clientX, y0: ev.clientY };
      } else if (id && findAnn(id)) {
        select(id);
        drag = { mode: "ann", id, g, x0: ev.clientX, y0: ev.clientY, moved: false };
      } else {
        drag = { mode: "pan", x0: ev.clientX, y0: ev.clientY, px: S.pan.x, py: S.pan.y, moved: false, click: true };
        mat.classList.add("panning");
      }
    } else {
      // tools: a click acts, a drag pans
      drag = { mode: "pan", x0: ev.clientX, y0: ev.clientY, px: S.pan.x, py: S.pan.y, moved: false, toolClick: true, ev };
    }
    mat.setPointerCapture(ev.pointerId);
    ev.preventDefault();
  }

  function onPointerMove(ev) {
    if (!S.doc) return;
    if (!drag) {
      if (S.tool !== "select") refreshOverlay(paperFromEvent(ev), ev);
      return;
    }
    const dx = ev.clientX - drag.x0, dy = ev.clientY - drag.y0;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    if (drag.mode === "pan") {
      if (!drag.moved) return;
      S.pan.x = drag.px + dx;
      S.pan.y = drag.py + dy;
      applyTransform();
    } else if (drag.mode === "ann" && drag.moved) {
      const mm = PX * S.zoom;
      drag.g.setAttribute("transform", `translate(${dx / mm} ${dy / mm})`);
    } else if (drag.mode === "view" && drag.moved) {
      moveViewDrag(ev);
    }
  }

  function onPointerUp(ev) {
    if (!drag) return;
    const d = drag;
    drag = null;
    $("mat").classList.remove("panning");
    if (d.mode === "pan") {
      if (!d.moved && d.click) select(null);
      if (!d.moved && d.toolClick) toolClick(paperFromEvent(ev), ev);
      return;
    }
    if (d.mode === "view") return endViewDrag(ev, d);
    if (d.mode !== "ann" || !d.moved) return;
    const mm = PX * S.zoom;
    moveAnnotation(d.id, (ev.clientX - d.x0) / mm, -(ev.clientY - d.y0) / mm);
  }

  function toolClick(P, ev) {
    const t = S.tool;
    if (t === "dim") {
      if (T.stage === 2 && T.kind === "callout") return finishCallout(P);
      T.cursor = P;
      if (T.stage < 2) refreshOverlay(P, ev);
      return dimClick(P);
    }
    if (t === "datum" || t === "tol") { refreshOverlay(P, ev); return attachClick(P, ev); }
    if (t === "note") return noteClick(P);
    if (t === "section") { refreshOverlay(P, ev); return sectionClick(P); }
  }

  function moveAnnotation(id, dx, dy) {
    commit(doc => {
      const a = doc.annotations.find(x => x.id === id);
      if (!a) return;
      a.placed = true;
      if (a.kind === "callout" || a.kind === "fcf") {
        const o = a.off || [12, 12];
        a.off = [o[0] + dx, o[1] + dy];
      } else if (a.kind === "datum") {
        const dir = unit(a.dir || [0, -1]);
        const t = [-dir[1], dir[0]];
        a.len = Math.max(1, (a.len == null ? 4 : a.len) + dx * dir[0] + dy * dir[1]);
        a.slide = (a.slide || 0) + dx * t[0] + dy * t[1];
      } else if (a.kind === "ldim") {
        const g = ldimCalc(a.view, a.refs, a.orient, a.off || 0);
        a.off = (a.off || 0) + dot([dx, dy], g.n);
        a.shift = (a.shift || 0) + dot([dx, dy], g.u);
      } else if (a.kind === "adim") {
        const s = viewScale(a.view);
        a.pick = [a.pick[0] + dx / s, a.pick[1] + dy / s];
      } else if (a.kind === "dim") {
        const gap = a.gap == null ? DIM_GAP0 + DIM_STEP * (a.tier || 0) : a.gap;
        const scale = viewScale(a.view);
        if (a.side === "at") {
          if (a.axis === "v") { a.at = (a.at ?? a.a[0]) + dx / scale; a.shift = (a.shift || 0) + dy; }
          else { a.at = (a.at ?? a.a[1]) + dy / scale; a.shift = (a.shift || 0) + dx; }
        } else if (a.axis === "h") {
          a.gap = Math.max(2, gap + (a.side === "top" ? dy : -dy));
          a.shift = (a.shift || 0) + dx;
        } else {
          a.gap = Math.max(2, gap + (a.side === "right" ? dx : -dx));
          a.shift = (a.shift || 0) + dy;
        }
      } else if (a.kind === "note") {
        a.pos = [a.pos[0] + dx, a.pos[1] + dy];
      }
    });
  }

  // --- dragging views (with alignment snapping)
  function startViewDrag(ev, vid) {
    const v = findView(vid);
    const r = S.views[vid];
    const c0 = v.center || [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2];
    const groups = [groupOf("view:" + vid)];
    for (const a of S.doc.annotations) if (a.view === vid) { const g = groupOf(a.id); if (g) groups.push(g); }
    for (const w of S.doc.views) if (w.type === "section" && w.parent === vid) { const g = groupOf("cut:" + w.id); if (g) groups.push(g); }
    drag = { mode: "view", vid, c0, x0: ev.clientX, y0: ev.clientY, moved: false, groups: groups.filter(Boolean), c: c0 };
  }

  function moveViewDrag(ev) {
    const d = drag, mm = PX * S.zoom;
    let c = [d.c0[0] + (ev.clientX - d.x0) / mm, d.c0[1] - (ev.clientY - d.y0) / mm];
    const guides = [];
    const snap = 5 / Math.max(S.zoom, 0.3);
    for (const rule of S.align[d.vid] || []) {
      const other = findView(rule.to);
      if (!other || !other.center) continue;
      const k = rule.axis === "x" ? 0 : 1;
      const target = other.center[k] + rule.off;
      if (Math.abs(c[k] - target) < snap) {
        c[k] = target;
        const oc = other.center;
        guides.push(k === 0 ? [[target, Math.min(oc[1], c[1]) - 60], [target, Math.max(oc[1], c[1]) + 60]]
                            : [[Math.min(oc[0], c[0]) - 60, target], [Math.max(oc[0], c[0]) + 60, target]]);
      }
    }
    d.c = c;
    const tx = (c[0] - d.c0[0]), ty = -(c[1] - d.c0[1]);
    for (const g of d.groups) g.setAttribute("transform", `translate(${tx} ${ty})`);
    T.guides = guides;
    refreshOverlay();
  }

  function endViewDrag(ev, d) {
    T.guides = null;
    refreshOverlay();
    if (!d.moved) return;
    const c = d.c;
    commit(doc => { const v = doc.views.find(x => x.id === d.vid); if (v) v.center = [c[0], c[1]]; });
  }

  // ------------------------------------------------------------------ panels
  function renderAll() {
    $("fileName").textContent = S.doc.part.file || "Untitled";
    const p = S.part;
    $("partMeta").textContent = p ? `${p.size.join(" × ")} mm, ${p.faces} faces` : "";
    $("stScale").textContent = "Scale " + S.scaleLabel;
    $("stSheet").textContent = S.doc.settings.sheet + " landscape, " + (S.doc.settings.projection === "first" ? "first" : "third") + " angle";
    renderSettings();
    renderViewList();
    renderTitle();
    renderProps();
    renderAnnList();
    updateUndo();
    if (!$("toolOpts").childElementCount && S.tool !== "select") renderToolOpts();
  }

  function renderSettings() {
    const st = S.doc.settings;
    $("setSheet").value = st.sheet;
    const sc = $("setScale");
    sc.value = String(st.scale);
    if (sc.value !== String(st.scale)) {
      const lbl = S.scaleLabel || String(st.scale);
      sc.append(el("option", { value: String(st.scale), text: lbl }));
      sc.value = String(st.scale);
    }
    for (const b of $("setProjection").children) b.setAttribute("aria-pressed", b.dataset.v === st.projection);
    for (const b of $("setStandard").children) b.setAttribute("aria-pressed", b.dataset.v === st.standard);
    $("setHidden").checked = st.hidden;
    $("setTangent").checked = st.tangent;
    $("setCenter").checked = st.centerlines;
    $("setText").value = String(st.text_height);
    $("setDec").value = String(st.decimals);
    if (document.activeElement !== $("notes")) $("notes").value = (S.doc.notes || []).join("\n");
    const bodies = S.bodies || [];
    $("bodyBox").hidden = bodies.length < 2;
    if (bodies.length >= 2) {
      const cur = st.body == null ? "all" : String(st.body);
      const sel = $("setBody");
      sel.innerHTML = "";
      for (const b of bodies) sel.append(el("option", { value: b.value, text: b.label, selected: b.value === cur }));
      $("bodyHint").textContent = `This file holds ${bodies.length - 1} separate bodies. Pick the one to draw.`;
    }
  }

  function renderViewList() {
    const ul = $("viewList");
    ul.innerHTML = "";
    if (!S.doc) return;
    for (const v of S.doc.views) {
      const s = S.viewScales[v.id];
      const tag = s && Math.abs(s - S.doc.settings.scale) > 1e-12 ? "scale " + scaleText(s) : (v.type === "section" ? "on " + viewName(v.parent) : "");
      ul.append(el("li", {}, el("button", { class: S.sel === "view:" + v.id ? "sel" : "", onclick: () => select("view:" + v.id) },
        el("span", { text: viewLabel(v) }), el("span", { class: "tag", text: tag }))));
    }
    for (const b of document.querySelectorAll("#addViews button")) b.disabled = !!findView(b.dataset.view);
  }

  function scaleText(s) {
    const m = SCALES.find(x => Math.abs(x[0] - s) < 1e-9);
    if (m) return m[1];
    return s >= 1 ? fmt(s, 3) + ":1" : "1:" + fmt(1 / s, 3);
  }

  function renderTitle() {
    const box = $("titleFields");
    if (box.contains(document.activeElement)) return;
    box.innerHTML = "";
    for (const [k, label] of TITLE_FIELDS) {
      box.append(el("label", {}, label, el("input", {
        type: "text", value: S.doc.title[k] || "",
        onchange: (e) => commit(doc => { doc.title[k] = e.target.value; }),
      })));
    }
  }

  // --------------------------------------------------- annotation list
  function annValue(a) {
    try {
      if (a.kind === "ldim") return (a.prefix || "") + fmt(ldimCalc(a.view, a.refs, a.orient, a.off || 0).value);
      if (a.kind === "adim") { const P = toPaper(a.view, a.pick); const g = adimCalc(a.view, a.refs, P); return g ? fmt(g.value) + "°" : "angle"; }
    } catch { /* view not on sheet */ }
    return "";
  }

  function annLabel(a) {
    const f = (v) => fmt(v, 3);
    if (a.kind === "ldim" || a.kind === "adim") {
      const v = annValue(a);
      return [a.tol && a.tol.mode === "basic" ? "[" + v + "]" : v, viewName(a.view)];
    }
    if (a.kind === "dim") {
      const k = a.axis === "h" ? 0 : 1;
      return [(a.prefix || "") + f(Math.abs(a.b[k] - a.a[k])), viewName(a.view)];
    }
    if (a.kind === "fcf") {
      const d = (a.datums || []).map(x => x[0]).filter(Boolean).join("|");
      return [`${CHAR_GLYPH[a.char] || "?"} ${a.dia ? "⌀" : ""}${a.tol}${d ? " | " + d : ""}`, CHAR_NAME[a.char] || a.char];
    }
    if (a.kind === "datum") return ["Datum " + a.letter, a.attach ? "on a dimension" : viewName(a.view)];
    if (a.kind === "callout") return [(a.lines || [""])[0].replace("{size}", f(a.size)), viewName(a.view)];
    if (a.kind === "note") return [(a.lines || [""])[0] || "Note", "Note"];
    if (a.kind === "angle") return ["Angle", viewName(a.view)];
    return [a.kind, ""];
  }

  function renderAnnList() {
    const box = $("annList");
    box.innerHTML = "";
    if (!S.doc) return;
    const groups = [["Datums", ["datum"]], ["Geometric tolerances", ["fcf"]], ["Dimensions", ["ldim", "adim", "dim", "angle"]],
      ["Hole and radius callouts", ["callout"]], ["Notes", ["note"]]];
    const onSheet = new Set(S.doc.views.map(v => v.id));
    let any = false;
    for (const [title, kinds] of groups) {
      const items = S.doc.annotations.filter(a => kinds.includes(a.kind) && (!a.view || onSheet.has(a.view)));
      if (!items.length) continue;
      any = true;
      box.append(el("h3", { text: `${title} (${items.length})` }));
      for (const a of items) {
        const [main, tag] = annLabel(a);
        box.append(el("button", { class: S.sel === a.id ? "sel" : "", onclick: () => select(a.id) },
          el("span", { text: main }), el("span", { class: "tag", text: tag })));
      }
    }
    if (!any) box.append(el("p", { class: "hint", text: "Nothing yet. Use Dimension, Datum and Tolerance on the left to annotate the views." }));
  }

  // --------------------------------------------------- property editor
  const num = (v) => (v === "" || v == null || isNaN(+v)) ? 0 : +v;

  function fieldNum(label, value, onchange, step = "0.01") {
    return el("label", {}, label, el("input", { type: "number", step, value: value ?? 0, onchange: (e) => onchange(num(e.target.value)) }));
  }
  function fieldText(label, value, onchange, attrs = {}) {
    return el("label", {}, label, el("input", Object.assign({ type: "text", value: value || "", onchange: (e) => onchange(e.target.value) }, attrs)));
  }
  function fieldSel(label, value, options, onchange) {
    return el("label", {}, label, el("select", { onchange: (e) => onchange(e.target.value) },
      options.map(([v, t]) => el("option", { value: v, text: t, selected: String(v) === String(value) }))));
  }
  function edit(id, fn) { return (v) => commit(doc => { const a = doc.annotations.find(x => x.id === id); if (a) fn(a, v); }); }
  function editView(vid, fn) { return (v) => commit(doc => { const w = doc.views.find(x => x.id === vid); if (w) fn(w, v); }); }

  function tolFields(a, id) {
    const t = a.tol || { mode: "none", up: 0.1, lo: -0.1 };
    const out = [fieldSel("Tolerance", t.mode, TOL_MODES, edit(id, (x, v) => { x.tol = Object.assign({ up: 0.1, lo: -0.1 }, x.tol, { mode: v }); }))];
    if (["sym", "dev", "limits"].includes(t.mode)) {
      out.push(el("div", { class: "grid2" },
        fieldNum(t.mode === "sym" ? "± value" : "Upper", t.up, edit(id, (x, v) => { x.tol.up = v; }), "0.001"),
        t.mode === "sym" ? null : fieldNum("Lower", t.lo, edit(id, (x, v) => { x.tol.lo = v; }), "0.001")));
    }
    return out;
  }

  function symbolBar(input) {
    const ins = (s) => () => {
      const i = input.selectionStart ?? input.value.length;
      input.value = input.value.slice(0, i) + s + input.value.slice(input.selectionEnd ?? i);
      input.focus();
      input.selectionStart = input.selectionEnd = i + s.length;
      input.dispatchEvent(new Event("change"));
    };
    return el("div", { class: "symbar", "aria-label": "Insert symbol" },
      ["⌀", "↧", "⌴", "⌵", "±", "°", "Ⓜ"].map(s => el("button", { type: "button", title: "Insert " + s, onmousedown: (e) => e.preventDefault(), onclick: ins(s), text: s })));
  }

  function fcfFields(a, id) {
    const out = [];
    out.push(fieldSel("Characteristic", a.char, CHARS.map(([k, n]) => [k, `${CHAR_GLYPH[k]}  ${n}`]), edit(id, (x, v) => { x.char = v; })));
    out.push(el("div", { class: "grid2" },
      fieldNum("Tolerance", a.tol, edit(id, (x, v) => { x.tol = v; }), "0.001"),
      fieldSel("Material condition", a.mod || "", [["", "None (RFS)"], ["M", "Ⓜ MMC"], ["L", "Ⓛ LMC"]], edit(id, (x, v) => { x.mod = v; }))));
    out.push(el("label", { class: "check-inline" },
      el("input", { type: "checkbox", checked: !!a.dia, onchange: (e) => commit(doc => { doc.annotations.find(x => x.id === id).dia = e.target.checked; }) }),
      "Diametral zone ⌀"));
    out.push(el("div", { class: "field" }, "Datum references"));
    const ds = a.datums || [];
    const letters = [["", "—"], ...datumLetters().map(l => [l, l])];
    for (const d of ds) if (d[0] && !letters.find(l => l[0] === d[0])) letters.push([d[0], d[0] + " (not on sheet)"]);
    for (let i = 0; i < 3; i++) {
      const d = ds[i] || ["", ""];
      const setD = (j) => edit(id, (x, v) => {
        x.datums = (x.datums || []).slice();
        while (x.datums.length <= i) x.datums.push(["", ""]);
        x.datums[i] = x.datums[i].slice();
        x.datums[i][j] = v;
        x.datums = x.datums.filter(r => r[0]);
      });
      out.push(el("div", { class: "datumrow" },
        fieldSel(["Primary", "Secondary", "Tertiary"][i], d[0], letters, setD(0)),
        fieldSel("Modifier", d[1] || "", [["", "None"], ["M", "Ⓜ MMB"], ["L", "Ⓛ LMB"]], setD(1))));
    }
    out.push(fieldText("Zone suffix", a.extra, edit(id, (x, v) => { x.extra = v; }), { placeholder: "e.g. CZ, UF" }));
    return out;
  }

  function renderProps() {
    const box = $("props");
    box.innerHTML = "";
    if (!S.doc) return;
    if (S.sel && String(S.sel).startsWith("view:")) return renderViewProps(box, S.sel.slice(5));
    const a = S.sel && findAnn(S.sel);
    if (!a) {
      box.append(el("p", { class: "hint", text: "Select a view, dimension, datum, frame or note to edit it." }));
      return;
    }
    const id = a.id;
    const kindName = { dim: "Dimension", ldim: "Dimension", adim: "Angle", fcf: "Feature control frame", datum: "Datum feature symbol",
      callout: "Hole / radius callout", note: "Note", angle: "Angle" }[a.kind] || a.kind;
    box.append(el("div", { class: "kind" }, kindName, a.view ? el("small", { text: viewName(a.view) }) : null));

    if (a.kind === "fcf") box.append(...fcfFields(a, id));

    if (a.kind === "ldim") {
      box.append(el("p", { class: "hint", text: "Measured " + annValue(a).replace(/^⌀/, "") + " mm" }));
      if (a.refs.every(r => r.t === "p")) {
        box.append(fieldSel("Direction", a.orient, [["h", "Horizontal"], ["v", "Vertical"], ["al", "Aligned (true length)"]],
          edit(id, (x, v) => { x.orient = v; })));
      }
    }
    if (a.kind === "ldim" || a.kind === "dim" || a.kind === "adim") {
      box.append(...tolFields(a, id));
      if (a.kind !== "adim") {
        box.append(el("div", { class: "grid2" },
          fieldText("Prefix", a.prefix, edit(id, (x, v) => { x.prefix = v; })),
          fieldText("Count", a.count, edit(id, (x, v) => { x.count = v; }), { placeholder: "e.g. 2X" })));
      }
      const t = fieldText("Text override", a.text, edit(id, (x, v) => { x.text = v; }), { placeholder: "<> = measured value" });
      box.append(t, symbolBar(t.querySelector("input")));
    }

    if (a.kind === "callout") {
      const ta = el("textarea", { rows: Math.max(2, (a.lines || []).length + 1), spellcheck: "false",
        onchange: (e) => commit(doc => { doc.annotations.find(x => x.id === id).lines = e.target.value.split("\n").filter(s => s.trim()); }) });
      ta.value = (a.lines || []).join("\n");
      box.append(el("label", {}, "Text ({size} = size with tolerance)", ta), symbolBar(ta));
      box.append(fieldNum("Size", a.size, edit(id, (x, v) => { x.size = v; }), "0.001"));
      box.append(...tolFields(a, id));
    }

    if (a.kind === "datum") {
      box.append(fieldText("Letter", a.letter, edit(id, (x, v) => { x.letter = (v || "A").toUpperCase().slice(0, 2); }), { maxlength: "2" }));
    }

    if (a.kind === "note") {
      const ta = el("textarea", { rows: 4, onchange: (e) => commit(doc => { doc.annotations.find(x => x.id === id).lines = e.target.value.split("\n"); }) });
      ta.value = (a.lines || []).join("\n");
      box.append(el("label", {}, "Text", ta), symbolBar(ta));
      box.append(fieldSel("Text height", a.h || 3.5, [[2.5, "2.5 mm"], [3.5, "3.5 mm"], [5, "5 mm"], [7, "7 mm"]], edit(id, (x, v) => { x.h = +v; })));
    }

    const row = el("div", { class: "actions-row" });
    if (["ldim", "callout"].includes(a.kind)) {
      row.append(el("button", { text: "Add datum", onclick: () => commit(doc => {
        doc.annotations.push({ id: "u" + Date.now(), kind: "datum", view: a.view, attach: id, letter: nextDatumLetter(), len: 4, dir: [0, -1], anchor: null, slide: 0, auto: false, placed: true });
      }) }));
      row.append(el("button", { text: "Add frame", onclick: () => { setTool("tol"); toast("Set the frame, then click this dimension."); } }));
    }
    row.append(el("button", { class: "danger", text: "Delete", onclick: () => deleteSel() }));
    box.append(row);
    if (a.attach) box.append(el("p", { class: "hint", text: "Drawn together with the " + (findAnn(a.attach) || {}).kind + " it belongs to." }));
  }

  function renderViewProps(box, vid) {
    const v = findView(vid);
    if (!v) return;
    box.append(el("div", { class: "kind" }, viewLabel(v), v.type === "section" ? el("small", { text: "on the " + viewName(v.parent).toLowerCase() + " view" }) : null));
    const sheetScale = S.doc.settings.scale;
    const scaleOpts = [["", "Sheet scale (" + scaleText(sheetScale) + ")"], ...SCALES.map(([s, l]) => [String(s), l])];
    box.append(fieldSel("Scale", v.scale == null ? "" : String(v.scale), scaleOpts, editView(vid, (w, val) => { w.scale = val ? +val : null; })));
    box.append(fieldSel("Hidden lines", v.hidden == null ? "" : (v.hidden ? "1" : "0"), [["", "As set for the sheet"], ["1", "Show"], ["0", "Hide"]],
      editView(vid, (w, val) => { w.hidden = val === "" ? null : val === "1"; })));
    box.append(el("label", { class: "check-inline" },
      el("input", { type: "checkbox", checked: !!v.label, onchange: (e) => commit(doc => { doc.views.find(x => x.id === vid).label = e.target.checked; }) }),
      "Show caption under the view"));
    if (v.type === "section") {
      box.append(fieldText("Letter", v.letter, editView(vid, (w, val) => { w.letter = (val || "A").toUpperCase().slice(0, 2); }), { maxlength: "2" }));
    }
    const row = el("div", { class: "actions-row" });
    if (v.type === "section") {
      row.append(el("button", { text: "Flip viewing direction", onclick: editView(vid, (w) => { w.dir = [-w.dir[0], -w.dir[1]]; }) }));
    }
    row.append(el("button", { class: "danger", text: "Delete view", onclick: () => deleteView(vid) }));
    box.append(row);
    box.append(el("p", { class: "hint", text: "Drag the view to move it; it snaps into line with views it projects from. Its annotations move with it." }));
  }

  function deleteView(vid) {
    const v = findView(vid);
    const n = S.doc.annotations.filter(a => a.view === vid).length;
    const kids = S.doc.views.filter(w => w.parent === vid).length;
    let msg = null;
    if (n || kids) msg = `Delete ${viewLabel(v)}${n ? ` and its ${n} annotation${n > 1 ? "s" : ""}` : ""}${kids ? ` and ${kids} section view${kids > 1 ? "s" : ""} taken from it` : ""}?`;
    S.sel = null;
    action("delete_view", { id: vid }, msg);
  }

  function deleteSel() {
    const id = S.sel;
    if (!id) return;
    if (String(id).startsWith("view:")) return deleteView(id.slice(5));
    if (!findAnn(id)) return;
    S.sel = null;
    commit(doc => { doc.annotations = doc.annotations.filter(a => a.id !== id && a.attach !== id); });
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    $("stepInput").addEventListener("change", (e) => { openAny(e.target.files[0]); e.target.value = ""; });
    $("projInput").addEventListener("change", (e) => { openProject(e.target.files[0]); e.target.value = ""; });
    $("saveProj").addEventListener("click", saveProject);
    for (const b of document.querySelectorAll("[data-fmt]")) b.addEventListener("click", () => exportAs(b.dataset.fmt));
    $("undo").addEventListener("click", undo);
    $("redo").addEventListener("click", redo);
    for (const b of document.querySelectorAll("#tools button")) b.addEventListener("click", () => { if (S.doc) setTool(b.dataset.tool); });

    const mat = $("mat");
    ["dragenter", "dragover"].forEach(t => mat.addEventListener(t, (e) => { e.preventDefault(); $("drop").classList.add("over"); }));
    ["dragleave", "drop"].forEach(t => mat.addEventListener(t, (e) => { e.preventDefault(); $("drop").classList.remove("over"); }));
    mat.addEventListener("drop", (e) => openAny(e.dataTransfer.files[0]));

    mat.addEventListener("pointerdown", onPointerDown);
    mat.addEventListener("pointermove", onPointerMove);
    mat.addEventListener("pointerup", onPointerUp);
    mat.addEventListener("pointercancel", () => { drag = null; mat.classList.remove("panning"); });
    mat.addEventListener("contextmenu", (e) => e.preventDefault());
    mat.addEventListener("pointerleave", () => { if (!drag && S.tool !== "select") { clearTargets(); OV.flush(); } });
    mat.addEventListener("dblclick", (e) => {
      if (S.tool === "section" && T.stage === 0 && T.pts && T.pts.length >= 2) { e.preventDefault(); finishSectionLine(); }
    });
    mat.addEventListener("wheel", (e) => {
      if (!S.doc) return;
      e.preventDefault();
      const r = mat.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomAt(Math.exp(-dy * 0.0016), e.clientX - r.left, e.clientY - r.top);
      refreshOverlay();
    }, { passive: false });
    $("zoomIn").addEventListener("click", () => { const r = mat.getBoundingClientRect(); zoomAt(1.25, r.width / 2, r.height / 2); });
    $("zoomOut").addEventListener("click", () => { const r = mat.getBoundingClientRect(); zoomAt(0.8, r.width / 2, r.height / 2); });
    $("fit").addEventListener("click", fit);
    window.addEventListener("resize", () => { if (S.doc) fit(); });

    // views
    for (const b of document.querySelectorAll("#addViews button")) b.addEventListener("click", () => action("add_view", { type: b.dataset.view }));
    $("rearrange").addEventListener("click", () => action("rearrange", {}, "Pick a new scale and re-arrange all views? Annotations stay with their views."));

    // sheet
    const set = (fn) => commit(doc => fn(doc.settings));
    $("setSheet").addEventListener("change", (e) => {
      pushHist();
      S.doc.settings.sheet = e.target.value;
      action("rearrange", {}, null, true);
    });
    $("setScale").addEventListener("change", (e) => set(s => { s.scale = +e.target.value; }));
    $("setProjection").addEventListener("click", (e) => {
      const v = e.target.dataset.v;
      if (!v || v === S.doc.settings.projection) return;
      if (confirm(`Switch to ${v} angle projection and move the views to match? Annotations stay with their views.\n\nCancel changes only the projection symbol.`)) {
        pushHist();
        S.doc.settings.projection = v;
        action("rearrange", {}, null, true);
      } else set(s => { s.projection = v; });
    });
    $("setStandard").addEventListener("click", (e) => { const v = e.target.dataset.v; if (v) action("standard", { standard: v }); });
    $("setHidden").addEventListener("change", (e) => set(s => { s.hidden = e.target.checked; }));
    $("setTangent").addEventListener("change", (e) => set(s => { s.tangent = e.target.checked; }));
    $("setCenter").addEventListener("change", (e) => set(s => { s.centerlines = e.target.checked; }));
    $("setText").addEventListener("change", (e) => set(s => { s.text_height = +e.target.value; }));
    $("setDec").addEventListener("change", (e) => set(s => { s.decimals = +e.target.value; }));
    $("reorient").addEventListener("click", (e) => {
      const w = e.target.closest("button") && e.target.closest("button").dataset.w;
      if (w) action("reorient", { which: w }, "Changing the front view redraws every view and removes all annotations and section views. Continue?");
    });
    $("notes").addEventListener("change", (e) => commit(doc => { doc.notes = e.target.value.split("\n"); }));
    $("setBody").addEventListener("change", (e) => action("body", { body: e.target.value },
      "Switching body redraws every view and removes all annotations and section views. Continue?"));

    document.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if (mod && e.key.toLowerCase() === "y" && !typing) { e.preventDefault(); redo(); return; }
      if (typing || mod || !S.doc) return;
      const k = e.key.toLowerCase();
      if (e.key === "Escape") {
        if (S.tool !== "select" && (T.stage || (T.pts && T.pts.length))) { setTool(S.tool); }
        else if (S.tool !== "select") setTool("select");
        else select(null);
      } else if (e.key === "Enter" && S.tool === "section") finishSectionLine();
      else if ((e.key === "Delete" || e.key === "Backspace") && S.sel && S.tool === "select") { e.preventDefault(); deleteSel(); }
      else if (k === "v") setTool("select");
      else if (k === "d") setTool("dim");
      else if (k === "a") setTool("datum");
      else if (k === "t") setTool("tol");
      else if (k === "n") setTool("note");
      else if (k === "s") setTool("section");
      else if (k === "f" || k === "0") fit();
    });
  }

  async function loadSamples() {
    try {
      const r = await fetch("/api/samples");
      const { samples } = await r.json();
      const box = $("samples");
      if (!samples.length) return;
      box.append("Or try a sample part:");
      for (const n of samples) {
        box.append(el("button", { text: n.replace(/\.(step|stp)$/i, "").replace(/_/g, " "), onclick: () => openSample(n) }));
      }
    } catch { /* samples are optional */ }
  }

  async function boot() {
    wire();
    loadSamples();
    setTool("select");
    const err = /error=([^&]+)/.exec(location.hash);
    if (err) { toast(decodeURIComponent(err[1])); history.replaceState(null, "", "#"); }
    const m = /sid=([a-f0-9]+)/.exec(location.hash);
    if (m) {
      try {
        const st = await api("/api/render", { sid: m[1], full: true });
        applyState(st, false);
      } catch { history.replaceState(null, "", "#"); }
    }
  }

  boot();
})();
