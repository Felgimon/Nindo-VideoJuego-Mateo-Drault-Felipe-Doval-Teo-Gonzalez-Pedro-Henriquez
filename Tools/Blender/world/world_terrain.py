"""Campo de alturas y colores del terreno de Nindō (todo en coordenadas de juego)."""
import math, random
import world_plan as W

# --------------------------------------------------------------------------- ruido
def _hash(ix, iz, seed=0):
    h = (ix * 374761393 + iz * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def vnoise(x, z, seed=0):
    ix, iz = math.floor(x), math.floor(z)
    fx, fz = x - ix, z - iz
    ux, uz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    a, b = _hash(ix, iz, seed), _hash(ix + 1, iz, seed)
    c, d = _hash(ix, iz + 1, seed), _hash(ix + 1, iz + 1, seed)
    return (a + (b - a) * ux) * (1 - uz) + (c + (d - c) * ux) * uz


def fbm(x, z, seed=0, octaves=4):
    v, a, f = 0.0, 0.5, 1.0
    for i in range(octaves):
        v += a * vnoise(x * f, z * f, seed + i * 17)
        a *= 0.5; f *= 2.03
    return v


def smoothstep(e0, e1, x):
    if e0 == e1:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------- geometría
def seg_dist(px, pz, ax, az, bx, bz):
    vx, vz = bx - ax, bz - az
    L2 = vx * vx + vz * vz
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * vx + (pz - az) * vz) / L2))
    cx, cz = ax + vx * t, az + vz * t
    return math.hypot(px - cx, pz - cz), t


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]; xj, zj = poly[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def poly_dist(x, z, poly):
    d = 1e9
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = min(d, seg_dist(x, z, a[0], a[1], b[0], b[1])[0])
    return d


# alturas en los vértices de los caminos (interpoladas de las áreas que tocan)
def _area_height_at(x, z):
    best, bd = None, 1e9
    for name, ax, az, r, h, soft in W.AREAS:
        d = math.hypot(x - ax, z - az) - r
        if d < bd and h is not None:
            bd, best = d, h
    return best if bd < 4 else None


_PATH_H = []
for name, pts, width, ph in W.PATHS:
    hs = [_area_height_at(x, z) for x, z in pts]
    # rellenar huecos interpolando
    known = [i for i, h in enumerate(hs) if h is not None]
    for i in range(len(hs)):
        if hs[i] is None:
            if not known:
                hs[i] = 0.0
            else:
                lo = max([k for k in known if k < i], default=None)
                hi = min([k for k in known if k > i], default=None)
                if lo is None: hs[i] = hs[hi]
                elif hi is None: hs[i] = hs[lo]
                else:
                    t = (i - lo) / (hi - lo)
                    hs[i] = hs[lo] + (hs[hi] - hs[lo]) * t
    _PATH_H.append(hs)
# la subida al dojo es una rampa recta 0 -> DOJO_H
for i, (name, pts, width, ph) in enumerate(W.PATHS):
    if name == "dojo_subida":
        _PATH_H[i] = [0.0, W.DOJO_H]


def _ground_walk_dist(x, z):
    d = 1e9
    for name, ax, az, r, h, soft in W.AREAS:
        d = min(d, math.hypot(x - ax, z - az) - r)
    for name, pts, width, ph in W.PATHS:
        for i in range(len(pts) - 1):
            sd, _ = seg_dist(x, z, *pts[i], *pts[i + 1])
            d = min(d, sd - width * 0.5)
    return d


# muelles de los santuarios sobre el agua (W.CHECKPOINT_LANDINGS): (x, z, eje largo sa/ca, desde, hasta, medio ancho).
# Tablero de dock_segment: 4 x 2.2 m; el borde transitable queda 5 cm afuera de los tablones, como en la pasarela. La
# punta que toca la pasarela se mete 0.6 m bajo sus tablones: si no, la unión de las dos zonas es un filo de 4 cm y el
# contorno de los límites invisibles puede cerrarla (el muelle quedaba aislado detrás de una pared)
LANDINGS = []
for _pid, _x, _z, _yaw, _sc in W.CHECKPOINT_LANDINGS:
    _sa, _ca = math.sin(math.radians(_yaw)), math.cos(math.radians(_yaw))
    _hl, _hw = 2.0 * _sc, 1.1 * _sc
    _near_neg = _ground_walk_dist(_x - _sa * _hl, _z - _ca * _hl) < _ground_walk_dist(_x + _sa * _hl, _z + _ca * _hl)
    LANDINGS.append((_x, _z, _sa, _ca, -_hl - (0.6 if _near_neg else 0.05), _hl + (0.05 if _near_neg else 0.6), _hw + 0.05))


def landing_dist(x, z):
    """Distancia con signo al tablero de los muelles de santuario (<0 arriba)."""
    d = 1e9
    for lx, lz, sa, ca, u0, u1, hw in LANDINGS:
        u = (x - lx) * sa + (z - lz) * ca
        v = (x - lx) * ca - (z - lz) * sa
        qu, qv = abs(u - (u0 + u1) * 0.5) - (u1 - u0) * 0.5, abs(v) - hw
        d = min(d, math.hypot(max(qu, 0.0), max(qv, 0.0)) + min(max(qu, qv), 0.0))
    return d


def walk_dist(x, z):
    """Distancia con signo al área transitable (<0 adentro)."""
    return min(_ground_walk_dist(x, z), landing_dist(x, z))


def path_info(x, z):
    """(distancia al borde del camino más cercano (<0 adentro), altura del camino, ancho)."""
    best = (1e9, 0.0, 0.0, "")
    for pi, (name, pts, width, ph) in enumerate(W.PATHS):
        hs = _PATH_H[pi]
        for i in range(len(pts) - 1):
            sd, t = seg_dist(x, z, *pts[i], *pts[i + 1])
            d = sd - width * 0.5
            if d < best[0]:
                best = (d, hs[i] + (hs[i + 1] - hs[i]) * t, width, name)
    return best


# áreas de tierra firme que caen dentro del polígono del lago (la orilla): se recortan del lago
_LAND_IN_LAKE = [(ax, az, r) for name, ax, az, r, h, soft in W.AREAS if h is not None and point_in_poly(ax, az, W.LAKE)]


def in_lake(x, z):
    if not point_in_poly(x, z, W.LAKE):
        return False
    for ax, az, r in _LAND_IN_LAKE:
        if (x - ax) ** 2 + (z - az) ** 2 < r * r:
            return False
    return True


def stream_dist(x, z):
    d = 1e9
    for pts, width in W.STREAMS:
        for i in range(len(pts) - 1):
            sd, _ = seg_dist(x, z, *pts[i], *pts[i + 1])
            d = min(d, sd - width * 0.5)
    px, pz, pr = W.POND
    d = min(d, math.hypot(x - px, z - pz) - pr)
    return d


def in_rect(x, z, r, pad=0.0):
    return r[0] - pad <= x <= r[2] + pad and r[1] - pad <= z <= r[3] + pad


def region(x, z):
    """Región artística (para colores/vegetación)."""
    if x < -80 and z > -40: return "montana"   # la montaña está al noroeste (no nevar la colina del hogar)
    if in_lake(x, z) or (x > 86 and z < 60): return "lago"
    if x > 50 and z > 90: return "bambu"
    if z > 95: return "dojo"
    if z < -140: return "hogar"
    if z < -78: return "campos"
    if z < -32: return "bosque"
    return "jardin"


# --------------------------------------------------------------------------- altura
def ground_height(x, z):
    """Altura del suelo transitable/natural (sin colinas exteriores)."""
    wsum, hsum = 0.0, 0.0
    for name, ax, az, r, h, soft in W.AREAS:
        if h is None:
            continue
        d = math.hypot(x - ax, z - az)
        w = smoothstep(r + soft, r * 0.6, d)
        if w > 0:
            wsum += w * 2.0; hsum += w * 2.0 * h
    pd, ph, pw, pname = path_info(x, z)
    w = smoothstep(4.0, -1.0, pd)
    if w > 0:
        wsum += w * 3.0; hsum += w * 3.0 * ph
    base = hsum / wsum if wsum > 0 else 0.0
    if wsum < 1.0:
        # lejos de todo: tender a la altura del borde
        base = base * wsum + (1 - wsum) * base
    return base


def height(x, z):
    reg = region(x, z)
    wd = walk_dist(x, z)
    g = ground_height(x, z)
    h = g
    # micro relieve
    h += (fbm(x * 0.08, z * 0.08, 3) - 0.5) * 0.5 * smoothstep(-6, 2, wd)
    # colinas / acantilados fuera de lo transitable
    if wd > 0:
        rise_max = 26.0 if reg == "montana" else (10.0 if reg in ("bosque", "bambu", "dojo") else 8.0)
        steep = 2.2 if reg == "montana" else 1.5
        n = fbm(x * 0.035, z * 0.035, 11)
        rise = min(wd * steep, rise_max * (0.6 + 0.8 * n))
        rise += (fbm(x * 0.12, z * 0.12, 5) - 0.5) * 2.0 * smoothstep(0, 8, wd)
        h += max(0.0, rise)
    # lago
    if in_lake(x, z):
        ds = poly_dist(x, z, W.LAKE)
        lake_h = W.WATER_LAKE - 0.4 - W.LAKE_DEPTH * smoothstep(0, 14, ds)
        h = min(h, lake_h) if wd > -1 else lake_h
    else:
        ds = poly_dist(x, z, W.LAKE)
        if ds < 5:
            h = min(h, W.WATER_LAKE + 0.15 + ds * 0.12) if wd < 3 else h
    # arroyos y estanque
    sd = stream_dist(x, z)
    if sd < 1.6 and reg == "jardin":
        bed = W.WATER_STREAM - 0.55
        h = min(h, bed + max(0.0, sd + 0.2) * 0.6)
    # arrozales: planos bajos
    for r in W.PADDIES:
        if in_rect(x, z, r):
            h = -0.3
    return h


# --------------------------------------------------------------------------- color
def ramp(x, z, lst, rng, freq=0.035, seed=21, jitter=0.12):
    """Elige un color de una rampa ordenada usando ruido de baja frecuencia: manchas grandes
    y suaves en vez de un mosaico aleatorio por triángulo."""
    n = fbm(x * freq, z * freq, seed)
    t = (n - 0.25) / 0.5 + (rng.random() - 0.5) * jitter
    return lst[int(max(0, min(len(lst) - 1, t * len(lst))))]


GRASS = {
    "hogar": ["grass_dark", "grass", "grass", "grass_light"],
    "campos": ["grass_dark", "grass", "grass", "grass_light", "grass_dry"],
    "bosque": ["grass_dark", "grass_dark", "grass_teal", "moss"],
    "jardin": ["grass_dark", "grass_teal", "grass", "grass", "grass_light"],
    "dojo": ["grass_dark", "moss", "grass", "grass"],
    "lago": ["grass_dark", "grass", "grass", "grass_light"],
    "bambu": ["grass_dark", "moss", "grass", "grass_dry"],
}


def face_color(x, z, h, nz, rng):
    """Color de paleta para un triángulo del terreno (centro x,z, altura h, normal vertical nz)."""
    reg = region(x, z)
    wd = walk_dist(x, z)
    pd, ph, pw, pname = path_info(x, z)
    if in_lake(x, z) and h < W.WATER_LAKE + 0.2:
        return "mud"
    if not in_lake(x, z) and poly_dist(x, z, W.LAKE) < 4 and h < W.WATER_LAKE + 0.9:
        return ramp(x, z, ["path_dark", "sand", "sand"], rng, 0.08)
    sd = stream_dist(x, z)
    if sd < 0.2 and reg == "jardin":
        return "mud"
    if sd < 1.6 and reg == "jardin":
        return ramp(x, z, ["dirt_dark", "moss", "moss"], rng, 0.1)
    for r in W.PADDIES:
        if in_rect(x, z, r):
            return "mud"
        if in_rect(x, z, r, 1.2):
            return "dirt_dark"
    for r in W.WHEAT:
        if in_rect(x, z, r):
            return ramp(x, z, ["dirt_dark", "dirt"], rng, 0.2)
    # patio del dojo: baldosas
    if reg == "dojo" and h > W.DOJO_H - 0.5 and wd < -1:
        cx, cz = math.floor(x / 2.5), math.floor(z / 2.5)
        return "stone_light" if (cx + cz) % 2 == 0 else "stone"
    steep = nz < 0.72
    snowy = reg == "montana" and h > 9.5
    if pd < -0.4:
        if pname == "pasarela_lago":
            return "mud"
        if snowy:
            return ramp(x, z, ["path_dark", "snow_shade", "snow_shade"], rng, 0.08)
        return ramp(x, z, ["path_dark", "path", "path", "path"], rng, 0.07, seed=33, jitter=0.2)
    if pd < 0.6:
        return "snow_shade" if snowy else ramp(x, z, ["dirt", "path_dark"], rng, 0.1)
    if reg == "montana":
        if steep:
            return ramp(x, z, ["rock_dark", "rock", "rock", "rock_light"], rng, 0.06)
        if h > 9.5:
            return "snow" if nz > 0.88 else "snow_shade"
        if h > 6.5:
            # nieve en manchas sobre piedra
            return ramp(x, z, ["stone_moss", "grass_dry", "snow_shade", "snow"], rng, 0.07, seed=5)
        return ramp(x, z, ["grass_dark", "stone_moss", "grass_dry"], rng, 0.05)
    if steep:
        return ramp(x, z, ["rock_brown_dark", "rock_brown", "rock_brown", "stone_moss"], rng, 0.06)
    return ramp(x, z, GRASS.get(reg, GRASS["jardin"]), rng)


# --------------------------------------------------------------------------- límites invisibles
def _zero_on_edge(p1, p2, v1, v2, exact):
    if not exact:
        t = v1 / (v1 - v2) if v1 != v2 else 0.5
        return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
    # bisección sobre walk_dist: una celda gruesa y las finas que comparten la arista dan el mismo punto
    a, b = 0.0, 1.0
    for _ in range(24):
        m = (a + b) * 0.5
        vm = walk_dist(p1[0] + (p2[0] - p1[0]) * m, p1[1] + (p2[1] - p1[1]) * m)
        if (vm < 0) == (v1 < 0):
            a = m
        else:
            b = m
    t = (a + b) * 0.5
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def _fine_boxes(x0, z0, step):
    """Cajas (i0, j0, i1, j1) de la grilla gruesa alrededor de cada muelle: un tablero de 2.2 m de ancho no se resuelve
    con celdas de 2 m, ahí el contorno se saca con celdas de 0.5 m. Margen chico a propósito: si la caja corta un
    detalle que la grilla gruesa no ve (la cuña de agua entre la pasarela y la plataforma de la arena), el contorno
    fino queda con puntas sueltas en el borde de la caja (validate_plan lo revisa)."""
    boxes = []
    for lx, lz, sa, ca, u0, u1, hw in LANDINGS:
        pts = [(lx + sa * u + ca * v, lz + ca * u - sa * v) for u in (u0, u1) for v in (-hw, hw)]
        boxes.append((math.floor((min(p[0] for p in pts) - 0.3 - x0) / step), math.floor((min(p[1] for p in pts) - 0.3 - z0) / step),
                      math.ceil((max(p[0] for p in pts) + 0.3 - x0) / step), math.ceil((max(p[1] for p in pts) + 0.3 - z0) / step)))
    return boxes


def wall_segments(x0, z0, nx, nz, step=2.0, fine=0.5, window=None):
    """Contorno walk_dist = 0 (marching squares) de la grilla de nx x nz celdas de 'step' m con origen (x0, z0): los
    límites invisibles B__limites. window = (xa, za, xb, zb) limita el cálculo a las celdas que lo tocan (validador).
    Fuera de las cajas de los muelles el resultado es el de siempre (interpolación lineal en celdas de 2 m)."""
    boxes = _fine_boxes(x0, z0, step)
    val = {}

    def V(x, z):
        k = (round(x, 4), round(z, 4))
        if k not in val:
            val[k] = walk_dist(x, z)
        return val[k]

    def in_box(x, z):
        return any(x0 + bi0 * step - 1e-6 <= x <= x0 + bi1 * step + 1e-6 and z0 + bj0 * step - 1e-6 <= z <= z0 + bj1 * step + 1e-6
                   for bi0, bj0, bi1, bj1 in boxes)

    segs = []

    def cell(cx, cz, s):
        c = [(cx, cz), (cx + s, cz), (cx + s, cz + s), (cx, cz + s)]
        v = [V(*p) for p in c]
        pts = []
        for k in range(4):
            a, b = k, (k + 1) % 4
            if (v[a] < 0) != (v[b] < 0):
                pts.append(_zero_on_edge(c[a], c[b], v[a], v[b], in_box(*c[a]) and in_box(*c[b])))
        if len(pts) == 2:
            segs.append((pts[0], pts[1]))
        elif len(pts) == 4:
            segs.append((pts[0], pts[1])); segs.append((pts[2], pts[3]))

    def wanted(cx, cz, s):
        return window is None or (cx + s >= window[0] and cx <= window[2] and cz + s >= window[1] and cz <= window[3])

    for j in range(nz):
        for i in range(nx):
            if any(bi0 <= i < bi1 and bj0 <= j < bj1 for bi0, bj0, bi1, bj1 in boxes):
                continue
            if wanted(x0 + i * step, z0 + j * step, step):
                cell(x0 + i * step, z0 + j * step, step)
    n = int(round(step / fine))
    for bi0, bj0, bi1, bj1 in boxes:
        for fj in range((bj1 - bj0) * n):
            for fi in range((bi1 - bi0) * n):
                cx, cz = x0 + bi0 * step + fi * fine, z0 + bj0 * step + fj * fine
                if wanted(cx, cz, fine):
                    cell(cx, cz, fine)
    return segs
