"""Clips del ninja común (Models/Ninja/Ninja 1.fbx) en el marco de autoría de team_rig (metros del juego,
frente -Y, izquierda +X). Katana en la mano derecha. 1.7 m de alto con cabeza grande: piernas de 0.54 m y
brazos de 0.46 m, la katana (0.97 m de la mano a la punta) es lo más largo de la silueta y es lo que avisa.

Gramática de aviso (ANIM-02): cada golpe tiene una pose de aviso que rompe la silueta vista desde arriba
(la hoja AFUERA del contorno del cuerpo), una pausa que se mueve, 2 cuadros de golpe en un arco limpio,
seguimiento y recuperación. Los cuatro golpes tienen avisos distintos para que se aprendan:
  Attack1  la hoja horizontal atrás a la DERECHA, la mano libre apunta a Kaito  -> tajo horizontal con salto corto
  Attack2  la hoja baja atrás a la IZQUIERDA, agachado                          -> tajo diagonal subiendo
  Attack3  agazapado con las dos manos arriba y la hoja atrás de la cabeza      -> salta y parte de arriba
  Thrust   el más bajo, la hoja recogida en la cadera derecha por fuera del cuerpo -> se lanza volando 3 m
Todos empiezan y terminan en la guardia (STANCE): los pasos de un combo encadenan sin saltos con el cruce de
0.08 s de Enemy.BeginStep. 'apex' y 'contact' son los de EnemyArchetypes.Ninja() (el builder los compara).

Pies: van en el piso del MUNDO (team_rig.FootKey) y el avance del golpe ('lunge' de AttackDef, que el juego aplica
al transform) se descuenta en el clip, así un pie apoyado no se mueve aunque el cuerpo avance. Como la embestida
del juego arranca en la suelta, los golpes con avance despegan los dos pies en la suelta (un salto corto de ninja)
y aterrizan cuando el transform terminó de avanzar: ningún pie se arrastra por el piso.
"""
import math
import nindo_anim as NA
import team_rig as T

Key = NA.Key
RUN_SPEED, WALK_SPEED = 5.0, 2.0          # EnemyArchetypes.Ninja(): runSpeed, walkSpeed
# blend tree de locomoción: Speed = velocidad / runSpeed
LOCOMOTION = (("Idle", 0.0), ("Walk", WALK_SPEED / RUN_SPEED), ("Run", 1.0))

# ------------------------------------------------------------------ guardia (pose base)
# pie derecho adelante, cadera girada para que el lado de la espada lidere, la hoja baja apuntando a Kaito
# (adentro de la silueta: así cada aviso se lee como un cambio)
STANCE = dict(
    hips=(0.0, 0.03, -0.075), hips_rot=(4.0, 0.0, 18.0), spine=(6.0, 0.0, -6.0), chest=(4.0, 0.0, -8.0),
    head=(-8.0, 0.0, -4.0), clav_r=(0, 0, 0), clav_l=(0, 0, 0),
    knee_r=(-0.25, -1.0, 0.0), knee_l=(0.55, -1.0, 0.0),
    grip=(-0.16, -0.30, 0.78), blade=(0.22, -0.86, 0.38), edge=(0.05, -0.35, -1.0), elbow_r=(-0.8, 0.3, -0.6),
    hand_l=(0.11, -0.17, 0.86), hand_l_dir=(-0.25, -0.55, 0.8), hand_l_palm=(-0.4, -0.9, 0.0), elbow_l=(0.8, 0.2, -0.6),
    fist_l=0.25, grip_l=0.0, breath=0.0, travel=0.0,
)
# pies de la guardia en el piso: (x, y, giro de la punta)
R0, L0 = (-0.12, -0.17, 6.0), (0.17, 0.19, 38.0)


def P(**kw):
    d = dict(STANCE)
    d.update(kw)
    return d


