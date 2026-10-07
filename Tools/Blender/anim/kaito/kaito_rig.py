"""Esqueleto de juego de Kaito y traducción de controles de animación a huesos.

ESQUELETO DE JUEGO (audit_anim ANIM-04/12). El rig del equipo colgaba las manos (Mando) y los pies (Pie)
de huesos de IK que nacen en la raíz de la armadura (Targetbrazo / Targetpie): Unity mezcla cada transform
por separado, así que en cada crossfade la muñeca y el tobillo se despegaban del antebrazo y la tibia
(4-9 % del alto). Acá:
  * Mando.L/R pasan a ser hijos de Antebrazo.L/R y Pie.L/R de Tibia.L/R (misma cabeza, cola y roll: el
    bind pose de cada hueso no cambia, solo su padre);
  * los pesos de Targetbrazo -> Mando, Targetpie -> Pie y Polebrazo.R (7 vértices del codo) -> el hueso
    más cercano del brazo: con el rig viejo esos vértices ya seguían a la mano y al pie;
  * los Target/Pole QUEDAN en el FBX, sin pesos y quietos en reposo: los kits de zona
    (Characters/Kits/Kit_kaito_bandana.fbx) traen el esqueleto completo de Kaito en su skin y
    CharacterKits.Attach no viste el kit si falta un solo nombre. Ningún clip nuevo los mueve.
  * nada más cambia: nombres, slots de material, objeto Isan colgado de KatanaBone, orientación de la
    armadura (el kit se arma con la misma; Kaito sigue con modelYaw 90).

ESPACIO DE AUTORÍA ("C"). La armadura de Kaito mira a +Y y tiene el piso en z = -0.8128 (unidades del
archivo: 2.833 u = 1.5 m en el juego). Para escribir las poses con las convenciones de nindo_anim (frente
-Y, derecha del personaje -X, piso en z 0, x+ = inclinarse adelante, z+ = girar a su izquierda) el Rig se
arma con el reposo llevado a C (giro de 180° en Z y el piso a 0). Las bases locales que escribe
Rig.to_local no dependen de ese cambio (es el mismo para todos los huesos), así que lo que se exporta es
la pose real de la armadura.
"""
import math
import bpy
from mathutils import Vector, Matrix, Quaternion
import nindo_anim as NA
from nindo_anim import V, euler_q, basis_yz, compose, rot3

# ------------------------------------------------------------------ medidas
GROUND_ARM_Z = -0.8128                 # suela en la pose de bind (lo que NormalizeHeight pone en y = 0)
TO_C = Matrix.Translation((0.0, 0.0, -GROUND_ARM_Z)) @ Matrix.Rotation(math.pi, 4, 'Z')
HEIGHT_U = 2.833                       # alto de bind (unión de Cuerpo + Isan) en unidades del archivo
M_PER_U = 1.5 / HEIGHT_U               # metros del juego por unidad (NindoContent: height 1.5)
U_PER_M = 1.0 / M_PER_U

# katana (medida sobre la malla Isan, espacio C en reposo): eje de la hoja, punto del puño derecho, punta.
# El filo mira a -X (la derecha de Kaito) con la hoja adelante: el slot Glint está de ese lado del eje.
BLADE_REST = Vector((0.088, -0.996, 0.022)).normalized()
EDGE_REST = Vector((-1.0, 0.088, 0.0)).normalized()
GRIP_REST = Vector((-1.083, 0.039, 1.499))         # centro del puño derecho sobre la empuñadura
TIP_C_REST = Vector((-0.893, -1.600, 1.536))
GRIP_L_OFF = 0.25                                  # la mano izquierda va 25 cm (u) más cerca del pomo

# pie (espacio C, lado derecho; el izquierdo es el espejo en X): tobillo, punta y talón de la suela
ANKLE_R = Vector((-0.243, 0.082, 0.215))
SOLE_TOE_Y, SOLE_HEEL_Y, SOLE_BALL_Y = -0.349, 0.24, -0.19

R_BONES = dict(clav="Hombro.R", ua="Brazo.R", fa="Antebrazo.R", hand="Mando.R", thigh="Pierna.r", shin="Tibia.R", foot="Pie.R")
L_BONES = dict(clav="Hombro.L", ua="Brazo.L", fa="Antebrazo.L", hand="Mando.L", thigh="Pierna.l", shin="Tibia.L", foot="Pie.L")
LEGACY = ("Targetbrazo.L", "Targetbrazo.R", "Targetpie.L", "Targetpie.R", "Polebrazo.L", "Polebrazo.R", "Polepie.L", "Polepie.R")
FINGERS = ("Dedo1", "Dedo2", "Dedo3", "Pulgar", "Puntadedo1", "Puntadedo2", "Puntadedo3", "Puntapulgar")

