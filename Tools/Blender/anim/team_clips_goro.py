"""Clips de Gorō, el Martillo de Kodoyama (Models/Minijefe.fbx), en el marco de autoría de team_rig (metros del juego,
frente -Y, izquierda +X). 3.4 m, piernas de 0.98 m, brazos de 1.04 m y un martillo de 3.7 m (la cabeza a 1.38 m de la
mano de arriba): el martillo ES el aviso, y cada golpe lo lleva a un lugar distinto de la silueta.

Lo que pedía la auditoría (ANIM-01/02) y cómo quedó:
  * Combo1 (martillazo en diagonal): el martillo ARRIBA a la derecha y atrás, el cuerpo torcido; baja cruzando al frente
    izquierdo. Combo2 (revés horizontal): el martillo atrás a la IZQUIERDA a la altura de la cadera; barre de izquierda a
    derecha. Combo3 (el de arriba): el martillo parado atrás de la cabeza con el pecho arqueado; cae derecho al frente.
    Contacto = activeStart en los tres (antes pegaban con el martillo todavía arriba).
  * Heavy (golpe sísmico, imparable): se agacha con el martillo atrás, SALTA (la pausa del juego cae en la cima) y el
    martillo pega en el piso al aterrizar: la onda sale con el impacto, no al despegar.
  * Spin: carga torcido con el martillo estirado a la derecha (el juego gira el modelo a 900°/s durante la fase activa);
    sale mareado y termina en la pose de StunSpin (el agotamiento que sigue).
  * StunSpin (mareado, agotado y ejecución), Parried y ParriedPerfect (el martillo rebota para arriba), Hit y HitHeavy, ExhaustedHit, Spotted (rugido: también el
    cambio de fase), Death (cae de rodillas sin soltar el martillo y se desploma), Idle, caminar y correr (sin
    'moonwalk': los pies clavados a la velocidad del transform). La presentación ('Intro') sigue siendo la del equipo.
"""
import math
import nindo_anim as NA
import team_rig as T

Key = NA.Key
RUN_SPEED, WALK_SPEED = 3.8, 2.0          # EnemyArchetypes.Goro(): runSpeed, walkSpeed
LOCOMOTION = (("Idle", 0.0), ("Walk", WALK_SPEED / RUN_SPEED), ("Run", 1.0))

# ------------------------------------------------------------------ guardia
# el martillo bajo adelante a la derecha, la cabeza casi en el piso (se arrastra): desde ahí cada aviso lo levanta a un
# lugar distinto. Las dos manos en el mango, la derecha arriba.
STANCE = dict(
    hips=(0.0, 0.02, -0.12), hips_rot=(6.0, 0.0, 10.0), spine=(8.0, 0.0, -6.0), head=(-8.0, 0.0, 0.0),
    knee_r=(-0.6, -1.0, 0.0), knee_l=(0.6, -1.0, 0.0),
    grip=(-0.62, -0.42, 1.25), haft=(0.18, -0.90, -0.40), face=(0.98, 0.2, 0.0), grip_l=0.0,
    hand_l=(0.66, -0.15, 1.15), hand_l_dir=(0.1, -0.3, -0.95), hand_l_palm=(-1.0, 0.0, 0.0), fist_l=0.8,
    elbow_r=(-1.0, 0.3, -0.6), elbow_l=(1.0, 0.4, -0.4), breath=0.0, travel=0.0,
)
R0, L0 = (-0.48, -0.18, -10.0), (0.50, 0.24, 20.0)


def P(**kw):
    d = dict(STANCE)
    d.update(kw)
    return d


def flat_face(haft, hint):
    """Cara del martillo perpendicular al mango y horizontal (la cabeza de canto: lo menos que baja respecto de su centro),
    del lado de 'hint'. Para las poses en que la cabeza descansa en el piso o pasa cerca."""
    f = (-haft[1], haft[0], 0.0)
    m = math.hypot(f[0], f[1]) or 1.0
    sg = 1.0 if f[0] * hint[0] + f[1] * hint[1] >= 0.0 else -1.0
    return (sg * f[0] / m, sg * f[1] / m, 0.0)


def P2(**kw):
    """Pose de golpe: las dos manos en el mango (en la guardia lo lleva con una sola)."""
    kw.setdefault("grip_l", 1.0)
    return P(**kw)


