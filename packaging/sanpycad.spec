# -*- mode: python ; coding: utf-8 -*-
"""
sanpycad.spec -- PyInstaller recipe for the self-contained SanPyCADM
bundle (a CPython interpreter, every library the app needs, and the
app's own files in one folder the user can double-click).

Build it with `python packaging/build_bundle.py`, not by hand.

SanPyCADM is B-rep-first (backend/brep.py wraps build123d/OpenCASCADE),
so build123d and its OCP dependency are collected with collect_all().
backend/*.py are loader stubs that read backend/_protected/<name>.enc
from disk, so they ship as DATA and their module names are excluded
from PyInstaller's own importer. Everything those encrypted modules
import is listed by hand in hiddenimports below.
"""
import os
import sys

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

PROTECTED_MODULES = [
    "brep", "drawing_layout", "geom_ops", "kernel_breadcrumb",
    "kernel_manager", "kernel_process", "mesh_types", "ocad",
    "python_eval", "server", "step_export",
]
BACKEND_LOADED_FROM_DISK = PROTECTED_MODULES + [
    "_crypto_loader", "openscad4", "vendor_assets",
]

hiddenimports = [
    "numpy", "sympy", "pyperclip", "webview",
    "scipy.spatial", "scipy.interpolate", "scipy.ndimage", "scipy.signal",
    "skimage.measure", "skimage.draw", "skimage._shared",
]
for pkg in ("scipy", "skimage", "sympy"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += [
    "ast", "base64", "collections", "contextlib", "datetime", "functools",
    "http.server", "inspect", "io", "json", "math", "multiprocessing",
    "multiprocessing.spawn", "platform", "queue", "re", "shutil", "socket",
    "socketserver", "struct", "subprocess", "tempfile", "threading", "time",
    "traceback", "urllib.request", "warnings", "webbrowser",
    "xml.etree.ElementTree", "faulthandler",
]

datas = collect_data_files("sympy")
binaries = []

# lib3mf is a separate package whose native dylib build123d loads at
# runtime, outside of anything static analysis can see.
for pkg in ("build123d", "OCP", "lib3mf", "manifold3d"):
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app.py")],
    pathex=[PROJECT_ROOT, os.path.join(PROJECT_ROOT, "packaging")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[os.path.join(PROJECT_ROOT, "packaging", "runtime_hook_scipy.py")],
    excludes=BACKEND_LOADED_FROM_DISK + [
        # IPython is deliberately NOT excluded: build123d imports it at
        # top level, so excluding it breaks the first brep.py call.
        "jupyter", "notebook", "pytest", "pandas",
    ],
    noarchive=False,
)

a.datas += Tree(os.path.join(PROJECT_ROOT, "backend"), prefix="backend",
                excludes=["__pycache__", "_protected_src", "*.pyc"])
a.datas += Tree(os.path.join(PROJECT_ROOT, "frontend"), prefix="frontend",
                excludes=["__pycache__", "*.pyc"])
a.datas += Tree(os.path.join(PROJECT_ROOT, "examples"), prefix="examples",
                excludes=["__pycache__", "*.pyc"])
a.datas += Tree(os.path.join(PROJECT_ROOT, "packaging"), prefix="packaging",
                excludes=["__pycache__", "*.pyc", "*.spec", "build_bundle.py",
                          "entitlements.plist"])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SanPyCADM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=IS_MAC,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SanPyCADM",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="SanPyCADM.app",
        icon=None,
        bundle_identifier="com.sanpycadm.app",
        info_plist={
            "CFBundleName": "SanPyCADM",
            "CFBundleDisplayName": "SanPyCADM",
            "CFBundleShortVersionString": os.environ.get("SANPYCADM_VERSION", "1.0.0"),
            "CFBundleVersion": os.environ.get("SANPYCADM_VERSION", "1.0.0"),
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
