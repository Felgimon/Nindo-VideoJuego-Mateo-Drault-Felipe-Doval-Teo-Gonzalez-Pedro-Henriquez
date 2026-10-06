"""Malla y esqueleto del Gran Koi (Mizuchi), fase 1 'Tancho' y fase 2 'corrompido'.

Ejes de Blender: el koi mira a -Y (en Unity, +Z), su izquierda es +X, Z arriba, metros; z = 0 es la
cubierta de la plataforma. Todo sale de una superficie del cuerpo definida por un perfil (ancho, lomo y
vientre por estación Y) con secciones de superelipse: los ojos, el disco rojo, las branquias, la cuerda
y las raíces de las aletas se apoyan en esa misma superficie, y los huesos se calculan desde las piezas,
así que el esqueleto nunca queda corrido respecto de la malla.

Las escamas son las facetas: cada anillo del loft está girado medio paso respecto del anterior y los
triángulos se emparejan en rombos (uno de cada lado de una arista del anillo). Con sombreado plano cada
rombo se pliega por la mitad y brilla distinto que sus vecinos: el patrón de escamas sale de la luz, no
de una textura, y se agranda junto con el cuerpo (más chicas en la cola, como en un pez de verdad).
"""
import math, random
from mathutils import Vector, Matrix, Quaternion
from koi_common import KoiBuilder, Dir, smoothstep, lerp, catmull, spow, clamp, frame_from

Z0 = 1.62            # eje del cuerpo flotando (altura de la cabeza de Kaito)
SIDES = 16           # lados del loft

# perfil (y, medio ancho, lomo z, vientre z). Joroba detrás de la cabeza, vientre a 0.76 m de la cubierta.
PROFILE = [
    (-2.74, 0.30, 1.73, 1.21), (-2.62, 0.47, 1.91, 1.09), (-2.45, 0.61, 2.06, 0.99), (-2.22, 0.72, 2.21, 0.92),
    (-1.95, 0.81, 2.34, 0.87), (-1.65, 0.89, 2.46, 0.83), (-1.32, 0.95, 2.57, 0.79), (-0.95, 0.98, 2.66, 0.77),
    (-0.60, 0.98, 2.70, 0.76), (-0.25, 0.96, 2.69, 0.77), (0.10, 0.92, 2.63, 0.80), (0.45, 0.86, 2.54, 0.85),
    (0.80, 0.78, 2.44, 0.92), (1.15, 0.69, 2.32, 1.00), (1.50, 0.59, 2.20, 1.09), (1.85, 0.49, 2.09, 1.18),
    (2.18, 0.40, 2.00, 1.27), (2.48, 0.32, 1.94, 1.34), (2.74, 0.26, 1.90, 1.40), (2.92, 0.23, 1.90, 1.42),
    (3.06, 0.21, 1.96, 1.38),
]
E_TOP, E_BOT = 2 / 2.3, 2 / 2.75   # exponentes de la superelipse: lomo redondo, vientre más plano
HEAD_RINGS = [-2.74, -2.62, -2.47, -2.28, -2.06, -1.82, -1.57, -1.32]
Y_STAKE = -0.52      # la estaca entra en la joroba, detrás de la cabeza
Y_ROPE = -0.22       # la shimenawa ciñe el cuerpo justo detrás de la estaca
MOUTH = Vector((0.0, -2.79, 1.38))   # centro de la boca protráctil


def prof(y):
    w = catmull([(p[0], p[1]) for p in PROFILE], y)
    top = catmull([(p[0], p[2]) for p in PROFILE], y)
    bot = catmull([(p[0], p[3]) for p in PROFILE], y)
    return w, top, bot


def surf(y, th):
    """Punto de la piel en la estación y, ángulo th (0 = flanco izquierdo +X, pi/2 = lomo)."""
    w, top, bot = prof(y)
    zm = bot + 0.46 * (top - bot)
    c, s = math.cos(th), math.sin(th)
    if s >= 0:
        z = zm + (top - zm) * spow(s, E_TOP)
        x = w * spow(c, E_TOP)
    else:
        z = zm + (zm - bot) * spow(s, E_BOT)
        x = w * spow(c, E_BOT)
    return Vector((x, y, z))


def surf_n(y, th):
    e = 1e-3
    dy = surf(y + e, th) - surf(y - e, th)
    dt = surf(y, th + e) - surf(y, th - e)
    n = dt.cross(dy).normalized()
    c = surf(y, th)
    if n.dot(Vector((c.x, 0, c.z - 1.6))) < 0:
        n = -n
    return n


def top_th(x, y):
    """Ángulo th del lomo donde la piel pasa por la coordenada lateral x (para apoyar cosas desde arriba)."""
    w = prof(y)[0]
    c = clamp(x / w, -0.999, 0.999)
    cc = spow(c, 1 / E_TOP)
    return math.acos(clamp(cc, -1, 1))


def top_pt(x, y, lift=0.0):
    th = top_th(x, y)
    return surf(y, th) + surf_n(y, th) * lift


def body_rings():
    """Estaciones Y del loft: fijas en la cabeza; en el cuerpo el paso sigue al grosor para que los rombos
    tengan siempre la misma proporción (≈1.3 de largo por ancho)."""
    ys = list(HEAD_RINGS)
    y = HEAD_RINGS[-1]
    while True:
        w, top, bot = prof(y)
        r = 0.5 * (w + 0.5 * (top - bot))
        step = max(0.15, 0.62 * 2 * math.pi * r / SIDES)
        y += step
        if y > 2.86:
            break
        ys.append(round(y, 4))
    ys += [2.96, 3.06]
    return ys


# ------------------------------------------------------------------ pesos del cuerpo
SPINE = [("head", -2.0), ("spine_f", -0.9), ("body", -0.05), ("spine_b1", 0.62), ("spine_b2", 1.35),
         ("spine_b3", 2.0), ("spine_b4", 2.5), ("tail", 2.95)]


def spine_w(y):
    if y <= SPINE[0][1]:
        return {SPINE[0][0]: 1.0}
    for (a, ya), (b, yb) in zip(SPINE[:-1], SPINE[1:]):
        if ya <= y <= yb:
            t = smoothstep(ya, yb, y)
            return {a: 1 - t, b: t}
    return {SPINE[-1][0]: 1.0}


def mix(wa, wb, t):
    out = {}
    for k, v in wa.items():
        out[k] = out.get(k, 0) + v * (1 - t)
    for k, v in wb.items():
        out[k] = out.get(k, 0) + v * t
    return out


# ------------------------------------------------------------------ anclajes (piezas y huesos los comparten)
def _fin_frame(base, axis, normal):
    a = Vector(axis).normalized()
    n = (Vector(normal) - a * Vector(normal).dot(a)).normalized()
    across = n.cross(a).normalized()
    return a, across, n


