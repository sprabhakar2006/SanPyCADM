"""The drawing document: plain JSON-able dicts shared by the server and the editor."""
import datetime
import itertools

SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
          "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}

# ISO 5455 preferred scales (paper / model)
SCALES = [20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]

_ids = itertools.count(1)


def new_id(prefix="a"):
    return "%s%d" % (prefix, next(_ids))


def bump_ids(doc):
    """Make sure new ids never collide with ids already in a loaded document."""
    global _ids
    top = 0
    for a in doc.get("annotations", []):
        digits = "".join(ch for ch in a.get("id", "") if ch.isdigit())
        if digits:
            top = max(top, int(digits))
    _ids = itertools.count(top + 1)


def scale_label(s):
    if s >= 1:
        return "%s:1" % fmt(s)
    return "1:%s" % fmt(1.0 / s)


def fmt(v, dec=2):
    if v is None:
        return ""
    s = ("%." + str(dec) + "f") % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


def fmt_dev(v, dec=3):
    """Signed deviation: +0.1, -0.05, 0."""
    s = fmt(v, dec)
    if s == "0":
        return "0"
    return s if s.startswith("-") else "+" + s


def default_notes(standard):
    if standard == "ASME":
        return [
            "NOTES:",
            "1. DIMENSIONING AND TOLERANCING PER ASME Y14.5-2018.",
            "2. ALL DIMENSIONS IN MILLIMETRES.",
            "3. UNLESS OTHERWISE SPECIFIED: LINEAR ±0.1, ANGULAR ±0.5°.",
            "4. BREAK ALL SHARP EDGES 0.2 MAX.",
        ]
    return [
        "NOTES:",
        "1. TOLERANCING ISO 8015. GEOMETRICAL TOLERANCES PER ISO 1101.",
        "2. GENERAL TOLERANCES ISO 2768-mK.",
        "3. ALL DIMENSIONS IN MILLIMETRES.",
        "4. REMOVE BURRS, BREAK SHARP EDGES 0.2 x 45°.",
    ]


def new_document(part_name, filename, ptype, frame, datums, standard="ISO", projection=None):
    projection = projection or ("third" if standard == "ASME" else "first")
    from .frame import default_views
    return {
        "version": 1,
        "part": {"name": part_name, "file": filename, "type": ptype},
        "settings": {
            "sheet": "A3",
            "scale": None,            # None = automatic
            "projection": projection,
            "standard": standard,
            "views": default_views(ptype, projection),
            "hidden": True,
            "tangent": True,
            "centerlines": True,
            "decimals": 2,
            "text_height": 3.5,
            "hlr": "auto",
            "auto": {"dims": False, "callouts": False, "gdt": False},
        },
        "views": [new_view(v) for v in default_views(ptype, projection)],
        "frame": {"X": list(frame[0]), "Y": list(frame[1]), "Z": list(frame[2])},
        "datums": [d.to_dict() for d in datums],
        "title": {
            "title": part_name.upper(),
            "drawing_no": "",
            "company": "",
            "material": "",
            "finish": "",
            "mass": "",
            "drawn_by": "",
            "checked_by": "",
            "approved_by": "",
            "date": datetime.date.today().isoformat(),
            "revision": "A",
            "sheet_no": "1 / 1",
        },
        "notes": default_notes(standard),
        "view_offsets": {},
        "annotations": [],
    }


STANDARD_VIEWS = ("front", "top", "bottom", "left", "right", "rear", "iso")
SECTION_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"     # I, O and Q are not used


def new_view(vtype, **extra):
    v = {"id": vtype, "type": vtype, "center": None, "scale": None, "hidden": None,
         "label": vtype in ("iso", "section")}
    v.update(extra)
    return v


def sync_view_ids(doc):
    """settings["views"] mirrors doc["views"] for code that only needs the names."""
    doc["settings"]["views"] = [v["id"] for v in doc.get("views", [])]


def migrate(doc):
    """Bring projects saved by earlier versions up to date (in place)."""
    if "views" not in doc:
        offs = doc.get("view_offsets") or {}
        doc["views"] = [new_view(v) for v in doc["settings"].get("views", ["front"])]
        doc["view_offsets"] = {}
        doc["settings"]["scale"] = doc["settings"].get("scale")
        if offs:
            doc["settings"]["scale"] = None      # re-arrange once
    sync_view_ids(doc)
    return doc


def next_section_letter(doc):
    used = {v.get("letter") for v in doc.get("views", []) if v.get("type") == "section"}
    for ch in SECTION_LETTERS:
        if ch not in used:
            return ch
    return "Z"


def next_datum_letter(doc):
    used = {a.get("letter") for a in doc.get("annotations", []) if a.get("kind") == "datum"}
    for ch in SECTION_LETTERS:
        if ch not in used:
            return ch
    return "Z"
