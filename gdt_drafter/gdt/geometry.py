"""Load a STEP/IGES/BREP file and recognise drawing-relevant features.

Recognised features (all in model millimetres):
  * planar faces       -> outward normal, area, offset
  * cylindrical groups -> holes, bosses/shaft diameters, radii (fillets/rounds)
  * counterbores       -> a larger coaxial hole sitting at the open end of a hole
  * hole depth / THRU  -> by probing the solid just beyond each end of the hole
"""
import contextlib
import math
import os
from dataclasses import dataclass, field

from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepTools import BRepTools
from OCP.BRep import BRep_Tool
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Cone
from OCP.GeomAdaptor import GeomAdaptor_Surface
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Pnt
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

from . import vec as V
from .occ import static, to_edge, to_face, to_solid

ANG_TOL = 1e-3      # direction tolerance (dot-product units)
LIN_TOL = 1e-3      # mm


@contextlib.contextmanager
def quiet():
    """Silence OpenCascade's console chatter (it writes straight to fd 1)."""
    try:
        fd = os.dup(1)
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, 1)
    except OSError:
        yield
        return
    try:
        yield
    finally:
        os.dup2(fd, 1)
        os.close(fd)
        os.close(null)


def load_shape(path):
    ext = os.path.splitext(path)[1].lower()
    with quiet():
        if ext in (".step", ".stp"):
            r = STEPControl_Reader()
            if r.ReadFile(path) != IFSelect_RetDone:
                raise ValueError("Could not read STEP file")
            r.TransferRoots()
            shape = r.OneShape()
        elif ext in (".iges", ".igs"):
            from OCP.IGESControl import IGESControl_Reader
            r = IGESControl_Reader()
            if r.ReadFile(path) != IFSelect_RetDone:
                raise ValueError("Could not read IGES file")
            r.TransferRoots()
            shape = r.OneShape()
        elif ext in (".brep", ".brp"):
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Shape
            shape = TopoDS_Shape()
            static(BRepTools, "Read")(shape, path, BRep_Builder())
        else:
            raise ValueError("Unsupported file type: " + ext)
    if shape is None or shape.IsNull():
        raise ValueError("The file contains no geometry")
    return shape


# ---------------------------------------------------------------- features

@dataclass
class Plane:
    """All coplanar faces sharing one outward normal (one datum-able surface)."""
    id: str
    normal: tuple          # outward unit normal
    point: tuple           # area-weighted centroid
    area: float
    offset: float          # normal . point
    faces: list = field(default_factory=list)
    pts: list = field(default_factory=list)   # sample points on the face boundaries
    parts: list = field(default_factory=list) # (centroid, area) of each face


@dataclass
class Cyl:
    """A group of cylindrical faces sharing axis, radius and side."""
    id: str
    axis: tuple            # canonical unit direction
    origin: tuple          # point on axis closest to the model origin
    radius: float
    internal: bool         # True = concave (hole / inside fillet)
    coverage: float        # radians of arc covered by the faces
    t0: float              # extent along axis (axis . point)
    t1: float
    area: float
    faces: list = field(default_factory=list)
    kind: str = ""         # hole | boss | radius
    thru: bool = False
    open_ends: tuple = (False, False)   # (at t0, at t1)
    cbore: dict = None     # {"radius":, "depth":, "id":}
    csink: dict = None     # {"diameter":, "angle":}
    absorbed: bool = False # counterbore that was folded into another hole

    @property
    def length(self):
        return self.t1 - self.t0

    def point_at(self, t):
        return V.add(self.origin, V.mul(self.axis, t))

    @property
    def center(self):
        return self.point_at(0.5 * (self.t0 + self.t1))


