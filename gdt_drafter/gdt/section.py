"""Section views: cut the part along a (straight or stepped) line drawn on a
parent view, project what remains, and find the cut faces to hatch.

A section spec (stored in doc["views"]):
  {"id": "secA", "type": "section", "parent": "front", "letter": "A",
   "pts": [[x, y], ...],   # cutting line in the parent view's model coordinates
   "dir": [dx, dy]}        # viewing direction (where the arrows point), parent 2-D
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer

from . import vec as V
from .frame import view_basis
from .geometry import quiet
from .occ import static, to_edge, to_face
from .projection import project_view

try:
    from OCP.TopoDS import TopoDS as _TopoDS
    _to_wire = getattr(_TopoDS, "Wire_s", None) or getattr(_TopoDS, "Wire")
except Exception:      # pragma: no cover
    _to_wire = None


def _u2(a, b):
    d = (b[0] - a[0], b[1] - a[1])
    L = math.hypot(*d)
    return (d[0] / L, d[1] / L) if L > 1e-12 else (1.0, 0.0)


def section_basis(frame, spec):
    """(N, Vx, Vy) of the section view; keeps the parent's 'up' where it can."""
    Np, Vxp, Vyp = view_basis(frame, spec["parent"])
    d = V.unit((spec["dir"][0], spec["dir"][1]))
    D3 = V.unit(V.add(V.mul(Vxp, d[0]), V.mul(Vyp, d[1])))
    Ns = V.neg(D3)
    if abs(V.dot(Vyp, Ns)) < 0.999:
        Vys = V.unit(V.sub(Vyp, V.mul(Ns, V.dot(Vyp, Ns))))
        Vxs = V.cross(Vys, Ns)
    else:
        Vxs = V.unit(V.sub(Vxp, V.mul(Ns, V.dot(Vxp, Ns))))
        Vys = V.cross(Ns, Vxs)
    return (Np, Vxp, Vyp), D3, (Ns, Vxs, Vys)


def removal_polygon(pts, d, L):
    """2-D polygon (parent view coords) of the material removed: everything on the
    viewer's side (-d) of the cutting line, with the end segments run out to L."""
    p = [tuple(q) for q in pts]
    u0 = _u2(p[0], p[1])
    uk = _u2(p[-2], p[-1])
    a = (p[0][0] - u0[0] * L, p[0][1] - u0[1] * L)
    b = (p[-1][0] + uk[0] * L, p[-1][1] + uk[1] * L)
    return [a] + p + [b, (b[0] - d[0] * L, b[1] - d[1] * L), (a[0] - d[0] * L, a[1] - d[1] * L)]


def _point_in_poly(q, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > q[1]) != (y2 > q[1]):
            x = x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1)
            if x > q[0]:
                inside = not inside
    return inside


def _poly_dist(q, poly):
    n = len(poly)
    return min(V.seg_dist(q, poly[i], poly[(i + 1) % n]) for i in range(n))


def _wire_loop(wire, face_reversed, step):
    """Ordered 3-D points around one wire."""
    pts = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        e = ex.Current()
        ex.Next()
        c = BRepAdaptor_Curve(e)
        f, l = c.FirstParameter(), c.LastParameter()
        try:
            length = abs(l - f) * max(1.0, _approx_speed(c, f, l))
        except Exception:
            length = 1.0
        n = max(1, min(200, int(length / step) + 1))
        seq = [c.Value(f + (l - f) * i / n) for i in range(n + 1)]
        if e.Orientation() == TopAbs_REVERSED:
            seq.reverse()
        pts.extend((p.X(), p.Y(), p.Z()) for p in seq[:-1])
    return pts


def _approx_speed(c, f, l):
    p0, p1 = c.Value(f), c.Value(l)
    pm = c.Value(0.5 * (f + l))
    chord = (math.dist((p0.X(), p0.Y(), p0.Z()), (pm.X(), pm.Y(), pm.Z()))
             + math.dist((pm.X(), pm.Y(), pm.Z()), (p1.X(), p1.Y(), p1.Z())))
    return chord / max(abs(l - f), 1e-12)


def section_geom(part, frame, spec, mode="auto"):
    (Np, Vxp, Vyp), D3, basis = section_basis(frame, spec)
    d = V.unit((spec["dir"][0], spec["dir"][1]))
    pts = [tuple(p) for p in spec["pts"]]
    L = 20.0 * max(part.size, 1.0)
    # parent-view 2-D -> 3-D at depth z along the parent's N
    to3 = lambda q, z: V.add(V.add(V.mul(Vxp, q[0]), V.mul(Vyp, q[1])), V.mul(Np, z))

    poly2 = removal_polygon(pts, d, L)
    with quiet():
        mk = BRepBuilderAPI_MakePolygon()
        for q in poly2:
            mk.Add(gp_Pnt(*to3(q, -L)))
        mk.Close()
        face = BRepBuilderAPI_MakeFace(mk.Wire()).Face()
        prism = BRepPrimAPI_MakePrism(face, gp_Vec(*V.mul(Np, 2 * L))).Shape()
        op = BRepAlgoAPI_Cut(part.shape, prism)
        op.Build()
        cut = op.Shape()

    vg = project_view(part, frame, spec["id"], mode, basis=basis, shape=cut, with_hidden=True)
    vg.kind = "section"
    vg.spec = spec
    vg.parent_basis = (Np, Vxp, Vyp)
    vg.removal = poly2
    vg.cut_loops = _cut_faces(part, cut, pts, D3, Vxp, Vyp, basis)
    _drop_step_lines(vg, part.size)
    return vg


