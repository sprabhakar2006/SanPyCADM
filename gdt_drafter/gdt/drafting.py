"""Auto-drafting: decide which dimensions, datum symbols and feature control
frames go on which view. Positions are only roughed in here (sides / tiers /
anchors); arrange.py does the final placement on the sheet.

Strategy (a common, inspection-friendly scheme):
  * datums A|B|C on the three mutually perpendicular primary faces
    (turned parts: A = main diameter axis, B = an end face)
  * flatness on A, perpendicularity on B and C, parallelism on the top face
  * every hole / boss: size callout + position (⌀t Ⓜ |A|B|C|) with basic
    (boxed) location dimensions measured from the datum planes
  * plane-to-plane sizes as baseline dimensions from the datums, covered by
    the general tolerance note
  * radii as "nX Rr" callouts; turned diameters with circular runout to A
"""
import math

from . import vec as V
from .document import new_id
from .layout import grid_cells, neighbours
from .projection import segments

TOL_TABLE = [
    (50.0, dict(form=0.02, orient=0.03, pos=0.05, runout=0.02, hole=0.05)),
    (150.0, dict(form=0.05, orient=0.05, pos=0.1, runout=0.03, hole=0.1)),
    (400.0, dict(form=0.1, orient=0.1, pos=0.2, runout=0.05, hole=0.15)),
    (1e18, dict(form=0.2, orient=0.2, pos=0.4, runout=0.1, hole=0.2)),
]

ORTHO = ("front", "top", "bottom", "left", "right", "rear")


def tolerances(size):
    for lim, t in TOL_TABLE:
        if size <= lim:
            return t
    return TOL_TABLE[-1][1]


# ------------------------------------------------------------ view helpers

def plane_line(vg, plane):
    """Edge-on projection of a plane in a view, or None if not edge-on."""
    n = plane.normal
    if abs(V.dot(n, vg.N)) > 1e-3:
        return None
    n2 = (V.dot(n, vg.Vx), V.dot(n, vg.Vy))
    L = math.hypot(*n2)
    if L < 1e-6:
        return None
    n2 = (n2[0] / L, n2[1] / L)
    t2 = (-n2[1], n2[0])
    c = plane.offset
    ss = [V.dot(vg.project(p), t2) for p in plane.pts] or [0.0]
    return {"n2": n2, "t2": t2, "c": c, "s0": min(ss), "s1": max(ss)}


def line_point(ln, s):
    return (ln["n2"][0] * ln["c"] + ln["t2"][0] * s, ln["n2"][1] * ln["c"] + ln["t2"][1] * s)


def visible_run(vg, ln, n=60):
    """Longest visible stretch (s0, s1) of an edge-on plane line."""
    best, cur = None, None
    s0, s1 = ln["s0"], ln["s1"]
    if s1 - s0 < 1e-6:
        return None
    for i in range(n + 1):
        s = s0 + (s1 - s0) * i / n
        if vg.visible_at(line_point(ln, s)):
            cur = (cur[0], s) if cur else (s, s)
            if best is None or cur[1] - cur[0] > best[1] - best[0]:
                best = cur
        else:
            cur = None
    return best


def circle_visibility(vg, center, r, n=16):
    k = 0
    for i in range(n):
        a = 2 * math.pi * i / n
        if vg.visible_at((center[0] + r * math.cos(a), center[1] + r * math.sin(a))):
            k += 1
    return k / float(n)


def side_of(n2):
    if abs(n2[0]) >= abs(n2[1]):
        return "right" if n2[0] > 0 else "left"
    return "top" if n2[1] > 0 else "bottom"


