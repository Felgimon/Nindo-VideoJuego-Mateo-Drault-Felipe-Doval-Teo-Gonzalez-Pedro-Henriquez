"""Biblioteca compartida de los export_<personaje>.py (Blender 4.4, modo -b).

Los FBX de los personajes del equipo se re-exportan EN EL MISMO LUGAR (mismo .meta y GUID): Unity
los sigue tomando como el mismo asset y los .anim, controllers y NindoContent no se tocan. Para que
eso sea seguro cada script:
  1. importa el FBX y guarda la pose de cada hueso en cada frame de cada acción,
  2. edita SOLO mallas y materiales (nunca huesos: ni nombres, ni padres, ni pose de bind),
  3. exporta a un archivo temporal con los ajustes del equipo (los mismos que dieron 0.0° de diferencia),
  4. valida con fbxcheck.py (nodos, bind pose, tomas, fps, texturas) y re-importando el temporal y
     comparando las poses hueso por hueso; solo si todo da igual copia encima del original.

Cada paso es idempotente (re-correr el script sobre un FBX ya procesado no cambia nada), así que el
punto de partida puede ser el FBX del repo. Para volver al original del equipo:
    git show d8fa5da:"Nindo/Assets/<ruta>.fbx" > original.fbx

Coordenadas: todo lo que se construye acá está en el espacio MUNDO de Blender del FBX importado en
pose de reposo (Z arriba, unidades del archivo). Cada script anota hacia dónde mira su personaje.
"""
import bpy, bmesh, math, os, re, sys, shutil, tempfile, collections
from mathutils import Vector, kdtree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fbxcheck  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ASSETS = os.path.join(REPO, "Nindo", "Assets")


# ======================================================================= argumentos
def args():
    """--write (pisa el FBX del repo si valida), --src <fbx> (otro origen), --out <dir> (temporales/renders)."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    # los temporales van fuera del repo: un FBX a medio validar no se tiene que poder commitear
    o = {"write": "--write" in argv, "src": None, "out": os.environ.get("NINDO_CHAR_OUT", os.path.join(tempfile.gettempdir(), "nindo_characters"))}
    for i, a in enumerate(argv):
        if a in ("--src", "--out") and i + 1 < len(argv):
            o[a[2:]] = argv[i + 1]
    os.makedirs(o["out"], exist_ok=True)
    return o


# ======================================================================= color
def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(hexc):
    h = hexc.lstrip("#")
    return tuple(s2l(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def base(name):
    """Nombre sin el sufijo .001 que agrega Blender al importar nombres repetidos."""
    return re.sub(r"\.\d{3}$", "", name)


# ======================================================================= escena
def load(path, anim_offset=1.0):
    """Importa el FBX en una escena vacía. Devuelve el Armature."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, anim_offset=anim_offset)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    return arm


def rest(arm, on=True):
    arm.data.pose_position = 'REST' if on else 'POSE'
    bpy.context.view_layer.update()


def meshes():
    return [o for o in bpy.data.objects if o.type == 'MESH']


