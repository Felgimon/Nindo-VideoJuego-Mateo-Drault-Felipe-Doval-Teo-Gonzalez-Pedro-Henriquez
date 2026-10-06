"""Clips de Kokuyō: claves, curvas, tiempos y resortes. Fuente única de los tiempos del FBX.

Gramática de cada golpe (la que pidió la auditoría para que el parry se lea):
  anticipación (contra-movimiento) -> pose de AVISO que rompe la silueta vista desde arriba ->
  espera que se mueve (nunca congelada) -> golpe de 2-3 cuadros por un arco limpio -> se pasa
  (follow-through) -> recuperación hasta una pose de encadenado.
La cadera y el tronco van un cuadro adelante de la hoja (las articulaciones se rompen en
sucesión) y la cabeza un cuadro atrás. El pie de adelante apoya justo en el cuadro del impacto.

'timing' de cada clip (cuadros a 30 fps, se copia al .fbx.json):
  tell [inicio, apex]   la anticipación hasta la pose de aviso
  apex                  cuadro de la pose de aviso (AttackDef.apex = apex / frames)
  hold [a, b]           la espera que se mueve
  contact               primer cuadro que pega (activeStart)
  active [a, b]         ventana que pega (activeStart, activeEnd)
  recover [a, b]        castigo / recuperación
  lunge [a, b, m]       avance que el JUEGO aplica al transform (en el clip ya está restado)
  kind                  parry | dodge (imparable) | none
"""
import copy, math
from mathutils import Vector, Quaternion
import nindo_anim as NA
from nindo_anim import Key, Clip, Spring, rot3
import kokuyo_rig as KR
from kokuyo_poses import *


# --------------------------------------------------------------------------- resortes
def springs(rig):
    """Cadenas secundarias. Los faldones además se abren cuando el muslo los empuja."""
    hips_rest = rot3(rig.rest["Hips"])
    thigh_rest = {S: rot3(rig.rest["Thigh_" + S]).col[1] for S in "RL"}
    hipj = {S: rig.head_rest("Thigh_" + S) for S in "RL"}
    plate = {}
    for a in KR.SKIRT_ANGLES:
        h, d, o, t = KR.skirt_frame(a)
        plate[KR.skirt_name(a)] = (h, o, t)

    def thigh_push(W, b):
        h, o, t = plate[b]
        Rh = rot3(W["Hips"]) @ hips_rest.transposed()
        oo, tt = Rh @ o, Rh @ t
        best = 0.0
        for S in "RL":
            cur = rot3(W["Thigh_" + S]).col[1]
            fol = Rh @ thigh_rest[S]
            ang = math.acos(max(-1.0, min(1.0, cur.dot(fol))))
            sw = cur - fol
            sw.z = 0.0
            if sw.length < 1e-5 or ang < 1e-3:
                continue
            c = max(0.0, sw.normalized().dot(oo))
            dist = Vector((h.x - hipj[S].x, h.y - hipj[S].y)).length
            w = max(0.0, min(1.0, 1.45 - dist / 0.65))
            best = max(best, ang * c * w)
        if best < 1e-3:
            return None
        return Quaternion(tt, -min(best, math.radians(75.0)))

    # la melena es pesada: rígida, amortiguada y con tope bajo (si no, en un tajo que frena de golpe se
    # da vuelta sobre la cabeza); busca colgar cuando el torso se inclina
    def local(bone, p):
        return rig.rest_inv[bone] @ Vector(p)
    # la coraza es ancha pero poco profunda: esferas grandes corridas hacia adelante, que asoman justo
    # por la espalda sin tocar la nuca (de donde sale la melena)
    back = [("Chest", local("Chest", (0.0, -0.12, 2.76)), 0.78), ("Spine", local("Spine", (0.0, -0.12, 2.36)), 0.7)]
    front = [("Hips", local("Hips", (0.0, -0.05, 1.95)), 0.8),
             ("Thigh_R", local("Thigh_R", (-0.41, -0.04, 1.36)), 0.46), ("Thigh_L", local("Thigh_L", (0.41, -0.04, 1.36)), 0.46)]
    sp = [Spring([f"Mane_{c}_1", f"Mane_{c}_2", f"Mane_{c}_3"], k=150.0, damp=0.2, grav=5.0, max_deg=40.0, floor=0.08, hang=0.3,
                 colliders=back, follow="Chest") for c in "CRL"]
    sp += [Spring([f"Sash_{s}_1", f"Sash_{s}_2"], k=120.0, damp=0.14, grav=6.0, max_deg=60.0, floor=0.06, hang=0.6,
                  colliders=front) for s in "RL"]
    sp += [Spring(["Sode_R"], k=320.0, damp=0.2, grav=0.0, max_deg=16.0), Spring(["Sode_L"], k=320.0, damp=0.2, grav=0.0, max_deg=16.0)]
    sp += [Spring(["Ribbon_1", "Ribbon_2"], k=75.0, damp=0.1, grav=6.0, max_deg=70.0, floor=0.05, hang=0.7,
                  colliders=[("UpperArm_L", local("UpperArm_L", (1.27, 0.0, 2.85)), 0.38)])]
    sp += [Spring(["Tassel_1", "Tassel_2"], k=70.0, damp=0.1, grav=7.0, max_deg=80.0, floor=0.04, hang=0.85)]
    sp += [Spring([KR.skirt_name(a)], k=240.0, damp=0.2, grav=0.0, max_deg=40.0, push=thigh_push, floor=0.07)
           for a in KR.SKIRT_ANGLES]
    return sp


SPRING_CHAINS = {"mane": ["Mane_C_1..3", "Mane_R_1..3", "Mane_L_1..3"], "obi_tails": ["Sash_R_1..2", "Sash_L_1..2"],
                 "ribbon_shoulder": ["Ribbon_1", "Ribbon_2"], "ribbon_pommel": ["Tassel_1", "Tassel_2"],
                 "sode": ["Sode_R", "Sode_L"], "kusazuri": [KR.skirt_name(a) for a in KR.SKIRT_ANGLES]}

LEAD = {"hips": -0.6, "hips_rot": -0.6, "spine": -0.3, "head": 1.0, "neck": 0.5}

CLIPS = []


def add(name, frames, keys, loop=False, lag=None, timing=None, events=None, notes="", root_vel=(0, 0, 0)):
    """keys: (cuadro, pose, curva) o (cuadro, pose, curva, {canal: curva})."""
    # cada clave con su propia copia: varios clips (y claves) comparten las poses de la biblioteca
    c = Clip(name, frames, [Key(k[0], copy.deepcopy(k[1]), k[2], dict(k[3]) if len(k) > 3 else None) for k in keys], loop=loop,
             lag=LEAD if lag is None else lag, timing=timing, events=events, notes=notes, root_vel=root_vel)
    CLIPS.append(c)
    return c


# =========================================================================== guardia que respira
_breath_in = mod(READY, breath=1.0, hips=(0.0, 0.06, -0.18), grip=(-1.22, 0.38, 1.54), head=(-8.0, 0.0, 3.0))
add("Idle", 72, [(0, READY, "sine"), (36, _breath_in, "sine"), (72, READY, "sine")], loop=True, lag={"head": 3.0, "grip": 2.0},
    notes="wakigamae: una mano, la nodachi colgando atrás; una respiración (el pecho sube a los 1.2 s)")

# =========================================================================== kesagiri (corte del monje)
# AVISO lateral: la hoja alta y hacia afuera, atrás del hombro derecho (desde arriba es una línea
# larga que sale de la silueta; vertical se acortaría y taparía la cabeza). El pie izquierdo entra
# en el impacto y el de atrás se arrastra con la embestida (1.2 m que mueve el juego).
_k_dip = mod(READY, hips=(0.0, 0.14, -0.27), hips_rot=(0.0, 0.0, -26.0), spine=(3.0, 0.0, -4.0), chest=(-2.0, 0.0, -6.0),
             neck=(-2.0, 0.0, 12.0), head=(-6.0, 0.0, 14.0),
             grip=(-1.3, 0.62, 1.8), blade=(-0.2, 0.92, -0.34), edge=(0.0, 0.3, -0.95), elbow_r=(-0.8, 0.4, -0.3))
HIGH_R = mod(READY, hips=(0.0, 0.2, -0.22), hips_rot=(0.0, 0.0, -28.0), spine=(-5.0, -4.0, -12.0), chest=(-6.0, 2.0, -10.0),
             neck=(2.0, 0.0, 18.0), head=(-4.0, 0.0, 24.0), clav_r=(0.0, 8.0, 0.0), clav_l=(0.0, -4.0, -6.0),
             grip=(-0.86, 0.24, 3.6), blade=(-0.55, 0.62, 0.56), edge=(-0.3, -0.62, 0.72), elbow_r=(-0.9, 0.3, 0.2),
             grip_l=1.0, elbow_l=(0.5, -0.6, -0.5))
# el avance sigue la curva del juego: arranca al soltar el apex y lleva ~60 % en el impacto
_k_settle = feet(mod(HIGH_R, hips=(0.0, 0.16, -0.26), grip=(-0.9, 0.27, 3.62), blade=(-0.57, 0.62, 0.54), travel=0.45),
                 r=toe(-0.62, 0.62, -30.0, 12.0), l=((0.53, -0.92, 0.42), (-12.0, 0.0, 14.0)))
