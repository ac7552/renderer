"""Builds the shoe templates the fitting room fits to a shop's side photo (app/javascript/lib/garments/templates.js)
and writes them to public/shoes/<name>.bin, with a contact sheet of renders per template.

Each template is one shoe of a family (a work boot, a court sneaker, a loafer...), modelled once with what a
shoe's made of: a sole with its edge, welt and tread; an upper that rises from it in walls and rounds over into
the toe box and the vamp; the opening, with a padded collar and the lining inside; a tongue, eyelets and laces
crossed over it; the seams of the toe cap, the vamp, the heel counter. In the browser the template is stretched,
height by height along its length, to the photo's outline, and painted with the shop's photos.

Run with Blender's Python module (pip install bpy==5.2.3):

    python3 script/shoes/build_templates.py [name ...]

The frame: the shoe's length along +z from heel (0) to toe (1), its height up +y from the floor (0), across +x
(the left shoe's outer side), in shoe lengths. Parts (the mesh's groups, the stage's materials): 0 the sole, 1 the
upper (and tongue), 2 the laces, 3 the collar and lining, 4 metal (eyelets, hooks, a penny's bar).
"""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "public" / "shoes"
SHEETS = ROOT / "tmp" / "shoes"

SOLE, UPPER, LACES, COLLAR, METAL = 0, 1, 2, 3, 4


# ---------------------------------------------------------------------------------------------------------------
# The families. Lengths are shares of the shoe's length (about 30 cm for a man's 9).
FAMILIES = {
    # A 6-inch work boot: padded collar, a lug sole on a welt, a toe cap, eyelets then speed hooks to the top.
    "workboot": dict(
        plan=dict(heel=0.135, waist=0.125, ball=0.178, toe=2.3, ball_at=0.7), welt=0.012,
        sole=dict(heel=0.115, fore=0.085, arch=0.012, breast=0.27, spring=0.025, lugs=False, welt=True, groove=False),
        top=[(0.0, 0.62), (0.3, 0.64), (0.36, 0.6), (0.42, 0.47), (0.55, 0.34), (0.7, 0.28), (0.82, 0.26), (0.92, 0.23), (1.0, 0.15)],
        throat=0.36, square=2.6, wall=0.3, collar=0.035, laced=True, lace_end=0.68, eyelets=9, hooks=3, metal=True,
        tongue=True, seams=["toecap"], bow=True, ankle=0.28, lean=0.05, lace=0.006),
    # A court sneaker on a cupsole: low collar, padded, a toe box, eyelets in the upper.
    "court": dict(
        plan=dict(heel=0.13, waist=0.13, ball=0.175, toe=2.2, ball_at=0.7), welt=0.008,
        sole=dict(heel=0.095, fore=0.08, arch=0.0, breast=None, spring=0.03, lugs=False, welt=False, groove=False),
        top=[(0.0, 0.29), (0.1, 0.3), (0.2, 0.27), (0.3, 0.29), (0.36, 0.3), (0.42, 0.28), (0.55, 0.24), (0.7, 0.2), (0.85, 0.17), (0.95, 0.14), (1.0, 0.1)],
        throat=0.36, square=2.6, wall=0.32, collar=0.03, laced=True, lace_end=0.66, eyelets=6, hooks=0, metal=False,
        tongue=True, seams=["toecap_court"], bow=True),
    # A high-top: the court's sole and toe, its collar up over the ankle.
    "hightop": dict(
        plan=dict(heel=0.13, waist=0.125, ball=0.172, toe=2.2, ball_at=0.7), welt=0.006,
        sole=dict(heel=0.085, fore=0.075, arch=0.0, breast=None, spring=0.03, lugs=False, welt=False, groove=False),
        top=[(0.0, 0.5), (0.25, 0.52), (0.33, 0.5), (0.4, 0.4), (0.5, 0.29), (0.65, 0.22), (0.82, 0.18), (0.94, 0.14), (1.0, 0.1)],
        throat=0.34, square=2.6, wall=0.34, collar=0.03, laced=True, lace_end=0.68, eyelets=8, hooks=0, metal=False,
        tongue=True, seams=["toecap_court"], bow=True, ankle=0.2, lean=0.03),
    # A Chelsea boot: elastic gores at the sides, a pull tab, a stacked heel.
    "chelsea": dict(
        plan=dict(heel=0.125, waist=0.112, ball=0.165, toe=2.4, ball_at=0.7), welt=0.006,
        sole=dict(heel=0.09, fore=0.045, arch=0.02, breast=0.27, spring=0.025, lugs=False, welt=True, groove=False),
        top=[(0.0, 0.6), (0.3, 0.6), (0.38, 0.55), (0.45, 0.4), (0.55, 0.3), (0.7, 0.23), (0.85, 0.19), (0.95, 0.15), (1.0, 0.09)],
        throat=0.38, square=2.7, wall=0.32, collar=0.012, laced=False, tongue=False, metal=False,
        seams=[], tab=True, ankle=0.26, lean=0.04),
    # A derby: a low lace-up dress shoe on a welted leather sole with a stacked heel.
    "derby": dict(
        plan=dict(heel=0.125, waist=0.11, ball=0.165, toe=2.4, ball_at=0.7), welt=0.009,
        sole=dict(heel=0.075, fore=0.035, arch=0.022, breast=0.27, spring=0.02, lugs=False, welt=True, groove=False),
        top=[(0.0, 0.25), (0.15, 0.24), (0.3, 0.22), (0.38, 0.24), (0.45, 0.22), (0.55, 0.19), (0.7, 0.16), (0.85, 0.14), (0.95, 0.11), (1.0, 0.07)],
        throat=0.4, square=2.8, wall=0.36, collar=0.012, laced=True, lace_end=0.6, eyelets=5, hooks=0, metal=False,
        tongue=True, seams=["toecap"], bow=True),
    # A penny loafer: a moccasin apron over the toe, a saddle strap across the vamp, a low heel.
    "loafer": dict(
        plan=dict(heel=0.125, waist=0.11, ball=0.165, toe=2.3, ball_at=0.7), welt=0.009,
        sole=dict(heel=0.075, fore=0.035, arch=0.022, breast=0.27, spring=0.02, lugs=False, welt=True, groove=False),
        top=[(0.0, 0.24), (0.15, 0.22), (0.35, 0.2), (0.48, 0.21), (0.55, 0.2), (0.7, 0.17), (0.85, 0.15), (0.95, 0.12), (1.0, 0.07)],
        throat=0.48, square=2.6, wall=0.4, collar=0.01, laced=False, tongue=False, metal=False,
        seams=["apron"], strap=True),
    # A runner: the court's upper on a thick, rockered midsole (more toe spring), a narrower toe, a padded collar
    # dipping below a raised heel tab.
    "runner": dict(
        plan=dict(heel=0.13, waist=0.122, ball=0.172, toe=2.0, ball_at=0.69), welt=0.006,
        sole=dict(heel=0.12, fore=0.075, arch=0.0, breast=None, spring=0.05, lugs=False, welt=False, groove=False),
        top=[(0.0, 0.33), (0.06, 0.28), (0.15, 0.26), (0.3, 0.29), (0.37, 0.3), (0.43, 0.28), (0.55, 0.24), (0.7, 0.2), (0.85, 0.165), (0.95, 0.13), (1.0, 0.09)],
        throat=0.36, square=2.3, wall=0.3, collar=0.035, laced=True, lace_end=0.66, eyelets=7, hooks=0, metal=False,
        tongue=True, seams=["toecap_court"], bow=True),
    # A chunky sneaker: a tall, flat platform sole, a wide plan, a heavily padded collar.
    "chunky": dict(
        plan=dict(heel=0.14, waist=0.14, ball=0.185, toe=2.3, ball_at=0.7), welt=0.008,
        sole=dict(heel=0.15, fore=0.12, arch=0.0, breast=None, spring=0.025, lugs=False, welt=False, groove=False),
        top=[(0.0, 0.37), (0.1, 0.38), (0.25, 0.36), (0.36, 0.37), (0.43, 0.34), (0.55, 0.3), (0.7, 0.26), (0.85, 0.22), (0.95, 0.18), (1.0, 0.13)],
        throat=0.36, square=2.5, wall=0.32, collar=0.04, laced=True, lace_end=0.66, eyelets=6, hooks=0, metal=False,
        tongue=True, seams=["toecap_court"], bow=True),
    # A ballet flat: a thin sole, a low topline round a wide opening.
    "flat": dict(
        plan=dict(heel=0.12, waist=0.105, ball=0.16, toe=2.2, ball_at=0.7), welt=0.004,
        sole=dict(heel=0.03, fore=0.022, arch=0.004, breast=None, spring=0.015, lugs=False, welt=False, groove=False),
        top=[(0.0, 0.18), (0.2, 0.15), (0.45, 0.12), (0.62, 0.12), (0.72, 0.13), (0.85, 0.12), (0.95, 0.1), (1.0, 0.06)],
        throat=0.7, square=2.4, wall=0.5, collar=0.008, laced=False, tongue=False, metal=False,
        seams=[]),
}


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def interp_points(points, z):
    xs, ys = zip(*points)
    # A smooth curve through the points (monotone cubic), not straight segments: a topline has no corners.
    from_ = np.array(xs), np.array(ys)
    return pchip(from_[0], from_[1], z)


