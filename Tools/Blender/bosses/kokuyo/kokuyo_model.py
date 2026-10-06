"""Geometría de Kokuyō: samurái de laca negra ("obsidiana"), 4.5 m, low-poly facetado.

Cómo se lee desde la cámara del juego (55°, ~300 px de alto) y por qué está hecho así:
* Silueta en "T" desde arriba: ō-sode enormes (línea de hombros de ~2.9 m), pecho de 1.95 m,
  cintura angosta que abre en una campana de 8 faldones (kusazuri) y piernas cortas y gruesas.
* De noche el negro no puede ser un agujero: cada placa es una lama con el canto superior
  biselado en acero claro (tile_light / tile_blue: es lo que mira a la luna, que viene de arriba)
  y el borde inferior en oro o en cordón violeta. Desde arriba se ven anillos de luz escalonados.
* Acentos que guían el ojo: media luna dorada de 1.1 m (frente), máscara roja con barba blanca,
  melena blanca de 7 mechones (espalda), obi y colas rojas, las dos mitades de la cinta naranja
  (la misma tela que la bandana de Kaito) y los brillos violetas: ojos, grietas del pecho y filo.
* Todo es rígido por pieza (cada placa pesa 100 % a un hueso: nada de "armadura de goma"); solo
  las mangas y el hakama mezclan dos huesos en la articulación.

Las piezas que el juego apaga o suelta en runtime son objetos aparte, hijos de su hueso:
Mask, Face, Katana_Nodachi, Crest_L/R, Sode_R / Sode_R_Broken y Crack_1..5.
"""
import math
import bpy, bmesh
from mathutils import Vector, Matrix
import nindo_lib as L
import nindo_palette as P
import kokuyo_rig as KR

# --------------------------------------------------------------------------- materiales propios
SLOT_EDGE, SLOT_SEAMS, SLOT_RIBBON, SLOT_MASKCRACK = 4, 5, 6, 7
EXTRA_MATS = ["Kokuyo_Edge", "Kokuyo_Seams", "Kokuyo_Ribbon", "Kokuyo_MaskCrack"]
# color de la bandana de Kaito tal como lo guarda su material (kaitooo.fbx, 'AmarilloBandana'): el
# proyecto está en espacio Gamma, así que en pantalla se ve exactamente este valor (#ef7600)
BANDANA_RGB = (0.9387, 0.4614, 0.0)
SEAM_RGB = (0.753, 0.541, 1.0)        # glow_purple
EDGE_BASE_RGB = (0.62, 0.64, 0.70)

C = dict(plate="ink", plate2="tile_dark", bevel="tile_light", bevel2="tile_blue", gold="gold", gold2="gold_dark",
         lace="cloth_purple", cloth="cloth_indigo", obi="cloth_red", obi2="wood_red_dark", rope="rope", straw="straw",
         glove="cloth_black", iron="iron", steel="iron_light", mask="wood_red", mask2="wood_red_dark",
         white="white", white2="cloth_white", sole="wood_black", skin="wood_pale", paper="paper")


# --------------------------------------------------------------------------- herramientas de malla
class Kit(L.MeshBuilder):
    """MeshBuilder de una pieza rígida (un hueso) con ayudas para armadura facetada."""

    def __init__(self, name, bone, seed=1, weights=None):
        super().__init__(name, seed)
        self.bone = bone
        self.weights = weights      # función(co) -> {hueso: peso} para piezas que doblan (mangas)

    def apply(self, part, M):
        for v in part.verts:
            v.co = M @ v.co
        return part

    def tag(self, faces, color, slot=None):
        self._tag(faces, color, slot, None)
        if slot is not None:
            for f in faces:
                f.material_index = slot

    def tube(self, pts, radii, sides, color, ups=None, phase=0.0, cap0=True, cap1=True, ring_colors=None, power=2.0):
        """Tubo facetado por una polilínea; radii[i] = r o (rx, ry) (ry según 'ups'). power > 2 da
        secciones más cuadradas (placas), < 2 más en rombo."""
        pts = [Vector(p) for p in pts]
        rings = []
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            up = Vector(ups[i]) if ups else (Vector((0, -1, 0)) if abs(t.y) < 0.9 else Vector((0, 0, 1)))
            yv = (up - t * up.dot(t)).normalized()
            xv = yv.cross(t).normalized()
            r = radii[i]
            rx, ry = (r, r) if not isinstance(r, (tuple, list)) else r
            ring = []
            for k in range(sides):
                a = phase + 2.0 * math.pi * k / sides
                ca, sa = math.cos(a), math.sin(a)
                e = 2.0 / power
                cx = math.copysign(abs(ca) ** e, ca)
                cy = math.copysign(abs(sa) ** e, sa)
                ring.append(p + xv * (rx * cx) + yv * (ry * cy))
            rings.append(ring)
        part = self.loft(rings, color, cap_start=cap0, cap_end=cap1)
        if ring_colors:
            n = sides
            fs = part.faces
            for f in fs:
                zc = f.calc_center_median()
                # color por tramo: el tramo más cercano a la cara
                best = min(range(len(pts) - 1), key=lambda j: ((pts[j] + pts[j + 1]) * 0.5 - zc).length)
                col = ring_colors[best]
                if col:
                    self.tag([f], col)
        return part

    def lame(self, tops, bots, outs, t=0.05, bev=0.035, trim=0.035, face="ink", top="tile_light", tr="gold",
             back=None, closed=False, caps=True, bottom=None, slot_trim=None, skip=()):
        """Lama de armadura: placa con espesor, canto superior biselado (mira a la luna) y borde inferior
        de color. tops/bots: puntos del borde de arriba y de abajo por columna; outs: normal hacia afuera."""
        cols = []
        for T, Bm, O in zip(tops, bots, outs):
            T, Bm, O = Vector(T), Vector(Bm), Vector(O).normalized()
            Dv = Bm - T
            h = Dv.length
            D = Dv / h
            O = (O - D * O.dot(D)).normalized()
            prof = [(-t * 0.5, 0.0), (t * 0.5, 0.0), (t * 0.5 + bev * 0.7, bev), (t * 0.5 + bev * 0.7, h - trim),
                    (t * 0.5 + bev * 0.35, h), (-t * 0.5, h)]
            cols.append([T + O * o + D * d for o, d in prof])
        vcols = [[self.bm.verts.new(p) for p in c] for c in cols]
        faces_by = {k: [] for k in range(6)}
        n = len(vcols)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            for k in range(6):
                if k in skip:
                    continue
                k2 = (k + 1) % 6
                f = self.bm.faces.new((vcols[i][k], vcols[i][k2], vcols[j][k2], vcols[j][k]))
                faces_by[k].append(f)
        capf = []
        if caps and not closed:
            capf.append(self.bm.faces.new(list(reversed(vcols[0]))))
            capf.append(self.bm.faces.new(vcols[-1]))
        part = self._new([v for c in vcols for v in c], face, None, None)
        self.tag(faces_by[0] + faces_by[1], top)
        self.tag(faces_by[3], tr, slot_trim)
        self.tag(faces_by[4], bottom or tr, slot_trim)
        self.tag(faces_by[5], back or face)
        self.tag(capf, face)
        return part

    def obox(self, center, size, x_axis, y_axis, color, bevel=0.0, up_color=None, up_thresh=0.45):
        """Caja orientada (ejes x, y; z = x × y) con chaflán opcional; caras del chaflán que miran
        arriba en 'up_color'."""
        X = Vector(x_axis).normalized()
        Y = Vector(y_axis)
        Y = (Y - X * Y.dot(X)).normalized()
        Z = X.cross(Y)
        R = Matrix((X, Y, Z)).transposed().to_4x4()
        M = Matrix.Translation(Vector(center)) @ R @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
        r = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        part = self._new(r["verts"], color, None, None)
        if bevel > 0.0:
            faces0 = part.faces
            edges = list({e for f in faces0 for e in f.edges})
            res = bmesh.ops.bevel(self.bm, geom=edges + part.verts, offset=bevel, segments=1, affect='EDGES',
                                  offset_type='OFFSET', profile=0.5, clamp_overlap=True)
            fs = [f for f in faces0 if f.is_valid] + list(res.get("faces", []))
            part = L.Part(self, list({v for f in fs for v in f.verts}))
            self.tag(part.faces, color)
        if up_color:
            self.up_shade(part, up_color, up_thresh)
        return part

    def up_shade(self, part, color, thresh=0.45, max_area=None):
        for f in part.faces:
            f.normal_update()
            if f.normal.z > thresh and (max_area is None or f.calc_area() < max_area):
                self.tag([f], color)
        return part

    def strip(self, pts, widths, normal_hint, color, thick=0.03, side_color=None):
        """Cinta con espesor a lo largo de una polilínea (cuerdas, colas de tela)."""
        pts = [Vector(p) for p in pts]
        rings = []
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            nh = Vector(normal_hint[i] if isinstance(normal_hint, list) else normal_hint)
            nv = (nh - t * nh.dot(t)).normalized()
            wv = t.cross(nv).normalized()
            w = widths[i] * 0.5
            rings.append([p + wv * w + nv * thick * 0.5, p - wv * w + nv * thick * 0.5,
                          p - wv * w - nv * thick * 0.5, p + wv * w - nv * thick * 0.5])
        part = self.loft(rings, color, cap_start=True, cap_end=True)
        if side_color:
            for f in part.faces:
                f.normal_update()
        return part


