"""Kits de accesorios por zona de los enemigos comunes (y las colas de la bandana de Kaito).

    blender -b --python Tools/Blender/characters/kits/build_kits.py -- [--only k1,k2] [--export]
            [--preview DIR] [--src-assets DIR] [--actions SUMO_FBX]

--export     escribe Nindo/Assets/Nindo/Art/Characters/Kits/Kit_<id>.fbx (+ kits.json con triángulos y cadenas)
--preview    renders de control (reposo y game cam) en DIR
--src-assets toma los FBX de los personajes de otro Assets (p. ej. el de la rama de los personajes pulidos):
             el esqueleto es el mismo, cambian solo los pesos que se copian de la piel
--actions    FBX del que se sacan las tomas para posar (el sumo del repo ya no trae tomas)
--bases      con --preview: también los personajes sin kit (ninja_base, sumo_base) para comparar

Después, lineup.py junta las celdas de los renders en las hojas de comparación (los cuatro ninjas, los cinco sumos).

Diseño (concepts/variants_sheet.png, audit_models.json): cada zona se tiene que leer a ~100 px desde la cámara
del juego con una silueta, un bloque de color y algo que se mueva:
  jardín/bosque (default): el ninja negro de siempre con el hachimaki rojo del clan Kurokage (las colas
                 dicen para dónde mira desde arriba) y vendas de brazo.
  montaña:      capa de paja (mino) en tres hileras con nieve arriba, cuello de piel, cinturón de soga con
                 shide, polainas con soga cruzada y sandalias de paja. Se mueve la capa (pesada).
  lago:         sombrero de paja ancho (el disco se ve desde arriba), red de pescar sobre los hombros con
                 flotadores, faja turquesa con un faldón cortado en ola, flotador de vidrio que brilla
                 (identifica al lago de noche) y un arpón cruzado en la espalda.
  bambú:        armadura de cañas (peto, hombreras, faldones), máscara de hojas y moño con dos hojas largas.
  élite:        el kit de su zona más una máscara oni roja y hombreras laqueadas rojas: "rojo = élite" en
                 todas las zonas (en el bambú las hojas de la máscara pasan a arce rojo).
  sumo:         lo mismo en grande; Ōzeki (jefe del bambú) lleva el ōichō dorado en hoja de ginkgo, la tsuna
                 blanca con shide y el delantal violeta con el emblema de bambú (sin kanji).
Los nombres: 'Acc_' adelante y nunca Katana/Isan/Cylinder/Martillo/Arma/Cube (Enemy, PlayerController y NPC
buscan sus armas por esos nombres).
"""
import bpy, os, sys, json, math, random
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kitlib as K  # noqa: E402
from kitlib import V, frame, smoothstep, lerp  # noqa: E402

KITS = {}

# Colores del cuerpo por variante (nombre de material del FBX del equipo -> color). Es la MISMA tabla que
# Enemies/EnemyVariants.cs aplica en el juego: acá solo se usa para que los renders muestren lo que se va a ver.
# El traje del ninja sigue negro (el carbón de export_ninja.py, #2e2b2c) con apenas el matiz de la zona: más
# saturado se leía azul marino, como el gi de Kaito.
BODY_COLORS = {
    "ninja_mountain": {"GrisOscuro": "#302f33"}, "ninja_mountain_elite": {"GrisOscuro": "#302f33"},
    "ninja_lake": {"GrisOscuro": "#272c2e"}, "ninja_lake_elite": {"GrisOscuro": "#272c2e"},
    "ninja_bamboo": {"GrisOscuro": "#292c27"}, "ninja_bamboo_elite": {"GrisOscuro": "#292c27"},
    "sumo_mountain": {"Pollera": "#44474d", "PolleraCinto": "#2c2f35", "Sagari": "#6b7079"},
    "sumo_lake": {"Pollera": "#1f4a5e", "PolleraCinto": "#173544", "Sagari": "#9fd0d6"},
    "sumo_bamboo": {"Pollera": "#2f4a2a", "PolleraCinto": "#1f3320", "Sagari": "#b8a35a"},
    "ozeki": {"Pollera": "#5b3a6b", "PolleraCinto": "#3a2446", "Sagari": "#d9a93a"},
}


def recolor_body(ch, colors):
    """Solo para los renders: pinta los materiales del cuerpo como lo hace el juego en esa variante."""
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name.startswith("Acc_"):
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None or K.base(m.name) not in colors:
                continue
            c = K.flat_material(K.base(m.name) + "_var", colors[K.base(m.name)])
            slot.material = c


def kit(name, char):
    def deco(fn):
        KITS[name] = (char, fn)
        return fn
    return deco


# ============================================================================ NINJA (mira a +X, Z arriba)
# cabeza: bola x -0.38..0.38, y -0.37..0.33, z 2.10..2.91 (centro y -0.02); ojos x~0.35 z 2.41..2.57
# hombros z 1.95..2.10 hasta y ±0.42; torso x -0.34..0.32; cintura z 1.25..1.40; muslo z 0.63..1.10; tibia 0.21..0.63
NH = V(0.0, -0.02, 2.50)       # centro de la cabeza


def ninja_colliders(k, legs=False):
    k.collider("Head", "Cabeza", (0.0, -0.02, 2.50), 0.40)
    k.collider("Chest", "EspaldaAlta", (-0.02, -0.02, 1.82), 0.36)
    k.collider("Hips", "EspaldaBaja", (-0.02, -0.02, 1.38), 0.36)
    if legs:
        k.collider("ThighL", "Pierna.L", (0.02, -0.23, 0.86), 0.20)
        k.collider("ThighR", "Pierna.R", (0.02, 0.19, 0.86), 0.20)


def hachimaki(k, color, tail_color=None, knot_color=None, tails=True, length=1.0, leaf=False):
    """Cinta en la frente, nudo atrás y dos colas largas (cadenas). Desde arriba las colas marcan la espalda."""
    g = k.geo
    M = frame((0.01, -0.02, 2.665), (1, 0, 0.12), (0, 0, 1))      # inclinada: más baja adelante (frente)
    g.band(M, 0.395, 0.355, 0.11, 0.035, color, seg=16).rigid("Cabeza")
    kc = knot_color or color
    # nudo: bloque central y dos orejas del moño
    g.box(frame((-0.405, -0.02, 2.69), (1, 0, 0), (0, 0, 1)), (0.09, 0.12, 0.11), kc, chamfer=0.02).rigid("Cabeza")
    for s in (-1, 1):
        g.box(frame((-0.42, -0.02 + s * 0.10, 2.71), (0.6, s * 0.8, 0.3), (0, 0, 1)), (0.12, 0.06, 0.08), kc, taper=0.7).rigid("Cabeza")
    if not tails:
        return
    tc = tail_color or color
    for name, s in (("TailA", 1), ("TailB", -1)):
        L = length
        pts = [V(-0.42, -0.02 + s * 0.04, 2.66), V(-0.50, -0.02 + s * 0.08, 2.50 - 0.02 * L),
               V(-0.56, -0.02 + s * 0.13, 2.30 - 0.06 * L), V(-0.60, -0.02 + s * 0.17, 2.10 - 0.10 * L),
               V(-0.62, -0.02 + s * 0.20, 1.92 - 0.14 * L)]
        ch = k.chain(name, "Cabeza", pts)
        # cinta con más filas que huesos para que doble suave; ancho que se afina hacia la punta
        rows = []
        for i in range(len(pts) - 1):
            for t in (0.0, 0.5):
                rows.append(pts[i].lerp(pts[i + 1], t))
        rows.append(pts[-1])
        n = len(rows)
        if leaf:
            widths = [0.05 + 0.12 * math.sin(math.pi * min(1, (i + 0.6) / n)) for i in range(n)]
        else:
            widths = [0.15 - 0.06 * (i / (n - 1)) for i in range(n)]
            widths[-1] = 0.035                                         # punta en flecha
        g.ribbon(rows, widths, 0.022, tc, up=(-1, 0, 0.25)).chain(name)


def tekko(k, color, band_color=None):
    """Vendas de antebrazo en tres vueltas escalonadas: el movimiento del brazo se ve desde arriba."""
    g = k.geo
    for side, s in (("R", 1), ("L", -1)):
        bone = "Antebrazo." + side
        a, b = k.char.bone_head(bone), k.char.bone_tail(bone)
        ax = (b - a).normalized()
        for i, (t0, r) in enumerate(((0.25, 0.150), (0.48, 0.156), (0.70, 0.150))):
            c = a.lerp(b, t0)
            M = frame(c + V(0.02, 0, 0), (1, 0, 0), ax)
            col = band_color if (band_color and i == 1) else color
            g.band(M, r, r * 0.9, 0.10, 0.03, col, seg=8).rigid(bone)