def pchip(x, y, xq):
    x, y = np.asarray(x, float), np.asarray(y, float)
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros_like(y)
    for k in range(1, len(x) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    xq = np.clip(np.asarray(xq, float), x[0], x[-1])
    k = np.clip(np.searchsorted(x, xq) - 1, 0, len(x) - 2)
    t = (xq - x[k]) / h[k]
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * y[k] + h10 * h[k] * m[k] + h01 * y[k + 1] + h11 * h[k] * m[k + 1]


# ---------------------------------------------------------------------------------------------------------------
# The plan: the shoe seen from above, its half width along its length.
def half_width(plan, z):
    z = np.asarray(z, float)
    zh, zw, zb = 0.17, 0.43, plan["ball_at"]
    w = np.empty_like(z)
    heel = z < zh
    w[heel] = plan["heel"] * np.sqrt(np.clip(1 - ((zh - z[heel]) / zh) ** 2, 0, 1)) ** 0.85
    mid = (z >= zh) & (z < zw)
    w[mid] = plan["heel"] + (plan["waist"] - plan["heel"]) * smoothstep(zh, zw, z[mid])
    fore = (z >= zw) & (z < zb + 0.06)
    w[fore] = plan["waist"] + (plan["ball"] - plan["waist"]) * np.sin(np.clip((z[fore] - zw) / (zb + 0.06 - zw), 0, 1) * math.pi / 2)
    toe = z >= zb + 0.06
    q = plan["toe"]
    w[toe] = plan["ball"] * np.clip(1 - ((z[toe] - zb - 0.06) / (1 - zb - 0.06)) ** q, 0, 1) ** (1 / q)
    return w


def outline(plan, count, grow=0.0):
    """The plan's outline (x, z) from the heel's middle round the outer side to the toe and back, `count` points
    at even steps along it, grown outward by `grow` (the sole's edge)."""
    z = np.concatenate([np.linspace(0, 0.06, 200, endpoint=False), np.linspace(0.06, 0.94, 600, endpoint=False), np.linspace(0.94, 1, 201)])
    z = (1 - np.cos(z * math.pi)) / 2
    w = half_width(plan, z)
    right = np.stack([w, z], 1)
    left = np.stack([-w[::-1][1:-1], z[::-1][1:-1]], 1)
    loop = np.concatenate([right, left])
    if grow:
        # Outward along the outline's normal.
        d = np.roll(loop, -1, 0) - np.roll(loop, 1, 0)
        nrm = np.stack([d[:, 1], -d[:, 0]], 1)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        # (Pointing out: away from the middle.)
        sign = np.sign(np.sum(nrm * (loop - [0, 0.5]), 1, keepdims=True))
        loop = loop + nrm * sign * grow
    seg = np.linalg.norm(np.diff(np.concatenate([loop, loop[:1]]), axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)])
    total = arc[-1]
    want = np.linspace(0, total, count, endpoint=False)
    closed = np.concatenate([loop, loop[:1]])
    xs = np.interp(want, arc, closed[:, 0])
    zs = np.interp(want, arc, closed[:, 1])
    return np.stack([xs, zs], 1)


