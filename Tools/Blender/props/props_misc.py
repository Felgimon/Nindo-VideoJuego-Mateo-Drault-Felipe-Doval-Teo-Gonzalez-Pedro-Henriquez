"""Nindo - misc props & interactables (lights, gameplay objects, village / farm / lake dressing).

All builders follow STYLE.md: origin at footprint centre, ground z = 0, front faces -Y,
flat faceted palette colours, glow_* colours on the emissive slot.
Special pivots:
  * lantern_hanging : origin at the TOP hook, geometry hangs below z = 0.
  * lantern_string  : origin at the centre of the line between the two rope ends (z = 0), sags below.
  * boat_small      : z = 0 is the water surface (hull dips below).
"""
import math
import bmesh
from mathutils import Vector, Matrix

import nindo_lib as L

TAU = 2.0 * math.pi


# =====================================================================================
#  helpers
# =====================================================================================
def front_phase(n):
    """Ring phase so that a flat side (not a corner) faces -Y."""
    return -math.pi / 2.0 + math.pi / n


def paint(mb, faces, color, slot=None):
    """Colour faces; glow_* -> emissive slot, everything else -> palette slot (unless slot given)."""
    faces = [f for f in faces if f is not None and f.is_valid]
    if not faces:
        return
    if slot is None:
        slot = L.SLOT_EMISSIVE if color.startswith("glow_") else L.SLOT_PALETTE
    mb._tag(faces, color, slot)


def skin(mb, rings, color, colors=None, cap_top=True, cap_bottom=False, top_color=None,
         bottom_color=None, closed=True, face_color=None, slot=None):
    """Skins a list of vertex rings.  A ring of length 1 is a pole (fan).
    colors[k] colours band k; face_color(k, i) -> colour overrides per face.
    Returns a Part with .bands (list of face lists), .top, .bottom."""
    bm = mb.bm
    vr = [[bm.verts.new(Vector(p)) for p in r] for r in rings]
    bands = []
    for a, b in zip(vr[:-1], vr[1:]):
        fs = []
        if len(a) == 1 and len(b) == 1:
            bands.append(fs)
            continue
        n = max(len(a), len(b))
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            if len(a) == 1:
                fs.append(bm.faces.new((a[0], b[j], b[i])))
            elif len(b) == 1:
                fs.append(bm.faces.new((a[i], a[j], b[0])))
            else:
                fs.append(bm.faces.new((a[i], a[j], b[j], b[i])))
        bands.append(fs)
    top = bot = None
    if cap_top and len(vr[-1]) > 2:
        top = bm.faces.new(vr[-1])
    if cap_bottom and len(vr[0]) > 2:
        bot = bm.faces.new(list(reversed(vr[0])))
    p = mb._new([v for r in vr for v in r], color, slot, None)
    if colors:
        for k, c in enumerate(colors):
            if c and k < len(bands):
                paint(mb, bands[k], c, slot)
    if face_color:
        for k, fs in enumerate(bands):
            for i, f in enumerate(fs):
                c = face_color(k, i)
                if c:
                    paint(mb, [f], c, slot)
    if top is not None and top_color:
        paint(mb, [top], top_color, slot)
    if bot is not None and bottom_color:
        paint(mb, [bot], bottom_color, slot)
    p.bands, p.top, p.bottom = bands, top, bot
    return p


def lathe(mb, prof, n, color, colors=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1),
          phase=None, cap_top=True, cap_bottom=False, top_color=None, bottom_color=None,
          twist=0.0, jitter=0.0, face_color=None, slot=None):
    """Surface of revolution.  prof = [(r, z), ...] bottom -> top (r = 0 -> pole)."""
    if phase is None:
        phase = front_phase(n)
    M = L._mat(loc, rot, scale)
    rings = []
    for k, (r, z) in enumerate(prof):
        if r <= 1e-6:
            rings.append([M @ Vector((0, 0, z))])
            continue
        ph = phase + twist * k
        ring = []
        for i in range(n):
            a = ph + TAU * i / n
            p = Vector((r * math.cos(a), r * math.sin(a), z))
            if jitter:
                p += Vector((mb.rng.uniform(-jitter, jitter), mb.rng.uniform(-jitter, jitter),
                             mb.rng.uniform(-jitter, jitter) * 0.6))
            ring.append(M @ p)
        rings.append(ring)
    return skin(mb, rings, color, colors, cap_top, cap_bottom, top_color, bottom_color,
                face_color=face_color, slot=slot)


def tube(mb, pts, radius, n, color, closed=False, cap=True, cap_color=None, phase=0.0,
         up=(0, 0, 1), face_color=None, slot=None):
    """Polyline tube (ropes, logs, handles).  radius can be a list (taper)."""
    pts = [Vector(p) for p in pts]
    m = len(pts)
    T = []
    for i in range(m):
        if closed:
            t = pts[(i + 1) % m] - pts[i - 1]
        else:
            t = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        T.append(t.normalized())
    ref = Vector(up)
    if abs(ref.dot(T[0])) > 0.95:
        ref = Vector((1, 0, 0)) if abs(T[0].x) < 0.9 else Vector((0, 1, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    radii = list(radius) if isinstance(radius, (list, tuple)) else [radius] * m
    rings = []
    for i, p in enumerate(pts):
        N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        rings.append([p + radii[i] * (math.cos(phase + TAU * k / n) * N + math.sin(phase + TAU * k / n) * B)
                      for k in range(n)])
    if closed:
        rings.append(rings[0])
    part = skin(mb, rings, color, cap_top=(cap and not closed), cap_bottom=(cap and not closed),
                top_color=cap_color, bottom_color=cap_color, face_color=face_color, slot=slot)
    return part


def slab(mb, pts2d, origin, u, v, depth, color, side_color=None, back=True, back_color=None, slot=None):
    """Polygon (CCW in the u,v plane) extruded along u x v by `depth` (from the plane)."""
    o, u, v = Vector(origin), Vector(u), Vector(v)
    w = u.cross(v).normalized()
    bm = mb.bm
    b = [bm.verts.new(o + u * x + v * y) for x, y in pts2d]
    t = [bm.verts.new(o + u * x + v * y + w * depth) for x, y in pts2d]
    n = len(pts2d)
    sides = []
    for i in range(n):
        j = (i + 1) % n
        sides.append(bm.faces.new((b[i], b[j], t[j], t[i])))
    front = bm.faces.new(t)
    bk = bm.faces.new(list(reversed(b))) if back else None
    p = mb._new(b + t, color, slot, None)
    if side_color:
        paint(mb, sides, side_color, slot)
    if bk is not None and back_color:
        paint(mb, [bk], back_color, slot)
    p.front, p.back, p.sides = front, bk, sides
    return p


def faces_facing(faces, d, thr=0.8):
    d = Vector(d).normalized()
    out = []
    for f in faces:
        f.normal_update()
        if f.normal.dot(d) > thr:
            out.append(f)
    return out


def inset(mb, faces, thickness, depth, color):
    """Insets faces individually (window/panel); the inner faces get `color`."""
    for f in faces:
        f.normal_update()
    bmesh.ops.inset_individual(mb.bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
    paint(mb, faces, color)
    return faces


def flame(mb, base, r, h, color, n=5, lean=(0.0, 0.0), twist=0.7, bulge=1.25, phase=0.0, simple=False):
    """Faceted, slightly twisted flame tongue (simple=True -> 3 rings, cheaper)."""
    x, y, z = base
    if simple:
        prof = [(r, 0.0), (r * bulge, h * 0.35), (0.0, h)]
    else:
        prof = [(r, 0.0), (r * bulge, h * 0.3), (r * 0.5, h * 0.66), (0.0, h)]
    rings = []
    for k, (rr, zz) in enumerate(prof):
        t = zz / h
        ox, oy = lean[0] * t * t, lean[1] * t * t
        if rr <= 0:
            rings.append([(x + ox, y + oy, z + zz)])
        else:
            ph = phase + twist * k
            rings.append([(x + ox + rr * math.cos(ph + TAU * i / n), y + oy + rr * math.sin(ph + TAU * i / n), z + zz)
                          for i in range(n)])
    return skin(mb, rings, color, cap_top=False, cap_bottom=True)


def spark(mb, loc, r, color="glow_warm"):
    """Tiny octahedron (8 tris)."""
    x, y, z = loc
    return lathe(mb, [(0.0, z - r), (r, z), (0.0, z + r)], 4, color, loc=(x, y, 0), phase=0.3)


def rock(mb, loc, r, h, color, n=5, top_color=None, squash=(1, 1), jit=0.25, phase=None):
    """Chunky faceted stone (two rings + top cap)."""
    x, y, z = loc
    ph = mb.rng.uniform(0, TAU) if phase is None else phase
    rings = []
    for (rr, zz) in ((r, -0.02), (r * 0.62, h)):
        ring = []
        for i in range(n):
            a = ph + TAU * i / n + mb.rng.uniform(-0.2, 0.2)
            q = rr * (1 + mb.rng.uniform(-jit, jit))
            ring.append((x + q * math.cos(a) * squash[0], y + q * math.sin(a) * squash[1],
                         z + zz + (mb.rng.uniform(-jit, jit) * h * 0.4 if zz > 0 else 0)))
        rings.append(ring)
    return skin(mb, rings, color, cap_top=True, top_color=top_color or color)


def cap_roof(mb, z0, r, n, edge_h, peak_h, upturn, top_r, color, under_color=None, edge_color=None,
             top_color=None, concave=0.93, mid=(0.55, 0.6), loc=(0, 0), phase=None, face_color=None):
    """Polygonal (hex) lantern roof with upturned corners.  2n verts per ring (corners + mids)."""
    if phase is None:
        phase = front_phase(n) - math.pi / n  # corners aligned with a front_phase(n) body's corners
    cx, cy = loc
    m = math.cos(math.pi / n) * concave

    def rp(rc, z, up, rm=None):
        rm = rc * m if rm is None else rm
        pts = []
        for i in range(2 * n):
            a = phase + math.pi * i / n
            corner = i % 2 == 0
            rr = rc if corner else rm
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a), z + (up if corner else 0.0)))
        return pts
    zm = z0 + edge_h + (peak_h - edge_h) * mid[1]
    rings = [[(cx, cy, z0 + 0.03)],
             rp(r, z0, upturn * 0.85),
             rp(r * 1.01, z0 + edge_h, upturn),
             rp(r * mid[0], zm, upturn * 0.25),
             rp(top_r, z0 + peak_h, 0.0, top_r)]
    cols = [under_color or color, edge_color or color, color, color]
    return skin(mb, rings, color, cols, cap_top=True, top_color=top_color or color, face_color=face_color)


