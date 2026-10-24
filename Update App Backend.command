#!/bin/bash
# Copies the latest backend/_protected/*.enc into dist/SanPyCADM.app,
# re-signs it (ad hoc) and relaunches. Takes seconds - no full rebuild.
cd "$(dirname "$0")" || exit 1
APP="dist/SanPyCADM.app"
[ -d "$APP" ] || { echo "No $APP - run 'Build and Launch SanPyCADM.command' first."; read -r; exit 1; }
pkill -f "SanPyCADM.app/Contents/MacOS" 2>/dev/null
n=0
while IFS= read -r d; do
  cp -f backend/_protected/*.enc "$d"/ && n=$((n+1)) && echo "updated: $d"
done < <(find "$APP" -type d -name _protected)
[ "$n" -gt 0 ] || { echo "No _protected folder found inside the app."; read -r; exit 1; }
xattr -cr "$APP" 2>/dev/null
codesign --force --deep --sign - "$APP" && echo "re-signed"
open "$APP"
echo "Done - SanPyCADM relaunched."
read -r -p "Press Enter to close..."
