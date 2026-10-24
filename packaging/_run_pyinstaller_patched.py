#!/usr/bin/env python3
"""
_run_pyinstaller_patched.py -- runs PyInstaller with one upstream bug
worked around first. build_bundle.py invokes THIS script instead of
calling `python -m PyInstaller` directly.

The bug: CPython 3.12.0 (fixed in 3.12.1) shipped a broken
code.replace() -- see https://github.com/python/cpython/pull/111866.
PyInstaller's own path-anonymization step (stripping the local
machine's absolute build paths out of the bytecode it freezes, so a
shipped bundle doesn't leak them -- see
PyInstaller.building.utils.strip_paths_in_code) calls code.replace()
on every single module it bundles. On a broken 3.12.0 interpreter,
that corrupts the bytecode of any module containing a specific (and
fairly common) pattern: a comprehension, followed by `del` of a
loop variable reused from that comprehension outside it. scipy's own
scipy/stats/_distn_infrastructure.py happens to do exactly this (to
clean up temporary docstring-building variables after module load),
which is why bundling scipy.stats on a 3.12.0 interpreter produces a
bundle that runs fine during the build but crashes the instant the
frozen app imports scipy.stats, with "NameError: name 'obj' is not
defined" deep inside a scipy file that looks, and is, entirely
correct. See https://github.com/pyinstaller/pyinstaller/issues/7992
for the full writeup (the PyInstaller maintainers confirmed it is a
CPython bug, not something they can fix on their end) and
https://github.com/pyinstaller/pyinstaller/issues/8186 for the same
symptom reported against scipy specifically.

The real fix is "don't build with exactly CPython 3.12.0" -- but this
app's one-click build script can't control which python3 happens to
be first on a user's PATH, and re-pointing it at a different
interpreter is a much bigger ask than working around a bug that has a
one-line fix on PyInstaller's side anyway (per the maintainer's own
suggestion in the issue thread above): make strip_paths_in_code a
no-op. The only cost is that a traceback raised inside the shipped
app would show this machine's build-time absolute paths instead of
anonymized ones -- irrelevant here, since app.py already redirects
all of this app's own runtime output to a per-user log file (see
packaging/bundle_paths.py's start_logging()) that only the person
running the app ever sees.

IMPORTANT gotchas that cost real debugging time, in the order they
were found:

1. The function got renamed between PyInstaller versions. Older
   versions call it `strip_paths_in_code` (in
   PyInstaller.building.utils); the version actually in use here
   (6.22.3) renamed it to `replace_filename_in_code_object`, with the
   same signature and the same job. Patching the old name is a silent
   no-op on the new version -- no error, the attribute assignment just
   creates an unused attribute, and the real (buggy) function keeps
   running untouched. So both names are patched below, on whichever
   module actually defines them, to be safe across versions.

2. Wherever the function is actually called from matters more than
   where it's defined. In 6.22.3, the call that corrupts scipy.stats
   happens in PyInstaller.archive.writers.ZlibArchiveWriter._write_entry
   (every single module going into the PYZ archive passes through
   there) -- NOT in building/api.py's PYZ.assemble(), which in this
   version just hands code objects straight to ZlibArchiveWriter
   without touching them itself. And archive/writers.py imports the
   function BY NAME: `from PyInstaller.building.utils import ...,
   replace_filename_in_code_object`. That binds writers.py's own
   module-level name to the original function object at import time;
   patching only `PyInstaller.building.utils.<name>` afterwards does
   NOT change writers.py's already-bound copy, since writers.py never
   looks the name up on the utils module again. Every module that
   imported the function by name has to be patched individually for
   this to actually take effect -- there is no single place to patch
   once and have it propagate.

Because the exact module/function-name combination that matters can
change again in a future PyInstaller release, this patches both known
names on every module found to define or import either of them,
skipping whichever doesn't exist in the installed version.
"""
import sys

_NOOP_NAMES = ("strip_paths_in_code", "replace_filename_in_code_object")


def _noop(co, *args, **kwargs):
    return co


def _patch_module(module):
    patched = []
    for name in _NOOP_NAMES:
        if hasattr(module, name):
            setattr(module, name, _noop)
            patched.append(name)
    return patched


import PyInstaller.building.utils as _piu
import PyInstaller.building.api as _pia
import PyInstaller.archive.writers as _piw

for _mod in (_piu, _pia, _piw):
    _patch_module(_mod)

from PyInstaller.__main__ import run  # noqa: E402

if __name__ == "__main__":
    run()
