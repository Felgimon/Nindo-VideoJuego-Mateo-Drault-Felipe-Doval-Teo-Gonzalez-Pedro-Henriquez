"""Biblioteca de los kits de accesorios por zona (Blender 4.4, modo -b).

Un kit es UNA malla con skin ('Acc_Kit') sobre el esqueleto del personaje del equipo, más huesos nuevos
para lo que se mueve solo (cintas, capas, flecos: cadenas 'Acc_<Nombre>_<i>' que terminan en
'Acc_<Nombre>_end') y marcadores de colisión ('AccCol_<Nombre>_<radio en centésimas>'). En Unity,
Core/CharacterKits.cs instancia el FBX del kit, cuelga las cadenas de los huesos vivos del personaje con
el mismo nombre, re-apunta los huesos del SkinnedMeshRenderer por nombre y tira el resto; FX/SpringChain.cs
mueve las cadenas.

Por qué todo con skin y nada "pegado a un hueso": el skin solo depende de la pose de bind (la misma en el
kit y en el personaje, porque el kit se exporta desde el MISMO armature importado, sin tocar un hueso), no
de la pose por defecto de cada FBX, que en los del equipo no es la de reposo.

Coordenadas: espacio MUNDO de Blender del FBX importado en reposo (Z arriba, unidades del archivo). Cada
personaje anota hacia dónde mira (CHARS[...]['front']).

Colores: los de la paleta compartida (nindo_palette.py) con UVs al centro de cada muestra, en los
materiales Nindo_Palette / Nindo_Emissive (el .meta los remapea a los del proyecto, como los props).
"""
import bpy, bmesh, math, os, re, sys, json, random, collections
from mathutils import Vector, Matrix, Quaternion, kdtree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ASSETS = os.path.join(REPO, "Nindo", "Assets")
KITS_DIR = os.path.join(ASSETS, "Nindo", "Art", "Characters", "Kits")
sys.path.insert(0, os.path.join(REPO, "Tools", "Blender"))
import nindo_palette as P  # noqa: E402

# fbx: ruta dentro de Assets; body: malla con skin; front: hacia dónde mira en el FBX; height: metros en el juego
CHARS = {
    "ninja": dict(fbx="Models/Ninja/Ninja 1.fbx", body="Cube", front=(1, 0, 0), height=1.7),
    "sumo": dict(fbx="Characters/Sumo/luchadorsumo.fbx", body="Cube", front=(0, 1, 0), height=2.6),
    "kaito": dict(fbx="Animations teo/kaitooo.fbx", body="Cuerpo", front=(1, 0, 0), height=1.5),
}

# lo mismo que usan los FBX del equipo (Tools/Blender/characters): 0.0° de diferencia en la pose de bind
EXPORT = dict(object_types={'ARMATURE', 'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
              axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X',
              mesh_smooth_type='OFF', use_armature_deform_only=False, path_mode='STRIP', embed_textures=False,
              bake_anim=False, use_mesh_modifiers=False, use_custom_props=False)


# ======================================================================= utilidades
def V(*a):
    return Vector(a[0]) if len(a) == 1 else Vector(a)


def base(name):
    return re.sub(r"\.\d{3}$", "", name)


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0))) if e1 != e0 else (1.0 if x >= e1 else 0.0)
    return t * t * (3 - 2 * t)


def frame(origin, x, z):
    """Matriz con origen y ejes X/Z dados (Y = Z x X): para armar piezas en un sistema local cómodo."""
    x = V(x).normalized(); z = V(z).normalized()
    y = z.cross(x).normalized(); z = x.cross(y).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = V(origin)
    return m


def rot_axis(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, V(axis))


