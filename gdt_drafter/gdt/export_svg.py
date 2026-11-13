"""SVG writer for canvas primitives."""
import math
from xml.sax.saxutils import escape, quoteattr

from .fonts import font_size

DASH = {"hidden": "3 1.5", "center": "9 1.5 1.5 1.5"}


def _n(v):
    s = "%.3f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def to_svg(cv, W, H, editor=False, background="#ffffff"):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" viewBox="0 0 %s %s" '
           'font-family="Helvetica, Arial, sans-serif">' % (_n(W), _n(H), _n(W), _n(H))]
    if background:
        out.append('<rect x="0" y="0" width="%s" height="%s" fill="%s"/>' % (_n(W), _n(H), background))
    out.append('<g stroke="#000" fill="none" stroke-linecap="round" stroke-linejoin="round">')
    Y = lambda y: H - y
    cur = None
    for it in cv.items:
        g = it.get("g")
        if g != cur:
            if cur is not None:
                out.append("</g>")
            if g is not None:
                out.append('<g class=%s data-id=%s>' % (quoteattr("k-" + str(it.get("gk", ""))), quoteattr(g)))
            cur = g
        t = it["t"]
        if t == "hitpoly":
            if editor:
                out.append('<polygon class="hit" points="%s" fill="transparent" stroke="none"/>'
                           % " ".join("%s,%s" % (_n(p[0]), _n(Y(p[1]))) for p in it["pts"]))
            continue
        if t == "hit":
            if editor:
                out.append('<rect class="hit" x="%s" y="%s" width="%s" height="%s" fill="transparent" stroke="none"/>'
                           % (_n(it["x0"]), _n(Y(it["y1"])), _n(it["x1"] - it["x0"]), _n(it["y1"] - it["y0"])))
            continue
        out.append(_item(it, Y))
    if cur is not None:
        out.append("</g>")
    out.append("</g></svg>")
    return "\n".join(out)


def _stroke(it):
    s = ' stroke-width="%s"' % _n(it.get("w", 0.25))
    d = DASH.get(it.get("dash"))
    if d:
        s += ' stroke-dasharray="%s"' % d
    return s


def _fill(it):
    f = it.get("fill")
    if f == "white":
        return ' fill="#fff" stroke="none"'
    if f:
        return ' fill="#000" stroke="none"'
    return ""


def _item(it, Y):
    t = it["t"]
    if t == "line":
        a, b = it["a"], it["b"]
        return '<line x1="%s" y1="%s" x2="%s" y2="%s"%s/>' % (_n(a[0]), _n(Y(a[1])), _n(b[0]), _n(Y(b[1])), _stroke(it))
    if t == "poly":
        pts = " ".join("%s,%s" % (_n(p[0]), _n(Y(p[1]))) for p in it["pts"])
        tag = "polygon" if it.get("closed") else "polyline"
        return '<%s points="%s"%s%s/>' % (tag, pts, _stroke(it) if not it.get("fill") else "", _fill(it))
    if t == "circle":
        c = it["c"]
        return '<circle cx="%s" cy="%s" r="%s"%s%s/>' % (_n(c[0]), _n(Y(c[1])), _n(it["r"]),
                                                         _stroke(it) if not it.get("fill") else "", _fill(it))
    if t == "arc":
        c, r = it["c"], it["r"]
        a0, a1 = math.radians(it["a0"]), math.radians(it["a1"])
        span = (it["a1"] - it["a0"]) % 360.0
        x0, y0 = c[0] + r * math.cos(a0), c[1] + r * math.sin(a0)
        x1, y1 = c[0] + r * math.cos(a1), c[1] + r * math.sin(a1)
        large = 1 if span > 180 else 0
        return '<path d="M%s %s A%s %s 0 %d 0 %s %s"%s/>' % (_n(x0), _n(Y(y0)), _n(r), _n(r), large, _n(x1), _n(Y(y1)), _stroke(it))
    if t == "rect":
        s = ""
        if it.get("fill"):
            s += '<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (
                _n(it["x0"]), _n(Y(it["y1"])), _n(it["x1"] - it["x0"]), _n(it["y1"] - it["y0"]), _fill(it))
        if it.get("stroke", True):
            s += '<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (
                _n(it["x0"]), _n(Y(it["y1"])), _n(it["x1"] - it["x0"]), _n(it["y1"] - it["y0"]), _stroke(it))
        return s
    if t == "text":
        x, y = it["p"]
        anchor = {"start": "start", "middle": "middle", "end": "end"}[it.get("anchor", "start")]
        rot = it.get("rot") or 0
        tr = ' transform="rotate(%s %s %s)"' % (_n(-rot), _n(x), _n(Y(y))) if rot else ""
        return '<text x="%s" y="%s" font-size="%s" text-anchor="%s" fill="#000" stroke="none" xml:space="preserve"%s>%s</text>' % (
            _n(x), _n(Y(y)), _n(font_size(it["h"])), anchor, tr, escape(it["s"]))
    return ""
