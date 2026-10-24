#!/usr/bin/env python3
"""
app.py -- launches SanPyCADM, the OpenSCAD-like desktop application.

This is the B-rep-first copy of SanPyCAD: unlike the main app and
SanPyCAD Experimental (both mesh-based -- everything ends up as
triangle soup), scripts here build on backend/brep.py, which wraps
build123d/OpenCASCADE (OCCT) to produce genuine boundary-representation
(B-rep) solids -- exact analytic/NURBS surfaces, exact booleans, real
STEP file export. The 3D viewer still renders triangles (that's all
WebGL can ever draw), but they're a disposable tessellation generated
just for display -- the actual model stays exact B-rep the whole time.
Its window title, launcher names, and console/log output are all
labeled "SanPyCADM" specifically so it's never confused with the
other two when installed side by side.

This starts the local geometry backend (backend/server.py, built on
build123d via backend/brep.py) and opens it in its own application window
using pywebview, so this behaves like a normal desktop app rather than "go
start a server and open your browser". If pywebview isn't installed, it
transparently falls back to opening your default browser instead -- the
app still works, just as a browser tab.

Normally you don't need to run this file directly -- just double-click
SanPyCADM.app (in the same folder as this file) to launch it
like any other desktop app, no Terminal/command line needed. This is
what that shortcut actually runs under the hood; it's still runnable by
hand too if you ever want to:
    python3 app.py

To get the native window (recommended), install pywebview first:
    pip install pywebview
"""

import json
import multiprocessing
import os
import sys
import socket
import tempfile
import threading
import time
import traceback
import webbrowser


def _hide_dock_icon():
    """macOS only: stop THIS process from getting its own Dock icon.
    A frozen .app re-launches its own executable for every
    multiprocessing child (the OCCT kernel worker, the resource tracker),
    and macOS gives each one a separate Dock icon -- the user saw three
    "SanPyCADM" icons where Windows shows one. Setting the process's
    activation policy to "prohibited" (no Dock icon, no menu bar) keeps
    just the real app window's icon. Pure ctypes (no pyobjc needed);
    silently does nothing anywhere it doesn't apply or can't work."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(ctypes.util.find_library("AppKit"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        nsapp = send(objc.objc_getClass(b"NSApplication"),
                     objc.sel_registerName(b"sharedApplication"))
        send.restype = ctypes.c_bool
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        send(nsapp, objc.sel_registerName(b"setActivationPolicy:"), 2)
    except Exception:
        pass


def _unblock_bundled_dlls():
    """Windows stamps every file extracted from a downloaded zip with a
    "this came from the internet" mark (an NTFS Zone.Identifier
    alternate data stream). .NET Framework refuses to load an assembly
    carrying that mark, which is what makes pywebview's winforms backend
    (it loads bundled DLLs via pythonnet/.NET) fail with a cryptic
    "Failed to resolve Python.Runtime.Loader.Initialize" RuntimeError on
    a plain unzip-and-run -- nothing to do with this app's own code.
    Removing the mark from every bundled DLL before webview is ever
    imported avoids that entirely. No-op on macOS/Linux or when running
    from source (only frozen Windows builds carry bundled DLLs)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name.lower().endswith(".dll"):
                try:
                    os.remove(os.path.join(root, name) + ":Zone.Identifier")
                except OSError:
                    pass  # no mark present, or the folder isn't writable


_unblock_bundled_dlls()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

import server  # noqa: E402


# Where this process records "I'm the currently-running SanPyCADM
# instance, listening on this port" -- see _write_instance_registry()
# below and the sibling SanPyCAD app's backend/brep_bridge.py
# (find_running_instance()), which reads this same fixed path to
# decide whether "Send to SanPyCADM" can reuse an already-open
# window instead of always launching a brand-new one. A fixed path in
# the OS temp dir (not a per-user data dir -- this app has no
# bundle_paths.py-style writable-data-folder concept the way the main
# SanPyCAD app does) rather than anything port-derived, since the
# whole point is that SanPyCAD doesn't know the port yet -- that's
# what it's about to read from here.
INSTANCE_REGISTRY_PATH = os.path.join(tempfile.gettempdir(), "sanpycadm_instance.json")