def FR(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    """Pie derecho en el cuadro f: 'dy' m adelante (en el mundo) de su lugar en la guardia."""
    return T.FootKey(f, R0[0] + dx, R0[1] - dy, R0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


def FL(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None):
    return T.FootKey(f, L0[0] + dx, L0[1] - dy, L0[2] if yaw is None else yaw, pitch, z, 0.0, ease, lift)


PLANTED = {"r": [FR(0)], "l": [FL(0)]}


# empujones del juego (Enemy): parry 0.4 m (perfecto 0.8), cortes livianos de Kaito 0.35-0.4 m, el corte final y las
# habilidades 1.4-1.8 m (HitHeavy). Cada clip se autora con SU distancia: los pies quedan clavados en el mundo.
PARRY_BACK, PERFECT_BACK, HIT_BACK, HEAVY_BACK = 0.4, 0.8, 0.375, 1.6
knock_travel = T.knock_travel


def clips(ch):
    out = [idle()]
    out += locomotion(ch)
    out += [attack1(), attack2(), attack3(), thrust()]
    out += [guard(), counter(), hit(), hit_heavy(), parried(), parried_perfect(), exhausted(), exhausted_hit(), spotted(), death()]
    return out


# ================================================================== quieto y locomoción
def idle():
    # 2.0 s: peso que va y viene entre los pies (cadera 1.5 cm), pecho y hombros respiran, la punta de la hoja
    # dibuja un ocho chico, la cabeza no deja de mirar adelante
    n = 60
    keys = []
    for f in (0, 15, 30, 45, 60):
        a = 2.0 * math.pi * f / n
        keys.append(Key(f, P(hips=(0.012 * math.sin(a), 0.03 + 0.006 * math.cos(a), -0.075 - 0.008 * (0.5 - 0.5 * math.cos(2 * a))),
                             breath=0.5 - 0.5 * math.cos(a),
                             grip=(-0.16 + 0.008 * math.sin(a), -0.30, 0.78 + 0.01 * math.sin(2 * a)),
                             blade=(0.22 + 0.05 * math.sin(a), -0.86, 0.38 + 0.04 * math.cos(a)),
                             head=(-8.0 + 1.5 * math.sin(a), 0.0, -4.0 + 3.0 * math.sin(a + 1.0))), "sine"))
    return T.TeamClip("Idle", n, keys, loop=True, feet=PLANTED, notes="guardia que respira; mismo pie adelante que los golpes")


def locomotion(ch):
    out = []
    # ---- caminata en guardia (2 m/s): pasos cortos, el derecho siempre adelante, la hoja no deja de apuntar
    n = 14
    g = T.gait2(ch, n, WALK_SPEED, 0.56, {"r": (-0.12, -0.07, 6.0), "l": (0.15, 0.07, 26.0)}, lift=0.06, toe_off=22.0, heel=-10.0)

    def walk(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g(f))
        # baja en cada apoyo (dos veces por ciclo) y la cadera acompaña al pie que avanza
        c["hips"] = (0.012 * math.sin(a), 0.02, -0.095 - 0.014 * math.cos(2 * a))
        c["hips_rot"] = (6.0, 2.0 * math.sin(a), 18.0 + 6.0 * math.sin(a))
        c["chest"] = (4.0, -1.5 * math.sin(a), -8.0 - 5.0 * math.sin(a))
        c["head"] = (-8.0, 0.0, -4.0 - 1.5 * math.sin(a))
        c["grip"] = (-0.16, -0.30, 0.78 + 0.012 * math.cos(2 * a + 0.6))
        c["hand_l"] = (0.11, -0.17, 0.86 + 0.01 * math.cos(2 * a + 0.9))
        return c
    out.append(NA.ProcClip("Walk", n, walk, loop=True, root_vel=(0, -WALK_SPEED, 0),
                           notes="avance en guardia a 2 m/s (rodeo y acecho)"))

    # ---- carrera (5 m/s, 6 pasos por segundo): inclinado, la katana adelante y baja apuntando adonde va, la mano
    # libre bombea. La hoja queda del mismo lado que en la caminata y la guardia: el blend de locomoción mezcla cada
    # hueso por separado y con la hoja atrás (como estaba) a media mezcla se metía en las piernas
    n = 10
    g2 = T.gait2(ch, n, RUN_SPEED, 0.32, {"r": (-0.09, -0.03, 0.0), "l": (0.09, -0.03, 0.0)}, lift=0.14, toe_off=40.0, heel=-14.0)

    def run(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g2(f))
        c.update(knee_r=(-0.1, -1.0, 0.2), knee_l=(0.1, -1.0, 0.2))
        # más bajo a mitad del apoyo y arriba en el vuelo (dos veces por ciclo)
        c["hips"] = (0.01 * math.sin(a), 0.0, -0.06 - 0.03 * math.cos(2 * a - 2.0 * math.pi * 0.16))
        c["hips_rot"] = (14.0, 0.0, 10.0 * math.sin(a))
        c["spine"] = (10.0, 0.0, -4.0 * math.sin(a))
        c["chest"] = (6.0, 0.0, -8.0 * math.sin(a))
        c["head"] = (-22.0, 0.0, 2.0 * math.sin(a))
        c["grip"] = (-0.20, -0.20 - 0.04 * math.sin(a), 0.72 + 0.015 * math.cos(2 * a))
        c["blade"] = (0.14, -0.97, 0.12 + 0.03 * math.sin(a))
        c["edge"] = (0.0, -0.06, -1.0)
        c["elbow_r"] = (-0.8, 0.4, -0.5)
        c["hand_l"] = (0.15, -0.05 + 0.20 * math.sin(a + math.pi), 0.80 - 0.05 * math.cos(a))
        c["hand_l_dir"] = (0.0, -0.4, 1.0)
        c["hand_l_palm"] = (-1.0, 0.0, 0.0)
        c["elbow_l"] = (0.6, 0.8, -0.4)
        c["fist_l"] = 0.8
        return c
    out.append(NA.ProcClip("Run", n, run, loop=True, root_vel=(0, -RUN_SPEED, 0),
                           notes="carrera a 5 m/s (runSpeed); con el Animator.speed de VariantMotion sigue clavada"))
    return out


# ================================================================== golpes
def attack1():
    """Tajo horizontal (abre los combos). Aviso: la hoja horizontal ATRÁS a la derecha (vista desde arriba: una
    línea que sale del contorno hacia atrás), el cuerpo enroscado, la mano libre apuntando a Kaito y el talón de
    atrás que se levanta (carga el salto). Pausa f8-f12, suelta f12-f14 con los dos pies en el aire (salto corto
    de 0.8 m: la embestida del juego), contacto = la hoja cruza el frente, cae en f16-f19 y queda abierto."""
    n, apex, contact = 24, 12, 14
    lunge, windup = 0.8, 0.55 + 0.12
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P(hips=(0.02, 0.07, -0.115), hips_rot=(6.0, 0.0, -12.0), spine=(8.0, 4.0, -14.0), chest=(4.0, 4.0, -22.0),
             head=(-8.0, -3.0, 32.0),
             grip=(-0.33, 0.06, 0.86), blade=(-0.5, 0.84, 0.16), edge=(-0.84, -0.5, 0.0), elbow_r=(-0.5, 0.7, -0.5),
             hand_l=(0.04, -0.40, 0.98), hand_l_dir=(0.0, -1.0, 0.1), hand_l_palm=(0.0, -0.2, -1.0), elbow_l=(0.6, 0.0, -0.8),
             fist_l=0.0)
    HOLD = dict(TELL, grip=(-0.34, 0.09, 0.85), blade=(-0.45, 0.88, 0.14), hips=(0.02, 0.075, -0.125))
    SMEAR = dict(HOLD, hips=(0.0, 0.02, -0.10), hips_rot=(6.0, 0.0, 2.0), chest=(4.0, 2.0, -6.0), head=(-8.0, -2.0, 12.0),
                 grip=(-0.38, -0.22, 0.86), blade=(-0.96, -0.26, 0.04), edge=(0.26, -0.96, 0.0))
    CONTACT = dict(SMEAR, hips=(0.0, -0.02, -0.09), hips_rot=(6.0, 0.0, 16.0), spine=(10.0, 0.0, 6.0), chest=(6.0, -2.0, 10.0),
                   head=(-10.0, 0.0, -12.0), grip=(-0.14, -0.44, 0.86), blade=(0.06, -1.0, 0.02), edge=(0.96, 0.06, 0.0),
                   elbow_r=(-0.8, 0.3, -0.4), hand_l=(0.28, -0.05, 0.92), hand_l_dir=(0.6, 0.6, 0.2), hand_l_palm=(0, 0, -1))
    FOLLOW = dict(CONTACT, hips=(0.0, -0.04, -0.12), hips_rot=(6.0, 0.0, 30.0), chest=(6.0, -3.0, 18.0), head=(-10.0, 0.0, -26.0),
                  grip=(0.12, -0.32, 0.84), blade=(0.92, -0.32, -0.12), edge=(0.32, 0.92, 0.0))
    PUNISH = dict(FOLLOW, hips=(0.0, -0.04, -0.16), hips_rot=(8.0, 0.0, 34.0), chest=(10.0, -4.0, 14.0), head=(-12.0, 0.0, -30.0),
                  grip=(0.22, -0.10, 0.74), blade=(0.7, 0.62, -0.3), edge=(-0.62, 0.7, 0.0),
                  hand_l=(0.30, 0.18, 0.86), hand_l_dir=(0.3, 0.6, -0.6), hand_l_palm=(1, 0, 0), fist_l=0.3)
    keys = [
        Key(0, P()),
        Key(8, TELL, "inout"),
        Key(apex, HOLD, "sine"),
        Key(13, SMEAR, "in"),
        Key(contact, CONTACT, "lin"),
        Key(16, FOLLOW, "out"),
        Key(19, PUNISH, "out"),
        Key(n, P(), "sine"),
    ]
    feet = {"r": [FR(0), FR(apex), FR(16, lunge, pitch=-12.0), FR(18, lunge)],
            "l": [FL(0), FL(7), FL(apex, pitch=24.0), FL(19, lunge, ease="out")]}
    return T.TeamClip("Attack1", n, keys, travel=tr, feet=feet, notes="tajo horizontal; aviso: hoja atrás a la derecha",
                      timing=dict(kind="light", apex=apex, contact=contact, active=[contact, 18], hold=[8, apex],
                                  lunge=lunge, windup=windup, state="Attack1"))


def attack2():
    """Tajo diagonal subiendo (segundo del combo, encadenado: aviso corto de 0.2 s). Aviso: agachado y enroscado a
    la izquierda, la mano de la espada cruzada a la cadera izquierda y la hoja baja ATRÁS a la izquierda, la punta
    cerca del piso. El golpe sube de abajo-izquierda a arriba-derecha cruzando el pecho de Kaito (salto corto).
    Apex en f7 (3 cuadros de suelta): el remolino del lago lo usa con 1.1 m de embestida y tiene que entrar entera en
    la suelta (si no, se desliza durante la pausa del juego con los pies clavados)."""
    n, apex, contact = 22, 7, 10
    lunge, windup = 0.8, 0.42
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P(hips=(-0.02, 0.06, -0.15), hips_rot=(8.0, 0.0, 40.0), spine=(14.0, -4.0, 14.0), chest=(8.0, -4.0, 16.0),
             head=(-14.0, 4.0, -40.0),
             grip=(0.16, 0.02, 0.56), blade=(0.55, 0.75, -0.38), edge=(0.1, -0.4, -0.9), elbow_r=(-0.3, -0.4, -0.9),
             hand_l=(0.30, 0.10, 0.80), hand_l_dir=(0.5, 0.4, -0.6), hand_l_palm=(1.0, 0.0, 0.0), elbow_l=(0.8, 0.4, -0.4),
             fist_l=0.4)
    HOLD = dict(TELL, grip=(0.17, 0.035, 0.55), blade=(0.53, 0.77, -0.39), hips=(-0.02, 0.062, -0.154))
    SMEAR = dict(HOLD, hips=(0.0, 0.0, -0.11), hips_rot=(6.0, 0.0, 22.0), chest=(4.0, -2.0, 4.0), head=(-12.0, 2.0, -20.0),
                 grip=(0.08, -0.30, 0.66), blade=(0.55, -0.55, -0.62), edge=(-0.2, -0.6, 0.75))
    CONTACT = dict(SMEAR, hips=(0.0, -0.03, -0.08), hips_rot=(4.0, 0.0, 6.0), spine=(6.0, 2.0, -6.0), chest=(0.0, 2.0, -10.0),
                   head=(-8.0, 0.0, -2.0), grip=(-0.12, -0.42, 0.90), blade=(-0.35, -0.78, 0.5), edge=(-0.55, 0.0, 0.83),
                   elbow_r=(-0.8, 0.2, -0.5), hand_l=(0.25, -0.02, 0.84), hand_l_dir=(0.5, 0.3, -0.7))
    FOLLOW = dict(CONTACT, hips=(0.0, -0.03, -0.12), hips_rot=(0.0, 0.0, -6.0), chest=(-6.0, 4.0, -22.0), head=(-4.0, 0.0, 14.0),
                  grip=(-0.30, -0.14, 1.12), blade=(-0.55, 0.25, 0.80), edge=(-0.5, 0.4, -0.35))
    PUNISH = dict(FOLLOW, hips=(0.0, -0.02, -0.12), grip=(-0.34, 0.0, 1.08), blade=(-0.45, 0.62, 0.62), elbow_r=(-0.8, 0.5, -0.2))
    keys = [
        Key(0, P()),
        Key(5, TELL, "inout"),
        Key(apex, HOLD, "sine"),
        Key(9, SMEAR, "in"),
        Key(contact, CONTACT, "lin"),
        Key(12, FOLLOW, "out"),
        Key(16, PUNISH, "out"),
        Key(n, P(), "sine"),
    ]
    feet = {"r": [FR(0), FR(apex), FR(12, lunge, pitch=-12.0), FR(14, lunge)],
            "l": [FL(0), FL(4), FL(apex, pitch=22.0), FL(15, lunge, ease="out")]}
    return T.TeamClip("Attack2", n, keys, travel=tr, feet=feet,
                      notes="tajo diagonal subiendo; aviso: agachado, hoja baja atrás a la izquierda",
                      timing=dict(kind="light", apex=apex, contact=contact, active=[contact, 14], hold=[5, apex],
                                  lunge=lunge, windup=windup, state="Attack2"))


def attack3():
    """Tajo de arriba con salto (cierra el combo, pesado). Aviso: agazapado sobre el pie de atrás, las dos manos
    arriba del hombro derecho y la hoja horizontal ATRÁS de la cabeza (desde arriba: una barra que sale por detrás),
    el pecho arqueado. En la suelta salta 1.4 m (la embestida), parte de arriba en el aire y cae agachado con la
    punta casi en el piso: el castigo más largo del combo. Lo usan también el salto del bambú (VariantMotion lo lleva
    por el aire) y el rompeguardia de la montaña.
    Apex en f13 (4 cuadros de suelta): la embestida de 1.4 m (y la del élite, 10 % más rápido) entra entera entre la
    suelta y el golpe, así ninguna pausa del juego en el apex lo desliza con los pies clavados."""
    n, apex, contact = 34, 13, 17
    lunge, windup = 1.4, 0.50
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    # hasso: las dos manos al lado del hombro derecho y la hoja inclinada ~35° de la horizontal hacia atrás y AFUERA
    # (parada, desde 52° de cámara se veía como un hilo sobre la cabeza; así proyecta casi todo su largo al costado)
    TELL = P(hips=(0.0, 0.10, -0.14), hips_rot=(-2.0, 0.0, 14.0), spine=(-6.0, 0.0, -6.0), chest=(-10.0, 0.0, -10.0),
             head=(4.0, 0.0, -6.0),
             grip=(-0.24, 0.04, 1.14), blade=(-0.64, 0.50, 0.58), edge=(0.45, -0.85, 0.25), elbow_r=(-0.9, 0.2, -0.3),
             grip_l=1.0, elbow_l=(0.8, -0.2, -0.4), fist_l=1.0)
    HOLD = dict(TELL, hips=(0.0, 0.11, -0.17), grip=(-0.25, 0.06, 1.14), blade=(-0.66, 0.52, 0.54), chest=(-12.0, 0.0, -10.0))
    LAUNCH = dict(HOLD, hips=(0.0, 0.0, -0.02), hips_rot=(6.0, 0.0, 10.0), spine=(4.0, 0.0, 0.0), chest=(-4.0, 0.0, -4.0),
                  head=(-6.0, 0.0, -4.0), grip=(-0.12, -0.12, 1.42), blade=(0.06, -0.10, 1.0), edge=(0.0, -1.0, 0.1),
                  knee_r=(-0.2, -1.0, 0.2))
    CONTACT = dict(LAUNCH, hips=(0.0, -0.06, -0.04), hips_rot=(14.0, 0.0, 10.0), spine=(14.0, 0.0, 0.0), chest=(10.0, 0.0, -4.0),
                   head=(-16.0, 0.0, -4.0), grip=(-0.08, -0.46, 1.02), blade=(0.02, -0.96, 0.25), edge=(0.0, 0.25, -0.96),
                   elbow_r=(-0.8, 0.3, -0.4), elbow_l=(0.8, 0.3, -0.4))
    # el seguimiento frena la punta justo sobre el piso (antes la hoja se hundía 30 cm durante todo el castigo)
    FOLLOW = dict(CONTACT, hips=(0.0, -0.08, -0.12), hips_rot=(20.0, 0.0, 12.0), spine=(18.0, 0.0, 0.0), head=(-22.0, 0.0, -4.0),
                  grip=(-0.06, -0.44, 0.66), blade=(0.02, -0.82, -0.57), edge=(0.0, 0.57, -0.82))
    LAND = dict(FOLLOW, hips=(0.0, -0.07, -0.25), hips_rot=(22.0, 0.0, 14.0), spine=(20.0, 0.0, 0.0), chest=(14.0, 0.0, -4.0),
                head=(-26.0, 0.0, -4.0), grip=(-0.06, -0.40, 0.48), blade=(0.0, -0.91, -0.41), edge=(0.0, 0.41, -0.91))
    PUNISH = dict(LAND, hips=(0.0, -0.06, -0.23), grip=(-0.06, -0.38, 0.49), blade=(0.0, -0.91, -0.41))
    keys = [
        Key(0, P()),
        Key(8, TELL, "inout"),
        Key(apex, HOLD, "sine"),
        Key(15, LAUNCH, "in"),
        Key(contact, CONTACT, "lin"),
        Key(19, FOLLOW, "out"),
        Key(21, LAND, "in2"),
        Key(27, PUNISH, "out"),
        Key(n, P(), "sine"),
    ]
    feet = {"r": [FR(0), FR(apex), FR(contact, 0.95, z=0.16), FR(20, lunge, pitch=-12.0), FR(22, lunge)],
            "l": [FL(0), FL(8), FL(apex, pitch=28.0), FL(18, 0.72, z=0.22, ease="out"), FL(23, lunge, ease="out")]}
    return T.TeamClip("Attack3", n, keys, travel=tr, feet=feet,
                      notes="tajo de arriba con salto; aviso: agazapado, hoja atrás de la cabeza",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 21], hold=[8, apex],
                                  lunge=lunge, windup=windup, state="Attack3"))


