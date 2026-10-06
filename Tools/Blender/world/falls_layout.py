"""Cascada Kohan: el trazado de la herradura de basalto y de sus caídas de agua, sin Blender.

Es la única fuente de los números de la cascada:
  * props/props_falls.py arma con esto la malla del acantilado y escribe en el manifest los labios de
    cada cortina (Unity genera el agua en runtime con FX/KohanFalls.cs a partir de esos puntos);
  * world_plan.py ubica el landmark, los pinos del borde y el santuario del saliente;
  * validate_plan.py chequea que la línea de caída quede fuera de la plataforma y lejos de la pasarela.

Coordenadas: e = este, n = norte, relativos al centro de la herradura H (metros); h = altura sobre el
agua del lago. El prop se coloca con yaw 180 (su frente, la boca de la herradura, mira al sur), así que
en el espacio del prop en Blender x = e, y = n, z = h.
Rumbo b: grados desde el norte, positivo hacia el este.

Por qué la caída está tan cerca (judge_water.json, arena_vfx): con la cámara de combate (pitch 43-47,
distancia 24-31, FOV 30) el borde de arriba de la imagen toca el agua apenas 11-13 m más allá de Kaito.
Una cortina "de fondo" no se vería nunca: el agua cae a ~13 m del centro de la arena (2.4 m pasada la
baranda) y la herradura envuelve la plataforma para que las cintas laterales entren por las esquinas.
"""
import math
import random

HX, HZ = 184.0, 74.0      # centro de la herradura (coordenadas de juego); 2 m al norte del centro de la arena
ARENA = (0.0, -2.0)       # centro de la plataforma de la arena (lake_arena_platform en 184, 72) relativo a H
DECK_R = 10.6             # radio circunscripto de la plataforma (props_structures.build_lake_arena_platform)
LIP_R = 14.5              # radio del borde por donde sale el agua
OUT_R = 25.5              # radio exterior de la herradura
ARM = 84.0                # los brazos llegan hasta +-84° y desde ahí bajan en escalones hasta el lago
STEP_END = 104.0          # último escalón de los brazos
G = 9.81
V0 = 1.2                  # velocidad horizontal del agua al salir del borde (m/s)
WATER_Y = -0.55           # nivel del lago en el juego (world_plan.WATER_LAKE): el prop va a esa altura
SHELF_H = 1.5             # saliente del santuario (pie del brazo oeste, junto al hilo de agua)
SHELF = (-16.4, -1.4)     # centro del saliente (= 167.6, 72.6 en el juego): ~3 m de agua hasta la baranda

# pasarela del lago (último tramo, de 170,56 a 184,72) relativa a H: el acantilado no se le acerca
WALK = ((170.0 - HX, 56.0 - HZ), (184.0 - HX, 72.0 - HZ))


def rim_h(b):
    """Altura del borde según el rumbo: 42 m en el eje, ~28 m a +-47°, ~18 m en los brazos."""
    c = max(0.0, math.cos(math.radians(b)))
    return 18.0 + 24.0 * c ** 2.2


def polar(r, b):
    a = math.radians(b)
    return r * math.sin(a), r * math.cos(a)


def bearing(e, n):
    return math.degrees(math.atan2(e, n))


