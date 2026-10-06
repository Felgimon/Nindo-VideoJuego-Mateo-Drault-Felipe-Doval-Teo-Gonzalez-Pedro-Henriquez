"""Chequeos del plan del mundo (sin Blender): python3 Tools/Blender/world/validate_plan.py
Cada marcador de gameplay tiene que quedar sobre suelo transitable, fuera del agua (salvo sobre
props flotantes) y lejos de los bordes; los edificios no pueden tapar caminos ni marcadores."""
import glob, json, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world_plan as W
import world_terrain as T

problems = []
WATER_OK = []   # (x, z, r): zonas sobre agua con piso (plataforma de la arena)
for pid, x, z, yaw, sc in W.LANDMARKS:
    if pid.startswith("lake_arena_platform"):
        WATER_OK.append((x, z, 9.2))


# muelles de santuarios (rectángulo de 4 x 2.2 m con el largo según el yaw)
LANDINGS = [(x, z, math.sin(math.radians(yaw)), math.cos(math.radians(yaw)), 2.0 * sc, 1.1 * sc)
            for pid, x, z, yaw, sc in W.CHECKPOINT_LANDINGS]


def on_landing(x, z, pad=0.0):
    return any(abs((x - lx) * sa + (z - lz) * ca) <= hl + pad and abs((x - lx) * ca - (z - lz) * sa) <= hw + pad
               for lx, lz, sa, ca, hl, hw in LANDINGS)


def on_platform(x, z):
    if any(math.hypot(x - a, z - b) < r for a, b, r in WATER_OK) or on_landing(x, z):
        return True
    # sobre la pasarela de tablones
    return any(name == "pasarela_lago" for name in [T.path_info(x, z)[3]]) and T.path_info(x, z)[0] < -0.3


def check(kind, name, x, z, margin=0.8):
    wd = T.walk_dist(x, z)
    if wd > -margin:
        problems.append(f"{kind} {name} ({x},{z}) está a {-wd:.1f} m del borde transitable (wd={wd:.2f})")
    if T.in_lake(x, z) and not on_platform(x, z):
        problems.append(f"{kind} {name} ({x},{z}) cae en el agua")
    # estanque y arroyos (stream_dist < 0 = adentro del agua)
    sd = T.stream_dist(x, z)
    if sd < margin and not on_platform(x, z) and T.path_info(x, z)[0] >= -0.3:
        problems.append(f"{kind} {name} ({x},{z}) cae en el estanque/arroyo (borde a {sd:.1f} m)")
    # pendiente
    h = T.height(x, z)
    sl = max(abs(T.height(x + 1, z) - h), abs(T.height(x, z + 1) - h))
    if sl > 0.6 and not on_platform(x, z):
        problems.append(f"{kind} {name} ({x},{z}) en pendiente fuerte ({sl:.2f} m/m)")


check("Start", "", W.START[0], W.START[1])
# cada muelle: en el lago, con fondo, y con una punta sobre la pasarela (si no, el santuario queda aislado)
for lx, lz, sa, ca, hl, hw in LANDINGS:
    if not T.in_lake(lx, lz) or W.WATER_LAKE - T.height(lx, lz) < 0.5:
        problems.append(f"Muelle ({lx},{lz}) fuera del lago o con poco fondo")
    ends = [(lx + sa * hl * k, lz + ca * hl * k) for k in (-1, 1)]
    if not any(T.path_info(ex, ez)[3] == "pasarela_lago" and T.path_info(ex, ez)[0] < 0.3 for ex, ez in ends):
        problems.append(f"Muelle ({lx},{lz}): ninguna punta toca la pasarela")
# el lugar donde se reaparece (1.8 m delante del santuario) también tiene que ser piso
for cid, x, z, yaw in W.CHECKPOINTS:
    sx, sz = x + math.sin(math.radians(yaw)) * 1.8, z + math.cos(math.radians(yaw)) * 1.8
    check("Reaparición", cid, sx, sz, 0.3)


# límites invisibles (la misma grilla que build_walls): ninguna pared entre la reaparición y el eje del camino o el
# centro del área más cercanos (el muelle del lago llegó a quedar encerrado detrás de la pared del borde de la pasarela)
def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1, p2, q1, q2):
    return (_cross(q1, q2, p1) > 0) != (_cross(q1, q2, p2) > 0) and (_cross(p1, p2, q1) > 0) != (_cross(p1, p2, q2) > 0)