# puño cerrado del Idle del equipo (base local w, x, y, z de la mano derecha; la izquierda es su espejo):
# la derecha agarra siempre la empuñadura; la izquierda va de abierta (reposo) a este puño con 'fingers_l'
FIST_R = {
    "Dedo1": (0.9047, -0.4116, 0.093, 0.0595), "Puntadedo1": (0.6958, -0.6018, 0.0834, 0.3831),
    "Dedo2": (0.9397, -0.2904, 0.1801, -0.0133), "Puntadedo2": (0.6051, -0.4048, -0.0911, 0.6795),
    "Dedo3": (0.797, -0.5918, 0.0716, 0.0965), "Puntadedo3": (0.7542, -0.3223, -0.1842, 0.5416),
    "Pulgar": (0.9121, -0.4099, 0.0, 0.0), "Puntapulgar": (0.9108, 0.3595, -0.0746, -0.1891),
}


def fist(side):
    out = {}
    for f, (w, x, y, z) in FIST_R.items():
        out[f + "." + side] = Quaternion((w, x, y, z)) if side == "R" else Quaternion((w, x, -y, -z))
    return out


# ------------------------------------------------------------------ esqueleto de juego
def game_skeleton(arm, body):
    """Reparenta manos y pies y pasa los pesos de los huesos de IK (idempotente). Devuelve un resumen."""
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.selected_objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.data.edit_bones
    changed = []
    for child, parent in (("Mando.L", "Antebrazo.L"), ("Mando.R", "Antebrazo.R"), ("Pie.L", "Tibia.L"), ("Pie.R", "Tibia.R")):
        if eb[child].parent is None or eb[child].parent.name != parent:
            eb[child].use_connect = False
            eb[child].parent = eb[parent]
            changed.append(child)
    bpy.ops.object.mode_set(mode='OBJECT')
    moved = {}
    vg = body.vertex_groups

    def merge(src, dst_pick):
        if src not in vg:
            return
        si = vg[src].index
        n = 0
        for v in body.data.vertices:
            w = next((g.weight for g in v.groups if g.group == si), 0.0)
            if w <= 0.0:
                continue
            dst = dst_pick(v)
            if dst not in vg:
                vg.new(name=dst)
            vg[dst].add([v.index], w, 'ADD')
            n += 1
        vg[src].remove([v.index for v in body.data.vertices])
        if n:
            moved[src] = n
    for S in "LR":
        merge("Targetbrazo." + S, lambda v, S=S: "Mando." + S)
        merge("Targetpie." + S, lambda v, S=S: "Pie." + S)
    # el codo derecho: al hueso del brazo cuya recta pasa más cerca de cada vértice
    arm_bones = [arm.data.bones[n] for n in ("Brazo.R", "Antebrazo.R")]
    Mi = arm.matrix_world.inverted() @ body.matrix_world

    def nearest(v):
        p = Mi @ v.co
        best = None
        for b in arm_bones:
            a, c = b.head_local, b.tail_local
            t = max(0.0, min(1.0, (p - a).dot(c - a) / max(1e-9, (c - a).length_squared)))
            d = (a + (c - a) * t - p).length
            if best is None or d < best[0]:
                best = (d, b.name)
        return best[1]
    merge("Polebrazo.R", nearest)
    for n in LEGACY:
        if n in vg:
            vg[n].remove([v.index for v in body.data.vertices])
    return {"reparented": changed, "weights_moved": moved}


def c_rig(arm):
    """Rig de nindo_anim con el reposo en el espacio C (ver arriba)."""
    rig = NA.Rig(arm)
    for n in rig.names:
        rig.rest[n] = TO_C @ rig.rest[n]
        rig.rest_inv[n] = rig.rest[n].inverted()
    for n in rig.names:
        p = rig.parent[n]
        rig.rel[n] = (rig.rest_inv[p] @ rig.rest[n]) if p else rig.rest[n].copy()
    return rig


def sole_points(side):
    """(punta, talón, bola) de la suela en reposo, espacio C, para un lado."""
    sx = 1.0 if side == "R" else -1.0
    ax = ANKLE_R.x * sx
    return (Vector((ax, SOLE_TOE_Y, 0.0)), Vector((ax, SOLE_HEEL_Y, 0.0)), Vector((ax, SOLE_BALL_Y, 0.0)))


