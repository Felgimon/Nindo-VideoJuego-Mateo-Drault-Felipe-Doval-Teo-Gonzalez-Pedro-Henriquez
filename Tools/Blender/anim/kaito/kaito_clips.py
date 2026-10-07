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


class Planted(tuple):
    """(tobillo, giro) de un pie APOYADO que además recuerda su huella en el mundo (lado, x, y, pivote). Entre
    dos claves con la misma huella KClip recalcula el tobillo desde la huella y el cabeceo interpolado: el
    borde que apoya (punta, bola o talón) queda clavado. Interpolando el tobillo en línea recta, un talón que
    se levanta sobre la punta corría la punta 3-15 cm."""

    def __new__(cls, side, x, y, pitch=0.0, yaw=0.0, pivot="flat"):
        t = super().__new__(cls, KR.foot_on(side, x, y, pitch, yaw, pivot))
        t.print = (side, x, y, pivot)
        return t


def feet(p, r=None, l=None):
    """r / l = (tobillo, giro) de un pie: Planted (flat / toe / plant) o en el aire (air / fa)."""
    q = mod(p)
    for s, v in (("r", r), ("l", l)):
        if v is None:
            continue
        q["foot_" + s], q["foot_" + s + "_rot"] = v
        if isinstance(v, Planted):
            q["_print_" + s] = v.print
        else:
            q.pop("_print_" + s, None)
    return q


def plant(side, x, y, pitch=0.0, yaw=0.0, pivot="flat"):
    return Planted(side, x, y, pitch, yaw, pivot)


def flat(side, x, y, yaw=0.0):
    return Planted(side, x, y, 0.0, yaw)


def toe(side, x, y, yaw=0.0, heel=30.0):
    return Planted(side, x, y, heel, yaw, "toe")


def air(x, y, z, pitch=0.0, yaw=0.0):
    """Pie en el aire: tobillo (x, y, z) con su giro."""
    return (x, y, z), (pitch, 0.0, yaw)


def hover(side, x, y, yaw=0.0, dz=0.05, pitch=0.0):
    """Pie en el aire JUSTO arriba de su huella: la clave anterior a apoyar. Sin ella el tobillo iba en línea recta
    desde el vuelo y la suela llegaba al piso todavía corriéndose (entraba patinando)."""
    return air(x, y, KR.ankle_rest(side).z + dz, pitch, yaw)


def lifted(side, x, y, clear=0.06, pitch=0.0, yaw=0.0):
    """Pie en el aire con la esquina más baja de la suela a 'clear' (u) del piso: un paso que se levanta de verdad
    (con un 'air' a mano, un pie con la punta abajo seguía rozando y se arrastraba mientras el cuerpo cambiaba)."""
    R = KR.foot_rot(pitch, 0.0, yaw)
    A = KR.ankle_rest(side)
    low = min((R @ (P - A)).z for P in KR.sole_corners(side))
    return air(x, y, clear - low, pitch, yaw)


def ankle_of(planted):
    """Tobillo (x, y, z) de un pie apoyado (para levantarlo desde donde está)."""
    return tuple(planted[0])


def inter(a, b, u):
    """Pose a la fracción u entre dos poses (para una clave de paso: después se le cambian los pies con feet()).
    Una clave con canales sueltos no sirve: los que faltan se quedarían quietos en todo el tramo."""
    pa = {k: v for k, v in a.items() if not k.startswith("_print_")}
    pb = {k: v for k, v in b.items() if not k.startswith("_print_")}
    tmp = Clip("_", 1, [Key(0, pa, "lin"), Key(1, pb, "lin")])
    out = {ch: tmp.sample(u, ch) for ch in set(pa) | set(pb)}
    return {k: (tuple(v) if isinstance(v, Vector) else v) for k, v in out.items()}


def at_travel(p, travel):
    """La misma pose cuando el cuerpo ya avanzó 'travel' (u): solo se corre lo clavado en el mundo."""
    q = copy.deepcopy(p)
    for s_ in ("r", "l"):
        x, y, z = q["foot_" + s_]
        q["foot_" + s_] = (x, y - travel, z)
        if "_print_" + s_ in q:
            side, px, py, piv = q["_print_" + s_]
            q["_print_" + s_] = (side, px, py - travel, piv)
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
            return self.step_arc(f, self.pivot_feet(f, super().controls(f)))
        k = max(0.0, min(1.0, f / 3.0, (self.frames - f) / 3.0))
        # timing 'cut': un corte (el teletransporte del remate) entre dos cuadros. A los dos lados el lag se apaga:
        # con la cadera adelantada, el cuadro anterior ya traía la cadera del otro lado y las piernas no llegaban
        for c in self.timing.get("cut", ()):
            k = min(k, max(0.0, abs(f - c) - 0.5) / 1.5)
        keep = self.lag
        self.lag = {c: v * k for c, v in keep.items()}
        try:
            return self.step_arc(f, self.pivot_feet(f, super().controls(f)))
        finally:
            self.lag = keep

    def step_arc(self, f, c):
        """Un pie que despega (clave apoyada -> clave en el aire) primero SUBE y después va; uno que aterriza
        (aire -> apoyado) llega arriba de su huella y después BAJA. En línea recta la suela se corría rozando el piso
        el primer cuadro del despegue y el último de la llegada (1-5 cm por cuadro)."""
        ks = self.keys
        ff = max(0.0, min(float(self.frames), f))
        i = self._seg(ff)
        a, b = ks[i], ks[i + 1]
        u = (ff - a.frame) / max(1e-6, b.frame - a.frame)
        for s_ in ("r", "l"):
            ch = "foot_" + s_
            pa, pb = s_ in a.prints, s_ in b.prints
            if pa == pb or ch not in a.ctrl or ch not in b.ctrl:
                continue
            e = NA.ease(b.ease_ch.get(ch, b.ease), u)
            up, along = (1.0 - (1.0 - e) ** 2, e * e) if pa else (e * e, 1.0 - (1.0 - e) ** 2)
            A, B = Vector(a.ctrl[ch]), Vector(b.ctrl[ch])
            c[ch] = (A.x + (B.x - A.x) * along, A.y + (B.y - A.y) * along, A.z + (B.z - A.z) * up)
        return c

    def pivot_feet(self, f, c):
        """Un pie con la misma huella en las dos claves del tramo gira sobre su borde (ver Planted): el tobillo
        sale de la huella y del cabeceo interpolado, que no cruza el cero (sobre la punta no se levanta la
        punta: el Catmull-Rom del giro se pasaba unos grados y el borde se despegaba)."""
        ks = self.keys
        ff = max(0.0, min(float(self.frames), f))
        i = self._seg(ff)
        a, b = ks[i], ks[i + 1]
        for s_ in ("r", "l"):
            pa, pb = a.prints.get(s_), b.prints.get(s_)
            if not pa or not pb or abs(pa[1] - pb[1]) > 1e-4 or abs(pa[2] - pb[2]) > 1e-4:
                continue
            pivs = {pa[3], pb[3]} - {"flat"}
            if len(pivs) > 1:
                continue
            piv = pivs.pop() if pivs else "flat"
            pitch, roll, yaw = c["foot_" + s_ + "_rot"]
            pitch = max(0.0, pitch) if piv in ("toe", "ball") else min(0.0, pitch) if piv == "heel" else pitch
            ank, rot = KR.foot_on(pa[0], pa[1], pa[2], pitch, yaw, piv, roll)
            c["foot_" + s_], c["foot_" + s_ + "_rot"] = ank, rot
        return c


