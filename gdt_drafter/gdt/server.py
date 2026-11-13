"""Local HTTP server for the editor (stdlib only)."""
import base64
import json
import os
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import math

from .document import default_notes, scale_label
from .layout import alignment_rules
from .export_dxf import to_dxf
from .export_pdf import to_pdf
from .export_svg import to_svg
from .session import Session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SAMPLES = os.path.join(ROOT, "samples")
LOCK = threading.Lock()
SESSIONS = {}
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


def _r(v):
    return round(v, 4)


def pick_entities(ctx):
    """Pickable geometry per view, in view model coordinates."""
    out = {}
    for name, info in ctx.lay.views.items():
        meta = ctx.vmeta.get(name, {})
        if meta.get("type") == "iso":
            continue
        vg = ctx.geoms[name]
        lines, circles, arcs, polys = [], [], [], []
        verts, centers = {}, {}

        def vert(p):
            verts[(round(p[0], 3), round(p[1], 3))] = [_r(p[0]), _r(p[1])]

        def ctr(c, r):
            centers[(round(c[0], 3), round(c[1], 3))] = [_r(c[0]), _r(c[1]), _r(r)]
        def put(cv, hidden):
            k = cv["k"]
            if k == "L":
                x1, y1, x2, y2 = cv["p"]
                lines.append([_r(x1), _r(y1), _r(x2), _r(y2), hidden])
                vert((x1, y1))
                vert((x2, y2))
            elif k == "C":
                circles.append([_r(cv["c"][0]), _r(cv["c"][1]), _r(cv["r"]), hidden])
                ctr(cv["c"], cv["r"])
            elif k == "A":
                arcs.append([_r(cv["c"][0]), _r(cv["c"][1]), _r(cv["r"]), _r(cv["a0"]), _r(cv["a1"]), hidden])
                ctr(cv["c"], cv["r"])
                for a in (cv["a0"], cv["a1"]):
                    vert((cv["c"][0] + cv["r"] * math.cos(math.radians(a)),
                          cv["c"][1] + cv["r"] * math.sin(math.radians(a))))
            else:
                pts = cv["pts"]
                vert(pts[0])
                vert(pts[-1])
                if cv.get("pieces"):      # tangent arcs written as one spline
                    for sub in cv["pieces"]:
                        put(sub, hidden)
                else:
                    step = max(1, len(pts) // 60)
                    polys.append([[[_r(x), _r(y)] for x, y in pts[::step] + [pts[-1]]], hidden])
        for hidden, curves in ((0, vg.visible + vg.tangent), (1, vg.hidden)):
            for cv in curves:
                put(cv, hidden)
        if ctx.doc["settings"].get("centerlines", True):     # centre lines pick like edges (flag 2)
            from .render import centerline_geom
            marks, axes = centerline_geom(ctx, name)
            for c, ext, _ in marks:
                lines.append([_r(c[0] - ext), _r(c[1]), _r(c[0] + ext), _r(c[1]), 2])
                lines.append([_r(c[0]), _r(c[1] - ext), _r(c[0]), _r(c[1] + ext), 2])
                ctr(c, 0.0) if (round(c[0], 3), round(c[1], 3)) not in centers else None
            for a, b in axes:
                lines.append([_r(a[0]), _r(a[1]), _r(b[0]), _r(b[1]), 2])
        out[name] = {"lines": lines, "circles": circles, "arcs": arcs, "polys": polys,
                     "verts": list(verts.values()), "centers": list(centers.values())}
    return out


def snap_points(ctx):
    """Paper-space snap points per orthographic view for the add-dimension tool."""
    out = {}
    for name, info in ctx.lay.views.items():
        if name == "iso":
            continue
        vg = ctx.geoms[name]
        pts = set()

        def add(p):
            q = ctx.lay.to_paper(name, p)
            pts.add((round(q[0], 2), round(q[1], 2)))
        for cv in vg.visible + vg.hidden:
            k = cv["k"]
            if k == "L":
                add(cv["p"][:2])
                add(cv["p"][2:])
            elif k == "C":
                c, r = cv["c"], cv["r"]
                add(c)
                for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r)):
                    add((c[0] + dx, c[1] + dy))
            elif k == "A":
                import math
                c, r = cv["c"], cv["r"]
                add(c)
                for a in (cv["a0"], cv["a1"]):
                    add((c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a))))
            else:
                add(cv["pts"][0])
                add(cv["pts"][-1])
        out[name] = [list(p) for p in list(pts)[:6000]]
    return out


