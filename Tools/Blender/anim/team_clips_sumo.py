"""Clips del sumo (Characters/Sumo/luchadorsumo.fbx) en el marco de autoría de team_rig (metros del juego, frente
-Y, izquierda +X). 2.6 m con el moño; piernas de 0.64 m bajo una panza enorme, brazos de 0.75 m, pies de 0.6 m.

Lo que dice la auditoría (ANIM-07) y cómo se resolvió:
  * Attack1/Attack2 (harite, la bofetada): aviso = la mano que va a pegar ATRÁS a la altura del hombro con el hombro
    girado (desde arriba, un brazo que sale del contorno para atrás), la otra adelante de guardia; la suelta es el
    brazo entero adelante con el cuerpo detrás y medio paso. Contacto = activeStart.
  * Attack3 (shiko, el pisotón): la pierna sube abierta al costado y se SOSTIENE arriba temblando 0.33 s (el aviso),
    baja de golpe en 3 cuadros y queda en cuclillas abiertas (la onda sale con el pie).
  * Special (tachiai, la embestida): agachado con los puños en el piso mirando para arriba (el aviso imparable), sale
    disparado y corre pisando corto mientras dura el carril (Enemy estira la fase activa con tl.sustain), frena
    derrapando con los brazos abiertos y vuelve a la guardia.
  * Hit 0.4 s, Parried 0.9 s (la mano rebotada para arriba, dos pasos atrás), Exhausted con las manos en las rodillas,
    Death que cae sentado y después de espaldas como un árbol, Idle que respira con la panza, caminar y trotar
    abiertos (los pies clavados en el mundo).
El esqueleto es el del equipo (manos y pies cuelgan de controles IK en la raíz): team_rig pone los controles pegados a
la mano/pie y las rodillas (que pesan vértices en los polos) rígidas con la tibia. SumoPoser.cs deja de posar los
golpes que estos clips ya traen (Attack1..Special) y sigue posando los propios del Ōzeki y de las variantes.
"""
import math
import nindo_anim as NA
import team_rig as T

Key = NA.Key
RUN_SPEED, WALK_SPEED = 3.4, 1.6          # EnemyArchetypes.Sumo(): runSpeed, walkSpeed
LOCOMOTION = (("Idle", 0.0), ("Walk", WALK_SPEED / RUN_SPEED), ("Run", 1.0))

# ------------------------------------------------------------------ guardia
# piernas abiertas con las puntas afuera y las rodillas sobre los pies, la cadera baja, la panza adelante, los brazos
# colgando a los costados de la panza listos para empujar
STANCE = dict(
    hips=(0.0, 0.02, -0.10), hips_rot=(6.0, 0.0, 0.0), spine=(6.0, 0.0, 0.0), head=(-10.0, 0.0, 0.0),
    knee_r=(-0.8, -0.6, 0.0), knee_l=(0.8, -0.6, 0.0),
    hand_r=(-0.62, -0.20, 1.05), hand_r_dir=(-0.1, -0.35, -0.9), hand_r_palm=(1.0, 0.0, 0.0), elbow_r=(-1.0, 0.3, -0.3),
    hand_l=(0.62, -0.20, 1.05), hand_l_dir=(0.1, -0.35, -0.9), hand_l_palm=(-1.0, 0.0, 0.0), elbow_l=(1.0, 0.3, -0.3),
    fist_r=0.3, fist_l=0.3, breath=0.0, travel=0.0,
)
R0, L0 = (-0.42, 0.02, -22.0), (0.42, 0.02, 22.0)


def P(**kw):
    d = dict(STANCE)
    d.update(kw)
    return d


def FR(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None, roll=0.0):
    return T.FootKey(f, R0[0] + dx, R0[1] - dy, R0[2] if yaw is None else yaw, pitch, z, roll, ease, lift)


def FL(f, dy=0.0, dx=0.0, yaw=None, pitch=0.0, z=0.0, ease="inout", lift=None, roll=0.0):
    return T.FootKey(f, L0[0] + dx, L0[1] - dy, L0[2] if yaw is None else yaw, pitch, z, roll, ease, lift)


PLANTED = {"r": [FR(0)], "l": [FL(0)]}


def knock_travel(n, meters, rate=10.0):
    return [-meters * (1.0 - math.exp(-rate * f / T.FPS)) for f in range(n + 1)]