def finish_kit(kit, extra_mats):
    obj = kit.finish()
    for n in extra_mats:
        m = bpy.data.materials.get(n) or bpy.data.materials.new(n)
        obj.data.materials.append(m)
    return obj


def mirror_bm_kit(src, name, bone, weights=None):
    """Copia espejada (x -> -x) de una pieza derecha para el lado izquierdo, con su propio hueso."""
    k = Kit(name, bone, weights=weights)
    k.bm.free()
    k.bm = src.bm.copy()
    k.uv = k.bm.loops.layers.uv.get("UVMap")
    k.col = k.bm.loops.layers.color.get("Col")
    for v in k.bm.verts:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(k.bm, faces=k.bm.faces)
    return k


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# --------------------------------------------------------------------------- piernas
def build_leg_r(kits):
    s = -1.0
    x0 = KR.ANKLE.x
    # pie acorazado: suela de madera, empeine de laca, puntera de oro
    k = kits["Foot_R"] = Kit("part_Foot_R", "Foot_R")
    sole = [(x0 + 0.17 * s, 0.24), (x0 + 0.21 * s, 0.05), (x0 + 0.23 * s, -0.36), (x0 + 0.15 * s, -0.62),
            (x0 - 0.15 * s, -0.62), (x0 - 0.22 * s, -0.36), (x0 - 0.2 * s, 0.05), (x0 - 0.16 * s, 0.24)]
    if s < 0:
        sole = list(reversed(sole))
    k.extrude_polygon(sole, 0.0, 0.07, C["sole"], top_color=C["sole"])
    k.tube([(x0, 0.24, 0.20), (x0, 0.02, 0.22), (x0, -0.30, 0.15), (x0, -0.56, 0.12)],
           [(0.16, 0.12), (0.2, 0.15), (0.215, 0.09), (0.17, 0.055)], 6, C["plate"],
           ups=[(0, 0, 1)] * 4, phase=math.pi / 6)
    # placas del empeine (lamas cortas que suben hacia el tobillo)
    for i, (y, z) in enumerate(((-0.36, 0.19), (-0.18, 0.25))):
        k.obox((x0, y, z + 0.035), (0.36, 0.16, 0.05), (1, 0, 0), (0, 1, 0.45 - 0.15 * i), C["plate2"], up_color=C["bevel2"])
    k.obox((x0, -0.55, 0.15), (0.34, 0.15, 0.1), (1, 0, 0), (0, 1, -0.35), C["gold"], up_color=C["gold"])
    # grebas (suneate): laca negra, placa frontal con filo de oro, rodillera dorada
    k = kits["Shin_R"] = Kit("part_Shin_R", "Shin_R")
    kn = KR.KNEE
    k.tube([(x0, 0.0, 0.18), (x0, 0.01, 0.5), (x0, -0.02, 0.8), (kn.x, kn.y + 0.02, 0.98)],
           [(0.21, 0.21), (0.25, 0.26), (0.26, 0.27), (0.27, 0.27)], 8, C["plate"], phase=math.pi / 8)
    tops, bots, outs = [], [], []
    for a in (-60, -30, 0, 30, 60):
        r = math.radians(a)
        o = Vector((math.sin(r), -math.cos(r), 0.0))
        tops.append(Vector((x0, -0.03, 0.92)) + o * 0.27)
        bots.append(Vector((x0, 0.0, 0.3)) + o * 0.23)
        outs.append(o)
    k.lame(tops, bots, outs, t=0.04, bev=0.04, trim=0.05, face=C["plate2"], top=C["bevel"], tr=C["gold"])
    k.tube([(x0, 0.0, 0.2), (x0, 0.0, 0.27)], [0.235, 0.235], 8, C["gold2"], phase=math.pi / 8, cap0=False, cap1=False)
    k.tube([(x0, -0.02, 0.86), (x0, -0.03, 0.93)], [0.285, 0.285], 8, C["gold2"], phase=math.pi / 8, cap0=False, cap1=False)
    # rodillera: domo de 6 caras hacia adelante
    kc = k.tube([(x0, -0.16, 1.03), (x0, -0.27, 1.03), (x0, -0.33, 1.04)], [0.2, 0.17, 0.08], 6, C["gold"],
                ups=[(0, 0, 1)] * 3, phase=math.pi / 6, cap0=False)
    k.up_shade(kc, C["gold"])
    # hakama: tela índigo que se infla y entra en la greba (mezcla con la cadera arriba)
    hip = KR.HIP_J

    def w_thigh(co):
        t = (co.z - 1.45) / (1.8 - 1.45)
        t = max(0.0, min(1.0, t))
        return {"Thigh_R": 1.0 - 0.35 * t, "Hips": 0.35 * t}
    k = kits["Thigh_R"] = Kit("part_Thigh_R", "Thigh_R", weights=w_thigh)
    k.tube([(hip.x * 0.95, 0.0, 1.8), (hip.x * 1.02, -0.02, 1.48), (kn.x, -0.06, 1.16), (kn.x, -0.07, 0.94)],
           [0.33, 0.37, 0.31, 0.24], 8, C["cloth"], phase=math.pi / 8)


