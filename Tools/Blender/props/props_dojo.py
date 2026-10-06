"""Nindō - patio del dojo Kurokage: la arena de Kokuyō (jefe final).

Props de la pelea final (judge_final "arena_vfx"): el piso de losas claras donde se lee la sombra de
Kokuyō, los 8 braseros del anillo (sin fuego en la malla: el fuego, la luz y el color los pone
FX/Braziers.cs para poder encenderlos, volverlos violetas y apagarlos en el eclipse), el poste donde
atan al abuelo (las cuerdas violetas son de FX/ShadowRopes.cs, para que se disuelvan), los estandartes
del clan y los fragmentos de obsidiana de la grieta.

Todo según STYLE.md: origen al centro de la base, suelo en z = 0, frente hacia -Y, facetado con la
paleta. El piso se coloca con yaw 180: así su +X local es el este del juego y su +Y el norte (el dojo).
"""
import math
import random
from mathutils import Vector

import nindo_lib as L
import props_misc as PM

TAU = 2.0 * math.pi


# =====================================================================================
#  piso del patio (dojo_courtyard_floor)
# =====================================================================================
FLOOR_R = 18.5          # radio del círculo de losas (la barrera de la arena está en 18)
CURB_W = 0.45           # cordón de piedra alrededor del círculo
SOUTH_CUT = -16.0       # las losas empiezan detrás del portón (su cara de atrás está en y = -16.15)
APRON = (-9.0, 9.0, 12.0, 20.3)   # explanada hasta las escaleras del dojo (frente en y = 20.1)
TOP = 0.05              # altura de la cara de las losas (el terreno del patio está en 0 ± 2 cm)
CHAMFER = 0.045         # bisel de cada losa: la luna lo prende de un lado y lo apaga del otro
JOINT = 0.025           # media junta entre losas