def gable_roof(mb, cx, cy, z_eave, w, d, rise, thick, color, axis="x", sag=0.0, upturn=0.0, nx=2,
               under_color=None, edge_color=None, top_fn=None):
    """Two-slab gable roof.  w = length along the ridge, d = eave-to-eave depth.
    Ridge along X (axis='x') or Y.  Each slab is a closed solid; faces are coloured by position:
    top surface = color (or top_fn(face)), underside = under_color, edges/gable ends = edge_color."""
    def P(u, v, z):
        return (cx + u, cy + v, z) if axis == "x" else (cx + v, cy + u, z)
    xs = [-w / 2.0 + w * i / (nx - 1) for i in range(nx)]
    parts = []
    zr = z_eave + rise
    for side in (-1, 1):
        rings = []
        for u in xs:
            up = upturn * (abs(u) / (w / 2.0)) ** 2
            vm, zm = side * d / 4.0, z_eave + rise * 0.5 - sag + up * 0.3
            ve, ze = side * d / 2.0, z_eave + up
            vr = -side * 0.03
            rings.append([P(u, vr, zr), P(u, vm, zm), P(u, ve, ze),
                          P(u, ve, ze - thick), P(u, vm, zm - thick), P(u, vr, zr - thick)])
        parts.append(skin(mb, rings, color, cap_top=True, cap_bottom=True))
    for p in parts:
        for f in p.faces:
            c = f.calc_center_median()
            v = (c.y - cy) if axis == "x" else (c.x - cx)
            t = min(1.0, abs(v) / (d / 2.0))
            ztop = zr * (1 - t) + z_eave * t - sag * math.sin(math.pi * t) * 0.8
            uu = abs((c.x - cx) if axis == "x" else (c.y - cy))
            ztop += upturn * (uu / (w / 2.0)) ** 2 * t
            if abs(c.z - (ztop - thick)) < thick * 0.4:
                paint(mb, [f], under_color or color)
            elif abs(c.z - ztop) < thick * 0.4:
                paint(mb, [f], top_fn(f) if top_fn else color)
            else:
                paint(mb, [f], edge_color or color)
    return parts


def bar(mb, a, b, w, color, h=None):
    """Square beam between two points."""
    return mb.plank_line(a, b, w, h if h is not None else w, color)


def blk(mb, base, size, color, top=None, rot=(0, 0, 0), open_bottom=True, jitter=0.0):
    """Box whose bottom centre is at `base`; optional top colour; bottom face removed (unseen)."""
    p = mb.box_base(base, size, color, rot=rot)
    fs = p.faces
    for f in fs:
        f.normal_update()
    if top:
        paint(mb, [f for f in fs if f.normal.z > 0.9], top)
    if open_bottom:
        bmesh.ops.delete(mb.bm, geom=[f for f in fs if f.normal.z < -0.99], context="FACES_ONLY")
        p.verts = [v for v in p.verts if v.is_valid]
    if jitter:
        p.jitter(jitter)
    return p


def shide(mb, x, y, ztop, h=0.26, w=0.07, color="paper", facing=(0, -1, 0)):
    """Zigzag paper streamer (shide) hanging from ztop, as a thin closed slab in the XZ plane."""
    s = h / 4.0
    pts = [(-w / 2, 0), (w / 2, 0), (w / 2, -s), (w * 1.0, -s), (w * 1.0, -2 * s), (w * 0.0, -2 * s),
           (w * 0.0, -3 * s), (w * 0.5, -3 * s), (w * 0.5, -4 * s), (-w * 0.5, -4 * s), (-w * 0.5, -3 * s),
           (-w * 1.0, -3 * s), (-w * 1.0, -2 * s), (-w / 2, -2 * s)]
    # simplify to an 8-point lightning bolt
    pts = [(-w * 0.5, 0.0), (w * 0.5, 0.0), (w * 0.5, -s * 1.3), (w * 1.1, -s * 1.3), (w * 0.2, -s * 4),
           (w * 0.2, -s * 2.5), (-w * 0.5, -s * 2.5)]
    return slab(mb, pts, (x, y + 0.008, ztop), (1, 0, 0), (0, 0, 1), 0.016, color)


# =====================================================================================
#  LIGHTS
# =====================================================================================
def build_lantern_stone(seed):
    mb = L.MeshBuilder("lantern_stone", seed)
    n = 6
    lathe(mb, [(0.37, 0.0), (0.37, 0.12), (0.27, 0.19)], n, "stone", ["stone", "stone_light"],
          top_color="stone_light")
    lathe(mb, [(0.115, 0.17), (0.105, 0.62), (0.16, 0.67), (0.30, 0.79), (0.31, 0.865), (0.25, 0.88)], n,
          "stone", ["stone", "stone", "stone_dark", "stone_light", "stone_light"], top_color="stone_light")
    fb = lathe(mb, [(0.22, 0.86), (0.22, 1.30)], n, "stone_light", cap_top=False)
    sides = fb.bands[0]
    fbk = faces_facing(sides, (0, -1, 0), 0.9) + faces_facing(sides, (0, 1, 0), 0.9)
    inset(mb, fbk, 0.03, -0.035, "glow_warm")
    inset(mb, [f for f in sides if f not in fbk], 0.06, -0.025, "glow_warm")
    moss = {(3, 1), (3, 2), (3, 7), (2, 1)}
    cap_roof(mb, 1.27, 0.5, n, 0.07, 0.28, 0.06, 0.1, "stone", under_color="stone_dark",
             edge_color="stone", concave=0.98,
             face_color=lambda k, i: "stone_moss" if (k, i) in moss else None)
    lathe(mb, [(0.1, 1.54), (0.06, 1.58), (0.09, 1.625), (0.0, 1.71)], n, "stone_light",
          ["stone", "stone_light", "stone_light"])
    mb.collider_capsule(0.35, 1.7)
    mb.tag("light_warm")
    mb.set("light_offset", [0.0, 0.0, 1.08])
    return mb.finish()