def mirror(d):
    """La misma pose del otro lado (la bofetada izquierda es la derecha espejada): x cambia de signo, los giros
    alrededor de Y y Z también, y los canales de un lado pasan al otro."""
    out = {}
    swap = lambda k: k.replace("_r", "_TMP").replace("_l", "_r").replace("_TMP", "_l")
    for k, v in d.items():
        nk = swap(k) if (k.endswith("_r") or k.endswith("_l") or "_r_" in k or "_l_" in k) else k
        if isinstance(v, tuple) and len(v) == 3:
            if k in ("hips_rot", "spine", "chest", "head") or k.startswith("clav") or k.endswith("_rot"):
                v = (v[0], -v[1], -v[2])
            else:
                v = (-v[0], v[1], v[2])
        out[nk] = v
    return out


def clips(ch):
    out = [idle()]
    out += locomotion(ch)
    out += [attack1(), attack2(), attack3(), special()]
    out += [hit(), parried(), exhausted(), spotted(), death()]
    return out


# ================================================================== quieto y locomoción
def idle():
    """3 s: la panza sube y baja (respira hondo), el peso pasa de un pie al otro, los brazos se mecen y la cabeza
    mira alrededor sin dejar de vigilar."""
    n = 90
    keys = []
    for f in range(0, n + 1, 15):
        a = 2.0 * math.pi * f / n
        b = 2.0 * math.pi * 2.0 * f / n
        keys.append(Key(f, P(hips=(0.025 * math.sin(a), 0.02, -0.10 - 0.012 * (0.5 - 0.5 * math.cos(b))),
                             hips_rot=(6.0, -2.0 * math.sin(a), 0.0), breath=0.5 - 0.5 * math.cos(b),
                             spine=(6.0 - 2.0 * math.sin(b), 1.5 * math.sin(a), 0.0),
                             head=(-10.0 + 3.0 * math.sin(b + 0.6), 0.0, 10.0 * math.sin(a + 0.8)),
                             hand_r=(-0.62 - 0.02 * math.sin(a), -0.20 + 0.03 * math.cos(a), 1.05 + 0.02 * math.sin(b)),
                             hand_l=(0.62 - 0.02 * math.sin(a), -0.20 - 0.03 * math.cos(a), 1.05 + 0.02 * math.sin(b + 0.5))), "sine"))
    return T.TeamClip("Idle", n, keys, loop=True, feet=PLANTED, notes="respira con la panza, el peso va y viene")


def locomotion(ch):
    out = []
    n = 22
    g = T.gait2(ch, n, WALK_SPEED, 0.62, {"r": (-0.40, 0.0, -18.0), "l": (0.40, 0.0, 18.0)}, lift=0.10, toe_off=18.0, heel=-8.0)

    def walk(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g(f))
        # se balancea de un pie al otro (la panza va sobre el pie apoyado) y baja en cada pisada
        c["hips"] = (-0.06 * math.sin(a), 0.02, -0.11 - 0.02 * math.cos(2 * a))
        c["hips_rot"] = (6.0, 5.0 * math.sin(a), 6.0 * math.sin(a))
        c["spine"] = (6.0, -3.0 * math.sin(a), -4.0 * math.sin(a))
        c["head"] = (-10.0, -2.0 * math.sin(a), 2.0 * math.sin(a))
        c["hand_r"] = (-0.64, -0.20 + 0.10 * math.sin(a + math.pi), 1.05 + 0.02 * math.cos(2 * a))
        c["hand_l"] = (0.64, -0.20 + 0.10 * math.sin(a), 1.05 + 0.02 * math.cos(2 * a))
        return c
    out.append(NA.ProcClip("Walk", n, walk, loop=True, root_vel=(0, -WALK_SPEED, 0), notes="caminata abierta a 1.6 m/s"))

    n = 14
    g2 = T.gait2(ch, n, RUN_SPEED, 0.42, {"r": (-0.36, -0.02, -12.0), "l": (0.36, -0.02, 12.0)}, lift=0.14, toe_off=26.0, heel=-10.0)

    def run(f):
        a = 2.0 * math.pi * f / n
        c = dict(STANCE)
        c.update(g2(f))
        c["hips"] = (-0.05 * math.sin(a), 0.0, -0.10 - 0.035 * math.cos(2 * a - 0.8))
        c["hips_rot"] = (12.0, 4.0 * math.sin(a), 8.0 * math.sin(a))
        c["spine"] = (10.0, -3.0 * math.sin(a), -6.0 * math.sin(a))
        c["head"] = (-16.0, 0.0, 3.0 * math.sin(a))
        c["hand_r"] = (-0.58, -0.10 + 0.22 * math.sin(a + math.pi), 1.18 + 0.04 * math.cos(a))
        c["hand_l"] = (0.58, -0.10 + 0.22 * math.sin(a), 1.18 - 0.04 * math.cos(a))
        c["hand_r_dir"] = (0.0, -0.6, -0.8)
        c["hand_l_dir"] = (0.0, -0.6, -0.8)
        c["fist_r"] = c["fist_l"] = 0.8
        return c
    out.append(NA.ProcClip("Run", n, run, loop=True, root_vel=(0, -RUN_SPEED, 0), notes="trote pesado a 3.4 m/s"))
    return out


