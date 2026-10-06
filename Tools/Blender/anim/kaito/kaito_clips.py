"""Clips de Kaito: poses clave, curvas y tiempos. Fuente única de los tiempos del FBX (kaitooo.fbx.json).

Espacio C (ver kaito_rig): unidades del archivo (1 u = 0.53 m), frente -Y, su derecha -X, piso z 0.
Giros en grados: x + = adelante, y + = hacia su izquierda, z + = gira a su izquierda (visto desde arriba).
Los pies van en el MUNDO del clip (antes de restar 'travel', el avance que el juego aplica al transform);
la cadera, las manos y la katana van relativas al transform del juego.

Gramática de los golpes de Kaito (es el jugador: el arranque tiene que ser inmediato, pero con peso):
  anticipación corta (2-3 cuadros: la cadera y el hombro se cargan hacia atrás, la hoja sale de la
  silueta) -> golpe de 1-2 cuadros por un arco limpio, el pie de adelante apoya en el impacto -> se pasa
  (follow-through) -> pose de encadenado. La cadera va un cuadro adelante de la hoja, la cabeza uno atrás.
Las poses de encadenado comparten el final de un clip y el principio del siguiente (A1_END = principio
del Corte 2, A2_END = principio del Corte final): el crossfade de 0.03 s del combo nunca salta de pose.

'timing' (cuadros a 30 fps; va al .fbx.json y de ahí salen los números de PlayerConfig):
  apex        carga máxima de la anticipación
  contact     primer cuadro que pega (AttackDef.activeStart = contact / frames)
  active      [a, b] ventana que pega (activeStart, activeEnd)
  combo       desde acá se puede encadenar (comboWindow)
  lunge       [a, b, metros] avance que el JUEGO aplica al transform, lineal (lungeStart, lungeEnd, lunge)
  strike      cuadro del tajo del remate (FinisherStrikeAt = strike / frames)
  phases      tramos con nombre que el código espera en segundos (habilidades)
"""
import copy, math
from mathutils import Vector
import nindo_anim as NA
from nindo_anim import Key, Clip
import kaito_rig as KR
import kaito_gait as G

U = KR.U_PER_M          # metros -> unidades
CLIPS = []
LEAD = {"hips": -0.6, "hips_rot": -0.6, "spine": -0.3, "head": 1.0, "hand_l": 0.6}


def mod(base, **kw):
    p = copy.deepcopy(base)
    p.update(kw)
    return p


def feet(p, r=None, l=None):
    """r / l = (tobillo, giro) de KR.foot_on (o de flat / toe / air)."""
    q = mod(p)
    if r is not None:
        q["foot_r"], q["foot_r_rot"] = r
    if l is not None:
        q["foot_l"], q["foot_l_rot"] = l
    return q


def flat(side, x, y, yaw=0.0):
    return KR.foot_on(side, x, y, 0.0, yaw)


def toe(side, x, y, yaw=0.0, heel=30.0):
    return KR.foot_on(side, x, y, heel, yaw, "toe")


def air(x, y, z, pitch=0.0, yaw=0.0):
    """Pie en el aire: tobillo (x, y, z) con su giro."""
    return (x, y, z), (pitch, 0.0, yaw)


def at_travel(p, travel):
    """La misma pose cuando el cuerpo ya avanzó 'travel' (u): solo se corre lo clavado en el mundo."""
    q = copy.deepcopy(p)
    for k in ("foot_r", "foot_l"):
        x, y, z = q[k]
        q[k] = (x, y - travel, z)
    q["travel"] = travel
    return q


def lunge_travel(frames, f0, f1, meters):
    """Avance (u) en cada cuadro con la ley del juego (PlayerController.TickAttack: velocidad constante entre
    lungeStart y lungeEnd)."""
    L = meters * U
    return [0.0 if f <= f0 else L if f >= f1 else L * (f - f0) / (f1 - f0) for f in range(frames + 1)]


class KClip(Clip):
    """Clip con los adelantos/atrasos ('lag') que se apagan en los 3 primeros y 3 últimos cuadros de un clip suelto:
    así el primer y el último cuadro son EXACTAMENTE las poses clave y los clips encadenados (A1_END -> Corte 2,
    GUARD -> desvío) empalman sin salto. Con el lag completo, una cadera que adelanta 0.6 cuadros arrancaba el
    clip ya metida en el primer tramo."""

    def controls(self, f):
        if self.loop:
            return super().controls(f)
        k = max(0.0, min(1.0, f / 3.0, (self.frames - f) / 3.0))
        keep = self.lag
        self.lag = {c: v * k for c, v in keep.items()}
        try:
            return super().controls(f)
        finally:
            self.lag = keep


def add(name, frames, keys, loop=False, lag=None, timing=None, events=None, notes="", travel=None):
    """keys: (cuadro, pose, curva[, {canal: curva, 'stop': (canales,)}]). travel: avance del juego por cuadro
    (lunge_travel): se escribe en cada clave y se interpola lineal (es una recta en el juego)."""
    def key(k):
        ch = dict(k[3]) if len(k) > 3 else {}
        stops = ch.pop("stop", ())
        p = copy.deepcopy(k[1])
        if travel is not None:
            p["travel"] = travel[k[0]]
            ch.setdefault("travel", "lin")
        return Key(k[0], p, k[2], ch, stops)
    ks = [key(k) for k in keys]
    if travel is not None:
        # una clave de avance en cada quiebre de la recta (si no, el tramo entre dos claves lo curvaría)
        have = {k.frame for k in ks}
        for f in range(1, frames):
            if f not in have and (travel[f] - travel[f - 1]) != (travel[f + 1] - travel[f]):
                prev = max((k for k in ks if k.frame < f), key=lambda k: k.frame)
                nxt = min((k for k in ks if k.frame > f), key=lambda k: k.frame)
                ks.append(_travel_key(f, travel[f], prev, nxt))
        ks.sort(key=lambda k: k.frame)
    c = KClip(name, frames, ks, loop=loop, lag=LEAD if lag is None else lag, timing=timing or {}, events=events, notes=notes)
    CLIPS.append(c)
    return c


def _travel_key(f, tv, prev, nxt):
    """Clave intermedia que solo fija el avance: el resto de los canales se completa interpolando prev -> nxt
    en ese cuadro (así la clave no cambia la pose)."""
    tmp = Clip("_", nxt.frame - prev.frame, [Key(0, prev.ctrl, "lin"), Key(nxt.frame - prev.frame, nxt.ctrl, nxt.ease, nxt.ease_ch)])
    ctrl = {ch: tmp.sample(f - prev.frame, ch) for ch in set(prev.ctrl) | set(nxt.ctrl)}
    ctrl = {k: (tuple(v) if isinstance(v, Vector) else v) for k, v in ctrl.items()}
    ctrl["travel"] = tv
    return Key(f, ctrl, "lin", dict(nxt.ease_ch, travel="lin"))


# =========================================================================== poses base
R_FOOT = (-0.22, -0.14, 6.0)          # huella del pie derecho (adelante) en guardia: x, y, giro
L_FOOT = (0.30, 0.22, 34.0)           # el izquierdo atrás y abierto

READY = feet({
    "hips": (0.0, 0.02, -0.07), "hips_rot": (3.0, 0.0, 14.0), "spine": (7.0, 0.0, -9.0), "head": (-7.0, 0.0, -4.0),
    "clav_r": (0.0, 0.0, 0.0), "clav_l": (0.0, 0.0, 0.0),
    # katana baja a su derecha, la punta adelante y afuera apenas levantada: desde arriba es una línea larga
    # que sale de la silueta hacia el enemigo; el filo mira abajo-adelante
    "grip": (-0.56, -0.3, 1.0), "blade": (-0.5, -0.8, 0.3), "edge": (-0.25, -0.2, -0.95), "elbow_r": (-0.7, 0.5, -0.5),
    "hand_l": (0.36, -0.34, 1.18), "hand_l_dir": (-0.3, -0.75, -0.4), "hand_l_up": (0.8, 0.0, 0.6), "elbow_l": (0.7, 0.4, -0.6),
    "fingers_l": 0.55, "grip_l": 0.0,
    "knee_r": (-0.25, -1.0, 0.0), "knee_l": (0.55, -1.0, 0.0),
    # escalares explícitos en la pose base: una clave sin el canal tomaría el valor de su vecina
    "lift": 0.0, "breath": 0.0, "tremble": 0.0, "arm_space": 0.0,
}, r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))