def oni_menpo(k, color="wood_red", dark="wood_red_dark", teeth="cloth_white"):
    """Media máscara oni (nariz a mentón) sobre la máscara de tela: el rasgo del élite."""
    g = k.geo
    M = frame((0.03, -0.02, 2.30), (1, 0, 0), (0, 0, 1))
    g.band(M, 0.375, 0.33, 0.20, 0.04, color, seg=14, a0=-72, a1=72, rx2=0.40, ry2=0.35).rigid("Cabeza")
    # nariz y pómulos
    g.box(frame((0.425, -0.02, 2.36), (1, 0, 0.3), (0, 0, 1)), (0.07, 0.09, 0.10), color, taper=0.6).rigid("Cabeza")
    for s in (-1, 1):
        g.box(frame((0.30, -0.02 + s * 0.31, 2.33), (0.5, s * 0.85, 0), (0, 0, 1)), (0.12, 0.05, 0.12), color, taper=0.4).rigid("Cabeza")
    # boca en mueca con colmillos
    g.box(frame((0.405, -0.02, 2.255), (1, 0, 0), (0, 0, 1)), (0.03, 0.30, 0.055), dark).rigid("Cabeza")
    for y, up in ((-0.10, 1), (0.06, 1), (-0.05, -1), (0.11, -1)):
        z = 2.255 + (-0.035 if up > 0 else 0.035)
        g.box(frame((0.418, -0.02 + y, z), (1, 0, 0), (0, 0, up)), (0.03, 0.04, 0.05), teeth, taper=0.2).rigid("Cabeza")


def sode(k, color, lace="gold", lames=3, slats=False, slat_colors=("bamboo", "bamboo_light")):
    """Hombreras sobre la cara de arriba del brazo en pose T (al bajar el brazo quedan del lado de afuera)."""
    g = k.geo
    for side, s in (("R", 1), ("L", -1)):
        bone = "Brazo." + side
        a, b = k.char.bone_head(bone), k.char.bone_tail(bone)
        ax = (b - a).normalized()
        for i in range(lames):
            c = a.lerp(b, 0.08 + 0.30 * i) + V(-0.06, 0, -0.02)
            M = frame(c, (0, 0, 1), ax)                  # ángulo 0 del arco = arriba (afuera con el brazo bajo)
            r = 0.205 + 0.02 * i
            if slats:
                cols = lambda ring, j: slat_colors[j % 2]
                g.band(M, r, r, 0.17, 0.035, slat_colors[0], seg=7, a0=-95, a1=95, colors=cols).rigid(bone)
            else:
                g.band(M, r, r, 0.15, 0.035, color, seg=7, a0=-95, a1=95).rigid(bone)
        # cordón de la hombrera (arriba, sobre la primera lámina)
        c = a.lerp(b, 0.08) + V(-0.06, 0, -0.02)
        g.ico(frame(c + V(0, 0, 0.215), (1, 0, 0), (0, 0, 1)), (0.04, 0.04, 0.03), lace, subdiv=0).rigid(bone)


@kit("ninja_default", "ninja")
def ninja_default(k):
    hachimaki(k, "cloth_red", knot_color="wood_red")
    tekko(k, "iron", band_color="iron_light")
    ninja_colliders(k)


@kit("ninja_elite", "ninja")
def ninja_elite(k):
    hachimaki(k, "cloth_red", knot_color="wood_red", length=1.25)
    tekko(k, "iron", band_color="iron_light")
    oni_menpo(k)
    sode(k, "wood_red")
    ninja_colliders(k)


# ---------------------------------------------------------------------------- piezas compartidas
def ell(c, rx, ry, a, z):
    """Punto de una elipse horizontal de centro c (x, y) y ángulo a en grados (0 = +X)."""
    r = math.radians(a)
    return V(c[0] + rx * math.cos(r), c[1] + ry * math.sin(r), z)


def shell(k, c, a0, a1, rows, cols, thick, color_fn, inner="thatch_dark", hem_zig=0.0, flute=0.0, seed=7,
          weight=None):
    """Hilera de capa/faldón: superficie abierta entre los ángulos a0..a1 con espesor y borde de abajo dentado.
    rows: lista (z, rx, ry) de arriba hacia abajo. color_fn(fila, col, normal) -> color de la cara exterior.
    hem_zig: cuánto bajan las puntas alternas del borde (paja); flute: estrías verticales (manojos)."""
    g = k.geo
    rnd = random.Random(seed)
    nr = len(rows)
    zig = [(-hem_zig * (1.0 if j % 2 == 0 else 0.25) * (0.8 + 0.4 * rnd.random())) for j in range(cols + 1)]
    outer, inner_r = [], []
    for i, (z, rx, ry) in enumerate(rows):
        ro, ri = [], []
        u = i / (nr - 1)
        for j in range(cols + 1):
            a = lerp(a0, a1, j / cols)
            fl = flute * (1 if j % 2 else -1) * (0.3 + 0.7 * u)
            dz = zig[j] * smoothstep(0.6, 1.0, u)
            ro.append(ell(c, rx + fl, ry + fl, a, z + dz))
            ri.append(ell(c, rx + fl - thick, ry + fl - thick, a, z + dz + thick * 0.3))
        outer.append(ro); inner_r.append(ri)
    oid = [g.add(r) for r in outer]
    iid = [g.add(r) for r in inner_r]
    idx = [i for r in oid + iid for i in r]
    for i in range(nr - 1):
        for j in range(cols):
            a, b, cc, d = oid[i][j], oid[i][j + 1], oid[i + 1][j + 1], oid[i + 1][j]
            n = (g.v[d] - g.v[a]).cross(g.v[b] - g.v[a]).normalized()      # normal hacia afuera
            g.face((a, d, cc, b), color_fn(i, j, n))
            g.face((iid[i][j], iid[i][j + 1], iid[i + 1][j + 1], iid[i + 1][j]), inner)
    # borde de abajo, borde de arriba y los dos costados
    last = nr - 1
    for j in range(cols):
        g.face((oid[last][j], oid[last][j + 1], iid[last][j + 1], iid[last][j]), inner)
        g.face((oid[0][j + 1], oid[0][j], iid[0][j], iid[0][j + 1]), color_fn(0, j, V(0, 0, 1)))
    for j in (0, cols):
        q = [oid[i][j] for i in range(nr)] + [iid[i][j] for i in reversed(range(nr))]
        for i in range(nr - 1):
            quad = (oid[i][j], oid[i + 1][j], iid[i + 1][j], iid[i][j])
            g.face(quad if j == 0 else tuple(reversed(quad)), inner)
    p = K.Part(g, idx)
    if weight:
        p.fn(weight)
    return p


def rope_ring(k, c, rx, ry, z, r, color="rope", dark="thatch_dark", seg=20, sides=6, tilt=None, hug=False):
    """Soga retorcida cerrada: tubo de 6 caras que gira 30° por tramo con caras alternadas claro/oscuro.
    hug: cada punto se apoya sobre la piel a esa altura (el cinto del sumo abraza la panza y la espalda)."""
    pts = [ell(c, rx, ry, 360 * i / seg, z) for i in range(seg + 1)]
    if hug:
        pts = [k.char.hug(c, 360 * i / seg, z, r * 0.8, (p - V(c[0], c[1], z)).length) for i, p in enumerate(pts)]
    if tilt:
        pts = [tilt @ p for p in pts]
    cols = lambda a, j: dark if (j + a) % 3 == 0 else color
    return k.geo.tube(pts, r, color, sides=sides, twist=30, cap0=False, cap1=False, colors=cols)


def cape_weight(k, columns, top_allow, base_until):
    """Pesos de la capa: mezcla en ángulo entre las cadenas-columna y, arriba, los de la piel del cuerpo."""
    cs = [(a, k.chains[n]) for a, n in columns]

    def f(p):
        a = math.degrees(math.atan2(p.y + 0.02, p.x + 0.03)) % 360
        ws = []
        for i, (ca, ch) in enumerate(cs):
            d = abs((a - ca + 180) % 360 - 180)
            ws.append(max(0.0, 1.0 - d / 45.0))
        tot = sum(ws)
        if tot < 1e-6:
            ws = [1.0 if i == min(range(len(cs)), key=lambda i: abs((a - cs[i][0] + 180) % 360 - 180)) else 0.0 for i in range(len(cs))]
            tot = 1.0
        base = k.char.body_weights(p, top_allow)
        out = {}
        for wv, (ca, ch) in zip(ws, cs):
            if wv <= 0:
                continue
            for b, x in ch.weights(p, base, base_until).items():
                out[b] = out.get(b, 0.0) + x * wv / tot
        return out
    return f