_k_mid = feet(mod(HIGH_R, hips=(0.03, -0.05, -0.34), hips_rot=(0.0, 0.0, 2.0), spine=(10.0, 0.0, 2.0), chest=(4.0, 0.0, 2.0),
                  neck=(-4.0, 0.0, 0.0), head=(-8.0, 0.0, -2.0),
                  grip=(-0.35, -0.78, 3.0), blade=(0.2, -0.95, 0.25), edge=(0.6, 0.0, -0.8), elbow_r=(-0.8, -0.2, -0.3),
                  travel=0.6),
              r=toe(-0.62, 0.22, -26.0, 22.0), l=((0.53, -1.5, 0.32), (-8.0, 0.0, 14.0)))
_k_impact = feet(mod(HIGH_R, hips=(0.05, -0.2, -0.5), hips_rot=(0.0, 0.0, 22.0), spine=(22.0, 0.0, 14.0), chest=(10.0, 0.0, 10.0),
                     neck=(-10.0, 0.0, -12.0), head=(-14.0, 0.0, -14.0), clav_r=(0.0, -4.0, 6.0), clav_l=(0.0, 4.0, 4.0),
                     grip=(0.35, -1.2, 1.9), blade=(0.62, -0.58, -0.53), edge=(0.55, 0.3, -0.78), elbow_r=(-0.5, 0.1, -0.85),
                     elbow_l=(0.8, 0.3, -0.5), travel=0.72),
                 r=toe(-0.62, -0.12, -28.0, 24.0), l=flat(0.52, -1.78, 14.0))
_k_over = feet(mod(_k_impact, hips=(0.06, -0.05, -0.48), hips_rot=(0.0, 0.0, 22.0), spine=(26.0, 0.0, 10.0), chest=(12.0, 0.0, 6.0),
                   grip=(0.4, -0.82, 1.5), blade=(0.72, -0.24, -0.66), edge=(0.6, 0.45, -0.66), travel=1.2),
               r=toe(-0.62, -0.58, -30.0, 18.0))
_k_rec_a = mod(_k_over, hips=(0.05, -0.08, -0.42), hips_rot=(0.0, 0.0, 18.0), spine=(22.0, 0.0, 8.0),
               grip=(0.4, -0.84, 1.56), blade=(0.66, -0.4, -0.62))
_low_l_w = at_travel(LOW_L, 1.2)
_k_step = feet(mod(_low_l_w, hips=(0.05, -0.08, -0.38)), r=toe(-0.62, -0.58, -30.0, 6.0))
KESA = add("Kesagiri", 36, [
    (0, READY, "sine"), (8, _k_dip, "sine"), (14, HIGH_R, "inout"), (16, _k_settle, "sine"), (17, _k_mid, "expo_in"),
    (18, _k_impact, "lin"), (21, _k_over, "expo_out", {"foot_r": "snap", "foot_r_rot": "snap"}), (25, _k_rec_a, "sine"), (30, _k_step, "inout"), (36, _low_l_w, "inout")],
    timing={"tell": [0, 14], "apex": 14, "hold": [14, 16], "contact": 18, "active": [18, 21], "recover": [21, 36],
            "lunge": [14, 20, 1.2], "kind": "parry", "chain_from": "READY", "chain_to": "LOW_L"},
    events=[{"frame": 14, "fn": "Apex"}, {"frame": 18, "fn": "Strike"}, {"frame": 18, "fn": "Step"}, {"frame": 34, "fn": "Step"}],
    notes="apex HIGH_R (hoja alta y afuera, atrás del hombro derecho); el pie izquierdo apoya en el impacto")

# solver compartido para los clips que necesitan leer la pose resuelta (soltar la espada, la máscara)
SOLVER = None


def solved(clip, f):
    """Pose resuelta de un cuadro del clip (sin resortes): para anclar en el mundo lo que se suelta."""
    pose = NA.Pose(SOLVER.rig)
    SOLVER.solve(pose, clip.controls(f))
    for n in SOLVER.rig.names:
        pose.get(n)
    return pose.W


# =========================================================================== recuperaciones cortas
add("RecoverL", 15, [(0, LOW_L, "sine"), (8, mod(READY, hips=(0.0, 0.0, -0.22), grip=(-0.9, -0.1, 1.5), blade=(-0.3, 0.6, -0.74),
                                                  grip_l=0.3), "sine"), (15, READY, "sine")],
    timing={"recover": [0, 15], "chain_from": "LOW_L", "chain_to": "READY"}, notes="LOW_L -> guardia (cierra un patrón)")
# chiburi: sacude la hoja (castigo corto que cierra un patrón y le da carácter)
_chi_a = mod(READY, grip=(-1.0, -0.35, 2.3), blade=(-0.45, -0.75, 0.48), edge=(-0.2, -0.45, -0.87), elbow_r=(-0.8, 0.2, -0.3),
             chest=(2.0, 0.0, 2.0), head=(-4.0, 0.0, 6.0))
_chi_b = mod(READY, grip=(-1.28, 0.05, 1.45), blade=(-0.6, 0.2, -0.78), edge=(-0.6, -0.5, 0.2), elbow_r=(-0.8, 0.3, -0.3))
add("RecoverHR", 12, [(0, READY, "sine"), (5, _chi_a, "out"), (7, _chi_b, "snap"), (12, READY, "sine")],
    timing={"recover": [0, 12], "chain_from": "READY", "chain_to": "READY"}, notes="chiburi: sacude la sangre de la hoja")

# =========================================================================== gyakugiri (luna ascendente)
# desde LOW_L: se enrosca bajo a su izquierda y corta subiendo hasta arriba a su derecha
_g_coil = feet(mod(LOW_L, hips=(0.05, 0.05, -0.52), hips_rot=(0.0, 0.0, 34.0), spine=(16.0, 0.0, 14.0), chest=(4.0, 0.0, 10.0),
                   neck=(-6.0, 0.0, -24.0), head=(-8.0, 0.0, -28.0),
                   grip=(0.95, 0.15, 1.42), blade=(0.55, 0.62, -0.56), edge=(0.2, 0.55, 0.8), elbow_r=(-0.3, -0.4, -0.9)),
               l=flat(*L_FOOT))
_g_hold = mod(_g_coil, hips=(0.05, 0.06, -0.54), grip=(0.97, 0.17, 1.41), blade=(0.55, 0.63, -0.55))
_g_hold2 = mod(_g_coil, hips=(0.05, 0.065, -0.545), grip=(0.98, 0.18, 1.4), blade=(0.55, 0.64, -0.54))
# primer cuadro del golpe: la hoja apenas sale del enrosque (el barrido grande es f12-14, con el impacto)
_g_mid = feet(mod(_g_coil, hips=(0.03, -0.05, -0.5), hips_rot=(0.0, 0.0, 22.0), spine=(14.0, 0.0, 8.0), chest=(3.0, 0.0, 6.0),
                  neck=(-6.0, 0.0, -14.0), head=(-8.0, 0.0, -16.0),
                  grip=(0.85, -0.35, 1.55), blade=(0.86, 0.12, -0.5), edge=(0.3, -0.3, 0.9), travel=0.3),
              r=toe(-0.62, 0.45, -30.0, 20.0), l=((0.53, -0.98, 0.38), (-10.0, 0.0, 14.0)))
_g_impact = feet(mod(_g_coil, hips=(-0.05, -0.18, -0.34), hips_rot=(0.0, 0.0, -24.0), spine=(4.0, 0.0, -14.0), chest=(-4.0, 0.0, -10.0),
                     neck=(-2.0, 0.0, 18.0), head=(-6.0, 0.0, 22.0), clav_r=(0.0, 10.0, 0.0),
                     grip=(-0.55, -0.85, 2.95), blade=(-0.6, -0.5, 0.62), edge=(-0.55, 0.0, 0.83), elbow_r=(-0.8, 0.3, -0.2),
                     elbow_l=(0.4, -0.6, -0.6), travel=0.6),
                 r=toe(-0.62, 0.2, -30.0, 20.0), l=flat(0.52, -1.38, 14.0))
_g_over = feet(mod(_g_impact, hips=(-0.06, -0.05, -0.3), hips_rot=(0.0, 0.0, -32.0), spine=(0.0, 0.0, -16.0),
                   grip=(-0.82, -0.45, 3.35), blade=(-0.62, 0.05, 0.78), edge=(-0.7, 0.3, -0.5), travel=0.8),
               r=toe(-0.62, -0.18, -30.0, 14.0))
_g_drop = feet(mod(READY, hips=(0.0, 0.0, -0.2), grip=(-1.12, 0.05, 2.1), blade=(-0.62, 0.35, -0.2), grip_l=0.0,
                   hand_l=(0.8, -0.6, 2.0), travel=0.8), r=flat(-0.62, -0.18, -30.0), l=flat(0.52, -1.38, 14.0))