# --------------------------------------------------------------------------- cintura, obi, faldones
def build_hips(kits):
    k = kits["Hips"] = Kit("part_Hips", "Hips")
    k.tube([(0, 0.0, 1.62), (0, 0.0, 2.02)], [(0.56, 0.46), (0.62, 0.5)], 8, C["cloth"], phase=math.pi / 8, cap0=True)
    # obi rojo y cuerda sagrada (shimenawa) torcida: tramos alternados de soga y paja
    k.tube([(0, 0.0, 1.98), (0, 0.0, 2.27)], [(0.71, 0.59), (0.73, 0.6)], 12, C["obi"], phase=math.pi / 12, cap0=False, cap1=False)
    n = 10
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1.08) / n
        p0 = Vector((math.sin(a0) * 0.76, -math.cos(a0) * 0.635, 2.27 + 0.012 * math.sin(3 * a0)))
        p1 = Vector((math.sin(a1) * 0.76, -math.cos(a1) * 0.635, 2.27 + 0.012 * math.sin(3 * a1)))
        k.tube([p0, p1], [0.058, 0.058], 5, C["rope"] if i % 2 == 0 else C["straw"], ups=[(0, 0, 1)] * 2, phase=i * 0.7,
               cap0=False, cap1=False)
    # nudo al frente, sobre la costura de los faldones; de ahí cuelgan las colas del obi
    k.obox((0, -0.70, 2.18), (0.30, 0.16, 0.22), (1, 0, 0), (0, 1, 0), C["obi2"])
    k.obox((0, -0.73, 2.27), (0.22, 0.12, 0.14), (1, 0, 0), (0, 1, 0), C["rope"], bevel=0.03, up_color=C["straw"])
    # shide: tiras de papel en zigzag colgando de la soga (acento blanco que se lee de noche)
    for s in (-1.0, 1.0):
        a = math.radians(38.0) * s
        base = Vector((math.sin(a) * 0.78, -math.cos(a) * 0.66, 2.22))
        o = Vector((math.sin(a), -math.cos(a), 0.0))
        tg = Vector((0, 0, 1)).cross(o).normalized()
        pts = [base, base + Vector((0, 0, -0.1)) + tg * 0.05, base + Vector((0, 0, -0.2)) - tg * 0.02,
               base + Vector((0, 0, -0.3)) + tg * 0.05, base + Vector((0, 0, -0.38)) + o * 0.02]
        k.strip(pts, [0.09, 0.09, 0.08, 0.08, 0.07], o, C["paper"], thick=0.02)


def build_sash(kits):
    """Dos colas rojas del obi, adelante: la franja vertical roja del concepto."""
    for s, side in ((-1.0, "R"), (1.0, "L")):
        for seg in (1, 2):
            bn = f"Sash_{side}_{seg}"
            k = kits[bn] = Kit("part_" + bn, bn)
            x = 0.10 * s
            if seg == 1:
                pts = [(x, -0.71, 2.10), (x * 1.05, -0.77, 1.82), (x * 1.1, -0.83, 1.58)]
                w = [0.20, 0.21, 0.22]
            else:
                pts = [(x * 1.1, -0.82, 1.64), (x * 1.15, -0.88, 1.40), (x * 1.2, -0.93, 1.18)]
                w = [0.22, 0.23, 0.24]
            st = k.strip(pts, w, (0, -1, 0), C["obi"], thick=0.04)
            if seg == 2:
                k.obox((x * 1.2, -0.935, 1.205), (0.25, 0.05, 0.06), (1, 0, 0), (0, 0.3, 1), C["gold2"], bevel=0.0)


def build_skirt(kits):
    """8 faldones de 3 lamas cada uno, con cordones violetas y el ruedo de oro."""
    for a in KR.SKIRT_ANGLES:
        bn = KR.skirt_name(a)
        k = kits[bn] = Kit("part_" + bn, bn)
        h0, down, out, tang = KR.skirt_frame(a)
        half = 24.5
        ncol = 2
        L3 = 0.36
        for j in range(3):
            d0 = j * 0.285
            tops, bots, outs = [], [], []
            for c in range(ncol):
                aa = a + (-half + 2 * half * c / (ncol - 1))
                hh, dd, oo, tt = KR.skirt_frame(aa)
                bump = 0.012 * j          # cada lama un poco más afuera: escalonado visible
                tops.append(hh + dd * d0 + oo * (0.03 + bump))
                bots.append(hh + dd * (d0 + L3) + oo * (0.03 + bump))
                outs.append(oo)
            last = j == 2
            k.lame(tops, bots, outs, t=0.045, bev=0.035, trim=0.045 if last else 0.03,
                   face=C["plate"], top=C["bevel2"] if j else C["bevel"], tr=C["gold"] if last else C["lace"])
        # dos cordones verticales (odoshi) sobre las lamas
        for u in (-0.42, 0.42):
            aa = a + u * half
            hh, dd, oo, tt = KR.skirt_frame(aa)
            pts = [hh + dd * (0.02 + 0.84 * i / 2.0) + oo * (0.085 + 0.012 * i) for i in range(3)]
            k.strip(pts, [0.035] * 3, [oo] * 3, C["lace"], thick=0.015)


# --------------------------------------------------------------------------- tronco (dō)
def _ring(rx, ry, z, n=12, cy=0.0, power=2.6):
    pts, outs = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.sin(a), -math.cos(a)     # i = 0 al frente (-Y)
        e = 2.0 / power
        x = rx * math.copysign(abs(ca) ** e, ca)
        y = cy + ry * math.copysign(abs(sa) ** e, sa)
        pts.append(Vector((x, y, z)))
        # normal de la superelipse
        nx = math.copysign(abs(ca) ** (2 - e), ca) / rx
        ny = math.copysign(abs(sa) ** (2 - e), sa) / ry
        outs.append(Vector((nx, ny, 0.0)).normalized())
    return pts, outs


# lamas del dō: (z arriba, z abajo, rx/ry arriba, rx/ry abajo, hueso)
DO_LAMES = [
    (3.34, 3.16, (0.56, 0.46), (0.90, 0.60), "Chest"),     # munaita / cuello
    (3.20, 2.96, (0.90, 0.60), (0.975, 0.63), "Chest"),
    (3.00, 2.76, (0.975, 0.63), (0.93, 0.61), "Chest"),
    (2.80, 2.56, (0.90, 0.60), (0.80, 0.56), "Chest"),
    (2.60, 2.40, (0.79, 0.56), (0.70, 0.52), "Spine"),
    (2.44, 2.20, (0.70, 0.53), (0.66, 0.51), "Spine"),
]


def torso_front_y(x, z):
    """Altura de la superficie frontal del dō en (x, z): para apoyar grietas y detalles."""
    for zt, zb, rt, rb, _ in DO_LAMES:
        if zb <= z <= zt:
            t = (zt - z) / (zt - zb)
            rx = rt[0] + (rb[0] - rt[0]) * t
            ry = rt[1] + (rb[1] - rt[1]) * t
            u = min(0.999, abs(x) / rx)
            return -(ry * (1.0 - u ** 2.6) ** (1 / 2.6)) - 0.055
    return -0.6


