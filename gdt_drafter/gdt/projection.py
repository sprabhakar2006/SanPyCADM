"""Hidden-line-removed orthographic / isometric projections.

Every curve is returned in *view coordinates*: millimetres of the model,
u = P . Vx (right), v = P . Vy (up). Curve records:
  {"k": "L", "p": [x1, y1, x2, y2]}
  {"k": "C", "c": [x, y], "r": r}
  {"k": "A", "c": [x, y], "r": r, "a0": deg, "a1": deg}   (counter-clockwise a0 -> a1)
  {"k": "P", "pts": [[x, y], ...]}
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_TangentialDeflection
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import (HLRBRep_Algo, HLRBRep_HLRToShape, HLRBRep_PolyAlgo,
                         HLRBRep_PolyHLRToShape)
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer

from . import vec as V
from .frame import view_basis
from .geometry import quiet
from .occ import to_edge

POLY_FACE_LIMIT = 600     # above this many faces use the faster mesh-based HLR


def _edges(compound):
    out = []
    if compound is None or compound.IsNull():
        return out
    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        out.append(to_edge(exp.Current()))
        exp.Next()
    return out


def _ang(c, p):
    return math.degrees(math.atan2(p[1] - c[1], p[0] - c[0])) % 360.0


def _curve(edge, defl):
    a = BRepAdaptor_Curve(edge)
    f, l = a.FirstParameter(), a.LastParameter()
    t = a.GetType()
    if t == GeomAbs_Line:
        p0, p1 = a.Value(f), a.Value(l)
        if math.hypot(p1.X() - p0.X(), p1.Y() - p0.Y()) < 1e-6:
            return None
        return {"k": "L", "p": [p0.X(), p0.Y(), p1.X(), p1.Y()]}
    if t == GeomAbs_Circle:
        circ = a.Circle()
        c = circ.Location()
        c = (c.X(), c.Y())
        r = circ.Radius()
        if l - f >= 2 * math.pi - 1e-6:
            return {"k": "C", "c": list(c), "r": r}
        ps = [a.Value(x) for x in (f, 0.5 * (f + l), l)]
        ps = [(p.X(), p.Y()) for p in ps]
        a0, am, a1 = (_ang(c, p) for p in ps)
        span = (a1 - a0) % 360.0
        if (am - a0) % 360.0 > span:     # mid not on ccw path -> swap
            a0, a1 = a1, a0
        return {"k": "A", "c": list(c), "r": r, "a0": a0, "a1": a1}
    try:
        d = GCPnts_TangentialDeflection(a, 0.08, defl)
        pts = [d.Value(i) for i in range(1, d.NbPoints() + 1)]
    except Exception:
        pts = [a.Value(f + (l - f) * i / 32.0) for i in range(33)]
    pts = [[p.X(), p.Y()] for p in pts]
    if len(pts) < 2:
        return None
    fit = _fit_analytic(pts, defl)
    if fit:
        return fit
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-6 and len(pts) < 3:
        return None
    cv = {"k": "P", "pts": pts}
    try:
        pieces = _arc_pieces(a, f, l, defl)
    except Exception:
        pieces = []
    if pieces:
        cv["pieces"] = pieces
    return cv


def _snap_radius(r, tol):
    for step in (1.0, 0.5, 0.1, 0.01):
        q = round(r / step) * step
        if q > 0 and abs(q - r) <= tol:
            return q
    return r


def _arc_pieces(a, f, l, defl, n=320):
    """Constant-radius stretches inside a free-form edge.

    CAD kernels often write a chain of tangent arcs as one spline. The curve
    is still drawn from its own points; these pieces only make each radius
    (and each straight run) pickable for dimensioning."""
    p, d1, d2 = gp_Pnt(), gp_Vec(), gp_Vec()
    P, K, T, S = [], [], [], [0.0]
    for i in range(n + 1):
        a.D2(f + (l - f) * i / n, p, d1, d2)
        vx, vy = d1.X(), d1.Y()
        sp = math.hypot(vx, vy)
        if sp < 1e-12:
            return []
        P.append((p.X(), p.Y()))
        T.append((vx / sp, vy / sp))
        K.append((vx * d2.Y() - vy * d2.X()) / sp ** 3)
        if i:
            S.append(S[-1] + math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]))
    total = S[-1]
    if total < 1e-6:
        return []
    min_len = max(0.02 * total, 20 * defl)
    out, i = [], 0
    while i < n:
        j, ksum = i, K[i]
        while j < n:
            kref = ksum / (j - i + 1)
            if abs(K[j + 1] - kref) > 0.03 * abs(kref) + 0.02 / total:
                break
            j += 1
            ksum += K[j]
        if j - i < 4 or S[j] - S[i] < min_len:
            i += 1
            continue
        lo, hi = i + (j - i) // 8, j - (j - i) // 8
        ks = sorted(K[lo:hi + 1])
        k = ks[len(ks) // 2]
        seg = S[j] - S[i]
        if abs(k) * seg < 0.01:
            if all(V.seg_dist(q, P[i], P[j]) < max(defl * 5, 1e-3) for q in P[i:j + 1]):
                out.append({"k": "L", "p": [P[i][0], P[i][1], P[j][0], P[j][1]]})
            i = j
            continue
        r = _snap_radius(1.0 / abs(k), max(5e-4 / abs(k), defl * 0.5))
        sg = 1.0 if k > 0 else -1.0
        cx = sum(P[m][0] - T[m][1] * sg * r for m in range(lo, hi + 1)) / (hi - lo + 1)
        cy = sum(P[m][1] + T[m][0] * sg * r for m in range(lo, hi + 1)) / (hi - lo + 1)
        tolv = max(defl * 5, 2e-3 * r)
        dev = lambda m: abs(math.hypot(P[m][0] - cx, P[m][1] - cy) - r)
        i2, j2 = i, j
        while i2 < lo and dev(i2) > tolv:
            i2 += 1
        while j2 > hi and dev(j2) > tolv:
            j2 -= 1
        if S[j2] - S[i2] >= min_len and all(dev(m) <= tolv for m in range(i2, j2 + 1)):
            a0, a1 = _ang((cx, cy), P[i2]), _ang((cx, cy), P[j2])
            if sg < 0:
                a0, a1 = a1, a0
            out.append({"k": "A", "c": [cx, cy], "r": r, "a0": a0, "a1": a1})
        i = j
    return out if any(c["k"] == "A" for c in out) else []


def _merge_arcs(curves):
    """Join arcs that share a circle; a closed ring of them becomes a circle."""
    groups, out = {}, []
    for cv in curves:
        if cv["k"] == "A":
            groups.setdefault((round(cv["c"][0], 2), round(cv["c"][1], 2), round(cv["r"], 2)), []).append(cv)
        else:
            out.append(cv)
    for arcs in groups.values():
        arcs = sorted(arcs, key=lambda c: c["a0"])
        chains = [dict(arcs[0])]
        for cv in arcs[1:]:
            last = chains[-1]
            span = (last["a1"] - last["a0"]) % 360.0
            if abs(((cv["a0"] - last["a0"]) % 360.0) - span) < 0.5:
                last["a1"] = cv["a1"]
            else:
                chains.append(dict(cv))
        if len(chains) > 1:
            first, last = chains[0], chains[-1]
            if abs((first["a0"] - last["a1"] + 180.0) % 360.0 - 180.0) < 0.5:
                last["a1"] = first["a1"]
                chains.pop(0)
        for cv in chains:
            total = sum((c["a1"] - c["a0"]) % 360.0 for c in arcs)
            if len(chains) == 1 and len(arcs) > 1 and total > 359.0:
                out.append({"k": "C", "c": cv["c"], "r": cv["r"]})
            else:
                out.append(cv)
    return out


def _fit_analytic(pts, defl):
    """Projected B-spline edges that are really lines, circles or arcs."""
    tol = max(defl * 5, 1e-3)
    a, b = pts[0], pts[-1]
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L > 1e-9 and all(V.seg_dist(p, a, b) < tol for p in pts):
        return {"k": "L", "p": [a[0], a[1], b[0], b[1]]}
    if len(pts) < 5:
        return None
    m = pts[len(pts) // 2]
    c = _circumcentre(a, m, b if L > 1e-9 else pts[len(pts) // 4])
    if c is None:
        return None
    r = math.hypot(a[0] - c[0], a[1] - c[1])
    if r < 1e-6 or any(abs(math.hypot(p[0] - c[0], p[1] - c[1]) - r) > tol for p in pts):
        return None
    if L < tol:
        return {"k": "C", "c": list(c), "r": r}
    a0, am, a1 = (_ang(c, p) for p in (a, m, b))
    span = (a1 - a0) % 360.0
    if (am - a0) % 360.0 > span:
        a0, a1 = a1, a0
    return {"k": "A", "c": list(c), "r": r, "a0": a0, "a1": a1}


def _circumcentre(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
    uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
    return (ux, uy)


def sample(cv, step):
    """Points along a curve, roughly every `step` model-mm."""
    k = cv["k"]
    if k == "L":
        x1, y1, x2, y2 = cv["p"]
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / step) + 1)
        return [(x1 + (x2 - x1) * i / (n - 1), y1 + (y2 - y1) * i / (n - 1)) for i in range(n)]
    if k in ("C", "A"):
        cx, cy = cv["c"]
        r = cv["r"]
        a0, a1 = (0.0, 360.0) if k == "C" else (cv["a0"], cv["a1"])
        span = 360.0 if k == "C" else (a1 - a0) % 360.0 or 360.0
        n = max(4, int(math.radians(span) * r / step) + 1)
        return [(cx + r * math.cos(math.radians(a0 + span * i / (n - 1))),
                 cy + r * math.sin(math.radians(a0 + span * i / (n - 1)))) for i in range(n)]
    pts = cv["pts"]
    out = [tuple(pts[0])]
    for p, q in zip(pts, pts[1:]):
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        n = max(1, int(L / step))
        out += [(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n) for i in range(1, n + 1)]
    return out


def segments(cv, step):
    pts = sample(cv, step)
    return list(zip(pts, pts[1:]))


def bounds(curves):
    xs, ys = [], []
    for cv in curves:
        if cv["k"] == "L":
            xs += [cv["p"][0], cv["p"][2]]
            ys += [cv["p"][1], cv["p"][3]]
        elif cv["k"] == "C":
            xs += [cv["c"][0] - cv["r"], cv["c"][0] + cv["r"]]
            ys += [cv["c"][1] - cv["r"], cv["c"][1] + cv["r"]]
        else:
            for x, y in sample(cv, 1e9 if cv["k"] == "P" else max(cv["r"] / 8, 1e-3)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]


class SegIndex:
    """Uniform grid of short segments for fast point-to-curve distance queries."""

    def __init__(self, curves, step, cell):
        self.cell = cell
        self.grid = {}
        for cv in curves:
            for a, b in segments(cv, step):
                x0, x1 = sorted((a[0], b[0]))
                y0, y1 = sorted((a[1], b[1]))
                for i in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
                    for j in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
                        self.grid.setdefault((i, j), []).append((a, b))

    def dist(self, p, limit):
        i0 = int(math.floor((p[0] - limit) / self.cell))
        i1 = int(math.floor((p[0] + limit) / self.cell))
        j0 = int(math.floor((p[1] - limit) / self.cell))
        j1 = int(math.floor((p[1] + limit) / self.cell))
        best = limit * 10
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for a, b in self.grid.get((i, j), ()):
                    d = V.seg_dist(p, a, b)
                    if d < best:
                        best = d
        return best


def _key(cv, nd=3):
    k = cv["k"]
    if k == "L":
        a = (round(cv["p"][0], nd), round(cv["p"][1], nd))
        b = (round(cv["p"][2], nd), round(cv["p"][3], nd))
        return ("L",) + tuple(sorted((a, b)))
    if k == "C":
        return ("C", round(cv["c"][0], nd), round(cv["c"][1], nd), round(cv["r"], nd))
    if k == "A":
        return ("A", round(cv["c"][0], nd), round(cv["c"][1], nd), round(cv["r"], nd),
                round(cv["a0"], 1), round(cv["a1"], 1))
    return ("P",) + tuple((round(x, nd), round(y, nd)) for x, y in (cv["pts"][0], cv["pts"][-1], cv["pts"][len(cv["pts"]) // 2]))


def _dedupe(curves):
    seen, out = set(), []
    for cv in curves:
        k = _key(cv)
        if k in seen:
            continue
        seen.add(k)
        out.append(cv)
    return out


def _drop_covered(curves, index, step, tol):
    out = []
    for cv in curves:
        pts = sample(cv, step)
        covered = sum(1 for p in pts if index.dist(p, tol) <= tol)
        if covered < 0.9 * len(pts):
            out.append(cv)
    return out


class ViewGeom:
    def __init__(self, name, N, Vx, Vy, visible, hidden, tangent, size):
        self.name = name
        self.N, self.Vx, self.Vy = N, Vx, Vy
        self.visible = visible
        self.hidden = hidden
        self.tangent = tangent
        self.size = size
        self.bbox = bounds(visible + hidden + tangent)
        self._vis_index = None

    def project(self, p):
        return (V.dot(p, self.Vx), V.dot(p, self.Vy))

    def depth(self, p):
        return V.dot(p, self.N)

    @property
    def vis_index(self):
        if self._vis_index is None:
            step = max(self.size / 400.0, 0.05)
            self._vis_index = SegIndex(self.visible + self.tangent, step, max(self.size / 40.0, 0.5))
        return self._vis_index

    def visible_at(self, p, tol=None):
        tol = tol if tol is not None else max(self.size * 1e-3, 0.02)
        return self.vis_index.dist(p, tol) <= tol

    def to_dict(self):
        return {"name": self.name, "bbox": self.bbox,
                "visible": self.visible, "hidden": self.hidden, "tangent": self.tangent}


def project_view(part, frame, name, mode="auto", basis=None, shape=None, with_hidden=None):
    """Hidden-line projection of `shape` (default: the part) for a named
    standard view, or for an explicit (N, Vx, Vy) basis."""
    N, Vx, Vy = basis if basis is not None else view_basis(frame, name)
    shape = part.shape if shape is None else shape
    if with_hidden is None:
        with_hidden = name != "iso"
    size = max(part.size, 1e-3)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*N), gp_Dir(*Vx))
    projector = HLRAlgo_Projector(ax)
    use_poly = mode == "fast" or (mode == "auto" and part.n_faces > POLY_FACE_LIMIT)
    with quiet():
        if use_poly:
            BRepMesh_IncrementalMesh(shape, size * 5e-4, False, 0.25, True)
            algo = HLRBRep_PolyAlgo()
            algo.Load(shape)
            algo.Projector(projector)
            algo.Update()
            h = HLRBRep_PolyHLRToShape()
            h.Update(algo)
        else:
            algo = HLRBRep_Algo()
            algo.Add(shape)
            algo.Projector(projector)
            algo.Update()
            algo.Hide()
            h = HLRBRep_HLRToShape(algo)
        vis = _edges(h.VCompound()) + _edges(h.OutLineVCompound())
        tan = _edges(h.Rg1LineVCompound())
        hid = _edges(h.HCompound()) + _edges(h.OutLineHCompound()) if with_hidden else []
    defl = size * 2e-4
    visible = _merge_arcs(_dedupe([c for c in (_curve(e, defl) for e in vis) if c]))
    tangent = _dedupe([c for c in (_curve(e, defl) for e in tan) if c])
    hidden = _merge_arcs(_dedupe([c for c in (_curve(e, defl) for e in hid) if c]))

    step = max(size / 400.0, 0.05)
    tol = max(size * 2e-4, 0.01)
    idx = SegIndex(visible, step, max(size / 40.0, 0.5))
    tangent = _drop_covered(tangent, idx, step, tol)
    idx2 = SegIndex(visible + tangent, step, max(size / 40.0, 0.5))
    hidden = _drop_covered(hidden, idx2, step, tol)
    return ViewGeom(name, N, Vx, Vy, visible, hidden, tangent, size)