_g_end = at_travel(READY, 0.8)
add("Gyakugiri", 30, [
    (0, LOW_L, "sine"), (7, _g_coil, "inout"), (10, _g_hold, "sine"), (11, _g_hold2, "sine"), (12, _g_mid, "expo_in"),
    (14, _g_impact, "lin"), (17, _g_over, "expo_out", {"foot_r": "snap", "foot_r_rot": "snap"}), (25, _g_drop, "sine"),
    (30, _g_end, "sine")],
    timing={"tell": [0, 10], "apex": 10, "hold": [10, 11], "contact": 14, "active": [14, 17], "recover": [17, 30],
            "lunge": [10, 15, 0.8], "kind": "parry", "chain_from": "LOW_L", "chain_to": "READY"},
    events=[{"frame": 10, "fn": "Apex"}, {"frame": 14, "fn": "Strike"}, {"frame": 14, "fn": "Step"}],
    notes="apex enroscado bajo a su izquierda (cadera 15 cm más baja); corta subiendo hasta arriba a su derecha")

# =========================================================================== tsuki (colmillo)
# AVISO: la hoja horizontal a la altura de la cadera derecha y el brazo izquierdo APUNTANDO a Kaito
# (la línea de la estocada es la lectura). La embestida (3.5 m del juego) es un deslizamiento: los dos
# pies dejan el piso un instante y el de adelante cae en el impacto.
_t_under = mod(READY, hips=(0.0, 0.1, -0.26), hips_rot=(0.0, 0.0, -18.0), grip=(-1.12, 0.3, 1.85),
               blade=(-0.96, 0.05, -0.28), edge=(0.0, -0.3, -0.95), hand_l=(0.8, -0.8, 2.1))
_t_gather = feet(mod(READY, hips=(0.0, 0.18, -0.34), hips_rot=(0.0, 0.0, -22.0), spine=(6.0, 0.0, -6.0), chest=(2.0, 0.0, -6.0),
                     neck=(-4.0, 0.0, 14.0), head=(-8.0, 0.0, 16.0),
                     grip=(-0.95, 0.35, 2.0), blade=(0.0, -0.995, 0.08), edge=(0.0, 0.0, -1.0), elbow_r=(-0.7, 0.6, -0.4),
                     hand_l=(0.7, -1.0, 2.5), hand_l_dir=(-0.05, -0.95, 0.3), hand_l_up=(-1.0, 0.0, 0.0), elbow_l=(0.6, 0.2, -0.6)),
                 r=flat(*R_FOOT), l=flat(*L_FOOT))
TSUKI_APEX = mod(_t_gather, hips=(0.0, 0.26, -0.46), hips_rot=(0.0, 0.0, -28.0), spine=(10.0, 0.0, -6.0), chest=(2.0, 0.0, -8.0),
                 neck=(-6.0, 0.0, 18.0), head=(-8.0, 0.0, 20.0),
                 grip=(-0.82, 0.38, 1.98), blade=(0.06, -0.997, 0.04),
                 hand_l=(0.55, -1.25, 2.72), hand_l_dir=(-0.12, -0.96, 0.22), elbow_l=(0.5, 0.1, -0.8))
_t_hold = mod(TSUKI_APEX, hips=(0.0, 0.27, -0.47), hand_l=(0.55, -1.27, 2.7))
_t_launch = feet(mod(TSUKI_APEX, hips=(0.0, 0.0, -0.4), hips_rot=(0.0, 0.0, -8.0), grip=(-0.7, -0.2, 2.05),
                     hand_l=(0.7, -0.4, 2.3), travel=0.7),
                 r=((-0.62, 0.35, 0.36), (30.0, 0.0, -30.0)), l=((0.54, -1.3, 0.34), (-10.0, 0.0, 12.0)))
_t_impact = at_travel(feet(mod(THRUST_END), r=toe(*R_FOOT, heel=24.0), l=flat(0.52, -1.08, 14.0)), 2.6)
_t_end = at_travel(THRUST_END, 3.5)
_t_end_hold = mod(_t_end, hips=(0.0, -0.3, -0.52), grip=(-0.3, -1.58, 2.18))
add("Tsuki", 42, [
    (0, READY, "sine"), (9, _t_under, "sine"), (16, _t_gather, "sine"), (18, TSUKI_APEX, "out"), (20, _t_hold, "sine"),
    (21, _t_launch, "expo_in", {"travel": "lin", "foot_l": "lin", "foot_r": "lin"}),
    (23, _t_impact, "lin"), (26, _t_end, "expo_out", {"travel": "out", "foot_l": "out", "foot_r": "out"}), (42, _t_end_hold, "sine")],
    timing={"tell": [0, 18], "apex": 18, "hold": [18, 20], "contact": 23, "active": [23, 26], "recover": [26, 42],
            "lunge": [19, 24, 3.5], "kind": "parry", "chain_from": "READY", "chain_to": "THRUST_END",
            # una estocada es lineal: su pico (~50 m/s) es más bajo que el de un tajo; la anticipación va
            # a la misma velocidad que la de los otros golpes (~35 m/s), así que el tope relativo es otro
            "tip_ratio_max": 0.75},
    events=[{"frame": 18, "fn": "Apex"}, {"frame": 23, "fn": "Strike"}, {"frame": 23, "fn": "Step"}],
    notes="estocada: la línea del brazo izquierdo apunta a Kaito; deslizamiento de 3.5 m (lo mueve el juego)")
# el pie de adelante vuelve atrás de un paso y el de atrás se arrastra hasta la guardia
_tr_a = feet(mod(THRUST_END, hips=(0.0, -0.18, -0.42), hips_rot=(0.0, 0.0, 10.0), spine=(10.0, 0.0, 4.0),
                 grip=(-0.7, -1.2, 2.0), blade=(-0.1, -0.95, -0.3), hand_l=(1.0, 0.2, 1.9)),
             r=toe(*R_FOOT, heel=12.0), l=((0.52, -0.86, 0.46), (-10.0, 0.0, 14.0)))
_tr_b = feet(mod(READY, hips=(0.0, 0.02, -0.2), grip=(-1.1, 0.05, 1.6), blade=(-0.3, 0.7, -0.65)),
             r=toe(*R_FOOT, heel=8.0), l=flat(*L_FOOT))
add("TsukiRecover", 18, [(0, THRUST_END, "sine"), (6, _tr_a, "inout"), (12, _tr_b, "inout", {"foot_l": "out2"}), (18, READY, "sine")],
    timing={"recover": [0, 18], "chain_from": "THRUST_END", "chain_to": "READY"},
    events=[{"frame": 12, "fn": "Step"}], notes="castigo: retrae la estocada; el pie de atrás se adelanta")


# =========================================================================== ichimonji (horizonte, imparable)
# se enrosca a su izquierda con la hoja horizontal atrás (aviso lento y ancho: dash o meterse bajo
# la empuñadura) y barre 240° a la altura de la cintura hasta pasarse atrás a su derecha
ICHI_BASE = mod(READY, hips=(0.05, 0.06, -0.4), grip_l=1.0, elbow_r=(-0.6, 0.5, -0.6), elbow_l=(0.6, 0.5, -0.6))


def _sweep(az_deg, r=1.05, z=2.05, hips_rot=0.0, spine_z=0.0, chest_z=0.0, tip_z=0.02, **kw):
    """Pose del barrido: la hoja apunta al azimut dado (0 = frente, + = hacia su izquierda)."""
    a = math.radians(az_deg)
    bd = Vector((math.sin(a), -math.cos(a), tip_z)).normalized()
    edge = Vector((-math.cos(a), -math.sin(a), 0.0))          # el filo mira hacia donde barre (horario)
    g = Vector((math.sin(a) * r, -math.cos(a) * r * 0.85, z))
    turn = hips_rot + spine_z + chest_z
    return feet(mod(ICHI_BASE, hips_rot=(0.0, 0.0, hips_rot), spine=(8.0, 0.0, spine_z), chest=(2.0, 0.0, chest_z),
                    neck=(-4.0, 0.0, -turn * 0.55), head=(-6.0, 0.0, -turn * 0.4),
                    grip=tuple(g), blade=tuple(bd), edge=tuple(edge), **kw), r=flat(-0.98, 0.74, -40.0), l=flat(*L_FOOT))


_i_step = feet(mod(READY, hips=(0.03, 0.06, -0.26), hips_rot=(0.0, 0.0, 6.0), grip=(-0.4, 0.2, 1.7), blade=(0.6, 0.5, -0.62),
                   grip_l=0.6), r=((-0.82, 0.7, 0.46), (-10.0, 0.0, -36.0)), l=flat(*L_FOOT))