@dataclass
class Part:
    shape: object
    name: str
    bbox: tuple                          # (xmin, ymin, zmin, xmax, ymax, zmax)
    planes: list
    cyls: list
    n_faces: int
    solids: list

    @property
    def size(self):
        b = self.bbox
        return max(b[3] - b[0], b[4] - b[1], b[5] - b[2])

    def feature(self, fid):
        for f in self.planes + self.cyls:
            if f.id == fid:
                return f
        return None

    def classify(self, p):
        """True if point p lies inside material."""
        pnt = gp_Pnt(*p)
        for s in self.solids:
            c = BRepClass3d_SolidClassifier(s, pnt, 1e-6)
            if c.State() == TopAbs_IN:
                return True
        return False


def _face_normal(face, surf, u, v):
    props = BRepLProp_SLProps(surf, u, v, 1, 1e-7)
    if not props.IsNormalDefined():
        return None
    n = props.Normal()
    d = (n.X(), n.Y(), n.Z())
    if face.Orientation() == TopAbs_REVERSED:
        d = V.neg(d)
    return d


def _to_analytic(face, tol=2e-3):
    """Recognise B-spline / swept faces that are really planes or cylinders."""
    try:
        from OCP.GeomConvert import GeomConvert_SurfToAnaSurf
        conv = GeomConvert_SurfToAnaSurf(static(BRep_Tool, "Surface")(face))
        res = conv.ConvertToAnalytical(tol)
        if res is None:
            return None
        ad = GeomAdaptor_Surface(res)
        return ad
    except Exception:
        return None


def _cyl_extent_from_boundary(face, origin, axis):
    """(angular coverage, t0, t1) of a cylindrical face from its boundary points."""
    pts = _boundary_points(face, 16)
    ref = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = V.unit(V.cross(axis, ref))
    e2 = V.cross(axis, e1)
    angs, ts = [], []
    for p in pts:
        d = V.sub(p, origin)
        t = V.dot(d, axis)
        ts.append(t)
        r = V.sub(d, V.mul(axis, t))
        angs.append(math.atan2(V.dot(r, e2), V.dot(r, e1)) % (2 * math.pi))
    if not angs:
        return 0.0, 0.0, 0.0
    angs.sort()
    gaps = [(angs[(i + 1) % len(angs)] - angs[i]) % (2 * math.pi) for i in range(len(angs))]
    big = max(gaps) if len(angs) > 1 else 2 * math.pi
    coverage = 2 * math.pi - big if big > 0.2 else 2 * math.pi
    return coverage, min(ts), max(ts)


def list_bodies(shape):
    """Solids in the file, largest first: [(index, volume, solid)]."""
    from OCP.TopExp import TopExp_Explorer as _E
    out = []
    ex = _E(shape, TopAbs_SOLID)
    while ex.More():
        so = to_solid(ex.Current())
        ex.Next()
        g = GProp_GProps()
        try:
            static(BRepGProp, "VolumeProperties")(so, g)
            vol = abs(g.Mass())
        except Exception:
            vol = 0.0
        out.append([so, vol])
    out.sort(key=lambda x: -x[1])
    return [(i, v, so) for i, (so, v) in enumerate(out)]


def _boundary_points(face, per_edge=6):
    pts = []
    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        e = to_edge(exp.Current())
        exp.Next()
        try:
            a = BRepAdaptor_Curve(e)
            f, l = a.FirstParameter(), a.LastParameter()
            for i in range(per_edge + 1):
                p = a.Value(f + (l - f) * i / per_edge)
                pts.append((p.X(), p.Y(), p.Z()))
        except Exception:
            continue
    return pts


