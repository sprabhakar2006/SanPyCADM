"""Sheet geometry, view grid (first/third angle), automatic scale and view placement."""
from .document import SCALES, SHEETS

BORDER_L, BORDER_O = 20.0, 10.0       # ISO 5457: 20 mm filing margin on the left
TB_W, TB_H = 180.0, 40.0
CELL_GAP = 18.0                       # extra space between neighbouring views
DIM_GAP0 = 10.0                       # first dimension line distance from the outline
DIM_STEP = 8.0                        # spacing between stacked dimension lines

GRID = {
    "first": {"front": (0, 0), "top": (0, -1), "bottom": (0, 1), "left": (1, 0), "right": (-1, 0), "rear": (2, 0)},
    "third": {"front": (0, 0), "top": (0, 1), "bottom": (0, -1), "left": (-1, 0), "right": (1, 0), "rear": (2, 0)},
}
ISO_PREF = {"first": [(1, -1), (-1, -1), (1, 1), (-1, 1), (1, 0)],
            "third": [(1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0)]}


def grid_cells(views, projection):
    g = GRID.get(projection, GRID["first"])
    cells = {v: g[v] for v in views if v in g}
    if "iso" in views:
        used = set(cells.values())
        for c in ISO_PREF.get(projection, ISO_PREF["first"]):
            if c not in used:
                cells["iso"] = c
                break
    if not cells:
        return cells
    if "front" not in cells and cells:
        pass
    return cells


def neighbours(cells, name):
    """Which sides of view `name` face another view: {'top','bottom','left','right'}."""
    if name not in cells:
        return set()
    c, r = cells[name]
    occ = set(v for k, v in cells.items() if k != name)
    out = set()
    if (c, r + 1) in occ:
        out.add("top")
    if (c, r - 1) in occ:
        out.add("bottom")
    if (c - 1, r) in occ:
        out.add("left")
    if (c + 1, r) in occ:
        out.add("right")
    return out


def sheet_rects(sheet):
    W, H = SHEETS.get(sheet, SHEETS["A3"])
    border = (BORDER_L, BORDER_O, W - BORDER_O, H - BORDER_O)
    tb = (W - BORDER_O - TB_W, BORDER_O, W - BORDER_O, BORDER_O + TB_H)
    notes = (BORDER_L + 4, BORDER_O + 3, tb[0] - 6, BORDER_O + TB_H)
    region = (BORDER_L + 6, BORDER_O + TB_H + 6, W - BORDER_O - 6, H - BORDER_O - 6)
    return W, H, border, tb, notes, region


class Layout:
    def __init__(self, sheet, W, H, border, tb, notes, region):
        self.sheet = sheet
        self.W, self.H = W, H
        self.border, self.tb, self.notes, self.region = border, tb, notes, region
        self.scale = 1.0
        self.views = {}      # name -> {"origin", "scale", "bbox", "rect"}

    def to_paper(self, view, p):
        v = self.views[view]
        s = v["scale"]
        return (v["origin"][0] + s * p[0], v["origin"][1] + s * p[1])

    def rect(self, view):
        return self.views[view]["rect"]

    def to_dict(self):
        return {"sheet": self.sheet, "W": self.W, "H": self.H, "scale": self.scale,
                "border": self.border, "tb": self.tb, "region": self.region,
                "views": {k: {"origin": v["origin"], "scale": v["scale"], "rect": v["rect"]} for k, v in self.views.items()}}


NICE_ISO = [10, 5, 4, 3, 2, 1.5, 1, 0.75, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1, 0.075, 0.05, 0.04, 0.03,
            0.025, 0.02, 0.015, 0.01]
ISO_LABEL = 12.0