ICHI_APEX = _sweep(132.0, r=0.95, hips_rot=34.0, spine_z=12.0, chest_z=8.0)
add("Ichimonji", 48, [
    (0, READY, "sine"), (8, _i_step, "inout"), (14, _sweep(120.0, r=0.95, hips_rot=26.0, spine_z=10.0, chest_z=6.0), "inout"),
    (21, ICHI_APEX, "sine"), (24, _sweep(135.0, r=0.95, hips_rot=35.0, spine_z=12.0, chest_z=8.0), "sine"),
    (26, _sweep(90.0, hips_rot=22.0, spine_z=8.0, chest_z=6.0), "in2"),
    (28, _sweep(30.0, hips_rot=6.0, spine_z=4.0, chest_z=2.0), "lin"), (29, _sweep(-8.0, hips_rot=-8.0), "lin"),
    (30, _sweep(-48.0, hips_rot=-20.0, spine_z=-6.0, chest_z=-4.0), "lin"),
    (31, _sweep(-88.0, hips_rot=-30.0, spine_z=-10.0, chest_z=-6.0), "lin"),
    (34, _sweep(-118.0, r=1.0, z=1.95, hips_rot=-42.0, spine_z=-12.0, chest_z=-8.0, tip_z=-0.1), "out"),
    (38, _sweep(-125.0, r=0.95, z=1.85, hips_rot=-40.0, spine_z=-10.0, chest_z=-8.0, tip_z=-0.25, grip_l=0.5), "sine"),
    (43, feet(mod(READY, hips=(0.0, 0.05, -0.24), hips_rot=(0.0, 0.0, -20.0), grip=(-1.2, 0.3, 1.6)),
              r=((-0.8, 0.68, 0.44), (-10.0, 0.0, -34.0)), l=flat(*L_FOOT)), "inout"),
    (48, READY, "inout")],
    timing={"tell": [0, 21], "apex": 21, "hold": [21, 24], "contact": 28, "active": [28, 32], "recover": [32, 48],
            "lunge": [24, 29, 0.0], "kind": "dodge", "safe_core_m": 1.4, "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 21, "fn": "Apex"}, {"frame": 28, "fn": "Strike"}],
    notes="barrido de 240° a la cintura; se pasa 0.33 s (castigo). Sin embestida: la hoja ya llega a 4.4 m")

# =========================================================================== kabuto-wari (rompecascos, imparable)
# AVISO: en puntas de pie con la hoja HORIZONTAL detrás de la cabeza (jōdan-ura: la silueta no pasa
# de 5.8 m); el tajo baja por encima y la hoja queda clavada: dos tirones (castigo) y la arranca
_kw_crouch = feet(mod(READY, hips=(0.0, 0.1, -0.48), hips_rot=(0.0, 0.0, -10.0), spine=(18.0, 0.0, -4.0), chest=(6.0, 0.0, -2.0),
                      neck=(-10.0, 0.0, 6.0), head=(-14.0, 0.0, 8.0),
                      grip=(-0.75, 0.05, 1.85), blade=(-0.3, 0.75, 0.59), edge=(-0.2, -0.6, 0.77), grip_l=1.0,
                      elbow_r=(-0.8, 0.4, -0.4), elbow_l=(0.6, -0.4, -0.6)),
                  r=flat(*R_FOOT), l=flat(*L_FOOT))
_kw_rise = feet(mod(_kw_crouch, hips=(0.0, 0.12, -0.08), spine=(-2.0, 0.0, 0.0), chest=(-4.0, 0.0, 0.0), neck=(-4.0, 0.0, 2.0),
                    head=(-6.0, 0.0, 2.0), grip=(-0.25, 0.2, 3.6), blade=(-0.25, 0.85, 0.46), edge=(0.0, -0.45, 0.89)),
                r=toe(*R_FOOT, heel=14.0), l=toe(*L_FOOT, heel=12.0))
KW_APEX = feet(mod(_kw_rise, hips=(0.0, 0.12, 0.03), spine=(-8.0, 0.0, 0.0), chest=(-8.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0),
                   head=(-4.0, 0.0, 0.0), clav_r=(0.0, 10.0, 0.0), clav_l=(0.0, -10.0, 0.0),
                   grip=(-0.05, 0.25, 4.12), blade=(-0.1, 0.99, -0.08), edge=(0.0, 0.08, 1.0),
                   elbow_r=(-0.9, -0.2, 0.2), elbow_l=(0.9, -0.2, 0.2)),
               r=toe(*R_FOOT, heel=22.0), l=toe(*L_FOOT, heel=20.0))
_kw_hold = mod(KW_APEX, grip=(-0.05, 0.27, 4.13), blade=(-0.1, 0.99, -0.09))
_kw_a = feet(mod(KW_APEX, hips=(0.0, -0.05, -0.12), spine=(6.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0),
                 grip=(-0.05, -0.62, 3.45), blade=(0.0, 0.55, 0.83), edge=(0.0, -0.83, 0.55)),
             r=toe(*R_FOOT, heel=16.0), l=((0.52, -0.95, 0.5), (-12.0, 0.0, 14.0)))
_kw_b = feet(mod(KW_APEX, hips=(0.0, -0.18, -0.36), spine=(18.0, 0.0, 0.0), chest=(8.0, 0.0, 0.0), neck=(-8.0, 0.0, 0.0),
                 head=(-10.0, 0.0, 0.0), grip=(0.0, -1.25, 2.6), blade=(0.0, -0.55, 0.83), edge=(0.0, -0.83, -0.55)),
             r=toe(*R_FOOT, heel=10.0), l=((0.52, -1.25, 0.3), (-6.0, 0.0, 14.0)))
KW_IMPACT = feet(mod(KW_APEX, hips=(0.0, -0.25, -0.64), spine=(32.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(-12.0, 0.0, 0.0),
                     head=(-16.0, 0.0, 0.0), clav_r=(0.0, -4.0, 4.0), clav_l=(0.0, 4.0, -4.0),
                     grip=(0.0, -1.58, 1.28), blade=(0.0, -0.72, -0.69), edge=(0.0, 0.69, -0.72),
                     elbow_r=(-0.7, 0.3, -0.6), elbow_l=(0.7, 0.3, -0.6), sword_ground=1.0),
                 r=flat(*R_FOOT), l=flat(0.52, -1.36, 14.0))
_kw_tug1 = mod(KW_IMPACT, hips=(0.0, -0.02, -0.56), spine=(18.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0), neck=(-4.0, 0.0, 0.0), head=(-8.0, 0.0, 0.0))
_kw_slack = mod(KW_IMPACT, hips=(0.0, -0.2, -0.62), spine=(28.0, 0.0, 0.0))
_kw_tug2 = mod(KW_IMPACT, hips=(0.0, 0.04, -0.5), spine=(12.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0),
               head=(-12.0, 0.0, 0.0), grip=(0.0, -1.56, 1.32))
_kw_yank0 = mod(_kw_tug2, grip=(0.0, -1.5, 1.42), blade=(0.0, -0.68, -0.73))
_kw_lift = feet(mod(_kw_yank0, hips=(0.0, -0.05, -0.42), spine=(16.0, 0.0, 0.0), grip=(-0.2, -1.25, 1.9), blade=(-0.1, -0.85, 0.5),
                    edge=(0.0, -0.5, -0.86)), r=flat(*R_FOOT), l=flat(0.52, -1.36, 14.0))
_kw_lift["sword_ground"] = 0.0
_kw_free = feet(mod(READY, hips=(0.0, 0.0, -0.32), spine=(4.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0),
                    grip=(-0.62, -0.62, 2.45), blade=(-0.3, 0.25, 0.92), edge=(-0.3, -0.9, 0.2), grip_l=1.0,
                    elbow_r=(-0.8, 0.3, -0.3), elbow_l=(0.6, -0.4, -0.6)),
                r=flat(*R_FOOT), l=((0.52, -1.0, 0.44), (-10.0, 0.0, 14.0)))
add("KabutoWari", 60, [
    (0, READY, "sine"), (12, _kw_crouch, "inout"), (17, _kw_rise, "out"), (20, KW_APEX, "out"), (23, _kw_hold, "sine"),
    (25, _kw_a, "expo_in"), (26, _kw_b, "lin"), (27, KW_IMPACT, "lin", {"foot_l": "snap"}), (33, _kw_tug1, "inout"),
    (36, _kw_slack, "inout"), (39, _kw_tug2, "inout"), (44, _kw_yank0, "sine"), (48, _kw_lift, "inout"),
    (54, _kw_free, "inout"), (60, READY, "inout")],
    timing={"tell": [0, 20], "apex": 20, "hold": [20, 24], "contact": 27, "active": [27, 29], "recover": [29, 60],
            "stuck": [28, 44], "rift_start": 27, "ground": [[26, 48]], "kind": "dodge", "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 20, "fn": "Apex"}, {"frame": 27, "fn": "Strike"}, {"frame": 27, "fn": "RiftStart"},
            {"frame": 33, "fn": "Tug"}, {"frame": 39, "fn": "Tug"}, {"frame": 47, "fn": "BladeFree"}],
    notes="la hoja queda clavada f28-44 (0.55 s de golpes libres); la grieta de obsidiana arranca en f27")

# =========================================================================== paso de sombra
_ss_crouch = feet(mod(READY, hips=(0.0, 0.06, -0.58), spine=(30.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(-12.0, 0.0, 0.0),
                      head=(-16.0, 0.0, 0.0), grip=(-0.95, 0.3, 1.25), blade=(-0.2, 0.75, -0.63), hand_l=(0.7, -0.7, 1.3)),
                  r=flat(*R_FOOT), l=flat(*L_FOOT))
add("ShadowSink", 21, [(0, READY, "sine"), (6, _ss_crouch, "inout"), (12, mod(_ss_crouch, lift=-1.1), "in2"),
                        (18, mod(_ss_crouch, lift=-4.0), "in2"), (21, mod(_ss_crouch, lift=-4.0), "lin")],
    timing={"kind": "none", "chain_from": "READY", "ground": [[8, 21]]}, events=[{"frame": 8, "fn": "ShadowPuddle"}],
    notes="se agacha y se hunde 4 m en su propia sombra (el charco violeta lo pone el juego)")
add("ShadowEmerge", 33, [
    (0, mod(_g_hold, lift=-4.0), "lin"), (5, mod(_g_hold, lift=0.18, hips=(0.05, 0.0, -0.36)), "out"), (7, mod(_g_hold, lift=0.0), "in2"),
    (9, _g_hold, "sine"), (11, _g_hold2, "sine"), (12, _g_mid, "expo_in"), (14, _g_impact, "lin"),
    (17, _g_over, "expo_out", {"foot_r": "snap", "foot_r_rot": "snap"}), (25, _g_drop, "sine"), (33, _g_end, "sine")],
    timing={"tell": [5, 9], "apex": 9, "hold": [9, 11], "contact": 14, "active": [14, 17], "recover": [17, 33],
            "lunge": [10, 15, 0.8], "kind": "parry", "chain_to": "READY", "ground": [[0, 4]]},
    events=[{"frame": 4, "fn": "ShadowErupt"}, {"frame": 9, "fn": "Apex"}, {"frame": 14, "fn": "Strike"}],
    notes="sale del charco enroscado y corta subiendo (como el gyakugiri)")

# =========================================================================== reacciones
# parry recibido: el brazo de la espada sale disparado arriba y atrás, la cabeza se va atrás y el
# gigante se balancea sobre los talones (los pies no se mueven: a los 0.5 s puede seguir el combo)
_p_hit = feet(mod(READY, hips=(0.0, 0.22, -0.18), hips_rot=(0.0, 0.0, -14.0), spine=(-14.0, 0.0, -4.0), chest=(-10.0, 0.0, 6.0),
                  neck=(-8.0, 0.0, 6.0), head=(-18.0, 0.0, 10.0), clav_r=(0.0, 14.0, 0.0),
                  grip=(-1.12, 0.55, 3.55), blade=(-0.32, 0.6, 0.73), edge=(-0.4, -0.75, 0.53), elbow_r=(-0.9, 0.3, 0.2),
                  hand_l=(1.35, -0.25, 2.55), hand_l_dir=(0.7, -0.3, 0.6), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.6, 0.6, -0.4)),
              r=flat(*R_FOOT), l=flat(*L_FOOT))
_p_rock = feet(mod(_p_hit, hips=(0.0, 0.42, -0.24), spine=(-18.0, 0.0, -4.0), head=(-20.0, 0.0, 12.0),
                   grip=(-1.15, 0.65, 3.4), blade=(-0.3, 0.72, 0.62)),
               r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=24.0))
_p_back = feet(mod(_p_hit, hips=(0.0, 0.25, -0.3), spine=(2.0, 0.0, 0.0), chest=(0.0, 0.0, 2.0), head=(-4.0, 0.0, 4.0),
                   grip=(-0.6, 0.0, 2.4), blade=(0.3, -0.4, -0.86), hand_l=(0.8, -0.5, 2.2)),
               r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=6.0))