def sole_corners(side):
    """Las cuatro esquinas de la suela (punta y talón, adentro y afuera) en reposo, espacio C."""
    sx = 1.0 if side == "R" else -1.0
    xs = (-0.408 * sx, -0.09 * sx) if side == "R" else (0.408, 0.09)
    return [Vector((x, y, 0.0)) for x in xs for y in (SOLE_TOE_Y, SOLE_HEEL_Y)]


def ankle_rest(side):
    return Vector((ANKLE_R.x * (1.0 if side == "R" else -1.0), ANKLE_R.y, ANKLE_R.z))


def foot_rot(pitch, roll=0.0, yaw=0.0):
    """Giro del pie (grados): cabeceo + = la punta baja (el talón sube), giro + = la punta hacia su izquierda."""
    return (Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Matrix.Rotation(math.radians(pitch), 3, 'X')
            @ Matrix.Rotation(math.radians(roll), 3, 'Y'))


def foot_on(side, x, y, pitch=0.0, yaw=0.0, pivot="flat", roll=0.0):
    """Tobillo (x, y, z) y giro del pie para una huella apoyada en (x, y) del piso (la huella = dónde queda
    el tobillo con el pie plano). pivot 'toe' / 'ball' / 'heel': el pie gira 'pitch' sobre el borde de la
    punta, la bola o el talón, que no se mueve (pararse en punta no patina ni mete la suela en el piso)."""
    toe, heel, ball = sole_points(side)
    A = ankle_rest(side)
    R = foot_rot(pitch, roll, yaw)
    Ry = Matrix.Rotation(math.radians(yaw), 3, 'Z')
    base = Vector((x, y, A.z))
    if pivot == "flat" or abs(pitch) < 1e-6:
        return tuple(base), (pitch, roll, yaw)
    P = {"toe": toe, "heel": heel, "ball": ball}[pivot]
    Pw = base + Ry @ (P - A)                       # el borde que apoya, con el pie plano
    ank = Pw + R @ (A - P)
    return tuple(ank), (pitch, roll, yaw)


# ------------------------------------------------------------------ controles por defecto
NEUTRAL = {
    "hips": (0.0, 0.0, 0.0), "hips_rot": (0.0, 0.0, 0.0), "spine": (0.0, 0.0, 0.0), "head": (0.0, 0.0, 0.0),
    "clav_r": (0.0, 0.0, 0.0), "clav_l": (0.0, 0.0, 0.0),
    "grip": tuple(GRIP_REST), "blade": tuple(BLADE_REST), "edge": tuple(EDGE_REST), "elbow_r": (-0.3, 0.6, -0.6),
    "hand_l": (0.5, -0.2, 1.1), "hand_l_dir": (0.2, -0.4, -0.9), "hand_l_up": (1.0, 0.0, 0.0), "elbow_l": (0.4, 0.6, -0.5),
    "grip_l": 0.0, "fingers_l": 0.6,
    "foot_r": tuple(ankle_rest("R")), "foot_r_rot": (0.0, 0.0, 0.0), "knee_r": (-0.15, -1.0, 0.0),
    "foot_l": tuple(ankle_rest("L")), "foot_l_rot": (0.0, 0.0, 0.0), "knee_l": (0.15, -1.0, 0.0),
    "travel": 0.0, "lift": 0.0, "breath": 0.0, "tremble": 0.0, "arm_space": 0.0,
}