def build_lantern_stone_tall(seed):
    mb = L.MeshBuilder("lantern_stone_tall", seed)
    n = 6
    # kiso (base) with carved lotus petals (alternating faces)
    lathe(mb, [(0.47, 0.0), (0.47, 0.15), (0.3, 0.27)], n, "stone", ["stone_dark", "stone"],
          top_color="stone_light", face_color=lambda k, i: "stone_light" if (k == 1 and i % 2 == 0) else None)
    # sao (pillar) with a fushi node
    lathe(mb, [(0.13, 0.25), (0.13, 1.0), (0.17, 1.07), (0.12, 1.56)], n,
          "stone", ["stone", "stone_light", "stone"], cap_top=False)
    # chudai (platform) with lotus flare
    lathe(mb, [(0.12, 1.55), (0.36, 1.69), (0.36, 1.77), (0.27, 1.785)], n, "stone",
          ["stone", "stone_light", "stone_light"], top_color="stone_light",
          face_color=lambda k, i: "stone_dark" if (k == 0 and i % 2 == 1) else None)
    # hibukuro (firebox)
    fb = lathe(mb, [(0.26, 1.765), (0.26, 2.22)], n, "stone_light", cap_top=False)
    sides = fb.bands[0]
    fbk = faces_facing(sides, (0, -1, 0), 0.9) + faces_facing(sides, (0, 1, 0), 0.9)
    inset(mb, fbk, 0.035, -0.04, "glow_warm")
    inset(mb, [f for f in sides if f not in fbk], 0.07, -0.03, "glow_warm")
    # kasa (roof) with upturned warabite corners
    moss = {(3, 0), (3, 1), (3, 6), (2, 0), (3, 11)}
    cap_roof(mb, 2.19, 0.6, n, 0.08, 0.3, 0.1, 0.11, "stone", under_color="stone_dark", concave=0.97,
             face_color=lambda k, i: "stone_moss" if (k, i) in moss else None)
    ph = front_phase(n) - math.pi / n
    for i in range(n):
        a = ph + TAU * i / n
        x, y = math.cos(a) * 0.58, math.sin(a) * 0.58
        lathe(mb, [(0.05, 2.3), (0.0, 2.42)], 3, "stone_light", loc=(x, y, 0), cap_top=False, phase=a)
    # ukebana + hoju finial
    lathe(mb, [(0.12, 2.47), (0.07, 2.52), (0.11, 2.56), (0.0, 2.66)], n,
          "stone_light", ["stone", "stone_light", "stone_light"])
    mb.collider_capsule(0.4, 2.6)
    mb.tag("light_warm")
    mb.set("light_offset", [0.0, 0.0, 2.0])
    return mb.finish()


def paper_lantern(mb, cx, cy, ztop, r, h, n=8, rim="black", band=None, slot=None):
    """Round paper lantern hanging with its top at ztop.  Glowing paper, dark rims.
    band = colour of the upper/lower taper bands (None = glow)."""
    rr = r * 0.48
    z = ztop
    prof = [(rr, z), (rr * 1.05, z - h * 0.09), (r * 0.86, z - h * 0.22), (r, z - h * 0.42),
            (r, z - h * 0.58), (r * 0.86, z - h * 0.78), (rr * 1.05, z - h * 0.91), (rr, z - h)]
    cols = [rim, band or "glow_warm", "glow_warm", "glow_warm", "glow_warm", band or "glow_warm", rim]
    p = lathe(mb, list(reversed(prof)), n, rim, list(reversed(cols)), loc=(cx, cy, 0), cap_top=True,
              cap_bottom=True, top_color=rim, bottom_color=rim)
    return p


def build_lantern_post(seed):
    mb = L.MeshBuilder("lantern_post", seed)
    mb.box_base((0, 0, 0), (0.34, 0.34, 0.16), "stone").jitter(0.015)
    mb.box_base((0, 0, 0.1), (0.15, 0.15, 2.12), "wood_dark")
    # small gabled roof on the post top
    gable_roof(mb, 0.0, 0.0, 2.1, 0.62, 0.58, 0.2, 0.05, "wood", axis="x",
               under_color="wood_dark", edge_color="wood_black")
    mb.box((0, 0, 2.31), (0.68, 0.08, 0.07), "wood_black")
    # arm + brace
    mb.box((0.33, 0, 2.02), (0.66, 0.08, 0.08), "wood")
    bar(mb, (0.06, 0, 1.7), (0.34, 0, 2.0), 0.06, "wood")
    mb.box((0.6, 0, 1.96), (0.035, 0.035, 0.08), "black")
    paper_lantern(mb, 0.6, 0.0, 1.93, 0.2, 0.44, n=8)
    mb.collider_capsule(0.2, 2.3)
    mb.tag("light_warm")
    mb.set("light_offset", [0.6, 0.0, 1.71])
    return mb.finish()


def chochin(mb, cx, cy, ztop, scale=1.0, n=8, red="lantern_red", rim="black", tassel=True):
    """Elongated red-banded chochin hanging below ztop (its top hook)."""
    s = scale
    mb.box((cx, cy, ztop - 0.03 * s), (0.04 * s, 0.04 * s, 0.06 * s), rim)
    lathe(mb, [(0.11 * s, ztop - 0.12 * s), (0.10 * s, ztop - 0.06 * s)], n, rim, loc=(cx, cy, 0),
          cap_bottom=False, top_color=rim)
    prof = [(0.11, -0.51), (0.16, -0.47), (0.19, -0.40), (0.2, -0.33), (0.2, -0.30), (0.195, -0.24),
            (0.165, -0.17), (0.11, -0.12)]
    prof = [(r * s, ztop + z * s) for r, z in prof]
    cols = [red, "glow_warm", "glow_warm", red, "glow_warm", "glow_warm", red]
    lathe(mb, prof, n, red, cols, loc=(cx, cy, 0), cap_top=False, cap_bottom=False)
    lathe(mb, [(0.10 * s, ztop - 0.555 * s), (0.11 * s, ztop - 0.505 * s)], n, rim, loc=(cx, cy, 0),
          cap_top=False, cap_bottom=True, bottom_color=rim)
    if tassel:
        lathe(mb, [(0.0, ztop - 0.6 * s), (0.035 * s, ztop - 0.55 * s)], 4, red, loc=(cx, cy, 0),
              cap_top=True)


def build_lantern_hanging(seed):
    mb = L.MeshBuilder("lantern_hanging", seed)
    chochin(mb, 0.0, 0.0, 0.0)
    mb.collider_none()
    mb.tag("light_warm")
    mb.set("light_offset", [0.0, 0.0, -0.32])
    return mb.finish()


def build_lantern_string(seed):
    mb = L.MeshBuilder("lantern_string", seed)
    N = 12
    pts = []
    for i in range(N + 1):
        x = -3.0 + 6.0 * i / N
        pts.append((x, 0.0, -0.5 * (1 - (x / 3.0) ** 2)))
    tube(mb, pts, 0.03, 3, "rope", cap=True, phase=math.pi / 2)
    for k, x in enumerate((-2.0, -1.0, 0.0, 1.0, 2.0)):
        z = -0.5 * (1 - (x / 3.0) ** 2) - 0.02
        red = k % 2 == 0
        n = 6
        prof = [(0.075, z - 0.36), (0.145, z - 0.27), (0.145, z - 0.11), (0.075, z - 0.02)]
        band = "lantern_red" if red else "glow_warm"
        lathe(mb, prof, n, band, [band, "glow_warm", band], loc=(x, 0, 0), cap_top=True, cap_bottom=True,
              top_color="black", bottom_color="black", rot=(0, 0, 0))
    mb.collider_none()
    mb.tag("light_warm")
    mb.set("light_offset", [0.0, 0.0, -0.7])
    return mb.finish()


def fire_cluster(mb, z, r, h, simple_side=True, seed_phase=0.0):
    """Chunky faceted fire: main tongue + outer red tongues + bright yellow core tongues."""
    flame(mb, (0, 0, z), r, h, "glow_fire", n=5, lean=(0.03, -0.02), phase=0.3 + seed_phase)
    for k in range(3):
        a = math.radians(30 + 120 * k) + seed_phase
        flame(mb, (math.cos(a) * r * 0.85, math.sin(a) * r * 0.85, z + 0.02), r * 0.48, h * 0.62, "glow_red",
              n=4, lean=(math.cos(a) * r * 0.45, math.sin(a) * r * 0.45), phase=a, simple=True)
    for k in range(2):
        a = math.radians(100 + 180 * k) + seed_phase
        flame(mb, (math.cos(a) * r * 0.45, math.sin(a) * r * 0.45, z + 0.04), r * 0.5, h * 0.8, "glow_spirit",
              n=4, lean=(math.cos(a) * r * 0.55, math.sin(a) * r * 0.55), phase=a, simple=True)


def build_torch_brazier(seed):
    mb = L.MeshBuilder("torch_brazier", seed)
    for k in range(3):
        a = math.radians(90 + 120 * k)
        foot = (math.cos(a) * 0.38, math.sin(a) * 0.38, 0.0)
        top = (math.cos(a) * 0.15, math.sin(a) * 0.15, 0.8)
        bar(mb, foot, top, 0.065, "iron")
    pts = []
    for k in range(3):
        a = math.radians(90 + 120 * k)
        r = 0.38 + (0.15 - 0.38) * (0.3 / 0.8)
        pts.append((math.cos(a) * r, math.sin(a) * r, 0.3))
    for k in range(3):
        bar(mb, pts[k], pts[(k + 1) % 3], 0.045, "iron")
    # bowl
    lathe(mb, [(0.13, 0.74), (0.31, 0.84), (0.4, 0.98), (0.33, 1.0), (0.3, 0.93)], 8, "iron",
          ["iron", "iron", "iron_light", "iron"], cap_bottom=True, top_color="glow_fire")
    fire_cluster(mb, 0.9, 0.23, 0.56)
    spark(mb, (0.12, -0.05, 1.55), 0.035)
    spark(mb, (-0.1, 0.08, 1.66), 0.03, "glow_spirit")
    mb.collider_capsule(0.3, 1.3)
    mb.tag("light_fire")
    mb.set("light_offset", [0.0, 0.0, 1.15])
    return mb.finish()