add("Parried", 30, [(0, _p_hit, "lin"), (5, _p_rock, "out"), (10, _p_back, "inout"), (15, LOW_L, "inout"), (30, READY, "sine")],
    lag={"head": 2.0, "neck": 1.0, "hand_l": 1.5},
    timing={"recover": [0, 30], "resume": 15, "chain_to": "READY"},
    events=[{"frame": 0, "fn": "Parried"}],
    notes="el clip de 'feel' más importante: cada parry tiene que sacudir al gigante. f15 = LOW_L (sigue el combo)")
_f_hit = mod(READY, hips=(0.0, 0.14, -0.2), spine=(-6.0, 4.0, 2.0), chest=(-8.0, 2.0, 4.0), neck=(-6.0, 0.0, 4.0), head=(-14.0, 0.0, 8.0),
             clav_r=(0.0, 6.0, 0.0), clav_l=(0.0, -6.0, 0.0), grip=(-1.12, 0.32, 1.7), hand_l=(0.9, -0.3, 2.0))
add("Flinch", 15, [(0, READY, "lin"), (3, _f_hit, "out"), (15, READY, "sine")], lag={"head": 1.5},
    timing={"recover": [0, 15], "chain_to": "READY"}, notes="lo usa la interrupción por habilidad (antes del aviso)")
add("Guard", 36, [(0, READY, "sine"), (10, GUARD, "inout"), (23, mod(GUARD, breath=0.7), "sine"), (36, GUARD, "sine")],
    timing={"chain_from": "READY", "hold_last": True},
    notes="seigan a dos manos (el juego deja el último cuadro: es una pose quieta y limpia)")
_c_flick = mod(GUARD, hips=(0.0, 0.0, -0.22), hips_rot=(0.0, 0.0, -18.0), grip=(-0.62, -0.78, 2.7), blade=(-0.78, -0.42, 0.46),
               edge=(-0.5, 0.6, -0.6), chest=(0.0, 0.0, -6.0))
_c_check = mod(GUARD, hips=(0.0, -0.42, -0.34), hips_rot=(0.0, 0.0, 30.0), spine=(16.0, 0.0, 14.0), chest=(6.0, 0.0, 10.0),
               neck=(-6.0, 0.0, -18.0), head=(-8.0, 0.0, -20.0), grip=(-0.75, -0.2, 2.15), blade=(-0.35, -0.5, -0.79),
               edge=(-0.3, 0.8, -0.4))
add("Counter", 15, [(0, GUARD, "lin"), (3, _c_flick, "snap"), (7, _c_check, "expo_out"), (10, mod(_c_check, hips=(0.0, -0.38, -0.36)), "sine"),
                    (15, LOW_L, "inout")],
    timing={"contact": 7, "active": [7, 9], "apex": 2, "recover": [9, 15], "kind": "push", "chain_from": "GUARD", "chain_to": "LOW_L"},
    events=[{"frame": 3, "fn": "Deflect"}, {"frame": 7, "fn": "Strike"}],
    notes="desvía la katana de Kaito y lo empuja con el hombro; termina en LOW_L para seguir con un gyakugiri")