def FR(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    return T.FootKey(f, R0[0] + dx, R0[1] - dy, R0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


def FL(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    return T.FootKey(f, L0[0] + dx, L0[1] - dy, L0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


PLANTED = {"r": [FR(0)], "l": [FL(0)]}


# empujones del juego (Enemy): parry 0.4 m (perfecto 0.8; el parry no descuenta knockbackResist); los golpes de Kaito
# sí (0.9): 0.35-0.4 m de los livianos quedan en 0.04 m y 1.4-1.8 m de los pesados (HitHeavy) en 0.16 m
PARRY_BACK, PERFECT_BACK, HIT_BACK, HEAVY_BACK = 0.4, 0.8, 0.04, 0.16
knock_travel = T.knock_travel


def clips(ch):
    out = [idle()]
    out += locomotion(ch)
    out += [combo1(), combo2(), combo3(), heavy(), spin()]
    out += [stun_spin(), exhausted_hit(), parried(), parried_perfect(), hit(), hit_heavy(), spotted(), death()]
    return out


# ================================================================== quieto y locomoción
def idle():
    """2.7 s: respira hondo con los hombros, el peso pasa de un pie al otro y la cabeza del martillo se mece apenas."""
    n = 80
    keys = []
    for f in range(0, n + 1, 10):
        a = 2.0 * math.pi * f / n
        b = 4.0 * math.pi * f / n
        keys.append(Key(f, P(hips=(0.03 * math.sin(a), 0.02, -0.12 - 0.015 * (0.5 - 0.5 * math.cos(b))),
                             hips_rot=(6.0, -2.0 * math.sin(a), 10.0), spine=(8.0 - 2.5 * math.sin(b), 1.5 * math.sin(a), -6.0),
                             head=(-8.0 + 3.0 * math.sin(b + 0.7), 0.0, 8.0 * math.sin(a + 1.2)), breath=0.5 - 0.5 * math.cos(b),
                             grip=(-0.62 + 0.02 * math.sin(a), -0.42, 1.25 + 0.02 * math.sin(b)),
                             haft=(0.18 + 0.04 * math.sin(a), -0.90, -0.40)), "sine"))
    return T.TeamClip("Idle", n, keys, loop=True, feet=PLANTED, notes="respira; el martillo bajo adelante")


def locomotion(ch):
    out = []
    n = 24
    g = T.gait2(ch, n, WALK_SPEED, 0.58, {"r": (-0.44, -0.04, -10.0), "l": (0.44, 0.04, 14.0)}, lift=0.14, toe_off=20.0, heel=-10.0)

    def walk(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g(f))
        c["hips"] = (-0.05 * math.sin(a), 0.0, -0.14 - 0.03 * math.cos(2 * a))
        c["hips_rot"] = (8.0, 4.0 * math.sin(a), 10.0 + 6.0 * math.sin(a))
        c["spine"] = (8.0, -2.5 * math.sin(a), -6.0 - 4.0 * math.sin(a))
        c["grip"] = (-0.64, -0.38 + 0.05 * math.sin(a), 1.25 + 0.03 * math.cos(2 * a))
        c["hand_l"] = (0.66, -0.15 + 0.12 * math.sin(a), 1.15)
        return c
    out.append(NA.ProcClip("Walk", n, walk, loop=True, root_vel=(0, -WALK_SPEED, 0), notes="caminata pesada a 2 m/s"))

    # corre con el martillo adelante a la derecha, la cabeza un poco más alta que caminando (antes iba atrás como una cola:
    # el blend de locomoción mezcla cada hueso por separado y a media mezcla la cabeza del martillo cruzaba el piso)
    n = 20
    g2 = T.gait2(ch, n, RUN_SPEED, 0.38, {"r": (-0.40, -0.06, -6.0), "l": (0.40, -0.06, 6.0)}, lift=0.22, toe_off=30.0, heel=-12.0)

    def run(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g2(f))
        c["hips"] = (-0.04 * math.sin(a), 0.0, -0.16 - 0.05 * math.cos(2 * a - 0.9))
        c["hips_rot"] = (14.0, 3.0 * math.sin(a), 8.0 * math.sin(a))
        c["spine"] = (10.0, -2.0 * math.sin(a), -6.0 * math.sin(a))
        c["head"] = (-18.0, 0.0, 3.0 * math.sin(a))
        c["grip"] = (-0.70, -0.30 + 0.06 * math.sin(a), 1.30 + 0.03 * math.cos(2 * a))
        c["haft"] = (0.15, -0.93, -0.31)
        c["face"] = (0.98, 0.2, 0.0)
        c["grip_l"] = 0.0
        c["hand_l"] = (0.62, -0.10 + 0.30 * math.sin(a), 1.35 - 0.05 * math.cos(a))
        c["hand_l_dir"] = (0.1, -0.5, -0.85)
        c["fist_l"] = 0.9
        c["elbow_r"] = (-1.0, 0.2, -0.5)
        return c
    out.append(NA.ProcClip("Run", n, run, loop=True, root_vel=(0, -RUN_SPEED, 0), notes="corre a 3.8 m/s con el martillo atrás"))
    return out


# ================================================================== golpes
def combo1():
    """Martillazo en diagonal (abre el combo). Aviso: el martillo arriba a la DERECHA y atrás (desde la cámara del juego,
    un brazo de 3 m que sale por arriba a la derecha del cuerpo), torcido 35° y el peso atrás. Baja cruzando al frente
    con un paso largo; la cabeza del martillo queda en el piso adelante a la izquierda (castigo)."""
    n, apex, contact = 36, 21, 24
    lunge, windup = 1.2, 0.85
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P2(hips=(0.05, 0.12, -0.16), hips_rot=(0.0, 0.0, -34.0), spine=(-6.0, 0.0, -12.0), head=(-6.0, 0.0, 30.0),
             grip=(-0.78, 0.18, 2.12), haft=(-0.45, 0.62, 0.64), face=(0.6, -0.6, 0.3), elbow_r=(-1.0, 0.0, -0.3), elbow_l=(0.6, -0.8, -0.2))
    HOLD = dict(TELL, hips=(0.05, 0.13, -0.18), grip=(-0.80, 0.20, 2.14), haft=(-0.46, 0.64, 0.62))
    SMEAR = dict(HOLD, hips=(0.0, 0.0, -0.20), hips_rot=(10.0, 0.0, -8.0), spine=(4.0, 0.0, -4.0), head=(-12.0, 0.0, 10.0),
                 grip=(-0.60, -0.45, 2.00), haft=(-0.30, -0.55, 0.78), face=(0.3, -0.8, -0.5))
    CONTACT = P2(hips=(0.0, -0.16, -0.30), hips_rot=(20.0, 0.0, 22.0), spine=(14.0, 0.0, 10.0), head=(-22.0, 0.0, -10.0),
                grip=(-0.42, -0.84, 1.46), haft=(0.28, -0.88, -0.38), face=(0.0, -0.4, -0.92), slide_l=0.45, elbow_r=(-1.0, 0.3, -0.3), elbow_l=(1.0, 0.3, -0.4))
    FOLLOW = dict(CONTACT, hips=(0.0, -0.17, -0.34), hips_rot=(22.0, 0.0, 30.0), grip=(-0.30, -0.80, 1.38), haft=(0.40, -0.86, -0.30),
                  face=(0.1, -0.3, -0.95))
    PUNISH = dict(FOLLOW, hips=(0.0, -0.15, -0.32), spine=(16.0, 0.0, 12.0), head=(-20.0, 0.0, -14.0))
    keys = [Key(0, P()), Key(12, TELL, "inout"), Key(apex, HOLD, "sine"), Key(22, SMEAR, "in"), Key(contact, CONTACT, "lin"),
            Key(26, FOLLOW, "out"), Key(31, PUNISH, "out"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(apex), FR(27, lunge, pitch=-10.0), FR(29, lunge)],
            "l": [FL(0), FL(12), FL(apex, pitch=16.0), FL(32, lunge, ease="out")]}
    return T.TeamClip("Combo1", n, keys, travel=tr, feet=feet, notes="martillazo en diagonal; aviso: martillo arriba a la derecha",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 28], hold=[12, apex], lunge=lunge,
                                  windup=windup, state="Combo1", reach=2.4))


def combo2():
    """Revés horizontal (encadenado). Aviso: el martillo atrás a la IZQUIERDA a la altura de la cadera, el cuerpo
    torcido a la izquierda (desde arriba: la cabeza del martillo sale del contorno por el otro lado que en Combo1).
    Barre de izquierda a derecha a la altura del pecho de Kaito."""
    n, apex, contact = 36, 18, 21
    lunge, windup = 1.2, 0.5
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P2(hips=(-0.04, 0.10, -0.20), hips_rot=(4.0, 0.0, 36.0), spine=(4.0, 0.0, 14.0), head=(-8.0, 0.0, -32.0),
             grip=(0.50, 0.28, 1.50), haft=(0.72, 0.62, 0.20), face=(-0.62, 0.72, 0.0), elbow_r=(-0.4, -0.8, -0.4), elbow_l=(1.0, 0.4, -0.3))
    HOLD = dict(TELL, hips=(-0.04, 0.11, -0.21), grip=(0.52, 0.30, 1.50))
    SMEAR = dict(HOLD, hips_rot=(6.0, 0.0, 14.0), spine=(6.0, 0.0, 6.0), head=(-10.0, 0.0, -10.0),
                 grip=(0.30, -0.40, 1.48), haft=(0.55, -0.82, 0.10), face=(-0.82, -0.55, 0.0))
    CONTACT = P2(hips=(0.0, -0.14, -0.24), hips_rot=(10.0, 0.0, -14.0), spine=(10.0, 0.0, -12.0), head=(-12.0, 0.0, 10.0),
                grip=(-0.36, -0.82, 1.42), haft=(0.02, -1.0, 0.05), face=(-1.0, 0.0, 0.0), slide_l=0.45, elbow_r=(-1.0, 0.0, -0.4), elbow_l=(0.8, 0.5, -0.4))
    # (la cabeza es un cilindro: la cara del seguimiento va del mismo lado que la de la guardia, así la vuelta no la
    # hace girar media vuelta por debajo del mango)
    FOLLOW = dict(CONTACT, hips_rot=(10.0, 0.0, -30.0), spine=(10.0, 0.0, -20.0), grip=(-0.62, -0.50, 1.42), haft=(-0.92, -0.38, 0.05),
                  face=(0.38, -0.92, 0.0))
    # la cara del martillo vuelve a la de la guardia por el plano horizontal (de frente a frente cruzaba vertical por el piso)
    PUNISH = dict(FOLLOW, hips=(0.0, -0.12, -0.22), grip=(-0.70, -0.40, 1.34), haft=(-0.90, -0.30, -0.24),
                  face=flat_face((-0.90, -0.30, -0.24), (1.0, 0.0, 0.0)))
    keys = [Key(0, P()), Key(10, TELL, "inout"), Key(apex, HOLD, "sine"), Key(19, SMEAR, "in"), Key(contact, CONTACT, "lin"),
            Key(24, FOLLOW, "out"), Key(29, PUNISH, "out"),
            # de vuelta a la guardia el mango barre por delante: la cara se mantiene de canto (si no, la cabeza se hunde)
            Key(33, P(grip=(-0.66, -0.42, 1.30), haft=(-0.45, -0.75, -0.35), face=flat_face((-0.45, -0.75, -0.35), (1.0, 0.0, 0.0))), "sine"),
            Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(apex), FR(24, lunge, pitch=-10.0), FR(26, lunge)],
            "l": [FL(0), FL(10), FL(apex, pitch=14.0), FL(29, lunge, ease="out")]}
    return T.TeamClip("Combo2", n, keys, travel=tr, feet=feet, notes="revés horizontal; aviso: martillo atrás a la izquierda",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 24], hold=[10, apex], lunge=lunge,
                                  windup=windup, state="Combo2", reach=2.4))