def build_torso(kits):
    kc = kits["Chest"] = Kit("part_Chest", "Chest")
    ks = kits["Spine"] = Kit("part_Spine", "Spine")
    # núcleo (no se ve: tapa huecos entre lamas al doblarse)
    ks.tube([(0, 0.0, 2.15), (0, 0.0, 2.66)], [(0.6, 0.47), (0.74, 0.52)], 10, C["plate"], phase=math.pi / 10)
    kc.tube([(0, 0.0, 2.6), (0, 0.0, 3.0), (0, 0.0, 3.3)], [(0.82, 0.55), (0.92, 0.58), (0.52, 0.42)], 10, C["plate"], phase=math.pi / 10)
    for i, (zt, zb, rt, rb, bone) in enumerate(DO_LAMES):
        k = kc if bone == "Chest" else ks
        tp, outs = _ring(rt[0], rt[1], zt)
        bp, _ = _ring(rb[0], rb[1], zb)
        if i == 0:
            face, top, tr = C["plate2"], C["gold"], C["gold"]
        elif i in (1, 2):
            face, top, tr = C["plate"], C["bevel"], C["lace"] if i == 1 else C["gold2"]
        else:
            face, top, tr = C["plate"], C["bevel2"], C["lace"]
        k.lame(tp, bp, outs, t=0.05, bev=0.04, trim=0.04, face=face, top=top, tr=tr, closed=True,
               skip=(5,) if i == 0 else (0, 5))
    # espaldar y cuello (nodowa)
    kc.obox((0, 0.62, 2.95), (0.9, 0.08, 0.5), (1, 0, 0), (0, 0, 1), C["plate2"], bevel=0.02, up_color=C["bevel2"])
    kn = kits["Neck"] = Kit("part_Neck", "Neck")
    kn.tube([(0, 0.02, 3.26), (0, 0.02, 3.58)], [0.27, 0.24], 8, C["plate"], phase=math.pi / 8)
    kn.obox((0, -0.27, 3.42), (0.36, 0.08, 0.2), (1, 0, 0), (0, 0.25, 1), C["plate2"], up_color=C["bevel"])


# --------------------------------------------------------------------------- hombros y ō-sode
SODE_FLARE = 30.0
SODE_YAW = 16.0         # el borde de adelante de la hombrera gira hacia el frente


def sode_lames(k, s, n_lames=5, jag=False, scale=1.0):
    """Ō-sode: 5 lamas escalonadas que abren hacia abajo, barra superior dorada, cordones violetas."""
    x_top = 1.02 * s
    flare = math.radians(SODE_FLARE)
    out = Vector((s * math.cos(flare), 0.0, -math.sin(flare)))
    down = Vector((s * math.sin(flare), 0.0, -math.cos(flare)))
    ys = [-0.52, -0.17, 0.17, 0.52]
    yaw = Matrix.Rotation(math.radians(SODE_YAW * -s), 3, 'Z')
    piv = Vector((x_top, 0.02, 3.48))
    for j in range(n_lames):
        d0 = j * 0.178
        hh = 0.22
        tops, bots, outs = [], [], []
        for y in ys:
            bulge = 0.16 * (1.0 - (y / 0.52) ** 2)
            base = Vector((x_top, 0.02 + y * (1.0 + 0.04 * j), 3.48)) + Vector((s * bulge, 0, 0))
            jagged = 0.0
            if jag and j == n_lames - 1:
                jagged = 0.06 * (1 if (ys.index(y) % 2) else -1) + 0.04
            tops.append(piv + yaw @ (base + down * d0 + out * (0.012 * j) - piv))
            bots.append(piv + yaw @ (base + down * (d0 + hh - jagged) + out * (0.012 * j) - piv))
            outs.append(yaw @ (out + Vector((0, y * 0.9, 0))))
        last = j == n_lames - 1
        k.lame(tops, bots, outs, t=0.05, bev=0.04, trim=0.04 if (last and not jag) else 0.032,
               face=C["plate"], top=C["bevel"], tr=C["gold"] if (last and not jag) else C["lace"],
               back=C["plate2"])
    # barra superior (kanmuri-ita) dorada
    k.obox(piv + yaw @ Vector((s * 0.1, 0.0, 0.02)), (0.13, 1.08, 0.09), yaw @ Vector((s, 0, 0)), yaw @ Vector((0, 1, 0)),
           C["gold2"], bevel=0.0 if jag else 0.025, up_color=C["gold"])
    # dos cordones verticales (la versión rota los perdió)
    for y in (() if jag else (-0.24, 0.24)):
        pts = []
        for j in range(3):
            d = 0.06 + j * 0.42
            bulge = 0.16 * (1.0 - (y / 0.52) ** 2)
            pts.append(piv + yaw @ (Vector((x_top + s * bulge, 0.02 + y, 3.48)) + down * d + out * (0.065 + 0.012 * j * 2) - piv))
        k.strip(pts, [0.045] * 3, [yaw @ out] * 3, C["lace"], thick=0.016)
    if scale != 1.0:
        c = Vector((x_top + s * 0.1, 0.02, 3.1))
        for v in k.bm.verts:
            v.co = c + (v.co - c) * scale


def build_shoulders(kits, rigid):
    for s, side in ((-1.0, "R"), (1.0, "L")):
        k = kits["Clav_" + side] = Kit("part_Clav_" + side, "Clav_" + side)
        k.obox((0.66 * s, 0.02, 3.24), (0.72, 0.7, 0.24), (1, 0, 0), (0, 1, 0), C["plate"], bevel=0.05, up_color=C["bevel"])
        k.obox((0.66 * s, 0.02, 3.37), (0.5, 0.56, 0.04), (1, 0, 0), (0, 1, 0), C["gold2"], bevel=0.0)
    # hombrera izquierda: va en el cuerpo, con la media cinta naranja (material de la bandana)
    kl = kits["Sode_L"] = Kit("part_Sode_L", "Sode_L")
    sode_lames(kl, 1.0)
    kn = Vector((1.13, -0.52, 3.36))          # moño en la esquina de adelante de la barra superior
    pieces = [kl.obox(kn, (0.13, 0.14, 0.12), (1, 0, 0), (0, 1, 0), C["glove"], bevel=0.03)]
    for side in (-1, 1):
        pieces.append(kl.obox(kn + Vector((0.03, side * 0.12, 0.06)), (0.07, 0.2, 0.1), (1, 0, 0), (0, 1, 0.5 * side), C["glove"]))
    band = [Vector((1.07, -0.5, 3.33)), Vector((1.09, -0.5, 3.57)), Vector((0.99, -0.49, 3.58)), Vector((0.97, -0.48, 3.38))]
    pieces.append(kl.strip(band, [0.11] * 4, [(0, -1, 0)] * 4, C["glove"], thick=0.04))
    for p in pieces:
        kl.tag(p.faces, C["glove"], SLOT_RIBBON)
    kr = kits["Ribbon_1"] = Kit("part_Ribbon_1", "Ribbon_1")
    kr2 = kits["Ribbon_2"] = Kit("part_Ribbon_2", "Ribbon_2")
    # dos colas que cuelgan del moño (cada tramo rígido a su hueso; la segunda cola un poco más corta)
    for kk, bn in ((kr, "Ribbon_1"), (kr2, "Ribbon_2")):
        b = KR_BONES[bn]
        for dy, short in ((-0.05, 0.0), (0.06, 0.12 if bn == "Ribbon_2" else 0.0)):
            d = b.tail - b.head
            a0 = b.head - d * 0.08 + Vector((0, dy, 0))
            a1 = b.tail - d * short + Vector((0.01, dy * 1.2, 0))
            kk.strip([a0, (a0 + a1) * 0.5 + Vector((0.02, 0, 0)), a1], [0.12, 0.12, 0.13], [(1, -0.4, 0)] * 3, C["glove"], thick=0.03)
    for kk in (kr, kr2):
        kk.tag(list(kk.bm.faces), C["glove"], SLOT_RIBBON)
    # hombrera derecha: objeto aparte (se rompe en el acto 3) + su versión rota, metida adentro
    kr_ = rigid["Sode_R"] = Kit("Sode_R", "Sode_R")
    sode_lames(kr_, -1.0)
    kb = rigid["Sode_R_Broken"] = Kit("Sode_R_Broken", "Sode_R")
    sode_lames(kb, -1.0, n_lames=3, jag=True, scale=0.97)


