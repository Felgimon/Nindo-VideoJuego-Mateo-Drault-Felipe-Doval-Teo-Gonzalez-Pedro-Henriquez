"""Construye el mundo de Nindō en Blender y lo exporta para Unity.

blender -b --python Tools/Blender/world/build_world.py -- [--export] [--preview] [--map]

Salida (Nindo/Assets/Nindo/Art/Models/World):
  World_Terrain.fbx   terreno facetado por chunks (T__), agua (W__), límites invisibles (B__)
  World_<zona>.fbx    empties: props (P__id__n__yYAW__sESCALA) y marcadores (M__Tipo__args)
"""
import sys, os, math, random, json, glob, importlib, time

HERE = os.path.dirname(os.path.abspath(__file__))
BL = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(BL))
sys.path[:0] = [HERE, BL, os.path.join(BL, "props")]

import bpy, bmesh
from mathutils import Vector, Euler
import nindo_lib as L
import nindo_palette as PAL
import world_plan as W
import world_terrain as T

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_DIR = os.path.join(REPO, "Nindo", "Assets", "Nindo", "Art", "Models", "World")
PREV_DIR = os.path.join(BL, "out", "world")
os.makedirs(PREV_DIR, exist_ok=True)
rng = random.Random(1234)

CELL = 2.5
X0, X1, Z0, Z1 = -244, 244, -204, 196
WATER_PROPS = {"house_fisher", "boat_small", "lake_arena_platform", "dock_segment", "boardwalk_segment"}


def B(x, z, h=0.0):
    """juego (x este, z norte, h arriba) -> Blender (Unity = (-bx, bz, -by))."""
    return Vector((-x, -z, h))


# =========================================================================== tamaños de props
SIZES = {}
for mf in glob.glob(os.path.join(BL, "out", "manifest_*.json")):
    for pid, m in json.load(open(mf)).items():
        s = m.get("size", [2, 2, 2])
        SIZES[pid] = max(s[0], s[2]) * 0.5
DEFAULT_R = {"house": 5, "dojo_main": 12, "dojo_gate": 6, "wall": 4.5, "tree": 1.6, "bamboo": 1.2, "cliff": 6, "rock_large": 2, "bush": 0.8}


def prop_radius(pid):
    if pid in SIZES:
        return SIZES[pid]
    for k, v in DEFAULT_R.items():
        if pid.startswith(k):
            return v
    return 1.0


# =========================================================================== almohadillas (aplanar bajo edificios)
PADS = []
for entry in W.LANDMARKS:
    pid, x, z, yaw, sc = entry
    base = pid.split("@")[0]
    if "@" in pid:
        continue
    r = prop_radius(base) * sc
    if base.startswith(("house", "storehouse", "pagoda", "pavilion", "shrine", "mountain_cabin", "temple_bell", "torii", "well", "wall_gate")) and base not in WATER_PROPS:
        PADS.append((x, z, r + 1.0, T.height(x, z)))


STAIRS = [(0, 96, 104, 0.0, 4.0, 4.7), (0, 104, 112, 4.0, 8.0, 4.7)]   # x, z0, z1, h0, h1, media anchura


def H(x, z):
    h = T.height(x, z)
    for sx, z0, z1, h0, h1, hw in STAIRS:
        # el terreno queda por debajo de la escalera (su malla es el suelo)
        if abs(x - sx) < hw + 0.6 and z0 - 0.5 < z < z1 + 0.5:
            if z < z0:
                h = min(h, h0)                     # al pie: al ras del arranque (sin zanja)
            elif z > z1:
                h = min(h, h1)                     # arriba: al ras del último escalón
            else:
                # bajo la escalera: línea de las narices - 0.25 (el escalón real siempre queda por encima;
                # con 0.45 la malla de 2.5 m interpolaba una zanja delante del primer escalón y el primer
                # escalón quedaba de 0.46-0.70 m, más que el stepOffset 0.4 de Kaito)
                h = min(h, h0 + (h1 - h0) * (z - z0) / (z1 - z0) - 0.25)
    for px, pz, pr, ph in PADS:
        d = math.hypot(x - px, z - pz)
        if d < pr + 3:
            w = T.smoothstep(pr + 3, pr, d)
            h = h + (ph - h) * w
    return h


# misma grilla (con el mismo jitter y descarte) que build_terrain: la altura de la malla
# triangulada de 2.5 m, que es lo que pisa Unity. H() es analítica y en los saltos de
# world_terrain.height() la malla no la puede seguir: los props apoyados en H flotaban
# (árboles hasta 7.9 m) o quedaban enterrados.
NXV = int((X1 - X0) / CELL) + 1
NZV = int((Z1 - Z0) / CELL) + 1
_GV = {}


def _grid_vert(i, j):
    k = (i, j)
    if k not in _GV:
        v = None
        if 0 <= i < NXV and 0 <= j < NZV:
            jx = 0.0 if i in (0, NXV - 1) else (T._hash(i, j, 7) - 0.5) * CELL * 0.55
            jz = 0.0 if j in (0, NZV - 1) else (T._hash(i, j, 9) - 0.5) * CELL * 0.55
            px, pz = X0 + i * CELL + jx, Z0 + j * CELL + jz
            if T.walk_dist(px, pz) < 46 or T.in_lake(px, pz):
                v = (px, pz, H(px, pz))
        _GV[k] = v
    return _GV[k]


def mesh_H(x, z):
    """Altura del terreno TRIANGULADO que exporta build_terrain. None = no hay terreno ahí."""
    i0 = int(math.floor((x - X0) / CELL))
    j0 = int(math.floor((z - Z0) / CELL))
    for j in (j0 - 1, j0, j0 + 1):
        for i in (i0 - 1, i0, i0 + 1):
            q = [_grid_vert(i, j), _grid_vert(i + 1, j), _grid_vert(i + 1, j + 1), _grid_vert(i, j + 1)]
            if None in q:
                continue
            tris = ((q[0], q[1], q[2]), (q[0], q[2], q[3])) if (i + j) % 2 == 0 else ((q[0], q[1], q[3]), (q[1], q[2], q[3]))
            for a, b, c in tris:
                d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(d) < 1e-12:
                    continue
                l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (z - c[1])) / d
                l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (z - c[1])) / d
                l3 = 1.0 - l1 - l2
                if min(l1, l2, l3) >= -1e-6:
                    return l1 * a[2] + l2 * b[2] + l3 * c[2]
    return None