def combo3():
    """El de arriba (cierra el combo). Aviso: el martillo parado atrás de la cabeza con las dos manos arriba y el pecho
    arqueado (desde arriba: la silueta más alta, la cabeza del martillo por encima de la suya). Cae derecho al frente
    con todo el peso; queda agachado con el martillo hundido."""
    n, apex, contact = 30, 16, 19
    lunge, windup = 1.0, 0.5
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P2(hips=(0.0, 0.14, -0.10), hips_rot=(-8.0, 0.0, 4.0), spine=(-12.0, 0.0, -2.0), head=(6.0, 0.0, 0.0),
             grip=(-0.12, 0.22, 2.62), haft=(0.05, 0.78, 0.62), face=(0.0, 0.62, -0.78), elbow_r=(-1.0, -0.2, 0.3), elbow_l=(1.0, -0.2, 0.3))
    HOLD = dict(TELL, hips=(0.0, 0.15, -0.11), grip=(-0.12, 0.25, 2.64), haft=(0.05, 0.80, 0.60))
    SMEAR = dict(HOLD, hips=(0.0, 0.0, -0.18), hips_rot=(8.0, 0.0, 4.0), spine=(4.0, 0.0, 0.0), head=(-8.0, 0.0, 0.0),
                 grip=(-0.10, -0.50, 2.40), haft=(0.0, -0.40, 0.92), face=(0.0, -0.92, -0.40))
    CONTACT = P2(hips=(0.0, -0.18, -0.34), hips_rot=(26.0, 0.0, 6.0), spine=(16.0, 0.0, 0.0), head=(-26.0, 0.0, 0.0),
                grip=(-0.36, -0.88, 1.44), haft=(0.24, -0.88, -0.40), face=(0.0, -0.40, -0.92), slide_l=0.45, elbow_r=(-1.0, 0.3, -0.3), elbow_l=(1.0, 0.3, -0.3))
    FOLLOW = dict(CONTACT, hips=(0.0, -0.18, -0.40), grip=(-0.34, -0.84, 1.38), haft=(0.24, -0.93, -0.28))
    keys = [Key(0, P()), Key(8, TELL, "inout"), Key(apex, HOLD, "sine"), Key(17, SMEAR, "in"), Key(contact, CONTACT, "lin"),
            Key(21, FOLLOW, "out"), Key(25, FOLLOW, "sine"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(apex), FR(22, lunge, pitch=-10.0), FR(24, lunge)],
            "l": [FL(0), FL(8), FL(apex, pitch=14.0), FL(26, lunge, ease="out")]}
    return T.TeamClip("Combo3", n, keys, travel=tr, feet=feet, notes="martillazo de arriba; aviso: martillo atrás de la cabeza",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 22], hold=[8, apex], lunge=lunge,
                                  windup=windup, state="Combo3", reach=2.4))


