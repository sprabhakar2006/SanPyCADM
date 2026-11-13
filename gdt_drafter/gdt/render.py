"""Turn the drawing document + geometry into sheet primitives."""
import math

from . import vec as V
from .canvas import Canvas, HIDDEN_W, THICK, THIN, item_points
from .document import SCALES, fmt, fmt_dev, scale_label
from .fonts import text_width
from .layout import DIM_GAP0, DIM_STEP
from .frame import VIEW_LABELS
from .projection import sample
from .section import hatch_lines, keeps_cylinder
from .symbols import CHARACTERISTICS, draw_runs, draw_symbol, parse, runs_height, runs_width

ARROW = 3.0
EXT_GAP = 1.0
EXT_OVER = 2.0
BOX = 7.0          # datum box side


class Ctx:
    def __init__(self, part, doc, geoms, lay):
        self.part = part
        self.doc = doc
        self.geoms = geoms
        self.lay = lay
        st = doc["settings"]
        self.h = float(st.get("text_height", 3.5))
        self.dec = int(st.get("decimals", 2))
        self.ann = {a["id"]: a for a in doc["annotations"]}
        self.vmeta = {v["id"]: v for v in doc.get("views", [])}
        self.children = {}
        for a in doc["annotations"]:
            if a.get("attach"):
                self.children.setdefault(a["attach"], []).append(a)

    def P(self, view, p):
        return self.lay.to_paper(view, p)

    def s(self, view):
        return self.lay.views[view]["scale"]


# ------------------------------------------------------------- transforms

def place_items(cv, items, origin, rot):
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    f = lambda p: (origin[0] + p[0] * ca - p[1] * sa, origin[1] + p[0] * sa + p[1] * ca)
    for it in items:
        t = it["t"]
        if t == "line":
            cv.line(f(it["a"]), f(it["b"]), w=it["w"], dash=it["dash"], layer=it["layer"])
        elif t == "poly":
            cv.poly([f(p) for p in it["pts"]], w=it["w"], closed=it["closed"], fill=it["fill"], dash=it["dash"], layer=it["layer"])
        elif t == "circle":
            cv.circle(f(it["c"]), it["r"], w=it["w"], fill=it["fill"], dash=it["dash"], layer=it["layer"])
        elif t == "arc":
            cv.arc(f(it["c"]), it["r"], it["a0"] + rot, it["a1"] + rot, w=it["w"], dash=it["dash"], layer=it["layer"])
        elif t == "rect":
            pts = [(it["x0"], it["y0"]), (it["x1"], it["y0"]), (it["x1"], it["y1"]), (it["x0"], it["y1"])]
            if it.get("fill"):
                cv.poly([f(p) for p in pts], w=0.01, closed=True, fill=it["fill"], layer=it["layer"])
            if it.get("stroke", True):
                cv.poly([f(p) for p in pts], w=it["w"], closed=True, layer=it["layer"])
        elif t == "text":
            cv.text(f(it["p"]), it["s"], it["h"], anchor=it["anchor"], rot=it.get("rot", 0) + rot, layer=it["layer"])


def halo_runs(cv, runs, x, y, h, anchor="start", rot=0.0, halo=True, layer="DIM"):
    """Draw rich-text runs at (x, y) baseline, optionally rotated, with a white halo."""
    tmp = Canvas()
    W = runs_width(runs, h)
    lo, hi = runs_height(runs, h)
    x0 = -W / 2 if anchor == "middle" else (-W if anchor == "end" else 0.0)
    if halo:
        tmp.rect(x0 - 0.6, -lo, x0 + W + 0.6, hi, w=0.01, fill="white", stroke=False, layer=layer)
    draw_runs(tmp, runs, x0, 0.0, h, layer=layer)
    place_items(cv, tmp.items, (x, y), rot)
    return W, lo, hi


# ------------------------------------------------------------- value text

def value_runs(ctx, value, tol, prefix="", count="", override=""):
    dec = ctx.dec
    v = fmt(value, dec)
    mode = (tol or {}).get("mode", "none")
    up, lo = (tol or {}).get("up", 0.0), (tol or {}).get("lo", 0.0)
    core = parse(prefix) + [("t", v)]
    if mode == "basic":
        core = [("box", core)]
    elif mode == "sym":
        core = core + [("t", " ±" + fmt(abs(up), 3))]
    elif mode == "dev":
        core = core + [("tol", fmt_dev(up), fmt_dev(lo))]
    elif mode == "limits":
        core = parse(prefix) + [("tol", fmt(value + up, 3), fmt(value + lo, 3))]
    elif mode == "ref":
        core = [("t", "(")] + core + [("t", ")")]
    if override:
        if "<>" in override:
            a, b = override.split("<>", 1)
            return parse(a) + core + parse(b)
        return parse(override)
    return (parse(count + " ") if count else []) + core


def line_runs(ctx, line, size, tol):
    """Callout line with a {size} token (number + tolerance)."""
    if "{size}" not in line:
        return parse(line)
    a, b = line.split("{size}", 1)
    prefix = ""
    if (tol or {}).get("mode") == "basic":       # the box encloses ⌀ / R as well
        for p in ("S⌀", "⌀", "Ø", "SR", "R"):
            if a.endswith(p):
                a, prefix = a[: -len(p)], p
                break
    return parse(a) + value_runs(ctx, size, tol, prefix) + parse(b)


# ------------------------------------------------------------- geometry

HATCH_SPACING = 2.5         # paper mm


def view_caption(ctx, vid):
    meta = ctx.vmeta.get(vid, {})
    info = ctx.lay.views[vid]
    if meta.get("type") == "section":
        L = meta.get("letter", "A")
        lab = ("SECTION %s-%s" if ctx.doc["settings"].get("standard") == "ASME" else "%s-%s") % (L, L)
    else:
        lab = VIEW_LABELS.get(meta.get("type", vid), vid.upper())
    s = info["scale"]
    # A pictorial view fitted at an in-between size (0.75 and the like) is not a
    # drawing scale anyone reads off, so only standard scales are written.
    if abs(s - ctx.lay.scale) > 1e-9 and any(abs(s - x) < 1e-9 for x in SCALES):
        lab += "  SCALE " + scale_label(s)
    return lab