# ================================================================== golpes
def harite_r(n, apex, contact, lunge, windup, name, state):
    """Bofetada de la mano derecha (se espeja para la izquierda)."""
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    TELL = P(hips=(0.05, 0.08, -0.16), hips_rot=(2.0, 0.0, -24.0), spine=(2.0, 3.0, -12.0), head=(-8.0, 0.0, 26.0),
             hand_r=(-0.74, 0.34, 1.62), hand_r_dir=(-0.25, 0.35, 0.9), hand_r_palm=(0.0, -1.0, 0.0), elbow_r=(-0.9, 0.1, -0.6),
             hand_l=(0.30, -0.55, 1.44), hand_l_dir=(0.0, -0.45, 0.9), hand_l_palm=(-0.3, -1.0, 0.0), elbow_l=(1.0, -0.1, -0.5),
             fist_r=0.0, fist_l=0.1)
    HOLD = dict(TELL, hips=(0.05, 0.09, -0.17), hand_r=(-0.75, 0.38, 1.63), hips_rot=(2.0, 0.0, -26.0))
    SMEAR = dict(HOLD, hips=(0.0, 0.0, -0.17), hips_rot=(8.0, 0.0, 0.0), spine=(8.0, 0.0, 2.0), head=(-10.0, 0.0, 8.0),
                 hand_r=(-0.48, -0.55, 1.62), hand_r_dir=(0.0, -0.3, 0.95))
    CONTACT = dict(SMEAR, hips=(0.0, -0.10, -0.19), hips_rot=(12.0, 0.0, 22.0), spine=(14.0, -2.0, 14.0), head=(-14.0, 0.0, -14.0),
                   hand_r=(-0.12, -1.02, 1.55), hand_r_dir=(0.05, -0.15, 1.0), hand_r_palm=(0.0, -1.0, 0.1), elbow_r=(-1.0, 0.2, -0.4),
                   hand_l=(0.62, 0.05, 1.20), hand_l_dir=(0.2, 0.3, -0.9), hand_l_palm=(-1.0, 0.0, 0.0), elbow_l=(1.0, 0.4, -0.2))
    FOLLOW = dict(CONTACT, hips_rot=(12.0, 0.0, 28.0), spine=(14.0, -2.0, 18.0), hand_r=(0.02, -1.00, 1.48))
    PUNISH = dict(FOLLOW, hips=(0.0, -0.08, -0.15), hips_rot=(8.0, 0.0, 16.0), spine=(10.0, 0.0, 8.0), head=(-12.0, 0.0, -6.0),
                  hand_r=(-0.30, -0.70, 1.30), hand_r_dir=(0.0, -0.6, 0.6), elbow_r=(-1.0, 0.3, -0.4))
    keys = [
        Key(0, P()),
        Key(8, TELL, "inout"),
        Key(apex, HOLD, "sine"),
        Key(apex + 1, SMEAR, "in"),
        Key(contact, CONTACT, "lin"),
        Key(contact + 2, FOLLOW, "out"),
        Key(contact + 5, PUNISH, "out"),
        Key(n, P(), "sine"),
    ]
    # el pie derecho entra con la mano (medio paso), el izquierdo se arrima después: la guardia queda 'lunge' más adelante
    feet = {"r": [FR(0), FR(apex), FR(contact + 2, lunge * 0.85, pitch=-10.0), FR(contact + 4, lunge * 0.85),
                  FR(contact + 8, lunge)],
            "l": [FL(0), FL(8), FL(apex, pitch=14.0), FL(contact + 6, lunge, ease="out")]}
    return T.TeamClip(name, n, keys, travel=tr, feet=feet, notes="harite; aviso: la mano atrás a la altura del hombro",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, contact + 4], hold=[8, apex],
                                  lunge=lunge, windup=windup, state=state, striker="r", reach=2.2))


def attack1():
    return harite_r(27, 15, 18, 0.6, 0.65, "Attack1", "Attack1")


