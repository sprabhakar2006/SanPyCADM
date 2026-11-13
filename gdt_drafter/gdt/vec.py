"""Tiny 3-D / 2-D vector helpers on plain tuples (keeps numpy out of the deps)."""
import math


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, k):
    return tuple(x * k for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return tuple(x / n for x in a) if n > 1e-15 else tuple(a)


def neg(a):
    return tuple(-x for x in a)


def parallel(a, b, tol=1e-4):
    """True when unit vectors a and b are parallel or anti-parallel."""
    return abs(abs(dot(a, b)) - 1.0) < tol


def same_dir(a, b, tol=1e-4):
    return dot(a, b) > 1.0 - tol


def perpendicular(a, b, tol=1e-4):
    return abs(dot(a, b)) < tol


def canonical(d):
    """Flip a direction so its first significant component is positive."""
    for c in d:
        if abs(c) > 1e-9:
            return d if c > 0 else neg(d)
    return d


def dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def seg_dist(p, a, b):
    """Distance from 2-D point p to segment ab."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-24:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