def draw_views(cv, ctx):
    st = ctx.doc["settings"]
    for name, info in ctx.lay.views.items():
        vg = ctx.geoms[name]
        meta = ctx.vmeta.get(name, {})
        cv.begin("view:" + name, "view")
        s = info["scale"]
        P = lambda p: ctx.P(name, p)
        show_hidden = meta.get("hidden")
        if show_hidden is None:
            show_hidden = st.get("hidden", True)
        if show_hidden:
            for c in vg.hidden:
                _curve(cv, c, P, s, HIDDEN_W, "hidden", "HIDDEN")
        if st.get("tangent", True):
            for c in vg.tangent:
                _curve(cv, c, P, s, 0.18, None, "TANGENT")
        for c in getattr(vg, "cut_loops", None) and hatch_lines(vg.cut_loops, HATCH_SPACING / s) or []:
            _curve(cv, c, P, s, 0.18, None, "HATCH")
        for c in vg.visible:
            _curve(cv, c, P, s, THICK, None, "VISIBLE")
        r = info["rect"]
        if meta.get("label"):
            iso_above = meta.get("type") == "section" and st.get("standard") != "ASME"
            y = r[3] + 4 if iso_above else r[1] - 7
            cv.text(((r[0] + r[2]) / 2, y), view_caption(ctx, name), 2.5 if meta.get("type") == "iso" else 3.5,
                    anchor="middle", layer="TEXT")
        cv.hit(r[0] - 2, r[1] - 2, r[2] + 2, r[3] + 2)
        cv.end()


def _exit_point(E, w, R):
    """E moved along unit w until it leaves rectangle R (or by 3 mm if outside)."""
    inside = R[0] <= E[0] <= R[2] and R[1] <= E[1] <= R[3]
    if not inside:
        return (E[0] + w[0] * 3, E[1] + w[1] * 3)
    ts = []
    for k, lo, hi in ((0, R[0], R[2]), (1, R[1], R[3])):
        if abs(w[k]) > 1e-12:
            ts.append(((hi if w[k] > 0 else lo) - E[k]) / w[k])
    t = min(ts) if ts else 0.0
    return (E[0] + w[0] * t, E[1] + w[1] * t)


def _band(pts, half):
    """Polygon around a polyline (for pick areas)."""
    left, right = [], []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        d = V.unit((b[0] - a[0], b[1] - a[1]))
        n = (-d[1] * half, d[0] * half)
        left.append((p[0] + n[0], p[1] + n[1]))
        right.append((p[0] - n[0], p[1] - n[1]))
    return left + right[::-1]


def draw_cut_lines(cv, ctx):
    """Cutting-plane lines (ISO 128 type H) with arrows and letters on parent views."""
    asme = ctx.doc["settings"].get("standard") == "ASME"
    for vid, meta in ctx.vmeta.items():
        if meta.get("type") != "section" or meta.get("parent") not in ctx.lay.views:
            continue
        parent = meta["parent"]
        pts = [ctx.P(parent, p) for p in meta["pts"]]
        if len(pts) < 2:
            continue
        d = V.unit((meta["dir"][0], meta["dir"][1]))
        r = ctx.lay.views[parent]["rect"]
        R = [r[0] - 5, r[1] - 5, r[2] + 5, r[3] + 5]
        w0 = V.unit((pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]))
        wk = V.unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))
        pts[0] = _exit_point(pts[0], w0, R)
        pts[-1] = _exit_point(pts[-1], wk, R)
        cv.begin("cut:" + vid, "cut")
        cv.poly(pts, w=THIN, dash="center", layer="CUT")
        letter = meta.get("letter", "A")
        for E, w in ((pts[0], w0), (pts[-1], wk)):
            inner = (E[0] - w[0] * 8, E[1] - w[1] * 8)
            cv.line(E, inner, w=0.7, layer="CUT")
            M = (E[0] - w[0] * 4, E[1] - w[1] * 4)
            if asme:
                tail, tip = M, (M[0] + d[0] * 10, M[1] + d[1] * 10)
                lp = (tip[0] + d[0] * 4, tip[1] + d[1] * 4)
            else:
                tail, tip = (M[0] - d[0] * 10, M[1] - d[1] * 10), M
                lp = (tail[0] - d[0] * 4, tail[1] - d[1] * 4)
            cv.line(tail, tip, w=THIN, layer="CUT")
            cv.arrow(tip, tail, ARROW, layer="CUT")
            cv.text((lp[0], lp[1] - ctx.h / 2), letter, ctx.h, anchor="middle", layer="TEXT")
        for i in range(1, len(pts) - 1):
            a, p, b = pts[i - 1], pts[i], pts[i + 1]
            da = V.unit((p[0] - a[0], p[1] - a[1]))
            db = V.unit((b[0] - p[0], b[1] - p[1]))
            cv.line((p[0] - da[0] * 4, p[1] - da[1] * 4), p, w=0.7, layer="CUT")
            cv.line(p, (p[0] + db[0] * 4, p[1] + db[1] * 4), w=0.7, layer="CUT")
        cv.hitpoly(_band(pts, 2.0))
        cv.end()


def _curve(cv, c, P, s, w, dash, layer):
    k = c["k"]
    if k == "L":
        x1, y1, x2, y2 = c["p"]
        cv.line(P((x1, y1)), P((x2, y2)), w=w, dash=dash, layer=layer)
    elif k == "C":
        cv.circle(P(c["c"]), c["r"] * s, w=w, dash=dash, layer=layer)
    elif k == "A":
        cv.arc(P(c["c"]), c["r"] * s, c["a0"], c["a1"], w=w, dash=dash, layer=layer)
    else:
        cv.poly([P(p) for p in c["pts"]], w=w, dash=dash, layer=layer)


