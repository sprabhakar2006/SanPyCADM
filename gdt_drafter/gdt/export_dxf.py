"""DXF (AutoCAD R2010) writer for canvas primitives, via ezdxf."""
import io
import math

LAYERS = {
    "VISIBLE": dict(color=7, lineweight=50, linetype="Continuous"),
    "HIDDEN": dict(color=1, lineweight=30, linetype="DASHED"),
    "TANGENT": dict(color=8, lineweight=18, linetype="Continuous"),
    "CENTER": dict(color=4, lineweight=25, linetype="CENTER"),
    "DIM": dict(color=3, lineweight=25, linetype="Continuous"),
    "GDT": dict(color=6, lineweight=25, linetype="Continuous"),
    "TEXT": dict(color=7, lineweight=25, linetype="Continuous"),
    "BORDER": dict(color=7, lineweight=50, linetype="Continuous"),
    "HATCH": dict(color=8, lineweight=18, linetype="Continuous"),
    "CUT": dict(color=4, lineweight=25, linetype="CENTER"),
    "THIN": dict(color=7, lineweight=25, linetype="Continuous"),
}


def to_dxf(cv, W, H):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4        # millimetres
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 0.3
    for name, a in LAYERS.items():
        if name not in doc.layers:
            lt = a["linetype"] if a["linetype"] in doc.linetypes else "Continuous"
            doc.layers.add(name, color=a["color"], linetype=lt, lineweight=a["lineweight"])
    if "GDT" not in doc.styles:
        doc.styles.add("GDT", font="arial.ttf")
    msp = doc.modelspace()

    def attrs(it):
        layer = it.get("layer", "THIN")
        if layer not in LAYERS:
            layer = "THIN"
        d = {"layer": layer}
        if it.get("dash") == "hidden":
            d["linetype"] = "DASHED"
        elif it.get("dash") == "center":
            d["linetype"] = "CENTER"
        w = it.get("w")
        if w:
            lw = int(round(w * 100))
            for std in (13, 18, 25, 30, 35, 50, 70):
                if lw <= std:
                    lw = std
                    break
            d["lineweight"] = lw
        return d

    for it in cv.items:
        t = it["t"]
        if t in ("hit", "hitpoly"):
            continue
        if t == "line":
            msp.add_line(it["a"], it["b"], dxfattribs=attrs(it))
        elif t == "poly":
            if it.get("fill") == "white":
                continue
            if it.get("fill") and len(it["pts"]) in (3, 4):
                pts = [tuple(p) for p in it["pts"]]
                if len(pts) == 4:
                    pts = [pts[0], pts[1], pts[3], pts[2]]
                msp.add_solid(pts, dxfattribs={"layer": attrs(it)["layer"]})
            else:
                msp.add_lwpolyline([tuple(p) for p in it["pts"]], close=bool(it.get("closed")), dxfattribs=attrs(it))
        elif t == "circle":
            msp.add_circle(it["c"], it["r"], dxfattribs=attrs(it))
        elif t == "arc":
            msp.add_arc(it["c"], it["r"], it["a0"], it["a1"], dxfattribs=attrs(it))
        elif t == "rect":
            if it.get("stroke", True):
                x0, y0, x1, y1 = it["x0"], it["y0"], it["x1"], it["y1"]
                msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs=attrs(it))
        elif t == "text":
            align = {"start": TextEntityAlignment.LEFT, "middle": TextEntityAlignment.CENTER,
                     "end": TextEntityAlignment.RIGHT}[it.get("anchor", "start")]
            e = msp.add_text(it["s"].replace("±", "%%p").replace("°", "%%d"),
                             dxfattribs={"layer": attrs(it)["layer"], "height": it["h"],
                                         "rotation": it.get("rot") or 0.0, "style": "GDT"})
            e.set_placement(tuple(it["p"]), align=align)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