def _write_instance_registry(port):
    """Best-effort -- a failure here (read-only temp dir, disk full,
    whatever) just means the NEXT "Send to SanPyCADM" won't find
    this instance and will fall back to launching a new one, same as
    before this feature existed. Never worth failing startup over."""
    try:
        with open(INSTANCE_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": os.getpid()}, f)
    except Exception:
        pass


def _clear_instance_registry(port):
    """Removes the registry entry on a clean shutdown, but ONLY if it
    still points at this exact process/port -- a second SanPyCADM
    instance that started (and re-wrote the registry) after this one
    must never have its own, newer entry deleted out from under it by
    this one exiting later."""
    try:
        with open(INSTANCE_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("port") == port and data.get("pid") == os.getpid():
            os.remove(INSTANCE_REGISTRY_PATH)
    except Exception:
        pass


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_server(url, timeout=5.0):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.05)
    return False


class Api:
    """Exposed to the frontend as `window.pywebview.api` (see js_api= below).

    export_file(): the native desktop window has no address bar, tabs, or
    back button, so the normal browser trick of building a Blob and
    clicking a hidden <a download> link doesn't work here: pywebview's
    underlying WKWebView (on macOS) doesn't honor the HTML5 download
    attribute, and instead just navigates the whole window to the blob's
    raw content -- which looks like the app "breaking" into a wall of
    vertex/face text with no way back except quitting and relaunching.
    Building the file here in Python and handing it to webview's own
    native Save panel avoids that entirely; the frontend only falls back
    to the Blob/<a download> approach when running as a plain browser tab
    (no window.pywebview), where it already works fine.

    save_script()/open_script(): same native-dialog approach, but for the
    script's own source code (.py) rather than rendered geometry -- this
    is the app's equivalent of a normal text editor's File > Save/Save
    As/Open, so a design can be closed and reopened later instead of only
    ever exported as a one-way STL/OBJ/etc snapshot.
    """

    def export_file(self, code, kind):
        try:
            if kind in ("svg", "drawing"):
                # Both are the same real, hidden-line-removed engineering
                # drawing now (see server.py's generate_drawing_svg()) --
                # NOT a plain triangle-mesh wireframe, so this branches
                # BEFORE the run_any()/meshes path below: a drawing needs
                # the live B-rep Shape objects, only reachable by re-
                # running the script through the kernel's own "drawing"
                # op (generate_drawing_svg() does that itself), not the
                # already-tessellated `meshes` this function's mesh-based
                # kinds (stl/obj/dxf) share below.
                data, error = server.generate_drawing_svg(code, csg_resolution=56)
                if error:
                    return {"error": error}
                default_name = "drawing.svg"
            else:
                result, _scene = server.run_any(code, csg_resolution=56)
                if result.get("error"):
                    return {"error": result["error"]}
                meshes = list(server.ev_meshes_from_result(result))
                if not meshes:
                    return {"error": "nothing to export (empty scene)"}

                builders = {
                    "stl": (server.build_stl_binary, "model.stl"),
                    "obj": (server.build_obj_text, "model.obj"),
                    "dxf": (server.build_dxf_text, "model.dxf"),
                }
                if kind not in builders:
                    return {"error": f"unknown export kind: {kind}"}
                builder, default_name = builders[kind]
                data = builder(meshes)

            window = webview.windows[0]
            save_dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
            if save_dialog is None:
                save_dialog = webview.SAVE_DIALOG  # older pywebview versions
            chosen = window.create_file_dialog(save_dialog, save_filename=default_name)
            if not chosen:
                return {"canceled": True}
            path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen

            is_binary = isinstance(data, (bytes, bytearray))
            mode_flag = "wb" if is_binary else "w"
            # Explicit utf-8 for the text formats (OBJ/SVG/DXF) rather than
            # relying on the platform's default text encoding -- Windows'
            # default is a locale codepage (e.g. cp1252), not utf-8, so a
            # model with a non-ASCII color name or similar could otherwise
            # fail to save there even though the exact same script exports
            # fine on macOS/Linux.
            with open(path, mode_flag, **({} if is_binary else {"encoding": "utf-8"})) as f:
                f.write(data)
            return {"path": path}
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}

    def save_script(self, code, path=None, sketch_data=None):
        """Writes `code` to `path` directly if given (plain "Save", once a
        file's already been saved to/opened from once this session), else
        prompts a native Save dialog first (plain "Save As", or the first
        "Save" of a brand new, never-yet-saved script).

        `sketch_data`, if given, is the JSON text of any "2D Sketch"
        shapes currently sent to this script (see index.html's
        sketchSessions) -- written to a small sidecar file next to the
        script itself (`<path>.sketch.json`) rather than into the
        script's own text, so reopening it later can silently re-inject
        those variables and restore the original editable sketch(es)
        WITHOUT ever having spliced a big literal points list into the
        code the user actually wrote and sees. Ported from the sibling
        SanPyCAD app's own save_script() -- same sidecar filename/shape,
        so a script saved from either app restores its sketches the same
        way (minus that app's separate guifn_data sidecar, since this
        app has no "GUI Functions" panel). If there's nothing to save
        (every sketch was removed from the script since it was last
        saved, or it never had one), any stale sidecar left over from an
        earlier save is cleaned up rather than left around pointing at
        shapes the script no longer uses -- this is also why a script
        saved here BEFORE this fix (no sidecar ever written) genuinely
        has no sketch data to recover: there was nowhere for it to have
        been kept."""
        try:
            if not path:
                default_name = "model.py"
                window = webview.windows[0]
                save_dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
                if save_dialog is None:
                    save_dialog = webview.SAVE_DIALOG  # older pywebview versions
                chosen = window.create_file_dialog(save_dialog, save_filename=default_name)
                if not chosen:
                    return {"canceled": True}
                path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            sidecar_path = path + ".sketch.json"
            if sketch_data:
                with open(sidecar_path, "w", encoding="utf-8") as f:
                    f.write(sketch_data)
            else:
                try:
                    os.remove(sidecar_path)
                except OSError:
                    pass  # no sidecar existed -- nothing to clean up
            return {"path": path}
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}

    def open_script(self):
        try:
            window = webview.windows[0]
            open_dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
            if open_dialog is None:
                open_dialog = webview.OPEN_DIALOG  # older pywebview versions
            chosen = window.create_file_dialog(
                open_dialog,
                file_types=(
                    "SanPyCADM scripts (*.py)",
                    "All files (*.*)",
                ),
            )
            if not chosen:
                return {"canceled": True}
            path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
            result = {"path": path, "code": code}
            # See save_script()'s sidecar comment above -- if this script
            # was saved (with this fix in place) with one or more "2D
            # Sketch" shapes attached, hand its JSON straight back so the
            # frontend can silently re-inject those variables (no
            # NameError on Render) and restore the original editable
            # sketch(es) in the panel.
            sidecar_path = path + ".sketch.json"
            if os.path.exists(sidecar_path):
                try:
                    with open(sidecar_path, "r", encoding="utf-8") as f:
                        result["sketch_data"] = f.read()
                except OSError:
                    pass  # non-fatal -- the script itself still opened fine
            return result
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}


