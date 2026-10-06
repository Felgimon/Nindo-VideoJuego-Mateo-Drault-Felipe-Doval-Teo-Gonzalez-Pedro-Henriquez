"""Esqueleto de Kokuyō y traducción de controles de animación a huesos.

Esqueleto de juego limpio desde el principio (lo que pidió la auditoría de animación): manos
bajo antebrazos, pies bajo tibias, sin huesos de IK en el FBX. Además de la cadena humana tiene
huesos para lo que se mueve solo (melena en 3 cadenas, cintas del obi, hombreras, faldones,
la cinta naranja del hombro y la del pomo) y para lo que el juego tiene que poder soltar o
apagar en runtime (máscara, las dos mitades de la media luna, la hombrera derecha, la espada).

Ejes: Blender Z arriba, frente -Y, derecha del personaje = -X (la mano de la espada).
"""
import math
from mathutils import Vector, Matrix, Quaternion
import nindo_anim as NA
from nindo_anim import BoneDef, V, euler_q, basis_yz, compose, rot3

# ------------------------------------------------------------------ medidas (metros, pose de reposo)
ANKLE_Z = 0.24
HIP_J = Vector((-0.40, 0.0, 1.74))          # cabeza del muslo derecho
KNEE = Vector((-0.42, -0.07, 1.00))         # rodilla apenas adelantada: el IK sabe para dónde doblar
ANKLE = Vector((-0.42, 0.0, ANKLE_Z))
TOE = Vector((-0.42, -0.46, 0.06))
SHOULDER = Vector((-0.98, 0.02, 3.12))
UPPER_LEN, FORE_LEN, HAND_LEN = 0.84, 0.78, 0.30
_u = Vector((-math.sin(math.radians(45)), 0.0, -math.cos(math.radians(45))))
ELBOW = SHOULDER + _u * UPPER_LEN
_l = (_u + Vector((0.0, -0.24, 0.0))).normalized()       # codo apenas doblado hacia atrás
WRIST = ELBOW + _l * FORE_LEN
_h = (_l + Vector((0.0, -0.08, 0.0))).normalized()
GRIP_OFF = 0.15                                          # centro del puño sobre el hueso de la mano
GRIP = WRIST + _h * GRIP_OFF
BLADE_REST = Vector((0.0, -math.cos(math.radians(30)), math.sin(math.radians(30))))   # adelante-arriba
SPINE_REST = Vector((0.0, math.sin(math.radians(30)), math.cos(math.radians(30))))   # lomo de la hoja
GRIP_L_OFF = 0.30        # la mano izquierda va 30 cm más atrás en la empuñadura
POMMEL_OFF = 0.66        # del centro del puño derecho al pomo
TIP_LOCAL = Vector((0.0, 2.75, 0.14))      # punta de la hoja en el espacio del hueso Katana

SKIRT_ANGLES = [22.5 + 45.0 * k for k in range(8)]       # 0° = frente: hay una costura justo al frente
SKIRT_TOP_Z = 2.08
SKIRT_R = (0.64, 0.54)
SKIRT_FLARE = 17.0
SKIRT_LEN = 0.92


def skirt_name(a):
    return f"Skirt_{int(round(a)) % 360:03d}"


def skirt_frame(a):
    """(cabeza, dirección hacia abajo con el vuelo, normal hacia afuera, tangente) de un faldón."""
    r = math.radians(a)
    out = Vector((math.sin(r), -math.cos(r), 0.0))       # a = 0 -> frente (-Y); a = 90 -> izquierda (+X)
    head = Vector((math.sin(r) * SKIRT_R[0], -math.cos(r) * SKIRT_R[1], SKIRT_TOP_Z))
    down = (Vector((0, 0, -1)) * math.cos(math.radians(SKIRT_FLARE)) + out * math.sin(math.radians(SKIRT_FLARE))).normalized()
    tang = Vector((0, 0, 1)).cross(out).normalized()
    return head, down, out, tang