def build_campfire(seed):
    mb = L.MeshBuilder("campfire", seed)
    lathe(mb, [(0.46, 0.0), (0.36, 0.035), (0.24, 0.045)], 7, "dirt_dark", ["dirt_dark", "black"],
          top_color="glow_fire")
    k = 8
    for i in range(k):
        a = TAU * i / k + 0.2
        r = 0.55
        rock(mb, (math.cos(a) * r, math.sin(a) * r, 0), 0.16, 0.17 + 0.05 * (i % 2),
             "stone" if i % 3 else "stone_dark", top_color="stone_light" if i % 2 else "stone",
             squash=(1.0, 0.85))
    for i in range(4):
        a = TAU * i / 4 + 0.4
        foot = Vector((math.cos(a) * 0.38, math.sin(a) * 0.38, 0.03))
        tip = Vector((math.cos(a) * 0.05, math.sin(a) * 0.05, 0.4))
        tube(mb, [foot - (tip - foot) * 0.1, tip], 0.06, 5, "trunk", cap_color="wood_pale")
    fire_cluster(mb, 0.04, 0.22, 0.76, seed_phase=0.5)
    spark(mb, (0.1, -0.12, 0.98), 0.03)
    mb.collider_none()
    mb.tag("light_fire")
    mb.set("light_offset", [0.0, 0.0, 0.45])
    return mb.finish()



# =====================================================================================
#  GAMEPLAY / INTERACTABLES
# =====================================================================================
def shimenawa(mb, a, b, sag, r, segs=6, sides=4, colors=("rope", "straw")):
    """Thick twisted straw rope between a and b (sagging), twist suggested by alternating facets."""
    a, b = Vector(a), Vector(b)
    pts = []
    for i in range(segs + 1):
        t = i / segs
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(p)
    rr = [r * (0.75 + 0.25 * math.sin(math.pi * i / segs)) for i in range(segs + 1)]
    return tube(mb, pts, rr, sides, colors[0], cap_color=colors[1],
                face_color=lambda k, i: colors[1] if (k + i) % 2 == 0 else None)


def build_shrine_checkpoint(seed):
    mb = L.MeshBuilder("shrine_checkpoint", seed)
    # stone base (two tiers)
    blk(mb, (0, 0, 0), (1.16, 1.0, 0.22), "stone_dark", top="stone").jitter(0.012)
    blk(mb, (0, 0.13, 0.2), (0.76, 0.62, 0.46), "stone", top="stone_light")
    # hokora house with a glowing open front
    body = blk(mb, (0, 0.14, 0.64), (0.56, 0.46, 0.6), "wood")
    for f in body.faces:
        f.normal_update()
    inset(mb, [f for f in body.faces if f.normal.y < -0.9], 0.07, -0.16, "glow_spirit")
    for sx in (-1, 1):
        blk(mb, (sx * 0.29, -0.1, 0.64), (0.08, 0.08, 0.62), "wood_red")
    # copper roof + ridge + chigi
    gable_roof(mb, 0.0, 0.14, 1.22, 0.86, 0.9, 0.32, 0.06, "copper_green", sag=0.03,
               under_color="wood_dark", edge_color="wood_black")
    mb.box((0, 0.14, 1.55), (0.9, 0.09, 0.08), "wood_black")
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box((sx * 0.43, 0.14 + sy * 0.06, 1.65), (0.035, 0.05, 0.32), "wood_black", rot=(sy * 28, 0, 0))
    # shimenawa with shide across the front
    shimenawa(mb, (-0.36, -0.15, 1.18), (0.36, -0.15, 1.18), 0.07, 0.04, segs=6, sides=3)
    shide(mb, -0.14, -0.17, 1.12)
    shide(mb, 0.14, -0.17, 1.12)
    # incense bowl with glowing ember
    lathe(mb, [(0.09, 0.2), (0.16, 0.29), (0.17, 0.35), (0.13, 0.36)], 6, "stone_dark",
          ["stone_dark", "stone_light", "stone_light"], loc=(0, -0.3, 0), top_color="glow_fire")
    mb.collider_box((1.2, 1.0, 1.8))
    mb.tag("light_warm", "smoke", "nonstatic")
    mb.set("light_offset", [0.0, -0.45, 0.9])
    return mb.finish()


def arc_blade(mb, cy, cz, r_out, r_in, a0, a1, segs, thick, color, taper=True, y_off=0.0):
    """Crescent-shaped arc slab in the XZ plane (portal swirl arm)."""
    rings = []
    for k in range(segs + 1):
        t = k / segs
        a = a0 + (a1 - a0) * t
        ro = r_out
        ri = r_in + (r_out - r_in) * (t ** 1.6 if taper else 0.0) * 0.92
        c, s_ = math.cos(a), math.sin(a)
        y0, y1 = cy + y_off - thick / 2, cy + y_off + thick / 2
        rings.append([(ro * c, y0, cz + ro * s_), (ri * c, y0, cz + ri * s_),
                      (ri * c, y1, cz + ri * s_), (ro * c, y1, cz + ro * s_)])
    return skin(mb, rings, color, cap_top=True, cap_bottom=True)


def build_portal_ring(seed):
    mb = L.MeshBuilder("portal_ring", seed)
    cz, R, Ri = 1.85, 1.8, 1.45
    # stepped base
    blk(mb, (0, 0, 0), (4.3, 2.3, 0.16), "stone_dark", top="stone").jitter(0.02)
    blk(mb, (0, 0, 0.14), (3.5, 1.5, 0.17), "stone", top="stone_light")
    # support blocks clamping the ring
    for sx in (-1, 1):
        blk(mb, (sx * 1.38, 0, 0.29), (0.62, 0.86, 0.62), "stone_dark", top="stone_moss")
    # ring: chamfered section swept around the Y axis
    n = 18
    sec = [(Ri, -0.26), (R - 0.08, -0.26), (R, -0.18), (R, 0.18), (R - 0.08, 0.26), (Ri, 0.26)]
    rings = []
    ph = -math.pi / 2 + math.pi / n
    for k in range(n):
        a = ph + TAU * k / n
        c, s_ = math.cos(a), math.sin(a)
        rings.append([(r * c, y, cz + r * s_) for r, y in sec])
    rings.append(rings[0])
    ring = skin(mb, rings, "stone", cap_top=False, cap_bottom=False)
    # colour: outer rim darker, inner face lighter; runes on alternate front/back faces
    fronts, backs = [], []
    for k, fs in enumerate(ring.bands):
        for i, f in enumerate(fs):
            if i == 0:
                (fronts if k % 2 == 0 else []).append(f)
            elif i == 4:
                (backs if k % 2 == 0 else []).append(f)
            elif i in (1, 3):
                paint(mb, [f], "stone_dark")
            elif i == 5:
                paint(mb, [f], "stone_light")
    for f in fronts + backs:
        f.normal_update()
    inset(mb, fronts + backs, 0.07, -0.025, "glow_portal")
    # keystone with a glowing gem
    blk(mb, (0, 0, cz + R - 0.22), (0.52, 0.66, 0.5), "stone_light", top="stone_moss", open_bottom=False)
    spark(mb, (0, -0.36, cz + R + 0.02), 0.1, "glow_portal")
    # dark vortex backing disc
    lathe(mb, [(Ri + 0.02, -0.025), (Ri + 0.02, 0.025)], 16, "cloth_indigo", rot=(90, 0, 0),
          loc=(0, 0, cz), cap_top=True, cap_bottom=True, top_color="cloth_indigo", bottom_color="cloth_indigo")
    # swirl arms (outer cyan, middle white, inner cyan) + white core
    for k in range(4):
        a0 = TAU * k / 4 + 0.3
        arc_blade(mb, 0, cz, 1.4, 1.05, a0, a0 + math.radians(78), 4, 0.1, "glow_portal")
    for k in range(3):
        a0 = TAU * k / 3 + 1.2
        arc_blade(mb, 0, cz, 0.95, 0.6, a0 + math.radians(85), a0, 3, 0.12, "glow_white")
    for k in range(3):
        a0 = TAU * k / 3 + 0.4
        arc_blade(mb, 0, cz, 0.52, 0.24, a0, a0 + math.radians(95), 3, 0.14, "glow_portal")
    lathe(mb, [(0.2, -0.08), (0.2, 0.08)], 6, "glow_white", rot=(90, 0, 0), loc=(0, 0, cz),
          cap_top=True, cap_bottom=True)
    mb.collider_box((4.3, 2.3, 0.31))
    mb.tag("light_cool", "nonstatic")
    mb.set("light_offset", [0.0, 0.0, cz])
    return mb.finish()