def heavy():
    """Golpe sísmico (imparable, onda de 4.6-6 m). Se agacha con el martillo atrás de la cabeza (aviso rojo) y salta:
    la cima del salto es el apex (la pausa del juego, si la hay, lo deja suspendido arriba). En la suelta cae con el
    martillo por delante y el contacto es el aterrizaje: la cabeza del martillo y los dos pies en el piso a la vez."""
    n, apex, contact = 60, 32, 40
    lunge, windup = 0.5, 1.1
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    CROUCH = P2(hips=(0.0, 0.10, -0.40), hips_rot=(14.0, 0.0, 0.0), spine=(-4.0, 0.0, 0.0), head=(-14.0, 0.0, 0.0),
               knee_r=(-0.8, -0.8, 0.0), knee_l=(0.8, -0.8, 0.0),
               grip=(-0.10, 0.20, 2.45), haft=(0.05, 0.85, 0.52), face=(0.0, 0.52, -0.85), elbow_r=(-1.0, -0.2, 0.3), elbow_l=(1.0, -0.2, 0.3))
    DEEP = dict(CROUCH, hips=(0.0, 0.11, -0.46))
    TAKEOFF = dict(CROUCH, hips=(0.0, 0.04, 0.14), hips_rot=(4.0, 0.0, 0.0), spine=(-10.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0),
                   grip=(-0.10, 0.25, 2.80), haft=(0.05, 0.92, 0.38))
    TOP = dict(TAKEOFF, hips=(0.0, 0.0, 0.50), knee_r=(-0.6, -1.0, 0.0), knee_l=(0.6, -1.0, 0.0),
               grip=(-0.10, 0.20, 2.90), haft=(0.05, 0.98, 0.20), spine=(-14.0, 0.0, 0.0))
    FALL = dict(TOP, hips=(0.0, -0.06, 0.30), hips_rot=(14.0, 0.0, 0.0), spine=(6.0, 0.0, 0.0), head=(-14.0, 0.0, 0.0),
                grip=(-0.22, -0.60, 2.50), haft=(0.10, -0.30, 0.95), face=(0.0, -0.95, -0.30), slide_l=0.3)
    LAND = P2(hips=(0.0, -0.14, -0.50), hips_rot=(28.0, 0.0, 0.0), spine=(16.0, 0.0, 0.0), head=(-28.0, 0.0, 0.0),
             knee_r=(-0.8, -0.8, 0.0), knee_l=(0.8, -0.8, 0.0),
             grip=(-0.38, -0.92, 1.36), haft=(0.26, -0.92, -0.28), face=(0.0, -0.28, -0.96), slide_l=0.45, elbow_r=(-1.0, 0.3, -0.3), elbow_l=(1.0, 0.3, -0.3))
    keys = [Key(0, P()), Key(12, CROUCH, "inout"), Key(22, DEEP, "sine"), Key(26, TAKEOFF, "out"), Key(apex, TOP, "out"),
            Key(36, FALL, "in"), Key(contact, LAND, "expo_in"), Key(43, dict(LAND, hips=(0.0, -0.13, -0.46)), "out"),
            Key(50, LAND, "sine"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(22), FR(26, pitch=24.0), FR(apex, 0.25, z=0.40, ease="out"), FR(contact, lunge, ease="in"), FR(n - 6, lunge)],
            "l": [FL(0), FL(22), FL(26, pitch=24.0), FL(apex, 0.25, z=0.40, ease="out"), FL(contact, lunge, ease="in"), FL(n - 6, lunge)]}
    return T.TeamClip("Heavy", n, keys, travel=tr, feet=feet, notes="golpe sísmico: salta y pega al aterrizar",
                      timing=dict(kind="unblockable", apex=apex, contact=contact, active=[contact, 42], hold=[12, 22], lunge=lunge,
                                  windup=windup, state="Heavy", reach=2.2))


