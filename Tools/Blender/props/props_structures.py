"""Nindo -- structures: houses, dojo, walls, gates, bridges, docks, stairs, fences,
shrines, torii, pagoda...

All builders follow STYLE.md: origin at the centre of the footprint, ground at z=0,
front = Blender -Y.  Water props (house_fisher, dock/boardwalk, lake arena) use
z=0 as the WATER SURFACE.  Door leaves (dojo_gate_door, wall_gate_door) have their
origin on the HINGE edge and extend toward +X.

Implementation notes
--------------------
* nindo_lib.MeshBuilder.finish() recalculates normals per connected island, which
  is only reliable for closed (or clearly convex-open) shells; a lone quad or an open
  curved strip can come out flipped.  Every piece here is therefore a closed solid
  (boxes, prisms, capped lofts) so the normals are always outward.
* Roofs are generated from a height field over the eave rectangle (see `Roof`):
  contour rings of "distance from the eave" are lofted into a thick closed slab,
  which gives hip (yosemune), hip-and-gable (irimoya) and truncated (mokoshi)
  roofs from the same code, with optional concave curve (sori), up-turned corners,
  stepped thatch layers, tile ribs and hip/verge ridges.
"""
import math
import random
from mathutils import Vector

import nindo_lib as L


# ============================================================== basic helpers
_DIRS = {'+x': (0, 1), '-x': (0, -1), '+y': (1, 1), '-y': (1, -1), '+z': (2, 1), '-z': (2, -1)}