# =========================================================================== guardia que respira
_breath = mod(READY, breath=1.0, hips=(0.012, 0.025, -0.085), grip=(-0.565, -0.305, 1.02), blade=(-0.51, -0.79, 0.32),
              hand_l=(0.365, -0.335, 1.21), head=(-9.0, 0.0, -3.0))
_shift = mod(READY, hips=(-0.03, 0.02, -0.08), hips_rot=(3.0, 0.0, 12.0), spine=(7.0, -1.5, -8.0), head=(-6.0, 1.5, -6.0),
             grip=(-0.55, -0.31, 0.98), blade=(-0.49, -0.81, 0.29))
add("Idle", 72, [(0, READY, "sine"), (24, _breath, "sine"), (44, _shift, "sine"), (60, mod(_breath, breath=0.5), "sine"),
                 (72, READY, "sine")], loop=True, lag={"head": 3.0, "grip": 2.0, "hand_l": 3.0, "spine": 1.0},
    notes="guardia de una mano: katana baja adelante, respiración y un cambio de peso por vuelta (2.4 s)")


# =========================================================================== locomoción
def body_walk(ph):
    """Paso corto y ligero (chibi): la katana cuelga a su derecha con la punta atrás y abajo."""
    s2 = math.cos(G.TAU * (2.0 * ph - 0.62))
    yaw = -6.0 * math.cos(G.TAU * (ph + 0.02))
    a = G.TAU * (ph - 0.5 - 0.06)
    sw = math.cos(G.TAU * (ph - 0.06))
    return {
        "hips": (0.03 * math.cos(G.TAU * (ph - 0.25)), 0.03, -0.035 + 0.025 * s2), "hips_rot": (3.0, 2.5 * math.cos(G.TAU * (ph - 0.25)), yaw),
        "spine": (4.0, -1.5 * math.cos(G.TAU * (ph - 0.25)), -yaw * 1.2), "head": (-4.0, 1.0 * math.cos(G.TAU * (ph - 0.3)), yaw * 0.3),
        "grip": (-0.5 + 0.01 * sw, -0.06 + 0.12 * sw, 0.95 + 0.02 * abs(sw)), "blade": (-0.28, 0.82, -0.5),
        "edge": (0.0, 0.52, 0.85), "elbow_r": (-0.7, 0.6, -0.3),
        "hand_l": (0.43, -0.02 - 0.2 * math.cos(a), 1.0 + 0.06 * math.cos(a)), "hand_l_dir": (0.15, -0.35 * math.cos(a), -0.95),
        "hand_l_up": (1.0, 0.0, 0.0), "elbow_l": (0.6, 0.8, -0.2), "fingers_l": 0.45,
        "knee_r": (-0.12, -1.0, 0.0), "knee_l": (0.12, -1.0, 0.0),
    }


def body_jog(ph):
    s2 = math.cos(G.TAU * (2.0 * ph - 2.0 * 0.12))
    yaw = -8.0 * math.cos(G.TAU * (ph + 0.03))
    a = G.TAU * (ph - 0.5 - 0.05)
    sw = math.cos(G.TAU * (ph - 0.05))
    return {
        "hips": (0.015 * math.sin(G.TAU * ph), 0.03, -0.05 + 0.04 * s2), "hips_rot": (6.0, 2.5 * math.cos(G.TAU * 2 * (ph - 0.12)), yaw),
        "spine": (6.0, 0.0, -yaw * 1.3), "head": (-4.0, 0.0, yaw * 0.35),
        "grip": (-0.5 - 0.02 * sw, 0.18 + 0.09 * sw, 0.98 + 0.03 * sw), "blade": (-0.3, 0.85, -0.42),
        "edge": (0.0, 0.45, 0.89), "elbow_r": (-0.7, 0.5, -0.5),
        "hand_l": (0.34 - 0.03 * math.cos(a), 0.02 - 0.2 * math.cos(a), 1.12 + 0.07 * math.cos(a)),
        "hand_l_dir": (0.0, -0.4 * math.cos(a) - 0.2, -0.9), "hand_l_up": (1.0, 0.0, 0.0), "elbow_l": (0.5, 0.9, -0.3), "fingers_l": 0.8,
        "knee_r": (-0.1, -1.0, 0.05), "knee_l": (0.1, -1.0, 0.05),
    }


def body_run(ph):
    """Carrera: cadera que se hunde en cada apoyo, todo el cuerpo inclinado (ProceduralMotion le suma 9°) y
    contragiro; la katana va atrás como una cola: desde arriba alarga la silueta contra la carrera."""
    s2 = math.cos(G.TAU * (2.0 * ph - 2.0 * 0.0833))      # mínimo a mitad de cada apoyo (2 cuadros de 12)
    yaw = -10.0 * math.cos(G.TAU * (ph + 0.04))
    lean = 10.0 + 2.5 * math.cos(G.TAU * (2.0 * ph - 0.3))
    a = G.TAU * (ph - 0.5 - 0.04)                          # el brazo izquierdo va contra la pierna izquierda
    hand_l = (0.33 - 0.03 * math.cos(a), 0.04 - 0.25 * math.cos(a), 1.14 + 0.1 * math.cos(a) + 0.04 * math.sin(a))
    swing_r = math.cos(G.TAU * (ph - 0.04))
    return {
        "hips": (0.012 * math.sin(G.TAU * ph), 0.06, -0.07 + 0.07 * s2), "hips_rot": (lean, 3.0 * math.cos(G.TAU * 2 * (ph - 0.1)), yaw),
        "spine": (8.0, 0.0, -yaw * 1.4), "head": (-(lean + 8.0) * 0.3 + 2.0 * math.cos(G.TAU * 2 * (ph - 0.3)), 0.0, yaw * 0.35),
        "grip": (-0.47 - 0.03 * swing_r, 0.37 + 0.07 * swing_r, 0.95 + 0.03 * swing_r), "blade": (-0.3, 0.92, 0.25),
        "edge": (0.0, 0.25, -0.97), "elbow_r": (-0.7, 0.4, -0.6),
        "hand_l": hand_l, "hand_l_dir": (0.0, -0.45 * math.cos(a) - 0.2, -0.9), "hand_l_up": (1.0, 0.0, 0.0),
        "elbow_l": (0.5, 0.9, -0.3), "fingers_l": 0.9,
        "knee_r": (-0.1, -1.0, 0.1), "knee_l": (0.1, -1.0, 0.1),
    }


# velocidades de los umbrales del blend tree (generate_assets.py KAITO_LOCO): Speed = v / 6.2
WALK_MPS, JOG_MPS, RUN_MPS = 1.2, 3.4, 6.2
WALK_SWING = [(0.5, -0.02, 0.33, -6.0)]
WALK = G.Gait("Walk", WALK_MPS, 18, {
    "l": G.FootCycle("L", WALK_MPS * U, 0.6, 0.62, 0.23, y_mid=0.04, heel=0.18, toe=0.3, pitch_in=-14.0, pitch_out=26.0,
                     swing=WALK_SWING, yaw=8.0),
    "r": G.FootCycle("R", WALK_MPS * U, 0.6, 0.62, -0.23, y_mid=0.04, heel=0.18, toe=0.3, pitch_in=-14.0, pitch_out=26.0,
                     swing=WALK_SWING, yaw=-8.0),
}, body_walk, notes=f"paso a {WALK_MPS} m/s: 18 cuadros, talón -> punta")
JOG_SWING = [(0.3, 0.28, 0.45, 40.0), (0.7, -0.24, 0.4, -4.0)]
JOG = G.Gait("Jog", JOG_MPS, 14, {
    "l": G.FootCycle("L", JOG_MPS * U, 14 / 30.0, 0.3, 0.21, y_mid=0.08, pitch_in=4.0, pitch_out=40.0, toe=1.0, swing=JOG_SWING,
                     yaw=6.0, pivot="toe"),
    "r": G.FootCycle("R", JOG_MPS * U, 14 / 30.0, 0.3, -0.21, y_mid=0.08, pitch_in=4.0, pitch_out=40.0, toe=1.0, swing=JOG_SWING,
                     yaw=-6.0, pivot="toe"),
}, body_jog, notes=f"trote a {JOG_MPS} m/s: 14 cuadros")
RUN_SWING = [(0.18, 0.40, 0.55, 62.0), (0.45, 0.10, 0.62, 30.0), (0.75, -0.42, 0.42, -6.0)]
RUN = G.Gait("Run", RUN_MPS, 12, {
    "l": G.FootCycle("L", RUN_MPS * U, 0.4, 2.0 / 12.0, 0.2, y_mid=0.1, pitch_in=6.0, pitch_out=48.0, toe=1.0, swing=RUN_SWING,
                     yaw=6.0, pivot="toe"),
    "r": G.FootCycle("R", RUN_MPS * U, 0.4, 2.0 / 12.0, -0.2, y_mid=0.1, pitch_in=6.0, pitch_out=48.0, toe=1.0, swing=RUN_SWING,
                     yaw=-6.0, pivot="toe"),
}, body_run, notes="carrera a 6.2 m/s (PlayerConfig.runSpeed): 12 cuadros, apoyo de 2 cuadros por pie sobre la bola")
for _g in (WALK, JOG, RUN):
    CLIPS.append(_g.clip())