GX0, GX1, GZ0, GZ1 = W.MAP_BOUNDS
for cid, x, z, yaw in W.CHECKPOINTS:
    sx, sz = x + math.sin(math.radians(yaw)) * 1.8, z + math.cos(math.radians(yaw)) * 1.8
    goals = [(ax, az) for name, ax, az, r, h, soft in W.AREAS]
    for name, pts, width, ph in W.PATHS:
        for a, b in zip(pts, pts[1:]):
            _, t = T.seg_dist(sx, sz, *a, *b)
            goals.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    gx, gz = min(goals, key=lambda g: math.hypot(g[0] - sx, g[1] - sz))
    win = (min(sx, gx) - 2, min(sz, gz) - 2, max(sx, gx) + 2, max(sz, gz) + 2)
    walls = T.wall_segments(GX0, GZ0, int((GX1 - GX0) / 2), int((GZ1 - GZ0) / 2), 2.0, window=win)
    hit = [w for w in walls if _segments_cross((sx, sz), (gx, gz), w[0], w[1])]
    if hit:
        problems.append(f"Reaparición {cid} ({sx:.1f},{sz:.1f}): {len(hit)} pared(es) invisible(s) antes de ({gx:.1f},{gz:.1f})")
# el contorno tiene que ser cerrado: una punta suelta es un hueco en la pared (cajas finas de los muelles mal cortadas)
_ends = {}
for a, b in T.wall_segments(GX0, GZ0, int((GX1 - GX0) / 2), int((GZ1 - GZ0) / 2), 2.0):
    for p in (a, b):
        k = (round(p[0], 3), round(p[1], 3))
        _ends[k] = _ends.get(k, 0) + 1
for (ex, ez), n in _ends.items():
    if n == 1 and GX0 < ex < GX1 and GZ0 < ez < GZ1:
        problems.append(f"Límites invisibles: punta suelta en ({ex:.2f},{ez:.2f})")
for k, (x, z) in W.POINTS.items():
    check("Point", k, x, z, 0.3)
for cid, x, z, yaw in W.CHECKPOINTS:
    check("Checkpoint", cid, x, z)
for eid, x, z, r, lock, enemies in W.ENCOUNTERS:
    for arch, ex, ez, yaw in enemies:
        check("Enemy", f"{eid}/{arch}", ex, ez)
for arch, ax, az, r, bx, bz, yaw in W.BOSSES:
    check("BossArena", arch, ax, az)
    check("Boss", arch, bx, bz)
    # el borde de la arena tiene que ser transitable casi entero
    bad = sum(1 for i in range(24) if T.walk_dist(ax + math.cos(i / 24 * math.tau) * (r - 1.5), az + math.sin(i / 24 * math.tau) * (r - 1.5)) > 0)
    if bad > 4:
        problems.append(f"Arena {arch}: {bad}/24 puntos del borde (r-1.5) fuera de lo transitable")
# arena de Kokuyō: el santuario y su reaparición fuera de la barrera (r 18), y el piso de losas debajo de la pelea
for arch, ax, az, r, bx, bz, yaw in W.BOSSES:
    if arch != "kage":
        continue
    for cid, x, z, cyaw in W.CHECKPOINTS:
        if math.hypot(x - ax, z - az) < r + 1.0:
            problems.append(f"Checkpoint {cid} ({x},{z}) dentro de la barrera de {arch} (a {math.hypot(x - ax, z - az):.1f} m, r {r})")
        # Kaito reaparece 1.8 m delante del santuario (Checkpoint.spawnPoint): ese punto también afuera y transitable
        sx, sz = x + math.sin(math.radians(cyaw)) * 1.8, z + math.cos(math.radians(cyaw)) * 1.8
        if math.hypot(x - ax, z - az) < r + 6.0:
            if math.hypot(sx - ax, sz - az) < r + 1.0:
                problems.append(f"Checkpoint {cid}: la reaparición ({sx:.1f},{sz:.1f}) cae dentro de la barrera de {arch} (a {math.hypot(sx - ax, sz - az):.1f} m, r {r})")
            check("Reaparición", cid, round(sx, 2), round(sz, 2))
    if not W.on_courtyard(bx, bz) or not W.on_courtyard(ax, az):
        problems.append(f"{arch}: el jefe o el centro de la arena fuera del piso del patio")
    for npc, variant, x, z, nyaw in W.NPCS:
        if variant == "dojo" and not W.on_courtyard(x, z):
            problems.append(f"NPC {npc} del dojo fuera del piso del patio")
