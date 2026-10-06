"""Nindō: la Cascada Kohan (landmark del jefe del lago).

kohan_falls_cliff   herradura de columnas hexagonales de basalto (42 m en el eje) con el umbral de cada
                    cortina, los contrafuertes que las separan, los tocones quebrados al pie, la meseta
                    escalonada con su río, los brazos que bajan en escalones al lago, el saliente del
                    santuario, las columnas caídas del pozo y la shimenawa que cruza la caída central.
                    El agua NO está en la malla: la genera Unity en runtime (FX/KohanFalls.cs) desde los
                    labios que este prop escribe en el manifest (clave "falls").
pine_falls_lip      pino negro torcido que crece del pilar de la shimenawa y se asoma sobre el agua.
falls_shrine_gate   portal de cuerda (dos postes, shimenawa y shide) del santuario del saliente.

El trazado (radios, rumbos, alturas, columnas) vive en Tools/Blender/world/falls_layout.py.
El acantilado se coloca con yaw 180 y su z = 0 es el nivel del lago: en su espacio x = este, y = norte.
"""
import math, os, random, sys
import bmesh
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "world"))
import nindo_lib as L
import falls_layout as FL
from props_nature import bark, bez, color_kinds, group, nrm, pad, shade_pad, tube
from props_misc import lathe, rock, shide, shimenawa

BASE_Z = -1.4             # las columnas arrancan bajo el agua (el lago es casi opaco en lo hondo)
# hacia la luna (Unity Euler 48,-38) en el espacio del prop: x = este, y = norte, z = arriba
MOON = Vector((0.412, -0.527, 0.743))
# tono de cada columna: (sombra, base, iluminada). Basalto azul pizarra, como las tejas oscuras del juego;
# una de cada cuatro tira a hierro para que la pared no sea un bloque de un solo color.
TONES = [("ink", "tile_dark", "tile_blue"), ("tile_dark", "tile_blue", "tile_light"),
         ("tile_dark", "tile_blue", "tile_light"), ("ink", "iron", "iron_light")]


def _hash01(*k):
    return (hash(k) % 10007) / 10007.0


def _lean_matrix(c, base_z):
    """Rotación de la columna alrededor de su pie (tocones y rocas inclinadas)."""
    if not c.lean:
        return None
    deg, toward = c.lean
    d = Vector(FL.polar(1.0, toward) + (0.0,))
    axis = Vector((0, 0, 1)).cross(d).normalized()          # inclinar hacia 'toward'
    pivot = Vector((c.e, c.n, base_z))
    return Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-pivot)


def _ring(c, z, scale=1.0, off=(0.0, 0.0), rot=0.0, zfn=None):
    pts = []
    for k in range(6):
        a = c.rot + rot + k * math.pi / 3
        x = c.e + off[0] + c.R * scale * math.cos(a)
        y = c.n + off[1] + c.R * scale * math.sin(a)
        pts.append((x, y, zfn(x, y) if zfn else z))
    return pts


def _hidden_sides(cols):
    """Caras laterales que tapa una vecina igual o más alta, en el panal de la meseta y de los brazos
    (columnas de un solo tramo, en grilla): no se ven nunca, así que no se generan (~570 tris menos)."""
    grid = [c for c in cols if c.kind in ("cell", "river", "step", "shelf")]
    cell = {}
    for c in grid:
        cell.setdefault((round(c.e / 2.0), round(c.n / 2.0)), []).append(c)

    def near(e, n):
        best, bd = None, 0.45
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for o in cell.get((round(e / 2.0) + i, round(n / 2.0) + j), ()):
                    d = math.hypot(o.e - e, o.n - n)
                    if d < bd:
                        best, bd = o, d
        return best
    out = {}
    for c in grid:
        hide = set()
        for k in range(6):
            a = c.rot + math.pi / 6 + k * math.pi / 3          # normal de la cara entre los vértices k y k+1
            o = near(c.e + 2.511 * math.cos(a), c.n + 2.511 * math.sin(a))
            if o is not None and o.top >= c.top:
                hide.add(k)
        out[id(c)] = hide
    return out