# --------------------------------------------------------------------------- brazos
def build_arm_r(kits):
    S, E, Wr = KR.SHOULDER, KR.ELBOW, KR.WRIST
    u = (E - S).normalized()
    l = (Wr - E).normalized()

    def w_sleeve(co):
        t = (co - S).dot(u) / KR.UPPER_LEN
        w = {"UpperArm_R": 1.0}
        if t < 0.18:
            a = (0.18 - t) / 0.18 * 0.45
            w = {"UpperArm_R": 1.0 - a, "Clav_R": a}
        elif t > 0.82:
            a = min(0.5, (t - 0.82) / 0.18 * 0.5)
            w = {"UpperArm_R": 1.0 - a, "Forearm_R": a}
        return w
    k = kits["UpperArm_R"] = Kit("part_UpperArm_R", "UpperArm_R", weights=w_sleeve)
    k.tube([S - u * 0.05, S + u * 0.3, S + u * 0.62, E + u * 0.03], [0.27, 0.3, 0.28, 0.24], 8, C["glove"],
           ups=[(0, -1, 0)] * 4, phase=math.pi / 8, cap0=False, cap1=False)
    # tres lamas en anillo (como las del dō, en chico) que dejan ver tela negra entre ellas
    ka = Vector((0, -1, 0))
    for j, (t0, r0, r1) in enumerate(((0.3, 0.325, 0.34), (0.56, 0.32, 0.31))):
        c0, c1 = S + u * t0, S + u * (t0 + 0.17)
        xv = ka.cross(u).normalized()
        yv = u.cross(xv).normalized()
        tops, bots, outs = [], [], []
        for i in range(8):
            a = 2 * math.pi * (i + 0.5) / 8
            o = xv * math.cos(a) + yv * math.sin(a)
            tops.append(c0 + o * r0)
            bots.append(c1 + o * r1)
            outs.append(o)
        k.lame(tops, bots, outs, t=0.04, bev=0.03, trim=0.03, face=C["plate"], top=C["bevel2"], tr=C["lace"], closed=True, skip=(5,))
    # kote: antebrazo de laca con placa superior, tachas doradas y puño de hierro
    k = kits["Forearm_R"] = Kit("part_Forearm_R", "Forearm_R")
    k.tube([E - l * 0.04, E + l * 0.4, Wr - l * 0.04], [0.24, 0.235, 0.19], 8, C["plate"], ups=[(0, -1, 0)] * 3, phase=math.pi / 8,
           cap0=False, cap1=False)
    up = (Vector((0, 0, 1)) - l * l.z).normalized()      # parte de afuera/arriba del antebrazo
    side = l.cross(up).normalized()
    tops, bots, outs = [], [], []
    for a in (-50, -20, 10, 40):
        r = math.radians(a)
        o = (up * math.cos(r) + side * math.sin(r)).normalized()
        tops.append(E + l * 0.08 + o * 0.245)
        bots.append(Wr - l * 0.1 + o * 0.205)
        outs.append(o)
    k.lame(tops, bots, outs, t=0.03, bev=0.03, trim=0.03, face=C["plate2"], top=C["bevel"], tr=C["gold2"])
    for i in range(3):
        p = E + l * (0.18 + 0.2 * i) + up * (0.262 - 0.012 * i)
        k.obox(p, (0.07, 0.07, 0.04), side, l, C["gold"])
    k.tube([Wr - l * 0.13, Wr - l * 0.02], [0.215, 0.215], 8, C["steel"], ups=[(0, -1, 0)] * 2, phase=math.pi / 8, cap0=False, cap1=False)
    # codera: tapa dorada en la punta del codo (hacia afuera de la flexión)
    tip = (u - l).normalized()
    k.tube([E + tip * 0.14, E + tip * 0.26], [0.16, 0.06], 6, C["gold2"], phase=math.pi / 6)
    # guante enorme, puño cerrado: la empuñadura pasa por el centro del puño
    k = kits["Hand_R"] = Kit("part_Hand_R", "Hand_R")
    hb = KR.Vector(KR.WRIST)
    hdir = (KR.GRIP - KR.WRIST).normalized()
    across = (KR.BLADE_REST - hdir * KR.BLADE_REST.dot(hdir)).normalized()
    thick = hdir.cross(across).normalized()
    g = KR.GRIP
    k.obox(g + hdir * 0.01, (0.27, 0.31, 0.25), across, hdir, C["glove"], bevel=0.05)
    # barra de nudillos (oro) y pulgar
    k.obox(g + hdir * 0.15 + thick * 0.06, (0.25, 0.06, 0.08), across, hdir, C["gold"])
    k.obox(g + across * 0.12 - thick * 0.11 + hdir * 0.02, (0.1, 0.16, 0.1), across, hdir, C["glove"])
    k.tube([hb - hdir * 0.02, hb + hdir * 0.08], [0.17, 0.2], 8, C["glove"], ups=[thick] * 2, phase=math.pi / 8, cap0=False, cap1=False)