def bx(mb, x0, x1, y0, y1, z0, z1, color, drop=(), **kw):
    """Box from min/max coordinates.  drop = faces never seen, e.g. ('-z', '+y')."""
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    z0, z1 = min(z0, z1), max(z0, z1)
    p = mb.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), color, **kw)
    if drop:
        drop_faces(mb, p, drop, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return p


def drop_faces(mb, part, drop, center):
    import bmesh
    kill = []
    for f in part.faces:
        c = f.calc_center_median()
        d = c - Vector(center)
        for key in drop:
            ax, sg = _DIRS[key]
            comp = (d.x, d.y, d.z)[ax]
            others = [abs(v) for i, v in enumerate((d.x, d.y, d.z)) if i != ax]
            if comp * sg > 1e-6 and all(o < 1e-5 for o in others):
                kill.append(f)
    if kill:
        bmesh.ops.delete(mb.bm, geom=kill, context='FACES_ONLY')


def rbox(mb, loc, size, color, rz=0.0, rx=0.0, ry=0.0, **kw):
    return mb.box(loc, size, color, rot=(rx, ry, rz), **kw)


def loft_dd(mb, rings, color, cap_start=False, cap_end=False, closed=True, slot=None, eps=1e-4, skip_seg=None):
    """Loft that de-duplicates coincident points (rings may collapse to lines/points).
    Returns (part, faces_by_band) where faces_by_band[i] lists (face, seg_index)."""
    bm = mb.bm
    cache = {}

    def V(p):
        k = (round(p[0] / eps), round(p[1] / eps), round(p[2] / eps))
        v = cache.get(k)
        if v is None:
            v = bm.verts.new(Vector(p))
            cache[k] = v
        return v

    vr = [[V(p) for p in ring] for ring in rings]
    made = []

    def addf(vs):
        out = []
        for v in vs:
            if not out or out[-1] is not v:
                out.append(v)
        while len(out) > 1 and out[0] is out[-1]:
            out.pop()
        if len(out) < 3 or len(set(out)) != len(out):
            return None
        try:
            f = bm.faces.new(out)
        except ValueError:
            return None
        made.append(f)
        return f

    n = len(rings[0])
    bands = []
    for a, b in zip(vr[:-1], vr[1:]):
        band = []
        for i in range(n if closed else n - 1):
            if i == skip_seg:
                continue
            j = (i + 1) % n
            f = addf([a[i], a[j], b[j], b[i]])
            if f is not None:
                band.append((f, i))
        bands.append(band)
    caps = []
    if cap_start:
        f = addf(list(reversed(vr[0])))
        if f:
            caps.append(f)
    if cap_end:
        f = addf(vr[-1])
        if f:
            caps.append(f)
    part = mb._new(list(cache.values()), color, slot, None)
    return part, bands, caps


def tube(mb, pts, section, color, caps=True, up=Vector((0, 0, 1)), slot=None, skip_seg=None):
    """Closed prism lofted along a polyline. section = [(u, v)] in the local frame
    (u = horizontal side, v = 'up' perpendicular to the path)."""
    pts = [Vector(p) for p in pts]
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        t.normalize()
        side = t.cross(up)
        if side.length < 1e-6:
            side = Vector((1, 0, 0))
        side.normalize()
        nup = side.cross(t).normalized()
        rings.append([tuple(p + side * u + nup * v) for (u, v) in section])
    part, _, _ = loft_dd(mb, rings, color, cap_start=caps, cap_end=caps, slot=slot, skip_seg=skip_seg)
    return part


def rect_section(w, h, v0=0.0):
    return [(-w / 2, v0), (w / 2, v0), (w / 2, v0 + h), (-w / 2, v0 + h)]


def stone_slab(mb, x, y, z_top, rx, ry, h, color="stone", sides=7, rz=0.0, jit=0.03, top_shrink=0.85):
    p = mb.prism((0, 0, 0), 1.0, h, sides, color, radius_top=top_shrink, base=False)
    p.transform(scale=(rx, ry, 1.0))
    p.transform(rot=(0, 0, rz))
    p.transform(loc=(x, y, z_top - h))
    if jit:
        p.jitter(jit, axes=(1, 1, 0.3))
    return p


def footing(mb, x, y, z_top, r=0.17, color="stone"):
    return mb.prism((x, y, -0.02), r, z_top + 0.02, 6, color, radius_top=r * 0.8, base=False)


def frange(a, b, n):
    """n+1 evenly spaced values from a to b."""
    return [a + (b - a) * i / n for i in range(n + 1)]


# ============================================================== wall helper
class Facade:
    """Local frame on a wall: u runs along the wall, v = z, w = outward offset from
    the wall's outer plane.  axis 'x': wall parallel to X at y = plane, outward = sign*Y.
    axis 'y': wall parallel to Y at x = plane, outward = sign*X."""

    def __init__(self, mb, axis, plane, sign):
        self.mb, self.axis, self.plane, self.sign = mb, axis, plane, sign

    def p(self, u, v, w):
        if self.axis == 'x':
            return (u, self.plane + self.sign * w, v)
        return (self.plane + self.sign * w, u, v)

    def box(self, u0, u1, v0, v1, w0, w1, color, back=False, **kw):
        a = self.p(u0, v0, w0)
        b = self.p(u1, v1, w1)
        drop = () if (back or w0 > -0.005) else (('-' if self.sign > 0 else '+') + ('y' if self.axis == 'x' else 'x'),)
        return bx(self.mb, a[0], b[0], a[1], b[1], a[2], b[2], color, drop=drop, **kw)

    def window(self, uc, v0, v1, width, bars=4, frame="wood_dark", bar="wood_dark",
               glow="glow_window", sill=True, hbars=0, fw=0.07):
        """Glowing window with a dark frame and vertical (and optional horizontal) bars."""
        u0, u1 = uc - width / 2, uc + width / 2
        self.box(u0 - fw, u1 + fw, v0, v1, -0.03, 0.045, frame)
        self.box(u0, u1, v0, v1, -0.03, 0.055, glow)
        self.box(u0 - fw - 0.02, u1 + fw + 0.02, v1, v1 + fw, -0.03, 0.08, frame)
        self.box(u0 - fw - 0.02, u1 + fw + 0.02, v0 - fw, v0, -0.03, 0.1 if sill else 0.08, frame)
        for i in range(1, bars + 1):
            u = u0 + (u1 - u0) * i / (bars + 1)
            self.box(u - 0.025, u + 0.025, v0, v1, -0.02, 0.085, bar)
        for i in range(1, hbars + 1):
            v = v0 + (v1 - v0) * i / (hbars + 1)
            self.box(u0, u1, v - 0.022, v + 0.022, -0.02, 0.075, bar)

    def shoji(self, u0, u1, v0, v1, panels=2, cols=2, rows=3, frame="wood_dark", kumiko="wood",
              glow="glow_window", koshi=0.0):
        """Row of sliding paper doors: glowing pane, panel stiles and a kumiko grid."""
        self.box(u0, u1, v0, v1, -0.03, 0.02, glow)
        pw = (u1 - u0) / panels
        fw = 0.06
        # rails
        self.box(u0, u1, v1 - fw, v1, -0.03, 0.06, frame)
        self.box(u0, u1, v0, v0 + fw + koshi, -0.03, 0.06, frame)
        for k in range(panels + 1):
            u = u0 + pw * k
            a = max(u0, u - fw / 2) if 0 < k < panels else (u0 if k == 0 else u1 - fw)
            self.box(a, a + fw, v0, v1, -0.03, 0.06, frame)
        vv0 = v0 + fw + koshi
        for k in range(panels):
            pu0, pu1 = u0 + pw * k, u0 + pw * (k + 1)
            for i in range(1, cols + 1):
                u = pu0 + (pu1 - pu0) * i / (cols + 1)
                self.box(u - 0.02, u + 0.02, vv0, v1 - fw, -0.02, 0.045, kumiko)
        for i in range(1, rows + 1):
            v = vv0 + (v1 - fw - vv0) * i / (rows + 1)
            self.box(u0, u1, v - 0.02, v + 0.02, -0.02, 0.045, kumiko)


def timber_box(mb, x0, x1, y0, y1, zf, zt, post=0.2, spacing=1.8, post_col="wood_dark",
               wall_col="plaster", koshi=0.0, koshi_col="wood", beam_col="wood_dark",
               sill_h=0.13, beam_h=0.22, skip_posts=(), extra_posts=None, recess=0.07, hide_top=True):
    """Timber-frame house body: plaster core recessed behind dark posts, sill and top
    beam, optional lower board skirting (koshi).  Returns the 4 Facades (front,
    back, left, right) whose plane is the CORE (plaster) surface."""
    r = recess
    bx(mb, x0 + r, x1 - r, y0 + r, y1 - r, zf, zt, wall_col, drop=('-z', '+z') if hide_top else ('-z',))
    # posts (outer face flush with the footprint)
    xs = _spaced(x0 + post / 2, x1 - post / 2, spacing)
    ys = _spaced(y0 + post / 2, y1 - post / 2, spacing)
    pts = set()
    for x in xs:
        pts.add((round(x, 3), round(y0 + post / 2, 3)))
        pts.add((round(x, 3), round(y1 - post / 2, 3)))
    for y in ys:
        pts.add((round(x0 + post / 2, 3), round(y, 3)))
        pts.add((round(x1 - post / 2, 3), round(y, 3)))
    for e in (extra_posts or []):
        pts.add((round(e[0], 3), round(e[1], 3)))
    for (x, y) in sorted(pts):
        if any(abs(x - sx) < 0.05 and abs(y - sy) < 0.05 for sx, sy in skip_posts):
            continue
        bx(mb, x - post / 2, x + post / 2, y - post / 2, y + post / 2, zf - 0.02, zt + 0.02, post_col,
           drop=('-z', '+z') if hide_top else ('-z',))
    # sill + top beam (beam slightly proud of the posts, sill slightly recessed)
    for (o, z0, z1) in ((0.025, zf, zf + sill_h), (-0.03, zt - beam_h, zt)):
        bx(mb, x0 + o, x1 - o, y0 + o, y0 + o + 0.16, z0, z1, beam_col)
        bx(mb, x0 + o, x1 - o, y1 - o - 0.16, y1 - o, z0, z1, beam_col)
        bx(mb, x0 + o, x0 + o + 0.16, y0 + o, y1 - o, z0 + 0.002, z1 - 0.002, beam_col)
        bx(mb, x1 - o - 0.16, x1 - o, y0 + o, y1 - o, z0 + 0.002, z1 - 0.002, beam_col)
    if koshi > 0:
        o = 0.045
        zk0, zk1 = zf + sill_h - 0.01, zf + sill_h + koshi
        bx(mb, x0 + o, x1 - o, y0 + o, y1 - o, zk0, zk1, koshi_col)
        bx(mb, x0 + o - 0.012, x1 - o + 0.012, y0 + o - 0.012, y1 - o + 0.012, zk1 - 0.005, zk1 + 0.05, beam_col)
    return (Facade(mb, 'x', y0 + r, -1), Facade(mb, 'x', y1 - r, 1),
            Facade(mb, 'y', x0 + r, -1), Facade(mb, 'y', x1 - r, 1))


def _spaced(a, b, spacing):
    n = max(1, int(round((b - a) / spacing)))
    return [a + (b - a) * i / n for i in range(n + 1)]


# ============================================================== roofs
class Roof:
    """Height-field roof over the eave rectangle |x|<=W, |y|<=D (local, centred at cx,cy).

    d(x, y) = distance from the eave contour (rectangular rings).  Hip slopes on
    the short sides stop at |x| = xg, above which a vertical gable triangle rises
    (irimoya).  xg = W - D -> pure hip roof; ze = top of the slab at the eave,
    H = rise from eave to ridge.  curve > 0 -> concave (sori) profile.  lift raises
    the eave corners (up-turned eaves).  steps = [(d, h)] stepped thatch layers."""

    def __init__(self, W, D, ze, H, xg=None, curve=0.0, lift=0.0, lift_len=None, cx=0.0, cy=0.0,
                 steps=(), nlev=3, frL=None, frS=None, flare=0.0):
        self.W, self.D, self.ze, self.H = W, D, ze, H
        self.xg = max(W - D, 0.0) if xg is None else xg
        self.dg = W - self.xg
        self.curve, self.lift = curve, lift
        self.Lc = lift_len or min(W, D) * 0.9
        self.cx, self.cy = cx, cy
        self.steps = sorted(steps)
        self.nlev = nlev
        self.frL = frL or [0.0, 0.1, 0.25, 0.5, 0.75, 0.9]
        self.frS = frS or [0.0, 0.15, 0.5, 0.85]
        self.flare = flare

    # ---- height field (local coordinates)
    def base(self, d):
        t = max(0.0, min(1.0, d / self.D))
        return self.ze + self.H * ((1 - self.curve) * t + self.curve * t * t)

    def stepped(self, d, inclusive=True):
        return sum(h for ds, h in self.steps if (ds <= d + 1e-9 if inclusive else ds < d - 1e-9))

    def lift_at(self, x, y):
        if not self.lift:
            return 0.0
        lx = min(1.0, max(0.0, (abs(x) - (self.W - self.Lc)) / self.Lc))
        ly = min(1.0, max(0.0, (abs(y) - (self.D - self.Lc)) / self.Lc))
        return self.lift * (lx * ly) ** 1.7

    def d_at(self, x, y):
        dy = self.D - abs(y)
        if abs(x) <= self.xg + 1e-9:
            return dy
        return min(self.W - abs(x), dy)

    def z(self, x, y):
        d = self.d_at(x, y)
        return self.base(d) + self.stepped(d) + self.lift_at(x, y)

    def zr(self):
        return self.base(self.D) + self.stepped(self.D)

    # ---- geometry
    def _ring(self, d, extra, zoff=0.0):
        hx = max(self.W - d, self.xg)
        hy = max(self.D - d, 0.0)
        cs = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        pts, sides = [], []
        for k in range(4):
            a, b = cs[k], cs[(k + 1) % 4]
            for f in (self.frL if k % 2 == 0 else self.frS):
                x = a[0] + (b[0] - a[0]) * f
                y = a[1] + (b[1] - a[1]) * f
                pts.append((x, y))
                sides.append(k)
        zb = self.base(d) + extra + zoff
        out = []
        for (x, y) in pts:
            lz = self.lift_at(x, y)
            fx = fy = 0.0
            if self.flare and d < 1e-6:
                fx = math.copysign(self.flare * lz / max(self.lift, 1e-6), x)
                fy = math.copysign(self.flare * lz / max(self.lift, 1e-6), y)
            out.append((self.cx + x + fx, self.cy + y + fy, zb + lz))
        return out, sides

    def levels(self, d_top=None):
        dt = self.D if d_top is None else d_top
        ds = {0.0, dt}
        for i in range(1, self.nlev):
            ds.add(dt * i / self.nlev)
        if 0 < self.dg < dt - 1e-6:
            ds.add(self.dg)
        for sd, _ in self.steps:
            if 0 < sd < dt:
                ds.add(sd)
        # drop levels too close to each other (keep special ones)
        special = {0.0, dt, self.dg} | {sd for sd, _ in self.steps}
        lst = sorted(ds)
        clean = []
        for d in lst:
            if clean and d - clean[-1] < 0.25 and not any(abs(d - s) < 1e-9 for s in special):
                continue
            if clean and d - clean[-1] < 0.25 and not any(abs(clean[-1] - s) < 1e-9 for s in special):
                clean.pop()
            clean.append(d)
        lev = []
        for d in clean:
            if any(abs(d - sd) < 1e-9 for sd, _ in self.steps):
                lev.append((d, self.stepped(d, inclusive=False), True))
            lev.append((d, self.stepped(d), False))
        return lev

    def build(self, mb, top, edge, under, gable=None, thick=0.4, bevel=0.0, d_top=None, cap_col=None,
              nose=None, step_nose=0.0, top2=None):
        """Closed roof slab.  nose = [(inset, dz), ...] extra fascia rings from the bottom
        edge up to the eave line (inset < 0 bulges outward) -> rounded thick eaves.
        top2 = colour of the slope above the first step (two-tone thatch)."""
        specs = []  # (kind, d, extra, zoff)
        specs.append(("fascia", max(bevel, 0.0), 0.0, -thick - (self.base(max(bevel, 0.0)) - self.ze)))
        for (ins, dz) in (nose or []):
            specs.append(("fascia", ins, 0.0, dz - (self.base(max(ins, 0.0)) - self.ze)))
        for (d, ex, is_low) in self.levels(d_top):
            if is_low:
                specs.append(("steplow", d, ex, 0.0))
                if step_nose:
                    h = self.stepped(d) - ex
                    specs.append(("stepmid", d - step_nose, ex + h * 0.55, self.base(d) - self.base(d - step_nose)))
            else:
                specs.append(("lev", d, ex, 0.0))
        rings, sides = [], None
        for (kind, d, ex, zoff) in specs:
            r, sides = self._ring(d, ex, zoff)
            rings.append(r)
        part, bands, caps = loft_dd(mb, rings, top, cap_start=True, cap_end=(d_top is not None))
        mb._tag(caps[:1], under)
        if d_top is not None and len(caps) > 1:
            mb._tag(caps[1:], cap_col or top)
        first_step = self.steps[0][0] if self.steps else 1e9
        for bi, band in enumerate(bands):
            kind_a, da = specs[bi][0], specs[bi][1]
            for (f, seg) in band:
                side = sides[seg]
                if kind_a in ("fascia", "steplow", "stepmid"):
                    mb._tag([f], edge)
                elif gable and side in (1, 3) and da >= self.dg - 1e-6:
                    mb._tag([f], gable)
                elif top2 and da >= first_step - 1e-6:
                    mb._tag([f], top2)
        return part

    def ribs(self, mb, color, spacing=0.5, w=0.17, h=0.075, segs=3, sink=0.05, margin=0.15,
             sides=(0, 1, 2, 3), eave_ext=0.06, end_color=None):
        """Raised tile ribs running down every slope, clipped at the hips."""
        sec = [(-w / 2, -sink), (w / 2, -sink), (0.0, h)]
        for k in sides:
            if k in (0, 2):
                span, sgn = 2 * self.W, (-1 if k == 0 else 1)
            else:
                span, sgn = 2 * self.D, (1 if k == 1 else -1)
            n = int(span / spacing)
            off = (span - (n - 1) * spacing) / 2
            for i in range(n):
                c = -span / 2 + off + i * spacing
                if k in (0, 2):
                    dend = (self.D - margin) if abs(c) <= self.xg else (self.W - abs(c) - margin * 0.6)
                else:
                    dend = min(self.D - abs(c) - margin * 0.6, self.dg - margin * 0.3)
                if dend < 0.3:
                    continue
                pts = []
                for j in range(segs + 1):
                    t = j / segs
                    d = dend * (t ** 1.25) - (eave_ext if j == 0 else 0.0)
                    dd = max(d, 0.0)
                    if k in (0, 2):
                        x, y = c, sgn * (self.D - d)
                        z = self.z(c, sgn * (self.D - dd))
                    else:
                        x, y = sgn * (self.W - d), c
                        z = self.z(sgn * (self.W - dd), c)
                    pts.append((self.cx + x, self.cy + y, z))
                tube(mb, pts, sec, color, skip_seg=0)

    def hip_lines(self):
        """Polylines (local) for the 4 corner ridges: ridge end -> verge -> hip -> eave."""
        out = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts = []
                yg = self.D - self.dg if self.dg < self.D else 0.0
                if yg > 0.05:
                    for t in (0.0, 0.5, 1.0):
                        y = sy * yg * t
                        pts.append((sx * self.xg, y, self.z(sx * (self.xg - 0.001), y)))
                n = 4
                dstart = min(self.dg, self.D)
                for i in range(n + 1):
                    d = dstart * (1 - i / n)
                    if pts and i == 0:
                        continue
                    x, y = sx * (self.W - d), sy * (self.D - d)
                    pts.append((x, y, self.base(d) + self.stepped(d) + self.lift_at(x, y)))
                out.append(pts)
        return out

    def ridges(self, mb, color, w=0.32, h=0.32, hip_w=0.24, hip_h=0.22, main=True, hips=True,
               end_up=0.18, end_ext=0.25, oni=None, main_ext=0.15):
        zr = self.zr()
        parts = []
        if main and self.xg > 0.05:
            parts.append(bx(mb, self.cx - self.xg - main_ext, self.cx + self.xg + main_ext,
                            self.cy - w / 2, self.cy + w / 2, zr - h * 0.45, zr + h * 0.55, color))
        if hips:
            for pl in self.hip_lines():
                pts = [Vector((self.cx + x, self.cy + y, z)) for (x, y, z) in pl]
                # extend + kick up at the eave end
                dvec = (pts[-1] - pts[-2])
                dvec.z = 0
                dvec.normalize()
                pts.append(pts[-1] + dvec * end_ext + Vector((0, 0, end_up)))
                tube(mb, pts, rect_section(hip_w, hip_h, -hip_h * 0.35), color)
        if oni and self.xg > 0.05:
            for sx in (-1, 1):
                x = self.cx + sx * (self.xg + main_ext)
                bx(mb, x - 0.12, x + 0.12, self.cy - w * 0.75, self.cy + w * 0.75, zr - h * 0.3, zr + h * 0.95, oni)
        return parts


class ProfileRoof:
    """Roof slab extruded along X (axis='x': profile across Y) or along Y (axis='y':
    profile across X) from a top profile [(s, z), ...] with s increasing.  Covers
    gable (kirizuma) roofs, shed / pent (hisashi) roofs and board roofs."""

    def __init__(self, a0, a1, prof, thick, axis='x', c=0.0):
        self.a0, self.a1, self.prof, self.thick, self.axis, self.c = a0, a1, list(prof), thick, axis, c

    @staticmethod
    def gable(a0, a1, D, ze, H, thick, curve=0.0, n=3, axis='x', c=0.0, D2=None):
        D2 = D if D2 is None else D2
        prof = []
        for i in range(n + 1):
            t = i / n
            prof.append((-D * (1 - t), ze + H * ((1 - curve) * t + curve * t * t)))
        for i in range(n - 1, -1, -1):
            t = i / n
            prof.append((D2 * (1 - t), ze + H * ((1 - curve) * t + curve * t * t)))
        return ProfileRoof(a0, a1, prof, thick, axis, c)

    @staticmethod
    def shed(a0, a1, s_eave, s_wall, z_eave, z_wall, thick, curve=0.0, n=2, axis='x', c=0.0):
        prof = []
        for i in range(n + 1):
            t = i / n
            prof.append((s_eave + (s_wall - s_eave) * t, z_eave + (z_wall - z_eave) * ((1 - curve) * t + curve * t * t)))
        if prof[0][0] > prof[-1][0]:
            prof.reverse()
        return ProfileRoof(a0, a1, prof, thick, axis, c)

    def P(self, a, s, z):
        return (a, self.c + s, z) if self.axis == 'x' else (self.c + s, a, z)

    def zs(self, s):
        pr = self.prof
        if s <= pr[0][0]:
            return pr[0][1]
        for (s0, z0), (s1, z1) in zip(pr[:-1], pr[1:]):
            if s0 <= s <= s1:
                return z0 + (z1 - z0) * (s - s0) / max(s1 - s0, 1e-9)
        return pr[-1][1]

    def build(self, mb, top, edge, under, end=None):
        n = len(self.prof)

        def ring(a):
            return ([self.P(a, s, z) for s, z in self.prof] +
                    [self.P(a, s, z - self.thick) for s, z in reversed(self.prof)])
        part, bands, caps = loft_dd(mb, [ring(self.a0), ring(self.a1)], top, cap_start=True, cap_end=True)
        for f, seg in bands[0]:
            if seg == n - 1 or seg == 2 * n - 1:
                mb._tag([f], edge)
            elif seg >= n:
                mb._tag([f], under)
        mb._tag(caps, end or edge)
        return part

    def ribs(self, mb, color, spacing=0.5, i0=0, i1=None, w=0.17, h=0.075, eave_ext=0.07, margin=0.12,
             sink=0.05, inset=0.15):
        """Tile ribs on the slope from profile index i0 (eave) to i1 (top)."""
        i1 = (len(self.prof) - 1) if i1 is None else i1
        step = 1 if i1 > i0 else -1
        seg = [self.prof[i] for i in range(i0, i1 + step, step)]
        sec = [(-w / 2, -sink), (w / 2, -sink), (0.0, h)]
        (s0, z0), (s1, z1) = seg[0], seg[1]
        L0 = math.hypot(s1 - s0, z1 - z0)
        ext = (s0 - (s1 - s0) / L0 * eave_ext, z0 - (z1 - z0) / L0 * eave_ext)
        (sa, za), (sb, zb) = seg[-2], seg[-1]
        L1 = math.hypot(sb - sa, zb - za)
        endp = (sb - (sb - sa) / L1 * margin, zb - (zb - za) / L1 * margin)
        path = [ext] + seg[1:-1] + [endp]
        span = self.a1 - self.a0 - 2 * inset
        cnt = max(1, int(span / spacing) + 1)
        for k in range(cnt):
            a = self.a0 + inset + (span * k / (cnt - 1) if cnt > 1 else span / 2)
            tube(mb, [self.P(a, s, z) for (s, z) in path], sec, color, skip_seg=0)

    def ridge(self, mb, color, w=0.3, h=0.3, ext=0.05, band=None):
        """Main ridge box over the highest profile point (+ optional white mortar band)."""
        s, z = max(self.prof, key=lambda p: p[1])
        a0, a1 = self.a0 - ext, self.a1 + ext
        p0 = self.P(a0, s - w / 2, z - h * 0.4)
        p1 = self.P(a1, s + w / 2, z + h * 0.6)
        bx(mb, p0[0], p1[0], p0[1], p1[1], p0[2], p1[2], color)
        if band:
            q0 = self.P(a0 + 0.02, s - w / 2 - 0.03, z + h * 0.05)
            q1 = self.P(a1 - 0.02, s + w / 2 + 0.03, z + h * 0.2)
            bx(mb, q0[0], q1[0], q0[1], q1[1], q0[2], q1[2], band)
        return z + h * 0.6

    def verges(self, mb, color, w=0.2, h=0.18, inset=0.08):
        """Raised tile/board rolls along both gable verges."""
        for a in (self.a0 + inset, self.a1 - inset):
            tube(mb, [self.P(a, s, z) for (s, z) in self.prof], rect_section(w, h, -h * 0.3), color)


# ============================================================== small props
def hanging_lantern(mb, x, y, z_top, h=0.5, r=0.19, glow="glow_warm", cap="wood_black", cord=0.25):
    bx(mb, x - 0.025, x + 0.025, y - 0.025, y + 0.025, z_top - cord, z_top + 0.05, cap)
    zt = z_top - cord
    mb.prism((x, y, zt - 0.06), r * 0.75, 0.06, 6, cap)
    mb.prism((x, y, zt - 0.06 - h * 0.15), r * 0.82, h * 0.15, 8, glow, radius_top=r * 0.75)
    mb.prism((x, y, zt - 0.06 - h * 0.85), r, h * 0.7, 8, glow)
    mb.prism((x, y, zt - 0.06 - h), r * 0.82, h * 0.15, 8, glow, radius_top=r)
    mb.prism((x, y, zt - 0.12 - h), r * 0.75, 0.06, 6, cap)


def barrel(mb, x, y, r=0.34, h=0.75, top="water_deep"):
    mb.prism((x, y, 0), r, h, 8, "wood", base=False)
    mb.prism((x, y, h * 0.18), r * 1.04, 0.07, 8, "iron", cap=False)
    mb.prism((x, y, h * 0.72), r * 1.04, 0.07, 8, "iron", cap=False)
    mb.prism((x, y, h - 0.06), r * 0.9, 0.04, 8, top)


def log_pile(mb, x0, x1, y, rows=3, r=0.1, color="wood_light", end_color="wood_pale", axis='x', depth=0.6):
    """Stack of firewood logs (hexagonal), lying across `axis`."""
    rng = random.Random(7)
    n = int((x1 - x0) / (2 * r))
    for row in range(rows):
        cnt = n - row
        for i in range(cnt):
            c = x0 + r + row * r + i * 2 * r
            z = r + row * r * 1.72
            L_ = depth * rng.uniform(0.85, 1.0)
            if axis == 'x':
                p = mb.prism((c, y - L_ / 2, z), r, L_, 6, color, rot=(-90, 0, 0))
            else:
                p = mb.prism((y - L_ / 2, c, z), r, L_, 6, color, rot=(0, 90, 0))
            p.color_faces(lambda f: end_color if abs(f.normal.y if axis == 'x' else f.normal.x) > 0.9 else None)


# ============================================================== shared house parts
def raised_floor(mb, X0, X1, Y0, Y1, zf, spacing=2.4, slab="wood_dark"):
    """Raised wooden floor on stone footings with a dark crawlspace core."""
    bx(mb, X0 + 0.35, X1 - 0.35, Y0 + 0.35, Y1 - 0.35, 0.0, zf - 0.1, "wood_black")
    pts = set()
    for x in _spaced(X0 + 0.12, X1 - 0.12, spacing):
        pts.add((round(x, 3), Y0 + 0.12)); pts.add((round(x, 3), Y1 - 0.12))
    for y in _spaced(Y0 + 0.12, Y1 - 0.12, spacing):
        pts.add((X0 + 0.12, round(y, 3))); pts.add((X1 - 0.12, round(y, 3)))
    for (x, y) in sorted(pts):
        mb.prism((x, y, -0.02), 0.2, zf - 0.12, 6, "stone", radius_top=0.15, base=False)
    bx(mb, X0 - 0.06, X1 + 0.06, Y0 - 0.06, Y1 + 0.06, zf - 0.15, zf, slab)


def thatch_ridge(mb, roof, color="thatch_dark", strap="wood_dark", straps=5, w=0.5, h=0.36, ext=0.12):
    zr = roof.zr()
    x0, x1 = -roof.xg - ext, roof.xg + ext
    sec = [(-w, -0.4), (w, -0.4), (w * 0.85, h * 0.45), (w * 0.4, h), (-w * 0.4, h), (-w * 0.85, h * 0.45)]
    tube(mb, [(roof.cx + x0, roof.cy, zr), (roof.cx + x1, roof.cy, zr)], sec, color)
    for x in frange(x0 + 0.35, x1 - 0.35, max(1, straps - 1)):
        secs = [(-0.08, -0.3), (0.08, -0.3), (0.08, h + 0.05), (-0.08, h + 0.05)]
        bx(mb, roof.cx + x - 0.08, roof.cx + x + 0.08, roof.cy - w * 0.9, roof.cy + w * 0.9,
           zr + h * 0.3, zr + h + 0.06, strap)
        for s in (-1, 1):
            bx(mb, roof.cx + x - 0.08, roof.cx + x + 0.08, roof.cy + s * w * 0.9 - 0.08, roof.cy + s * w * 0.9 + 0.08,
               zr - 0.3, zr + h * 0.5, strap)
    for s in (-1, 1):
        bx(mb, roof.cx + s * (roof.xg + ext) - 0.1, roof.cx + s * (roof.xg + ext) + 0.1,
           roof.cy - w * 0.8, roof.cy + w * 0.8, zr - 0.25, zr + h + 0.04, strap)


def gable_boards(mb, roof, color="wood_black", lattice="wood_light", bars=5, out=0.05):
    """Verge boards (hafu) on the irimoya gable triangles + a smoke-vent lattice."""
    zr = roof.zr()
    zg = roof.base(roof.dg) + roof.stepped(roof.dg)
    yg = roof.D - roof.dg
    for sx in (-1, 1):
        xg = roof.cx + sx * (roof.xg + out)
        for sy in (-1, 1):
            mb.plank_line((xg, roof.cy + sy * yg, zg - 0.02), (xg, roof.cy, zr + 0.1), 0.1, 0.16, color)
        if lattice:
            for k in range(bars):
                y = (k - (bars - 1) / 2) * (yg * 1.1 / bars)
                ztop = zr - abs(y) * (zr - zg) / yg - 0.12
                if ztop - zg < 0.2:
                    continue
                bx(mb, xg - 0.02 * sx - 0.03, xg - 0.02 * sx + 0.03, roof.cy + y - 0.035, roof.cy + y + 0.035,
                   zg + 0.05, ztop, lattice)
            bx(mb, xg - 0.04, xg + 0.04, roof.cy - yg, roof.cy + yg, zg - 0.02, zg + 0.1, color)


# ============================================================== 1. house_kaito
def build_house_kaito(seed):
    mb = L.MeshBuilder("house_kaito", seed)
    zf = 0.5
    X0, X1, Y0, Y1 = -3.6, 3.6, -2.0, 2.6
    ZT = 2.65
    raised_floor(mb, X0, X1, Y0, Y1, zf, spacing=2.4)
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, zf, ZT, spacing=1.8, koshi=0.6,
                                          skip_posts=[(-0.0, Y0 + 0.1)])
    # front: 4 glowing shoji in the middle bay, a half-open plank door on the right
    front.shoji(-1.72, 1.72, zf + 0.12, 2.25, panels=4, cols=1, rows=3, koshi=0.2)
    front.box(-1.8, 1.8, 2.25, 2.36, -0.03, 0.07, "wood_dark")          # kamoi (lintel)
    front.box(2.0, 3.35, zf + 0.12, 2.25, -0.03, 0.075, "wood_black")
    front.box(2.05, 2.62, zf + 0.14, 2.2, -0.03, 0.08, "glow_window")   # doorway light
    for u in (2.74, 3.0, 3.25):
        front.box(u - 0.12, u + 0.12, zf + 0.14, 2.2, 0.075, 0.12, "wood")
    front.box(2.64, 3.37, zf + 0.12, zf + 0.2, 0.075, 0.14, "wood_dark")
    front.box(2.64, 3.37, 2.14, 2.22, 0.075, 0.14, "wood_dark")
    front.window(-2.68, 1.4, 1.95, 0.8, bars=4)
    right.window(0.3, 1.4, 1.95, 1.0, bars=5)
    left.window(-0.6, 1.4, 1.95, 0.7, bars=3)
    back.window(-1.8, 1.35, 1.95, 1.3, bars=6)
    back.window(1.9, 1.45, 1.95, 0.6, bars=3)
    # --- engawa veranda along the front
    ey0, ey1 = -3.0, Y0 - 0.02
    bx(mb, X0, X1, ey0 + 0.02, ey0 + 0.14, zf - 0.22, zf - 0.08, "wood_dark")    # edge beam
    for x in (-3.45, 0.0, 3.45):
        mb.prism((x, ey0 + 0.09, -0.02), 0.16, 0.32, 6, "stone", radius_top=0.12, base=False)
    nb = 4
    bw = (ey1 - ey0) / nb
    for i in range(nb):
        yb0 = ey0 + i * bw + 0.012
        bx(mb, X0 - 0.02, X1 + 0.02, yb0, yb0 + bw - 0.024, zf - 0.08, zf,
           "wood_light" if i % 2 == 0 else "wood_pale")
    bx(mb, X0 + 0.1, X1 - 0.1, ey0 + 0.2, ey1 - 0.05, zf - 0.2, zf - 0.07, "wood_black")
    for x in (X0 + 0.08, X1 - 0.08):
        bx(mb, x - 0.08, x + 0.08, ey0 + 0.02, ey0 + 0.18, zf - 0.01, 2.52, "wood_dark")
    bx(mb, X0, X1, ey0 + 0.03, ey0 + 0.17, 2.36, 2.52, "wood_dark")      # eave beam
    # stepping stones
    stone_slab(mb, 0.0, -3.28, 0.34, 0.62, 0.26, 0.36, "stone_light", sides=7, rz=8)
    stone_slab(mb, 0.15, -3.78, 0.17, 0.75, 0.32, 0.2, "stone", sides=7, rz=-6)
    # --- big thatched irimoya roof
    roof = Roof(W=4.5, D=3.5, ze=3.05, H=2.1, xg=2.55, curve=-0.05, lift=0.12, steps=[(1.15, 0.24)],
                nlev=3, frL=[0.0, 0.07, 0.2, 0.35, 0.5, 0.65, 0.8, 0.93], frS=[0.0, 0.12, 0.3, 0.5, 0.7, 0.88])
    rp = roof.build(mb, "thatch", "thatch_dark", "thatch_dark", gable="wood_dark", thick=0.55, bevel=0.1,
                    nose=[(-0.07, -0.28)], step_nose=0.07, top2="thatch_light")
    rp.jitter(0.06, axes=(1, 1, 0.6))
    thatch_ridge(mb, roof)
    gable_boards(mb, roof)
    # --- details: drying persimmons, entrance lantern, rain barrel, firewood
    pole_y0, pole_y1 = -1.4, 0.9
    mb.prism((-4.05, pole_y0 - 0.1, 2.33), 0.04, pole_y1 - pole_y0 + 0.2, 6, "bamboo_dry", rot=(-90, 0, 0))
    for y in (pole_y0 - 0.05, pole_y1 + 0.05):
        bx(mb, -4.07, -4.03, y - 0.02, y + 0.02, 2.3, 2.56, "rope")
    for y in frange(pole_y0, pole_y1, 4):
        bx(mb, -4.07, -4.03, y - 0.015, y + 0.015, 1.55, 2.33, "rope")
        for k in range(4):
            z = 2.18 - k * 0.19
            mb.prism((-4.05, y, z - 0.07), 0.065, 0.14, 5, "maple_orange", radius_top=0.04)
    hanging_lantern(mb, -1.95, -3.25, 2.5, h=0.46, r=0.18)
    barrel(mb, 4.0, 1.7)
    log_pile(mb, -1.0, 0.4, 3.0, rows=2, r=0.12, axis='x', depth=0.55)
    mb.collider_box((7.5, 5.85, 5.4), (0.0, -0.18, 2.7))
    mb.tag("occluder", "light_warm")
    mb.set("light_offset", [0.0, -4.0, 1.8])
    return mb.finish()