def attack2():
    """La bofetada izquierda (segunda del tsuppari, encadenada): la derecha espejada con un aviso más corto."""
    c = harite_r(27, 13, 16, 0.6, 0.5, "Attack2", "Attack2")
    keys = []
    for k in c.keys:
        f = k.frame if k.frame != 8 else 6           # aviso más corto: encadenado
        keys.append(Key(f, mirror(k.ctrl), k.ease))
    feet = {"l": [T.FootKey(fk.frame if fk.frame != 8 else 6, -fk.x, fk.y, -fk.yaw, fk.pitch, fk.z, -fk.roll, fk.ease, fk.lift)
                  for fk in c.feet["r"]],
            "r": [T.FootKey(fk.frame if fk.frame != 8 else 6, -fk.x, fk.y, -fk.yaw, fk.pitch, fk.z, -fk.roll, fk.ease, fk.lift)
                  for fk in c.feet["l"]]}
    t = dict(c.timing, hold=[6, c.timing["apex"]], striker="l")
    return T.TeamClip("Attack2", c.frames, keys, travel=c.travel_table, feet=feet, timing=t,
                      notes="harite izquierdo; aviso: la mano izquierda atrás a la altura del hombro")


def attack3():
    """Shiko: el peso pasa al pie izquierdo, la pierna derecha sube abierta al costado con la mano en el muslo y se
    sostiene arriba (aviso: desde arriba, una pierna que sale del contorno), baja de golpe y queda en cuclillas."""
    n, apex, contact = 42, 24, 27
    lunge, windup = 0.2, 0.65
    tr, _ = T.lunge_travel(n, apex, contact, lunge, windup_min=windup)
    SHIFT = P(hips=(0.16, 0.02, -0.12), hips_rot=(4.0, 8.0, 0.0), spine=(4.0, 6.0, 0.0), head=(-10.0, -6.0, 0.0),
              hand_r=(-0.60, -0.24, 1.06), hand_l=(0.56, -0.32, 0.92), hand_l_dir=(0.0, -0.5, -0.8), hand_l_palm=(0.0, 1.0, 0.0))
    UP = P(hips=(0.20, 0.04, -0.06), hips_rot=(2.0, 14.0, 0.0), spine=(6.0, -6.0, 0.0), head=(-10.0, -8.0, 0.0),
           knee_r=(-1.0, -0.4, 0.4),
           hand_r=(-0.58, -0.25, 1.22), hand_r_dir=(-0.2, -0.4, -0.9), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.3, 0.2),
           hand_l=(0.60, -0.30, 0.86), hand_l_dir=(0.1, -0.5, -0.85), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.2, 0.2))
    HOLD = dict(UP, hips=(0.21, 0.04, -0.05), hips_rot=(2.0, 16.0, 0.0))
    SMEAR = dict(HOLD, hips=(0.10, 0.02, -0.18), hips_rot=(10.0, 8.0, 0.0), spine=(10.0, 4.0, 0.0))
    STOMP = P(hips=(0.0, 0.0, -0.34), hips_rot=(16.0, 0.0, 0.0), spine=(14.0, 0.0, 0.0), head=(-20.0, 0.0, 0.0),
              knee_r=(-1.0, -0.4, 0.0), knee_l=(1.0, -0.4, 0.0),
              hand_r=(-0.62, -0.40, 0.70), hand_r_dir=(0.0, -0.3, -0.95), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.0, 0.3),
              hand_l=(0.62, -0.40, 0.70), hand_l_dir=(0.0, -0.3, -0.95), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.0, 0.3))
    BOUNCE = dict(STOMP, hips=(0.0, 0.0, -0.29), spine=(12.0, 0.0, 0.0))
    keys = [
        Key(0, P()),
        Key(6, SHIFT, "inout"),
        Key(14, UP, "out"),
        Key(apex, HOLD, "sine"),
        Key(25, SMEAR, "in"),
        Key(contact, STOMP, "expo_in"),
        Key(29, BOUNCE, "out"),
        Key(31, STOMP, "sine"),
        Key(36, dict(STOMP, hips=(0.0, 0.0, -0.20)), "sine"),
        Key(n, P(), "sine"),
    ]
    # el pie derecho sube al costado (1 m afuera, el tobillo a ~0.9 m) y baja de golpe un poco más abierto
    feet = {"r": [FR(0), FR(6), FR(14, dx=-0.20, yaw=-35.0, z=0.52, roll=-25.0, ease="out"), FR(apex, dx=-0.22, yaw=-35.0, z=0.56, roll=-28.0, ease="sine"),
                  FR(contact, lunge, dx=-0.14, yaw=-28.0, ease="expo_in", lift=0.0), FR(34, lunge, dx=-0.14, yaw=-28.0),
                  FR(40, lunge, lift=0.05)],
            "l": [FL(0), FL(contact + 3), FL(36, lunge, ease="inout")]}
    return T.TeamClip("Attack3", n, keys, travel=tr, feet=feet, notes="shiko; aviso: la pierna derecha arriba al costado",
                      timing=dict(kind="heavy", apex=apex, contact=contact, active=[contact, 31], hold=[14, apex],
                                  lunge=lunge, windup=windup, state="Attack3", striker="foot_r", reach=1.2))