# --------------------------------------------------------------------------- cabeza: kabuto y melena
def build_head(kits):
    k = kits["Head"] = Kit("part_Head", "Head")
    cy = 0.03
    # cráneo dentro del casco (tapa el interior que se ve desde abajo)
    k.tube([(0, cy, 3.5), (0, cy, 3.74)], [0.27, 0.32], 8, C["plate"], phase=math.pi / 8)
    # hachimaki-bachi (cuenco): anillos facetados; lo que mira arriba agarra la luna
    rings = [(3.73, 0.385), (3.86, 0.375), (3.97, 0.33), (4.05, 0.24), (4.09, 0.12)]
    bowl = k.tube([(0, cy, z) for z, _ in rings], [r for _, r in rings], 10, C["plate"], phase=math.pi / 10, cap0=False)
    for f in bowl.faces:
        f.normal_update()
        if f.normal.z > 0.75:
            k.tag([f], C["bevel"])
        elif f.normal.z > 0.35:
            k.tag([f], C["bevel2"])
    k.tube([(0, cy, 4.07), (0, cy, 4.15)], [0.1, 0.06], 8, C["gold"], phase=math.pi / 8)       # tehen
    k.tube([(0, cy, 3.71), (0, cy, 3.77)], [0.395, 0.395], 10, C["gold2"], phase=math.pi / 10, cap0=False, cap1=False)  # koshimaki
    # visera (mabizashi)
    tops, bots, outs = [], [], []
    for a in (-70, -35, 0, 35, 70):
        r = math.radians(a)
        o = Vector((math.sin(r), -math.cos(r), 0.0))
        tops.append(Vector((0, cy, 3.77)) + o * 0.36)
        bots.append(Vector((0, cy, 3.69)) + o * 0.5)
        outs.append(o + Vector((0, 0, 0.6)))
    k.lame(tops, bots, outs, t=0.03, bev=0.02, trim=0.03, face=C["plate"], top=C["bevel"], tr=C["gold"])
    # soporte de la media luna (kuwagata-dai) y cuernos dorados
    k.obox((0, -0.43, 3.86), (0.2, 0.06, 0.16), (1, 0, 0), (0, 0.3, 1), C["plate2"])

    # shikoro: 3 gradas abiertas al frente que abren hacia abajo
    for j in range(3):
        zt = 3.74 - j * 0.115
        rt = 0.39 + j * 0.075
        rb = rt + 0.085
        tops, bots, outs = [], [], []
        angs = [55 + (305 - 55) * i / 7.0 for i in range(8)]
        for a in angs:
            r = math.radians(a)
            o = Vector((math.sin(r), -math.cos(r), 0.0))
            tops.append(Vector((0, cy, zt)) + o * rt)
            bots.append(Vector((0, cy, zt - 0.17)) + o * rb)
            outs.append(o + Vector((0, 0, 0.5)))
        last = j == 2
        k.lame(tops, bots, outs, t=0.04, bev=0.035, trim=0.035, face=C["plate"], top=C["bevel"],
               tr=C["gold"] if last else C["lace"], back=C["plate2"])
    # fukigaeshi: alas dobladas hacia afuera en el frente de la primera grada, rojo oscuro con filo de oro
    for s in (-1.0, 1.0):
        r = math.radians(55)
        o = Vector((math.sin(r) * s, -math.cos(r), 0.0))
        p0 = Vector((0, cy, 3.73)) + o * 0.4
        k.obox(p0 + Vector((0.07 * s, -0.08, -0.06)), (0.06, 0.24, 0.22), (s, -0.7, 0), (0, 0, 1), C["mask2"],
               up_color=C["gold"], up_thresh=0.6)
    # melena: 7 mechones planos (2-3-2 por cadena), en abanico y con una S suave; cada tramo es
    # rígido a su hueso y se solapa con el siguiente para que no se abra al doblar
    groups = {"R": ((-0.08, 1.0, 0.0), (0.06, 1.2, 0.03)), "C": ((-0.1, 1.25, 0.02), (0.0, 1.4, 0.0), (0.1, 1.25, 0.02)),
              "L": ((-0.06, 1.2, 0.03), (0.08, 1.0, 0.0))}
    idx = 0
    for ch, offs in groups.items():
        for ox, ln, dz in offs:
            for seg in (1, 2, 3):
                bn = f"Mane_{ch}_{seg}"
                kk = kits.setdefault(bn, Kit("part_" + bn, bn))
                kb = KR_BONES[bn]
                h, t = kb.head, kb.tail
                d = (t - h) * (ln if seg == 3 else 1.0)
                fan = 1.0 + 0.35 * seg                      # se abren hacia abajo
                a = h - (t - h) * 0.1 + Vector((ox * (fan - 0.35), 0.0, 0.0))
                m = h + d * 0.55 + Vector((ox * (fan - 0.15), 0.02, 0.0))
                b = h + d + Vector((ox * fan, 0.0, -dz if seg == 3 else 0.0))
                w = [(0.17, 0.18, 0.17), (0.17, 0.16, 0.14), (0.14, 0.1, 0.03)][seg - 1]
                col = C["white"] if idx % 2 == 0 else C["white2"]
                kk.strip([a, m, b], list(w), [(0, 1, 0.25)] * 3, col, thick=0.05)
            idx += 1


KR_BONES = {b.name: b for b in KR.bones()}


# --------------------------------------------------------------------------- media luna (dos mitades)
CREST_TILT = 40.0     # hacia atrás: de frente sigue siendo una media luna y desde 55° mira a la cámara


def build_crest(rigid):
    """Maedate: media luna dorada de ~1.1 m, inclinada 28° hacia atrás para leerse desde arriba."""
    for s, side in ((-1.0, "R"), (1.0, "L")):
        k = rigid["Crest_" + side] = Kit("Crest_" + side, "Crest_" + side)
        outer, inner = [], []
        angs = [270.0 + s * (110.0 * i / 6.0) for i in range(7)]
        for a in angs:
            r = math.radians(a)
            outer.append((0.6 * math.cos(r), 0.5 * math.sin(r)))
            inner.append((0.5 * math.cos(r), 0.04 + 0.4 * math.sin(r)))
        tipr = math.radians(angs[-1] + s * 6.0)
        tip = (0.6 * math.cos(tipr) * 0.98, 0.5 * math.sin(tipr) + 0.05)
        poly = outer + [tip] + list(reversed(inner))
        if s > 0:
            poly = list(reversed(poly))
        th = 0.07
        # se apoya por abajo en el soporte de la frente y se inclina hacia atrás desde ahí
        M = (Matrix.Translation((0, -0.46, 3.87)) @ Matrix.Rotation(math.radians(-CREST_TILT), 4, 'X')
             @ Matrix.Translation((0, 0, 0.5)))
        vf = [k.bm.verts.new(M @ Vector((x, -th / 2, z))) for x, z in poly]
        vb = [k.bm.verts.new(M @ Vector((x, th / 2, z))) for x, z in poly]
        n = len(poly)
        fs = []
        for i in range(n):
            j = (i + 1) % n
            fs.append(k.bm.faces.new((vf[i], vb[i], vb[j], vf[j])))
        ff = k.bm.faces.new(vf)
        fb = k.bm.faces.new(list(reversed(vb)))
        k._new(vf + vb, C["gold"], None, None)
        k.tag(fs + [fb], C["gold2"])
        k.tag([ff], C["gold"])
        # los cantos que miran arriba (el interior de la U) agarran la luna: oro claro
        for f in fs:
            f.normal_update()
            if f.normal.z > 0.3:
                k.tag([f], C["gold"])