# ============================================================== 2. house_farmer_a
def build_house_farmer_a(seed):
    """Small thatched hip-roof farmhouse with an earthen-floor entrance."""
    mb = L.MeshBuilder("house_farmer_a", seed)
    X0, X1, Y0, Y1 = -2.7, 2.7, -1.7, 1.7
    zf, ZT = 0.28, 2.35
    stone_base(mb, X0 - 0.08, X1 + 0.08, Y0 - 0.08, Y1 + 0.08, zf)
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, zf, ZT, spacing=1.35, koshi=0.85,
                                          wall_col="plaster_dirty", koshi_col="wood", post_col="wood_dark")
    # entrance: plank door slid open, warm light inside
    front.box(0.2, 1.45, zf + 0.12, 2.05, -0.03, 0.075, "wood_black")
    front.box(0.25, 0.85, zf + 0.13, 2.0, -0.03, 0.08, "glow_window")
    for u in (0.97, 1.2, 1.43):
        front.box(u - 0.11, u + 0.11, zf + 0.14, 2.0, 0.075, 0.12, "wood_light")
    front.box(0.86, 1.55, zf + 0.13, zf + 0.2, 0.075, 0.14, "wood_dark")
    front.box(0.86, 1.55, 1.93, 2.0, 0.075, 0.14, "wood_dark")
    front.window(-1.35, 1.25, 1.8, 0.9, bars=5)
    back.window(0.6, 1.25, 1.8, 1.0, bars=5)
    left.window(0.0, 1.3, 1.75, 0.6, bars=3)
    # thatched hip roof
    roof = Roof(W=3.5, D=2.5, ze=2.8, H=1.5, xg=1.15, curve=-0.05, lift=0.1, steps=[(0.85, 0.18)], nlev=3,
                frL=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9], frS=[0.0, 0.15, 0.5, 0.85])
    rp = roof.build(mb, "thatch", "thatch_dark", "thatch_dark", gable="wood_dark", thick=0.5, bevel=0.08,
                    nose=[(-0.06, -0.25)], step_nose=0.06, top2="thatch_light")
    rp.jitter(0.045, axes=(1, 1, 0.6))
    thatch_ridge(mb, roof, straps=2, w=0.34, h=0.24, ext=0.05)
    gable_boards(mb, roof, bars=3)
    # props: firewood against the right wall, barrel, straw bundles
    log_pile(mb, -1.0, 0.6, 3.0, rows=2, r=0.11, axis='y', depth=0.5)
    barrel(mb, -3.05, -1.2, r=0.3, h=0.65)
    for i, (x, y) in enumerate(((-3.05, 0.6), (-3.1, 1.05))):
        mb.prism((x, y, 0), 0.22, 0.85, 6, "straw", radius_top=0.14, base=False).jitter(0.02)
        mb.prism((x, y, 0.45), 0.235, 0.08, 6, "rope", cap=False)
    mb.collider_box((5.7, 3.7, 4.3), (0, 0, 2.15))
    mb.tag("occluder")
    return mb.finish()


def stone_base(mb, x0, x1, y0, y1, h, color="stone", cap="stone_dark"):
    """Low stone plinth with a darker top course."""
    bx(mb, x0, x1, y0, y1, -0.02, h - 0.06, color).jitter(0.015)
    bx(mb, x0 - 0.03, x1 + 0.03, y0 - 0.03, y1 + 0.03, h - 0.07, h, cap)


# ============================================================== 3. house_farmer_b
def build_house_farmer_b(seed):
    """Board-roofed farmhouse (ishiokiyane: stones hold the boards) with a lean-to shed."""
    mb = L.MeshBuilder("house_farmer_b", seed)
    rng = random.Random(seed * 31 + 3)
    X0, X1, Y0, Y1 = -2.6, 1.4, -1.7, 1.7
    zf, ZT = 0.32, 2.88
    raised_floor(mb, X0, X1, Y0, Y1, zf, spacing=2.0)
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, zf, ZT, spacing=1.3, koshi=0.0,
                                          wall_col="wood_grey", post_col="wood_dark", beam_col="wood_dark")
    # vertical board battens on the walls
    for fac, (u0, u1) in ((front, (X0, X1)), (back, (X0, X1)), (left, (Y0, Y1))):
        for u in frange(u0 + 0.45, u1 - 0.45, int((u1 - u0 - 0.9) / 0.65)):
            fac.box(u - 0.03, u + 0.03, zf + 0.15, ZT - 0.3, -0.02, 0.03, "wood")
    front.box(-1.25, -0.35, zf + 0.12, 2.15, -0.03, 0.07, "wood_black")        # door frame
    front.box(-1.2, -0.75, zf + 0.13, 2.1, -0.03, 0.075, "glow_window")         # door gap
    front.box(-0.78, -0.38, zf + 0.13, 2.1, 0.06, 0.11, "wood")                  # door leaf
    front.window(0.55, 1.3, 1.85, 0.8, bars=4)
    back.window(-1.0, 1.3, 1.85, 1.0, bars=5)
    left.window(0.0, 1.35, 1.8, 0.6, bars=3)
    # --- main board roof: gentle gable, ridge along X
    roof = ProfileRoof.gable(X0 - 0.45, X1 + 0.3, 2.5, 2.62, 1.15, 0.16, curve=0.0, n=2)
    roof.build(mb, "wood_dark", "wood_dark", "wood_dark")
    # boards running down each slope
    xs = frange(X0 - 0.45 + 0.21, X1 + 0.3 - 0.21, 11)
    for sgn in (-1, 1):
        for i, x in enumerate(xs):
            col = rng.choice(("wood_grey", "wood_grey", "stone_warm", "wood_grey", "wood_light"))
            e = rng.uniform(-0.08, 0.06)
            a = (x, sgn * (2.5 + e), 2.62 + 0.035 - e * 0.46)
            b = (x, sgn * 0.02, 2.62 + 1.15 + 0.035)
            mb.plank_line(a, b, 0.4, 0.05, col)
    # battens + stones
    for sgn in (-1, 1):
        for t in (0.3, 0.72):
            y = sgn * 2.5 * (1 - t)
            z = 2.62 + 1.15 * t + 0.07
            bx(mb, X0 - 0.5, X1 + 0.35, y - 0.06, y + 0.06, z - 0.03, z + 0.07, "wood_dark")
            for x in frange(X0 - 0.15, X1 + 0.05, 4):
                r = rng.uniform(0.15, 0.21)
                mb.ico((x + rng.uniform(-0.15, 0.15), y + sgn * 0.12, z + r * 0.75), r,
                       rng.choice(("stone", "stone_light", "stone_moss")), subdiv=1, scale=(1.15, 1.0, 0.75), jitter=0.12)
    # gable infill (boards) under the verges
    for x in (X0 + 0.08, X1 - 0.08):
        gable_wall(mb, x, Y0 + 0.05, Y1 - 0.05, ZT - 0.1, 3.62, 0.14, "wood_grey")
        sx = -1 if x < 0 else 1
        bx(mb, x + sx * 0.05, x + sx * 0.11, -0.07, 0.07, ZT - 0.1, 3.55, "wood_dark")
    # ridge board
    zr = 2.62 + 1.15
    bx(mb, X0 - 0.5, X1 + 0.35, -0.2, 0.2, zr - 0.02, zr + 0.12, "wood_dark")
    # gable (verge) boards
    for x in (X0 - 0.45, X1 + 0.3):
        for sgn in (-1, 1):
            mb.plank_line((x, sgn * 2.55, 2.55), (x, 0.0, zr + 0.06), 0.07, 0.24, "wood_black")
    # --- lean-to shed on the +X side
    sx0, sx1 = X1, 2.95
    shed = ProfileRoof.shed(-1.95, 1.95, sx1 + 0.15, sx0 + 0.2, 1.95, 2.42, 0.12, axis='y', n=1)
    shed.build(mb, "wood_grey", "wood_dark", "wood_dark")
    for y in frange(-1.85, 1.85, 8):
        a = (sx1 + 0.15, y, 1.95 + 0.04)
        b = (sx0 + 0.2, y, 2.42 + 0.04)
        mb.plank_line(a, b, 0.36, 0.04, "wood_light" if int(round((y + 2) / 0.46)) % 2 else "wood_grey")
    for y in (-1.6, 1.6):
        bx(mb, sx1 - 0.18, sx1 - 0.04, y - 0.07, y + 0.07, 0.0, 2.02, "wood_dark")
        mb.prism((sx1 - 0.11, y, -0.02), 0.13, 0.16, 6, "stone", base=False)
    bx(mb, sx1 - 0.2, sx1 - 0.02, -1.75, 1.75, 1.82, 1.98, "wood_dark")
    bx(mb, sx0, sx1 - 0.1, 1.55, 1.68, 0.0, 2.1, "wood_grey")          # back board wall
    log_pile(mb, -1.3, 1.2, (sx0 + sx1) / 2 + 0.1, rows=3, r=0.11, axis='y', depth=1.1)
    barrel(mb, sx0 + 0.75, -1.25, r=0.28, h=0.6, top="wood_dark")
    mb.collider_box((5.6, 3.5, 4.0), (0.2, 0, 2.0))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== tile roof helpers
def tile_irimoya(mb, roof, rib_spacing=0.5, segs=2, slab="tile_dark", rib="tile_blue", ridge="tile_dark",
                 under="wood_dark", gable="plaster", thick=0.28, band="plaster", oni="tile_dark",
                 hip_w=0.24, d_top=None, ridge_h=0.34, rafters=None):
    roof.build(mb, slab, "wood_dark", under, gable=gable, thick=thick, d_top=d_top,
               cap_col=slab, nose=[(-0.05, -thick * 0.45)])
    roof.ribs(mb, rib, spacing=rib_spacing, segs=segs)
    if d_top is None:
        roof.ridges(mb, ridge, w=0.34, h=ridge_h, hip_w=hip_w, hip_h=0.2, oni=oni)
        if band:
            zr = roof.zr()
            bx(mb, roof.cx - roof.xg - 0.13, roof.cx + roof.xg + 0.13, roof.cy - 0.2, roof.cy + 0.2,
               zr + ridge_h * 0.05, zr + ridge_h * 0.2, band)
    else:
        roof.ridges(mb, ridge, main=False, hip_w=hip_w, hip_h=0.2)


# ============================================================== 4. house_village_a
def build_house_village_a(seed):
    """Clan-village townhouse: tiled irimoya roof, white plaster, dark lattice, noren."""
    mb = L.MeshBuilder("house_village_a", seed)
    X0, X1, Y0, Y1 = -3.35, 3.35, -2.35, 2.35
    zf, ZT = 0.36, 3.1
    stone_base(mb, X0 - 0.1, X1 + 0.1, Y0 - 0.1, Y1 + 0.1, zf, color="stone_dark", cap="stone")
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, zf, ZT, spacing=1.65, koshi=0.55,
                                          wall_col="plaster", koshi_col="wood_black", post_col="wood_dark",
                                          skip_posts=[(0.0, Y0 + 0.1)])
    # entrance with noren
    front.box(-0.85, 0.85, zf + 0.12, 2.35, -0.03, 0.03, "glow_window")
    front.box(-0.95, 0.95, 2.35, 2.5, -0.03, 0.09, "wood_dark")
    for i, u in enumerate((-0.56, 0.0, 0.56)):
        front.box(u - 0.26, u + 0.26, 1.55, 2.36, 0.09, 0.13, "cloth_indigo")
    front.box(-0.12, 0.12, 1.92, 2.16, 0.13, 0.15, "cloth_white")
    front.box(-0.9, 0.9, 2.36, 2.42, 0.08, 0.17, "wood")                      # noren pole
    # lattice windows (dense koshi)
    for u in (-2.15, 2.15):
        front.window(u, 0.95, 2.25, 1.6, bars=9, frame="wood_dark", bar="wood_dark")
    back.window(-1.6, 1.05, 2.25, 1.8, bars=9)
    back.window(1.7, 1.25, 2.1, 1.0, bars=5)
    right.window(0.0, 1.1, 2.2, 1.4, bars=7)
    left.window(0.4, 1.25, 2.1, 0.9, bars=5)
    # sign board over the door
    front.box(-0.55, 0.55, 2.62, 2.95, 0.08, 0.14, "wood_dark")
    front.box(-0.45, 0.45, 2.68, 2.89, 0.14, 0.16, "wood_pale")
    # roof
    roof = Roof(W=4.0, D=3.0, ze=3.38, H=1.38, xg=2.3, curve=0.35, lift=0.32, nlev=3, flare=0.1,
                frL=[0.0, 0.08, 0.22, 0.5, 0.78, 0.92], frS=[0.0, 0.12, 0.5, 0.88])
    tile_irimoya(mb, roof, rib_spacing=0.48, segs=2, thick=0.3)
    gable_boards(mb, roof, color="wood_dark", lattice="wood_dark", bars=5, out=0.03)
    hanging_lantern(mb, 1.25, -3.0, 3.08, h=0.42, r=0.16, cord=0.35)
    mb.collider_box((6.9, 4.9, 4.9), (0, 0, 2.45))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 5. house_village_b
def gable_wall(mb, x, y0, y1, z0, z1, t, color):
    """Triangular gable infill (closed prism) in the plane x, thickness t."""
    ym = (y0 + y1) / 2
    tri = lambda xx: [(xx, y0, z0), (xx, y1, z0), (xx, ym, z1)]
    p, _, _ = loft_dd(mb, [tri(x - t / 2), tri(x + t / 2)], color, cap_start=True, cap_end=True)
    return p