# ======================================================================= materiales
def material(name, hexc=None, rough=0.85, emission=None, strength=0.0):
    """Material plano (sin texturas, metálico 0). Si ya existe lo actualiza: los scripts son idempotentes.
    metálico 0 siempre: con metallic = 1 las hojas importaban casi negras en URP (MODEL-02)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None:
        nt.nodes.clear()
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(b.outputs[0], out.inputs[0])
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE' or n.type == 'NORMAL_MAP']:
        nt.nodes.remove(n)
    for inp in ("Base Color", "Normal", "Metallic", "Roughness"):
        for l in list(b.inputs[inp].links):
            nt.links.remove(l)
    if hexc is not None:
        c = lin(hexc)
        b.inputs["Base Color"].default_value = (*c, 1)
        m.diffuse_color = (*c, 1)
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Roughness"].default_value = rough
    m.metallic = 0.0; m.roughness = rough
    if emission is not None:
        b.inputs["Emission Color"].default_value = (*lin(emission), 1)
        b.inputs["Emission Strength"].default_value = strength
    else:
        b.inputs["Emission Strength"].default_value = 0.0
    return m


def recolor(mapping):
    """{nombre base de material: '#hex' | dict(hexc=, rough=, emission=, strength=)} sobre todos los slots."""
    done = set()
    for o in meshes():
        for s in o.material_slots:
            if s.material and base(s.material.name) in mapping and s.material.name not in done:
                v = mapping[base(s.material.name)]
                kw = v if isinstance(v, dict) else {"hexc": v}
                material(s.material.name, **kw)
                done.add(s.material.name)
    return done


def strip_images():
    """Saca todas las imágenes (las 4K empaquetadas inflaban el sumo a 100 MB y Gorō a 68 MB)."""
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in [n for n in m.node_tree.nodes if n.type in ('TEX_IMAGE', 'NORMAL_MAP')]:
                m.node_tree.nodes.remove(n)
    for im in list(bpy.data.images):
        bpy.data.images.remove(im)


def slot(obj, mat):
    """Índice del slot de 'mat' en obj (lo agrega si falta)."""
    for i, s in enumerate(obj.material_slots):
        if s.material == mat:
            return i
    obj.data.materials.append(mat)
    return len(obj.material_slots) - 1


# ======================================================================= análisis de caras
class Face:
    __slots__ = ("index", "c", "n", "dom", "mat", "area")


def faces(obj):
    """Datos por cara en mundo (reposo): centro, normal, hueso dominante y material base."""
    me = obj.data
    gname = {g.index: g.name for g in obj.vertex_groups}
    mw = obj.matrix_world; nm = mw.to_3x3().inverted().transposed()
    out = []
    for p in me.polygons:
        w = collections.Counter()
        for vi in p.vertices:
            for g in me.vertices[vi].groups:
                w[g.group] += g.weight
        f = Face()
        f.index = p.index
        f.c = mw @ p.center
        f.n = (nm @ p.normal).normalized()
        f.dom = gname.get(w.most_common(1)[0][0], "") if w else ""
        f.mat = base(obj.material_slots[p.material_index].material.name) if p.material_index < len(obj.material_slots) and obj.material_slots[p.material_index].material else ""
        f.area = p.area
        out.append(f)
    return out


def reassign(obj, pred, mat):
    """Mueve al material 'mat' las caras donde pred(Face) es verdadero. Devuelve cuántas."""
    idx = slot(obj, mat)
    me = obj.data
    n = 0
    for f in faces(obj):
        if pred(f) and me.polygons[f.index].material_index != idx:
            me.polygons[f.index].material_index = idx; n += 1
    return n


def count(obj, matname):
    return sum(1 for f in faces(obj) if f.mat == matname)


# ======================================================================= geometría nueva
class Geo:
    """Acumulador de geometría en MUNDO (reposo) con un material por cara. Se pega a una malla con attach()."""

    def __init__(self):
        self.v = []; self.f = []  # f: (indices, material)

    def add_verts(self, pts):
        i0 = len(self.v); self.v.extend(Vector(p) for p in pts); return list(range(i0, i0 + len(pts)))

    def face(self, idx, mat):
        self.f.append((list(idx), mat))

    # ---------------------------------------------------------------- primitivas
    def loft(self, rings, mat, cap0=True, cap1=True, mats=None):
        """Une anillos (listas de puntos con la misma cantidad) en un tubo; mats(i_ring, j_seg) -> material."""
        ids = [self.add_verts(r) for r in rings]
        n = len(rings[0])
        for a in range(len(ids) - 1):
            for j in range(n):
                k = (j + 1) % n
                self.face((ids[a][j], ids[a][k], ids[a + 1][k], ids[a + 1][j]), mats(a, j) if mats else mat)
        if cap0: self.face(list(reversed(ids[0])), mat)
        if cap1: self.face(ids[-1], mat)
        return ids

    def prism(self, c0, c1, r0, r1, mat, seg=6, up=(0, 0, 1), sy=1.0, cap0=True, cap1=True):
        """Prisma/cono truncado de c0 a c1 (radios r0 -> r1); sy aplasta la sección en su eje 'lado'."""
        c0, c1 = Vector(c0), Vector(c1)
        ax = (c1 - c0).normalized()
        side = ax.cross(Vector(up))
        if side.length < 1e-5: side = ax.orthogonal()
        side.normalize(); nrm = side.cross(ax).normalized()

        def ring(c, r):
            return [c + (side * math.cos(2 * math.pi * j / seg) * r + nrm * math.sin(2 * math.pi * j / seg) * r * sy) for j in range(seg)]
        return self.loft([ring(c0, r0), ring(c1, r1)], mat, cap0, cap1)

    def ribbon(self, pts, widths, mat, thick=0.02, up=(0, 0, 1), mats=None):
        """Cinta plana con espesor a lo largo de una polilínea ('up' = normal aproximada de la cinta)."""
        pts = [Vector(p) for p in pts]; up = Vector(up).normalized(); n = len(pts)
        rings = []
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
            side = t.cross(up)
            if side.length < 1e-5: side = t.orthogonal()
            side.normalize(); nn = side.cross(t).normalized()
            w = widths[i] / 2 if isinstance(widths, (list, tuple)) else widths / 2
            rings.append([p - side * w - nn * thick / 2, p + side * w - nn * thick / 2, p + side * w + nn * thick / 2, p - side * w + nn * thick / 2])
        return self.loft(rings, mat, True, True, mats)

def arc_band(geo, c, rx, ry, h, t, mat, a0, a1, seg=10, rx2=None, ry2=None, drop=0.0):
    """Banda elíptica abierta (de a0 a a1 grados, 0 = +X, 90 = +Y), con espesor y caras en los cortes.
    rx2/ry2 = radios de arriba (abanico), drop = cuánto baja el borde en los extremos del arco."""
    rx2 = rx if rx2 is None else rx2; ry2 = ry if ry2 is None else ry2
    c = Vector(c)
    rings = []
    for j in range(seg + 1):
        a = math.radians(a0 + (a1 - a0) * j / seg)
        u = abs(2 * j / seg - 1)                      # 1 en las puntas, 0 en el medio
        dz = -drop * u * u
        ca, sa = math.cos(a), math.sin(a)
        rings.append([c + Vector((rx * ca, ry * sa, -h / 2 + dz)), c + Vector((rx2 * ca, ry2 * sa, h / 2 + dz)),
                      c + Vector(((rx2 - t) * ca, (ry2 - t) * sa, h / 2 + dz)), c + Vector(((rx - t) * ca, (ry - t) * sa, -h / 2 + dz))])
    geo.loft(rings, mat, cap0=True, cap1=True)


def attach(obj, geo, weights, flat=True, near_mat=None):
    """Pega 'geo' a la malla 'obj' (transformando de mundo a local) con pesos:
       ('bone', nombre)         -> 100 % a ese hueso (piezas rígidas: pelo, cascos, ojos, caras)
       ('nearest_each', None)   -> cada vértice copia los del vértice original más cercano (telas que siguen el cuerpo)
       near_mat: buscar el vértice más cercano solo entre los del material con ese nombre base.
       Devuelve la cantidad de triángulos agregados."""
    me = obj.data
    inv = obj.matrix_world.inverted()
    src_w = None
    if weights[0] == "nearest_each":
        allowed = None
        if near_mat:
            mi = {i for i, s in enumerate(obj.material_slots) if s.material and base(s.material.name) == near_mat}
            allowed = {vi for p in me.polygons if p.material_index in mi for vi in p.vertices}
        kd = kdtree.KDTree(len(me.vertices))
        for v in me.vertices:
            if allowed is None or v.index in allowed:
                kd.insert(obj.matrix_world @ v.co, v.index)
        kd.balance()
        src_w = (kd, [{g.group: g.weight for g in v.groups} for v in me.vertices])
    mats = {}
    for _, mname in geo.f:
        if mname not in mats:
            mats[mname] = slot(obj, bpy.data.materials[mname])
    bm = bmesh.new(); bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    uvl = bm.loops.layers.uv.active
    vgi = {g.name: g.index for g in obj.vertex_groups}
    if weights[0] == "bone":
        if weights[1] not in vgi:
            vgi[weights[1]] = obj.vertex_groups.new(name=weights[1]).index
        rigid = {vgi[weights[1]]: 1.0}
    else:
        rigid = None
    bv = []
    new_faces = []
    for p in geo.v:
        v = bm.verts.new(inv @ p)
        wd = rigid if rigid is not None else src_w[1][src_w[0].find(p)[1]]
        for g, w in wd.items():
            v[dl][g] = w
        bv.append(v)
    bm.verts.index_update()
    n = 0
    for idx, mname in geo.f:
        try:
            f = bm.faces.new([bv[i] for i in idx])
        except ValueError:
            continue  # cara repetida
        f.material_index = mats[mname]
        f.smooth = not flat
        if uvl is not None:
            for l in f.loops: l[uvl].uv = (0.0, 0.0)
        new_faces.append(f)
        n += len(idx) - 2
    # piezas cerradas: normales hacia afuera sin importar el orden en que se armaron
    bmesh.ops.recalc_face_normals(bm, faces=new_faces)
    bm.to_mesh(me); bm.free()
    me.update()
    return n


def bisect_loops(obj, heights, matname):
    """Corta anillos horizontales (z mundo) en las caras del material 'matname': la división de aristas
    interpola los pesos, así una faja nueva se deforma igual que la tela de alrededor (MODEL-08)."""
    me = obj.data
    idx = next(i for i, s in enumerate(obj.material_slots) if s.material and base(s.material.name) == matname)
    inv = obj.matrix_world.inverted()
    # normal del plano en local: M^T * n (M = 3x3 local->mundo)
    nloc = (obj.matrix_world.to_3x3().transposed() @ Vector((0, 0, 1))).normalized()
    bm = bmesh.new(); bm.from_mesh(me)
    for z in heights:
        fs = [f for f in bm.faces if f.material_index == idx]
        geom = fs + list({e for f in fs for e in f.edges}) + list({v for f in fs for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=inv @ Vector((0, 0, z)), plane_no=nloc)
    bm.to_mesh(me); bm.free(); me.update()


# ======================================================================= pesos y normales
def limit_weights(obj, limit=4):
    """Máximo 4 huesos por vértice y normalizado: Unity trunca a 4 (maxBonesPerVertex) y sin esto
    deformaba distinto que Blender (MODEL-11). Devuelve el máximo que quedó."""
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects: o.select_set(False)
    obj.select_set(True)
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=0.001)
        bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=limit)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
    worst = max((len([g for g in v.groups if g.weight > 1e-4]) for v in obj.data.vertices), default=0)
    return worst


def flat_normals(obj):
    """Caras planas sin normales custom: el look facetado del juego, igual para la geometría nueva."""
    me = obj.data
    if me.has_custom_normals:
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    me.shade_flat()


def replace_mesh(obj, geo):
    """Reemplaza la malla de un objeto rígido (arma) manteniendo el objeto: nombre, padre, hueso,
    transform y animación quedan igual, así KatanaRig/Enemy siguen encontrándolo por nombre."""
    inv = obj.matrix_world.inverted()
    me = bpy.data.meshes.new(obj.data.name + "_n")
    bm = bmesh.new()
    bv = [bm.verts.new(inv @ p) for p in geo.v]
    names = []
    for idx, mname in geo.f:
        if mname not in names: names.append(mname)
        try:
            f = bm.faces.new([bv[i] for i in idx])
        except ValueError:
            continue
        f.material_index = names.index(mname)
        f.smooth = False
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops: l[uvl].uv = (0.0, 0.0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    for n in names: me.materials.append(bpy.data.materials[n])
    old = obj.data
    name = old.name
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    me.name = name
    return sum(len(p.vertices) - 2 for p in me.polygons)


# ======================================================================= animación
def take_actions(arm):
    """Renombra las acciones para que la exportación reproduzca las tomas originales ('Armature|Idle'):
    el importador las llama '<objeto>|<toma>' y el exportador escribe '<objeto>|<acción>'."""
    pre = arm.name + "|"
    for a in bpy.data.actions:
        if a.name.startswith(pre + pre):
            a.name = a.name[2 * len(pre):]


def weapon_takes(src, arm):
    """Tomas del FBX original que no son del esqueleto ('Isan|Atack1', 'Katana|Block'...): animaciones de
    1 frame de objetos pegados a huesos que el importador de Blender no lee y que nada usa (los
    controllers referencian solo tomas 'Armature|...'). Se pierden al re-exportar y se avisa."""
    return {s for s in fbxcheck.summary(src)["stacks"] if not s.startswith(arm.name + "|")}


def sample_poses(arm, step=1):
    """{acción: [(frame, {hueso: matriz 4x4 en espacio del armature})]} para comparar antes/después."""
    out = {}
    if arm.animation_data is None: arm.animation_data_create()
    rest(arm, False)
    keep = arm.animation_data.action
    scn = bpy.context.scene
    for a in bpy.data.actions:
        if not any(fc.data_path.startswith("pose.bones") for fc in a.fcurves):
            continue
        arm.animation_data.action = a
        f0, f1 = (int(round(x)) for x in a.frame_range)
        rows = []
        for f in range(f0, f1 + 1, step):
            scn.frame_set(f)
            bones = {pb.name: pb.matrix.copy() for pb in arm.pose.bones}
            bones["<objeto Armature>"] = arm.matrix_world.copy()   # las tomas también mueven el objeto
            rows.append((f, bones))
        out[a.name] = rows
    arm.animation_data.action = keep
    return out


def compare_poses(A, B):
    """Peor diferencia de rotación (°) y traslación entre dos muestreos del mismo FBX (antes/después)."""
    worst_r = worst_t = 0.0; where = ""; missing = []
    for an, rows in A.items():
        if an not in B: missing.append(an); continue
        bmap = dict(B[an])
        for f, bones in rows:
            if f not in bmap: missing.append(f"{an}@{f}"); continue
            for bname, ma in bones.items():
                mb = bmap[f].get(bname)
                if mb is None: missing.append(bname); continue
                r = math.degrees(ma.to_quaternion().rotation_difference(mb.to_quaternion()).angle)
                r = min(r, 360 - r)
                t = (ma.to_translation() - mb.to_translation()).length
                if r > worst_r: worst_r = r; where = f"{an}@{f}:{bname}"
                worst_t = max(worst_t, t)
    return worst_r, worst_t, where, missing[:10]


# ======================================================================= exportación
# simplify 0: cada frame horneado tal cual (con 1.0, el default de Blender, el peor hueso se corría 0.25°);
# Unity igual reduce las claves al importar (animationCompression)
TEAM = dict(object_types={'ARMATURE', 'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
            axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X',
            mesh_smooth_type='OFF', use_armature_deform_only=False, path_mode='STRIP', embed_textures=False,
            bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
            bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0)


def export(path, **over):
    for o in bpy.data.objects: o.select_set(o.type in ('ARMATURE', 'MESH'))
    kw = dict(TEAM); kw.update(over)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, **kw)


def report_mesh(obj):
    me = obj.data
    per = collections.Counter(base(obj.material_slots[p.material_index].material.name) for p in me.polygons)
    infl = max((len([g for g in v.groups if g.weight > 1e-4]) for v in me.vertices), default=0)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    print(f"  {obj.name}: {tris} tris, {len(me.vertices)} verts, max {infl} huesos/vértice, materiales {dict(per)}")
    return tris


def finish(arm, src, rel, opts, export_kw=None, anim_offset=1.0, poses=None, bind_tol=0.01):
    """Común a todos: pesos, normales, imágenes fuera, tomas; exporta, valida contra 'src' y (con --write)
    escribe en el lugar del repo (Assets/<rel>), aunque el origen haya sido otro archivo (--src)."""
    dst_name = os.path.basename(rel)
    rest(arm, True)
    for o in meshes():
        if o.vertex_groups:
            limit_weights(o)
        flat_normals(o)
    strip_images()
    all_actions = (export_kw or {}).get("bake_anim_use_all_actions", True)
    dropped = weapon_takes(src, arm) if all_actions else set()
    if all_actions:
        take_actions(arm)
    rest(arm, False)
    print("mallas:")
    for o in meshes(): report_mesh(o)
    tmp = os.path.join(opts["out"], dst_name)
    export(tmp, **(export_kw or {}))
    print("exportado", tmp, f"{os.path.getsize(tmp) / 1e6:.2f} MB")
    ok = fbxcheck.compare(src, tmp, rot_tol=bind_tol, dropped_takes=dropped)
    if poses is not None:
        arm2 = load(tmp, anim_offset)
        after = sample_poses(arm2)
        r, t, where, missing = compare_poses(poses, after)
        print(f"poses (todas las acciones, cada frame): peor {r:.4f}° / {t:.5f} en {where}; faltan {missing}")
        if r > 0.05 or t > 0.002 or missing:
            ok = False
    if ok and opts["write"]:
        dst = os.path.join(ASSETS, rel)
        shutil.copyfile(tmp, dst)
        print("ESCRITO", dst)
    elif not ok:
        print("NO SE ESCRIBIÓ: la validación falló")
    return ok, tmp


# ======================================================================= armas
def katana(geo, origin, axis, edge, flat, handle_len, blade_len, width, thick, sori, m,
           handle_r=None, guard_r=None, wrap_bands=7, blade_rings=9):
    """Katana facetada de ~250-350 triángulos sobre un marco dado (mundo):
       origin = tsuba, axis = hacia la punta, edge = hacia el filo, flat = normal de la cara de la hoja.
       m: dict de materiales {'steel', 'glint', 'wrap', 'skin', 'metal'} (skin = rombos del mango).
       El filo (las dos caras que bajan al borde) es el slot 'glint': el combate lo enciende en el aviso.
       La hoja se curva hacia el lomo (sori) como una katana de verdad: el filo queda en el lado convexo."""
    O, A, E, F = Vector(origin), Vector(axis).normalized(), Vector(edge).normalized(), Vector(flat).normalized()
    hr = handle_r or width * 0.62
    gr = guard_r or width * 1.25

    def P(t, s, u):
        return O + A * t + E * s + F * u

    # mango: hexágono algo ovalado, bandas alternadas (ito / rombos de piel de raya)
    rings = []
    for k in range(wrap_bands + 1):
        t = -handle_len + handle_len * k / wrap_bands
        bulge = 1.0 + 0.08 * math.sin(math.pi * k / wrap_bands)   # el tsuka se ensancha apenas al centro
        rings.append([P(t, math.cos(2 * math.pi * j / 6) * hr * bulge, math.sin(2 * math.pi * j / 6) * hr * 0.8 * bulge) for j in range(6)])
    geo.loft(rings, m["wrap"], cap0=False, cap1=False, mats=lambda a, j: m["wrap"] if a % 2 == 0 else m["skin"])
    # kashira (pomo) y fuchi (virola junto a la tsuba)
    geo.prism(P(-handle_len - 0.035, 0, 0), P(-handle_len + 0.005, 0, 0), hr * 0.9, hr * 1.08, m["metal"], seg=6, up=F)
    geo.prism(P(-0.04, 0, 0), P(-0.005, 0, 0), hr * 1.08, hr * 1.1, m["metal"], seg=6, up=F)
    # tsuba: disco octogonal
    geo.prism(P(-0.005, 0, 0), P(0.022, 0, 0), gr, gr, m["metal"], seg=8, up=F, sy=0.82)
    # habaki: collar de la base de la hoja
    geo.prism(P(0.022, width * 0.05, 0), P(0.075, width * 0.05, 0), width * 0.62, width * 0.58, m["metal"], seg=6, up=F, sy=0.55)
    # hoja: sección de 5 vértices (filo, dos aristas del shinogi, dos del lomo)
    blade = []
    for k in range(blade_rings):
        s = k / (blade_rings - 1)
        t = 0.06 + (blade_len - 0.06) * (s * 0.94)
        c = -sori * (s ** 2)                             # el centro se va hacia el lomo
        w = width * (1.0 - 0.28 * s)
        th = thick * (1.0 - 0.45 * s)
        blade.append([P(t, c + w * 0.5, 0), P(t, c + w * 0.08, th * 0.5), P(t, c - w * 0.5, th * 0.45),
                      P(t, c - w * 0.5, -th * 0.45), P(t, c + w * 0.08, -th * 0.5)])
    face_mat = lambda a, j: m["glint"] if j in (0, 4) else m["steel"]
    ids = geo.loft(blade, m["steel"], cap0=True, cap1=False, mats=face_mat)
    # kissaki: la punta sube hacia el lomo
    tip = geo.add_verts([P(blade_len, -sori - width * 0.30, 0)])[0]
    last = ids[-1]
    for j in range(5):
        k = (j + 1) % 5
        geo.face((last[j], last[k], tip), face_mat(0, j))
    return geo