def analyse(shape, name="PART"):
    planes, raw_cyls, cones = [], [], []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while exp.More():
        face = to_face(exp.Current())
        exp.Next()
        idx += 1
        surf = BRepAdaptor_Surface(face, True)
        st = surf.GetType()
        ana = surf
        converted = False
        if st not in (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone):
            ana = _to_analytic(face)
            if ana is None:
                continue
            st = ana.GetType()
            converted = True
            if st not in (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone):
                continue
        props = GProp_GProps()
        static(BRepGProp, "SurfaceProperties")(face, props)
        area = props.Mass()
        if area < 1e-9:
            continue
        c = props.CentreOfMass()
        centroid = (c.X(), c.Y(), c.Z())
        umin, umax, vmin, vmax = static(BRepTools, "UVBounds")(face)
        um, vm = 0.5 * (umin + umax), 0.5 * (vmin + vmax)
        n = _face_normal(face, surf, um, vm)
        if n is None:
            continue
        if st == GeomAbs_Plane:
            n = V.unit(n)
            off = V.dot(n, centroid)
            bpts = _boundary_points(face)
            for pl in planes:
                if V.dot(pl.normal, n) > 1 - ANG_TOL and abs(pl.offset - off) < LIN_TOL * 10:
                    tot = pl.area + area
                    pl.point = V.add(V.mul(pl.point, pl.area / tot), V.mul(centroid, area / tot))
                    pl.area = tot
                    pl.faces.append(idx)
                    pl.pts.extend(bpts)
                    pl.parts.append((centroid, area))
                    break
            else:
                planes.append(Plane("", n, centroid, area, off, [idx], bpts, [(centroid, area)]))
        elif st == GeomAbs_Cylinder:
            cyl = ana.Cylinder()
            ax = cyl.Axis()
            loc = ax.Location()
            loc = (loc.X(), loc.Y(), loc.Z())
            d = ax.Direction()
            d = (d.X(), d.Y(), d.Z())
            p = surf.Value(um, vm)
            p = (p.X(), p.Y(), p.Z())
            foot = V.add(loc, V.mul(d, V.dot(V.sub(p, loc), d)))
            radial = V.sub(p, foot)
            internal = V.dot(n, radial) < 0
            dc = V.canonical(d)
            origin = V.sub(loc, V.mul(dc, V.dot(loc, dc)))
            ta = V.dot(V.add(loc, V.mul(d, vmin)), dc)
            tb = V.dot(V.add(loc, V.mul(d, vmax)), dc)
            coverage, t0, t1 = abs(umax - umin), min(ta, tb), max(ta, tb)
            if converted:
                coverage, t0, t1 = _cyl_extent_from_boundary(face, origin, dc)
            raw_cyls.append(dict(axis=dc, origin=origin, radius=cyl.Radius(), internal=internal,
                                 coverage=coverage, t0=t0, t1=t1, area=area, face=idx))
        else:  # cone — remembered for countersinks
            if converted:
                continue
            cone = surf.Cone()
            ax = cone.Axis()
            d = ax.Direction()
            loc = ax.Location()
            loc = (loc.X(), loc.Y(), loc.Z())
            dc = V.canonical((d.X(), d.Y(), d.Z()))
            cones.append(dict(axis=dc, origin=V.sub(loc, V.mul(dc, V.dot(loc, dc))),
                              half_angle=abs(cone.SemiAngle()), centroid=centroid,
                              vmin=vmin, vmax=vmax, ref_radius=cone.RefRadius(), area=area))

    # ---- group cylinders by (axis line, radius, side)
    groups = []
    for rc in raw_cyls:
        for g in groups:
            if (V.dot(g["axis"], rc["axis"]) > 1 - ANG_TOL
                    and V.norm(V.sub(g["origin"], rc["origin"])) < LIN_TOL * 10
                    and abs(g["radius"] - rc["radius"]) < LIN_TOL
                    and g["internal"] == rc["internal"]):
                g["coverage"] += rc["coverage"]
                g["t0"] = min(g["t0"], rc["t0"])
                g["t1"] = max(g["t1"], rc["t1"])
                g["area"] += rc["area"]
                g["faces"].append(rc["face"])
                break
        else:
            g = dict(rc)
            g["faces"] = [g.pop("face")]
            groups.append(g)

    cyls = []
    for g in groups:
        c = Cyl("", g["axis"], g["origin"], g["radius"], g["internal"], g["coverage"],
                g["t0"], g["t1"], g["area"], g["faces"])
        if c.coverage >= 1.5 * math.pi:          # keyways / cross-holes interrupt the surface
            c.kind = "hole" if c.internal else "boss"
        else:
            c.kind = "radius"
        cyls.append(c)

    solids = []
    se = TopExp_Explorer(shape, TopAbs_SOLID)
    while se.More():
        solids.append(to_solid(se.Current()))
        se.Next()

    box = Bnd_Box()
    try:
        static(BRepBndLib, "AddOptimal")(shape, box, False, False)
    except Exception:
        static(BRepBndLib, "Add")(shape, box)
    lo, hi = box.CornerMin(), box.CornerMax()
    bbox = (lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z())

    part = Part(shape, name, tuple(bbox), planes, cyls, idx, solids)
    _probe_holes(part)
    _counterbores(part)
    _countersinks(part, cones)

    # stable ids: planes by area, cylinders by radius
    part.planes.sort(key=lambda p: -p.area)
    for i, p in enumerate(part.planes, 1):
        p.id = "P%d" % i
    part.cyls.sort(key=lambda c: (c.kind, -c.radius, c.t0))
    for i, c in enumerate(part.cyls, 1):
        c.id = "C%d" % i
    return part


