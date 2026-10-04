"""Nindo nature props: trees, bamboo, bushes, ground cover, rocks, cliffs, crops.

All foliage (needles, leaves, blossoms, grass blades) lives on SLOT_FOLIAGE with a
height-based wind weight; trunks/rocks stay on the palette slot with wind 0.

NOTE on geometry: MeshBuilder.finish() runs recalc_face_normals(), which picks an
arbitrary side for isolated single faces, and face(double=True) back faces get
welded away by remove_doubles.  So every thin thing here (blades, petals, pads,
water quads) is built as a small closed / tent-shaped volume whose outward side
is unambiguous.  That keeps it correct with back-face culling in Unity.
"""
import math, random
import bmesh
from mathutils import Vector, Matrix
import nindo_lib as L

FOL = L.SLOT_FOLIAGE
TAU = 2.0 * math.pi


# =============================================================== low level helpers
def geo(mb, co, faces, color, slot=None, wind=None):
    """Creates verts + faces from index lists; returns a Part."""
    vs = [mb.bm.verts.new(Vector(c)) for c in co]
    fl = [mb.bm.faces.new([vs[i] for i in f]) for f in faces]
    p = mb._new(vs, color, slot, wind)
    p.flist = fl
    return p


def color_kinds(mb, part, kinds, fn):
    """kinds: list aligned with part.flist; fn(kind, face) -> colour."""
    for f, k in zip(part.flist, kinds):
        c = fn(k, f)
        if c:
            mb._tag([f], c, None, None)


def fit_height(mb, H, z_from=0.3):
    """Scales vertical positions (above z_from) so the prop's top is exactly H."""
    top = max(v.co.z for v in mb.bm.verts)
    if top <= z_from + 1e-3:
        return
    k = (H - z_from) / (top - z_from)
    for v in mb.bm.verts:
        if v.co.z > z_from:
            v.co.z = z_from + (v.co.z - z_from) * k


def group(mb, *parts):
    vs = []
    for p in parts:
        if p is not None:
            vs.extend(p.verts)
    return L.Part(mb, vs)


def nrm(f):
    f.normal_update()
    return f.normal


class FaceDice:
    """Per-face deterministic dice for colour choices made while iterating Part.faces (a set,
    whose order changes between runs).  It still advances the shared rng exactly like a plain
    rng.random()/rng.choice() call would, so geometry built afterwards is unaffected."""

    def __init__(self, rng, f, salt=0):
        self.rng = rng
        c = f.calc_center_median()
        self.r = random.Random(hash((round(c.x * 1000), round(c.y * 1000), round(c.z * 1000), salt)))

    def random(self):
        self.rng.random()
        return self.r.random()

    def choice(self, seq):
        self.rng.choice(seq)
        return self.r.choice(seq)


def shade(part, top, side, under, t_top=0.55, t_under=-0.3, rng=None, alt=None, p_alt=0.0,
          alt_side=None, p_alt_side=0.0):
    """Colours faces of a part by facing: top / side / under (+ random accents)."""
    rng = rng or random.Random(0)

    def fn(f):
        d = FaceDice(rng, f)
        n = nrm(f)
        if n.z >= t_top:
            return alt if (alt and d.random() < p_alt) else top
        if n.z <= t_under:
            return under
        return alt_side if (alt_side and d.random() < p_alt_side) else side
    part.color_faces(fn)
    return part


def bark(part, rng, dark="trunk", light="trunk_light", p_light=0.35, snow=None, snow_t=0.6):
    def fn(f):
        d = FaceDice(rng, f)
        n = nrm(f)
        if snow and n.z > snow_t:
            return snow
        lit = (n.z * 0.6 - n.y * 0.25 - n.x * 0.35)
        return light if (lit > 0.18 or d.random() < p_light * 0.5) else dark
    part.color_faces(fn)
    return part


def bez(p0, p1, p2, p3, n):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        pts.append(p0 * u * u * u + p1 * 3 * u * u * t + p2 * 3 * u * t * t + p3 * t * t * t)
    return pts


