"""GD&T and dimensioning symbols drawn as geometry (no special fonts needed),
plus 'rich text' runs that mix plain text, symbols, stacked tolerances and boxes.
"""
import math

from .canvas import TEXT_STROKE
from .fonts import text_width

# characteristic name -> (label for UI, needs datum?, tolerance zone may be diametral?)
CHARACTERISTICS = {
    "straightness": ("Straightness", False, True),
    "flatness": ("Flatness", False, False),
    "circularity": ("Circularity", False, False),
    "cylindricity": ("Cylindricity", False, False),
    "profile_line": ("Profile of a line", None, False),
    "profile_surface": ("Profile of a surface", None, False),
    "parallelism": ("Parallelism", True, True),
    "perpendicularity": ("Perpendicularity", True, True),
    "angularity": ("Angularity", True, True),
    "position": ("Position", True, True),
    "concentricity": ("Concentricity / coaxiality", True, True),
    "symmetry": ("Symmetry", True, False),
    "circular_runout": ("Circular runout", True, False),
    "total_runout": ("Total runout", True, False),
}

# glyph widths as a fraction of cap height
SYM_W = {"dia": 0.95, "depth": 0.8, "cbore": 0.95, "csink": 0.95, "sq": 0.9, "deg": 0.45}


def _arrowhead(cv, tip, frm, size, layer):
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    hw = size * 0.35
    cv.poly([tip, (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)], w=0.01, closed=True, fill=True, layer=layer)


def draw_symbol(cv, name, x, y, h, layer="TEXT"):
    """Draw symbol `name` in an h x h box whose bottom-left is (x, y). Returns width."""
    w = TEXT_STROKE
    P = lambda a, b: (x + a * h, y + b * h)
    L = lambda a, b, c, d: cv.line(P(a, b), P(c, d), w=w, layer=layer)
    if name == "straightness":
        L(0.05, 0.5, 0.95, 0.5)
    elif name == "flatness":
        cv.poly([P(0.05, 0.22), P(0.62, 0.22), P(0.95, 0.78), P(0.38, 0.78)], w=w, closed=True, layer=layer)
    elif name == "circularity":
        cv.circle(P(0.5, 0.5), 0.42 * h, w=w, layer=layer)
    elif name == "cylindricity":
        cv.circle(P(0.5, 0.5), 0.32 * h, w=w, layer=layer)
        a = math.radians(62)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        for s in (-1, 1):
            cx, cy = 0.5 + s * px * 0.32, 0.5 + s * py * 0.32
            L(cx - dx * 0.55, cy - dy * 0.55, cx + dx * 0.55, cy + dy * 0.55)
    elif name in ("profile_line", "profile_surface"):
        cv.arc(P(0.5, 0.22), 0.42 * h, 0, 180, w=w, layer=layer)
        if name == "profile_surface":
            L(0.08, 0.22, 0.92, 0.22)
    elif name == "parallelism":
        L(0.12, 0.05, 0.52, 0.95)
        L(0.48, 0.05, 0.88, 0.95)
    elif name == "perpendicularity":
        L(0.05, 0.05, 0.95, 0.05)
        L(0.5, 0.05, 0.5, 0.95)
    elif name == "angularity":
        L(0.05, 0.05, 0.95, 0.05)
        L(0.05, 0.05, 0.82, 0.7)
    elif name == "position":
        cv.circle(P(0.5, 0.5), 0.3 * h, w=w, layer=layer)
        L(0.05, 0.5, 0.95, 0.5)
        L(0.5, 0.05, 0.5, 0.95)
    elif name == "concentricity":
        cv.circle(P(0.5, 0.5), 0.42 * h, w=w, layer=layer)
        cv.circle(P(0.5, 0.5), 0.22 * h, w=w, layer=layer)
    elif name == "symmetry":
        L(0.05, 0.5, 0.95, 0.5)
        L(0.25, 0.8, 0.75, 0.8)
        L(0.25, 0.2, 0.75, 0.2)
    elif name == "circular_runout":
        L(0.2, 0.05, 0.72, 0.9)
        _arrowhead(cv, P(0.78, 1.0), P(0.2, 0.05), 0.42 * h, layer)
    elif name == "total_runout":
        L(0.05, 0.05, 0.55, 0.05)
        L(0.05, 0.05, 0.4, 0.82)
        L(0.45, 0.05, 0.8, 0.82)
        _arrowhead(cv, P(0.45, 1.0), P(0.05, 0.05), 0.38 * h, layer)
        _arrowhead(cv, P(0.85, 1.0), P(0.45, 0.05), 0.38 * h, layer)
    elif name == "dia":
        cv.circle(P(0.47, 0.5), 0.36 * h, w=w, layer=layer)
        L(0.08, 0.02, 0.86, 0.98)
        return SYM_W["dia"] * h
    elif name == "depth":
        L(0.4, 1.0, 0.4, 0.02)
        L(0.05, 0.0, 0.75, 0.0)
        L(0.4, 0.02, 0.18, 0.38)
        L(0.4, 0.02, 0.62, 0.38)
        return SYM_W["depth"] * h
    elif name == "cbore":
        cv.poly([P(0.08, 0.9), P(0.08, 0.08), P(0.87, 0.08), P(0.87, 0.9)], w=w, layer=layer)
        return SYM_W["cbore"] * h
    elif name == "csink":
        cv.poly([P(0.05, 0.9), P(0.475, 0.06), P(0.9, 0.9)], w=w, layer=layer)
        return SYM_W["csink"] * h
    elif name == "sq":
        cv.rect(x + 0.1 * h, y, x + 0.85 * h, y + 0.75 * h, w=w, layer=layer)
        return SYM_W["sq"] * h
    return h


