#!/bin/bash
# Run this ONCE, right after unzipping SanPyCADM, before you
# ever double-click SanPyCADM.app -- just double-click this
# file itself (Finder may still warn about an unidentified developer the
# first time; that's expected for the same reason described below, and
# it's fine to allow).
#
# Why this is needed: macOS tags every file extracted from a downloaded
# zip with a "quarantine" flag. If an app still has that flag the very
# first time it's launched, Gatekeeper runs it from an isolated, read-only,
# randomly-named copy instead of its real location -- a feature Apple
# calls "App Translocation". SanPyCADM.app finds app.py (and
# everything else it needs) by looking right next to itself on disk, so a
# translocated copy can't see any of it and fails with a "could not find
# app.py" error, even though nothing was actually moved.
#
# This script just removes that quarantine flag from the whole SanPyCAD
# Brep folder, so macOS never translocates it in the first place.
# It doesn't touch anything else, doesn't need admin/sudo, and only needs
# to be run once per download (re-downloading or re-unzipping reapplies
# the flag, so re-run this if that ever happens).
DIR="$(cd "$(dirname "$0")" && pwd)"
xattr -cr "$DIR" 2>/dev/null
/usr/bin/osascript -e 'display alert "SanPyCADM" message "Done -- the download quarantine flag has been cleared. You can now double-click SanPyCADM.app normally, including the very first time."' >/dev/null 2>&1