# ---------------------------------------------------------------------------- montaña (Kodoyama)
def ninja_mountain_parts(k):
    g = k.geo
    C = (-0.03, -0.02)
    # tres columnas de la capa de paja (izquierda, centro, derecha de la espalda), pesadas
    for name, a in (("CapeL", 225), ("CapeC", 180), ("CapeR", 135)):
        k.chain(name, "EspaldaAlta", [ell(C, 0.38, 0.52, a, 1.98), ell(C, 0.45, 0.61, a, 1.50),
                                       ell(C, 0.50, 0.64, a, 1.08), ell(C, 0.54, 0.67, a, 0.68)])
    cw = cape_weight(k, ((225, "CapeL"), (180, "CapeC"), (135, "CapeR")), {"EspaldaAlta", "Hombro.L", "Hombro.R"}, 0.26)
    rnd = random.Random(11)

    def straw(top_snow):
        def f(i, j, n):
            if top_snow and i == 0 and n.z > 0.35:
                return "snow"
            if top_snow and i == 0 and n.z > 0.12:
                return "snow_shade"
            # arriba de cada hilera más oscuro (la sombra de la de arriba), abajo la paja al aire: se leen las capas
            if i == 0:
                return ("thatch", "thatch_dark", "thatch")[(j + rnd.randint(0, 2)) % 3]
            return ("straw", "thatch_light", "wheat")[(j + rnd.randint(0, 2)) % 3]
        return f
    # hilera 1 sobre los hombros y la parte de arriba de los brazos: de frente la paja enmarca el torso
    shell(k, C, 80, 280, [(2.10, 0.28, 0.42), (1.86, 0.42, 0.60), (1.56, 0.50, 0.68)], 16, 0.035, straw(True),
          hem_zig=0.09, flute=0.018, seed=3, weight=cw)
    shell(k, C, 98, 262, [(1.70, 0.44, 0.60), (1.40, 0.51, 0.66), (1.08, 0.57, 0.71)], 14, 0.035, straw(False),
          hem_zig=0.10, flute=0.02, seed=4, weight=cw)
    shell(k, C, 112, 248, [(1.28, 0.52, 0.65), (1.00, 0.58, 0.70), (0.70, 0.64, 0.76)], 12, 0.035, straw(False),
          hem_zig=0.12, flute=0.022, seed=5, weight=cw)
    # cuello de piel con nieve: dona gruesa y mechones hacia afuera
    M = frame((-0.02, -0.02, 2.08), (1, 0, 0), (0, 0, 1))
    fur = lambda a, j: ("cloth_white", "snow", "trunk", "plaster_shade")[a]
    g.band(M, 0.45, 0.50, 0.17, 0.17, "cloth_white", seg=14, rx2=0.31, ry2=0.34, jitter=0.06, seed=8, colors=fur
           ).body({"EspaldaAlta", "Hombro.L", "Hombro.R"})
    for i in range(16):
        a = 360 * (i + 0.5) / 16
        p = ell((-0.02, -0.02), 0.43, 0.48, a, 2.02)
        out = (p - V(-0.02, -0.02, 2.02)).normalized()
        g.cone(frame(p, out.cross(V(0, 0, 1)), out * 0.6 + V(0, 0, -1)), 0.075, 0.0, 0.09 + 0.04 * (i % 3), FUR[i % 4],
               sides=4, cap1=False).body({"EspaldaAlta", "Hombro.L", "Hombro.R"})
    # cinturón de soga con nudo adelante y dos shide (papel ritual, como la soga de Gorō)
    rope_ring(k, (-0.01, -0.02), 0.385, 0.405, 1.37, 0.045).body({"EspaldaBaja", "Root", "EspaldaAlta"})
    g.ico(frame((0.40, -0.02, 1.37), (1, 0, 0), (0, 0, 1)), (0.07, 0.09, 0.07), "rope", subdiv=1, jitter=0.12).rigid("EspaldaBaja")
    for i, y in enumerate((-0.16, 0.12)):
        top = V(0.39, -0.02 + y, 1.33)
        pts = [top, top + V(0.02, 0, -0.12), top + V(0.03, 0, -0.24), top + V(0.04, 0, -0.34)]
        k.chain(f"Shide{i}", "EspaldaBaja", pts)
        g.zigzag_shide(top, (0.1, 0, -1), (0, 1, 0), 0.07, 4, 0.06, 0.014, "flower_white").chain(f"Shide{i}")
    # polainas blancas con soga cruzada y sandalias de paja
    for side, s in (("R", 1), ("L", -1)):
        bone = "Tibia." + side
        a, b = k.char.bone_head(bone), k.char.bone_tail(bone)
        y = 0.205 if s > 0 else -0.245
        pts = [V(-0.10, y + 0.01 * s, 0.22), V(-0.06, y, 0.40), V(-0.03, y - 0.005 * s, 0.60)]
        g.tube(pts, [0.135, 0.15, 0.165], "cloth_white", sides=7).rigid(bone)
        for d in (1, -1):
            hel = []
            for i in range(9):
                t = i / 8
                p = V(-0.10, y, 0.22).lerp(V(-0.03, y, 0.60), t)
                ang = math.radians(d * 330 * t + (0 if d > 0 else 180))
                rr = 0.152 + 0.02 * t
                hel.append(p + V(math.cos(ang) * rr, math.sin(ang) * rr, 0))
            g.tube(hel, 0.016, "wood_dark", sides=3).rigid(bone)
        foot = "Pie." + side
        sole = [ell((-0.01, y + 0.005 * s), 0.27, 0.15, a, 0.035) for a in range(0, 360, 45)]
        sole2 = [p + V(0, 0, 0.04) for p in sole]
        g.loft([sole, sole2], "straw", True, True, True).rigid(foot)
        g.band(frame((0.08, y, 0.10), (1, 0, 0), (0.35, 0, 1)), 0.11, 0.14, 0.04, 0.02, "thatch_dark", seg=8).rigid(foot)
    ninja_colliders(k, legs=True)


@kit("ninja_mountain", "ninja")
def ninja_mountain(k):
    ninja_mountain_parts(k)
    hachimaki(k, "snow_shade", knot_color="rock", length=0.55)
    tekko(k, "rock_dark", band_color="rope")


@kit("ninja_mountain_elite", "ninja")
def ninja_mountain_elite(k):
    ninja_mountain_parts(k)
    hachimaki(k, "cloth_red", knot_color="wood_red", length=0.55)
    tekko(k, "rock_dark", band_color="rope")
    oni_menpo(k)
    sode(k, "wood_red")


# ---------------------------------------------------------------------------- lago (Kohan)
def kasa(k, band=None):
    """Sombrero cónico de paja (sugegasa): el disco ancho es lo que se ve del ninja del lago desde arriba."""
    g = k.geo
    M = frame((0.02, -0.02, 2.70), (1, 0, 0.10), (-0.10, 0, 1))      # un poco caído hacia adelante
    prof = [(0.00, 0.80), (0.035, 0.79), (0.13, 0.58), (0.25, 0.33), (0.33, 0.14)]
    woven = lambda a, j: ("straw", "thatch_light")[j % 2] if a > 0 else "thatch"
    g.apex_cone(M, prof, 0.38, "straw", sides=16, colors=woven).rigid("Cabeza")
    # cara de abajo (oscura) y una vincha interior
    under = [M @ V(math.cos(2 * math.pi * j / 16) * 0.79, math.sin(2 * math.pi * j / 16) * 0.79, 0.0) for j in range(16)]
    g.poly(list(reversed(under)), "thatch_dark").rigid("Cabeza")
    if band:
        g.band(M @ Matrix.Translation((0, 0, 0.10)), 0.645, 0.645, 0.11, 0.02, band, seg=16, rx2=0.525, ry2=0.525).rigid("Cabeza")
    g.cone(M @ Matrix.Translation((0, 0, 0.33)), 0.06, 0.03, 0.08, "wood", sides=6).rigid("Cabeza")
    # barbijo: dos cordones bajo el mentón
    for s in (-1, 1):
        g.ribbon([M @ V(0.12, s * 0.30, 0.0), V(0.20, -0.02 + s * 0.27, 2.40), V(0.30, -0.02 + s * 0.12, 2.18), V(0.33, -0.02, 2.13)],
                 0.035, 0.012, "wood_dark", up=(1, 0, 0)).rigid("Cabeza")


def net_shawl(k, c=(-0.02, -0.02), top=2.05, rtop=(0.28, 0.31), rmid=(0.43, 0.51), bot_front=1.64, bot_side=1.93,
              n=8, color="trunk", float_color="flower_white", allow=None, rows=4):
    """Red de pescar sobre los hombros: rombos de cuerda (no un paño) con borde de soga y boyas."""
    g = k.geo
    allow = allow or {"EspaldaAlta", "Hombro.L", "Hombro.R"}

    def surf(a, v):
        # v 0 (cuello) .. 1 (borde): el borde sube a los costados (por los brazos) y baja adelante y atrás
        zb = lerp(bot_front, bot_side, abs(math.sin(math.radians(a))) ** 2)
        z = lerp(top, zb, v)
        rx = lerp(rtop[0], rmid[0], math.sqrt(v)); ry = lerp(rtop[1], rmid[1], math.sqrt(v))
        return ell(c, rx, ry, a, z)
    step = 360.0 / n
    for d in (1, -1):
        for i in range(n):
            pts = [surf(i * step + d * step * (r / rows) * 1.0, r / rows) for r in range(rows + 1)]
            g.tube(pts, 0.022, color, sides=3).body(allow)
    # borde de soga y boyas blancas en el borde
    edge = [surf(a, 1.0) for a in range(0, 361, 15)]
    g.tube(edge, 0.03, "rope", sides=4, cap0=False, cap1=False).body(allow)
    for i in range(6):
        a = 360 * (i + 0.25) / 6
        p = surf(a, 1.0) + V(0, 0, -0.04)
        g.ico(frame(p, (1, 0, 0), (0, 0, 1)), (0.05, 0.05, 0.05), float_color, subdiv=0).body(allow)