def bones():
    B = [
        BoneDef("Root", (0, 0, 0), (0, 0, 0.4), None, True, (0, -1, 0)),
        BoneDef("Hips", (0, 0, 1.85), (0, 0, 2.15), "Root"),
        BoneDef("Spine", (0, 0, 2.18), (0, 0, 2.70), "Hips"),
        BoneDef("Chest", (0, 0, 2.72), (0, 0, 3.28), "Spine"),
        BoneDef("Neck", (0, 0.02, 3.30), (0, 0.0, 3.50), "Chest"),
        BoneDef("Head", (0, 0, 3.50), (0, 0, 3.95), "Neck"),
        BoneDef("Mask", (0, -0.36, 3.66), (0, -0.60, 3.66), "Head", True, (0, 0, 1)),
        BoneDef("Crest_R", (-0.03, -0.42, 3.94), (-0.45, -0.52, 4.36), "Head", True, (0, -1, 0)),
        # melena: 3 cadenas (los 7 mechones se reparten 2-3-2), cuelgan de la nuca bajo el shikoro
        BoneDef("Mane_C_1", (0, 0.42, 3.62), (0, 0.60, 3.18), "Head", True, (0, 1, 0)),
        BoneDef("Mane_C_2", (0, 0.60, 3.18), (0, 0.70, 2.74), "Mane_C_1", True, (0, 1, 0)),
        BoneDef("Mane_C_3", (0, 0.70, 2.74), (0, 0.73, 2.28), "Mane_C_2", True, (0, 1, 0)),
        BoneDef("Mane_R_1", (-0.17, 0.40, 3.62), (-0.23, 0.58, 3.18), "Head", True, (0, 1, 0)),
        BoneDef("Mane_R_2", (-0.23, 0.58, 3.18), (-0.26, 0.67, 2.76), "Mane_R_1", True, (0, 1, 0)),
        BoneDef("Mane_R_3", (-0.26, 0.67, 2.76), (-0.27, 0.70, 2.36), "Mane_R_2", True, (0, 1, 0)),
        BoneDef("Clav_R", (-0.22, 0.02, 3.15), (-0.92, 0.02, 3.15), "Chest", True, (0, 0, 1)),
        BoneDef("Sode_R", (-1.02, 0.02, 3.50), (-1.32, 0.02, 2.66), "Clav_R", True, (0, -1, 0)),
        BoneDef("UpperArm_R", SHOULDER, ELBOW, "Clav_R", True, (0, -1, 0)),
        BoneDef("Forearm_R", ELBOW, WRIST, "UpperArm_R", True, (0, -1, 0)),
        BoneDef("Hand_R", WRIST, WRIST + _h * HAND_LEN, "Forearm_R", True, (0, -1, 0)),
        BoneDef("Thigh_R", HIP_J, KNEE, "Hips", True, (0, -1, 0)),
        BoneDef("Shin_R", KNEE, ANKLE, "Thigh_R", True, (0, -1, 0)),
        BoneDef("Foot_R", ANKLE, TOE, "Shin_R", True, (0, 0, 1)),
        # colas del obi: cuelgan adelante, sobre la costura de los faldones (lectura frontal)
        BoneDef("Sash_R_1", (-0.10, -0.70, 2.00), (-0.11, -0.82, 1.60), "Hips", True, (0, -1, 0)),
        BoneDef("Sash_R_2", (-0.11, -0.82, 1.60), (-0.12, -0.92, 1.20), "Sash_R_1", True, (0, -1, 0)),
    ]
    B = NA.mirrored(B)
    # espada (solo en la mano derecha) y cinta del pomo
    pommel = GRIP - BLADE_REST * POMMEL_OFF
    B += [
        BoneDef("Katana", GRIP, GRIP + BLADE_REST * 0.6, "Hand_R", True, SPINE_REST),
        BoneDef("Tassel_1", pommel, pommel + Vector((0.0, 0.03, -0.27)), "Katana", True, (0, -1, 0)),
        BoneDef("Tassel_2", pommel + Vector((0.0, 0.03, -0.27)), pommel + Vector((0.0, 0.05, -0.54)), "Tassel_1", True, (0, -1, 0)),
        # media cinta naranja atada a la hombrera izquierda (la otra mitad va en el pomo)
        BoneDef("Ribbon_1", (1.17, -0.58, 3.32), (1.24, -0.64, 2.98), "Sode_L", True, (0, -1, 0)),
        BoneDef("Ribbon_2", (1.24, -0.64, 2.98), (1.29, -0.67, 2.64), "Ribbon_1", True, (0, -1, 0)),
        # marcador de frente (exportado: el validador de Unity comprueba que mire a +Z)
        BoneDef("Facing", (0, -0.8, 3.4), (0, -1.2, 3.4), "Root", True, (0, 0, 1)),
    ]
    for a in SKIRT_ANGLES:
        h, d, o, t = skirt_frame(a)
        B.append(BoneDef(skirt_name(a), h, h + d * SKIRT_LEN, "Hips", True, o))
    return B