# --------------------------------------------------------------------------- máscara (menpo oni)
def build_mask(rigid):
    k = rigid["Mask"] = Kit("Mask", "Mask")
    xs = [-0.27, -0.19, -0.1, 0.0, 0.1, 0.19, 0.27]
    rows = [3.90, 3.82, 3.75, 3.67, 3.59, 3.52, 3.45]

    def depth(x, z):
        ax = abs(x)
        y = -0.43 + 0.55 * ax * ax + 0.04 * ax
        if z >= 3.88:
            y += 0.04
        if 3.8 <= z <= 3.84:
            y -= 0.035                              # ceño
        if abs(z - 3.67) < 0.01 and ax < 0.05:
            y -= 0.07                               # nariz
        if abs(z - 3.67) < 0.01 and 0.15 < ax < 0.22:
            y -= 0.03                               # pómulos
        if z <= 3.47:
            y += 0.03
        return y
    grid = [[Vector((x, depth(x, z), z + (0.025 if (z == 3.75 and abs(x) > 0.15) else 0.0))) for x in xs] for z in rows]
    # frente y dorso (espesor 3.5 cm: la máscara se ve también cuando cae al piso)
    vf = [[k.bm.verts.new(p) for p in row] for row in grid]
    front = {}
    for r in range(len(rows) - 1):
        for c in range(len(xs) - 1):
            f = k.bm.faces.new((vf[r][c], vf[r][c + 1], vf[r + 1][c + 1], vf[r + 1][c]))
            front[(r, c)] = f
    rim = []
    R, Cc = len(rows) - 1, len(xs) - 1
    edge = [(0, c) for c in range(Cc + 1)] + [(r, Cc) for r in range(1, R + 1)] + [(R, c) for c in range(Cc - 1, -1, -1)] + [(r, 0) for r in range(R - 1, 0, -1)]
    vbe = [k.bm.verts.new(vf[a][b].co + Vector((0, 0.035, 0))) for a, b in edge]
    for i in range(len(edge)):
        a, b = edge[i], edge[(i + 1) % len(edge)]
        rim.append(k.bm.faces.new((vf[a[0]][a[1]], vbe[i], vbe[(i + 1) % len(edge)], vf[b[0]][b[1]])))
    back = [k.bm.faces.new(list(reversed(vbe)))]
    k._new([v for row in vf for v in row] + vbe, C["mask"], None, None)
    k.tag(back + rim, C["mask2"])
    # ceño fruncido (fila 0-1) más oscuro, ojos violetas (fila 2, columnas 1 y 4), boca negra
    for c in range(Cc):
        k.tag([front[(0, c)]], C["mask2"])
    for c in (1, 4):
        k.tag([front[(2, c)]], "glow_purple", SLOT_SEAMS)
    for c in (2, 3):
        k.tag([front[(4, c)]], C["plate"])
    # colmillos (2 arriba, 2 abajo), bigote y barba blanca, patillas
    for x, z, dz in ((-0.07, 3.585, -0.09), (0.07, 3.585, -0.09), (-0.15, 3.52, 0.08), (0.15, 3.52, 0.08)):
        k.tube([(x, -0.455, z), (x, -0.46, z + dz)], [0.034, 0.004], 3, C["white"], ups=[(0, -1, 0)] * 2, phase=math.pi / 2)
    for x, z1, w0, col in ((0.0, 3.13, 0.075, C["white"]), (-0.09, 3.27, 0.06, C["white2"]), (0.09, 3.27, 0.06, C["white2"])):
        k.tube([(x, -0.42, 3.5), (x * 1.15, -0.455, 3.38), (x * 1.3, -0.43, z1)], [(w0, 0.04), (w0 * 0.75, 0.035), (0.01, 0.01)],
               4, col, ups=[(0, -1, 0)] * 3, phase=math.pi / 4, cap0=False)
    for s in (-1.0, 1.0):     # bigote que cae a los costados de la boca
        k.tube([(0.05 * s, -0.47, 3.6), (0.15 * s, -0.47, 3.55), (0.2 * s, -0.44, 3.44)], [(0.035, 0.025), (0.03, 0.02), (0.006, 0.006)],
               4, C["white2"], ups=[(0, -1, 0)] * 3, phase=math.pi / 4)

    # grieta del lado izquierdo (se enciende en el eclipse): mismo rojo que la máscara, apenas en relieve
    pts = [Vector((0.07, 0, 3.9)), Vector((0.12, 0, 3.82)), Vector((0.1, 0, 3.67)), Vector((0.2, 0, 3.53))]
    for p in pts:
        p.y = depth(p.x, round(p.z, 2)) - 0.006
    st = k.strip(pts, [0.03] * len(pts), [(0, -1, 0.15)] * len(pts), C["mask"], thick=0.012)
    k.tag(st.faces, C["mask"], SLOT_MASKCRACK)


def build_face(rigid):
    """El rostro bajo la máscara (se ve recién en el final): viejo guerrero curtido, cejas blancas,
    cicatriz sobre el ojo izquierdo, barba corta gris."""
    k = rigid["Face"] = Kit("Face", "Head")
    xs = [-0.22, -0.14, -0.06, 0.06, 0.14, 0.22]
    rows = [3.86, 3.78, 3.71, 3.64, 3.57, 3.5]

    def depth(x, z):
        ax = abs(x)
        y = -0.32 + 0.6 * ax * ax
        if abs(z - 3.64) < 0.01 and ax < 0.07:
            y -= 0.04
        if abs(z - 3.78) < 0.01:
            y -= 0.012
        return y
    grid = [[Vector((x, depth(x, z), z)) for x in xs] for z in rows]
    vf = [[k.bm.verts.new(p) for p in row] for row in grid]
    faces = {}
    for r in range(len(rows) - 1):
        for c in range(len(xs) - 1):
            faces[(r, c)] = k.bm.faces.new((vf[r][c], vf[r][c + 1], vf[r + 1][c + 1], vf[r + 1][c]))
    k._new([v for row in vf for v in row], C["skin"], None, None)
    # costados hacia atrás (cierra el volumen dentro del casco)
    for r in range(len(rows) - 1):
        for c in (0, len(xs) - 1):
            a, b = vf[r][c], vf[r + 1][c]
            pa, pb = a.co + Vector((0, 0.18, 0)), b.co + Vector((0, 0.18, 0))
            va, vb = k.bm.verts.new(pa), k.bm.verts.new(pb)
            f = k.bm.faces.new((a, b, vb, va))
            k._new([va, vb], C["skin"], None, None)
    for c in (0, 1, 3, 4):
        k.obox((xs[c] * 0.5 + xs[c + 1] * 0.5, depth(xs[c], 3.78) - 0.02, 3.79), (0.1, 0.03, 0.035), (1, 0, 0.25 if c < 2 else -0.25), (0, 1, 0), C["white2"])
    for c in (1, 3):
        k.obox((xs[c] * 0.5 + xs[c + 1] * 0.5, depth(xs[c], 3.71) - 0.012, 3.735), (0.08, 0.02, 0.018), (1, 0, 0), (0, 1, 0), C["plate"])
    k.obox((0.1, -0.345, 3.75), (0.025, 0.02, 0.2), (1, 0, 0.3), (0, 1, 0), C["mask2"])        # cicatriz
    k.obox((0, -0.31, 3.55), (0.12, 0.02, 0.02), (1, 0, 0), (0, 1, 0), C["mask2"])             # boca
    for s in (-1.0, 1.0):
        k.tube([(0.03 * s, -0.345, 3.585), (0.1 * s, -0.33, 3.53)], [0.025, 0.008], 4, C["white2"], ups=[(0, -1, 0)] * 2)
    k.tube([(0, -0.31, 3.51), (0, -0.33, 3.43)], [(0.1, 0.04), (0.03, 0.02)], 4, C["white2"], ups=[(0, -1, 0)] * 2, phase=math.pi / 4)


