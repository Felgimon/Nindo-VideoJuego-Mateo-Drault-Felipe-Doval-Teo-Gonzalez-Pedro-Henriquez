"""Poses de los "sabores" de movimiento de las variantes (Enemies/VariantMotion.cs, MotionFlavor) sobre el Idle
del equipo, con el kit de cada zona puesto: para ver si la diferencia se lee a la distancia del juego.

    blender -b --python Tools/Blender/characters/kits/preview_motion.py -- OUT_DIR --src-assets DIR --actions SUMO_FBX

Lee los MotionFlavor del .cs (los mismos números que corren en el juego) y aplica las rotaciones de VariantMotion
en el instante de máxima amplitud (respiración arriba, vaivén al costado, mirada girada). Escribe motion_ninja.png
y motion_sumo.png: arriba de costado (la inclinación), abajo la cámara del juego a 1080p x2.
"""
import bpy, os, re, sys, math
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitlib as K  # noqa: E402
import preview_kits as PV  # noqa: E402
import build_kits as B  # noqa: E402

CS = os.path.join(K.REPO, "Nindo", "Assets", "Nindo", "Scripts", "Enemies", "VariantMotion.cs")
# (kit, sabor) por fila; None = el Idle del equipo sin retoques
ROWS = {
    "ninja": [("ninja_default", None), ("ninja_mountain", "Mountain"), ("ninja_lake", "Lake"), ("ninja_bamboo", "Bamboo")],
    "sumo": [("sumo_default", None), ("sumo_mountain", "Mountain"), ("sumo_lake", "Lake"), ("sumo_bamboo", "Bamboo"), ("ozeki", "Champion")],
}
BONES = {"ninja": dict(lower="EspaldaBaja", upper="EspaldaAlta", head="Cabeza"), "sumo": dict(lower=None, upper="Torso", head="Cabeza")}


def flavors():
    src = open(CS, encoding="utf-8").read()
    out = {}
    for name, body in re.findall(r"MotionFlavor (\w+) = new MotionFlavor\s*\{([^}]*)\}", src):
        d = dict(idleSpeed=1, lean=0, hunch=0, headPitch=0, breathe=0, breatheHz=0.3, sway=0, swayHz=0.4, scan=0, scanEvery=1.6)
        for k, v in re.findall(r"(\w+)\s*=\s*(-?[\d.]+)f", body):
            d[k] = float(v)
        out[name] = d
    return out


def freeze_pose(arm):
    """Deja la pose del frame actual como pose fija (sin acción) para sumarle rotaciones a mano."""
    basis = {pb.name: pb.matrix_basis.copy() for pb in arm.pose.bones}
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = basis[pb.name]
    bpy.context.view_layer.update()


def rotate_world(arm, bone, axis, deg):
    """Como VariantMotion: b.rotation = AngleAxis(deg, axis) * b.rotation (gira el hueso sobre su cabeza)."""
    if not bone or bone not in arm.pose.bones or abs(deg) < 1e-6:
        return
    pb = arm.pose.bones[bone]
    mw = arm.matrix_world @ pb.matrix
    head = mw.translation.copy()
    R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
    pb.matrix = arm.matrix_world.inverted() @ R @ mw
    bpy.context.view_layer.update()


def apply_flavor(ch, f):
    """Las rotaciones de VariantMotion.LateUpdate con peso 1, quieto, en el pico de la respiración y del vaivén."""
    arm = ch.arm
    up = Vector((0, 0, 1))
    fwd = Vector((0, -1, 0))                    # place() deja al personaje mirando a -Y (hacia la cámara)
    pitch = up.cross(fwd)                       # girar +θ sobre este eje lleva la cabeza hacia adelante
    w = f["swayHz"] * 2 * math.pi
    t = (math.pi / 2) / w if w > 0 else 0.0     # sin(t w) = 1: el vaivén en su extremo
    breathe = f["breathe"] * 0.5                # respiración arriba (quieto: 0.4 + 0.6)
    sway = f["sway"]
    b = BONES[ch.key]
    share = 0.4 if b["lower"] else 0.0
    for bone, p, r in ((b["lower"], f["lean"] * share, math.sin(t * w) * sway),
                       (b["upper"], f["lean"] * (1 - share) + breathe, math.sin(t * w - 0.8) * sway * 0.6)):
        rotate_world(arm, bone, fwd, r)
        rotate_world(arm, bone, pitch, p)
    for s in ("Hombro.L", "Hombro.R"):
        rotate_world(arm, s, pitch, f["hunch"])
    rotate_world(arm, b["head"], fwd, -math.sin(t * w - 1.6) * sway * 0.5)
    rotate_world(arm, b["head"], pitch, f["headPitch"] - breathe * 0.5)
    rotate_world(arm, b["head"], up, f["scan"])


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    src = argv[argv.index("--src-assets") + 1] if "--src-assets" in argv else None
    actions = argv[argv.index("--actions") + 1] if "--actions" in argv else None
    tmp = os.path.join(out, "_motion")
    os.makedirs(tmp, exist_ok=True)
    fl = flavors()
    for char, rows in ROWS.items():
        side, game = [], []
        for kit_name, flavor in rows:
            ch = K.load_char(char, src, actions if char == "sumo" else None)
            k = K.Kit(ch, kit_name)
            B.KITS[kit_name][1](k)
            k.build()
            B.recolor_body(ch, B.BODY_COLORS.get(kit_name, {}))
            PV.night_scene()
            PV.place(ch, (0, 0, 0), 0, B.GAME_SCALE.get(kit_name, 1.0))
            K.use_action(ch.arm, "Idle")
            bpy.context.scene.frame_set(10)
            freeze_pose(ch.arm)
            if flavor:
                apply_flavor(ch, fl[flavor])
            h = K.CHARS[char]["height"] * B.GAME_SCALE.get(kit_name, 1.0)
            cam = PV.camera()
            PV.aim(cam, Vector((0, 0, h * 0.5)), 90, 12, h * 6, 0, ortho=h * 1.25)
            side.append(PV.render(os.path.join(tmp, f"{kit_name}_side.png"), 256, 360))
            game.append(PV.game_view(os.path.join(tmp, f"{kit_name}_game.png"), Vector((0, 0, PV.CELL_TARGET_Z)), 20, *PV.CELL[char]))
            print("POSE", kit_name, flavor)
        PV.sheet(side + game, os.path.join(out, f"motion_{char}.png"), len(rows), cell=(256, 480), scale_game=2)


if __name__ == "__main__":
    main()