def lake_obi(k, color="water_shallow", foam="water_foam"):
    """Faja turquesa con faldón cortado en ola (se mueve) y moño atrás."""
    g = k.geo
    M = frame((-0.01, -0.02, 1.37), (1, 0, 0), (0, 0, 1))
    g.band(M, 0.39, 0.41, 0.17, 0.05, color, seg=14).body({"EspaldaBaja", "Root", "EspaldaAlta"})
    g.box(frame((-0.42, -0.02, 1.37), (1, 0, 0), (0, 0, 1)), (0.10, 0.20, 0.15), "water_deep", chamfer=0.03).rigid("EspaldaBaja")
    # faldón con el borde cortado en olas (el mismo del sumo del lago, a escala del ninja)
    wave_apron(k, "Flap", "EspaldaBaja", (0.41, -0.02, 1.30), 0.30, 0.44, color=color, foam=foam, normal=(1, 0, 0), cols=4)


def ukidama(k, at, bone, r=0.10):
    """Boya de vidrio que brilla (el turquesa del agua): de noche identifica a los del lago. Cuelga y se balancea."""
    g = k.geo
    at = V(at)
    k.chain("Float", bone, [at, at + V(0, 0, -0.16), at + V(0, 0, -0.16 - r * 2)])
    c = at + V(0, 0, -0.16 - r)
    g.ico(frame(c, (1, 0, 0), (0, 0, 1)), (r, r, r * 1.05), "glow_water", subdiv=1).chain("Float")
    for a in (0, 60, 120):
        M = frame(c, (1, 0, 0), (0, 0, 1)) @ Matrix.Rotation(math.radians(a), 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'X')
        g.band(M, r + 0.012, r + 0.012, 0.018, 0.012, "rope", seg=8).chain("Float")
    g.tube([at, at + V(0, 0, -0.16)], 0.012, "rope", sides=3).chain("Float")


def harpoon(k, base_pt, tip_pt, bone="EspaldaAlta"):
    """Arpón de pesca (mori) cruzado en la espalda: la punta de hierro asoma sobre el hombro."""
    g = k.geo
    a, b = V(base_pt), V(tip_pt)
    ax = (b - a).normalized()
    g.tube([a, b], 0.03, "wood", sides=5).rigid(bone)
    for t in (0.18, 0.62):
        p = a.lerp(b, t)
        g.tube([p - ax * 0.05, p + ax * 0.05], 0.038, "rope", sides=5).rigid(bone)
    side = ax.cross(V(1, 0, 0)).normalized()
    head = [b, b + ax * 0.08, b + ax * 0.30]
    g.tube(head, [0.035, 0.03, 0.006], "iron_light", sides=4, cap1=False).rigid(bone)
    for s in (-1, 1):
        root = b + ax * 0.10
        g.tube([root, root + side * s * 0.07 + ax * 0.02, root + side * s * 0.05 - ax * 0.08], [0.018, 0.016, 0.004], "iron_light",
               sides=3, cap1=False).rigid(bone)


def ninja_lake_parts(k, elite=False):
    kasa(k, band="cloth_red" if elite else "water_deep")
    net_shawl(k)
    lake_obi(k)
    ukidama(k, (-0.24, -0.38, 1.30), "EspaldaBaja")        # cadera izquierda atrás: lejos del kunai y de la mano
    harpoon(k, (-0.47, 0.33, 1.12), (-0.49, -0.36, 2.52))
    ninja_colliders(k, legs=True)


@kit("ninja_lake", "ninja")
def ninja_lake(k):
    ninja_lake_parts(k)
    tekko(k, "water_deep", band_color="water_foam")


@kit("ninja_lake_elite", "ninja")
def ninja_lake_elite(k):
    ninja_lake_parts(k, elite=True)
    tekko(k, "water_deep", band_color="water_foam")
    oni_menpo(k)
    sode(k, "wood_red")


# ---------------------------------------------------------------------------- bambú (Take)
def slat_plate(k, c, rx, ry, a0, a1, z0, z1, n, colors=("bamboo", "bamboo_light"), node="bamboo_dark", depth=0.03,
               weight=None, gap=0.12):
    """Placa de cañas verticales siguiendo una elipse: cada caña es un prisma de 5 caras con su nudo."""
    g = k.geo
    parts = []
    for i in range(n):
        a = lerp(a0, a1, (i + 0.5) / n)
        w = math.radians(a1 - a0) / n * (rx + ry) / 2 * (1 - gap)
        p0 = ell(c, rx, ry, a, z0); p1 = ell(c, rx, ry, a, z1)
        mid = p0.lerp(p1, 0.55)
        col = colors[i % len(colors)]
        out = (p0 - V(c[0], c[1], z0)).normalized()
        # 'up' = hacia afuera: el lado ancho de la caña queda tangente a la placa y el espesor es radial
        for q0, q1, cc in ((p0, mid - (p1 - p0).normalized() * 0.015, col), (mid + (p1 - p0).normalized() * 0.015, p1, col)):
            parts.append(g.tube([q0, q1], w / 2, cc, sides=4, sy=depth / w * 2, up=out, phase=45))
        parts.append(g.tube([mid - (p1 - p0).normalized() * 0.016, mid + (p1 - p0).normalized() * 0.016], w / 2 + 0.008, node, sides=4,
                            sy=(depth + 0.016) / (w + 0.016), up=out, phase=45))
    idx = [i for p in parts for i in p.idx]
    p = K.Part(g, idx)
    if weight:
        p.fn(weight)
    return p


def leaf(g, base, direction, length, width, color, normal=(1, 0, 0), bend=0.0, mid=None):
    """Hoja de bambú: lanceolada, con nervio central (dos caras con un quiebre) y punta curvada."""
    base = V(base); d = V(direction).normalized(); nrm = V(normal).normalized()
    side = d.cross(nrm).normalized()
    nrm = side.cross(d).normalized()
    n = 6
    left, right, ridge = [], [], []
    for i in range(n + 1):
        t = i / n
        w = width * math.sin(math.pi * min(1.0, t * 1.15)) * (1 - 0.15 * t)
        p = base + d * length * t + nrm * bend * t * t * length
        left.append(p - side * w / 2); right.append(p + side * w / 2); ridge.append(p + nrm * 0.012)
    L = g.add(left); R = g.add(right); M = g.add(ridge)
    B = g.add([p - nrm * 0.012 for p in ridge])
    mc = mid or color
    for i in range(n):
        g.face((L[i], L[i + 1], M[i + 1], M[i]), color)
        g.face((M[i], M[i + 1], R[i + 1], R[i]), mc)
        g.face((L[i + 1], L[i], B[i], B[i + 1]), "leaf_dark")
        g.face((R[i], R[i + 1], B[i + 1], B[i]), "leaf_dark")
    return K.Part(g, L + R + M + B)


def leaf_mask(k, cols=("leaf", "leaf_light"), dark="leaf_dark"):
    """Máscara de hojas: cubre de la nariz al mentón y abre puntas hacia las sienes, dejando los ojos libres."""
    g = k.geo
    parts = []
    # base: media máscara curva
    M = frame((0.03, -0.02, 2.29), (1, 0, 0), (0, 0, 1))
    parts.append(g.band(M, 0.37, 0.33, 0.21, 0.035, cols[0], seg=12, a0=-70, a1=70, rx2=0.40, ry2=0.35))
    # hoja central (nariz) y dos por mejilla, más dos que suben a las sienes enmarcando los ojos
    parts.append(leaf(g, (0.41, -0.02, 2.18), (0.15, 0, 1), 0.25, 0.08, cols[1], normal=(1, 0, 0), mid=cols[0]))
    for s in (-1, 1):
        parts.append(leaf(g, (0.37, -0.02 + s * 0.10, 2.20), (0.25, s * 0.95, 0.25), 0.30, 0.12, cols[0], normal=(1, s * 0.3, 0), mid=cols[1]))
        parts.append(leaf(g, (0.28, -0.02 + s * 0.22, 2.36), (-0.05, s * 0.45, 1.0), 0.36, 0.11, cols[1], normal=(1, s * 0.6, 0), bend=0.06, mid=cols[0]))
    idx = [i for p in parts for i in p.idx]
    K.Part(g, idx).rigid("Cabeza")


def topknot_leaves(k, streamer="bamboo_light"):
    """Moño negro con atadura verde, dos hojitas paradas y dos hojas largas que flamean (lo que se mueve)."""
    g = k.geo
    top = V(-0.06, -0.02, 2.90)
    g.ico(frame(top + V(0, 0, 0.05), (1, 0, 0), (0, 0, 1)), (0.10, 0.09, 0.08), "black", subdiv=1).rigid("Cabeza")
    g.band(frame(top + V(0, 0, 0.0), (1, 0, 0), (0, 0, 1)), 0.075, 0.07, 0.05, 0.02, "bamboo", seg=8).rigid("Cabeza")
    for s in (-1, 1):
        leaf(g, top + V(0.02, s * 0.03, 0.10), (0.3, s * 0.4, 1), 0.22, 0.08, "bamboo", normal=(1, 0, 0), bend=-0.1).rigid("Cabeza")
    for name, s in (("LeafA", 1), ("LeafB", -1)):
        pts = [top + V(-0.08, s * 0.04, 0.02), top + V(-0.24, s * 0.09, -0.12), top + V(-0.36, s * 0.15, -0.34),
               top + V(-0.44, s * 0.20, -0.58), top + V(-0.48, s * 0.24, -0.80)]
        k.chain(name, "Cabeza", pts)
        rows = []
        for i in range(len(pts) - 1):
            for t in (0.0, 0.5):
                rows.append(pts[i].lerp(pts[i + 1], t))
        rows.append(pts[-1])
        nn = len(rows)
        widths = [0.03 + 0.06 * math.sin(math.pi * min(1.0, (i + 1.0) / nn)) for i in range(nn)]
        widths[-1] = 0.012
        g.ribbon(rows, widths, 0.014, streamer, up=(-1, 0, 0.3)).chain(name)