def pec_def(side):
    """Aleta pectoral 'mariposa': 9 radios en abanico desde la base, en el flanco bajo detrás de la branquia."""
    sx = side
    th0, th1 = math.radians(-28), math.radians(-44)
    b0 = surf(-1.46, th0); b1 = surf(-0.84, th1)
    b0.x *= sx; b1.x *= sx
    base_c = (b0 + b1) / 2
    # hacia afuera, apenas atrás y caída ~17°: abierta como ala se lee ancha desde arriba y, de perfil,
    # el abanico se ve bajo el cuerpo (horizontal era una línea en la vista lateral)
    axis = Vector((0.92 * sx, 0.30, -0.30))
    normal = Vector((0.22 * sx, -0.05, 1.0))
    a, across, n = _fin_frame(base_c, axis, normal)
    if across.dot(Vector((0, 1, 0))) < 0:
        across = -across                               # across apunta hacia la cola
    # radios: ángulo respecto del eje (+ = hacia la cola) y largo; el borde de ataque es el más rígido
    rays = [(-30, 1.35), (-17, 1.55), (-5, 1.66), (7, 1.70), (19, 1.68), (31, 1.62), (43, 1.52), (55, 1.38), (67, 1.18)]
    out = []
    for i, (ang, ln) in enumerate(rays):
        u = i / (len(rays) - 1)
        root = b0.lerp(b1, u)
        r = math.radians(ang)
        d = (a * math.cos(r) + across * math.sin(r)).normalized()
        droop = -0.10 * (u - 0.3)                        # el borde de fuga cae un poco: se lee el volumen
        tip = root + d * ln + n * droop
        out.append((root, tip))
    return out, n, a


def pel_def(side):
    sx = side
    th = math.radians(-62)
    b0 = surf(0.32, th); b1 = surf(0.74, th - 0.08)
    b0.x *= sx; b1.x *= sx
    axis = Vector((0.55 * sx, 0.55, -0.62))
    normal = Vector((0.75 * sx, -0.1, 0.65))
    a, across, n = _fin_frame((b0 + b1) / 2, axis, normal)
    if across.dot(Vector((0, 1, 0))) < 0:
        across = -across
    rays = [(-20, 0.62), (-5, 0.74), (10, 0.78), (25, 0.7), (40, 0.55)]
    out = []
    for i, (ang, ln) in enumerate(rays):
        root = b0.lerp(b1, i / (len(rays) - 1))
        r = math.radians(ang)
        out.append((root, root + (a * math.cos(r) + across * math.sin(r)) * ln))
    return out, n, a


def anal_def():
    ys = [1.62, 1.78, 1.94, 2.10, 2.24]
    out = []
    for i, y in enumerate(ys):
        root = surf(y, -math.pi / 2) + Vector((0, 0, 0.03))
        ln = [0.42, 0.55, 0.58, 0.5, 0.36][i]
        d = Vector((0, 0.62, -0.78)).normalized()
        out.append((root, root + d * ln))
    return out, Vector((1, 0, 0)), Vector((0, 0.62, -0.78))


def dorsal_def(phase):
    ys = [-0.02, 0.24, 0.50, 0.76, 1.02, 1.28, 1.54, 1.80, 2.04, 2.26]
    hs = [0.80, 0.76, 0.70, 0.64, 0.58, 0.51, 0.45, 0.38, 0.31, 0.22]
    if phase == 2:   # crin erizada: más alta y despareja
        hs = [h * k for h, k in zip(hs, (1.18, 1.05, 1.2, 1.0, 1.16, 0.98, 1.12, 0.96, 1.1, 1.0))]
    out = []
    for y, h in zip(ys, hs):
        root = top_pt(0.0, y, -0.04)
        tip = root + Vector((0, 0.42 * h, h))
        out.append((root, tip))
    return out, Vector((1, 0, 0)), Vector((0, 0.4, 1))


TAIL_BASE = Vector((0.0, 3.0, 1.67))


def tail_def(side, phase):
    """Media cola 'abanico' (cola doble, tipo ryukin): un lóbulo en un plano inclinado 55° de la vertical.
    De perfil se ve horquillada (lóbulo de arriba y de abajo); desde arriba, ancha."""
    sx = side
    e = Vector((math.sin(math.radians(62)) * sx, 0.0, math.cos(math.radians(62))))
    back = Vector((0, 1, 0.04)).normalized()
    n = back.cross(e).normalized()
    if n.dot(Vector((sx, 0, 0))) < 0:
        n = -n
    rays = [(-58, 1.62), (-44, 1.55), (-29, 1.38), (-14, 1.22), (0, 1.14), (14, 1.24), (29, 1.42), (44, 1.62), (58, 1.75)]
    out = []
    for i, (ang, ln) in enumerate(rays):
        u = i / (len(rays) - 1)
        root = TAIL_BASE + e * lerp(-0.2, 0.24, u) + back * (-0.08 + 0.04 * abs(u - 0.5))
        r = math.radians(ang)
        d = (back * math.cos(r) + e * math.sin(r)).normalized()
        out.append((root, root + d * ln))
    return out, n, back


# ------------------------------------------------------------------ esqueleto
def bones():
    """Tabla (nombre, cabeza, cola, padre, z_hint). z_hint orienta el roll (eje local Z) del hueso: arriba
    para la columna, la normal de la aleta para las aletas (así escalar X local pliega el abanico)."""
    UP = Vector((0, 0, 1)); FWD = Vector((0, -1, 0))
    B = []

    def add(n, h, t, p, z=UP):
        B.append((n, Vector(h), Vector(t), p, Vector(z)))

    add("root", (0, 0, 0), (0, 0.6, 0), None)
    add("FacingProbe", (0, -3.0, Z0), (0, -3.3, Z0), "root")
    add("body", (0, -0.35, Z0), (0, 0.25, Z0), "root")
    add("spine_f", (0, -0.35, Z0), (0, -1.35, Z0), "body")
    add("head", (0, -1.35, Z0), (0, -2.55, 1.5), "spine_f")
    add("jaw", (0, -2.3, 1.34), (0, -2.86, 1.33), "head")
    # colmillos de marfil (fase 1) y bigotes de dragón (fase 2): cadenas separadas que salen de las
    # comisuras. Los bigotes flotan por encima de las pectorales, así que al rolar no tocan la cubierta.
    for s, sx in (("L", 1), ("R", -1)):
        pts = barbel_path(sx)
        add(f"barbel_{s}1", pts[0], pts[2], "jaw")
        add(f"barbel_{s}2", pts[2], pts[4], f"barbel_{s}1")
        wp = whisker_path(sx)
        add(f"whisker_{s}1", wp[0], wp[3], "jaw")
        add(f"whisker_{s}2", wp[3], wp[6], f"whisker_{s}1")
        add(f"whisker_{s}3", wp[6], wp[12], f"whisker_{s}2")
    for s, sx in (("L", 1), ("R", -1)):
        g0 = surf(-1.74, math.radians(8)); g1 = surf(-1.30, math.radians(4))
        g0.x *= sx; g1.x *= sx
        add(f"gill_{s}", g0, g1, "head", Vector((sx, 0, 0)))
    for s, sx in (("L", 1), ("R", -1)):
        hp = horn_path(sx)
        add(f"horn_{s}", hp[0], hp[-1], "head", FWD)
    gl = top_pt(0, -1.88)
    add("eye_glint", gl, gl + Vector((0, 0, 0.3)), "head", FWD)
    for s, sx in (("L", 1), ("R", -1)):
        rays, n, a = pec_def(sx)
        root = (rays[0][0] + rays[-1][0]) / 2
        mid = rays[4]
        add(f"pec_{s}1", root, mid[0].lerp(mid[1], 0.36), "spine_f", n)
        add(f"pec_{s}2", mid[0].lerp(mid[1], 0.36), mid[0].lerp(mid[1], 0.7), f"pec_{s}1", n)
        add(f"pec_{s}3", mid[0].lerp(mid[1], 0.7), mid[1], f"pec_{s}2", n)
    st = top_pt(0, Y_STAKE)
    add("seal", (0, Y_STAKE, st.z - 0.08), (0, Y_STAKE, st.z + 0.45), "body", FWD)
    for s, sx in (("L", 1), ("R", -1)):
        sh = shide_anchor(sx)
        add(f"shide_{s}", sh, sh + Vector((0, 0, -0.45)), "body", Vector((sx, 0, 0)))
    # cadena de atrás
    add("spine_b1", (0, 0.25, Z0), (0, 1.0, 1.63), "body")
    add("spine_b2", (0, 1.0, 1.63), (0, 1.7, 1.65), "spine_b1")
    add("spine_b3", (0, 1.7, 1.65), (0, 2.3, 1.67), "spine_b2")
    add("spine_b4", (0, 2.3, 1.67), (0, 2.75, 1.69), "spine_b3")
    add("tail", (0, 2.75, 1.69), (0, 3.1, 1.71), "spine_b4")
    dr, _, _ = dorsal_def(1)
    for i, (idx, par) in enumerate(((1, "body"), (3, "spine_b1"), (5, "spine_b2"), (7, "spine_b3"))):
        r0, r1 = dr[idx]
        add(f"dorsal_{i + 1}", r0 + Vector((0, 0, 0.04)), r0.lerp(r1, 0.85), par, FWD)
    for s, sx in (("L", 1), ("R", -1)):
        rays, n, a = pel_def(sx)
        root = (rays[0][0] + rays[-1][0]) / 2
        add(f"pel_{s}", root, rays[2][0].lerp(rays[2][1], 0.9), "spine_b1", n)
    ar, _, _ = anal_def()
    add("anal", ar[2][0], ar[2][0].lerp(ar[2][1], 0.9), "spine_b3", Vector((1, 0, 0)))
    for s, sx in (("L", 1), ("R", -1)):
        rays, n, back = tail_def(sx, 1)
        mid = rays[4]
        d = (mid[1] - mid[0]).normalized()
        add(f"fluke_{s}1", TAIL_BASE + Vector((0.06 * sx, 0, 0)), mid[0] + d * 0.62, "tail", n)
        add(f"fluke_{s}2", mid[0] + d * 0.62, mid[1], f"fluke_{s}1", n)
    return B