# =========================================================================== golpes: pies relativos al cuerpo
def fr(side, x, y_rel, tv, yaw=0.0, heel=0.0):
    """Pie apoyado (o en punta con 'heel' grados) a 'y_rel' del cuerpo cuando ya avanzó 'tv' (u): la huella en
    el mundo es y_rel - tv (dos claves con la misma huella en el mundo = pie clavado)."""
    return toe(side, x, y_rel - tv, yaw, heel) if heel else flat(side, x, y_rel - tv, yaw)


def fa(x, y_rel, z, tv, pitch=0.0, yaw=0.0):
    """Pie en el aire a 'y_rel' del cuerpo."""
    return air(x, y_rel - tv, z, pitch, yaw)


# =========================================================================== corte 1 (derecha -> izquierda)
# carga: la hoja atrás de su hombro derecho y AFUERA (desde arriba sale de la silueta por la derecha), cadera
# cargada a la derecha; salto corto hacia adelante (los 0.9 m los mueve el juego), los dos pies en el aire en
# el tajo, la hoja barre por su derecha hasta cruzar adelante (impacto) y termina envuelta a su izquierda;
# el pie derecho apoya enseguida del impacto y el izquierdo dos cuadros después
A1_N = 13
A1_TR = lunge_travel(A1_N, 1, 5, 0.9)
T1 = A1_TR
_a1_cock = feet(mod(READY, hips=(0.0, 0.08, -0.1), hips_rot=(0.0, 0.0, -20.0), spine=(2.0, -3.0, -18.0), head=(-4.0, 0.0, 16.0),
                    clav_r=(0.0, 6.0, 0.0), grip=(-0.66, 0.08, 1.48), blade=(-0.62, 0.5, 0.6), edge=(-0.3, -0.85, 0.3),
                    elbow_r=(-0.6, 0.5, 0.5), hand_l=(0.48, -0.42, 1.32), hand_l_dir=(0.1, -0.9, 0.1), hand_l_up=(0.3, 0.0, 1.0),
                    fingers_l=0.15),
                r=fr("R", -0.22, -0.14 + T1[2], T1[2], 6.0, 22.0), l=fr("L", 0.3, 0.52, T1[2], 34.0, 40.0))
_a1_sweep = feet(mod(_a1_cock, hips=(0.0, -0.02, -0.06), hips_rot=(10.0, 0.0, -4.0), spine=(9.0, 0.0, -6.0), head=(-8.0, 0.0, 6.0),
                     grip=(-0.62, -0.36, 1.36), blade=(-0.92, -0.25, 0.2), edge=(0.2, -0.95, 0.1), elbow_r=(-0.6, 0.4, -0.3)),
                 r=fa(-0.24, -0.45, 0.42, T1[3], -10.0, 6.0), l=fa(0.3, 0.35, 0.4, T1[3], 30.0, 30.0))
_a1_hit = feet(mod(READY, hips=(0.0, -0.1, -0.12), hips_rot=(14.0, 0.0, 16.0), spine=(12.0, 0.0, 10.0), head=(-14.0, 0.0, -10.0),
                   clav_r=(0.0, 0.0, 8.0), grip=(-0.2, -0.64, 1.2), blade=(0.15, -0.97, -0.1), edge=(0.97, 0.15, 0.0),
                   elbow_r=(-0.5, 0.1, -0.9), hand_l=(0.55, 0.05, 1.25), hand_l_dir=(0.6, 0.6, -0.3), hand_l_up=(0.0, 0.0, 1.0),
                   fingers_l=0.3),
               r=fa(-0.24, -0.5, 0.27, T1[4], -14.0, 4.0), l=fa(0.3, 0.12, 0.36, T1[4], 20.0, 30.0))
_a1_cross = feet(mod(_a1_hit, hips_rot=(14.0, 0.0, 26.0), spine=(12.0, 0.0, 18.0), head=(-13.0, 0.0, -16.0),
                     grip=(0.12, -0.52, 1.06), blade=(0.72, -0.6, -0.33), edge=(0.6, 0.78, 0.1), elbow_r=(-0.3, -0.1, -0.9)),
                 r=fr("R", -0.24, -0.2, T1[5], 2.0), l=fa(0.3, 0.3, 0.3, T1[5], 10.0, 30.0))
_a1_over = feet(mod(_a1_cross, hips=(0.02, -0.06, -0.15), hips_rot=(12.0, 0.0, 34.0), spine=(10.0, 0.0, 22.0), head=(-12.0, 0.0, -20.0),
                    grip=(0.3, -0.32, 0.98), blade=(0.8, 0.35, -0.45), edge=(0.3, 0.92, 0.1), elbow_r=(-0.2, -0.2, -0.9)),
                r=fr("R", -0.24, -0.2, T1[6], 2.0), l=fr("L", 0.3, 0.3, T1[6], 30.0))
A1_END = feet(mod(READY, hips=(0.0, 0.0, -0.11), hips_rot=(6.0, 0.0, 26.0), spine=(8.0, 0.0, 14.0), head=(-8.0, 0.0, -16.0),
                  grip=(0.18, -0.4, 0.98), blade=(0.7, -0.45, -0.55), edge=(0.35, 0.85, -0.2), elbow_r=(-0.3, 0.0, -0.9),
                  hand_l=(0.5, 0.0, 1.15), hand_l_dir=(0.4, 0.5, -0.7), hand_l_up=(0.3, 0.0, 1.0), fingers_l=0.5),
              r=flat("R", -0.24, -0.2, 2.0), l=flat("L", 0.3, 0.3, 30.0))
# a f8 ya está en la pose de empalme (el combo se puede encadenar desde f7: el crossfade de 0.03 s no salta)
_a1_settle = feet(mod(A1_END, hips=(0.0, 0.0, -0.14), blade=(0.74, -0.4, -0.54)), r=fr("R", -0.24, -0.2, T1[8], 2.0),
                  l=fr("L", 0.3, 0.3, T1[8], 30.0))
add("Attack1", A1_N, [
    (0, READY, "sine"), (2, _a1_cock, "out"), (3, _a1_sweep, "in2"), (4, _a1_hit, "lin"), (5, _a1_cross, "out2"),
    (6, _a1_over, "out"), (8, _a1_settle, "sine"), (13, at_travel(A1_END, T1[13]), "sine")],
    travel=A1_TR,
    timing={"apex": 2, "contact": 4, "active": [4, 7], "combo": 7, "lunge": [1, 5, 0.9], "chain_to": "A1_END"},
    events=[{"frame": 4, "fn": "Strike"}, {"frame": 5, "fn": "FootR"}, {"frame": 6, "fn": "FootL"}],
    notes="tajo de derecha a izquierda con salto corto; el pie derecho apoya enseguida del impacto, termina envuelto a la izquierda")

# =========================================================================== corte 2 (revés ascendente)
# desde A1_END: la muñeca se enrosca atrás a su izquierda y la hoja sube cruzando por delante (impacto) hasta
# arriba a su derecha; el pie izquierdo (el de atrás) sale enseguida y entra adelante al terminar el avance
A2_N = 11
A2_TR = lunge_travel(A2_N, 0, 4, 1.0)
T2 = A2_TR
_a2_coil = feet(mod(A1_END, hips=(0.0, 0.0, -0.14), hips_rot=(8.0, 0.0, 32.0), spine=(10.0, 0.0, 22.0), head=(-8.0, 0.0, -22.0),
                    grip=(0.38, -0.14, 0.88), blade=(0.6, 0.6, -0.5), edge=(-0.5, 0.0, -0.85), elbow_r=(-0.1, 0.2, -0.95)),
                r=fr("R", -0.24, -0.2 + T2[1], T2[1], 2.0), l=fa(0.3, 0.4, 0.33, T2[1], 30.0, 30.0))
