"""Clips del abuelo (Nindo/Art/Models/Characters/Grandpa.fbx) en el marco de autoría de team_rig. 1.45 m con el
sombrero, piernas de 0.40 m y brazos cortitos (0.33 m): un viejito encorvado.

Antes tenía un solo cuadro quieto como 'Idle' (y se deslizaba como una estatua). Ahora:
  * Idle (2.5 s): encorvado con las manos atrás, respira con los hombros, cabecea y mira alrededor.
  * Walk (1 s, 0.8 m/s): pasitos cortos, encorvado, las manos atrás (el blend de NPC pide Speed 0.5 al caminar).
  * Bound (3 s): atado al poste del dojo por las cuerdas de sombra (KageArenaFX): la espalda contra el poste, las
    manos atrás, la cabeza gacha; cada tanto forcejea con los hombros. Mantiene el alto parado: las cuerdas se arman
    con los bounds del abuelo.
  * Freed (3 s, el final): libre, se frota las muñecas, se endereza y le hace una reverencia honda a Kaito; termina en
    la pose de Idle.
'Kidnap' sigue siendo la toma del equipo (el ninja del secuestro lo carga). En los clips nuevos el ninja del FBX (el
esqueleto '.001', oculto en el NPC 'grandpa') queda en la pose del primer cuadro del secuestro, así 'Idle' sirve
también al NPC 'kidnap' antes de que arranque la toma.
"""
import math
import nindo_anim as NA
import team_rig as T

Key = NA.Key
WALK_SPEED = 0.8
# NPC.Update pide Speed 0.5 al caminar: con este umbral camina entero
LOCOMOTION = (("Idle", 0.0), ("Walk", 0.5))

STANCE = dict(
    hips=(0.0, 0.02, -0.03), hips_rot=(10.0, 0.0, 0.0), spine=(16.0, 0.0, 0.0), head=(-18.0, 0.0, 0.0),
    knee_r=(-0.2, -1.0, 0.0), knee_l=(0.2, -1.0, 0.0),
    hand_r=(-0.07, 0.17, 0.66), hand_r_dir=(0.6, 0.2, -0.75), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.6, 0.0),
    hand_l=(0.07, 0.19, 0.68), hand_l_dir=(-0.6, 0.2, -0.75), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.6, 0.0),
    fist_r=0.4, fist_l=0.5, breath=0.0,
)
R0, L0 = (-0.10, 0.0, -12.0), (0.10, 0.0, 12.0)


def P(**kw):
    d = dict(STANCE)
    d.update(kw)
    return d


