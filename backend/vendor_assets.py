"""
vendor_assets.py

SanPyCAD's frontend (frontend/index.html) uses two third-party JS
libraries -- CodeMirror 5 (the code editor) and Three.js (the 3D
viewport) -- that it originally always loaded live from a CDN
(cdnjs.cloudflare.com / cdn.jsdelivr.net). That meant the app needed
internet access on every single launch, not just the first one.

This module downloads those exact files once, into frontend/vendor/,
so the app can run with zero network access afterwards. index.html
tries the local frontend/vendor/... copy of each asset first and only
falls back to the CDN URL if that local file is missing or fails to
load -- see loadScript()/loadCss() in index.html.

Design notes:
  - Uses only Python's stdlib (urllib.request) -- no extra dependency
    just to fetch a few files once.
  - Each asset is downloaded independently (its own try/except) so one
    failure (e.g. no internet yet, one CDN briefly down) doesn't block
    the others -- the app still runs fine off the CDN meanwhile via
    index.html's fallback.
  - Downloads are written atomically (temp file + os.replace) so a
    killed/interrupted download can never leave a half-written file
    that looks "present" to missing_assets() but is actually corrupt.
  - This is meant to be called once in a background thread at startup
    (see server.py's print_backend_status()); it's a no-op almost
    instantly on every launch after the first, since it only fetches
    what's actually missing.
"""

import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
VENDOR_DIR = os.path.join(FRONTEND_DIR, "vendor")

# (local path relative to frontend/vendor/, remote URL). The local paths
# are exactly what index.html requests (as /vendor/<local path>) before
# ever trying the CDN URL -- keep these two lists in sync with the
# vendorPath/cdnUrl pairs in index.html's loadScript()/loadCss() calls.
_ASSETS = [
    ("codemirror/5.65.16/codemirror.min.css",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css"),
    ("codemirror/5.65.16/theme/dracula.min.css",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css"),
    ("codemirror/5.65.16/addon/hint/show-hint.min.css",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/hint/show-hint.min.css"),
    ("codemirror/5.65.16/addon/dialog/dialog.min.css",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.css"),
    ("codemirror/5.65.16/codemirror.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"),
    ("codemirror/5.65.16/mode/clike/clike.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"),
    ("codemirror/5.65.16/mode/python/python.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"),
    ("codemirror/5.65.16/addon/edit/closebrackets.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/closebrackets.min.js"),
    ("codemirror/5.65.16/addon/edit/matchbrackets.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"),
    ("codemirror/5.65.16/addon/hint/show-hint.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/hint/show-hint.min.js"),
    ("codemirror/5.65.16/addon/comment/comment.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/comment/comment.min.js"),
    ("codemirror/5.65.16/addon/dialog/dialog.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/dialog/dialog.min.js"),
    ("codemirror/5.65.16/addon/search/searchcursor.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/searchcursor.min.js"),
    ("codemirror/5.65.16/addon/search/search.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/search/search.min.js"),
    ("three.js/r128/three.min.js",
     "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"),
    ("three.js/r128/OrbitControls.js",
     "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"),
]


def missing_assets():
    """Local (relative) paths of assets not yet vendored (or vendored as
    a suspicious 0-byte file from some earlier interrupted attempt)."""
    missing = []
    for local, _url in _ASSETS:
        full = os.path.join(VENDOR_DIR, local)
        if not os.path.isfile(full) or os.path.getsize(full) == 0:
            missing.append(local)
    return missing


def ensure_vendor_assets(timeout=6, on_progress=None):
    """Downloads whatever's currently missing from _ASSETS into
    frontend/vendor/. Safe to call on every launch -- it only does
    network work for files that aren't already there, so after the
    first successful run this returns almost instantly.

    timeout: per-file socket timeout in seconds, so one stalled
        connection can't hang the whole pass.
    on_progress: optional callable(local_path, ok, error_or_None),
        called once per asset actually attempted.

    Returns the list of local paths that are still missing afterwards
    (empty list == every asset now available for fully offline use).
    """
    todo = missing_assets()
    for local in todo:
        url = dict(_ASSETS)[local]
        dest = os.path.join(VENDOR_DIR, local)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".part"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = resp.read()
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)  # atomic on both POSIX and Windows
            if on_progress:
                on_progress(local, True, None)
        except Exception as e:
            # No internet yet, one CDN briefly unreachable, etc. -- not
            # fatal: index.html falls back to the CDN URL directly for
            # anything still missing, so the app keeps working either
            # way. Just leave it for the next launch to retry.
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            if on_progress:
                on_progress(local, False, str(e))
    return missing_assets()


def ensure_vendor_assets_async(timeout=6, on_done=None):
    """Kicks off ensure_vendor_assets() on a background daemon thread so
    it never delays app startup -- the app is fully usable immediately
    (via the CDN fallback) while this quietly fills in frontend/vendor/
    for next time. `on_done(still_missing_list)` is called on that
    background thread when the pass finishes, if given."""
    import threading

    def _run():
        still_missing = ensure_vendor_assets(timeout=timeout)
        if on_done:
            on_done(still_missing)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