for pid, x, z, yaw, flag in W.PORTALS:
    check("Portal", pid, x, z)
for tid, x, z, r in W.TRIGGERS:
    check("Trigger", tid, x, z, 0.0)
for npc, variant, x, z, yaw in W.NPCS:
    check("NPC", npc, x, z)

# edificios encima de caminos o de marcadores
BIG = ("house", "storehouse", "pagoda", "pavilion", "shrine", "mountain_cabin", "temple_bell", "well", "dojo_main")
marks = [(f"cp {c[0]}", c[1], c[2]) for c in W.CHECKPOINTS] + [(f"enemy {e[0]}", a[1], a[2]) for e in W.ENCOUNTERS for a in e[5]] \
    + [(f"portal {p[0]}", p[1], p[2]) for p in W.PORTALS] + [("start", W.START[0], W.START[1])]
for pid, x, z, yaw, sc in W.LANDMARKS:
    base = pid.split("@")[0]
    if not base.startswith(BIG):
        continue
    r = 2.6 * sc if not base.startswith("dojo_main") else 9.0
    pd = T.path_info(x, z)[0]
    if pd < r * 0.5 and not base.startswith(("well", "shrine_small", "dojo_main")):
        problems.append(f"{base} ({x},{z}) pisa un camino (dist borde {pd:.1f})")
    for name, mx, mz in marks:
        if math.hypot(mx - x, mz - z) < r + 1.0:
            problems.append(f"{base} ({x},{z}) tapa a {name} ({mx},{mz})")

# props flotantes / sobre pilotes: tienen que estar en el agua y con fondo suficiente
for pid, x, z, yaw, sc in W.LANDMARKS:
    base = pid.split("@")[0]
    if base in ("boat_small", "house_fisher", "lake_arena_platform"):
        if not T.in_lake(x, z):
            problems.append(f"{base} ({x},{z}) es un prop de agua pero no está en el lago")
        elif W.WATER_LAKE - T.height(x, z) < (1.0 if base == "boat_small" else 0.5):
            problems.append(f"{base} ({x},{z}) tiene poca profundidad ({W.WATER_LAKE - T.height(x, z):.2f} m)")

# pendiente a lo largo de los caminos (CharacterController: slopeLimit 45°, NavMesh 42°)
for name, pts, width, ph in W.PATHS:
    if name in ("pasarela_lago", "dojo_subida"):
        continue   # tablones y escaleras: los pisa la malla del prop, no el terreno
    worst = (0, None)
    for i in range(len(pts) - 1):
        (ax, az), (bx, bz) = pts[i], pts[i + 1]
        L = math.hypot(bx - ax, bz - az)
        n = max(1, int(L))
        for k in range(n):
            x0, z0 = ax + (bx - ax) * k / n, az + (bz - az) * k / n
            x1, z1 = ax + (bx - ax) * (k + 1) / n, az + (bz - az) * (k + 1) / n
            sl = abs(T.height(x1, z1) - T.height(x0, z0)) / math.hypot(x1 - x0, z1 - z0)
            if sl > worst[0]:
                worst = (sl, (round(x0, 1), round(z0, 1)))
    if worst[0] > 0.75:
        problems.append(f"Camino {name}: pendiente {math.degrees(math.atan(worst[0])):.0f}° en {worst[1]}")

# caminos que cruzan el estanque o un arroyo: cada cruce necesita un puente (si no, Kaito vadea medio metro de agua)
# tablero de cada puente según su tamaño en el manifest (largo en +z local con yaw 0): un radio fijo
# daba por buenos un puente girado a lo largo del arroyo o un tablón a 4 m del cruce
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
SIZES = {pid: m["size"] for mf in glob.glob(os.path.join(OUT, "manifest_*.json"))
         for pid, m in json.load(open(mf, encoding="utf-8")).items()}