def add(name, frames, keys, loop=False, lag=None, timing=None, events=None, notes="", travel=None):
    """keys: (cuadro, pose, curva[, {canal: curva, 'stop': (canales,)}]). travel: avance del juego por cuadro
    (lunge_travel): se escribe en cada clave y se interpola lineal (es una recta en el juego)."""
    def key(k):
        ch = dict(k[3]) if len(k) > 3 else {}
        stops = ch.pop("stop", ())
        p = copy.deepcopy(k[1])
        prints = {s_: p.pop("_print_" + s_) for s_ in ("r", "l") if "_print_" + s_ in p}
        if travel is not None:
            p["travel"] = travel[k[0]]
            ch.setdefault("travel", "lin")
        out = Key(k[0], p, k[2], ch, stops)
        out.prints = prints
        return out
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
    out = Key(f, ctrl, "lin", dict(nxt.ease_ch, travel="lin"))
    # la clave intermedia conserva las huellas que comparten sus vecinas (el pie sigue clavado)
    out.prints = {s_: v for s_, v in prev.prints.items() if nxt.prints.get(s_) == v}
    return out


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
# cargada a la derecha, los dos talones arriba sobre la huella de la guardia (empuja); salto corto hacia adelante
# (los 0.9 m los mueve el juego, f2-f5), los dos pies en el aire mientras avanza, la hoja barre por su derecha
# hasta cruzar adelante (impacto) y termina envuelta a su izquierda; el pie derecho apoya al terminar el avance y
# el izquierdo un cuadro después.
# Los pies NUNCA tocan el piso mientras el juego mueve el cuerpo: el imán del ataque corta el avance contra un
# enemigo pegado (PlayerController.TickAttack) y un pie clavado en el mundo patinaba 22-60 cm hacia atrás; en el
# aire, un avance más corto es solo un salto más corto
A1_N = 13
A1_TR = lunge_travel(A1_N, 2, 5, 0.9)
T1 = A1_TR
_a1_cock = feet(mod(READY, hips=(0.0, 0.08, -0.1), hips_rot=(0.0, 0.0, -20.0), spine=(2.0, -3.0, -18.0), head=(-4.0, 0.0, 16.0),
                    clav_r=(0.0, 6.0, 0.0), grip=(-0.66, 0.08, 1.48), blade=(-0.62, 0.5, 0.6), edge=(-0.3, -0.85, 0.3),
                    elbow_r=(-0.6, 0.5, 0.5), hand_l=(0.48, -0.42, 1.32), hand_l_dir=(0.1, -0.9, 0.1), hand_l_up=(0.3, 0.0, 1.0),
                    fingers_l=0.15),
                r=fr("R", R_FOOT[0], R_FOOT[1], T1[2], R_FOOT[2], 22.0), l=fr("L", L_FOOT[0], L_FOOT[1], T1[2], L_FOOT[2], 30.0))
_a1_sweep = feet(mod(_a1_cock, lift=0.08, hips=(0.0, -0.02, -0.06), hips_rot=(10.0, 0.0, -4.0), spine=(9.0, 0.0, -6.0),
                     head=(-8.0, 0.0, 6.0), grip=(-0.62, -0.36, 1.36), blade=(-0.92, -0.25, 0.2), edge=(0.2, -0.95, 0.1),
                     elbow_r=(-0.6, 0.4, -0.3)),
                 r=fa(-0.24, -0.42, 0.44, T1[3], -10.0, 6.0), l=fa(0.3, 0.42, 0.5, T1[3], 22.0, 30.0))
_a1_hit = feet(mod(READY, lift=0.06, hips=(0.0, -0.1, -0.12), hips_rot=(14.0, 0.0, 16.0), spine=(12.0, 0.0, 10.0),
                   head=(-14.0, 0.0, -10.0), clav_r=(0.0, 0.0, 8.0), grip=(-0.2, -0.64, 1.2), blade=(0.15, -0.97, -0.1),
                   edge=(0.97, 0.15, 0.0), elbow_r=(-0.5, 0.1, -0.9), hand_l=(0.55, 0.05, 1.25), hand_l_dir=(0.6, 0.6, -0.3),
                   hand_l_up=(0.0, 0.0, 1.0), fingers_l=0.3),
               r=fa(-0.24, -0.4, 0.36, T1[4], -12.0, 4.0), l=fa(0.3, 0.3, 0.46, T1[4], 18.0, 30.0))
_a1_cross = feet(mod(_a1_hit, lift=0.0, hips_rot=(14.0, 0.0, 26.0), spine=(12.0, 0.0, 18.0), head=(-13.0, 0.0, -16.0),
                     grip=(0.12, -0.52, 1.06), blade=(0.72, -0.6, -0.33), edge=(0.6, 0.78, 0.1), elbow_r=(-0.3, -0.1, -0.9)),
                 r=fr("R", -0.24, -0.2, T1[5], 2.0), l=fa(0.3, 0.32, 0.4, T1[5], 10.0, 30.0))
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
    timing={"apex": 2, "contact": 4, "active": [4, 7], "combo": 7, "lunge": [2, 5, 0.9], "riposte_from": 2, "chain_to": "A1_END"},
    events=[{"frame": 4, "fn": "Strike"}, {"frame": 5, "fn": "FootR"}, {"frame": 6, "fn": "FootL"}],
    notes="tajo de derecha a izquierda con salto corto (en el aire mientras avanza); el pie derecho apoya al terminar el avance")

# =========================================================================== corte 2 (revés ascendente)
# desde A1_END: la muñeca se enrosca atrás a su izquierda (los dos talones arriba: empuja), salta y la hoja sube
# cruzando por delante (impacto) hasta arriba a su derecha; el pie izquierdo (el de atrás) pasa adelante en el
# aire y apoya al terminar el avance (f4), el derecho tres cuadros después
A2_N = 11
A2_TR = lunge_travel(A2_N, 1, 4, 1.0)
T2 = A2_TR
_a2_coil = feet(mod(A1_END, hips=(0.0, 0.0, -0.14), hips_rot=(8.0, 0.0, 32.0), spine=(10.0, 0.0, 22.0), head=(-8.0, 0.0, -22.0),
                    grip=(0.38, -0.14, 0.88), blade=(0.6, 0.6, -0.5), edge=(-0.5, 0.0, -0.85), elbow_r=(-0.1, 0.2, -0.95)),
                r=fr("R", -0.24, -0.2, T2[1], 2.0, 24.0), l=fr("L", 0.3, 0.3, T2[1], 30.0, 34.0))
_a2_low = feet(mod(_a2_coil, lift=0.06, hips=(0.0, -0.06, -0.14), hips_rot=(10.0, 0.0, 18.0), spine=(11.0, 0.0, 10.0),
                   head=(-11.0, 0.0, -8.0), grip=(0.18, -0.55, 0.98), blade=(0.6, -0.75, -0.25), edge=(-0.3, 0.0, -0.95)),
               r=fa(-0.26, 0.2, 0.44, T2[2], 16.0, 2.0), l=fa(0.24, -0.08, 0.42, T2[2], 0.0, 15.0))