def centerline_geom(ctx, name):
    """Centre lines of one view in view model coordinates.

    Returns (marks, axes): marks are (centre, arm length, dashed) crosses on
    holes seen end-on, axes are (a, b) axis lines of holes seen side-on, both
    already extended past the feature as drawn."""
    vg = ctx.geoms[name]
    s = ctx.lay.views[name]["scale"]
    marks, lines = [], []          # lines: (dir2, offset, t0, t1) merged per axis line
    for c in ctx.part.cyls:
        if c.kind not in ("hole", "boss") or c.absorbed:
            continue
        if getattr(vg, "kind", "") == "section" and not keeps_cylinder(vg, c):
            continue
        ad = abs(V.dot(c.axis, vg.N))
        if ad > 1 - 1e-3:
            r = c.radius * s
            if c.cbore:
                r = max(r, c.cbore["radius"] * s)
            if c.csink:
                r = max(r, c.csink["diameter"] * s / 2)
            marks.append((vg.project(c.center), (r + 2.5) / s, r > 4))
        elif ad < 1e-3:
            p0 = vg.project(c.point_at(c.t0))
            p1 = vg.project(c.point_at(c.t1))
            d = V.unit((p1[0] - p0[0], p1[1] - p0[1]))
            d = d if (d[0] > 1e-9 or (abs(d[0]) <= 1e-9 and d[1] > 0)) else (-d[0], -d[1])
            nrm = (-d[1], d[0])
            off = V.dot(p0, nrm)
            ta, tb = sorted((V.dot(p0, d), V.dot(p1, d)))
            for L in lines:
                if abs(L[0][0] - d[0]) < 1e-6 and abs(L[0][1] - d[1]) < 1e-6 and abs(L[1] - off) < 1e-3:
                    L[2] = min(L[2], ta)
                    L[3] = max(L[3], tb)
                    break
            else:
                lines.append([d, off, ta, tb])
    axes = []
    for d, off, ta, tb in lines:
        nrm = (-d[1], d[0])
        ta, tb = ta - 3 / s, tb + 3 / s
        axes.append(((nrm[0] * off + d[0] * ta, nrm[1] * off + d[1] * ta),
                     (nrm[0] * off + d[0] * tb, nrm[1] * off + d[1] * tb)))
    return marks, axes


def draw_centerlines(cv, ctx):
    if not ctx.doc["settings"].get("centerlines", True):
        return
    for name in ctx.lay.views:
        if name == "iso":
            continue
        marks, axes = centerline_geom(ctx, name)
        for c, ext, dashed in marks:
            dash = "center" if dashed else None
            cv.line(ctx.P(name, (c[0] - ext, c[1])), ctx.P(name, (c[0] + ext, c[1])), w=THIN, dash=dash, layer="CENTER")
            cv.line(ctx.P(name, (c[0], c[1] - ext)), ctx.P(name, (c[0], c[1] + ext)), w=THIN, dash=dash, layer="CENTER")
        for a, b in axes:
            cv.line(ctx.P(name, a), ctx.P(name, b), w=THIN, dash="center", layer="CENTER")


# ------------------------------------------------------------- dimensions

def dim_line_pos(ctx, a):
    """Paper coordinate of the dimension line (y for 'h', x for 'v')."""
    view = a["view"]
    r = ctx.lay.views[view]["rect"]
    side = a.get("side", "top")
    if side == "at":
        if a["axis"] == "v":
            return ctx.P(view, (a.get("at", a["a"][0]), 0))[0]
        return ctx.P(view, (0, a.get("at", a["a"][1])))[1]
    gap = a.get("gap")
    if gap is None:
        gap = DIM_GAP0 + DIM_STEP * a.get("tier", 0)
    return {"top": r[3] + gap, "bottom": r[1] - gap, "left": r[0] - gap, "right": r[2] + gap}[side]


def _ext_start(ctx, a, which, P):
    """Extension lines start 1 mm off the outline, or beyond the centre mark
    when they come from a hole centre. Returns (point, setback)."""
    back = EXT_GAP
    fid = a.get("feature")
    if which == "b" and fid:
        f = ctx.part.feature(fid)
        if f is not None and hasattr(f, "radius"):
            vg = ctx.geoms[a["view"]]
            if abs(V.dot(f.axis, vg.N)) > 1 - 1e-3 and V.dist2(vg.project(f.center), a["b"]) < 1e-3:
                back = f.radius * ctx.s(a["view"]) + 3.0
    return P, back


def draw_dim(cv, ctx, a):
    view = a["view"]
    A = ctx.P(view, a["a"])
    B = ctx.P(view, a["b"])
    h = ctx.h
    k = 0 if a["axis"] == "h" else 1
    value = abs(a["b"][k] - a["a"][k])
    L = dim_line_pos(ctx, a)
    if a["axis"] == "h":
        DA, DB = (A[0], L), (B[0], L)
    else:
        DA, DB = (L, A[1]), (L, B[1])
    if a.get("side") != "at":
        for which, P, D in (("a", A, DA), ("b", B, DB)):
            P, back = _ext_start(ctx, a, which, P)
            if a["axis"] == "h":
                sgn = 1 if D[1] > P[1] else -1
                y0 = P[1] + sgn * back
                if (D[1] - y0) * sgn > 0:
                    cv.line((P[0], y0), (D[0], D[1] + sgn * EXT_OVER), w=THIN, layer="DIM")
            else:
                sgn = 1 if D[0] > P[0] else -1
                x0 = P[0] + sgn * back
                if (D[0] - x0) * sgn > 0:
                    cv.line((x0, P[1]), (D[0] + sgn * EXT_OVER, D[1]), w=THIN, layer="DIM")
    span = math.hypot(DB[0] - DA[0], DB[1] - DA[1])
    runs = value_runs(ctx, value, a.get("tol"), a.get("prefix", ""), a.get("count", ""), a.get("text", ""))
    tw = runs_width(runs, h)
    if span < 1e-6:
        return
    u = ((DB[0] - DA[0]) / span, (DB[1] - DA[1]) / span)
    if span > 2 * ARROW + 1.0:
        cv.line(DA, DB, w=THIN, layer="DIM")
        cv.arrow(DA, DB, ARROW)
        cv.arrow(DB, DA, ARROW)
    else:   # arrows outside
        cv.line((DA[0] - u[0] * (ARROW + 3), DA[1] - u[1] * (ARROW + 3)), (DB[0] + u[0] * (ARROW + 3), DB[1] + u[1] * (ARROW + 3)), w=THIN, layer="DIM")
        cv.arrow(DA, (DA[0] - u[0] * 5, DA[1] - u[1] * 5), ARROW)
        cv.arrow(DB, (DB[0] + u[0] * 5, DB[1] + u[1] * 5), ARROW)
    mid = ((DA[0] + DB[0]) / 2, (DA[1] + DB[1]) / 2)
    shift = a.get("shift", 0.0) or 0.0
    if span < tw + 2 and not shift and a.get("side") != "at":
        shift = (span + tw) / 2 + ARROW + 2
    if a["axis"] == "h":
        halo_runs(cv, runs, mid[0] + shift, mid[1] + 1.0 + runs_height(runs, h)[0] - 0.25 * h, h, anchor="middle")
    else:
        halo_runs(cv, runs, mid[0] - 1.0 - (runs_height(runs, h)[0] - 0.25 * h), mid[1] + shift, h, anchor="middle", rot=90)