_a2_low = feet(mod(_a2_coil, hips=(0.0, -0.06, -0.14), hips_rot=(10.0, 0.0, 18.0), spine=(11.0, 0.0, 10.0), head=(-11.0, 0.0, -8.0),
                   grip=(0.18, -0.55, 0.98), blade=(0.6, -0.75, -0.25), edge=(-0.3, 0.0, -0.95)),
               r=fr("R", -0.24, 0.5, T2[2], 2.0, 32.0), l=fa(0.25, -0.1, 0.38, T2[2], 0.0, 15.0))
_a2_hit = feet(mod(READY, hips=(0.0, -0.1, -0.12), hips_rot=(10.0, 0.0, -4.0), spine=(10.0, 4.0, -8.0), head=(-12.0, -4.0, 6.0),
                   clav_r=(0.0, 6.0, 0.0), grip=(-0.2, -0.64, 1.3), blade=(-0.1, -0.95, 0.3), edge=(-0.85, 0.0, 0.5),
                   elbow_r=(-0.5, 0.3, -0.8), hand_l=(0.5, 0.15, 1.15), hand_l_dir=(0.5, 0.5, -0.7), hand_l_up=(0.2, 0.0, 1.0),
                   fingers_l=0.4),
               r=fa(-0.28, 0.35, 0.36, T2[3], 30.0, 0.0), l=fa(0.22, -0.4, 0.26, T2[3], -14.0, 10.0))
_a2_rise = feet(mod(_a2_hit, hips_rot=(8.0, 0.0, -16.0), spine=(7.0, 5.0, -16.0), head=(-11.0, -5.0, 14.0), clav_r=(0.0, 12.0, 0.0),
                    grip=(-0.4, -0.45, 1.6), blade=(-0.7, -0.45, 0.55), edge=(-0.6, 0.35, -0.7), elbow_r=(-0.6, 0.3, -0.2)),
                r=fa(-0.3, 0.1, 0.32, T2[4], 10.0, 0.0), l=fr("L", 0.22, -0.3, T2[4], 10.0))
_a2_over = feet(mod(_a2_rise, hips=(0.0, -0.06, -0.1), hips_rot=(6.0, 0.0, -26.0), spine=(4.0, 6.0, -24.0), head=(-10.0, -6.0, 20.0),
                    clav_r=(0.0, 14.0, 0.0), grip=(-0.5, -0.2, 1.76), blade=(-0.55, 0.38, 0.74), edge=(-0.5, -0.82, 0.2),
                    elbow_r=(-0.7, 0.4, 0.2)),
                r=fa(-0.3, 0.2, 0.3, T2[5], 0.0, 0.0), l=fr("L", 0.22, -0.3, T2[5], 10.0))
A2_END = feet(mod(READY, hips=(0.0, 0.04, -0.09), hips_rot=(2.0, 0.0, -22.0), spine=(2.0, 4.0, -20.0), head=(-6.0, -4.0, 18.0),
                  clav_r=(0.0, 10.0, 0.0), grip=(-0.46, 0.0, 1.72), blade=(-0.45, 0.55, 0.7), edge=(-0.4, -0.75, 0.35),
                  elbow_r=(-0.7, 0.4, 0.3), hand_l=(0.25, -0.3, 1.45), hand_l_dir=(-0.4, -0.5, 0.6), hand_l_up=(0.5, -0.5, 0.5),
                  fingers_l=0.35),
              r=flat("R", -0.3, 0.18, 0.0), l=flat("L", 0.22, -0.3, 10.0))
add("Attack2", A2_N, [
    (0, A1_END, "sine"), (1, _a2_coil, "out"), (2, _a2_low, "in2"), (3, _a2_hit, "lin"), (4, _a2_rise, "out2"),
    (5, _a2_over, "out"), (7, feet(mod(A2_END, hips=(0.0, 0.03, -0.12)), r=fr("R", -0.3, 0.18, T2[7], 0.0),
                                   l=fr("L", 0.22, -0.3, T2[7], 10.0)), "sine"),
    (11, at_travel(A2_END, T2[11]), "sine")],
    travel=A2_TR,
    timing={"apex": 1, "contact": 3, "active": [3, 6], "combo": 6, "lunge": [0, 4, 1.0], "chain_from": "A1_END", "chain_to": "A2_END"},
    events=[{"frame": 3, "fn": "Strike"}, {"frame": 4, "fn": "FootL"}, {"frame": 7, "fn": "FootR"}],
    notes="revés ascendente desde la izquierda baja; el pie izquierdo entra adelante al final del avance, la hoja termina alta a la derecha")

# =========================================================================== corte final (salto a dos manos)
# desde A2_END: sube la hoja con las dos manos atrás de su hombro derecho (la hoja sale de la silueta hacia
# atrás y afuera: se ve desde arriba aunque la cabeza tape las manos), se agacha, salta 1.6 m, la hoja pasa
# por arriba y baja en diagonal: cruza adelante en el impacto y queda baja a su izquierda al caer; 3 cuadros
# de impacto quieto
A3_N = 20
A3_TR = lunge_travel(A3_N, 3, 7, 1.6)
T3 = A3_TR
_a3_raise = feet(mod(A2_END, hips=(0.0, 0.1, -0.22), hips_rot=(-4.0, 0.0, -26.0), spine=(-8.0, 4.0, -18.0), head=(-2.0, -4.0, 20.0),
                     clav_r=(0.0, 14.0, 0.0), clav_l=(0.0, -10.0, 0.0), grip=(-0.22, 0.2, 1.94), blade=(-0.55, 0.65, 0.52),
                     edge=(-0.3, -0.5, 0.8), elbow_r=(-0.8, 0.2, 0.4), grip_l=1.0, elbow_l=(0.8, 0.2, 0.2), fingers_l=1.0),
                 r=fr("R", -0.3, 0.18, T3[3], 0.0, 26.0), l=fr("L", 0.22, -0.3, T3[3], 10.0, 26.0))
_a3_air = feet(mod(_a3_raise, hips=(0.0, 0.02, -0.08), hips_rot=(4.0, 0.0, -22.0), spine=(-4.0, 3.0, -16.0), lift=0.36,
                   grip=(-0.2, 0.18, 1.96), blade=(-0.53, 0.62, 0.58)),
               r=fa(-0.3, -0.1, 0.62, T3[5], -10.0, 0.0), l=fa(0.24, 0.2, 0.7, T3[5], 30.0, 10.0))
_a3_over = feet(mod(_a3_air, hips=(0.0, -0.04, -0.06), hips_rot=(10.0, 0.0, -8.0), spine=(6.0, 0.0, -6.0), head=(-12.0, 0.0, 6.0), lift=0.2,
                    grip=(-0.15, -0.22, 2.0), blade=(-0.35, -0.25, 0.9), edge=(-0.1, -0.95, -0.2)),
                r=fa(-0.3, -0.4, 0.42, T3[6], -14.0, 2.0), l=fa(0.26, 0.3, 0.45, T3[6], 20.0, 20.0))
_a3_hit = feet(mod(READY, lift=0.0, hips=(0.0, -0.12, -0.15), hips_rot=(18.0, 0.0, 10.0), spine=(18.0, 0.0, 6.0), head=(-22.0, 0.0, -6.0),
                   clav_r=(0.0, -4.0, 4.0), clav_l=(0.0, 4.0, 4.0), grip=(-0.06, -0.62, 1.32), blade=(0.2, -0.95, 0.05),
                   edge=(0.1, 0.0, -1.0), elbow_r=(-0.5, 0.2, -0.8), grip_l=1.0, elbow_l=(0.6, 0.3, -0.7), fingers_l=1.0),
               r=fr("R", -0.27, -0.42, T3[7], 4.0), l=fr("L", 0.3, 0.38, T3[7], 26.0, 34.0))
A3_LOW = feet(mod(_a3_hit, hips=(0.0, -0.16, -0.27), hips_rot=(22.0, 0.0, 18.0), spine=(22.0, 0.0, 10.0), head=(-26.0, 0.0, -10.0),
                  grip=(0.08, -0.6, 0.82), blade=(0.5, -0.75, -0.43), edge=(0.35, -0.25, -0.9)),
              r=fr("R", -0.27, -0.42, T3[8], 4.0), l=fr("L", 0.3, 0.38, T3[8], 26.0, 34.0))