def state(sid, s, full=True, geom_key=None, new_id=None):
    ctx, cv, bbs = s.build()
    gk = s.geom_key()
    out = {
        "sid": sid,
        "doc": s.doc,
        "svg": to_svg(cv, ctx.lay.W, ctx.lay.H, editor=True, background=None),
        "sheet": {"W": ctx.lay.W, "H": ctx.lay.H},
        "scale": ctx.lay.scale,
        "scale_label": scale_label(ctx.lay.scale),
        "views": {k: v["rect"] for k, v in ctx.lay.views.items()},
        "view_scales": {k: v["scale"] for k, v in ctx.lay.views.items()},
        "view_origins": {k: v["origin"] for k, v in ctx.lay.views.items()},
        "align": alignment_rules(s.doc, ctx.geoms, ctx.lay),
        "geom_key": gk,
        "new_id": new_id,
        "bboxes": bbs,
    }
    if full or geom_key != gk:
        out["pick"] = pick_entities(ctx)
    if full:
        out["features"] = s.features()
        out["bodies"] = s.body_list()
        out["part"] = {"name": s.part.name, "faces": s.part.n_faces,
                       "size": [round(s.part.bbox[3] - s.part.bbox[0], 3), round(s.part.bbox[4] - s.part.bbox[1], 3),
                                round(s.part.bbox[5] - s.part.bbox[2], 3)]}
    return out


def open_session(data, filename, doc=None, standard="ISO"):
    s = Session.from_bytes(data, filename, doc=doc, standard=standard)
    sid = uuid.uuid4().hex[:12]
    SESSIONS.clear()            # single-user app: keep only the open part
    SESSIONS[sid] = s
    return sid, s