# ------------------------------------------------------------ rich text

SPECIAL = {"⌀": ("sym", "dia"), "Ø": ("sym", "dia"), "↧": ("sym", "depth"), "⌴": ("sym", "cbore"),
           "⌵": ("sym", "csink"), "□": ("sym", "sq"), "Ⓜ": ("circ", "M"), "Ⓛ": ("circ", "L"),
           "Ⓕ": ("circ", "F"), "Ⓟ": ("circ", "P"), "Ⓢ": ("circ", "S"), "Ⓣ": ("circ", "T"), "Ⓤ": ("circ", "U")}


def parse(s):
    """Turn a user string with ⌀ ↧ ⌴ ⌵ Ⓜ … into runs."""
    runs, buf = [], ""
    for ch in s or "":
        if ch in SPECIAL:
            if buf:
                runs.append(("t", buf))
                buf = ""
            runs.append(SPECIAL[ch])
        else:
            buf += ch
    if buf:
        runs.append(("t", buf))
    return runs


def run_width(run, h):
    k = run[0]
    if k == "t":
        return text_width(run[1], h)
    if k == "sym":
        return SYM_W.get(run[1], 1.0) * h + 0.15 * h
    if k == "gdt":
        return 1.0 * h
    if k == "circ":
        return 1.25 * h
    if k == "tol":
        return max(text_width(run[1], h * 0.7), text_width(run[2], h * 0.7)) + 0.55 * h
    if k == "box":
        return runs_width(run[1], h) + 0.9 * h
    return 0.0


def runs_width(runs, h):
    return sum(run_width(r, h) for r in runs)


def runs_height(runs, h):
    """(below baseline, above baseline) extents."""
    lo, hi = 0.25 * h, 1.05 * h
    for r in runs:
        if r[0] == "box":
            lo, hi = max(lo, 0.45 * h), max(hi, 1.45 * h)
        if r[0] == "tol":
            lo, hi = max(lo, 0.25 * h), max(hi, 1.25 * h)
        if r[0] == "circ":
            lo, hi = max(lo, 0.3 * h), max(hi, 1.2 * h)
    return lo, hi


def draw_runs(cv, runs, x, y, h, anchor="start", layer="TEXT"):
    """Draw runs with baseline at y. Returns (x0, x1) actually used."""
    W = runs_width(runs, h)
    if anchor == "middle":
        x -= W / 2
    elif anchor == "end":
        x -= W
    x0 = x
    for r in runs:
        k = r[0]
        if k == "t":
            cv.text((x, y), r[1], h, layer=layer)
        elif k == "sym":
            draw_symbol(cv, r[1], x + 0.05 * h, y, h, layer=layer)
        elif k == "gdt":
            draw_symbol(cv, r[1], x, y, h, layer=layer)
        elif k == "circ":
            cv.circle((x + 0.62 * h, y + 0.45 * h), 0.6 * h, w=TEXT_STROKE, layer=layer)
            cv.text((x + 0.62 * h, y + 0.45 * h - 0.33 * h), r[1], h * 0.66, anchor="middle", layer=layer)
        elif k == "tol":
            sh = h * 0.7
            cv.text((x + 0.25 * h, y + 0.55 * h), r[1], sh, layer=layer)
            cv.text((x + 0.25 * h, y - 0.1 * h), r[2], sh, layer=layer)
        elif k == "box":
            iw = runs_width(r[1], h)
            cv.rect(x + 0.1 * h, y - 0.4 * h, x + iw + 0.8 * h, y + 1.4 * h, w=TEXT_STROKE, layer=layer)
            draw_runs(cv, r[1], x + 0.45 * h, y, h, layer=layer)
        x += run_width(r, h)
    return x0, x0 + W