BRIDGES = [(x, z, math.sin(math.radians(yaw)), math.cos(math.radians(yaw)), SIZES[b][2] * 0.5 * sc, SIZES[b][0] * 0.5 * sc)
           for pid, x, z, yaw, sc in W.LANDMARKS for b in [pid.split("@")[0]] if b.startswith("bridge") and b in SIZES]


def on_bridge(px, pz, dx, dz):
    """(px, pz) cae sobre el tablero de un puente orientado como el camino (dx, dz unitario)."""
    return any(abs((px - bx) * sa + (pz - bz) * ca) <= hl - 0.3 and abs((px - bx) * ca - (pz - bz) * sa) <= hw
               and abs(dx * sa + dz * ca) >= 0.7 for bx, bz, sa, ca, hl, hw in BRIDGES)
for name, pts, width, ph in W.PATHS:
    if name in ("pasarela_lago", "dojo_subida"):
        continue
    seen = set()
    for i in range(len(pts) - 1):
        (ax, az), (bx, bz) = pts[i], pts[i + 1]
        L = math.hypot(bx - ax, bz - az)
        n = max(1, int(L / 0.5))
        ux, uz = (bx - ax) / max(L, 1e-6), (bz - az) / max(L, 1e-6)
        for k in range(n + 1):
            x, z = ax + (bx - ax) * k / n, az + (bz - az) * k / n
            key = (round(x / 4), round(z / 4))
            if T.stream_dist(x, z) < 0 and key not in seen and not on_bridge(x, z, ux, uz):
                seen.add(key)
                problems.append(f"Camino {name}: cruza agua sin puente en ({x:.1f}, {z:.1f})")

# Cascada Kohan: el agua cae fuera de la plataforma (> 12 m del centro de la arena, si no las cortinas pasan por
# encima de la baranda) y lejos de la pasarela; ninguna columna del acantilado toca la plataforma ni la pasarela
import falls_layout as FALLS
arena = next(((x, z) for pid, x, z, yaw, sc in W.LANDMARKS if pid == "lake_arena_platform"), None)
walk = next((pts for name, pts, width, ph in W.PATHS if name == "pasarela_lago"), [])


def walk_dist(x, z):
    best = 1e9
    for (ax, az), (bx, bz) in zip(walk[:-1], walk[1:]):
        vx, vz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((x - ax) * vx + (z - az) * vz) / (vx * vx + vz * vz)))
        px, pz = ax + vx * t, az + vz * t
        if arena is None or math.hypot(px - arena[0], pz - arena[1]) > FALLS.DECK_R:   # los tablones terminan en la baranda
            best = min(best, math.hypot(x - px, z - pz))
    return best


if arena is not None:
    for e, n in FALLS.plunge_points(1.0):
        x, z = FALLS.game_xz(e, n)
        d = math.hypot(x - arena[0], z - arena[1])
        if d < 12.0:
            problems.append(f"Cascada: el agua cae a {d:.1f} m del centro de la arena en ({x:.1f}, {z:.1f}) (mínimo 12)")
        if walk_dist(x, z) < 6.0:
            problems.append(f"Cascada: el agua cae a {walk_dist(x, z):.1f} m de la pasarela en ({x:.1f}, {z:.1f})")
    for c in FALLS.columns():
        for ce, cn in c.corners():
            x, z = FALLS.game_xz(ce, cn)
            if math.hypot(x - arena[0], z - arena[1]) < FALLS.DECK_R + 0.6:
                problems.append(f"Cascada: columna '{c.kind}' en ({x:.1f}, {z:.1f}) toca la plataforma de la arena")
                break
            if walk_dist(x, z) < 2.5:
                problems.append(f"Cascada: columna '{c.kind}' en ({x:.1f}, {z:.1f}) a menos de 2.5 m de la pasarela")
                break
    if not any(pid.startswith("kohan_falls_cliff") for pid, *_ in W.LANDMARKS):
        problems.append("Cascada: falta el landmark kohan_falls_cliff")

print("\n".join(problems) if problems else "OK: sin problemas")
print(f"{len(problems)} problemas")