def special():
    """Tachiai (embestida imparable). f0-f12 se agacha hasta la pose del aviso: cuclillas hondas con los dos puños en
    el piso adelante y la cabeza levantada mirando a Kaito (rojo: no se desvía); f12-f14 pausa que tiembla. Sale
    disparado (f14-f18) y desde el contacto corre agachado pisando corto con los brazos adelante: f18-f42 es la fase
    activa que Enemy estira lo que dura el carril (a 11-13 m/s los pies no pueden apoyar clavados: 'slide_ok'). Frena
    derrapando con los brazos abiertos y vuelve a la guardia."""
    n, apex, contact, end = 60, 14, 18, 42
    CROUCH = P(hips=(0.0, 0.14, -0.40), hips_rot=(36.0, 0.0, 0.0), spine=(10.0, 0.0, 0.0), head=(-44.0, 0.0, 0.0),
               knee_r=(-1.0, -0.5, 0.0), knee_l=(1.0, -0.5, 0.0),
               hand_r=(-0.30, -0.58, 0.24), hand_r_dir=(0.0, -0.3, -0.95), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.0, 0.0),
               hand_l=(0.30, -0.58, 0.24), hand_l_dir=(0.0, -0.3, -0.95), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.0, 0.0),
               fist_r=1.0, fist_l=1.0)
    HOLD = dict(CROUCH, hips=(0.0, 0.15, -0.42))
    LAUNCH = P(hips=(0.0, -0.10, -0.24), hips_rot=(32.0, 0.0, 0.0), spine=(14.0, 0.0, 0.0), head=(-40.0, 0.0, 0.0),
               hand_r=(-0.30, -0.75, 1.10), hand_r_dir=(0.0, -0.6, 0.8), hand_r_palm=(0.0, -1.0, 0.0), elbow_r=(-1.0, 0.0, -0.5),
               hand_l=(0.30, -0.75, 1.10), hand_l_dir=(0.0, -0.6, 0.8), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(1.0, 0.0, -0.5),
               fist_r=0.0, fist_l=0.0)
    BRAKE = P(hips=(0.0, 0.10, -0.20), hips_rot=(-8.0, 0.0, 0.0), spine=(-6.0, 0.0, 0.0), head=(-4.0, 0.0, 0.0),
              hand_r=(-0.90, -0.10, 1.40), hand_r_dir=(-0.6, 0.0, 0.8), hand_r_palm=(0.0, -1.0, 0.0), elbow_r=(-1.0, 0.2, -0.3),
              hand_l=(0.90, -0.10, 1.40), hand_l_dir=(0.6, 0.0, 0.8), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(1.0, 0.2, -0.3),
              fist_r=0.0, fist_l=0.0)
    keys = [Key(0, P()), Key(10, CROUCH, "inout"), Key(apex, HOLD, "sine"), Key(16, LAUNCH, "in"), Key(contact, LAUNCH, "out")]
    # carrera: pisadas cortas y rápidas (8 cuadros por ciclo a velocidad 1; el juego la estira o acelera según el carril)
    feet_r, feet_l = [FR(0), FR(8, -0.10, dx=0.06, yaw=-10.0), FR(apex, -0.10, dx=0.06, yaw=-10.0, pitch=20.0)], \
                     [FL(0), FL(8, -0.10, dx=-0.06, yaw=10.0), FL(apex, -0.10, dx=-0.06, yaw=10.0, pitch=20.0)]
    f = contact
    while f < end:
        a = 2.0 * math.pi * (f - contact) / 8.0
        keys.append(Key(f, dict(LAUNCH, hips=(0.03 * math.sin(a), -0.10, -0.24 - 0.04 * math.cos(2 * a)),
                                hips_rot=(32.0, 3.0 * math.sin(a), 6.0 * math.sin(a))), "sine"))
        f += 2
    feet_r += [FR(contact, -0.35, dx=0.06, yaw=-10.0, z=0.12), FR(22, 0.35, dx=0.06, yaw=-10.0), FR(26, -0.35, dx=0.06, yaw=-10.0, z=0.18),
               FR(30, 0.35, dx=0.06, yaw=-10.0), FR(34, -0.35, dx=0.06, yaw=-10.0, z=0.18), FR(38, 0.35, dx=0.06, yaw=-10.0),
               FR(end, -0.30, dx=0.0, yaw=-22.0, z=0.12)]
    feet_l += [FL(contact, 0.30, dx=-0.06, yaw=10.0), FL(22, -0.35, dx=-0.06, yaw=10.0, z=0.18), FL(26, 0.35, dx=-0.06, yaw=10.0),
               FL(30, -0.35, dx=-0.06, yaw=10.0, z=0.18), FL(34, 0.35, dx=-0.06, yaw=10.0), FL(38, -0.35, dx=-0.06, yaw=10.0, z=0.18),
               FL(end, 0.20, dx=0.0)]
    keys += [Key(end, dict(LAUNCH, hips=(0.0, -0.06, -0.22)), "sine"), Key(46, BRAKE, "out"), Key(50, dict(BRAKE, hips=(0.0, 0.06, -0.16)), "sine"),
             Key(n, P(), "sine")]
    feet_r += [FR(45, -0.30, yaw=-22.0, pitch=-14.0, ease="out"), FR(48, -0.30, yaw=-22.0), FR(55, 0.0)]
    feet_l += [FL(47, 0.20), FL(52, 0.0, ease="inout")]
    return T.TeamClip("Special", n, keys, feet={"r": feet_r, "l": feet_l}, tremble=0.0,
                      notes="tachiai: puños en el piso, sale disparado, corre y frena derrapando",
                      timing=dict(kind="unblockable", apex=apex, contact=contact, active=[contact, end], hold=[10, apex],
                                  lunge=0.0, windup=0.8, state="Special", striker="r", slide_ok=80.0, reach=1.0))