# ------------------------------------------------------------- feature control frames

def fcf_parts(ctx, a):
    h = ctx.h
    tol = [("sym", "dia")] if a.get("dia") else []
    tol += [("t", fmt(a.get("tol", 0), 3))]
    if a.get("mod"):
        tol += [("circ", a["mod"])]
    if a.get("extra"):
        tol += parse(" " + a["extra"])
    cells = [("gdt", a.get("char", "position"))]
    comps = [[cells[0]], tol]
    for d in a.get("datums") or []:
        if not d or not d[0]:
            continue
        r = [("t", d[0])]
        if len(d) > 1 and d[1]:
            r.append(("circ", d[1]))
        comps.append(r)
    widths = []
    H = 2 * h
    for i, c in enumerate(comps):
        if i == 0:
            widths.append(H)
        else:
            widths.append(max(H, runs_width(c, h) + h))
    return comps, widths, H


def fcf_size(ctx, a):
    comps, widths, H = fcf_parts(ctx, a)
    return sum(widths), H


def draw_fcf_at(cv, ctx, a, x, y):
    """Frame with bottom-left at (x, y)."""
    h = ctx.h
    comps, widths, H = fcf_parts(ctx, a)
    W = sum(widths)
    cv.rect(x, y, x + W, y + H, w=0.01, fill="white", stroke=False, layer="GDT")
    cv.rect(x, y, x + W, y + H, w=THIN, layer="GDT")
    cx = x
    for i, (c, w) in enumerate(zip(comps, widths)):
        if i > 0:
            cv.line((cx, y), (cx, y + H), w=THIN, layer="GDT")
        if i == 0:
            draw_symbol(cv, c[0][1], cx + (w - h) / 2, y + (H - h) / 2, h, layer="GDT")
        else:
            draw_runs(cv, c, cx + w / 2, y + (H - h) / 2, h, anchor="middle", layer="GDT")
        cx += w
    return W, H


def draw_fcf(cv, ctx, a):
    if a.get("attach"):
        return          # drawn with its parent callout / dimension
    view = a["view"]
    P = ctx.P(view, a["anchor"])
    off = a.get("off") or [12, 12]
    K = (P[0] + off[0], P[1] + off[1])
    W, H = fcf_size(ctx, a)
    if off[0] >= 0:
        x = K[0]
    else:
        x = K[0] - W
    draw_fcf_at(cv, ctx, a, x, K[1] - H / 2)
    cv.line(P, K, w=THIN, layer="GDT")
    cv.arrow(P, K, ARROW, layer="GDT")


# ------------------------------------------------------------- datum symbols

def draw_datum_symbol(cv, ctx, base, d, letter, length):
    """Filled triangle on `base`, leader along unit d, box with letter."""
    t = (-d[1], d[0])
    tw, th = 2.2, 3.6
    p1 = (base[0] + t[0] * tw, base[1] + t[1] * tw)
    p2 = (base[0] - t[0] * tw, base[1] - t[1] * tw)
    apex = (base[0] + d[0] * th, base[1] + d[1] * th)
    cv.poly([p1, p2, apex], w=0.01, closed=True, fill=True, layer="GDT")
    end = (apex[0] + d[0] * length, apex[1] + d[1] * length)
    cv.line(apex, end, w=THIN, layer="GDT")
    c = (end[0] + d[0] * BOX / 2, end[1] + d[1] * BOX / 2)
    cv.rect(c[0] - BOX / 2, c[1] - BOX / 2, c[0] + BOX / 2, c[1] + BOX / 2, w=0.01, fill="white", stroke=False, layer="GDT")
    cv.rect(c[0] - BOX / 2, c[1] - BOX / 2, c[0] + BOX / 2, c[1] + BOX / 2, w=THIN, layer="GDT")
    cv.text((c[0], c[1] - ctx.h / 2), letter, ctx.h, anchor="middle", layer="GDT")


def datum_len(a):
    return a.get("len") if a.get("len") is not None else 4.0


def draw_datum(cv, ctx, a):
    if a.get("attach") and a["attach"] in ctx.ann:
        return          # drawn with its parent callout / dimension
    view = a["view"]
    P = ctx.P(view, a["anchor"])
    d = a.get("dir") or [0, -1]
    d = V.unit((d[0], d[1]))
    t = (-d[1], d[0])
    sl = a.get("slide", 0.0) or 0.0
    base = (P[0] + t[0] * sl, P[1] + t[1] * sl)
    draw_datum_symbol(cv, ctx, base, d, a.get("letter", "A"), datum_len(a))


# ------------------------------------------------------------- callouts