def _segment(mb, c, z0, z1, ch, off, rot, scale, cap, M=None, hide=()):
    """Prisma hexagonal de z0 a z1 con chaflán arriba (la arista clara que dibuja cada columna).
    cap: 'flat'; 'tilt' = la tapa sigue rim_h() en cada vértice (umbral bajo el agua, labio continuo);
    'broken' = tapa partida en un plano inclinado (columna quebrada)."""
    if cap == "tilt":
        zfn = lambda x, y: FL.rim_h(FL.bearing(x, y)) - 0.05
    elif cap == "broken":
        ang = c.rot + _hash01(round(c.e, 2), round(c.n, 2)) * math.tau
        slope = 0.25 + 0.35 * _hash01(round(c.n, 2), round(c.e, 2))
        dx, dy = math.cos(ang) * slope, math.sin(ang) * slope
        zfn = lambda x, y: z1 + (x - c.e) * dx + (y - c.n) * dy
    else:
        zfn = None
    bot = _ring(c, z0, scale, off, rot)
    if zfn:
        mid = [(x, y, zfn(x, y) - ch) for (x, y, _) in _ring(c, z1, scale, off, rot)]
        top = _ring(c, z1, scale * 0.86, off, rot, zfn)
    else:
        mid = _ring(c, z1 - ch, scale, off, rot)
        top = _ring(c, z1, scale * (1.0 - min(0.16, ch / max(c.R, 0.1))), off, rot)
    p = mb.loft([bot, mid, top], "tile_blue", cap_end=True)
    if hide:
        dead = []
        for k in hide:
            a, b = p.verts[k], p.verts[(k + 1) % 6]
            dead += [f for f in a.link_faces if b in f.verts]
        bmesh.ops.delete(mb.bm, geom=dead, context='FACES_ONLY')
    if M is not None:
        for v in p.verts:
            v.co = M @ v.co
    return p


def _color_column(part, c, tone, segtops, base_z):
    """Basalto oscuro con cantos claros (como el arte conceptual): el cuerpo de cada cara va en el tono base o
    sombra y solo las caras que dan de lleno a la luna y los chaflanes de arriba se aclaran; la luz de Unity
    modela el resto. Cerca de las cortinas la piedra está mojada: todo un escalón más oscuro."""
    dark, base, lit = tone
    b = FL.bearing(c.e, c.n)
    r = math.hypot(c.e, c.n)
    spray = FL.sheet_of(b, 7.0) is not None and r < FL.LIP_R + 6.5     # mojado por la llovizna de las cortinas
    lip = FL.rim_h(b)
    salt = int(_hash01(round(c.e, 1), round(c.n, 1)) * 1000)
    darker = {lit: base, base: dark, dark: "ink"}

    def fn(f):
        n = nrm(f)
        z = f.calc_center_median().z
        k = _hash01(round(z * 3), salt, round(n.x * 4), round(n.y * 4))
        wet = (spray and z < lip - 1.0) or (c.kind in ("stump", "rock", "buttress", "sill") and z < 5.0)
        if n.z > 0.7:                                     # tapas (la de arriba y las repisas de las juntas)
            if c.kind == "sill":
                return "tile_dark"                        # la cubre el agua
            if c.kind == "river":
                return "ink"                              # lecho del río (el agua es otra cara encima)
            if c.kind == "shelf":
                return "stone_moss" if k < 0.55 else ("moss" if k < 0.8 else "snow_shade")
            if c.kind == "rock":
                return "tile_blue" if k < 0.55 else "tile_light"
            if spray and z < lip + 0.5:
                return "ice" if k < 0.4 else ("snow_shade" if k < 0.7 else "tile_blue")
            if z > 24:
                return "snow" if k < 0.72 else "snow_shade"
            if z > 9:
                return "snow" if k < 0.35 else ("stone_moss" if k < 0.65 else "snow_shade")
            return "stone_moss" if k < 0.45 else ("moss" if k < 0.75 else "grass_teal")
        if n.z > 0.2:                                     # chaflán: el canto claro que dibuja la columna
            if z > 24 and not spray:
                return "snow_shade" if k < 0.5 else lit
            return lit if (n.dot(MOON) > 0.1 or k < 0.35) else base
        d = n.dot(MOON)
        if z < 0.9:
            return "ink" if k < 0.6 else dark             # línea de salpicadura: piedra mojada, casi negra
        if c.kind == "sill" and len(segtops) > 1 and z < segtops[-2] - 0.05:
            return "ink" if k < 0.6 else dark             # el hueco detrás del agua
        if d > 0.5:
            col = lit if k < 0.55 else base
        elif d > 0.05:
            col = base if k < 0.75 else dark
        else:
            col = dark if k < 0.8 else "ink"
        return darker.get(col, col) if wet else col
    part.color_faces(fn)