_a2_hit = feet(mod(READY, lift=0.05, hips=(0.0, -0.1, -0.12), hips_rot=(10.0, 0.0, -4.0), spine=(10.0, 4.0, -8.0),
                   head=(-12.0, -4.0, 6.0), clav_r=(0.0, 6.0, 0.0), grip=(-0.2, -0.64, 1.3), blade=(-0.1, -0.95, 0.3),
                   edge=(-0.85, 0.0, 0.5), elbow_r=(-0.5, 0.3, -0.8), hand_l=(0.5, 0.15, 1.15), hand_l_dir=(0.5, 0.5, -0.7),
                   hand_l_up=(0.2, 0.0, 1.0), fingers_l=0.4),
               r=fa(-0.28, 0.3, 0.44, T2[3], 22.0, 0.0), l=fa(0.22, -0.36, 0.32, T2[3], -12.0, 10.0))
_a2_rise = feet(mod(_a2_hit, lift=0.0, hips_rot=(8.0, 0.0, -16.0), spine=(7.0, 5.0, -16.0), head=(-11.0, -5.0, 14.0),
                    clav_r=(0.0, 12.0, 0.0), grip=(-0.4, -0.45, 1.6), blade=(-0.7, -0.45, 0.55), edge=(-0.6, 0.35, -0.7),
                    elbow_r=(-0.6, 0.3, -0.2)),
                r=fa(-0.3, 0.14, 0.37, T2[4], 12.0, 0.0), l=fr("L", 0.22, -0.3, T2[4], 10.0))
_a2_over = feet(mod(_a2_rise, hips=(0.0, -0.06, -0.1), hips_rot=(6.0, 0.0, -26.0), spine=(4.0, 6.0, -24.0), head=(-10.0, -6.0, 20.0),
                    clav_r=(0.0, 14.0, 0.0), grip=(-0.5, -0.2, 1.76), blade=(-0.55, 0.38, 0.74), edge=(-0.5, -0.82, 0.2),
                    elbow_r=(-0.7, 0.4, 0.2)),
                r=fa(-0.3, 0.17, 0.33, T2[5], 2.0, 0.0), l=fr("L", 0.22, -0.3, T2[5], 10.0))
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
    timing={"apex": 1, "contact": 3, "active": [3, 6], "combo": 6, "lunge": [1, 4, 1.0], "chain_from": "A1_END", "chain_to": "A2_END"},
    events=[{"frame": 3, "fn": "Strike"}, {"frame": 4, "fn": "FootL"}, {"frame": 7, "fn": "FootR"}],
    notes="revés ascendente con un salto; el pie izquierdo pasa adelante en el aire y apoya al terminar el avance")

# =========================================================================== corte final (salto a dos manos)
# desde A2_END: sube la hoja con las dos manos por encima de su hombro derecho y la tira AFUERA y atrás (la
# punta 0.9 m a su derecha: desde la cámara del juego sale de la silueta por el costado; atrás de la cabeza la
# tapaban la cabeza y el pelo y el corte final no se distinguía de los otros dos), se agacha, salta 1.6 m, la hoja
# pasa por arriba y baja en diagonal: cruza adelante en el impacto y queda baja y abierta a su izquierda al caer
# (una línea larga que sale del cuerpo, no metida debajo de la cabeza); 3 cuadros de impacto quieto
A3_N = 20
A3_TR = lunge_travel(A3_N, 3, 7, 1.6)
T3 = A3_TR
_a3_raise = feet(mod(A2_END, hips=(0.0, 0.1, -0.22), hips_rot=(-4.0, 0.0, -26.0), spine=(-8.0, 4.0, -18.0), head=(-2.0, -4.0, 20.0),
                     clav_r=(0.0, 14.0, 0.0), clav_l=(0.0, -10.0, 0.0), grip=(-0.29, 0.1, 1.9), blade=(-0.82, 0.33, 0.48),
                     edge=(-0.3, -0.5, 0.8), elbow_r=(-0.8, 0.2, 0.4), grip_l=1.0, elbow_l=(0.8, 0.2, 0.2), fingers_l=1.0),
                 r=fr("R", -0.3, 0.18, T3[3], 0.0, 26.0), l=fr("L", 0.22, -0.3, T3[3], 10.0, 26.0))
_a3_air = feet(mod(_a3_raise, hips=(0.0, 0.02, -0.08), hips_rot=(4.0, 0.0, -22.0), spine=(-4.0, 3.0, -16.0), lift=0.36,
                   grip=(-0.28, 0.08, 1.93), blade=(-0.8, 0.35, 0.49)),
               r=fa(-0.3, -0.1, 0.62, T3[5], -10.0, 0.0), l=fa(0.24, 0.2, 0.7, T3[5], 30.0, 10.0))
_a3_over = feet(mod(_a3_air, hips=(0.0, -0.04, -0.06), hips_rot=(10.0, 0.0, -8.0), spine=(6.0, 0.0, -6.0), head=(-12.0, 0.0, 6.0), lift=0.2,
                    grip=(-0.15, -0.22, 2.0), blade=(-0.35, -0.25, 0.9), edge=(-0.1, -0.95, -0.2)),
                r=fa(-0.3, -0.4, 0.42, T3[6], -14.0, 2.0), l=fa(0.26, 0.3, 0.45, T3[6], 20.0, 20.0))
_a3_hit = feet(mod(READY, lift=0.0, hips=(0.0, -0.12, -0.15), hips_rot=(18.0, 0.0, 10.0), spine=(18.0, 0.0, 6.0), head=(-22.0, 0.0, -6.0),
                   clav_r=(0.0, -4.0, 4.0), clav_l=(0.0, 4.0, 4.0), grip=(-0.06, -0.62, 1.32), blade=(0.2, -0.95, 0.05),
                   edge=(0.1, 0.0, -1.0), elbow_r=(-0.5, 0.2, -0.8), grip_l=1.0, elbow_l=(0.6, 0.3, -0.7), fingers_l=1.0),
               r=fr("R", -0.27, -0.42, T3[7], 4.0), l=fr("L", 0.3, 0.38, T3[7], 26.0, 34.0))
A3_LOW = feet(mod(_a3_hit, hips=(0.0, -0.16, -0.27), hips_rot=(22.0, 0.0, 18.0), spine=(22.0, 0.0, 10.0), head=(-26.0, 0.0, -10.0),
                  grip=(0.15, -0.52, 0.84), blade=(0.85, -0.35, -0.38), edge=(0.0, 0.2, -0.98)),
              r=fr("R", -0.27, -0.42, T3[8], 4.0), l=fr("L", 0.3, 0.38, T3[8], 26.0, 34.0))
_a3_hold = feet(mod(A3_LOW, hips=(0.0, -0.17, -0.29), grip=(0.16, -0.53, 0.82), blade=(0.86, -0.34, -0.38), head=(-27.0, 0.0, -10.0)),
                r=fr("R", -0.27, -0.42, T3[11], 4.0), l=fr("L", 0.3, 0.38, T3[11], 26.0, 34.0))
_a3_rec = feet(mod(READY, hips=(0.0, 0.0, -0.14), grip_l=0.4, fingers_l=0.8),
               r=fa(-0.24, -0.3, 0.3, T3[15], 0.0, 6.0), l=fr("L", 0.3, 0.38, T3[15], 30.0))