def stun_pose(a=0.0):
    """Mareado: la cabeza del martillo apoyada en el piso a la derecha (de canto, sin hundirse), el cuerpo en círculos y
    la cabeza colgando."""
    return P(hips=(0.04 * math.sin(a), 0.06 + 0.03 * math.cos(a), -0.22), hips_rot=(14.0 + 4.0 * math.cos(a), 6.0 * math.sin(a), 14.0),
             spine=(14.0 + 4.0 * math.sin(a), -5.0 * math.cos(a), -4.0), head=(18.0 + 8.0 * math.sin(a + 1.0), 12.0 * math.cos(a), 10.0 * math.sin(a)),
             grip=(-0.62, -0.50, 1.34 + 0.03 * math.sin(2 * a)), haft=(-0.50, -0.62, -0.60), face=(-0.62, 0.78, 0.0), grip_l=0.0,
             hand_l=(0.70, -0.30, 1.10), hand_l_dir=(0.1, -0.3, -0.95), hand_l_palm=(-1.0, 0.0, 0.0), fist_l=0.3, elbow_l=(1.0, 0.3, 0.0))


def spin():
    """Torbellino (imparable). Carga torcido a la derecha con el martillo estirado atrás a la derecha (la cabeza a 2 m
    del cuerpo). En la fase activa el juego gira el modelo a 900°/s: el martillo va estirado horizontal hacia afuera y
    el cuerpo se inclina al otro lado como contrapeso. Al terminar sale mareado y cae en la pose de StunSpin."""
    n, apex, contact, end = 66, 16, 19, 56
    TELL = P2(hips=(0.06, 0.10, -0.20), hips_rot=(4.0, 0.0, -40.0), spine=(0.0, 0.0, -16.0), head=(-8.0, 0.0, 40.0),
             grip=(-0.92, 0.32, 1.55), haft=(-0.85, 0.50, 0.12), face=(0.5, 0.85, 0.0), elbow_r=(-1.0, 0.0, -0.4), elbow_l=(0.4, -0.9, -0.3))
    HOLD = dict(TELL, hips=(0.06, 0.11, -0.22), grip=(-0.94, 0.34, 1.55))
    SPINP = P2(hips=(0.04, 0.0, -0.20), hips_rot=(4.0, 10.0, 0.0), spine=(0.0, 8.0, 0.0), head=(-10.0, -6.0, 0.0),
              grip=(-1.05, -0.10, 1.70), haft=(-0.99, -0.10, 0.06), face=(0.10, -0.99, 0.0), elbow_r=(-1.0, 0.0, -0.3), elbow_l=(0.3, -0.9, -0.3))
    # de la guardia (adelante-abajo) al aviso (atrás a la derecha) el martillo pasa por el costado derecho y arriba: sin
    # esta clave el giro más corto lo llevaba por abajo y la cabeza cruzaba el piso
    SIDE = dict(P(), grip=(-0.80, -0.05, 1.45), haft=(-0.95, -0.20, 0.25), face=flat_face((-0.95, -0.20, 0.25), (0.0, 1.0, 0.0)),
                hips_rot=(5.0, 0.0, -14.0), head=(-8.0, 0.0, 16.0))
    keys = [Key(0, P()), Key(5, SIDE, "in"), Key(10, TELL, "out"), Key(apex, HOLD, "sine"), Key(contact, SPINP, "in")]
    f = contact + 4
    while f <= end:
        a = 2.0 * math.pi * (f - contact) / 12.0
        keys.append(Key(f, dict(SPINP, hips=(0.04, 0.0, -0.20 - 0.03 * math.cos(2 * a)), grip=(-1.05, -0.10, 1.70 + 0.05 * math.sin(a))), "sine"))
        f += 4
    S0 = stun_pose()
    keys += [Key(60, dict(S0, hips_rot=(18.0, -10.0, 10.0), head=(24.0, -14.0, 10.0)), "out"), Key(n, S0, "sine")]
    # pisa en el lugar mientras gira (el modelo entero rota: los pies no pueden quedar clavados, 'slide_ok')
    fr_, fl_ = [FR(0), FR(10, dx=0.06, yaw=-30.0), FR(contact, dx=0.06, yaw=-30.0)], [FL(0), FL(10, -0.10), FL(contact, -0.10)]
    f, up = contact + 3, True
    while f < end:
        fr_.append(FR(f, dx=0.06, yaw=-30.0, z=0.10 if up else 0.0, lift=0.0))
        fl_.append(FL(f, -0.10, z=0.0 if up else 0.10, lift=0.0))
        f += 3
        up = not up
    fr_ += [FR(end, dx=0.06, yaw=-30.0), FR(62, -0.10, dx=0.10, yaw=-20.0)]
    fl_ += [FL(end, -0.10), FL(60, 0.05, dx=-0.08)]
    return T.TeamClip("Spin", n, keys, feet={"r": fr_, "l": fl_}, tremble=0.0, notes="torbellino: carga torcido, gira, sale mareado",
                      timing=dict(kind="unblockable", apex=apex, contact=contact, active=[contact, end], hold=[10, apex], lunge=0.0,
                                  windup=0.95, state="Spin", slide_ok=40.0, reach=2.6))