def _probe_holes(part):
    for c in part.cyls:
        if c.kind != "hole" or not part.solids:
            continue
        # probe far enough to clear a drill-point cone (~0.6 r long)
        eps = max(0.2, 0.75 * c.radius)
        a = part.classify(c.point_at(c.t0 - eps))
        b = part.classify(c.point_at(c.t1 + eps))
        c.open_ends = (not a, not b)
        c.thru = (not a) and (not b)


def _counterbores(part):
    holes = [c for c in part.cyls if c.kind == "hole"]
    for big in holes:
        for small in holes:
            if small is big or small.absorbed or big.radius <= small.radius + LIN_TOL:
                continue
            if V.dot(big.axis, small.axis) < 1 - ANG_TOL:
                continue
            if V.norm(V.sub(big.origin, small.origin)) > LIN_TOL * 10:
                continue
            # big must sit at one end of small and open to air on its far side
            if abs(big.t1 - small.t0) < 1e-2 and big.open_ends[0]:
                small.cbore = {"radius": big.radius, "depth": big.length, "id": big.id, "end": 0}
                small.open_ends = (True, small.open_ends[1])
                small.thru = small.open_ends[1]
                big.absorbed = True
            elif abs(big.t0 - small.t1) < 1e-2 and big.open_ends[1]:
                small.cbore = {"radius": big.radius, "depth": big.length, "id": big.id, "end": 1}
                small.open_ends = (small.open_ends[0], True)
                small.thru = small.open_ends[0]
                big.absorbed = True
            if big.absorbed:
                break


def _countersinks(part, cones):
    for c in part.cyls:
        if c.kind != "hole":
            continue
        for k in cones:
            if V.dot(k["axis"], c.axis) < 1 - ANG_TOL:
                continue
            if V.norm(V.sub(k["origin"], c.origin)) > LIN_TOL * 10:
                continue
            t = V.dot(k["centroid"], c.axis)
            if t < c.t0 - c.radius * 3 or t > c.t1 + c.radius * 3:
                continue
            # largest diameter of the cone
            r1 = k["ref_radius"] + k["vmin"] * math.sin(k["half_angle"])
            r2 = k["ref_radius"] + k["vmax"] * math.sin(k["half_angle"])
            rmax = max(abs(r1), abs(r2))
            if rmax > c.radius + LIN_TOL:
                end = 0 if abs(t - c.t0) < abs(t - c.t1) else 1
                # a cone at a blind end (drill point) is not a countersink
                if not c.open_ends[end] and not (c.thru):
                    continue
                c.csink = {"diameter": 2 * rmax, "angle": math.degrees(2 * k["half_angle"]), "end": end}
                break