_r_crouch = mod(READY, hips=(0.0, 0.1, -0.42), spine=(28.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(10.0, 0.0, 0.0), head=(20.0, 0.0, 0.0),
                clav_r=(0.0, -8.0, 0.0), clav_l=(0.0, 8.0, 0.0), grip=(-0.85, -0.25, 1.45), blade=(-0.2, 0.6, -0.77),
                hand_l=(0.62, -0.62, 1.55))
_r_out = mod(READY, hips=(0.0, 0.04, -0.06), spine=(-14.0, 0.0, 0.0), chest=(-16.0, 0.0, 0.0), neck=(-10.0, 0.0, 0.0), head=(-24.0, 0.0, 0.0),
             clav_r=(0.0, 14.0, 0.0), clav_l=(0.0, -14.0, 0.0), grip=(-1.62, 0.0, 2.85), blade=(-0.8, 0.3, -0.52), edge=(-0.3, 0.2, 0.93),
             hand_l=(1.72, -0.12, 2.85), hand_l_dir=(0.9, -0.1, 0.3), hand_l_up=(0.0, -1.0, 0.0), elbow_r=(-0.5, 0.6, -0.6),
             elbow_l=(0.5, 0.6, -0.6))
_r_tr = [mod(_r_out, head=(-24.0 + d, 0.0, d * 0.4), chest=(-16.0 + d * 0.3, 0.0, 0.0), grip=(-1.62, 0.0, 2.85 + d * 0.006))
         for d in (2.5, -2.0, 2.0, -1.5)]
add("Roar", 39, [(0, READY, "sine"), (9, _r_crouch, "inout"), (14, _r_out, "expo_out"), (18, _r_tr[0], "sine"), (22, _r_tr[1], "sine"),
                 (26, _r_tr[2], "sine"), (30, _r_tr[3], "sine"), (39, READY, "inout")],
    timing={"kind": "none", "chain_to": "READY"}, events=[{"frame": 14, "fn": "Roar"}],
    notes="se encoge y explota abriendo los brazos; tiembla hasta f30")


# =========================================================================== rodilla en el piso (agotado)
# cae sobre la rodilla derecha clavando la nodachi adelante; jadea 3 veces (las grietas laten con la
# respiración: evento Breath) y se levanta. Dura exhaustedTime (3.6 s)
_kn_drop = feet(mod(READY, hips=(0.0, 0.12, -0.5), spine=(14.0, 0.0, 0.0), chest=(6.0, 0.0, 0.0), head=(6.0, 0.0, 0.0),
                    grip=(-0.9, -0.55, 2.3), blade=(-0.25, -0.45, -0.86), edge=(-0.3, -0.85, 0.4),
                    hand_l=(0.7, -0.75, 1.6), knee_r=(0.0, -0.6, -0.8)),
                r=((-0.52, 0.66, 0.5), (30.0, 0.0, -10.0)), l=flat(*L_FOOT))
KNEEL_W = feet(mod(KNEEL), l=flat(*L_FOOT))
_kn_in = mod(KNEEL_W, breath=1.0, hips=(0.0, 0.17, -0.8), spine=(18.0, 0.0, 2.0), head=(10.0, 0.0, 2.0), clav_r=(0.0, 9.0, 0.0),
             clav_l=(0.0, -7.0, 0.0))
_kn_rise = feet(mod(READY, hips=(0.0, 0.1, -0.45), spine=(20.0, 0.0, 0.0), chest=(6.0, 0.0, 0.0),
                    grip=(-1.0, -0.4, 2.0), blade=(-0.3, 0.1, -0.95), hand_l=(0.62, -0.72, 1.5)),
                r=((-0.55, 0.64, 0.48), (20.0, 0.0, -20.0)), l=flat(*L_FOOT))
_kn_keys = [(0, READY, "sine"), (5, _kn_drop, "in2"), (10, KNEEL_W, "snap")]
for i, f in enumerate((23, 36, 49, 62, 75, 88)):
    _kn_keys.append((f, _kn_in if i % 2 == 0 else KNEEL_W, "sine"))
_kn_keys += [(97, _kn_rise, "inout"), (108, READY, "out")]
add("Kneel", 108, _kn_keys, lag={"head": 2.0, "neck": 1.0},
    timing={"kneel": [10, 90], "ground": [[3, 98]], "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 10, "fn": "Armor"}] + [{"frame": f, "fn": "Breath"} for f in (23, 49, 75)],
    notes="agotado: 3 respiraciones (las grietas del pecho laten); se levanta en f90-108")
add("KneelRise", 15, [(0, KNEEL_W, "sine"), (7, _kn_rise, "inout"), (15, READY, "out")],
    timing={"chain_from": "KNEEL", "chain_to": "READY", "ground": [[0, 8]]}, notes="cuando el agotamiento termina antes (que Guard no salte)")

# =========================================================================== arranca su sombra (acto 1 -> 2)
_st_down = feet(mod(READY, hips=(0.0, 0.0, -0.74), hips_rot=(0.0, 0.0, -6.0), spine=(40.0, 0.0, 6.0), chest=(14.0, 0.0, 4.0),
                    neck=(-10.0, 0.0, 0.0), head=(-14.0, 0.0, 0.0), grip=(-1.15, 0.45, 1.25), blade=(-0.3, 0.85, -0.42),
                    hand_l=(0.75, -1.25, 0.28), hand_l_dir=(0.0, -0.5, -0.86), hand_l_up=(0.0, -0.86, 0.5), elbow_l=(0.8, 0.4, 0.2)),
                r=flat(*R_FOOT), l=flat(*L_FOOT))
_st_grab = mod(_st_down, hand_l=(0.75, -1.25, 0.22), spine=(42.0, 0.0, 6.0))
_st_rip = feet(mod(READY, hips=(0.0, 0.18, -0.12), spine=(-16.0, 0.0, -4.0), chest=(-14.0, 0.0, -4.0), neck=(-8.0, 0.0, 0.0),
                   head=(-22.0, 0.0, 0.0), clav_l=(0.0, -16.0, 0.0), grip=(-1.4, 0.4, 2.2), blade=(-0.6, 0.6, -0.53),
                   hand_l=(0.85, -0.35, 4.05), hand_l_dir=(0.1, -0.2, 0.97), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.3, 0.0)),
               r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=10.0))
_st_stagger = feet(mod(READY, hips=(0.0, 0.3, -0.3), spine=(4.0, 0.0, 6.0), chest=(-4.0, 0.0, 6.0), head=(-8.0, 0.0, 8.0),
                       grip=(-1.25, 0.45, 1.8), hand_l=(1.0, -0.2, 2.4)), r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=14.0))
add("ShadowTear", 54, [(0, READY, "sine"), (10, _st_down, "inout"), (16, _st_grab, "sine"), (24, _st_rip, "expo_out"),
                       (30, mod(_st_rip, head=(-24.0, 0.0, 2.0), hand_l=(0.88, -0.3, 4.1)), "sine"), (40, _st_stagger, "inout"),
                       (54, READY, "inout")],
    lag={"head": 2.0, "neck": 1.0, "hand_l": -0.5},
    timing={"chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 16, "fn": "ShadowGrab"}, {"frame": 24, "fn": "CrestSnap"}, {"frame": 24, "fn": "ShadowTear"}],
    notes="la mano izquierda agarra la sombra del piso y la arranca hacia arriba (la media luna izquierda salta en f24)")

# =========================================================================== eclipse (acto 2 -> 3)
_ec_plant = feet(mod(READY, hips=(0.0, 0.05, -0.3), spine=(10.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0),
                     grip=(-0.58, -1.0, 2.15), blade=(0.03, -0.12, -0.99), edge=(0.0, -1.0, 0.0), elbow_r=(-0.8, 0.3, -0.3),
                     hand_l=(0.7, -0.6, 1.8), sword_ground=1.0), r=flat(*R_FOOT), l=flat(*L_FOOT))
_ec_lift = mod(READY, grip=(-0.9, -0.6, 2.7), blade=(-0.1, -0.3, -0.95), edge=(0.0, -1.0, 0.3))
_ec_reach = mod(_ec_plant, hips=(0.0, 0.1, -0.24), spine=(-10.0, 0.0, 0.0), chest=(-12.0, 0.0, 2.0), neck=(-10.0, 0.0, 0.0),
                head=(-26.0, 0.0, 4.0), clav_l=(0.0, -16.0, 0.0),
                hand_l=(0.42, 0.2, 4.3), hand_l_dir=(0.0, 0.2, 0.98), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.0, 0.2))
_ec_close = mod(_ec_reach, hand_l=(0.44, 0.15, 4.25), hand_l_dir=(0.05, 0.4, 0.92))
_ec_pull = mod(_ec_plant, hips=(0.0, 0.05, -0.34), spine=(6.0, 0.0, 0.0), chest=(-4.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0),
               hand_l=(0.62, -0.45, 3.2), hand_l_dir=(0.0, -0.3, 0.95), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.3, -0.2))
add("Eclipse", 72, [(0, READY, "sine"), (10, _ec_lift, "inout"), (20, _ec_plant, "expo_in"), (30, _ec_reach, "inout"),
                    (34, _ec_close, "snap"), (44, _ec_pull, "inout"), (56, _ec_lift, "inout"), (72, READY, "inout")],
    lag={"head": 2.0, "hand_l": 1.0},
    events=[{"frame": 20, "fn": "SwordPlant"}, {"frame": 30, "fn": "MoonFade"}, {"frame": 34, "fn": "FistClose"}],
    timing={"chain_from": "READY", "chain_to": "READY", "ground": [[16, 52]]},
    notes="clava la nodachi y cierra el puño sobre la luna (las luces empiezan a bajar en f30)")

# =========================================================================== último desfile: "¡Todavía no!"
_ls_slump = feet(mod(KNEEL_W, hips=(0.0, 0.2, -0.86), spine=(30.0, 0.0, 4.0), head=(22.0, 0.0, 0.0)), l=flat(*L_FOOT))
_ls_slump["sword_ground"] = 1.0
_ls_push = feet(mod(READY, hips=(0.0, 0.1, -0.45), spine=(24.0, 0.0, 0.0), chest=(8.0, 0.0, 0.0), head=(4.0, 0.0, 0.0),
                    grip=(-0.75, -0.85, 2.05), blade=(0.02, -0.15, -0.99), edge=(0.0, -1.0, 0.0), hand_l=(0.6, -0.75, 1.55)),
                r=((-0.55, 0.64, 0.46), (24.0, 0.0, -20.0)), l=flat(*L_FOOT))
_ls_roar = feet(mod(_r_out, hips=(0.0, 0.06, -0.2)), r=flat(*R_FOOT), l=flat(*L_FOOT))
add("LastStand", 45, [(0, _ls_slump, "lin"), (8, mod(_ls_slump, hips=(0.0, 0.22, -0.9), head=(26.0, 0.0, 0.0)), "sine"),
                      (16, _ls_push, "inout"), (22, _ls_roar, "expo_out"), (26, _r_tr[0], "sine"), (30, _r_tr[1], "sine"),
                      (45, READY, "inout")],
    lag={"head": 2.0},
    timing={"chain_to": "READY", "ground": [[0, 18]]}, events=[{"frame": 22, "fn": "Roar"}],
    notes="al 10 %: se apoya en la espada, se levanta rugiendo y arranca el último desfile")

# =========================================================================== derrota, máscara que cae, seiza
# la nodachi queda clavada donde la soltó y la máscara rueda hasta el piso: ambas viven en el clip (así
# no dependen de reparentar en runtime) y siguen ahí en DefeatLoop y SeizaBow
FALLEN = {}
SEIZA_D = mod(SEIZA, head=(18.0, 0.0, 0.0), neck=(6.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0),
              hand_l=(0.58, -0.5, 1.05), hand_l_dir=(-0.1, -0.95, -0.3), hand_l_up=(0.0, 0.3, 1.0),
              sword_free=1.0, hand_r=(-0.58, -0.5, 1.05), hand_r_dir=(0.1, -0.95, -0.3), hand_r_up=(0.0, 0.3, 1.0),
              elbow_r=(-0.7, 0.5, -0.3))


