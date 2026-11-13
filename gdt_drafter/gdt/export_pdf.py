"""Minimal vector PDF writer for canvas primitives (no third-party deps).

Units: the page content is scaled so 1 unit = 1 mm. Text uses the built-in
Helvetica font with WinAnsi encoding; GD&T symbols are geometry.
"""
import math
import zlib

from .fonts import font_size, text_width

MM = 72.0 / 25.4
DASH = {"hidden": "[3 1.5] 0 d", "center": "[9 1.5 1.5 1.5] 0 d"}


def _n(v):
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _esc(s):
    b = s.encode("cp1252", errors="replace")
    out = []
    for ch in b:
        c = chr(ch)
        if c in "()\\":
            out.append("\\" + c)
        elif ch < 32 or ch > 126:
            out.append("\\%03o" % ch)
        else:
            out.append(c)
    return "".join(out)


def _arc_beziers(cx, cy, r, a0, a1):
    """Cubic Bezier segments approximating a ccw arc (degrees)."""
    span = (a1 - a0) % 360.0
    if span < 1e-9:
        span = 360.0
    n = max(1, int(math.ceil(span / 90.0)))
    d = math.radians(span / n)
    k = 4.0 / 3.0 * math.tan(d / 4)
    segs = []
    a = math.radians(a0)
    for _ in range(n):
        b = a + d
        p0 = (cx + r * math.cos(a), cy + r * math.sin(a))
        p3 = (cx + r * math.cos(b), cy + r * math.sin(b))
        p1 = (p0[0] - k * r * math.sin(a), p0[1] + k * r * math.cos(a))
        p2 = (p3[0] + k * r * math.sin(b), p3[1] - k * r * math.cos(b))
        segs.append((p0, p1, p2, p3))
        a = b
    return segs


def _stroke_state(it, ops, state):
    w = it.get("w", 0.25)
    dash = it.get("dash")
    if state.get("w") != w:
        ops.append("%s w" % _n(w))
        state["w"] = w
    if state.get("dash") != dash:
        ops.append(DASH.get(dash, "[] 0 d"))
        state["dash"] = dash


def _fill_color(it, ops, state):
    col = "1 g" if it.get("fill") == "white" else "0 g"
    if state.get("fill") != col:
        ops.append(col)
        state["fill"] = col


def content_stream(cv, H):
    ops = ["%s 0 0 %s 0 0 cm" % (_n(MM), _n(MM)), "1 J 1 j 0 G 0 g"]
    state = {}
    for it in cv.items:
        t = it["t"]
        if t in ("hit", "hitpoly"):
            continue
        if t == "line":
            _stroke_state(it, ops, state)
            a, b = it["a"], it["b"]
            ops.append("%s %s m %s %s l S" % (_n(a[0]), _n(a[1]), _n(b[0]), _n(b[1])))
        elif t == "poly":
            pts = it["pts"]
            if len(pts) < 2:
                continue
            path = "%s %s m " % (_n(pts[0][0]), _n(pts[0][1])) + " ".join("%s %s l" % (_n(x), _n(y)) for x, y in pts[1:])
            if it.get("fill"):
                _fill_color(it, ops, state)
                ops.append(path + " h f")
            else:
                _stroke_state(it, ops, state)
                ops.append(path + (" h S" if it.get("closed") else " S"))
        elif t in ("circle", "arc"):
            c, r = it["c"], it["r"]
            a0, a1 = (0.0, 360.0) if t == "circle" else (it["a0"], it["a1"])
            segs = _arc_beziers(c[0], c[1], r, a0, a1)
            path = "%s %s m " % (_n(segs[0][0][0]), _n(segs[0][0][1]))
            path += " ".join("%s %s %s %s %s %s c" % (_n(p1[0]), _n(p1[1]), _n(p2[0]), _n(p2[1]), _n(p3[0]), _n(p3[1]))
                             for _, p1, p2, p3 in segs)
            if t == "circle" and it.get("fill"):
                _fill_color(it, ops, state)
                ops.append(path + " h f")
            else:
                _stroke_state(it, ops, state)
                ops.append(path + (" h S" if t == "circle" else " S"))
        elif t == "rect":
            x0, y0, x1, y1 = it["x0"], it["y0"], it["x1"], it["y1"]
            re = "%s %s %s %s re" % (_n(x0), _n(y0), _n(x1 - x0), _n(y1 - y0))
            if it.get("fill"):
                _fill_color(it, ops, state)
                ops.append(re + " f")
            if it.get("stroke", True):
                _stroke_state(it, ops, state)
                ops.append(re + " S")
        elif t == "text":
            s = it["s"]
            h = it["h"]
            fs = font_size(h)
            x, y = it["p"]
            w = text_width(s, h)
            dx = {"start": 0.0, "middle": -w / 2, "end": -w}[it.get("anchor", "start")]
            a = math.radians(it.get("rot") or 0.0)
            ca, sa = math.cos(a), math.sin(a)
            tx, ty = x + dx * ca, y + dx * sa
            if state.get("fill") != "0 g":
                ops.append("0 g")
                state["fill"] = "0 g"
            ops.append("BT /F1 %s Tf %s %s %s %s %s %s Tm (%s) Tj ET" % (
                _n(fs), _n(ca), _n(sa), _n(-sa), _n(ca), _n(tx), _n(ty), _esc(s)))
    return "\n".join(ops).encode("latin-1")


def to_pdf(cv, W, H, title="Drawing"):
    stream = zlib.compress(content_stream(cv, H))
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << /Font << /F1 4 0 R >> >> "
                 "/Contents 5 0 R >>" % (_n(W * MM), _n(H * MM))).encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(("<< /Title (%s) /Producer (GD&T Drafter) >>" % _esc(title)).encode("latin-1"))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, len(objs), xref)
    return bytes(out)