def FR(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    return T.FootKey(f, R0[0] + dx, R0[1] - dy, R0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


def FL(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    return T.FootKey(f, L0[0] + dx, L0[1] - dy, L0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


PLANTED = {"r": [FR(0)], "l": [FL(0)]}


def clips(ch):
    return [idle(), walk(ch), bound(), freed()]


def idle():
    n = 75
    keys = []
    for f in range(0, n + 1, 15):
        a = 2.0 * math.pi * f / n
        b = 2.0 * math.pi * 2.0 * f / n
        keys.append(Key(f, P(hips=(0.01 * math.sin(a), 0.02, -0.03 - 0.006 * (0.5 - 0.5 * math.cos(b))), breath=0.5 - 0.5 * math.cos(b),
                             spine=(16.0 - 2.0 * math.sin(b), 1.5 * math.sin(a), 0.0),
                             head=(-18.0 + 5.0 * math.sin(b + 0.5), 0.0, 14.0 * math.sin(a + 1.0))), "sine"))
    return T.TeamClip("Idle", n, keys, loop=True, feet=PLANTED, notes="encorvado, manos atrás, respira y mira alrededor")


def walk(ch):
    n = 24
    g = T.gait2(ch, n, WALK_SPEED, 0.62, {"r": (-0.09, 0.0, -10.0), "l": (0.09, 0.0, 10.0)}, lift=0.05, toe_off=14.0, heel=-8.0)

    def fn(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g(f))
        c["hips"] = (-0.015 * math.sin(a), 0.02, -0.05 - 0.008 * math.cos(2 * a))
        c["hips_rot"] = (12.0, 3.0 * math.sin(a), 5.0 * math.sin(a))
        c["spine"] = (18.0, -2.0 * math.sin(a), -4.0 * math.sin(a))
        c["head"] = (-20.0 + 2.0 * math.cos(2 * a), 0.0, 2.0 * math.sin(a))
        return c
    return NA.ProcClip("Walk", n, fn, loop=True, root_vel=(0, -WALK_SPEED, 0), notes="pasitos cortos encorvado, 0.8 m/s")


def bound_pose(a=0.0, k=0.0):
    """Atado: la espalda contra el poste (detrás), las manos atrás alrededor del poste, la cabeza gacha. 'k' forcejea."""
    return P(hips=(0.0, 0.05, -0.02), hips_rot=(-2.0, 0.0, 0.0), spine=(-2.0 + 4.0 * k, 3.0 * k * math.sin(a * 3.0), 0.0),
             head=(24.0 - 12.0 * k + 3.0 * math.sin(a), 0.0, 6.0 * math.sin(a * 0.5) + 10.0 * k * math.sin(a * 3.0)),
             breath=0.5 - 0.5 * math.cos(2 * a),
             hand_r=(-0.06, 0.20, 0.70 + 0.02 * k), hand_r_dir=(0.5, 0.3, -0.8), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.5, 0.0),
             hand_l=(0.06, 0.20, 0.70 + 0.02 * k), hand_l_dir=(-0.5, 0.3, -0.8), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.5, 0.0),
             clav_r=(0.0, 0.0, -8.0 * k), clav_l=(0.0, 0.0, 8.0 * k), fist_r=0.8, fist_l=0.8)


def bound():
    n = 90
    keys = []
    for f in range(0, n + 1, 6):
        a = 2.0 * math.pi * f / n
        # forcejea una vez por vuelta (cuadros 48-66) y se rinde
        k = max(0.0, math.sin(math.pi * (f - 48) / 18.0)) if 48 <= f <= 66 else 0.0
        keys.append(Key(f, bound_pose(a, k), "sine"))
    return T.TeamClip("Bound", n, keys, loop=True, feet={"r": [FR(0, dx=0.02)], "l": [FL(0, dx=-0.02)]},
                      notes="atado al poste: manos atrás, cabeza gacha, forcejea cada tanto")


def freed():
    n = 90
    B = bound_pose()
    RUB = P(hips=(0.0, 0.03, -0.03), hips_rot=(6.0, 0.0, 0.0), spine=(10.0, 0.0, 0.0), head=(10.0, 0.0, 0.0),
            hand_r=(-0.06, -0.20, 0.74), hand_r_dir=(0.6, -0.4, 0.0), hand_r_palm=(1.0, 0.0, 0.0), elbow_r=(-1.0, 0.0, -0.4),
            hand_l=(0.06, -0.22, 0.72), hand_l_dir=(-0.6, -0.4, 0.0), hand_l_palm=(-1.0, 0.0, 0.0), elbow_l=(1.0, 0.0, -0.4),
            fist_r=0.6, fist_l=0.2)
    UP = P(hips=(0.0, 0.02, -0.02), hips_rot=(0.0, 0.0, 0.0), spine=(0.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0),
           hand_r=(-0.18, -0.02, 0.62), hand_r_dir=(0.0, -0.2, -1.0), hand_r_palm=(1.0, 0.0, 0.0), elbow_r=(-1.0, 0.2, -0.2),
           hand_l=(0.18, -0.02, 0.62), hand_l_dir=(0.0, -0.2, -1.0), hand_l_palm=(-1.0, 0.0, 0.0), elbow_l=(1.0, 0.2, -0.2),
           fist_r=0.2, fist_l=0.2)
    BOW = dict(UP, hips=(0.0, 0.07, -0.05), hips_rot=(36.0, 0.0, 0.0), spine=(18.0, 0.0, 0.0), head=(8.0, 0.0, 0.0),
               hand_r=(-0.10, -0.16, 0.50), hand_l=(0.10, -0.16, 0.50))
    keys = [Key(0, B), Key(12, RUB, "inout"), Key(20, dict(RUB, hand_r=(-0.02, -0.22, 0.76), hand_l=(0.02, -0.20, 0.72)), "sine"),
            Key(28, RUB, "sine"), Key(40, UP, "inout"), Key(54, BOW, "inout"), Key(66, BOW, "sine"), Key(78, UP, "inout"), Key(n, P(), "sine")]
    feet = {"r": [FR(0, dx=0.02), FR(30, dx=0.02), FR(38, lift=0.03)], "l": [FL(0, dx=-0.02), FL(33, dx=-0.02), FL(41, lift=0.03)]}
    return T.TeamClip("Freed", n, keys, feet=feet, notes="libre: se frota las muñecas y le hace una reverencia a Kaito",
                      timing=dict(sheet=[0, 12, 28, 40, 54, 66, 78, 90]))