add("Attack3", A3_N, [
    (0, A2_END, "sine"), (3, _a3_raise, "out"), (5, _a3_air, "inout"), (6, _a3_over, "in2"), (7, _a3_hit, "lin"),
    (8, A3_LOW, "out"), (11, _a3_hold, "lin"), (15, _a3_rec, "sine"),
    (17, feet(mod(READY, hips=(0.0, 0.01, -0.09)), r=fr("R", R_FOOT[0], R_FOOT[1], T3[17], R_FOOT[2]), l=fa(L_FOOT[0], L_FOOT[1], 0.4, T3[17], 8.0, L_FOOT[2])),
     "sine"),
    (20, feet(READY, r=fr("R", R_FOOT[0], R_FOOT[1], T3[20], R_FOOT[2]), l=fr("L", L_FOOT[0], L_FOOT[1], T3[20], L_FOOT[2])), "sine")],
    travel=A3_TR,
    timing={"apex": 3, "contact": 7, "active": [7, 10], "hold": [8, 11], "lunge": [3, 7, 1.6], "chain_from": "A2_END",
            "chain_to": "READY"},
    events=[{"frame": 7, "fn": "Strike"}, {"frame": 7, "fn": "Land"}],
    notes="salto con las dos manos, la hoja pasa por arriba y cruza en diagonal; cae con la hoja baja y queda quieto 3 cuadros")


# =========================================================================== dash mágico
# El juego lo toca a 1.4x (PlayerController.TryDash): 14 cuadros = 0.33 s reales. TickDash lo mueve desde el
# primer cuadro (40 m/s que bajan a 10 m/s en 0.26 s = f11) y después lo frena en 0.125 s (0.6 m más, hasta f14).
# Sin anticipación: arranca ya en el aire, en la pose aerodinámica (cuerpo bajo e inclinado, katana y brazo
# izquierdo atrás, la rodilla derecha arriba adelante y la pierna izquierda estirada atrás: desde arriba es una
# flecha, y ningún pie roza el piso mientras viaja: la punta de atrás se arrastraba los 6.5 m). En f11 cae sobre
# la huella de la guardia, el talón derecho adelante con la punta arriba y la punta izquierda atrás: lo que
# todavía frena el juego se lee como un frenazo. Termina en la guardia (Dash -> Locomotion y Dash -> Corte 1 no
# saltan: antes terminaba de costado con los pies cambiados)
# los brazos van en el espacio del pecho (arm_space): con el cuerpo inclinado quedan atrás y arriba como alas
_dash = feet(mod(READY, hips=(0.0, -0.04, -0.2), hips_rot=(24.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0), head=(-22.0, 0.0, 0.0),
                 arm_space=1.0, grip=(-0.44, 0.36, 1.08), blade=(-0.2, 0.96, 0.18), edge=(0.0, 0.2, -0.98), elbow_r=(-0.6, 0.6, 0.3),
                 hand_l=(0.42, 0.3, 1.12), hand_l_dir=(0.15, 0.9, -0.3), hand_l_up=(1.0, 0.0, 0.0), elbow_l=(0.6, 0.6, 0.3),
                 fingers_l=0.1, knee_r=(-0.1, -1.0, 0.2)),
             r=air(-0.2, -0.26, 0.44, -6.0, -4.0), l=air(0.22, 0.44, 0.52, 34.0, 8.0))
_dash_launch = feet(mod(_dash, hips=(0.0, -0.02, -0.18), hips_rot=(16.0, 0.0, 0.0)),
                    r=air(-0.2, -0.18, 0.38, -4.0, -4.0), l=air(0.22, 0.34, 0.46, 30.0, 8.0))
_dash_b = feet(mod(_dash, hips=(0.0, -0.04, -0.18), grip=(-0.45, 0.37, 1.1), hand_l=(0.43, 0.32, 1.14), head=(-21.0, 0.0, 0.0)),
               r=air(-0.2, -0.28, 0.46, -8.0, -4.0), l=air(0.22, 0.46, 0.54, 36.0, 8.0))
# la caída es la guardia frenando (cadera atrás y abajo, talón derecho adelante con la punta arriba) con los brazos
# y la hoja YA en la guardia: un corte buffereado arranca desde acá con 0.05 s de fundido
_dash_land = feet(mod(READY, hips=(0.0, 0.05, -0.11), hips_rot=(-2.0, 0.0, 12.0), spine=(4.0, 0.0, -8.0), head=(-8.0, 0.0, -3.0),
                      arm_space=0.0, fingers_l=0.45),
                  r=plant("R", R_FOOT[0], R_FOOT[1], -8.0, R_FOOT[2], "heel"), l=toe("L", *L_FOOT, 8.0))
DASH_END = feet(mod(READY, hips=(0.0, 0.04, -0.1)), r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))
# al caer (f11) la mano izquierda y la cabeza ya están en la guardia, sin atraso: con el atraso de LEAD todavía
# venían de las "alas" y un corte buffereado (TickDash: Attack1 con 0.05 s de fundido desde f11) los hacía saltar
add("Dash", 14, [(0, _dash_launch, "lin"), (2, _dash, "out"), (6, _dash_b, "sine"), (10, _dash, "sine"),
                 (11, _dash_land, "in2"), (14, DASH_END, "sine")], lag=mod(LEAD, hand_l=0.0, head=0.0),
    timing={"travel_frames": [0, 11], "airborne": [0, 10], "play_speed": 1.4},
    notes="se toca a 1.4x: f0-f10 en el aire mientras viaja (0.26 s), cae en f11 en la guardia y frena (el juego lo desliza 0.6 m)")

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

# contraataque listo: EXACTAMENTE la carga del Corte 1 (su f2, RIPOSTE_FRAME): la hoja atrás de su hombro derecho y
# los talones arriba. El contraataque (TickParrySuccess) arranca el Corte 1 en ese cuadro: sale del desvío sin
# volver a cargar, y desde el final del desvío no hay salto (antes la muñeca daba 130-160° en el fundido de 0.05 s)
COUNTER = _a1_cock

_defl_r = mod(GUARD, hips=(0.0, 0.1, -0.12), hips_rot=(0.0, 0.0, -12.0), spine=(0.0, 0.0, -14.0), head=(-4.0, 0.0, 10.0),
              grip=(-0.4, -0.42, 1.5), blade=(-0.5, -0.55, 0.67), edge=(-0.75, 0.25, -0.6), elbow_r=(-0.8, 0.2, -0.3),
              hand_l=(0.4, -0.42, 1.36), hand_l_dir=(0.0, -0.25, 0.97), hand_l_up=(0.0, 1.0, 0.0), fingers_l=0.0)
_defl_r2 = mod(_defl_r, hips=(0.0, 0.11, -0.13), grip=(-0.42, -0.41, 1.5), blade=(-0.53, -0.52, 0.67))
add("ParrySuccessR", 12, [(0, GUARD, "lin"), (1, _defl_r, "snap"), (3, _defl_r2, "lin"), (7, mod(COUNTER, hips=(0.0, 0.1, -0.14)), "sine"),
                          (12, COUNTER, "sine")],
    timing={"impact": 1, "hold": [1, 3], "counter_ready": 7, "chain_to": "COUNTER"},
    notes="desvía hacia su derecha: la hoja se abre afuera y arriba, la palma empuja; 2 cuadros quieto (hit-stop) y queda cargado")