def place_views(doc, geoms, gutters):
    """Pick the scale (unless fixed) and position every view.

    Orthographic views sit on the projection grid at one scale. The isometric
    view is an illustration: it goes into whichever free area (an empty grid
    corner, a strip to the right, or a strip below) lets it be largest, at a
    tidy scale no larger than the main scale. The whole composition is centred.

    geoms:   name -> ViewGeom (model-space bbox)
    gutters: name -> {"top","bottom","left","right"} paper mm reserved around the view
    """
    st = doc["settings"]
    W, H, border, tb, notes, region = sheet_rects(st["sheet"])
    lay = Layout(st["sheet"], W, H, border, tb, notes, region)
    views = [v for v in st["views"] if v in geoms]
    cells = grid_cells(views, st["projection"])
    if not cells:
        return lay
    ortho = {n: c for n, c in cells.items() if n != "iso"}
    iso_cell = cells.get("iso")
    rw, rh = region[2] - region[0], region[3] - region[1]
    iso_b = geoms["iso"].bbox if iso_cell else None
    iso_w = (iso_b[2] - iso_b[0]) if iso_b else 0.0
    iso_h = (iso_b[3] - iso_b[1]) if iso_b else 0.0

    def size(name, s):
        b = geoms[name].bbox
        g = gutters.get(name, {})
        return (g.get("left", 4) + (b[2] - b[0]) * s + g.get("right", 4),
                g.get("bottom", 4) + (b[3] - b[1]) * s + g.get("top", 4))

    def block(s):
        cols, rows = {}, {}
        for n, (c, r) in ortho.items():
            w, h = size(n, s)
            cols[c] = max(cols.get(c, 0), w)
            rows[r] = max(rows.get(r, 0), h)
        bw = sum(cols.values()) + CELL_GAP * (len(cols) - 1) if cols else 0.0
        bh = sum(rows.values()) + CELL_GAP * (len(rows) - 1) if rows else 0.0
        return bw, bh, cols, rows

    def nice(limit):
        opts = [x for x in NICE_ISO if x <= limit + 1e-12]
        return opts[0] if opts else 0.0

    def fit_iso(w, h, s):
        if w <= 6 or h <= ISO_LABEL + 4:
            return 0.0
        return nice(min(s, (w - 6) / max(iso_w, 1e-9), (h - ISO_LABEL - 4) / max(iso_h, 1e-9)))

    def grid_xy(x0, y0, cols, rows):
        colx, x = {}, x0
        for c in sorted(cols):
            colx[c] = x
            x += cols[c] + CELL_GAP
        rowy, y = {}, y0
        for r in sorted(rows):
            rowy[r] = y
            y += rows[r] + CELL_GAP
        return colx, rowy

    def cell_rect(bw, bh, cols, rows):
        ci, ri = iso_cell
        if ci not in cols or ri not in rows:
            return None
        colx, rowy = grid_xy(region[0] + (rw - bw) / 2, region[1] + (rh - bh) / 2, cols, rows)
        fx0, fx1 = colx[ci], colx[ci] + cols[ci]
        fy0, fy1 = rowy[ri], rowy[ri] + rows[ri]
        if ci == max(cols):
            fx1 = region[2]
        if ci == min(cols):
            fx0 = region[0]
        if ri == max(rows):
            fy1 = region[3]
        if ri == min(rows):
            fy0 = region[1]
        return (fx0, fy0, fx1, fy1)

    def iso_options(s, bw, bh, cols, rows):
        if not iso_cell:
            return [(s, 9, "none")]
        out = []
        cr = cell_rect(bw, bh, cols, rows)
        if cr:
            out.append((fit_iso(cr[2] - cr[0], cr[3] - cr[1], s), 2, "cell"))
        out.append((fit_iso(rw - bw - CELL_GAP, rh, s), 1, "right"))
        out.append((fit_iso(rw, rh - bh - CELL_GAP, s), 0, "below"))
        return out

    fixed = st.get("scale")
    candidates = [float(fixed)] if fixed else SCALES
    chosen = None
    for i, s in enumerate(candidates):
        bw, bh, cols, rows = block(s)
        if bw > rw or bh > rh:
            continue
        opt = max(iso_options(s, bw, bh, cols, rows))
        if iso_cell and not fixed and opt[0] < 0.2 * s and i + 1 < len(candidates):
            s2 = candidates[i + 1]
            b2 = block(s2)
            if max(iso_options(s2, *b2))[0] >= 0.5 * s2:
                continue          # one step smaller gives a properly sized iso
        chosen = (s, opt, bw, bh, cols, rows)
        break
    if chosen is None:            # nothing fits: smallest candidate, let it overflow
        s = candidates[-1]
        bw, bh, cols, rows = block(s)
        chosen = (s, max(iso_options(s, bw, bh, cols, rows)), bw, bh, cols, rows)
    s, (si, _, strat), bw, bh, cols, rows = chosen
    lay.scale = s
    w_iso, h_iso = iso_w * si, iso_h * si + ISO_LABEL

    iso_rect = None
    if strat == "right" and si > 0:
        tot = bw + CELL_GAP + w_iso
        x0 = region[0] + max(0.0, (rw - tot) / 2)
        y0 = region[1] + (rh - bh) / 2
        iso_rect = (x0 + bw + CELL_GAP, region[1], x0 + bw + CELL_GAP + w_iso, region[3])
    elif strat == "below" and si > 0:
        tot = bh + CELL_GAP + h_iso
        ybase = region[1] + max(0.0, (rh - tot) / 2)
        y0 = ybase + h_iso + CELL_GAP
        x0 = region[0] + (rw - bw) / 2
        iso_rect = (region[0], ybase, region[2], ybase + h_iso)
    else:
        x0 = region[0] + (rw - bw) / 2
        y0 = region[1] + (rh - bh) / 2
        if strat == "cell" and si > 0:
            iso_rect = cell_rect(bw, bh, cols, rows)
    colx, rowy = grid_xy(x0, y0, cols, rows)

    gl, gb = {}, {}
    for n, (c, r) in ortho.items():
        gl[c] = max(gl.get(c, 0), gutters.get(n, {}).get("left", 4))
        gb[r] = max(gb.get(r, 0), gutters.get(n, {}).get("bottom", 4))

    offs = doc.get("view_offsets", {})
    for n, (c, r) in ortho.items():
        b = geoms[n].bbox
        px = colx[c] + gl.get(c, 4)
        py = rowy[r] + gb.get(r, 4)
        dx, dy = offs.get(n, (0, 0))
        ox, oy = px - b[0] * s + dx, py - b[1] * s + dy
        rect = [ox + b[0] * s, oy + b[1] * s, ox + b[2] * s, oy + b[3] * s]
        lay.views[n] = {"origin": (ox, oy), "scale": s, "bbox": b, "rect": rect, "cell": (c, r)}

    if iso_cell and si > 0 and iso_rect:
        fx0, fy0, fx1, fy1 = iso_rect
        w, h = iso_w * si, iso_h * si
        px = fx0 + (fx1 - fx0 - w) / 2
        py = fy0 + ISO_LABEL + (fy1 - fy0 - ISO_LABEL - h) / 2
        dx, dy = offs.get("iso", (0, 0))
        ox, oy = px - iso_b[0] * si + dx, py - iso_b[1] * si + dy
        rect = [ox + iso_b[0] * si, oy + iso_b[1] * si, ox + iso_b[2] * si, oy + iso_b[3] * si]
        lay.views["iso"] = {"origin": (ox, oy), "scale": si, "bbox": iso_b, "rect": rect, "cell": iso_cell}
    return lay