def callout_block(ctx, a):
    """Size of the text block + stacked frames below the reference line."""
    h = ctx.h
    lines = [line_runs(ctx, ln, a.get("size", 0), a.get("tol")) for ln in a.get("lines", [])]
    W = max([runs_width(r, h) for r in lines] + [0])
    above = 0.0
    for r in lines:
        lo, hi = runs_height(r, h)
        above += lo + hi + 0.6
    above += 0.6
    stack = [ctx.ann[i] for i in stack_ids(ctx, a)]
    below, sw = 0.0, 0.0
    for s in stack:
        if s["kind"] == "fcf":
            fw, fh = fcf_size(ctx, s)
            below += fh
            sw = max(sw, fw)
        elif s["kind"] == "datum":
            below += 3.6 + 3 + BOX
    W = max(W, sw)
    return lines, W, above, below + (1.0 if stack else 0.0)


def stack_ids(ctx, a):
    out = [x["id"] for x in ctx.doc["annotations"] if x.get("attach") == a["id"] and x["kind"] == "fcf"]
    out += [x["id"] for x in ctx.doc["annotations"] if x.get("attach") == a["id"] and x["kind"] == "datum"]
    return out


def callout_anchor(ctx, a, K):
    view = a["view"]
    P = ctx.P(view, a["anchor"])
    if a.get("center"):
        C = ctx.P(view, a["center"])
        d = (K[0] - C[0], K[1] - C[1])
        L = math.hypot(*d)
        r = math.hypot(P[0] - C[0], P[1] - C[1])
        if L > r + 0.5:
            return (C[0] + d[0] / L * r, C[1] + d[1] / L * r)
    return P


def draw_callout(cv, ctx, a):
    h = ctx.h
    view = a["view"]
    P0 = ctx.P(view, a["anchor"])
    if a.get("pcd") and a.get("center"):
        C = ctx.P(view, a["center"])
        cv.circle(C, math.hypot(P0[0] - C[0], P0[1] - C[1]), w=THIN, dash="center", layer="CENTER")
    off = a.get("off") or [12, 12]
    K = (P0[0] + off[0], P0[1] + off[1])
    P = callout_anchor(ctx, a, K)
    lines, W, above, below = callout_block(ctx, a)
    right = off[0] >= 0
    x0 = K[0] if right else K[0] - W - 1.0
    x1 = x0 + W + 1.0
    cv.line(P, K, w=THIN, layer="DIM")
    cv.arrow(P, K, ARROW)
    cv.line((x0, K[1]), (x1, K[1]), w=THIN, layer="DIM")
    y = K[1] + 0.6
    for r in reversed(lines):
        lo, hi = runs_height(r, h)
        y += lo
        if right:
            draw_runs(cv, r, x0 + 0.5, y, h, layer="DIM")
        else:
            draw_runs(cv, r, x1 - 0.5, y, h, anchor="end", layer="DIM")
        y += hi + 0.6
    yb = K[1] - 1.0
    for sid in stack_ids(ctx, a):
        s = ctx.ann[sid]
        if s["kind"] == "fcf":
            fw, fh = fcf_size(ctx, s)
            fx = x0 if right else x1 - fw
            draw_fcf_at(cv, ctx, s, fx, yb - fh)
            yb -= fh
        else:
            bx = (x0 + 5.0) if right else (x1 - 5.0)
            draw_datum_symbol(cv, ctx, (bx, yb), (0.0, -1.0), s.get("letter", "A"), 3.0)
            yb -= 3.6 + 3 + BOX


# ------------------------------------------------------------- angular dimension

def angle_radius(ctx, a):
    s = ctx.s(a["view"])
    return a["r"] * s + (a.get("gap") if a.get("gap") is not None else 9.0)


def draw_angle(cv, ctx, a):
    view = a["view"]
    C = ctx.P(view, a["center"])
    s = ctx.s(view)
    Rp = angle_radius(ctx, a)
    a0, a1 = a["a0"], a["a1"]
    span = (a1 - a0) % 360.0
    u = lambda ang, r: (C[0] + r * math.cos(math.radians(ang)), C[1] + r * math.sin(math.radians(ang)))
    for ang in (a0, a1):
        cv.line(u(ang, a["r"] * s + 1.5), u(ang, Rp + 2.0), w=THIN, layer="DIM")
    cv.arc(C, Rp, a0, a1, w=THIN, layer="DIM")
    da = math.degrees(4.0 / Rp)
    cv.arrow(u(a0, Rp), u(a0 + da, Rp), ARROW)
    cv.arrow(u(a1, Rp), u(a1 - da, Rp), ARROW)
    mid = a0 + span / 2
    runs = value_runs(ctx, span, a.get("tol"), "", "", a.get("text", ""))
    runs = runs[:-1] + [runs[-1]] if runs else runs
    if runs and runs[0][0] == "box":
        runs = [("box", runs[0][1] + [("t", "°")])]
    else:
        runs = runs + [("t", "°")]
    p = u(mid, Rp + 2.5 + ctx.h * 0.9)
    halo_runs(cv, runs, p[0], p[1] - ctx.h / 2, ctx.h, anchor="middle")


# ------------------------------------------------------------- picked dimensions

def _canon(u):
    if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
        return (-u[0], -u[1])
    return u


def _ref_paper(ctx, view, r):
    s = ctx.s(view)
    if r.get("t") == "l":
        return {"t": "l", "A": ctx.P(view, r["a"]), "B": ctx.P(view, r["b"])}
    return {"t": "p", "P": ctx.P(view, r["p"]), "rad": float(r.get("c") or 0.0) * s}


