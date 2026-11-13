"""Choose datums and orient the part on the sheet.

The drawing frame (Xd, Yd, Zd) is right-handed:
  Zd = "up" on the sheet in the front view  (prismatic: datum A at the bottom)
  Xd = "right" in the front view            (longest in-plane extent; datum on the left)
  Yd = away from the viewer of the front view
"""
from dataclasses import dataclass, asdict

from . import vec as V

MODEL_AXES = [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]


@dataclass
class Datum:
    letter: str
    feature: str           # feature id (P# / C#)
    kind: str              # plane | axis
    direction: tuple       # outward normal (plane) or axis direction

    def to_dict(self):
        return asdict(self)


def _neg_pref(n):
    """Tie-break score: surfaces facing -Z, -Y, -X (min side of the model) win."""
    i = max(range(3), key=lambda k: abs(n[k]))
    return (1 if n[i] < 0 else 0, i == 2, i == 1)


def _largest(planes, pred):
    cands = [p for p in planes if pred(p)]
    if not cands:
        return None
    top = max(p.area for p in cands)
    near = [p for p in cands if p.area >= top * 0.97]
    return max(near, key=lambda p: (_neg_pref(p.normal), p.area))


def part_type(part):
    bosses = [c for c in part.cyls if c.kind == "boss"]
    if not bosses:
        return "prismatic"
    total = sum(p.area for p in part.planes) + sum(c.area for c in part.cyls)
    best = 0.0
    for b in bosses:
        same = [c for c in bosses if V.parallel(c.axis, b.axis) and V.norm(V.sub(c.origin, b.origin)) < 1e-2]
        a = sum(c.area for c in same)
        a += sum(p.area for p in part.planes if V.parallel(p.normal, b.axis))
        best = max(best, a)
    return "turned" if best > 0.6 * total else "prismatic"


def choose_datums(part):
    ptype = part_type(part)
    datums = []
    if ptype == "turned":
        bosses = [c for c in part.cyls if c.kind == "boss"]
        a = max(bosses, key=lambda c: (round(c.length, 3), c.area))
        datums.append(Datum("A", a.id, "axis", a.axis))
        ends = [p for p in part.planes if V.parallel(p.normal, a.axis)]
        if ends:
            offs = [V.dot(p.point, a.axis) for p in ends]
            lo, hi = min(offs), max(offs)
            extreme = [p for p, o in zip(ends, offs) if abs(o - lo) < 1e-3 or abs(o - hi) < 1e-3]
            b = max(extreme or ends, key=lambda p: (p.area, _neg_pref(p.normal)))
            datums.append(Datum("B", b.id, "plane", b.normal))
        return ptype, datums

    A = _largest(part.planes, lambda p: True)
    if A is None:
        return ptype, datums
    datums.append(Datum("A", A.id, "plane", A.normal))
    B = _largest(part.planes, lambda p: V.perpendicular(p.normal, A.normal, 1e-3))
    if B is not None:
        datums.append(Datum("B", B.id, "plane", B.normal))
        C = _largest(part.planes, lambda p: V.perpendicular(p.normal, A.normal, 1e-3)
                     and V.perpendicular(p.normal, B.normal, 1e-3))
        if C is not None:
            datums.append(Datum("C", C.id, "plane", C.normal))
    holes = sorted([c for c in part.cyls if c.kind == "hole" and not c.absorbed
                    and V.parallel(c.axis, A.normal)], key=lambda c: -c.radius)
    letters = "BC"
    while len(datums) < 3 and holes:
        h = holes.pop(0)
        datums.append(Datum(letters[len(datums) - 1], h.id, "axis", h.axis))
    return ptype, datums


def _corners(bbox):
    x0, y0, z0, x1, y1, z1 = bbox
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def _extent(bbox, d):
    vals = [V.dot(c, d) for c in _corners(bbox)]
    return max(vals) - min(vals)


def choose_frame(part, ptype, datums):
    by = {d.letter: d for d in datums}
    if ptype == "turned" and "A" in by:
        ax = by["A"].direction
        Xd = ax
        if "B" in by:
            Xd = V.neg(by["B"].direction) if V.dot(by["B"].direction, ax) != 0 else ax
            Xd = V.unit(Xd)
        Zd = min(MODEL_AXES, key=lambda m: abs(V.dot(m, Xd)))
        Zd = V.unit(V.sub(Zd, V.mul(Xd, V.dot(Zd, Xd))))
        Yd = V.cross(Zd, Xd)
        return Xd, Yd, Zd

    if "A" in by and by["A"].kind == "plane":
        Zd = V.neg(by["A"].direction)
    else:
        Zd = (0.0, 0.0, 1.0)
    planar = [d for d in datums if d.kind == "plane" and d.letter != "A"]
    if planar:
        u1 = planar[0].direction
    else:
        u1 = min(MODEL_AXES, key=lambda m: abs(V.dot(m, Zd)))
    u1 = V.unit(V.sub(u1, V.mul(Zd, V.dot(u1, Zd))))
    u2 = V.cross(Zd, u1)
    Xd = u1 if _extent(part.bbox, u1) >= _extent(part.bbox, u2) - 1e-6 else u2
    for d in planar:
        if V.parallel(d.direction, Xd, 1e-3):
            Xd = V.neg(d.direction)        # that datum sits on the left
            break
    else:
        Xd = V.canonical(Xd)
    Xd = V.unit(Xd)
    Yd = V.cross(Zd, Xd)
    return Xd, Yd, Zd


# view name -> (N toward viewer, paper-right) in terms of the frame
def view_basis(frame, name):
    Xd, Yd, Zd = frame
    table = {
        "front": (V.neg(Yd), Xd),
        "top": (Zd, Xd),
        "bottom": (V.neg(Zd), Xd),
        "left": (V.neg(Xd), V.neg(Yd)),
        "right": (Xd, Yd),
        "rear": (Yd, V.neg(Xd)),
    }
    if name == "iso":
        N = V.unit(V.add(V.add(Xd, V.neg(Yd)), Zd))
        Vy = V.unit(V.sub(Zd, V.mul(N, V.dot(Zd, N))))
        Vx = V.cross(Vy, N)
        return N, Vx, Vy
    N, Vx = table[name]
    Vy = V.cross(N, Vx)
    return N, Vx, Vy


VIEW_LABELS = {
    "front": "FRONT VIEW", "top": "TOP VIEW", "bottom": "BOTTOM VIEW",
    "left": "LEFT SIDE VIEW", "right": "RIGHT SIDE VIEW", "rear": "REAR VIEW",
    "iso": "ISOMETRIC VIEW",
}


def side_view_name(projection):
    """The side view that sits to the right of the front view."""
    return "left" if projection == "first" else "right"


def default_views(ptype, projection):
    side = side_view_name(projection)
    if ptype == "turned":
        return ["front", side, "iso"]
    return ["front", "top", side, "iso"]