# ----------------------------------------------------------------------------
# Explicit placement: every view in doc["views"] carries a paper "center".

STANDARD = ("front", "top", "bottom", "left", "right", "rear", "iso")
FREE_MARGIN = 16.0          # room kept around a view for its dimensions


def _rect_for(geom, scale, center):
    b = geom.bbox
    w, h = (b[2] - b[0]) * scale, (b[3] - b[1]) * scale
    return [center[0] - w / 2, center[1] - h / 2, center[0] + w / 2, center[1] + h / 2]


def layout_views(doc, geoms):
    """Layout from the stored view centres (views without a centre are skipped)."""
    st = doc["settings"]
    W, H, border, tb, notes, region = sheet_rects(st["sheet"])
    lay = Layout(st["sheet"], W, H, border, tb, notes, region)
    lay.scale = float(st.get("scale") or 1.0)
    for v in doc.get("views", []):
        vid = v["id"]
        if vid not in geoms or not v.get("center"):
            continue
        g = geoms[vid]
        s = float(v.get("scale") or lay.scale)
        b = g.bbox
        cx, cy = v["center"]
        ox = cx - s * (b[0] + b[2]) / 2
        oy = cy - s * (b[1] + b[3]) / 2
        rect = [ox + b[0] * s, oy + b[1] * s, ox + b[2] * s, oy + b[3] * s]
        lay.views[vid] = {"origin": (ox, oy), "scale": s, "bbox": b, "rect": rect}
    return lay