def ldim_geom(ctx, a):
    """Paper geometry of a picked linear dimension. None if degenerate."""
    view = a["view"]
    refs = [_ref_paper(ctx, view, r) for r in a.get("refs", [])]
    if len(refs) != 2:
        return None
    orient = a.get("orient", "al")
    lines = [r for r in refs if r["t"] == "l"]
    if orient == "h":
        u = (1.0, 0.0)
    elif orient == "v":
        u = (0.0, 1.0)
    elif lines:
        L0 = lines[0]
        t = V.unit((L0["B"][0] - L0["A"][0], L0["B"][1] - L0["A"][1]))
        u = (-t[1], t[0])
    else:
        P1, P2 = refs[0]["P"], refs[1]["P"]
        if math.hypot(P2[0] - P1[0], P2[1] - P1[1]) < 1e-9:
            return None
        u = V.unit((P2[0] - P1[0], P2[1] - P1[1]))
    u = _canon(u)
    n = (-u[1], u[0])
    feats = []
    for r in refs:
        if r["t"] == "l":
            M = ((r["A"][0] + r["B"][0]) / 2, (r["A"][1] + r["B"][1]) / 2)
            feats.append((V.dot(M, u), V.dot(M, n), r))
        else:
            feats.append((V.dot(r["P"], u), V.dot(r["P"], n), r))
    (s1, n1, r1), (s2, n2, r2) = feats
    if abs(s2 - s1) < 1e-9:
        return None
    td = (n1 + n2) / 2 + float(a.get("off", 10.0) or 0.0)
    DA = (u[0] * s1 + n[0] * td, u[1] * s1 + n[1] * td)
    DB = (u[0] * s2 + n[0] * td, u[1] * s2 + n[1] * td)
    exts = []
    for sv, _, r in ((s1, n1, r1), (s2, n2, r2)):
        D = (u[0] * sv + n[0] * td, u[1] * sv + n[1] * td)
        if r["t"] == "l":
            ta, tb = V.dot(r["A"], n), V.dot(r["B"], n)
            lo, hi = min(ta, tb), max(ta, tb)
            if lo - 1e-6 <= td <= hi + 1e-6:
                continue
            tn = hi if td > hi else lo
            gap = EXT_GAP
        else:
            tn = V.dot(r["P"], n)
            gap = EXT_GAP + (r["rad"] + 1.5 if r["rad"] > 0 else 0.0)
        sgn = 1.0 if td > tn else -1.0
        if abs(td - tn) <= gap:
            continue
        start = (u[0] * sv + n[0] * (tn + sgn * gap), u[1] * sv + n[1] * (tn + sgn * gap))
        end = (D[0] + n[0] * sgn * EXT_OVER, D[1] + n[1] * sgn * EXT_OVER)
        exts.append((start, end))
    value = abs(s2 - s1) / ctx.s(view)
    return {"u": u, "n": n, "DA": DA, "DB": DB, "exts": exts, "value": value, "td": td,
            "side": 1.0 if (td - (n1 + n2) / 2) >= 0 else -1.0}


def _rot_box(x, y, w, lo, hi, ang, anchor="middle"):
    """Corners of a text box of width w (baseline at x,y) rotated by ang degrees."""
    x0 = -w / 2 if anchor == "middle" else 0.0
    a = math.radians(ang)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(x0 - 0.8, -lo - 0.4), (x0 + w + 0.8, -lo - 0.4), (x0 + w + 0.8, hi + 0.4), (x0 - 0.8, hi + 0.4)]
    return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts]


def draw_ldim(cv, ctx, a):
    g = ldim_geom(ctx, a)
    if not g:
        return None
    h = ctx.h
    u, n, DA, DB = g["u"], g["n"], g["DA"], g["DB"]
    for st, en in g["exts"]:
        cv.line(st, en, w=THIN, layer="DIM")
    span = math.hypot(DB[0] - DA[0], DB[1] - DA[1])
    runs = value_runs(ctx, g["value"], a.get("tol"), a.get("prefix", ""), a.get("count", ""), a.get("text", ""))
    tw = runs_width(runs, h)
    if span > 2 * ARROW + 1.0:
        cv.line(DA, DB, w=THIN, layer="DIM")
        cv.arrow(DA, DB, ARROW)
        cv.arrow(DB, DA, ARROW)
    else:
        e = ARROW + 3
        cv.line((DA[0] - u[0] * e, DA[1] - u[1] * e), (DB[0] + u[0] * e, DB[1] + u[1] * e), w=THIN, layer="DIM")
        cv.arrow(DA, (DA[0] - u[0] * 5, DA[1] - u[1] * 5), ARROW)
        cv.arrow(DB, (DB[0] + u[0] * 5, DB[1] + u[1] * 5), ARROW)
    shift = float(a.get("shift", 0.0) or 0.0)
    if span < tw + 2 and not shift:
        shift = (span + tw) / 2 + ARROW + 2
    mid = ((DA[0] + DB[0]) / 2 + u[0] * shift, (DA[1] + DB[1]) / 2 + u[1] * shift)
    lo, hi = runs_height(runs, h)
    off = 1.0 + lo - 0.25 * h
    ang = math.degrees(math.atan2(u[1], u[0]))
    tx, ty = mid[0] + n[0] * off, mid[1] + n[1] * off
    halo_runs(cv, runs, tx, ty, h, anchor="middle", rot=ang)
    hits = [_band([DA, DB], 1.6), _rot_box(tx, ty, tw, lo, hi, ang)]
    # stacked children: frames on the far side of the dimension line, datum in line with it
    k = 1.5
    for c in ctx.children.get(a["id"], []):
        if c["kind"] == "fcf":
            fw, fh = fcf_size(ctx, c)
            ext = abs(n[0]) * fw + abs(n[1]) * fh
            cx = (DA[0] + DB[0]) / 2 - n[0] * (k + ext / 2)
            cy = (DA[1] + DB[1]) / 2 - n[1] * (k + ext / 2)
            draw_fcf_at(cv, ctx, c, cx - fw / 2, cy - fh / 2)
            hits.append([(cx - fw / 2, cy - fh / 2), (cx + fw / 2, cy - fh / 2), (cx + fw / 2, cy + fh / 2), (cx - fw / 2, cy + fh / 2)])
            k += ext + 1.0
        elif c["kind"] == "datum":
            d = V.unit((DB[0] - DA[0], DB[1] - DA[1]))
            L = datum_len(c)
            draw_datum_symbol(cv, ctx, DB, d, c.get("letter", "A"), L)
            end = (DB[0] + d[0] * (3.6 + L + BOX), DB[1] + d[1] * (3.6 + L + BOX))
            hits.append(_band([DB, end], BOX / 2 + 0.5))
    return hits