def build_seal_pedestal(seed):
    mb = L.MeshBuilder("seal_pedestal", seed)
    n = 8
    lathe(mb, [(0.52, 0.0), (0.52, 0.14), (0.42, 0.21)], n, "stone_dark", ["stone_dark", "stone"],
          top_color="stone", face_color=lambda k, i: "stone_moss" if (k == 0 and i in (2, 3, 6)) else None)
    col = lathe(mb, [(0.3, 0.19), (0.29, 0.5), (0.33, 0.54), (0.33, 0.6), (0.28, 0.64), (0.28, 0.84)], n,
                "stone", ["stone", "stone_dark", "stone_light", "stone_dark", "stone"], cap_top=False)
    inset(mb, [f for i, f in enumerate(col.bands[0]) if i % 2 == 0], 0.06, -0.015, "glow_spirit")
    lathe(mb, [(0.28, 0.82), (0.47, 0.93), (0.47, 1.05), (0.42, 1.1), (0.31, 1.1), (0.29, 1.05)], n, "stone",
          ["stone_dark", "stone", "stone_light", "stone_light", "stone_dark"], top_color="glow_spirit",
          face_color=lambda k, i: "stone_moss" if (k == 2 and i == 3) else None)
    mb.collider_box((1.04, 1.04, 1.1))
    return mb.finish()


def medallion(mb, cz, face, rim, edge, n=10):
    """Thick upright disc (0.5 m) with a raised rim, facing -Y; returns centre z."""
    prof = [(0.0, -0.05), (0.19, -0.05), (0.19, -0.075), (0.25, -0.075), (0.25, 0.075), (0.19, 0.075),
            (0.19, 0.05), (0.0, 0.05)]
    lathe(mb, prof, n, face, [face, rim, rim, edge, rim, rim, face], rot=(90, 0, 0), loc=(0, 0, cz),
          phase=math.pi / 2, cap_top=False)
    # little bail on top
    blk(mb, (0, 0, cz + 0.235), (0.09, 0.07, 0.07), edge, top=rim, open_bottom=False)


def relief(mb, pts, cz, color, depth, z0=0.0, side_color=None):
    """Extruded polygon (x,z relative to medallion centre) on BOTH faces of the medallion."""
    slab(mb, pts, (0, -0.05 + 0.004 - z0, cz), (1, 0, 0), (0, 0, 1), depth, color, side_color=side_color,
         back=False)
    slab(mb, pts, (0, 0.05 - 0.004 + z0, cz), (-1, 0, 0), (0, 0, 1), depth, color, side_color=side_color,
         back=False)


def octa_pts(cx, cz, r, n=8):
    return [(cx + r * math.cos(TAU * i / n + math.pi / n), cz + r * math.sin(TAU * i / n + math.pi / n))
            for i in range(n)]


def build_key_seal_mountain(seed):
    mb = L.MeshBuilder("key_seal_mountain", seed)
    cz = 0.25
    medallion(mb, cz, "stone", "gold", "gold_dark")
    relief(mb, [(-0.155, -0.1), (0.155, -0.1), (0.02, 0.115), (-0.035, 0.03), (-0.085, 0.06)], cz,
           "stone_light", 0.03, side_color="stone_dark")
    relief(mb, [(-0.012, 0.072), (0.0, 0.045), (0.028, 0.06), (0.062, 0.04), (0.02, 0.115)], cz,
           "glow_spirit", 0.016, z0=0.026)
    relief(mb, octa_pts(-0.1, 0.1, 0.035, 6), cz, "glow_spirit", 0.02)
    relief(mb, [(-0.17, -0.1), (0.17, -0.1), (0.15, -0.135), (-0.15, -0.135)], cz, "gold_dark", 0.02)
    mb.collider_none()
    mb.tag("nonstatic")
    return mb.finish()


def build_key_seal_lake(seed):
    mb = L.MeshBuilder("key_seal_lake", seed)
    cz = 0.25
    medallion(mb, cz, "water_deep", "gold", "copper_green")
    wave = [(-0.175, -0.07), (-0.11, -0.01), (-0.05, -0.0), (-0.07, 0.04), (-0.02, 0.07), (0.04, 0.04),
            (0.03, -0.02), (0.1, -0.03), (0.175, -0.07), (0.15, -0.12), (-0.15, -0.12)]
    relief(mb, wave, cz, "water_shallow", 0.03, side_color="copper_green")
    relief(mb, [(-0.07, 0.04), (-0.02, 0.07), (0.04, 0.04), (-0.01, 0.045)], cz, "glow_water", 0.014, z0=0.026)
    relief(mb, [(-0.14, -0.06), (0.14, -0.06), (0.12, -0.075), (-0.12, -0.075)], cz, "glow_water", 0.014,
           z0=0.026)
    relief(mb, octa_pts(0.085, 0.1, 0.04, 6), cz, "glow_water", 0.02)
    mb.collider_none()
    mb.tag("nonstatic")
    return mb.finish()


def build_key_seal_bamboo(seed):
    mb = L.MeshBuilder("key_seal_bamboo", seed)
    cz = 0.25
    medallion(mb, cz, "leaf_dark", "gold", "bamboo_dark")
    # bamboo stalk (slightly slanted) with node bands
    relief(mb, [(-0.07, -0.17), (-0.02, -0.17), (0.0, 0.17), (-0.05, 0.17)], cz, "bamboo", 0.025,
           side_color="bamboo_dark")
    for zz in (0.02,):
        x = -0.045 + 0.05 * (zz + 0.17) / 0.34
        relief(mb, [(x - 0.035, zz - 0.012), (x + 0.035, zz - 0.012), (x + 0.035, zz + 0.012),
                    (x - 0.035, zz + 0.012)], cz, "bamboo_light", 0.012, z0=0.022)
    # leaves
    relief(mb, [(-0.01, 0.06), (0.09, 0.04), (0.16, 0.08), (0.08, 0.075)], cz, "leaf_light", 0.03)
    relief(mb, [(-0.01, -0.02), (0.08, -0.06), (0.15, -0.04), (0.07, -0.035)], cz, "bamboo_light", 0.03)
    relief(mb, [(-0.06, 0.02), (-0.13, 0.05), (-0.17, 0.0), (-0.12, 0.015)], cz, "leaf_light", 0.03)
    for (x, z) in ((0.1, 0.13), (-0.12, -0.09)):
        relief(mb, octa_pts(x, z, 0.022, 5), cz, "glow_firefly", 0.022)
    mb.collider_none()
    mb.tag("nonstatic")
    return mb.finish()


def build_scythe(seed):
    mb = L.MeshBuilder("scythe", seed)
    zc = 0.03
    # handle (lying along X) with a rope grip at the butt and an iron collar at the blade end
    tube(mb, [(-0.72, 0.0, zc), (0.66, 0.0, zc)], 0.03, 6, "wood_light", cap_color="wood")
    tube(mb, [(-0.66, 0.0, zc), (-0.46, 0.0, zc)], 0.036, 6, "rope", cap_color="rope",
         face_color=lambda k, i: "thatch_dark" if i % 2 else None)
    tube(mb, [(0.56, 0.0, zc), (0.7, 0.0, zc)], 0.04, 6, "iron", cap_color="iron_light")
    # curved iron blade lying flat, curving toward -Y
    spine = [(0.69, 0.03), (0.71, -0.1), (0.68, -0.25), (0.6, -0.39), (0.47, -0.5), (0.33, -0.55)]
    edge = [(0.33, -0.55), (0.45, -0.45), (0.55, -0.35), (0.61, -0.23), (0.63, -0.1), (0.62, 0.03)]
    pts = spine + edge[1:]
    # CCW order (seen from above)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if area < 0:
        pts = list(reversed(pts))
    slab(mb, pts, (0, 0, 0.012), (1, 0, 0), (0, 1, 0), 0.026, "iron_light", side_color="iron", back=False)
    # the YELLOW ribbon (Kaito's bandana in disguise) tied around the handle
    tube(mb, [(0.25, 0.0, zc), (0.4, 0.0, zc)], 0.048, 6, "flower_yellow", cap_color="gold")
    mb.box((0.32, 0.0, 0.065), (0.11, 0.1, 0.07), "flower_yellow", rot=(0, 0, 25))
    tail1 = [(0.28, -0.04), (0.38, -0.03), (0.35, -0.17), (0.38, -0.31), (0.32, -0.46), (0.27, -0.38),
             (0.19, -0.45), (0.23, -0.3), (0.22, -0.15)]
    tail2 = [(0.32, 0.03), (0.4, 0.05), (0.36, 0.17), (0.25, 0.27), (0.24, 0.38), (0.19, 0.31),
             (0.12, 0.33), (0.17, 0.22), (0.26, 0.13)]
    for t in (tail1, tail2):
        area = sum(t[i][0] * t[(i + 1) % len(t)][1] - t[(i + 1) % len(t)][0] * t[i][1] for i in range(len(t)))
        if area < 0:
            t = list(reversed(t))
        slab(mb, t, (0, 0, 0.004), (1, 0, 0), (0, 1, 0), 0.02, "flower_yellow", side_color="gold", back=False)
    mb.collider_none()
    mb.tag("nonstatic")
    return mb.finish()


