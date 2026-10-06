"""Poses procedurales del sumo (Enemies/SumoPoser.cs) sobre el esqueleto del equipo, con el kit del Ōzeki puesto:
para ver desde la cámara del juego si cada carga y cada golpe se leen como lo que son.

    blender -b --python Tools/Blender/characters/sumo_poses.py -- OUT_DIR [--kit ozeki|none] [--moves A,B]

Lee la tabla de poses del .cs (los mismos números que corren en el juego) y la aplica con la misma cuenta que
SumoPoser.Apply: cadera abajo, torso inclinado/girado sobre su pivote, la cabeza compensa, piernas y brazos con IK
de dos huesos hacia puntos del espacio del personaje (y los controles TargetBrazo/TargetPie movidos a la punta).
Como base usa una pose de reposo con los brazos colgando (el FBX no trae el Idle: es un .anim de Unity).
Escribe sumo_poses.png: por golpe, carga y golpe de frente y de costado a la densidad del juego a 1080p y
una vista de cerca de costado para revisar codos y rodillas.
"""
import bpy, os, re, sys, math
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "kits"))
import kitlib as K  # noqa: E402
import preview_kits as PV  # noqa: E402
import build_kits as B  # noqa: E402

CS = os.path.join(K.REPO, "Nindo", "Assets", "Nindo", "Scripts", "Enemies", "SumoPoser.cs")
ORDER = ["hariteR", "shikoR", "tachiai", "grab", "morote", "salt", "hop", "stumble"]


# ----------------------------------------------------------------------------------------------- tabla del .cs
def _call(src, i):
    """Texto entre el '(' en src[i] y su ')' correspondiente."""
    depth, j = 0, i
    while j < len(src):
        if src[j] == "(": depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return src[i + 1:j], j
        j += 1
    raise ValueError("paréntesis sin cerrar")


def _pose(args):
    expr = re.sub(r"(\d)f\b", r"\1", args)
    vals = eval(f"P({expr})", {"P": lambda *a: a, "V": lambda x, y, z: (x, y, z), "default": (0, 0, 0)})
    names = ["drop", "lean", "twist", "roll", "handR", "wHandR", "handL", "wHandL", "footR", "wFootR", "footL", "wFootL"]
    d = dict(drop=0, lean=0, twist=0, roll=0, handR=(0, 0, 0), wHandR=0, handL=(0, 0, 0), wHandL=0,
             footR=(0, 0, 0), wFootR=0, footL=(0, 0, 0), wFootL=0)
    for n, v in zip(names, vals):
        d[n] = v
    return d


def moves():
    src = open(CS, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"var (\w+) = new Move\s*\{", src):
        name, i = m.group(1), m.end()
        body = {}
        for key in ("wind", "strike"):
            k = src.index(key + " = SumoPose.Of(", i)
            args, _ = _call(src, k + len(key + " = SumoPose.Of"))
            body[key] = _pose(args)
        out[name] = body
    return out


# ----------------------------------------------------------------------------------------------- huesos en el mundo
def mw(arm, b):
    return arm.matrix_world @ arm.pose.bones[b].matrix


def pos(arm, b):
    return mw(arm, b).translation.copy()


def set_world(arm, b, M):
    arm.pose.bones[b].matrix = arm.matrix_world.inverted() @ M
    bpy.context.view_layer.update()


def rotate(arm, b, q, pivot=None):
    M = mw(arm, b)
    p = M.translation.copy() if pivot is None else pivot
    set_world(arm, b, Matrix.Translation(p) @ q.to_matrix().to_4x4() @ Matrix.Translation(-p) @ M)


def translate(arm, b, d):
    M = mw(arm, b)
    M.translation += d
    set_world(arm, b, M)


def axis_angle(axis, deg):
    from mathutils import Quaternion
    if axis.length < 1e-9 or abs(deg) < 1e-9:
        return Quaternion()
    return Quaternion(axis.normalized(), math.radians(deg))


def from_to(a, b):
    return a.rotation_difference(b)


