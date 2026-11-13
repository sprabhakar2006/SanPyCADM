"""Automatic placement: dimension tiers, view gutters, view positions and a
collision-avoiding label placer for leader callouts and feature control frames."""
import math

from . import vec as V
from .autocats import auto_settings
from .canvas import Canvas
from .drafting import side_of
from .layout import DIM_GAP0, DIM_STEP, place_views
from .render import (BOX, Ctx, callout_block, draw_annotation, fcf_size)


def _dim_len(a):
    k = 0 if a["axis"] == "h" else 1
    return abs(a["b"][k] - a["a"][k])


def assign_tiers(doc):
    groups = {}
    for a in doc["annotations"]:
        if a["kind"] == "dim" and a.get("side") != "at":
            groups.setdefault((a["view"], a["side"]), []).append(a)
    for key, dims in groups.items():
        fixed = [a for a in dims if a.get("placed")]
        free = sorted([a for a in dims if not a.get("placed")], key=_dim_len)
        for i, a in enumerate(free):
            a["tier"] = i
            a["gap"] = None
        for a in fixed:
            if a.get("gap") is None:
                a["gap"] = DIM_GAP0 + DIM_STEP * a.get("tier", 0)


def dim_extent(a):
    g = a.get("gap")
    if g is None:
        g = DIM_GAP0 + DIM_STEP * a.get("tier", 0)
    return g + 6.0


HAND_DIM_RESERVE = DIM_GAP0 + DIM_STEP + 6.0     # two tiers of hand-placed dimensions


def compute_gutters(doc, h):
    gut = {}
    if not auto_settings(doc["settings"])["dims"]:
        for v in doc["settings"]["views"]:
            if v != "iso":
                gut[v] = {k: HAND_DIM_RESERVE for k in ("top", "bottom", "left", "right")}
    for a in doc["annotations"]:
        v = a.get("view")
        if not v:
            continue
        g = gut.setdefault(v, {"top": 4.0, "bottom": 4.0, "left": 4.0, "right": 4.0})
        if a["kind"] == "dim" and a.get("side") in g:
            g[a["side"]] = max(g[a["side"]], dim_extent(a))
    # datum symbols sit beyond the dimensions on their side
    for a in doc["annotations"]:
        if a["kind"] != "datum" or a.get("attach") or not a.get("view"):
            continue
        g = gut.setdefault(a["view"], {"top": 4.0, "bottom": 4.0, "left": 4.0, "right": 4.0})
        side = side_of(a.get("dir") or [0, -1])
        if not a.get("placed"):
            dims_here = [d for d in doc["annotations"] if d["kind"] == "dim" and d["view"] == a["view"]
                         and d.get("side") == side]
            a["len"] = (max(dim_extent(d) for d in dims_here) - 2.0) if dims_here else 4.0
        g[side] = max(g[side], (a.get("len") or 4.0) + 3.6 + BOX + 2.0)
    return gut


# ------------------------------------------------------------------ labels

def _overlap(r, s, pad=0.8):
    return not (r[2] + pad <= s[0] or s[2] + pad <= r[0] or r[3] + pad <= s[1] or s[3] + pad <= r[1])


def _seg_hits_rect(p, q, r):
    # Liang-Barsky clip test
    x0, y0, x1, y1 = r
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def place_label(P, block, pref_ang, obstacles, labels, region, view_rect, center=None):
    """block = (W, above, below): text block size around the knee point K.
    Returns the knee offset (dx, dy) from P."""
    W, above, below = block
    best = None
    offsets = [0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90, 120, -120, 150, -150, 180]
    for dist in [6 + 4 * i for i in range(40)]:
        for da in offsets:
            ang = pref_ang + math.radians(da)
            K = (P[0] + dist * math.cos(ang), P[1] + dist * math.sin(ang))
            right = math.cos(ang) >= -1e-6
            rect = ([K[0], K[1] - below, K[0] + W + 1, K[1] + above] if right
                    else [K[0] - W - 1, K[1] - below, K[0], K[1] + above])
            if rect[0] < region[0] or rect[1] < region[1] or rect[2] > region[2] or rect[3] > region[3]:
                continue
            if _overlap(rect, view_rect, 1.5):
                continue
            if any(_overlap(rect, o) for o in obstacles):
                continue
            score = dist + abs(da) * 0.25
            deg = math.degrees(ang) % 90
            if deg < 10 or deg > 80:
                score += 6
            if any(_seg_hits_rect(P, K, o) for o in labels):
                score += 40
            if best is None or score < best[0]:
                best = (score, K)
        if best is not None and best[0] < dist:
            break
    if best is None:
        K = (P[0] + 15 * math.cos(pref_ang), P[1] + 15 * math.sin(pref_ang))
    else:
        K = best[1]
    return [K[0] - P[0], K[1] - P[1]]


def arrange(part, doc, geoms, lay):
    """Stack auto dimensions in tiers and place labels that have no position yet."""
    assign_tiers(doc)
    ctx = Ctx(part, doc, geoms, lay)
    W_, H_ = lay.W, lay.H
    region = (lay.border[0] + 2, lay.border[1] + 2, lay.border[2] - 2, lay.border[3] - 2)

    obstacles = [list(lay.tb), list(lay.notes)]
    labelled = {v["id"] for v in doc.get("views", []) if v.get("label")}
    for name, v in lay.views.items():
        r = v["rect"]
        below = 11.0 if name in labelled else 1.0       # labelled views carry a caption
        obstacles.append([r[0] - 1, r[1] - below, r[2] + 1, r[3] + 1])
    labels = []

    # fixed things first: dimensions, datum symbols, already-placed labels
    tmp = Canvas()
    for a in doc["annotations"]:
        if a.get("view") not in lay.views or a.get("attach"):
            continue
        is_free = a["kind"] in ("callout", "fcf") and not a.get("placed")
        if is_free:
            continue
        bb = draw_annotation(tmp, ctx, a)
        if bb:
            obstacles.append(bb)
            if a["kind"] in ("callout", "fcf", "datum"):
                labels.append(bb)

    free = [a for a in doc["annotations"] if a["kind"] in ("callout", "fcf") and not a.get("attach")
            and not a.get("placed") and a.get("view") in lay.views]
    # outer items first so inner leaders can find room
    for a in free:
        view = a["view"]
        vr = lay.views[view]["rect"]
        P = ctx.P(view, a["anchor"])
        vc = ((vr[0] + vr[2]) / 2, (vr[1] + vr[3]) / 2)
        if a["kind"] == "callout":
            lines, W, above, below = callout_block(ctx, a)
            block = (W, above, below)
            if a.get("center"):
                C = ctx.P(view, a["center"])
                d = (P[0] - C[0], P[1] - C[1])
                if math.hypot(*d) < 1e-6:
                    d = (P[0] - vc[0], P[1] - vc[1])
            else:
                d = (P[0] - vc[0], P[1] - vc[1])
        else:
            fw, fh = fcf_size(ctx, a)
            block = (fw, fh / 2, fh / 2)
            d = tuple(a.get("dir") or (P[0] - vc[0], P[1] - vc[1]))
        pref = math.atan2(d[1], d[0]) if math.hypot(*d) > 1e-9 else math.pi / 4
        a["off"] = place_label(P, block, pref, obstacles, labels, region, vr)
        bb = draw_annotation(tmp, ctx, a)
        if bb:
            labels.append(bb)
            obstacles.append(bb)
    return lay
