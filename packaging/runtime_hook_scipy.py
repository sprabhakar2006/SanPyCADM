"""
runtime_hook_scipy.py -- PyInstaller runtime hook, run before app.py.

Forces scipy's submodules to fully import, in a safe order, before
anything else in the frozen app gets a chance to trigger them.

Why this is needed: recent scipy versions lazily load their submodules
off the package root via module-level __getattr__ (PEP 562) -- `import
scipy; scipy.stats` doesn't actually import scipy.stats until that
attribute is first touched. backend/geom_ops.py reaches scipy indirectly,
through skimage.measure (`from scipy import signal`), which itself
reaches further into scipy.stats (`from scipy.stats import ...` inside
scipy/signal/_peak_finding.py) -- a RE-ENTRANT trip back through scipy's
own lazy-loading __getattr__ while the first one is still resolving.
Plain CPython handles that fine, but PyInstaller's frozen import
machinery has a known weak spot with exactly this pattern: it can hand
back a module object that's still mid-initialization, which is how you
get a module-level NameError for a name (e.g. `obj`) that the real,
fully-loaded module would have defined by then -- not a bug in SanPyCAD,
and not something a hiddenimports entry can fix on its own, since
hiddenimports only guarantees a module gets BUNDLED, not the ORDER it's
first imported in.

Importing scipy.stats (which pulls in scipy.signal along the way) here,
eagerly and non-reentrantly, means it's already sitting fully-formed in
sys.modules by the time geom_ops.py/ocad.py reach for it indirectly
through skimage -- so that re-entrant lazy-load path never gets
triggered in the first place.
"""
# Reordering scipy.stats ahead of scipy.signal (tried first) was not
# enough on its own -- the crash still reproduces from a bare `import
# scipy.stats`, because the reentrant trigger is INSIDE scipy.stats's
# own init chain, not just between scipy.signal and scipy.stats.
# scipy/stats/__init__.py pulls in _stats_py.py, which pulls in
# distributions.py, which pulls in _distn_infrastructure.py -- and
# something in that chain re-enters scipy's PEP 562 package-level
# lazy loader on the SAME, still-initializing module, which is what
# PyInstaller's frozen importer handles badly (see this file's module
# docstring). Importing each of those leaf modules directly, by their
# own dotted path, deepest/most-specific first, forces each one to
# finish and land in sys.modules as an ordinary, complete module
# BEFORE anything tries to reach it again through the parent
# package's lazy __getattr__ -- so that reentrant path never triggers.
import scipy.stats._distn_infrastructure  # noqa: F401
import scipy.stats.distributions  # noqa: F401
import scipy.stats._stats_py  # noqa: F401
import scipy.stats  # noqa: F401
import scipy.signal._peak_finding  # noqa: F401
import scipy.signal  # noqa: F401
import scipy.spatial  # noqa: F401
import scipy.interpolate  # noqa: F401
import scipy.ndimage  # noqa: F401