# =========================================================================== terreno
def build_terrain():
    t0 = time.time()
    nx = int((X1 - X0) / CELL) + 1
    nz = int((Z1 - Z0) / CELL) + 1
    verts = {}
    keep = {}
    for j in range(nz):
        for i in range(nx):
            x, z = X0 + i * CELL, Z0 + j * CELL
            jx = (T._hash(i, j, 7) - 0.5) * CELL * 0.55
            jz = (T._hash(i, j, 9) - 0.5) * CELL * 0.55
            if i in (0, nx - 1): jx = 0
            if j in (0, nz - 1): jz = 0
            px, pz = x + jx, z + jz
            wd = T.walk_dist(px, pz)
            keep[(i, j)] = wd < 46 or T.in_lake(px, pz)
            if keep[(i, j)]:
                verts[(i, j)] = (px, pz, H(px, pz))
    print(f"heights {time.time() - t0:.1f}s")
    CH = 24  # celdas por chunk (60 m)
    objs = []
    for cj in range(0, nz - 1, CH):
        for ci in range(0, nx - 1, CH):
            mb = L.MeshBuilder(f"T__chunk_{ci // CH}_{cj // CH}")
            any_face = False
            vcache = {}

            def V(i, j):
                if (i, j) not in vcache:
                    x, z, h = verts[(i, j)]
                    vcache[(i, j)] = mb.bm.verts.new(B(x, z, h))
                return vcache[(i, j)]

            for j in range(cj, min(cj + CH, nz - 1)):
                for i in range(ci, min(ci + CH, nx - 1)):
                    quad = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                    if not all(q in verts for q in quad):
                        continue
                    tris = ([quad[0], quad[1], quad[2]], [quad[0], quad[2], quad[3]]) if (i + j) % 2 == 0 else \
                           ([quad[0], quad[1], quad[3]], [quad[1], quad[2], quad[3]])
                    for tri in tris:
                        pts = [verts[q] for q in tri]
                        cx = sum(p[0] for p in pts) / 3; cz = sum(p[1] for p in pts) / 3; ch = sum(p[2] for p in pts) / 3
                        col = T.face_color(cx, cz, ch, nz_vertical(pts), rng)
                        try:
                            f = mb.bm.faces.new([V(*q) for q in tri])
                        except ValueError:
                            continue
                        f.material_index = L.SLOT_PALETTE
                        mb._tag([f], col, L.SLOT_PALETTE)
                        any_face = True
            if any_face:
                bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces)
                # que las normales apunten hacia arriba
                for f in mb.bm.faces:
                    if f.normal.z < 0:
                        f.normal_flip()
                objs.append(finish_mesh(mb))
            else:
                mb.bm.free()
    print(f"terrain {len(objs)} chunks {time.time() - t0:.1f}s")
    return objs


def nz_vertical(pts):
    (ax, az, ah), (bx, bz, bh), (cx, cz, chh) = pts
    u = Vector((bx - ax, bh - ah, bz - az)); v = Vector((cx - ax, chh - ah, cz - az))
    n = u.cross(v)
    return abs(n.y) / max(1e-6, n.length)