_a3_hold = feet(mod(A3_LOW, hips=(0.0, -0.17, -0.29), grip=(0.1, -0.61, 0.8), blade=(0.51, -0.74, -0.43), head=(-27.0, 0.0, -10.0)),
                r=fr("R", -0.27, -0.42, T3[11], 4.0), l=fr("L", 0.3, 0.38, T3[11], 26.0, 34.0))
_a3_rec = feet(mod(READY, hips=(0.0, 0.0, -0.14), grip_l=0.4, fingers_l=0.8),
               r=fa(-0.24, -0.3, 0.3, T3[15], 0.0, 6.0), l=fr("L", 0.3, 0.38, T3[15], 30.0))
add("Attack3", A3_N, [
    (0, A2_END, "sine"), (3, _a3_raise, "out"), (5, _a3_air, "inout"), (6, _a3_over, "in2"), (7, _a3_hit, "lin"),
    (8, A3_LOW, "out"), (11, _a3_hold, "lin"), (15, _a3_rec, "sine"),
    (17, feet(mod(READY, hips=(0.0, 0.01, -0.09)), r=fr("R", R_FOOT[0], R_FOOT[1], T3[17], R_FOOT[2]), l=fa(0.3, 0.3, 0.32, T3[17], 10.0, 32.0)),
     "sine"),
    (20, feet(READY, r=fr("R", R_FOOT[0], R_FOOT[1], T3[20], R_FOOT[2]), l=fr("L", L_FOOT[0], L_FOOT[1], T3[20], L_FOOT[2])), "sine")],
    travel=A3_TR,
    timing={"apex": 3, "contact": 7, "active": [7, 10], "hold": [8, 11], "lunge": [3, 7, 1.6], "chain_from": "A2_END",
            "chain_to": "READY"},
    events=[{"frame": 7, "fn": "Strike"}, {"frame": 7, "fn": "Land"}],
    notes="salto con las dos manos, la hoja pasa por arriba y cruza en diagonal; cae con la hoja baja y queda quieto 3 cuadros")


# =========================================================================== dash mágico
# El juego lo toca a 1.4x (PlayerController.TryDash): 14 cuadros = 0.33 s reales, el tramo que viaja (0.26 s)
# es f0-f11 y el resto el freno. Sin anticipación: el código ya lo mueve a 25 m/s en el primer cuadro, así
# que arranca casi en la pose aerodinámica (cuerpo bajo, katana y brazo izquierdo atrás, una rodilla arriba y
# la otra pierna estirada: desde arriba es una flecha); frena con el pie izquierdo que patina y la katana que
# sigue de largo por la inercia
# los brazos van en el espacio del pecho (arm_space): con el cuerpo inclinado quedan atrás y arriba como alas
_dash = feet(mod(READY, hips=(0.0, -0.04, -0.2), hips_rot=(24.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0), head=(-22.0, 0.0, 0.0),
                 arm_space=1.0, grip=(-0.44, 0.36, 1.08), blade=(-0.2, 0.96, 0.18), edge=(0.0, 0.2, -0.98), elbow_r=(-0.6, 0.6, 0.3),
                 hand_l=(0.42, 0.3, 1.12), hand_l_dir=(0.15, 0.9, -0.3), hand_l_up=(1.0, 0.0, 0.0), elbow_l=(0.6, 0.6, 0.3),
                 fingers_l=0.1),
             r=air(-0.22, 0.4, 0.33, 50.0, -4.0), l=air(0.2, -0.3, 0.4, 6.0, 8.0))
_dash_launch = feet(mod(_dash, hips=(0.0, -0.02, -0.22), hips_rot=(18.0, 0.0, 0.0)), r=toe("R", -0.22, 0.26, -4.0, 45.0),
                    l=air(0.2, -0.22, 0.36, 4.0, 8.0))
_dash_b = feet(mod(_dash, hips=(0.0, -0.04, -0.18), grip=(-0.45, 0.37, 1.1), hand_l=(0.43, 0.32, 1.14), head=(-21.0, 0.0, 0.0)),
               r=air(-0.22, 0.42, 0.35, 54.0, -4.0), l=air(0.2, -0.28, 0.42, 8.0, 8.0))
_dash_brake = feet(mod(READY, hips=(0.0, 0.1, -0.17), hips_rot=(-6.0, 0.0, 4.0), spine=(-2.0, 0.0, -4.0), head=(-6.0, 0.0, 0.0),
                       arm_space=0.0, grip=(-0.56, -0.24, 0.94), blade=(-0.4, -0.88, -0.2), edge=(-0.2, -0.1, -0.97),
                       hand_l=(0.4, -0.1, 1.15), hand_l_dir=(0.2, -0.5, -0.8), fingers_l=0.4),
                   r=toe("R", -0.24, 0.3, -4.0, 30.0), l=KR.foot_on("L", 0.24, -0.36, -14.0, 10.0, "heel"))
DASH_END = feet(mod(READY, hips=(0.0, 0.05, -0.1)), r=flat("R", -0.24, 0.24, -2.0), l=flat("L", 0.24, -0.3, 12.0))
add("Dash", 14, [(0, _dash_launch, "lin"), (2, _dash, "out"), (6, _dash_b, "sine"), (10, _dash, "sine"),
                 (12, _dash_brake, "out"), (14, DASH_END, "sine")],
    timing={"travel_frames": [0, 11], "slide_ok": True, "play_speed": 1.4},
    notes="se toca a 1.4x: f0-f11 viaja (0.26 s), f11-f14 frena con el pie izquierdo patinando")

# =========================================================================== parry
# GUARDIA: la hoja cruzada adelante a la altura del mentón, la punta a su izquierda y el filo hacia afuera, la
# palma izquierda apoyada en el lomo: desde arriba es una barra que cruza adelante de la cabeza. Sale en 2
# cuadros (la ventana del parry ya corre) y espera temblando; si no llegó nada, en 0.28 s vuelve a la guardia
GUARD = feet(mod(READY, hips=(0.0, 0.04, -0.13), hips_rot=(6.0, 0.0, 10.0), spine=(6.0, 0.0, -10.0), head=(-8.0, 0.0, 0.0),
                 clav_r=(0.0, 6.0, 0.0), grip=(-0.32, -0.32, 1.42), blade=(0.92, -0.2, 0.34), edge=(0.0, -0.95, 0.3),
                 elbow_r=(-0.7, 0.2, -0.6), hand_l=(0.11, -0.33, 1.46), hand_l_dir=(0.1, -0.15, 0.98), hand_l_up=(0.0, 1.0, 0.0),
                 elbow_l=(0.8, 0.3, -0.5), fingers_l=0.0),
             r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))
_guard_hold = mod(GUARD, hips=(0.0, 0.05, -0.15), tremble=1.0, grip=(-0.32, -0.33, 1.41), head=(-9.0, 0.0, 0.0))
add("ParryStance", 16, [(0, READY, "lin"), (2, GUARD, "snap"), (5, mod(_guard_hold, tremble=0.4), "sine"), (9, _guard_hold, "sine"),
                        (16, READY, "sine")],
    timing={"guard": 2, "hold": [2, 9], "recover": [9, 16]},
    notes="guardia en 2 cuadros, espera que tiembla hasta 0.3 s (ventana 0.24 s), vuelve a la guardia (ParryRecover 0.28 s)")

# contraataque listo: la hoja cargada atrás a su derecha como el principio del Corte 1 (el contraataque sale
# desde 0.06 s del desvío y el crossfade de 0.05 s no salta)
COUNTER = feet(mod(READY, hips=(0.0, 0.06, -0.14), hips_rot=(2.0, 0.0, -14.0), spine=(6.0, -2.0, -12.0), head=(-8.0, 0.0, 12.0),
                   clav_r=(0.0, 4.0, 0.0), grip=(-0.62, 0.02, 1.3), blade=(-0.65, 0.55, 0.52), edge=(-0.2, -0.9, 0.3),
                   elbow_r=(-0.6, 0.5, 0.3), hand_l=(0.42, -0.4, 1.25), hand_l_dir=(0.1, -0.9, 0.2), hand_l_up=(0.3, 0.0, 1.0),
                   fingers_l=0.2),
               r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))