# ---------------------------------------------------------------------------------------------------------------
class Mesh:
    """Points and quads (or triangles), each face with its part."""

    def __init__(self):
        self.verts, self.faces, self.parts = [], [], []

    def add(self, pts):
        base = len(self.verts)
        self.verts.extend(map(tuple, np.asarray(pts).reshape(-1, 3)))
        return base

    def grid(self, pts, part, close_u=False, flip=False):
        """A grid of points (rows by columns) as quads; close_u joins the last column to the first."""
        pts = np.asarray(pts)
        rows, cols = pts.shape[:2]
        base = self.add(pts)
        idx = lambda r, c: base + r * cols + (c % cols)
        for r in range(rows - 1):
            for c in range(cols if close_u else cols - 1):
                f = (idx(r, c), idx(r, c + 1), idx(r + 1, c + 1), idx(r + 1, c))
                self.faces.append(f[::-1] if flip else f)
                self.parts.append(part)
        return base, rows, cols

    def face(self, f, part):
        self.faces.append(tuple(f))
        self.parts.append(part)


def tube(mesh, path, radius, part, sides=8, closed=False):
    """A round cord along a path of points."""
    path = np.asarray(path, float)
    n = len(path)
    rings = []
    prev = None
    for i in range(n):
        t = path[min(n - 1, i + 1)] - path[max(0, i - 1)]
        t /= np.linalg.norm(t) + 1e-12
        if prev is None:
            helper = np.array([0, 1, 0]) if abs(t[1]) < 0.9 else np.array([1, 0, 0])
            u = np.cross(t, helper)
        else:
            u = prev - t * np.dot(prev, t)
        u /= np.linalg.norm(u) + 1e-12
        v = np.cross(t, u)
        prev = u
        r = radius[i] if hasattr(radius, "__len__") else radius
        ang = np.linspace(0, 2 * math.pi, sides, endpoint=False)
        rings.append(path[i] + r * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v))
    rings = np.array(rings)
    base, rows, cols = mesh.grid(rings, part, close_u=True)
    if not closed:
        for end, r in ((0, 0), (1, rows - 1)):
            centre = mesh.add([rings[r].mean(0)])
            for c in range(cols):
                a, b = base + r * cols + c, base + r * cols + (c + 1) % cols
                mesh.face((centre, b, a) if end == 0 else (centre, a, b), part)


def torus(mesh, centre, axis, radius, thickness, part, sides=6, around=14):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    helper = np.array([0, 1, 0]) if abs(axis[1]) < 0.9 else np.array([1, 0, 0])
    u = np.cross(axis, helper); u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    ang = np.linspace(0, 2 * math.pi, around, endpoint=False)
    path = [np.asarray(centre) + radius * (math.cos(a) * u + math.sin(a) * v) for a in ang]
    path.append(path[0])
    tube(mesh, path, thickness, part, sides=sides, closed=True)