def _clip(poly, inside, cut):
    """Sutherland-Hodgman contra un semiplano: inside(p) -> bool, cut(a, b) -> punto del borde."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ia, ib = inside(a), inside(b)
        if ia:
            out.append(a)
        if ia != ib:
            out.append(cut(a, b))
    return out


def _clip_line(poly, nx, ny, d):
    """Deja la parte con nx*x + ny*y >= d."""
    def f(p):
        return p[0] * nx + p[1] * ny - d

    def cut(a, b):
        t = f(a) / (f(a) - f(b))
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return _clip(poly, lambda p: f(p) >= 0, cut)


def _inset(poly, d):
    """Achica un polígono convexo (antihorario) moviendo cada lado d hacia adentro."""
    n = len(poly)
    lines = []
    for i in range(n):
        (ax, ay), (bx_, by) = poly[i], poly[(i + 1) % n]
        ex, ey = bx_ - ax, by - ay
        L_ = math.hypot(ex, ey)
        if L_ < 1e-6:
            continue
        nx, ny = -ey / L_, ex / L_        # normal hacia adentro (polígono antihorario)
        lines.append((ax + nx * d, ay + ny * d, ex, ey))
    out = []
    m = len(lines)
    for i in range(m):
        x1, y1, dx1, dy1 = lines[i - 1]
        x2, y2, dx2, dy2 = lines[i]
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 1e-9:
            out.append((x2, y2))
            continue
        t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / den
        out.append((x1 + dx1 * t, y1 + dy1 * t))
    return out


def _area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _slab(mb, poly, color, side, rng, tilt=0.012, crack=False, zj=0.008):
    """Losa biselada: cara superior inclinada apenas al azar (cada losa toma la luna distinto) y un bisel
    alrededor que baja hasta la junta. Sólido cerrado (con base) para que las normales salgan bien."""
    if len(poly) < 3 or _area(poly) < 0.05:
        return
    top = _inset(poly, CHAMFER)
    if len(top) < 3 or _area(top) < 0.02:
        top = _inset(poly, CHAMFER * 0.4)
        if len(top) < 3 or _area(top) < 0.01:
            return
    cx = sum(p[0] for p in top) / len(top)
    cy = sum(p[1] for p in top) / len(top)
    gx, gy = rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt)
    zc = TOP + rng.uniform(-zj, zj)

    def z_at(x, y):
        return zc + gx * (x - cx) + gy * (y - cy)
    bm = mb.bm
    zb = TOP - 0.035
    vb = [bm.verts.new((x, y, zb)) for x, y in poly]
    if crack and len(top) == 4:
        # losa partida en dos por la diagonal: cada mitad con su propia inclinación
        g2x, g2y = rng.uniform(-tilt * 2, tilt * 2), rng.uniform(-tilt * 2, tilt * 2)
        vt = [bm.verts.new((x, y, z_at(x, y))) for x, y in top]
        c0, c2 = vt[0], vt[2]
        extra = [bm.verts.new((top[k][0], top[k][1], zc + g2x * (top[k][0] - cx) + g2y * (top[k][1] - cy) - 0.012))
                 for k in (0, 2)]
        f1 = bm.faces.new((vt[0], vt[1], vt[2]))
        f2 = bm.faces.new((extra[0], extra[1], vt[3]))
        tops = [f1, f2]
        ring = vt
    else:
        ring = [bm.verts.new((x, y, z_at(x, y))) for x, y in top]
        tops = [bm.faces.new(ring)]
    n = len(poly)
    sides = []
    # el bisel une cada lado de la base con el lado correspondiente de la cara superior
    for i in range(n):
        j = (i + 1) % n
        a, b = vb[i], vb[j]
        c, d = ring[j % len(ring)], ring[i % len(ring)]
        try:
            sides.append(bm.faces.new((a, b, c, d)))
        except ValueError:
            pass
    try:
        bm.faces.new(list(reversed(vb)))
    except ValueError:
        pass
    verts = vb + ring + ([v for f in tops for v in f.verts])
    mb._new(list(set(verts)), side, None, None)
    PM.paint(mb, tops, color)


def _arc(r, a0, a1, n):
    return [(r * math.cos(a0 + (a1 - a0) * i / n), r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def build_dojo_courtyard_floor(seed):
    """Piso del patio: un círculo de losas claras en anillos (la arena) con un cordón oscuro, el medallón
    de la luna en el centro y una explanada rectangular hasta las escaleras del dojo, donde está el poste
    del abuelo. La sombra violeta de Kokuyō (FX/PlanarShadow) necesita un suelo pálido y parejo para
    leerse: las losas son stone_light con poca variación y las juntas apenas más oscuras."""
    mb = L.MeshBuilder("dojo_courtyard_floor", seed)
    rng = random.Random(seed * 7 + 3)

    def tone(x, y):
        # desgaste en manchas grandes de baja frecuencia (no un damero) y muy pocas losas sueltas distintas:
        # la sombra violeta de Kokuyō tiene que caer sobre un tono parejo
        n = 0.5 + 0.5 * math.sin(x * 0.19 + 1.3) * math.cos(y * 0.15 - 0.4) + rng.uniform(-0.06, 0.06)
        r = rng.random()
        if r < 0.02:
            return "stone_warm", "stone_warm"
        if r < 0.05:
            return "plaster_shade", "plaster_shade"
        if n < 0.1:
            return "stone", "stone"
        return "stone_light", "stone_light"

    # --- base (las juntas): un "tapete" de piedra oscura con faldón para que el borde nunca flote
    base_poly = []
    a_s = math.asin(SOUTH_CUT / FLOOR_R)                    # ángulo donde el corte sur toca el círculo
    xs = math.sqrt(FLOOR_R ** 2 - SOUTH_CUT ** 2)
    ya = math.sqrt(FLOOR_R ** 2 - APRON[1] ** 2)            # el círculo corta los lados de la explanada
    a_ne = math.atan2(ya, APRON[1])
    a_nw = math.pi - a_ne
    base_poly += _arc(FLOOR_R + CURB_W, a_s, a_ne, 24)
    base_poly += [(APRON[1], APRON[3]), (APRON[0], APRON[3])]
    base_poly += _arc(FLOOR_R + CURB_W, a_nw, math.pi - a_s + TAU * 0, 24)[0:]
    # cerrar por el corte sur (de oeste a este)
    base_poly = [(x, max(y, SOUTH_CUT)) for x, y in base_poly]
    zb = TOP - 0.03
    bm = mb.bm
    top_v = [bm.verts.new((x, y, zb)) for x, y in base_poly]
    low_v = [bm.verts.new((x, y, -0.4)) for x, y in base_poly]
    bm.faces.new(top_v)
    nb = len(base_poly)
    for i in range(nb):
        j = (i + 1) % nb
        bm.faces.new((low_v[i], low_v[j], top_v[j], top_v[i]))
    mb._new(top_v + low_v, "stone_dark", None, None)

    # --- medallón central: piedra oscura y una media luna dorada (el lugar del Tsukuyomi)
    MR = 3.1
    med = [(MR * math.cos(TAU * i / 20), MR * math.sin(TAU * i / 20)) for i in range(20)]
    _slab(mb, med, "stone_light", "stone", rng, tilt=0.0, zj=0.0)
    # media luna: círculo A (r 2.55) menos círculo B (r 2.2 corrido 0.95 hacia el dojo) -> cuernos al norte
    ra, rb, off = 2.55, 2.2, 0.95
    # intersecciones de los dos círculos
    yi = (ra * ra - rb * rb + off * off) / (2 * off)
    xi = math.sqrt(max(0.0, ra * ra - yi * yi))
    aa0 = math.atan2(yi, xi)                         # en A, del cuerno este bajando por el sur al oeste
    aa1 = math.pi - aa0
    ab0 = math.atan2(yi - off, xi)
    ab1 = math.pi - ab0
    N = 22
    outer = [(ra * math.cos(aa0 - (TAU - (aa1 - aa0)) * k / N), ra * math.sin(aa0 - (TAU - (aa1 - aa0)) * k / N))
             for k in range(N + 1)]
    inner = [(rb * math.cos(ab0 - (TAU - (ab1 - ab0)) * k / N), off + rb * math.sin(ab0 - (TAU - (ab1 - ab0)) * k / N))
             for k in range(N + 1)]
    # sólido cerrado de 3 cm (sobresale 2 cm del medallón): cuatro puntos por sección, de cuerno a cuerno
    z1, z0 = TOP + 0.02, TOP - 0.01
    secs = [[(ox, oy, z1), (ix, iy, z1), (ix, iy, z0), (ox, oy, z0)] for (ox, oy), (ix, iy) in zip(outer, inner)]
    PM.skin(mb, secs, "gold_dark", cap_top=True, cap_bottom=True)

    # --- anillos de losas (aparejo trabado: cada anillo corrido media losa)
    radii = [MR, 4.7, 6.25, 7.8, 9.35, 10.9, 12.45, 14.0, 15.55, 17.05, FLOOR_R]
    for k in range(len(radii) - 1):
        r0, r1 = radii[k] + JOINT, radii[k + 1] - JOINT
        rm = (r0 + r1) / 2
        n = max(8, round(TAU * rm / 1.6))
        ph = (k % 2) * 0.5 * TAU / n + rng.uniform(-0.05, 0.05)
        for i in range(n):
            a0 = ph + TAU * i / n + JOINT / rm
            a1 = ph + TAU * (i + 1) / n - JOINT / rm
            poly = [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)),
                    (r1 * math.cos(a1), r1 * math.sin(a1)), (r0 * math.cos(a1), r0 * math.sin(a1))]
            # antihorario visto desde arriba
            if _area(poly) < 0:
                poly.reverse()
            poly = _clip_line(poly, 0, 1, SOUTH_CUT + JOINT)
            if len(poly) < 3:
                continue
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            col, side = tone(cx, cy)
            # las del centro (donde más se pelea) están más gastadas: alguna partida
            _slab(mb, poly, col, side, rng, crack=(len(poly) == 4 and rng.random() < (0.12 if rm < 9 else 0.05)))

    # --- cordón de piedra (sólidos cerrados) alrededor del círculo, abierto en el corte sur
    a_from, a_to = a_s, math.pi - a_s
    span = (TAU - (a_to - a_from))
    nseg = round(span * (FLOOR_R + CURB_W / 2) / 1.5)
    for i in range(nseg):
        g = 0.025 / FLOOR_R
        b0 = a_to + span * i / nseg + g
        b1 = a_to + span * (i + 1) / nseg - g
        r0, r1 = FLOOR_R + 0.02, FLOOR_R + CURB_W
        poly = [(r0 * math.cos(b0), r0 * math.sin(b0)), (r1 * math.cos(b0), r1 * math.sin(b0)),
                (r1 * math.cos(b1), r1 * math.sin(b1)), (r0 * math.cos(b1), r0 * math.sin(b1))]
        if _area(poly) < 0:
            poly.reverse()
        h = 0.11 + rng.uniform(-0.015, 0.015)
        part = mb.extrude_polygon(poly, TOP - 0.04, h, "stone_dark", top_color="stone", base=True)
        part.jitter(0.008)

    # --- explanada norte (hasta el dojo): losas rectangulares de 1.6 x 1.2 en hileras trabadas
    x0, x1, y0, y1 = APRON
    W_, H_ = 1.6, 1.2
    row = 0
    y = y0
    while y < y1 - 0.05:
        yy1 = min(y + H_, y1)
        x = x0 - (W_ * 0.5 if row % 2 else 0.0)
        while x < x1 - 0.05:
            xx0, xx1 = max(x, x0), min(x + W_, x1)
            poly = [(xx0 + JOINT, y + JOINT), (xx1 - JOINT, y + JOINT), (xx1 - JOINT, yy1 - JOINT), (xx0 + JOINT, yy1 - JOINT)]
            cx, cy = (xx0 + xx1) / 2, (y + yy1) / 2
            # fuera del círculo y su cordón (localmente el círculo es su tangente)
            d = math.hypot(cx, cy)
            if d < FLOOR_R + CURB_W + 0.9:
                nx, ny = cx / d, cy / d
                poly = _clip_line(poly, nx, ny, FLOOR_R + CURB_W + JOINT)
            if len(poly) >= 3 and _area(poly) > 0.08:
                col, side = tone(cx, cy)
                _slab(mb, poly, col, side, rng)
            x += W_
        y += H_
        row += 1

    mb.collider_mesh()
    mb.tag("walkable")
    return _faces_up(mb.finish(), TOP - 0.025)


def _faces_up(obj, zmin):
    """finish() orienta las normales por isla con una heurística que con las mitades sueltas de las losas
    partidas puede fallar: todo lo que se ve del piso (por encima de la junta) tiene que mirar hacia arriba."""
    me = obj.data
    flipped = 0
    for p in me.polygons:
        if p.center.z > zmin and p.normal.z < -0.2:
            p.flip()
            flipped += 1
    me.update()
    if flipped:
        print(f"{obj.name}: {flipped} caras dadas vuelta corregidas")
    return obj


# =====================================================================================
#  brasero del anillo (brazier_kage)
# =====================================================================================
BRAZIER_FIRE_Z = 1.12    # = Braziers.FireHeight (FX/Braziers.cs): donde nace el fuego


def build_brazier_kage(seed):
    """Brasero pesado del patio: cuenco de hierro con banda y borde dorados sobre tres patas curvas y una
    base hexagonal oscura (contrasta con las losas claras). Sin fuego ni emisivos: las brasas encendidas,
    las llamas y la luz son de FX/Braziers.cs (se apagan en el eclipse y se vuelven violetas)."""
    mb = L.MeshBuilder("brazier_kage", seed)
    n = 6
    # base: hexágono de piedra con la cara de arriba más clara
    PM.lathe(mb, [(0.6, 0.0), (0.6, 0.1), (0.54, 0.15)], n, "stone_dark", ["stone_dark", "stone"],
             top_color="stone", phase=PM.front_phase(n))
    # patas: tres curvas tipo cabriolé, de sección cuadrada, con pie dorado
    for k in range(3):
        a = math.radians(90 + 120 * k)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(ca * 0.43, sa * 0.43, 0.14), (ca * 0.4, sa * 0.4, 0.3), (ca * 0.27, sa * 0.27, 0.55),
               (ca * 0.25, sa * 0.25, 0.68), (ca * 0.33, sa * 0.33, 0.84)]
        PM.tube(mb, pts, [0.05, 0.045, 0.04, 0.042, 0.05], 4, "iron", phase=a + math.pi / 4)
        PM.lathe(mb, [(0.075, 0.13), (0.085, 0.17), (0.05, 0.22)], 5, "gold_dark", loc=(ca * 0.43, sa * 0.43, 0),
                 cap_top=False, phase=a)
    # aro que une las patas a media altura
    ring = [(math.cos(math.radians(90 + 120 * k)) * 0.36, math.sin(math.radians(90 + 120 * k)) * 0.36, 0.36) for k in range(3)]
    for k in range(3):
        PM.bar(mb, ring[k], ring[(k + 1) % 3], 0.035, "iron")
    # cuenco: octógono de hierro, banda dorada, borde de hierro claro (lo toma la luna) con canto dorado
    nb = 8
    bowl = PM.lathe(mb, [(0.18, 0.78), (0.42, 0.86), (0.55, 0.96), (0.6, 1.02), (0.62, 1.1), (0.64, 1.16), (0.56, 1.17),
                         (0.5, 1.1)],
                    nb, "iron", ["iron", "iron", "gold_dark", "iron", "iron_light", "gold", "iron"],
                    cap_bottom=True, cap_top=False, bottom_color="iron")
    # remaches dorados sobre la banda
    for k in range(nb):
        a = PM.front_phase(nb) + TAU * (k + 0.5) / nb
        PM.spark(mb, (math.cos(a) * 0.585, math.sin(a) * 0.585, 0.99), 0.035, "gold")
    # asas laterales (anillos de hierro)
    for s in (-1, 1):
        pts = [(s * 0.62, -0.12, 1.06), (s * 0.74, -0.1, 1.0), (s * 0.77, 0.0, 0.94), (s * 0.74, 0.1, 1.0), (s * 0.62, 0.12, 1.06)]
        PM.tube(mb, pts, 0.025, 4, "iron_light", cap=True)
    # brasas apagadas: un montículo de carbón facetado y algunos trozos
    coal = PM.lathe(mb, [(0.52, 1.08), (0.4, 1.12), (0.18, 1.15), (0.0, 1.16)], 7, "wood_black",
                    ["wood_black", "black", "wood_black"], jitter=0.025, cap_top=False)
    for k in range(5):
        a = TAU * k / 5 + 0.4
        r = 0.18 + 0.12 * (k % 2)
        PM.rock(mb, (math.cos(a) * r, math.sin(a) * r, 1.1), 0.07, 0.06, "black", n=4, top_color="wood_black")
    mb.collider_capsule(0.55, 1.2)
    return mb.finish()


# =====================================================================================
#  poste del abuelo (binding_post)
# =====================================================================================
def build_binding_post(seed):
    """Poste de madera oscura donde Kokuyō ata al abuelo, en la explanada frente al dojo. Tiene base de piedra
    con zunchos de hierro, una argolla y un rollo de cuerda común al pie. Las vueltas de "cuerda de sombra"
    violeta NO están acá: las pone FX/ShadowRopes.cs alrededor del poste y del abuelo, y se disuelven cuando
    Kokuyō cae."""
    mb = L.MeshBuilder("binding_post", seed)
    # base de piedra
    PM.blk(mb, (0, 0, 0), (0.8, 0.8, 0.24), "stone", top="stone_light", jitter=0.012)
    PM.blk(mb, (0, 0, 0.22), (0.5, 0.5, 0.08), "stone_dark", top="stone")
    # poste: cuadrado con aristas biseladas (octógono irregular), de 2.8 m
    w, c = 0.15, 0.045
    sec = [(w, w - c), (w - c, w), (-w + c, w), (-w, w - c), (-w, -w + c), (-w + c, -w), (w - c, -w), (w, -w + c)]
    rings = []
    for z, s in ((0.28, 1.0), (1.5, 0.97), (2.75, 0.93)):
        rings.append([(x * s, y * s, z) for x, y in sec])
    post = PM.skin(mb, rings, "wood_dark", cap_top=True, cap_bottom=False,
                   face_color=lambda k, i: "wood" if i % 2 == 0 else None)
    post.jitter(0.006)
    # remate: sombrerete piramidal con canto de hierro
    PM.lathe(mb, [(0.2, 2.74), (0.21, 2.8), (0.12, 2.92), (0.0, 2.98)], 4, "wood_black",
             ["iron", "wood_black", "wood_black"], phase=math.pi / 4)
    PM.lathe(mb, [(0.035, 2.97), (0.0, 3.08)], 4, "iron_light", phase=0.0)
    # zunchos de hierro
    for z in (0.42, 2.48):
        PM.lathe(mb, [(0.17, z), (0.17, z + 0.07)], 8, "iron", cap_top=False, phase=math.pi / 8)
    # argolla al frente (-Y), a la altura del pecho del abuelo
    PM.bar(mb, (0, -0.15, 1.36), (0, -0.21, 1.36), 0.04, "iron")
    pts = [(0.0, -0.21, 1.36), (0.07, -0.24, 1.3), (0.0, -0.26, 1.22), (-0.07, -0.24, 1.3), (0.0, -0.21, 1.36)]
    PM.tube(mb, pts, 0.018, 4, "iron_light", cap=False)
    # rollo de cuerda común al pie (al costado: el abuelo está parado adelante)
    spiral = []
    for i in range(29):
        t = i / 28
        a = t * TAU * 2.4
        r = 0.08 + 0.2 * t
        spiral.append((0.55 + math.cos(a) * r, 0.18 + math.sin(a) * r, 0.04 + 0.03 * (1 - t)))
    PM.tube(mb, spiral, 0.03, 4, "rope", cap=True, cap_color="straw")
    PM.tube(mb, [(0.75, 0.2, 0.06), (0.62, -0.18, 0.04), (0.35, -0.42, 0.04)], 0.028, 4, "rope", cap=True, cap_color="straw")
    # piedras sueltas
    for x, y, r in ((-0.55, -0.35, 0.09), (-0.48, 0.42, 0.07), (0.4, -0.5, 0.06)):
        PM.rock(mb, (x, y, 0), r, r * 0.8, "stone_dark", n=5, top_color="stone")
    mb.collider_capsule(0.32, 2.9)
    return mb.finish()


# =====================================================================================
#  estandarte del clan (banner_kurokage)
# =====================================================================================
def _crescent_pts(cx, cz, r, n=10):
    """Media luna con los cuernos hacia arriba, como polígono (u, v) antihorario."""
    rb, off = r * 0.84, r * 0.42
    yi = (r * r - rb * rb + off * off) / (2 * off)
    xi = math.sqrt(max(0.0, r * r - yi * yi))
    a0 = math.atan2(yi, xi)
    b0 = math.atan2(yi - off, xi)
    outer = [(cx + r * math.cos(a0 - (TAU - (math.pi - 2 * a0)) * k / n), cz + r * math.sin(a0 - (TAU - (math.pi - 2 * a0)) * k / n))
             for k in range(n + 1)]
    inner = [(cx + rb * math.cos(math.pi - b0 + (TAU - (math.pi - 2 * b0)) * k / n), cz + off + rb * math.sin(math.pi - b0 + (TAU - (math.pi - 2 * b0)) * k / n))
             for k in range(n + 1)]
    pts = outer + inner[1:-1]
    if _area(pts) < 0:
        pts.reverse()
    return pts


def build_banner_kurokage(seed):
    """Nobori del clan Kurokage: tela violeta con la media luna negra (la del casco de Kokuyō) y un ribete
    de tinta abajo. Misma estructura que banner_nobori (la tela se mece con el material de follaje)."""
    mb = L.MeshBuilder("banner_kurokage", seed)
    PM.blk(mb, (0, 0, 0), (0.36, 0.36, 0.18), "stone_dark", top="stone").jitter(0.01)
    PM.lathe(mb, [(0.05, 0.12), (0.042, 3.96)], 6, "wood_black", cap_top=True)
    PM.lathe(mb, [(0.0, 3.96), (0.07, 4.04), (0.0, 4.2)], 4, "gold", cap_top=False)
    mb.box((0.36, 0, 3.82), (0.72, 0.045, 0.045), "wood_black")
    x0, x1, zt, zb, th = 0.07, 0.67, 3.78, 1.48, 0.012
    xs = [x0, (x0 + x1) / 2, x1]
    rows = [zt - (zt - zb) * (i / 6) for i in range(7)]
    rings = []
    for z in rows:
        rings.append([(xs[0], -th, z), (xs[1], -th, z), (xs[2], -th, z), (xs[2], th, z), (xs[1], th, z),
                      (xs[0], th, z)])
    cloth = PM.skin(mb, list(reversed(rings)), "cloth_purple", cap_top=True, cap_bottom=True, slot=L.SLOT_FOLIAGE)
    # ribete de tinta en el borde de abajo (las dos últimas hileras)
    for f in cloth.faces:
        if f.calc_center_median().z < zb + (zt - zb) / 6 * 0.95:
            PM.paint(mb, [f], "ink", L.SLOT_FOLIAGE)
    cx, cz, r = (x0 + x1) / 2, 3.08, 0.21
    pts = _crescent_pts(cx, cz, r)
    em_f = PM.slab(mb, pts, (0, -th + 0.002, 0), (1, 0, 0), (0, 0, 1), 0.006, "ink", back=False, slot=L.SLOT_FOLIAGE)
    em_b = PM.slab(mb, [(-x, z) for x, z in reversed(pts)], (0, th - 0.002, 0), (-1, 0, 0), (0, 0, 1), 0.006, "ink",
                   back=False, slot=L.SLOT_FOLIAGE)
    # balanceo: 0 en el mástil y el travesaño, 1 en la esquina libre de abajo
    cl = mb.col
    for part in (cloth, em_f, em_b):
        for f in part.faces:
            for l in f.loops:
                u = max(0.0, min(1.0, (l.vert.co.x - x0) / (x1 - x0)))
                v = max(0.0, min(1.0, (zt - l.vert.co.z) / (zt - zb)))
                w = (u ** 0.8) * (v ** 0.6)
                cc = l[cl]
                l[cl] = (w, cc[1], cc[2], 1.0)
    for z in (3.6, 2.85, 2.1):
        mb.box((0.05, 0, z), (0.07, 0.1, 0.07), "gold_dark")
    mb.collider_capsule(0.15, 4.0)
    return mb.finish()


# =====================================================================================
#  fragmentos de obsidiana (para la grieta de Kokuyō)
# =====================================================================================
def _shard(mb, x, y, h, r, lean, rot, rng):
    """Cristal de 5 caras, ahusado, con la punta violeta emisiva."""
    n = 5
    pts = []
    ca, sa = math.cos(rot), math.sin(rot)
    lx, ly = lean
    for z, s in ((0.0, 1.0), (h * 0.62, 0.78), (h * 0.86, 0.42)):
        ring = []
        for i in range(n):
            a = rot + TAU * i / n + rng.uniform(-0.15, 0.15)
            q = r * s * (1 + rng.uniform(-0.12, 0.12))
            t = z / h
            ring.append((x + math.cos(a) * q + lx * t * h, y + math.sin(a) * q + ly * t * h, z))
        pts.append(ring)
    pts.append([(x + lx * h, y + ly * h, h)])
    part = PM.skin(mb, pts, "ink", colors=["ink", "ink", "glow_purple"], cap_top=False,
                   face_color=lambda k, i: "tile_blue" if (k < 2 and (i + k) % 2 == 0) else None)
    return part


def _shard_prop(name, h, seed):
    mb = L.MeshBuilder(name, seed)
    rng = random.Random(seed * 13 + len(name))
    _shard(mb, 0.0, 0.0, h, h * 0.2, (0.06, -0.04), 0.3, rng)
    _shard(mb, h * 0.22, h * 0.1, h * 0.45, h * 0.11, (0.25, 0.1), 1.1, rng)
    if h > 0.8:
        _shard(mb, -h * 0.2, h * 0.08, h * 0.32, h * 0.09, (-0.3, 0.05), 2.0, rng)
    PM.rock(mb, (0, 0, 0), h * 0.28, h * 0.06, "stone_dark", n=5, top_color="stone")
    mb.collider_none()
    mb.tag("nonstatic")
    return mb.finish()


def build_obsidian_shard_s(seed):
    return _shard_prop("obsidian_shard_s", 0.6, seed)


def build_obsidian_shard_m(seed):
    return _shard_prop("obsidian_shard_m", 1.0, seed)


def build_obsidian_shard_l(seed):
    return _shard_prop("obsidian_shard_l", 1.4, seed)


PROPS = {
    "dojo_courtyard_floor": build_dojo_courtyard_floor,
    "brazier_kage": build_brazier_kage,
    "binding_post": build_binding_post,
    "banner_kurokage": build_banner_kurokage,
    "obsidian_shard_s": build_obsidian_shard_s,
    "obsidian_shard_m": build_obsidian_shard_m,
    "obsidian_shard_l": build_obsidian_shard_l,
}