_defl_r = mod(GUARD, hips=(0.0, 0.1, -0.12), hips_rot=(0.0, 0.0, -12.0), spine=(0.0, 0.0, -14.0), head=(-4.0, 0.0, 10.0),
              grip=(-0.4, -0.42, 1.5), blade=(-0.5, -0.55, 0.67), edge=(-0.75, 0.25, -0.6), elbow_r=(-0.8, 0.2, -0.3),
              hand_l=(0.4, -0.42, 1.36), hand_l_dir=(0.0, -0.25, 0.97), hand_l_up=(0.0, 1.0, 0.0), fingers_l=0.0)
_defl_r2 = mod(_defl_r, hips=(0.0, 0.11, -0.13), grip=(-0.42, -0.41, 1.5), blade=(-0.53, -0.52, 0.67))
add("ParrySuccessR", 12, [(0, GUARD, "lin"), (1, _defl_r, "snap"), (3, _defl_r2, "lin"), (7, mod(COUNTER, hips=(0.0, 0.07, -0.16)), "sine"),
                          (12, COUNTER, "sine")],
    timing={"impact": 1, "hold": [1, 3], "counter_ready": 7, "chain_to": "COUNTER"},
    notes="desvía hacia su derecha: la hoja se abre afuera y arriba, la palma empuja; 2 cuadros quieto (hit-stop) y queda cargado")
_defl_l = mod(GUARD, hips=(0.0, 0.1, -0.15), hips_rot=(8.0, 0.0, 24.0), spine=(6.0, 0.0, 14.0), head=(-8.0, 0.0, -14.0),
              grip=(-0.12, -0.5, 1.3), blade=(0.75, -0.6, -0.25), edge=(0.6, 0.35, -0.7), elbow_r=(-0.5, 0.0, -0.85),
              hand_l=(0.5, 0.12, 1.24), hand_l_dir=(0.6, 0.6, -0.4), hand_l_up=(0.2, 0.0, 1.0), fingers_l=0.2)
_defl_l2 = mod(_defl_l, hips=(0.0, 0.11, -0.16), grip=(-0.11, -0.49, 1.29), blade=(0.76, -0.58, -0.27))
add("ParrySuccessL", 12, [(0, GUARD, "lin"), (1, _defl_l, "snap"), (3, _defl_l2, "lin"), (7, mod(COUNTER, hips=(0.0, 0.07, -0.16)), "sine"),
                          (12, COUNTER, "sine")],
    timing={"impact": 1, "hold": [1, 3], "counter_ready": 7, "chain_to": "COUNTER"},
    notes="desvía hacia su izquierda y abajo, el cuerpo gira con el golpe; 2 cuadros quieto y queda cargado")
# PERFECTO: la hoja salta arriba con la palma adelante (el destello), queda arriba 3 cuadros y baja girando
# hasta una guardia agazapada, la hoja atrás apuntando: se lee "ahora te toca a vos"
_flick = feet(mod(GUARD, hips=(0.0, 0.06, -0.04), hips_rot=(-2.0, 0.0, 4.0), spine=(-6.0, 0.0, -4.0), head=(-4.0, 0.0, 0.0),
                  clav_r=(0.0, 12.0, 0.0), grip=(-0.32, -0.28, 1.86), blade=(0.15, -0.35, 0.92), edge=(0.0, -0.95, -0.3),
                  elbow_r=(-0.8, 0.3, 0.0), hand_l=(0.36, -0.5, 1.42), hand_l_dir=(0.0, -0.3, 0.95), hand_l_up=(0.0, 1.0, 0.0),
                  fingers_l=0.0),
              r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))
_flick2 = mod(_flick, hips=(0.0, 0.06, -0.05), grip=(-0.33, -0.28, 1.87), blade=(0.12, -0.33, 0.94))
LOW_COUNTER = feet(mod(READY, hips=(0.0, 0.08, -0.24), hips_rot=(10.0, 0.0, -18.0), spine=(14.0, 0.0, -14.0), head=(-22.0, 0.0, 12.0),
                       grip=(-0.6, 0.12, 0.9), blade=(-0.5, 0.82, 0.28), edge=(0.0, 0.3, -0.95), elbow_r=(-0.6, 0.6, 0.2),
                       hand_l=(0.36, -0.45, 1.02), hand_l_dir=(0.0, -0.9, -0.3), hand_l_up=(0.0, 0.0, 1.0), fingers_l=0.2),
                   r=flat("R", *R_FOOT), l=toe("L", *L_FOOT, 20.0))
add("PerfectParry", 14, [(0, GUARD, "lin"), (1, _flick, "snap"), (4, _flick2, "lin"), (6, mod(_flick, grip=(-0.5, -0.1, 1.5),
                                                                                       blade=(-0.6, 0.3, 0.75), edge=(-0.3, -0.9, 0.2)), "in2"),
                         (9, LOW_COUNTER, "out"), (14, mod(LOW_COUNTER, hips=(0.0, 0.08, -0.22), tremble=0.6), "sine")],
    timing={"impact": 1, "hold": [1, 4], "counter_ready": 9},
    notes="parry perfecto: la hoja salta arriba y la palma adelante (3 cuadros), baja girando a una guardia agazapada")

# =========================================================================== golpe propio desviado
# el enemigo devuelve el golpe (Blocked): la hoja sale despedida arriba y atrás, el cuerpo se va hacia atrás
# con un saltito (el juego lo empuja ~1 m) y cae agachado; los pies patinan a propósito al caer
_knock = feet(mod(READY, hips=(0.0, 0.14, -0.06), hips_rot=(-12.0, 0.0, -8.0), spine=(-14.0, 0.0, -6.0), head=(4.0, 0.0, 8.0),
                  clav_r=(0.0, 14.0, 0.0), grip=(-0.45, 0.12, 1.74), blade=(-0.3, 0.55, 0.78), edge=(0.0, -0.8, 0.6),
                  elbow_r=(-0.8, 0.4, 0.3), hand_l=(0.55, 0.18, 1.36), hand_l_dir=(0.6, 0.4, 0.5), hand_l_up=(0.0, 0.5, 0.8),
                  fingers_l=0.05),
              r=toe("R", -0.22, -0.14, 6.0, 30.0), l=flat("L", 0.3, 0.22, 34.0))
_knock_air = feet(mod(_knock, hips=(0.0, 0.12, -0.04), lift=0.12, hips_rot=(-8.0, 0.0, -6.0)),
                  r=air(-0.24, -0.25, 0.42, -16.0, 6.0), l=air(0.3, 0.2, 0.36, 10.0, 30.0))
_knock_land = feet(mod(READY, hips=(0.0, 0.1, -0.18), hips_rot=(8.0, 0.0, 6.0), spine=(14.0, 0.0, -4.0), head=(-14.0, 0.0, 0.0),
                       grip=(-0.6, -0.1, 1.15), blade=(-0.45, -0.5, 0.74), edge=(-0.2, -0.75, -0.6), hand_l=(0.48, -0.2, 1.1),
                       fingers_l=0.3),
                   r=flat("R", -0.24, -0.2, 6.0), l=toe("L", 0.32, 0.3, 34.0, 20.0))