def thrust():
    """Estocada desde lejos (2.6-5.5 m, embestida de 3.2 m). Aviso: el más bajo de todos, con un paso afuera del pie
    de adelante, y la hoja recogida en la cadera derecha con la punta ABIERTA hacia afuera y adelante (desde la cámara
    del juego: una línea que sale 0.6 m del contorno del lado de la espada, no tapada por las piernas); la mano libre
    adelante sobre el lomo. El apex es la pose agachada (f11) y la suelta dura 10 cuadros: los 3.2 m de la embestida
    (12 m/s como mucho) entran enteros entre la suelta y el golpe, así una pausa del juego en el apex lo deja agazapado
    y quieto. En la suelta despega, vuela bajo y estirado, clava la estocada en el aire y aterriza en una zancada larga.
    Lo usa también el arpón del lago (2.4 m)."""
    n, apex, contact = 40, 11, 21
    lunge, windup = 3.2, 0.70
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    LOW = P(hips=(0.0, 0.06, -0.21), hips_rot=(14.0, 0.0, 34.0), spine=(14.0, 0.0, -10.0), chest=(6.0, 0.0, -20.0),
            head=(-24.0, 0.0, -6.0), knee_l=(0.8, -0.6, 0.0), knee_r=(-0.6, -1.0, 0.0),
            grip=(-0.34, 0.12, 0.50), blade=(-0.45, -0.89, 0.06), edge=(0.0, 0.0, -1.0), elbow_r=(-0.8, 0.6, -0.3),
            hand_l=(-0.04, -0.30, 0.62), hand_l_dir=(-0.3, -0.9, 0.0), hand_l_palm=(0.0, 0.0, -1.0), elbow_l=(0.8, 0.0, -0.6),
            fist_l=0.1)
    HOLD = dict(LOW, grip=(-0.35, 0.15, 0.49), hips=(0.0, 0.07, -0.22), head=(-26.0, 0.0, -6.0))
    PUSH = dict(HOLD, hips=(0.0, -0.02, -0.15), hips_rot=(22.0, 0.0, 30.0), spine=(16.0, 0.0, -10.0), head=(-30.0, 0.0, -4.0),
                knee_r=(-0.2, -1.0, 0.3), grip=(-0.30, 0.06, 0.55), blade=(-0.32, -0.95, 0.05))
    FLY = dict(PUSH, hips=(0.0, -0.06, -0.10), hips_rot=(26.0, 0.0, 28.0), spine=(16.0, 0.0, -12.0), chest=(8.0, 0.0, -20.0),
               head=(-34.0, 0.0, -2.0), grip=(-0.24, 0.0, 0.58), blade=(-0.10, -0.99, 0.04))
    CONTACT = dict(FLY, hips=(0.0, -0.10, -0.12), hips_rot=(22.0, 0.0, 30.0), spine=(16.0, 0.0, -14.0), chest=(10.0, 0.0, -24.0),
                   head=(-30.0, 0.0, 4.0),
                   grip=(-0.12, -0.62, 0.66), blade=(0.04, -1.0, 0.02), edge=(0.0, 0.0, -1.0), elbow_r=(-0.8, 0.0, -0.6),
                   hand_l=(0.28, 0.22, 0.80), hand_l_dir=(0.5, 0.8, -0.2), hand_l_palm=(0.0, 0.0, -1.0), elbow_l=(0.8, 0.5, -0.2))
    LAND = dict(CONTACT, hips=(0.0, -0.08, -0.22), hips_rot=(16.0, 0.0, 30.0), grip=(-0.12, -0.64, 0.62))
    PUNISH = dict(LAND, grip=(-0.12, -0.58, 0.60), hips=(0.0, -0.07, -0.23))
    keys = [
        Key(0, P()),
        Key(9, LOW, "inout"),
        Key(apex, HOLD, "sine"),
        Key(12, PUSH, "out"),
        Key(15, FLY, "out"),
        Key(20, dict(CONTACT, grip=(-0.16, -0.34, 0.62)), "inout"),
        Key(contact, CONTACT, "snap"),
        Key(25, LAND, "in2"),
        Key(31, PUNISH, "sine"),
        Key(n, P(), "sine"),
    ]
    # el transform arranca en la suelta (f11) y en f12 ya avanzó 0.77 m: los pies despegan en f11-f12 y vuelan con el
    # cuerpo; el de adelante aterriza estirado 0.25 m más allá de la embestida y el de atrás cae de punta detrás
    # en el vuelo los pies van con el cuerpo cuadro a cuadro (el avance del juego no es lineal en cuadros del clip):
    # (cuadro, delante de su lugar en la guardia respecto de lo que avanzó el transform, altura)
    w = -0.08                                    # el paso afuera del aviso (base más ancha)
    fly_r = [(12, -0.18, 0.05), (13, -0.08, 0.09), (14, -0.02, 0.12), (16, 0.02, 0.12), (18, 0.05, 0.11), (19, 0.08, 0.10),
             (20, 0.10, 0.09), (21, 0.14, 0.08), (22, 0.18, 0.06), (23, 0.22, 0.05), (24, 0.26, 0.03)]
    fly_l = [(13, -0.26, 0.07), (14, -0.24, 0.10), (16, -0.22, 0.11), (18, -0.21, 0.10), (19, -0.20, 0.10), (21, -0.19, 0.09),
             (23, -0.18, 0.07), (25, -0.18, 0.04)]
    feet = {"r": [FR(0), FR(7, dx=w, lift=0.04), FR(apex, dx=w)]
                 + [FR(f, tr[f] + o, dx=w if f < 16 else 0.0, z=z, ease="lin", lift=0.0) for f, o, z in fly_r]
                 + [FR(26, lunge + 0.20, pitch=-10.0), FR(28, lunge + 0.20), FR(32, lunge + 0.20), FR(37, lunge)],
            "l": [FL(0), FL(9), FL(apex, pitch=30.0), FL(12, tr[12] - 0.28, pitch=40.0, z=0.03, ease="lin", lift=0.0)]
                 + [FL(f, tr[f] + o, z=z, ease="lin", lift=0.0) for f, o, z in fly_l]
                 + [FL(27, lunge - 0.15, pitch=28.0, ease="out"), FL(33, lunge - 0.15, pitch=28.0), FL(n - 2, lunge)]}
    return T.TeamClip("Thrust", n, keys, travel=tr, feet=feet, notes="estocada voladora; aviso: muy agachado, hoja abierta en la cadera",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 25], hold=[9, apex],
                                  lunge=lunge, windup=windup, state="Thrust"))


