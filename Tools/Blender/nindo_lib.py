"""Nindo low-poly modelling toolkit for Blender (bpy + bmesh).

Conventions (READ BEFORE MODELLING)
-----------------------------------
* Units are metres.  Blender is Z-up.  A prop's origin is at the centre of its
  footprint on the ground (z = 0).
* The FRONT of every prop faces Blender -Y (Blender "Front" view).  After the
  FBX export used by this toolkit, -Y becomes Unity +Z (Unity forward).
* Every face gets a palette colour (see nindo_palette.PALETTE) and a material
  slot:  SLOT_PALETTE (lit, opaque), SLOT_EMISSIVE (glowing: windows, lantern
  paper, fire, portals), SLOT_FOLIAGE (leaves that sway in the wind; the
  vertex colour R channel is the sway weight 0..1), SLOT_WATER.
* Flat shading only.  Keep things chunky and readable from a high camera
  (pitch ~50 deg, ~20 m away): exaggerate silhouettes, avoid thin details
  under ~4 cm, no faces nobody will ever see (bottoms resting on the ground).
"""
import bpy, bmesh, math, random, os, json
from mathutils import Vector, Matrix, Euler

import nindo_palette as P

SLOT_PALETTE, SLOT_EMISSIVE, SLOT_FOLIAGE, SLOT_WATER = 0, 1, 2, 3
SLOT_NAMES = ["Nindo_Palette", "Nindo_Emissive", "Nindo_Foliage", "Nindo_Water"]

HERE = os.path.dirname(os.path.abspath(__file__))


