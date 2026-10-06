"""Utilidades compartidas del Gran Koi (Mizuchi): rutas, materiales de la paleta y un constructor de
mallas con pesos de huesos.

Por qué no se usa nindo_lib.MeshBuilder tal cual: un personaje necesita pesos de piel por vértice al
crearlo (no hay auto-weights, el resultado tiene que ser determinista) y aletas de doble cara cuya cara
trasera ocupa las MISMAS posiciones que la delantera. MeshBuilder.finish() funde vértices duplicados y
recalcula normales, lo que pegaría las dos caras de cada aleta. Este constructor respeta el sentido de
cada cara tal como se crea (el que llama decide hacia dónde mira) y escribe el mismo atlas de paleta
(UV al centro del color) y los mismos slots de material que el resto del juego.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS_BLENDER = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(os.path.dirname(TOOLS_BLENDER))
for p in (TOOLS_BLENDER, os.path.join(TOOLS_BLENDER, "props")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import nindo_palette as P   # noqa: E402
import nindo_lib as L       # noqa: E402

SLOT_PALETTE, SLOT_EMISSIVE = 0, 1
# el brillo del koi no usa Nindo_Emissive (x3.2): con el ACES del juego el violeta de la fase 2 salía
# casi blanco (saturación 0.15). Cada fase lleva su material de brillo (Unity los remapea por nombre a
# Art/Characters/Mizuchi/Mizuchi_Glow.mat y Mizuchi_Curse.mat, ver generate_assets.character_fbx_metas)
GLOW_P1, GLOW_P2 = "Mizuchi_Glow", "Mizuchi_Curse"
SLOTS = ["Nindo_Palette", GLOW_P1]
# fuerza de emisión de las vistas de Blender (sin ACES): solo para que los renders de revisión se parezcan
GLOW_STRENGTH = {GLOW_P1: 1.4, GLOW_P2: 1.3}


# ------------------------------------------------------------------ matemática chica
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def catmull(table, x):
    """Interpolación Catmull-Rom de una tabla [(x, valor), ...] ordenada por x (sin rebotes en los extremos)."""
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, x1 = table[i][0], table[i + 1][0]
        if x0 <= x <= x1:
            p0 = table[max(i - 1, 0)][1]
            p1, p2 = table[i][1], table[i + 1][1]
            p3 = table[min(i + 2, len(table) - 1)][1]
            t = (x - x0) / (x1 - x0)
            t2, t3 = t * t, t * t * t
            v = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            lo, hi = min(p1, p2), max(p1, p2)
            # Catmull-Rom puede pasarse entre dos muestras: acotado al tramo para que la silueta no ondule
            span = hi - lo
            return clamp(v, lo - 0.15 * span, hi + 0.15 * span)
    return table[-1][1]


def spow(v, e):
    """Potencia con signo (superelipses)."""
    return math.copysign(abs(v) ** e, v)


def frame_from(d, up_hint=Vector((0, 0, 1))):
    """Base ortonormal (x, y=d, z) con z lo más parecido posible a up_hint."""
    d = Vector(d).normalized()
    up = Vector(up_hint)
    if abs(d.dot(up.normalized())) > 0.98:
        up = Vector((0, -1, 0))
    x = d.cross(up).normalized()
    z = x.cross(d).normalized()
    return x, d, z


# ------------------------------------------------------------------ materiales (los mismos del resto del juego)
def material(name):
    """Nindo_Palette (el del juego) o uno de los brillos del koi: el mismo atlas de paleta con la emisión
    enchufada al color (en Unity el mapa de emisión solo tiene las muestras glow_*)."""
    if name not in GLOW_STRENGTH:
        return L.get_material(name)
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = L.get_material(name)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = next(n for n in nt.nodes if n.type == 'TEX_IMAGE')
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = GLOW_STRENGTH[name]
    return m


def materials(slots=None):
    return [material(n) for n in (slots or SLOTS)]


# ------------------------------------------------------------------ constructor de mallas con pesos
class KoiBuilder:
    """Malla de paleta con pesos de huesos. v(co, pesos) crea un vértice; face(...) una cara con color.

    'outward' (opcional) en face(): un punto o dirección hacia donde debe mirar la cara; si la normal
    calculada apunta al revés se invierte el orden. Así las piezas se pueden escribir sin pensar en el
    sentido de giro y las caras de las aletas (doble cara) quedan bien de los dos lados."""

    def __init__(self, name, bone_names, slots=None):
        self.name = name
        self.slots = list(slots or SLOTS)
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.dl = self.bm.verts.layers.deform.verify()
        self.gi = {n: i for i, n in enumerate(bone_names)}
        self.bone_names = list(bone_names)

    def v(self, co, w):
        vv = self.bm.verts.new(Vector(co))
        self.set_w(vv, w)
        return vv

    def set_w(self, vv, w):
        # como mucho 4 huesos por vértice (Unity: maxBonesPerVertex 4) y pesos normalizados
        items = sorted(((b, x) for b, x in w.items() if x > 1e-4), key=lambda t: -t[1])[:4]
        tot = sum(x for _, x in items) or 1.0
        vv[self.dl].clear()
        for b, x in items:
            vv[self.dl][self.gi[b]] = x / tot

    def get_w(self, vv):
        return {self.bone_names[i]: x for i, x in vv[self.dl].items()}

    def face(self, verts, color, outward=None, slot=None):
        if outward is not None:
            n = _poly_normal([v.co for v in verts])
            c = sum((v.co for v in verts), Vector()) / len(verts)
            ref = Vector(outward) if isinstance(outward, Dir) else Vector(outward) - c
            if n.dot(ref) < 0:
                verts = list(reversed(verts))
        try:
            f = self.bm.faces.new(verts)
        except ValueError:
            return None
        u, vv = P.uv_of(color)
        if slot is None:
            slot = SLOT_EMISSIVE if color.startswith("glow_") and len(self.slots) > 1 else SLOT_PALETTE
        f.material_index = slot
        f.smooth = False
        for lp in f.loops:
            lp[self.uv].uv = (u, vv)
        return f

    def double(self, verts, color, front_dir):
        """Cara de doble lado (aletas, papel): la de adelante mira a front_dir, la otra al revés con
        vértices propios (mismas posiciones y pesos) para que no se fundan."""
        f1 = self.face(verts, color, outward=Dir(front_dir))
        back = [self.copy(v) for v in verts]
        f2 = self.face(back, color, outward=Dir(-Vector(front_dir)))
        return f1, f2

    def copy(self, v):
        nv = self.bm.verts.new(v.co.copy())
        for k, x in v[self.dl].items():
            nv[self.dl][k] = x
        return nv

    def finish(self, collection=None):
        bm = self.bm
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for m in materials(self.slots):
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        for n in self.bone_names:
            ob.vertex_groups.new(name=n)
        return ob


class Dir(tuple):
    """Marca un 'outward' como dirección (no como punto)."""
    def __new__(cls, v):
        return super().__new__(cls, tuple(Vector(v).normalized()))


def _poly_normal(cos):
    n = Vector()
    for i in range(len(cos)):
        a, b = cos[i], cos[(i + 1) % len(cos)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n.normalized() if n.length > 1e-12 else Vector((0, 0, 1))


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