# ================================================================== defensa
def guard_pose():
    """Guardia cerrada: la hoja horizontal delante de la cara, la mano libre empuja el lomo cerca de la punta."""
    return P(hips=(0.0, 0.05, -0.12), hips_rot=(4.0, 0.0, 10.0), spine=(4.0, 0.0, -4.0), chest=(0.0, 0.0, -6.0), head=(-4.0, 0.0, 0.0),
             grip=(-0.26, -0.26, 1.02), blade=(0.98, -0.10, 0.12), edge=(0.0, -0.45, 0.89), elbow_r=(-0.9, 0.2, -0.4),
             hand_l=(0.30, -0.30, 1.04), hand_l_dir=(0.1, -0.2, 1.0), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.2, -0.4), fist_l=0.1)


GUARD_FEET = PLANTED


def guard():
    """Guardia cerrada (EnterGuard, después de un combo o al aguantar demasiados golpes): una barra a la altura del
    pecho, desde arriba es la única pose con la hoja cruzada al frente, se lee 'no le pegues: rebota'."""
    n = 36
    G = guard_pose()
    keys = []
    for f in (0, 9, 18, 27, 36):
        a = 2.0 * math.pi * f / n
        keys.append(Key(f, dict(G, hips=(0.004 * math.sin(a), 0.05, -0.12 - 0.006 * math.cos(a)), breath=0.5 - 0.5 * math.cos(a),
                                grip=(-0.26, -0.26, 1.02 + 0.006 * math.sin(a)), hand_l=(0.30, -0.30, 1.04 + 0.006 * math.sin(a))), "sine"))
    return T.TeamClip("Guard", n, keys, loop=True, feet=GUARD_FEET, notes="guardia cerrada: hoja horizontal delante de la cara")