# huesos que resuelve el IK o la cadena principal: los 'extra' no pueden tocar a sus padres
IK_BONES = {"UpperArm_R", "Forearm_R", "Hand_R", "Katana", "UpperArm_L", "Forearm_L", "Hand_L",
            "Thigh_R", "Shin_R", "Foot_R", "Thigh_L", "Shin_L", "Foot_L"}

# ------------------------------------------------------------------ controles por defecto
NEUTRAL = {
    "hips": (0.0, 0.0, 0.0), "hips_rot": (0.0, 0.0, 0.0),
    "spine": (0.0, 0.0, 0.0), "chest": (0.0, 0.0, 0.0), "neck": (0.0, 0.0, 0.0), "head": (0.0, 0.0, 0.0),
    "clav_r": (0.0, 0.0, 0.0), "clav_l": (0.0, 0.0, 0.0),
    "grip": tuple(GRIP), "blade": tuple(BLADE_REST), "edge": tuple(-SPINE_REST), "elbow_r": (-0.3, 0.8, -0.3),
    "hand_l": tuple(Vector((-GRIP.x, GRIP.y, GRIP.z))), "hand_l_dir": (0.6, -0.25, -0.7), "hand_l_up": (0.0, -1.0, 0.0),
    "elbow_l": (0.3, 0.8, -0.3), "grip_l": 0.0,
    "foot_r": tuple(ANKLE), "foot_r_rot": (0.0, 0.0, 0.0), "knee_r": (-0.15, -1.0, 0.0),
    "foot_l": (-ANKLE.x, ANKLE.y, ANKLE.z), "foot_l_rot": (0.0, 0.0, 0.0), "knee_l": (0.15, -1.0, 0.0),
    "travel": 0.0, "lift": 0.0, "breath": 0.0, "extra": {},
}