def _prepare_defeat(clip, rig, solve=None):
    """Ancla en el mundo la espada (cuando la suelta, f20) y la máscara (cuando se cortan los cordones, f40).
    La mano derecha arranca su recorrido libre exactamente desde la empuñadura."""
    for k in clip.keys:
        k.ctrl["sword_free"] = 0.0
        k.ctrl["mask_free"] = 0.0
    W = solved(clip, 20)
    K = W["Katana"]
    FALLEN["sword"] = (tuple(K.translation), tuple(rot3(K).col[1]), tuple(rot3(K).col[2]))
    H = W["Hand_R"]
    hand20 = (tuple(H @ SOLVER.grip_in_hand_r_local()), tuple(rot3(H).col[1]), tuple(rot3(H).col[2]))
    W = solved(clip, 40)
    M = W["Mask"]
    r0 = rot3(rig.rest["Mask"])
    eul = (rot3(M) @ r0.transposed()).to_euler('XYZ')
    m0 = (tuple(M.translation), tuple(math.degrees(a) for a in eul))
    floor = Vector((0.35, -1.75, 0.07))
    FALLEN["mask"] = (tuple(floor), (-88.0, 0.0, 160.0))
    path = {40: m0, 44: ((m0[0][0] + 0.05, m0[0][1] - 0.35, m0[0][2] - 0.55), (m0[1][0] - 40.0, m0[1][1], m0[1][2] + 20.0)),
            48: ((0.3, -1.45, 0.3), (-110.0, 0.0, 70.0)), 50: ((0.32, -1.55, 0.08), (-95.0, 0.0, 95.0)),
            53: ((0.33, -1.64, 0.22), (-80.0, 0.0, 120.0)), 56: ((0.34, -1.7, 0.08), (-92.0, 0.0, 140.0)),
            62: (FALLEN["mask"][0], FALLEN["mask"][1])}
    for k in clip.keys:
        if k.frame >= 20:
            k.ctrl["sword_free"] = 1.0
            k.ctrl["sword_pos"], k.ctrl["sword_dir"], k.ctrl["sword_up"] = FALLEN["sword"]
        if k.frame == 20:
            k.ctrl["hand_r"], k.ctrl["hand_r_dir"], k.ctrl["hand_r_up"] = hand20
            k.ease_ch["sword_free"] = "hold"
        if k.frame == 40:
            k.ease_ch["mask_free"] = "hold"
        if k.frame >= 40:
            k.ctrl["mask_free"] = 1.0
            p = path.get(k.frame)
            if p is None:
                p = FALLEN["mask"]
            k.ctrl["mask_pos"], k.ctrl["mask_rot"] = p


def _with_fallen(p):
    q = mod(p)
    q["sword_free"] = 1.0
    q["sword_pos"], q["sword_dir"], q["sword_up"] = FALLEN["sword"]
    q["mask_free"] = 1.0
    q["mask_pos"], q["mask_rot"] = FALLEN["mask"]
    return q


def _prepare_fallen(clip, rig, solve=None):
    if not FALLEN:
        _prepare_defeat(DEFEAT, rig)
    for k in clip.keys:
        k.ctrl.update(_with_fallen(k.ctrl))


_df_bow = mod(KNEEL_W, head=(22.0, 0.0, 0.0), spine=(26.0, 0.0, 2.0))
_df_let = mod(_df_bow, hand_r=(-0.7, -0.75, 1.75), hand_r_dir=(0.0, -0.6, -0.8), hand_r_up=(0.0, -0.8, 0.6))
_df_rest = mod(_df_bow, hand_r=(-0.55, -0.55, 1.35), hand_r_dir=(0.0, -0.9, -0.4), hand_r_up=(0.0, 0.0, 1.0),
               hand_l=(0.55, -0.62, 1.32))
_df_snap = mod(_df_rest, head=(-12.0, 0.0, 0.0), neck=(-6.0, 0.0, 0.0))
_df_low = mod(_df_rest, head=(24.0, 0.0, 0.0), neck=(8.0, 0.0, 0.0))
_df_lift = feet(mod(_df_low, hips=(0.0, 0.25, -0.95)), l=((0.45, -0.3, 0.5), (40.0, 0.0, 6.0)))
_df_keys = [(0, KNEEL_W, "sine"), (10, _df_bow, "sine"), (20, _df_bow, "sine"),
            (26, _df_let, "inout"), (34, _df_rest, "inout"), (40, _df_rest, "sine"), (42, _df_snap, "snap"),
            (44, mod(_df_snap), "sine"), (48, mod(_df_low, head=(10.0, 0.0, 0.0)), "sine"), (50, mod(_df_low, head=(14.0, 0.0, 0.0)), "sine"),
            (53, mod(_df_low, head=(18.0, 0.0, 0.0)), "sine"), (56, _df_low, "sine"), (62, mod(_df_low), "sine"),
            (70, _df_lift, "inout"), (80, mod(SEIZA_D, hips=(0.0, 0.2, -1.04)), "inout"), (90, SEIZA_D, "sine")]
DEFEAT = add("Defeat", 90, _df_keys, lag={"head": 2.0, "neck": 1.0},
             timing={"release": 20, "mask_snap": 40, "ground": [[0, 90]], "chain_from": "KNEEL", "chain_to": "SEIZA_D"},
             events=[{"frame": 20, "fn": "SwordRelease"}, {"frame": 40, "fn": "MaskSnap"}, {"frame": 50, "fn": "MaskHit"},
                     {"frame": 56, "fn": "MaskHit"}],
             notes="suelta la espada (queda clavada), se cortan los cordones de la máscara (cae y rueda) y se sienta en seiza")
DEFEAT.prepare = _prepare_defeat
_dl = add("DefeatLoop", 60, [(0, SEIZA_D, "sine"), (30, mod(SEIZA_D, breath=1.0, head=(16.0, 0.0, 0.0)), "sine"), (60, SEIZA_D, "sine")],
          loop=True, lag={"head": 3.0}, timing={"chain_from": "SEIZA_D", "ground": [[0, 60]]}, notes="seiza respirando, sin máscara")
_dl.prepare = _prepare_fallen
_bow = mod(SEIZA_D, spine=(42.0, 0.0, 0.0), chest=(10.0, 0.0, 0.0), neck=(6.0, 0.0, 0.0), head=(18.0, 0.0, 0.0),
           hand_l=(0.4, -1.25, 0.24), hand_l_dir=(-0.2, -0.95, 0.0), hand_l_up=(0.0, 0.0, 1.0),
           hand_r=(-0.4, -1.25, 0.24), hand_r_dir=(0.2, -0.95, 0.0), hand_r_up=(0.0, 0.0, 1.0))
_sb = add("SeizaBow", 60, [(0, SEIZA_D, "sine"), (16, _bow, "inout"), (36, mod(_bow, spine=(44.0, 0.0, 0.0)), "sine"), (60, SEIZA_D, "inout")],
          lag={"head": 3.0, "hand_l": 1.0}, timing={"chain_from": "SEIZA_D", "chain_to": "SEIZA_D", "ground": [[0, 60]]},
          notes="la reverencia del final (Kaito le devuelve su media cinta)")
_sb.prepare = _prepare_fallen

# =========================================================================== seiza de espera e intro
add("SeizaIdle", 90, [(0, SEIZA, "sine"), (45, mod(SEIZA, breath=1.0, head=(6.0, 0.0, 0.0)), "sine"), (90, SEIZA, "sine")],
    loop=True, lag={"head": 3.0}, notes="espera arrodillado al pie de la escalera, la espada sobre los muslos")
_in_look = mod(SEIZA, head=(-4.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0))
_in_knee = feet(mod(SEIZA, hips=(0.0, 0.18, -0.88), spine=(14.0, 0.0, 0.0), head=(-2.0, 0.0, 0.0),
                    hand_l=(0.6, -0.82, 1.18), hand_l_dir=(0.0, -0.6, -0.8), hand_l_up=(0.0, -0.8, 0.6),
                    grip=(-0.68, -0.7, 1.3), blade=(0.6, -0.6, -0.53), edge=(0.0, -0.7, 0.7), knee_r=(0.0, -0.55, -0.83)),
                r=toe(-0.45, 0.62, -6.0, 62.0), l=((0.52, -0.58, 0.42), (-6.0, 0.0, 14.0)))
_in_kneel = feet(mod(_in_knee, hips=(0.0, 0.18, -0.82)), l=flat(*L_FOOT))
_in_stand = feet(mod(READY, hips=(0.0, 0.05, -0.3), spine=(14.0, 0.0, 2.0), grip=(-1.05, -0.4, 1.7), blade=(0.1, -0.85, -0.52),
                     edge=(0.0, -0.5, 0.86), hand_l=(0.62, -0.75, 1.6)),
                 r=((-0.56, 0.64, 0.5), (24.0, 0.0, -20.0)), l=flat(*L_FOOT))
_in_draw = mod(READY, hips=(0.0, 0.05, -0.12), spine=(-4.0, 0.0, 0.0), chest=(-6.0, 0.0, 0.0), head=(-8.0, 0.0, 0.0),
               clav_r=(0.0, 12.0, 0.0), grip=(-0.6, -0.05, 4.1), blade=(0.35, 0.93, 0.08), edge=(0.0, -0.08, 1.0),
               elbow_r=(-0.9, 0.2, 0.3), hand_l=(0.9, -0.5, 2.2))