def bone_names():
    return [b[0] for b in bones()]


# ------------------------------------------------------------------ caminos de piezas finas
def barbel_path(sx):
    """Colmillo de marfil (fase 1): cae desde la comisura hacia adelante y se curva."""
    p = [Vector((0.22 * sx, -2.84, 1.44))]
    for d in ((0.07, -0.13, -0.14), (0.09, -0.1, -0.17), (0.08, -0.02, -0.18), (0.06, 0.07, -0.15)):
        p.append(p[-1] + Vector((d[0] * sx, d[1], d[2])))
    return p


def whisker_path(sx):
    """Bigote de dragón (fase 2, 3.2 m): se abre hacia adelante y afuera desde la comisura y vuelve
    flotando por encima de la pectoral hasta el costado de la cabeza. Desde arriba dibuja un gancho."""
    p = [Vector((0.2 * sx, -2.80, 1.44))]
    for d in ((0.25, -0.2, -0.12), (0.3, -0.05, -0.1), (0.3, 0.15, 0.0), (0.25, 0.32, 0.1), (0.15, 0.42, 0.14),
              (0.06, 0.45, 0.1), (-0.02, 0.42, 0.04), (-0.06, 0.38, 0.0), (-0.05, 0.36, -0.03), (0.0, 0.34, -0.04),
              (0.06, 0.3, -0.02), (0.1, 0.26, 0.02)):
        p.append(p[-1] + Vector((d[0] * sx, d[1], d[2])))
    return p


def short_barbel_path(sx):
    p0 = Vector((0.11 * sx, -2.87, 1.52))
    return [p0, p0 + Vector((0.05 * sx, -0.12, -0.07)), p0 + Vector((0.1 * sx, -0.2, -0.17))]


def horn_path(sx):
    p0 = top_pt(0.3 * sx, -1.62, -0.03)
    return [p0, p0 + Vector((0.07 * sx, 0.16, 0.30)), p0 + Vector((0.14 * sx, 0.42, 0.50)), p0 + Vector((0.16 * sx, 0.74, 0.58))]


def shide_anchor(sx):
    p = surf(Y_ROPE + 0.05, math.radians(-8))
    p.x *= sx
    return p + Vector((0.09 * sx, 0, 0))


