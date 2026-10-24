# generate_reference_captures.py
#
# Run this INSIDE SanPyCADM itself, the same way you'd run any other
# example: paste this whole file into the app's Python editor and click
# Run (Python mode). It reuses the app's own live kernel -- the one with
# build123d/OCCT actually loaded -- to build a real Shape for every brep.py
# function call it can find, tessellate each one into a plain triangle
# list (no build123d objects, just [x, y, z] floats), and write the whole
# thing out as reference_captures.json next to this project's examples/
# folder.
#
# That JSON has zero build123d dependency to READ back -- hand it to
# Claude (or open it yourself) and it can render real pictures of each
# function's actual output with plain matplotlib, no CAD kernel needed on
# that end. This is the missing half of the illustrated brep.py function
# reference guide: the text-only edition already covers all 264
# functions; this script is what would let a future edition add real
# per-function pictures the same way the openscad4.py guide has them.
#
# What it does, step by step:
#   1. Wraps every public (non-underscore) function in the `brep` module
#      so the first couple of REAL calls made anywhere below get their
#      args and return value recorded, without changing behavior at all.
#   2. Runs every *.py file in examples/ through that instrumented
#      namespace (same globals shape python_eval.py itself builds), each
#      with a short timeout so one hanging script can't stall the rest.
#   3. For every captured return value that's an actual build123d Shape,
#      calls this file's own to_triangles() to flatten it into plain
#      [[p0,p1,p2],...] triangle data. Point-list results (2D/3D profiles
#      that never became a Shape -- circle(), cr2dt(), arc(), etc. all
#      return plain point lists) are stored as-is. Anything else (plain
#      numbers, None, unrecognized types) is skipped.
#   4. Writes reference_captures.json with one entry per successfully
#      captured-and-tessellated function.
#
# Safe to re-run any time -- it only reads examples/ and writes one
# output JSON, it doesn't modify brep.py or any example.

import os, sys, glob, json, signal, traceback

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(brep.__file__)), "..", "examples")
EXAMPLES_DIR = os.path.normpath(EXAMPLES_DIR)
OUT_JSON = os.path.join(EXAMPLES_DIR, "..", "reference_captures.json")
OUT_JSON = os.path.normpath(OUT_JSON)

public_names = [n for n in dir(brep) if not n.startswith("_") and callable(getattr(brep, n))]

captured = {}


def make_wrapper(name, real_fn):
    def wrapper(*args, **kwargs):
        result = real_fn(*args, **kwargs)
        lst = captured.setdefault(name, [])
        if len(lst) < 2:
            lst.append(result)
        return result
    wrapper.__name__ = name
    return wrapper


originals = {}
for name in public_names:
    real_fn = getattr(brep, name)
    originals[name] = real_fn
    try:
        setattr(brep, name, make_wrapper(name, real_fn))
    except Exception:
        pass

# Build a namespace shaped like python_eval.py's own (brep's public names
# directly callable, plus o/np/brep itself) so example scripts resolve
# exactly like they do inside the real app.
ns = {n: getattr(brep, n) for n in public_names}
ns["brep"] = brep
ns["np"] = np
ns["numpy"] = np
if "o" in globals():
    ns["o"] = o
if "ocad" in globals():
    ns["ocad"] = ocad
if "openscad4" in globals():
    ns["openscad4"] = openscad4  # backward-compat alias, see ocad.py's own docstring


def handler(signum, frame):
    raise TimeoutError()


had_alarm = hasattr(signal, "SIGALRM")
if had_alarm:
    signal.signal(signal.SIGALRM, handler)

results_log = []
for path in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.py"))):
    fname = os.path.basename(path)
    local_ns = dict(ns)
    if had_alarm:
        signal.alarm(20)
    try:
        src = open(path, encoding="utf-8").read()
        exec(compile(src, path, "exec"), local_ns)
        results_log.append((fname, "ok"))
    except Exception as e:
        results_log.append((fname, f"{type(e).__name__}: {e}"))
    finally:
        if had_alarm:
            signal.alarm(0)

# restore originals so this doesn't leave brep permanently monkeypatched
for name, real_fn in originals.items():
    try:
        setattr(brep, name, real_fn)
    except Exception:
        pass

for fname, status in results_log:
    print(fname, "->", status)

# ---- tessellate captured results ----
out = {}
n_shape = n_points = n_skip = n_fail = 0
for name, calls in captured.items():
    entry = None
    for result in calls:
        if result is None:
            continue
        if hasattr(result, "wrapped"):  # a real build123d Shape
            try:
                tris = brep.to_triangles(result)
                tris_plain = [[[float(c) for c in p] for p in tri] for tri in tris]
                if tris_plain:
                    entry = {"type": "triangles", "data": tris_plain}
                    n_shape += 1
                    break
            except Exception:
                n_fail += 1
                continue
        elif isinstance(result, (list, tuple)) and len(result) > 0:
            try:
                pts = [[float(c) for c in p] for p in result if hasattr(p, "__len__") and len(p) in (2, 3)]
                if len(pts) >= 2:
                    entry = {"type": "points", "data": pts}
                    n_points += 1
                    break
            except Exception:
                n_fail += 1
                continue
    if entry is not None:
        out[name] = entry
    else:
        n_skip += 1

with open(OUT_JSON, "w") as f:
    json.dump(out, f)

print()
print(f"captured {len(captured)} distinct functions actually called")
print(f"tessellated as real shapes: {n_shape}, stored as point lists: {n_points}, skipped: {n_skip}, tessellate failures: {n_fail}")
print("wrote", OUT_JSON)