def _sector(C, d1, d2, P):
    """Of the four sectors between two lines through C, the one holding P: (a0, a1) ccw degrees."""
    ap = math.degrees(math.atan2(P[1] - C[1], P[0] - C[0])) % 360.0
    best = None
    for r1 in (d1, (-d1[0], -d1[1])):
        for r2 in (d2, (-d2[0], -d2[1])):
            t1 = math.degrees(math.atan2(r1[1], r1[0])) % 360.0
            t2 = math.degrees(math.atan2(r2[1], r2[0])) % 360.0
            for a0, a1 in ((t1, t2), (t2, t1)):
                sweep = (a1 - a0) % 360.0
                if sweep <= 180.0 + 1e-9 and (ap - a0) % 360.0 <= sweep + 1e-9:
                    if best is None or sweep < best[2]:
                        best = (a0, a1, sweep)
    return best


def adim_geom(ctx, a):
    view = a["view"]
    refs = [_ref_paper(ctx, view, r) for r in a.get("refs", [])]
    if len(refs) != 2 or any(r["t"] != "l" for r in refs):
        return None
    A1, B1, A2, B2 = refs[0]["A"], refs[0]["B"], refs[1]["A"], refs[1]["B"]
    d1 = V.unit((B1[0] - A1[0], B1[1] - A1[1]))
    d2 = V.unit((B2[0] - A2[0], B2[1] - A2[1]))
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-6:
        return None
    t = ((A2[0] - A1[0]) * d2[1] - (A2[1] - A1[1]) * d2[0]) / den
    C = (A1[0] + d1[0] * t, A1[1] + d1[1] * t)
    P = ctx.P(view, a["pick"])
    R = max(math.hypot(P[0] - C[0], P[1] - C[1]), 4.0)
    sec = _sector(C, d1, d2, P)
    if not sec:
        return None
    a0, a1, sweep = sec
    return {"C": C, "R": R, "a0": a0, "a1": a1, "value": sweep, "segs": [(A1, B1), (A2, B2)]}


def draw_adim(cv, ctx, a):
    g = adim_geom(ctx, a)
    if not g:
        return None
    C, R, a0, a1 = g["C"], g["R"], g["a0"], g["a1"]
    pt = lambda ang, r: (C[0] + r * math.cos(math.radians(ang)), C[1] + r * math.sin(math.radians(ang)))
    for ang in (a0, a1):
        ray = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        # the edge lying along this ray decides whether an extension line is needed
        best = None
        for A, B in g["segs"]:
            ta = (A[0] - C[0]) * ray[0] + (A[1] - C[1]) * ray[1]
            tb = (B[0] - C[0]) * ray[0] + (B[1] - C[1]) * ray[1]
            off = abs((A[0] - C[0]) * ray[1] - (A[1] - C[1]) * ray[0]) + abs((B[0] - C[0]) * ray[1] - (B[1] - C[1]) * ray[0])
            if best is None or off < best[0]:
                best = (off, min(ta, tb), max(ta, tb))
        _, lo, hi = best
        if lo - 1e-6 <= R <= hi + 1e-6:
            continue
        tn = hi if R > hi else lo
        sgn = 1.0 if R > tn else -1.0
        cv.line(pt(ang, tn + sgn * EXT_GAP), pt(ang, R + sgn * EXT_OVER), w=THIN, layer="DIM")
    cv.arc(C, R, a0, a1, w=THIN, layer="DIM")
    da = math.degrees(min(4.0 / R, 0.4))
    cv.arrow(pt(a0, R), pt(a0 + da, R), ARROW)
    cv.arrow(pt(a1, R), pt(a1 - da, R), ARROW)
    runs = value_runs(ctx, g["value"], a.get("tol"), "", "", a.get("text", ""))
    if runs and runs[0][0] == "box":
        runs = [("box", runs[0][1] + [("t", "°")])]
    elif not a.get("text"):
        runs = runs + [("t", "°")]
    mid = a0 + ((a1 - a0) % 360.0) / 2
    p = pt(mid, R + 2.5 + ctx.h * 0.7)
    W, lo, hi = halo_runs(cv, runs, p[0], p[1] - ctx.h / 2, ctx.h, anchor="middle")
    span = (a1 - a0) % 360.0
    arc_pts = [pt(a0 + span * i / 12.0, R) for i in range(13)]
    return [_band(arc_pts, 1.8), _rot_box(p[0], p[1] - ctx.h / 2, W, lo, hi, 0.0)]


# ------------------------------------------------------------- notes

def draw_note(cv, ctx, a):
    h = a.get("h", ctx.h)
    x, y = a.get("pos", [50, 50])
    for i, ln in enumerate(a.get("lines", [])):
        draw_runs(cv, parse(ln), x, y - i * h * 1.7, h, layer="TEXT")


DRAWERS = {"dim": draw_dim, "fcf": draw_fcf, "datum": draw_datum, "callout": draw_callout, "note": draw_note,
           "angle": draw_angle, "ldim": draw_ldim, "adim": draw_adim}


def draw_annotation(cv, ctx, a):
    if a.get("view") and a["view"] not in ctx.lay.views:
        return None
    fn = DRAWERS.get(a["kind"])
    if not fn:
        return None
    start = len(cv.items)
    cv.begin(a["id"], a["kind"])
    try:
        hits = fn(cv, ctx, a)
    finally:
        cv.end()
    if isinstance(hits, list) and hits:
        cv.begin(a["id"], a["kind"])
        for poly in hits:
            cv.hitpoly(poly)
        cv.end()
        xs = [x for it in cv.items[start:] for x, _ in item_points(it)]
        ys = [y for it in cv.items[start:] for _, y in item_points(it)]
        return [min(xs), min(ys), max(xs), max(ys)] if xs else None
    # attached items share the parent's group so they move together
    xs, ys = [], []
    for it in cv.items[start:]:
        for x, y in item_points(it):
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    bb = [min(xs), min(ys), max(xs), max(ys)]
    cv.begin(a["id"], a["kind"])
    cv.hit(bb[0] - 1, bb[1] - 1, bb[2] + 1, bb[3] + 1)
    cv.end()
    return bb