def build_training_dummy(seed):
    mb = L.MeshBuilder("training_dummy", seed)
    # crossed foot planks
    blk(mb, (0, 0, 0), (0.9, 0.14, 0.09), "wood_dark", top="wood")
    blk(mb, (0, 0, 0.0), (0.14, 0.9, 0.1), "wood_dark", top="wood")
    lathe(mb, [(0.075, 0.08), (0.07, 1.62)], 6, "wood", cap_top=True, top_color="wood_light")
    # straw body bundle with rope bindings
    lathe(mb, [(0.27, 0.42), (0.21, 0.52), (0.215, 0.62), (0.225, 0.67), (0.22, 0.95), (0.225, 1.0),
               (0.19, 1.12)], 8, "straw", ["thatch", "straw", "rope", "straw", "rope", "straw"],
          top_color="thatch", jitter=0.008)
    # head bundle
    lathe(mb, [(0.13, 1.14), (0.16, 1.24), (0.155, 1.4), (0.07, 1.52), (0.0, 1.6)], 8, "straw",
          ["rope", "straw", "straw", "thatch"], jitter=0.006)
    # red hachimaki band on the head
    lathe(mb, [(0.165, 1.31), (0.165, 1.37)], 8, "cloth_red", cap_top=False)
    mb.box((0.0, 0.18, 1.32), (0.05, 0.08, 0.16), "cloth_red", rot=(20, 0, 15))
    # arm bundle through the body
    tube(mb, [(-0.5, 0.0, 0.92), (0.5, 0.0, 0.92)], [0.08, 0.08], 6, "straw", cap_color="thatch")
    for x in (-0.36, 0.36):
        tube(mb, [(x - 0.03, 0, 0.92), (x + 0.03, 0, 0.92)], 0.088, 6, "rope", cap_color="rope", cap=False)
    mb.collider_capsule(0.3, 1.6)
    return mb.finish()


def katana(mb, x0, x1, y, z, saya="wood_black", tsuka="cloth_indigo"):
    """Horizontal sheathed katana from x0 (handle end) to x1 (scabbard tip)."""
    L_ = x1 - x0
    hx = x0 + L_ * 0.26
    mb.box(((x0 + hx) / 2, y, z), (abs(hx - x0), 0.05, 0.055), tsuka)
    mb.box((hx, y, z), (0.03, 0.1, 0.1), "gold")
    mb.box(((hx + x1) / 2, y, z + 0.004), (abs(x1 - hx), 0.055, 0.06), saya)


def spear(mb, x, y, z0, h, lean=0.0):
    a = Vector((x, y, z0))
    b = Vector((x, y + lean, z0 + h))
    bar(mb, a, b, 0.05, "wood")
    d = (b - a).normalized()
    c = b + d * 0.02
    bar(mb, c - d * 0.06, c + d * 0.02, 0.075, "black")
    tip = b + d * 0.36
    base = c + d * 0.02
    lathe(mb, [(0.0, 0.0), (0.05, 0.08), (0.0, 0.36)], 4, "iron_light", loc=base,
          rot=(-math.degrees(math.atan2(lean, h)), 0, 0), phase=0.0)


def build_weapon_rack(seed):
    mb = L.MeshBuilder("weapon_rack", seed)
    for sx in (-1, 1):
        blk(mb, (sx * 0.86, 0, 0), (0.12, 0.5, 0.09), "wood_dark", top="wood")
        blk(mb, (sx * 0.86, 0.05, 0.08), (0.1, 0.1, 1.42), "wood_dark", top="wood")
    mb.box((0, 0.05, 1.47), (1.94, 0.12, 0.1), "wood_red")
    mb.box((0, 0.05, 0.22), (1.82, 0.1, 0.08), "wood_dark")
    mb.box((0.48, -0.06, 0.12), (0.62, 0.14, 0.08), "wood_dark")
    # katana holder boards (left half)
    for x in (-0.68, -0.06):
        blk(mb, (x, -0.02, 0.26), (0.08, 0.1, 1.08), "wood_red", top="wood_red_dark")
    katana(mb, -0.78, 0.02, -0.09, 1.2, "wood_black", "cloth_white")
    katana(mb, -0.78, 0.02, -0.09, 0.95, "wood_red", "black")
    katana(mb, -0.8, 0.04, -0.09, 0.7, "wood_black", "cloth_indigo")
    # two spears leaning on the top beam (right half)
    spear(mb, 0.32, -0.08, 0.14, 1.95, lean=0.1)
    spear(mb, 0.64, -0.08, 0.14, 1.85, lean=0.1)
    mb.collider_box((1.9, 0.55, 1.55))
    return mb.finish()



# =====================================================================================
#  VILLAGE / FARM DRESSING
# =====================================================================================
def rotate_parts(parts, pivot, rot):
    for p in parts:
        p.transform(loc=(-pivot[0], -pivot[1], -pivot[2]))
        p.transform(rot=rot)
        p.transform(loc=pivot)


def ink(mb, origin, u, v, strokes, color="ink", depth=0.008):
    """Tiny dark 'kanji' strokes on a surface.  strokes = [(x0, y0, x1, y1), ...] in (u, v) coords;
    the strokes stand out along u x v."""
    for (x0, y0, x1, y1) in strokes:
        slab(mb, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], origin, u, v, depth, color, back=False)


def build_scarecrow(seed):
    mb = L.MeshBuilder("scarecrow", seed)
    blk(mb, (0, 0, 0), (0.09, 0.09, 1.5), "wood", top="wood_light")
    mb.box((0, 0, 1.3), (1.5, 0.07, 0.07), "wood")
    # kimono body (square frustum) + straw skirt
    lathe(mb, [(0.25, 0.62), (0.32, 0.76)], 6, "straw", cap_top=False, jitter=0.01)
    lathe(mb, [(0.34, 0.74), (0.24, 1.4)], 4, "cloth_indigo", scale=(1.0, 0.75, 1.0), phase=math.pi / 4,
          top_color="cloth_indigo")
    lathe(mb, [(0.315, 0.98), (0.3, 1.06)], 4, "rope", scale=(1.0, 0.75, 1.0), phase=math.pi / 4,
          cap_top=False)
    # white collar V + patch
    slab(mb, [(-0.12, 0.0), (-0.07, 0.0), (0.0, -0.17), (0.07, 0.0), (0.12, 0.0), (0.0, -0.24)],
         (0, -0.135, 1.39), (1, 0, 0), (0, 0, 1), 0.02, "cloth_white", back=False)
    slab(mb, [(0.06, 0.0), (0.16, 0.0), (0.16, 0.1), (0.06, 0.1)], (0, -0.155, 0.8), (1, 0, 0), (0, 0, 1),
         0.012, "cloth_blue", back=False)
    # hanging kimono sleeves + straw hands
    for sx in (-1, 1):
        mb.box((sx * 0.42, 0, 1.22), (0.44, 0.17, 0.3), "cloth_indigo")
        lathe(mb, [(0.085, 0.0), (0.0, 0.2)], 5, "straw", rot=(0, sx * 90, 0), loc=(sx * 0.62, 0, 1.28),
              cap_bottom=True, jitter=0.01)
    # sack head with a painted face
    lathe(mb, [(0.1, 1.38), (0.16, 1.47), (0.155, 1.6), (0.07, 1.68)], 6, "cloth_white",
          top_color="cloth_white")
    fy = -0.155 * math.cos(math.pi / 6) + 0.006
    ink(mb, (0, fy, 1.53), (1, 0, 0), (0, 0, 1), [(-0.08, 0.0, -0.03, 0.02), (0.03, 0.0, 0.08, 0.02),
                                                  (-0.05, -0.06, 0.05, -0.04)])
    # straw kasa hat, slightly tilted
    hat = lathe(mb, [(0.0, 1.62), (0.44, 1.58), (0.43, 1.62), (0.0, 1.92)], 8, "straw",
                ["thatch_dark", "thatch", "straw"], cap_top=False)
    rotate_parts([hat], (0, 0, 1.6), (-8, 6, 0))
    mb.collider_capsule(0.35, 1.9)
    return mb.finish()


def wheel(mb, x, y, z, r, w, side):
    """Solid cart wheel in the YZ plane; alternating spoke-coloured fan on the outer face."""
    prof = [(0.0, -w / 2), (r, -w / 2), (r, w / 2), (r * 0.8, w / 2 + 0.005), (0.0, w / 2 + 0.02)]
    rot = (0, 90, 0) if side > 0 else (0, -90, 0)
    lathe(mb, prof, 8, "wood_dark", ["wood_dark", "wood_black", "wood_dark", "wood"], loc=(x, y, z), rot=rot,
          cap_top=False, phase=0.0, face_color=lambda k, i: "wood_light" if (k == 3 and i % 2 == 0) else None)
    mb.box((x + side * (w / 2 + 0.03), y, z), (0.05, 0.1, 0.1), "iron")


