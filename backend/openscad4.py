"""
openscad4.py -- backward-compatibility shim.

The real geometry engine has moved to ocad.py (renamed so the file
itself no longer shares a name with the actual third-party OpenSCAD
software -- this module has never wrapped or depended on it; it's an
independent implementation, just historically named/styled after
OpenSCAD's own function set).

This file exists purely so any existing script, saved notebook, or
example that still does `import openscad4`, `import openscad4 as o4`,
or `from openscad4 import *` keeps working completely unchanged,
forever -- including the "opt-in mesh bridge" escape hatch this app's
own python_eval.py pre-binds as `o`/`ocad`/`openscad4` in every
script's namespace (see its module docstring). New code (and this
app's own internals) should use `import ocad` directly instead.
"""
from ocad import *  # noqa: F401,F403