class Handler(BaseHTTPRequestHandler):
    server_version = "GDTDrafter/1.0"

    def log_message(self, fmt, *args):
        pass

    # ---------------------------------------------------------- helpers
    def _send(self, code, body, ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self):
        raw = self._body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _session(self, req):
        s = SESSIONS.get(req.get("sid"))
        if s is None:
            raise LookupError("This drawing is no longer open on the server. Open the STEP file or project again.")
        if req.get("doc"):
            s.doc = req["doc"]
        return s

    # ---------------------------------------------------------- GET
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path in ("/", "/index.html"):
            path = "/index.html"
        if path == "/api/ping":
            from . import __version__
            return self._send(200, {"app": "gdt-drafter", "version": __version__})
        if path == "/api/quit":         # a newer copy is taking over
            self._send(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == "/api/samples":
            names = sorted(f for f in os.listdir(SAMPLES) if f.lower().endswith((".step", ".stp"))) if os.path.isdir(SAMPLES) else []
            return self._send(200, {"samples": names})
        if path == "/api/project":
            q = parse_qs(url.query)
            s = SESSIONS.get((q.get("sid") or [""])[0])
            if s is None:
                return self._send(404, {"error": "Nothing is open."})
            with open(s.path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            name = os.path.splitext(s.filename)[0] + ".gdt.json"
            body = json.dumps({"format": "gdt-drafter-project", "version": 1, "filename": s.filename,
                               "step_b64": data, "doc": s.doc}).encode("utf-8")
            return self._send(200, body, headers={"Content-Disposition": 'attachment; filename="%s"' % name})
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fp.startswith(WEB) or not os.path.isfile(fp):
            return self._send(404, {"error": "Not found"})
        with open(fp, "rb") as f:
            data = f.read()
        if path == "/index.html":       # stamp the version so a browser never mixes old and new files
            from . import __version__
            data = (data.replace(b'href="style.css"', b'href="style.css?v=%s"' % __version__.encode())
                        .replace(b'src="app.js"', b'src="app.js?v=%s"' % __version__.encode())
                        .replace(b"{{version}}", __version__.encode()))
        self._send(200, data, MIME.get(os.path.splitext(fp)[1], "application/octet-stream"))

    # ---------------------------------------------------------- POST
    def do_POST(self):
        url = urlparse(self.path)
        try:
            with LOCK:
                if url.path == "/api/open":
                    q = parse_qs(url.query)
                    name = (q.get("name") or ["part.step"])[0]
                    std = (q.get("standard") or ["ISO"])[0]
                    data = self._body()
                    if not data:
                        return self._send(400, {"error": "The file was empty."})
                    sid, s = open_session(data, name, standard=std)
                    return self._send(200, state(sid, s))
                if url.path == "/api/sample":
                    req = self._json()
                    name = os.path.basename(req.get("name", ""))
                    with open(os.path.join(SAMPLES, name), "rb") as f:
                        data = f.read()
                    sid, s = open_session(data, name, standard=req.get("standard", "ISO"))
                    return self._send(200, state(sid, s))
                if url.path == "/api/project":
                    req = self._json()
                    if req.get("format") != "gdt-drafter-project":
                        return self._send(400, {"error": "That file is not a GD&T Drafter project (.gdt.json)."})
                    data = base64.b64decode(req["step_b64"])
                    sid, s = open_session(data, req.get("filename", "part.step"), doc=req.get("doc"))
                    return self._send(200, state(sid, s))
                req = self._json()
                if url.path == "/api/render":
                    s = self._session(req)
                    return self._send(200, state(req["sid"], s, full=req.get("full", False),
                                                 geom_key=req.get("geom_key")))
                if url.path == "/api/action":
                    s = self._session(req)
                    act = req.get("action")
                    args = req.get("args") or {}
                    new = None
                    if act == "add_view":
                        new = "view:" + s.add_view(args.get("type"))
                    elif act == "delete_view":
                        s.delete_view(args.get("id"))
                    elif act == "add_section":
                        new = "view:" + s.add_section(args.get("parent"), args.get("pts") or [], args.get("dir") or [0, 1])
                    elif act == "rearrange":
                        s.rearrange()
                    elif act == "add_dim":
                        new = s.add_dim(args)
                    elif act == "add_callout":
                        new = s.add_callout(args.get("view"), args.get("center"), float(args.get("r", 1)),
                                            bool(args.get("arc")), args.get("anchor"), args.get("off") or [12, 12])
                    elif act == "autodraft":
                        s.autodraft()
                    elif act == "reset_auto":
                        s.reset_auto()
                    elif act == "reorient":
                        s.reorient(args.get("which"))
                    elif act == "set_datum":
                        s.set_datum(args.get("letter", ""), args.get("feature"))
                    elif act == "add":
                        s.add_for_feature(args.get("feature"), args.get("what", "fcf:position"))
                    elif act == "auto":
                        s.set_auto(args.get("auto") or {})
                    elif act == "body":
                        s.set_body(args.get("body"))
                    elif act == "standard":
                        old = s.doc["settings"].get("standard", "ISO")
                        new = args.get("standard", "ISO")
                        s.doc["settings"]["standard"] = new
                        if s.doc.get("notes") == default_notes(old):
                            s.doc["notes"] = default_notes(new)
                    else:
                        return self._send(400, {"error": "Unknown action " + str(act)})
                    return self._send(200, state(req["sid"], s, geom_key=req.get("geom_key"), new_id=new))
                if url.path == "/api/export":
                    s = self._session(req)
                    fmt = req.get("format", "pdf")
                    ctx, cv, bbs = s.build()
                    base = (s.doc["title"].get("drawing_no") or s.part.name or "drawing").replace(" ", "_")
                    if fmt == "pdf":
                        body, ctype = to_pdf(cv, ctx.lay.W, ctx.lay.H, s.doc["title"].get("title", "")), "application/pdf"
                    elif fmt == "svg":
                        body, ctype = to_svg(cv, ctx.lay.W, ctx.lay.H).encode("utf-8"), "image/svg+xml"
                    elif fmt == "dxf":
                        body, ctype = to_dxf(cv, ctx.lay.W, ctx.lay.H), "application/dxf"
                    else:
                        return self._send(400, {"error": "Unknown format"})
                    return self._send(200, body, ctype,
                                      {"Content-Disposition": 'attachment; filename="%s.%s"' % (base, fmt)})
                return self._send(404, {"error": "Not found"})
        except LookupError as e:
            return self._send(410, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(400, {"error": str(e) or e.__class__.__name__})


def serve(port=8765, host="127.0.0.1"):
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