def rice_sack(mb, loc, scale=(0.3, 0.24, 0.2), color="cloth_white", rot=(0, 0, 0)):
    x, y, z = loc
    body = mb.ico((x, y, z + scale[2] * 0.85), 1.0, color, subdiv=1, scale=scale, rot=rot)
    body.jitter(0.02)
    lathe(mb, [(0.05, 0.0), (0.075, 0.09)], 4, "rope", loc=(x, y, z + scale[2] * 1.7), rot=rot,
          top_color=color)
    return body


def build_cart_hand(seed):
    mb = L.MeshBuilder("cart_hand", seed)
    R, ay = 0.42, 0.62
    for sx in (-1, 1):
        wheel(mb, sx * 0.64, ay, R, R, 0.09, sx)
    parts = []
    parts.append(mb.box((0, ay, R), (1.3, 0.08, 0.08), "wood_dark"))
    parts.append(mb.box((0, 0.6, 0.6), (1.04, 1.42, 0.06), "wood_light"))
    for sx in (-1, 1):
        parts.append(mb.box((sx * 0.5, 0.6, 0.7), (0.06, 1.42, 0.16), "wood"))
        parts.append(mb.box((sx * 0.36, -0.05, 0.545), (0.08, 2.5, 0.07), "wood_dark"))
    parts.append(mb.box((0, 1.3, 0.7), (1.0, 0.06, 0.16), "wood"))
    parts.append(mb.box((0, -1.25, 0.545), (0.86, 0.07, 0.07), "wood_light"))
    parts.append(rice_sack(mb, (-0.22, 0.75, 0.63), (0.3, 0.34, 0.2), "cloth_white", rot=(0, 0, 70)))
    parts.append(rice_sack(mb, (0.22, 0.45, 0.63), (0.28, 0.32, 0.2), "straw", rot=(0, 0, 100)))
    # tilt everything that rests on the axle so the handle touches the ground
    hy, hz = -1.25, 0.545 - 0.035
    dy, dz = hy - ay, hz - R
    target = 0.035 - R
    th = math.atan2(dz, dy) - math.atan2(target, -math.sqrt(max(dy * dy + dz * dz - target * target, 0)))
    rotate_parts(parts, (0, ay, R), (math.degrees(-th), 0, 0))
    mb.collider_box((1.4, 2.6, 1.0), (0, 0, 0.5))
    return mb.finish()


def barrel_body(mb, loc, rot=(0, 0, 0), r=0.355, h=0.9, hoops=True, lid="wood_light"):
    prof = [(r * 0.84, 0.0), (r * 0.91, h * 0.08), (r, h * 0.42), (r, h * 0.58), (r * 0.91, h * 0.92),
            (r * 0.84, h)]
    cols = ["iron", "wood", "wood", "wood", "iron"] if hoops else ["iron", "wood", "iron", "wood", "iron"]
    p = lathe(mb, prof, 8, "wood", cols, loc=loc, rot=rot, cap_top=True, cap_bottom=True, top_color=lid,
              bottom_color=lid, face_color=lambda k, i: "wood_light" if (k in (1, 3) and i % 2 == 0) else None)
    return p


def build_barrel(seed):
    mb = L.MeshBuilder("barrel", seed)
    r, h = 0.34, 0.9
    prof = [(r * 0.85, 0.0), (r * 0.92, 0.08), (r, 0.36), (r, 0.54), (r * 0.92, 0.82), (r * 0.85, 0.9),
            (r * 0.78, 0.9), (r * 0.78, 0.86)]
    lathe(mb, prof, 8, "wood", ["iron", "wood", "wood", "wood", "iron", "wood_dark", "wood_dark"],
          top_color="wood_light", face_color=lambda k, i: "wood_light" if (k in (1, 3) and i % 2 == 0) else None)
    lathe(mb, [(r + 0.012, 0.42), (r + 0.012, 0.48)], 8, "iron", cap_top=False)
    mb.box((0, 0, 0.865), (0.06, r * 1.5, 0.02), "wood_dark")
    mb.collider_capsule(0.36, 0.9)
    return mb.finish()


def build_barrel_stack(seed):
    mb = L.MeshBuilder("barrel_stack", seed)
    r = 0.355
    for sx in (-1, 1):
        barrel_body(mb, (sx * 0.365 - 0.3, 0.45, r), rot=(90, 0, 0), r=r)
    up = math.sqrt((2 * r) ** 2 - 0.365 ** 2)
    barrel_body(mb, (-0.3, 0.45, r + up), rot=(90, 0, 18), r=r)
    # komodaru: straw-wrapped sake barrel
    x = 0.78
    lathe(mb, [(0.29, 0.0), (0.33, 0.1), (0.33, 0.52), (0.29, 0.64), (0.25, 0.65)], 8, "straw",
          ["rope", "straw", "rope", "wood_light"], loc=(x, -0.05, 0), top_color="wood_light",
          face_color=lambda k, i: "thatch" if (k == 1 and i % 2) else None)
    slab(mb, [(-0.12, 0.0), (0.12, 0.0), (0.12, 0.26), (-0.12, 0.26)], (x, -0.05 - 0.33 * 0.92 + 0.01, 0.17),
         (1, 0, 0), (0, 0, 1), 0.02, "cloth_red", back=False)
    slab(mb, [(-0.035, 0.0), (0.035, 0.0), (0.035, 0.2), (-0.035, 0.2)], (x, -0.05 - 0.33 * 0.92 - 0.006, 0.2),
         (1, 0, 0), (0, 0, 1), 0.012, "cloth_white", back=False)
    mb.collider_box((2.0, 0.95, 1.4), (0.0, 0.0, 0.7))
    return mb.finish()


def crate(mb, base, size, rz=0.0, brace=True, stamp=False, frame="wood_light", panel="wood"):
    x, y, z = base
    sx, sy, sz = size
    p = mb.box_base((0, 0, 0), size, frame)
    fs = p.faces
    for f in fs:
        f.normal_update()
    bmesh.ops.delete(mb.bm, geom=[f for f in fs if f.normal.z < -0.99], context="FACES_ONLY")
    p.verts = [v for v in p.verts if v.is_valid]
    vis = [f for f in p.faces]
    inset(mb, vis, 0.075 * min(sx, sy, sz) / 0.8, -0.025, panel)
    extra = []
    if brace:
        a = math.degrees(math.atan2(sz - 0.12, sx - 0.12))
        L_ = math.hypot(sx - 0.12, sz - 0.12)
        extra.append(mb.box((0, -sy / 2 + 0.005, sz / 2), (L_, 0.03, 0.08), frame, rot=(0, -a, 0)))
        extra.append(mb.box((0, sy / 2 - 0.005, sz / 2), (L_, 0.03, 0.08), frame, rot=(0, a, 0)))
    if stamp:
        extra.append(slab(mb, [(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)], (sx / 2 - 0.02, 0, sz / 2),
                          (0, 1, 0), (0, 0, 1), 0.012, "cloth_red", back=False))
    for q in [p] + extra:
        q.transform(rot=(0, 0, rz))
        q.transform(loc=(x, y, z))
    return p


def build_crate(seed):
    mb = L.MeshBuilder("crate", seed)
    crate(mb, (0, 0, 0), (0.8, 0.8, 0.8), stamp=True)
    mb.collider_box((0.8, 0.8, 0.8))
    return mb.finish()


def build_crate_stack(seed):
    mb = L.MeshBuilder("crate_stack", seed)
    crate(mb, (-0.42, 0.05, 0), (0.8, 0.8, 0.8), rz=4, brace=True)
    crate(mb, (0.45, 0.12, 0), (0.75, 0.75, 0.7), rz=-7, brace=False, stamp=True)
    crate(mb, (-0.1, 0.1, 0.795), (0.6, 0.6, 0.55), rz=14, brace=False)
    crate(mb, (0.55, -0.66, 0), (0.5, 0.5, 0.45), rz=24, brace=False, frame="wood", panel="wood_dark")
    mb.collider_box((1.75, 1.6, 1.35), (0.0, -0.1, 0.675))
    return mb.finish()


def tawara(mb, loc, rz=0.0, L_=0.62, r=0.22):
    """Straw rice bale lying along its local X axis."""
    x, y, z = loc
    prof = [(r * 0.72, 0.0), (r * 0.95, L_ * 0.12), (r, L_ * 0.44), (r, L_ * 0.56), (r * 0.95, L_ * 0.88),
            (r * 0.72, L_)]
    p = lathe(mb, prof, 6, "straw", ["thatch", "straw", "rope", "straw", "thatch"], rot=(0, 90, 0),
              loc=(-L_ / 2, 0, 0), cap_top=True, cap_bottom=True, top_color="thatch_dark",
              bottom_color="thatch_dark", phase=0.0)
    p.transform(rot=(0, 0, rz))
    p.transform(loc=(x, y, z + r * 0.92))
    return p