_defl_l = mod(GUARD, hips=(0.0, 0.1, -0.15), hips_rot=(8.0, 0.0, 24.0), spine=(6.0, 0.0, 14.0), head=(-8.0, 0.0, -14.0),
              grip=(-0.12, -0.5, 1.3), blade=(0.75, -0.6, -0.25), edge=(0.6, 0.35, -0.7), elbow_r=(-0.5, 0.0, -0.85),
              hand_l=(0.5, 0.12, 1.24), hand_l_dir=(0.6, 0.6, -0.4), hand_l_up=(0.2, 0.0, 1.0), fingers_l=0.2)
_defl_l2 = mod(_defl_l, hips=(0.0, 0.11, -0.16), grip=(-0.11, -0.49, 1.29), blade=(0.76, -0.58, -0.27))
add("ParrySuccessL", 12, [(0, GUARD, "lin"), (1, _defl_l, "snap"), (3, _defl_l2, "lin"), (7, mod(COUNTER, hips=(0.0, 0.1, -0.14)), "sine"),
                          (12, COUNTER, "sine")],
    timing={"impact": 1, "hold": [1, 3], "counter_ready": 7, "chain_to": "COUNTER"},
    notes="desvía hacia su izquierda y abajo, el cuerpo gira con el golpe; 2 cuadros quieto y queda cargado")
# PERFECTO: la hoja salta arriba con la palma adelante (el destello), queda arriba 3 cuadros y baja girando
# hasta una guardia agazapada, la hoja atrás apuntando: se lee "ahora te toca a vos"; se endereza en la carga del
# contraataque (COUNTER) para que el Corte 1 salga sin salto
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
                         (9, LOW_COUNTER, "out"), (14, COUNTER, "sine")],
    timing={"impact": 1, "hold": [1, 4], "counter_ready": 9, "chain_to": "COUNTER"},
    notes="parry perfecto: la hoja salta arriba y la palma adelante (3 cuadros), baja girando a una guardia agazapada y "
          "queda cargado como el Corte 1")

# =========================================================================== golpe propio desviado
# el enemigo devuelve el golpe (Blocked): la hoja sale despedida arriba y atrás, el cuerpo se va hacia atrás
# con un saltito y cae agachado SOBRE LAS HUELLAS DE LA GUARDIA (después no se corre nada: el clip termina en la
# guardia sin arrastrar los pies). El empujón del juego (Push 0.9: ~1.3 m en 0.3 s) lo desliza en el mundo hasta
# f9: esos dos cuadros de patinada al caer son a propósito (frena sobre las suelas)
_knock = feet(mod(READY, hips=(0.0, 0.14, -0.06), hips_rot=(-12.0, 0.0, -8.0), spine=(-14.0, 0.0, -6.0), head=(4.0, 0.0, 8.0),
                  clav_r=(0.0, 14.0, 0.0), grip=(-0.45, 0.12, 1.74), blade=(-0.3, 0.55, 0.78), edge=(0.0, -0.8, 0.6),
                  elbow_r=(-0.8, 0.4, 0.3), hand_l=(0.55, 0.18, 1.36), hand_l_dir=(0.6, 0.4, 0.5), hand_l_up=(0.0, 0.5, 0.8),
                  fingers_l=0.05),
              r=toe("R", *R_FOOT, 30.0), l=flat("L", *L_FOOT))
_knock_air = feet(mod(_knock, hips=(0.0, 0.12, -0.04), lift=0.12, hips_rot=(-8.0, 0.0, -6.0)),
                  r=air(-0.24, -0.25, 0.42, -16.0, 6.0), l=air(0.3, 0.2, 0.36, 10.0, 30.0))
_knock_land = feet(mod(READY, hips=(0.0, 0.1, -0.18), hips_rot=(8.0, 0.0, 6.0), spine=(14.0, 0.0, -4.0), head=(-14.0, 0.0, 0.0),
                       grip=(-0.6, -0.1, 1.15), blade=(-0.45, -0.5, 0.74), edge=(-0.2, -0.75, -0.6), hand_l=(0.48, -0.2, 1.1),
                       fingers_l=0.3),
                   r=flat("R", *R_FOOT), l=toe("L", *L_FOOT, 20.0))
