"""Device-independent drawing primitives in sheet millimetres (origin bottom-left, y up).

The same primitive list feeds the SVG, PDF and DXF writers, so the three
outputs always match.
"""
import math

from .fonts import text_width

# line weights (mm) and layers
THICK = 0.5
THIN = 0.25
HIDDEN_W = 0.3
TEXT_STROKE = 0.25


class Canvas:
    def __init__(self):
        self.items = []
        self._group = None
        self._kind = None

    # -- grouping (used by the editor to pick annotations)
    def begin(self, gid, kind):
        self._group, self._kind = gid, kind

    def end(self):
        self._group, self._kind = None, None

    def _add(self, item):
        if self._group is not None:
            item["g"] = self._group
            item["gk"] = self._kind
        self.items.append(item)
        return item

    # -- primitives
    def line(self, a, b, w=THIN, dash=None, layer="THIN"):
        return self._add({"t": "line", "a": [a[0], a[1]], "b": [b[0], b[1]], "w": w, "dash": dash, "layer": layer})

    def poly(self, pts, w=THIN, closed=False, fill=False, dash=None, layer="THIN"):
        return self._add({"t": "poly", "pts": [[p[0], p[1]] for p in pts], "w": w, "closed": closed,
                          "fill": fill, "dash": dash, "layer": layer})

    def circle(self, c, r, w=THIN, fill=False, dash=None, layer="THIN"):
        return self._add({"t": "circle", "c": [c[0], c[1]], "r": r, "w": w, "fill": fill, "dash": dash, "layer": layer})

    def arc(self, c, r, a0, a1, w=THIN, dash=None, layer="THIN"):
        """Counter-clockwise arc from a0 to a1 (degrees)."""
        return self._add({"t": "arc", "c": [c[0], c[1]], "r": r, "a0": a0, "a1": a1, "w": w, "dash": dash, "layer": layer})

    def rect(self, x0, y0, x1, y1, w=THIN, fill=None, stroke=True, layer="THIN"):
        return self._add({"t": "rect", "x0": min(x0, x1), "y0": min(y0, y1), "x1": max(x0, x1), "y1": max(y0, y1),
                          "w": w, "fill": fill, "stroke": stroke, "layer": layer})

    def text(self, p, s, h, anchor="start", rot=0.0, layer="TEXT"):
        if not s:
            return None
        return self._add({"t": "text", "p": [p[0], p[1]], "s": s, "h": h, "anchor": anchor, "rot": rot, "layer": layer})

    def hit(self, x0, y0, x1, y1):
        """Invisible pick rectangle for the editor (ignored by PDF/DXF)."""
        return self._add({"t": "hit", "x0": x0, "y0": y0, "x1": x1, "y1": y1})

    def hitpoly(self, pts):
        """Invisible pick polygon for the editor (ignored by PDF/DXF)."""
        return self._add({"t": "hitpoly", "pts": [[p[0], p[1]] for p in pts]})

    # -- helpers
    def arrow(self, tip, frm, size=3.0, layer="DIM"):
        """Filled arrowhead with its tip at `tip`, pointing away from `frm`."""
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        bx, by = tip[0] - ux * size, tip[1] - uy * size
        hw = size * 0.18
        return self.poly([tip, (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)],
                         w=0.01, closed=True, fill=True, layer=layer)

    def bounds(self, group=None):
        xs, ys = [], []
        for it in self.items:
            if group is not None and it.get("g") != group:
                continue
            for x, y in item_points(it):
                xs.append(x)
                ys.append(y)
        if not xs:
            return None
        return [min(xs), min(ys), max(xs), max(ys)]


def item_points(it):
    t = it["t"]
    if t == "line":
        return [it["a"], it["b"]]
    if t == "poly":
        return it["pts"]
    if t in ("circle", "arc"):
        c, r = it["c"], it["r"]
        return [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
    if t in ("rect", "hit"):
        return [(it["x0"], it["y0"]), (it["x1"], it["y1"])]
    if t == "hitpoly":
        return []
    if t == "text":
        w = text_width(it["s"], it["h"])
        x, y = it["p"]
        if it["anchor"] == "middle":
            x0 = x - w / 2
        elif it["anchor"] == "end":
            x0 = x - w
        else:
            x0 = x
        pts = [(x0, y - it["h"] * 0.25), (x0 + w, y + it["h"] * 1.05)]
        if it.get("rot"):
            a = math.radians(it["rot"])
            ca, sa = math.cos(a), math.sin(a)
            out = []
            for px, py in [(pts[0][0], pts[0][1]), (pts[1][0], pts[0][1]), (pts[1][0], pts[1][1]), (pts[0][0], pts[1][1])]:
                rx, ry = px - x, py - y
                out.append((x + rx * ca - ry * sa, y + rx * sa + ry * ca))
            return out
        return pts
    return []