def _overlaps(r, s, pad=0.0):
    return not (r[2] + pad <= s[0] or s[2] + pad <= r[0] or r[3] + pad <= s[1] or s[3] + pad <= r[1])


def find_spot(lay, w, h, pref, avoid_extra=()):
    """Centre for a w x h view: free of other views (plus margins), inside the
    drawing area, as close as possible to `pref`."""
    region = lay.region
    occupied = [list(lay.tb), list(lay.notes)] + [list(r) for r in avoid_extra]
    occupied += [[r[0] - FREE_MARGIN, r[1] - FREE_MARGIN, r[2] + FREE_MARGIN, r[3] + FREE_MARGIN]
                 for r in (v["rect"] for v in lay.views.values())]
    m = FREE_MARGIN
    x_lo, x_hi = region[0] + w / 2 + m, region[2] - w / 2 - m
    y_lo, y_hi = region[1] + h / 2 + m, region[3] - h / 2 - m
    best = None
    if x_lo <= x_hi and y_lo <= y_hi:
        step = 4.0
        nx = int((x_hi - x_lo) / step) + 1
        ny = int((y_hi - y_lo) / step) + 1
        for i in range(nx + 1):
            x = min(x_lo + i * step, x_hi)
            for j in range(ny + 1):
                y = min(y_lo + j * step, y_hi)
                r = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
                if any(_overlaps(r, o) for o in occupied):
                    continue
                d = (x - pref[0]) ** 2 + (y - pref[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, (x, y))
    if best:
        return list(best[1])
    # sheet is full: keep it where it was wanted, inside the drawing area
    return [min(max(pref[0], region[0] + w / 2), region[2] - w / 2),
            min(max(pref[1], region[1] + h / 2), region[3] - h / 2)]


def preferred_center(lay, doc, geoms, view):
    """Where a view would conventionally go relative to its parent / the front view."""
    st = doc["settings"]
    proj = st.get("projection", "first")
    vid = view["id"]
    s = float(view.get("scale") or lay.scale)
    g = geoms[vid]
    w = (g.bbox[2] - g.bbox[0]) * s
    h = (g.bbox[3] - g.bbox[1]) * s
    if view.get("type") == "section":
        parent = lay.views.get(view.get("parent"))
        if not parent:
            return [(lay.region[0] + lay.region[2]) / 2, (lay.region[1] + lay.region[3]) / 2]
        pr = parent["rect"]
        pc = ((pr[0] + pr[2]) / 2, (pr[1] + pr[3]) / 2)
        d = view["dir"]
        sgn = 1.0 if proj == "first" else -1.0
        gap = FREE_MARGIN * 2 + 6
        if abs(d[0]) >= abs(d[1]):
            return [pc[0] + sgn * (1 if d[0] > 0 else -1) * ((pr[2] - pr[0]) / 2 + gap + w / 2), pc[1]]
        return [pc[0], pc[1] + sgn * (1 if d[1] > 0 else -1) * ((pr[3] - pr[1]) / 2 + gap + h / 2)]
    front = lay.views.get("front")
    if front and vid in GRID.get(proj, GRID["first"]):
        c, r = GRID.get(proj, GRID["first"])[vid]
        fr = front["rect"]
        fc = ((fr[0] + fr[2]) / 2, (fr[1] + fr[3]) / 2)
        gap = FREE_MARGIN * 2 + 6
        return [fc[0] + c * ((fr[2] - fr[0]) / 2 + gap + w / 2), fc[1] + r * ((fr[3] - fr[1]) / 2 + gap + h / 2)]
    if vid == "iso":
        rg = lay.region
        return [rg[2] - w / 2 - 20, rg[3] - h / 2 - 20] if proj == "third" else [rg[2] - w / 2 - 20, rg[1] + h / 2 + 40]
    return [(lay.region[0] + lay.region[2]) / 2, (lay.region[1] + lay.region[3]) / 2]


def auto_arrange(doc, geoms, gutters):
    """First-time (or 'Re-arrange views') placement: grid layout for the standard
    views with an automatic scale unless one is set, then the rest in free space."""
    st = doc["settings"]
    views = doc.get("views", [])
    std_ids = [v["id"] for v in views if v.get("type") in STANDARD and v["id"] in geoms]
    tmp = {"settings": dict(st, views=std_ids), "view_offsets": {}}
    lay = place_views(tmp, {k: geoms[k] for k in std_ids}, gutters)
    st["scale"] = lay.scale
    for v in views:
        info = lay.views.get(v["id"])
        if info:
            r = info["rect"]
            v["center"] = [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]
            v["scale"] = info["scale"] if abs(info["scale"] - lay.scale) > 1e-12 else None
        elif v.get("type") not in STANDARD:
            v["center"] = None
    place_missing(doc, geoms)


def place_missing(doc, geoms):
    """Give every view without a centre a free spot near its conventional place."""
    pending = [v for v in doc.get("views", []) if not v.get("center") and v["id"] in geoms]
    for v in pending:
        lay = layout_views(doc, geoms)
        s = float(v.get("scale") or lay.scale)
        g = geoms[v["id"]]
        w = (g.bbox[2] - g.bbox[0]) * s
        h = (g.bbox[3] - g.bbox[1]) * s + (12 if v.get("type") in ("iso", "section") else 0)
        pref = preferred_center(lay, doc, geoms, v)
        v["center"] = find_spot(lay, w, h, pref)


def alignment_rules(doc, geoms, lay):
    """Pairs of views that project along a shared axis: {view: [{axis, to, off}]}.
    Aligned when center[axis] == partner center[axis] + off."""
    out = {}
    ids = [v["id"] for v in doc.get("views", []) if v["id"] in lay.views and v.get("type") != "iso"]
    for a in ids:
        ga, la = geoms[a], lay.views[a]
        for b in ids:
            if a == b:
                continue
            gb, lb = geoms[b], lay.views[b]
            if abs(la["scale"] - lb["scale"]) > 1e-12:
                continue
            s = la["scale"]
            for axis, k, va, vb in (("x", 0, ga.Vx, gb.Vx), ("y", 1, ga.Vy, gb.Vy)):
                if sum(x * y for x, y in zip(va, vb)) > 1 - 1e-6:
                    ca = (ga.bbox[k] + ga.bbox[k + 2]) / 2
                    cb = (gb.bbox[k] + gb.bbox[k + 2]) / 2
                    out.setdefault(a, []).append({"axis": axis, "to": b, "off": s * (ca - cb)})
    return out