def _pending_import_from_env():
    """"Send to SanPyCADM" handoff for a BRAND-NEW process: the
    sibling SanPyCAD app launches a fresh SanPyCADM instance with
    SANPYCADM_IMPORT set to a .step file it just wrote (see its own
    backend/brep_bridge.py for why an env var and not a CLI argument --
    it survives every one of this app's own launchers, none of which
    touch argv today, with zero changes needed to any of them). Turns
    that into a ready-to-run starter script (server.build_starter_import_
    code() -- shared with the OTHER handoff path, a live POST to
    /import_from_sanpycad for when a SanPyCADM window is already
    open and SanPyCAD reuses it instead of spawning a new one) instead
    of the usual blank default one; returns None for a normal launch
    with nothing to import (the overwhelmingly common case).

    A `<path>.names.json` sidecar next to the .step file (written by
    SanPyCAD's own send_to_brep(), same idea as the "2D Sketch"
    panel's own `.sketch.json` sidecar) carries each body's ORIGINAL
    SanPyCAD variable name (in the same order the shapes were written)
    and, alongside it, each body's actual solid-vs-surface kind (see
    step_export.py's last_shape_kinds() on the SanPyCAD side) -- only
    read here, at process startup, since the live-handoff path above
    gets both straight in the POST body instead.

    A ".sanpycad_script.py" file instead of a ".step" one means
    SanPyCAD's own send_to_brep() sent an actual SCRIPT to re-run here
    (its own newer, preferred handoff -- see that function's own
    docstring for why running the exact same script directly, instead
    of a STEP export/import round-trip, is both faster and more
    faithful to what the script actually draws): its contents ARE the
    starter code, verbatim, no further building needed."""
    path = os.environ.get("SANPYCADM_IMPORT")
    if not path:
        return None
    if not os.path.isfile(path):
        print(f"[SanPyCADM] SANPYCADM_IMPORT={path!r} does not exist -- ignoring")
        return None

    if path.endswith(".sanpycad_script.py"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            print(f"[SanPyCADM] couldn't read {path!r}: {e} -- ignoring")
            return None

    names = []
    shape_kinds = {}
    names_path = path + ".names.json"
    if os.path.isfile(names_path):
        try:
            with open(names_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
            names = [str(n) for n in sidecar.get("names", []) if n]
            shape_kinds = {str(k): str(v) for k, v in (sidecar.get("shape_kinds") or {}).items()}
        except Exception:
            names, shape_kinds = [], {}  # sidecar missing/corrupt -- fall back to s1/s2/... below

    return server.build_starter_import_code(path, names, shape_kinds)


def main():
    server.print_backend_status()

    pending_import = _pending_import_from_env()
    if pending_import is not None:
        server.set_pending_import(pending_import)

    # Warm up the geometry kernel worker process now, in the background,
    # rather than waiting for the first /render. Deliberately done HERE
    # (inside main(), behind this file's own `if __name__ == "__main__":`
    # guard below) and not as an import-time side effect of `import
    # server` above -- see kernel_manager.py's start()/KernelManager
    # docstrings for why doing it eagerly at import time breaks
    # multiprocessing's 'spawn' start method (the macOS/Windows default)
    # on every single launch.
    server.MANAGER.start()

    port = find_free_port()
    httpd, port = server.serve(host="127.0.0.1", port=port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _write_instance_registry(port)
    import atexit
    atexit.register(_clear_instance_registry, port)

    url = f"http://127.0.0.1:{port}/"
    wait_for_server(url)
    print(f"[SanPyCADM] backend running at {url}")

    def _fall_back_to_browser(reason):
        """Shared fallback: the app server itself is fine either way, so a
        pywebview failure is never fatal -- just less polished. Used both
        when pywebview isn't installed at all, and when it's installed but
        can't actually open a native window (e.g. on Windows, when the
        .NET/WebView2 runtime pywebview's winforms backend depends on is
        missing, blocked by antivirus, or otherwise broken on that
        machine -- that shows up as a RuntimeError/clr_loader failure, not
        an ImportError, which is why this is handled separately below)."""
        print(reason)
        webbrowser.open(url)
        print("[SanPyCADM] press Ctrl+C here to stop the app")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    try:
        global webview
        import webview
    except ImportError:
        _fall_back_to_browser(
            "[SanPyCADM] pywebview not installed -- opening your default "
            "browser instead. For a real app window, run: pip install pywebview"
        )
        httpd.shutdown()
        return

    try:
        api = Api()
        window = webview.create_window(
            "SanPyCADM", url, width=1400, height=900, min_size=(900, 600),
            js_api=api,
        )
        # debug=True enables "Inspect Element" in the app window, so JS
        # errors can be diagnosed the same way as in a regular browser if
        # something ever goes wrong -- but on some platforms/backends
        # (notably Windows' WebView2/EdgeChromium backend), it doesn't
        # just make that available on request: it pops the whole DevTools
        # panel open automatically, every single launch. That's a
        # developer/troubleshooting tool, not something anyone needs for
        # normal use, so it's off unless explicitly asked for.
        debug_mode = bool(os.environ.get("SANPYCAD_DEBUG"))
        webview.start(debug=debug_mode)
    except Exception as exc:
        # pywebview IS installed here, but failed to actually open a
        # native window -- on Windows this is almost always its winforms
        # backend failing to load the .NET/CLR runtime it needs (missing
        # or broken .NET Framework / WebView2 Runtime, or an antivirus
        # that quarantined part of the bundled pythonnet DLL). Rather
        # than crashing with a raw traceback, fall back to the browser so
        # the app is still usable, and say what's likely wrong.
        _fall_back_to_browser(
            f"[SanPyCADM] could not open the app window ({exc!r}) -- "
            "opening your default browser instead. This usually means "
            "Windows is missing (or has a broken) Microsoft Edge WebView2 "
            "Runtime or .NET Framework install; installing/repairing "
            "WebView2 from "
            "https://developer.microsoft.com/microsoft-edge/webview2/ "
            "and relaunching SanPyCADM should restore the native window."
        )

    httpd.shutdown()


if __name__ == "__main__":
    # Required for any frozen (PyInstaller) Windows build that uses
    # multiprocessing -- this app spawns its OCCT geometry kernel as a
    # worker subprocess (see kernel_manager.py) for crash isolation.
    # Windows has no fork(); multiprocessing's 'spawn' start method
    # launches a worker by re-running this very .exe with special
    # --multiprocessing-fork arguments. freeze_support() is what makes
    # a frozen executable recognize those arguments and run just the
    # worker payload instead of falling through to main() again. Without
    # it, every worker spawn re-launches a full second copy of the app
    # (a new window) -- and if that copy's own first render also spawns
    # a worker, IT does the same thing, cascading into windows opening
    # one after another with no end. A no-op on macOS/Linux (which fork
    # instead) and when running from source (not frozen), so it's safe
    # to always call unconditionally here.
    # Any process started by multiprocessing (kernel worker, resource
    # tracker) is not the real app -- keep it out of the macOS Dock.
    if any(a.startswith("--multiprocessing") for a in sys.argv[1:]) or \
            (len(sys.argv) > 1 and sys.argv[1] == "-c"):
        _hide_dock_icon()
    multiprocessing.freeze_support()
    main()