class Drafter:
    def __init__(self, part, frame, datums, ptype, geoms, settings, assembly=False):
        self.assembly = assembly
        self.part = part
        self.frame = frame
        self.datums = datums                  # list of dicts
        self.ptype = ptype
        self.geoms = geoms
        self.settings = settings
        self.tol = tolerances(part.size)
        self.ann = []
        views = [v for v in settings["views"] if v in geoms]
        self.views = views
        self.ortho = [v for v in views if v in ORTHO]
        self.cells = grid_cells(views, settings["projection"])
        self.by_letter = {d["letter"]: d for d in datums}
        self.by_feature = {d["feature"]: d for d in datums}
        self.callout_of = {}                  # feature id -> callout annotation id

    # -------------------------------------------------- utilities
    def free_side(self, view, axis):
        nb = neighbours(self.cells, view)
        opts = ["top", "bottom"] if axis == "h" else ["left", "right"]
        if self.ptype == "turned" and axis == "h":
            opts = ["bottom", "top"]       # keep the top free for datum A / runout frames
        for s in opts:
            if s not in nb:
                return s
        return opts[0]

    SIDE_DIR = {"top": (0.0, 1.0), "bottom": (0.0, -1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0)}

    def vsegs(self, vg):
        segs = getattr(vg, "_draft_segs", None)
        if segs is None:
            step = max(vg.size / 300.0, 0.05)
            segs = []
            for cv in vg.visible:
                segs.extend(segments(cv, step))
            vg._draft_segs = segs
        return segs

    def crossings(self, vg, p, d, start=0.0):
        """How many visible outlines an extension line from p in direction d would cross."""
        bb = vg.bbox
        far = 2 * max(bb[2] - bb[0], bb[3] - bb[1]) + 10
        e = start + max(vg.size * 1e-3, 0.05)
        a = (p[0] + d[0] * e, p[1] + d[1] * e)
        b = (p[0] + d[0] * far, p[1] + d[1] * far)
        hits = []
        for s0, s1 in self.vsegs(vg):
            x = _seg_intersection(a, b, s0, s1)
            if x is not None and not any(abs(x[0] - h[0]) + abs(x[1] - h[1]) < 1e-3 for h in hits):
                hits.append(x)
        return len(hits)

    def choose_side(self, view, axis, endpoints_for):
        """endpoints_for(side) -> [(point, setback)]; least crossings wins, free side breaks ties."""
        vg = self.geoms[view]
        pref = self.free_side(view, axis)
        best = None
        for side in (["top", "bottom"] if axis == "h" else ["left", "right"]):
            d = self.SIDE_DIR[side]
            cost = sum(self.crossings(vg, p, d, st) for p, st in endpoints_for(side))
            score = (cost, 0 if side == pref else 1)
            if best is None or score < best[0]:
                best = (score, side)
        return best[1]

    def add(self, a):
        a.setdefault("id", new_id())
        a.setdefault("auto", True)
        a.setdefault("placed", False)
        self.ann.append(a)
        return a

    def datum_plane(self, letter):
        d = self.by_letter.get(letter)
        if d and d["kind"] == "plane":
            return self.part.feature(d["feature"])
        return None

    def view_pref(self, *names):
        order = [n for n in names if n in self.ortho] + [n for n in self.ortho if n not in names]
        return order

    def side_view(self):
        for n in ("left", "right"):
            if n in self.ortho:
                return n
        return None

    # -------------------------------------------------- datums on planes
    def best_edge_view(self, plane, prefs, need_also=None):
        """Choose (view, line, run) where the plane is edge-on & visible.
        Prefers views where its outward side faces free space."""
        best = None
        for rank, vn in enumerate(prefs):
            vg = self.geoms[vn]
            ln = plane_line(vg, plane)
            if not ln:
                continue
            if need_also is not None and plane_line(vg, need_also) is None:
                continue
            run = visible_run(vg, ln)
            if not run or run[1] - run[0] < 0.1 * (ln["s1"] - ln["s0"] + 1e-9):
                continue
            free = side_of(ln["n2"]) not in neighbours(self.cells, vn)
            score = (1 if free else 0, -rank)
            if best is None or score > best[0]:
                best = (score, vn, ln, run)
        return best[1:] if best else None

    def surface_fcf(self, plane, view, ln, run, frac, char, tol, datums, dia=False):
        s = run[0] + (run[1] - run[0]) * frac
        p = line_point(ln, s)
        return self.add({"kind": "fcf", "view": view, "anchor": list(p), "dir": list(ln["n2"]),
                         "char": char, "tol": tol, "dia": dia, "mod": "", "datums": datums,
                         "feature": plane.id, "attach": None, "off": None})

    def datum_symbol(self, letter, plane, view, ln, run, frac):
        s = run[0] + (run[1] - run[0]) * frac
        p = line_point(ln, s)
        return self.add({"kind": "datum", "view": view, "anchor": list(p), "dir": list(ln["n2"]),
                         "letter": letter, "feature": plane.id, "len": None, "slide": 0.0, "attach": None})

    # -------------------------------------------------- main
    def run(self):
        if not self.ortho:
            return self.ann
        if self.assembly:
            self.plane_levels(overall_only=True)
            return self.ann
        if self.ptype == "turned":
            self.turned()
        else:
            self.prismatic_datums()
        self.holes_and_bosses()
        self.plane_levels()
        self.radii()
        return self.ann

    def prismatic_datums(self):
        side = self.side_view()
        A, B, C = self.datum_plane("A"), self.datum_plane("B"), self.datum_plane("C")
        t = self.tol
        if A:
            got = self.best_edge_view(A, self.view_pref("front", side or "", "top"))
            if got:
                vn, ln, run = got
                self.datum_symbol("A", A, vn, ln, run, 0.18)
                self.surface_fcf(A, vn, ln, run, 0.62, "flatness", t["form"], [])
        if B:
            got = (self.best_edge_view(B, self.view_pref(side or "", "front", "top"), need_also=A)
                   or self.best_edge_view(B, self.view_pref("top", side or "", "front")))
            if got:
                vn, ln, run = got
                self.datum_symbol("B", B, vn, ln, run, 0.2)
                self.surface_fcf(B, vn, ln, run, 0.65, "perpendicularity", t["orient"], [["A", ""]] if A else [])
        if C:
            got = (self.best_edge_view(C, self.view_pref("front", "top", side or ""), need_also=A)
                   or self.best_edge_view(C, self.view_pref("top", "front", side or "")))
            if got:
                vn, ln, run = got
                self.datum_symbol("C", C, vn, ln, run, 0.25)
                refs = [["A", ""]] if A else []
                if B:
                    refs.append(["B", ""])
                self.surface_fcf(C, vn, ln, run, 0.7, "perpendicularity", t["orient"], refs)
        if A:
            # parallelism on the face opposite datum A
            opp = [p for p in self.part.planes if V.dot(p.normal, A.normal) < -1 + 1e-3 and p.area > 0.1 * A.area]
            if opp:
                top = max(opp, key=lambda p: p.offset)
                got = self.best_edge_view(top, self.view_pref("front", side or "", "top"))
                if got:
                    vn, ln, run = got
                    self.surface_fcf(top, vn, ln, run, 0.5, "parallelism", t["orient"] * 2, [["A", ""]])

    # -------------------------------------------------- turned parts
    def main_axis(self):
        d = self.by_letter.get("A")
        if d and d["kind"] == "axis":
            return self.part.feature(d["feature"])
        return None

    def turned(self):
        A = self.main_axis()
        if not A or "front" not in self.ortho:
            return
        vg = self.geoms["front"]
        t = self.tol
        bosses = [c for c in self.part.cyls if c.kind == "boss" and V.parallel(c.axis, A.axis)
                  and V.norm(V.sub(c.origin, A.origin)) < 1e-2]
        for c in sorted(bosses, key=lambda c: c.t0):
            cu, cv = vg.project(c.center)
            r = c.radius
            is_a = c.id == A.id
            dim = self.add({"kind": "dim", "view": "front", "axis": "v", "a": [cu, cv - r], "b": [cu, cv + r],
                            "side": "at", "at": cu, "tier": 0, "gap": None, "shift": 0.0, "prefix": "⌀",
                            "text": "", "count": "", "feature": c.id,
                            "tol": {"mode": "dev", "up": 0.0, "lo": -2 * t["form"]} if is_a else {"mode": "none", "up": 0.1, "lo": -0.1}})
            if is_a:
                self.add({"kind": "datum", "view": "front", "anchor": [cu, cv + r], "dir": [0.0, 1.0],
                          "letter": "A", "feature": c.id, "len": None, "slide": 0.0, "attach": None,
                          "inline": dim["id"]})
            else:
                u = vg.project(c.point_at(c.t0 + 0.7 * c.length))[0]
                self.add({"kind": "fcf", "view": "front", "anchor": [u, cv + r], "dir": [0.0, 1.0],
                          "char": "circular_runout", "tol": t["runout"], "dia": False, "mod": "",
                          "datums": [["A", ""]], "feature": c.id, "attach": None, "off": None})
        B = self.datum_plane("B")
        if B:
            got = self.best_edge_view(B, self.view_pref("front"))
            if got:
                vn, ln, run = got
                self.datum_symbol("B", B, vn, ln, run, 0.85)
                self.surface_fcf(B, vn, ln, run, 0.3, "perpendicularity", t["orient"], [["A", ""]])

    # -------------------------------------------------- holes & bosses
    def holes_and_bosses(self):
        feats = [c for c in self.part.cyls if c.kind in ("hole", "boss") and not c.absorbed]
        A = self.main_axis() if self.ptype == "turned" else None
        if A:
            feats = [c for c in feats if not (c.kind == "boss" and V.parallel(c.axis, A.axis)
                                             and V.norm(V.sub(c.origin, A.origin)) < 1e-2)]
        groups = []
        for c in feats:
            key = (c.kind, round(c.radius, 4), c.thru, round(c.length, 3), V.canonical(tuple(round(x, 4) for x in c.axis)),
                   (round(c.cbore["radius"], 3), round(c.cbore["depth"], 3)) if c.cbore else None,
                   (round(c.csink["diameter"], 3), round(c.csink["angle"], 1)) if c.csink else None)
            for g in groups:
                if g[0] == key:
                    g[1].append(c)
                    break
            else:
                groups.append((key, [c]))
        loc_points = {}       # view -> list of (feature, center2d)
        for key, members in groups:
            view = self.circle_view(members)
            if not view:
                continue
            vg = self.geoms[view]
            centers = [vg.project(m.center) for m in members]
            bb = vg.bbox
            vc = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
            # anchor on the member nearest a corner, on the side facing out
            idx = max(range(len(members)), key=lambda i: V.dist2(centers[i], vc))
            c2 = centers[idx]
            d = (c2[0] - vc[0], c2[1] - vc[1])
            L = math.hypot(*d)
            d = (0.7071, 0.7071) if L < 1e-6 else (d[0] / L, d[1] / L)
            # snap to a 45° leader direction
            d = (math.copysign(0.7071, d[0] or 1), math.copysign(0.7071, d[1] or 1))
            r = members[0].radius
            anchor = [c2[0] + r * d[0], c2[1] + r * d[1]]
            m0 = members[0]
            lines = self.callout_lines(m0, len(members))
            tol = ({"mode": "dev", "up": self.tol["hole"], "lo": 0.0} if m0.kind == "hole"
                   else {"mode": "dev", "up": 0.0, "lo": -self.tol["hole"]})
            co = self.add({"kind": "callout", "view": view, "anchor": anchor, "center": list(c2),
                           "lines": lines, "size": 2 * r, "tol": tol, "off": None,
                           "feature": m0.id, "members": [m.id for m in members]})
            for m in members:
                self.callout_of[m.id] = co["id"]
            # geometric control
            own = self.by_feature.get(m0.id)
            refs = self.position_refs(m0)
            on_axis_A = A is not None and V.parallel(m0.axis, A.axis) and V.norm(V.sub(m0.origin, A.origin)) < 1e-2
            if own:
                prim = [r for r in refs if r[0] < own["letter"]][:1]
                self.add({"kind": "fcf", "view": view, "anchor": None, "attach": co["id"],
                          "char": "perpendicularity" if prim else "cylindricity",
                          "tol": self.tol["orient"] if prim else self.tol["form"],
                          "dia": bool(prim), "mod": "M" if prim else "", "datums": prim,
                          "feature": m0.id, "off": None})
                self.add({"kind": "datum", "view": view, "anchor": None, "dir": [0.0, -1.0], "letter": own["letter"],
                          "feature": m0.id, "len": None, "slide": 0.0, "attach": co["id"]})
            elif refs:
                if on_axis_A:
                    refs = [[self.by_letter["A"]["letter"], ""]]
                self.add({"kind": "fcf", "view": view, "anchor": None, "attach": co["id"],
                          "char": "position", "tol": self.tol["pos"] if not on_axis_A else self.tol["runout"],
                          "dia": True, "mod": "M" if m0.kind in ("hole", "boss") else "",
                          "datums": refs, "feature": m0.id, "off": None})
            bc = bolt_circle(centers) if len(members) >= 3 else None
            if bc:
                self.bolt_circle_annotations(view, vg, members, centers, bc, co)
            elif not on_axis_A:
                loc_points.setdefault(view, []).extend((m, c) for m, c in zip(members, centers))
            if bc and not self.center_on_datum_axis(vg, bc[:2]):
                loc_points.setdefault(view, []).append((_Pt(m0.id), (bc[0], bc[1])))
        for view, pts in loc_points.items():
            self.location_dims(view, pts)

    def center_on_datum_axis(self, vg, c):
        for d in self.datums:
            if d["kind"] != "axis":
                continue
            f = self.part.feature(d["feature"])
            if f is not None and abs(V.dot(f.axis, vg.N)) > 1 - 1e-3 and V.dist2(vg.project(f.center), c) < 1e-2:
                return True
        return False

    def bolt_circle_annotations(self, view, vg, members, centers, bc, co):
        cx, cy, R = bc
        co["lines"][0] += " EQ SP"
        angs = sorted(math.degrees(math.atan2(c[1] - cy, c[0] - cx)) % 360.0 for c in centers)
        n = len(angs)
        # put the PCD leader between two holes, as close to 45° as possible
        mids = [(angs[i] + ((angs[(i + 1) % n] - angs[i]) % 360.0) / 2) % 360.0 for i in range(n)]
        am = min(mids, key=lambda a: min(abs(a - 45), abs(a - 405)))
        anchor = [cx + R * math.cos(math.radians(am)), cy + R * math.sin(math.radians(am))]
        self.add({"kind": "callout", "view": view, "anchor": anchor, "center": [cx, cy], "pcd": True,
                  "lines": ["⌀{size}"], "size": 2 * R, "tol": {"mode": "basic", "up": 0.1, "lo": -0.1},
                  "off": None, "feature": members[0].id, "members": []})
        if any(min(a % 90.0, 90.0 - a % 90.0) < 0.01 for a in angs):
            return      # a hole sits on a centre line: orientation is implied
        signed = [a if a <= 180 else a - 360 for a in angs]
        first = min(signed, key=abs)
        a0, a1 = (0.0, first) if first > 0 else (first % 360.0, 360.0)
        self.add({"kind": "angle", "view": view, "center": [cx, cy], "r": R, "a0": a0, "a1": a1 % 360.0 if a1 != 360.0 else 0.0,
                  "gap": None, "tol": {"mode": "basic", "up": 0.5, "lo": -0.5}, "feature": members[0].id})

    def circle_view(self, members):
        best = None
        prefs = self.view_pref("top", "front", self.side_view() or "")
        for rank, vn in enumerate(prefs):
            vg = self.geoms[vn]
            if abs(V.dot(members[0].axis, vg.N)) < 1 - 1e-3:
                continue
            vis = sum(circle_visibility(vg, vg.project(m.center), m.radius) for m in members) / len(members)
            score = (vis > 0.5, vis, -rank)
            if best is None or score > best[0]:
                best = (score, vn)
        return best[1] if best else None

    def callout_lines(self, c, n):
        cnt = "%dX " % n if n > 1 else ""
        if c.kind == "boss":
            return [cnt + "⌀{size}"]
        first = cnt + "⌀{size}" + (" THRU" if c.thru else " ↧%s" % _f(c.length))
        lines = [first]
        if c.cbore:
            lines.append("⌴⌀%s ↧%s" % (_f(2 * c.cbore["radius"]), _f(c.cbore["depth"])))
        if c.csink:
            lines.append("⌵⌀%s X %s°" % (_f(c.csink["diameter"]), _f(c.csink["angle"], 0)))
        return lines

    def position_refs(self, c):
        """Datum reference frame for locating cylinder c: primary = datum whose
        plane is perpendicular to the axis (or the datum axis it is parallel to)."""
        refs, used = [], set()
        for d in self.datums:
            f = self.part.feature(d["feature"])
            if f is None or f.id == c.id:
                continue
            if d["kind"] == "plane" and V.parallel(f.normal, c.axis, 1e-3):
                refs.append([d["letter"], ""])
                used.add(d["letter"])
                break
        for d in self.datums:
            if d["letter"] in used:
                continue
            f = self.part.feature(d["feature"])
            if f is None or f.id == c.id:
                continue
            if d["kind"] == "plane" and V.parallel(f.normal, c.axis, 1e-3):
                continue
            refs.append([d["letter"], "M" if d["kind"] == "axis" else ""])
            if len(refs) == 3:
                break
        return refs

    def location_dims(self, view, pts):
        vg = self.geoms[view]
        refs = {"h": None, "v": None}
        for d in self.datums:
            f = self.part.feature(d["feature"])
            if d["kind"] != "plane" or f is None:
                continue
            ln = plane_line(vg, f)
            if not ln:
                continue
            ax = "h" if abs(ln["n2"][0]) > 0.999 else ("v" if abs(ln["n2"][1]) > 0.999 else None)
            if ax and refs[ax] is None:
                refs[ax] = ("plane", ln, d["letter"])
        for d in self.datums:
            if d["kind"] != "axis":
                continue
            f = self.part.feature(d["feature"])
            if f is None or abs(V.dot(f.axis, vg.N)) < 1 - 1e-3:
                continue
            p = vg.project(f.center)
            for ax in ("h", "v"):
                if refs[ax] is None:
                    refs[ax] = ("point", p, d["letter"])
        bb = vg.bbox
        for ax in ("h", "v"):
            ref = refs[ax]
            k = 0 if ax == "h" else 1
            if ref is None:
                base_val, basic = bb[k], False
            elif ref[0] == "plane":
                ln = ref[1]
                base_val, basic = ln["c"] * ln["n2"][k], True
            else:
                base_val, basic = ref[1][k], True
            def ends(side, pts=pts, k=k):
                return [(c, m.radius) for m, c in pts]
            side = self.choose_side(view, ax, ends)
            seen = []
            for m, c in pts:
                val = c[k]
                if abs(val - base_val) < 1e-3 or any(abs(val - s) < 1e-3 for s in seen):
                    continue
                if self.by_feature.get(m.id) and ref and ref[0] == "point":
                    continue
                seen.append(val)
                # base point: on the reference, at the edge facing the dimension side
                if ax == "h":
                    ey = bb[3] if side == "top" else bb[1]
                    a = [base_val, ey]
                else:
                    ex = bb[0] if side == "left" else bb[2]
                    a = [ex, base_val]
                if ref and ref[0] == "point":
                    a = list(ref[1])
                self.add({"kind": "dim", "view": view, "axis": ax, "a": a, "b": list(c), "side": side,
                          "tier": 0, "gap": None, "shift": 0.0, "prefix": "", "text": "", "count": "",
                          "feature": m.id, "tol": {"mode": "basic" if basic else "none", "up": 0.1, "lo": -0.1}})

    # -------------------------------------------------- plane-to-plane sizes
    def plane_levels(self, overall_only=False):
        self.overall_only = overall_only
        X, Y, Z = self.frame
        side = self.side_view()
        plan = []
        if self.ptype == "turned":
            plan.append((X, ["front", "top"]))
        else:
            plan.append((Z, ["front", side, "rear"]))
            plan.append((X, ["front", "top", "bottom", "rear"]))
            plan.append((Y, [side, "top", "bottom"]))
        for D, prefs in plan:
            for vn in prefs:
                if vn in self.ortho:
                    self.levels_in_view(D, vn)
                    break

    def levels_in_view(self, D, view):
        vg = self.geoms[view]
        du, dv = V.dot(D, vg.Vx), V.dot(D, vg.Vy)
        if abs(du) > 0.999:
            ax, k = "h", 0
        elif abs(dv) > 0.999:
            ax, k = "v", 1
        else:
            return
        if getattr(self, "overall_only", False):
            return self.overall_dim(D, view, ax, k)
        planes = [p for p in self.part.planes if V.parallel(p.normal, D, 1e-3) and not self.is_hole_floor(p)]
        if not planes:
            return
        lines = [(p, plane_line(vg, p)) for p in planes]
        lines = [(p, ln) for p, ln in lines if ln]
        if not lines:
            return
        ref = None
        for d in self.datums:
            if d["kind"] == "plane":
                f = self.part.feature(d["feature"])
                if f is not None and V.parallel(f.normal, D, 1e-3):
                    ref = f
                    break
        val = lambda ln: ln["c"] * ln["n2"][k]
        if ref is None:
            ref = min(lines, key=lambda pl: val(pl[1]))[0]
        ref_ln = plane_line(vg, ref)
        if ref_ln is None:
            return
        base = val(ref_ln)
        bb = vg.bbox

        def ends(side):
            out = [(self._edge_point(ref_ln, k, side, bb), 0.0)]
            for p, ln in lines:
                if p.id != ref.id:
                    out.append((self._edge_point(ln, k, side, bb), 0.0))
            return out
        side = self.choose_side(view, ax, ends)
        seen = []
        extremes = [bb[k], bb[k + 2]]
        targets = [(val(ln), p, ln) for p, ln in lines if p.id != ref.id]
        for e in extremes:
            if abs(e - base) > 1e-3 and not any(abs(t[0] - e) < 1e-3 for t in targets):
                targets.append((e, None, None))
        for v_, p, ln in sorted(targets, key=lambda t: abs(t[0] - base)):
            if abs(v_ - base) < 1e-3 or any(abs(v_ - s) < 1e-3 for s in seen):
                continue
            seen.append(v_)
            a = self._edge_point(ref_ln, k, side, bb)
            b = self._edge_point(ln, k, side, bb) if ln else ([v_, bb[3] if side == "top" else bb[1]] if ax == "h"
                                                             else [bb[0] if side == "left" else bb[2], v_])
            self.add({"kind": "dim", "view": view, "axis": ax, "a": a, "b": b, "side": side, "tier": 0,
                      "gap": None, "shift": 0.0, "prefix": "", "text": "", "count": "",
                      "feature": p.id if p else None, "tol": {"mode": "none", "up": 0.1, "lo": -0.1}})

    def overall_dim(self, D, view, ax, k):
        vg = self.geoms[view]
        bb = vg.bbox
        side = self.free_side(view, ax)
        if ax == "h":
            y = bb[3] if side == "top" else bb[1]
            a, b = [bb[0], y], [bb[2], y]
        else:
            x = bb[0] if side == "left" else bb[2]
            a, b = [x, bb[1]], [x, bb[3]]
        self.add({"kind": "dim", "view": view, "axis": ax, "a": a, "b": b, "side": side, "tier": 0,
                  "gap": None, "shift": 0.0, "prefix": "", "text": "", "count": "", "feature": None,
                  "tol": {"mode": "ref", "up": 0.1, "lo": -0.1}})

    def is_hole_floor(self, p):
        """Flat bottoms of blind holes and counterbore floors (sized by the callout instead).
        Coplanar faces are merged, so every face of the plane must be such a floor."""
        holes = [c for c in self.part.cyls if c.kind == "hole" and V.parallel(c.axis, p.normal, 1e-3)]
        if not holes:
            return False
        for centroid, area in (p.parts or [(p.point, p.area)]):
            ok = False
            for c in holes:
                foot = V.add(c.origin, V.mul(c.axis, V.dot(centroid, c.axis)))
                if V.norm(V.sub(foot, centroid)) > 1e-2:
                    continue
                r_out = max([o.radius for o in holes if V.norm(V.sub(o.origin, c.origin)) < 1e-2] + [c.radius])
                if area <= math.pi * r_out ** 2 * 1.02:
                    ok = True
                    break
            if not ok:
                return False
        return True

    def _edge_point(self, ln, k, side, bb):
        """End of an edge-on plane line nearest to the dimension side."""
        p0, p1 = line_point(ln, ln["s0"]), line_point(ln, ln["s1"])
        if side == "top":
            return list(max((p0, p1), key=lambda p: p[1]))
        if side == "bottom":
            return list(min((p0, p1), key=lambda p: p[1]))
        if side == "left":
            return list(min((p0, p1), key=lambda p: p[0]))
        return list(max((p0, p1), key=lambda p: p[0]))

    # -------------------------------------------------- radii
    def radii(self):
        rads = [c for c in self.part.cyls if c.kind == "radius"]
        groups = []
        for c in rads:
            key = (round(c.radius, 4), V.canonical(tuple(round(x, 4) for x in c.axis)))
            for g in groups:
                if g[0] == key:
                    g[1].append(c)
                    break
            else:
                groups.append((key, [c]))
        for key, members in groups:
            for vn in self.view_pref("top", "front", self.side_view() or ""):
                vg = self.geoms[vn]
                if abs(V.dot(members[0].axis, vg.N)) < 1 - 1e-3:
                    continue
                arc = None
                for m in members:
                    c2 = vg.project(m.center)
                    for cv in vg.visible:
                        if cv["k"] == "A" and abs(cv["r"] - m.radius) < 1e-3 and V.dist2(cv["c"], c2) < 1e-2:
                            arc = cv
                            break
                    if arc:
                        break
                if not arc:
                    continue
                span = (arc["a1"] - arc["a0"]) % 360.0
                am = math.radians(arc["a0"] + span / 2)
                anchor = [arc["c"][0] + arc["r"] * math.cos(am), arc["c"][1] + arc["r"] * math.sin(am)]
                n = len(members)
                self.add({"kind": "callout", "view": vn, "anchor": anchor, "center": list(arc["c"]),
                          "lines": [("%dX " % n if n > 1 else "") + "R{size}"], "size": members[0].radius,
                          "tol": {"mode": "none", "up": 0.1, "lo": -0.1}, "off": None,
                          "feature": members[0].id, "members": [m.id for m in members]})
                break