def _mat(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    S = Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    R = Euler(tuple(math.radians(a) for a in rot), 'XYZ').to_matrix().to_4x4()
    T = Matrix.Translation(Vector(loc))
    return T @ R @ S


class Part:
    """Handle to geometry just created, so it can be tweaked afterwards."""

    def __init__(self, mb, verts):
        self.mb = mb
        self.verts = list(verts)

    @property
    def faces(self):
        fs = set()
        for v in self.verts:
            fs.update(v.link_faces)
        return list(fs)

    def jitter(self, amount=0.05, seed=None, axes=(1, 1, 1)):
        rng = random.Random(seed) if seed is not None else self.mb.rng
        for v in self.verts:
            v.co.x += rng.uniform(-amount, amount) * axes[0]
            v.co.y += rng.uniform(-amount, amount) * axes[1]
            v.co.z += rng.uniform(-amount, amount) * axes[2]
        return self

    def transform(self, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        M = _mat(loc, rot, scale)
        for v in self.verts:
            v.co = M @ v.co
        return self

    def color(self, name, slot=None, wind=None):
        self.mb._tag(self.faces, name, slot, wind)
        return self

    def color_faces(self, fn):
        """fn(face) -> palette colour name (or None to keep)."""
        for f in self.faces:
            c = fn(f)
            if c:
                self.mb._tag([f], c, None, None)
        return self

    def wind_by_height(self, z0, z1, maximum=1.0):
        """Sets per-vertex sway weight by height (foliage)."""
        cl = self.mb.col
        for f in self.faces:
            for l in f.loops:
                t = 0.0 if z1 <= z0 else max(0.0, min(1.0, (l.vert.co.z - z0) / (z1 - z0)))
                c = l[cl]
                l[cl] = (t * maximum, c[1], c[2], 1.0)
        return self


class MeshBuilder:
    def __init__(self, name, seed=1):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.col = self.bm.loops.layers.color.new("Col")
        self.rng = random.Random(seed)
        self.meta = {"collider": None, "tags": []}

    # ------------------------------------------------------------ tagging
    def _tag(self, faces, color, slot=None, wind=None):
        u, v = P.uv_of(color)
        if slot is None:
            slot = SLOT_EMISSIVE if color.startswith("glow_") else None
        for f in faces:
            if slot is not None:
                f.material_index = slot
            f.smooth = False
            for l in f.loops:
                l[self.uv].uv = (u, v)
                if wind is not None:
                    c = l[self.col]
                    l[self.col] = (wind, c[1], c[2], 1.0)

    def _new(self, verts, color, slot, wind):
        p = Part(self, verts)
        fs = p.faces
        for f in fs:
            f.material_index = SLOT_PALETTE if slot is None else slot
            for l in f.loops:
                l[self.col] = (0.0, 0.0, 0.0, 1.0)
        self._tag(fs, color, slot, wind)
        return p

    # ------------------------------------------------------------ primitives
    def box(self, loc, size, color, rot=(0, 0, 0), slot=None, wind=None):
        """Axis-aligned box centred at loc with full size (sx, sy, sz)."""
        r = bmesh.ops.create_cube(self.bm, size=1.0, matrix=_mat(loc, rot, size))
        return self._new(r["verts"], color, slot, wind)

    def box_base(self, loc, size, color, **kw):
        """Box whose BOTTOM is at loc.z (handy for stacking)."""
        x, y, z = loc
        return self.box((x, y, z + size[2] / 2.0), size, color, **kw)

    def prism(self, loc, radius, height, sides, color, radius_top=None, rot=(0, 0, 0),
              slot=None, wind=None, cap=True, base=True):
        """Cylinder/frustum with `sides` segments.  loc = centre of the BOTTOM cap
        (before rotation; rotation pivots around loc)."""
        rt = radius if radius_top is None else radius_top
        M = _mat(loc, rot) @ Matrix.Translation((0, 0, height / 2.0))
        r = bmesh.ops.create_cone(self.bm, cap_ends=cap, cap_tris=False, segments=sides,
                                  radius1=radius, radius2=max(rt, 0.0), depth=height, matrix=M)
        p = self._new(r["verts"], color, slot, wind)
        if not base and cap:
            # remove bottom cap face (never seen)
            bottom = [f for f in p.faces if f.normal.z < -0.99 and all(abs(v.co.z - loc[2]) < 1e-4 for v in f.verts)]
            if bottom and rot == (0, 0, 0):
                bmesh.ops.delete(self.bm, geom=bottom, context='FACES_ONLY')
        return p

    def cone(self, loc, radius, height, sides, color, **kw):
        return self.prism(loc, radius, height, sides, color, radius_top=0.0, **kw)

    def ico(self, loc, radius, color, subdiv=1, scale=(1, 1, 1), jitter=0.0, rot=(0, 0, 0), slot=None, wind=None):
        r = bmesh.ops.create_icosphere(self.bm, subdivisions=subdiv, radius=1.0,
                                       matrix=_mat(loc, rot, (radius * scale[0], radius * scale[1], radius * scale[2])))
        p = self._new(r["verts"], color, slot, wind)
        if jitter:
            p.jitter(jitter * radius)
        return p

    def sphere(self, loc, radius, color, segments=8, rings=5, scale=(1, 1, 1), rot=(0, 0, 0), slot=None, wind=None):
        r = bmesh.ops.create_uvsphere(self.bm, u_segments=segments, v_segments=rings, radius=1.0,
                                      matrix=_mat(loc, rot, (radius * scale[0], radius * scale[1], radius * scale[2])))
        return self._new(r["verts"], color, slot, wind)

    def face(self, pts, color, slot=None, wind=None, double=False):
        vs = [self.bm.verts.new(Vector(p)) for p in pts]
        f = self.bm.faces.new(vs)
        allv = list(vs)
        if double:
            vs2 = [self.bm.verts.new(Vector(p)) for p in reversed(pts)]
            self.bm.faces.new(vs2)
            allv += vs2
        return self._new(allv, color, slot, wind)

    def extrude_polygon(self, pts2d, z0, z1, color, top_color=None, slot=None, wind=None, base=False):
        """Vertical extrusion of a 2D polygon (counter-clockwise, seen from above)."""
        bot = [self.bm.verts.new((x, y, z0)) for x, y in pts2d]
        top = [self.bm.verts.new((x, y, z1)) for x, y in pts2d]
        n = len(pts2d)
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((bot[i], bot[j], top[j], top[i])))
        ftop = self.bm.faces.new(top)
        if base:
            self.bm.faces.new(list(reversed(bot)))
        p = self._new(bot + top, color, slot, wind)
        if top_color:
            self._tag([ftop], top_color, slot, wind)
        return p

    def loft(self, rings, color, cap_start=False, cap_end=False, closed=True, slot=None, wind=None):
        """Skins a list of rings (each a list of 3D points with the same count)."""
        vrings = [[self.bm.verts.new(Vector(p)) for p in ring] for ring in rings]
        n = len(rings[0])
        for a, b in zip(vrings[:-1], vrings[1:]):
            rng = range(n) if closed else range(n - 1)
            for i in rng:
                j = (i + 1) % n
                self.bm.faces.new((a[i], a[j], b[j], b[i]))
        if cap_start:
            self.bm.faces.new(list(reversed(vrings[0])))
        if cap_end:
            self.bm.faces.new(vrings[-1])
        return self._new([v for r in vrings for v in r], color, slot, wind)

    def strip(self, left, right, color, slot=None, wind=None, double=False):
        """Quad strip between two polylines (e.g. a roof surface or a path)."""
        lv = [self.bm.verts.new(Vector(p)) for p in left]
        rv = [self.bm.verts.new(Vector(p)) for p in right]
        for i in range(len(left) - 1):
            self.bm.faces.new((lv[i], rv[i], rv[i + 1], lv[i + 1]))
            if double:
                pass
        p = self._new(lv + rv, color, slot, wind)
        if double:
            l2 = [self.bm.verts.new(Vector(p_)) for p_ in left]
            r2 = [self.bm.verts.new(Vector(p_)) for p_ in right]
            for i in range(len(left) - 1):
                self.bm.faces.new((l2[i + 1], r2[i + 1], r2[i], l2[i]))
            self._new(l2 + r2, color, slot, wind)
        return p

    def plank_line(self, a, b, width, thick, color, **kw):
        """A beam between points a and b (square cross-section width x thick)."""
        a, b = Vector(a), Vector(b)
        d = b - a
        L = d.length
        if L < 1e-6:
            return None
        q = d.to_track_quat('Z', 'Y')
        M = Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((width, thick, L, 1))
        r = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        return self._new(r["verts"], color, kw.get("slot"), kw.get("wind"))

    def mirror_x(self, part):
        """Duplicates a part mirrored across X=0 (keeps colours)."""
        geom = bmesh.ops.duplicate(self.bm, geom=part.verts + part.faces + list({e for f in part.faces for e in f.edges}))
        nv = [g for g in geom["geom"] if isinstance(g, bmesh.types.BMVert)]
        for v in nv:
            v.co.x = -v.co.x
        nf = [g for g in geom["geom"] if isinstance(g, bmesh.types.BMFace)]
        bmesh.ops.reverse_faces(self.bm, faces=nf)
        return Part(self, nv)

    def duplicate(self, part, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        geom = bmesh.ops.duplicate(self.bm, geom=part.verts + part.faces + list({e for f in part.faces for e in f.edges}))
        nv = [g for g in geom["geom"] if isinstance(g, bmesh.types.BMVert)]
        p = Part(self, nv)
        p.transform(loc, rot, scale)
        return p

    # ------------------------------------------------------------ metadata
    def collider_box(self, size, center=None):
        """Box collider in Blender prop space (size x,y,z; center default = half height)."""
        c = center if center is not None else (0, 0, size[2] / 2.0)
        self.meta["collider"] = {"type": "box", "size": list(size), "center": list(c)}

    def collider_capsule(self, radius, height, center_z=None):
        self.meta["collider"] = {"type": "capsule", "radius": radius, "height": height,
                                 "center": [0, 0, height / 2.0 if center_z is None else center_z]}

    def collider_mesh(self):
        self.meta["collider"] = {"type": "mesh"}

    def collider_none(self):
        self.meta["collider"] = {"type": "none"}

    def tag(self, *tags):
        """Tags understood by Unity's WorldBuilder:
        'occluder'  -> hidden (shadows only) when it blocks the view of Kaito (trees, roofs)
        'light_warm' / 'light_cool' / 'light_fire' -> spawns a pooled point light at 'light_offset'
        'fireflies' -> spawns fireflies around it, 'smoke' -> incense/chimney smoke
        'nonstatic' -> not static-batched (animated/interactive props)"""
        self.meta["tags"].extend(tags)

    def set(self, key, value):
        self.meta[key] = value

    # ------------------------------------------------------------ finish
    def finish(self, triangulate=True, merge=0.0005):
        bm = self.bm
        if merge:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if triangulate:
            bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for n in SLOT_NAMES:
            me.materials.append(get_material(n))
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj["nindo_meta"] = json.dumps(self.meta)
        return obj


# ---------------------------------------------------------------- materials
_palette_img = None


def palette_image():
    global _palette_img
    if _palette_img is None:
        path = os.path.join(HERE, "out", "NindoPalette.png")
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            P.write_png(path)
        _palette_img = bpy.data.images.load(path, check_existing=True)
    return _palette_img


def get_material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = palette_image()
    tex.interpolation = 'Closest'
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    if name == "Nindo_Emissive":
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 6.0
    if name == "Nindo_Water":
        bsdf.inputs["Roughness"].default_value = 0.15
    return m


# ---------------------------------------------------------------- helpers
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    global _palette_img
    _palette_img = None


def ring(cx, cy, z, r, n, phase=0.0, rx=None, ry=None):
    rx = r if rx is None else rx
    ry = r if ry is None else ry
    return [(cx + rx * math.cos(phase + 2 * math.pi * i / n), cy + ry * math.sin(phase + 2 * math.pi * i / n), z) for i in range(n)]


def export_fbx(objs, path):
    """Exports objects so that Blender -Y (front) == Unity +Z and Z-up == Unity Y-up,
    with identity root rotation in Unity (bake_space_transform)."""
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH', 'EMPTY'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                             axis_forward='-Z', axis_up='Y', bake_space_transform=True,
                             mesh_smooth_type='FACE', use_mesh_modifiers=True, add_leaf_bones=False,
                             bake_anim=False, path_mode='STRIP', embed_textures=False,
                             use_custom_props=False, colors_type='LINEAR')


def blender_to_unity_vec(v):
    """Position/offset mapping used by the exporter above (Blender -> Unity)."""
    return [-v[0], v[2], -v[1]]


def blender_to_unity_size(s):
    return [abs(s[0]), abs(s[2]), abs(s[1])]