STUN_FEET = {"r": [FR(0, -0.10, dx=0.10, yaw=-20.0)], "l": [FL(0, 0.05, dx=-0.08)]}


def stun_spin():
    """Mareado/agotado (loop de 2 s: el agotamiento después del torbellino o de quebrarle la postura, y la pose de la
    ejecución): apoya la cabeza del martillo en el piso, el cuerpo da vueltas y la cabeza le cuelga."""
    n = 60
    keys = [Key(f, stun_pose(2.0 * math.pi * f / n), "sine") for f in range(0, n + 1, 10)]
    return T.TeamClip("StunSpin", n, keys, loop=True, feet=STUN_FEET, notes="mareado: el cuerpo en círculos")


def parried_clip(name, n, settle, recoil, back, knock, hold, stumble, feet, notes):
    """Parry recibido: Enemy.OnParried corta el clip a los parriedRecoil s (0.32; x1.5 el perfecto) y arranca el paso
    siguiente con un cruce de 0.08 s: en el cuadro del corte tiene que estar en la guardia de los golpes ('chain')."""
    keys = [Key(0, P()), Key(2, knock, "snap"), Key(hold, dict(knock, grip=(knock["grip"][0], knock["grip"][1] + 0.04, knock["grip"][2] + 0.06)), "out"),
            Key(hold + 2, stumble, "inout"), Key(settle, P(), "sine"), Key(n, P(), "sine")]
    return T.TeamClip(name, n, keys, travel=knock_travel(n, back), feet=feet, notes=notes,
                      timing=dict(sheet=[2, hold, hold + 2, settle], chain=[(round(recoil * T.FPS, 1), "Combo1", 0, 0.12)]))


def parried():
    """El martillo rebota (parry común: 0.32 s, 0.4 m atrás): sale despedido para arriba con los dos brazos y el cuerpo
    se echa atrás con un paso pesado; cae de vuelta adelante por su peso y en el corte (f9.6) está en la guardia."""
    b = PARRY_BACK
    KNOCK = P2(hips=(0.0, 0.14, -0.14), hips_rot=(-12.0, 0.0, 6.0), spine=(-14.0, 0.0, 4.0), head=(12.0, 0.0, 6.0),
               grip=(-0.46, 0.06, 2.20), haft=(-0.20, 0.10, 0.97), face=(0.0, 0.97, -0.1), elbow_r=(-1.0, 0.0, 0.2), elbow_l=(1.0, 0.0, 0.2))
    STUMBLE = dict(KNOCK, hips=(0.0, 0.08, -0.16), hips_rot=(0.0, 0.0, 8.0), spine=(-2.0, 0.0, -2.0), head=(0.0, 0.0, 2.0),
                   grip=(-0.58, -0.30, 1.70), haft=(0.05, -0.70, 0.71), face=(0.9, 0.3, 0.3), grip_l=0.5)
    feet = {"l": [FL(0), FL(5, -b, ease="out", lift=0.08)],
            "r": [FR(0), FR(1), FR(7, -b, pitch=-8.0, ease="out", lift=0.08), FR(8, -b)]}
    return parried_clip("Parried", 10, 9, 0.32, b, KNOCK, 4, STUMBLE, feet,
                        "parry recibido: el martillo rebota arriba y cae adelante; en guardia al corte")