def build_house_village_b(seed):
    """Two-storey machiya: tiled pent roofs + tiled gable roof, balcony rail, glowing windows."""
    mb = L.MeshBuilder("house_village_b", seed)
    X0, X1, Y0, Y1 = -2.6, 2.6, -2.35, 2.35
    zf, Z1, Z2 = 0.3, 3.15, 5.97
    stone_base(mb, X0 - 0.08, X1 + 0.08, Y0 - 0.08, Y1 + 0.08, zf, color="stone_dark", cap="stone")
    f1, b1, l1, r1 = timber_box(mb, X0, X1, Y0, Y1, zf, Z1, spacing=1.3, koshi=0.5, wall_col="plaster",
                                koshi_col="wood_black", skip_posts=[(-0.65, Y0 + 0.1), (0.65, Y0 + 0.1)])
    f2, b2, l2, r2 = timber_box(mb, X0 + 0.05, X1 - 0.05, Y0 + 0.05, Y1 - 0.05, Z1, Z2, spacing=1.3,
                                koshi=0.0, wall_col="plaster", sill_h=0.16, beam_h=0.2)
    # ground floor: shop-front lattice + doorway with noren
    f1.box(-0.85, 0.85, zf + 0.12, 2.4, -0.03, 0.03, "glow_window")
    f1.box(-0.95, 0.95, 2.4, 2.55, -0.03, 0.09, "wood_dark")
    for u in (-0.53, 0.0, 0.53):
        f1.box(u - 0.24, u + 0.24, 1.7, 2.41, 0.09, 0.13, "cloth_red")
    f1.box(-0.1, 0.1, 2.02, 2.22, 0.13, 0.15, "cloth_white")
    f1.window(-1.75, 0.95, 2.3, 1.2, bars=8)
    f1.window(1.75, 0.95, 2.3, 1.2, bars=8)
    b1.window(0.0, 1.1, 2.2, 1.6, bars=8)
    l1.window(0.5, 1.2, 2.1, 0.9, bars=5)
    # upper floor windows
    f2.window(0.0, 3.75, 4.95, 3.2, bars=12, hbars=1)
    b2.window(-0.9, 3.85, 4.85, 1.4, bars=6)
    b2.window(1.2, 4.0, 4.75, 0.7, bars=3)
    r2.window(0.0, 3.9, 4.8, 1.2, bars=5)
    l2.window(-0.6, 3.9, 4.8, 0.8, bars=4)
    # pent roofs (front + back) between the floors
    for sgn in (-1, 1):
        pent = ProfileRoof.shed(X0 - 0.15, X1 + 0.15, sgn * (Y1 + 0.75), sgn * (Y1 - 0.05), 3.0, 3.5, 0.16,
                                curve=0.0, n=1)
        pent.build(mb, "tile_dark", "wood_dark", "wood_dark")
        i0 = 0 if sgn < 0 else len(pent.prof) - 1
        i1 = len(pent.prof) - 1 if sgn < 0 else 0
        pent.ribs(mb, "tile_blue", spacing=0.55, i0=i0, i1=i1, inset=0.12, margin=0.05)
        bx(mb, X0 - 0.15, X1 + 0.15, sgn * (Y1 - 0.1), sgn * (Y1 + 0.12), 3.42, 3.6, "tile_dark")
    # balcony rail on the upper floor front (sits on the pent roof)
    yr = Y0 - 0.32
    for x in frange(X0 + 0.15, X1 - 0.15, 8):
        bx(mb, x - 0.035, x + 0.035, yr - 0.035, yr + 0.035, 3.3, 4.1, "wood_dark")
    bx(mb, X0 + 0.05, X1 - 0.05, yr - 0.06, yr + 0.06, 4.05, 4.15, "wood_dark")
    bx(mb, X0 + 0.05, X1 - 0.05, yr - 0.05, yr + 0.05, 3.62, 3.7, "wood_dark")
    for x in (X0 + 0.15, X1 - 0.15):
        bx(mb, x - 0.05, x + 0.05, yr, Y0 + 0.06, 4.05, 4.13, "wood_dark")
    # main gable roof
    roof = ProfileRoof.gable(X0 - 0.5, X1 + 0.5, 3.0, 5.92, 1.25, 0.24, curve=0.3, n=3)
    roof.build(mb, "tile_dark", "wood_dark", "wood_dark", end="wood_dark")
    n = len(roof.prof)
    roof.ribs(mb, "tile_blue", spacing=0.55, i0=0, i1=n // 2, inset=0.3)
    roof.ribs(mb, "tile_blue", spacing=0.55, i0=n - 1, i1=n // 2, inset=0.3)
    roof.verges(mb, "tile_dark", w=0.24, h=0.2, inset=0.12)
    top = roof.ridge(mb, "tile_dark", w=0.34, h=0.34, ext=0.05, band="plaster")
    for x in (X0 - 0.55, X1 + 0.55):
        bx(mb, x - 0.12, x + 0.12, -0.27, 0.27, top - 0.4, top + 0.18, "tile_dark")
    # gable infill with exposed beams
    for x in (X0 + 0.12, X1 - 0.12):
        gable_wall(mb, x, Y0 + 0.1, Y1 - 0.1, Z2 - 0.05, 6.95, 0.16, "plaster")
        sx = -1 if x < 0 else 1
        bx(mb, x + sx * 0.06, x + sx * 0.12, -0.08, 0.08, Z2, 6.85, "wood_dark")
        bx(mb, x + sx * 0.06, x + sx * 0.12, Y0 + 0.8, Y1 - 0.8, 6.3, 6.42, "wood_dark")
    # hanging sign + lantern
    hanging_lantern(mb, -1.6, Y0 - 0.55, 2.98, h=0.4, r=0.15, cord=0.3)
    mb.collider_box((5.4, 4.9, 7.2), (0, 0, 3.6))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 6. house_fisher
def pile(mb, x, y, z0, z1, r=0.14, color="wood_dark", sides=6, lean=(0.0, 0.0)):
    """Wooden pile (stilt) from z0 to z1, optionally leaning a little."""
    a = Vector((x - lean[0], y - lean[1], z0))
    b = Vector((x, y, z1))
    d = b - a
    rot = d.to_track_quat('Z', 'Y').to_euler()
    p = mb.prism((0, 0, 0), r, d.length, sides, color)
    p.transform(rot=tuple(math.degrees(v) for v in rot))
    p.transform(loc=tuple(a))
    return p


def deck_boards(mb, x0, x1, y0, y1, z_top, along='x', width=0.36, thick=0.08, cols=("wood_light", "wood"),
                gap=0.025, jit=0.0, rng=None):
    """Plank deck: boards running along X or Y with small gaps."""
    span = (y1 - y0) if along == 'x' else (x1 - x0)
    n = max(1, int(round(span / width)))
    w = span / n
    for i in range(n):
        c = cols[i % len(cols)]
        dz = rng.uniform(-jit, jit) if (rng and jit) else 0.0
        if along == 'x':
            bx(mb, x0, x1, y0 + i * w + gap / 2, y0 + (i + 1) * w - gap / 2, z_top - thick + dz, z_top + dz, c)
        else:
            bx(mb, x0 + i * w + gap / 2, x0 + (i + 1) * w - gap / 2, y0, y1, z_top - thick + dz, z_top + dz, c)


def build_house_fisher(seed):
    """Fisherman's stilt house over the lake (z=0 is the water surface)."""
    mb = L.MeshBuilder("house_fisher", seed)
    rng = random.Random(seed * 7 + 11)
    DZ = 1.2
    DX0, DX1, DY0, DY1 = -4.5, 4.5, -3.5, 3.5
    X0, X1, Y0, Y1 = -3.0, 3.0, -1.5, 3.4
    # piles (10) + braces + stringers
    pxs = (-4.3, -1.45, 1.45, 4.3)
    for x in pxs:
        for y in (DY0 + 0.2, DY1 - 0.2):
            pile(mb, x, y, -2.5, DZ - 0.12, lean=(rng.uniform(-0.12, 0.12), rng.uniform(-0.1, 0.1)))
    for x in (DX0 + 0.2, DX1 - 0.2):
        pile(mb, x, 0.0, -2.5, DZ - 0.12)
    for y in (DY0 + 0.2, 0.0, DY1 - 0.2):
        bx(mb, DX0 + 0.05, DX1 - 0.05, y - 0.1, y + 0.1, DZ - 0.32, DZ - 0.1, "wood_dark")
    for (xa, xb) in ((-4.3, -1.45), (1.45, 4.3)):
        mb.plank_line((xa, DY0 + 0.32, -0.4), (xb, DY0 + 0.32, DZ - 0.3), 0.1, 0.1, "wood")
    mb.plank_line((-4.3, DY1 - 0.32, DZ - 0.3), (-1.45, DY1 - 0.32, -0.4), 0.1, 0.1, "wood")
    # deck: dark slab under the house + boards on the open parts
    bx(mb, DX0 + 0.05, DX1 - 0.05, DY0 + 0.05, DY1 - 0.05, DZ - 0.16, DZ - 0.06, "wood_dark")
    deck_boards(mb, DX0, DX1, DY0, Y0 - 0.02, DZ, along='x', width=0.38, cols=("wood_light", "wood", "wood_light", "wood_pale"),
                jit=0.012, rng=rng)
    deck_boards(mb, DX0, X0 - 0.02, Y0 - 0.02, DY1, DZ, along='y', width=0.38, cols=("wood", "wood_light"), jit=0.012, rng=rng)
    deck_boards(mb, X1 + 0.02, DX1, Y0 - 0.02, DY1, DZ, along='y', width=0.38, cols=("wood_light", "wood"), jit=0.012, rng=rng)
    bx(mb, X0, X1, Y0, Y1, DZ - 0.08, DZ, "wood")
    # low rail along the side decks
    for sx in (-1, 1):
        xr = sx * (DX1 - 0.1)
        for y in (-1.2, 0.9, 3.3):
            bx(mb, xr - 0.06, xr + 0.06, y - 0.06, y + 0.06, DZ - 0.05, DZ + 0.75, "wood_dark")
        bx(mb, xr - 0.05, xr + 0.05, -1.25, 3.35, DZ + 0.66, DZ + 0.76, "wood")
    # ladder down to the water at the front
    lx = 2.6
    for s in (-1, 1):
        bx(mb, lx + s * 0.32 - 0.05, lx + s * 0.32 + 0.05, DY0 - 0.12, DY0 + 0.0, -0.7, DZ + 0.45, "wood_dark")
    for z in frange(-0.4, DZ - 0.15, 4):
        bx(mb, lx - 0.3, lx + 0.3, DY0 - 0.1, DY0 - 0.02, z - 0.04, z + 0.04, "wood")
    # mooring post with rope
    pile(mb, -3.6, DY0 - 0.35, -2.0, DZ + 0.6, r=0.12)
    mb.prism((-3.6, DY0 - 0.35, DZ + 0.25), 0.15, 0.12, 6, "rope")
    # house body
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, DZ, DZ + 2.3, spacing=1.5, koshi=0.0,
                                          wall_col="wood_grey", post_col="wood_dark")
    for fac, (u0, u1) in ((front, (X0, X1)), (back, (X0, X1)), (left, (Y0, Y1)), (right, (Y0, Y1))):
        for u in frange(u0 + 0.4, u1 - 0.4, int((u1 - u0 - 0.8) / 0.7)):
            fac.box(u - 0.03, u + 0.03, DZ + 0.15, DZ + 2.08, -0.02, 0.03, "wood")
    front.box(-0.45, 0.45, DZ + 0.12, DZ + 2.0, -0.03, 0.06, "wood_black")
    front.box(-0.4, 0.1, DZ + 0.13, DZ + 1.95, -0.03, 0.07, "glow_window")
    front.box(0.08, 0.42, DZ + 0.13, DZ + 1.95, 0.05, 0.1, "wood")
    front.window(-1.9, DZ + 0.95, DZ + 1.6, 0.9, bars=4)
    front.window(1.9, DZ + 0.95, DZ + 1.6, 0.7, bars=3)
    back.window(0.5, DZ + 0.95, DZ + 1.6, 1.0, bars=5)
    right.window(1.0, DZ + 1.0, DZ + 1.6, 0.7, bars=3)
    # thatched gable roof, ridge along X
    cy = (Y0 + Y1) / 2
    roof = Roof(W=3.7, D=3.05, ze=DZ + 2.62, H=1.75, xg=2.75, cy=cy, curve=-0.05, steps=[(0.85, 0.15)],
                frL=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9], frS=[0.0, 0.15, 0.5, 0.85])
    rp = roof.build(mb, "thatch", "thatch_dark", "thatch_dark", gable="wood_dark", thick=0.48, bevel=0.08,
                    nose=[(-0.05, -0.22)], step_nose=0.05, top2="thatch_light")
    rp.jitter(0.04, axes=(1, 1, 0.6))
    thatch_ridge(mb, roof, straps=4, w=0.42, h=0.3)
    gable_boards(mb, roof, bars=4)
    # drying-fish rack on the front deck
    for x in (-4.15, -2.35):
        bx(mb, x - 0.06, x + 0.06, -2.85, -2.73, DZ, DZ + 1.75, "wood_dark")
    bx(mb, -4.3, -2.2, -2.86, -2.72, DZ + 1.62, DZ + 1.72, "wood")
    bx(mb, -4.3, -2.2, -2.86, -2.72, DZ + 1.1, DZ + 1.18, "wood")
    for i, x in enumerate(frange(-3.95, -2.55, 5)):
        for zz in (DZ + 1.6, DZ + 1.08):
            p = mb.prism((0, 0, 0), 0.07, 0.36, 5, "iron_light" if (i + int(zz)) % 2 else "stone_light",
                         radius_top=0.03)
            p.transform(scale=(1.0, 0.45, 1.0)).transform(rot=(180, 0, 0)).transform(loc=(x, -2.79, zz - 0.02))
    # net hung over the right rail + baskets + lantern
    bx(mb, DX1 - 0.16, DX1 - 0.04, -1.0, 0.7, DZ + 0.05, DZ + 0.78, "rope").jitter(0.03)
    bx(mb, DX1 - 0.13, DX1 + 0.02, -0.8, 0.5, DZ - 0.25, DZ + 0.1, "rope").jitter(0.03)
    for (x, y, r) in ((1.0, -2.5, 0.28), (1.55, -2.85, 0.22)):
        mb.prism((x, y, DZ), r, 0.32, 7, "bamboo_dry", radius_top=r * 1.15)
        mb.prism((x, y, DZ + 0.2), r * 1.07, 0.06, 7, "wood", cap=False)
    hanging_lantern(mb, 0.85, Y0 - 0.5, DZ + 2.3, h=0.38, r=0.14, cord=0.22)
    mb.collider_mesh()
    mb.tag("occluder", "walkable", "light_warm")
    mb.set("light_offset", [0.85, Y0 - 0.9, DZ + 1.6])
    return mb.finish()


# ============================================================== dojo helpers
def shachihoko(mb, x, y, z, sx, scale=1.0, color="gold"):
    """Stylised golden fish-tail fin on a ridge end (sx = outward direction)."""
    s = scale
    body = [(x, y, z), (x - sx * 0.05 * s, y, z + 0.45 * s), (x + sx * 0.12 * s, y, z + 0.85 * s),
            (x + sx * 0.38 * s, y, z + 1.05 * s)]
    tube(mb, body, [(-0.16 * s, -0.22 * s), (0.16 * s, -0.22 * s), (0.11 * s, 0.2 * s), (-0.11 * s, 0.2 * s)], color)
    # tail fin
    tail = [(x + sx * 0.3 * s, y, z + 1.0 * s), (x + sx * 0.5 * s, y, z + 1.2 * s)]
    tube(mb, tail, [(-0.05 * s, -0.25 * s), (0.05 * s, -0.25 * s), (0.05 * s, 0.25 * s), (-0.05 * s, 0.25 * s)], color)
    # little dorsal fins
    bx(mb, x - 0.05 * s, x + 0.05 * s, y - 0.3 * s, y + 0.3 * s, z + 0.3 * s, z + 0.42 * s, "gold_dark")


def nobori(mb, x, y, z0, height=5.0, cloth="cloth_red", emblem="cloth_white", w=0.85, ch=3.0, sy=-1):
    """Vertical banner on a pole (cloth hangs from a top crossbar)."""
    mb.prism((x, y, z0), 0.06, height, 6, "wood_dark")
    mb.prism((x, y, z0 + height), 0.09, 0.12, 6, "gold")
    cx = x + w / 2 + 0.06
    bx(mb, x, x + w + 0.12, y - 0.04, y + 0.04, z0 + height - 0.25, z0 + height - 0.17, "wood_dark")
    bx(mb, cx - w / 2, cx + w / 2, y - 0.03, y + 0.03, z0 + height - 0.25 - ch, z0 + height - 0.2, cloth)
    e = mb.prism((0, 0, 0), w * 0.28, 0.08, 8, emblem, rot=(90, 0, 0))
    e.transform(loc=(cx, y + sy * 0.0, z0 + height - 0.25 - ch * 0.32))
    bx(mb, cx - w / 2, cx + w / 2, y - 0.045, y + 0.045, z0 + height - 0.25 - ch * 0.08, z0 + height - 0.25 - ch * 0.02, "black")


def stairs_block(mb, x0, x1, y_front, y_back, z_bottom, z_top, n, color="stone", nose=None, alt=None):
    """Solid stone steps (each step a box from z_bottom), rising toward +Y."""
    d = (y_back - y_front) / n
    h = (z_top - z_bottom) / n
    for i in range(n):
        c = alt if (alt and i % 2) else color
        bx(mb, x0, x1, y_front + i * d, y_back + 0.02, z_bottom - 0.02 if i == 0 else z_bottom + i * h - 0.05,
           z_bottom + (i + 1) * h, c)
        if nose:
            bx(mb, x0 + 0.01, x1 - 0.01, y_front + i * d - 0.02, y_front + i * d + 0.06,
               z_bottom + (i + 1) * h - 0.05, z_bottom + (i + 1) * h + 0.005, nose)


# ============================================================== 7. dojo_main
def build_dojo_main(seed):
    """The clan dojo: stone platform, red pillars, two-tier tiled irimoya roof."""
    mb = L.MeshBuilder("dojo_main", seed)
    PZ = 1.2
    PX, PY0, PY1 = 10.3, -5.95, 7.25
    # --- stone platform with coping, plinth and big corner/accent stones
    bx(mb, -PX, PX, PY0, PY1, -0.02, PZ - 0.18, "stone")
    bx(mb, -PX - 0.08, PX + 0.08, PY0 - 0.08, PY1 + 0.08, PZ - 0.2, PZ, "stone_dark")
    bx(mb, -PX - 0.1, PX + 0.1, PY0 - 0.1, PY1 + 0.1, -0.02, 0.18, "stone_dark")
    for x in (-PX, PX):
        for y in (PY0, PY1):
            bx(mb, x - 0.45, x + 0.45, y - 0.45, y + 0.45, 0.15, PZ - 0.19, "stone_light")
    for x in (-8.3, -6.0, 6.0, 8.3):
        bx(mb, x - 0.55, x + 0.55, PY0 - 0.04, PY0 + 0.3, 0.15, PZ - 0.19, "stone_warm")
    for y in (-2.6, 0.6, 3.9):
        for x in (-PX, PX):
            bx(mb, x - 0.04 if x > 0 else x - 0.04, x + 0.04 if x < 0 else x + 0.04, y - 0.55, y + 0.55,
               0.15, PZ - 0.19, "stone_warm")
    # --- wide front stairs (front = -Y) with cheek walls
    SW = 4.2
    stairs_block(mb, -SW, SW, PY0 - 2.05, PY0 + 0.05, 0.0, PZ, 6, color="stone_light", alt="stone")
    for s in (-1, 1):
        bx(mb, s * SW, s * (SW + 0.55), PY0 - 2.12, PY0 + 0.05, -0.02, PZ + 0.22, "stone_dark")
        mb.prism((s * (SW + 0.275), PY0 - 1.9, PZ + 0.22), 0.26, 0.35, 6, "stone", radius_top=0.2)
    # --- main body (inner walls)
    ZF = PZ
    IX0, IX1, IY0, IY1 = -7.3, 7.3, -4.2, 5.35
    ZW = 5.0
    bx(mb, IX0 - 1.45, IX1 + 1.45, IY0 - 1.65, IY1 + 0.25, ZF - 0.02, ZF + 0.14, "wood")     # veranda floor
    front, back, left, right = timber_box(mb, IX0, IX1, IY0, IY1, ZF + 0.14, ZW + 0.4, post=0.34, spacing=2.45,
                                          koshi=0.8, wall_col="plaster", koshi_col="wood_dark",
                                          post_col="wood_red", beam_col="wood_dark", beam_h=0.3, sill_h=0.18,
                                          skip_posts=[(-1.217, IY0 + 0.17), (1.217, IY0 + 0.17)])
    o = -0.02
    bx(mb, IX0 + o, IX1 - o, IY0 + o, IY1 - o, ZF + 2.95, ZF + 3.17, "wood_dark")              # nuki band
    # big glowing front doors across the three central bays
    front.shoji(-3.6, 3.6, ZF + 0.32, ZF + 2.9, panels=6, cols=1, rows=3, frame="wood_red_dark", kumiko="wood_dark",
                glow="glow_warm", koshi=0.35)
    for u in (-2.4, 2.4):
        front.box(u - 0.15, u + 0.15, ZF + 0.14, ZF + 2.95, -0.03, 0.12, "wood_red")
    back.window(-4.85, ZF + 1.4, ZF + 2.6, 1.6, bars=4)
    back.window(0.0, ZF + 1.4, ZF + 2.6, 2.2, bars=6)
    back.window(4.85, ZF + 1.4, ZF + 2.6, 1.6, bars=4)
    for fac in (left, right):
        fac.window(0.6, ZF + 1.4, ZF + 2.6, 2.0, bars=5)
    # --- red colonnade around the veranda (front + sides)
    OX, OY0, OY1 = 8.45, IY0 - 1.45, IY1 + 0.05
    cols_ = set()
    for x in frange(-OX, OX, 7):
        cols_.add((round(x, 3), OY0))
    for y in frange(OY0, OY1, 4):
        cols_.add((-OX, round(y, 3))); cols_.add((OX, round(y, 3)))
    for (x, y) in sorted(cols_):
        bx(mb, x - 0.36, x + 0.36, y - 0.36, y + 0.36, ZF - 0.05, ZF + 0.17, "stone_dark")
        mb.prism((x, y, ZF + 0.15), 0.25, ZW - ZF + 0.2, 6, "wood_red", base=False)
    bx(mb, -OX - 0.2, OX + 0.2, OY0 - 0.17, OY0 + 0.17, ZW - 0.1, ZW + 0.25, "wood_red_dark")
    for x in (-OX, OX):
        bx(mb, x - 0.17, x + 0.17, OY0 - 0.2, OY1 + 0.2, ZW - 0.1 + 0.001, ZW + 0.25 - 0.001, "wood_red_dark")
    bx(mb, -OX - 0.2, OX + 0.2, OY0 - 0.12, OY0 + 0.12, ZF + 3.0, ZF + 3.18, "wood_red_dark")
    for x in frange(-OX, OX, 7):
        bx(mb, x - 0.32, x + 0.32, OY0 - 0.3, OY0 + 0.3, ZW + 0.25, ZW + 0.45, "wood_dark")
    # --- lower roof tier (truncated hip, up-turned corners)
    cy = 0.0
    DT = 3.8
    low = Roof(W=10.6, D=7.3, ze=5.6, H=3.9, cy=cy, curve=0.3, lift=0.7, lift_len=4.2, flare=0.3, nlev=2,
               frL=[0.0, 0.06, 0.16, 0.32, 0.5, 0.68, 0.84, 0.94], frS=[0.0, 0.08, 0.22, 0.5, 0.78, 0.92])
    tile_irimoya(mb, low, rib_spacing=0.9, segs=2, thick=0.42, d_top=DT, band=None, hip_w=0.3)
    # --- upper storey (clerestory) + upper roof
    UX, UY0, UY1 = 6.0, cy - 3.3, cy + 3.3
    zu0 = low.base(DT) - 0.1
    zu1 = zu0 + 1.5
    uf, ub, ul, ur = timber_box(mb, -UX, UX, UY0, UY1, zu0, zu1, post=0.3, spacing=2.0, wall_col="plaster",
                                post_col="wood_red", beam_col="wood_dark", sill_h=0.2, beam_h=0.24)
    for fac in (uf, ub):
        for u in (-3.4, 3.4):
            fac.window(u, zu0 + 0.5, zu0 + 1.15, 1.5, bars=3, frame="wood_dark")
    up = Roof(W=7.6, D=5.0, ze=zu1 + 0.4, H=2.5, xg=4.6, cy=cy, curve=0.42, lift=0.6, lift_len=3.2, flare=0.28,
              nlev=3, frL=[0.0, 0.06, 0.16, 0.32, 0.5, 0.68, 0.84, 0.94], frS=[0.0, 0.1, 0.25, 0.5, 0.75, 0.9])
    tile_irimoya(mb, up, rib_spacing=0.8, segs=3, thick=0.4, ridge_h=0.5, hip_w=0.3, oni="tile_dark")
    gable_boards(mb, up, color="wood_dark", lattice="gold_dark", bars=7, out=0.04)
    zr = up.zr()
    for sx in (-1, 1):
        shachihoko(mb, sx * (up.xg + 0.05), cy, zr + 0.22, sx, scale=1.0)
    # plaque (gaku) on the clerestory front
    bx(mb, -1.2, 1.2, UY0 - 0.2, UY0 - 0.08, zu0 + 0.2, zu0 + 1.15, "gold_dark")
    bx(mb, -1.05, 1.05, UY0 - 0.26, UY0 - 0.18, zu0 + 0.28, zu0 + 1.07, "wood_black")
    # --- entrance lanterns + banners
    for x in (-4.6, 4.6):
        hanging_lantern(mb, x, OY0, ZW - 0.1, h=0.8, r=0.34, cord=0.25)
    for s in (-1, 1):
        x = s * 6.0 - 0.5
        bx(mb, x - 0.35, x + 0.35, PY0 - 1.95, PY0 - 1.25, -0.02, 0.35, "stone_dark", drop=('-z',))
        nobori(mb, x, PY0 - 1.6, 0.35, height=6.0, cloth="cloth_red" if s < 0 else "cloth_indigo", ch=3.6, w=0.95)
    mb.collider_mesh()
    mb.tag("occluder", "light_warm")
    mb.set("light_offset", [0.0, -6.0, 3.0])
    return mb.finish()