def _f(v, dec=2):
    from .document import fmt
    return fmt(v, dec)


def autodraft(part, frame, datums, ptype, geoms, settings, assembly=False):
    return Drafter(part, frame, datums, ptype, geoms, settings, assembly).run()


def _seg_intersection(p, q, a, b):
    """Intersection point of segments pq and ab, or None."""
    r = (q[0] - p[0], q[1] - p[1])
    s = (b[0] - a[0], b[1] - a[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((a[0] - p[0]) * s[1] - (a[1] - p[1]) * s[0]) / den
    u = ((a[0] - p[0]) * r[1] - (a[1] - p[1]) * r[0]) / den
    if 0.0 <= t <= 1.0 and -1e-9 <= u <= 1.0 + 1e-9:
        return (p[0] + t * r[0], p[1] + t * r[1])
    return None


class _Pt:
    """Stand-in feature for a pattern centre used as a dimension end point."""
    def __init__(self, fid):
        self.id = fid
        self.radius = 0.0


def bolt_circle(centers, tol=1e-3):
    """(cx, cy, R) if the points are equally spaced on a circle, else None."""
    n = len(centers)
    cx = sum(c[0] for c in centers) / n
    cy = sum(c[1] for c in centers) / n
    rs = [math.hypot(c[0] - cx, c[1] - cy) for c in centers]
    R = sum(rs) / n
    if R < 1e-6 or max(abs(r - R) for r in rs) > max(tol, R * 1e-4):
        return None
    angs = sorted(math.degrees(math.atan2(c[1] - cy, c[0] - cx)) % 360.0 for c in centers)
    step = 360.0 / n
    for i in range(n):
        gap = (angs[(i + 1) % n] - angs[i]) % 360.0
        if abs(gap - step) > 0.05:
            return None
    return cx, cy, R
