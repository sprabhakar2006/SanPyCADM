#!/usr/bin/env python3
"""
build_protected_backend.py -- (maintainer tool, NOT shipped to end
users) encrypts the real backend source in backend/_protected_src/
into backend/_protected/<name>.enc, which is what the loader stubs in
backend/ actually decrypt and run at runtime -- see
backend/_crypto_loader.py for the full explanation of how and why.

Why this file exists separately from the stubs: backend/_protected_src/
holds the actual, editable, human-readable source -- the thing you (or
a future dev session) should keep editing when adding features or
fixing bugs, exactly like before this protection scheme existed. This
script is how you turn an edit there into an updated .enc bundle.

This is NOT tied to a specific Python version -- it encrypts source
TEXT, which decrypts back to plain .py text that compile()/exec()
handles the same on any CPython 3.x. Run once per release:

    python3 build_protected_backend.py

IMPORTANT: never add backend/_protected_src/ or this script itself to
a distribution zip -- that would ship the very source this whole setup
exists to keep out of the zip. The zip-building step should only ever
pick up backend/_crypto_loader.py, backend/_protected/ (the .enc
files), and the stub .py files in backend/.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "backend" / "_protected_src"
OUT_DIR = HERE / "backend" / "_protected"
MODULES = ["ocad", "geom_ops", "step_export", "brep", "drawing_layout", "kernel_breadcrumb",
           "kernel_manager", "kernel_process", "mesh_types",
           "python_eval", "server"]

sys.path.insert(0, str(HERE / "backend"))
import _crypto_loader  # noqa: E402


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    missing = [m for m in MODULES if not (SRC_DIR / f"{m}.py").is_file()]
    if missing:
        print(f"ERROR: missing source for {missing} under {SRC_DIR}")
        sys.exit(1)

    print(f"Encrypting into {OUT_DIR} ...")
    for name in MODULES:
        src = SRC_DIR / f"{name}.py"
        dst = OUT_DIR / f"{name}.enc"
        source_text = src.read_text(encoding="utf-8")
        blob = _crypto_loader.encrypt_source(source_text)
        assert _crypto_loader.decrypt_source(blob) == source_text, \
            f"round-trip mismatch for {name} -- refusing to write a bad build"
        dst.write_bytes(blob)
        print(f"  {name}.py -> {dst.relative_to(HERE)}  ({len(blob):,} bytes)")

    print(f"\nDone. backend/_protected/ now has all {len(MODULES)} modules, "
          f"and works on any Python 3.x (no per-version builds needed).")


if __name__ == "__main__":
    main()