# ================================================================== reacciones
def hit():
    """Golpe recibido (0.4 s): la cabeza y el pecho se sacuden atrás, la panza rebota adelante, un pie retrocede."""
    n = 12
    back = 0.2
    PEAK = P(hips=(0.0, 0.08, -0.08), hips_rot=(-8.0, 0.0, 8.0), spine=(-12.0, 0.0, 6.0), head=(14.0, 0.0, 10.0),
             hand_r=(-0.78, -0.05, 1.30), hand_r_dir=(-0.5, 0.0, 0.85), hand_l=(0.74, 0.0, 1.22), hand_l_dir=(0.5, 0.0, 0.85))
    REB = P(hips=(0.0, 0.0, -0.13), hips_rot=(10.0, 0.0, -2.0), spine=(10.0, 0.0, -2.0), head=(-14.0, 0.0, -2.0))
    keys = [Key(0, P()), Key(2, PEAK, "snap"), Key(6, REB, "inout"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(1), FR(6, -back, ease="out"), FR(n, -back)], "l": [FL(0), FL(3, pitch=10.0), FL(9, -back, ease="out")]}
    return T.TeamClip("Hit", n, keys, travel=knock_travel(n, back), feet=feet, notes="golpe recibido: sacudón atrás y rebote")


def parried():
    """Le desviaron la bofetada (la recompensa del parry): el brazo que pegaba sale despedido arriba y afuera, el
    cuerpo se va para atrás con la panza adelante y da dos pasos atrás; a los 0.35 s ya puede seguir el tsuppari."""
    n = 27
    back = 0.55
    KNOCK = P(hips=(0.0, 0.12, -0.10), hips_rot=(-14.0, 0.0, -16.0), spine=(-16.0, 4.0, -10.0), head=(16.0, 0.0, -14.0),
              hand_r=(-0.70, 0.30, 1.85), hand_r_dir=(-0.3, 0.4, 0.85), hand_r_palm=(0.0, -1.0, 0.0), elbow_r=(-1.0, 0.0, 0.0),
              hand_l=(0.85, -0.10, 1.30), hand_l_dir=(0.6, 0.0, 0.8), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(1.0, 0.2, -0.2),
              fist_r=0.0, fist_l=0.0)
    STUMBLE = dict(KNOCK, hips=(0.0, 0.10, -0.15), hips_rot=(-4.0, 3.0, -8.0), spine=(-6.0, 3.0, -6.0), head=(6.0, 0.0, -8.0),
                   hand_r=(-0.72, 0.10, 1.45), hand_l=(0.78, -0.12, 1.18))
    keys = [Key(0, P()), Key(3, KNOCK, "snap"), Key(6, dict(KNOCK, hand_r=(-0.72, 0.34, 1.90)), "out"),
            Key(12, STUMBLE, "inout"), Key(n, P(), "sine")]
    feet = {"l": [FL(0), FL(1, pitch=12.0), FL(7, -back - 0.15, ease="out"), FL(10, -back - 0.15), FL(16, -back, lift=0.06)],
            "r": [FR(0), FR(2), FR(10, -back, pitch=-8.0, ease="out"), FR(12, -back)]}
    return T.TeamClip("Parried", n, keys, travel=knock_travel(n, back), feet=feet,
                      notes="parry recibido: el brazo despedido arriba, dos pasos atrás", timing=dict(sheet=[3, 6, 12, 18]))