def counter():
    """Desvío (segundo golpe contra la guardia): la hoja barre hacia afuera y arriba sacando la de Kaito del medio,
    con un pisotón del pie de adelante en el lugar, y vuelve a la guardia lista para el contraataque."""
    n = 12
    G = guard_pose()
    SWEEP = dict(G, hips=(0.0, 0.0, -0.11), hips_rot=(4.0, 0.0, -10.0), chest=(-4.0, 0.0, -18.0), head=(-4.0, 0.0, 14.0),
                 grip=(-0.36, -0.20, 1.18), blade=(-0.45, -0.55, 0.70), edge=(-0.85, 0.2, 0.45),
                 hand_l=(0.22, -0.10, 0.92), hand_l_dir=(0.3, -0.4, 0.8), hand_l_palm=(-0.6, -0.8, 0.0))
    keys = [Key(0, G), Key(3, SWEEP, "snap"), Key(6, dict(SWEEP, grip=(-0.34, -0.16, 1.14)), "out"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(1, pitch=-8.0), FR(3, ease="in"), FR(n)], "l": [FL(0)]}
    return T.TeamClip("Counter", n, keys, feet=feet, notes="desvío con la hoja hacia afuera y un pisotón; termina en guardia")


# ================================================================== reacciones
def hit():
    """Golpe recibido (0.3 s, se reinicia golpe a golpe): la cabeza y el pecho se van para atrás, el brazo de la
    espada se abre y el empujón de los cortes livianos de Kaito (0.35-0.4 m) lo lleva con un paso corto de cada pie;
    a los 9 cuadros está otra vez en guardia."""
    n = 9
    back = HIT_BACK
    PEAK = P(hips=(0.0, 0.08, -0.09), hips_rot=(-10.0, 0.0, 26.0), spine=(-10.0, 0.0, 0.0), chest=(-14.0, 0.0, 6.0),
             head=(14.0, 0.0, 8.0),
             grip=(-0.36, -0.08, 0.98), blade=(-0.35, -0.55, 0.75), elbow_r=(-0.9, 0.2, 0.0),
             hand_l=(0.36, 0.02, 1.0), hand_l_dir=(0.6, 0.0, 0.8), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.2, 0.0), fist_l=0.0)
    keys = [Key(0, P()), Key(2, PEAK, "snap"), Key(4, PEAK, "out"), Key(n, P(), "sine")]
    # el de atrás despega enseguida (el empujón es casi todo en los primeros 0.1 s) y el de adelante lo sigue
    feet = {"r": [FR(0), FR(1), FR(6, -back, pitch=-6.0, ease="out"), FR(n, -back)],
            "l": [FL(0), FL(5, -back, ease="out")]}
    return T.TeamClip("Hit", n, keys, travel=knock_travel(n, back), feet=feet,
                      notes="golpe recibido: cabeza y pecho atrás, un paso atrás con el empujón (0.375 m)")


