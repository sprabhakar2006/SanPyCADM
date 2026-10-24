#!/usr/bin/env python3
"""
build_bundle.py -- build the self-contained SanPyCADM bundle for the
machine you run it on:

    python packaging/build_bundle.py

Produces dist/SanPyCADM.app (macOS) or dist/SanPyCADM/ (Windows/Linux)
plus a zip next to it. PyInstaller cannot cross-compile, so
.github/workflows/build-installers.yml runs this on GitHub's macOS and
Windows runners.

Steps: check dependencies, fetch CodeMirror/Three.js into
frontend/vendor/, run PyInstaller against packaging/sanpycad.spec, zip.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "sanpycad.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"

RUNTIME_DEPS = ["build123d", "IPython", "numpy", "scipy", "sympy", "skimage", "webview", "pyperclip"]


def step(msg):
    print(f"\n==> {msg}", flush=True)


def check_deps():
    step("Checking build dependencies")
    if sys.version_info < (3, 10):
        print(f"  Python {sys.version.split()[0]} is too old -- SanPyCADM needs 3.10+")
        sys.exit(1)
    print(f"  Python {sys.version.split()[0]}  ok")
    missing = []
    try:
        import PyInstaller  # noqa: F401
        print("  PyInstaller  ok")
    except ImportError:
        missing.append("pyinstaller")

    for name in RUNTIME_DEPS:
        try:
            __import__(name)
            print(f"  {name:12} ok")
        except ImportError:
            missing.append({"skimage": "scikit-image", "webview": "pywebview"}.get(name, name))

    if missing:
        print("\nMissing, and the bundle cannot be built without them:")
        print(f"    {sys.executable} -m pip install {' '.join(missing)}")
        sys.exit(1)


def fetch_vendor_assets():
    """Put CodeMirror/Three.js in frontend/vendor/ before freezing so the
    bundle works offline from its first launch."""
    step("Fetching editor/3D-viewer assets into frontend/vendor/")
    sys.path.insert(0, str(ROOT / "backend"))
    import vendor_assets

    missing = vendor_assets.missing_assets()
    if not missing:
        print("  already present")
        return
    print(f"  {len(missing)} missing, downloading...")
    still_missing = vendor_assets.ensure_vendor_assets(timeout=30)
    if still_missing:
        print(f"\nERROR: {len(still_missing)} asset(s) could not be downloaded:")
        for rel in still_missing:
            print(f"    {rel}")
        sys.exit(1)
    print("  done")


def run_pyinstaller():
    step("Running PyInstaller (a few minutes -- OCP/OpenCASCADE is large)")
    for path in (BUILD, DIST):
        if path.exists():
            shutil.rmtree(path)
    # via _run_pyinstaller_patched.py: works around a CPython 3.12.0 bug
    # that corrupts scipy.stats when bundled.
    cmd = [sys.executable, str(ROOT / "packaging" / "_run_pyinstaller_patched.py"),
           "--noconfirm", "--clean", str(SPEC)]
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def sign_macos(app_path):
    """Ad-hoc sign the .app (required for arm64 to launch at all)."""
    step("Ad-hoc signing (required on Apple Silicon, harmless on Intel)")
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app_path)], check=True)
    subprocess.run(["codesign", "--verify", "--verbose", str(app_path)], check=True)


def zip_result():
    step("Zipping the bundle")
    tag = "mac" if IS_MAC else ("win" if IS_WINDOWS else "linux")
    if IS_MAC:
        target, zip_path = DIST / "SanPyCADM.app", DIST / f"SanPyCADM-{tag}.zip"
        sign_macos(target)
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(target), str(zip_path)], check=True)
    else:
        target, zip_path = DIST / "SanPyCADM", DIST / f"SanPyCADM-{tag}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    zf.write(path, Path("SanPyCADM") / path.relative_to(target))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  {zip_path.name}  ({size_mb:.0f} MB)")
    return target, zip_path


def main():
    check_deps()
    fetch_vendor_assets()
    run_pyinstaller()
    target, zip_path = zip_result()
    print(f"\nBuilt: {target}")
    print(f"Ship:  {zip_path}")
    if IS_MAC:
        print("\nNot notarized: the first launch on another Mac shows an "
              "'unidentified developer' warning -- right-click the app > Open > Open.")


if __name__ == "__main__":
    main()
