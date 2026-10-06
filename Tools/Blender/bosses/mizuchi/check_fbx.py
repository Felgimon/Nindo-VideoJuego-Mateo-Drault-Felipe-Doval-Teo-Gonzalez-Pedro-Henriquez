"""Ida y vuelta del FBX exportado: lo importa en una escena vacía y compara, cuadro por cuadro, la punta de
algunas articulaciones clave con la referencia que escribió build_mizuchi.py (--export). Detecta tomas corridas
un cuadro, curvas simplificadas de más (latigazos suavizados) y ejes dados vuelta.

blender -b --factory-startup --python check_fbx.py -- <Mizuchi.fbx> <roundtrip_ref.json>
"""
import bpy, sys, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
FBX, REF = argv[0], argv[1]
ref = json.load(open(REF, encoding="utf-8"))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30
bpy.ops.import_scene.fbx(filepath=FBX)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
worst_all = 0.0
for clip, bones in ref["clips"].items():
    act = next((a for a in bpy.data.actions if a.name.endswith("|" + clip)), None)
    if act is None:
        print("FALTA", clip)
        worst_all = 99
        continue
    arm.animation_data.action = act
    # Blender 4.4 (acciones con slots): la acción importada solo se aplica si su slot queda asignado
    if getattr(act, "slots", None) and arm.animation_data.action_slot is None:
        arm.animation_data.action_slot = act.slots[0]
    f0 = int(round(act.frame_range[0]))       # el importador de Blender corre las tomas (empiezan en 1)
    worst = (0.0, "", 0)
    n = len(next(iter(bones.values())))
    for f in range(n):
        bpy.context.scene.frame_set(f0 + f)
        for b, pts in bones.items():
            p = arm.matrix_world @ arm.pose.bones[b].head      # en el mundo: el importador mueve los ejes al objeto
            e = (Vector(pts[f]) - Vector(p)).length
            if e > worst[0]:
                worst = (e, b, f)
    worst_all = max(worst_all, worst[0])
    print(f"RT {clip}: error máx {worst[0] * 100:.2f} cm en {worst[1]} f{worst[2]}")
mats = sorted({m.name for o in bpy.data.objects if o.type == 'MESH' for m in o.data.materials})
print("MESHES", sorted(o.name for o in bpy.data.objects if o.type == 'MESH'), "MATERIALS", mats)
print("ROUNDTRIP", "OK" if worst_all < 0.02 else "FALLA", f"{worst_all * 100:.2f} cm")