def build_sack_pile(seed):
    mb = L.MeshBuilder("sack_pile", seed)
    tawara(mb, (0.0, -0.23, 0), rz=3)
    tawara(mb, (0.05, 0.23, 0), rz=-4)
    tawara(mb, (0.02, 0.0, 0.38), rz=8)
    rice_sack(mb, (0.6, -0.15, 0), (0.24, 0.22, 0.26), "cloth_white", rot=(0, -12, 30))
    rice_sack(mb, (-0.58, 0.12, 0), (0.22, 0.24, 0.24), "cloth_white", rot=(8, 10, -20))
    mb.collider_box((1.6, 1.0, 0.85))
    return mb.finish()


def build_hay_bale(seed):
    mb = L.MeshBuilder("hay_bale", seed)
    prof = [(0.55, 0.0), (0.62, 0.22), (0.61, 0.58), (0.5, 0.84), (0.27, 1.04), (0.1, 1.13), (0.0, 1.2)]
    lathe(mb, prof, 10, "straw", ["thatch_dark", "straw", "thatch", "straw", "thatch_light", "thatch"],
          jitter=0.025, cap_top=False, face_color=lambda k, i: "thatch_light" if (k == 1 and i % 3 == 0) else None)
    lathe(mb, [(0.6, 0.62), (0.565, 0.7)], 10, "rope", cap_top=False)
    # tied top knot
    lathe(mb, [(0.13, 1.08), (0.09, 1.2), (0.16, 1.3), (0.0, 1.27)], 6, "thatch", ["rope", "thatch_light", "thatch"])
    # loose straw on the ground
    for (x, y, a) in ((0.72, -0.25, 30), (-0.6, -0.5, -50), (0.3, -0.72, 75)):
        mb.box((x, y, 0.015), (0.3, 0.05, 0.03), "straw", rot=(0, 0, a))
    mb.collider_box((1.25, 1.25, 1.2))
    return mb.finish()


def build_well(seed):
    mb = L.MeshBuilder("well", seed)
    stones = ["stone", "stone_dark", "stone_warm", "stone", "stone_moss", "stone_light"]
    prof = [(0.72, 0.0), (0.74, 0.3), (0.72, 0.58), (0.74, 0.74), (0.78, 0.78), (0.78, 0.88), (0.56, 0.9),
            (0.54, 0.5)]
    ring = lathe(mb, prof, 12, "stone", ["stone", "stone", "stone", "stone_dark", "stone_light", "stone_light",
                                         "stone_dark"], jitter=0.012,
                 face_color=lambda k, i: stones[(i * 7 + k * 3) % len(stones)] if k < 3 else None)
    paint(mb, [ring.top], "water_deep", slot=L.SLOT_WATER)
    # frame
    for sx in (-1, 1):
        blk(mb, (sx * 0.92, 0, 0), (0.24, 0.24, 0.12), "stone_dark", top="stone")
        blk(mb, (sx * 0.92, 0, 0.1), (0.12, 0.12, 1.98), "wood_dark", top="wood")
        bar(mb, (sx * 0.92, 0, 1.62), (sx * 0.62, 0, 1.94), 0.07, "wood_dark")
    mb.box((0, 0, 1.98), (2.1, 0.13, 0.13), "wood")
    # pulley
    mb.box((0, 0, 1.86), (0.2, 0.06, 0.14), "wood_dark")
    lathe(mb, [(0.0, -0.04), (0.13, -0.04), (0.13, 0.04), (0.0, 0.04)], 8, "wood_light",
          ["wood_light", "wood_dark", "wood_light"], rot=(90, 0, 0), loc=(0, 0, 1.78), cap_top=False)
    # thatched roof
    gable_roof(mb, 0, 0, 2.02, 2.35, 1.5, 0.42, 0.09, "thatch", nx=3, sag=0.04, upturn=0.06,
               under_color="thatch_dark", edge_color="thatch_dark")
    mb.box((0, 0, 2.45), (2.42, 0.18, 0.1), "thatch_dark")
    # ropes + bucket on the rim
    tube(mb, [(0.13, 0, 1.78), (0.13, 0, 0.62)], 0.025, 3, "rope")
    bx, by = -0.3, -0.62
    tube(mb, [(-0.13, 0, 1.78), (bx, by, 1.2), (bx, by, 1.18)], 0.025, 3, "rope")
    lathe(mb, [(0.13, 0.9), (0.165, 1.16), (0.14, 1.16), (0.13, 1.0)], 8, "wood_light",
          ["wood_light", "wood_dark", "wood_dark"], loc=(bx, by, 0), top_color="water_shallow",
          face_color=lambda k, i: "bamboo_dark" if False else None)
    lathe(mb, [(0.15, 0.94), (0.15, 0.99)], 8, "bamboo_dark", loc=(bx, by, 0), cap_top=False)
    lathe(mb, [(0.163, 1.08), (0.163, 1.12)], 8, "bamboo_dark", loc=(bx, by, 0), cap_top=False)
    mb.box((bx, by, 1.2), (0.36, 0.05, 0.05), "wood")
    for sx in (-1, 1):
        mb.box((bx + sx * 0.16, by, 1.15), (0.05, 0.05, 0.12), "wood")
    mb.collider_box((1.58, 1.58, 0.9))
    return mb.finish()


def arrow_board(mb, z, direction, tilt, w=0.78, h=0.2, y0=-0.06, d=0.05):
    """Arrow-shaped board in front of the post pointing to -X (direction=-1) or +X (+1)."""
    tip = 0.14
    pts = [(-w * 0.62, 0.0), (-w * 0.62 + tip, h / 2), (w * 0.38, h / 2), (w * 0.38, -h / 2),
           (-w * 0.62 + tip, -h / 2)]
    if direction > 0:
        pts = [(-x, y) for x, y in reversed(pts)]
    a = math.radians(tilt)
    pts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in pts]
    slab(mb, pts, (0, y0, z), (1, 0, 0), (0, 0, 1), d, "wood_pale", side_color="wood_light")
    # ink kanji scribbles (front + back)
    cx = -0.2 * (1 if direction < 0 else -1)
    strokes = []
    for (sx0, sy0, sx1, sy1) in ((-0.13, -0.015, -0.03, 0.015), (-0.095, -0.06, -0.065, 0.06),
                                 (0.0, 0.03, 0.12, 0.055), (0.045, -0.06, 0.075, 0.03),
                                 (0.0, -0.055, 0.12, -0.03)):
        strokes.append((cx + sx0, sy0, cx + sx1, sy1))
    rs = []
    for (x0, y0_, x1, y1) in strokes:
        xs = [x0 * math.cos(a) - y0_ * math.sin(a), x1 * math.cos(a) - y1 * math.sin(a)]
        ys = [x0 * math.sin(a) + y0_ * math.cos(a), x1 * math.sin(a) + y1 * math.cos(a)]
        rs.append((min(xs), min(ys), max(xs), max(ys)))
    ink(mb, (0, y0 - d + 0.003, z), (1, 0, 0), (0, 0, 1), rs)
    ink(mb, (0, y0 - 0.003, z), (-1, 0, 0), (0, 0, 1), [(-x1, y0_, -x0, y1) for (x0, y0_, x1, y1) in rs])


def build_signpost(seed):
    mb = L.MeshBuilder("signpost", seed)
    rock(mb, (0, 0, 0), 0.2, 0.1, "stone_dark", top_color="stone", n=5)
    blk(mb, (0, 0, 0.0), (0.12, 0.12, 1.74), "wood", top="wood_dark")
    lathe(mb, [(0.11, 1.73), (0.0, 1.84)], 4, "wood_dark", phase=0.0)
    arrow_board(mb, 1.48, -1, 4)
    arrow_board(mb, 1.18, 1, -5)
    mb.collider_capsule(0.25, 1.8)
    return mb.finish()


PROPS = {
    "lantern_stone": build_lantern_stone,
    "lantern_stone_tall": build_lantern_stone_tall,
    "lantern_post": build_lantern_post,
    "lantern_hanging": build_lantern_hanging,
    "lantern_string": build_lantern_string,
    "torch_brazier": build_torch_brazier,
    "campfire": build_campfire,
    "shrine_checkpoint": build_shrine_checkpoint,
    "portal_ring": build_portal_ring,
    "seal_pedestal": build_seal_pedestal,
    "key_seal_mountain": build_key_seal_mountain,
    "key_seal_lake": build_key_seal_lake,
    "key_seal_bamboo": build_key_seal_bamboo,
    "scythe": build_scythe,
    "training_dummy": build_training_dummy,
    "weapon_rack": build_weapon_rack,
    "scarecrow": build_scarecrow,
    "cart_hand": build_cart_hand,
    "barrel": build_barrel,
    "barrel_stack": build_barrel_stack,
    "crate": build_crate,
    "crate_stack": build_crate_stack,
    "sack_pile": build_sack_pile,
    "hay_bale": build_hay_bale,
    "well": build_well,
    "signpost": build_signpost,
}