def parried_perfect():
    """Parry perfecto (0.48 s, 0.8 m: Enemy lo elige si el controller lo tiene): el martillo se va para atrás por encima
    de la cabeza y lo arrastra; dos pasos pesados atrás con los brazos estirados arriba y en el corte (f14.4) vuelve a
    la guardia."""
    b = PERFECT_BACK
    KNOCK = P2(hips=(0.0, 0.16, -0.12), hips_rot=(-16.0, 0.0, 6.0), spine=(-18.0, 0.0, 4.0), head=(16.0, 0.0, 6.0),
               grip=(-0.40, 0.30, 2.40), haft=(-0.20, 0.55, 0.81), face=(0.0, 0.81, -0.55), elbow_r=(-1.0, 0.0, 0.2), elbow_l=(1.0, 0.0, 0.2))
    STUMBLE = dict(KNOCK, hips=(0.0, 0.12, -0.20), hips_rot=(-4.0, 0.0, 8.0), spine=(-6.0, 0.0, 0.0), head=(4.0, 0.0, 4.0),
                   grip=(-0.50, 0.0, 2.10), haft=(-0.30, 0.10, 0.95), face=(0.3, 0.95, 0.0))
    feet = {"l": [FL(0), FL(6, -b + 0.15, ease="out", lift=0.10), FL(8, -b + 0.15), FL(13, -b, lift=0.05)],
            "r": [FR(0), FR(1), FR(9, -b, pitch=-8.0, ease="out", lift=0.10), FR(11, -b)]}
    return parried_clip("ParriedPerfect", 15, 14, 0.48, b, KNOCK, 6, STUMBLE, feet,
                        "parry perfecto: el martillo se va atrás por encima de la cabeza, dos pasos atrás; en guardia al corte")


def hit():
    """Golpe recibido cuando no tiene la armadura del golpe (0.5 s): un sacudón del pecho y la cabeza, sin soltar el
    martillo; los pies quedan clavados en el mundo con los 4 cm del empujón (aguanta)."""
    n = 15
    PEAK = P(hips=(0.0, 0.06, -0.14), hips_rot=(-4.0, 0.0, 14.0), spine=(-10.0, 0.0, 0.0), head=(14.0, 0.0, 8.0),
             grip=(-0.52, -0.38, 1.40))
    keys = [Key(0, P()), Key(2, PEAK, "snap"), Key(7, dict(P(), hips=(0.0, 0.0, -0.15)), "inout"), Key(n, P(), "sine")]
    b = HIT_BACK
    feet = {"r": [FR(0), FR(3), FR(9, -b, ease="out", lift=0.05)], "l": [FL(0), FL(5), FL(11, -b, ease="out", lift=0.05)]}
    return T.TeamClip("Hit", n, keys, travel=knock_travel(n, b), feet=feet, notes="sacudón; se acomoda los 4 cm del empujón")


def hit_heavy():
    """Golpe pesado recibido (corte final y habilidades de Kaito: 0.16 m después de su resistencia; Enemy lo elige
    cuando el empujón pasa de 1 m): el sacudón más grande y un paso pesado atrás del pie derecho."""
    n = 15
    b = HEAVY_BACK
    PEAK = P(hips=(0.0, 0.10, -0.12), hips_rot=(-8.0, 0.0, 18.0), spine=(-16.0, 0.0, 2.0), head=(20.0, 0.0, 10.0),
             grip=(-0.56, -0.30, 1.52), hand_l=(0.76, -0.05, 1.30))
    keys = [Key(0, P()), Key(2, PEAK, "snap"), Key(8, dict(P(), hips=(0.0, 0.02, -0.17)), "inout"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(2), FR(8, -b, ease="out", lift=0.06)], "l": [FL(0), FL(6), FL(12, -b, ease="out", lift=0.05)]}
    return T.TeamClip("HitHeavy", n, keys, travel=knock_travel(n, b), feet=feet, notes="golpe pesado: sacudón y un paso atrás")


def exhausted_hit():
    """Golpe recibido estando mareado (Enemy lo usa si existe y al terminar vuelve al loop de StunSpin): se tambalea con
    la cabeza que se va para atrás sin despegar el martillo del piso; empieza y termina en el cuadro 0 de StunSpin (con
    Hit se paraba en plena ventana de daño)."""
    n = 12
    S = stun_pose()
    PEAK = dict(S, hips=(0.0, 0.12, -0.20), hips_rot=(4.0, -6.0, 18.0), spine=(2.0, 6.0, -2.0), head=(34.0, -10.0, 14.0))
    keys = [Key(0, S), Key(2, PEAK, "snap"), Key(6, dict(S, hips=(0.03, 0.04, -0.24), head=(10.0, 8.0, 4.0)), "inout"), Key(n, S, "sine")]
    b = HIT_BACK
    feet = {k: [v[0], T.FootKey(4, v[0].x, v[0].y, v[0].yaw), T.FootKey(10, v[0].x, v[0].y + b, v[0].yaw, 0.0, 0.0, 0.0, "out", 0.05)]
            for k, v in STUN_FEET.items()}
    return T.TeamClip("ExhaustedHit", n, keys, travel=knock_travel(n, b), feet=feet,
                      notes="mareado: se tambalea con el golpe; vuelve al cuadro 0 de StunSpin",
                      timing=dict(chain=[(n, "StunSpin", 0, 0.02)]))