def hit_heavy():
    """Golpe pesado recibido (el corte final de Kaito y sus habilidades lo empujan 1.4-1.8 m; Enemy lo elige cuando el
    empujón pasa de 1 m): sale despedido para atrás con los dos pies en el aire, los brazos abiertos, cae sobre el pie
    de atrás, trastabilla un paso y se rearma. 0.53 s = el aturdimiento de un golpe pesado (0.32 x 1.6)."""
    n = 16
    back = HEAVY_BACK
    FLUNG = P(hips=(0.0, 0.10, -0.04), hips_rot=(-18.0, 0.0, 30.0), spine=(-14.0, 0.0, 6.0), chest=(-18.0, 0.0, 10.0),
              head=(22.0, 0.0, 10.0),
              grip=(-0.44, 0.04, 1.10), blade=(-0.45, 0.40, 0.80), elbow_r=(-0.9, 0.2, 0.1), clav_r=(0, 0, 8),
              hand_l=(0.36, 0.14, 1.00), hand_l_dir=(0.8, 0.2, 0.5), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.3, 0.1), fist_l=0.0)
    CATCH = dict(FLUNG, hips=(0.0, 0.10, -0.16), hips_rot=(-2.0, 0.0, 24.0), spine=(2.0, 0.0, 2.0), chest=(-4.0, 0.0, 4.0),
                 head=(6.0, 0.0, 4.0), grip=(-0.36, -0.08, 0.92), blade=(-0.30, -0.45, 0.84), clav_r=(0, 0, 0),
                 hand_l=(0.34, -0.06, 0.92), hand_l_dir=(0.5, -0.3, 0.8))
    keys = [Key(0, P()), Key(2, FLUNG, "snap"), Key(5, dict(FLUNG, hips=(0.0, 0.10, -0.08)), "out"), Key(8, CATCH, "in2"),
            Key(11, dict(CATCH, hips=(0.0, 0.08, -0.13)), "out"), Key(n, P(), "sine")]
    feet = {"l": [FL(0), FL(5, -back + 0.30, ease="out", lift=0.12), FL(7, -back + 0.30), FL(12, -back, lift=0.05)],
            "r": [FR(0), FR(7, -back + 0.12, pitch=-8.0, ease="out", lift=0.12), FR(9, -back + 0.12), FR(14, -back, lift=0.04)]}
    return T.TeamClip("HitHeavy", n, keys, travel=knock_travel(n, back), feet=feet,
                      notes="golpe pesado recibido: despedido 1.6 m, cae y trastabilla", timing=dict(sheet=[2, 5, 8, 11, 16]))


def parried_clip(name, back, n, settle, recoil, knock, hold, stumble, feet, notes):
    """Parry recibido: el corte del juego (Enemy.OnParried: Recoil de parriedRecoil = 0.32 s, x1.5 si fue perfecto)
    arranca el paso siguiente del combo con un cruce de 0.08 s, así que en el cuadro del corte el clip tiene que estar
    en la guardia de los golpes ('chain' lo mide). 'settle' = cuadro desde el que ya está en guardia."""
    keys = [Key(0, P()), Key(2, knock, "snap"), Key(hold, dict(knock, grip=V3(knock["grip"], 0.0, 0.03, 0.03)), "out"),
            Key(hold + 2, stumble, "inout"), Key(settle, P(), "sine"), Key(n, P(), "sine")]
    cut = round(recoil * T.FPS, 1)
    return T.TeamClip(name, n, keys, travel=knock_travel(n, back), feet=feet, notes=notes,
                      timing=dict(sheet=[2, hold, hold + 2, settle], chain=[(cut, "Attack1", 0, 0.10)]))


def V3(p, dx, dy, dz):
    return (p[0] + dx, p[1] + dy, p[2] + dz)


PARRY_KNOCK = P(hips=(0.0, 0.10, -0.07), hips_rot=(-12.0, 0.0, 34.0), spine=(-12.0, 0.0, 10.0), chest=(-16.0, -6.0, 16.0),
                head=(16.0, 0.0, 14.0),
                grip=(-0.42, 0.10, 1.20), blade=(-0.55, 0.62, 0.55), edge=(-0.6, -0.4, 0.4), elbow_r=(-0.9, 0.2, 0.3), clav_r=(0, 0, 10),
                hand_l=(0.38, 0.16, 0.98), hand_l_dir=(0.9, 0.2, 0.4), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(0.7, 0.5, 0.2), fist_l=0.0)