def exhausted_pose(a=0.0):
    return P(hips=(0.01 * math.sin(a), 0.08, -0.24 - 0.02 * math.sin(2 * a)), hips_rot=(24.0, 0.0, 0.0),
             spine=(18.0 + 3.0 * math.sin(2 * a), 2.0 * math.sin(a), 0.0), head=(16.0 + 6.0 * math.sin(a), 6.0 * math.cos(a), 8.0 * math.sin(a)),
             breath=0.5 + 0.5 * math.sin(2 * a), knee_r=(-1.0, -0.4, 0.0), knee_l=(1.0, -0.4, 0.0),
             hand_r=(-0.52, -0.42, 0.66 + 0.02 * math.sin(2 * a)), hand_r_dir=(0.1, -0.5, -0.85), hand_r_palm=(0.0, 1.0, 0.0), elbow_r=(-1.0, 0.2, 0.3),
             hand_l=(0.52, -0.42, 0.66 + 0.02 * math.sin(2 * a)), hand_l_dir=(-0.1, -0.5, -0.85), hand_l_palm=(0.0, 1.0, 0.0), elbow_l=(1.0, 0.2, 0.3),
             fist_r=0.2, fist_l=0.2)


def exhausted():
    """Agotado (3.8 s a merced de Kaito, y la pose de la ejecución): las manos en las rodillas, la cabeza colgando que
    gira mareada y la panza que sube y baja de a tirones."""
    n = 48
    keys = [Key(f, exhausted_pose(2.0 * math.pi * f / n), "sine") for f in (0, 12, 24, 36, 48)]
    return T.TeamClip("Exhausted", n, keys, loop=True, feet=PLANTED, notes="agotado: manos en las rodillas, jadea")


def spotted():
    """Alerta y presentación (también la sal del Ōzeki y la finta del bambú, con SumoPoser encima): se palmea los
    muslos con un pisotón corto y levanta las manos abiertas adelante, 'vení'."""
    n = 24
    SLAP = P(hips=(0.0, 0.02, -0.18), hips_rot=(14.0, 0.0, 0.0), spine=(10.0, 0.0, 0.0), head=(-18.0, 0.0, 0.0),
             hand_r=(-0.50, -0.30, 0.78), hand_r_dir=(0.0, -0.3, -0.95), hand_r_palm=(0.0, 1.0, 0.0),
             hand_l=(0.50, -0.30, 0.78), hand_l_dir=(0.0, -0.3, -0.95), hand_l_palm=(0.0, 1.0, 0.0), fist_r=0.0, fist_l=0.0)
    UP = P(hips=(0.0, 0.0, -0.08), hips_rot=(0.0, 0.0, 0.0), spine=(-4.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0),
           hand_r=(-0.50, -0.62, 1.55), hand_r_dir=(0.0, -0.2, 1.0), hand_r_palm=(0.0, -1.0, 0.0), elbow_r=(-1.0, 0.0, -0.5),
           hand_l=(0.50, -0.62, 1.55), hand_l_dir=(0.0, -0.2, 1.0), hand_l_palm=(0.0, -1.0, 0.0), elbow_l=(1.0, 0.0, -0.5),
           fist_r=0.0, fist_l=0.0)
    keys = [Key(0, P()), Key(5, dict(SLAP, hand_r=(-0.62, -0.30, 1.05), hand_l=(0.62, -0.30, 1.05)), "inout"),
            Key(7, SLAP, "expo_in"), Key(9, dict(SLAP, hips=(0.0, 0.02, -0.16)), "out"),
            Key(15, UP, "out"), Key(19, dict(UP, hand_r=(-0.52, -0.60, 1.58), hand_l=(0.52, -0.60, 1.58)), "sine"), Key(n, P(), "sine")]
    feet = {"r": [FR(0), FR(3, z=0.10, ease="out"), FR(7, ease="expo_in", lift=0.0), FR(n)], "l": [FL(0)]}
    return T.TeamClip("Spotted", n, keys, feet=feet, notes="se palmea los muslos con un pisotón y abre las manos")