# ------------------------------------------------------------------ construcción
class Koi:
    def __init__(self, phase, seed=11):
        self.phase = phase
        self.rng = random.Random(seed + phase)
        self.mb = KoiBuilder(f"Body_P{phase}", bone_names())

    # --- tubo afinado a lo largo de una polilínea (bigotes, cuernos, cuerda)
    def tube(self, pts, r0, r1, sides, color_fn, weight_fn, cap=True, closed=False, up=(0, 0, 1), twist=0.0):
        """'up' orienta las secciones; para caminos que pasan por la vertical (la cuerda que rodea el cuerpo)
        hay que darle un eje que nunca sea paralelo al camino, si no la sección se da vuelta a mitad."""
        mb = self.mb
        n = len(pts)
        rings = []
        for i, p in enumerate(pts):
            if closed:
                d = (pts[(i + 1) % n] - pts[i - 1]).normalized()
            else:
                d = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
            x, _, z = frame_from(d, Vector(up))
            t = i / (n - 1) if n > 1 else 0
            r = lerp(r0, r1, t)
            # 'twist' rota la sección a lo largo del camino: las caras quedan en hélice (cuerda torcida)
            a0 = 2 * math.pi * twist * i / sides
            ring = [mb.v(p + (x * math.cos(2 * math.pi * k / sides + a0) + z * math.sin(2 * math.pi * k / sides + a0)) * r,
                         weight_fn(i, t)) for k in range(sides)]
            rings.append(ring)
        segs = n if closed else n - 1
        for i in range(segs):
            A, Bv = rings[i], rings[(i + 1) % n]
            c = (pts[i] + pts[(i + 1) % n]) / 2
            for k in range(sides):
                k2 = (k + 1) % sides
                mb.face([A[k], A[k2], Bv[k2], Bv[k]], color_fn(i, k), outward=Dir(((A[k].co + Bv[k2].co) / 2 - c)))
        if cap and not closed:
            tip = mb.v(pts[-1] + (pts[-1] - pts[-2]).normalized() * r1 * 0.8, weight_fn(n - 1, 1.0))
            for k in range(sides):
                mb.face([rings[-1][k], rings[-1][(k + 1) % sides], tip], color_fn(n - 2, k), outward=Dir(pts[-1] - pts[-2]))
        return rings

    # --- abanico plisado de doble cara (todas las aletas)
    def fan(self, rays, normal, colors, weight_fn, rows=(0.0, 0.34, 0.68), pleat=0.05, notch=0.16,
            rim=None, torn=0.0, jag=0.0):
        """rays: [(raíz, punta)]. Membrana entre radios en filas 'rows' + el borde; cada radio se pliega
        ±pleat sobre la normal (acordeón) y la membrana entre dos puntas se retrae 'notch' (borde festoneado,
        las puntas de los radios sobresalen como en las aletas largas de los koi mariposa).
        La grilla se comparte entre caras (un vértice = un peso: sin grietas al deformar) y la cara de atrás
        usa una copia de la grilla, para que las dos caras no se fundan."""
        mb = self.mb
        normal = Vector(normal).normalized()
        nr = len(rays)
        ts = list(rows) + [1.0]
        lens = [1.0 + (self.rng.uniform(-jag, jag) if jag else 0.0) for _ in rays]
        G = []
        for i, (r0, r1) in enumerate(rays):
            sgn = 1 if i % 2 else -1
            col = []
            for t in ts:
                tt = t * lens[i]
                p = r0.lerp(r1, tt) + normal * (pleat * sgn * (0.2 + 0.8 * t))
                col.append(mb.v(p, weight_fn(p, tt, i)))
            G.append(col)
        Nv = []
        for i in range(nr - 1):
            tm = 0.5 * (lens[i] + lens[i + 1]) * (1.0 - notch)
            ra, rb = rays[i], rays[i + 1]
            pm = (ra[0].lerp(ra[1], tm) + rb[0].lerp(rb[1], tm)) / 2
            Nv.append(mb.v(pm, weight_fn(pm, tm, i)))
        Gb = [[mb.copy(v) for v in col] for col in G]
        Nb = [mb.copy(v) for v in Nv]
        for i in range(nr - 1):
            for j in range(len(rows)):
                last = j == len(rows) - 1
                c = colors(i, j, len(rows))
                if rim and last:
                    c = rim(i, c)
                if torn and j > 0 and self.rng.random() < (torn * 1.8 if last else torn * 0.5):
                    continue    # aleta rota (fase 2): sobre todo desgarros en el borde, algún agujero
                for g, nn, d in ((G, Nv, normal), (Gb, Nb, -normal)):
                    if last:
                        verts = [g[i][j], g[i + 1][j], g[i + 1][j + 1], nn[i], g[i][j + 1]]
                    else:
                        verts = [g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]]
                    mb.face(verts, c, outward=Dir(d))

    # --- loft del cuerpo con escamas en rombo
    def body(self):
        mb = self.mb
        ys = body_rings()
        self.ring_y = ys
        rings = []
        for r, y in enumerate(ys):
            off = 0.5 * (r % 2)
            ring = []
            for k in range(SIDES):
                th = 2 * math.pi * (k + off) / SIDES
                ring.append(mb.v(surf(y, th), spine_w(y)))
            rings.append(ring)
        self.rings = rings
        colors = self.scale_colors(ys)
        for r in range(len(ys) - 1):
            A, Bv = rings[r], rings[r + 1]
            for k in range(SIDES):
                k1 = (k + 1) % SIDES
                if r % 2 == 0:
                    t1 = ([A[k], A[k1], Bv[k]], (r, k))           # base en el anillo r
                    t2 = ([Bv[k], A[k1], Bv[k1]], (r + 1, k))     # base en el anillo r+1
                else:
                    t1 = ([A[k], A[k1], Bv[k1]], (r, k))
                    t2 = ([A[k], Bv[k1], Bv[k]], (r + 1, k))
                for verts, key in (t1, t2):
                    c = sum((v.co for v in verts), Vector()) / 3
                    mb.face(verts, colors(key), outward=Dir(Vector((c.x, 0, c.z - 1.62))))
        # tapa de la cola (queda dentro de la base del abanico)
        last = rings[-1]
        cap = mb.v(Vector((0, ys[-1] + 0.03, 1.67)), spine_w(ys[-1]))
        for k in range(SIDES):
            mb.face([last[k], last[(k + 1) % SIDES], cap], self.skin("tail"), outward=Dir((0, 1, 0)))
        self.mouth(rings[0])

    def skin(self, where):
        if self.phase == 1:
            return {"tail": "plaster", "face": "white", "lip": "sakura", "lip_in": "sakura_dark", "throat": "black"}[where]
        return {"tail": "ink", "face": "ink", "lip": "cloth_purple", "lip_in": "ink", "throat": "glow_purple"}[where]

    def scale_colors(self, ys):
        """Color de cada rombo (clave = arista del anillo). Fase 1: blanco nácar con hileras diagonales
        apenas cálidas, panza crema, el disco rojo es pieza aparte, pocas manchas de tinta (sumi) y ~3.5 %
        de escamas gin-rin que brillan con la luna. Fase 2: laca negra, panza piedra, reflejos violeta y
        venas que brillan desde la estaca."""
        rng = self.rng
        cache = {}
        # manchas de tinta (sumi): pocas y grandes, de borde irregular (el ruido por rombo las deshilacha)
        ink_seeds = [(-0.02, math.radians(60), 0.44), (1.0, math.radians(120), 0.38), (1.9, math.radians(72), 0.3),
                     (0.42, math.radians(14), 0.28)]
        veins = self.crack_paths() if self.phase == 2 else []

        def vein_d(y, th):
            best = 9.0
            for pts in veins:
                for (y0, t0, _), (y1, t1, _) in zip(pts[:-1], pts[1:]):
                    for u in (0, 0.25, 0.5, 0.75, 1):
                        yy, tt = lerp(y0, y1, u), lerp(t0, t1, u)
                        r = prof(yy)[0]
                        d = math.hypot(y - yy, (th - tt) * r)
                        best = min(best, d)
            return best

        def col(key):
            if key in cache:
                return cache[key]
            r, k = key
            y = ys[min(r, len(ys) - 1)]
            th = 2 * math.pi * (k + 0.5 + 0.5 * (r % 2)) / SIDES
            th = (th + math.pi) % (2 * math.pi) - math.pi
            up = math.sin(th)
            if self.phase == 1:
                if y < -1.32:                         # cabeza: piel lisa, sin escamas
                    c = "white" if up > -0.45 else "plaster"
                elif up < -0.62:
                    c = "plaster_shade"
                else:
                    c = "white" if (r + k) % 2 else "plaster"
                    wob = rng.uniform(0.7, 1.25)
                    for sy, st, sr in ink_seeds:
                        rr = prof(sy)[0]
                        if math.hypot(y - sy, (th - st) * rr) < sr * wob:
                            c = "ink"
                    if c != "ink" and up > 0.3 and -1.1 < y < 2.5 and rng.random() < 0.06:
                        c = "glow_moon"
            else:
                if up < -0.62:
                    c = "stone_dark"
                else:
                    c = "ink" if (r + k) % 2 else "cloth_black"
                    # la laca se tiñe de violeta alrededor de las grietas (el brillo es la cinta de cracks())
                    if y > -1.32 and (vein_d(y, th) < 0.2 or (up > 0.2 and rng.random() < 0.06)):
                        c = "cloth_purple"
            cache[key] = c
            return c
        return col

    # --- grietas de la maldición (fase 2): salen de la estaca, se ramifican y se afinan
    def crack_paths(self):
        if hasattr(self, "_cracks"):
            return self._cracks
        rng = random.Random(77)
        paths = []

        def walk(y, th, ang, steps, w0):
            pts = [(y, th, w0)]
            for s_ in range(steps):
                ang += rng.uniform(-28, 28)
                r = prof(y)[0]
                y += math.cos(math.radians(ang)) * 0.24
                th += math.sin(math.radians(ang)) * 0.24 / max(0.25, r)
                pts.append((y, th, w0 * (1 - (s_ + 1) / (steps + 1.5))))
            return pts
        for ang in (-160, -30, 28, 150, 95, -95):
            main = walk(Y_STAKE, math.pi / 2, ang, 9, 0.075)
            paths.append(main)
            for j in (3, 6):
                y, th, w = main[j]
                paths.append(walk(y, th, ang + rng.choice((-45, 45)), 3, w * 0.8))
        self._cracks = paths
        return paths

    def cracks(self):
        if self.phase != 2:
            return
        mb = self.mb
        for pts in self.crack_paths():
            ring = []
            for i, (y, th, w) in enumerate(pts):
                p = surf(y, th) + surf_n(y, th) * 0.018
                ring.append((p, surf_n(y, th), w * (1.25 if i % 2 else 0.8), y))
            for i in range(len(ring) - 1):
                (p0, n0, w0, y0), (p1, n1, w1, y1) = ring[i], ring[i + 1]
                t = (p1 - p0).normalized()
                s0 = n0.cross(t).normalized()
                s1 = n1.cross(t).normalized()
                q = [mb.v(p0 - s0 * w0, spine_w(y0)), mb.v(p0 + s0 * w0, spine_w(y0)),
                     mb.v(p1 + s1 * w1, spine_w(y1)), mb.v(p1 - s1 * w1, spine_w(y1))]
                mb.face(q, "glow_purple", outward=Dir(n0 + n1))

    # --- boca protráctil: labios, garganta y pared oscura (para que al abrir no se vea a través)
    def mouth(self, ring0):
        mb = self.mb
        n = SIDES
        c0 = MOUTH
        def ellipse(cy, rx, rz, dz=0.0, off=0.0):
            return [Vector((rx * math.cos(2 * math.pi * (k + off) / n), cy, c0.z + dz + rz * math.sin(2 * math.pi * (k + off) / n))) for k in range(n)]

        def lw(p):
            # labio de abajo con la mandíbula; el de arriba mitad y mitad: al adelantar la mandíbula
            # (boca protráctil de carpa) el tubo entero sale, al abrirla baja sobre todo el de abajo
            low = smoothstep(c0.z + 0.06, c0.z - 0.06, p.z)
            return {"jaw": lerp(0.45, 1.0, low), "head": lerp(0.55, 0.0, low)}
        lb = [mb.v(p, lw(p)) for p in ellipse(-2.745, 0.21, 0.165, 0.0, 0.5)]
        # cara (anillo 0 del loft -> base del labio): mismo zig-zag que el cuerpo
        for k in range(n):
            k1 = (k + 1) % n
            for verts in ([ring0[k], ring0[k1], lb[k]], [lb[k], ring0[k1], lb[k1]]):
                cc = sum((v.co for v in verts), Vector()) / 3
                mb.face(verts, self.skin("face"), outward=Dir((cc.x * 0.5, -1, (cc.z - 1.5) * 0.6)))
        l1 = [mb.v(p, lw(p)) for p in ellipse(-2.84, 0.27, 0.215, 0.0, 0.5)]
        l2 = [mb.v(p, lw(p)) for p in ellipse(-2.93, 0.225, 0.18, 0.0, 0.5)]
        l3 = [mb.v(p, lw(p)) for p in ellipse(-2.9, 0.13, 0.1, 0.0, 0.5)]
        for a, b, cname, odir in ((lb, l1, "lip", (0, -0.3, 0)), (l1, l2, "lip", (0, -1, 0)), (l2, l3, "lip_in", (0, -1, 0))):
            for k in range(n):
                k1 = (k + 1) % n
                verts = [a[k], a[k1], b[k1], b[k]]
                cc = sum((v.co for v in verts), Vector()) / 4
                o = Vector((cc.x, 0, cc.z - c0.z)).normalized() + Vector(odir)
                mb.face(verts, self.skin(cname), outward=Dir(o))
        # garganta: cono hacia adentro; la pared del fondo tapa el interior del cuerpo
        throat = mb.v(Vector((0, -2.6, c0.z)), {"head": 0.6, "jaw": 0.4})
        for k in range(n):
            mb.face([l3[k], l3[(k + 1) % n], throat], self.skin("throat"), outward=Dir((0, -1, 0)))
        wall = [mb.v(Vector((0.3 * math.cos(2 * math.pi * k / 8), -2.55, c0.z + 0.05 + 0.26 * math.sin(2 * math.pi * k / 8))), {"head": 1.0}) for k in range(8)]
        mb.face(wall, "black", outward=Dir((0, -1, 0)))

    # --- ojos dorados con pupila y brillo
    def eyes(self):
        mb = self.mb
        for sx in (1, -1):
            y, th = -2.04, math.radians(16)
            c = surf(y, th); c.x *= sx
            nrm = surf_n(y, th); nrm.x *= sx
            nrm = (nrm + Vector((0, -0.18, 0.2))).normalized()
            x, _, z = frame_from(nrm, Vector((0, 0, 1)))
            w = spine_w(y)
            iris = "gold" if self.phase == 1 else "glow_spirit"
            def ring(r, lift, nseg=8, rot=0.0):
                return [mb.v(c + nrm * lift + (x * math.cos(2 * math.pi * k / nseg + rot) + z * math.sin(2 * math.pi * k / nseg + rot)) * r, w) for k in range(nseg)]
            brow = ring(0.25, -0.01)
            o = ring(0.2, 0.04)
            i_ = ring(0.11, 0.08)
            for A, Bv, cn in ((brow, o, self.skin("face")), (o, i_, iris)):
                for k in range(8):
                    k1 = (k + 1) % 8
                    mb.face([A[k], A[k1], Bv[k1], Bv[k]], cn, outward=Dir(nrm))
            if self.phase == 1:
                pc = mb.v(c + nrm * 0.095, w)
                for k in range(8):
                    mb.face([i_[k], i_[(k + 1) % 8], pc], "black", outward=Dir(nrm))
                # brillo: un rombo chico arriba-adelante de la pupila (vida en los primeros planos)
                g = c + nrm * 0.1 + z * 0.04 + x * (-0.03 * sx)
                gl = [mb.v(g + z * 0.028, w), mb.v(g + x * 0.022, w), mb.v(g - z * 0.022, w), mb.v(g - x * 0.022, w)]
                mb.face(gl, "glow_moon", outward=Dir(nrm))
            else:
                # pupila de dragón: ranura vertical
                pts = [c + nrm * 0.08 + z * 0.085, c + nrm * 0.085 + x * 0.025, c + nrm * 0.08 - z * 0.085, c + nrm * 0.085 - x * 0.025]
                mb.face([mb.v(p, w) for p in pts], "black", outward=Dir(nrm))

    # --- opérculos: placa que se abre, con el borde trasero marcado
    def gills(self):
        mb = self.mb
        for s, sx in (("L", 1), ("R", -1)):
            ths = [math.radians(a) for a in (58, 40, 22, 4, -14, -32, -50, -66)]
            cols = []
            for th in ths:
                yf = -1.80 + 0.06 * abs(math.sin(th))
                yr = -1.36 + 0.10 * math.cos(th)
                col = []
                for u in (0.0, 0.5, 1.0):
                    y = lerp(yf, yr, u)
                    p = surf(y, th); nn = surf_n(y, th)
                    p.x *= sx; nn.x *= sx
                    p = p + nn * (0.015 + 0.05 * u)
                    w = mix(spine_w(y), {f"gill_{s}": 1.0}, 0.65 * smoothstep(0.0, 1.0, u))
                    col.append((mb.v(p, w), nn, y, th))
                cols.append(col)
            plate = self.skin("face") if self.phase == 1 else "ink"
            for i in range(len(cols) - 1):
                for j in range(2):
                    a, b, c, d = cols[i][j], cols[i + 1][j], cols[i + 1][j + 1], cols[i][j + 1]
                    mb.face([a[0], b[0], c[0], d[0]], plate if j == 0 or self.phase == 2 else ("plaster" if i % 3 == 1 else plate), outward=Dir(a[1]))
                # borde: tira del canto trasero hasta la piel (se lee como la ranura de la branquia)
                a, b = cols[i][2], cols[i + 1][2]
                pa = surf(a[2] + 0.02, a[3]); pb = surf(b[2] + 0.02, b[3])
                pa.x *= sx; pb.x *= sx
                va = mb.v(pa, spine_w(a[2])); vb = mb.v(pb, spine_w(b[2]))
                mb.face([a[0], b[0], vb, va], "plaster_shade" if self.phase == 1 else "glow_purple", outward=Dir((0, 1, 0)))
            if self.phase == 2:
                # púas doradas en el canto del opérculo
                for i in (1, 3, 5):
                    a = cols[i][2]
                    base = a[0].co.copy()
                    d = (a[1] * 0.6 + Vector((0, 1, 0.25))).normalized()
                    x, _, z = frame_from(d)
                    w = {f"gill_{s}": 1.0}
                    ring = [self.mb.v(base + (x * math.cos(2 * math.pi * k / 4) + z * math.sin(2 * math.pi * k / 4)) * 0.045, w) for k in range(4)]
                    tip = self.mb.v(base + d * 0.22, w)
                    for k in range(4):
                        self.mb.face([ring[k], ring[(k + 1) % 4], tip], "gold", outward=Dir(d + (x * math.cos(2 * math.pi * (k + 0.5) / 4) + z * math.sin(2 * math.pi * (k + 0.5) / 4))))

    # --- tancho: UN disco rojo arriba de la cabeza (marca de la cabeza y la mordida vista desde arriba)
    def tancho(self):
        if self.phase != 1:
            return
        mb = self.mb
        cy, R = -1.86, 0.55
        nseg = 14
        rings = []
        for rr in (0.0, 0.3, R):
            ring = []
            for k in range(nseg if rr > 0 else 1):
                a = 2 * math.pi * k / nseg
                x, y = rr * math.cos(a), cy + rr * 0.94 * math.sin(a)
                p = top_pt(x, y, 0.028)
                ring.append(mb.v(p, spine_w(y)))
            rings.append(ring)
        c = rings[0][0]
        for k in range(nseg):
            mb.face([c, rings[1][k], rings[1][(k + 1) % nseg]], "flower_red", outward=Dir((0, 0, 1)))
        for k in range(nseg):
            k1 = (k + 1) % nseg
            mb.face([rings[1][k], rings[2][k], rings[2][k1], rings[1][k1]], "flower_red", outward=Dir((0, 0, 1)))
        # canto del disco hasta la piel
        for k in range(nseg):
            k1 = (k + 1) % nseg
            a, b = rings[2][k], rings[2][k1]
            pa = a.co - Vector((0, 0, 0.05)); pb = b.co - Vector((0, 0, 0.05))
            va = mb.v(pa, spine_w(pa.y)); vb = mb.v(pb, spine_w(pb.y))
            mid = (a.co + b.co) / 2
            mb.face([a, b, vb, va], "maple_dark", outward=Dir(Vector((mid.x, mid.y - cy, 0))))

    # --- bigotes
    def barbels(self):
        def chain_w(names, joints, last):
            # punto del camino donde arranca cada hueso (ver bones()): en la unión se reparte mitad y mitad
            def wf(i, t):
                if i == 0:
                    return {names[0]: 0.6, "jaw": 0.4}
                b = max(j for j, start in enumerate(joints) if start <= i)
                if i == joints[b] and b > 0 and i != last:
                    return {names[b - 1]: 0.5, names[b]: 0.5}
                return {names[b]: 1.0}
            return wf
        for s, sx in (("L", 1), ("R", -1)):
            if self.phase == 1:
                pts = barbel_path(sx)
                self.tube(pts, 0.072, 0.026, 5, lambda i, k: "cloth_white" if k % 2 else "paper",
                          chain_w([f"barbel_{s}1", f"barbel_{s}2"], [0, 2], len(pts) - 1))
                sp = short_barbel_path(sx)
                self.tube(sp, 0.04, 0.016, 4, lambda i, k: "cloth_white", lambda i, t: {"head": 0.7, "jaw": 0.3})
            else:
                pts = whisker_path(sx)
                self.tube(pts, 0.062, 0.016, 5, lambda i, k: "glow_purple" if (k + i) % 3 else "cloth_purple",
                          chain_w([f"whisker_{s}1", f"whisker_{s}2", f"whisker_{s}3"], [0, 3, 6], len(pts) - 1))

    def horns(self):
        if self.phase != 2:
            return
        for s, sx in (("L", 1), ("R", -1)):
            hp = horn_path(sx)
            self.tube(hp, 0.12, 0.03, 5, lambda i, k: ("gold_dark", "gold", "glow_spirit")[min(i, 2)],
                      lambda i, t, s=s: {f"horn_{s}": 1.0})

    # --- estaca de hierro oxidado con el Sello del Agua (medallón de ola, sin kanji)
    def seal(self):
        mb = self.mb
        st = top_pt(0, Y_STAKE)
        z0, z1 = st.z - 0.12, st.z + 0.5
        W = {"seal": 1.0}
        rust = ["iron", "rock_brown_dark", "iron", "clay_dark", "iron", "rock_brown_dark"]
        def prism(zb, zt, rb, rt, sides, colfn, rot=0.0):
            bot = [mb.v((rb * math.cos(2 * math.pi * k / sides + rot), Y_STAKE + rb * math.sin(2 * math.pi * k / sides + rot), zb), W) for k in range(sides)]
            top = [mb.v((rt * math.cos(2 * math.pi * k / sides + rot), Y_STAKE + rt * math.sin(2 * math.pi * k / sides + rot), zt), W) for k in range(sides)]
            for k in range(sides):
                k1 = (k + 1) % sides
                mb.face([bot[k], bot[k1], top[k1], top[k]], colfn(k), outward=(0, Y_STAKE, (zb + zt) / 2))
            return bot, top
        prism(z0, z1, 0.115, 0.085, 6, lambda k: rust[k])
        for zc in (st.z + 0.06, st.z + 0.36):
            b, t = prism(zc - 0.035, zc + 0.035, 0.14, 0.14, 6, lambda k: "iron_light", rot=math.pi / 6)
            mb.face(t, "iron_light", outward=(0, Y_STAKE, zc + 1))
            mb.face(b, "iron", outward=(0, Y_STAKE, zc - 1))
        # el medallón va clavado en la punta de la estaca, como una tablilla en su poste
        cz = z1 + 0.36
        self.medallion(Vector((0, Y_STAKE, cz)), 0.4)
        # herida de la maldición alrededor de la estaca (se ve desde arriba aunque el medallón esté de canto)
        nseg = 10
        inner = [top_pt(0.13 * math.cos(2 * math.pi * k / nseg), Y_STAKE + 0.13 * math.sin(2 * math.pi * k / nseg), 0.012) for k in range(nseg)]
        outer = [top_pt(0.33 * math.cos(2 * math.pi * (k + 0.5) / nseg), Y_STAKE + 0.3 * math.sin(2 * math.pi * (k + 0.5) / nseg), 0.006) for k in range(nseg)]
        vi = [mb.v(p, spine_w(p.y)) for p in inner]
        vo = [mb.v(p, spine_w(p.y)) for p in outer]
        for k in range(nseg):
            k1 = (k + 1) % nseg
            mb.face([vi[k], vo[k], vi[k1]], "glow_purple", outward=Dir((0, 0, 1)))
            mb.face([vi[k1], vo[k], vo[k1]], "cloth_purple" if self.phase == 1 else "glow_purple", outward=Dir((0, 0, 1)))

    def medallion(self, c, R):
        """Disco de canto (normal ±X) con aro dorado, un hilo violeta (la maldición) y en la cara azul una
        ola que rompe, en las dos caras. Es el emblema del Sello del Agua: el mismo motivo de ola que el
        key_seal_lake que Kaito levanta al final, simplificado para leerse a 50 px."""
        mb = self.mb
        W = {"seal": 1.0}
        nseg = 14
        th = 0.045
        def pt(r, a, x):
            return Vector((x, c.y + r * math.cos(a), c.z + r * math.sin(a)))
        rings = {}
        for name, r, x in (("ro", R, th), ("ri", R * 0.84, th + 0.012), ("rp", R * 0.78, th - 0.004)):
            for sx in (1, -1):
                rings[(name, sx)] = [mb.v(pt(r, 2 * math.pi * k / nseg, x * sx), W) for k in range(nseg)]
        curse = "glow_purple"
        for sx in (1, -1):
            ro, ri, rp = rings[("ro", sx)], rings[("ri", sx)], rings[("rp", sx)]
            for k in range(nseg):
                k1 = (k + 1) % nseg
                mb.face([ro[k], ro[k1], ri[k1], ri[k]], "gold", outward=Dir((sx, 0, 0)))
                mb.face([ri[k], ri[k1], rp[k1], rp[k]], curse, outward=Dir((sx, 0, 0)))
            ctr = mb.v(Vector((th * sx - 0.006 * sx, c.y, c.z)), W)
            for k in range(nseg):
                mb.face([rp[k], rp[(k + 1) % nseg], ctr], "cloth_blue", outward=Dir((sx, 0, 0)))
        ro_a, ro_b = rings[("ro", 1)], rings[("ro", -1)]
        for k in range(nseg):
            k1 = (k + 1) % nseg
            mid = (ro_a[k].co + ro_b[k1].co) / 2
            mb.face([ro_a[k], ro_a[k1], ro_b[k1], ro_b[k]], "gold_dark" if k % 2 else "gold", outward=Dir(mid - c))
        s = R * 0.74
        crest = [(-0.72, -0.30), (-0.55, -0.05), (-0.35, 0.18), (-0.12, 0.32), (0.10, 0.30), (0.22, 0.18), (0.12, 0.08),
                 (0.02, 0.12), (-0.06, 0.02), (0.05, -0.10), (0.30, -0.12), (0.55, -0.22), (0.72, -0.30), (0.62, -0.46), (-0.62, -0.46)]
        deep = [(-0.62, -0.5), (0.62, -0.5), (0.45, -0.74), (-0.45, -0.74)]
        spray = [[(x + 0.07 * math.cos(2 * math.pi * k / 4), y + 0.07 * math.sin(2 * math.pi * k / 4)) for k in range(4)]
                 for x, y in ((0.36, 0.36), (0.5, 0.18), (0.22, 0.52))]
        for sx in (1, -1):
            base = th * sx
            self.slab([(u * s, v * s) for u, v in crest], c, base - sx * 0.008, sx, 0.024, "water_foam")
            self.slab([(u * s, v * s) for u, v in deep], c, base - sx * 0.008, sx, 0.02, "water_shallow")
            for sp in spray:
                self.slab([(u * s, v * s) for u, v in sp], c, base - sx * 0.008, sx, 0.02, "glow_water")

    def slab(self, pts, c, x0, sx, depth, color):
        """Polígono (u = -Y local, v = Z) en relieve sobre la cara del medallón que mira a sx·X."""
        mb = self.mb
        W = {"seal": 1.0}
        # en la cara +X, u crece hacia -Y (el frente del koi) para que la ola se lea igual de los dos lados
        def p3(u, v, x):
            return Vector((x, c.y - u * sx, c.z + v))
        bot = [mb.v(p3(u, v, x0), W) for u, v in pts]
        top = [mb.v(p3(u, v, x0 + sx * depth), W) for u, v in pts]
        mb.face(top, color, outward=Dir((sx, 0, 0)))
        n = len(pts)
        cc = sum((p.co for p in top), Vector()) / n
        for k in range(n):
            k1 = (k + 1) % n
            mid = (top[k].co + top[k1].co) / 2
            mb.face([bot[k], bot[k1], top[k1], top[k]], color, outward=Dir(Vector((0, mid.y - cc.y, mid.z - cc.z))))

    # --- shimenawa: cuerda de paja trenzada con nudo, borlas y shide
    def rope(self):
        mb = self.mb
        nseg = 26
        pts = []
        for k in range(nseg):
            th = 2 * math.pi * k / nseg
            y = Y_ROPE - 0.08 * math.sin(th)      # inclinada: más adelante arriba, como atada al pasar
            p = surf(y, th) + surf_n(y, th) * 0.09
            pts.append(p)
        def wf(i, t):
            return spine_w(pts[i % nseg].y)
        def cf(i, k):
            # dos cabos trenzados: rayas diagonales
            return "thatch_dark" if (i + k) % 3 == 0 else ("wheat_dark" if (i + k) % 3 == 1 else "straw")
        # las rayas diagonales de cf ya dibujan los cabos torcidos; un 'twist' geométrico no cerraría el anillo
        self.tube(pts, 0.15, 0.15, 6, cf, wf, closed=True, up=(0, 1, 0))
        # nudo arriba a la izquierda de la estaca: dos lazos y la vuelta del medio
        kc = surf(Y_ROPE - 0.06, math.radians(68)) + surf_n(Y_ROPE - 0.06, math.radians(68)) * 0.1
        nrm = surf_n(Y_ROPE - 0.06, math.radians(68))
        w = spine_w(kc.y)
        ax = Vector((0, 1, 0)).cross(nrm).normalized()
        for side in (-1, 1):
            ctr = kc + Vector((0, side * 0.24, 0.0)) + nrm * 0.07
            loop = [ctr + Vector((0, side * 0.17 * math.cos(a), 0)) + nrm * (0.13 * math.sin(a))
                    for a in [2 * math.pi * j / 8 for j in range(8)]]
            self.tube(loop, 0.075, 0.075, 5, cf, lambda i, t, w=w: w, closed=True, up=ax)
        self.tube([kc - Vector((0, 0.12, 0)), kc + Vector((0, 0.12, 0))], 0.135, 0.135, 6, lambda i, k: "wheat_dark" if k % 2 else "straw",
                  lambda i, t, w=w: w, cap=True)
        # los dos cabos del nudo cuelgan por el flanco izquierdo y terminan en borlas grandes
        WL = {"shide_L": 1.0}
        for j, dy in enumerate((-0.16, 0.16)):
            a = kc + Vector((0.05, dy, -0.05))
            b = a + Vector((0.16, dy * 0.3, -0.34))
            c = b + Vector((0.06, 0.0, -0.3))
            self.tube([a, b, c], 0.06, 0.055, 5, lambda i, k: "straw" if k % 2 else "wheat_dark",
                      lambda i, t, w=w: mix(w, WL, t), cap=False)
            self.tassel(c, WL, big=True)
        # borlas y shide colgando en los dos flancos (huesos shide_L/R: flamean con resorte)
        for s, sx in (("L", 1), ("R", -1)):
            a = shide_anchor(sx)
            W = {f"shide_{s}": 1.0}
            for j, dy in enumerate((-0.5, -0.25, 0.0, 0.25, 0.5)):
                top = a + Vector((0.0, dy, 0.02 - 0.05 * abs(dy)))
                if j % 2 == 0:
                    self.shide(top, sx, W, 4 if self.phase == 1 else 3)
                else:
                    self.tassel(top, W)

    def shide(self, top, sx, W, nseg):
        """Tira de papel en zigzag (el rayo de los santuarios), de doble cara."""
        mb = self.mb
        h, wd = 0.15, 0.16
        x = top.x
        col = "paper" if self.phase == 1 else "plaster_dirty"
        for i in range(nseg):
            dy = 0.055 * (1 if i % 2 else -1)
            z0, z1 = top.z - i * h, top.z - (i + 1) * h
            q = [Vector((x, top.y + dy - wd / 2, z0)), Vector((x, top.y + dy + wd / 2, z0)),
                 Vector((x, top.y + dy + wd / 2, z1 + 0.01)), Vector((x, top.y + dy - wd / 2, z1 + 0.01))]
            mb.double([mb.v(p, W) for p in q], col, (sx, 0, 0))

    def tassel(self, top, W, big=False):
        """Borla (fusa) de paja: anillo dorado y un mechón que se abre abajo."""
        mb = self.mb
        sides = 6
        k = 1.35 if big else 1.0
        prof_ = [(dz * k, r * k) for dz, r in ((0.0, 0.04), (0.07, 0.09), (0.12, 0.095), (0.14, 0.07), (0.44, 0.12), (0.47, 0.0))]
        rings = []
        for dz, r in prof_:
            rings.append([mb.v(top + Vector((r * math.cos(2 * math.pi * k / sides), r * math.sin(2 * math.pi * k / sides), -dz)), W) for k in range(sides)])
        cols = ["gold", "gold", "gold_dark", "straw", "wheat"]
        for j in range(len(rings) - 1):
            for k in range(sides):
                k1 = (k + 1) % sides
                c = cols[j] if j < 3 else ("straw" if k % 2 else "wheat")
                mb.face([rings[j][k], rings[j][k1], rings[j + 1][k1], rings[j + 1][k]], c,
                        outward=Dir((math.cos(2 * math.pi * (k + 0.5) / sides), math.sin(2 * math.pi * (k + 0.5) / sides), 0)))

    # --- aletas
    def fin_colors(self):
        """Radios alternados blanco / índigo como en el concept; la fila de la base del radio oscuro es un
        azul más claro (la aleta 'nace' del cuerpo sin un corte duro). Fase 2: tinta y violeta."""
        p1 = self.phase == 1
        def colors(i, j, nrows):
            if p1:
                if i % 2:
                    return "tile_blue" if j == 0 else "cloth_indigo"
                return "white" if j else "plaster"
            return "cloth_purple" if i % 2 else ("ink" if j else "cloth_black")
        return colors

    def rim(self):
        # el último 10 % de los radios oscuros toma un filo de agua (fase 1) o de maldición (fase 2): de
        # noche dibuja el borde de las aletas sin que la aleta entera brille (en el prototipo le ganaba a todo)
        if self.phase == 1:
            return lambda i, c: "glow_water" if i % 2 else c
        return lambda i, c: "glow_purple" if i % 2 else c

    def fins(self):
        p2 = self.phase == 2
        torn = 0.12 if p2 else 0.0
        jag = 0.1 if p2 else 0.0
        rows4 = (0.0, 0.3, 0.62, 0.9)
        # pectorales: abanico grande, pesos por largo a lo largo del radio (L1 base, L2 medio, L3 punta)
        for s, sx in (("L", 1), ("R", -1)):
            rays, n, a = pec_def(sx)
            def pw(p, t, i, s=s):
                if t < 0.22:
                    return {f"pec_{s}1": 1.0}
                if t < 0.5:
                    u = smoothstep(0.22, 0.5, t)
                    return {f"pec_{s}1": 1 - u, f"pec_{s}2": u}
                u = smoothstep(0.58, 0.9, t)
                return {f"pec_{s}2": 1 - u, f"pec_{s}3": u}
            self.fan(rays, n, self.fin_colors(), pw, rows=rows4, pleat=0.055, notch=0.07,
                     rim=self.rim(), torn=torn, jag=jag)
            rays, n, a = pel_def(sx)
            self.fan(rays, n, self.fin_colors(), lambda p, t, i, s=s: mix(spine_w(p.y), {f"pel_{s}": 1.0}, smoothstep(0.0, 0.35, t)),
                     rows=(0.0, 0.5, 0.88), pleat=0.03, notch=0.06, rim=self.rim(), torn=torn * 0.5, jag=jag)
            rays, n, back = tail_def(sx, self.phase)
            def tw(p, t, i, s=s):
                if t < 0.12:
                    return {"tail": 1.0}
                if t < 0.42:
                    u = smoothstep(0.12, 0.42, t)
                    return {"tail": 1 - u, f"fluke_{s}1": u}
                u = smoothstep(0.42, 0.75, t)
                return {f"fluke_{s}1": 1 - u, f"fluke_{s}2": u}
            self.fan(rays, n, self.fin_colors(), tw, rows=rows4, pleat=0.06, notch=0.08,
                     rim=self.rim(), torn=torn, jag=jag)
        rays, n, _ = dorsal_def(self.phase)
        dbones = [("dorsal_1", -0.02, 0.5), ("dorsal_2", 0.5, 1.02), ("dorsal_3", 1.02, 1.54), ("dorsal_4", 1.54, 2.3)]
        def dw(p, t, i):
            y0 = rays[min(i, len(rays) - 1)][0].y
            b = next((bn for bn, a0, a1 in dbones if y0 <= a1 + 1e-3), "dorsal_4")
            return mix(spine_w(y0), {b: 1.0}, smoothstep(0.05, 0.45, t))
        self.fan(rays, n, self.fin_colors(), dw, rows=(0.0, 0.36, 0.7, 0.9), pleat=0.04, notch=0.12 if p2 else 0.07,
                 rim=self.rim(), torn=torn * 0.7, jag=0.18 if p2 else 0.0)
        rays, n, _ = anal_def()
        self.fan(rays, n, self.fin_colors(), lambda p, t, i: mix(spine_w(p.y), {"anal": 1.0}, smoothstep(0.0, 0.3, t)),
                 rows=(0.0, 0.5, 0.88), pleat=0.03, notch=0.06, rim=self.rim(), torn=torn * 0.5, jag=jag)

    def build(self):
        self.body()
        self.eyes()
        self.gills()
        self.tancho()
        self.barbels()
        self.horns()
        self.seal()
        self.cracks()
        self.rope()
        self.fins()
        return self.mb.finish()


def build_ripple(names):
    """'Espejo de agua' bajo el koi: anillo plano en la cubierta (32 tris), 100 % al root. Marca la altura
    a la que flota vista desde arriba y define el piso para NormalizeHeight (el punto más bajo del modelo)."""
    mb = KoiBuilder("Ripple", names)
    n = 16
    inner = [mb.v((2.28 * math.cos(2 * math.pi * k / n), 2.28 * math.sin(2 * math.pi * k / n), 0.0), {"root": 1.0}) for k in range(n)]
    outer = [mb.v((2.5 * math.cos(2 * math.pi * (k + 0.5) / n), 2.5 * math.sin(2 * math.pi * (k + 0.5) / n), 0.0), {"root": 1.0}) for k in range(n)]
    for k in range(n):
        k1 = (k + 1) % n
        mb.face([inner[k], outer[k], inner[k1]], "glow_water", outward=Dir((0, 0, 1)))
        mb.face([inner[k1], outer[k], outer[k1]], "glow_water", outward=Dir((0, 0, 1)))
    return mb.finish()