def _column(mb, c, rng, hide=()):
    """Arma una columna con sus juntas: cada tramo un poco corrido y girado (la junta se lee como una
    línea de luz). Los umbrales retroceden debajo de la repisa del borde (el hueco detrás del agua)."""
    base_z = BASE_Z if c.base is None else c.base
    bounds = [base_z] + [s for s in c.segs if base_z + 1.0 < s < c.top - 0.8] + [c.top]
    parts = []
    radial = Vector((c.e, c.n, 0.0)).normalized() if (c.e or c.n) else Vector((0, 1, 0))
    M = _lean_matrix(c, base_z)
    for i in range(len(bounds) - 1):
        z0, z1 = bounds[i], bounds[i + 1]
        last = i == len(bounds) - 2
        off = (rng.uniform(-0.07, 0.07), rng.uniform(-0.07, 0.07))
        rot = math.radians(rng.uniform(-4, 4)) if c.kind != "sill" else 0.0
        scale = rng.uniform(0.95, 1.0)
        if c.recess and not last:
            off = (off[0] + radial.x * c.recess, off[1] + radial.y * c.recess)
            scale *= 0.92
        ch = (0.32 if last else 0.12) * (1.0 if c.R > 1.0 else 0.7)
        cap = "flat"
        if last and c.tilt:
            cap = "tilt"
        elif last and c.kind in ("stump", "rock"):
            cap = "broken"
        parts.append(_segment(mb, c, z0, z1, ch, off, rot, scale, cap, M, hide if len(bounds) == 2 else ()))
    _color_column(group(mb, *parts), c, TONES[rng.randrange(len(TONES))], bounds[1:], base_z)
    return parts


def _icicles(mb, rng, c, z):
    """Carámbanos bajo una repisa cerca del agua (la llovizna se congela)."""
    for k in range(rng.randint(3, 5)):
        a = c.rot + rng.uniform(0, math.tau)
        rr = c.R * rng.uniform(0.75, 0.98)
        x, y = c.e + rr * math.cos(a), c.n + rr * math.sin(a)
        length = rng.uniform(0.7, 1.8)
        mb.cone((x, y, z), rng.uniform(0.09, 0.15), length, 3, "ice", rot=(180, 0, rng.uniform(0, 120)))