# --------------------------------------------------------------------------- nodachi (espacio local)
def build_sword(rigid):
    """Nodachi de 3.1 m en el espacio del hueso Katana: Y a lo largo de la hoja desde el centro del
    puño, Z = lomo. El filo usa su propio material (Kokuyo_Edge) para encenderse en los avisos."""
    k = rigid["Katana_Nodachi"] = Kit("Katana_Nodachi", "Katana")
    po = -KR.POMMEL_OFF
    # tsuka con cruces de cuerda
    k.tube([(0, po + 0.06, 0), (0, 0.12, 0)], [0.052, 0.056], 6, C["glove"], ups=[(0, 0, 1)] * 2, phase=math.pi / 6)
    n = 6
    for i in range(n):
        y = po + 0.1 + i * (0.12 - po - 0.14) / (n - 1)
        k.tube([(0, y - 0.03, 0), (0, y + 0.03, 0)], [0.062, 0.062], 6, C["rope"], ups=[(0, 0, 1)] * 2, phase=math.pi / 6 + 0.5)
    k.tube([(0, po - 0.02, 0), (0, po + 0.07, 0)], [0.05, 0.068], 6, C["steel"], ups=[(0, 0, 1)] * 2, phase=math.pi / 6)
    # tsuba de 8 lados y habaki
    tb = k.tube([(0, 0.12, 0), (0, 0.165, 0)], [0.18, 0.17], 8, C["gold"], ups=[(0, 0, 1)] * 2, phase=math.pi / 8)
    k.tube([(0, 0.165, 0), (0, 0.27, 0)], [(0.04, 0.09), (0.035, 0.085)], 4, C["gold2"], ups=[(0, 0, 1)] * 2, phase=math.pi / 4)
    # hoja: sección de 6 lados (lomo, dos caras, dos biseles de filo, filo), sori de 12 cm
    LB = 2.3
    N = 10
    rings = []
    for i in range(N + 1):
        t = i / N
        y = 0.27 + LB * t
        zc = 0.12 * t * t
        h = 0.17 - 0.06 * t                # de lomo a filo
        th = 0.026 - 0.008 * t
        top = zc + h * 0.42
        bot = zc - h * 0.58
        shin = zc + h * 0.12
        rings.append([Vector((0, y, top)), Vector((th, y, shin)), Vector((th * 0.55, y, bot + 0.035)), Vector((0, y, bot)),
                      Vector((-th * 0.55, y, bot + 0.035)), Vector((-th, y, shin))])
    tip = Vector((0, 0.27 + LB + 0.2, 0.12 + 0.02))
    vr = [[k.bm.verts.new(p) for p in r] for r in rings]
    vt = k.bm.verts.new(tip)
    edge_f, flat_f, spine_f = [], [], []
    for a, b in zip(vr[:-1], vr[1:]):
        for i in range(6):
            j = (i + 1) % 6
            f = k.bm.faces.new((a[i], a[j], b[j], b[i]))
            (edge_f if i in (2, 3) else spine_f if i in (0, 5) and False else flat_f).append(f)
    for i in range(6):
        j = (i + 1) % 6
        f = k.bm.faces.new((vr[-1][i], vr[-1][j], vt))
        (edge_f if i in (2, 3) else flat_f).append(f)
    k.bm.faces.new(list(reversed(vr[0])))
    k._new([v for r in vr for v in r] + [vt], C["steel"], None, None)
    k.tag(edge_f, "white", SLOT_EDGE)
    for f in flat_f:
        f.normal_update()
    # lomo y caras: el lomo en hierro oscuro (contraste con el filo que brilla)
    for a, b in zip(vr[:-1], vr[1:]):
        pass


# --------------------------------------------------------------------------- grietas del pecho
CRACK_ORIGIN = (0.12, 2.95)    # punto de impacto, apenas a la izquierda del esternón
CRACKS = [   # (x, z) desde el impacto hacia afuera; se encienden de 1 a 5, una por punto de desequilibrio
    [(0.12, 2.95), (0.02, 3.0), (-0.06, 2.98), (-0.17, 3.07), (-0.3, 3.1), (-0.42, 3.19)],
    [(0.12, 2.95), (0.2, 3.04), (0.27, 3.03), (0.36, 3.13), (0.48, 3.16)],
    [(0.12, 2.95), (0.1, 2.85), (0.15, 2.77), (0.11, 2.68), (0.14, 2.58)],
    [(0.12, 2.95), (0.24, 2.9), (0.33, 2.93), (0.45, 2.84), (0.58, 2.83)],
    [(0.12, 2.95), (0.03, 2.88), (-0.08, 2.9), (-0.16, 2.8), (-0.3, 2.77)],
]


def build_cracks(rigid):
    for i, pts2 in enumerate(CRACKS):
        k = rigid[f"Crack_{i + 1}"] = Kit(f"Crack_{i + 1}", "Chest")
        pts = [Vector((x, torso_front_y(x, z) - 0.03, z)) for x, z in pts2]
        n = len(pts)
        ws = [0.06 - 0.045 * j / (n - 1) for j in range(n)]
        st = k.strip(pts, ws, [(0, -1, 0)] * len(pts), "glow_purple", thick=0.025)
        k.tag(st.faces, "glow_purple", SLOT_SEAMS)


# --------------------------------------------------------------------------- armado
def build(arm, rig):
    """Construye todo y lo engancha a la armadura. Devuelve (cuerpo, {nombre: objeto rígido}, stats)."""
    kits, rigid = {}, {}
    build_leg_r(kits)
    build_arm_r(kits)
    for bn in ("Foot_R", "Shin_R", "Thigh_R", "UpperArm_R", "Forearm_R", "Hand_R"):
        src = kits[bn]
        ln = bn[:-2] + "_L"
        wf = None
        if src.weights:
            fr = src.weights
            def wf(co, fr=fr):
                w = fr(Vector((-co.x, co.y, co.z)))
                return {(n[:-2] + "_L" if n.endswith("_R") else n): v for n, v in w.items()}
        kits[ln] = mirror_bm_kit(src, "part_" + ln, ln, weights=wf)
    build_hips(kits)
    build_sash(kits)
    build_skirt(kits)
    build_torso(kits)
    build_shoulders(kits, rigid)
    build_head(kits)
    build_crest(rigid)
    build_mask(rigid)
    build_face(rigid)
    build_sword(rigid)
    build_cracks(rigid)
    # cinta del pomo: va en el cuerpo (hueso Tassel_1/2, hijos de Katana)
    pom = KR.GRIP - KR.BLADE_REST * KR.POMMEL_OFF
    for seg, z0, z1 in ((1, 0.0, -0.29), (2, -0.27, -0.56)):
        bn = f"Tassel_{seg}"
        k = kits[bn] = Kit("part_" + bn, bn)
        for dx in (-0.035, 0.035):
            pts = [pom + Vector((dx, 0.03, z0)), pom + Vector((dx * 1.4, 0.05, (z0 + z1) / 2)), pom + Vector((dx * 1.8, 0.06, z1))]
            k.strip(pts, [0.09, 0.1, 0.11], [(0, 1, 0)] * 3, C["glove"], thick=0.03)
        if seg == 1:
            k.obox(pom + Vector((0, 0.02, -0.03)), (0.11, 0.1, 0.09), (1, 0, 0), (0, 1, 0), C["glove"])
        k.tag(list(k.bm.faces), C["glove"], SLOT_RIBBON)

    stats = {}
    objs = []
    per_kit = {}
    for bn, k in kits.items():
        o = finish_kit(k, EXTRA_MATS)
        per_kit[bn] = tri_count(o)
        vg = {}
        for v in o.data.vertices:
            w = k.weights(v.co) if k.weights else {k.bone: 1.0}
            for name, val in w.items():
                if name not in vg:
                    vg[name] = o.vertex_groups.get(name) or o.vertex_groups.new(name=name)
                vg[name].add([v.index], val, 'REPLACE')
        objs.append(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    body = bpy.context.view_layer.objects.active
    body.name = "Kokuyo_Body"
    body.data.name = "Kokuyo_Body"
    body.parent = arm
    mod = body.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    stats["body"] = tri_count(body)
    print("TRIS_POR_PIEZA", sorted(per_kit.items(), key=lambda kv: -kv[1]))
    out = {}
    for name, k in rigid.items():
        o = finish_kit(k, EXTRA_MATS)
        o.name = name
        o.data.name = name
        bone = k.bone
        M = rig.rest[bone]
        o.data.transform(M.inverted()) if name != "Katana_Nodachi" else None
        o.matrix_world = M
        o.parent = arm
        o.parent_type = 'BONE'
        o.parent_bone = bone
        bpy.context.view_layer.update()
        o.matrix_world = M
        out[name] = o
        stats[name] = tri_count(o)
    # limpia ranuras de material vacías (Unity no necesita submallas fantasma)
    for o in [body] + list(out.values()):
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.material_slot_remove_unused()
        o.select_set(False)
    return body, out, stats