def parried():
    """Le desviaron el golpe (parry común: Recoil 0.32 s y 0.4 m atrás). La mano de la espada sale despedida arriba y
    AFUERA a la derecha con la hoja apuntando atrás, el pecho se abre y se tuerce, la mano libre se abre: desde arriba
    la silueta se abre en una X (f2-f4); salta para atrás con los dos pies y en f9 (el corte) ya está en guardia."""
    STUMBLE = dict(PARRY_KNOCK, hips=(0.0, 0.08, -0.11), hips_rot=(-2.0, 2.0, 24.0), chest=(-4.0, -2.0, 4.0), head=(2.0, 0.0, 2.0),
                   grip=(-0.30, -0.12, 0.98), blade=(-0.20, -0.30, 0.93), hand_l=(0.24, -0.10, 0.92), clav_r=(0, 0, 3))
    b = PARRY_BACK
    feet = {"l": [FL(0), FL(4, -b, ease="out", lift=0.06)],
            "r": [FR(0), FR(1), FR(6, -b, pitch=-8.0, ease="out", lift=0.06), FR(8, -b)]}
    return parried_clip("Parried", b, 10, 9, 0.32, PARRY_KNOCK, 4, STUMBLE, feet,
                        "parry recibido: brazo de la espada despedido arriba y afuera, salto atrás; en guardia al corte")


def parried_perfect():
    """Parry perfecto (Recoil 0.48 s y 0.8 m atrás; Enemy lo elige si el controller lo tiene): la recompensa grande.
    Despedido con los dos pies en el aire, el brazo de la espada atrás por encima de la cabeza, aterriza sobre el de
    atrás, trastabilla un paso y en f14 (el corte) está en guardia."""
    KNOCK = dict(PARRY_KNOCK, hips=(0.0, 0.12, -0.04), hips_rot=(-18.0, 0.0, 40.0), spine=(-16.0, 0.0, 12.0),
                 chest=(-20.0, -8.0, 18.0), head=(22.0, 0.0, 16.0), grip=(-0.46, 0.20, 1.26), blade=(-0.50, 0.75, 0.42),
                 clav_r=(0, 0, 14), hand_l=(0.30, 0.14, 0.92))
    STUMBLE = dict(KNOCK, hips=(0.0, 0.10, -0.13), hips_rot=(-4.0, 3.0, 26.0), spine=(-4.0, 0.0, 4.0), chest=(-8.0, -3.0, 10.0),
                   head=(8.0, 0.0, 8.0), grip=(-0.38, 0.0, 1.08), blade=(-0.40, 0.30, 0.86), hand_l=(0.34, 0.04, 0.94), clav_r=(0, 0, 4))
    b = PERFECT_BACK
    feet = {"l": [FL(0), FL(4, -b + 0.14, ease="out", lift=0.10), FL(6, -b + 0.14), FL(11, -b, lift=0.04)],
            "r": [FR(0), FR(6, -b + 0.02, pitch=-8.0, ease="out", lift=0.10), FR(9, -b)]}
    return parried_clip("ParriedPerfect", b, 15, 14, 0.48, KNOCK, 6, STUMBLE, feet,
                        "parry perfecto: despedido 0.8 m con los dos pies en el aire, trastabilla; en guardia al corte")


def exhausted_pose(a=0.0):
    return P(hips=(0.01 * math.sin(a), 0.06, -0.17 - 0.012 * math.sin(2 * a)), hips_rot=(16.0, 0.0, 10.0),
             spine=(18.0 - 3.0 * math.sin(2 * a), 0.0, 0.0), chest=(12.0, 0.0, -4.0),
             head=(10.0 + 8.0 * math.sin(a), 8.0 * math.cos(a), 6.0 * math.sin(a)), breath=0.5 + 0.5 * math.sin(2 * a),
             grip=(-0.30, -0.18, 0.36 + 0.01 * math.sin(2 * a)), blade=(-0.25, -0.90, -0.35), edge=(-0.96, 0.27, 0.0),
             elbow_r=(-0.8, 0.4, -0.2),
             hand_l=(0.17, -0.10, 0.42 + 0.008 * math.sin(2 * a)), hand_l_dir=(-0.2, -0.5, -0.8), hand_l_palm=(-0.3, 0.6, -0.7),
             elbow_l=(0.8, 0.4, 0.0), fist_l=0.3)


EXH_FEET = {"r": [FR(0, dx=-0.03)], "l": [FL(0, 0.13, dx=0.02, yaw=30.0)]}


def exhausted():
    """Postura quebrada (2.4 s a merced de Kaito, y la pose de la ejecución): agachado, el brazo de la espada
    colgando con la punta APOYADA en el piso adelante (antes se hundía media hoja), la otra mano en la rodilla, el pecho que sube y baja, la cabeza que se le
    va en círculos (mareo). Desde arriba: la silueta más chica y la hoja quieta en el piso."""
    n = 48
    keys = [Key(f, exhausted_pose(2.0 * math.pi * f / n), "sine") for f in (0, 12, 24, 36, 48)]
    return T.TeamClip("Exhausted", n, keys, loop=True, feet=EXH_FEET, notes="postura quebrada: agachado, hoja en el piso, mareo")


def exhausted_hit():
    """Golpe recibido estando quebrado (Enemy lo usa si el controller lo tiene y al terminar vuelve al loop de
    Exhausted): un sacudón que empieza y termina en el primer cuadro de Exhausted, con el empujón liviano de Kaito
    (0.375 m) en dos pasitos arrastrados para atrás (con Hit se paraba en guardia en plena ventana de daño)."""
    n = 12
    back = HIT_BACK
    E = exhausted_pose()
    PEAK = dict(E, hips=(0.0, 0.10, -0.15), hips_rot=(4.0, 0.0, 16.0), spine=(4.0, 0.0, 6.0), chest=(-4.0, 0.0, 4.0),
                head=(24.0, 0.0, 10.0), grip=(-0.34, -0.10, 0.44), hand_l=(0.26, -0.02, 0.56), hand_l_dir=(0.6, -0.2, 0.4))
    keys = [Key(0, E), Key(2, PEAK, "snap"), Key(5, dict(PEAK, hips=(0.0, 0.09, -0.16)), "out"), Key(n, E, "sine")]
    r, l = EXH_FEET["r"][0], EXH_FEET["l"][0]
    feet = {"l": [l, T.FootKey(5, l.x, l.y + back, l.yaw, 0.0, 0.0, 0.0, "out", 0.05)],
            "r": [r, T.FootKey(1, r.x, r.y, r.yaw), T.FootKey(7, r.x, r.y + back, r.yaw, 0.0, 0.0, 0.0, "out", 0.05)]}
    return T.TeamClip("ExhaustedHit", n, keys, travel=knock_travel(n, back), feet=feet,
                      notes="sacudón estando quebrado, dos pasitos atrás; vuelve al primer cuadro de Exhausted",
                      timing=dict(chain=[(n, "Exhausted", 0, 0.02)]))


