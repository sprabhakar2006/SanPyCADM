#!/bin/bash
# Double-click to build a fully self-contained SanPyCADM.app (its own Python and
# every library -- build123d/OpenCASCADE, scipy, manifold3d, ... -- inside the app)
# and launch it. The first run takes 10-15 minutes; later runs are faster.
set -uo pipefail
cd "$(dirname "$0")"
echo "=== SanPyCADM one-click standalone build ==="
VENV_DIR=".build_venv"
fail() { echo; echo "!!! FAILED: $1"; echo; read -p "Press Enter to close this window..."; exit 1; }

PYTHON_BIN="$(command -v python3)"
[ -z "$PYTHON_BIN" ] && fail "python3 not found. Install Python 3.10+ from python.org, then double-click this file again."

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating a clean isolated Python environment (first run only)..."
  "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Could not create the virtual environment"
fi
source "$VENV_DIR/bin/activate" || fail "Could not activate the virtual environment"

echo "Installing/checking dependencies (large downloads the first time -- please be patient)..."
pip install --quiet --upgrade pip || fail "pip upgrade failed"
pip install --quiet numpy "scipy==1.13.1" sympy scikit-image pywebview pyperclip pyinstaller build123d ipython manifold3d || fail "Dependency install failed -- check your internet connection"

echo "Closing any running copy of the built app..."
pkill -f "dist/SanPyCADM.app/Contents/MacOS/SanPyCADM" 2>/dev/null || true
sleep 1
echo "Cleaning up any previous build..."
rm -rf dist build

echo "Building the app (several minutes -- please wait)..."
python packaging/build_bundle.py || fail "Build failed -- see the error above. Copy it and send it back for help."

echo "=== Build succeeded. Launching SanPyCADM... ==="
rm -f launch_debug.log
nohup "dist/SanPyCADM.app/Contents/MacOS/SanPyCADM" > launch_debug.log 2>&1 &
APP_PID=$!
disown
SUCCESS=0
for i in 1 2 3 4 5 6; do
  sleep 1
  kill -0 "$APP_PID" 2>/dev/null || break
  grep -qi "Traceback (most recent call last)" launch_debug.log 2>/dev/null && break
done
if kill -0 "$APP_PID" 2>/dev/null && ! grep -qi "Traceback (most recent call last)" launch_debug.log 2>/dev/null; then SUCCESS=1; fi
if [ "$SUCCESS" = "1" ]; then
  echo; echo "All done! SanPyCADM is running. The standalone app is: dist/SanPyCADM.app (zip: dist/SanPyCADM-mac.zip)"
else
  echo; echo "!!! SanPyCADM quit unexpectedly. Its output:"; echo; cat launch_debug.log
  fail "SanPyCADM did not start correctly -- see the output above."
fi
read -p "Press Enter to close..."