def finish_mesh(mb):
    me = bpy.data.meshes.new(mb.name)
    mb.bm.to_mesh(me)
    mb.bm.free()
    for n in L.SLOT_NAMES:
        me.materials.append(L.get_material(n))
    for p in me.polygons:
        p.use_smooth = False
    o = bpy.data.objects.new(mb.name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


# =========================================================================== agua
# Agua low-poly animada (shader "Nindo/Water Lowpoly"). Cada vértice guarda en su color:
#   R = amplitud de las olas (lago 1, arroyos 0.3, arrozales 0.1)
#   G = cercanía a la orilla (1 = toca tierra) -> espuma
#   B = profundidad (0 bajo, 1 hondo) -> color y transparencia
# La malla es una grilla con vértices compartidos para que las olas la deformen sin abrirse.
WAVES = [((0.958, 0.287), 0.35, 1.1, 0.55), ((-0.371, 0.928), 0.55, 1.5, 0.30), ((0.659, -0.753), 0.90, 2.1, 0.15)]
WAVE_HEIGHT = 0.26   # = _WaveHeight del material (Tools/Unity/generate_assets.py)


def wave_height(x, z, t, amp):
    """Misma fórmula que el vertex shader (para la vista previa)."""
    h = 0.0
    for (dx, dz), k, w, a in WAVES:
        h += a * math.sin((dx * x + dz * z) * k + t * w)
    return h * WAVE_HEIGHT * amp


def water_object(name, verts, faces, cols):
    """verts: [(x, z, y)] en coordenadas de juego; cols: [(r, g, b)] por vértice."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([B(x, z, y) for x, z, y in verts], [], faces)
    me.update()
    # caras hacia arriba
    for poly in me.polygons:
        if poly.normal.z < 0:
            poly.flip()
    me.update()
    attr = me.color_attributes.new("Col", 'BYTE_COLOR', 'CORNER')
    for poly in me.polygons:
        # G (orilla) y B (profundidad) se promedian por cara: el shader los lee con nointerpolation y así
        # no depende de cuál es el vértice provocador (D3D/Vulkan/Metal = primero, GL = último).
        # R (amplitud de ola) queda por vértice para que las olas no abran grietas entre caras.
        vs = [cols[me.loops[li].vertex_index] for li in poly.loop_indices]
        g = sum(c[1] for c in vs) / len(vs)
        bb = sum(c[2] for c in vs) / len(vs)
        for li in poly.loop_indices:
            attr.data[li].color = (cols[me.loops[li].vertex_index][0], g, bb, 1.0)   # lineal (FBX colors_type LINEAR)
    uv = me.uv_layers.new(name="UVMap")
    u, v = PAL.uv_of("water_deep")
    for l in uv.data:
        l.uv = (u, v)
    for n in L.SLOT_NAMES:
        me.materials.append(L.get_material(n))
    for poly in me.polygons:
        poly.material_index = L.SLOT_WATER
        poly.use_smooth = False
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def grid_water(name, x0, z0, x1, z1, step, y, keep, color_fn):
    """Grilla regular (triángulos alternados) con las celdas para las que keep(cx, cz) es True."""
    nx, nz = int(math.ceil((x1 - x0) / step)), int(math.ceil((z1 - z0) / step))
    index, verts, cols, faces = {}, [], [], []

    def vid(i, j):
        if (i, j) not in index:
            x, z = x0 + i * step, z0 + j * step
            index[(i, j)] = len(verts)
            verts.append((x, z, y))
            cols.append(color_fn(x, z))
        return index[(i, j)]
    for j in range(nz):
        for i in range(nx):
            if not keep(x0 + (i + 0.5) * step, z0 + (j + 0.5) * step):
                continue
            a, b_, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            if (i + j) % 2 == 0:
                faces += [(a, b_, c), (a, c, d)]
            else:
                faces += [(a, b_, d), (b_, c, d)]
    return water_object(name, verts, faces, cols) if faces else None


def build_water():
    objs = []
    # ---------------------------------------------------------------- lago
    xs = [p[0] for p in W.LAKE]; zs = [p[1] for p in W.LAKE]

    def lake_keep(cx, cz):
        return T.in_lake(cx, cz) or (T.poly_dist(cx, cz, W.LAKE) < 6 and T.walk_dist(cx, cz) < 40)

    def lake_col(x, z):
        depth = W.WATER_LAKE - H(x, z)                     # metros de agua sobre el fondo
        shore = max(0.0, min(1.0, 1.0 - depth / 0.9))      # 1 donde el terreno toca el agua
        deep = max(0.0, min(1.0, depth / 3.0))
        return (0.35 + 0.65 * deep, shore, deep)
    o = grid_water("W__lago", min(xs) - 6, min(zs) - 6, max(xs) + 6, max(zs) + 6, 2.0, W.WATER_LAKE, lake_keep, lake_col)
    if o:
        objs.append(o)
    # ---------------------------------------------------------------- arroyos (tiras subdivididas)
    verts, cols, faces = [], [], []
    for pts, width in W.STREAMS:
        for i in range(len(pts) - 1):
            (ax, az), (bx, bz) = pts[i], pts[i + 1]
            dx, dz = bx - ax, bz - az
            Ln = math.hypot(dx, dz)
            ux, uz = dx / Ln, dz / Ln
            half = width * 0.5 + 0.6
            n = max(1, int(math.ceil((Ln + 2.4) / 1.5)))
            base = len(verts)
            for k in range(n + 1):
                s = -1.2 + (Ln + 2.4) * k / n
                for side in (-1.0, 0.0, 1.0):
                    x = ax + ux * s - uz * half * side
                    z = az + uz * s + ux * half * side
                    verts.append((x, z, W.WATER_STREAM))
                    cols.append((0.3, 0.7 if side else 0.0, 0.25 if side else 0.45))   # orilla 0.7: espuma ocasional, no fija
            for k in range(n):
                for c in range(2):
                    v0 = base + k * 3 + c
                    faces += [(v0, v0 + 1, v0 + 4), (v0, v0 + 4, v0 + 3)]
    # estanque: anillos concéntricos
    px_, pz_, pr = W.POND
    rings = [(0.0, 1), (pr * 0.4, 10), (pr * 0.75, 16), (pr + 0.8, 22)]
    ring_ids = []
    for ri, (rr, cnt) in enumerate(rings):
        ids = []
        for k in range(cnt):
            a = k / cnt * math.tau + ri * 0.3
            ids.append(len(verts))
            verts.append((px_ + math.cos(a) * rr, pz_ + math.sin(a) * rr, W.WATER_STREAM))
            edge = rr / (pr + 0.8)
            cols.append((0.25, max(0.0, (edge - 0.75) * 4.0), 1.0 - edge))
        ring_ids.append(ids)
    for ri in range(1, len(rings)):
        inner, outer = ring_ids[ri - 1], ring_ids[ri]
        # triangulación entre anillos con distinta cantidad de vértices
        i = j = 0
        ni, no = len(inner), len(outer)
        while i < ni or j < no:
            if j < no and (i >= ni or (j + 1) / no <= (i + 1) / ni):
                faces.append((inner[i % ni], outer[j % no], outer[(j + 1) % no]))
                j += 1
            else:
                faces.append((inner[i % ni], outer[j % no], inner[(i + 1) % ni]))
                i += 1
    # arrozales: grillas chicas
    for r in W.PADDIES:
        nx_, nz_ = int((r[2] - r[0]) / 2), int((r[3] - r[1]) / 2)
        base = len(verts)
        for j in range(nz_ + 1):
            for i in range(nx_ + 1):
                x, z = r[0] + (r[2] - r[0]) * i / nx_, r[1] + (r[3] - r[1]) * j / nz_
                edge = i in (0, nx_) or j in (0, nz_)
                verts.append((x, z, -0.12))
                cols.append((0.1, 0.5 if edge else 0.1, 0.1))
        for j in range(nz_):
            for i in range(nx_):
                a = base + j * (nx_ + 1) + i
                faces += [(a, a + 1, a + nx_ + 2), (a, a + nx_ + 2, a + nx_ + 1)]
    objs.append(water_object("W__arroyos", verts, faces, cols))
    return objs


def finish_mesh_builder(mb):
    for f in mb.bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    return finish_mesh(mb)


# =========================================================================== límites (marching squares)
def build_walls():
    step = 2.0
    nx = int((X1 - X0) / step); nz = int((Z1 - Z0) / step)
    val = [[T.walk_dist(X0 + i * step, Z0 + j * step) for i in range(nx + 1)] for j in range(nz + 1)]
    segs = []

    def interp(p1, p2, v1, v2):
        t = v1 / (v1 - v2) if v1 != v2 else 0.5
        return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)

    for j in range(nz):
        for i in range(nx):
            c = [(X0 + i * step, Z0 + j * step), (X0 + (i + 1) * step, Z0 + j * step), (X0 + (i + 1) * step, Z0 + (j + 1) * step), (X0 + i * step, Z0 + (j + 1) * step)]
            v = [val[j][i], val[j][i + 1], val[j + 1][i + 1], val[j + 1][i]]
            pts = []
            for k in range(4):
                a, b = k, (k + 1) % 4
                if (v[a] < 0) != (v[b] < 0):
                    pts.append(interp(c[a], c[b], v[a], v[b]))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segs.append((pts[0], pts[1])); segs.append((pts[2], pts[3]))
    mb = L.MeshBuilder("B__limites")
    for (ax, az), (bx, bz) in segs:
        ha, hb = H(ax, az), H(bx, bz)
        lo, hi = min(ha, hb) - 2.0, max(ha, hb) + 6.0
        mb.face([B(ax, az, lo), B(bx, bz, lo), B(bx, bz, hi), B(ax, az, hi)], "black", double=True)
    print(f"walls {len(segs)} segments")
    return [finish_mesh(mb)]


# =========================================================================== colocación de props
PLACED = []          # (pid, x, z, yaw, scale, y)   -> empties P__ (prefab + collider en Unity)
DECOR_PLACED = []    # igual, pero se fusiona en mallas D__ por chunk (sin collider, sin GameObjects)
# decoración de suelo sin collider: miles de instancias -> una malla por chunk de 60 m
DECOR = {"grass_tuft_a", "grass_tuft_b", "flowers_yellow", "flowers_pink", "flowers_blue", "tall_grass_patch",
         "reeds_patch", "mushroom_cluster", "lily_pads", "rice_patch", "wheat_patch", "cabbage_row", "rock_small_b",
         "bush_round_a", "bush_round_b", "bush_round_c", "bush_azalea_pink", "bush_azalea_white", "bush_snow"}
DECOR_SHADOW = {"bush_round_a", "bush_round_b", "bush_round_c", "bush_azalea_pink", "bush_azalea_white", "bush_snow", "tall_grass_patch", "reeds_patch"}
OCC = {}             # hash espacial: (cx, cz) -> lista (x, z, r)


def occ_free(x, z, r):
    ci, cj = int(math.floor(x / 8)), int(math.floor(z / 8))
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for ox, oz, orr in OCC.get((ci + di, cj + dj), ()):
                if math.hypot(x - ox, z - oz) < r + orr:
                    return False
    return True


def occ_add(x, z, r):
    OCC.setdefault((int(math.floor(x / 8)), int(math.floor(z / 8))), []).append((x, z, r))


def place(pid, x, z, yaw=0.0, scale=1.0, y=None, radius=None, block=True, ground=True):
    """ground=True: 'y' es relativa a H (o None = H) y se corrige a la malla triangulada.
    ground=False: altura absoluta (agua, '@altura', parches de arroz)."""
    base = pid.split("@")[0]
    if y is None:
        if "@" in pid:
            y = float(pid.split("@")[1]); ground = False
        elif base in WATER_PROPS:
            y = W.WATER_LAKE; ground = False
        else:
            y = H(x, z)
    if ground:
        g = mesh_H(x, z)
        if g is None:
            return                      # fuera de la malla (borde norte): no colgar props en el vacío
        y += g - H(x, z)                # misma altura relativa a H, pero sobre lo que pisa Unity
    (DECOR_PLACED if base in DECOR else PLACED).append((base, x, z, yaw, scale, y))
    if block:
        occ_add(x, z, (radius if radius is not None else prop_radius(base)) * scale)


def place_landmarks():
    for pid, x, z, yaw, sc in W.LANDMARKS:
        y = None
        if pid == "shrine_small" and x > 180:
            y = W.WATER_LAKE + 1.0
        if pid == "lily_pads":
            y = W.WATER_STREAM + 0.02
        place(pid, x, z, yaw, sc, y=y, ground=(y is None))
    # muralla
    x = W.WALL_X_RANGE[0]
    while x <= W.WALL_X_RANGE[1]:
        if abs(x) > 6:
            place("wall_segment", x, W.WALL_Z, 0, 1.0, y=min(H(x, W.WALL_Z), H(x, W.WALL_Z - 1), H(x, W.WALL_Z + 1)) - 0.2)
        x += 8
    for wx in (-6.0, 6.0, W.WALL_X_RANGE[0] - 4, W.WALL_X_RANGE[1] + 4):
        place("wall_post", wx, W.WALL_Z, 0, 1.0)
    # pasarela del lago: tablones desde 2 m antes de que empiece el agua hasta el borde de la arena
    for name, pts, width, ph in W.PATHS:
        if name != "pasarela_lago":
            continue
        arena = [(lm[1], lm[2]) for lm in W.LANDMARKS if lm[0] == "lake_arena_platform"]
        segs, acc = [], 0.0
        for i in range(len(pts) - 1):
            L_ = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            segs.append((acc, acc + L_, pts[i], pts[i + 1]))
            acc += L_

        def at(sv):
            for s0, s1, (ax, az), (bx, bz) in segs:
                if sv <= s1 or s1 == acc:
                    t = (sv - s0) / max(1e-6, s1 - s0)
                    return ax + (bx - ax) * t, az + (bz - az) * t
            return pts[-1]
        sv, s_start, s_end = 0.0, None, acc
        while sv <= acc:
            x_, z_ = at(sv)
            if s_start is None and (T.in_lake(x_, z_) or H(x_, z_) < W.WATER_LAKE + 0.05):
                s_start = max(0.0, sv - 2.0)
            if arena and math.hypot(x_ - arena[0][0], z_ - arena[0][1]) < 10.2:
                s_end = sv
                break
            sv += 0.25
        if s_start is None:
            continue
        for s0, s1, (ax, az), (bx, bz) in segs:
            c0, c1 = max(s0, s_start), min(s1, s_end)
            if c1 - c0 < 0.5:
                continue
            n = max(1, round((c1 - c0) / 5.8))
            yaw = math.degrees(math.atan2(bx - ax, bz - az))
            for k in range(n):
                sm = c0 + (k + 0.5) * (c1 - c0) / n
                cx, cz = at(sm)
                place("boardwalk_segment", cx, cz, yaw, (c1 - c0) / n / 6.0)
    # faroles a lo largo de los caminos principales
    for name, pts, width, ph in W.PATHS:
        if name in ("pasarela_lago", "dojo_subida"):
            continue
        acc = 0.0
        side = 1
        for i in range(len(pts) - 1):
            (ax, az), (bx, bz) = pts[i], pts[i + 1]
            Ln = math.hypot(bx - ax, bz - az)
            dx, dz = (bx - ax) / Ln, (bz - az) / Ln
            d = 0.0
            while d < Ln:
                if acc >= 18.0:
                    acc = 0.0
                    px, pz = ax + dx * d - dz * (width * 0.5 + 1.2) * side, az + dz * d + dx * (width * 0.5 + 1.2) * side
                    reg = T.region(px, pz)
                    lamp = {"montana": "torch_brazier", "bambu": "lantern_stone", "lago": "lantern_post", "dojo": "lantern_stone_tall"}.get(reg, "lantern_stone" if reg == "jardin" else "lantern_post")
                    if occ_free(px, pz, 1.0) and T.walk_dist(px, pz) < 1.5:
                        place(lamp, px, pz, math.degrees(math.atan2(dx, dz)) + 90 * side, 1.0)
                    side = -side
                d += 2.0; acc += 2.0


SCATTER = {
    # región: lista de (prop, peso, escala_min, escala_max) para bosque exterior
    "hogar": [("tree_round_a", 2, 0.9, 1.2), ("tree_round_b", 2, 0.9, 1.2), ("tree_pine_a", 1, 0.9, 1.1), ("tree_cedar_a", 2, 0.9, 1.1), ("tree_sakura_b", 0.5, 0.9, 1.1), ("bush_round_a", 1.5, 0.8, 1.3)],
    "campos": [("tree_round_a", 2, 0.9, 1.2), ("tree_round_b", 2, 0.9, 1.2), ("tree_cedar_a", 2, 0.9, 1.2), ("tree_cedar_b", 1.5, 0.9, 1.2), ("bush_round_b", 1, 0.8, 1.2)],
    "bosque": [("tree_cedar_a", 4, 0.9, 1.3), ("tree_cedar_b", 4, 0.9, 1.3), ("tree_pine_c", 1, 0.9, 1.2), ("tree_round_b", 1, 0.9, 1.2), ("bush_round_c", 1.5, 0.8, 1.2)],
    "jardin": [("tree_sakura_a", 1.5, 0.9, 1.2), ("tree_sakura_b", 1.5, 0.9, 1.2), ("tree_maple_a", 1, 0.9, 1.2), ("tree_pine_a", 1.2, 0.9, 1.2), ("tree_pine_b", 1, 0.9, 1.2), ("tree_cedar_a", 2, 1.0, 1.3), ("bush_azalea_pink", 1, 0.9, 1.2), ("bush_round_a", 1, 0.9, 1.3)],
    "dojo": [("tree_pine_a", 2, 1.0, 1.3), ("tree_pine_b", 2, 1.0, 1.3), ("tree_cedar_b", 3, 1.0, 1.3), ("tree_maple_a", 1, 0.9, 1.1)],
    "montana": [("tree_pine_snow_a", 3, 0.9, 1.3), ("tree_pine_snow_b", 3, 0.9, 1.3), ("tree_dead_a", 0.6, 0.8, 1.2), ("rock_snow_a", 1, 0.8, 1.6), ("bush_snow", 1, 0.8, 1.2)],
    "lago": [("tree_round_a", 2, 0.9, 1.2), ("tree_round_b", 2, 0.9, 1.2), ("tree_cedar_a", 1.5, 0.9, 1.2), ("tree_maple_a", 0.6, 0.9, 1.1), ("bush_round_b", 1, 0.8, 1.2)],
    "bambu": [("bamboo_cluster_a", 4, 0.9, 1.2), ("bamboo_cluster_b", 4, 0.9, 1.2), ("tree_cedar_b", 0.6, 1.0, 1.2), ("bamboo_young", 1, 0.9, 1.3)],
}
GROUND = {
    "hogar": [("grass_tuft_a", 3), ("grass_tuft_b", 3), ("flowers_yellow", 0.6), ("flowers_pink", 0.4), ("rock_small_a", 0.3)],
    "campos": [("grass_tuft_a", 3), ("grass_tuft_b", 3), ("flowers_yellow", 0.4), ("rock_small_b", 0.3)],
    "bosque": [("grass_tuft_b", 2), ("mushroom_cluster", 0.5), ("rock_small_a", 0.5), ("bush_round_c", 0.4)],
    "jardin": [("grass_tuft_a", 2), ("grass_tuft_b", 2), ("flowers_blue", 0.7), ("flowers_pink", 0.7), ("flowers_yellow", 0.6), ("bush_azalea_white", 0.3), ("tall_grass_patch", 0.5)],
    "dojo": [("grass_tuft_a", 1), ("rock_small_b", 0.4)],
    "montana": [("rock_small_a", 1), ("rock_small_b", 1), ("rock_medium_a", 0.5), ("grass_tuft_b", 0.8)],
    "lago": [("grass_tuft_a", 2), ("reeds_patch", 0.5), ("rock_small_b", 0.5), ("flowers_blue", 0.4)],
    "bambu": [("grass_tuft_b", 2), ("bamboo_young", 0.6), ("mushroom_cluster", 0.4), ("rock_small_a", 0.4)],
}


def pick(lst):
    tot = sum(e[1] for e in lst)
    r = rng.random() * tot
    for e in lst:
        r -= e[1]
        if r <= 0:
            return e
    return lst[-1]


def scatter():
    n_tree = n_ground = n_cliff = 0
    step = 3.1
    x = X0
    while x < X1:
        z = Z0
        while z < Z1:
            px, pz = x + rng.uniform(0, step), z + rng.uniform(0, step)
            wd = T.walk_dist(px, pz)
            reg = T.region(px, pz)
            lake = T.in_lake(px, pz)
            if lake:
                z += step; continue
            if 1.2 < wd < 30:
                # bosque exterior: más denso cerca del borde visible
                dens = 0.62 if wd < 14 else 0.35
                if reg == "bambu": dens += 0.25
                if rng.random() < dens:
                    h0 = H(px, pz)
                    slope = abs(H(px + 1.5, pz) - h0) + abs(H(px, pz + 1.5) - h0)
                    if slope > 2.6 and rng.random() < 0.55 and wd > 3:
                        pid = rng.choice(("cliff_a", "cliff_b")) if reg != "montana" else "cliff_c"
                        sc = rng.uniform(0.7, 1.2)
                        if occ_free(px, pz, prop_radius(pid) * sc * 0.6):
                            place(pid, px, pz, rng.uniform(0, 360), sc, y=h0 - 1.5, radius=prop_radius(pid) * 0.6)
                            n_cliff += 1
                    else:
                        pid, w, s0, s1 = pick(SCATTER[reg])
                        sc = rng.uniform(s0, s1)
                        r = prop_radius(pid) * sc * (0.55 if pid.startswith(("tree", "bamboo")) else 0.8)
                        if occ_free(px, pz, r):
                            place(pid, px, pz, rng.uniform(0, 360), sc, y=h0 - 0.05, radius=r)
                            n_tree += 1
            elif -10 < wd <= 1.2:
                # decoración de suelo (no sobre caminos)
                pd = T.path_info(px, pz)[0]
                if pd > 0.8 and T.stream_dist(px, pz) > 1.5 and not any(T.in_rect(px, pz, r, 1) for r in W.PADDIES + W.WHEAT):
                    edge = wd > -3.5
                    if rng.random() < (0.55 if edge else 0.22):
                        if edge and rng.random() < 0.3:
                            pid = rng.choice(("bush_round_a", "bush_round_b", "bush_round_c")) if reg not in ("montana", "bambu") else ("bush_snow" if reg == "montana" else "bamboo_young")
                        else:
                            pid, w = pick(GROUND[reg])
                        sc = rng.uniform(0.8, 1.3)
                        r = prop_radius(pid) * sc * 0.6
                        if occ_free(px, pz, r):
                            place(pid, px, pz, rng.uniform(0, 360), sc, radius=r, block=pid.startswith(("bush", "rock", "tall")))
                            n_ground += 1
            z += step
        x += step
    # cobertura de suelo densa (se fusiona en mallas por chunk, así que es barata)
    COVER = {"hogar": 0.34, "campos": 0.3, "bosque": 0.26, "jardin": 0.34, "dojo": 0.12, "montana": 0.12, "lago": 0.26, "bambu": 0.22}
    n_cover = 0
    step = 1.7
    x = X0
    while x < X1:
        z = Z0
        while z < Z1:
            px, pz = x + rng.uniform(0, step), z + rng.uniform(0, step)
            wd = T.walk_dist(px, pz)
            if wd < 9 and not T.in_lake(px, pz):
                reg = T.region(px, pz)
                p = COVER[reg] * (1.0 if wd < 0 else 0.55)
                if rng.random() < p and T.path_info(px, pz)[0] > 0.3 and T.stream_dist(px, pz) > 1.2 \
                        and not any(T.in_rect(px, pz, r, 1) for r in W.PADDIES + W.WHEAT) \
                        and not (reg == "dojo" and H(px, pz) > W.DOJO_H - 0.5 and wd < -1) and occ_free(px, pz, 0.35):
                    if reg == "montana" and H(px, pz) > 9.5:
                        pid = rng.choice(("rock_small_b", "grass_tuft_b"))
                    else:
                        r = rng.random()
                        pid = "grass_tuft_a" if r < 0.42 else "grass_tuft_b" if r < 0.8 else \
                            {"jardin": "flowers_pink", "hogar": "flowers_yellow", "lago": "flowers_blue", "campos": "flowers_yellow",
                             "bosque": "mushroom_cluster", "bambu": "mushroom_cluster", "dojo": "grass_tuft_a", "montana": "rock_small_b"}[reg]
                    if pid.startswith("grass_tuft"):
                        # matas en grupitos: se ve mucho más natural que briznas sueltas
                        for k in range(rng.randint(2, 5)):
                            a, d = rng.uniform(0, 6.28), rng.uniform(0, 0.7)
                            place(rng.choice(("grass_tuft_a", "grass_tuft_b")), px + math.cos(a) * d, pz + math.sin(a) * d,
                                  rng.uniform(0, 360), rng.uniform(1.0, 1.8), block=False)
                    else:
                        place(pid, px, pz, rng.uniform(0, 360), rng.uniform(0.8, 1.3), block=False)
                    if reg in ("hogar", "campos", "jardin", "lago") and rng.random() < 0.05:
                        place("tall_grass_patch", px + 1.2, pz, rng.uniform(0, 360), rng.uniform(0.7, 1.0), block=False)
                    n_cover += 1
            z += step
        x += step
    print(f"cover {n_cover}")
    # cultivos
    for r in W.PADDIES:
        for xx in range(int(r[0]) + 1, int(r[2]), 2):
            for zz in range(int(r[1]) + 1, int(r[3]), 2):
                place("rice_patch", xx + 0.5, zz + 0.5, 0, 1.0, y=-0.3, block=False, ground=False)
    for r in W.WHEAT:
        for xx in range(int(r[0]) + 1, int(r[2]), 2):
            for zz in range(int(r[1]) + 1, int(r[3]), 2):
                place("wheat_patch", xx + 0.5, zz + 0.5, rng.uniform(-8, 8), 1.0, block=False)
    print(f"scatter trees={n_tree} ground={n_ground} cliffs={n_cliff}")


# =========================================================================== decoración fusionada
_PROP_FNS = None


def prop_fns():
    global _PROP_FNS
    if _PROP_FNS is None:
        _PROP_FNS = {}
        for p in sorted(glob.glob(os.path.join(BL, "props", "props_*.py"))):
            name = os.path.splitext(os.path.basename(p))[0]
            try:
                _PROP_FNS.update(importlib.import_module(name).PROPS)
            except Exception as e:
                print("no pude importar", name, e)
    return _PROP_FNS


def build_decor():
    from mathutils import Matrix
    fns = prop_fns()
    meshes = {}
    for pid in sorted({d[0] for d in DECOR_PLACED}):
        if pid not in fns:
            print("decor: falta el prop", pid)
            continue
        o = fns[pid](1)
        meta = json.loads(o.get("nindo_meta", "{}"))
        col = (meta.get("collider") or {}).get("type", "none")
        if col not in (None, "none"):
            print(f"decor: {pid} tiene collider '{col}' (se fusiona igual, sin collider)")
        meshes[pid] = o.data
        bpy.data.objects.remove(o, do_unlink=True)
    CH = 60.0
    chunks = {}
    for pid, x, z, yaw, sc, y in DECOR_PLACED:
        if pid not in meshes:
            continue
        key = (int((x - X0) // CH), int((z - Z0) // CH), pid in DECOR_SHADOW)
        bm = chunks.get(key)
        if bm is None:
            bm = chunks[key] = bmesh.new()
        n0 = len(bm.verts)
        bm.from_mesh(meshes[pid])
        bm.verts.ensure_lookup_table()
        M = Matrix.Translation(B(x, z, y)) @ Matrix.Rotation(math.radians(-yaw), 4, 'Z') @ Matrix.Scale(sc, 4)
        bmesh.ops.transform(bm, matrix=M, verts=bm.verts[n0:])
    objs = []
    tris = 0
    for (ci, cj, sh), bm in sorted(chunks.items()):
        name = f"D__decor{'_sh' if sh else ''}_{ci}_{cj}"
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for n in L.SLOT_NAMES:
            me.materials.append(L.get_material(n))
        tris += sum(len(p.vertices) - 2 for p in me.polygons)
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        objs.append(o)
    print(f"decor {len(DECOR_PLACED)} instancias -> {len(objs)} mallas, {tris} tris")
    return objs


# =========================================================================== marcadores
MARKERS = []   # (name, x, z, y, yaw)


def marker(name, x, z, yaw=0.0, y=None):
    if y is None:
        if T.in_lake(x, z):
            # sobre el agua: piso de la plataforma de la arena o tablones de la pasarela
            on_arena = any(lm[0] == "lake_arena_platform" and math.hypot(x - lm[1], z - lm[2]) < 9.5 for lm in W.LANDMARKS)
            y = W.WATER_LAKE + (1.0 if on_arena else 0.8)
        else:
            y = H(x, z)
    MARKERS.append((name, x, z, y, yaw))


def build_markers():
    sx, sz, syaw = W.START
    marker("M__Start", sx, sz, syaw)
    for k, (x, z) in W.POINTS.items():
        marker(f"M__Point__{k}", x, z)
    for cid, x, z, yaw in W.CHECKPOINTS:
        marker(f"M__Checkpoint__{cid}", x, z, yaw)
        occ_add(x, z, 2.0)
    for zid, x, z, r, prio in W.ZONES:
        marker(f"M__Zone__{zid}__{r}__{prio}", x, z)
    for eid, x, z, r, lock, enemies in W.ENCOUNTERS:
        marker(f"M__Encounter__{eid}__{r}__{lock}", x, z)
        for i, (arch, ex, ez, yaw) in enumerate(enemies):
            marker(f"M__Enemy__{arch}__{eid}__{i}", ex, ez, yaw)
    for arch, ax, az, r, bx, bz, yaw in W.BOSSES:
        y = (W.WATER_LAKE + 1.0) if arch == "mizuchi" else None
        marker(f"M__BossArena__{arch}__{r}", ax, az, y=y)
        marker(f"M__Boss__{arch}", bx, bz, yaw, y=y)
    for pid, x, z, yaw, flag in W.PORTALS:
        y = (W.WATER_LAKE + 1.0) if pid == "p_lake" else None
        marker(f"M__Portal__{pid}__{flag}__cp_dojo_gate", x, z, yaw, y=y)
        occ_add(x, z, 2.5)
    for tid, x, z, r in W.TRIGGERS:
        marker(f"M__Trigger__{tid}__{r}", x, z)
    for flag, prop, x, z, yaw, ang in W.DOORS:
        y = 8.0 if prop.startswith("dojo") else None
        marker(f"M__Door__{flag}__{prop}__{ang}", x, z, yaw, y=y)
    for flag, x, z, yaw, w in W.BARRIERS:
        marker(f"M__Barrier__{flag}__{w}", x, z, yaw)
    for npc, variant, x, z, yaw in W.NPCS:
        marker(f"M__NPC__{npc}__{variant}", x, z, yaw)
    for x, z, sx_, sz_ in W.FIREFLIES:
        marker(f"M__Fireflies__{sx_}__{sz_}", x, z)
    marker("M__SealGate", 0, 113, 180, y=8.0)   # centro del portón (dojo_gate@8, 0, 113, 180)


# =========================================================================== exportación
def export():
    os.makedirs(OUT_DIR, exist_ok=True)
    # --- terreno
    L.export_fbx(TERRAIN_OBJS, os.path.join(OUT_DIR, "World_Terrain.fbx"))
    # --- props y marcadores por región
    groups = {}
    for i, (pid, x, z, yaw, sc, y) in enumerate(PLACED):
        groups.setdefault(T.region(x, z), []).append((f"P__{pid}__{i:05d}__y{yaw:.1f}__s{sc:.3f}", x, z, y, yaw, sc))
    for i, (name, x, z, y, yaw) in enumerate(MARKERS):
        groups.setdefault(T.region(x, z), []).append((name + f"__n{i}" if name.count("__") < 1 else name, x, z, y, yaw, 1.0))
    for reg, items in groups.items():
        objs = []
        used = set()
        for name, x, z, y, yaw, sc in items:
            nm = name
            k = 1
            while nm in used:
                nm = f"{name}__dup{k}"; k += 1
            used.add(nm)
            e = bpy.data.objects.new(nm, None)
            e.empty_display_size = 0.5
            e.location = B(x, z, y)
            e.rotation_euler = (0, 0, math.radians(-yaw))
            # la pasarela se estira solo a lo largo (Blender Y local = Z local en Unity)
            e.scale = (1.0, sc, 1.0) if name.startswith("P__boardwalk_segment__") else (sc, sc, sc)
            bpy.context.scene.collection.objects.link(e)
            objs.append(e)
        L.export_fbx(objs, os.path.join(OUT_DIR, f"World_{reg}.fbx"))
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
    json.dump({"placed": len(PLACED), "markers": len(MARKERS)}, open(os.path.join(PREV_DIR, "stats.json"), "w"))


# =========================================================================== vista previa
def preview_water(t=0.7):
    """Aproxima en Blender lo que hace el shader del agua: olas (en un instante t), facetas,
    color por profundidad y espuma facetada en la orilla."""
    mat = bpy.data.materials.new("PreviewWater")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    attr = nt.nodes.new("ShaderNodeVertexColor"); attr.layer_name = "Col"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(attr.outputs["Color"], sep.inputs["Color"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")          # profundidad -> color
    ramp.color_ramp.elements[0].color = (0.10, 0.36, 0.42, 1)
    ramp.color_ramp.elements[1].color = (0.02, 0.09, 0.18, 1)
    nt.links.new(sep.outputs["Blue"], ramp.inputs["Fac"])
    foam = nt.nodes.new("ShaderNodeMath"); foam.operation = 'GREATER_THAN'; foam.inputs[1].default_value = 0.64   # = _FoamThreshold
    nt.links.new(sep.outputs["Green"], foam.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'
    mix.inputs["B"].default_value = (0.75, 0.88, 0.92, 1)
    nt.links.new(foam.outputs[0], mix.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.18
    for o in bpy.context.scene.objects:
        if not o.name.startswith("W__"):
            continue
        me = o.data
        col = me.color_attributes.get("Col")
        amp = [0.0] * len(me.vertices)
        if col is not None:
            for li, l in enumerate(me.loops):
                amp[l.vertex_index] = col.data[li].color[0]
        for v in me.vertices:
            gx, gz = -v.co.x, -v.co.y
            v.co.z += wave_height(gx, gz, t, amp[v.index])
        me.update()
        for i in range(len(me.materials)):
            me.materials[i] = mat


def preview(shots):
    import nindo_preview as PV
    # construir cada prop una vez y crear instancias
    mods = prop_fns()
    cols = {}
    root = bpy.data.collections.new("PropLib")
    bpy.context.scene.collection.children.link(root)
    lib_layer = bpy.context.view_layer.layer_collection.children["PropLib"]
    lib_layer.exclude = True
    for pid in sorted({p[0] for p in PLACED}):
        col = bpy.data.collections.new("lib_" + pid)
        root.children.link(col)
        if pid in mods:
            try:
                o = mods[pid](1)
                bpy.context.scene.collection.objects.unlink(o)
                col.objects.link(o)
            except Exception as e:
                print("prop failed", pid, e)
        cols[pid] = col
    for pid, x, z, yaw, sc, y in PLACED:
        e = bpy.data.objects.new("I_" + pid, None)
        e.instance_type = 'COLLECTION'
        e.instance_collection = cols[pid]
        e.location = B(x, z, y)
        e.rotation_euler = (0, 0, math.radians(-yaw))
        e.scale = (sc, sc, sc)
        bpy.context.scene.collection.objects.link(e)
    preview_water()
    PV.setup_night(ground=False, strength=1.1)
    scn = bpy.context.scene
    for o in WALL_OBJS:
        o.hide_render = True
    try:
        scn.eevee.taa_render_samples = 12
    except Exception:
        pass
    only = None
    for a in argv:
        if a.startswith("--only="):
            only = set(a[7:].split(","))
    for name, x, z, *rest in shots:
        if only and name not in only:
            continue
        h = H(x, z)
        if name.startswith("map"):
            # vista cenital ortográfica (norte arriba, este a la derecha)
            size = rest[0] if rest else 500
            cd = bpy.data.cameras.new(name); cam = bpy.data.objects.new(name, cd); scn.collection.objects.link(cam)
            cd.type = 'ORTHO'; cd.ortho_scale = size; cd.clip_end = 2000
            cam.location = B(x, z, 400); cam.rotation_euler = (0, 0, math.radians(180))
            scn.camera = cam
            scn.render.resolution_x, scn.render.resolution_y = (1400, 1240) if size >= 400 else (1100, 1100)
        else:
            # cámara del juego: FOV vertical (como Unity), pitch y distancia del CameraDirector
            fov = rest[0] if rest else 30
            dist = rest[1] if len(rest) > 1 else 24
            pitch = math.radians(rest[2] if len(rest) > 2 else 52)
            yaw = math.radians(rest[3] if len(rest) > 3 else 0)
            cd = bpy.data.cameras.new(name); cd.lens_unit = 'FOV'; cd.sensor_fit = 'VERTICAL'; cd.angle = math.radians(fov); cd.clip_end = 600
            cam = bpy.data.objects.new(name, cd); scn.collection.objects.link(cam)
            target = Vector((x, z, h + 1.0))
            back = Vector((-math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))) * dist
            eye = target + back
            PV.look(cam, B(eye.x, eye.y, eye.z), B(target.x, target.y, target.z))
            scn.camera = cam
            scn.render.resolution_x, scn.render.resolution_y = 960, 540
        scn.render.filepath = os.path.join(PREV_DIR, f"shot_{name}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", name)


# =========================================================================== main
L.clear_scene()
place_landmarks()
build_markers()
scatter()
TERRAIN_OBJS = build_terrain() + build_water() + build_decor()
WALL_OBJS = build_walls()
TERRAIN_OBJS += WALL_OBJS
print(f"placed {len(PLACED)} props, {len(MARKERS)} markers")
if "--export" in argv:
    export()
if "--preview" in argv or "--map" in argv:
    shots = [("map", 0, -5), ("map_sur", 0, -110, 150), ("map_centro", 0, 30, 150), ("map_oeste", -150, 80, 150), ("map_este", 140, 80, 150)] if "--map" in argv else []
    if "--preview" in argv:
        shots += [("hogar", -30, -164), ("campos", 10, -118), ("bosque", 6, -62), ("muralla", 0, -38),
                  ("jardin", 0, 24), ("jardin_e", 30, 40), ("dojo_puerta", 0, 100), ("dojo_patio", 0, 136),
                  ("montana", -140, 70), ("cumbre", -200, 124), ("lago", 120, 14), ("lago_jefe", 182, 70),
                  ("bambu", 96, 126), ("bambu_arena", 124, 160), ("cinematica_dojo", 0, 120, 40, 34, 14, 0)]
    preview(shots)
