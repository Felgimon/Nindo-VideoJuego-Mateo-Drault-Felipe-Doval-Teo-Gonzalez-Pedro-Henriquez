"""Exporta al abuelo (ViejoGaga.blend del Drive del equipo) a Unity.

El .blend trae al abuelo (malla 'Cuerpo', sin materiales) y a un ninja ('Cube') con la
animación 'inicio' = el secuestro. Coloreamos al abuelo por hueso dominante y exportamos
ambos con el clip. En Unity: clip 'Idle' (primer frame) y 'Kidnap' (completo).

blender -b ViejoGaga.blend --python export_grandpa.py -- <out.fbx> [preview.png]
"""
import bpy, sys, os, json, math, collections
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]

def mat(name, rgb, rough=0.8):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*rgb, 1)
    return m

def srgb(h):
    h = h.lstrip('#'); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

o = bpy.data.objects['Cuerpo']
me = o.data
me.materials.clear()
M = {k: mat("Abuelo_" + k, srgb(v)) for k, v in {
    "Sombrero": "#c9a868", "Piel": "#e8b48a", "Kimono": "#3d5a7a", "Faja": "#8a2b22", "Pantalon": "#3a3633", "Sandalia": "#5a3d28", "Barba": "#e8e4dc"}.items()}
order = list(M.keys())
for k in order: me.materials.append(M[k])
idx2name = {g.index: g.name for g in o.vertex_groups}
# centro de la cabeza
head = [o.matrix_world @ p.center for p in me.polygons]
for p in me.polygons:
    w = collections.Counter()
    for vi in p.vertices:
        for g in me.vertices[vi].groups:
            w[g.group] += g.weight
    dom = idx2name[w.most_common(1)[0][0]] if w else "Root"
    c = o.matrix_world @ p.center
    if dom == "Cabeza":
        r = math.hypot(c.x - 0.1, c.y - 0.0)
        k = "Sombrero" if (c.z > 2.66 or r > 0.46) else ("Barba" if c.z < 2.33 else "Piel")
    elif dom.startswith(("Mano", "Dedo", "Pulgar", "Punta")):
        k = "Piel"
    elif dom.startswith("Pie"):
        k = "Sandalia"
    elif dom.startswith("Tibia"):
        k = "Pantalon"
    elif dom == "Root" and 1.25 < c.z < 1.45:
        k = "Faja"
    else:
        k = "Kimono"
    p.material_index = order.index(k)
    p.use_smooth = False

# limpiar la escena
for ob in list(bpy.data.objects):
    if ob.type not in ('ARMATURE', 'MESH') or (ob.type == 'MESH' and ob.name not in ('Cuerpo', 'Cube')):
        bpy.data.objects.remove(ob, do_unlink=True)
arm = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE')
act = bpy.data.actions['inicio']
arm.animation_data.action = act
f0, f1 = (int(x) for x in act.frame_range)
bpy.context.scene.frame_start, bpy.context.scene.frame_end = f0, f1
bpy.context.scene.render.fps = 30

if len(argv) > 1:
    # vista previa
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    scn.display.shading.color_type = 'MATERIAL'
    scn.render.resolution_x = scn.render.resolution_y = 420
    cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd); scn.collection.objects.link(cam)
    cd.type = 'ORTHO'; cd.ortho_scale = 4.2
    cam.location = (3.5, -5, 3.2); cam.rotation_euler = (math.radians(65), 0, math.radians(35))
    scn.camera = cam
    for i, f in enumerate((f0, (f0 + f1) // 2, f1)):
        scn.frame_set(f); scn.render.filepath = argv[1].replace(".png", f"_{i}.png")
        bpy.ops.render.render(write_still=True)

for ob in bpy.data.objects:
    ob.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=out, use_selection=True, object_types={'ARMATURE', 'MESH'},
                         apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y',
                         mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False,
                         bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.5,
                         path_mode='STRIP', embed_textures=False, primary_bone_axis='Y', secondary_bone_axis='X')
json.dump({"frames": f1 - f0 + 1, "first": f0, "take": "Scene"}, open(out + ".json", "w"))
print("EXPORTED", out, f0, f1)
