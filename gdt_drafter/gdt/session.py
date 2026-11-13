"""One open part: geometry, projections cache, document, render/export entry points."""
import copy
import math
import os
import tempfile

from . import vec as V
from .arrange import arrange
from .autocats import CATS, auto_settings, categorize
from .autocats import apply as apply_cats
from .autocats import merge as merge_cats
from .arrange import assign_tiers, compute_gutters
from .document import (STANDARD_VIEWS, bump_ids, fmt, migrate, new_document, new_id, new_view,
                       next_section_letter, sync_view_ids)
from .layout import auto_arrange, layout_views, place_missing
from .section import section_geom
from .drafting import Drafter, autodraft, plane_line, side_of
from .frame import Datum, choose_datums, choose_frame, view_basis
from .geometry import analyse, list_bodies, load_shape
from .projection import project_view
from .render import Ctx, render


class Session:
    def __init__(self, path, filename=None, doc=None, standard="ISO"):
        self.path = path
        self.filename = filename or os.path.basename(path)
        name = os.path.splitext(self.filename)[0]
        self.name = name
        self.shape = load_shape(path)
        self.bodies = list_bodies(self.shape)
        self._geoms = {}
        if doc is None:
            body = 0 if len(self.bodies) > 1 else None
            self._analyse(body)
            ptype, datums = self._datums()
            frame = choose_frame(self.part, ptype, datums)
            doc = new_document(name, self.filename, ptype, frame, datums, standard)
            doc["settings"]["body"] = body
            self.doc = doc
            self.autodraft()
        else:
            bump_ids(doc)
            self.doc = migrate(doc)
            self._analyse(doc["settings"].get("body"))
            for a in doc["annotations"]:          # projects saved before categories existed
                if a.get("auto") and "cats" not in a:
                    categorize(doc["annotations"], make_alternatives=False)
                    break

    def _analyse(self, body):
        if body is not None and 0 <= body < len(self.bodies):
            shape = self.bodies[body][2]
        else:
            shape = self.shape
        self.body = body
        self.part = analyse(shape, self.name)

    @property
    def assembly(self):
        return self.body is None and len(self.bodies) > 1

    def _datums(self):
        if self.assembly:
            return "prismatic", []
        return choose_datums(self.part)

    def set_body(self, body):
        body = None if body in (None, "", "all") else int(body)
        self._analyse(body)
        self._geoms = {}
        self.doc["settings"]["body"] = body
        self.reset_auto()

    @classmethod
    def from_bytes(cls, data, filename, doc=None, standard="ISO"):
        ext = os.path.splitext(filename)[1].lower() or ".step"
        fd, path = tempfile.mkstemp(suffix=ext, prefix="gdt_")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return cls(path, filename, doc, standard)

    # ------------------------------------------------------------ geometry
    @property
    def frame(self):
        f = self.doc["frame"]
        return tuple(f["X"]), tuple(f["Y"]), tuple(f["Z"])

    def view_key(self, v):
        st = self.doc["settings"]
        key_frame = tuple(round(x, 9) for vv in self.frame for x in vv)
        k = (v["type"], key_frame, st.get("hlr", "auto"), self.body)
        if v["type"] == "section":
            k += (v["parent"], tuple(tuple(round(c, 6) for c in p) for p in v["pts"]),
                  tuple(round(c, 6) for c in v["dir"]))
        return k

    def geoms(self):
        sync_view_ids(self.doc)
        mode = self.doc["settings"].get("hlr", "auto")
        out = {}
        for v in self.doc["views"]:
            k = self.view_key(v)
            if k not in self._geoms:
                if v["type"] == "section":
                    spec = dict(v)
                    self._geoms[k] = section_geom(self.part, self.frame, spec, mode)
                else:
                    self._geoms[k] = project_view(self.part, self.frame, v["type"], mode)
            g = self._geoms[k]
            if v["type"] == "section":
                g.spec = dict(v)
            out[v["id"]] = g
        return out

    def geom_key(self):
        import hashlib
        st = self.doc["settings"]
        extra = (st.get("centerlines", True), st.get("scale"), [v.get("scale") for v in self.doc["views"]])
        return hashlib.sha1(repr(([self.view_key(v) for v in self.doc["views"]], extra)).encode()).hexdigest()[:16]

    # ------------------------------------------------------------ views
    def ensure_layout(self, geoms):
        st = self.doc["settings"]
        std = [v for v in self.doc["views"] if v["type"] in STANDARD_VIEWS]
        if st.get("scale") is None or (std and all(not v.get("center") for v in std)):
            assign_tiers(self.doc)          # stacked auto dimensions decide how much room each view needs
            auto_arrange(self.doc, geoms, compute_gutters(self.doc, float(st.get("text_height", 3.5))))
        else:
            place_missing(self.doc, geoms)

    def rearrange(self):
        """Automatic scale and positions for every view (annotations stay attached)."""
        self.doc["settings"]["scale"] = None
        for v in self.doc["views"]:
            v["center"] = None
            if v["type"] != "iso":
                v["scale"] = None

    def add_view(self, vtype):
        if vtype not in STANDARD_VIEWS:
            raise ValueError("Unknown view " + str(vtype))
        if any(v["id"] == vtype for v in self.doc["views"]):
            raise ValueError("That view is already on the sheet.")
        self.doc["views"].append(new_view(vtype))
        sync_view_ids(self.doc)
        return vtype

    def delete_view(self, vid):
        gone = {vid} | {v["id"] for v in self.doc["views"] if v.get("parent") == vid}
        self.doc["views"] = [v for v in self.doc["views"] if v["id"] not in gone]
        anns = self.doc["annotations"]
        dead = {a["id"] for a in anns if a.get("view") in gone}
        self.doc["annotations"] = [a for a in anns if a["id"] not in dead and a.get("attach") not in dead]
        sync_view_ids(self.doc)

    def add_section(self, parent, pts, direction):
        pv = next((v for v in self.doc["views"] if v["id"] == parent), None)
        if pv is None or pv["type"] not in ("front", "top", "bottom", "left", "right", "rear"):
            raise ValueError("Draw the cutting line on a front, top, side or rear view.")
        pts = [[float(p[0]), float(p[1])] for p in pts]
        if len(pts) < 2:
            raise ValueError("A cutting line needs at least two points.")
        d = V.unit((float(direction[0]), float(direction[1])))
        letter = next_section_letter(self.doc)
        vid = "sec" + letter
        while any(v["id"] == vid for v in self.doc["views"]):
            vid += "_"
        self.doc["views"].append(new_view("section", id=vid, parent=parent, letter=letter,
                                          pts=pts, dir=[d[0], d[1]], hidden=False))
        sync_view_ids(self.doc)
        return vid

    def ensure_views_for_drafting(self):
        return self.geoms()

    # ------------------------------------------------------------ drafting
    def _full_autodraft(self):
        """Everything the auto-draft can add, tagged by category."""
        return categorize(autodraft(self.part, self.frame, self.doc["datums"], self.doc["part"]["type"],
                                    self.geoms(), self.doc["settings"], assembly=self.assembly))

    def autodraft(self):
        self.doc["annotations"] = apply_cats(self._full_autodraft(), auto_settings(self.doc["settings"]))

    def set_auto(self, switches):
        """Turn auto-draft categories on/off, keeping every other annotation and edit."""
        st = self.doc["settings"]
        old_on = auto_settings(st)
        new_on = {k: bool(switches.get(k, old_on[k])) for k in CATS}
        st["auto"] = new_on
        if new_on != old_on:
            self.doc["annotations"] = merge_cats(self.doc["annotations"], self._full_autodraft(), old_on, new_on)

    def _reset_views(self):
        """Orientation or body changed: every view's geometry is new."""
        self.doc["views"] = [new_view(v["type"]) for v in self.doc["views"] if v["type"] != "section"]
        self.doc["settings"]["scale"] = None
        sync_view_ids(self.doc)

    def reorient(self, which):
        X, Y, Z = self.frame
        neg = V.neg
        if which == "left":
            Y2, Z2 = X, Z
        elif which == "right":
            Y2, Z2 = neg(X), Z
        elif which == "rear":
            Y2, Z2 = neg(Y), Z
        elif which == "top":
            Y2, Z2 = neg(Z), Y
        elif which == "bottom":
            Y2, Z2 = Z, neg(Y)
        elif which == "rot_ccw":
            X2, Y2, Z2 = neg(Z), Y, X
        elif which == "rot_cw":
            X2, Y2, Z2 = Z, Y, neg(X)
        else:
            return
        if which not in ("rot_ccw", "rot_cw"):
            X2 = V.cross(Y2, Z2)
        self.doc["frame"] = {"X": list(X2), "Y": list(Y2), "Z": list(Z2)}
        self.doc["view_offsets"] = {}
        self._reset_views()
        self.autodraft()

    def set_datum(self, letter, feature_id):
        f = self.part.feature(feature_id)
        if f is None:
            raise ValueError("Unknown feature " + feature_id)
        kind = "plane" if hasattr(f, "normal") else "axis"
        direction = f.normal if kind == "plane" else f.axis
        ds = [d for d in self.doc["datums"] if d["letter"] != letter and d["feature"] != feature_id]
        if letter:
            ds.append(Datum(letter, feature_id, kind, direction).to_dict())
        ds.sort(key=lambda d: d["letter"])
        self.doc["datums"] = ds
        self.autodraft()

    def reset_auto(self):
        """Re-detect datums + orientation and regenerate everything."""
        ptype, datums = self._datums()
        frame = choose_frame(self.part, ptype, datums)
        self.doc["part"]["type"] = ptype
        self.doc["datums"] = [d.to_dict() for d in datums]
        self.doc["frame"] = {"X": list(frame[0]), "Y": list(frame[1]), "Z": list(frame[2])}
        self.doc["view_offsets"] = {}
        self._reset_views()
        self.autodraft()

    def add_for_feature(self, fid, what):
        """Add one annotation for a feature: what in
        datum:<L> | fcf:<characteristic> | callout. Added items count as the user's own."""
        anns = self.doc["annotations"]
        start = len(anns)
        try:
            return self._add_for_feature(fid, what)
        finally:
            for a in anns[start:]:
                a["auto"] = False

    def _pattern_callout(self, f):
        """The auto-draft's callout for f's pattern ('4X ⌀10 THRU'), or None."""
        dr = Drafter(self.part, self.frame, self.doc["datums"], self.doc["part"]["type"], self.geoms(),
                     self.doc["settings"])
        if f.kind == "radius":
            dr.radii()
        else:
            dr.holes_and_bosses()
        for a in dr.ann:
            if a["kind"] == "callout" and not a.get("pcd") and f.id in (a.get("members") or []):
                return a
        return None

    def _add_for_feature(self, fid, what):
        geoms = self.geoms()
        dr = Drafter(self.part, self.frame, self.doc["datums"], self.doc["part"]["type"], geoms, self.doc["settings"])
        f = self.part.feature(fid)
        if f is None:
            raise ValueError("Unknown feature")
        anns = self.doc["annotations"]
        callout = next((a for a in anns if a["kind"] == "callout" and fid in (a.get("members") or [a.get("feature")])), None)
        kind, _, arg = what.partition(":")
        letters = [d["letter"] for d in self.doc["datums"]]
        if hasattr(f, "normal"):          # plane
            got = dr.best_edge_view(f, dr.view_pref("front", "top", dr.side_view() or ""))
            if not got:
                raise ValueError("That face is not seen edge-on in any view")
            vn, ln, run = got
            if kind == "datum":
                dr.datum_symbol(arg or "D", f, vn, ln, run, 0.4)
            else:
                char = arg or "flatness"
                refs = [] if char in ("flatness", "straightness", "profile_surface", "profile_line") else \
                    [[l, ""] for l in letters if self._datum_feature(l) != fid][:1]
                dr.surface_fcf(f, vn, ln, run, 0.5, char, dr.tol["orient"] if refs else dr.tol["form"], refs)
        else:                             # cylinder
            if kind == "callout" or callout is None:
                before = len(dr.ann)
                pattern = self._pattern_callout(f)
                if pattern is not None:
                    dr.add(dict(pattern, id=new_id(), off=None, placed=False))
                elif f.kind == "radius":
                    raise ValueError("No view shows this radius as an arc")
                else:
                    view = dr.circle_view([f])
                    if not view:
                        raise ValueError("No view shows this feature as a circle")
                    vg = geoms[view]
                    c2 = vg.project(f.center)
                    anchor = [c2[0] + f.radius * 0.7071, c2[1] + f.radius * 0.7071]
                    tol = {"mode": "dev", "up": dr.tol["hole"], "lo": 0.0} if f.kind == "hole" else \
                        {"mode": "dev", "up": 0.0, "lo": -dr.tol["hole"]}
                    dr.add({"kind": "callout", "view": view, "anchor": anchor, "center": list(c2),
                            "lines": dr.callout_lines(f, 1), "size": 2 * f.radius, "tol": tol, "off": None,
                            "feature": f.id, "members": [f.id]})
                new = dr.ann[before:]
                callout = next((a for a in new if a["kind"] == "callout"), callout)
                if kind == "callout":
                    anns.extend(new)
                    return new
            if kind == "datum":
                dr.add({"kind": "datum", "view": callout["view"], "anchor": None, "dir": [0.0, -1.0],
                        "letter": arg or "D", "feature": fid, "len": None, "slide": 0.0, "attach": callout["id"]})
            else:
                char = arg or "position"
                refs = dr.position_refs(f) if char in ("position", "perpendicularity", "parallelism", "angularity",
                                                       "concentricity", "circular_runout", "total_runout", "symmetry") else []
                if char in ("perpendicularity", "parallelism", "angularity"):
                    refs = refs[:1]
                dr.add({"kind": "fcf", "view": callout["view"], "anchor": None, "attach": callout["id"],
                        "char": char, "tol": dr.tol["pos"] if char == "position" else dr.tol["orient"],
                        "dia": char in ("position", "perpendicularity", "concentricity"),
                        "mod": "M" if char == "position" else "", "datums": refs, "feature": fid, "off": None})
        anns.extend(dr.ann)
        return dr.ann

    # ------------------------------------------------------------ picked annotations
    def _cyls_in_view(self, vg):
        return [c for c in self.part.cyls if not c.absorbed]

    def _is_diameter(self, view, refs):
        """Two parallel lines that are the silhouettes of one cylinder."""
        vg = self.geoms().get(view)
        if vg is None or len(refs) != 2 or any(r.get("t") != "l" for r in refs):
            return False
        (a1, b1), (a2, b2) = [(r["a"], r["b"]) for r in refs]
        t = V.unit((b1[0] - a1[0], b1[1] - a1[1]))
        nrm = (-t[1], t[0])
        gap = abs((a2[0] - a1[0]) * nrm[0] + (a2[1] - a1[1]) * nrm[1])
        tol = max(self.part.size * 1e-5, 1e-4)
        for c in self._cyls_in_view(vg):
            if c.kind not in ("hole", "boss") or abs(V.dot(c.axis, vg.N)) > 1e-3:
                continue
            ax = V.unit(vg.project(c.axis)) if V.norm(vg.project(c.axis)) > 1e-9 else None
            if ax is None or abs(abs(ax[0] * t[0] + ax[1] * t[1]) - 1) > 1e-4:
                continue
            if abs(gap - 2 * c.radius) > tol * 10:
                continue
            q = vg.project(c.center)
            d1 = abs((q[0] - a1[0]) * nrm[0] + (q[1] - a1[1]) * nrm[1])
            d2 = abs((q[0] - a2[0]) * nrm[0] + (q[1] - a2[1]) * nrm[1])
            if abs(d1 - c.radius) < tol * 10 and abs(d2 - c.radius) < tol * 10:
                return True
        return False

    def add_dim(self, spec):
        kind = spec.get("kind")
        view = spec.get("view")
        if view not in self.doc["settings"]["views"]:
            raise ValueError("That view is no longer on the sheet.")
        refs = spec.get("refs") or []
        if kind == "ldim":
            if len(refs) != 2:
                raise ValueError("A dimension needs two picks.")
            a = {"kind": "ldim", "view": view, "refs": refs, "orient": spec.get("orient", "al"),
                 "off": float(spec.get("off", 10.0)), "shift": 0.0, "prefix": "", "text": "", "count": "",
                 "tol": {"mode": "none", "up": 0.1, "lo": -0.1}}
            if a["orient"] == "perp" and self._is_diameter(view, refs):
                a["prefix"] = "⌀"
        elif kind == "adim":
            if len(refs) != 2 or any(r.get("t") != "l" for r in refs):
                raise ValueError("An angle needs two straight edges.")
            a = {"kind": "adim", "view": view, "refs": refs, "pick": spec["pick"], "text": "",
                 "tol": {"mode": "none", "up": 0.5, "lo": -0.5}}
        else:
            raise ValueError("Unknown dimension type")
        a.update(id=new_id("d"), auto=False, placed=True)
        self.doc["annotations"].append(a)
        return a["id"]

    def add_callout(self, view, center, r, arc, anchor, off):
        """Leader callout for a picked circle or arc, pattern-aware for holes."""
        vg = self.geoms().get(view)
        if vg is None:
            raise ValueError("That view is no longer on the sheet.")
        tol = max(self.part.size * 1e-5, 1e-4) * 10
        match = None
        for c in self._cyls_in_view(vg):
            if abs(abs(V.dot(c.axis, vg.N)) - 1) > 1e-3:
                continue
            q = vg.project(c.center)
            if math.hypot(q[0] - center[0], q[1] - center[1]) > tol:
                continue
            radii = [c.radius] + ([c.cbore["radius"]] if c.cbore else []) + ([c.csink["diameter"] / 2] if c.csink else [])
            if any(abs(rr - r) < tol for rr in radii):
                match = c
                break
        lines, size, members = None, (r if arc else 2 * r), []
        if match is not None:
            pat = None
            try:
                pat = self._pattern_callout(match)
            except Exception:
                pat = None
            if pat is not None:
                lines, members = list(pat["lines"]), list(pat.get("members") or [])
            elif match.kind in ("hole", "boss"):
                dr = Drafter(self.part, self.frame, self.doc["datums"], self.doc["part"]["type"], self.geoms(),
                             self.doc["settings"])
                lines = dr.callout_lines(match, 1)
            size = match.radius if match.kind == "radius" else 2 * match.radius
            if match.kind == "radius" and not lines:
                lines = ["R{size}"]
        if not lines:
            lines = ["R{size}"] if arc else ["⌀{size}"]
        size = round(size, 4)
        a = {"id": new_id("c"), "kind": "callout", "view": view, "anchor": list(anchor), "center": list(center),
             "lines": lines, "size": size, "tol": {"mode": "none", "up": 0.1, "lo": -0.1}, "off": list(off),
             "feature": match.id if match is not None else None, "members": members, "auto": False, "placed": True}
        self.doc["annotations"].append(a)
        return a["id"]

    def _datum_feature(self, letter):
        for d in self.doc["datums"]:
            if d["letter"] == letter:
                return d["feature"]
        return None

    def add_note(self, x, y, text):
        a = {"id": new_id(), "kind": "note", "pos": [x, y], "lines": text.split("\n"), "h": self.doc["settings"].get("text_height", 3.5),
             "auto": False, "placed": True}
        self.doc["annotations"].append(a)
        return a

    # ------------------------------------------------------------ output
    def build(self):
        geoms = self.geoms()
        self.ensure_layout(geoms)
        autos = [a for a in self.doc["annotations"] if a["kind"] == "dim" and a.get("side") == "auto"
                 and a.get("view") in geoms]
        if autos:
            dr = Drafter(self.part, self.frame, self.doc["datums"], self.doc["part"]["type"], geoms, self.doc["settings"])
            for a in autos:
                pts = [(tuple(a["a"]), 0.0), (tuple(a["b"]), 0.0)]
                a["side"] = dr.choose_side(a["view"], a["axis"], lambda side, pts=pts: pts)
        lay = layout_views(self.doc, geoms)
        arrange(self.part, self.doc, geoms, lay)
        ctx = Ctx(self.part, self.doc, geoms, lay)
        cv, bbs = render(ctx)
        return ctx, cv, bbs

    def body_list(self):
        if len(self.bodies) < 2:
            return []
        out = [{"value": "all", "label": "All %d bodies (assembly, no GD&T)" % len(self.bodies)}]
        for i, vol, _ in self.bodies:
            out.append({"value": str(i), "label": "Body %d%s, %s cm³" % (i + 1, " (largest)" if i == 0 else "", fmt(vol / 1000.0, 1))})
        return out

    def features(self):
        out = []
        if self.assembly:
            return out
        dmap = {d["feature"]: d["letter"] for d in self.doc["datums"]}
        X, Y, Z = self.frame
        names = [(V.neg(Z), "Bottom"), (Z, "Top"), (V.neg(Y), "Front"), (Y, "Back"), (V.neg(X), "Left"), (X, "Right")]
        b = self.part.bbox
        corners = [(x, y, z) for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])]
        for p in self.part.planes:
            n = p.normal
            side = next((nm for d, nm in names if V.dot(d, n) > 1 - 1e-3), "Angled")
            lo = min(V.dot(c, n) for c in corners)
            hi = max(V.dot(c, n) for c in corners)
            where = "outer" if abs(p.offset - hi) < 1e-3 else "%s mm in" % _n(hi - p.offset)
            out.append({"id": p.id, "type": "plane", "label": "%s face" % side,
                        "detail": "%s mm², %s" % (fmt(p.area, 0), where),
                        "datum": dmap.get(p.id, "")})
        for c in self.part.cyls:
            if c.absorbed:
                continue
            if c.kind == "hole":
                lab = "Hole ⌀%s %s" % (_n(2 * c.radius), "THRU" if c.thru else "↧" + _n(c.length))
                if c.cbore:
                    lab += " ⌴⌀%s" % _n(2 * c.cbore["radius"])
            elif c.kind == "boss":
                lab = "Diameter ⌀%s" % _n(2 * c.radius)
            else:
                lab = "Radius R%s" % _n(c.radius)
            ctr = c.center
            out.append({"id": c.id, "type": c.kind, "label": lab,
                        "detail": "at %s, %s, %s" % tuple(_n(x) for x in ctr),
                        "datum": dmap.get(c.id, "")})
        return out


def _n(v):
    from .document import fmt
    return fmt(v, 2)