class Solver:
    """Traduce un diccionario de controles a la pose de todos los huesos (ver nindo_anim.Pose)."""

    def __init__(self, rig):
        self.rig = rig
        R = rig
        # relación fija mano -> espada (el puño agarra la empuñadura en el centro)
        self.hand_from_katana = R.rest_inv["Katana"] @ R.rest["Hand_R"]
        # mano izquierda: su muñeca vista desde el centro de su puño (espejo de la derecha)
        self.grip_in_hand_r = R.rest_inv["Hand_R"] @ GRIP
        self.misses = {}

    def katana_frame(self, grip, blade, spine):
        return compose(V(grip), basis_yz(blade, spine))

    def left_grip(self, K):
        """Mano izquierda sobre la empuñadura: espejo de la derecha respecto del plano de la hoja,
        30 cm más cerca del pomo."""
        Hr = K @ self.hand_from_katana
        X = rot3(K).col[0]                                     # normal del plano de la hoja
        S = Matrix(((1 - 2 * X.x * X.x, -2 * X.x * X.y, -2 * X.x * X.z),
                    (-2 * X.y * X.x, 1 - 2 * X.y * X.y, -2 * X.y * X.z),
                    (-2 * X.z * X.x, -2 * X.z * X.y, 1 - 2 * X.z * X.z)))
        # reflejo de la mano derecha (S) y del hueso espejado (diag): rotación propia otra vez
        Rl = S @ rot3(Hr) @ Matrix.Diagonal((-1.0, 1.0, 1.0))
        g = K.translation - rot3(K).col[1] * GRIP_L_OFF
        off = Vector((-self.grip_in_hand_r.x, self.grip_in_hand_r.y, self.grip_in_hand_r.z))
        # palma: el mismo punto del puño que en la derecha, espejado en el eje X local
        wrist = g - Rl @ off
        return compose(wrist, Rl)

    def solve(self, pose, c):
        c = {**NEUTRAL, **{k: v for k, v in c.items() if v is not None}}
        R = self.rig
        # el cuerpo (cadera, manos) se autora relativo al transform del juego; lo que queda clavado en
        # el MUNDO (pies apoyados, espada clavada, máscara en el piso) se corre con el avance del golpe
        sh = Vector((0.0, c["travel"], c["lift"]))
        up = Vector((0.0, 0.0, c["lift"]))
        # ---- cadera y tronco
        hip_rest = R.rest["Hips"]
        Hm = compose(hip_rest.translation + V(c["hips"]) + up, euler_q(c["hips_rot"]).to_matrix() @ rot3(hip_rest))
        # la cadera baja lo justo para que los dos pies lleguen a su apoyo (pies clavados aunque la
        # clave pida una cadera un poco alta)
        drop = 0.0
        for s_ in ("r", "l"):
            S_ = s_.upper()
            J = (Hm @ R.rel["Thigh_" + S_]).translation
            A = V(c["foot_" + s_]) + sh
            reach = (R.length["Thigh_" + S_] + R.length["Shin_" + S_]) * 0.985
            dxy = Vector((J.x - A.x, J.y - A.y)).length
            if dxy < reach:
                need = (J.z - A.z) - math.sqrt(reach * reach - dxy * dxy)
                drop = max(drop, need)
        if drop > 0.0:
            Hm.translation.z -= drop
        self.hip_drop = drop
        pose.place("Hips", Hm)
        br = c["breath"]
        pose.delta("Spine", c["spine"])
        ch = V(c["chest"]) + Vector((-2.2 * br, 0.0, 0.0))
        pose.delta("Chest", ch)
        pose.delta("Neck", V(c["neck"]) + Vector((1.0 * br, 0.0, 0.0)))
        pose.delta("Head", c["head"])
        pose.delta("Clav_R", V(c["clav_r"]) + Vector((0.0, -1.5 * br, 0.0)))
        pose.delta("Clav_L", V(c["clav_l"]) + Vector((0.0, 1.5 * br, 0.0)))
        # ---- brazo de la espada
        sword_free = c.get("sword_free", 0.0) or 0.0
        if sword_free >= 0.5:
            # espada clavada / soltada: la hoja queda donde dice 'sword_*' y la mano va libre
            K = self.katana_frame(V(c["sword_pos"]) + sh, c["sword_dir"], c["sword_up"])
            Hr = compose(V(c["hand_r"]) + up, basis_yz(c["hand_r_dir"], c["hand_r_up"]))
            Hr.translation = Hr.translation - rot3(Hr) @ self.grip_in_hand_r_local()
        else:
            # 'edge' = hacia dónde mira el filo; el eje Z del hueso es el lomo (lo opuesto)
            K = self.katana_frame(V(c["grip"]) + up, c["blade"], -V(c["edge"]))
            if (c.get("sword_ground", 0.0) or 0.0) < 0.5:
                K = self.clear_floor(K, c["lift"])
            Hr = K @ self.hand_from_katana
        self.reach_with_clavicle(pose, "R", Hr.translation)
        miss_r = pose.two_bone("UpperArm_R", "Forearm_R", Hr.translation, c["elbow_r"])
        wr = pose.tail("Forearm_R")
        Hr = compose(wr, rot3(Hr))
        pose.place("Hand_R", Hr)
        pose.twist_follow("Forearm_R", "Hand_R", 0.5)
        if sword_free >= 0.5:
            pose.place("Katana", K)
        else:
            pose.place("Katana", Hr @ R.rel["Katana"])
        K = pose.get("Katana")
        # ---- brazo libre / segunda mano en la empuñadura
        g = c["grip_l"]
        Hf = compose(V(c["hand_l"]) + up, basis_yz(c["hand_l_dir"], c["hand_l_up"]))
        Hf.translation = Hf.translation - rot3(Hf) @ self.grip_in_hand_l_local()
        if g > 0.001 and sword_free < 0.5:
            Hg = self.left_grip(K)
            loc = Hf.translation.lerp(Hg.translation, g)
            q = Hf.to_quaternion().slerp(Hg.to_quaternion(), g)
            Hl = compose(loc, q.to_matrix())
        else:
            Hl = Hf
        self.reach_with_clavicle(pose, "L", Hl.translation)
        miss_l = pose.two_bone("UpperArm_L", "Forearm_L", Hl.translation, c["elbow_l"])
        pose.place("Hand_L", compose(pose.tail("Forearm_L"), rot3(Hl)))
        pose.twist_follow("Forearm_L", "Hand_L", 0.5)
        # ---- las ō-sode cuelgan del hombro pero el brazo las levanta al abrirse o subir (si no, lo
        # atraviesa); al bajar el brazo no se meten hacia el cuerpo: cuelgan
        for S, sg in (("R", 1.0), ("L", -1.0)):
            ua = "UpperArm_" + S
            r0 = rot3(pose.follow(ua)).col[1]
            r1 = rot3(pose.get(ua)).col[1]
            out = -sg                                         # signo de x hacia afuera
            abd = math.atan2(r1.x * out, -r1.z) - math.atan2(r0.x * out, -r0.z)
            flex = math.atan2(-r1.y, -r1.z) - math.atan2(-r0.y, -r0.z)
            abd_l = max(0.0, min(abd * 0.7, math.radians(42.0)))
            flex_l = max(-math.radians(35.0), min(flex * 0.45, math.radians(45.0)))
            if abd_l > 1e-4 or abs(flex_l) > 1e-4:
                q = (Matrix.Rotation(sg * abd_l, 3, 'Y') @ Matrix.Rotation(-flex_l, 3, 'X'))
                A = rot3(pose.get("Clav_" + S)) @ rot3(R.rest["Clav_" + S]).transposed()
                pose.delta("Sode_" + S, (A.transposed() @ q @ A).to_quaternion())
        # ---- piernas
        miss_legs = 0.0
        for s in ("r", "l"):
            S = s.upper()
            ank = V(c["foot_" + s]) + sh
            pr = c["foot_" + s + "_rot"]
            Rf = (Matrix.Rotation(math.radians(pr[2]), 3, 'Z') @ Matrix.Rotation(math.radians(pr[0]), 3, 'X')
                  @ Matrix.Rotation(math.radians(pr[1]), 3, 'Y')) @ rot3(R.rest["Foot_" + S])
            miss_legs = max(miss_legs, pose.two_bone("Thigh_" + S, "Shin_" + S, ank, c["knee_" + s]))
            pose.place("Foot_" + S, compose(pose.tail("Shin_" + S), Rf))
        # ---- máscara suelta (la derrota): cae y rueda hasta el piso, en mundo
        if (c.get("mask_free", 0.0) or 0.0) >= 0.5:
            pose.place("Mask", compose(V(c["mask_pos"]) + sh, euler_q(c["mask_rot"]).to_matrix() @ rot3(R.rest["Mask"])))
        # ---- giros extra de huesos secundarios (hombreras, faldones, melena...)
        for bn, r in sorted(c["extra"].items(), key=lambda kv: R.names.index(kv[0])):
            assert bn not in IK_BONES, bn
            pose.delta(bn, r)
        self.misses = {"hand_r": miss_r, "hand_l": miss_l, "legs": miss_legs}
        return self.misses

    def clear_floor(self, K, lift, floor=0.06):
        """Una nodachi de 3.1 m llega al piso en casi cualquier guardia baja: si la punta lo atravesaría,
        la hoja gira hacia arriba sobre el puño lo justo (como quien la deja rozar el piso). Las poses
        que la clavan a propósito lo desactivan con 'sword_ground'."""
        z_min = floor + lift
        tip = (K @ TIP_LOCAL)
        if tip.z >= z_min:
            return K
        g = K.translation
        bd = rot3(K).col[1]
        ax = bd.cross(Vector((0.0, 0.0, 1.0)))
        if ax.length < 1e-4:
            ax = rot3(K).col[0]
        ax.normalize()
        lo, hi = 0.0, math.radians(80.0)
        for _ in range(18):
            mid = (lo + hi) * 0.5
            R = Matrix.Rotation(mid, 3, ax)
            if (g + R @ (tip - g)).z >= z_min:
                hi = mid
            else:
                lo = mid
        R = Matrix.Rotation(hi, 3, ax)
        return compose(g, R @ rot3(K))

    def reach_with_clavicle(self, pose, S, target, max_deg=24.0):
        """Si la muñeca no llega, el hombro se adelanta (la clavícula gira hacia el objetivo, como la
        escápula al estirarse): da ~25 cm más de alcance sin despegar la mano de la empuñadura."""
        R = self.rig
        cl, ua, fa = "Clav_" + S, "UpperArm_" + S, "Forearm_" + S
        reach = (R.length[ua] + R.length[fa]) * 0.985
        for _ in range(2):
            sh = (pose.get(cl) @ R.rel[ua]).translation
            ex = (V(target) - sh).length - reach
            if ex <= 0.0:
                return
            ch = pose.head(cl)
            a = (sh - ch)
            b = (V(target) - ch)
            ax = a.cross(b)
            if ax.length < 1e-6:
                return
            ang = min(ex / max(a.length, 1e-3), math.radians(max_deg))
            M = pose.get(cl)
            Rq = Quaternion(ax.normalized(), ang).to_matrix()
            pose.place(cl, compose(ch, Rq @ rot3(M)))

    def grip_in_hand_r_local(self):
        return self.grip_in_hand_r

    def grip_in_hand_l_local(self):
        return Vector((-self.grip_in_hand_r.x, self.grip_in_hand_r.y, self.grip_in_hand_r.z))