def _in_cut(q, cut_loops):
    for loops in cut_loops:
        inside = False
        for loop in loops:
            if _point_in_poly(q, loop):
                inside = not inside
        if inside:
            return True
    return False


def _drop_step_lines(vg, size):
    """Where a stepped cut changes plane, the cut faces meet edge-on. Drafting
    standards leave that line out, so drop straight edges hatched on both sides."""
    if len(vg.cut_loops) < 2:
        return
    eps = max(size * 2e-3, 0.05)
    keep = []
    for cv in vg.visible:
        if cv["k"] == "L":
            x1, y1, x2, y2 = cv["p"]
            L = math.hypot(x2 - x1, y2 - y1)
            if L > 1e-9:
                nx, ny = -(y2 - y1) / L, (x2 - x1) / L
                both = True
                for t in (0.25, 0.5, 0.75):
                    mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    if not (_in_cut((mx + nx * eps, my + ny * eps), vg.cut_loops)
                            and _in_cut((mx - nx * eps, my - ny * eps), vg.cut_loops)):
                        both = False
                        break
                if both:
                    continue
        keep.append(cv)
    vg.visible = keep


def _cut_faces(part, cut, pts, D3, Vxp, Vyp, basis):
    """Faces lying on a cutting plane, as loops of section-view 2-D points."""
    Ns, Vxs, Vys = basis
    tol = max(part.size * 1e-5, 1e-4)
    step = max(part.size / 300.0, 0.05)
    segs = []
    n = len(pts)
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        u = _u2(a, b)
        u3 = V.add(V.mul(Vxp, u[0]), V.mul(Vyp, u[1]))
        if abs(V.dot(u3, D3)) > 1e-6:
            continue            # a step between two cutting planes, seen edge-on
        A3 = V.add(V.mul(Vxp, a[0]), V.mul(Vyp, a[1]))
        B3 = V.add(V.mul(Vxp, b[0]), V.mul(Vyp, b[1]))
        lo, hi = sorted((V.dot(A3, u3), V.dot(B3, u3)))
        if i == 0:
            lo = -1e18 if V.dot(A3, u3) <= V.dot(B3, u3) else lo
            hi = hi if V.dot(A3, u3) <= V.dot(B3, u3) else 1e18
        if i == n - 2:
            hi = 1e18 if V.dot(A3, u3) <= V.dot(B3, u3) else hi
            lo = lo if V.dot(A3, u3) <= V.dot(B3, u3) else -1e18
        segs.append((V.dot(A3, D3), u3, lo - tol, hi + tol))
    out = []
    exp = TopExp_Explorer(cut, TopAbs_FACE)
    while exp.More():
        f = to_face(exp.Current())
        exp.Next()
        surf = BRepAdaptor_Surface(f, True)
        if surf.GetType() != GeomAbs_Plane:
            continue
        ax = surf.Plane().Axis().Direction()
        nrm = (ax.X(), ax.Y(), ax.Z())
        if abs(V.dot(nrm, D3)) < 1 - 1e-6:
            continue
        g = GProp_GProps()
        static(BRepGProp, "SurfaceProperties")(f, g)
        c = g.CentreOfMass()
        c = (c.X(), c.Y(), c.Z())
        hit = any(abs(V.dot(c, D3) - off) < tol * 10 and lo <= V.dot(c, u3) <= hi for off, u3, lo, hi in segs)
        if not hit:
            continue
        loops = []
        wexp = TopExp_Explorer(f, TopAbs_WIRE)
        while wexp.More():
            w = _to_wire(wexp.Current()) if _to_wire else wexp.Current()
            wexp.Next()
            loop3 = _wire_loop(w, f.Orientation() == TopAbs_REVERSED, step)
            if len(loop3) >= 3:
                loops.append([[V.dot(p, Vxs), V.dot(p, Vys)] for p in loop3])
        if loops:
            out.append(loops)
    return out


def keeps_cylinder(vg, cyl):
    """False when a cylinder lies wholly in the material the section removed."""
    if not getattr(vg, "removal", None):
        return True
    Np, Vxp, Vyp = vg.parent_basis
    for k in range(7):
        t = cyl.t0 + (cyl.t1 - cyl.t0) * k / 6.0
        p3 = cyl.point_at(t)
        q = (V.dot(p3, Vxp), V.dot(p3, Vyp))
        if not _point_in_poly(q, vg.removal) or _poly_dist(q, vg.removal) < cyl.radius * 0.999:
            return True
    return False


def hatch_lines(loops_list, spacing, angle_deg=45.0):
    """45° hatch segments (view coords) for faces given as lists of loops (even-odd)."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    rot = lambda p: (p[0] * ca + p[1] * sa, -p[0] * sa + p[1] * ca)        # into hatch frame
    back = lambda p: (p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca)
    out = []
    for loops in loops_list:
        edges = []
        ys = []
        for loop in loops:
            r = [rot(p) for p in loop]
            ys += [p[1] for p in r]
            for i in range(len(r)):
                edges.append((r[i], r[(i + 1) % len(r)]))
        if not ys:
            continue
        y = math.floor(min(ys) / spacing) * spacing + spacing * 0.5
        top = max(ys)
        while y < top:
            xs = []
            for (x1, y1), (x2, y2) in edges:
                if (y1 > y) != (y2 > y):
                    xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                if xs[i + 1] - xs[i] > 1e-9:
                    p, q = back((xs[i], y)), back((xs[i + 1], y))
                    out.append({"k": "L", "p": [p[0], p[1], q[0], q[1]]})
            y += spacing
    return out