def _shimenawa(mb, rng, cols):
    """Cuerda sagrada gruesa cruzando la caída central, con shide de papel y flecos de paja. Se ve en las
    tomas de la presentación y del cambio de fase (desde el juego queda fuera de cuadro)."""
    b0, b1, r = FL.ROPE
    tops = [c.top for c in cols if c.kind == "buttress" and min(abs(FL.bearing(c.e, c.n) - b0), abs(FL.bearing(c.e, c.n) - b1)) < 6]
    za = min(tops) - 0.7
    mid_min = FL.rim_h(0.0) + FL.WATER_LIFT + 0.9
    sag = max(0.3, min(1.6, za - mid_min))
    pts = []
    n = 14
    for i in range(n + 1):
        t = i / n
        b = b0 + (b1 - b0) * t
        e, nn = FL.polar(r, b)
        pts.append(Vector((e, nn, za - sag * 4 * t * (1 - t))))
    tw = tube(mb, pts, [0.3] * len(pts), 7, "rope", rng, jitter=0.03)
    # trenzado: facetas alternadas de paja clara (como la shimenawa de las barreras)
    tw.color_faces(lambda f: "straw" if _hash01(round(f.calc_center_median().x * 2), round(f.calc_center_median().z * 3)) < 0.4 else None)
    for i in (2, 4, 7, 10, 12):
        p = pts[i]
        out = -Vector((p.x, p.y, 0)).normalized() * 0.32          # del lado de la arena
        tang = (pts[i + 1] - pts[i - 1]).normalized()
        yaw = math.degrees(math.atan2(tang.y, tang.x))
        w, h = 0.36, 0.42
        for s in range(3):
            dx = (w * 0.35) * (1 if s % 2 else -1)
            cx = p + out + tang * dx + Vector((0, 0, -0.32 - h * (s + 0.5)))
            mb.box(tuple(cx), (w, 0.06, h), "paper", rot=(0, 0, yaw))
    for i in (1, 3, 5, 6, 8, 9, 11, 13):
        p = pts[i]
        mb.cone((p.x, p.y, p.z - 0.22), 0.12, 0.7, 3, "straw", rot=(180, 0, _hash01(i) * 120))


def _river(mb, cols):
    """Agua quieta del río sobre la meseta (solo se ve desde las tomas altas): tapas de agua."""
    for c in cols:
        if c.kind != "river":
            continue
        pts = _ring(c, c.top + 0.37, 1.06)
        # hexágono cerrado y chato (una cara suelta toma cualquier normal al recalcularlas)
        mb.loft([_ring(c, c.top + 0.2, 1.06), pts], "water_deep", cap_end=True, slot=L.SLOT_WATER)


def build_kohan_falls_cliff(seed):
    rng = random.Random(seed + 404)
    mb = L.MeshBuilder("kohan_falls_cliff", seed)
    cols = FL.columns()
    hidden = _hidden_sides(cols)
    for c in cols:
        _column(mb, c, rng, hidden.get(id(c), ()))
        if c.kind == "buttress" and FL.sheet_of(FL.bearing(c.e, c.n), 6.0) is not None:
            for s in c.segs[-2:]:
                if s > 3.0:
                    _icicles(mb, rng, c, s - 0.02)
    _river(mb, cols)
    _shimenawa(mb, rng, cols)
    # sin collider: nadie llega (la arena es la plataforma) y una MeshCollider de 7k tris sumaría islas
    # sueltas al NavMesh sobre las columnas. Tampoco 'occluder': está al norte de todo, nunca tapa a Kaito,
    # y su caja (que envuelve la arena) lo apagaba al pisar la baranda norte.
    mb.collider_none()
    mb.tag("waterfall")
    mb.set("falls", FL.falls_meta())
    return mb.finish()


