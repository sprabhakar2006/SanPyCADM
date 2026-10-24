# SanPyCADM

**Code-first CAD with real B-rep solids, SanPyCAD's function library, and mesh speed where you want it.**

Write a script, press Render, and the solid appears beside it. SanPyCADM merges
the [SanPyCAD](https://github.com/sprabhakar2006/SanPyCAD) geometry library
(`cube`, `prism`, `sweep_sec2path`, `helix`, `o_3d`, `fillet_by_offset`, ...) with an
[OpenCASCADE](https://dev.opencascade.org/) B-rep kernel, so shapes you build are
exact solids you can fillet, chamfer, split, pick edges and faces on, and export to STEP.
When an exact result is impractical (a 20-turn thread, a spring), switch that one shape to a
mesh and the boolean runs in a fraction of a second.

**Download:** [latest release](https://github.com/sprabhakar2006/sanpycadm/releases/latest)
(macOS Apple Silicon and Windows x64). No Python needed.

<!-- TODO: add a screen recording of a render here:  ![SanPyCADM](docs/demo.gif) -->

---

## Install

| Platform | Steps |
|---|---|
| **macOS** (Apple Silicon) | Download `SanPyCADM-mac-arm64.zip`, unzip, drag `SanPyCADM.app` to Applications. The app is not notarized: the first time, right-click it and choose **Open**. |
| **Windows** (x64) | Download `SanPyCADM-win-x64.zip`, unzip, run `SanPyCADM.exe`. If SmartScreen warns, choose **More info → Run anyway**. |

Settings and logs live in `~/Library/Application Support/SanPyCADM` (macOS) or
`%APPDATA%\SanPyCADM` (Windows). `SanPyCADM.log` there is the first place to look if
something misbehaves.

## Your first model

```python
s1 = prism(c1, path)                       # base solid
p1 = helix(7.5, 2.01, 20, 5)               # thread path
s2 = sweep_sec2path(sec1, p1, orientation=3)
show(difference(as_mesh(s1), as_mesh(s2)))
```

Open **tap** from the Examples list for the full threaded-cutter model.
Press **Render** (or Ctrl/Cmd+Enter). The line being executed is highlighted in the
editor, so you can see where a slow step is.

## Choose per shape: B-rep or mesh

| Use | When |
|---|---|
| `swp(x)` | You need an exact B-rep: fillets, chamfers, edge/face picking, STEP export. |
| `as_mesh(x)` | You want speed: long swept solids, threads, springs. Booleans run on [manifold3d](https://pypi.org/project/manifold3d/) and the result is flat-shaded, as in SanPyCAD. |

`difference()` switches to the fast mesh boolean as soon as one operand is a mesh.
If an exact cut silently removes nothing (an invalid multi-turn cutter), it falls back to
the mesh boolean and says so in the console. Pass `exact=True` to force the exact cut.

## What you get

- **Automatic B-rep conversion.** Stacks of closed cross-sections (from `prism`, `swp`, ...) become
  real B-rep solids when they reach `show()`, `union`, `difference`, `intersection`, `hull`,
  `split`, `fillet` or `chamfer`. Anything that can't be converted safely keeps working as a
  point list or mesh and is flagged in the console.
- **Pick Edges / Faces.** Click edges and faces in the 3D view to get their indices, apply fillets,
  and auto-pick seams.
- **Drawing.** Hidden-line 2D views of the model; export SVG and DXF.
- **Sketch on Face** and a 2D sketcher that sends profiles straight into your script.
- **Variables panel and GUI Functions.** Click a variable to jump to its line; run many functions
  from small panels that write real code into the editor.
- **Find function** palette (Cmd/Ctrl+K) with task-based search.
- **Notebook-style kernel.** Variables persist between renders, so an expensive step runs once
  and everything after it can be iterated on freely.
- **Export** STL, OBJ, STEP, SVG and DXF. Scripts save as plain `.py` files.
- **Runs offline.** The editor and 3D viewer are bundled.

## What it doesn't do yet

- No OpenSCAD-text mode and no `fo()`.
- No mesh/STL import (`import_mesh`, `import_profile(s)` and `resize` are not ported yet).
- Exact B-rep cuts with long, nearly touching multi-turn threads are unreliable in OpenCASCADE;
  use `as_mesh()` for those.
- Mesh results cannot be filleted or exported as STEP.

## Run from source

```bash
git clone https://github.com/sprabhakar2006/sanpycadm.git
cd sanpycadm
pip install -r requirements.txt
python3 app.py
```

Requires Python 3.10+ (`numpy`, `build123d`; `manifold3d` and `pywebview` recommended).
The geometry kernel ships in pre-built form under `backend/_protected/`.

## Build a standalone app yourself

```bash
pip install pyinstaller
python packaging/build_bundle.py
```

This produces `dist/SanPyCADM.app` (macOS) or `dist/SanPyCADM/` (Windows). PyInstaller cannot
cross-compile, so build on the platform you want. `.github/workflows/build-installers.yml` does
this on GitHub's macOS and Windows runners and attaches the zips to a release when you push a
tag (`git tag v1.0.1 && git push --tags`).

## Credits

SanPyCADM is built on the `ocad` geometry library by **Sanjeev Prabhakar**,
[build123d](https://build123d.readthedocs.io/) / OpenCASCADE (exact B-rep),
[manifold3d](https://pypi.org/project/manifold3d/) (fast mesh booleans),
[CodeMirror](https://codemirror.net/) and [Three.js](https://threejs.org/).

## License

[MIT](LICENSE).