# ======================================================================= personaje
class Char:
    def __init__(self, key, arm, body):
        self.key = key
        self.arm = arm
        self.body = body
        self.front = V(CHARS[key]["front"])
        self.up = V(0, 0, 1)
        self.side = self.up.cross(self.front)          # hacia la izquierda del personaje
        self._kd = None

    def bvh(self):
        if getattr(self, "_bvh", None) is None:
            from mathutils.bvhtree import BVHTree
            dg = bpy.context.evaluated_depsgraph_get()
            ev = self.body.evaluated_get(dg)
            me = ev.to_mesh()
            mw = self.body.matrix_world
            verts = [mw @ v.co for v in me.vertices]
            polys = [tuple(q.vertices) for q in me.polygons]
            ev.to_mesh_clear()
            self._bvh = BVHTree.FromPolygons(verts, polys)
        return self._bvh

    def surface(self, p, offset=0.0):
        """Punto de la piel más cercano a p, empujado 'offset' hacia afuera por la normal (redes y pieles que
        se apoyan en el cuerpo en vez de flotar)."""
        loc, nrm, _, _ = self.bvh().find_nearest(V(p))
        if loc is None:
            return V(p)
        if (V(p) - loc).dot(nrm) < 0:
            nrm = -nrm
        return loc + nrm * offset

    def hug(self, c, a, z, offset, fallback):
        """Punto de la piel a la altura z en la dirección horizontal 'a' (grados) desde el eje c (x, y), empujado
        'offset' hacia afuera: un cinturón que abraza la panza a la misma altura en vez de flotar como un aro.
        Rayo de afuera hacia el eje (el primer impacto es la piel de afuera aunque haya brazos más lejos, porque
        el rayo arranca a 'fallback' + 0.05 del eje, apenas fuera del radio del cinto)."""
        d = V(math.cos(math.radians(a)), math.sin(math.radians(a)), 0)
        o = V(c[0], c[1], z) + d * (fallback + 0.05)
        hit, _, _, dist = self.bvh().ray_cast(o, -d, fallback + 0.05)
        if hit is None:
            return V(c[0], c[1], z) + d * fallback
        return hit + d * offset

    def bone_head(self, name):
        return self.arm.matrix_world @ self.arm.data.bones[name].head_local

    def bone_tail(self, name):
        return self.arm.matrix_world @ self.arm.data.bones[name].tail_local

    # pesos copiados del cuerpo: las telas que van pegadas siguen la deformación de la piel de abajo
    def body_kd(self):
        if self._kd is None:
            me = self.body.data
            gname = {g.index: g.name for g in self.body.vertex_groups}
            mw = self.body.matrix_world
            self._bw = []
            self._bp = []
            for v in me.vertices:
                self._bp.append(mw @ v.co)
                self._bw.append({gname[g.group]: g.weight for g in v.groups if g.weight > 1e-4 and g.group in gname})
            kd = kdtree.KDTree(len(self._bp))
            for i, p in enumerate(self._bp):
                kd.insert(p, i)
            kd.balance()
            self._kd = kd
        return self._kd

    def body_weights(self, p, allow=None, k=4):
        """Promedio (por inversa de la distancia) de los pesos de los k vértices del cuerpo más cercanos.
        allow: solo vértices cuyo hueso dominante está en ese conjunto (una faja no copia pesos del brazo)."""
        kd = self.body_kd()
        acc = collections.Counter()
        tot = 0.0
        n = 0
        for co, i, d in kd.find_n(p, 64 if allow else k):
            w = self._bw[i]
            if not w:
                continue
            if allow is not None and max(w, key=w.get) not in allow:
                continue
            f = 1.0 / max(d, 1e-3)
            for b, x in w.items():
                acc[b] += x * f
            tot += f
            n += 1
            if n >= k:
                break
        if tot <= 0:
            return None
        return {b: x / tot for b, x in acc.items()}