def kusazuri(k, colors=("bamboo", "bamboo_light"), node="bamboo_dark"):
    """Cuatro faldones de cañas colgando de la faja: cada uno un hueso que pivota (se mecen con las piernas)."""
    g = k.geo
    C = (-0.01, -0.02)
    for name, a in (("TassetFL", 40), ("TassetFR", -40), ("TassetBL", 140), ("TassetBR", 220)):
        top = ell(C, 0.42, 0.44, a, 1.29)
        bot = ell(C, 0.50, 0.52, a, 0.92)
        k.chain(name, "EspaldaBaja", [top, bot])
        n = 3
        span = 30
        p = slat_plate(k, C, 0.45, 0.47, a - span / 2, a + span / 2, 1.29, 0.93, n, colors, node, depth=0.035, gap=0.08)
        # el faldón se abre hacia abajo
        for i in p.idx:
            v = g.v[i]
            u = (1.29 - v.z) / 0.36
            out = (V(v.x, v.y, 0) - V(C[0], C[1], 0)).normalized()
            g.v[i] = v + out * 0.06 * u
        p.chain(name)
        cord = [ell(C, 0.455, 0.475, a + d, 1.24) for d in (-span / 2, 0, span / 2)]
        g.tube(cord, 0.015, "leaf_pine_dark", sides=3).chain(name)


def ninja_bamboo_parts(k, elite=False):
    g = k.geo
    C = (-0.01, -0.02)
    allow = {"EspaldaAlta", "EspaldaBaja", "Root"}
    w = lambda p: k.char.body_weights(p, allow)
    slat_plate(k, C, 0.38, 0.38, -62, 62, 1.52, 2.00, 8, weight=w)          # peto
    slat_plate(k, C, 0.38, 0.38, 128, 232, 1.52, 2.00, 7, weight=w)         # espaldar
    for z in (1.62, 1.90):
        for a0, a1 in ((-64, 64), (126, 234)):
            pts = [ell(C, 0.405, 0.405, lerp(a0, a1, t / 6), z) for t in range(7)]
            g.tube(pts, 0.016, "leaf_pine_dark", sides=3, cap0=False, cap1=False).fn(w)
    # tirantes sobre los hombros
    for s in (-1, 1):
        pts = [ell(C, 0.39, 0.39, 40 * s, 2.00), V(0.10, -0.02 + s * 0.24, 2.10), V(-0.12, -0.02 + s * 0.24, 2.10), ell(C, 0.39, 0.39, 180 - 40 * s, 2.00)]
        g.tube(pts, 0.02, "leaf_pine_dark", sides=3).body({"EspaldaAlta", "Hombro.L", "Hombro.R"})
    # faja verde-negra
    g.band(frame((-0.01, -0.02, 1.37), (1, 0, 0), (0, 0, 1)), 0.39, 0.41, 0.16, 0.05, "leaf_pine_dark", seg=14
           ).body({"EspaldaBaja", "Root", "EspaldaAlta"})
    g.box(frame((0.41, -0.02, 1.37), (1, 0, 0), (0, 0, 1)), (0.06, 0.14, 0.12), "bamboo_dark", chamfer=0.02).rigid("EspaldaBaja")
    kusazuri(k)
    if elite:
        sode(k, "wood_red")
        leaf_mask(k, cols=("maple", "maple_orange"))
    else:
        sode(k, "bamboo", slats=True)
        leaf_mask(k)
    topknot_leaves(k)
    # cantimplora de caña en la cadera
    a = V(0.05, 0.40, 0.98); b = V(0.02, 0.43, 1.30)
    g.tube([a, b], 0.065, "bamboo", sides=6).rigid("Root")
    for t in (0.35, 0.8):
        p = a.lerp(b, t)
        g.tube([p - (b - a).normalized() * 0.015, p + (b - a).normalized() * 0.015], 0.072, "bamboo_dark", sides=6).rigid("Root")
    ninja_colliders(k, legs=True)


@kit("ninja_bamboo", "ninja")
def ninja_bamboo(k):
    ninja_bamboo_parts(k)
    tekko(k, "leaf_pine_dark", band_color="bamboo")


@kit("ninja_bamboo_elite", "ninja")
def ninja_bamboo_elite(k):
    ninja_bamboo_parts(k, elite=True)
    tekko(k, "leaf_pine_dark", band_color="bamboo")


# ============================================================================ SUMO (mira a +Y, su izquierda es -X)
# cabeza z 3.70..4.90 (pelo y chonmage hasta 5.04; motoyui en y -0.34..-0.12, z 4.76..5.02), cara al frente y 0.59
# panza z 2.30: x ±1.18, y -0.47..0.82; mawashi z 1.01..2.45 (cinto 1.69..2.45, x ±1.22, atrás y -1.29)
# brazos en T sobre X a z 3.3 (Brazo 0.81..1.66, Antebrazo ..2.26); piernas x ±0.53..1.0; pies con IK (pie.L/R)
SC = (0.0, -0.18)              # centro de la cintura


def sumo_colliders(k):
    k.collider("Head", "Cabeza", (0.0, -0.10, 4.30), 0.66)
    k.collider("Belly", "Torso", (0.0, -0.10, 2.65), 1.12)
    k.collider("ThighL", "Pierna.L", (0.78, -0.10, 1.20), 0.46)
    k.collider("ThighR", "Pierna.R", (-0.78, -0.10, 1.20), 0.46)


def ribbon_tails(k, prefix, parent, knot, color, path, width=0.10):
    """Moño con dos colas sueltas (cadenas). path: puntos de la cola A relativos al nudo (la B es su espejo en X)."""
    g = k.geo
    knot = V(knot)
    g.ico(frame(knot, (1, 0, 0), (0, 0, 1)), (0.09, 0.07, 0.07), color, subdiv=0).rigid(parent)
    for s in (-1, 1):
        g.box(frame(knot + V(s * 0.09, 0, 0.01), (s, 0, 0.3), (0, 1, 0)), (0.12, 0.05, 0.07), color, taper=0.6).rigid(parent)
    for name, s in ((prefix + "A", 1), (prefix + "B", -1)):
        pts = [knot + V(s * 0.03, 0, -0.02)] + [knot + V(s * q[0], q[1], q[2]) for q in path]
        k.chain(name, parent, pts)
        rows = []
        for i in range(len(pts) - 1):
            for t in (0.0, 0.5):
                rows.append(pts[i].lerp(pts[i + 1], t))
        rows.append(pts[-1])
        n = len(rows)
        widths = [width - width * 0.35 * i / (n - 1) for i in range(n)]
        widths[-1] = width * 0.3
        g.ribbon(rows, widths, 0.02, color, up=(0, -1, 0.3)).chain(name)


SUMO_KNOT = (0.0, -0.36, 4.98)                                          # sobre el motoyui, arriba del chonmage
SUMO_TAIL = [(0.05, -0.26, -0.14), (0.09, -0.44, -0.40), (0.12, -0.52, -0.66)]  # bajan pegadas al pelo de la nuca