def spotted():
    """Rugido (1.4 s): la alerta y el cambio de fase (Boss.phaseAnim). Junta aire agachado y ruge con el pecho afuera,
    los brazos abiertos y el martillo levantado con una mano (desde arriba: la silueta más ancha)."""
    n = 42
    IN = P(hips=(0.0, 0.06, -0.24), hips_rot=(16.0, 0.0, 6.0), spine=(14.0, 0.0, 0.0), head=(-20.0, 0.0, 0.0))
    ROAR = P(hips=(0.0, 0.04, -0.10), hips_rot=(-6.0, 0.0, 0.0), spine=(-16.0, 0.0, 0.0), head=(18.0, 0.0, 0.0),
             grip=(-1.05, -0.10, 2.55), haft=(-0.30, 0.10, 0.95), face=(0.0, -1.0, 0.1), grip_l=0.0, elbow_r=(-1.0, 0.0, -0.2),
             hand_l=(1.10, -0.20, 2.10), hand_l_dir=(0.6, -0.1, 0.8), hand_l_palm=(0.0, -1.0, 0.0), fist_l=1.0, elbow_l=(1.0, 0.0, -0.4))
    keys = [Key(0, P()), Key(8, IN, "inout"), Key(13, ROAR, "out")]
    for i, f in enumerate(range(16, 33, 2)):
        s = 1 if i % 2 else -1
        keys.append(Key(f, dict(ROAR, spine=(-16.0, 1.2 * s, 0.0), head=(18.0, 0.0, 2.0 * s)), "sine"))
    keys += [Key(36, dict(ROAR, hips=(0.0, 0.03, -0.12)), "sine"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(10), FR(14, dx=-0.08, lift=0.06), FR(34, dx=-0.08), FR(n, lift=0.06)],
            "l": [FL(0), FL(10), FL(14, dx=0.08, lift=0.06), FL(32, dx=0.08), FL(n - 2, lift=0.06)]}
    return T.TeamClip("Spotted", n, keys, feet=feet, tremble=0.0, notes="rugido: pecho afuera, brazos abiertos")


def death():
    """Muerte (2 s): el golpe lo echa atrás, la cabeza del martillo cae al piso sin que la suelte, se le doblan las
    rodillas y queda arrodillado con la cabeza gacha; después se desploma hacia adelante sobre el martillo."""
    n = 60
    slide = [-0.8 * math.sin(min(1.0, (f / T.FPS) * 1.8) * math.pi * 0.5) for f in range(n + 1)]
    REC = P(hips=(0.0, 0.14, -0.10), hips_rot=(-12.0, 0.0, 8.0), spine=(-14.0, 0.0, 0.0), head=(18.0, 0.0, 6.0),
            grip=(-0.62, -0.30, 1.56), haft=(-0.45, -0.55, -0.70), face=flat_face((-0.45, -0.55, -0.70), (1.0, 0.0, 0.0)))
    KNEEL = P(hips=(0.0, 0.16, -0.58), hips_rot=(-2.0, 0.0, 8.0), spine=(10.0, 0.0, 0.0), head=(24.0, 0.0, 0.0),
              knee_r=(-0.3, -1.0, -0.3), knee_l=(0.3, -1.0, -0.3),
              grip=(-0.72, -0.40, 1.46), haft=(-0.45, -0.60, -0.66), face=flat_face((-0.45, -0.60, -0.66), (1.0, 0.0, 0.0)), grip_l=0.0,
              hand_l=(0.50, -0.30, 0.95), hand_l_dir=(0.0, -0.3, -0.95), hand_l_palm=(-1.0, 0.0, 0.0), fist_l=0.2)
    BOW = dict(KNEEL, spine=(26.0, 0.0, 0.0), head=(30.0, 0.0, 0.0), hips=(0.0, 0.16, -0.55))
    DOWN = dict(BOW, hips=(0.0, -0.10, -0.48), hips_rot=(62.0, 0.0, 10.0), spine=(18.0, 0.0, 0.0), head=(-20.0, 0.0, 20.0),
                grip=(-0.80, -0.70, 0.62), haft=(-0.55, -0.83, 0.0), face=flat_face((-0.55, -0.83, 0.0), (1.0, 0.0, 0.0)), hand_l=(0.55, -0.80, 0.40), hand_l_dir=(0.0, -0.8, -0.3))
    keys = [Key(0, P()), Key(4, REC, "snap"), Key(12, dict(REC, hips=(0.0, 0.16, -0.18)), "out"), Key(24, KNEEL, "in2"),
            Key(27, dict(KNEEL, hips=(0.0, 0.16, -0.55)), "out"), Key(32, KNEEL, "sine"), Key(44, BOW, "sine"),
            Key(50, dict(BOW, hips=(0.0, 0.04, -0.46), hips_rot=(30.0, 0.0, 9.0), spine=(22.0, 0.0, 0.0)), "in"), Key(54, DOWN, "out"), Key(57, dict(DOWN, hips=(0.0, -0.10, -0.45)), "out"), Key(n, DOWN, "sine")]
    # el empujón lo lleva 0.8 m atrás: los pies retroceden con él y quedan de punta para las rodillas apoyadas
    feet = {"r": [FR(0), FR(3), FR(11, -0.70, ease="out"), FR(16, -0.70), FR(24, -1.60, yaw=0.0, pitch=60.0)],
            "l": [FL(0), FL(5, pitch=10.0), FL(14, -0.75, ease="out"), FL(18, -0.75), FL(25, -1.30, yaw=0.0, pitch=60.0)]}
    return T.TeamClip("Death", n, keys, travel=slide, feet=feet, notes="muerte: de rodillas sin soltar el martillo y se desploma",
                      timing=dict(sheet=[4, 12, 24, 32, 44, 54, 60], slide_ok=6.0))