# ---------------------------------------------------------------------------------------------------------------
def build(name, spec, around=120, rows=30):
    plan, sole_spec = spec["plan"], spec["sole"]
    mesh = Mesh()
    top_h = lambda z: interp_points(spec["top"], z)
    # The sole: its bottom (the arch lifted between the heel and the ball, the toe sprung) and its top.
    def bottom(z):
        z = np.asarray(z, float)
        b = np.zeros_like(z)
        if sole_spec["arch"]:
            br = sole_spec["breast"] or 0.3
            b += sole_spec["arch"] * smoothstep(br - 0.005, br + 0.02, z) * (1 - smoothstep(0.5, 0.64, z))
        b += sole_spec["spring"] * smoothstep(0.8, 1.02, z) ** 1.6
        return b
    def sole_top(z):
        z = np.asarray(z, float)
        br = sole_spec["breast"] or 0.35
        heel, fore = sole_spec["heel"], sole_spec["fore"]
        # The heel's height to its breast, the forepart's after, down the waist between.
        h = fore + (heel - fore) * (1 - smoothstep(br - 0.02, 0.6, z))
        return bottom(z) * 0.6 + h

    # --- The upper -----------------------------------------------------------------------------------------
    ring = outline(plan, around)                      # (x, z) round the plan
    xs, zs = ring[:, 0], ring[:, 1]
    wall = spec["wall"]
    throat = spec["throat"]
    collar_r = spec["collar"]
    insole = sole_top(zs) + 0.02
    T = top_h(zs)                                     # the topline (open) or the top's height (closed) there
    S0 = sole_top(zs)
    # Where each point of the outline goes in to, on the shoe's middle line.
    zq = np.clip(zs, 0.05, 0.955)
    open_ = (1 - smoothstep(throat - 0.04, throat + 0.03, zs)) * smoothstep(-0.01, 0.025, zs)
    n_exp = spec["square"]
    t = np.linspace(0, 1, rows)
    pts = np.zeros((rows, around, 3))
    for r, tt in enumerate(t):
        # The closed shape: the wall up to a share of the height, then over the top in to the middle line.
        wall_top = S0 + wall * (T - S0)
        if tt <= 0.3:
            f = tt / 0.3
            cx, cz, cy = xs, zs, S0 + f * (wall_top - S0)
        else:
            # (Short of the middle line: the last strip across the top is the zip between the two sides, flat
            # and as wide as a row, so the top has no crease down its middle.)
            phi = (tt - 0.3) / 0.7 * (math.pi / 2)
            inward = (1 - np.cos(phi) ** (2 / n_exp)) * (1 - 0.06 * (tt - 0.3) / 0.7)
            up = np.sin(phi) ** (2 / n_exp)
            cx = xs * (1 - inward)
            cz = zs + (zq - zs) * inward
            # (The top's height where the point now is, not where it started on the outline: round the toe the
            # rows run in along the length, and would otherwise dip at its tip.)
            cy = wall_top + (top_h(cz) - wall_top) * up
        # The open shape: the wall to the topline, over the collar's roll, down the lining, across the insole.
        th = 0.012                                    # the upper's thickness
        if tt <= 0.45:
            f = tt / 0.45
            lean = 1 - 0.06 * f ** 2                  # leaning in a little to the topline
            ox, oz, oy = xs * lean, zs + (zq - zs) * 0.0, S0 + f * (T - S0)
        elif tt <= 0.6:
            a = (tt - 0.45) / 0.15 * math.pi          # the roll, half round, in towards the middle
            rr = th / 2 + collar_r
            k = 1 - (th + 2 * collar_r * 0.6) / np.maximum(np.abs(xs) + 1e-6, 0.05) * (1 - math.cos(a)) / 2
            ox = xs * 0.94 * k
            oz = zs + (zq - zs) * (1 - k) * 0.4
            oy = T + rr * math.sin(a)
        elif tt <= 0.85:
            f = (tt - 0.6) / 0.25
            k = 1 - (th + 2 * collar_r * 0.6) / np.maximum(np.abs(xs) + 1e-6, 0.05)
            ox = xs * 0.94 * k
            oz = zs + (zq - zs) * (1 - k) * 0.4
            oy = T + (insole - T) * smoothstep(0, 1, f)
        else:
            f = (tt - 0.85) / 0.15
            k = 1 - (th + 2 * collar_r * 0.6) / np.maximum(np.abs(xs) + 1e-6, 0.05)
            ox = xs * 0.94 * k * (1 - f)
            oz = zs + (zq - zs) * ((1 - k) * 0.4 + (1 - (1 - k) * 0.4) * f)
            oy = insole
        o = open_
        pts[r, :, 0] = cx * (1 - o) + ox * o
        pts[r, :, 2] = cz * (1 - o) + oz * o
        pts[r, :, 1] = cy * (1 - o) + oy * o
    # A shaft narrows to the ankle and leans forward over the heel counter's bulge (a boot's, a high-top's).
    ankle, lean = spec.get("ankle", 0.0), spec.get("lean", 0.0)
    if ankle or lean:
        h, z = pts[:, :, 1], pts[:, :, 2]
        shaft = 1 - smoothstep(0.32, 0.5, z)
        pts[:, :, 0] *= 1 - ankle * smoothstep(0.16, 0.5, h) * shaft
        back = 1 - smoothstep(0.08, 0.3, z)
        pts[:, :, 2] += (lean * smoothstep(0.14, 0.55, h) - 0.012 * np.exp(-((h - 0.13) / 0.07) ** 2)) * back
    base, R, C = mesh.grid(pts, UPPER, close_u=True, flip=True)
    # The lining and the collar's roll (in the opening) take the collar's part: re-mark their faces.
    nf = len(mesh.faces)
    first_face = nf - (R - 1) * C
    for r in range(R - 1):
        for c in range(C):
            ozone = (open_[c] + open_[(c + 1) % C]) / 2
            if ozone > 0.5 and t[r] >= 0.45:
                mesh.parts[first_face + r * C + c] = COLLAR
    # The middle line closed: each point of the last row zipped to its mirror across the shoe.
    last = base + (R - 1) * C
    half = C // 2
    for c in range(1, half):
        a, b = last + c, last + c + 1
        a2, b2 = last + (C - c), last + (C - c - 1)
        part = COLLAR if open_[c] > 0.5 else UPPER
        mesh.face((a, b, b2, a2), part)
    # (The ends: the heel's and the toe's points meet their neighbours.)
    mesh.face((last + 0, last + 1, last + C - 1), COLLAR if open_[0] > 0.5 else UPPER)
    mesh.face((last + half, last + half + 1, last + half - 1), UPPER)
    upper_pts = pts

    # --- The sole --------------------------------------------------------------------------------------------
    grow = spec["welt"]
    sring = outline(plan, around, grow=grow)
    sx, sz = sring[:, 0], sring[:, 1]
    zc = np.clip(sz, 0.06, 0.94)
    B, ST = bottom(sz), sole_top(np.clip(sz, 0, 1))
    bev = 0.01
    prof = []
    # Up from the middle of the underside, round its edge, up its side, over its top edge to the upper's foot.
    steps = [("in", 1.0), ("in", 0.6), ("in", 0.25), ("edge", 0.0), ("edge", 0.5), ("edge", 1.0)]
    side_rows = np.linspace(0, 1, 9)
    layers = []
    for kind, f in steps:
        if kind == "in":
            x = sx * (1 - f) * 0.93
            z = sz + (zc - sz) * f
            y = B
            layers.append((x, y, z))
        else:
            a = f * math.pi / 2
            x = sx * (1 - (1 - math.sin(a)) * bev / np.maximum(np.abs(sx), 0.05)) if False else sx - np.sign(sx) * 0 + 0 * f
            k = 1 - bev * (1 - math.sin(a)) / np.maximum(np.hypot(sx, sz - 0.5), 0.05)
            x = sx * k
            z = 0.5 + (sz - 0.5) * k
            y = B + bev * (1 - math.cos(a))
            layers.append((x, y, z))
    # The side wall.
    for f in side_rows[1:-1]:
        layers.append((sx, B + bev + f * (ST - B - 2 * bev), sz))
    # The top edge and in to the upper.
    for a in (0.5, 1.0):
        ang = a * math.pi / 2
        k = 1 - bev * (1 - math.cos(ang)) / np.maximum(np.hypot(sx, sz - 0.5), 0.05)
        layers.append((sx * k, ST - bev + bev * math.sin(ang), 0.5 + (sz - 0.5) * k))
    # Over the top, in to under the upper's wall.
    xs_in = outline(plan, around)
    layers.append((xs_in[:, 0] * 0.995, ST, xs_in[:, 1]))
    layers.append((xs_in[:, 0] * 0.9, ST - 0.003, xs_in[:, 1] * 0.98 + 0.01))
    spts = np.array([np.stack([x, np.broadcast_to(y, sx.shape), z], 1) for x, y, z in layers])
    # The sole's sidewall details: a welt's ledge. (Not a lug sole's blocks or a cupsole's groove: the side photo paints
    # the sole's own, and blocks modelled where its sole is smooth stand out as stripes.)
    side_from, side_to = 6, 6 + len(side_rows) - 2
    perim = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(sring, axis=0), axis=1))])
    for li in range(side_from, side_to):
        h = (spts[li, :, 1] - B) / np.maximum(ST - B, 1e-6)
        out = np.zeros(around)
        if sole_spec["lugs"]:
            # Blocks round the lower half, every 3 cm, a few millimetres proud.
            block = (np.sin(perim / 0.028 * 2 * math.pi) > -0.2).astype(float)
            out += 0.006 * block * (h < 0.55)
            out += 0.003 * (h > 0.62) * (h < 0.8)  # a ridge above them
        if sole_spec["groove"]:
            out -= 0.004 * np.exp(-((h - 0.55) / 0.06) ** 2)
        if sole_spec["welt"]:
            out += 0.004 * (h > 0.82)
        nrm = np.stack([sx, np.zeros(around), sz - 0.5], 1)
        nrm[:, 2] *= 0.35
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        spts[li] += nrm * out[:, None]
    sb, SR, SC = mesh.grid(spts, SOLE, close_u=True)
    # The underside's middle zipped.
    first = sb
    for c in range(1, around // 2):
        mesh.face((first + c + 1, first + c, first + (around - c), first + (around - c - 1)), SOLE)
    mesh.face((first + 1, first + 0, first + around - 1), SOLE)
    mesh.face((first + around // 2 - 1, first + around // 2, first + around // 2 + 1), SOLE)

    # --- The tongue, eyelets and laces ---------------------------------------------------------------------------
    def surface_at(z, x):
        """The upper's outside at (x, z) on its top (the closed shape): its height there."""
        zz = np.full(1, z)
        Tz, S0z = top_h(zz)[0], sole_top(zz)[0]
        wz = half_width(plan, zz)[0]
        wt = S0z + wall * (Tz - S0z)
        frac = min(0.999, abs(x) / max(wz, 1e-6))
        # Inverse of the superellipse over the top: inward = 1 - cos^(2/n) => cos = (1-inward)^(n/2)
        c = (1 - (1 - frac)) if False else frac
        cosv = c ** (n_exp / 2)
        phi = math.acos(min(1, cosv))
        return wt + (Tz - wt) * math.sin(phi) ** (2 / n_exp)

    if spec.get("tongue"):
        lace_end = spec["lace_end"]
        zt = np.linspace(throat - 0.02, lace_end + 0.03, 24)
        cols = np.linspace(-1, 1, 9)
        tp = np.zeros((len(zt), len(cols), 3))
        for i, z in enumerate(zt):
            wz = half_width(plan, np.array([z]))[0]
            tw = wz * 0.42 * (1 - 0.3 * (z - zt[0]) / (zt[-1] - zt[0]))
            for j, cf in enumerate(cols):
                x = cf * tw
                y = surface_at(z, x) + 0.004 - 0.003 * cf ** 2
                tp[i, j] = (x, y, z)
        # The tongue's top standing up out of the throat, a little above the collar, leaning back.
        lift = []
        Tth = top_h(np.array([throat]))[0]
        for k, f in enumerate(np.linspace(0, 1, 7)[1:]):
            z = zt[0] - 0.035 * f
            row = tp[0].copy()
            row[:, 2] = z
            row[:, 1] = tp[0, :, 1] + (Tth + 0.025 - tp[0, :, 1].max()) * f
            row[:, 0] *= 1 - 0.15 * f
            lift.append(row)
        tp = np.concatenate([np.array(lift[::-1]), tp])
        mesh.grid(tp, UPPER, flip=True)
        # (Its underside, a millimetre below.)
        under = tp.copy(); under[:, :, 1] -= 0.003
        mesh.grid(under, COLLAR)

    if spec.get("laced"):
        lace_end = spec["lace_end"]
        count = spec["eyelets"]
        hooks = spec.get("hooks", 0)
        zl = np.linspace(throat + 0.02, lace_end, count)
        eyes = []
        for i, z in enumerate(zl):
            wz = half_width(plan, np.array([z]))[0]
            e = wz * (0.5 - 0.16 * (i / max(1, count - 1)))
            yl = surface_at(z, e) + 0.002
            eyes.append(((-e, yl, z), (e, yl, z)))
        # Eyelets (or hooks, the top ones of a boot) in metal, or a stitched hole's ring in the upper.
        for i, (a, b) in enumerate(eyes):
            for p in (a, b):
                nrm = np.array([np.sign(p[0]) * 0.5, 1.0, 0.0])
                if spec.get("metal"):
                    if i < hooks:
                        # A speed hook: a post and its hook, standing out from the eyestay.
                        hook_path = [np.array(p), np.array(p) + [np.sign(p[0]) * 0.004, 0.006, 0], np.array(p) + [np.sign(p[0]) * 0.001, 0.011, -0.003]]
                        tube(mesh, hook_path, 0.003, METAL, sides=6)
                    else:
                        torus(mesh, p, nrm, 0.0075, 0.0026, METAL)
                else:
                    torus(mesh, p, nrm, 0.006, 0.002, UPPER)
        # The lace: straight across at the toe's end, crossed between the rows to the top.
        order = list(range(count - 1, -1, -1))
        lr = spec.get("lace", 0.0045)
        def arc(a, b, lift=0.006):
            a, b = np.array(a), np.array(b)
            mid = (a + b) / 2 + [0, lift, 0]
            return [a, (a + mid) / 2 + [0, lift * 0.3, 0], mid, (b + mid) / 2 + [0, lift * 0.3, 0], b]
        tube(mesh, arc(eyes[-1][0], eyes[-1][1]), lr, LACES)
        for i in range(count - 1, 0, -1):
            tube(mesh, arc(eyes[i][0], eyes[i - 1][1], 0.007), lr, LACES)
            tube(mesh, arc(eyes[i][1], eyes[i - 1][0], 0.009), lr, LACES)
        if spec.get("bow"):
            # A bow at the top: two loops and two ends hanging down the sides.
            a, b = np.array(eyes[0][0]), np.array(eyes[0][1])
            knot = (a + b) / 2 + [0, 0.012, -0.004]
            for sgn in (-1, 1):
                loop = [knot + [sgn * 0.002, 0, 0]]
                for ang in np.linspace(0.2, 2 * math.pi - 0.2, 14):
                    loop.append(knot + [sgn * (0.022 * (1 - math.cos(ang)) / 2 + 0.002), 0.006 * math.sin(ang) + 0.01 * (1 - math.cos(ang)) / 2 * 0.3, -0.012 * math.sin(ang) * 0.5])
                tube(mesh, loop, lr, LACES)
                end = [knot, knot + [sgn * 0.01, -0.004, 0.006], knot + [sgn * 0.018, -0.02, 0.012], knot + [sgn * 0.021, -0.038, 0.016]]
                tube(mesh, end, lr, LACES)
            tube(mesh, [a, (a + knot) / 2 + [0, 0.004, 0], knot], lr, LACES)
            tube(mesh, [b, (b + knot) / 2 + [0, 0.004, 0], knot], lr, LACES)

    if spec.get("tab"):
        # A pull tab up the back of the collar.
        Th = top_h(np.array([0.0]))[0]
        # (On the shaft's back as it leans: the backmost point of the upper near the top.)
        near_top = upper_pts[..., 1] > Th - 0.06
        z0 = float(upper_pts[..., 2][near_top].min()) + 0.002
        tab = np.array([[[x, Th - 0.03 + f * 0.065, z0 - 0.006 * f] for x in np.linspace(-0.018, 0.018, 4)] for f in np.linspace(0, 1, 6)])
        mesh.grid(tab, COLLAR)
        back = tab.copy(); back[:, :, 2] -= 0.003
        mesh.grid(back, COLLAR, flip=True)

    if spec.get("strap"):
        # The saddle strap across the vamp, and the slot (the penny's) cut in it.
        zs_ = np.linspace(throat + 0.035, throat + 0.085, 8)
        cols = np.linspace(-1, 1, 25)
        sp = np.zeros((len(zs_), len(cols), 3))
        for i, z in enumerate(zs_):
            wz = half_width(plan, np.array([z]))[0]
            for j, cf in enumerate(cols):
                x = cf * wz * 0.98
                y = surface_at(z, x) + 0.003
                if abs(cf) > 0.95:
                    y = surface_at(z, x * 0.98) - 0.03 * (abs(cf) - 0.95) / 0.05
                sp[i, j] = (x * (1.02 if abs(cf) > 0.9 else 1), y, z)
        mesh.grid(sp, UPPER, flip=True)

    # The shell (the upper's walls, collar and lining, and the sole), for the profile the page fits by: not the
    # tongue, laces or a bow, which stand above the topline and would squash the walls under them.
    shell = (upper_pts.reshape(-1, 3), spts.reshape(-1, 3))
    return mesh, dict(top_h=top_h, sole_top=sole_top, bottom=bottom, half=lambda z: half_width(plan, z), throat=throat, shell=shell)


# ---------------------------------------------------------------------------------------------------------------
# Seams: grooves pressed into the upper, with a row of stitches beside them. Only those on top (a toe cap, a
# moccasin's apron): the sides are painted from the shop's side photo, its own seams and stitching where they are.
def seam_curves(name, spec, f):
    top_h, sole_top, half = f["top_h"], f["sole_top"], f["half"]
    throat = spec["throat"]
    curves = []
    # Each: (kind, points as (x, y, z) on the side or (x, z) from above, depth, stitch rows)
    zz = np.linspace(0, 1, 200)
    if "toecap" in spec["seams"]:
        # Round the toe at three quarters of the length, over the top from side to side.
        z0 = 0.79
        pts = []
        for a in np.linspace(-1, 1, 40):
            w = half(np.array([z0]))[0]
            x = a * w
            z = z0 + 0.06 * (1 - a * a) ** 0.5 * 0.0 + 0.0
            pts.append((x, z + 0.015 * (1 - a * a)))
        curves.append(("top", pts, 0.005, 2))
    if "toecap_court" in spec["seams"]:
        z0 = 0.8
        pts = [(a * half(np.array([z0]))[0], z0 + 0.03 * (1 - a * a)) for a in np.linspace(-1, 1, 40)]
        curves.append(("top", pts, 0.003, 1))
    if "vamp" in spec["seams"]:
        # From the eyestay's foot down and back to the sole, either side.
        z_top = throat + 0.12
        pts = []
        for f2 in np.linspace(0, 1, 30):
            z = z_top - 0.12 * f2 ** 1.3
            y = sole_top(np.array([z]))[0] + (top_h(np.array([z]))[0] - sole_top(np.array([z]))[0]) * (0.75 * (1 - f2) + 0.02)
            pts.append((z, y))
        curves.append(("side", pts, 0.0045, 1))
    if "counter" in spec["seams"]:
        # The heel counter: up from the sole a third of the way along, curving back to the collar.
        pts = []
        for f2 in np.linspace(0, 1, 30):
            z = 0.2 - 0.17 * f2 ** 0.8
            y = sole_top(np.array([z]))[0] + (top_h(np.array([z]))[0] - sole_top(np.array([z]))[0]) * (0.05 + 0.78 * f2)
            pts.append((z, y))
        curves.append(("side", pts, 0.004, 1))
    if "collar_line" in spec["seams"]:
        pts = []
        for z in np.linspace(0.0, throat - 0.01, 30):
            y = top_h(np.array([z]))[0] - 0.045
            pts.append((z, y))
        curves.append(("side", pts, 0.002, 2))
    if "gore" in spec["seams"]:
        # The elastic gore: a tall narrow V from the topline down the side.
        zc = 0.27
        tp = top_h(np.array([zc]))[0]
        pts = [(zc - 0.05, tp), (zc - 0.012, tp - 0.17), (zc, tp - 0.19), (zc + 0.012, tp - 0.17), (zc + 0.05, tp)]
        dense = []
        for (a1, b1), (a2, b2) in zip(pts, pts[1:]):
            for f2 in np.linspace(0, 1, 12, endpoint=False):
                dense.append((a1 + (a2 - a1) * f2, b1 + (b2 - b1) * f2))
        dense.append(pts[-1])
        curves.append(("side", dense, 0.004, 0))
    if "apron" in spec["seams"]:
        # A moccasin's apron: a U over the vamp, from beside the strap round the toe and back.
        pts = []
        for a in np.linspace(-math.pi / 2, math.pi / 2, 40):
            z = 0.62 + 0.27 * math.cos(a)
            w = half(np.array([min(0.99, z)]))[0]
            pts.append((0.62 * w * math.sin(a), z))
        curves.append(("top", pts, -0.004, 2))  # raised: the moc's ridge
    return curves


def apply_seams(verts, normals, upper_mask, curves, part_side):
    """Each upper point pushed in (or out) by the seams near it, and stitched beside them."""
    v = verts
    disp = np.zeros(len(v))
    for kind, pts, depth, stitches in curves:
        pts = np.asarray(pts, float)
        if kind == "top":
            P = v[:, [0, 2]]
            # only what faces up
            facing = np.clip((normals[:, 1] - 0.2) / 0.4, 0, 1)
        else:
            P = v[:, [2, 1]]
            facing = np.clip((np.abs(normals[:, 0]) - 0.3) / 0.4, 0, 1)
        a, b = pts[:-1], pts[1:]
        ab = b - a
        L = np.linalg.norm(ab, axis=1)
        cum = np.concatenate([[0], np.cumsum(L)])
        best = np.full(len(v), np.inf)
        along = np.zeros(len(v))
        side = np.zeros(len(v))
        for i in range(len(a)):
            ap = P - a[i]
            t = np.clip((ap @ ab[i]) / (L[i] ** 2 + 1e-12), 0, 1)
            d = ap - t[:, None] * ab[i]
            dist = np.linalg.norm(d, axis=1)
            better = dist < best
            best[better] = dist[better]
            along[better] = cum[i] + t[better] * L[i]
            cr = ab[i, 0] * ap[:, 1] - ab[i, 1] * ap[:, 0]
            side[better] = np.sign(cr[better])
        w = 0.0065
        disp += -abs(depth) * np.exp(-(best / w) ** 2) * facing if depth > 0 else abs(depth) * np.exp(-(best / (w * 2.2)) ** 2) * facing
        # Stitches: dots in rows a few millimetres off the seam, every 4 mm.
        for k in range(stitches):
            off = 0.0045 + k * 0.004
            row = np.exp(-((best - off) / 0.0016) ** 2) * (np.cos(along / 0.006 * 2 * math.pi) > 0.1)
            disp += 0.0012 * row * facing
    disp *= upper_mask
    return verts + normals * disp[:, None]


# ---------------------------------------------------------------------------------------------------------------
def to_blender(mesh, name):
    import bpy
    me = bpy.data.meshes.new(name)
    # Blender's frame: length along X, across along -Y, up along Z.
    V = np.array(mesh.verts)
    bv = np.stack([V[:, 2], -V[:, 0], V[:, 1]], 1)
    me.from_pydata(bv.tolist(), [], [list(f) for f in mesh.faces])
    me.validate()
    # Every face's winding made consistent, facing out (the zips and caps were wound by hand).
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for part in range(5):
        me.materials.append(material(part))
    for poly, part in zip(me.polygons, mesh.parts):
        poly.material_index = part
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


_MATERIALS = {}
def material(part):
    import bpy
    if part in _MATERIALS:
        return _MATERIALS[part]
    m = bpy.data.materials.new(f"part{part}")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    colour = [(0.5, 0.25, 0.12, 1), (0.55, 0.3, 0.08, 1), (0.35, 0.2, 0.06, 1), (0.08, 0.05, 0.03, 1), (0.8, 0.6, 0.25, 1)][part]
    bsdf.inputs["Base Color"].default_value = colour
    bsdf.inputs["Roughness"].default_value = 0.35 if part == 4 else 0.75
    if part == 4:
        bsdf.inputs["Metallic"].default_value = 0.9
    _MATERIALS[part] = m
    return m


def finish(ob, spec, f, name):
    """Smoothed (one subdivision), the seams pressed in, normals out; returns the evaluated points, triangles and
    each triangle's part, in the template's frame."""
    import bpy
    mod = ob.modifiers.new("sub", "SUBSURF")
    mod.levels = mod.render_levels = 1
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="sub")
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    n = len(me.vertices)
    co = np.zeros(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    V = np.stack([-co[:, 1], co[:, 2], co[:, 0]], 1)
    me.update()
    nb = np.zeros(n * 3); me.vertices.foreach_get("normal", nb); nb = nb.reshape(-1, 3)
    N = np.stack([-nb[:, 1], nb[:, 2], nb[:, 0]], 1)
    part_of = np.full(n, -1)
    for p in me.polygons:
        for vi in p.vertices:
            if part_of[vi] in (-1, UPPER):
                part_of[vi] = p.material_index if part_of[vi] == -1 else part_of[vi]
    upper_mask = (part_of == UPPER).astype(float)
    V = apply_seams(V, N, upper_mask, seam_curves(name, spec, f), part_of)
    co = np.stack([V[:, 2], -V[:, 0], V[:, 1]], 1).reshape(-1)
    me.vertices.foreach_set("co", co)
    me.update()
    return ob


def export(ob, name, spec, f):
    """public/shoes/<name>.bin: a small JSON header (its length first, 4 bytes), then the points (Uint16 x3, over the
    box in the header), the triangles (Uint16 or Uint32 x3) and each triangle's part (Uint8)."""
    import bpy
    deps = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.vertices)
    co = np.zeros(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    V = np.stack([-co[:, 1], co[:, 2], co[:, 0]], 1)
    tris = np.zeros(len(me.loop_triangles) * 3, dtype=np.int64); me.loop_triangles.foreach_get("vertices", tris)
    tris = tris.reshape(-1, 3)
    parts = np.zeros(len(me.loop_triangles), dtype=np.int64); me.loop_triangles.foreach_get("material_index", parts)
    # Triangles grouped by part (so each part is one draw).
    order = np.argsort(parts, kind="stable")
    tris, parts = tris[order], parts[order]
    # Winding: outward (the stage computes its normals from it).
    lo, hi = V.min(0), V.max(0)
    q = np.round((V - lo) / (hi - lo) * 65535).astype(np.uint16)
    # The profile the fitting reads: along the shoe (64 bins), the upper's top, the sole's top and bottom, the
    # upper's half width.
    bins = 64
    zn = (V[:, 2] - lo[2]) / (hi[2] - lo[2])
    vpart = np.full(n, -1)
    for tri, p in zip(tris, parts):
        for vi in tri:
            if vpart[vi] == -1 or p == SOLE:
                vpart[vi] = p
    prof = {"top": [], "soleTop": [], "bottom": [], "half": []}
    up_pts, sole_pts = f["shell"]
    bu = np.minimum(bins - 1, ((up_pts[:, 2] - lo[2]) / (hi[2] - lo[2]) * bins).astype(int))
    bs = np.minimum(bins - 1, ((sole_pts[:, 2] - lo[2]) / (hi[2] - lo[2]) * bins).astype(int))
    for k in range(bins):
        up, so = bu == k, bs == k
        prof["top"].append(float(up_pts[up, 1].max()) if up.any() else None)
        prof["soleTop"].append(float(sole_pts[so, 1].max()) if so.any() else None)
        prof["bottom"].append(float(sole_pts[so, 1].min()) if so.any() else None)
        prof["half"].append(float(np.abs(up_pts[up, 0]).max()) if up.any() else None)
    for key in prof:
        vals = prof[key]
        known = [i for i, v in enumerate(vals) if v is not None]
        prof[key] = [round(float(np.interp(i, known, [vals[j] for j in known])), 5) for i in range(bins)]
    groups = []
    for p in range(5):
        idx = np.nonzero(parts == p)[0]
        if len(idx):
            groups.append([int(idx[0]) * 3, int(len(idx)) * 3, p])
    header = {
        "name": name, "box": [lo.round(6).tolist(), hi.round(6).tolist()], "count": n, "triangles": int(len(tris)),
        "groups": groups, "profile": prof, "throat": spec["throat"], "laced": bool(spec.get("laced")),
    }
    head = json.dumps(header, separators=(",", ":")).encode()
    head += b" " * ((4 - len(head) % 4) % 4)
    big = n > 65535
    body = q.tobytes() + (b"\0\0" if (q.nbytes % 4) else b"") + (tris.astype(np.uint32 if big else np.uint16).tobytes())
    tri_bytes = tris.astype(np.uint32 if big else np.uint16).nbytes
    pad = (4 - (q.nbytes + (2 if q.nbytes % 4 else 0) + tri_bytes) % 4) % 4
    body += b"\0" * pad + parts.astype(np.uint8).tobytes()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.bin", "wb") as fh:
        fh.write(struct.pack("<I", len(head)))
        fh.write(head)
        fh.write(body)
    ev.to_mesh_clear()
    return n, len(tris)


def main(names):
    import bpy
    sys.path.insert(0, str(Path(__file__).parent))
    from render import render_sheet
    SHEETS.mkdir(parents=True, exist_ok=True)
    for name in names:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _MATERIALS.clear()
        spec = FAMILIES[name]
        mesh, f = build(name, spec)
        ob = to_blender(mesh, name)
        finish(ob, spec, f, name)
        n, t = export(ob, name, spec, f)
        size = (OUT / f"{name}.bin").stat().st_size
        print(f"{name}: {n} points, {t} triangles, {size / 1024:.0f} KB")
        render_sheet(str(SHEETS / f"{name}.png"))


def write_index():
    """public/shoes/index.json: each template's profile and box (a few kilobytes, fetched first), so the page can
    choose the template whose side matches the photo's before fetching it."""
    index = {}
    for path in sorted(OUT.glob("*.bin")):
        with open(path, "rb") as fh:
            head_length = struct.unpack("<I", fh.read(4))[0]
            head = json.loads(fh.read(head_length))
        index[head["name"]] = {k: head[k] for k in ("box", "profile", "throat", "laced")}
        # (Its content's hash, on its link: a rebuilt template isn't read from a browser's old copy.)
        import hashlib
        index[head["name"]]["v"] = hashlib.md5(path.read_bytes()).hexdigest()[:10]
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv[1:] or list(FAMILIES))
    write_index()