def build_pine_falls_lip(seed):
    """Pino negro torcido que crece del pilar y se asoma sobre el agua (frente = -Y). Base en z = 0."""
    rng = random.Random(seed + 77)
    mb = L.MeshBuilder("pine_falls_lip", seed)
    # tronco: sale casi horizontal hacia el frente y se levanta en la punta (pino de acantilado)
    pts = bez(Vector((0, 0.4, -0.3)), Vector((0, -1.0, 1.0)), Vector((0.5, -3.4, 1.0)), Vector((0.3, -4.6, 2.6)), 7)
    trunk = tube(mb, pts, [0.46, 0.4, 0.33, 0.28, 0.23, 0.18, 0.12], 6, "trunk", rng, jitter=0.07)
    bark(trunk, rng, snow="snow", snow_t=0.75)
    pads = []
    top = pts[-1]
    pads.append(pad(mb, (top.x, top.y, top.z + 0.15), 1.8, 1.4, 0.75, 10, rng))
    pads.append(pad(mb, (top.x + 0.3, top.y - 0.4, top.z + 0.7), 1.05, 0.9, 0.55, 8, rng))
    # dos ramas laterales con su copa plana (escalonada, como un bonsái grande)
    for side, t, length, rise in ((-1, 0.45, 2.0, 0.3), (1, 0.7, 1.7, 0.6)):
        st = pts[int(t * (len(pts) - 1))]
        d = Vector((side * 0.9, -0.4, 0)).normalized()
        sb = bez(st, st + d * length * 0.4 + Vector((0, 0, 0.3)), st + d * length * 0.8 + Vector((0, 0, rise)),
                 st + d * length + Vector((0, 0, rise + 0.1)), 4)
        br = tube(mb, sb, [0.18, 0.14, 0.1, 0.07], 5, "trunk", rng, jitter=0.05)
        bark(br, rng, snow="snow", snow_t=0.75)
        end = sb[-1]
        pads.append(pad(mb, (end.x, end.y, end.z + 0.1), 1.3, 1.05, 0.55, 9, rng))
    for p in pads:
        shade_pad(mb, p, rng, "leaf_pine_light", "leaf_pine", "leaf_pine_dark", p_light=0.6)

        # nieve sobre las caras de arriba de cada copa
        def snow(k, f):
            if k % 4 == 3 and _hash01(round(f.calc_center_median().x * 5), round(f.calc_center_median().y * 5)) < 0.75:
                return "snow" if _hash01(k) < 0.7 else "snow_shade"
            return None
        color_kinds(mb, p, list(range(len(p.flist))), snow)
    fol = group(mb, *pads)
    zmin = min(v.co.z for v in fol.verts)
    fol.wind_by_height(zmin - 1.5, zmin + 2.0, 0.6)
    mb.collider_none()
    return mb.finish()


def build_falls_shrine_gate(seed):
    """Portal de cuerda del santuario de la cascada: dos postes de madera vieja con la shimenawa, shide y
    flecos de paja, sobre dos piedras. Frente = -Y (se lo mira desde la arena)."""
    mb = L.MeshBuilder("falls_shrine_gate", seed)
    X, zr, sag = 1.3, 2.05, 0.32
    for sx in (-1, 1):
        rock(mb, (sx * X, 0, 0), 0.26, 0.16, "stone_dark", top_color="stone_moss", n=5)
        lathe(mb, [(0.11, 0.0), (0.1, 2.3), (0.0, 2.42)], 6, "wood_grey", ["wood_grey", "wood_dark"], loc=(sx * X, 0, 0))
        lathe(mb, [(0.125, zr - 0.08), (0.125, zr + 0.07)], 6, "straw", loc=(sx * X, 0, 0), cap_top=False)
    shimenawa(mb, (-X + 0.05, 0, zr), (X - 0.05, 0, zr), sag, 0.15, segs=10, sides=5)

    def rope_z(x):
        t = (x + X) / (2 * X)
        return zr - sag * 4 * t * (1 - t)
    for x in (-0.7, 0.0, 0.7):
        shide(mb, x, 0.0, rope_z(x) - 0.06, h=0.42, w=0.13)
    for x in (-0.36, 0.36):
        z = rope_z(x) - 0.06
        lathe(mb, [(0.0, z - 0.3), (0.07, z)], 4, "straw", loc=(x, 0, 0), cap_top=True, top_color="thatch")
    mb.collider_none()
    return mb.finish()


PROPS = {
    "kohan_falls_cliff": build_kohan_falls_cliff,
    "pine_falls_lip": build_pine_falls_lip,
    "falls_shrine_gate": build_falls_shrine_gate,
}
