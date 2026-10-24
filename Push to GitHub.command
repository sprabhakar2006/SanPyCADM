#!/bin/bash
# Pushes this folder to github.com/sprabhakar2006/sanpycadm and tags v1.0.0
# (the tag triggers the automated mac/win build + GitHub Release).
# FIRST create an EMPTY repo named "sanpycadm" on GitHub (no README).
# The readable backend source (backend/_protected_src) is git-ignored and
# is refused below if it ever sneaks into the index.
set -uo pipefail
cd "$(dirname "$0")"
[ -d .git ] || { git init -q && git branch -M main; }
git add -A
if git ls-files | grep -q "_protected_src"; then
  echo "!!! _protected_src is staged -- aborting so readable source is not published."
  git rm -r --cached -q backend/_protected_src
  echo "Removed it from the index; run this script again."
  read -p "Press Enter to close..."; exit 1
fi
git diff --cached --quiet || git -c user.email="sprabhakar2006@gmail.com" -c user.name="Sanjeev Prabhakar" commit -q -m "SanPyCADM: ${1:-update}"
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/sprabhakar2006/sanpycadm.git
git push -u --force origin main || { echo "!!! Push failed"; read -p "Press Enter..."; exit 1; }
git tag -f v1.0.0 && git push --force origin v1.0.0
echo "Done. Builds: https://github.com/sprabhakar2006/sanpycadm/actions"
echo "Release:     https://github.com/sprabhakar2006/sanpycadm/releases"
read -p "Press Enter to close..."
