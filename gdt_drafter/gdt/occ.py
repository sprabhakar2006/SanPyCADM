"""Small compatibility layer over the OCP (OpenCascade) bindings.

OCP 7.x exposes static methods with an `_s` suffix (TopoDS.Edge_s); OCP 8
moved the TopoDS casts to plain functions (TopoDS.Edge). Everything else
in this package goes through these helpers so either version works.
"""
from OCP.TopoDS import TopoDS


def _pick(owner, name):
    fn = getattr(owner, name + "_s", None)
    if fn is None:
        fn = getattr(owner, name)
    return fn


to_edge = _pick(TopoDS, "Edge")
to_face = _pick(TopoDS, "Face")
to_solid = _pick(TopoDS, "Solid")
to_vertex = _pick(TopoDS, "Vertex")


def static(owner, name):
    """Return owner.name_s if present, else owner.name."""
    return _pick(owner, name)