class Solver:
    """Controles -> pose de todos los huesos (nindo_anim.Pose en espacio C)."""

    def __init__(self, rig):
        self.rig = rig
        R = rig
        self.K_rest = compose(GRIP_REST, basis_yz(BLADE_REST, -EDGE_REST))
        self.hand_from_K = self.K_rest.inverted() @ R.rest["Mando.R"]
        # la mano izquierda: dónde queda su puño respecto de la muñeca (espejo de la derecha)
        self.grip_in_hand_r = R.rest_inv["Mando.R"] @ GRIP_REST
        self.fist = {"R": fist("R"), "L": fist("L")}
        self.misses = {}

    def katana_frame(self, grip, blade, edge):
        return compose(V(grip), basis_yz(blade, -V(edge)))

    def left_grip(self, K):
        """Mano izquierda en la empuñadura: espejo de la derecha respecto del plano de la hoja (los dos puños
        cierran igual), GRIP_L_OFF más cerca del pomo."""
        Hr = K @ self.hand_from_K
        X = rot3(K).col[0]
        S = Matrix(((1 - 2 * X.x * X.x, -2 * X.x * X.y, -2 * X.x * X.z),
                    (-2 * X.y * X.x, 1 - 2 * X.y * X.y, -2 * X.y * X.z),
                    (-2 * X.z * X.x, -2 * X.z * X.y, 1 - 2 * X.z * X.z)))
        Rl = S @ rot3(Hr) @ Matrix.Diagonal((-1.0, 1.0, 1.0))
        g = K.translation - rot3(K).col[1] * GRIP_L_OFF
        off = Vector((-self.grip_in_hand_r.x, self.grip_in_hand_r.y, self.grip_in_hand_r.z))
        return compose(g - Rl @ off, Rl)

    def clear_floor(self, K, floor=0.04):
        """Si la punta de la hoja atravesaría el piso, la hoja gira hacia arriba sobre el puño lo justo (la deja
        rozar el piso: caídas, golpes bajos)."""
        tip_local = self.K_rest.inverted() @ TIP_C_REST
        tip = K @ tip_local
        if tip.z >= floor:
            return K
        g = K.translation
        bd = rot3(K).col[1]
        ax = bd.cross(Vector((0.0, 0.0, 1.0)))
        if ax.length < 1e-4:
            ax = rot3(K).col[0]
        ax.normalize()
        lo, hi = 0.0, math.radians(85.0)
        for _ in range(18):
            mid = (lo + hi) * 0.5
            if (g + Matrix.Rotation(mid, 3, ax) @ (tip - g)).z >= floor:
                hi = mid
            else:
                lo = mid
        return compose(g, Matrix.Rotation(hi, 3, ax) @ rot3(K))

    def reach_with_clavicle(self, pose, B, target, max_deg=22.0):
        """Brazos cortos (0.3 m): si la muñeca no llega, el hombro se estira hacia el objetivo."""
        R = self.rig
        reach = (R.length[B["ua"]] + R.length[B["fa"]]) * 0.985
        for _ in range(2):
            sh = (pose.get(B["clav"]) @ R.rel[B["ua"]]).translation
            ex = (V(target) - sh).length - reach
            if ex <= 0.0:
                return
            ch = pose.head(B["clav"])
            a, b = sh - ch, V(target) - ch
            ax = a.cross(b)
            if ax.length < 1e-6:
                return
            ang = min(ex / max(a.length, 1e-3), math.radians(max_deg))
            M = pose.get(B["clav"])
            pose.place(B["clav"], compose(ch, Quaternion(ax.normalized(), ang).to_matrix() @ rot3(M)))

    def fingers(self, pose, side, amount):
        for n, q in self.fist[side].items():
            Q = Quaternion().slerp(q, max(0.0, min(1.0, amount)))
            pose.place(n, pose.follow(n) @ Q.to_matrix().to_4x4())

    def solve(self, pose, c):
        c = {**NEUTRAL, **{k: v for k, v in c.items() if v is not None}}
        R = self.rig
        # 'travel': lo que el juego ya movió el transform (lo clavado en el mundo se corre hacia atrás en el cuerpo);
        # 'lift': un salto (sube cadera y manos; los pies van en el mundo y el piso no se mueve)
        sh = Vector((0.0, c["travel"], 0.0))
        up = Vector((0.0, 0.0, c["lift"]))
        tr = c["tremble"]
        # ---- pelvis: baja lo justo para que los dos pies lleguen
        rr = R.rest["Root"]
        Hm = compose(rr.translation + V(c["hips"]) + up, euler_q(c["hips_rot"]).to_matrix() @ rot3(rr))
        drop = 0.0
        for B, s in ((R_BONES, "r"), (L_BONES, "l")):
            J = (Hm @ R.rel[B["thigh"]]).translation
            A = V(c["foot_" + s]) + sh
            reach = (R.length[B["thigh"]] + R.length[B["shin"]]) * 0.985
            dxy = Vector((J.x - A.x, J.y - A.y)).length
            if dxy < reach:
                drop = max(drop, (J.z - A.z) - math.sqrt(reach * reach - dxy * dxy))
        if drop > 0.0:
            Hm.translation.z -= drop
        self.hip_drop = drop
        pose.place("Root", Hm)
        br = c["breath"]
        pose.delta("tronco", V(c["spine"]) + Vector((-2.5 * br, 0.0, 0.0)))
        pose.delta("cabeza", V(c["head"]) + Vector((1.5 * br, 0.0, 0.0)))
        pose.delta("Hombro.R", V(c["clav_r"]) + Vector((0.0, -2.0 * br, 0.0)))
        pose.delta("Hombro.L", V(c["clav_l"]) + Vector((0.0, 2.0 * br, 0.0)))
        # ---- brazos en el espacio del pecho ('arm_space' 0..1): con el tronco muy girado (dash, caídas) es más fácil
        # decir dónde van las manos respecto del pecho que del transform; 1 = las posiciones y direcciones de las
        # manos y la hoja se leen como si el pecho estuviera en reposo y lo siguen
        w = c.get("arm_space") or 0.0
        if w > 0.0:
            A = pose.get("tronco") @ R.rest_inv["tronco"]
            A3 = rot3(A)
            for k in ("grip", "hand_l"):
                c[k] = tuple(V(c[k]).lerp(A @ V(c[k]), w))
            for k in ("blade", "edge", "hand_l_dir", "hand_l_up", "elbow_r", "elbow_l"):
                c[k] = tuple(NA.slerp_dir(V(c[k]), A3 @ V(c[k]), w))
        # ---- brazo de la katana (temblor: la tensión de una espera, en el puño)
        upw = up * (1.0 - w)                # con los brazos en el pecho el salto ya viene con el pecho
        g = V(c["grip"]) + upw + Vector((math.sin(tr * 37.0), math.cos(tr * 29.0), math.sin(tr * 23.0))) * (0.006 if tr else 0.0)
        g.z = max(g.z, 0.1)                 # el puño nunca atraviesa el piso
        K = self.clear_floor(self.katana_frame(g, c["blade"], c["edge"]))
        Hr = K @ self.hand_from_K
        self.reach_with_clavicle(pose, R_BONES, Hr.translation)
        miss_r = pose.two_bone("Brazo.R", "Antebrazo.R", Hr.translation, c["elbow_r"])
        pose.place("Mando.R", compose(pose.tail("Antebrazo.R"), rot3(Hr)))
        pose.twist_follow("Antebrazo.R", "Mando.R", 0.5)
        self.fingers(pose, "R", 1.0)
        Kc = pose.get("Mando.R") @ self.hand_from_K.inverted()
        # ---- mano libre / segunda mano en la empuñadura
        gl = c["grip_l"]
        hl = V(c["hand_l"]) + upw
        hl.z = max(hl.z, 0.12)
        Hf = compose(hl, basis_yz(c["hand_l_dir"], c["hand_l_up"]))
        if gl > 0.001:
            Hg = self.left_grip(Kc)
            Hl = compose(Hf.translation.lerp(Hg.translation, gl), Hf.to_quaternion().slerp(Hg.to_quaternion(), gl).to_matrix())
        else:
            Hl = Hf
        self.reach_with_clavicle(pose, L_BONES, Hl.translation)
        miss_l = pose.two_bone("Brazo.L", "Antebrazo.L", Hl.translation, c["elbow_l"])
        pose.place("Mando.L", compose(pose.tail("Antebrazo.L"), rot3(Hl)))
        pose.twist_follow("Antebrazo.L", "Mando.L", 0.5)
        self.fingers(pose, "L", max(c["fingers_l"], gl))
        # ---- piernas
        miss_legs = 0.0
        for B, s, S in ((R_BONES, "r", "R"), (L_BONES, "l", "L")):
            ank = V(c["foot_" + s]) + sh
            pr = c["foot_" + s + "_rot"]
            Rp = foot_rot(pr[0], pr[1], pr[2])
            Rf = Rp @ rot3(R.rest[B["foot"]])
            # ninguna esquina de la suela bajo el piso: entre dos claves (tobillo en línea recta, giro por su
            # curva) un pie que se para en punta hundía la punta 1-3 cm; el tobillo sube lo justo
            A0 = ankle_rest(S)
            low = min((ank + Rp @ (P - A0)).z for P in sole_corners(S))
            if low < 0.0:
                ank = ank + Vector((0.0, 0.0, -low))
            miss_legs = max(miss_legs, pose.two_bone(B["thigh"], B["shin"], ank, c["knee_" + s]))
            pose.place(B["foot"], compose(pose.tail(B["shin"]), Rf))
        self.misses = {"hand_r": miss_r, "hand_l": miss_l, "legs": miss_legs}
        return self.misses
