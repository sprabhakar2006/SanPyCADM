"""
bundle_paths.py -- path plumbing used ONLY by the frozen (PyInstaller)
build of SanPyCADM. Running from source never imports this file.

Two things change when the app is frozen into a bundle:

1. Where the app's own files live. From source, app.py sits next to
   backend/, frontend/ and examples/. Inside a bundle those are copied
   into PyInstaller's resource directory (sys._MEIPASS: Contents/
   Frameworks on macOS, _internal\\ on Windows), which is somewhere
   else entirely and is NOT next to the executable the user clicked.

2. Where the app is allowed to WRITE. A bundle is meant to be
   read-only: /Applications on macOS needs an admin password to write
   into, and C:\\Program Files on Windows needs elevation. This app
   writes much less at runtime than the main SanPyCAD app does -- it
   has no sanpycad_config.json and no imports/ folder (those are a
   SanPyCAD-only concept; see that app's own bundle_paths.py) -- but
   it still writes its own session log, and frontend/vendor/ is
   normally fetched into the app's own folder on first run. Both are
   redirected to the per-user application data folder, which always
   exists and is always writable:

       macOS    ~/Library/Application Support/SanPyCADM
       Windows  %APPDATA%\\SanPyCADM
       Linux    ~/.local/share/SanPyCADM  (XDG_DATA_HOME if set)
"""
import os
import sys

APP_NAME = "SanPyCADM"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """The folder that backend/, frontend/ and examples/ sit in."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_data_dir():
    """Per-user, always-writable folder for this app's own data."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def redirect_writable_paths():
    """Neutralize the one writable-path concern this app has when frozen.

    Safe to call when not frozen -- it simply does nothing, so app.py
    can call it unconditionally. Import errors are swallowed on
    purpose: a missing optional backend module must not stop the app
    from starting.
    """
    if not is_frozen():
        return

    data_dir = user_data_dir()

    # frontend/vendor/ -- CodeMirror and Three.js are downloaded into the
    # bundle at BUILD time (see packaging/build_bundle.py's
    # fetch_vendor_assets() step), so there is nothing to fetch at
    # runtime and nowhere writable to fetch it to. Neutralize the
    # downloader rather than let it fail against a read-only bundle on
    # every launch.
    try:
        import vendor_assets
        vendor_assets.missing_assets = lambda: []
        vendor_assets.ensure_vendor_assets_async = lambda timeout=6, on_done=None: (
            on_done([]) if callable(on_done) else None
        )
    except Exception:
        pass

    return data_dir


def start_logging():
    """Send the app's console output to a log file.

    A windowed bundle has no terminal attached, so everything the app
    prints -- which worker process started, why a render failed, any
    traceback -- would otherwise be lost. PyInstaller replaces
    sys.stdout/sys.stderr with a null writer in windowed mode, so
    without this there is no way at all to see what went wrong on a
    user's machine. The file is truncated on each launch, so it always
    describes the current session rather than growing forever.

    Returns the log path, or None when not frozen (running from source
    already has a terminal).
    """
    if not is_frozen():
        return None
    log_path = os.path.join(user_data_dir(), "SanPyCADM.log")
    try:
        stream = open(log_path, "w", encoding="utf-8", buffering=1)
    except OSError:
        return None
    sys.stdout = stream
    sys.stderr = stream
    return log_path