def spotted():
    """Alerta (0.6 s, Enemy.Alert): se sobresalta (un saltito en el lugar, la cabeza adelante), la hoja sube vertical
    delante de la cara un instante, como quien saluda al rival, y baja a la guardia."""
    n = 18
    UP = P(hips=(0.0, 0.03, -0.02), hips_rot=(-2.0, 0.0, 12.0), spine=(-4.0, 0.0, -4.0), chest=(-6.0, 0.0, -6.0), head=(-14.0, 0.0, -2.0),
           grip=(-0.12, -0.24, 1.0), blade=(0.0, -0.15, 1.0), edge=(0.0, -1.0, 0.0), elbow_r=(-0.9, 0.2, -0.3),
           hand_l=(0.16, -0.10, 0.92), hand_l_dir=(-0.2, -0.3, 0.9), hand_l_palm=(-0.7, -0.6, 0.0))
    keys = [Key(0, P()), Key(4, dict(UP, hips=(0.0, 0.03, 0.02)), "out"), Key(7, UP, "in"),
            Key(10, dict(UP, grip=(-0.12, -0.25, 1.02)), "sine"), Key(n, P(), "inout")]
    feet = {"r": [FR(0), FR(2, z=0.035, lift=0.0, ease="out"), FR(6, lift=0.0, ease="in"), FR(n)],
            "l": [FL(0), FL(2, z=0.035, lift=0.0, ease="out"), FL(6, lift=0.0, ease="in"), FL(n)]}
    return T.TeamClip("Spotted", n, keys, feet=feet, notes="alerta: saltito y la hoja vertical delante de la cara")


def death():
    """Muerte (1.1 s; Enemy.DeathRoutine lo corre 0.8 m hacia atrás en ~0.55 s y a los 1.45 s lo vuelve humo; con este
    clip ya no lo gira como una tabla): el golpe lo echa para atrás con un paso, se le aflojan las rodillas, cae de
    rodillas soltando la katana y se desploma de costado-boca abajo. Los pies acompañan el deslizamiento."""
    n = 33
    slide = [-0.8 * math.sin(min(1.0, (f / T.FPS) * 1.8) * math.pi * 0.5) for f in range(n + 1)]
    D0 = P(hips=(0.0, 0.10, -0.08), hips_rot=(-14.0, 0.0, 22.0), chest=(-16.0, 0.0, 8.0), head=(20.0, 0.0, 8.0),
           grip=(-0.36, 0.0, 0.92), blade=(-0.5, 0.3, 0.8), hand_l=(0.36, 0.06, 0.96), hand_l_dir=(0.6, 0.0, 0.8),
           hand_l_palm=(0.0, -1.0, 0.0), elbow_r=(-0.9, 0.2, 0.0), elbow_l=(0.9, 0.2, 0.0), fist_l=0.0)
    KNEES = P(hips=(0.0, 0.10, -0.335), hips_rot=(-4.0, 0.0, 6.0), spine=(-2.0, 0.0, 0.0), chest=(-6.0, 0.0, 0.0), head=(16.0, 0.0, 0.0),
              knee_r=(0.0, -1.0, -0.2), knee_l=(0.0, -1.0, -0.2),
              grip=(-0.30, -0.06, 0.42), blade=(-0.45, -0.80, -0.40), edge=(-0.9, 0.45, 0.0), elbow_r=(-0.8, 0.4, 0.0),
              hand_l=(0.26, -0.04, 0.44), hand_l_dir=(0.1, -0.2, -1.0), hand_l_palm=(-1.0, 0.0, 0.0), elbow_l=(0.8, 0.4, 0.0))
    DOWN = dict(KNEES, hips=(0.0, 0.0, -0.345), hips_rot=(70.0, 0.0, 6.0), spine=(14.0, 0.0, 4.0), chest=(6.0, 0.0, 0.0),
                head=(-30.0, 0.0, 30.0),
                grip=(-0.36, -0.55, 0.12), blade=(-0.6, -0.8, 0.0), edge=(0.0, 0.0, -1.0), elbow_r=(-0.6, 0.0, 0.8),
                hand_l=(0.34, -0.45, 0.10), hand_l_dir=(0.4, -0.8, 0.0), hand_l_palm=(0.0, 0.0, -1.0), elbow_l=(0.6, 0.0, 0.8))
    keys = [Key(0, P()), Key(3, D0, "snap"), Key(8, dict(D0, hips=(0.0, 0.14, -0.14)), "out"),
            Key(16, KNEES, "in"), Key(19, dict(KNEES, hips=(0.0, 0.08, -0.355), head=(24.0, 0.0, 6.0)), "out"),
            Key(28, DOWN, "in"), Key(30, dict(DOWN, hips=(0.0, -0.01, -0.355)), "out"), Key(n, DOWN, "sine")]
    # en el mundo: el pie de adelante retrocede con el empujón; después los dos quedan de punta (empeine al piso) para
    # las rodillas apoyadas
    # (de rodillas: la punta del pie ~0.36 m detrás de la cadera en el clip, que terminó 0.8 m atrás en el mundo)
    feet = {"r": [FR(0), FR(2), FR(8, -0.62, pitch=-6.0, ease="out"), FR(10, -0.62), FR(16, -1.50, dx=-0.02, yaw=0.0, pitch=70.0, ease="out"),
                  FR(28, -1.50, dx=-0.02, yaw=0.0, pitch=80.0)],
            "l": [FL(0), FL(4, pitch=10.0), FL(12, -0.80, dx=-0.03, yaw=10.0, ease="out"), FL(17, -1.15, dx=-0.03, yaw=0.0, pitch=70.0),
                  FL(28, -1.15, dx=-0.03, yaw=0.0, pitch=80.0)]}
    return T.TeamClip("Death", n, keys, travel=slide, feet=feet, notes="muerte: atrás, de rodillas, boca abajo",
                      # de rodillas el pie gira sobre la punta y el empeine roza el piso: 4 cm de tolerancia
                      timing=dict(sheet=[3, 8, 16, 22, 28], slide_ok=4.0))