def wraps(k, bone, t0, t1, r0, r1, color, band=None, n=3, off=(0, 0, 0)):
    """Vendas en vueltas sobre un hueso (muñecas, antebrazos, tobillos): anillos escalonados."""
    g = k.geo
    a, b = k.char.bone_head(bone), k.char.bone_tail(bone)
    ax = (b - a).normalized()
    for i in range(n):
        t = lerp(t0, t1, i / max(1, n - 1))
        r = lerp(r0, r1, i / max(1, n - 1))
        col = band if (band and i == n // 2) else color
        g.band(frame(a.lerp(b, t) + V(off), ax.orthogonal(), ax), r, r, (t1 - t0) / n * (b - a).length * 1.05, 0.03, col, seg=8).rigid(bone)


def belt_pt(k, a, z, r, rx=1.30, ry=1.16):
    """Punto del cinto que abraza la panza (el mismo cálculo que rope_ring con hug): nudos y colgantes."""
    return k.char.hug(SC, a, z, r * 0.8, (ell(SC, rx, ry, a, z) - V(SC[0], SC[1], z)).length)


def laid_rope(k, path, R, colors=("cloth_white", "plaster", "plaster_shade"), strands=3, pitch=0.6, per_turn=6, sides=5,
              closed=True):
    """Soga torcida de verdad: 'strands' cordones que se enroscan alrededor del eje sobre un alma oscura (los surcos).
    Un tubo con caras pintadas se leía como un flotador; con cordones la diagonal de la soga se ve hasta de lejos.
    colors: los cordones alternan los dos primeros; el tercero es el alma (la sombra entre cordones)."""
    g = k.geo
    path = [V(p) for p in path]
    if closed and (path[0] - path[-1]).length > 1e-6:
        path.append(path[0].copy())
    lens = [(path[i + 1] - path[i]).length for i in range(len(path) - 1)]
    L = sum(lens)
    turns = max(1, round(L / pitch))
    n = turns * per_turn
    up = V(0, 0, 1)

    def at(d):
        for i, ln in enumerate(lens):
            if d <= ln or i == len(lens) - 1:
                t = min(1.0, d / max(ln, 1e-9))
                return path[i].lerp(path[i + 1], t), (path[i + 1] - path[i]).normalized()
            d -= ln
    parts = [g.tube(path, R * 0.6, colors[2], sides=6, cap0=not closed, cap1=not closed)]
    for st in range(strands):
        pts = []
        for i in range(n + 1):
            p, t = at(L * i / n)
            side = t.cross(up)
            if side.length < 1e-4:
                side = t.orthogonal()
            side.normalize()
            nr = side.cross(t).normalized()
            th = 2 * math.pi * (i / per_turn + st / strands)
            pts.append(p + (side * math.cos(th) + nr * math.sin(th)) * R * 0.48)
        parts.append(g.tube(pts, R * 0.56, colors[st % 2], sides=sides, cap0=not closed, cap1=not closed))
    return K.Part(g, [i for q in parts for i in q.idx])


def sumo_tsuna(k, z, rx, ry, r, seg=28):
    """Tsuna del yokozuna: soga blanca de tres cordones que se apoya en el mawashi (sin aire entre soga y cuerpo)."""
    pts = [k.char.hug(SC, 360 * i / seg, z, r * 0.75, (ell(SC, rx, ry, 360 * i / seg, z) - V(SC[0], SC[1], z)).length)
           for i in range(seg)]
    return laid_rope(k, pts, r, pitch=0.62)


# piel de abrigo: blancos cálidos (bajo la luna fría los azulados se leían hielo), la sombra en gris cálido,
# el revés de cuero oscuro y la nieve solo en las caras que miran arriba
FUR = ("cloth_white", "plaster", "cloth_white", "plaster_shade")


def tuft(g, p, out, rnd, length, radius, colors=FUR, n=3):
    """Mechón de piel: n conos finos que salen de p hacia afuera y abajo, abiertos en abanico (silueta peluda)."""
    up = V(0, 0, 1)
    side = out.cross(up)
    if side.length < 1e-4:
        side = out.orthogonal()
    side.normalize()
    parts = []
    for j in range(n):
        spread = (j - (n - 1) / 2) * 0.55 + rnd.uniform(-0.15, 0.15)
        d = (out * 0.75 - up * (0.65 + rnd.uniform(-0.15, 0.25)) + side * spread).normalized()
        ln = length * rnd.uniform(0.75, 1.15)
        col = colors[(j + rnd.randint(0, 3)) % len(colors)]
        parts.append(g.cone(frame(p, d.orthogonal(), d), radius * rnd.uniform(0.8, 1.1), 0.0, ln, col, sides=4, cap1=False))
    return K.Part(g, [i for q in parts for i in q.idx])


def fur_mantle(k, c, z_top, z_bot, r_top, r_bot, clumps=26, seed=21):
    """Manto de piel sobre hombros y espalda: una base gruesa y encima mechones de conos finos apoyados en la piel,
    abierto adelante para que se vea el pecho; el borde de abajo cuelga en flecos."""
    g = k.geo
    ch = k.char
    allow = {"Torso", "Hombro.L", "Hombro.R"}
    rnd = random.Random(seed)
    M = frame((c[0], c[1], (z_top + z_bot) / 2), (1, 0, 0), (0, 0, 1))
    h = z_top - z_bot
    # perfil de la banda: afuera, arriba (nieve), adentro (cuero), abajo
    fur = lambda a, j: ("cloth_white", "snow", "trunk", "plaster_shade")[a]
    # base: herradura abierta adelante (el frente es +Y = 90°: el arco va de 125° a 415° = 55°)
    g.band(M, r_bot[0], r_bot[1], h, 0.30, "cloth_white", seg=16, rx2=r_top[0], ry2=r_top[1], a0=125, a1=415, jitter=0.07,
           seed=seed, colors=fur).body(allow)
    for i in range(clumps):
        a = 125 + 290 * (i + rnd.uniform(0.1, 0.9)) / clumps
        zz = lerp(z_bot + 0.10, z_top + 0.02, rnd.random())
        u = (zz - z_bot) / h
        p = ell(c, lerp(r_bot[0], r_top[0], u) + 0.05, lerp(r_bot[1], r_top[1], u) + 0.05, a, zz)
        p = ch.surface(p, 0.12)
        out = (p - V(c[0], c[1], p.z)).normalized()
        tuft(g, p, out, rnd, 0.42, 0.13).body(allow)
    # flecos colgando del borde
    for i in range(18):
        a = 128 + 284 * (i + 0.5) / 18
        p = ch.surface(ell(c, r_bot[0], r_bot[1], a, z_bot + 0.04), 0.10)
        out = (p - V(c[0], c[1], p.z)).normalized()
        tuft(g, p, out, rnd, 0.34, 0.11, n=2).body(allow)


def sumo_default_parts(k, ribbon="cloth_red", tape="cloth_white"):
    ribbon_tails(k, "Tie", "Cabeza", SUMO_KNOT, ribbon, SUMO_TAIL, width=0.13)
    for side in ("L", "R"):
        wraps(k, "Antebrazo." + side, 0.62, 0.95, 0.27, 0.25, tape)


@kit("sumo_default", "sumo")
def sumo_default(k):
    sumo_default_parts(k)
    sumo_colliders(k)


@kit("sumo_mountain", "sumo")
def sumo_mountain(k):
    g = k.geo
    fur_mantle(k, (0.0, -0.20), 3.86, 3.15, (0.66, 0.62), (1.14, 1.08))
    # soga de paja gruesa sobre el mawashi, nudo grande adelante y dos borlas con mechón blanco (se mueven)
    rope_ring(k, SC, 1.30, 1.16, 2.30, 0.12, seg=24, hug=True).body({"Root", "Torso"})
    front = belt_pt(k, 90, 2.30, 0.12)
    g.ico(frame(front + V(0, 0.08, 0), (1, 0, 0), (0, 0, 1)), (0.20, 0.14, 0.17), "rope", subdiv=1, jitter=0.1).rigid("Root")
    for name, x in (("TasselL", -0.16), ("TasselR", 0.16)):
        top = front + V(x, 0.12, -0.10)
        pts = [top, top + V(x * 0.3, 0.04, -0.30), top + V(x * 0.5, 0.06, -0.62)]
        k.chain(name, "Root", pts)
        g.tube(pts, [0.06, 0.055, 0.05], "rope", sides=5, twist=40).chain(name)
        g.ico(frame(pts[-1] + V(0, 0, -0.10), (1, 0, 0), (0, 0, 1)), (0.12, 0.12, 0.16), "cloth_white", subdiv=1, jitter=0.2).chain(name)
    for i, x in enumerate((-0.55, 0.55)):
        top = belt_pt(k, 90 - x * 70, 2.22, 0.14)
        k.chain(f"Shide{i}", "Root", [top, top + V(0, 0.03, -0.24), top + V(0, 0.05, -0.46)])
        g.zigzag_shide(top, (0, 0.1, -1), (1, 0, 0), 0.11, 4, 0.12, 0.02, "flower_white").chain(f"Shide{i}")
    # antebrazos de cuero con soga, polainas blancas con bandas y puño de piel
    for side in ("L", "R"):
        wraps(k, "Antebrazo." + side, 0.15, 0.9, 0.31, 0.27, "trunk", band="rope", n=4)
        wraps(k, "Tibia." + side, 0.1, 0.85, 0.36, 0.30, "cloth_white", band="wood_dark", n=4)
        a = k.char.bone_head("Tibia." + side)
        g.band(frame(a + V(0, 0, -0.02), (1, 0, 0), (0, 0, 1)), 0.42, 0.40, 0.16, 0.12, "cloth_white", seg=10, jitter=0.08,
               colors=lambda r, j: ("cloth_white", "snow", "trunk", "plaster_shade")[r]).rigid("Tibia." + side)
    sumo_colliders(k)


def lattice_band(k, M, rx, ry, width, n, rows, color="trunk", edge="rope", allow=None, floats=8, float_colors=("flower_white",),
                 drape=0.07):
    """Red de pescar en banda (cruzada al pecho): rombos de cuerda, bordes de soga y boyas. Cada punto se apoya
    sobre la piel ('drape' por encima) para que caiga sobre el hombro y la panza en vez de flotar como un aro."""
    g = k.geo
    ch = k.char

    def P(a, v):
        r = math.radians(a)
        return ch.surface(M @ V(rx * math.cos(r), ry * math.sin(r), v), drape)

    def strand(pts, rr, col, sides, closed=False):
        # subdivide para que la cuerda siga la curva del cuerpo entre nudos
        fine = []
        for i in range(len(pts) - 1):
            for t in (0.0, 0.5):
                fine.append(ch.surface(pts[i].lerp(pts[i + 1], t), drape))
        fine.append(pts[-1])
        g.tube(fine, rr, col, sides=sides, cap0=not closed, cap1=not closed).body(allow)
    step = 360.0 / n
    for d in (1, -1):
        for i in range(n):
            strand([P(i * step + d * step * r / rows, -width / 2 + width * r / rows) for r in range(rows + 1)], 0.03, color, 3)
    for v in (-width / 2, width / 2):
        strand([P(a, v) for a in range(0, 361, 20)], 0.04, edge, 4, closed=True)
    for i in range(floats):
        p = P(360 * (i + 0.3) / floats, -width / 2) + V(0, 0, -0.07)
        g.ico(frame(p, (1, 0, 0), (0, 0, 1)), (0.08, 0.08, 0.08), float_colors[i % len(float_colors)], subdiv=0).body(allow)


def wave_apron(k, name, parent, top, width, length, color="water_shallow", deep="water_deep", foam="water_foam",
               normal=(0, 1, 0), cols=8, waves=True, flare=1.12):
    """Faldón que cuelga de la faja (cadena de 2 huesos: se mece). Con 'waves' la franja de abajo es espuma blanca
    con el borde de arriba festoneado en crestas (el dibujo de ola del concept); se ensancha hacia abajo ('flare')."""
    g = k.geo
    top = V(top); nrm = V(normal).normalized()
    side = V(0, 0, 1).cross(nrm).normalized()
    pts = [top, top + V(0, 0, -length / 2) + nrm * 0.03, top + V(0, 0, -length) + nrm * 0.05]
    k.chain(name, parent, pts)
    nr = 5
    grid = []
    for i in range(nr):
        u = i / (nr - 1)
        c = pts[0].lerp(pts[-1], u)
        w = width * lerp(1.0, flare, u)
        row = []
        for j in range(cols + 1):
            x = -w / 2 + w * j / cols
            dz = 0.0
            if waves and i == nr - 2:
                dz = (0.11 if j % 2 else -0.02) * length          # crestas: el límite turquesa/espuma ondula
            if waves and i == nr - 1:
                dz = (0.02 if j % 2 else -0.03) * length          # el borde de abajo apenas irregular
            row.append(c + side * x + V(0, 0, dz))
        grid.append(row)
    fi = [g.add(r) for r in grid]
    bi = [g.add([p - nrm * 0.04 for p in r]) for r in grid]
    for i in range(nr - 1):
        for j in range(cols):
            col = foam if (waves and i == nr - 2) else color
            g.face((fi[i][j], fi[i + 1][j], fi[i + 1][j + 1], fi[i][j + 1]), col)
            g.face((bi[i][j + 1], bi[i + 1][j + 1], bi[i + 1][j], bi[i][j]), deep)
        for j in (0, cols):
            q = (fi[i][j], bi[i][j], bi[i + 1][j], fi[i + 1][j])
            g.face(q if j == 0 else tuple(reversed(q)), deep)
    for j in range(cols):
        g.face((fi[0][j + 1], bi[0][j + 1], bi[0][j], fi[0][j]), deep)
        g.face((fi[-1][j], bi[-1][j], bi[-1][j + 1], fi[-1][j + 1]), foam if waves else deep)
    K.Part(g, [i for r in fi + bi for i in r]).chain(name)
    return pts


@kit("sumo_lake", "sumo")
def sumo_lake(k):
    g = k.geo
    # red cruzada del hombro izquierdo (-X, arriba) a la cadera derecha (+X, abajo)
    tilt = math.radians(32)
    M = frame((0.0, -0.12, 3.05), (math.cos(tilt), 0, -math.sin(tilt)), (math.sin(tilt), 0, math.cos(tilt)))
    lattice_band(k, M, 1.25, 1.10, 0.70, 14, 3, allow={"Torso", "Hombro.L", "Hombro.R", "Root"}, floats=7)
    # el faldón va por delante de los sagari del modelo (llegan a y 1.06); arriba, un doblez de la faja lo
    # une a la panza para que se lea metido en el mawashi y no como un cartel parado delante
    wave_apron(k, "Apron", "Root", (0.0, 1.13, 2.22), 1.10, 1.25, cols=8)
    g.box(frame((0.0, 0.99, 2.25), (1, 0, 0), (0, 0, 1)), (1.16, 0.32, 0.13), "water_deep", chamfer=0.05).rigid("Root")
    rope_ring(k, SC, 1.28, 1.14, 2.36, 0.07, seg=24, hug=True).body({"Root", "Torso"})
    front = belt_pt(k, 90, 2.36, 0.07)
    g.ico(frame(front + V(0, 0.06, 0), (1, 0, 0), (0, 0, 1)), (0.13, 0.09, 0.11), "rope", subdiv=1, jitter=0.1).rigid("Root")
    ukidama(k, (0.55, -1.38, 2.30), "Root", r=0.17)
    ribbon_tails(k, "Tie", "Cabeza", SUMO_KNOT, "water_shallow", SUMO_TAIL, width=0.13)
    for side in ("L", "R"):
        wraps(k, "Antebrazo." + side, 0.62, 0.95, 0.27, 0.25, "water_foam", band="water_deep")
        wraps(k, "Tibia." + side, 0.45, 0.85, 0.32, 0.30, "cloth_white")
    sumo_colliders(k)


@kit("sumo_bamboo", "sumo")
def sumo_bamboo(k):
    g = k.geo
    # cinturón de caña trenzada verde con nudo y hojas metidas; sagari de cañas que se mecen juntas
    rope_ring(k, SC, 1.29, 1.15, 2.32, 0.10, color="bamboo", dark="bamboo_dark", seg=24, hug=True).body({"Root", "Torso"})
    rope_ring(k, SC, 1.30, 1.16, 2.12, 0.07, color="bamboo_dark", dark="leaf_pine_dark", seg=24, hug=True).body({"Root", "Torso"})
    front = belt_pt(k, 90, 2.30, 0.10)
    g.ico(frame(front + V(0, 0.08, 0), (1, 0, 0), (0, 0, 1)), (0.17, 0.11, 0.14), "bamboo_dark", subdiv=1, jitter=0.1).rigid("Root")
    for s in (-1, 1):
        leaf(g, front + V(s * 0.10, 0.10, 0.06), (s * 0.6, 0.2, 1), 0.62, 0.20, "leaf", normal=(0, 1, 0), bend=-0.08, mid="leaf_light").rigid("Root")
        leaf(g, front + V(s * 0.14, 0.10, 0.00), (s * 1.0, 0.25, 0.25), 0.50, 0.17, "leaf_light", normal=(0, 1, 0), bend=-0.05, mid="leaf").rigid("Root")
    top = front + V(0, 0.14, -0.14)
    k.chain("Chimes", "Root", [top, top + V(0, 0.03, -0.30), top + V(0, 0.05, -0.62)])
    for i in range(7):
        x = (i - 3) * 0.14
        a = top + V(x, 0.0, -0.02 - 0.03 * abs(i - 3)); b = a + V(0, 0.04, -0.62 + 0.06 * abs(i - 3))
        g.tube([a, b], 0.058, "bamboo_dry" if i % 2 else "bamboo", sides=5).chain("Chimes")
        g.tube([a.lerp(b, 0.45), a.lerp(b, 0.5)], 0.066, "bamboo_dark", sides=5).chain("Chimes")
    g.tube([top + V(-0.48, 0, -0.02), top + V(0.48, 0, -0.02)], 0.035, "leaf_pine_dark", sides=4).chain("Chimes")
    ribbon_tails(k, "Tie", "Cabeza", SUMO_KNOT, "bamboo_light", SUMO_TAIL, width=0.12)
    for side in ("L", "R"):
        wraps(k, "Antebrazo." + side, 0.15, 0.9, 0.31, 0.27, "bamboo", band="leaf_pine_dark", n=4)
        wraps(k, "Brazo." + side, 0.35, 0.65, 0.40, 0.38, "leaf_pine", band="bamboo", n=3)
    sumo_colliders(k)


def ginkgo_oicho(k, color="gold", dark="gold_dark"):
    """Ōichō de campeón como hoja de ginkgo dorada: abanico inclinado sobre la cabeza (se lee de frente y de arriba)."""
    g = k.geo
    base = V(0.0, -0.18, 4.98)
    fwd = V(0, 0.28, 0.96).normalized()           # casi parado: de frente se ve la hoja entera sobre la cabeza
    side = V(1, 0, 0)
    up = side.cross(fwd).normalized()
    n = 9
    rim = []
    for j in range(n + 1):
        a = math.radians(-62 + 124 * j / n)
        rr = 0.78 * (1 - 0.06 * math.cos(3 * a))        # borde ondulado de la hoja
        notch = 0.12 if j == n // 2 or j == n // 2 + 1 else 0.0
        rim.append(base + (fwd * math.cos(a) + side * math.sin(a)) * (rr - notch))
    top = [p + up * 0.06 for p in rim]
    bot = [p - up * 0.06 for p in rim]
    c0 = g.add([base + up * 0.04]); c1 = g.add([base - up * 0.04])
    T = g.add(top); B = g.add(bot)
    for j in range(n):
        col = color if j % 2 == 0 else dark
        g.face((c0[0], T[j], T[j + 1]), col)
        g.face((c1[0], B[j + 1], B[j]), dark if j % 2 == 0 else color)
        g.face((T[j], B[j], B[j + 1], T[j + 1]), dark)
    g.face((c0[0], c1[0], B[0], T[0]), dark)
    g.face((c0[0], T[n], B[n], c1[0]), dark)
    K.Part(g, c0 + c1 + T + B).rigid("Cabeza")
    # tallo y atadura blanca
    g.tube([base + V(0, -0.10, -0.02), base + fwd * 0.10], 0.07, "black", sides=6).rigid("Cabeza")
    g.band(frame(base + V(0, -0.04, -0.01), (1, 0, 0), fwd), 0.085, 0.085, 0.06, 0.03, "cloth_white", seg=8).rigid("Cabeza")


def bamboo_crest(g, c, nrm, r, color="gold", bone="Root", chain=None):
    """Emblema del delantal: anillo y tres hojas de bambú con tallo (sin letras)."""
    nrm = V(nrm).normalized()
    side = V(0, 0, 1).cross(nrm).normalized()
    up = nrm.cross(side).normalized()
    M = frame(c, side, nrm)
    parts = [g.band(M, r, r, 0.03, 0.05, color, seg=16)]
    parts.append(g.tube([c - up * r * 0.85 + nrm * 0.01, c + up * r * 0.55 + nrm * 0.01], 0.025, color, sides=4))
    for s, ang, ln in ((0, 0, 0.62), (-1, 50, 0.55), (1, 50, 0.55), (-1, 100, 0.45), (1, 100, 0.45)):
        a = math.radians(ang)
        dvec = up * math.cos(a) + side * s * math.sin(a)
        base = c + up * r * (0.05 if s == 0 else -0.15) + nrm * 0.015
        parts.append(leaf(g, base, dvec, r * ln, r * 0.22, color, normal=nrm, mid="gold_dark"))
    p = K.Part(g, [i for q in parts for i in q.idx])
    return p.chain(chain) if chain else p.rigid(bone)


@kit("ozeki", "sumo")
def ozeki(k):
    g = k.geo
    ginkgo_oicho(k)
    # tsuna blanca de tres cordones con el lazo de dos orejas atrás (lo que se ve del Ōzeki de espaldas)
    sumo_tsuna(k, 2.40, 1.40, 1.24, 0.21).body({"Root", "Torso"})
    back = belt_pt(k, 270, 2.42, 0.21, 1.40, 1.24) + V(0, -0.10, 0.02)
    for s in (-1, 1):
        c = back + V(s * 0.36, -0.06, 0.04)
        loop = [c + V(s * math.cos(t) * 0.34, -0.10 * math.sin(t) ** 2, math.sin(t) * 0.24)
                for t in (2 * math.pi * i / 10 + math.pi for i in range(10))]
        laid_rope(k, loop, 0.11, pitch=0.42, per_turn=5, sides=4).rigid("Root")
    g.ico(frame(back, (1, 0, 0), (0, 0, 1)), (0.20, 0.16, 0.20), "cloth_white", subdiv=1, jitter=0.06).rigid("Root")
    # shide grandes colgando de la tsuna sobre los bordes del delantal (enmarcan el emblema, como en el concept)
    for i, sx in enumerate((-1, 1)):
        for j, x in enumerate((0.60, 0.86)):
            top = V(sx * x, 1.22 + 0.03 * j, 2.27 - 0.03 * j)
            name = f"Shide{i}{j}"
            k.chain(name, "Root", [top, top + V(0, 0.02, -0.38), top + V(0, 0.04, -0.76)])
            g.zigzag_shide(top, (0, 0.05, -1), (sx, 0, 0), 0.15, 5, 0.17, 0.02, "white").chain(name)
    # keshō-mawashi: delantal violeta con borde y flecos dorados y el emblema de bambú
    top = V(0.0, 1.15, 2.22)                       # delante de los sagari del modelo; la tsuna tapa el borde
    W = 1.80
    pts = wave_apron(k, "Apron", "Root", top, W, 1.42, color="cloth_purple", deep="cloth_purple", cols=4, waves=False, flare=1.0)
    # borde dorado, flecos y emblema siguen la cadena del delantal
    for s in (-1, 1):
        g.tube([top + V(s * W / 2, 0.02, 0), pts[1] + V(s * W / 2, 0.02, 0), pts[2] + V(s * W / 2, 0.02, 0.0)], 0.045, "gold", sides=4).chain("Apron")
    hem = pts[2] + V(0, 0.02, 0)
    g.tube([hem + V(-W / 2 - 0.02, 0, 0), hem + V(W / 2 + 0.02, 0, 0)], 0.05, "gold", sides=4).chain("Apron")
    for i in range(14):
        x = -W / 2 + 0.05 + (W - 0.10) * i / 13
        g.box(frame(hem + V(x, 0.0, -0.13), (1, 0, 0), (0, 0, 1)), (0.075, 0.035, 0.24), "gold" if i % 2 else "gold_dark").chain("Apron")
    bamboo_crest(g, pts[0].lerp(pts[2], 0.45) + V(0, 0.05, 0), (0, 1, 0), 0.40, chain="Apron")
    for side in ("L", "R"):
        wraps(k, "Antebrazo." + side, 0.62, 0.95, 0.27, 0.25, "cloth_purple", band="gold")
        wraps(k, "Brazo." + side, 0.45, 0.70, 0.40, 0.38, "cloth_purple", n=2)
        wraps(k, "Tibia." + side, 0.55, 0.85, 0.33, 0.31, "cloth_purple", n=2)
    sumo_colliders(k)


# ============================================================================ KAITO (mira a +X)
@kit("kaito_bandana", "kaito")
def kaito_bandana(k):
    """Las dos colas de la bandana amarilla (el nudo ya está en el modelo, x -0.86 z 2.46)."""
    g = k.geo
    for name, s in (("TailA", 1), ("TailB", -1)):
        pts = [V(-0.80, s * 0.035, 2.44), V(-0.92, s * 0.075, 2.31), V(-1.02, s * 0.12, 2.14),
               V(-1.09, s * 0.16, 1.95), V(-1.13, s * 0.19, 1.76)]
        k.chain(name, "cabeza", pts)
        rows = []
        for i in range(len(pts) - 1):
            for t in (0.0, 0.5):
                rows.append(pts[i].lerp(pts[i + 1], t))
        rows.append(pts[-1])
        n = len(rows)
        widths = [0.15 - 0.05 * (i / (n - 1)) for i in range(n)]
        widths[-1] = 0.04
        # mismo material que la bandana del cuerpo: CharacterKits le pone el material vivo de ese slot (color,
        # emisión del Espíritu y rim iguales a la bandana)
        g.ribbon(rows, widths, 0.024, "mat:AmarilloBandana#ffc21a", up=(-1, 0, 0.3)).chain(name)
    k.collider("Head", "cabeza", (-0.02, 0.0, 2.38), 0.55)
    k.collider("Back", "tronco", (-0.05, 0.0, 1.55), 0.40)


# ============================================================================ build
# escala del modelo en el juego respecto del personaje base (EnemyArchetypes: el Ōzeki es un sumo x1.35)
GAME_SCALE = {"ozeki": 1.35}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"only": None, "export": False, "preview": None, "src": None, "actions": None, "bases": False}
    for i, a in enumerate(argv):
        if a == "--only": o["only"] = argv[i + 1].split(",")
        if a == "--export": o["export"] = True
        if a == "--bases": o["bases"] = True
        if a == "--preview": o["preview"] = argv[i + 1]
        if a == "--src-assets": o["src"] = argv[i + 1]
        if a == "--actions": o["actions"] = argv[i + 1]
    return o


