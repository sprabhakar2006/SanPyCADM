@echo off
rem run_sanpycadm.bat -- alternate Windows launcher for
rem SanPyCADM (the B-rep-first copy of SanPyCAD, built on
rem build123d/OpenCASCADE instead of triangle meshes).
rem
rem Double-click "SanPyCADM.vbs" instead for the normal
rem experience (no console window, error alerts instead of a raw
rem traceback). This .bat file is a simpler backup for two cases: (1)
rem some locked-down/corporate Windows machines block .vbs files from
rem running at all (VBScript has a long history of being abused by
rem malware, so this is a common security policy), and (2) you'd rather
rem see the console output live (e.g. while troubleshooting) instead of
rem just a log file. It does the same thing "SanPyCADM.vbs"
rem does -- just with a visible console window, and without the
rem pre-flight numpy/build123d check (if a package is
rem missing, Python's own error shows directly in this window).

setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 app.py
  goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
  python app.py
  goto :done
)

where python3 >nul 2>nul
if %errorlevel%==0 (
  python3 app.py
  goto :done
)

echo Could not find Python 3 on PATH.
echo Install it from https://www.python.org/downloads/
echo (check "Add python.exe to PATH" during setup), then re-run this file.
pause
exit /b 1

:done
if errorlevel 1 (
  echo.
  echo SanPyCADM exited with an error -- see the messages above.
  echo If a package is missing, try: pip install numpy build123d pywebview
  pause
)