def death():
    """Muerte (1.5 s; Enemy.DeathRoutine lo corre 0.8 m atrás en ~0.55 s): el golpe lo echa atrás, trastabilla un paso,
    las rodillas ceden y cae sentado con un rebote de la panza, después se va de espaldas como un árbol con los brazos
    abiertos. Termina boca arriba, quieto (el humo lo hace desaparecer)."""
    n = 45
    slide = [-0.8 * math.sin(min(1.0, (f / T.FPS) * 1.8) * math.pi * 0.5) for f in range(n + 1)]
    REC = P(hips=(0.0, 0.10, -0.08), hips_rot=(-10.0, 0.0, 6.0), spine=(-14.0, 0.0, 4.0), head=(18.0, 0.0, 6.0),
            hand_r=(-0.80, 0.0, 1.35), hand_r_dir=(-0.5, 0.0, 0.85), hand_l=(0.80, 0.05, 1.30), hand_l_dir=(0.5, 0.0, 0.85),
            fist_r=0.0, fist_l=0.0)
    SIT = P(hips=(0.0, 0.10, -0.62), hips_rot=(-14.0, 0.0, 0.0), spine=(-8.0, 0.0, 0.0), head=(12.0, 0.0, 0.0),
            knee_r=(-0.8, -0.6, 0.4), knee_l=(0.8, -0.6, 0.4),
            hand_r=(-0.82, 0.10, 0.62), hand_r_dir=(-0.4, 0.2, -0.9), hand_r_palm=(0.0, 0.0, -1.0), elbow_r=(-1.0, 0.3, 0.2),
            hand_l=(0.82, 0.10, 0.62), hand_l_dir=(0.4, 0.2, -0.9), hand_l_palm=(0.0, 0.0, -1.0), elbow_l=(1.0, 0.3, 0.2),
            fist_r=0.0, fist_l=0.0)
    LIE = P(hips=(0.0, 0.18, -0.66), hips_rot=(-78.0, 0.0, 0.0), spine=(-6.0, 0.0, 0.0), head=(16.0, 0.0, 12.0),
            knee_r=(-0.6, -0.5, 0.6), knee_l=(0.6, -0.5, 0.6),
            hand_r=(-0.95, 0.45, 0.26), hand_r_dir=(-0.8, 0.5, 0.0), hand_r_palm=(0.0, 0.0, 1.0), elbow_r=(-1.0, 0.0, 0.3),
            hand_l=(0.95, 0.45, 0.26), hand_l_dir=(0.8, 0.5, 0.0), hand_l_palm=(0.0, 0.0, 1.0), elbow_l=(1.0, 0.0, 0.3),
            fist_r=0.2, fist_l=0.2)
    keys = [Key(0, P()), Key(3, REC, "snap"), Key(10, dict(REC, hips=(0.0, 0.14, -0.14)), "out"),
            Key(20, SIT, "in2"), Key(23, dict(SIT, hips=(0.0, 0.10, -0.58), spine=(4.0, 0.0, 0.0)), "out"),
            Key(26, SIT, "sine"), Key(36, LIE, "in2"), Key(39, dict(LIE, hips=(0.0, 0.18, -0.63), head=(10.0, 0.0, 12.0)), "out"),
            Key(n, LIE, "sine")]
    # la pierna derecha retrocede con el empujón; sentado, los pies quedan adelante con las rodillas arriba
    feet = {"r": [FR(0), FR(2), FR(9, -0.62, ease="out"), FR(16, -0.62), FR(22, -0.62, dx=-0.05, pitch=-30.0)],
            "l": [FL(0), FL(2, pitch=10.0), FL(10, -0.55, ease="out"), FL(22, -0.55, dx=0.05, pitch=-30.0)]}
    return T.TeamClip("Death", n, keys, travel=slide, feet=feet, notes="muerte: cae sentado y después de espaldas",
                      timing=dict(sheet=[3, 10, 20, 26, 36, 45], slide_ok=6.0))