def main():
    o = parse()
    report = {}
    man_path = os.path.join(K.KITS_DIR, "kits.json")
    if os.path.exists(man_path):
        report = json.load(open(man_path))
    if o["preview"] and o["bases"]:
        import preview_kits as PV
        for char in ("ninja", "sumo"):
            ch = K.load_char(char, o["src"], o["actions"] if char == "sumo" else None)
            PV.preview(ch, None, f"{char}_base", o["preview"])
    for name, (char, fn) in KITS.items():
        if o["only"] and name not in o["only"]:
            continue
        ch = K.load_char(char, o["src"], o["actions"] if char == "sumo" else None)
        k = K.Kit(ch, name)
        fn(k)
        obj = k.build()
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        info = {"character": char, "tris": tris, "chains": list(k.chains.keys()),
                "colliders": len(k.colliders), "groups": len(obj.vertex_groups)}
        print(f"KIT {name}: {tris} tris, cadenas {info['chains']}, {info['groups']} huesos")
        if o["preview"]:
            import preview_kits as PV
            recolor_body(ch, BODY_COLORS.get(name, {}))
            PV.preview(ch, obj, name, o["preview"], scale_mul=GAME_SCALE.get(name, 1.0))
        if o["export"]:
            path = os.path.join(K.KITS_DIR, f"Kit_{name}.fbx")
            size = K.export_kit(ch, obj, path)
            info["bytes"] = size
            report[name] = info
            print("ESCRITO", path, size)
    if o["export"]:
        os.makedirs(K.KITS_DIR, exist_ok=True)
        with open(man_path, "w") as f:
            json.dump(report, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
