"""
gdt_bridge.py -- glue between SanPyCADM and the bundled GD&T Drafter.

GD&T Drafter (the `gdt` package + `web/` editor in this folder) turns a STEP
file into a GD&T-annotated 2D drawing. SanPyCADM runs its own copy of
GD&T Drafter's small HTTP server in a background thread of the SanPyCADM
process, on its own port (never the same one as SanPyCADM, because both
UIs use absolute /api/... URLs), and opens the model there.

Nothing here touches SanPyCADM's own kernel: the caller exports the shown
shape(s) to a STEP file first and hands the path to open_step().
"""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
_LOCK = threading.Lock()
_STATE = {"httpd": None, "port": None}
FIRST_PORT = 8765


def _import_server():
    if HERE not in sys.path:
        sys.path.append(HERE)
    try:
        import OCP  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("GD&T Drafter needs the OpenCascade bindings (OCP): %s" % exc)
    from gdt import server
    return server


def ensure_server():
    """Start GD&T Drafter's server once; returns (server_module, port)."""
    server = _import_server()
    with _LOCK:
        if _STATE["httpd"] is None:
            last = None
            for port in range(FIRST_PORT, FIRST_PORT + 40):
                try:
                    httpd = server.serve(port)
                except OSError as exc:      # port busy (e.g. a standalone GD&T Drafter)
                    last = exc
                    continue
                t = threading.Thread(target=httpd.serve_forever, name="gdt-drafter", daemon=True)
                t.start()
                _STATE["httpd"], _STATE["port"] = httpd, port
                break
            else:
                raise RuntimeError("No free port for GD&T Drafter near %d (%s)" % (FIRST_PORT, last))
    return server, _STATE["port"]


def open_step(step_path, name="model.step", standard="ISO"):
    """Open a STEP file as a new drawing; returns the editor URL."""
    server, port = ensure_server()
    with open(step_path, "rb") as f:
        data = f.read()
    if not data:
        raise ValueError("The exported STEP file is empty.")
    with server.LOCK:
        sid, _ = server.open_session(data, name, standard=standard)
    return "http://127.0.0.1:%d/#sid=%s" % (port, sid)


def shutdown():
    with _LOCK:
        httpd, _STATE["httpd"] = _STATE["httpd"], None
    if httpd is not None:
        try:
            httpd.shutdown()
        except Exception:
            pass