def walk_dist(e, n):
    (ax, ay), (bx, by) = WALK
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((e - ax) * vx + (n - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(e - ax - vx * t, n - ay - vy * t)


# cortinas: (nombre, rumbo inicial, rumbo final, capas). La principal se parte en tres por dos contrafuertes
# de columnas (se leen como "varias cortinas", como en el arte conceptual); las cintas laterales caen en
# las esquinas superiores del encuadre de combate y los hilos al pie de los brazos.
SHEETS = [
    ("center", -15.0, 15.0, 2),
    ("west", -47.0, -24.0, 2),
    ("east", 24.0, 47.0, 2),
    ("ribbon_w", -67.0, -56.0, 2),
    ("ribbon_e", 56.0, 67.0, 2),
    ("trickle_w", -77.0, -73.0, 1),
    ("trickle_e", 73.0, 77.0, 1),
]
WATER_LIFT = 0.12         # el agua pasa 12 cm por encima del umbral de piedra


def fall_time(h):
    return math.sqrt(2.0 * max(h, 0.01) / G)


def plunge_r(b):
    """Radio (desde H) donde el agua que sale del borde en el rumbo b toca el lago."""
    return LIP_R - V0 * fall_time(rim_h(b) + WATER_LIFT)


def sheet_of(b, margin=0.0):
    for s in SHEETS:
        if s[1] - margin <= b <= s[2] + margin:
            return s
    return None


def plunge_points(step=1.0):
    """[(e, n)] de la línea de caída de todas las cortinas (para el validador y el pozo)."""
    out = []
    for name, b0, b1, layers in SHEETS:
        n = max(2, int(math.ceil((b1 - b0) / step)) + 1)
        for k in range(n):
            b = b0 + (b1 - b0) * k / (n - 1)
            out.append(polar(plunge_r(b), b))
    return out


# =========================================================================== columnas
class Column:
    """Columna hexagonal de basalto. Los vértices del hexágono se guardan para que la malla y los
    chequeos usen exactamente la misma forma. segs = alturas de las juntas (de abajo hacia arriba).
    lean = (grados, rumbo hacia donde se inclina) para tocones quebrados y rocas del pozo."""

    def __init__(self, e, n, R, rot, top, kind, segs=(), tilt=False, recess=0.0, lean=None, base=None):
        self.e, self.n, self.R, self.rot = e, n, R, rot
        self.top = top
        # 'sill' (umbral bajo una cortina), 'buttress', 'stump', 'cell', 'river', 'step', 'shelf', 'rock'
        self.kind = kind
        self.segs = list(segs)
        self.tilt = tilt            # umbral: la tapa sigue rim_h() y el labio del agua queda continuo
        self.recess = recess        # retroceso (m) de la parte de abajo detrás de la cortina
        self.lean = lean
        self.base = base            # None = desde el fondo (bajo el agua)

    def corners(self):
        return [(self.e + self.R * math.cos(self.rot + k * math.pi / 3), self.n + self.R * math.sin(self.rot + k * math.pi / 3))
                for k in range(6)]


def _facing(b):
    """Giro del hexágono para que una CARA (no una arista) mire al centro de la herradura."""
    return math.radians(90.0 - b) + math.pi / 6


def _front_row(rng):
    """Fila del frente: una empalizada de columnas a lo largo del borde, con una cara plana hacia H.
    Bajo cada cortina, umbrales con la tapa inclinada siguiendo rim_h(); entre cortinas, contrafuertes
    más altos que separan las caídas, con tocones quebrados al pie (lo que más se ve desde el juego)."""
    cols = []
    edges = [-ARM]
    for s in sorted(SHEETS, key=lambda s: s[1]):
        edges += [s[1], s[2]]
    edges.append(ARM)
    rc_ref = LIP_R + 1.3
    for i in range(len(edges) - 1):
        b0, b1 = edges[i], edges[i + 1]
        if b1 - b0 < 0.5:
            continue
        under = sheet_of((b0 + b1) * 0.5) is not None
        width = math.radians(b1 - b0) * rc_ref
        n = max(1, int(round(width / 2.6)))
        for k in range(n):
            bb0 = b0 + (b1 - b0) * k / n
            bb1 = b0 + (b1 - b0) * (k + 1) / n
            b = (bb0 + bb1) * 0.5
            w = math.radians(bb1 - bb0) * rc_ref           # ancho tangencial (de esquina a esquina)
            R = max(0.75, w * 0.5)
            if under:
                rc = LIP_R + R * math.sqrt(3) / 2           # la cara plana del frente justo en el borde
                h = rim_h(b)
                # juntas: la de arriba es la "repisa" del borde (sobresale); debajo, el muro retrocede
                segs = [max(1.0, h - 2.6 - rng.uniform(0, 0.8))]
                z = segs[0] - rng.uniform(4.0, 6.5)
                while z > 2.5:
                    segs.insert(0, z)
                    z -= rng.uniform(4.5, 7.0)
                cols.append(Column(*polar(rc, b), R, _facing(b), h - 0.05, "sill", segs, tilt=True, recess=1.3))
            else:
                rc = LIP_R + R * math.sqrt(3) / 2 - rng.uniform(0.15, 0.7)   # los contrafuertes asoman
                # los dos que enmarcan la caída central son pilares altos (de ellos cuelga la shimenawa)
                gate = abs(b0 - 15.0) < 0.01 or abs(b1 + 15.0) < 0.01
                top = rim_h(b) + (rng.uniform(4.6, 5.4) if gate else rng.uniform(1.2, 3.4))
                segs = []
                z = top - rng.uniform(2.5, 5.0)
                while z > 2.0:
                    segs.insert(0, z)
                    z -= rng.uniform(4.0, 7.5)
                cols.append(Column(*polar(rc, b), R, _facing(b), top, "buttress", segs))
                # tocones al pie: columnas quebradas, algunas inclinadas, entre la pared y el pozo
                if rng.random() < 0.85:
                    sb = b + rng.uniform(-0.25, 0.25) * (b1 - b0)
                    if sheet_of(sb, 1.5) is None:
                        sr = rc - R * 0.9 - rng.uniform(0.6, 1.0)
                        st = rng.uniform(2.0, 7.5) if abs(b) < 70 else rng.uniform(1.5, 4.5)
                        cols.append(Column(*polar(sr, sb), R * rng.uniform(0.55, 0.75), _facing(sb) + math.radians(rng.uniform(-20, 20)),
                                           st, "stump", [st * rng.uniform(0.4, 0.6)],
                                           lean=(rng.uniform(3, 14), sb + 180 + rng.uniform(-50, 50))))
    return cols


def _lattice(rng):
    """Detrás de la empalizada: panal de columnas (la meseta escalonada) y los brazos que bajan al lago."""
    cols = []
    R = 1.45
    dx, dy = R * math.sqrt(3), R * 1.5          # hexágonos "de punta" en una grilla fija (como el basalto real)
    for j in range(-30, 30):
        for i in range(-30, 30):
            e = (i + 0.5 * (j & 1)) * dx + 0.37
            n = j * dy + 0.21
            r = math.hypot(e, n)
            b = bearing(e, n)
            ab = abs(b)
            jit = (rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12))
            roll = rng.random()
            if ab <= ARM and LIP_R + 3.05 <= r <= OUT_R:
                h = rim_h(b)
                if ab < 9.0 and r < OUT_R - 1.0:
                    top = h - 0.25            # cauce: el agua (tapa + 0.37) queda al nivel del labio
                    kind = "river"
                else:
                    t = (r - LIP_R - 3.0) / (OUT_R - LIP_R - 3.0)
                    top = h + 0.6 + 3.0 * t + (roll - 0.35) * 1.4
                    # el anillo de afuera baja en escalones: de costado se lee una meseta que se desarma,
                    # no un muro de 45 m parado en el lago
                    edge = max(0.0, r - (OUT_R - 3.2)) / 3.2
                    top -= h * 0.42 * edge ** 1.3
                    top = round(top / 0.6) * 0.6
                    kind = "cell"
                cols.append(Column(e + jit[0], n + jit[1], R - 0.05, math.radians(30), top, kind))
            elif ARM < ab <= STEP_END and LIP_R - 1.4 <= r <= LIP_R + 7.0:
                # brazo que baja en escalones (calzada de gigantes) hasta el lago
                if math.hypot(e - ARENA[0], n - ARENA[1]) < DECK_R + 2.6 or walk_dist(e, n) < 9.0:
                    continue                                   # lejos de la baranda de la arena y de la pasarela
                if any(math.hypot(e - x, n - y) < 2.4 for x, y in _shelf_centres()):
                    continue                                   # ahí va el saliente del santuario
                u = (ab - ARM) / (STEP_END - ARM)
                top = rim_h(ARM) * (1.0 - u) ** 1.5 + (roll - 0.5) * 1.6 - (r - LIP_R) * 0.35
                top = max(0.7, round(top / 1.1) * 1.1)
                cols.append(Column(e + jit[0], n + jit[1], R - 0.05, math.radians(30), top, "step"))
    return cols


def _shelf_centres():
    """Racimo de columnas del saliente: la del centro y cinco alrededor (la del noreste no: ahí está el
    último contrafuerte del brazo)."""
    d = 1.42 * math.sqrt(3)
    out = [SHELF]
    for k in range(6):
        a = math.radians(30 + 60 * k)
        x, y = SHELF[0] + d * math.cos(a), SHELF[1] + d * math.sin(a)
        if k != 0:
            out.append((x, y))
    return out


def _shelf(rng):
    return [Column(x, y, 1.38, math.radians(30), SHELF_H + (0.0 if i == 0 else rng.choice((-0.15, 0.0, 0.0, 0.12))), "shelf")
            for i, (x, y) in enumerate(_shelf_centres())]


# rocas del pozo, en la línea de caída: (rumbo, radio, tamaño, alto sobre el agua). Son columnas de basalto
# caídas (mismo lenguaje que el acantilado) con un collar de espuma que dibuja KohanFalls.
POOL_ROCKS = [(-31.0, 10.6, 2.1, 1.2), (-7.0, 10.0, 1.6, 0.8), (17.0, 10.6, 2.2, 1.3), (37.0, 11.2, 1.5, 0.7)]


def _pool_rocks(rng):
    cols = []
    for b, r, size, ht in POOL_ROCKS:
        e, n = polar(r, b)
        cols.append(Column(e, n, size * 0.5, math.radians(rng.uniform(0, 60)), ht, "rock", [ht * 0.45],
                           lean=(rng.uniform(10, 24), b + rng.uniform(-60, 60)), base=-1.2))
    return cols


_COLS = None


def columns():
    global _COLS
    if _COLS is None:
        rng = random.Random(2207)
        _COLS = _front_row(rng) + _lattice(rng) + _shelf(rng) + _pool_rocks(rng)
    return _COLS


def _point_in(poly, x, y):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def top_at(e, n, cols=None):
    """Altura de la tapa de la columna que contiene (e, n) (None si no hay columna)."""
    best = None
    for c in cols or columns():
        if c.lean is None and _point_in(c.corners(), e, n):
            best = c.top if best is None else max(best, c.top)
    return best


# =========================================================================== pinos y santuario
# pinos del borde: (prop, rumbo, radio, yaw, escala). El torcido se asoma sobre la cortina oeste.
PINES = [
    ("tree_pine_snow_b", -36.0, 22.5, 20.0, 1.0),
    ("tree_pine_snow_a", 31.0, 21.0, 140.0, 0.9),
    ("tree_pine_snow_a", 61.0, 20.0, 250.0, 1.1),
    ("tree_pine_snow_b", -66.0, 21.5, 300.0, 0.85),
    ("pine_falls_lip", -19.5, 15.2, 185.0, 1.4),
]


def pine_spots(cols=None):
    """[(prop, e, n, yaw, escala, altura de la tapa)] — la altura es la de la columna donde apoya."""
    cols = cols or columns()
    out = []
    for prop, b, r, yaw, sc in PINES:
        e, n = polar(r, b)
        h = top_at(e, n, cols)
        out.append((prop, e, n, yaw, sc, h if h is not None else rim_h(b)))
    return out


def game_xz(e, n):
    return HX + e, HZ + n


# santuario del saliente (taki shrine al pie del hilo oeste), relativo al centro del saliente:
# (prop, de, dn, yaw, escala). Mira a la arena (al este); el portal de cuerda queda delante.
SHRINE = [
    ("shrine_small", -0.9, 0.0, 100.0, 0.75),
    ("falls_shrine_gate", 1.9, -0.3, 100.0, 1.0),
    ("lantern_stone", 1.0, -2.2, 100.0, 1.0),
]


def landmarks():
    """Entradas de world_plan.LANDMARKS de la cascada: (prop@altura, x, z, yaw, escala). La altura va fija
    ('@', ver build_world.place) porque todo apoya en el acantilado o en el agua, no en el terreno."""
    out = [(f"kohan_falls_cliff@{WATER_Y}", HX, HZ, 180.0, 1.0)]
    for prop, e, n, yaw, sc, h in pine_spots():
        x, z = game_xz(e, n)
        out.append((f"{prop}@{WATER_Y + h:.2f}", round(x, 2), round(z, 2), yaw, sc))
    for prop, de, dn, yaw, sc in SHRINE:
        x, z = game_xz(SHELF[0] + de, SHELF[1] + dn)
        out.append((f"{prop}@{WATER_Y + SHELF_H:.2f}", round(x, 2), round(z, 2), yaw, sc))
    return out


# shimenawa: cruza la cortina central entre los dos contrafuertes que la enmarcan
ROPE = (-18.5, 18.5, LIP_R - 0.35)


# =========================================================================== datos para Unity
def unity_local(e, n, h):
    """Punto del prop (yaw 180) en el espacio local de Unity del prop (= exportador de nindo_lib)."""
    return [-e, h, -n]


def sheets_for_unity(samples_per_m=0.8):
    """Labios de las cortinas para KohanFalls.cs: puntos en el espacio local de Unity del prop, de oeste a
    este, a la altura por la que pasa el agua. El agua sale hacia el centro de la herradura."""
    out = []
    for name, b0, b1, layers in SHEETS:
        width = math.radians(b1 - b0) * LIP_R
        n = max(3, int(math.ceil(width * samples_per_m)) + 1)
        lip = []
        for k in range(n):
            b = b0 + (b1 - b0) * k / (n - 1)
            e, nn = polar(LIP_R, b)
            lip += unity_local(e, nn, rim_h(b) + WATER_LIFT)
        out.append({"name": name, "lip": [round(v, 3) for v in lip], "layers": layers})
    return out


def plunge_line(step=4.0):
    """Línea de caída de toda la herradura, de oeste a este (también contra la roca, entre cortinas):
    [(e, n, w)] con w = 1 bajo una cortina y 0 donde no cae agua. Es el borde del pozo de espuma."""
    out = []
    k = 0
    while True:
        b = -STEP_END + k * step
        if b > STEP_END + 1e-6:
            break
        e, n = polar(plunge_r(b), b)
        out.append((e, n, 1.0 if sheet_of(b, 1.5) else 0.0))
        k += 1
    return out


# cintas de espuma del desagüe: salen de los extremos del pozo, rodean la plataforma (a más de 11 m del centro
# de la arena) y siguen al sur pasando bajo la pasarela. Línea central (e, n); la del este es la espejada.
RIBBON_W = [(-12.5, -1.3), (-12.9, -6.5), (-11.5, -12.0), (-8.8, -17.0), (-5.5, -22.5), (-2.0, -28.0)]
RIBBON_WIDTH = 3.0


def falls_meta():
    rocks = []
    for b, r, size, ht in POOL_ROCKS:
        e, n = polar(r, b)
        rocks += [round(v, 3) for v in unity_local(e, n, ht)] + [round(size * 0.5, 3)]
    plunge = []
    for e, n, w in plunge_line():
        x, y, z = unity_local(e, n, 0.0)
        plunge += [round(x, 3), round(z, 3), w]
    ribbons = []
    for sign in (1.0, -1.0):
        pts = []
        for e, n in RIBBON_W:
            x, y, z = unity_local(e * sign, n, 0.0)
            pts += [round(x, 3), round(z, 3)]
        ribbons.append({"pts": pts})
    ax, an = ARENA
    return {
        "sheets": sheets_for_unity(),
        "center": unity_local(0.0, 0.0, 0.0),
        "arena": unity_local(ax, an, 0.0),
        "deckRadius": DECK_R,
        "deckHeight": 1.0,          # piso de lake_arena_platform sobre el agua
        "v0": V0,
        # rocas del pozo: x, y, z (punta) y radio, en grupos de 4
        "rocks": rocks,
        # línea de caída completa: x, z (locales) y peso de cortina, en grupos de 3
        "plunge": plunge,
        "ribbons": ribbons,
        "ribbonWidth": RIBBON_WIDTH,
    }


if __name__ == "__main__":
    cs = columns()
    kinds = {}
    for c in cs:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    print("columnas", len(cs), kinds)
    for name, b0, b1, layers in SHEETS:
        for b in (b0, (b0 + b1) / 2, b1):
            e, n = polar(plunge_r(b), b)
            d = math.hypot(e - ARENA[0], n - ARENA[1])
            print(f"{name:10} b={b:6.1f} labio={rim_h(b):5.1f} m  caída {fall_time(rim_h(b)):.2f} s  "
                  f"pozo r={plunge_r(b):5.2f}  a {d:5.2f} m del centro de la arena, {walk_dist(e, n):5.1f} m de la pasarela")
    for s in pine_spots(cs):
        print("pino", s[0], "juego", tuple(round(v, 1) for v in game_xz(s[1], s[2])), "altura", round(s[5], 2))
    print("saliente", game_xz(*SHELF), "tapa", top_at(*SHELF, cs))