# ============================================================== 8. dojo_gate
def round_socket(mb, x, y, z, r=0.3, sy=-1):
    """Empty stone seal socket: thick ring + recessed dark disc, facing sy*Y."""
    ring_ = mb.prism((0, 0, 0), r * 1.22, 0.16, 12, "stone", radius_top=r * 1.12, rot=(90 * sy * -1, 0, 0))
    ring_.transform(loc=(x, y, z))
    disc = mb.prism((0, 0, 0), r, 0.2, 12, "stone_dark", rot=(90 * sy * -1, 0, 0))
    disc.transform(loc=(x, y - sy * 0.06, z))


def build_dojo_gate(seed):
    """Monumental gate in front of the dojo plateau: 11 m wide, two-tier roof,
    4.2 x 4.5 m opening with three (unlit) stone seal sockets above it."""
    mb = L.MeshBuilder("dojo_gate", seed)
    HW = 4.65            # half width of the body
    OW, OH = 2.1, 4.5    # half opening width, opening height
    YP = 1.35            # pillar line (front -YP / back +YP)
    ZB = 6.45            # top of the body (inside the lower roof)
    for s in (-1, 1):
        x_in, x_out = s * OW, s * HW
        # side wings: stone base + plaster wall framed by red posts
        bx(mb, x_in + s * 0.3, x_out, -YP + 0.1, YP - 0.1, -0.02, 1.0, "stone")
        bx(mb, x_in + s * 0.25, x_out + s * 0.06, -YP + 0.04, YP - 0.04, 0.95, 1.12, "stone_dark")
        bx(mb, x_in + s * 0.3, x_out - s * 0.05, -YP + 0.18, YP - 0.18, 1.1, ZB, "plaster")
        xm = (x_in + x_out) / 2 + s * 0.15
        for y in (-YP, YP):
            for x in (x_in + s * 0.3, x_out - s * 0.27):
                mb.prism((x, y, -0.02), 0.42, 0.32, 8, "stone_dark", radius_top=0.34, base=False)
                mb.prism((x, y, 0.28), 0.29, ZB - 0.28, 8, "wood_red", base=False)
            bx(mb, xm - 0.15, xm + 0.15, y - 0.15, y + 0.15, 1.05, ZB, "wood_red")
            bx(mb, x_in + s * 0.3, x_out, y - 0.12, y + 0.12, 3.0, 3.2, "wood_red_dark")
        # wing windows (dark lattice, not glowing)
        for y, sg in ((-YP + 0.18, -1), (YP - 0.18, 1)):
            fac = Facade(mb, 'x', y, sg)
            for xc in ((x_in + s * 0.3 + xm) / 2, (xm + x_out - s * 0.27) / 2):
                fac.box(xc - 0.42, xc + 0.42, 3.55, 4.45, -0.02, 0.04, "wood_black")
                for k in range(3):
                    u = xc - 0.28 + k * 0.28
                    fac.box(u - 0.04, u + 0.04, 3.55, 4.45, 0.0, 0.09, "wood_red_dark")
    # lintel + socket board over the opening with the three seal sockets (front face)
    bx(mb, -OW - 0.3, OW + 0.3, -YP - 0.2, YP + 0.2, OH, OH + 0.16, "wood_red_dark")
    bx(mb, -OW - 0.1, OW + 0.1, -YP + 0.1, YP - 0.1, OH + 0.16, ZB, "plaster", drop=('+z',))
    bx(mb, -1.85, 1.85, -YP - 0.24, -YP + 0.12, OH + 0.16, OH + 0.98, "wood_black")        # socket board
    bx(mb, -1.95, 1.95, -YP - 0.3, -YP + 0.12, OH + 0.98, OH + 1.1, "wood_red_dark")
    bx(mb, -HW, HW, -YP - 0.2, -YP + 0.2, 5.95, 6.2, "wood_red_dark")
    bx(mb, -HW, HW, YP - 0.2, YP + 0.2, 5.95, 6.2, "wood_red_dark")
    for x in (-1.15, 0.0, 1.15):
        round_socket(mb, x, -YP - 0.24, OH + 0.57, r=0.3, sy=-1)
    # threshold + door stops
    bx(mb, -OW, OW, -0.12, 0.12, -0.02, 0.08, "wood_dark")
    for s in (-1, 1):
        bx(mb, s * OW - 0.04, s * (OW + 0.3), -0.3, 0.3, 0.0, OH, "wood_red_dark")
    # --- lower roof (truncated hip with up-turned corners)
    DT = 1.25
    low = Roof(W=5.3, D=2.55, ze=6.72, H=1.25, curve=0.35, lift=0.45, lift_len=2.4, flare=0.18, nlev=2,
               frL=[0.0, 0.06, 0.18, 0.35, 0.5, 0.65, 0.82, 0.94], frS=[0.0, 0.15, 0.5, 0.85])
    tile_irimoya(mb, low, rib_spacing=0.6, segs=2, thick=0.3, d_top=DT, band=None, hip_w=0.24)
    # --- neck (short upper storey) with red posts and dark lattice
    zu0 = low.base(DT) - 0.12
    zu1 = 7.5
    uf, ub, ul, ur = timber_box(mb, -3.6, 3.6, -1.3, 1.3, zu0, zu1, post=0.24, spacing=1.8, wall_col="wood_black",
                                post_col="wood_red", beam_col="wood_red_dark", sill_h=0.12, beam_h=0.14)
    for fac in (uf, ub):
        for u in frange(-3.2, 3.2, 16):
            fac.box(u - 0.04, u + 0.04, zu0 + 0.1, zu1 - 0.1, -0.02, 0.06, "wood_red_dark")
    # --- upper roof (irimoya)
    up = Roof(W=4.15, D=2.25, ze=7.72, H=0.58, xg=2.6, curve=0.35, lift=0.38, lift_len=1.8, flare=0.18,
              nlev=3, frL=[0.0, 0.07, 0.2, 0.5, 0.8, 0.93], frS=[0.0, 0.15, 0.5, 0.85])
    tile_irimoya(mb, up, rib_spacing=0.55, segs=2, thick=0.3, ridge_h=0.3, hip_w=0.22, oni="gold_dark")
    gable_boards(mb, up, color="wood_red_dark", lattice="gold_dark", bars=5, out=0.04)
    mb.collider_mesh()
    mb.tag("occluder")
    return mb.finish()


# ============================================================== door leaves
def door_leaf(mb, W, H, T, studs_rows=4, studs_cols=4, wood="wood_dark", band="iron", stud="iron_light",
              planks=5, pull=True):
    """Heavy door leaf, hinge at x=0, extends to +X.  Front = -Y, back = +Y."""
    pw = W / planks
    for i in range(planks):
        c = wood if i % 2 == 0 else ("wood_black" if wood == "wood_dark" else wood)
        bx(mb, i * pw + 0.004, (i + 1) * pw - 0.004, -T / 2 + 0.01 * (i % 2), T / 2 - 0.01 * (i % 2), 0.0, H, c)
    # hinge stile (pivot post) and top/bottom rails
    mb.prism((0.07, 0, 0.0), 0.09, H + 0.08, 8, "wood_black")
    for z in (0.02, H - 0.2):
        bx(mb, 0.0, W, -T / 2 - 0.03, T / 2 + 0.03, z, z + 0.18, "wood_black")
    # iron bands with studs on both faces
    zs = frange(H * 0.18, H * 0.82, studs_rows - 1)
    for z in zs:
        for sy in (-1, 1):
            y0 = sy * T / 2
            bx(mb, 0.05, W - 0.04, y0 - 0.02, y0 + 0.02, z - 0.07, z + 0.07, band)
            for x in frange(0.25, W - 0.2, studs_cols - 1):
                p = mb.cone((0, 0, 0), 0.06, 0.06, 4, stud, rot=(-90 * sy, 0, 0))
                p.transform(loc=(x, y0 + sy * 0.015, z))
    if pull:
        for sy in (-1, 1):
            p = mb.prism((0, 0, 0), 0.12, 0.05, 8, "iron", rot=(90, 0, 0))
            p.transform(loc=(W - 0.3, sy * (T / 2 + 0.04), H * 0.47))
            r = mb.prism((0, 0, 0), 0.16, 0.035, 8, "iron_light", radius_top=0.16, rot=(90, 0, 0), cap=False)
            r.transform(loc=(W - 0.3, sy * (T / 2 + 0.07), H * 0.4))


def build_dojo_gate_door(seed):
    mb = L.MeshBuilder("dojo_gate_door", seed)
    door_leaf(mb, 2.1, 4.4, 0.25, studs_rows=5, studs_cols=4, planks=5)
    mb.collider_box((2.1, 0.25, 4.4), (1.05, 0.0, 2.2))
    mb.tag("nonstatic")
    mb.set("pivot", "hinge_edge_x0")
    return mb.finish()


def build_wall_gate_door(seed):
    mb = L.MeshBuilder("wall_gate_door", seed)
    door_leaf(mb, 1.7, 3.5, 0.2, studs_rows=3, studs_cols=3, planks=4, wood="wood")
    mb.collider_box((1.7, 0.2, 3.5), (0.85, 0.0, 1.75))
    mb.tag("nonstatic")
    mb.set("pivot", "hinge_edge_x0")
    return mb.finish()


