"""
_crypto_loader.py -- shared helper used by the tiny stub files in this
backend/ folder (ocad.py, brep.py, drawing_layout.py,
kernel_breadcrumb.py, kernel_manager.py, kernel_process.py,
mesh_types.py, python_eval.py, server.py). This file itself has
nothing to hide (it's just import plumbing), which is exactly why it's
the one thing here left as plain, readable source.

Why this exists: the modules above contain the actual app logic (the
B-rep engine built on build123d, the kernel worker process, the
Python-mode evaluator, the HTTP route table), which this app ships as
encrypted source only -- backend/_protected/<name>.enc -- rather than
as plain .py text, so a curious end user opening the folder doesn't
find readable Python they can just copy out. Each stub file below is a
few lines that hand off to load_protected() here, which decrypts the
matching .enc file and runs it in the stub's own module slot, so
callers see no difference at all: `import brep` still gives you every
function brep.py always had.

This is bytecode-level protection, not real encryption -- Python still
has to be given something it can execute, and this cipher can be
reversed by anyone who reads this file (the key has to ship with the
app, since nothing here asks the end user for a password) and writes a
few lines of Python. It raises the bar from "open it in any text
editor" to "read this file and write a decrypt script," nothing
stronger. If you ever need protection that resists that too, look at
PyArmor (adds real obfuscation, at the cost of its own runtime
dependency) or shipping a compiled standalone executable via
PyInstaller/Nuitka instead of Python source at all.

The cipher: a XOR stream generated from repeated SHA-256 hashing of
(key + block counter) -- stdlib-only (hashlib), no third-party crypto
dependency, matching this app's existing "only build123d/numpy are
hard dependencies" philosophy. It is NOT a standards-vetted cipher
(not AES-GCM or similar) -- it's a lightweight, adequate-for-this-
purpose deterrent, not something to rely on for defending genuinely
sensitive data.

NOTE: this key is intentionally DIFFERENT from SanPyCAD's and
SanPyCAD-2D's own _crypto_loader.py keys -- each app has its own, so a
key extracted from one doesn't unlock the others.
"""
import hashlib
import importlib.util
import os
import sys

# Embedded key -- see the module docstring's limits section above.
# Regenerate with `python3 -c "import secrets; print(secrets.token_hex(32))"`
# and re-run build_protected_backend.py if you ever want to rotate it.
_KEY_HEX = "80b20b09cbfb8f61c976758c1673f98993fda358c93445ba5e98854590e4a862"
_KEY = bytes.fromhex(_KEY_HEX)


def _keystream(length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(_KEY + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:length])


def _xor(data):
    """Symmetric -- the same function encrypts and decrypts."""
    ks = _keystream(len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


def encrypt_source(source_text):
    """str (Python source) -> encrypted bytes, for the build script."""
    return _xor(source_text.encode("utf-8"))


def decrypt_source(blob):
    """encrypted bytes -> str (Python source)."""
    return _xor(blob).decode("utf-8")


def load_protected(modname, stub_path):
    """
    Decrypts modname's real source from backend/_protected/<modname>.enc
    and runs it as if it were the code of the stub sitting at
    `stub_path` (i.e. backend/<modname>.py's own location) -- so any
    __file__-relative logic inside the real module keeps resolving
    exactly as it would if the real source were sitting right there in
    backend/.

    `modname` must already be registered in sys.modules (true for any
    module mid-import, which is the only time a stub ever calls this).
    """
    backend_dir = os.path.dirname(os.path.abspath(stub_path))
    enc_path = os.path.join(backend_dir, "_protected", modname + ".enc")

    if not os.path.isfile(enc_path):
        raise ImportError(
            f"Missing encrypted module file for '{modname}': {enc_path}. "
            f"This copy of the app is incomplete -- backend/_protected/ "
            f"should contain a .enc file for every stub in backend/."
        )

    with open(enc_path, "rb") as f:
        source = decrypt_source(f.read())

    module = sys.modules[modname]
    module.__file__ = stub_path
    module.__spec__ = importlib.util.spec_from_loader(modname, loader=None, origin=stub_path)
    code = compile(source, stub_path, "exec")
    exec(code, module.__dict__)
    return module