_in_flick = mod(READY, hips=(0.0, 0.02, -0.24), grip=(-1.25, -0.45, 2.1), blade=(-0.55, -0.55, -0.63), edge=(-0.6, 0.6, -0.1))
add("Intro", 96, [(0, SEIZA, "sine"), (24, SEIZA, "sine"), (32, _in_look, "inout"), (44, _in_knee, "inout"),
                  (52, _in_kneel, "inout", {"foot_l": "out2"}), (62, _in_stand, "inout"), (74, _in_draw, "inout"),
                  (78, _in_flick, "snap"), (84, mod(READY, grip=(-1.22, 0.3, 1.55)), "sine"), (96, READY, "sine")],
    lag={"head": 2.0, "neck": 1.0},
    timing={"chain_from": "SEIZA", "chain_to": "READY"},
    events=[{"frame": 24, "fn": "HeadRise"}, {"frame": 52, "fn": "Step"}, {"frame": 62, "fn": "Step"},
            {"frame": 78, "fn": "Chiburi"}, {"frame": 80, "fn": "EyesIgnite"}],
    notes="seiza -> levanta la cabeza -> se para empujándose en la rodilla -> alza la nodachi -> chiburi -> guardia")

# =========================================================================== tsukuyomi (anillos)
_ty_plant = feet(mod(READY, hips=(0.0, 0.1, -0.3), spine=(12.0, 0.0, 0.0), chest=(4.0, 0.0, 0.0),
                     grip=(-0.12, -1.05, 2.3), blade=(0.02, -0.05, -0.998), edge=(0.0, -1.0, 0.0), grip_l=1.0,
                     elbow_r=(-0.8, 0.0, -0.3), elbow_l=(0.8, 0.0, -0.3), sword_ground=1.0), r=flat(*R_FOOT), l=flat(*L_FOOT))
_ty_up = mod(_ty_plant, hips=(0.0, 0.12, -0.12), spine=(2.0, 0.0, 0.0), grip=(-0.12, -1.05, 2.45), head=(-10.0, 0.0, 0.0))
_ty_slam = mod(_ty_plant, hips=(0.0, 0.05, -0.5), spine=(24.0, 0.0, 0.0), chest=(10.0, 0.0, 0.0), grip=(-0.12, -1.05, 2.12))
_ty = [(0, READY, "sine"), (14, _ty_plant, "inout")]
for f in (30, 45, 60):
    _ty += [(f - 6, _ty_up, "inout"), (f, _ty_slam, "expo_in"), (f + 3, mod(_ty_slam, hips=(0.0, 0.05, -0.46)), "out")]
_ty += [(75, READY, "inout")]
add("Tsukuyomi", 75, _ty, timing={"rings": [30, 45, 60], "ground": [[2, 72]], "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": f, "fn": "RingSlam"} for f in (30, 45, 60)],
    notes="clava la espada al frente y la hunde tres veces: un anillo por golpe")


# =========================================================================== locomoción (ciclos procedurales)
# Los pies siguen una trayectoria por fase: en el apoyo se deslizan hacia atrás EXACTAMENTE a la
# velocidad del juego (sin patinar) y en el vuelo hacen un arco. La cadera sube y baja dos veces por
# ciclo (más baja al recibir el peso), gira con la pierna que avanza y el pecho contrarresta.
def _smooth(u):
    return u * u * (3.0 - 2.0 * u)


def gait(name, frames, speed, direction, stance, lift, bob, lean, yaw_amp, sway, sword="trail", notes=""):
    """direction: (x, y) en el que avanza el personaje (frente = (0, -1)); speed en m/s."""
    T = frames / NA.FPS
    d = Vector((direction[0], direction[1], 0.0)).normalized()
    span = speed * stance * T                   # lo que recorre el pie apoyado (en el espacio del personaje)
    side = abs(d.x) > 0.5
    base_r = Vector((-0.62, 0.15 if not side else 0.05, 0.24))
    base_l = Vector((0.52, -0.15 if not side else -0.05, 0.24))
    yaw_r, yaw_l = (-30.0, 14.0) if not side else (-12.0, 8.0)

    def foot(u, base, yaw):
        """u: fase del pie (0 = apoya plano adelante)."""
        heel_max = 18.0
        if u < stance:
            w = u / stance
            p = base + d * (span * (0.5 - w))
            if w > 0.75:                          # despega el talón al final del apoyo (gira sobre la punta)
                return toe(p.x, p.y, yaw, (w - 0.75) / 0.25 * heel_max)
            return (p.x, p.y, 0.24), (0.0, 0.0, yaw)
        # vuelo: de la punta del despegue al apoyo plano siguiente, en arco
        w = (u - stance) / (1.0 - stance)
        s = _smooth(w)
        p0 = base + d * (-0.5 * span)
        a0, _ = toe(p0.x, p0.y, yaw, heel_max)
        p1 = base + d * (0.5 * span)
        a = Vector(a0).lerp(Vector((p1.x, p1.y, 0.24)), s) + Vector((0.0, 0.0, lift * math.sin(math.pi * w)))
        pitch = heel_max * (1.0 - s) - 12.0 * math.sin(math.pi * w)   # adelanta la punta levantada
        return tuple(a), (pitch, 0.0, yaw)

    def fn(f):
        t = f / frames
        ur, ul = t % 1.0, (t + 0.5) % 1.0
        fr, rr = foot(ur, base_r, yaw_r)
        fl, rl = foot(ul, base_l, yaw_l)
        c2 = math.cos(4.0 * math.pi * (t - 0.08))            # dos bajadas por ciclo, justo después de apoyar
        yw = yaw_amp * math.sin(2.0 * math.pi * (t + 0.25))
        sw = sway * math.sin(2.0 * math.pi * t)
        lean_v = Vector((d.x, d.y, 0.0)) * 0.05
        p = mod(READY, hips=(sw * (0 if side else 1) + lean_v.x, 0.05 + lean_v.y, -0.2 - bob * (0.5 + 0.5 * c2)),
                hips_rot=(lean * (0.3 if not side else 0.0), sw * 10.0 * (0 if side else 1), -16.0 + yw),
                spine=(6.0 + lean * 0.5, 0.0, 6.0 - yw * 0.6), chest=(4.0 + lean * 0.3, 0.0, 7.0 - yw * 0.7),
                neck=(-4.0 - lean * 0.4, 0.0, 1.0 + yw * 0.5), head=(-7.0 - lean * 0.4, 0.0, 3.0 + yw * 0.3))
        # la nodachi cuelga atrás y rebota con el paso; al acechar la punta casi raspa el piso
        g = Vector(READY["grip"]) + Vector((0.0, 0.0, -bob * 0.4 * c2))
        bl = Vector(READY["blade"])
        if sword == "drag":
            bl = Vector((-0.3, 0.8, -0.58)).normalized()
        p["grip"] = tuple(g)
        p["blade"] = tuple((bl + Vector((0.0, 0.0, 0.03 * c2))).normalized())
        swing = math.sin(2.0 * math.pi * (t + 0.5))           # el brazo libre va contra la pierna izquierda
        p["hand_l"] = (0.86, -0.52 + 0.25 * swing * (0 if side else 1), 1.72 + 0.05 * abs(swing))
        p["foot_r"], p["foot_r_rot"] = fr, rr
        p["foot_l"], p["foot_l_rot"] = fl, rl
        return p
    c = NA.ProcClip(name, frames, fn, loop=True, root_vel=(d.x * speed, d.y * speed, 0.0),
                    timing={"ground_speed_mps": speed, "stance": stance, "contacts": [0, frames // 2]},
                    events=[{"frame": 0, "fn": "Step"}, {"frame": frames // 2, "fn": "Step"}], notes=notes,
                    sheet_frames=[round(frames * k / 8) for k in range(9)])
    CLIPS.append(c)
    return c


gait("Walk", 36, 1.8, (0.0, -1.0), stance=0.62, lift=0.28, bob=0.05, lean=3.0, yaw_amp=6.0, sway=0.04,
     notes="camina a 1.8 m/s (walkSpeed): pasos de 1.08 m, cadera +-5 cm")
gait("Stalk", 30, 3.0, (0.0, -1.0), stance=0.46, lift=0.42, bob=0.08, lean=8.0, yaw_amp=9.0, sway=0.05, sword="drag",
     notes="acecha a 3.0 m/s (runSpeed): pasos de 1.5 m, la punta casi raspa el piso")
gait("StrafeL", 36, 1.8, (1.0, 0.0), stance=0.6, lift=0.24, bob=0.04, lean=2.0, yaw_amp=3.0, sway=0.0,
     notes="rodea hacia su izquierda a 1.8 m/s sin cruzar los pies (suriashi de costado)")
gait("StrafeR", 36, 1.8, (-1.0, 0.0), stance=0.6, lift=0.24, bob=0.04, lean=2.0, yaw_amp=3.0, sway=0.0,
     notes="rodea hacia su derecha a 1.8 m/s")
