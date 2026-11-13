"""Which kinds of annotation the auto-draft adds.

Every auto annotation is tagged with the categories it needs:
  dims      linear, location, diameter, PCD and angle dimensions
  callouts  hole and radius size callouts ("4X ⌀10 THRU", "2X R8")
  gdt       datum feature symbols and feature control frames
A frame or datum stacked under a callout needs both "callouts" and "gdt".
When callouts are off, a datum symbol on a hole gets drawn on the hole itself
instead (its copy carries unless=["callouts"]).
"""
import math

from .document import new_id

CATS = ("dims", "callouts", "gdt")
NEW_DOC_DEFAULT = {"dims": False, "callouts": False, "gdt": True}
ALL_ON = {"dims": True, "callouts": True, "gdt": True}


def auto_settings(settings):
    a = settings.get("auto")
    if a is None:                      # projects saved before this option existed
        return dict(ALL_ON)
    return {k: bool(a.get(k, ALL_ON[k])) for k in CATS}


def _cats_for(a, by_id):
    k = a["kind"]
    if k in ("dim", "angle") or (k == "callout" and a.get("pcd")):
        return ["dims"]
    if k == "callout":
        return ["callouts"]
    if k in ("fcf", "datum"):
        p = by_id.get(a.get("attach"))
        if p is not None and p["kind"] == "callout":
            return ["callouts", "gdt"]
        return ["gdt"]
    return []


def categorize(anns, make_alternatives=True):
    """Tag annotations with 'cats'; add stand-alone datum symbols for hole datums."""
    by_id = {a["id"]: a for a in anns}
    extra = []
    for a in anns:
        if "cats" in a:
            continue
        a["cats"] = _cats_for(a, by_id)
        if make_alternatives and a["kind"] == "datum" and a["cats"] == ["callouts", "gdt"]:
            p = by_id[a["attach"]]
            anchor = list(p["anchor"])
            c = p.get("center") or anchor
            d = (anchor[0] - c[0], anchor[1] - c[1])
            L = math.hypot(*d) or 1.0
            alt = dict(a)
            alt.update({"id": new_id(), "attach": None, "anchor": anchor, "dir": [d[0] / L, d[1] / L],
                        "cats": ["gdt"], "unless": ["callouts"], "len": None, "slide": 0.0})
            extra.append(alt)
    return anns + extra


def active(a, on):
    return (all(on.get(c, True) for c in a.get("cats", []))
            and not any(on.get(c, False) for c in a.get("unless", [])))


def apply(anns, on):
    """Auto annotations that belong on the sheet with these switches."""
    return [a for a in anns if active(a, on)]


def merge(current, fresh, old_on, new_on):
    """Switch categories on/off without touching anything else.

    current: the document's annotations (may contain user edits and user-made items)
    fresh:   a newly generated, categorised full auto-draft
    """
    removed = set()
    keep = []
    for a in current:
        if a.get("auto") and not active(a, new_on):
            removed.add(a["id"])
        else:
            keep.append(a)
    # anything stacked under a removed callout goes with it
    keep = [a for a in keep if a.get("attach") not in removed]

    add = [a for a in fresh if active(a, new_on) and not active(a, old_on)]
    add_ids = {a["id"] for a in add}
    fresh_by_id = {a["id"]: a for a in fresh}
    callout_for = {}
    for a in keep:
        if a["kind"] == "callout" and not a.get("pcd"):
            for fid in a.get("members") or [a.get("feature")]:
                callout_for[fid] = a["id"]
    out = []
    for a in add:
        att = a.get("attach")
        if att and att not in add_ids:
            parent = fresh_by_id.get(att)
            target = callout_for.get(parent.get("feature")) if parent else None
            if not target:
                continue          # its callout was deleted by the user
            a = dict(a, attach=target)
        out.append(a)
    return keep + out
