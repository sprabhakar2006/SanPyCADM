"""
ocad.py -- loader stub. The core geometry/math engine (ported ocad primitives used by scripts) is shipped as encrypted source only,
under backend/_protected/ocad.enc -- see backend/_crypto_loader.py for
why and how, and build_protected_backend.py (in the main project
folder, not shipped here) for regenerating it after an edit.

Everything ocad.py has always exposed still works exactly the same
via `import ocad` -- this stub just hands the loading off
transparently.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crypto_loader import load_protected  # noqa: E402

load_protected(__name__, os.path.abspath(__file__))