add("Blocked", 14, [(0, READY, "lin"), (1, _knock, "snap"), (4, _knock_air, "out"),
                    (6, feet(inter(_knock_air, _knock_land, 0.8), r=hover("R", R_FOOT[0], R_FOOT[1], R_FOOT[2], 0.04),
                             l=hover("L", L_FOOT[0], L_FOOT[1], L_FOOT[2], 0.06)), "sine"),
                    (7, _knock_land, "in2"), (14, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="rebote contra la guardia: la hoja sale despedida arriba-atrás, saltito hacia atrás, cae agachado en la guardia")

# =========================================================================== recibir daño
# el juego lo empuja (Push: 0.8-1.5 m en 0.3-0.5 s) y lo da vuelta hacia el golpe: los pies apoyados patinan EN EL
# MUNDO a propósito (frena sobre las suelas); dentro del clip no se corren (el final es la guardia sin arrastre)
_hit = feet(mod(READY, hips=(0.0, 0.12, -0.08), hips_rot=(-12.0, 0.0, 8.0), spine=(-14.0, 0.0, 6.0), head=(8.0, 4.0, 10.0),
                clav_r=(0.0, 8.0, 0.0), clav_l=(0.0, -8.0, 0.0), grip=(-0.62, 0.02, 1.08), blade=(-0.62, 0.4, -0.45),
                edge=(0.0, 0.7, 0.7), elbow_r=(-0.8, 0.3, 0.0), hand_l=(0.56, 0.12, 1.3), hand_l_dir=(0.7, 0.3, 0.4),
                hand_l_up=(0.0, 0.0, 1.0), fingers_l=0.05),
            r=toe("R", *R_FOOT, 20.0), l=flat("L", *L_FOOT))
_hit2 = mod(_hit, hips=(0.0, 0.13, -0.1), spine=(-12.0, 0.0, 6.0), head=(6.0, 4.0, 10.0))
_hit_rec = feet(mod(READY, hips=(0.0, 0.07, -0.13), spine=(12.0, 0.0, -6.0), head=(-12.0, 0.0, -2.0), grip=(-0.58, -0.22, 0.98)),
                r=flat("R", *R_FOOT), l=flat("L", *L_FOOT))
add("Hit", 11, [(0, READY, "lin"), (1, _hit, "snap"), (3, _hit2, "lin"), (6, _hit_rec, "sine"), (11, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="golpe liviano: la cabeza y el pecho se van atrás de golpe, los brazos se abren; recupera la guardia en 0.37 s")
_hh = mod(_hit, hips=(0.0, 0.16, -0.06), hips_rot=(-20.0, 0.0, 10.0), spine=(-18.0, 0.0, 8.0), head=(14.0, 6.0, 14.0),
          grip=(-0.66, 0.15, 1.2), blade=(-0.55, 0.6, -0.3), hand_l=(0.6, 0.2, 1.42))
_hh_air = feet(mod(_hh, lift=0.16, hips=(0.0, 0.14, -0.06), hips_rot=(-14.0, 0.0, 6.0)),
               r=air(-0.24, -0.3, 0.45, -20.0, 6.0), l=air(0.3, 0.05, 0.4, -8.0, 30.0))
# cae en tres apoyos: los dos pies (sobre las huellas de la guardia: después no se arrastran) y la mano izquierda en
# el piso, agachado (se lee "me voltearon")
_hh_land = feet(mod(READY, hips=(0.0, 0.16, -0.3), hips_rot=(24.0, 0.0, 10.0), spine=(18.0, 0.0, 0.0), head=(-20.0, 0.0, 0.0),
                    grip=(-0.62, -0.05, 0.85), blade=(-0.6, 0.2, 0.77), edge=(-0.6, -0.5, -0.6), hand_l=(0.42, -0.5, 0.46),
                    hand_l_dir=(0.1, -0.8, -0.6), hand_l_up=(0.0, 0.0, 1.0), elbow_l=(0.8, 0.2, 0.4), fingers_l=0.0),
                r=flat("R", *R_FOOT), l=toe("L", *L_FOOT, 30.0))
_hh_land2 = mod(_hh_land, hips=(0.0, 0.17, -0.32), hand_l=(0.42, -0.5, 0.45))
add("HitHeavy", 20, [(0, READY, "lin"), (1, _hh, "snap"), (3, _hh_air, "out"),
                     (5, feet(inter(_hh_air, _hh_land, 0.75), r=hover("R", R_FOOT[0], R_FOOT[1], R_FOOT[2], 0.05),
                              l=hover("L", L_FOOT[0], L_FOOT[1], L_FOOT[2], 0.07)), "sine"),
                     (6, _hh_land, "in2"), (11, _hh_land2, "sine"), (20, READY, "sine")],
    timing={"impact": 1, "slide_ok": True},
    notes="golpe pesado: lo levanta, cae en tres apoyos con la mano en el piso y se para (0.65 s)")

# =========================================================================== muerte
# se va atrás (el pie derecho da un paso atrás), se tambalea, el izquierdo se va atrás y apoya la rodilla, y cae
# de costado: antes de caer los pies se despegan (las rodillas quedan en el piso y las suelas suben); ningún pie
# se arrastra, y en la cámara lenta de Die (x0.25) se vería
_d_snap = mod(_hh, hips=(0.0, 0.14, -0.06), head=(16.0, 6.0, 12.0))
_d_stag = feet(mod(READY, hips=(0.0, 0.08, -0.16), hips_rot=(16.0, 0.0, -6.0), spine=(20.0, 0.0, -4.0), head=(14.0, -4.0, -6.0),
                   clav_r=(0.0, -6.0, 0.0), clav_l=(0.0, 6.0, 0.0), grip=(-0.5, -0.1, 0.8), blade=(-0.45, -0.6, -0.4),
                   edge=(-0.5, 0.2, -0.8), elbow_r=(-0.6, 0.3, -0.7), hand_l=(0.3, -0.25, 0.95), hand_l_dir=(0.0, -0.4, -0.9),
                   hand_l_up=(1.0, 0.0, 0.0), fingers_l=0.5),
               r=flat("R", -0.24, -0.3, 4.0), l=toe("L", *L_FOOT, 20.0))
# una rodilla en el piso (la izquierda), la katana colgando de la mano; los brazos en el espacio del pecho (cuelgan
# con el tronco vencido)
_D_KNEE_L = plant("L", 0.28, 0.5, 70.0, 20.0, "toe")
_d_knee = feet(mod(READY, hips=(0.0, 0.12, -0.34), hips_rot=(18.0, 0.0, -4.0), spine=(20.0, 0.0, -4.0), head=(18.0, -6.0, -4.0),
                   clav_r=(0.0, -8.0, 0.0), clav_l=(0.0, 8.0, 0.0), arm_space=1.0, grip=(-0.46, -0.2, 0.98),
                   blade=(-0.3, -0.75, -0.6), edge=(-0.9, 0.3, 0.0), elbow_r=(-0.6, 0.4, -0.6), hand_l=(0.34, -0.18, 1.0),
                   hand_l_dir=(0.0, -0.3, -0.95), hand_l_up=(1.0, 0.0, 0.0), fingers_l=0.4, knee_l=(0.2, -0.6, -0.8)),
               r=flat("R", -0.24, -0.3, 4.0), l=_D_KNEE_L)
_d_knee2 = mod(_d_knee, hips=(0.0, 0.12, -0.35), head=(24.0, -6.0, -4.0))
# cae hacia adelante y de costado (su izquierda): la cabeza enorme apoya de lado, el cuerpo atrás sobre la cadera
_d_fall = feet(mod(READY, hips=(0.14, -0.12, -0.2), hips_rot=(54.0, 38.0, 6.0), spine=(-6.0, 6.0, 0.0), head=(-18.0, 16.0, 0.0),
                   clav_r=(0.0, 0.0, 10.0), arm_space=1.0, grip=(-0.6, -0.42, 1.1), blade=(-0.5, -0.86, 0.1), edge=(0.0, 0.0, 1.0),
                   elbow_r=(-0.4, 0.4, -0.8), hand_l=(0.5, -0.42, 1.12), hand_l_dir=(0.1, -0.4, 0.9), hand_l_up=(0.0, 1.0, 0.3),
                   fingers_l=0.3, knee_l=(0.3, -0.8, 0.0), knee_r=(-0.3, -0.8, 0.0)),
               r=lifted("R", -0.2, 0.34, 0.035, 30.0, 0.0), l=lifted("L", 0.3, 0.38, 0.035, 40.0, 30.0))
# tendido: las puntas bajan a tocar el piso en el mismo lugar (se asientan, no se arrastran)
_d_rest = feet(mod(_d_fall, hips=(0.15, -0.13, -0.23), head=(-16.0, 18.0, 0.0), grip=(-0.6, -0.43, 1.08)),
               r=lifted("R", -0.2, 0.34, 0.004, 30.0, 0.0), l=lifted("L", 0.3, 0.38, 0.004, 40.0, 30.0))
_ar, _al = ankle_of(flat("R", -0.24, -0.3, 4.0)), ankle_of(_D_KNEE_L)
add("Death", 42, [(0, READY, "lin"), (2, _d_snap, "snap"),
                  (5, feet(inter(_d_snap, _d_stag, 0.5), r=lifted("R", -0.23, -0.24, 0.07, -6.0, 5.0), l=toe("L", *L_FOOT, 20.0)), "out"),
                  (8, _d_stag, "inout"),
                  (13, feet(inter(_d_stag, _d_knee, 0.45), l=lifted("L", 0.29, 0.4, 0.07, 62.0, 22.0)), "inout"),
                  (18, _d_knee, "in2"), (22, _d_knee2, "sine"),
                  (26, feet(inter(_d_knee2, _d_fall, 0.3), r=lifted("R", _ar[0], _ar[1] + 0.02, 0.08, -6.0, 4.0),
                            l=lifted("L", _al[0], _al[1], 0.08, 60.0, 22.0)), "out"),
                  (31, _d_fall, "in"), (35, mod(_d_rest, hips=(0.15, -0.13, -0.2)), "out"), (42, _d_rest, "sine")],
    timing={"impact": 2, "knee": 18, "ground": 31, "slide_ok": True},
    notes="se va atrás, se tambalea, cae sobre una rodilla y después de costado; queda tendido (la cámara lenta de Die lo estira)")

# =========================================================================== remate (iai)
# 80 cuadros con el tajo en f54.4 (FinisherStrikeAt 0.68: el juego lo teletransporta detrás del enemigo en ese
# instante). Antes: da un paso adelante con el pie derecho y se planta agachado, girado, con la katana baja atrás a
# su derecha (wakigamae: desde arriba es una cola larga que sale por detrás; Kaito tiene brazos de 30 cm y no
# llega a desenvainar desde la cadera izquierda) y la palma izquierda apuntando al enemigo; espera respirando y
# temblando cada vez más y se comprime en f50-54. En f55 ya está del otro lado (el teletransporte: f54-f55 es un
# corte, los pies cambian de lugar), de espaldas al enemigo, estirado en una zancada baja con la hoja afuera a su
# derecha: lo único que se ve del tajo es la pose de "ya corté" y la estela de tinta. Quieto (zanshin), chiburi en
# f61-65, el pie derecho vuelve con un paso y en f72 está en la guardia: el remate corto devuelve el control ahí
# (ShortFinisherEnd 0.9) y el fundido a Locomotion no arrastra los pies. El pie izquierdo no se mueve de su huella
# de la guardia en todo el clip (gira sobre la punta)
IAI = feet(mod(READY, hips=(0.0, 0.1, -0.3), hips_rot=(12.0, 0.0, -28.0), spine=(10.0, 0.0, -8.0), head=(-14.0, 0.0, 30.0),
               clav_r=(0.0, 4.0, 0.0), grip=(-0.56, 0.24, 0.92), blade=(-0.32, 0.88, 0.35), edge=(0.0, 0.35, -0.94),
               elbow_r=(-0.6, 0.6, -0.2), hand_l=(0.22, -0.48, 1.3), hand_l_dir=(-0.1, -0.5, 0.86), hand_l_up=(0.0, 1.0, 0.3),
               elbow_l=(0.8, 0.2, -0.5), fingers_l=0.0, knee_l=(0.6, -0.8, 0.0)),
           r=flat("R", -0.3, -0.38, 10.0), l=flat("L", *L_FOOT))
_step_in = feet(inter(READY, IAI, 0.5), r=lifted("R", -0.27, -0.27, 0.08, -6.0, 8.0), l=flat("L", *L_FOOT))
_iai_b = mod(IAI, breath=1.0, hips=(0.0, 0.1, -0.31), head=(-15.0, 0.0, 30.0), tremble=0.3)
_iai_deep = mod(IAI, hips=(0.0, 0.12, -0.35), hips_rot=(18.0, 0.0, -30.0), head=(-18.0, 0.0, 30.0), tremble=1.0,
                grip=(-0.56, 0.27, 0.9))
_iai_cmp = mod(IAI, hips=(0.0, 0.11, -0.36), hips_rot=(20.0, 0.0, -30.0), spine=(16.0, 0.0, -10.0), head=(-22.0, 0.0, 30.0),
               tremble=1.6, grip=(-0.55, 0.3, 0.88), hand_l=(0.2, -0.52, 1.24))
AFTER_CUT = feet(mod(READY, hips=(0.0, -0.24, -0.33), hips_rot=(14.0, 0.0, -30.0), spine=(12.0, 0.0, -16.0), head=(-8.0, 0.0, 14.0),
                     clav_r=(0.0, 10.0, 0.0), grip=(-0.8, -0.36, 1.25), blade=(-0.9, -0.3, 0.3), edge=(-0.15, 0.55, -0.82),
                     elbow_r=(-0.8, 0.0, -0.5), hand_l=(0.42, 0.08, 1.16), hand_l_dir=(0.6, 0.75, -0.2), hand_l_up=(0.0, 0.0, 1.0),
                     elbow_l=(0.6, 0.6, -0.3), fingers_l=0.05),
                 r=flat("R", -0.28, -0.64, 4.0), l=toe("L", *L_FOOT, 30.0))
_ac_hold = mod(AFTER_CUT, hips=(0.0, -0.24, -0.35), grip=(-0.81, -0.35, 1.24), head=(-9.0, 0.0, 14.0))
_chi_up = mod(_ac_hold, grip=(-0.76, -0.36, 1.42), blade=(-0.75, -0.35, 0.56), edge=(-0.3, 0.2, -0.93))
_chi_snap = mod(_ac_hold, hips=(0.0, -0.22, -0.34), grip=(-0.72, -0.3, 0.92), blade=(-0.7, -0.5, -0.45), edge=(-0.5, 0.0, -0.86))
# vuelta a la guardia: el pie derecho se levanta de la zancada y apoya en su huella; el izquierdo baja el talón
_step_out = feet(inter(_chi_snap, READY, 0.45), r=lifted("R", -0.25, -0.4, 0.08, -8.0, 5.0), l=toe("L", *L_FOOT, 18.0))
SHORT_FINISHER_END = 72
add("Finisher", 80, [
    (0, READY, "sine"), (4, _step_in, "out"), (8, IAI, "in2"), (22, _iai_b, "sine"), (36, mod(IAI, tremble=0.6), "sine"),
    (50, _iai_deep, "sine"), (54, _iai_cmp, "in2"), (55, AFTER_CUT, "hold"), (61, _ac_hold, "sine"), (63, _chi_up, "inout"),
    (65, _chi_snap, "snap"), (66, mod(_chi_snap, grip=(-0.72, -0.31, 0.93)), "lin"), (69, _step_out, "inout"),
    (SHORT_FINISHER_END, READY, "in2"), (76, _breath, "sine"), (80, READY, "sine")],
    timing={"strike": 54, "zanshin": [55, 61], "chiburi": [61, 66], "short_end": SHORT_FINISHER_END, "skid": [[54, 55]],
            "cut": [54.5]},
    events=[{"frame": 54, "fn": "Strike"}],
    notes="iai: cargado y temblando hasta f54, en f55 (FinisherStrikeAt 0.68) ya cortó y está del otro lado; chiburi, un "
          "paso y en f72 (ShortFinisherEnd 0.9) está en la guardia")

# =========================================================================== Corte del Viento (habilidad 1)
# PlayerController.TickWindSlash: 0.32 s de preparación (cámara sobre el hombro y cámara lenta), 0.16 s de viaje
# (9 m), los cortes aparecen 0.06 s después y termina a 0.55 s: 31 cuadros. Prepara como el iai (con el mismo paso
# adelante), viaja en el aire en la pose del dash (f10-f14: el juego lo mueve a 56 m/s) y llega en la pose de "ya
# corté" de espaldas a los cortados; chiburi, un paso atrás y termina en la guardia (WindSlash -> Locomotion sin
# arrastrar los pies). La cadera sin adelanto: con él, en f14 ya bajaba a la zancada y las piernas no llegaban a
# los pies del dash
_ws_cmp = mod(_iai_cmp, tremble=1.2)
add("WindSlash", 31, [
    (0, READY, "sine"), (2, _step_in, "out"), (4, IAI, "in2"), (8, _iai_deep, "sine"), (9, _ws_cmp, "in2"), (10, _dash, "lin"),
    (14, _dash_b, "sine"), (15, AFTER_CUT, "out"), (20, _ac_hold, "sine"), (22, _chi_up, "inout"), (24, _chi_snap, "snap"),
    (27, _step_out, "inout"), (30, READY, "in2"), (31, READY, "sine")], lag=mod(LEAD, hips=0.0, hips_rot=0.0),
    timing={"phases": {"prep": [0, 9.6], "travel": [9.6, 14.4], "slashes": 16.2, "end": 31}, "airborne": [10, 14]},
    notes="prepara (iai) 0.32 s, viaja 0.16 s en el aire en la pose del dash, llega de espaldas con la hoja afuera; "
          "chiburi, un paso y guardia")

# =========================================================================== Torbellino de Hojas (habilidad 2)
# PlayerController.TickWhirlwind gira el MODELO 720° (horario visto desde arriba) entre 0.12 y 0.74 s (f3.6-f22.2): el
# clip no gira, pone la pose del trompo. Se enrosca a su izquierda (contra el giro) sobre las puntas de los pies en
# las huellas de la guardia, y en f4 ya está en el aire: el giro arranca rapidísimo (EaseOut: 30° en el primer medio
# cuadro) y un pie apoyado dibujaría un círculo en el piso. En el aire los pies van juntos bajo el centro, la hoja
# estirada a su derecha a la altura de la cintura con el filo hacia atrás (al girar horario, el lado derecho barre
# hacia atrás) y el brazo izquierdo abierto; baja casi vertical sobre las huellas de la guardia cuando ya no gira
_wh_coil = feet(mod(READY, hips=(0.0, 0.04, -0.2), hips_rot=(10.0, 0.0, 30.0), spine=(10.0, 0.0, 24.0), head=(-12.0, 0.0, -20.0),
                    grip=(0.1, -0.32, 1.0), blade=(0.8, 0.3, -0.25), edge=(-0.3, 0.9, 0.0), elbow_r=(-0.3, -0.3, -0.9),
                    hand_l=(0.45, 0.25, 1.2), fingers_l=0.6),
                r=toe("R", *R_FOOT, 26.0), l=toe("L", *L_FOOT, 26.0))
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
    (23, feet(inter(_wh_spin, _wh_land, 0.6), r=hover("R", R_FOOT[0], R_FOOT[1], R_FOOT[2], 0.05),
              l=hover("L", L_FOOT[0], L_FOOT[1], L_FOOT[2], 0.05)), "sine"),
    (24, _wh_land, "in2"), (30, READY, "sine")],
    timing={"phases": {"coil": [0, 3.6], "spin": [3.6, 22.2], "end": 29.7}, "spin": [3.6, 22.2, -720.0], "airborne": [4, 22]},
    notes="enrosque en puntas, trompo en el aire con la hoja afuera a su derecha (el código gira el modelo 720°), cae "
          "agachado en la guardia")

# =========================================================================== gestos de exploración
# Rezar en el santuario (Checkpoint): el pie izquierdo da un paso atrás y apoya la rodilla; la katana ofrecida hacia
# el santuario, la punta arriba y adelante y las dos manos juntas en la empuñadura a la altura del pecho (el voto del
# samurái), la cabeza inclinada. Vertical quedaba escondida atrás del pelo desde la cámara del juego; inclinada 40°
# hacia adelante es una raya que sale de la silueta por delante y por arriba: se lee "reza" y no "se agachó".
# Respira y la cabeza se inclina un poco más (espera que se mueve); el pie vuelve con otro paso. Moverse lo corta
# (PlayerController.TickLocomotion)
_pray = feet(mod(READY, hips=(0.0, 0.1, -0.34), hips_rot=(4.0, 0.0, 0.0), spine=(6.0, 0.0, 0.0), head=(18.0, 0.0, 0.0),
                 grip=(-0.05, -0.48, 1.08), blade=(0.0, -0.64, 0.77), edge=(0.0, -0.77, -0.64), elbow_r=(-0.8, 0.1, -0.6),
                 grip_l=1.0, elbow_l=(0.8, 0.1, -0.6), fingers_l=1.0, knee_l=(0.2, -0.6, -0.8)),
             r=flat("R", *R_FOOT), l=plant("L", 0.26, 0.46, 70.0, 10.0, "toe"))
_pray_b = mod(_pray, breath=1.0, hips=(0.0, 0.1, -0.35), head=(22.0, 0.0, 0.0))
_pray_d = mod(_pray, hips=(0.0, 0.1, -0.355), head=(24.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0))
add("Pray", 40, [(0, READY, "sine"), (5, feet(inter(READY, _pray, 0.45), l=lifted("L", 0.27, 0.4, 0.07, 62.0, 12.0)), "inout"),
                 (10, _pray, "in2"), (17, _pray_b, "sine"), (24, _pray_d, "sine"), (30, _pray, "sine"),
                 (35, feet(inter(_pray, READY, 0.55), l=lifted("L", 0.28, 0.38, 0.06, 40.0, 24.0)), "inout"), (40, READY, "in2")],
    timing={"kneel": 10, "rise": 30},
    notes="paso atrás y rodilla al piso, la katana ofrecida hacia adelante y arriba con las dos manos (1.33 s)")
# Juntar algo (la mitad de la llave): se agacha, la mano izquierda baja, la cierra y se para
_reach = feet(mod(READY, hips=(0.0, 0.06, -0.26), hips_rot=(18.0, 0.0, 6.0), spine=(22.0, 0.0, 4.0), head=(16.0, 0.0, -4.0),
                  arm_space=0.0, hand_l=(0.26, -0.5, 0.42), hand_l_dir=(0.0, -0.6, -0.8), hand_l_up=(1.0, 0.0, 0.0),
                  elbow_l=(0.8, 0.2, -0.4), fingers_l=0.0),
              r=flat("R", *R_FOOT), l=toe("L", *L_FOOT, 20.0))
add("Interact", 20, [(0, READY, "sine"), (7, _reach, "inout"), (10, mod(_reach, fingers_l=1.0, hand_l=(0.26, -0.48, 0.44)), "out"),
                     (20, READY, "inout")],
    timing={"grab": 10}, notes="se agacha a juntar algo con la mano izquierda (0.67 s)")


# =========================================================================== empalmes
# (clip, cuadro (-1 = el último), clip siguiente, cuadro en que arranca, tope en grados): los crossfades cortos
# del código. Los del combo son exactos, los del contraataque casi (en el f2 del Corte 1 la mano libre todavía
# trae 0.4 cuadros de atraso: 4°); el corte buffereado desde el dash (0.05 s de
# fundido desde f11) tolera la caída, y el remate corto (0.2 s de fundido a Locomotion) el atraso de la mano libre
RIPOSTE_FRAME = 2
CHAINS = [
    ("Attack1", -1, "Attack2", 0, 1.0), ("Attack2", -1, "Attack3", 0, 1.0), ("Attack3", -1, "Attack1", 0, 1.0),
    ("Attack3", -1, "Idle", 0, 1.0),
    ("ParrySuccessR", -1, "Attack1", RIPOSTE_FRAME, 6.0), ("ParrySuccessL", -1, "Attack1", RIPOSTE_FRAME, 6.0),
    ("PerfectParry", -1, "Attack1", RIPOSTE_FRAME, 6.0), ("ParryStance", 2, "ParrySuccessR", 0, 1.0),
    ("Dash", 11, "Attack1", 0, 40.0), ("Dash", -1, "Idle", 0, 12.0), ("ParryStance", -1, "Idle", 0, 1.0),
    ("Blocked", -1, "Idle", 0, 1.0), ("Hit", -1, "Idle", 0, 1.0), ("HitHeavy", -1, "Idle", 0, 1.0),
    ("Finisher", SHORT_FINISHER_END, "Idle", 0, 15.0), ("Finisher", -1, "Idle", 0, 1.0), ("WindSlash", -1, "Idle", 0, 1.0),
    ("Whirlwind", -1, "Idle", 0, 1.0), ("Pray", -1, "Idle", 0, 1.0), ("Interact", -1, "Idle", 0, 1.0),
]