def load_char(key, src_assets=None, actions_from=None):
    """Importa el FBX del personaje en una escena vacía (reposo). actions_from: otro FBX del mismo esqueleto del
    que se toman las acciones (el sumo del equipo ya no trae tomas: sus clips son .anim de Unity)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = src_assets or ASSETS
    path = os.path.join(root, CHARS[key]["fbx"])
    if actions_from:
        bpy.ops.import_scene.fbx(filepath=actions_from)
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for a in bpy.data.actions:
            a.use_fake_user = True
        for m in list(bpy.data.meshes):
            bpy.data.meshes.remove(m)
        for im in list(bpy.data.images):
            bpy.data.images.remove(im)
    bpy.ops.import_scene.fbx(filepath=path)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    # las tomas del equipo también animan el objeto Armature (posición/escala): para posar y renderizar se
    # usan solo las curvas de los huesos, si no cada frame lo devolvía a su lugar y escala del FBX
    for a in bpy.data.actions:
        for fc in [fc for fc in a.fcurves if not fc.data_path.startswith("pose.")]:
            a.fcurves.remove(fc)
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    body = bpy.data.objects[CHARS[key]["body"]]
    return Char(key, arm, body)


def bind_slots(arm):
    """El importador de 4.4 crea un slot por toma con otro identificador: sin esto la acción no anima nada."""
    for a in bpy.data.actions:
        if len(a.slots) == 1:
            a.slots[0].name_display = arm.name


def use_action(arm, sub):
    bind_slots(arm)
    act = next((a for a in bpy.data.actions if a.name.lower().endswith("|" + sub.lower())), None) or \
        next((a for a in bpy.data.actions if sub.lower() in a.name.lower()), None)
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act is not None and ad.action_slot is None and act.slots:
        ad.action_slot = act.slots[0]
    arm.data.pose_position = 'POSE'
    return act


# ======================================================================= geometría
class Part:
    """Rango de vértices recién creados: se les asignan pesos de una de cuatro maneras."""

    def __init__(self, geo, idx):
        self.geo = geo
        self.idx = list(idx)

    def rigid(self, bone):
        for i in self.idx:
            self.geo.w[i] = {bone: 1.0}
        return self

    def body(self, allow=None, k=4):
        """Pesos de la piel más cercana (solo de los huesos 'allow' si se puede: lejos de ellos, de cualquiera)."""
        ch = self.geo.kit.char
        for i in self.idx:
            p = self.geo.v[i]
            self.geo.w[i] = ch.body_weights(p, allow, k) or ch.body_weights(p, None, k)
        return self

    def chain(self, name, base_weight=None, base_until=0.0):
        """Pesos a lo largo de la cadena 'name' (proyección al tramo más cercano, mezcla suave en las juntas).
        base_weight: pesos del ancla para la parte de arriba (t < base_until del largo total)."""
        ch = self.geo.kit.chains[name]
        for i in self.idx:
            self.geo.w[i] = ch.weights(self.geo.v[i], base_weight, base_until)
        return self

    def fn(self, f):
        for i in self.idx:
            self.geo.w[i] = f(self.geo.v[i])
        return self


class Geo:
    def __init__(self, kit):
        self.kit = kit
        self.v = []          # Vector mundo
        self.w = []          # {hueso: peso}
        self.f = []          # (indices, color de paleta)

    def add(self, pts):
        i0 = len(self.v)
        for p in pts:
            self.v.append(V(p)); self.w.append(None)
        return list(range(i0, i0 + len(pts)))

    def face(self, idx, color):
        self.f.append((tuple(idx), color))

    # ---------------------------------------------------------------- primitivas base
    def loft(self, rings, color, closed=True, cap0=False, cap1=False, colors=None):
        """Une anillos de igual cantidad de puntos. colors(i_anillo, j) -> color por cara."""
        ids = [self.add(r) for r in rings]
        n = len(rings[0])
        m = n if closed else n - 1
        for a in range(len(ids) - 1):
            for j in range(m):
                k = (j + 1) % n
                self.face((ids[a][j], ids[a][k], ids[a + 1][k], ids[a + 1][j]), colors(a, j) if colors else color)
        if cap0:
            self.face(list(reversed(ids[0])), color)
        if cap1:
            self.face(ids[-1], color)
        return Part(self, [i for r in ids for i in r])

    def poly(self, pts, color):
        idx = self.add(pts)
        self.face(idx, color)
        return Part(self, idx)

    # ---------------------------------------------------------------- piezas
    def band(self, M, rx, ry, h, t, color, seg=12, rx2=None, ry2=None, a0=0.0, a1=360.0, jitter=0.0, seed=1,
             colors=None, zfn=None):
        """Banda elíptica (cinta, faja, cuello) alrededor del eje Z local de M; abierta si a1-a0 < 360.
        rx2/ry2: radios arriba (cónica). zfn(u) -> desplazamiento vertical del anillo según el ángulo (0..1)."""
        rx2 = rx if rx2 is None else rx2; ry2 = ry if ry2 is None else ry2
        full = abs(a1 - a0) >= 359.9
        nseg = seg if full else seg + 1
        rnd = random.Random(seed)
        rings = [[], [], [], []]
        for j in range(nseg):
            u = j / seg
            a = math.radians(a0 + (a1 - a0) * u)
            ca, sa = math.cos(a), math.sin(a)
            jj = 1.0 + (rnd.uniform(-jitter, jitter) if jitter else 0.0)
            dz = zfn(u) if zfn else 0.0
            rings[0].append(M @ V(rx * jj * ca, ry * jj * sa, -h / 2 + dz))
            rings[1].append(M @ V(rx2 * jj * ca, ry2 * jj * sa, h / 2 + dz))
            rings[2].append(M @ V((rx2 - t) * jj * ca, (ry2 - t) * jj * sa, h / 2 + dz))
            rings[3].append(M @ V((rx - t) * jj * ca, (ry - t) * jj * sa, -h / 2 + dz))
        # perfil: exterior abajo->arriba, tapa, interior, base
        prof = [rings[0], rings[1], rings[2], rings[3], rings[0]]
        ids = [self.add(r) for r in prof[:4]]
        ids.append(ids[0])
        m = nseg if full else nseg - 1
        for a in range(4):
            for j in range(m):
                k = (j + 1) % nseg
                c = colors(a, j) if colors else color
                self.face((ids[a][j], ids[a][k], ids[a + 1][k], ids[a + 1][j]), c)
        if not full:
            for e in (0, nseg - 1):
                q = [ids[0][e], ids[1][e], ids[2][e], ids[3][e]]
                self.face(q if e == 0 else list(reversed(q)), color)
        return Part(self, [i for r in ids[:4] for i in r])

    def tube(self, pts, r, color, sides=6, twist=0.0, up=(0, 0, 1), cap0=True, cap1=True, colors=None, sy=1.0, phase=0.0):
        """Tubo por una polilínea. r: radio o lista por punto. twist: grados por punto (cuerda retorcida)."""
        pts = [V(p) for p in pts]
        n = len(pts)
        up = V(up)
        rings = []
        prev_side = None
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
            side = t.cross(up)
            if side.length < 1e-4:
                side = prev_side if prev_side is not None else t.orthogonal()
            side.normalize()
            if prev_side is not None and side.dot(prev_side) < 0:
                side = -side
            prev_side = side
            nrm = side.cross(t).normalized()
            rr = r[i] if isinstance(r, (list, tuple)) else r
            ring = []
            for j in range(sides):
                a = 2 * math.pi * j / sides + math.radians(twist * i + phase)
                ring.append(p + side * math.cos(a) * rr + nrm * math.sin(a) * rr * sy)
            rings.append(ring)
        return self.loft(rings, color, True, cap0, cap1, colors)

    def ribbon(self, pts, widths, thick, color, up=(0, 0, 1), colors=None, twist=None):
        """Cinta plana con espesor (cola de hachimaki, hoja, fleco). widths: número o lista por punto.
        up: normal aproximada de la cara de la cinta; twist: grados por punto alrededor del eje."""
        pts = [V(p) for p in pts]
        n = len(pts)
        rings = []
        upv = V(up).normalized()
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
            u = upv
            if twist:
                u = Quaternion(t, math.radians(twist[i] if isinstance(twist, (list, tuple)) else twist * i)) @ upv
            side = t.cross(u)
            if side.length < 1e-4:
                side = t.orthogonal()
            side.normalize()
            nn = side.cross(t).normalized()
            w = (widths[i] if isinstance(widths, (list, tuple)) else widths) / 2
            rings.append([p - side * w - nn * thick / 2, p + side * w - nn * thick / 2, p + side * w + nn * thick / 2, p - side * w + nn * thick / 2])
        return self.loft(rings, color, True, True, True, colors)

    def box(self, M, size, color, taper=1.0, chamfer=0.0, colors=None):
        """Caja (con chaflán opcional en las aristas verticales) centrada en el origen de M; taper achica la tapa."""
        sx, sy, sz = (s / 2 for s in size)
        c = min(chamfer, sx * 0.9, sy * 0.9)
        if c > 0:
            prof = [(-sx + c, -sy), (sx - c, -sy), (sx, -sy + c), (sx, sy - c), (sx - c, sy), (-sx + c, sy), (-sx, sy - c), (-sx, -sy + c)]
        else:
            prof = [(-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy)]
        r0 = [M @ V(x, y, -sz) for x, y in prof]
        r1 = [M @ V(x * taper, y * taper, sz) for x, y in prof]
        return self.loft([r0, r1], color, True, True, True, colors)

    def cone(self, M, r0, r1, h, color, sides=8, rings=None, sy=1.0, cap0=True, cap1=True, colors=None, jitter=0.0, seed=2):
        """Cono/tronco a lo largo del Z local de M. rings: lista (z, radio) para perfiles con quiebre (sombreros)."""
        rnd = random.Random(seed)
        prof = rings or [(0.0, r0), (h, r1)]
        rr = []
        for z, r in prof:
            ring = []
            for j in range(sides):
                a = 2 * math.pi * j / sides
                jj = 1 + (rnd.uniform(-jitter, jitter) if jitter else 0)
                ring.append(M @ V(math.cos(a) * r * jj, math.sin(a) * r * sy * jj, z))
            rr.append(ring)
        top = prof[-1][1]
        part = self.loft(rr, color, True, cap0, cap1 and top > 1e-4, colors)
        return part

    def apex_cone(self, M, profile, apex_z, color, sides=12, colors=None, jitter=0.0, seed=3):
        """Sombrero: perfil (z, r) de afuera hacia adentro y una punta en apex_z (caras triangulares arriba)."""
        rnd = random.Random(seed)
        rr = []
        for z, r in profile:
            ring = []
            for j in range(sides):
                a = 2 * math.pi * (j + 0.5 * (len(rr) % 2) * 0) / sides
                jj = 1 + (rnd.uniform(-jitter, jitter) if jitter else 0)
                ring.append(M @ V(math.cos(a) * r * jj, math.sin(a) * r * jj, z))
            rr.append(ring)
        part = self.loft(rr, color, True, False, False, colors)
        apex = self.add([M @ V(0, 0, apex_z)])[0]
        last = part.idx[-sides:]
        for j in range(sides):
            k = (j + 1) % sides
            self.face((last[j], last[k], apex), colors(len(rr) - 1, j) if colors else color)
        part.idx.append(apex)
        return part

    def ico(self, M, radii, color, subdiv=1, jitter=0.0, seed=4):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        rnd = random.Random(seed)
        vmap = {}
        pts = []
        for v in bm.verts:
            j = 1 + (rnd.uniform(-jitter, jitter) if jitter else 0)
            vmap[v.index] = len(pts)
            pts.append(M @ V(v.co.x * radii[0] * j, v.co.y * radii[1] * j, v.co.z * radii[2] * j))
        idx = self.add(pts)
        for f in bm.faces:
            self.face([idx[vmap[v.index]] for v in f.verts], color)
        bm.free()
        return Part(self, idx)

    def zigzag_shide(self, top, down, lateral, step, n, width, thick, color):
        """Shide (papel ritual en zigzag) colgando de 'top'."""
        top = V(top); down = V(down).normalized(); lat = V(lateral).normalized()
        pts = [top]
        for i in range(1, n + 1):
            pts.append(top + down * step * i + lat * (step * 0.55 * (1 if i % 2 else -1)))
        return self.ribbon(pts, width, thick, color, up=lat.cross(down))


# ======================================================================= cadenas
class Chain:
    def __init__(self, kit, name, parent, pts):
        self.kit = kit
        self.name = name
        self.parent = parent
        self.pts = [V(p) for p in pts]
        self.bones = [f"Acc_{name}_{i}" for i in range(len(self.pts) - 1)]
        self.end = f"Acc_{name}_end"
        self.lens = [(self.pts[i + 1] - self.pts[i]).length for i in range(len(self.pts) - 1)]
        self.total = sum(self.lens)

    def project(self, p):
        """(índice de tramo, t en el tramo, distancia recorrida) del punto más cercano de la polilínea."""
        best = None
        acc = 0.0
        for i in range(len(self.pts) - 1):
            a, b = self.pts[i], self.pts[i + 1]
            ab = b - a
            t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
            d = (a + ab * t - p).length
            if best is None or d < best[0] - 1e-6:
                best = (d, i, t, acc + self.lens[i] * t)
            acc += self.lens[i]
        return best[1], best[2], best[3]

    def weights(self, p, base_weight=None, base_until=0.0):
        i, t, s = self.project(p)
        n = len(self.bones)
        w = collections.Counter()
        # mezcla lineal alrededor de cada junta (media longitud de tramo a cada lado)
        if t < 0.5 and i > 0:
            w[self.bones[i - 1]] += 0.5 - t; w[self.bones[i]] += 0.5 + t
        elif t >= 0.5 and i < n - 1:
            w[self.bones[i]] += 1.5 - t; w[self.bones[i + 1]] += t - 0.5
        else:
            w[self.bones[i]] += 1.0
        if i == 0 and t < 0.5:
            # la raíz se apoya en el hueso del que cuelga
            k = 0.5 - t
            for b in list(w):
                w[b] *= 1 - k
            w[self.parent] += k
        u = s / max(self.total, 1e-6)
        if base_weight and u < base_until:
            k = 1 - smoothstep(0.0, base_until, u)
            for b in list(w):
                w[b] *= 1 - k
            for b, x in base_weight.items():
                w[b] += x * k
        return dict(w)


# ======================================================================= kit
class Kit:
    def __init__(self, char, name):
        self.char = char
        self.name = name
        self.geo = Geo(self)
        self.chains = collections.OrderedDict()
        self.colliders = []         # (nombre, hueso padre, centro mundo, radio)

    def chain(self, name, parent, pts):
        c = Chain(self, name, parent, pts)
        self.chains[name] = c
        return c

    def collider(self, name, parent, center, radius):
        self.colliders.append((name, parent, V(center), radius))

    def tris(self):
        return sum(len(i) - 2 for i, _ in self.geo.f)

    # ------------------------------------------------------------ construir en la escena
    def build(self):
        """Agrega los huesos al armature del personaje y crea 'Acc_Kit' con skin. Devuelve el objeto."""
        arm = self.char.arm
        inv = arm.matrix_world.inverted()
        bpy.context.view_layer.objects.active = arm
        for o in bpy.context.selected_objects:
            o.select_set(False)
        arm.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones
        for c in self.chains.values():
            parent = eb[c.parent]
            prev = parent
            for i, bn in enumerate(c.bones):
                b = eb.new(bn)
                b.head = inv @ c.pts[i]
                b.tail = inv @ c.pts[i + 1]
                b.parent = prev
                b.use_connect = False
                b.use_deform = True
                prev = b
            d = (c.pts[-1] - c.pts[-2]).normalized()
            e = eb.new(c.end)
            e.head = inv @ c.pts[-1]
            e.tail = inv @ (c.pts[-1] + d * max(0.04, c.lens[-1] * 0.25))
            e.parent = prev
            e.use_deform = False
        for name, parent, center, radius in self.colliders:
            # la esfera es el hueso y un hijo '_r' a un radio de distancia: en Unity el radio se mide entre los
            # dos en el mundo (vale con cualquier escala del FBX y de NormalizeHeight); el número del nombre es
            # el radio en unidades del archivo, para sacar de ahí la escala de los grosores de SpringChain
            bn = f"AccCol_{name}_{int(round(radius * 100))}"
            b = eb.new(bn)
            b.head = inv @ center
            b.tail = inv @ (center + V(0, 0, max(radius, 0.05)))
            b.parent = eb[parent]
            b.use_deform = False
            r = eb.new(bn + "_r")
            r.head = inv @ (center + V(0, 0, radius))
            r.tail = inv @ (center + V(0, 0, radius + 0.05))
            r.parent = b
            r.use_deform = False
        bpy.ops.object.mode_set(mode='OBJECT')

        # malla
        geo = self.geo
        me = bpy.data.meshes.new("Acc_Kit")
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        dl = bm.verts.layers.deform.verify()
        names = []
        for w in geo.w:
            for bn in (w or {}):
                if bn not in names:
                    names.append(bn)
        gi = {n: i for i, n in enumerate(names)}
        bv = []
        for p, w in zip(geo.v, geo.w):
            if not w:
                raise RuntimeError(f"{self.name}: vértice sin pesos en {p}")
            v = bm.verts.new(inv @ p)          # en el espacio del armature (la malla cuelga de él sin transform)
            # máximo 4 huesos y normalizado: Unity trunca a 4 (maxBonesPerVertex)
            top = sorted(w.items(), key=lambda kv: -kv[1])[:4]
            tot = sum(x for _, x in top)
            for bn, x in top:
                if x / tot > 1e-3:
                    v[dl][gi[bn]] = x / tot
            bv.append(v)
        # slots: paleta, emisivo (si hay brillo) y los materiales con nombre propio ('mat:Nombre#hex'): esos los
        # reemplaza en Unity el material vivo del cuerpo que se llame igual (las colas de la bandana de Kaito)
        slots = []
        if any(not c.startswith(("glow_", "mat:")) for _, c in geo.f):
            slots.append("Nindo_Palette")
        if any(c.startswith("glow_") for _, c in geo.f):
            slots.append("Nindo_Emissive")
        for _, color in geo.f:
            if color.startswith("mat:") and color not in slots:
                slots.append(color)
        for idx, color in geo.f:
            try:
                f = bm.faces.new([bv[i] for i in idx])
            except ValueError:
                continue
            f.smooth = False
            if color.startswith("mat:"):
                f.material_index = slots.index(color)
                u, v = 0.5, 0.5
            else:
                f.material_index = slots.index("Nindo_Emissive" if color.startswith("glow_") else "Nindo_Palette")
                u, v = P.uv_of(color)
            for l in f.loops:
                l[uvl].uv = (u, v)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new("Acc_Kit", me)
        bpy.context.scene.collection.objects.link(obj)
        for n in names:
            obj.vertex_groups.new(name=n)
        for spec in slots:
            if spec.startswith("mat:"):
                nm, hexc = spec[4:].split("#")
                me.materials.append(flat_material(nm, "#" + hexc))
            else:
                me.materials.append(palette_material(spec))
        obj.parent = arm
        mod = obj.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        missing = [n for n in names if n not in arm.data.bones]
        if missing:
            raise RuntimeError(f"{self.name}: grupos sin hueso {missing}")
        return obj


# ======================================================================= materiales
_pal_img = None


def palette_image():
    global _pal_img
    try:
        alive = _pal_img is not None and _pal_img.name in bpy.data.images
    except ReferenceError:          # la escena se reinició (load_char) y la imagen ya no existe
        alive = False
    if not alive:
        path = os.path.join(REPO, "Tools", "Blender", "out", "NindoPalette.png")
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            P.write_png(path)
        _pal_img = bpy.data.images.load(path, check_existing=True)
    return _pal_img


def palette_material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = palette_image()
    tex.interpolation = 'Closest'
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    b.inputs["Metallic"].default_value = 0.0
    if name == "Nindo_Emissive":
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = 3.2
    return m


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def flat_material(name, hexc):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    h = hexc.lstrip("#")
    c = tuple(s2l(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*c, 1)
    b.inputs["Roughness"].default_value = 0.8
    b.inputs["Metallic"].default_value = 0.0
    m.diffuse_color = (*c, 1)
    return m


# ======================================================================= exportar
def export_kit(char, kit_obj, path):
    """Exporta solo el armature y Acc_Kit (sin el cuerpo, el arma ni animación), en reposo."""
    arm = char.arm
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    for o in bpy.data.objects:
        o.select_set(o == arm or o == kit_obj)
    bpy.context.view_layer.objects.active = arm
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, **EXPORT)
    return os.path.getsize(path)