def tube(mb, pts, radii, sides, color, rng=None, jitter=0.0, phase=None, cap_start=False, slot=None,
         wind=None, squash=1.0):
    """Lofts rings (perpendicular to the polyline, parallel transported) along pts.
    A radius of 0 makes a pointed tip (verts welded in finish())."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rng = rng or random.Random(0)
    phase = rng.uniform(0, TAU) if phase is None else phase
    tans = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        tans.append(t.normalized())
    t0 = tans[0]
    ref = Vector((1, 0, 0)) if abs(t0.x) < 0.9 else Vector((0, 1, 0))
    nm = (ref - t0 * ref.dot(t0)).normalized()
    rings = []
    for i in range(n):
        if i > 0:
            nm = tans[i - 1].rotation_difference(tans[i]) @ nm
            nm = (nm - tans[i] * nm.dot(tans[i])).normalized()
        b = tans[i].cross(nm)
        r = radii[i]
        ring = []
        for k in range(sides):
            a = phase + TAU * k / sides
            p = pts[i] + (nm * math.cos(a) + b * math.sin(a) * squash) * r
            if jitter and r > 1e-4:
                p = p + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * jitter * r
            ring.append(p)
        rings.append(ring)
    return mb.loft(rings, color, cap_start=cap_start, slot=slot, wind=wind)


def pyramid(mb, base_pts, apex, color, slot=None, wind=None):
    """Open-bottom pyramid; base_pts counter-clockwise seen from the apex side."""
    co = [tuple(p) for p in base_pts] + [tuple(apex)]
    n = len(base_pts)
    faces = [(i, (i + 1) % n, n) for i in range(n)]
    return geo(mb, co, faces, color, slot, wind)


def blade(mb, base, tip, width, color, rng, thick=None, slot=FOL, wind=None):
    """Grass/leaf blade = thin 3-sided pyramid (3 tris), visible from every side."""
    base = Vector(base)
    tip = Vector(tip)
    d = (tip - base)
    d.z = 0
    if d.length < 1e-4:
        d = Vector((math.cos(rng.uniform(0, TAU)), math.sin(rng.uniform(0, TAU)), 0))
    d.normalize()
    side = Vector((-d.y, d.x, 0))
    th = width * 0.45 if thick is None else thick
    b0 = base + side * width * 0.5
    b1 = base - side * width * 0.5
    b2 = base + d * th
    # CCW seen from above: b1 -> b0 -> b2 ... check with cross
    pts = [b0, b1, b2]
    if ((b1 - b0).cross(b2 - b0)).z < 0:
        pts = [b0, b2, b1]
    return pyramid(mb, pts, tip, color, slot, wind)


def pad(mb, c, rx, ry, h, n, rng, rot=None, slot=FOL, top_r=0.62, droop=0.1, lobe=0.84, under=0.22):
    """Flattened faceted cloud/canopy pad: under-centre, lobed mid ring, top ring, top-centre.
    Faces in .flist come in groups of 4 per segment: under, side, side, top."""
    cx, cy, cz = c
    rot = rng.uniform(0, TAU) if rot is None else rot
    co = [(cx + rng.uniform(-0.1, 0.1) * rx, cy + rng.uniform(-0.1, 0.1) * ry, cz - h * under)]
    for k in range(n):
        a = rot + TAU * k / n + rng.uniform(-0.18, 0.18) * TAU / n
        rr = rng.uniform(0.9, 1.08) * (1.0 if k % 2 == 0 else lobe)
        co.append((cx + math.cos(a) * rx * rr, cy + math.sin(a) * ry * rr,
                   cz + rng.uniform(-droop, droop * 0.6) * h))
    for k in range(n):
        a = rot + TAU * (k + 0.5) / n + rng.uniform(-0.15, 0.15) * TAU / n
        rr = rng.uniform(0.88, 1.08) * top_r
        co.append((cx + math.cos(a) * rx * rr, cy + math.sin(a) * ry * rr,
                   cz + h * rng.uniform(0.34, 0.5)))
    co.append((cx + rng.uniform(-0.12, 0.12) * rx, cy + rng.uniform(-0.12, 0.12) * ry, cz + h * 0.64))
    faces = []
    B, M, T, C = 0, 1, 1 + n, 1 + 2 * n
    for i in range(n):
        j = (i + 1) % n
        faces.append((B, M + j, M + i))
        faces.append((M + i, M + j, T + i))
        faces.append((M + j, T + j, T + i))
        faces.append((T + i, T + j, C))
    return geo(mb, co, faces, "leaf", slot)


def blob(mb, c, r, rng, scale=(1, 1, 1), segs=7, rings=4, jitter=0.12, slot=FOL, color="leaf"):
    p = mb.sphere(c, r, color, segments=segs, rings=rings, scale=scale,
                  rot=(rng.uniform(-8, 8), rng.uniform(-8, 8), rng.uniform(0, 360)), slot=slot)
    if jitter:
        for v in p.verts:
            v.co += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.7, 0.7))) * jitter * r
    return p


def hull(mb, pts, color, slot=None, wind=None):
    vs = [mb.bm.verts.new(Vector(p)) for p in pts]
    res = bmesh.ops.convex_hull(mb.bm, input=vs)
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(mb.bm, geom=junk, context='VERTS')
    faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
    verts = sorted({v for f in faces for v in f.verts}, key=lambda v: tuple(v.co))   # stable order
    return mb._new(verts, color, slot, wind)


def drop_below_ground(mb, part, z=0.0):
    """Deletes faces that are entirely below z (never seen)."""
    dead = [f for f in part.faces if all(v.co.z < z - 0.02 for v in f.verts)]
    if dead:
        bmesh.ops.delete(mb.bm, geom=dead, context='FACES')
    part.verts = [v for v in part.verts if v.is_valid]
    return part


def ground_disc(mb, c, r, n, rng, color, h=0.03, slot=None):
    """Very flat cone sitting on the ground (moss patch, petal, puddle...)."""
    cx, cy, cz = c
    a0 = rng.uniform(0, TAU)
    base = [(cx + math.cos(a0 + TAU * k / n) * r * rng.uniform(0.7, 1.1),
             cy + math.sin(a0 + TAU * k / n) * r * rng.uniform(0.7, 1.1), cz) for k in range(n)]
    return pyramid(mb, base, (cx, cy, cz + h), color, slot)


def petal(mb, c, size, rng, color, slot=None):
    cx, cy, cz = c
    a = rng.uniform(0, TAU)
    pts = [(cx + math.cos(a + k * TAU / 3) * size * (1.0 if k == 0 else 0.55),
            cy + math.sin(a + k * TAU / 3) * size * (1.0 if k == 0 else 0.55), cz) for k in range(3)]
    return pyramid(mb, pts, (cx, cy, cz + 0.012), color, slot)


def dirvec(a, z=0.0):
    return Vector((math.cos(a), math.sin(a), z))


# ================================================================= TREES
def _trunk_spine(rng, height, lean, n=7, wiggle=0.3, lean_dir=None, power=1.4):
    ld = rng.uniform(0, TAU) if lean_dir is None else lean_dir
    ph = rng.uniform(0, TAU)
    pts = []
    for i in range(n):
        t = i / (n - 1)
        off = lean * (t ** power)
        w = math.sin(t * math.pi * 1.7 + ph) * wiggle * min(1.0, t * 2.5)
        p = dirvec(ld) * off + dirvec(ld + math.pi / 2) * w
        p.z = height * t
        pts.append(p)
    return pts, ld


def _branch(mb, rng, start, direction, length, rise, r0, r1, sides=5, droop=0.0, segs=4):
    d = Vector(direction).normalized()
    p0 = Vector(start)
    p3 = p0 + d * length + Vector((0, 0, rise))
    p1 = p0 + d * length * 0.35 + Vector((0, 0, rise * 0.7 + 0.15))
    p2 = p0 + d * length * 0.7 + Vector((0, 0, rise - droop)) + Vector((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), 0))
    pts = bez(p0, p1, p2, p3, segs)
    radii = [r0 + (r1 - r0) * (i / (segs - 1)) for i in range(segs)]
    return tube(mb, pts, radii, sides, "trunk", rng, jitter=0.06), p3


def shade_pad(mb, p, rng, light, base, dark, p_light=0.6, p_side_dark=0.3, side=None):
    """Colours a pad() by face kind: tops light/base, sides base/dark, under dark."""
    side = side or base

    def fn(k, f):
        kind = k % 4
        if kind == 0:
            return dark
        if kind == 3:
            return light if rng.random() < p_light else base
        n = nrm(f)
        if n.z > 0.62:
            return light if rng.random() < p_light * 0.6 else base
        return dark if rng.random() < p_side_dark else side
    color_kinds(mb, p, list(range(len(p.flist))), fn)
    return p


def _roots(mb, rng, n, r0, dark="trunk", light="trunk_light", length=0.9):
    a0 = rng.uniform(0, TAU)
    for i in range(n):
        a = a0 + TAU * i / n + rng.uniform(-0.3, 0.3)
        d = dirvec(a)
        p0 = Vector((0, 0, 0.45)) + d * r0 * 0.3
        p1 = d * (r0 + length * 0.45) + Vector((0, 0, 0.12))
        p2 = d * (r0 + length * rng.uniform(0.8, 1.1)) + Vector((0, 0, -0.08))
        rt = tube(mb, [p0, p1, p2], [r0 * 0.45, r0 * 0.3, 0.0], 5, dark, rng, jitter=0.05)
        bark(rt, rng, dark, light)


def build_pine(seed, H, name, nbranch=4, subs=(0, 2), pn=10):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    s = H / 7.5
    crown_z = H * 0.78
    spine, ld = _trunk_spine(rng, crown_z, lean=rng.uniform(1.2, 1.7) * s, n=7, wiggle=0.45 * s, power=1.15)
    radii = [0.56 * s, 0.38 * s, 0.33 * s, 0.29 * s, 0.24 * s, 0.19 * s, 0.14 * s]
    spine[0].z = -0.08
    trunk = tube(mb, spine, radii, 6, "trunk", rng, jitter=0.08)
    bark(trunk, rng)
    pads = []
    top = spine[-1]
    # crown: wide pad + small cap pad
    pads.append(pad(mb, (top.x, top.y, top.z + 0.2 * s), 1.35 * s, 1.15 * s, 0.75 * s, 10, rng))
    pads.append(pad(mb, (top.x + rng.uniform(-0.35, 0.35) * s, top.y + rng.uniform(-0.35, 0.35) * s,
                         top.z + 0.7 * s), 0.8 * s, 0.72 * s, 0.55 * s, 8, rng))
    base_a = ld + math.pi + rng.uniform(-0.4, 0.4)
    for i in range(nbranch):
        f_ = i / max(1, nbranch - 1)
        t = 0.36 + 0.44 * f_ + rng.uniform(-0.03, 0.03)
        k = t * (len(spine) - 1)
        i0 = int(k)
        st = spine[i0].lerp(spine[min(i0 + 1, len(spine) - 1)], k - i0)
        a = base_a + i * (math.pi * 0.8) + rng.uniform(-0.3, 0.3)
        length = (2.4 - 1.0 * f_) * s * rng.uniform(0.9, 1.1)
        rise = rng.uniform(0.25, 0.55) * s
        br, end = _branch(mb, rng, st, dirvec(a), length, rise, 0.21 * s, 0.1 * s, droop=0.4 * s)
        bark(br, rng)
        rx = (1.45 - 0.35 * f_) * s * rng.uniform(0.9, 1.08)
        pads.append(pad(mb, (end.x, end.y, end.z + 0.14 * s), rx, rx * rng.uniform(0.75, 0.9),
                        0.6 * s, pn, rng))
        off = dirvec(a + rng.uniform(-1.0, 1.0)) * rx * 0.4
        pads.append(pad(mb, (end.x + off.x, end.y + off.y, end.z + 0.48 * s), rx * 0.55, rx * 0.5,
                        0.42 * s, 6, rng))
        if i in subs:
            # side twig with its own little pad
            mid = st.lerp(end, 0.45)
            sa = a + rng.choice((-1, 1)) * rng.uniform(0.8, 1.1)
            sb, send = _branch(mb, rng, mid, dirvec(sa), 1.0 * s, 0.25 * s, 0.11 * s, 0.06 * s,
                               droop=0.15 * s, segs=3)
            bark(sb, rng)
            pads.append(pad(mb, (send.x, send.y, send.z + 0.1 * s), 0.75 * s, 0.65 * s, 0.42 * s, 8, rng))
    for p in pads:
        shade_pad(mb, p, rng, "leaf_pine_light", "leaf_pine", "leaf_pine_dark", p_light=0.7)
    fit_height(mb, H)
    fol = group(mb, *pads)
    zmin = min(v.co.z for v in fol.verts)
    fol.wind_by_height(zmin - 1.0, H, 0.7)
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def _tier(mb, rng, z_b, z_t, R, n, center=(0, 0), droop=0.25, snow=False, apex_off=0.0, lobe=0.78):
    """One faceted conifer tier (lobed skirt cone).  Returns part with .kinds per face:
    'under', 'skirt' (outer band), 'cap' (upper part)."""
    cx, cy = center
    rot = rng.uniform(0, TAU)
    hh = z_t - z_b
    co = [(cx, cy, z_b + hh * 0.2)]          # under centre (concave)
    for k in range(n):
        a = rot + TAU * k / n + rng.uniform(-0.12, 0.12) * TAU / n
        tipk = (k % 2 == 0)
        rr = R * rng.uniform(0.92, 1.06) * (1.0 if tipk else lobe)
        co.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr,
                   z_b - (droop * rng.uniform(0.7, 1.0) if tipk else droop * 0.25)))
    rings = 2 if snow else 1
    if snow:
        for k in range(n):   # snow line ring
            a = rot + TAU * k / n + rng.uniform(-0.1, 0.1) * TAU / n
            rr = R * rng.uniform(0.66, 0.74) * (1.0 if k % 2 == 0 else 0.9)
            co.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr, z_b + hh * rng.uniform(0.1, 0.16)))
    for k in range(n):       # mid ring
        a = rot + TAU * (k + 0.5) / n + rng.uniform(-0.12, 0.12) * TAU / n
        rr = R * rng.uniform(0.44, 0.54)
        co.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr, z_b + hh * rng.uniform(0.42, 0.5)))
    ao = dirvec(rng.uniform(0, TAU)) * apex_off
    co.append((cx + ao.x, cy + ao.y, z_t))
    faces, kinds = [], []
    U = 0
    A = len(co) - 1
    rs = [1 + n * r for r in range(rings + 1)]
    for i in range(n):
        j = (i + 1) % n
        faces.append((U, 1 + j, 1 + i)); kinds.append("under")
        for r in range(rings):
            a0, a1 = rs[r], rs[r + 1]
            kd = "skirt" if r == 0 else "cap"
            if r == rings - 1:      # next ring is offset by half a step
                faces.append((a0 + i, a0 + j, a1 + i)); kinds.append(kd)
                faces.append((a0 + j, a1 + j, a1 + i)); kinds.append(kd)
            else:
                faces.append((a0 + i, a0 + j, a1 + j, a1 + i)); kinds.append(kd)
        last = rs[rings]
        faces.append((last + i, last + j, A)); kinds.append("cap")
    p = geo(mb, co, faces, "leaf_pine", FOL)
    p.kinds = kinds
    return p


def build_cedar(seed, H, name, ntier=7, z0f=0.2, width=0.19, lean_amt=(0.15, 0.35)):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    lean = dirvec(rng.uniform(0, TAU)) * rng.uniform(*lean_amt)
    trunk = mb.prism((0, 0, -0.05), 0.36, H * 0.85, 6, "trunk", radius_top=0.1, base=False)
    for v in trunk.verts:
        t = max(0.0, v.co.z) / H
        v.co.x += lean.x * t * 2
        v.co.y += lean.y * t * 2
    trunk.jitter(0.03)
    bark(trunk, rng)
    tiers = []
    z0 = H * z0f
    Rmax = H * width
    for i in range(ntier):
        t = i / (ntier - 1)
        zb = z0 + (H - z0) * (t ** 0.9) * 0.82
        zt = zb + (H - z0) * (0.27 - 0.09 * t) * (7.0 / ntier) ** 0.5
        if i == ntier - 1:
            zt = H
        wob = 1.0 if i % 2 == 0 else rng.uniform(0.82, 0.92)
        R = Rmax * (1.0 - t * 0.72) * wob * rng.uniform(0.94, 1.06)
        c = (lean.x * (zb / H) * 2 + rng.uniform(-0.15, 0.15), lean.y * (zb / H) * 2 + rng.uniform(-0.15, 0.15))
        n = 8 if i < ntier - 2 else 6
        p = _tier(mb, rng, zb, zt, R, n, center=c, droop=0.45 * (1 - t) + 0.12, apex_off=0.18, lobe=0.72)

        def fn(kind, f, i=i):
            if kind == "under":
                return "leaf_pine_dark"
            if kind == "skirt":
                return "leaf_pine_dark" if rng.random() < 0.3 else "leaf_pine"
            n_ = nrm(f)
            lit = n_.z + 0.45 * n_.y - 0.3 * n_.x
            return "leaf_pine_light" if (lit > 0.6 and rng.random() < 0.75) else "leaf_pine"
        color_kinds(mb, p, p.kinds, fn)
        # slight random tilt of the whole tier for a hand-made look
        tilt = Matrix.Rotation(math.radians(rng.uniform(-5, 5)), 4, dirvec(rng.uniform(0, TAU)))
        piv = Vector((c[0], c[1], zb))
        for v in p.verts:
            v.co = piv + (tilt @ (v.co - piv))
        tiers.append(p)
    fit_height(mb, H)
    fol = group(mb, *tiers)
    fol.wind_by_height(z0, H, 0.55)
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def build_snow_pine(seed, H, name, ntier=5):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    trunk = mb.prism((0, 0, -0.05), 0.32, H * 0.75, 6, "trunk_snow", radius_top=0.1, base=False)
    trunk.jitter(0.03)
    bark(trunk, rng, dark="trunk_snow", light="trunk")
    z0 = H * 0.15
    Rmax = H * 0.27
    tiers = []
    for i in range(ntier):
        t = i / (ntier - 1)
        zb = z0 + (H - z0) * t * 0.8
        zt = zb + (H - z0) * (0.36 - 0.1 * t)
        if i == ntier - 1:
            zt = H
        R = Rmax * (1.0 - t * 0.72) * rng.uniform(0.92, 1.05)
        p = _tier(mb, rng, zb, zt, R, 10 if i < 2 else 8, droop=0.45 * (1 - t) + 0.15, snow=True,
                  apex_off=0.12, lobe=0.72)

        def fn(kind, f):
            if kind == "under":
                return "leaf_pine_dark"
            if kind == "skirt":
                return "leaf_pine" if rng.random() < 0.55 else "leaf_pine_dark"
            n_ = nrm(f)
            return "snow" if (n_.z + 0.3 * n_.y > 0.55 or rng.random() < 0.3) else "snow_shade"
        color_kinds(mb, p, p.kinds, fn)
        tiers.append(p)
    fit_height(mb, H)
    fol = group(mb, *tiers)
    fol.wind_by_height(z0, H, 0.4)
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def _broadleaf_trunk(mb, rng, trunk_h, nb, spread, height_top, r0=0.32, sides=6, colors=("trunk", "trunk_light"),
                     branch_len=(1.6, 2.4), rise=(1.0, 1.8), lean=0.4):
    spine, ld = _trunk_spine(rng, trunk_h, lean=lean, n=5, wiggle=0.15)
    spine[0].z = -0.05
    radii = [r0 * 1.35, r0, r0 * 0.9, r0 * 0.82, r0 * 0.72]
    t = tube(mb, spine, radii, sides, colors[0], rng, jitter=0.08)
    bark(t, rng, colors[0], colors[1])
    ends = []
    a0 = rng.uniform(0, TAU)
    top = spine[-1]
    for i in range(nb):
        a = a0 + TAU * i / nb + rng.uniform(-0.35, 0.35)
        k = rng.uniform(0.0, 0.25)
        st = spine[-2].lerp(top, 0.5 + k)
        L_ = rng.uniform(*branch_len) * spread
        br, end = _branch(mb, rng, st, dirvec(a), L_, rng.uniform(*rise), r0 * 0.62, r0 * 0.22,
                          sides=5, droop=-0.2)
        bark(br, rng, colors[0], colors[1])
        ends.append((end, a))
    return spine, ends


def build_sakura(seed, H, name, nmain=4):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    s = H / 5.5
    spine, ld = _trunk_spine(rng, 1.8 * s, lean=0.55 * s, n=5, wiggle=0.2 * s)
    spine[0].z = -0.08
    t = tube(mb, spine, [0.5 * s, 0.33 * s, 0.3 * s, 0.28 * s, 0.25 * s], 6, "trunk", rng, jitter=0.1)
    bark(t, rng)
    _roots(mb, rng, 3, 0.4 * s)
    top = spine[-1]
    puffs = []   # (centre, radius, flatness)
    puffs.append((top + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.9 * s)), 1.55 * s, 0.75))
    a0 = ld + rng.uniform(-0.5, 0.5)
    ends = []
    for i in range(nmain):
        a = a0 + TAU * i / nmain + rng.uniform(-0.25, 0.25)
        Lb = rng.uniform(1.8, 2.2) * s
        st = spine[-2].lerp(top, rng.uniform(0.4, 1.0))
        br, end = _branch(mb, rng, st, dirvec(a), Lb, rng.uniform(0.9, 1.3) * s, 0.22 * s, 0.08 * s,
                          droop=-0.3 * s)
        bark(br, rng)
        ends.append((end, a))
        puffs.append((end + Vector((0, 0, 0.35 * s)), rng.uniform(1.1, 1.3) * s, 0.7))
    # gap fillers between neighbouring branch ends: lower, smaller, drooping edge of the umbrella
    for i in range(nmain):
        (e0, _), (e1, _) = ends[i], ends[(i + 1) % nmain]
        if nmain <= 3 and i == nmain - 1:
            continue
        m = e0.lerp(e1, 0.5)
        d = (m - top)
        d.z = 0
        if d.length > 1e-3:
            m = m + d.normalized() * 0.35 * s
        puffs.append((Vector((m.x, m.y, m.z - 0.05 * s)), rng.uniform(0.8, 0.95) * s, 0.72))
    blooms = []
    for c, r, fl in puffs:
        p = pad(mb, c, r, r * rng.uniform(0.85, 1.0), r * fl * 1.25, 8, rng, top_r=0.7, lobe=0.82, under=0.42,
                droop=0.15)
        shade_pad(mb, p, rng, "sakura_light", "sakura", "sakura_dark", p_light=0.55, p_side_dark=0.4)
        blooms.append(p)
    fit_height(mb, H)
    fol = group(mb, *blooms)
    fol.wind_by_height(top.z, H, 0.6)
    # fallen petals under the canopy
    for i in range(14):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0.8, 2.8) * s
        petal(mb, (math.cos(a) * d, math.sin(a) * d, 0.0), rng.uniform(0.14, 0.2),
              rng, rng.choice(("sakura", "sakura_light", "sakura_light", "sakura_dark")))
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def build_maple(seed, H, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    s = H / 5.0
    spine, ends = _broadleaf_trunk(mb, rng, 1.5 * s, 4, 1.0 * s, H, r0=0.22 * s, lean=0.5 * s,
                                   branch_len=(1.5, 2.0), rise=(0.7, 1.1), colors=("trunk", "trunk_light"))
    top = spine[-1]
    pads = []
    zlow = top.z + 0.9 * s
    for end, a in ends:   # low tier at the branch ends
        rx = rng.uniform(1.15, 1.35) * s
        pads.append(pad(mb, (end.x, end.y, end.z + 0.15 * s), rx, rx * 0.85, 0.55 * s, 8, rng, lobe=0.8))
    a0 = rng.uniform(0, TAU)
    for i in range(3):    # middle tier
        a = a0 + TAU * i / 3 + rng.uniform(-0.3, 0.3)
        c = top + dirvec(a) * rng.uniform(0.6, 0.9) * s
        pads.append(pad(mb, (c.x, c.y, zlow + 0.85 * s), 1.15 * s, 1.0 * s, 0.6 * s, 8, rng, lobe=0.8))
    pads.append(pad(mb, (top.x + rng.uniform(-0.2, 0.2), top.y + rng.uniform(-0.2, 0.2), zlow + 1.55 * s),
                    1.05 * s, 0.95 * s, 0.75 * s, 8, rng, lobe=0.85))
    for p in pads:
        shade_pad(mb, p, rng, "maple_orange", "maple", "maple_dark", p_light=0.45, p_side_dark=0.4)
    fit_height(mb, H)
    fol = group(mb, *pads)
    fol.wind_by_height(top.z, H, 0.6)
    for i in range(10):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0.6, 2.4) * s
        petal(mb, (math.cos(a) * d, math.sin(a) * d, 0.0), rng.uniform(0.14, 0.2), rng,
              rng.choice(("maple", "maple_orange", "maple_dark")))
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def build_round(seed, H, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    s = H / 6.5
    spine, ends = _broadleaf_trunk(mb, rng, 2.4 * s, 3, 0.8 * s, H, r0=0.28 * s, lean=0.3 * s,
                                   branch_len=(1.2, 1.6), rise=(1.0, 1.4))
    top = spine[-1]
    blobs = []
    cmain = Vector((top.x, top.y, H - 1.75 * s))
    blobs.append((cmain, 1.85 * s, 0.85))
    for end, a in ends:
        c = end + dirvec(a) * 0.3 * s + Vector((0, 0, 0.35 * s))
        blobs.append((c, rng.uniform(1.25, 1.5) * s, 0.8))
    a = rng.uniform(0, TAU)
    blobs.append((cmain + dirvec(a) * 0.8 * s + Vector((0, 0, 0.9 * s)), 1.15 * s, 0.85))
    parts = []
    for c, r, sq in blobs:
        b = blob(mb, c, r, rng, scale=(1, rng.uniform(0.85, 1.0), sq), segs=8, rings=5, jitter=0.12)
        shade(b, "leaf_light", "leaf", "leaf_dark", t_top=0.55, t_under=-0.25, rng=rng,
              alt="leaf", p_alt=0.3, alt_side="leaf_dark", p_alt_side=0.3)
        parts.append(b)
    fit_height(mb, H)
    fol = group(mb, *parts)
    fol.wind_by_height(top.z, H, 0.6)
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


def build_dead(seed, H, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    spine, ld = _trunk_spine(rng, H * 0.82, lean=0.7, n=6, wiggle=0.35, power=1.2)
    spine[0].z = -0.05
    radii = [0.42, 0.27, 0.22, 0.17, 0.12, 0.0]
    t = tube(mb, spine, radii, 6, "trunk_snow", rng, jitter=0.1)
    bark(t, rng, "trunk_snow", "trunk", snow="snow", snow_t=0.75)
    a0 = rng.uniform(0, TAU)
    for i in range(5):
        tt = 0.42 + 0.12 * i + rng.uniform(-0.03, 0.03)
        k = tt * (len(spine) - 1)
        i0 = int(k)
        st = spine[i0].lerp(spine[min(i0 + 1, len(spine) - 1)], k - i0)
        a = a0 + i * 2.3 + rng.uniform(-0.3, 0.3)
        Lb = (1.9 - 0.25 * i) * rng.uniform(0.85, 1.1)
        d = dirvec(a)
        p0 = st
        p3 = p0 + d * Lb + Vector((0, 0, Lb * rng.uniform(0.5, 0.9)))
        p1 = p0 + d * Lb * 0.4 + Vector((0, 0, 0.1))
        p2 = p0 + d * Lb * 0.75 + dirvec(a + 1.5) * 0.3 + Vector((0, 0, Lb * 0.3))
        pts = bez(p0, p1, p2, p3, 4)
        br = tube(mb, pts, [0.17 - 0.012 * i, 0.12, 0.07, 0.0], 5, "trunk_snow", rng, jitter=0.08)
        bark(br, rng, "trunk_snow", "trunk", snow="snow", snow_t=0.5)
        # twig
        q0 = pts[2]
        da = a + rng.choice((-1, 1)) * rng.uniform(0.7, 1.2)
        q1 = q0 + dirvec(da) * 0.7 + Vector((0, 0, 0.45))
        tw = tube(mb, [q0, q0.lerp(q1, 0.5) + Vector((0, 0, 0.1)), q1], [0.07, 0.05, 0.0], 4, "trunk_snow", rng)
        bark(tw, rng, "trunk_snow", "trunk", snow="snow", snow_t=0.5)
    _roots(mb, rng, 4, 0.42, "trunk_snow", "trunk")
    fit_height(mb, H)
    mb.collider_capsule(0.35, 3.0)
    mb.tag("occluder")
    return mb.finish()


# ================================================================= BAMBOO
def leaf_tent(mb, base, direction, length, width, droop, color, rng, slot=FOL):
    """Long leaf = 2-tri 'tent' (ridge up) - always faces the high camera."""
    d = Vector(direction)
    d.z = 0
    d.normalize()
    side = Vector((-d.y, d.x, 0))
    b = Vector(base)
    tip = b + d * length + Vector((0, 0, -droop))
    mid = b + d * length * 0.4 + Vector((0, 0, -droop * 0.25))
    lw = mid + side * width * 0.5 + Vector((0, 0, -width * 0.25))
    rw = mid - side * width * 0.5 + Vector((0, 0, -width * 0.25))
    p = geo(mb, [b, lw, tip, rw], [(0, 1, 2), (0, 2, 3)], color, slot)
    # make sure both faces point up (geo winding check)
    for f in p.flist:
        if nrm(f).z < 0:
            f.normal_flip()
    return p


def leaf_spray(mb, rng, base, out_dir, n, length, width=0.13, colors=("bamboo_light", "leaf")):
    parts = []
    a0 = math.atan2(out_dir.y, out_dir.x)
    for k in range(n):
        a = a0 + (k - (n - 1) / 2) * rng.uniform(0.45, 0.65)
        L_ = length * rng.uniform(0.8, 1.1)
        parts.append(leaf_tent(mb, base, dirvec(a), L_, width * rng.uniform(0.9, 1.15), L_ * rng.uniform(0.25, 0.5),
                               colors[0] if rng.random() < 0.55 else colors[1], rng))
    return parts


def culm(mb, rng, base, height, r, lean, nodes, sides=6, color="bamboo", light="bamboo_light"):
    """Bamboo culm: tapered segments with flared dark node bands, pointed tip.
    lean = horizontal offset (Vector) of the top; bends progressively."""
    base = Vector(base)
    zs = [0.0]
    # node heights spread over the lower 75 %
    for k in range(nodes):
        zn = height * (0.18 + 0.62 * (k + 0.5) / nodes) + rng.uniform(-0.15, 0.15) * height / (nodes + 2)
        zs.append(zn)
        zs.append(zn + 0.16)
    zs.append(height)
    pts, radii = [], []
    for i, z in enumerate(zs):
        t = z / height
        p = base + lean * (t ** 1.6)
        p.z = base.z + z
        pts.append(p)
        rr = r * (1.0 - 0.35 * t)
        if i == len(zs) - 1:
            rr = 0.0
        elif i > 0 and i % 2 == 0:     # top of a node band: flare
            rr *= 1.22
        radii.append(rr)
    t = tube(mb, pts, radii, sides, color, rng, phase=rng.uniform(0, TAU))
    # colour: node bands dark, lit faces light
    faces = t.faces
    for f in faces:
        zc = f.calc_center_median().z - base.z
        band = any(zs[2 * k + 1] - 0.01 <= zc <= zs[2 * k + 2] + 0.01 for k in range(nodes))
        if band:
            mb._tag([f], "bamboo_dark")
        else:
            n = nrm(f)
            if (-n.x * 0.6 + n.y * 0.5 + n.z) > 0.25:
                mb._tag([f], light)
    return t, pts


def build_bamboo_cluster(seed, name, nculm=9, H=9.0, spread=0.55, n2=5, spray=(4, 4, 4)):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    leaves = []
    a0 = rng.uniform(0, TAU)
    dry = rng.randrange(nculm)
    for i in range(nculm):
        a = a0 + i * 2.4 + rng.uniform(-0.3, 0.3)
        d = math.sqrt((i + 0.5) / nculm) * spread
        base = Vector((math.cos(a) * d, math.sin(a) * d, -0.05))
        h = H * rng.uniform(0.82, 1.0) if i > 1 else H * rng.uniform(0.95, 1.0)
        out = dirvec(a)
        lean = out * h * rng.uniform(0.1, 0.17) + dirvec(rng.uniform(0, TAU)) * 0.25
        col, lt = ("bamboo_dry", "bamboo_light") if i == dry else ("bamboo", "bamboo_light")
        nodes = 2 if i < n2 else 1
        c, pts = culm(mb, rng, base, h, rng.uniform(0.1, 0.13), lean, nodes, color=col, light=lt)
        for k, nl in enumerate(spray):
            t = 0.52 + 0.4 * (k + rng.uniform(0.1, 0.9)) / len(spray)
            p = base + lean * (t ** 1.6) + Vector((0, 0, h * t))
            od = dirvec(a + rng.uniform(-1.5, 1.5))
            leaves += leaf_spray(mb, rng, p, od, nl, rng.uniform(1.0, 1.25), width=0.18)
        leaves += leaf_spray(mb, rng, pts[-1] + Vector((0, 0, -0.4)), dirvec(a + rng.uniform(-1, 1)), 3, 0.95,
                             width=0.17)
    fol = group(mb, *leaves)
    fol.wind_by_height(H * 0.4, H, 0.9)
    mb.collider_capsule(0.8, 3.0)
    mb.tag("occluder")
    return mb.finish()


def build_bamboo_wall(seed, name, length=6.0, H=9.0, n=13):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    leaves = []
    for i in range(n):
        x = -length / 2 + 0.25 + (length - 0.5) * (i + rng.uniform(-0.25, 0.25)) / (n - 1)
        y = (0.2 if i % 2 else -0.2) + rng.uniform(-0.08, 0.08)
        base = Vector((x, y, -0.05))
        h = H * rng.uniform(0.85, 1.05)
        lean = Vector((rng.uniform(-0.7, 0.7), rng.uniform(-0.15, 0.15) + (0.15 if y > 0 else -0.15), 0))
        col = "bamboo_dry" if rng.random() < 0.12 else "bamboo"
        nodes = 2 if i % 3 else 1
        c, pts = culm(mb, rng, base, h, rng.uniform(0.1, 0.13), lean, nodes, color=col)
        for k in range(3):
            t = 0.52 + 0.4 * (k + rng.uniform(0.1, 0.9)) / 3
            p = base + lean * (t ** 1.6) + Vector((0, 0, h * t))
            side = 1 if (k + i) % 2 else -1
            od = dirvec(rng.uniform(-0.5, 0.5) + (0 if side > 0 else math.pi))
            leaves += leaf_spray(mb, rng, p, od, 3, rng.uniform(1.0, 1.2), width=0.18)
        leaves += leaf_spray(mb, rng, pts[-1] + Vector((0, 0, -0.4)),
                             dirvec(rng.choice((0, math.pi)) + rng.uniform(-0.5, 0.5)), 3, 0.9, width=0.17)
    fol = group(mb, *leaves)
    fol.wind_by_height(H * 0.4, H, 0.9)
    mb.collider_box((length, 0.9, 3.0), (0, 0, 1.5))
    mb.tag("occluder")
    return mb.finish()


def build_bamboo_young(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    leaves = []
    a0 = rng.uniform(0, TAU)
    for i in range(5):
        a = a0 + i * 2.4
        d = math.sqrt((i + 0.5) / 5) * 0.35
        base = Vector((math.cos(a) * d, math.sin(a) * d, -0.03))
        h = 2.5 * rng.uniform(0.7, 1.0) if i else 2.5
        lean = dirvec(a) * h * 0.12
        c, pts = culm(mb, rng, base, h, 0.06, lean, 1, sides=6)
        for k in range(2):
            t = rng.uniform(0.55, 0.85)
            p = base + lean * (t ** 1.6) + Vector((0, 0, h * t))
            leaves += leaf_spray(mb, rng, p, dirvec(a + rng.uniform(-1.4, 1.4)), 3, 0.45, width=0.1)
        leaves += leaf_spray(mb, rng, pts[-1] + Vector((0, 0, -0.15)), dirvec(rng.uniform(0, TAU)), 2, 0.4, width=0.09)
    # bamboo shoots (takenoko)
    for k in range(2):
        a = rng.uniform(0, TAU)
        c = dirvec(a) * rng.uniform(0.55, 0.75)
        sh = mb.cone((c.x, c.y, -0.02), 0.09, rng.uniform(0.28, 0.4), 5, "bamboo_dry", base=False)
        sh.jitter(0.015)
        shade(sh, "bamboo_dry", "wood_light", "wood_light", t_top=0.5, rng=rng, alt_side="bamboo_dry", p_alt_side=0.5)
    fol = group(mb, *leaves)
    fol.wind_by_height(0.6, 2.5, 1.0)
    mb.collider_none()
    return mb.finish()


# ================================================================= BUSHES / GROUND COVER
BUSH_SCHEMES = [("leaf_light", "leaf", "leaf_dark"), ("leaf", "leaf_dark", "leaf_dark"),
                ("leaf_light", "leaf_light", "leaf")]


def _bush_blobs(mb, rng, specs, schemes, segs=6, rings=4, jitter=0.18):
    parts = []
    for k, (c, r, sc) in enumerate(specs):
        cols = schemes[k % len(schemes)]
        b = blob(mb, c, r, rng, scale=sc, segs=segs, rings=rings, jitter=jitter)
        shade(b, cols[0], cols[1], cols[2], t_top=0.45, t_under=-0.2, rng=rng,
              alt=cols[1], p_alt=0.35, alt_side=cols[2], p_alt_side=0.35)
        drop_below_ground(mb, b, 0.0)
        parts.append(b)
    return parts


def build_bush(seed, name, H, n=5, wide=1.0, schemes=None, nleaf=6):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    r0 = H * 0.5
    specs = [((0, 0, H - r0 * 0.95), r0, (1.05 * wide, 1.0, 0.85))]
    a0 = rng.uniform(0, TAU)
    for i in range(n - 2):
        a = a0 + TAU * i / (n - 2) + rng.uniform(-0.4, 0.4)
        r = r0 * rng.uniform(0.62, 0.78)
        c = dirvec(a) * r0 * rng.uniform(0.75, 0.95) * wide
        specs.append(((c.x, c.y, r * rng.uniform(0.55, 0.8)), r, (1.0, 1.0, 0.85)))
    c = dirvec(rng.uniform(0, TAU)) * r0 * 0.35
    specs.append(((c.x, c.y, H - r0 * 0.45), r0 * 0.55, (1, 1, 0.9)))
    schemes = schemes or [BUSH_SCHEMES[0], BUSH_SCHEMES[1], BUSH_SCHEMES[0], BUSH_SCHEMES[2]]
    parts = _bush_blobs(mb, rng, specs, schemes)
    # a few leaves poking out of the silhouette
    for i in range(nleaf):
        a = a0 + TAU * (i + 0.5) / nleaf + rng.uniform(-0.3, 0.3)
        z = rng.uniform(0.35, 0.75) * H
        base = dirvec(a) * r0 * 0.8 * wide + Vector((0, 0, z))
        parts.append(leaf_tent(mb, base, dirvec(a + rng.uniform(-0.4, 0.4)), r0 * 0.75, r0 * 0.3,
                               r0 * 0.25, rng.choice(("leaf", "leaf_light")), rng))
    fit_height(mb, H, z_from=0.0)
    fol = group(mb, *parts)
    fol.wind_by_height(0.15, H, 0.4)
    mb.collider_none()
    return mb.finish()


def build_azalea(seed, name, flower):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    H = 0.9
    alt = {"flower_pink": "sakura", "flower_white": "sakura_light"}.get(flower, flower)
    specs = [((0, 0, 0.42), 0.62, (1.25, 1.1, 0.78))]
    a0 = rng.uniform(0, TAU)
    for i in range(4):
        a = a0 + TAU * i / 4 + rng.uniform(-0.3, 0.3)
        c = dirvec(a) * rng.uniform(0.55, 0.7)
        r = rng.uniform(0.36, 0.44)
        specs.append(((c.x, c.y, r * 0.75), r, (1.15, 1.05, 0.8)))
    parts = []
    for (c, r, sc) in specs:
        b = blob(mb, c, r, rng, scale=sc, segs=7, rings=4, jitter=0.1)

        def fn(f):
            d = FaceDice(rng, f)
            n = nrm(f)
            if n.z > 0.5:
                return flower if d.random() < 0.7 else alt
            if n.z < -0.2:
                return "leaf_dark"
            if n.z > 0.15:
                return flower if d.random() < 0.3 else "leaf"
            return "leaf" if d.random() < 0.6 else "leaf_dark"
        b.color_faces(fn)
        parts.append(b)
    dots = []
    for b in parts[:]:
        fs = sorted((f for f in b.faces if 0.0 < nrm(f).z < 0.6), key=lambda f: tuple(f.calc_center_median()))
        for f in rng.sample(fs, min(len(fs), 4)):
            c = f.calc_center_median()
            n = nrm(f)
            tng = (f.verts[0].co - c).normalized()
            bt = n.cross(tng)
            rr = rng.uniform(0.09, 0.12)
            pts = [c + (tng * math.cos(a) + bt * math.sin(a)) * rr for a in (0, TAU / 3, 2 * TAU / 3)]
            dots.append(pyramid(mb, pts, c + n * 0.06, flower, FOL))
    for b in parts:
        drop_below_ground(mb, b, 0.0)
    fit_height(mb, H, z_from=0.0)
    fol = group(mb, *parts, *dots)
    fol.wind_by_height(0.2, H, 0.25)
    mb.collider_none()
    return mb.finish()


def build_bush_snow(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    H = 1.0
    specs = [((0, 0, 0.5), 0.55, (1.1, 1.0, 0.85)), ((0.5, 0.2, 0.3), 0.4, (1, 1, 0.85)),
             ((-0.45, -0.3, 0.28), 0.36, (1, 1, 0.85)), ((0.1, -0.45, 0.25), 0.32, (1, 1, 0.85)),
             ((-0.1, 0.15, 0.85), 0.3, (1, 1, 0.8))]
    parts = []
    for (c, r, sc) in specs:
        b = blob(mb, c, r, rng, scale=sc, segs=6, rings=4, jitter=0.18)

        def fn(f):
            d = FaceDice(rng, f)
            n = nrm(f)
            if n.z > 0.8 and f.calc_center_median().z > 0.45:
                return "snow" if d.random() < 0.8 else "snow_shade"
            if n.z < -0.2:
                return "leaf_pine_dark"
            if n.z > 0.4:
                return "leaf_pine_light" if d.random() < 0.6 else "leaf_pine"
            return "leaf_pine" if d.random() < 0.6 else "leaf_pine_dark"
        b.color_faces(fn)
        drop_below_ground(mb, b, 0.0)
        parts.append(b)
    a0 = rng.uniform(0, TAU)
    for i in range(9):
        a = a0 + TAU * i / 9 + rng.uniform(-0.2, 0.2)
        base = dirvec(a) * 0.45 + Vector((0, 0, rng.uniform(0.25, 0.6)))
        parts.append(leaf_tent(mb, base, dirvec(a), 0.38, 0.15, 0.1, rng.choice(("leaf_pine_light", "leaf_pine")), rng))
    fit_height(mb, H, z_from=0.0)
    fol = group(mb, *parts)
    fol.wind_by_height(0.15, H, 0.25)
    mb.collider_none()
    return mb.finish()


def build_grass_tuft(seed, name, n, H, cols):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    blades = []
    a0 = rng.uniform(0, TAU)
    for i in range(n):
        a = a0 + i * 2.4 + rng.uniform(-0.3, 0.3)
        r = rng.uniform(0.0, 0.12)
        base = Vector((math.cos(a) * r, math.sin(a) * r, -0.02))
        h = H * rng.uniform(0.6, 1.0)
        lean = rng.uniform(0.15, 0.45) * h
        tip = base + dirvec(a) * lean + Vector((0, 0, h))
        blades.append(blade(mb, base, tip, rng.uniform(0.07, 0.1), rng.choice(cols), rng))
    fol = group(mb, *blades)
    fol.wind_by_height(0.0, H, 1.0)
    mb.collider_none()
    return mb.finish()


def build_tall_grass(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    blades = []
    clumps = []
    for i in range(9):
        for _ in range(30):
            c = Vector((rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8), 0))
            if all((c - o).length > 0.45 for o in clumps):
                clumps.append(c)
                break
    cols = ("grass_teal", "grass_teal", "grass_light", "grass_light", "grass_dry", "grass")
    per = max(6, 80 // max(1, len(clumps)))
    for c in clumps:
        dry = rng.random() < 0.3
        for k in range(per):
            a = rng.uniform(0, TAU)
            r = rng.uniform(0, 0.2)
            base = c + Vector((math.cos(a) * r, math.sin(a) * r, -0.03))
            h = rng.uniform(0.8, 1.1) * (0.75 if k % 4 == 0 else 1.0)
            tip = base + dirvec(a) * rng.uniform(0.15, 0.4) * h + Vector((0, 0, h))
            col = "grass_dry" if (dry and rng.random() < 0.6) else rng.choice(cols)
            blades.append(blade(mb, base, tip, rng.uniform(0.09, 0.12), col, rng))
    fol = group(mb, *blades)
    fol.wind_by_height(0.0, 1.1, 1.0)
    mb.collider_none()
    mb.tag("fireflies")
    return mb.finish()


def build_reeds(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    fol = []
    for i in range(34):
        c = Vector((rng.uniform(-0.65, 0.65), rng.uniform(-0.65, 0.65), -0.03))
        h = rng.uniform(0.8, 1.4)
        a = rng.uniform(0, TAU)
        tip = c + dirvec(a) * rng.uniform(0.08, 0.3) * h + Vector((0, 0, h))
        fol.append(blade(mb, c, tip, rng.uniform(0.07, 0.1), rng.choice(("reed", "reed", "grass_light", "grass_dry")), rng))
    for i in range(6):
        c = Vector((rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), -0.03))
        h = rng.uniform(1.15, 1.4)
        lean = dirvec(rng.uniform(0, TAU)) * rng.uniform(0.05, 0.15)
        top = c + lean + Vector((0, 0, h))
        hb = top - Vector((0, 0, 0.3)) - lean * 0.2
        fol.append(blade(mb, c, hb + Vector((0, 0, 0.05)), 0.06, "reed", rng))
        head = tube(mb, [hb - Vector((0, 0, 0.02)), hb + Vector((0, 0, 0.02)), hb + Vector((0, 0, 0.24)),
                         hb + Vector((0, 0, 0.27))], [0.0, 0.06, 0.06, 0.0], 5, "wood", rng, slot=FOL)
        shade(head, "trunk_light", "wood", "trunk", t_top=0.4, rng=rng, alt_side="trunk_light", p_alt_side=0.3)
        fol.append(head)
        fol.append(blade(mb, hb + Vector((0, 0, 0.25)), top + Vector((0, 0, 0.15)), 0.04, "reed", rng, thick=0.03))
    g = group(mb, *fol)
    g.wind_by_height(0.0, 1.5, 1.0)
    mb.collider_none()
    return mb.finish()


def build_flowers(seed, name, petal_col, centre_col, n=8, star=True, nleaf=12):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    fol = []
    for i in range(nleaf):
        c = Vector((rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), -0.02))
        a = rng.uniform(0, TAU)
        h = rng.uniform(0.15, 0.3)
        fol.append(blade(mb, c, c + dirvec(a) * h * 0.5 + Vector((0, 0, h)), 0.09,
                         rng.choice(("grass", "grass_light", "leaf")), rng))
    placed = []
    for i in range(n):
        for _ in range(20):
            c = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0))
            if all((c - o).length > 0.2 for o in placed):
                break
        placed.append(c)
        h = rng.uniform(0.28, 0.45)
        head = c + dirvec(rng.uniform(0, TAU)) * 0.05 + Vector((0, 0, h))
        fol.append(blade(mb, c + Vector((0, 0, -0.02)), head + Vector((0, 0, 0.01)), 0.05, "grass", rng, thick=0.04))
        r = rng.uniform(0.09, 0.12)
        a0 = rng.uniform(0, TAU)
        k = 10
        pts = []
        for j in range(k):
            rr = r if j % 2 == 0 else r * (0.45 if star else 0.72)
            pts.append(head + dirvec(a0 + TAU * j / k) * rr + Vector((0, 0, -0.015 if j % 2 == 0 else 0.0)))
        fl = pyramid(mb, pts, head + Vector((0, 0, 0.03)), petal_col, FOL)
        fol.append(fl)
        if centre_col:
            cc = mb.cone(tuple(head + Vector((0, 0, 0.012))), 0.035, 0.035, 4, centre_col, slot=FOL, base=False)
            fol.append(cc)
    g = group(mb, *fol)
    g.wind_by_height(0.0, 0.45, 0.8)
    mb.collider_none()
    return mb.finish()


def build_lily_pads(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    pads = []
    for i in range(7):
        for _ in range(30):
            c = Vector((rng.uniform(-0.75, 0.75), rng.uniform(-0.75, 0.75), 0.02))
            r = rng.uniform(0.28, 0.45)
            if all((c - o).length > (r + orr) * 0.95 for o, orr in pads):
                break
        pads.append((c, r))
        n = 9
        a0 = rng.uniform(0, TAU)
        notch = 0.55
        pts = []
        for j in range(n):
            a = a0 + notch / 2 + (TAU - notch) * j / (n - 1)
            pts.append(c + dirvec(a) * r * rng.uniform(0.93, 1.03))
        co = [tuple(c + Vector((0, 0, 0.025)))] + [tuple(p) for p in pts]
        faces = [(0, j + 1, j + 2) for j in range(n - 1)]
        col = rng.choice(("leaf", "leaf", "leaf_dark", "grass_light"))
        p = geo(mb, co, faces, col)
        p.color_faces(lambda f: FaceDice(rng, f).choice((col, col, "leaf_dark" if col != "leaf_dark" else "leaf")))
    # lotus flowers
    for li in range(2):
        c, r = pads[li]
        base = c + Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), 0.03))
        if li == 0:
            a0 = rng.uniform(0, TAU)
            for ring, (cnt, rad, ht, out, cols) in enumerate(((7, 0.16, 0.13, 0.2, ("sakura_light", "flower_pink")),
                                                              (5, 0.09, 0.18, 0.1, ("flower_pink", "sakura")))):
                for j in range(cnt):
                    a = a0 + TAU * (j + 0.5 * ring) / cnt
                    d = dirvec(a)
                    sd = dirvec(a + math.pi / 2)
                    b0 = base + d * rad * 0.25 - sd * 0.06
                    b1 = base + d * rad * 0.25 + sd * 0.06
                    b2 = base + d * (rad * 0.25 - 0.05)
                    tip = base + d * (rad + out * 0.6) + Vector((0, 0, ht))
                    pyramid(mb, [b0, b1, b2], tip, cols[j % 2])
            mb.cone(tuple(base + Vector((0, 0, 0.02))), 0.05, 0.06, 5, "flower_yellow", base=False)
        else:
            bud = tube(mb, [base, base + Vector((0, 0, 0.1)), base + Vector((0, 0, 0.28))], [0.0, 0.08, 0.0], 4,
                       "flower_pink", rng)
            shade(bud, "sakura_light", "flower_pink", "sakura", t_top=0.3, rng=rng)
    mb.collider_none()
    return mb.finish()


# ================================================================= ROCKS / CLIFFS
def _nkey(n, salt=0):
    """Stable pseudo-random value per facet orientation (coplanar tris share it)."""
    k = (round(n.x * 6), round(n.y * 6), round(n.z * 6), salt)
    return (hash(k) % 1000) / 1000.0


def rock_colors(part, rng, light="rock_light", mid="rock", dark="rock_dark", top=None, top_t=0.72, p_top=0.8,
                top_alt=None):
    salt = rng.randrange(1000)

    def fn(f):
        n = nrm(f)
        r = _nkey(n, salt)
        if top and n.z > top_t and r < p_top:
            return top_alt if (top_alt and r < p_top * 0.3) else top
        if n.z > 0.55:
            return light if r < 0.75 else mid
        if n.z < -0.25:
            return dark
        lit = -0.5 * n.x + 0.45 * n.y + n.z * 0.6
        if lit > 0.25:
            return light if r < 0.35 else mid
        return dark if r < 0.5 else mid
    part.color_faces(fn)
    return part


def chamfer_box_pts(rng, c, sx, sy, sz, chamfer=0.38, jit=0.1, taper=0.82, cheap=False):
    cx, cy, cz = c
    pts = []
    for zn in (-1, 1):
        tp = taper if zn > 0 else 1.0
        for xn in (-1, 1):
            for yn in (-1, 1):
                for axis in (range(3) if (zn > 0 or not cheap) else (2,)):
                    p = [xn * sx * tp, yn * sy * tp, zn * sz]
                    p[axis] *= 1 - chamfer * rng.uniform(0.55, 1.45)
                    p = [p[0] + rng.uniform(-jit, jit) * sx, p[1] + rng.uniform(-jit, jit) * sy,
                         p[2] + rng.uniform(-jit, jit) * sz]
                    pts.append((cx + p[0], cy + p[1], cz + p[2]))
    return pts


def rock_chunk(mb, rng, c, sx, sy, sz, n=14, rot=None, chamfer=0.38, taper=0.82, tilt=6, **cols):
    """Faceted boulder: convex hull of a jittered chamfered box (n <= 12 -> cheaper, only top chamfered)."""
    pts = chamfer_box_pts(rng, c, sx, sy, sz, chamfer=chamfer, taper=taper, cheap=(n <= 12))
    rot = rng.uniform(0, 360) if rot is None else rot
    p = hull(mb, pts, "rock")
    M = (Matrix.Translation(Vector(c)) @ Matrix.Rotation(math.radians(rot), 4, 'Z') @
         Matrix.Rotation(math.radians(rng.uniform(-tilt, tilt)), 4, 'X') @ Matrix.Translation(-Vector(c)))
    for v in p.verts:
        v.co = M @ v.co
    rock_colors(p, rng, **cols)
    return p


def _bounds(mb):
    xs = [v.co.x for v in mb.bm.verts]
    ys = [v.co.y for v in mb.bm.verts]
    zs = [v.co.z for v in mb.bm.verts]
    return Vector((min(xs), min(ys), max(0.0, min(zs)))), Vector((max(xs), max(ys), max(zs)))


def _box_from_bounds(mb, shrink=0.85):
    mn, mx = _bounds(mb)
    size = mx - mn
    c = (mn + mx) / 2
    mb.collider_box((size.x * shrink, size.y * shrink, size.z * 0.95), (c.x, c.y, size.z * 0.95 / 2 + mn.z))


def build_rock(seed, name, size, n=14, parts=1, moss=False, snow=False, collider="box", squareness=0.25):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    sx = size * 0.5
    sy = size * rng.uniform(0.36, 0.44)
    sz = size * rng.uniform(0.28, 0.36)
    cols = {}
    if moss:
        cols = dict(top="moss", top_alt="stone_moss", top_t=0.7, p_top=0.75)
    if snow:
        cols = dict(top="snow", top_alt="snow_shade", top_t=0.45, p_top=0.95, light="rock", mid="rock",
                    dark="rock_dark")
    main = rock_chunk(mb, rng, (0, 0, sz * 0.8), sx, sy, sz, n, chamfer=0.25 + squareness * 0.5, **cols)
    chunks = [main]
    a0 = rng.uniform(0, TAU)
    for i in range(parts - 1):
        a = a0 + i * 2.2
        k = rng.uniform(0.35, 0.5)
        c = dirvec(a) * sx * 0.95
        chunks.append(rock_chunk(mb, rng, (c.x, c.y, sz * k * 0.7), sx * k, sy * k, sz * k, max(10, n - 4),
                                 **({} if snow else cols)))
    zmin = min(v.co.z for v in main.verts)
    dz = -zmin - 0.07 * sz
    for v in mb.bm.verts:
        v.co.z += dz
    for c in chunks:
        drop_below_ground(mb, c, 0.0)
    if snow:
        # thick snow cap: convex hull of the rock's upper verts, lifted and slightly enlarged
        ztop = max(v.co.z for v in main.verts)
        top = sorted((v.co.copy() for v in main.verts if v.co.z > ztop - 0.45 * sz), key=tuple)
        cx = sum(p.x for p in top) / len(top)
        cy = sum(p.y for p in top) / len(top)
        pts = []
        for p in top:
            q = Vector((cx + (p.x - cx) * 1.06, cy + (p.y - cy) * 1.06, p.z + 0.1 + rng.uniform(0, 0.05)))
            pts += [q, q - Vector((0, 0, 0.24))]
        cap = hull(mb, pts, "snow")
        cap.color_faces(lambda f: "snow" if nrm(f).z > 0.5 else "snow_shade")
    if collider == "box":
        _box_from_bounds(mb)
    elif collider == "mesh":
        mb.collider_mesh()
    else:
        mb.collider_none()
    return mb.finish()


STRATA = {
    "brown": ["rock_brown_dark", "rock_brown", "rock", "rock_brown", "rock_brown_dark", "rock", "rock_brown",
              "rock_dark"],
    "grey": ["rock_dark", "rock", "rock_brown_dark", "rock", "rock_dark", "rock", "rock_brown_dark", "rock"],
}


def _column(mb, rng, x, w, yf, yb, ztop, bands, strata, snowy, slope, front_jit=0.28, lean=0.0):
    """One faceted rock column of the cliff: ring per strata boundary, grass/snow lip + cap on top."""
    hw = w / 2
    fp = [(x - hw, yf + rng.uniform(0.3, 0.6)), (x - hw * 0.2, yf + rng.uniform(-0.1, 0.15)),
          (x + hw * 0.5, yf + rng.uniform(0.0, 0.25)), (x + hw, yf + rng.uniform(0.35, 0.7)),
          (x + hw, yb), (x - hw, yb)]
    cx = sum(p[0] for p in fp) / len(fp)
    cy = sum(p[1] for p in fp) / len(fp)
    levels = [b for b in bands if b < ztop - 0.6] + [ztop - 0.5]
    rings = []
    for li, z in enumerate(levels):
        ring = []
        inset = 0.12 * (z / max(ztop, 1.0))
        for (px, py) in fp:
            d = Vector((px - cx, py - cy, 0))
            dl = d.length
            d = d / dl if dl > 1e-4 else d
            j = 0.0 if li == 0 else rng.uniform(-front_jit, front_jit)
            o = d * (j - inset * 2) + Vector((lean * z, 0, 0))
            ring.append((px + o.x, py + o.y, z + slope * px + (rng.uniform(-0.15, 0.15) if li else 0.0)))
        rings.append(ring)
    # grass/snow lip (slightly overhanging) and top edge
    lip, top = [], []
    for (qx, qy, qz) in rings[-1]:
        d = Vector((qx - cx, qy - cy, 0))
        d = d.normalized() if d.length > 1e-4 else d
        lip.append((qx + d.x * 0.22, qy + d.y * 0.22, ztop - 0.18 + slope * qx * 0.3 + rng.uniform(-0.06, 0.06)))
        top.append((qx + d.x * 0.08, qy + d.y * 0.08, ztop + slope * qx * 0.3 + rng.uniform(-0.05, 0.12)))
    rings += [lip, top]
    part = mb.loft(rings, "rock", cap_end=True)
    nl = len(levels)
    grass_top, grass_side, ledge = ("snow", "snow_shade", "snow") if snowy else ("grass", "moss", "stone_moss")

    def fn(f):
        n = nrm(f)
        zc = f.calc_center_median().z
        if zc > ztop - 0.12 and n.z > 0.5:
            return grass_top if _nkey(n) < 0.7 else (grass_side if snowy else "grass_light")
        if zc > levels[-1] + 0.02:
            return grass_side if n.z < 0.5 else grass_top
        bi = 0
        for k in range(nl - 1):
            if zc - slope * f.calc_center_median().x > levels[k]:
                bi = k
        col = strata[bi % len(strata)]
        if n.z > 0.55:
            return ledge
        if n.z < -0.3:
            return "rock_brown_dark" if "brown" in col else "rock_dark"
        return col
    part.color_faces(fn)
    return part


def build_cliff(seed, name, W, Hc, D=5.0, layers=5, scheme="brown", snowy=False, ncol=5):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    strata = STRATA[scheme]
    bands = [-0.1]
    for i in range(layers):
        bands.append(bands[-1] + Hc / layers * rng.uniform(0.75, 1.25))
    k = Hc / bands[-1]
    bands = [b * k for b in bands]
    bands[0] = -0.1
    slope = rng.uniform(-0.06, 0.06)
    xs = [-W / 2 + W * (i + 0.5) / ncol + rng.uniform(-0.2, 0.2) * W / ncol for i in range(ncol)]
    tops = []
    for i, x in enumerate(xs):
        w = W / ncol * rng.uniform(1.4, 1.6)
        ztop = Hc * rng.uniform(0.86, 1.0)
        if i in (0, ncol - 1):
            ztop *= rng.uniform(0.88, 0.96)
        yf = -D / 2 + rng.uniform(0.0, 0.5)
        _column(mb, rng, x, w, yf, D / 2, ztop, bands, strata, snowy, slope)
        tops.append((x, w, ztop))
    # lower buttresses in front: ledges seen from the high camera
    for j in range(2 if W > 9 else 1):
        x = rng.uniform(-W / 2 + 1.5, W / 2 - 1.5)
        w = rng.uniform(1.8, 2.6)
        zt = Hc * rng.uniform(0.35, 0.55)
        _column(mb, rng, x, w, -D / 2 - rng.uniform(0.8, 1.3), -D / 2 + 1.0, zt, bands, strata, snowy, slope)
    # top decoration: grass mounds / snow drifts and a rock
    for j in range(3 if W > 9 else 2):
        x, w, zt = tops[rng.randrange(len(tops))]
        c = (x + rng.uniform(-0.5, 0.5), rng.uniform(-D * 0.2, D * 0.2), zt + 0.1)
        if snowy:
            m = pad(mb, c, rng.uniform(0.8, 1.2), rng.uniform(0.7, 1.0), 0.55, 7, rng, slot=None, under=0.4)
            shade_pad(mb, m, rng, "snow", "snow", "snow_shade", p_light=0.8, p_side_dark=0.4)
        else:
            m = pad(mb, c, rng.uniform(0.7, 1.0), rng.uniform(0.6, 0.9), 0.9, 7, rng, slot=FOL, under=0.4)
            shade_pad(mb, m, rng, "leaf_light", "leaf", "leaf_dark", p_light=0.6, p_side_dark=0.4)
            m.wind_by_height(zt, zt + 1.0, 0.3)
    x, w, zt = tops[rng.randrange(len(tops))]
    ch = rock_chunk(mb, rng, (x, rng.uniform(-1, 1), zt + 0.2), 0.7, 0.55, 0.45, 10,
                    **(dict(top="snow", top_t=0.5) if snowy else {}))
    # base boulders
    for j in range(3):
        x = rng.uniform(-W / 2 + 1, W / 2 - 1)
        sc = rng.uniform(0.55, 0.95)
        cols = dict(top="snow", top_alt="snow_shade", top_t=0.6) if snowy else {}
        if scheme == "brown":
            cols.update(light="rock_brown", mid="rock_brown", dark="rock_brown_dark")
        ch = rock_chunk(mb, rng, (x, -D / 2 - 0.9, sc * 0.55), sc, sc * 0.8, sc * 0.6, 10, **cols)
        drop_below_ground(mb, ch, 0.0)
    mb.collider_mesh()
    return mb.finish()


def build_pillar(seed, name, H=6.0):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    n = 7
    ph = rng.uniform(0, TAU)
    rings = []
    nseg = 6
    off = Vector((0, 0, 0))
    r = 1.0
    zs = [-0.15] + sorted(rng.uniform(0.5, 5.4) for _ in range(nseg - 1)) + [H - 0.25]
    for li, z in enumerate(zs):
        if li:
            off += Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0))
            r *= rng.uniform(0.88, 0.97) if li % 2 else rng.uniform(1.0, 1.08)
        ring = []
        for k in range(n):
            a = ph + TAU * k / n
            rr = r * rng.uniform(0.8, 1.1) * (1.0 if k % 2 else 0.9)
            ring.append((off.x + math.cos(a) * rr, off.y + math.sin(a) * rr * 0.85, z + rng.uniform(-0.1, 0.1) * (li > 0)))
        rings.append(ring)
    top = [(x * 0.7 + off.x * 0.3, y * 0.7 + off.y * 0.3, H + rng.uniform(-0.08, 0.05)) for (x, y, z) in rings[-1]]
    rings.append(top)
    col = mb.loft(rings, "rock", cap_end=True)
    strata = ["rock_dark", "rock", "rock_light", "rock", "rock_dark", "rock", "rock_light"]

    def fn(f):
        nn = nrm(f)
        zc = f.calc_center_median().z
        if nn.z > 0.6:
            return "snow" if zc > H - 0.6 else "snow_shade"
        if nn.z < -0.3:
            return "rock_dark"
        bi = max(i for i, z in enumerate(zs) if zc >= z - 1e-3) if zc >= zs[0] else 0
        return strata[bi % len(strata)]
    col.color_faces(fn)
    for j in range(3):
        a = ph + j * 2.1
        c = dirvec(a) * 1.15
        ch = rock_chunk(mb, rng, (c.x, c.y, 0.3), 0.55, 0.45, 0.4, 10)
        drop_below_ground(mb, ch, 0.0)
    mb.collider_box((1.9, 1.7, H), (0, 0, H / 2))
    return mb.finish()


# ================================================================= MISC NATURE
def build_log(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    Lg = 3.5
    n = 7
    pts = [Vector((-Lg / 2 + Lg * t, math.sin(t * 3.0) * 0.12, 0.3 + math.sin(t * 2.0) * 0.03))
           for t in (0, 0.25, 0.5, 0.75, 1.0)]
    radii = [0.36, 0.33, 0.32, 0.3, 0.28]
    rings = []
    ph = rng.uniform(0, TAU)
    for p, r in zip(pts, radii):
        ring = []
        for k in range(n):
            a = ph + TAU * k / n
            ring.append((p.x + rng.uniform(-0.03, 0.03), p.y + math.cos(a) * r * rng.uniform(0.92, 1.05),
                         p.z + math.sin(a) * r * rng.uniform(0.92, 1.05)))
        rings.append(ring)
    # ring order must wind so faces point outward: loft along +X with CCW around +X
    log = mb.loft(rings, "trunk", cap_start=True, cap_end=True)

    def fn(f):
        d = FaceDice(rng, f)
        n_ = nrm(f)
        if abs(n_.x) > 0.85:
            return "wood_light"
        if n_.z > 0.75:
            return "moss" if d.random() < 0.4 else ("stone_moss" if d.random() < 0.5 else "trunk_light")
        if n_.z > 0.3:
            return "trunk_light" if d.random() < 0.6 else "trunk"
        return "trunk"
    log.color_faces(fn)
    # broken branch stub
    p = pts[2] + Vector((0, 0.25, 0.15))
    stub = tube(mb, [pts[2], p + Vector((0.1, 0.25, 0.25))], [0.12, 0.07], 5, "trunk", rng)
    bark(stub, rng)
    # inner rings on the end caps
    for e, sgn in ((pts[0], -1), (pts[-1], 1)):
        ring_c = Vector((e.x + sgn * 0.012, e.y, e.z))
        pts3 = [ring_c + Vector((0, math.cos(a) * 0.15, math.sin(a) * 0.15)) for a in (0, TAU / 5, 2 * TAU / 5, 3 * TAU / 5, 4 * TAU / 5)]
        if sgn < 0:
            pts3 = list(reversed(pts3))
        pyramid(mb, pts3, ring_c + Vector((sgn * 0.02, 0, 0)), "wood_pale")
    # moss tufts
    for i in range(3):
        x = rng.uniform(-1.2, 1.2)
        ground_disc(mb, (x, rng.uniform(-0.05, 0.05), 0.64), rng.uniform(0.15, 0.22), 6, rng, "moss", h=0.06)
    # a couple of small mushrooms on the side
    mb.collider_box((Lg, 0.75, 0.66), (0, 0, 0.33))
    return mb.finish()


def build_stump(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    n = 7
    H = 0.6
    rings = []
    ph = rng.uniform(0, TAU)
    for z, r in ((-0.05, 0.5), (0.25, 0.4), (H, 0.38)):
        rings.append([(math.cos(ph + TAU * k / n) * r * rng.uniform(0.92, 1.06),
                       math.sin(ph + TAU * k / n) * r * rng.uniform(0.92, 1.06), z + (rng.uniform(-0.04, 0.06) if z == H else 0)) for k in range(n)])
    rings.append([(x * 0.78, y * 0.78, z - 0.02) for (x, y, z) in rings[-1]])
    st = mb.loft(rings, "trunk", cap_end=True)

    def fn(f):
        d = FaceDice(rng, f)
        n_ = nrm(f)
        c = f.calc_center_median()
        if n_.z > 0.85 and c.z > H - 0.1:
            r = math.hypot(c.x, c.y)
            return "wood_light" if r < 0.15 else "wood_pale"
        if n_.z > 0.3:
            return "trunk_light"
        return "trunk_light" if d.random() < 0.3 else "trunk"
    st.color_faces(fn)
    _roots(mb, rng, 4, 0.38, length=0.45)
    pyramid(mb, [(math.cos(a) * 0.1, math.sin(a) * 0.1, H + 0.01) for a in (0, TAU / 3, 2 * TAU / 3)],
            (0, 0, H + 0.025), "wood_light")
    ground_disc(mb, (0.25, -0.1, H - 0.02), 0.12, 5, rng, "moss", h=0.05)
    mb.collider_box((0.85, 0.85, H), (0, 0, H / 2))
    return mb.finish()


def build_rice(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    S = 1.0
    # shallow water slab, top at z = 0.02 (closed box so its normal can't flip)
    mb.extrude_polygon([(-S, -S), (S, -S), (S, S), (-S, S)], -0.02, 0.02, "water_shallow",
                       slot=L.SLOT_WATER)
    blades = []
    rows, cols = 5, 5
    for i in range(rows):
        for j in range(cols):
            c = Vector((-0.8 + 1.6 * j / (cols - 1) + rng.uniform(-0.04, 0.04),
                        -0.8 + 1.6 * i / (rows - 1) + rng.uniform(-0.04, 0.04), -0.02))
            a0 = rng.uniform(0, TAU)
            for k in range(3):
                a = a0 + TAU * k / 3 + rng.uniform(-0.3, 0.3)
                h = rng.uniform(0.32, 0.48)
                tip = c + dirvec(a) * rng.uniform(0.1, 0.2) + Vector((0, 0, h))
                blades.append(blade(mb, c + dirvec(a) * 0.02, tip, 0.06,
                                    rng.choice(("rice_green", "rice_green", "grass_light")), rng))
    g = group(mb, *blades)
    g.wind_by_height(0.0, 0.5, 1.0)
    mb.collider_none()
    return mb.finish()


def build_wheat(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    fol = []
    wind = dirvec(rng.uniform(0, TAU))
    nx, ny = 4, 4
    for i in range(nx):
        for j in range(ny):
            c = Vector((-0.85 + 1.7 * (i + rng.uniform(0.25, 0.75)) / nx,
                        -0.85 + 1.7 * (j + rng.uniform(0.25, 0.75)) / ny, -0.03))
            a0 = rng.uniform(0, TAU)
            for k in range(3):
                a = a0 + TAU * k / 3 + rng.uniform(-0.4, 0.4)
                base = c + dirvec(a) * rng.uniform(0.03, 0.1)
                h = rng.uniform(0.82, 1.0)
                lean = (wind * 0.5 + dirvec(a) * 0.6) * rng.uniform(0.1, 0.22)
                eb = base + lean * 0.75 + Vector((0, 0, h - 0.3))
                fol.append(blade(mb, base, eb + Vector((0, 0, 0.06)), 0.055, rng.choice(("wheat_dark", "grass_dry")),
                                 rng, thick=0.05))
                d = lean.normalized() if lean.length > 1e-3 else Vector((1, 0, 0))
                sd = Vector((-d.y, d.x, 0))
                tip = eb + d * 0.08 + Vector((0, 0, 0.32))
                ring = [eb + sd * 0.05, eb - sd * 0.05 + d * 0.01, eb - d * 0.05]
                fol.append(pyramid(mb, ring, tip, "wheat" if rng.random() < 0.75 else "wheat_dark", FOL))
    g = group(mb, *fol)
    g.wind_by_height(0.0, 1.05, 1.0)
    mb.collider_none()
    return mb.finish()


def build_cabbages(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    Lr = 3.0
    secs = []
    for k in range(6):
        x = -Lr / 2 + Lr * k / 5
        w = 0.42 + rng.uniform(-0.04, 0.04)
        h = 0.2 + rng.uniform(-0.03, 0.03)
        secs.append([(x, -w, -0.02), (x, -w * 0.55, h), (x, w * 0.55, h), (x, w, -0.02)])
    ridge = mb.loft(secs, "dirt", cap_start=True, cap_end=True, closed=False)

    def fn(f):
        n_ = nrm(f)
        return "dirt" if n_.z > 0.85 else "dirt_dark"
    ridge.color_faces(fn)
    for i in range(6):
        x = -1.2 + 2.4 * i / 5 + rng.uniform(-0.05, 0.05)
        c = Vector((x, rng.uniform(-0.04, 0.04), 0.2))
        r = rng.uniform(0.19, 0.23)
        core = blob(mb, (c.x, c.y, c.z + r * 0.7), r, rng, scale=(1, 1, 0.85), segs=6, rings=3, jitter=0.1,
                    slot=None)
        shade(core, "grass_light", "rice_green", "leaf", t_top=0.5, rng=rng, alt="rice_green", p_alt=0.3)
        a0 = rng.uniform(0, TAU)
        for k in range(5):
            a = a0 + TAU * k / 5
            base = c + dirvec(a) * r * 0.5 + Vector((0, 0, r * 0.65))
            lf = leaf_tent(mb, base, dirvec(a), r * 1.35, r * 1.0, r * 0.55, "leaf", rng, slot=None)
            lf.color_faces(lambda f: FaceDice(rng, f).choice(("leaf", "leaf_light", "grass")))
    mb.collider_none()
    return mb.finish()


def build_mushrooms(seed, name):
    rng = random.Random(seed)
    mb = L.MeshBuilder(name, seed)
    specs = [(0.0, 0.0, 0.32, 0.14, "glow_firefly"), (0.2, 0.1, 0.22, 0.1, "glow_firefly"),
             (-0.16, 0.14, 0.17, 0.08, "glow_purple"), (0.08, -0.2, 0.13, 0.07, "glow_firefly"),
             (-0.22, -0.12, 0.24, 0.1, "glow_purple")]
    for (x, y, h, r, glow) in specs:
        lean = Vector((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0))
        b = Vector((x, y, -0.01))
        top = b + lean + Vector((0, 0, h))
        st = tube(mb, [b, b.lerp(top, 0.5), top], [r * 0.38, r * 0.3, r * 0.28], 5, "paper", rng)
        shade(st, "paper", "paper", "plaster_shade", rng=rng, alt_side="plaster_shade", p_alt_side=0.4)
        n = 6
        a0 = rng.uniform(0, TAU)
        co = [tuple(top + Vector((0, 0, -0.01)))]
        for k in range(n):
            co.append(tuple(top + dirvec(a0 + TAU * k / n) * r + Vector((0, 0, -r * 0.15))))
        for k in range(n):
            co.append(tuple(top + dirvec(a0 + TAU * (k + 0.5) / n) * r * 0.6 + Vector((0, 0, r * 0.45))))
        co.append(tuple(top + Vector((0, 0, r * 0.75))))
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces += [(0, 1 + j, 1 + i), (1 + i, 1 + j, 1 + n + i), (1 + j, 1 + n + j, 1 + n + i),
                      (1 + n + i, 1 + n + j, 1 + 2 * n)]
        cap = geo(mb, co, faces, glow)
        color_kinds(mb, cap, list(range(len(cap.flist))),
                    lambda k, f: "plaster_shade" if k % 4 == 0 else (glow if k % 4 == 3 or rng.random() < 0.6 else
                                                                      ("flower_purple" if "purple" in glow else "flower_yellow")))
    ground_disc(mb, (0, 0, 0.0), 0.38, 7, rng, "moss", h=0.04)
    mb.collider_none()
    return mb.finish()


PROPS = {
    "tree_pine_a": lambda seed: build_pine(seed + 11, 6.0, "tree_pine_a", nbranch=3, subs=(0, 1)),
    "tree_pine_b": lambda seed: build_pine(seed + 23, 7.5, "tree_pine_b", nbranch=4, subs=(0, 2)),
    "tree_pine_c": lambda seed: build_pine(seed + 37, 9.0, "tree_pine_c", nbranch=5, subs=(1, 3), pn=8),
    "tree_cedar_a": lambda seed: build_cedar(seed + 5, 11.0, "tree_cedar_a"),
    "tree_cedar_b": lambda seed: build_cedar(seed + 17, 12.8, "tree_cedar_b", ntier=8, z0f=0.27, width=0.155,
                                              lean_amt=(0.35, 0.5)),
    "tree_pine_snow_a": lambda seed: build_snow_pine(seed + 3, 7.5, "tree_pine_snow_a", 5),
    "tree_pine_snow_b": lambda seed: build_snow_pine(seed + 29, 9.8, "tree_pine_snow_b", 6),
    "tree_sakura_a": lambda seed: build_sakura(seed + 7, 5.2, "tree_sakura_a", 3),
    "tree_sakura_b": lambda seed: build_sakura(seed + 41, 6.4, "tree_sakura_b", 5),
    "tree_maple_a": lambda seed: build_maple(seed + 13, 5.0, "tree_maple_a"),
    "tree_round_a": lambda seed: build_round(seed + 19, 6.2, "tree_round_a"),
    "tree_round_b": lambda seed: build_round(seed + 31, 7.0, "tree_round_b"),
    "tree_dead_a": lambda seed: build_dead(seed + 43, 5.0, "tree_dead_a"),
    "bamboo_cluster_a": lambda seed: build_bamboo_cluster(seed + 2, "bamboo_cluster_a", 9, 9.0, 0.55),
    "bamboo_cluster_b": lambda seed: build_bamboo_cluster(seed + 52, "bamboo_cluster_b", 11, 8.5, 0.75, n2=4, spray=(3, 3, 3)),
    "bamboo_wall": lambda seed: build_bamboo_wall(seed + 8, "bamboo_wall"),
    "bamboo_young": lambda seed: build_bamboo_young(seed + 4, "bamboo_young"),
    "bush_round_a": lambda seed: build_bush(seed + 1, "bush_round_a", 1.1, 5),
    "bush_round_b": lambda seed: build_bush(seed + 14, "bush_round_b", 1.4, 6, 1.1, nleaf=8),
    "bush_round_c": lambda seed: build_bush(seed + 27, "bush_round_c", 0.8, 4, 1.35,
                                              schemes=[BUSH_SCHEMES[2], BUSH_SCHEMES[0], BUSH_SCHEMES[1]]),
    "bush_azalea_pink": lambda seed: build_azalea(seed + 3, "bush_azalea_pink", "flower_pink"),
    "bush_azalea_white": lambda seed: build_azalea(seed + 33, "bush_azalea_white", "flower_white"),
    "bush_snow": lambda seed: build_bush_snow(seed + 6, "bush_snow"),
    "grass_tuft_a": lambda seed: build_grass_tuft(seed + 9, "grass_tuft_a", 9, 0.35, ("grass", "grass", "grass_light")),
    "grass_tuft_b": lambda seed: build_grass_tuft(seed + 19, "grass_tuft_b", 12, 0.5, ("grass", "grass_light", "grass_light", "grass_dark")),
    "tall_grass_patch": lambda seed: build_tall_grass(seed + 21, "tall_grass_patch"),
    "reeds_patch": lambda seed: build_reeds(seed + 15, "reeds_patch"),
    "flowers_yellow": lambda seed: build_flowers(seed + 5, "flowers_yellow", "flower_yellow", "wood_light", 7, False, 10),
    "flowers_blue": lambda seed: build_flowers(seed + 25, "flowers_blue", "flower_blue", None, 7, True),
    "flowers_pink": lambda seed: build_flowers(seed + 45, "flowers_pink", "flower_pink", "flower_yellow", 7, True, 9),
    "lily_pads": lambda seed: build_lily_pads(seed + 12, "lily_pads"),
    "rock_small_a": lambda seed: build_rock(seed + 1, "rock_small_a", 0.5, 12, 1, collider="box"),
    "rock_small_b": lambda seed: build_rock(seed + 2, "rock_small_b", 0.45, 10, 2, collider="none", squareness=0.4),
    "rock_medium_a": lambda seed: build_rock(seed + 3, "rock_medium_a", 1.3, 14, 2, collider="box"),
    "rock_medium_b": lambda seed: build_rock(seed + 4, "rock_medium_b", 1.25, 16, 1, collider="box", squareness=0.45),
    "rock_large_a": lambda seed: build_rock(seed + 5, "rock_large_a", 2.5, 18, 3, moss=True, collider="box"),
    "rock_large_b": lambda seed: build_rock(seed + 6, "rock_large_b", 2.75, 20, 2, moss=True, collider="mesh",
                                            squareness=0.4),
    "rock_snow_a": lambda seed: build_rock(seed + 7, "rock_snow_a", 1.75, 16, 2, snow=True, collider="box"),
    "cliff_a": lambda seed: build_cliff(seed + 1, "cliff_a", 10.0, 10.0, 5.0, 5, "brown"),
    "cliff_b": lambda seed: build_cliff(seed + 2, "cliff_b", 11.8, 14.0, 6.0, 7, "brown"),
    "cliff_c": lambda seed: build_cliff(seed + 3, "cliff_c", 9.0, 12.0, 5.0, 6, "grey", snowy=True),
    "rock_pillar": lambda seed: build_pillar(seed + 9, "rock_pillar"),
    "log_fallen": lambda seed: build_log(seed + 3, "log_fallen"),
    "stump": lambda seed: build_stump(seed + 5, "stump"),
    "rice_patch": lambda seed: build_rice(seed + 7, "rice_patch"),
    "wheat_patch": lambda seed: build_wheat(seed + 9, "wheat_patch"),
    "cabbage_row": lambda seed: build_cabbages(seed + 11, "cabbage_row"),
    "mushroom_cluster": lambda seed: build_mushrooms(seed + 13, "mushroom_cluster"),
}