# ------------------------------------------------------------- sheet

def draw_sheet(cv, ctx):
    lay = ctx.lay
    doc = ctx.doc
    W, H = lay.W, lay.H
    b = lay.border
    cv.begin("sheet", "sheet")
    cv.rect(b[0], b[1], b[2], b[3], w=0.7, layer="BORDER")
    # centring marks
    for x, y0, y1 in ((W / 2, 0, b[1]), (W / 2, b[3], H)):
        cv.line((x, y0 + (5 if y0 == 0 else 0)), (x, y1 - (5 if y1 == H else 0)), w=0.7, layer="BORDER")
    for y, x0, x1 in ((H / 2, 5, b[0]), (H / 2, b[2], W - 5)):
        cv.line((x0, y), (x1, y), w=0.7, layer="BORDER")
    draw_title_block(cv, ctx)
    draw_notes(cv, ctx)
    cv.end()



def _cell(cv, x, y, w, h, label, value, vh=3.5, bold=False):
    cv.rect(x, y, x + w, y + h, w=THIN, layer="BORDER")
    if label:
        cv.text((x + 1.0, y + h - 2.4), label, 1.6, layer="TEXT")
    if value:
        vh = min(vh, h * 0.5)
        s = str(value)
        while text_width(s, vh) > w - 2.5 and vh > 1.6:
            vh -= 0.25
        cv.text((x + 1.5, y + (h - 2.4 - vh) / 2 + 0.3), s, vh, layer="TEXT")


def draw_title_block(cv, ctx):
    lay = ctx.lay
    t = ctx.doc["title"]
    st = ctx.doc["settings"]
    x0, y0, x1, y1 = lay.tb
    cv.rect(x0, y0, x1, y1, w=0.7, layer="BORDER")
    L = 70.0
    # left block
    _cell(cv, x0, y0, 40, 10, "MATERIAL", t.get("material"))
    _cell(cv, x0 + 40, y0, 30, 10, "MASS", t.get("mass"))
    _cell(cv, x0, y0 + 10, 40, 10, "FINISH", t.get("finish"))
    _cell(cv, x0 + 40, y0 + 10, 30, 10, "DATE", t.get("date"))
    _cell(cv, x0, y0 + 20, 23.33, 10, "DRAWN", t.get("drawn_by"), 2.5)
    _cell(cv, x0 + 23.33, y0 + 20, 23.33, 10, "CHECKED", t.get("checked_by"), 2.5)
    _cell(cv, x0 + 46.67, y0 + 20, 23.33, 10, "APPROVED", t.get("approved_by"), 2.5)
    _cell(cv, x0, y0 + 30, 70, 10, "COMPANY", t.get("company"), 3.5)
    # right block
    rx = x0 + L
    _cell(cv, rx, y0, 22, 10, "SCALE", scale_label(lay.scale))
    _cell(cv, rx + 22, y0, 16, 10, "SIZE", st.get("sheet", "A3"))
    _cell(cv, rx + 38, y0, 26, 10, "PROJECTION", "")
    _projection_symbol(cv, rx + 38 + 13, y0 + 4.2, st.get("projection", "first"))
    _cell(cv, rx + 64, y0, 26, 10, "SHEET", t.get("sheet_no"))
    _cell(cv, rx + 90, y0, 20, 10, "REV", t.get("revision"))
    _cell(cv, rx, y0 + 10, 110, 12, "DRAWING No.", t.get("drawing_no"), 5)
    _cell(cv, rx, y0 + 22, 110, 18, "TITLE", t.get("title"), 6)
    tol_std = "ISO GPS" if st.get("standard") != "ASME" else "ASME Y14.5"
    cv.text((x1 - 1.0, y0 + 22 + 1.2), tol_std, 1.6, anchor="end", layer="TEXT")


def _projection_symbol(cv, cx, cy, projection):
    """ISO 128 truncated-cone symbol (first or third angle), centred at (cx, cy)."""
    R, r, Lc = 2.4, 1.2, 5.0
    gap = 2.4
    if projection == "first":
        tx = cx - (Lc + gap + 2 * R) / 2
        circ_x = tx + Lc + gap + R
    else:
        circ_x = cx - (Lc + gap + 2 * R) / 2 + R
        tx = circ_x + R + gap
    cv.poly([(tx, cy - r), (tx + Lc, cy - R), (tx + Lc, cy + R), (tx, cy + r)], w=THIN, closed=True, layer="BORDER")
    cv.circle((circ_x, cy), R, w=THIN, layer="BORDER")
    cv.circle((circ_x, cy), r, w=THIN, layer="BORDER")
    x_a = min(tx, circ_x - R) - 1
    x_b = max(tx + Lc, circ_x + R) + 1
    cv.line((x_a, cy), (x_b, cy), w=0.13, dash="center", layer="CENTER")
    cv.line((circ_x, cy - R - 1), (circ_x, cy + R + 1), w=0.13, dash="center", layer="CENTER")


def wrap(text, h, width):
    words = text.split(" ")
    out, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_width(trial, h) <= width or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = "    " + w
    if cur:
        out.append(cur)
    return out


def draw_notes(cv, ctx):
    lay = ctx.lay
    x0, y0, x1, y1 = lay.notes
    h = 2.5
    lines = []
    for n in ctx.doc.get("notes", []):
        lines += wrap(n, h, x1 - x0)
    y = y1 - 4
    for ln in lines:
        draw_runs(cv, parse(ln), x0, y, h, layer="TEXT")
        y -= h * 1.75


# ------------------------------------------------------------- everything

def render(ctx):
    cv = Canvas()
    draw_views(cv, ctx)
    draw_cut_lines(cv, ctx)
    cv.begin("centerlines", "geom")
    draw_centerlines(cv, ctx)
    cv.end()
    bbs = {}
    for a in ctx.doc["annotations"]:
        bb = draw_annotation(cv, ctx, a)
        if bb:
            bbs[a["id"]] = bb
    draw_sheet(cv, ctx)
    return cv, bbs