# ============================================================== 10. wall_segment
def wall_cap(mb, x0, x1, half, ze, H, rib_sp=0.4, rib_inset=None, thick=0.14):
    roof = ProfileRoof.gable(x0, x1, half, ze, H, thick, curve=0.0, n=1)
    roof.build(mb, "tile_dark", "wood_dark", "wood_dark", end="tile_dark")
    n = len(roof.prof)
    ins = rib_sp / 2 if rib_inset is None else rib_inset
    roof.ribs(mb, "tile_blue", spacing=rib_sp, i0=0, i1=n // 2, inset=ins, margin=0.08, w=0.15, h=0.06)
    roof.ribs(mb, "tile_blue", spacing=rib_sp, i0=n - 1, i1=n // 2, inset=ins, margin=0.08, w=0.15, h=0.06)
    return roof


def build_wall_segment(seed):
    """Clan wall (dobei), tiles seamlessly along X: x in [-4, 4]."""
    mb = L.MeshBuilder("wall_segment", seed)
    rng = random.Random(seed * 5 + 1)
    HX, T = 4.0, 0.45
    # stone base: core + two courses of slightly proud blocks on both faces
    bx(mb, -HX, HX, -T, T, -0.02, 1.2, "stone")
    for sy in (-1, 1):
        x = -HX
        for row, (z0, z1) in enumerate(((0.0, 0.62), (0.6, 1.16))):
            x = -HX + (0.0 if row == 0 else 0.55)
            first = True
            while x < HX - 0.05:
                w = rng.uniform(0.85, 1.35)
                if first and row == 1:
                    bx(mb, -HX, x - 0.04, sy * T - 0.04, sy * (T + 0.035), z0, z1, "stone_light")
                    first = False
                xe = min(HX, x + w)
                if HX - xe < 0.35:
                    xe = HX
                c = rng.choice(("stone", "stone_light", "stone_warm", "stone"))
                bx(mb, x + 0.035, xe - 0.035 if xe < HX else HX, sy * T - 0.04 * sy, sy * (T + 0.035),
                   z0 + 0.03, z1 - 0.03, c)
                x = xe
    bx(mb, -HX, HX, -T - 0.07, T + 0.07, 1.14, 1.24, "stone_dark")
    # plaster upper wall with timber posts and top beam
    bx(mb, -HX, HX, -T + 0.1, T - 0.1, 1.2, 3.12, "plaster")
    for x in (-2.0, 2.0):
        bx(mb, x - 0.12, x + 0.12, -T + 0.06, T - 0.06, 1.2, 2.95, "wood_dark")
    bx(mb, -HX, HX, -T + 0.06, T - 0.06, 2.72, 2.98, "wood_dark")
    # small loopholes (sama): dark squares + triangles
    for sy in (-1, 1):
        for x in (-3.0, 3.0):
            Facade(mb, 'x', sy * (T - 0.1), sy).box(x - 0.13, x + 0.13, 1.85, 2.11, -0.02, 0.012, "black")
        for x in (-1.0, 1.0):
            Facade(mb, 'x', sy * (T - 0.1), sy).box(x - 0.1, x + 0.1, 1.9, 2.1, -0.02, 0.012, "black")
    # tiled cap overhanging both sides
    wall_cap(mb, -HX, HX, 0.82, 3.02, 0.36, rib_sp=0.4)
    bx(mb, -HX, HX, -0.16, 0.16, 3.33, 3.52, "tile_dark")
    bx(mb, -HX, HX, -0.18, 0.18, 3.36, 3.42, "plaster")
    mb.collider_box((8.0, 0.9, 3.5), (0, 0, 1.75))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 11. wall_post
def build_wall_post(seed):
    mb = L.MeshBuilder("wall_post", seed)
    H = 0.6
    bx(mb, -H, H, -H, H, -0.02, 1.25, "stone")
    bx(mb, -H - 0.04, H + 0.04, -H - 0.04, H + 0.04, 0.0, 0.6, "stone_light")
    bx(mb, -H - 0.06, H + 0.06, -H - 0.06, H + 0.06, 1.18, 1.3, "stone_dark")
    bx(mb, -H + 0.08, H - 0.08, -H + 0.08, H - 0.08, 1.3, 3.0, "plaster")
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx(mb, sx * (H - 0.04) - 0.1, sx * (H - 0.04) + 0.1, sy * (H - 0.04) - 0.1, sy * (H - 0.04) + 0.1,
               1.3, 3.0, "wood_dark")
    bx(mb, -H + 0.02, H - 0.02, -H + 0.02, H - 0.02, 2.78, 3.02, "wood_dark")
    roof = Roof(W=0.9, D=0.9, ze=3.12, H=0.44, curve=0.3, lift=0.12, nlev=2, frL=[0.0, 0.2, 0.5, 0.8],
                frS=[0.0, 0.2, 0.5, 0.8])
    roof.build(mb, "tile_dark", "wood_dark", "wood_dark", thick=0.16, nose=[(-0.03, -0.07)])
    roof.ribs(mb, "tile_blue", spacing=0.36, segs=1, w=0.13, h=0.05)
    roof.ridges(mb, "tile_dark", main=False, hip_w=0.13, hip_h=0.12, end_up=0.08, end_ext=0.08)
    mb.prism((0, 0, roof.zr() - 0.08), 0.14, 0.2, 6, "tile_dark")
    mb.prism((0, 0, roof.zr() + 0.1), 0.09, 0.14, 6, "stone_dark", radius_top=0.0)
    mb.collider_box((1.2, 1.2, 3.8), (0, 0, 1.9))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 12. wall_gate
def build_wall_gate(seed):
    """Yagura gate tower for the village wall (8 m wide, opening 3.4 x 3.6)."""
    mb = L.MeshBuilder("wall_gate", seed)
    rng = random.Random(seed * 13 + 2)
    HX, OW, OH = 4.0, 1.7, 3.6
    D0, D1 = -1.5, 1.5
    for s in (-1, 1):
        x_in, x_out = s * OW, s * HX
        # stone pier with battered blocks
        bx(mb, x_in + s * 0.35, x_out, D0, D1, -0.02, 1.6, "stone")
        for (z0, z1) in ((0.0, 0.55), (0.53, 1.08), (1.06, 1.58)):
            for y in (D0, D1):
                xa = x_in + s * 0.35
                nb = 2
                for k in range(nb):
                    a = xa + (x_out - xa) * k / nb
                    b = xa + (x_out - xa) * (k + 1) / nb
                    off = 0.18 * ((k + int(z0 * 2)) % 2) * s
                    c = rng.choice(("stone", "stone_light", "stone_warm"))
                    bx(mb, a + 0.03 * s + off * 0, b - 0.03 * s, y - 0.035, y + 0.035, z0 + 0.03, z1 - 0.03, c)
        bx(mb, x_in + s * 0.3, x_out, D0 - 0.06, D1 + 0.06, 1.56, 1.68, "stone_dark")
        bx(mb, x_in + s * 0.42, x_out - s * 0.0, D0 + 0.12, D1 - 0.12, 1.68, 3.95, "plaster")
        # red-brown timber frame on the piers
        for y in (D0 + 0.1, D1 - 0.1):
            for x in (x_in + s * 0.25, x_out - s * 0.15):
                bx(mb, x - 0.15, x + 0.15, y - 0.15, y + 0.15, 1.6, 4.0, "wood_dark")
        bx(mb, x_in + s * 0.25, x_out, D0 + 0.0, D0 + 0.2, 2.7, 2.88, "wood_dark")
        bx(mb, x_in + s * 0.25, x_out, D1 - 0.2, D1 - 0.0, 2.7, 2.88, "wood_dark")
        # door stop posts
        bx(mb, s * OW - 0.05, s * OW + 0.05 + s * 0.2, -0.25, 0.25, 0.0, OH, "wood_black")
    # lintel + tower floor
    bx(mb, -HX, HX, D0 - 0.05, D1 + 0.05, OH, OH + 0.4, "wood_dark")
    bx(mb, -OW, OW, -0.12, 0.12, -0.02, 0.06, "wood_dark")
    # tower body
    zt0, zt1 = OH + 0.4, 5.86
    tf, tb, tl, tr = timber_box(mb, -3.5, 3.5, -1.25, 1.25, zt0, zt1, post=0.24, spacing=1.75, wall_col="plaster",
                                post_col="wood_dark", sill_h=0.16, beam_h=0.18)
    for fac in (tf, tb):
        for u in (-1.75, 0.0, 1.75):
            fac.window(u, zt0 + 0.35, zt0 + 0.95, 0.75, bars=3)
    for fac in (tl, tr):
        fac.window(0.0, zt0 + 0.35, zt0 + 0.95, 0.7, bars=3)
    # skirt pent roof between pier tops and tower (front/back)
    for sgn in (-1, 1):
        sk = ProfileRoof.shed(-HX - 0.2, HX + 0.2, sgn * (D1 + 0.55), sgn * (1.25 - 0.05), OH + 0.25, OH + 0.75, 0.13,
                              n=1)
        sk.build(mb, "tile_dark", "wood_dark", "wood_dark")
        i0 = 0 if sgn < 0 else len(sk.prof) - 1
        sk.ribs(mb, "tile_blue", spacing=0.55, i0=i0, i1=len(sk.prof) - 1 - i0, inset=0.15, margin=0.04, w=0.15, h=0.06)
    # tower roof: irimoya
    roof = Roof(W=4.3, D=2.25, ze=6.07, H=1.3, xg=2.7, curve=0.35, lift=0.35, lift_len=1.6, flare=0.15, nlev=3,
                frL=[0.0, 0.08, 0.22, 0.5, 0.78, 0.92], frS=[0.0, 0.15, 0.5, 0.85])
    tile_irimoya(mb, roof, rib_spacing=0.58, segs=2, thick=0.3, ridge_h=0.3, hip_w=0.22)
    gable_boards(mb, roof, color="wood_dark", lattice="wood_dark", bars=4, out=0.03)
    # lantern under the gate
    hanging_lantern(mb, 0.0, D0 - 0.25, OH + 0.25, h=0.45, r=0.17, cord=0.15)
    mb.collider_mesh()
    mb.tag("occluder", "light_warm")
    mb.set("light_offset", [0.0, -2.2, 2.6])
    return mb.finish()


# ============================================================== 14. mountain_cabin
def snow_blanket(mb, x0, x1, D, ze, H, rng, nx=6, ny=3, thick=0.24, inset=0.14, droop=0.1, bump=0.07):
    """Lumpy snow layer on a straight gable roof z = ze + H*(1-|y|/D), ridge along X.
    Inset from the eaves so the dark roof edge still reads; drooping rounded lips."""
    Di = D - inset
    ys = [-Di * (1 - i / ny) for i in range(ny + 1)] + [Di * (1 - i / ny) for i in range(ny - 1, -1, -1)]
    surf = lambda y: ze + H * (1 - abs(y) / D)
    xs = frange(x0, x1, nx)
    bumps = {}
    rings = []
    for xi, x in enumerate(xs):
        endf = 0.55 if xi in (0, nx) else 1.0
        top = []
        for j, y in enumerate(ys):
            z = surf(y) + thick * endf
            if j in (0, len(ys) - 1):
                z -= droop
            elif 0 < xi < nx:
                z += rng.uniform(-bump, bump)
            top.append((x, y, z))
        lip_f = (x, -Di - 0.07, surf(-Di) + 0.02)
        lip_b = (x, Di + 0.07, surf(Di) + 0.02)
        bottom = [(x, y, surf(y) - 0.03) for y in reversed(ys)]
        rings.append([lip_f] + top + [lip_b] + bottom[1:-1])
    part, bands, caps = loft_dd(mb, rings, "snow", cap_start=True, cap_end=True)
    nt = len(ys) + 2
    for band in bands:
        for f, seg in band:
            if seg == 0 or seg == nt - 2:
                mb._tag([f], "snow_shade")
    mb._tag(caps, "snow_shade")
    return part


def log_x(mb, x0, x1, y, z, r, color="wood", end="wood_light"):
    p = mb.prism((x0, y, z), r, x1 - x0, 6, color, rot=(0, 90, 0))
    p.color_faces(lambda f: end if abs(f.normal.x) > 0.9 else None)
    return p


def log_y(mb, y0, y1, x, z, r, color="wood", end="wood_light"):
    p = mb.prism((x, y0, z), r, y1 - y0, 6, color, rot=(-90, 0, 0))
    p.color_faces(lambda f: end if abs(f.normal.y) > 0.9 else None)
    return p


def build_mountain_cabin(seed):
    """Mountain boss's rough hut: stone base, heavy log walls, snowy board roof, icicles."""
    mb = L.MeshBuilder("mountain_cabin", seed)
    rng = random.Random(seed * 17 + 5)
    X0, X1, Y0, Y1 = -2.75, 2.75, -2.15, 2.15
    ZS = 0.85
    # rough stone base
    bx(mb, X0, X1, Y0, Y1, -0.02, ZS, "stone_dark", drop=('-z',))
    for (y, sg) in ((Y0, -1), (Y1, 1)):
        x = X0 - 0.05
        row = 0
        for (z0, z1) in ((0.0, 0.45), (0.42, ZS + 0.02)):
            x = X0 - 0.05 + (0.35 if row else 0.0)
            while x < X1:
                w = rng.uniform(0.6, 1.0)
                xe = min(X1 + 0.05, x + w)
                c = rng.choice(("stone", "rock", "stone_dark", "rock_light"))
                bx(mb, x + 0.03, xe - 0.03, y - 0.06 * (sg < 0) - 0.0, y + 0.06 * (sg > 0), z0 + 0.03, z1 - 0.02, c,
                   drop=(('+y',) if sg < 0 else ('-y',))).jitter(0.025)
                x = xe
            row += 1
    for (x, sg) in ((X0, -1), (X1, 1)):
        bx(mb, x - 0.06 * (sg < 0), x + 0.06 * (sg > 0), Y0 + 0.05, Y1 - 0.05, 0.02, ZS, "rock",
           drop=(('+x',) if sg < 0 else ('-x',))).jitter(0.03)
    # log walls (alternating courses, ends crossing at the corners)
    r = 0.16
    zc = ZS + r
    k = 0
    while zc < 2.75:
        if k % 2 == 0:
            for y in (Y0 + r, Y1 - r):
                log_x(mb, X0 - 0.3, X1 + 0.3, y, zc, r, color="wood" if k % 4 else "wood_dark")
        else:
            for x in (X0 + r, X1 - r):
                log_y(mb, Y0 - 0.3, Y1 + 0.3, x, zc, r, color="wood" if k % 4 != 1 else "wood_dark")
        zc += r * 1.62
        k += 1
    bx(mb, X0 + 0.2, X1 - 0.2, Y0 + 0.2, Y1 - 0.2, ZS - 0.05, 3.1, "wood_black", drop=('-z', '+z'))
    for x in (X0 + 0.12, X1 - 0.12):
        gable_wall(mb, x, Y0 + 0.05, Y1 - 0.05, 2.75, 4.25, 0.16, "wood_dark")
        sx = -1 if x < 0 else 1
        for yb in (-0.9, -0.3, 0.3, 0.9):
            ztop = 4.25 - abs(yb) / 2.1 * 1.5 - 0.08
            bx(mb, x + sx * 0.07, x + sx * 0.12, yb - 0.035, yb + 0.035, 2.8, ztop, "wood")
    # door with a glowing gap + small window
    bx(mb, -0.6, 0.6, Y0 - 0.06, Y0 + 0.3, ZS - 0.1, 2.45, "wood_black")
    bx(mb, -0.5, -0.2, Y0 - 0.08, Y0 + 0.3, ZS - 0.05, 2.3, "glow_fire")
    for u in (-0.08, 0.2, 0.47):
        bx(mb, u - 0.14, u + 0.14, Y0 - 0.2, Y0 - 0.08, ZS - 0.05, 2.3, "wood")
    bx(mb, -0.22, 0.62, Y0 - 0.24, Y0 - 0.14, 1.55, 1.68, "iron")
    bx(mb, -0.7, 0.7, Y0 - 0.12, Y0 + 0.2, 2.42, 2.6, "wood_dark")
    stone_slab(mb, 0.0, Y0 - 0.55, 0.22, 0.75, 0.35, 0.26, "stone", sides=6)
    for sx in (1,):
        bx(mb, 1.45, 2.15, Y0 - 0.06, Y0 + 0.3, 1.75, 2.25, "wood_black")
        bx(mb, 1.52, 2.08, Y0 - 0.08, Y0 + 0.3, 1.82, 2.18, "glow_fire")
        for u in (1.66, 1.8, 1.94):
            bx(mb, u - 0.03, u + 0.03, Y0 - 0.12, Y0 + 0.3, 1.8, 2.2, "wood_dark")
    bx(mb, -1.6, -0.9, Y1 - 0.3, Y1 + 0.08, 1.8, 2.25, "glow_fire")
    for u in (-1.48, -1.25, -1.02):
        bx(mb, u - 0.03, u + 0.03, Y1 - 0.3, Y1 + 0.12, 1.78, 2.27, "wood_dark")
    # board roof (ridge along X) with a thick snow blanket
    ze, H = 2.75, 1.65
    roof = ProfileRoof.gable(-3.5, 3.5, 3.0, ze, H, 0.2, curve=0.0, n=2)
    roof.build(mb, "wood_dark", "wood_dark", "wood_dark")
    snow_blanket(mb, -3.32, 3.32, 3.0, ze, H, rng, nx=6, ny=3, thick=0.26, inset=0.16)
    zr = ze + H
    # smoke vent on the ridge
    bx(mb, -0.45, 0.45, -0.35, 0.35, zr - 0.1, zr + 0.55, "wood_dark")
    bx(mb, -0.6, 0.6, -0.5, 0.5, zr + 0.55, zr + 0.7, "wood_dark")
    bx(mb, -0.58, 0.58, -0.48, 0.48, zr + 0.7, zr + 0.86, "snow").jitter(0.03)
    # icicles along both eaves
    for sgn in (-1, 1):
        for x in frange(-3.1, 3.1, 9):
            h = rng.uniform(0.18, 0.42)
            ice = mb.cone((0, 0, 0), 0.06, h, 4, "ice", rot=(180, 0, 0))
            ice.transform(loc=(x + rng.uniform(-0.15, 0.15), sgn * 2.93, ze - 0.12))
    # firewood stack against the right wall, snow on top
    log_pile(mb, -1.6, 1.0, X1 + 0.45, rows=3, r=0.12, axis='y', depth=0.7)
    bx(mb, X1 + 0.12, X1 + 0.8, -1.5, 0.95, 0.66, 0.78, "snow").jitter(0.03)
    for y in (-1.7, 1.15):
        bx(mb, X1 + 0.1, X1 + 0.8, y - 0.05, y + 0.05, 0.0, 0.78, "wood_dark")
    # snow drifts at the base
    for (x, y, rx, ry) in ((-2.9, -2.2, 0.8, 0.5), (2.6, 2.3, 1.0, 0.45), (-2.6, 2.4, 0.6, 0.4)):
        stone_slab(mb, x, y, 0.22, rx, ry, 0.24, "snow", sides=7, top_shrink=0.6, jit=0.03)
    mb.collider_box((5.6, 4.4, 4.6), (0, 0, 2.3))
    mb.tag("occluder", "light_fire")
    mb.set("light_offset", [0.0, -2.9, 1.2])
    return mb.finish()


# ============================================================== 15. lake_arena_platform
def _clip_poly_y(poly, y0, y1):
    """Clip a convex 2D polygon to the band y0 <= y <= y1."""
    def clip(pts, keep, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ka, kb = keep(a), keep(b)
            if ka:
                out.append(a)
            if ka != kb:
                out.append(inter(a, b))
        return out
    def at_y(yv):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yv - a[1]) / (b[1] - a[1]), yv)
    p = clip(poly, lambda q: q[1] >= y0, at_y(y0))
    if len(p) < 3:
        return []
    p = clip(p, lambda q: q[1] <= y1, at_y(y1))
    return p if len(p) >= 3 else []


def build_lake_arena_platform(seed):
    """Octagonal boss-arena platform on piles in the lake (z=0 water, floor z=1.0)."""
    mb = L.MeshBuilder("lake_arena_platform", seed)
    R = 10.6           # circumradius; flat edges face +-X / +-Y
    FZ = 1.0
    oct_ = [(R * math.cos(math.radians(22.5 + 45 * k)), R * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    # plank strips (alternating colours) running along X
    n = 22
    ys = frange(-R * math.cos(math.radians(22.5)), R * math.cos(math.radians(22.5)), n)
    for i in range(n):
        poly = _clip_poly_y(oct_, ys[i] + 0.02, ys[i + 1] - 0.02)
        if poly:
            mb.extrude_polygon(poly, FZ - 0.1, FZ, "wood_light" if i % 2 else "wood",
                               top_color="wood_light" if i % 2 else "wood")
    # dark sub-floor + fascia ring
    sub = [(x * 0.995, y * 0.995) for x, y in oct_]
    mb.extrude_polygon(sub, FZ - 0.3, FZ - 0.09, "wood_dark", base=True)
    ring_o = [(x * 1.012, y * 1.012) for x, y in oct_]
    for k in range(8):
        a, b = ring_o[k], ring_o[(k + 1) % 8]
        mb.plank_line((a[0], a[1], FZ - 0.17), (b[0], b[1], FZ - 0.17), 0.16, 0.26, "wood_red_dark")
    # central mon: dark octagon ring + gold disc (flush, walkable)
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        b = math.radians(22.5 + 45 * (k + 1))
        rr = 3.2
        mb.plank_line((rr * math.cos(a), rr * math.sin(a), FZ + 0.005), (rr * math.cos(b), rr * math.sin(b), FZ + 0.005),
                      0.3, 0.03, "wood_red_dark")
    mb.prism((0, 0, FZ - 0.02), 0.9, 0.045, 8, "gold", base=False)
    mb.prism((0, 0, FZ - 0.02), 0.55, 0.05, 8, "wood_red_dark", base=False)
    # piles
    pts = [(x * 0.97, y * 0.97) for x, y in oct_]
    pts += [((oct_[k][0] + oct_[(k + 1) % 8][0]) / 2 * 0.97, (oct_[k][1] + oct_[(k + 1) % 8][1]) / 2 * 0.97) for k in range(8)]
    pts += [(4.5 * math.cos(math.radians(45 * k)), 4.5 * math.sin(math.radians(45 * k))) for k in range(0, 8, 2)]
    for (x, y) in pts:
        mb.prism((x, y, -2.5), 0.22, 2.2 + FZ - 0.25 + 0.02, 6, "wood_dark", cap=False)
    # low red railing on 7 edges (the -Y edge is the open entrance)
    zr0, zr1 = FZ, FZ + 0.75
    rin = 0.985
    for k in range(8):
        a = (oct_[k][0] * rin, oct_[k][1] * rin)
        b = (oct_[(k + 1) % 8][0] * rin, oct_[(k + 1) % 8][1] * rin)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if mid[1] < -R * 0.8:       # entrance edge: just the two end posts stay (added below)
            continue
        for p in (a, mid):
            bx(mb, p[0] - 0.09, p[0] + 0.09, p[1] - 0.09, p[1] + 0.09, zr0 - 0.02, zr1 + 0.05, "wood_red", drop=('-z',))
            mb.cone((p[0], p[1], zr1 + 0.05), 0.11, 0.14, 4, "gold", rot=(0, 0, 45))
        mb.plank_line((a[0], a[1], zr1 - 0.05), (b[0], b[1], zr1 - 0.05), 0.12, 0.1, "wood_red")
        mb.plank_line((a[0], a[1], zr0 + 0.3), (b[0], b[1], zr0 + 0.3), 0.08, 0.07, "wood_red_dark")
    # stone lantern bases on the 4 diagonal edges
    for k in (1, 3, 5, 7):
        a = math.radians(45 * k)
        x, y = 8.5 * math.cos(a), 8.5 * math.sin(a)
        bx(mb, x - 0.5, x + 0.5, y - 0.5, y + 0.5, FZ - 0.02, FZ + 0.16, "stone_dark", drop=('-z',))
        mb.prism((x, y, FZ + 0.16), 0.3, 0.42, 6, "stone", radius_top=0.24, base=False)
        bx(mb, x - 0.33, x + 0.33, y - 0.33, y + 0.33, FZ + 0.58, FZ + 0.68, "stone_light", drop=('-z',))
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


# ============================================================== 16. shrine_small
def shide(mb, x, y, z, s=1.0):
    """Zig-zag paper streamer hanging from a rope at (x, y, z)."""
    w, h = 0.13 * s, 0.13 * s
    for i in range(3):
        dx = (w * 0.5) * (1 if i % 2 else -1) * 0.6
        bx(mb, x + dx - w / 2, x + dx + w / 2, y - 0.02, y + 0.02, z - (i + 1) * h, z - i * h + 0.01, "paper")


def rope_sag(mb, a, b, sag, r, color="rope", n=6, sides=6):
    a, b = Vector(a), Vector(b)
    pts = []
    for i in range(n + 1):
        t = i / n
        p = a + (b - a) * t
        p.z -= sag * 4 * t * (1 - t)
        pts.append(tuple(p))
    sec = [(r * math.cos(2 * math.pi * k / sides), r * math.sin(2 * math.pi * k / sides)) for k in range(sides)]
    return tube(mb, pts, sec, color)


def build_shrine_small(seed):
    """Small Shinto shrine: red pillars, copper roof with chigi, shimenawa, glowing lamp."""
    mb = L.MeshBuilder("shrine_small", seed)
    # stone platform + steps
    bx(mb, -2.1, 2.1, -1.45, 1.75, -0.02, 0.38, "stone", drop=('-z',))
    bx(mb, -2.16, 2.16, -1.51, 1.81, 0.33, 0.45, "stone_dark", drop=('-z',))
    stairs_block(mb, -0.8, 0.8, -1.95, -1.45, 0.0, 0.45, 2, color="stone_light")
    # raised floor on red posts
    ZF = 0.95
    X0, X1, Y0, Y1 = -1.35, 1.35, -0.75, 1.35
    bx(mb, X0 - 0.2, X1 + 0.2, Y0 - 0.55, Y1 + 0.15, ZF - 0.12, ZF, "wood_red_dark", drop=('-z',))
    for x in (X0, 0.0, X1):
        for y in (Y0 - 0.45, Y1):
            mb.prism((x, y, 0.42), 0.11, ZF - 0.5, 6, "wood_red", cap=False)
    # small steps up to the floor
    for i, (y0_, z1_) in enumerate(((-1.42, 0.62), (-1.3, 0.8))):
        bx(mb, -0.5, 0.5, y0_, y0_ + 0.14, 0.4, z1_, "wood_red_dark")
    # body
    front, back, left, right = timber_box(mb, X0, X1, Y0, Y1, ZF, 3.12, post=0.2, spacing=1.35, koshi=0.0,
                                          wall_col="plaster", post_col="wood_red", beam_col="wood_red_dark",
                                          sill_h=0.12, beam_h=0.2, skip_posts=[(0.0, Y0 + 0.1)])
    front.shoji(-0.95, 0.95, ZF + 0.12, 2.4, panels=2, cols=1, rows=3, frame="wood_red_dark", kumiko="wood_dark",
                glow="glow_window", koshi=0.25)
    # front pillars of the veranda
    for x in (X0 + 0.05, X1 - 0.05):
        mb.prism((x, Y0 - 0.45, ZF), 0.1, 1.85, 8, "wood_red", base=False)
    bx(mb, X0 - 0.1, X1 + 0.1, Y0 - 0.55, Y0 - 0.35, 2.68, 2.85, "wood_red_dark")
    # nagare-style copper roof (front slope longer), ridge along X
    roof = ProfileRoof.gable(-2.2, 2.2, 2.25, 2.62, 1.28, 0.16, curve=0.38, n=3, c=0.25, D2=1.55)
    roof.build(mb, "copper_green", "gold_dark", "wood_red_dark", end="copper_green")
    nn = len(roof.prof)
    roof.ribs(mb, "copper_green", spacing=0.55, i0=0, i1=nn // 2, inset=0.3, w=0.08, h=0.05, sink=0.03, margin=0.2)
    roof.ribs(mb, "copper_green", spacing=0.55, i0=nn - 1, i1=nn // 2, inset=0.3, w=0.08, h=0.05, sink=0.03, margin=0.2)
    roof.verges(mb, "copper_green", w=0.14, h=0.12, inset=0.06)
    zr = roof.ridge(mb, "copper_green", w=0.34, h=0.28, ext=0.0)
    # katsuogi (billets across the ridge) + crossed chigi at both ends
    for x in (-1.0, 0.0, 1.0):
        mb.prism((x, 0.25 - 0.4, zr + 0.02), 0.09, 0.8, 6, "gold_dark", rot=(-90, 0, 0))
    for sx in (-1, 1):
        x = sx * 2.15
        for sy in (-1, 1):
            mb.plank_line((x, 0.25 + sy * 0.55, zr - 0.45), (x, 0.25 - sy * 0.3, zr + 0.6), 0.07, 0.16, "wood_dark")
    # gable infill
    for x in (X0 + 0.1, X1 - 0.1):
        gable_wall(mb, x, Y0 + 0.1, Y1 - 0.1, 2.7, 3.55, 0.12, "wood_red_dark")
    # shimenawa rope with shide over the front
    rz = 2.42
    rope_sag(mb, (X0 - 0.02, Y0 - 0.58, rz), (X1 + 0.02, Y0 - 0.58, rz), 0.26, 0.11, "straw", n=6)
    for x in (-0.8, 0.0, 0.8):
        t = (x - X0) / (X1 - X0)
        sag = 0.26 * 4 * t * (1 - t)
        shide(mb, x, Y0 - 0.58, rz - 0.06 - sag, s=1.15)
    # offering box + hanging bronze lamp (glowing)
    bx(mb, -0.45, 0.45, -1.95, -1.6, 0.0, 0.5, "wood", drop=('-z',))
    bx(mb, -0.5, 0.5, -2.0, -1.55, 0.5, 0.58, "wood_dark")
    lx, ly = 1.05, Y0 - 0.95
    bx(mb, lx - 0.02, lx + 0.02, ly - 0.02, ly + 0.02, 2.2, 2.75, "iron")
    mb.cone((lx, ly, 2.08), 0.24, 0.16, 6, "copper_green")
    mb.prism((lx, ly, 1.75), 0.15, 0.33, 6, "glow_warm")
    mb.prism((lx, ly, 1.68), 0.17, 0.07, 6, "iron")
    mb.collider_box((4.4, 3.8, 3.9), (0, -0.05, 1.95))
    mb.tag("occluder", "light_warm")
    mb.set("light_offset", [lx, ly, 1.8])
    return mb.finish()


# ============================================================== 17/18. torii
def kasagi_path(x_half, z, up, n=6):
    pts = []
    for i in range(n + 1):
        t = -1 + 2 * i / n
        pts.append((t * x_half, 0.0, z + up * abs(t) ** 2.4))
    return pts


def build_torii_red(seed):
    mb = L.MeshBuilder("torii_red", seed)
    PX = 2.2
    for s in (-1, 1):
        # slight inward lean (myojin style)
        pile(mb, s * PX, 0, 0.0, 4.25, r=0.22, color="wood_red", sides=8, lean=(-s * 0.08, 0.0))
        mb.prism((s * (PX + 0.04), 0, -0.02), 0.29, 0.45, 8, "black", radius_top=0.27, base=False)
        mb.prism((s * (PX + 0.035), 0, 0.43), 0.3, 0.06, 8, "black", cap=False)
    # nuki crossbeam (passes through the pillars)
    bx(mb, -PX - 0.55, PX + 0.55, -0.11, 0.11, 3.3, 3.56, "wood_red")
    # shimaki (red) + kasagi (black, up-turned ends)
    tube(mb, kasagi_path(3.0, 4.2, 0.16), rect_section(0.36, 0.22, 0.0), "wood_red")
    tube(mb, kasagi_path(3.3, 4.4, 0.26), [(-0.24, 0.0), (0.24, 0.0), (0.2, 0.34), (-0.2, 0.34)], "black")
    # gakuzuka strut + plaque
    bx(mb, -0.12, 0.12, -0.09, 0.09, 3.5, 4.25, "wood_red")
    bx(mb, -0.34, 0.34, -0.12, 0.12, 3.62, 4.16, "black")
    bx(mb, -0.27, 0.27, -0.16, 0.16, 3.68, 4.1, "gold_dark")
    bx(mb, -0.22, 0.22, -0.18, 0.18, 3.73, 4.05, "black")
    mb.collider_mesh()
    return mb.finish()


def build_torii_stone(seed):
    mb = L.MeshBuilder("torii_stone", seed)
    rng = random.Random(seed * 3 + 9)
    PX = 1.85
    for s in (-1, 1):
        p = pile(mb, s * PX, 0, 0.0, 3.6, r=0.24, color="stone", sides=8, lean=(-s * 0.07, 0.0))
        p.jitter(0.012)
        p.color_faces(lambda f: "stone_moss" if (f.calc_center_median().z < 0.9 and rng.random() < 0.6) else None)
        mb.prism((s * PX, 0, -0.02), 0.36, 0.3, 8, "stone_dark", radius_top=0.32, base=False).jitter(0.015)
    bx(mb, -PX - 0.45, PX + 0.45, -0.13, 0.13, 2.85, 3.13, "stone").jitter(0.012)
    tube(mb, kasagi_path(2.45, 3.58, 0.1), rect_section(0.34, 0.24, 0.0), "stone_light")
    k = tube(mb, kasagi_path(2.7, 3.82, 0.2), [(-0.26, 0.0), (0.26, 0.0), (0.22, 0.38), (-0.22, 0.38)], "stone")
    k.color_faces(lambda f: "stone_moss" if f.normal.z > 0.5 and rng.random() < 0.35 else None)
    bx(mb, -0.14, 0.14, -0.11, 0.11, 3.1, 3.62, "stone")
    mb.collider_mesh()
    return mb.finish()


# ============================================================== 19. bridge_arch
def build_bridge_arch(seed):
    """Red taiko (drum) bridge, 9 m along Y, walkable curved plank deck."""
    mb = L.MeshBuilder("bridge_arch", seed)
    HL, HW, RISE = 4.5, 1.2, 1.4

    def zc(y):
        return RISE * math.cos(math.pi * y / (2 * HL)) ** 1.15 if abs(y) < HL else 0.0
    # deck planks (follow the curve)
    n = 18
    for i in range(n):
        y0 = -HL + 2 * HL * i / n
        y1 = -HL + 2 * HL * (i + 1) / n
        a = Vector((0, y0 + 0.012, zc(y0)))
        b = Vector((0, y1 - 0.012, zc(y1)))
        mb.plank_line((0, a.y, a.z - 0.05), (0, b.y, b.z - 0.05), 2 * HW, 0.1,
                      "wood_light" if i % 2 else "wood_pale")
    # curved side beams (red) + solid belly under the deck
    ys = frange(-HL, HL, 12)
    for s in (-1, 1):
        tube(mb, [(s * (HW + 0.05), y, zc(y) - 0.1) for y in ys], rect_section(0.16, 0.34, -0.3), "wood_red_dark")
    belly = []
    for y in ys:
        z = zc(y)
        belly.append([(-HW + 0.05, y, z - 0.12), (HW - 0.05, y, z - 0.12), (HW - 0.05, y, z - 0.38), (-HW + 0.05, y, z - 0.38)])
    loft_dd(mb, belly, "wood_red_dark", cap_start=True, cap_end=True)
    # legs into the water
    for y in (-2.0, 2.0):
        for s in (-1, 1):
            pile(mb, s * 0.95, y, -1.2, zc(y) - 0.3, r=0.13, color="wood_red", sides=6)
        bx(mb, -1.15, 1.15, y - 0.09, y + 0.09, zc(y) - 0.55, zc(y) - 0.3, "wood_red_dark")
    # railings: posts with gold caps, curved top + mid rails
    pys = [-HL + 0.15, -2.6, -1.0, 1.0, 2.6, HL - 0.15]
    for s in (-1, 1):
        x = s * (HW - 0.02)
        for y in pys:
            z = zc(y)
            bx(mb, x - 0.08, x + 0.08, y - 0.08, y + 0.08, z - 0.1, z + 1.0, "wood_red", drop=('-z',))
            mb.prism((x, y, z + 1.0), 0.1, 0.05, 6, "gold_dark")
            mb.cone((x, y, z + 1.05), 0.1, 0.2, 6, "gold")
        rys = frange(pys[0], pys[-1], 10)
        tube(mb, [(x, y, zc(y) + 0.86) for y in rys], rect_section(0.11, 0.09, 0.0), "wood_red")
        tube(mb, [(x, y, zc(y) + 0.42) for y in rys], rect_section(0.07, 0.07, 0.0), "wood_red_dark")
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


# ============================================================== 20. bridge_plank
def build_bridge_plank(seed):
    mb = L.MeshBuilder("bridge_plank", seed)
    rng = random.Random(seed * 23 + 1)
    HL, HW = 3.0, 1.0
    for x in (-0.68, 0.68):
        p = log_y(mb, -HL - 0.1, HL + 0.1, x, 0.16, 0.17, color="trunk", end="wood_light")
        p.jitter(0.02)
    n = 13
    w = 2 * HL / n
    for i in range(n):
        y = -HL + w * (i + 0.5) + rng.uniform(-0.03, 0.03)
        L_ = 2 * HW * rng.uniform(0.9, 1.0)
        off = rng.uniform(-0.08, 0.08)
        p = rbox(mb, (off, y, 0.37), (L_, w * rng.uniform(0.8, 0.92), 0.08),
                 rng.choice(("wood", "wood_light", "wood", "wood_light", "wood_pale", "wood_grey")), rz=rng.uniform(-4, 4))
        p.jitter(0.012)
    # rope rail on the +X side
    xs = 0.98
    for y in (-2.8, 0.0, 2.8):
        bx(mb, xs - 0.06, xs + 0.06, y - 0.06, y + 0.06, -0.05, 1.15, "wood", drop=('-z',)).jitter(0.01)
        mb.prism((xs, y, 0.95), 0.085, 0.08, 6, "rope", cap=False)
    for (ya, yb) in ((-2.8, 0.0), (0.0, 2.8)):
        rope_sag(mb, (xs, ya, 1.0), (xs, yb, 1.0), 0.18, 0.04, "rope", n=5, sides=5)
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


# ============================================================== 21/22. dock + boardwalk
def build_dock_segment(seed):
    """4 m (Y) dock piece, tiles along Y; z=0 is the water surface, deck at z=0.8."""
    mb = L.MeshBuilder("dock_segment", seed)
    HL, HW, DZ = 2.0, 1.1, 0.8
    n = 10
    w = 2 * HL / n
    for i in range(n):
        y0 = -HL + i * w
        bx(mb, -HW, HW, y0 + 0.015, y0 + w - 0.015, DZ - 0.08, DZ,
           ("wood_light", "wood", "wood_light", "wood_pale", "wood")[i % 5])
    for x in (-0.8, 0.8):
        bx(mb, x - 0.1, x + 0.1, -HL, HL, DZ - 0.3, DZ - 0.08, "wood_dark", drop=('-y', '+y'))
    for y in (-1.0, 1.0):
        bx(mb, -HW - 0.05, HW + 0.05, y - 0.09, y + 0.09, DZ - 0.38, DZ - 0.16, "wood_dark")
        for x in (-HW - 0.12, HW + 0.12):
            mb.prism((x, y, -2.0), 0.14, 2.0 + DZ + 0.28, 6, "wood_dark")
            mb.prism((x, y, DZ + 0.12), 0.155, 0.08, 6, "rope", cap=False)
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


def build_boardwalk_segment(seed):
    """6 m (Y) narrow lake boardwalk, tiles along Y; rope railing on the +X side."""
    mb = L.MeshBuilder("boardwalk_segment", seed)
    rng = random.Random(seed * 41 + 7)
    HL, HW, DZ = 3.0, 0.9, 0.8
    n = 15
    w = 2 * HL / n
    for i in range(n):
        y0 = -HL + i * w
        dz = rng.uniform(-0.012, 0.012)
        bx(mb, -HW + rng.uniform(0, 0.05), HW - rng.uniform(0, 0.05), y0 + 0.015, y0 + w - 0.015, DZ - 0.07 + dz, DZ + dz,
           rng.choice(("wood_light", "wood", "wood_light", "wood_grey")))
    for x in (-0.65, 0.65):
        bx(mb, x - 0.09, x + 0.09, -HL, HL, DZ - 0.27, DZ - 0.07, "wood_dark", drop=('-y', '+y'))
    for y in (-1.5, 1.5):
        bx(mb, -HW, HW, y - 0.08, y + 0.08, DZ - 0.33, DZ - 0.15, "wood_dark")
        mb.prism((-0.82, y, -2.0), 0.12, 2.0 + DZ - 0.15, 6, "wood_dark", cap=False)
        mb.prism((0.95, y, -2.0), 0.12, 2.0 + DZ + 0.95, 6, "wood_dark")
        mb.prism((0.95, y, DZ + 0.62), 0.135, 0.08, 6, "rope", cap=False)
    # rope: sags between the posts and is continuous across the tiling seam (y = +-3)
    zr = DZ + 0.68
    sag = 0.22
    rope_sag(mb, (0.95, -1.5, zr), (0.95, 1.5, zr), sag, 0.04, "rope", n=6, sides=5)
    def half(y_from, y_to, rising):
        pts = []
        for i in range(4):
            t = i / 3
            y = y_from + (y_to - y_from) * t
            u = 0.5 + 0.5 * t if not rising else 0.5 * t     # param on the full 3 m span
            pts.append((0.95, y, zr - sag * 4 * u * (1 - u)))
        sec = [(0.04 * math.cos(2 * math.pi * k / 5), 0.04 * math.sin(2 * math.pi * k / 5)) for k in range(5)]
        tube(mb, pts, sec, "rope")
    half(1.5, 3.0, False)
    half(-3.0, -1.5, True)
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


# ============================================================== 23/24. stone stairs
def stone_stairs(mb, W, n, depth, rise, wall_w, wall_up, rng, tread=("stone_light", "stone"), riser="stone_dark",
                 wall="stone", coping="stone_light"):
    """Solid stepped stairs rising toward +Y (low end at y=-depth/2), with side walls.
    W = total width including walls."""
    y0, y1 = -depth / 2, depth / 2
    d, h = depth / n, rise / n
    inner = W / 2 - wall_w
    prof = [(y0, 0.0)]
    for i in range(n):
        prof.append((y0 + i * d, (i + 1) * h))
        prof.append((y0 + (i + 1) * d if i < n - 1 else y1, (i + 1) * h))
    prof.append((y1, 0.0))
    ring = lambda x: [(x, y, z) for (y, z) in prof]
    part, bands, caps = loft_dd(mb, [ring(-inner - 0.02), ring(inner + 0.02)], riser, cap_start=True, cap_end=True)
    for f, seg in bands[0]:
        if seg >= 1 and seg <= 2 * n and seg % 2 == 1:      # horizontal treads
            mb._tag([f], tread[(seg // 2) % len(tread)])
    # step nosings (thin lighter lips) for readability
    for i in range(n):
        yf = y0 + i * d
        zt = (i + 1) * h
        bx(mb, -inner, inner, yf - 0.025, yf + 0.07, zt - 0.06, zt + 0.004, tread[(i + 1) % len(tread)],
           drop=('-z', '+y'))
    # side walls with a sloped top + coping + end blocks
    for s in (-1, 1):
        xa, xb = s * inner, s * (W / 2)
        wp = [(y0 - 0.05, 0.0), (y1, 0.0), (y1, rise + wall_up), (y0 + d * 0.6, h + wall_up)]
        wring = lambda x: [(x, y, z) for (y, z) in wp]
        p, _, _ = loft_dd(mb, [wring(xa), wring(xb)], wall, cap_start=True, cap_end=True)
        p.jitter(0.008)
        cx = (xa + xb) / 2
        tube(mb, [(cx, y0 + d * 0.6, h + wall_up), (cx, y1, rise + wall_up)],
             rect_section(wall_w + 0.08, 0.12, -0.02), coping)
        bx(mb, cx - wall_w / 2 - 0.05, cx + wall_w / 2 + 0.05, y0 - 0.1, y0 + d * 0.65, -0.02, h + wall_up + 0.12,
           coping, drop=('-z',))
    return inner


def build_stairs_stone(seed):
    mb = L.MeshBuilder("stairs_stone", seed)
    rng = random.Random(seed * 29 + 3)
    stone_stairs(mb, 4.0, 8, 3.2, 1.6, 0.3, 0.3, rng)
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


def build_stairs_stone_large(seed):
    mb = L.MeshBuilder("stairs_stone_large", seed)
    rng = random.Random(seed * 29 + 4)
    stone_stairs(mb, 9.0, 16, 8.0, 4.0, 0.5, 0.35, rng, tread=("stone_light", "stone", "stone_light", "stone_warm"))
    # lantern bases on the side walls (bottom + top of each wall)
    for s in (-1, 1):
        x = s * 4.25
        for (y, z) in ((-3.75, 0.25 + 0.35 + 0.12), (3.7, 4.0 + 0.35 + 0.12)):
            bx(mb, x - 0.38, x + 0.38, y - 0.38, y + 0.38, z - 0.15, z + 0.12, "stone_dark", drop=('-z',))
            mb.prism((x, y, z + 0.12), 0.24, 0.35, 6, "stone", radius_top=0.2, base=False)
            bx(mb, x - 0.3, x + 0.3, y - 0.3, y + 0.3, z + 0.47, z + 0.56, "stone_light", drop=('-z',))
    mb.collider_mesh()
    mb.tag("walkable")
    return mb.finish()


# ============================================================== 25/26. fences
def build_fence_wood(seed):
    mb = L.MeshBuilder("fence_wood", seed)
    rng = random.Random(seed * 37 + 1)
    HL = 1.25
    for x in (-HL, HL):
        bx(mb, x - 0.07, x + 0.07, -0.07, 0.07, -0.02, 1.0, "wood", drop=('-z',))
        mb.cone((x, 0, 1.0), 0.099, 0.12, 4, "wood_light", rot=(0, 0, 45))
    for z, c in ((0.42, "wood_light"), (0.84, "wood")):
        p = rbox(mb, (0, 0.0, z), (2 * HL, 0.05, 0.12), c, ry=rng.uniform(-1.2, 1.2))
        p.jitter(0.006)
        for x in (-HL, HL):
            bx(mb, x - 0.085, x + 0.085, -0.085, 0.085, z - 0.045, z + 0.045, "rope")
    # a leaning middle stake for a hand-made look
    rbox(mb, (0.15, 0.05, 0.5), (0.08, 0.06, 1.0), "wood_grey", ry=6)
    mb.collider_box((2.5, 0.2, 1.1), (0, 0, 0.55))
    return mb.finish()


def build_fence_bamboo(seed):
    mb = L.MeshBuilder("fence_bamboo", seed)
    rng = random.Random(seed * 43 + 2)
    HL = 1.25
    for x in (-HL, HL):
        p = mb.prism((x, 0, -0.02), 0.06, 1.37, 6, "bamboo_dry", base=False)
        p.color_faces(lambda f: "bamboo_light" if f.normal.z > 0.9 else None)
        mb.prism((x, 0, 0.62), 0.067, 0.04, 6, "bamboo_dark", cap=False)
    for z in (0.32, 0.72, 1.1):
        mb.prism((-HL, 0.0, z), 0.026, 2 * HL, 5, "bamboo_dry", rot=(0, 90, 0), cap=False)
    for i, x in enumerate(frange(-1.0, 1.0, 8)):
        y = 0.048 if i % 2 else -0.048
        top = 1.28 + rng.uniform(-0.02, 0.02)
        mb.prism((x, y, -0.02), 0.023, top + 0.02, 5, rng.choice(("bamboo_dry", "bamboo_dry", "bamboo_light")),
                 base=False)
        bx(mb, x - 0.035, x + 0.035, -0.035, 0.035, 1.07, 1.13, "cloth_black")
    mb.collider_box((2.5, 0.2, 1.3), (0, 0, 0.65))
    return mb.finish()


# ============================================================== 27. storehouse_kura
def diag_lines(fac, u0, u1, v0, v1, spacing, w=0.045, out=0.02, color="plaster"):
    """White namako-wall diagonal lattice clipped to the rectangle (on a Facade)."""
    for sgn in (1, -1):
        c = (u0 - v1) if sgn > 0 else (u0 + v0)
        cmax = (u1 - v0) if sgn > 0 else (u1 + v1)
        c += spacing / 2
        while c < cmax:
            pts = []
            for v in (v0, v1):
                u = c + v if sgn > 0 else c - v
                if u0 <= u <= u1:
                    pts.append((u, v))
            for u in (u0, u1):
                v = u - c if sgn > 0 else c - u
                if v0 < v < v1:
                    pts.append((u, v))
            if len(pts) >= 2:
                (ua, va), (ub, vb) = pts[0], pts[1]
                if abs(ua - ub) > 0.05:
                    fac.mb.plank_line(fac.p(ua, va, out / 2), fac.p(ub, vb, out / 2), out + 0.02, w, color)
            c += spacing


def build_storehouse_kura(seed):
    mb = L.MeshBuilder("storehouse_kura", seed)
    H = 1.7
    bx(mb, -H - 0.15, H + 0.15, -H - 0.15, H + 0.15, -0.02, 0.38, "stone", drop=('-z',))
    bx(mb, -H - 0.18, H + 0.18, -H - 0.18, H + 0.18, 0.34, 0.46, "stone_dark", drop=('-z',))
    bx(mb, -H, H, -H, H, 0.45, 3.55, "plaster", drop=('-z', '+z'))
    # black namako band with white diagonal lattice
    bx(mb, -H - 0.04, H + 0.04, -H - 0.04, H + 0.04, 0.45, 1.45, "tile_dark", drop=('-z',))
    bx(mb, -H - 0.07, H + 0.07, -H - 0.07, H + 0.07, 1.42, 1.52, "plaster")
    for (axis, plane, sign) in (('x', -H - 0.04, -1), ('x', H + 0.04, 1), ('y', -H - 0.04, -1), ('y', H + 0.04, 1)):
        fac = Facade(mb, axis, plane, sign)
        if axis == 'x' and sign < 0:
            diag_lines(fac, -H, -0.85, 0.5, 1.4, 0.5)
            diag_lines(fac, 0.85, H, 0.5, 1.4, 0.5)
        else:
            diag_lines(fac, -H, H, 0.5, 1.4, 0.5)
    # dark frieze under the floating roof
    bx(mb, -H - 0.06, H + 0.06, -H - 0.06, H + 0.06, 3.4, 3.78, "wood_black")
    # iron double door in a stepped plaster frame
    front = Facade(mb, 'x', -H, -1)
    front.box(-0.95, 0.95, 0.46, 2.75, -0.02, 0.12, "plaster_shade")
    front.box(-0.8, 0.8, 0.46, 2.6, -0.02, 0.2, "plaster")
    front.box(-0.62, 0.62, 0.46, 2.42, -0.02, 0.24, "iron")
    front.box(-0.02, 0.02, 0.5, 2.38, -0.02, 0.27, "black")
    for v in (0.85, 1.45, 2.05):
        front.box(-0.6, 0.6, v - 0.05, v + 0.05, 0.2, 0.27, "iron_light")
    front.box(-0.12, 0.12, 1.15, 1.35, 0.2, 0.3, "gold_dark")
    stone_slab(mb, 0.0, -H - 0.55, 0.28, 0.7, 0.32, 0.3, "stone_light", sides=6)
    # small high windows with iron shutters on the sides + back
    for (axis, plane, sign) in (('y', -H, -1), ('y', H, 1), ('x', H, 1)):
        fac = Facade(mb, axis, plane, sign)
        fac.box(-0.38, 0.38, 2.55, 3.15, -0.02, 0.1, "plaster_shade")
        fac.box(-0.26, 0.26, 2.65, 3.05, -0.02, 0.12, "black")
        fac.box(0.27, 0.62, 2.62, 3.08, 0.12, 0.18, "iron")
    # gable walls with the clan crest
    for x in (-H + 0.05, H - 0.05):
        gable_wall(mb, x, -H, H, 3.5, 4.55, 0.12, "plaster")
        sx = -1 if x < 0 else 1
        m = mb.prism((0, 0, 0), 0.24, 0.06, 10, "black", rot=(0, 90 * sx, 0))
        m.transform(loc=(x + sx * 0.05, 0, 4.0))
        m2 = mb.prism((0, 0, 0), 0.15, 0.08, 10, "plaster", rot=(0, 90 * sx, 0))
        m2.transform(loc=(x + sx * 0.05, 0, 4.0))
    # thick tiled gable roof
    roof = ProfileRoof.gable(-2.12, 2.12, 2.05, 3.82, 0.95, 0.24, curve=0.2, n=2)
    roof.build(mb, "tile_dark", "wood_black", "wood_black", end="tile_dark")
    nn = len(roof.prof)
    roof.ribs(mb, "tile_blue", spacing=0.46, i0=0, i1=nn // 2, inset=0.25)
    roof.ribs(mb, "tile_blue", spacing=0.46, i0=nn - 1, i1=nn // 2, inset=0.25)
    roof.verges(mb, "tile_dark", w=0.22, h=0.18, inset=0.1)
    top = roof.ridge(mb, "tile_dark", w=0.34, h=0.36, ext=0.04, band="plaster")
    for x in (-2.2, 2.2):
        bx(mb, x - 0.12, x + 0.12, -0.3, 0.3, top - 0.45, top + 0.12, "tile_dark")
    mb.collider_box((3.7, 3.7, 4.9), (0, 0, 2.45))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 28. pavilion_azumaya
def build_pavilion_azumaya(seed):
    mb = L.MeshBuilder("pavilion_azumaya", seed)
    P = 1.3
    bx(mb, -1.65, 1.65, -1.65, 1.65, -0.02, 0.16, "stone_light", drop=('-z',))
    bx(mb, -1.72, 1.72, -1.72, 1.72, -0.02, 0.08, "stone", drop=('-z',))
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.prism((sx * P, sy * P, 0.14), 0.11, 2.36, 6, "wood_dark", base=False)
            mb.prism((sx * P, sy * P, 0.12), 0.16, 0.12, 6, "stone_dark")
    # beams + decorative brackets
    for s in (-1, 1):
        bx(mb, -P - 0.25, P + 0.25, s * P - 0.08, s * P + 0.08, 2.3, 2.5, "wood_dark")
        bx(mb, s * P - 0.08, s * P + 0.08, -P - 0.25, P + 0.25, 2.31, 2.49, "wood_dark")
        bx(mb, -P + 0.1, P - 0.1, s * P - 0.05, s * P + 0.05, 2.05, 2.12, "wood")
    # benches (L-shaped) + small table
    for (x0, x1, y0, y1) in ((-1.15, 1.15, 0.8, 1.2), (0.8, 1.2, -1.15, 0.75)):
        bx(mb, x0, x1, y0, y1, 0.42, 0.5, "wood_light")
        for (xx, yy) in ((x0 + 0.12, y0 + 0.12), (x1 - 0.12, y1 - 0.12)):
            bx(mb, xx - 0.06, xx + 0.06, yy - 0.06, yy + 0.06, 0.14, 0.43, "wood_dark", drop=('-z',))
    # thatched pyramidal roof (hogyo) with a clay finial
    roof = Roof(W=2.05, D=2.05, ze=2.82, H=1.05, xg=0.0, curve=-0.05, lift=0.08, steps=[(0.55, 0.14)], nlev=2,
                frL=[0.0, 0.25, 0.5, 0.75], frS=[0.0, 0.25, 0.5, 0.75])
    rp = roof.build(mb, "thatch", "thatch_dark", "thatch_dark", thick=0.4, bevel=0.06, nose=[(-0.04, -0.18)],
                    step_nose=0.04, top2="thatch_light")
    rp.jitter(0.03, axes=(1, 1, 0.5))
    zr = roof.zr()
    mb.prism((0, 0, zr - 0.3), 0.28, 0.38, 6, "thatch_dark", radius_top=0.2)
    mb.prism((0, 0, zr + 0.05), 0.2, 0.12, 6, "clay_dark")
    mb.prism((0, 0, zr + 0.17), 0.12, 0.16, 6, "clay", radius_top=0.05)
    # hanging lantern
    hanging_lantern(mb, 0.0, 0.0, 2.45, h=0.42, r=0.17, cord=0.22)
    mb.collider_mesh()
    mb.tag("occluder", "light_warm")
    mb.set("light_offset", [0.0, 0.0, 2.0])
    return mb.finish()


# ============================================================== 29. pagoda_small
def build_pagoda_small(seed):
    mb = L.MeshBuilder("pagoda_small", seed)
    bx(mb, -1.5, 1.5, -1.5, 1.5, -0.02, 0.42, "stone", drop=('-z',))
    bx(mb, -1.56, 1.56, -1.56, 1.56, 0.38, 0.5, "stone_dark", drop=('-z',))
    stairs_block(mb, -0.45, 0.45, -1.85, -1.5, 0.0, 0.5, 2, color="stone_light")
    tiers = [  # (body half, z0, z1, roof W, ze, H, d_top)
        (0.95, 0.5, 2.15, 1.62, 2.45, 1.0, 0.85),
        (0.8, None, None, 1.45, None, 0.92, 0.8),
        (0.66, None, None, 1.3, None, 1.05, None),
    ]
    z = 0.5
    zr = 0
    for i, (bh, _, _, W, _, H, dt) in enumerate(tiers):
        z0 = z
        z1 = z0 + (1.65 if i == 0 else 0.95)
        fr, bk, lf, rt = timber_box(mb, -bh, bh, -bh, bh, z0, z1, post=0.16, spacing=bh, wall_col="wood_dark",
                                    post_col="wood_red", beam_col="wood_red_dark", sill_h=0.1, beam_h=0.14)
        if i == 0:
            fr.shoji(-0.5, 0.5, z0 + 0.1, z1 - 0.25, panels=2, cols=1, rows=2, frame="wood_red_dark",
                     kumiko="wood_dark", glow="glow_window")
            bk.shoji(-0.5, 0.5, z0 + 0.1, z1 - 0.25, panels=2, cols=1, rows=2, frame="wood_red_dark",
                     kumiko="wood_dark", glow="glow_window")
        else:
            # little balcony rail
            for s in (-1, 1):
                bx(mb, -bh - 0.14, bh + 0.14, s * (bh + 0.12) - 0.035, s * (bh + 0.12) + 0.035, z0 + 0.3, z0 + 0.37, "wood_red")
                bx(mb, s * (bh + 0.12) - 0.035, s * (bh + 0.12) + 0.035, -bh - 0.14, bh + 0.14, z0 + 0.3, z0 + 0.37, "wood_red")
        # bracket band
        bx(mb, -bh - 0.12, bh + 0.12, -bh - 0.12, bh + 0.12, z1 - 0.02, z1 + 0.16, "wood_dark")
        ze = z1 + 0.4
        roof = Roof(W=W, D=W, ze=ze, H=H, xg=0.0, curve=0.45, lift=0.32, lift_len=W * 0.75, flare=0.12, nlev=2,
                    frL=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9], frS=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9])
        roof.build(mb, "tile_dark", "wood_red_dark", "wood_dark", thick=0.24, d_top=dt, cap_col="tile_dark",
                   nose=[(-0.04, -0.1)])
        roof.ribs(mb, "tile_blue", spacing=0.42, segs=2, w=0.14, h=0.06)
        roof.ridges(mb, "tile_dark", main=False, hip_w=0.16, hip_h=0.14, end_up=0.14, end_ext=0.14)
        if dt is not None:
            z = roof.base(dt) - 0.05
        else:
            zr = roof.zr()
    # sorin spire
    mb.prism((0, 0, zr - 0.15), 0.3, 0.3, 6, "gold_dark", radius_top=0.22)
    mb.prism((0, 0, zr + 0.15), 0.07, 2.3, 6, "gold")
    for k in range(7):
        zz = zr + 0.45 + k * 0.22
        mb.prism((0, 0, zz), 0.17 - k * 0.008, 0.07, 8, "gold", cap=True)
    mb.prism((0, 0, zr + 2.05), 0.2, 0.18, 6, "gold_dark", radius_top=0.08)
    mb.ico((0, 0, zr + 2.42), 0.17, "gold", subdiv=1, scale=(1, 1, 1.25))
    mb.collider_box((3.0, 3.0, 10.0), (0, 0, 5.0))
    mb.tag("occluder")
    return mb.finish()


# ============================================================== 30. arch_bamboo_gate
def bamboo_pole(mb, x, y, z0, z1, r, color="bamboo", node="bamboo_dark", nodes=3, sides=6):
    mb.prism((x, y, z0), r, z1 - z0, sides, color, base=False) \
        .color_faces(lambda f: "bamboo_light" if f.normal.z > 0.9 else None)
    for k in range(nodes):
        z = z0 + (z1 - z0) * (k + 1) / (nodes + 1)
        mb.prism((x, y, z), r * 1.12, 0.05, sides, node, cap=False)


def build_arch_bamboo_gate(seed):
    mb = L.MeshBuilder("arch_bamboo_gate", seed)
    OW = 1.75
    for s in (-1, 1):
        for (dx, dy, r, h, c) in ((0.13, -0.12, 0.12, 2.95, "bamboo"), (0.13, 0.13, 0.11, 2.85, "bamboo_dark"),
                                  (0.36, 0.0, 0.1, 2.6, "bamboo_dry")):
            bamboo_pole(mb, s * (OW + dx), dy, -0.05, h, r, color=c, nodes=3)
        bx(mb, s * (OW + 0.02), s * (OW + 0.5), -0.25, 0.25, 0.95, 1.05, "cloth_black")
        bx(mb, s * (OW + 0.02), s * (OW + 0.5), -0.25, 0.25, 2.2, 2.3, "cloth_black")
        mb.prism((s * (OW + 0.2), 0, -0.02), 0.45, 0.14, 7, "stone", radius_top=0.38, base=False).jitter(0.03)
    # horizontal bamboo beams
    for (z, r, ext, c) in ((2.62, 0.11, 2.55, "bamboo"), (2.32, 0.085, 2.25, "bamboo_dry")):
        mb.prism((-ext, 0.0, z), r, 2 * ext, 6, c, rot=(0, 90, 0)) \
            .color_faces(lambda f: "bamboo_light" if abs(f.normal.x) > 0.9 else None)
    for s in (-1, 1):
        bx(mb, s * (OW + 0.13) - 0.14, s * (OW + 0.13) + 0.14, -0.18, 0.18, 2.52, 2.73, "cloth_black")
    # small thatched cap
    cap = ProfileRoof.gable(-2.6, 2.6, 0.62, 2.82, 0.32, 0.24, curve=-0.2, n=2)
    p = cap.build(mb, "thatch", "thatch_dark", "thatch_dark", end="thatch_dark")
    p.jitter(0.025, axes=(1, 1, 0.5))
    mb.prism((-2.65, 0.0, 3.12), 0.07, 5.3, 6, "bamboo_dark", rot=(0, 90, 0))
    for x in (-1.6, 0.0, 1.6):
        bx(mb, x - 0.05, x + 0.05, -0.5, 0.5, 2.98, 3.12, "cloth_black").transform(loc=(0, 0, 0))
    mb.collider_mesh()
    return mb.finish()


PROPS = {
    "house_kaito": build_house_kaito,
    "house_farmer_a": build_house_farmer_a,
    "house_farmer_b": build_house_farmer_b,
    "house_village_a": build_house_village_a,
    "house_village_b": build_house_village_b,
    "house_fisher": build_house_fisher,
    "dojo_main": build_dojo_main,
    "dojo_gate": build_dojo_gate,
    "dojo_gate_door": build_dojo_gate_door,
    "wall_segment": build_wall_segment,
    "wall_post": build_wall_post,
    "wall_gate": build_wall_gate,
    "wall_gate_door": build_wall_gate_door,
    "mountain_cabin": build_mountain_cabin,
    "lake_arena_platform": build_lake_arena_platform,
    "shrine_small": build_shrine_small,
    "torii_red": build_torii_red,
    "torii_stone": build_torii_stone,
    "bridge_arch": build_bridge_arch,
    "bridge_plank": build_bridge_plank,
    "dock_segment": build_dock_segment,
    "boardwalk_segment": build_boardwalk_segment,
    "stairs_stone": build_stairs_stone,
    "stairs_stone_large": build_stairs_stone_large,
    "fence_wood": build_fence_wood,
    "fence_bamboo": build_fence_bamboo,
    "storehouse_kura": build_storehouse_kura,
    "pavilion_azumaya": build_pavilion_azumaya,
    "pagoda_small": build_pagoda_small,
    "arch_bamboo_gate": build_arch_bamboo_gate,
}