add("Blocked", 14, [(0, READY, "lin"), (1, _knock, "snap"), (4, _knock_air, "out"), (7, _knock_land, "in2"), (14, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="rebote contra la guardia: la hoja sale despedida arriba-atrás, saltito hacia atrás, cae agachado")

# =========================================================================== recibir daño
_hit = feet(mod(READY, hips=(0.0, 0.12, -0.08), hips_rot=(-12.0, 0.0, 8.0), spine=(-14.0, 0.0, 6.0), head=(8.0, 4.0, 10.0),
                clav_r=(0.0, 8.0, 0.0), clav_l=(0.0, -8.0, 0.0), grip=(-0.62, 0.02, 1.08), blade=(-0.62, 0.4, -0.45),
                edge=(0.0, 0.7, 0.7), elbow_r=(-0.8, 0.3, 0.0), hand_l=(0.56, 0.12, 1.3), hand_l_dir=(0.7, 0.3, 0.4),
                hand_l_up=(0.0, 0.0, 1.0), fingers_l=0.05),
            r=toe("R", -0.22, -0.14, 6.0, 20.0), l=flat("L", 0.3, 0.22, 34.0))
_hit2 = mod(_hit, hips=(0.0, 0.13, -0.1), spine=(-12.0, 0.0, 6.0), head=(6.0, 4.0, 10.0))
_hit_rec = feet(mod(READY, hips=(0.0, 0.07, -0.13), spine=(12.0, 0.0, -6.0), head=(-12.0, 0.0, -2.0), grip=(-0.58, -0.22, 0.98)),
                r=flat("R", -0.22, -0.14, 6.0), l=flat("L", 0.3, 0.22, 34.0))
add("Hit", 11, [(0, READY, "lin"), (1, _hit, "snap"), (3, _hit2, "lin"), (6, _hit_rec, "sine"), (11, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="golpe liviano: la cabeza y el pecho se van atrás de golpe, los brazos se abren; recupera la guardia en 0.37 s")
_hh = mod(_hit, hips=(0.0, 0.16, -0.06), hips_rot=(-20.0, 0.0, 10.0), spine=(-18.0, 0.0, 8.0), head=(14.0, 6.0, 14.0),
          grip=(-0.66, 0.15, 1.2), blade=(-0.55, 0.6, -0.3), hand_l=(0.6, 0.2, 1.42))
_hh_air = feet(mod(_hh, lift=0.16, hips=(0.0, 0.14, -0.06), hips_rot=(-14.0, 0.0, 6.0)),
               r=air(-0.24, -0.3, 0.45, -20.0, 6.0), l=air(0.3, 0.05, 0.4, -8.0, 30.0))
# cae en tres apoyos: los dos pies y la mano izquierda en el piso, agachado (se lee "me voltearon")
_hh_land = feet(mod(READY, hips=(0.0, 0.16, -0.3), hips_rot=(24.0, 0.0, 10.0), spine=(18.0, 0.0, 0.0), head=(-20.0, 0.0, 0.0),
                    grip=(-0.62, -0.05, 0.85), blade=(-0.6, 0.2, 0.77), edge=(-0.6, -0.5, -0.6), hand_l=(0.42, -0.5, 0.46),
                    hand_l_dir=(0.1, -0.8, -0.6), hand_l_up=(0.0, 0.0, 1.0), elbow_l=(0.8, 0.2, 0.4), fingers_l=0.0),
                r=flat("R", -0.26, -0.26, 6.0), l=toe("L", 0.32, 0.36, 30.0, 30.0))
_hh_land2 = mod(_hh_land, hips=(0.0, 0.17, -0.32), hand_l=(0.42, -0.5, 0.45))
add("HitHeavy", 20, [(0, READY, "lin"), (1, _hh, "snap"), (3, _hh_air, "out"), (6, _hh_land, "in2"), (11, _hh_land2, "sine"),
                     (20, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="golpe pesado: lo levanta, cae en tres apoyos con la mano en el piso y se para (0.65 s)")

# =========================================================================== muerte
_d_snap = mod(_hh, hips=(0.0, 0.14, -0.06), head=(16.0, 6.0, 12.0))
_d_stag = feet(mod(READY, hips=(0.0, 0.08, -0.16), hips_rot=(16.0, 0.0, -6.0), spine=(20.0, 0.0, -4.0), head=(14.0, -4.0, -6.0),
                   clav_r=(0.0, -6.0, 0.0), clav_l=(0.0, 6.0, 0.0), grip=(-0.5, -0.1, 0.8), blade=(-0.45, -0.6, -0.4),
                   edge=(-0.5, 0.2, -0.8), elbow_r=(-0.6, 0.3, -0.7), hand_l=(0.3, -0.25, 0.95), hand_l_dir=(0.0, -0.4, -0.9),
                   hand_l_up=(1.0, 0.0, 0.0), fingers_l=0.5),
               r=flat("R", -0.24, -0.3, 4.0), l=toe("L", 0.3, 0.3, 30.0, 20.0))
# una rodilla en el piso (la izquierda), la katana colgando de la mano; los brazos en el espacio del pecho (cuelgan
# con el tronco vencido)
_d_knee = feet(mod(READY, hips=(0.0, 0.12, -0.34), hips_rot=(18.0, 0.0, -4.0), spine=(20.0, 0.0, -4.0), head=(18.0, -6.0, -4.0),
                   clav_r=(0.0, -8.0, 0.0), clav_l=(0.0, 8.0, 0.0), arm_space=1.0, grip=(-0.46, -0.2, 0.98),
                   blade=(-0.3, -0.75, -0.6), edge=(-0.9, 0.3, 0.0), elbow_r=(-0.6, 0.4, -0.6), hand_l=(0.34, -0.18, 1.0),
                   hand_l_dir=(0.0, -0.3, -0.95), hand_l_up=(1.0, 0.0, 0.0), fingers_l=0.4, knee_l=(0.2, -0.6, -0.8)),
               r=flat("R", -0.24, -0.34, 4.0), l=KR.foot_on("L", 0.28, 0.5, 70.0, 20.0, "toe"))
# cae hacia adelante y de costado (su izquierda): la cabeza enorme apoya de lado, el cuerpo atrás sobre la cadera
_d_fall = feet(mod(READY, hips=(0.14, -0.12, -0.2), hips_rot=(54.0, 38.0, 6.0), spine=(-6.0, 6.0, 0.0), head=(-18.0, 16.0, 0.0),
                   clav_r=(0.0, 0.0, 10.0), arm_space=1.0, grip=(-0.6, -0.42, 1.1), blade=(-0.5, -0.86, 0.1), edge=(0.0, 0.0, 1.0),
                   elbow_r=(-0.4, 0.4, -0.8), hand_l=(0.5, -0.42, 1.12), hand_l_dir=(0.1, -0.4, 0.9), hand_l_up=(0.0, 1.0, 0.3),
                   fingers_l=0.3, knee_l=(0.3, -0.8, 0.0), knee_r=(-0.3, -0.8, 0.0)),
               r=air(-0.2, 0.34, 0.34, 30.0, 0.0), l=air(0.3, 0.38, 0.28, 40.0, 30.0))
_d_rest = mod(_d_fall, hips=(0.15, -0.13, -0.23), head=(-16.0, 18.0, 0.0), grip=(-0.6, -0.43, 1.08))
add("Death", 42, [(0, READY, "lin"), (2, _d_snap, "snap"), (8, _d_stag, "inout"), (18, _d_knee, "in2"),
                  (22, mod(_d_knee, hips=(0.0, 0.12, -0.35), head=(24.0, -6.0, -4.0)), "sine"),
                  (31, _d_fall, "in"), (35, mod(_d_rest, hips=(0.15, -0.13, -0.2)), "out"), (42, _d_rest, "sine")],
    timing={"impact": 2, "knee": 18, "ground": 31, "slide_ok": True},
    notes="se va atrás, se tambalea, cae sobre una rodilla y después de costado; queda tendido (la cámara lenta de Die lo estira)")

# =========================================================================== remate (iai)
# 80 cuadros con el tajo en f54.4 (FinisherStrikeAt 0.68: el juego lo teletransporta detrás del enemigo en ese
# instante). Antes: se planta agachado, girado, con la katana baja atrás a su derecha (wakigamae: desde arriba
# es una cola larga que sale por detrás; Kaito tiene brazos de 30 cm y no llega a desenvainar desde la cadera
# izquierda) y la palma izquierda apuntando al enemigo; espera respirando y temblando cada vez más y se
# comprime en f50-54. En f55 ya está del otro lado, de espaldas al enemigo, estirado en una zancada baja con la
# hoja afuera a su derecha: lo único que se ve del tajo es la pose de "ya corté" y la estela de tinta. Quieto
# (zanshin), chiburi en f62-66 y se para. El remate corto corta en 0.85 (f68): el chiburi ya terminó
IAI = feet(mod(READY, hips=(0.0, 0.1, -0.3), hips_rot=(12.0, 0.0, -28.0), spine=(10.0, 0.0, -8.0), head=(-14.0, 0.0, 30.0),
               clav_r=(0.0, 4.0, 0.0), grip=(-0.56, 0.24, 0.92), blade=(-0.32, 0.88, 0.35), edge=(0.0, 0.35, -0.94),
               elbow_r=(-0.6, 0.6, -0.2), hand_l=(0.22, -0.48, 1.3), hand_l_dir=(-0.1, -0.5, 0.86), hand_l_up=(0.0, 1.0, 0.3),
               elbow_l=(0.8, 0.2, -0.5), fingers_l=0.0, knee_l=(0.6, -0.8, 0.0)),
           r=flat("R", -0.3, -0.38, 10.0), l=flat("L", 0.34, 0.32, 50.0))
_iai_b = mod(IAI, breath=1.0, hips=(0.0, 0.1, -0.31), head=(-15.0, 0.0, 30.0), tremble=0.3)
_iai_deep = mod(IAI, hips=(0.0, 0.12, -0.35), hips_rot=(18.0, 0.0, -30.0), head=(-18.0, 0.0, 30.0), tremble=1.0,
                grip=(-0.56, 0.27, 0.9))
_iai_cmp = mod(IAI, hips=(0.0, 0.11, -0.36), hips_rot=(20.0, 0.0, -30.0), spine=(16.0, 0.0, -10.0), head=(-22.0, 0.0, 30.0),
               tremble=1.6, grip=(-0.55, 0.3, 0.88), hand_l=(0.2, -0.52, 1.24))
AFTER_CUT = feet(mod(READY, hips=(0.0, -0.24, -0.33), hips_rot=(14.0, 0.0, -30.0), spine=(12.0, 0.0, -16.0), head=(-8.0, 0.0, 14.0),
                     clav_r=(0.0, 10.0, 0.0), grip=(-0.8, -0.36, 1.25), blade=(-0.9, -0.3, 0.3), edge=(-0.15, 0.55, -0.82),
                     elbow_r=(-0.8, 0.0, -0.5), hand_l=(0.42, 0.08, 1.16), hand_l_dir=(0.6, 0.75, -0.2), hand_l_up=(0.0, 0.0, 1.0),
                     elbow_l=(0.6, 0.6, -0.3), fingers_l=0.05),
                 r=flat("R", -0.28, -0.64, 4.0), l=toe("L", 0.3, 0.26, 30.0, 30.0))
_ac_hold = mod(AFTER_CUT, hips=(0.0, -0.24, -0.35), grip=(-0.81, -0.35, 1.24), head=(-9.0, 0.0, 14.0))
_chi_up = mod(_ac_hold, grip=(-0.76, -0.36, 1.42), blade=(-0.75, -0.35, 0.56), edge=(-0.3, 0.2, -0.93))
_chi_snap = mod(_ac_hold, hips=(0.0, -0.22, -0.34), grip=(-0.72, -0.3, 0.92), blade=(-0.7, -0.5, -0.45), edge=(-0.5, 0.0, -0.86))
_fin_end = feet(mod(READY, hips=(0.0, -0.1, -0.08)), r=flat("R", -0.26, -0.5, 6.0), l=flat("L", 0.3, 0.1, 30.0))
add("Finisher", 80, [
    (0, READY, "sine"), (8, IAI, "out"), (22, _iai_b, "sine"), (36, mod(IAI, tremble=0.6), "sine"), (50, _iai_deep, "sine"),
    (54, _iai_cmp, "in2"), (55, AFTER_CUT, "lin"), (62, _ac_hold, "sine"), (64, _chi_up, "inout"), (66, _chi_snap, "snap"),
    (68, mod(_chi_snap, grip=(-0.72, -0.31, 0.93)), "lin"), (74, feet(mod(READY, hips=(0.0, -0.12, -0.16)), r=flat("R", -0.26, -0.5, 6.0),
                                                                      l=toe("L", 0.3, 0.1, 30.0, 10.0)), "sine"),
    (80, _fin_end, "sine")],
    timing={"strike": 54, "zanshin": [55, 62], "chiburi": [62, 68], "short_end": 68, "slide_ok": True},
    events=[{"frame": 54, "fn": "Strike"}],
    notes="iai: cargado y temblando hasta f54, en f55 (FinisherStrikeAt 0.68) ya cortó y está del otro lado; chiburi y se para")

# =========================================================================== Corte del Viento (habilidad 1)
# PlayerController.TickWindSlash: 0.32 s de preparación (cámara sobre el hombro y cámara lenta), 0.16 s de viaje
# (9 m), los cortes aparecen 0.06 s después y termina a 0.55 s: 31 cuadros. Prepara como el iai, viaja en la pose
# del dash y llega en la pose de "ya corté" de espaldas a los cortados
_ws_cmp = mod(_iai_cmp, tremble=1.2)
add("WindSlash", 31, [
    (0, READY, "sine"), (4, IAI, "out"), (8, _iai_deep, "sine"), (9, _ws_cmp, "in2"), (10, _dash, "lin"), (14, _dash_b, "sine"),
    (15, AFTER_CUT, "out"), (20, _ac_hold, "sine"), (22, _chi_up, "inout"), (24, _chi_snap, "snap"),
    (31, feet(mod(READY, hips=(0.0, -0.1, -0.1)), r=flat("R", -0.26, -0.5, 6.0), l=flat("L", 0.3, 0.1, 30.0)), "sine")],
    timing={"phases": {"prep": [0, 9.6], "travel": [9.6, 14.4], "slashes": 16.2, "end": 31}, "slide_ok": True},
    notes="prepara (iai) 0.32 s, viaja 0.16 s en la pose del dash, llega de espaldas con la hoja afuera; chiburi y guardia")

# =========================================================================== Torbellino de Hojas (habilidad 2)
# PlayerController.TickWhirlwind gira el MODELO 720° (horario visto desde arriba) entre 0.12 y 0.74 s: el clip
# no gira, pone la pose del trompo. Se enrosca a su izquierda (contra el giro), salta apenas con los pies juntos
# bajo el centro (el giro del modelo no los arrastra), la hoja estirada a su derecha a la altura de la cintura
# con el filo hacia atrás (al girar horario, el lado derecho barre hacia atrás) y el brazo izquierdo abierto
_wh_coil = feet(mod(READY, hips=(0.0, 0.04, -0.22), hips_rot=(10.0, 0.0, 30.0), spine=(10.0, 0.0, 24.0), head=(-12.0, 0.0, -20.0),
                    grip=(0.1, -0.32, 1.0), blade=(0.8, 0.3, -0.25), edge=(-0.3, 0.9, 0.0), elbow_r=(-0.3, -0.3, -0.9),
                    hand_l=(0.45, 0.25, 1.2), fingers_l=0.6),
                r=flat("R", -0.2, -0.12, 0.0), l=flat("L", 0.22, 0.12, 20.0))
_wh_spin = feet(mod(READY, hips=(0.0, 0.0, -0.06), lift=0.2, hips_rot=(6.0, 6.0, 0.0), spine=(4.0, 6.0, -6.0), head=(-6.0, 0.0, 4.0),
                    clav_r=(0.0, 10.0, 0.0), clav_l=(0.0, -10.0, 0.0), grip=(-0.7, 0.0, 1.32), blade=(-0.96, 0.2, -0.05),
                    edge=(-0.2, 0.98, 0.0), elbow_r=(-0.6, 0.6, -0.5), hand_l=(0.7, -0.02, 1.36), hand_l_dir=(0.95, 0.1, 0.1),
                    hand_l_up=(0.0, 0.0, 1.0), elbow_l=(0.4, 0.6, -0.6), fingers_l=0.05),
                r=air(-0.12, 0.02, 0.4, 20.0, 0.0), l=air(0.12, 0.04, 0.46, 30.0, 0.0))
_wh_spin2 = feet(mod(_wh_spin, lift=0.3, hips=(0.0, 0.0, -0.04), grip=(-0.72, 0.02, 1.36)),
                 r=air(-0.12, 0.0, 0.5, 24.0, 0.0), l=air(0.12, 0.02, 0.56, 34.0, 0.0))
_wh_land = feet(mod(READY, hips=(0.0, 0.04, -0.24), hips_rot=(14.0, 0.0, -10.0), spine=(14.0, 0.0, -10.0), head=(-16.0, 0.0, 8.0),
                    grip=(-0.6, -0.42, 0.85), blade=(-0.5, -0.84, -0.2), edge=(-0.9, 0.3, 0.0), hand_l=(0.5, -0.1, 1.1), fingers_l=0.3),
                r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))
add("Whirlwind", 30, [
    (0, READY, "sine"), (3, _wh_coil, "out"), (5, _wh_spin, "out"), (13, _wh_spin2, "sine"), (21, _wh_spin, "sine"),
    (24, _wh_land, "in2"), (30, READY, "sine")],
    timing={"phases": {"coil": [0, 3.6], "spin": [3.6, 22.2], "end": 29.7}, "slide_ok": True},
    notes="enrosque, trompo en el aire con la hoja afuera a su derecha (el código gira el modelo 720°), cae agachado")