def solve_two_bone(arm, upper, lower, lower_len, tip, target, hint):
    """La misma cuenta que SumoPoser.SolveTwoBone."""
    a, b = pos(arm, upper), pos(arm, lower)
    la, lb = (b - a).length, lower_len
    at = target - a
    d = at.length
    if la < 1e-4 or lb < 1e-4 or d < 1e-4:
        return tip
    dr = at / d
    d = max(abs(la - lb) + 1e-3, min(la + lb - 1e-3, d))
    cos_a = max(-1.0, min(1.0, (la * la + d * d - lb * lb) / (2 * la * d)))
    bend = (hint - a) - dr * (hint - a).dot(dr)
    if bend.length < 1e-6:
        bend = (b - a) - dr * (b - a).dot(dr)
    bend.normalize()
    elbow = a + dr * (la * cos_a) + bend * (la * math.sqrt(1 - cos_a * cos_a))
    r1 = from_to(b - a, elbow - a)
    rotate(arm, upper, r1)
    fore = tip - b
    fore = (r1 @ fore.normalized()) * lb if fore.length > 1e-6 else (elbow - a).normalized() * lb
    reach = a + dr * d
    rotate(arm, lower, from_to(fore, reach - elbow))
    return reach


# ----------------------------------------------------------------------------------------------- pose
class Rig:
    def __init__(self, arm, fwd):
        self.arm = arm
        self.up = Vector((0, 0, 1))
        self.fwd = fwd
        self.right = fwd.cross(self.up)
        self.origin = Vector((0, 0, 0))
        self.u = (pos(arm, "Cabeza") - pos(arm, "Torso")).length / 1.435
        self.limbs = {}
        for key, (up_, lo, end) in {"armA": ("Brazo.L", "Antebrazo.L", "Palma.L"), "armB": ("Brazo.R", "Antebrazo.R", "Palma.R"),
                                    "legA": ("Pierna.L", "Tibia.L", "pie.L"), "legB": ("Pierna.R", "Tibia.R", "pie.R")}.items():
            ctrl = arm.pose.bones[end].parent.name
            side = 1.0 if (pos(arm, up_) - self.origin).dot(self.right) > 0 else -1.0
            self.limbs[key] = dict(upper=up_, lower=lo, end=end, ctrl=ctrl, side=side,
                                   lower_len=(pos(arm, end) - pos(arm, lo)).length)
        A, Bb = self.limbs["armA"], self.limbs["armB"]
        self.armR, self.armL = (A, Bb) if A["side"] > 0 else (Bb, A)
        A, Bb = self.limbs["legA"], self.limbs["legB"]
        self.legR, self.legL = (A, Bb) if A["side"] > 0 else (Bb, A)

    def char_point(self, c, side):
        return self.origin + (self.right * (c[0] * side) + self.up * c[1] + self.fwd * c[2]) * self.u

    def reset(self):
        for pb in self.arm.pose.bones:
            pb.matrix_basis = Matrix()
        bpy.context.view_layer.update()

    def idle(self):
        """Reposo aproximado del Idle del equipo: brazos colgando un poco abiertos."""
        for l in (self.armR, self.armL):
            tgt = self.char_point((1.35, 2.25, 0.15), l["side"])
            hint = pos(self.arm, l["upper"]) + (self.right * (l["side"] * 0.7) - self.up * 0.9 - self.fwd * 0.5) * self.u
            reach = solve_two_bone(self.arm, l["upper"], l["lower"], l["lower_len"], pos(self.arm, l["end"]), tgt, hint)
            translate(self.arm, l["ctrl"], reach - pos(self.arm, l["end"]))

    def apply(self, p, w=1.0):
        arm, up, fwd, right, u = self.arm, self.up, self.fwd, self.right, self.u
        handR, handL = pos(arm, self.armR["end"]), pos(arm, self.armL["end"])
        footR, footL = pos(arm, self.legR["end"]), pos(arm, self.legL["end"])
        rotR = mw(arm, self.armR["ctrl"]).to_quaternion()
        rotL = mw(arm, self.armL["ctrl"]).to_quaternion()
        drop = -up * (p["drop"] * u * w)
        translate(arm, "Root", drop)
        q = axis_angle(up.cross(fwd), p["lean"] * w) @ axis_angle(right.cross(fwd), p["twist"] * w) @ axis_angle(up.cross(right), p["roll"] * w)
        pivot = pos(arm, "Torso")
        rotate(arm, "Torso", q)
        rotate(arm, "Cabeza", axis_angle(up.cross(fwd), -p["lean"] * 0.45 * w))
        for l, anim, c, wf in ((self.legR, footR, p["footR"], p["wFootR"]), (self.legL, footL, p["footL"], p["wFootL"])):
            tgt = anim.lerp(self.char_point(c, l["side"]), wf * w) if wf * w > 1e-3 else anim
            hint = pos(arm, l["upper"]) + (fwd * 1.0 + right * (l["side"] * 0.7)) * u
            reach = solve_two_bone(arm, l["upper"], l["lower"], l["lower_len"], anim, tgt, hint)
            translate(arm, l["ctrl"], reach - pos(arm, l["end"]))
        for l, anim, rot, c, wh in ((self.armR, handR, rotR, p["handR"], p["wHandR"]), (self.armL, handL, rotL, p["handL"], p["wHandL"])):
            moved = pivot + q @ (anim + drop - pivot)
            tgt = moved.lerp(self.char_point(c, l["side"]), wh * w) if wh * w > 1e-3 else moved
            hint = pos(arm, l["upper"]) + (right * (l["side"] * 0.7) - up * 0.9 - fwd * 0.5) * u
            reach = solve_two_bone(arm, l["upper"], l["lower"], l["lower_len"], pos(arm, l["end"]), tgt, hint)
            M = mw(arm, l["ctrl"])
            R = (q @ rot).to_matrix().to_4x4()
            R.translation = M.translation
            set_world(arm, l["ctrl"], R)
            translate(arm, l["ctrl"], reach - pos(arm, l["end"]))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else os.path.join(K.REPO, "Tools", "Blender", "out", "sumo_poses")
    kit = "ozeki"
    only = None
    for i, a in enumerate(argv):
        if a == "--kit": kit = argv[i + 1]
        if a == "--moves": only = argv[i + 1].split(",")
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, "_tmp")
    os.makedirs(tmp, exist_ok=True)
    table = moves()
    ch = K.load_char("sumo")
    if kit != "none":
        k = K.Kit(ch, kit)
        B.KITS[kit][1](k)
        k.build()
        B.recolor_body(ch, B.BODY_COLORS.get(kit, {}))
    PV.night_scene()
    scale = B.GAME_SCALE.get(kit, 1.0)
    PV.place(ch, (0, 0, 0), 0, scale)
    ch.arm.data.pose_position = 'POSE'
    bpy.context.view_layer.update()
    rig = Rig(ch.arm, Vector((0, -1, 0)))           # place() lo deja mirando a -Y (hacia la cámara del juego)
    h = K.CHARS["sumo"]["height"] * scale
    cam = PV.camera()
    shots = []
    names = [n for n in ORDER if n in table and (not only or n in only)]
    for n in names:
        for key in ("wind", "strike"):
            rig.reset(); rig.idle(); rig.apply(table[n][key])
            for yaw, pitch in ((80, 6), (20, 20)):
                PV.aim(cam, Vector((0, 0, h * 0.45)), yaw, pitch, h * 6, 0, ortho=h * 1.25)
                shots.append(PV.render(os.path.join(tmp, f"{n}_{key}_{yaw}.png"), 300, 330))
        # cámara del juego a la densidad de 1080p: carga y golpe, de frente y de costado (Kaito al sur o al costado)
        for key in ("wind", "strike"):
            rig.reset(); rig.idle(); rig.apply(table[n][key])
            for yaw in (0, 90):
                shots.append(PV.game_view(os.path.join(tmp, f"{n}_{key}_g{yaw}.png"), Vector((0, 0, h * 0.4)), yaw, 280, 320))
    path = PV.sheet(shots, os.path.join(out, "sumo_poses.png"), 8, cell=(300, 330), scale_game=1)
    print("POSES", path, names)


if __name__ == "__main__":
    main()
