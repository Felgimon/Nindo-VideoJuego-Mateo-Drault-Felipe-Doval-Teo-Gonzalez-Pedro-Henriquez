"""Ciclos de locomoción de Kaito (caminar, trotar, correr) como funciones de la fase.

Un pie apoyado está CLAVADO en el mundo: en el espacio del cuerpo su huella se corre hacia atrás a la
velocidad del suelo, en línea recta, y el pie gira sobre el talón al apoyar y sobre la punta al
despegar (ese borde no se mueve). En el vuelo el tobillo va por una spline de Hermite cuyos extremos
tienen la velocidad del apoyo: el pie despega y aterriza sin tirones (no "pisa fuerte" ni patina al
llegar). Con eso la velocidad que se autora es exacta: Unity mezcla los ciclos por Speed = v / runSpeed
y en cada umbral los pies no patinan.

DENSIDAD. A 30 fps el pie de la carrera avanza 21 cm por cuadro en el espacio del cuerpo: Unity interpola el
giro de cada hueso entre claves y el pie clavado describe un arco (patinaba 6-8 cm por apoyo y se hundía 2 cm
entre cuadros). Los ciclos se hornean con el doble de cuadros (DENSITY) y el blend tree los toca a x2
(timing 'time_scale', que generate_assets.py pone en el m_TimeScale del hijo y en la velocidad del estado).

DESPEGUE Y LLEGADA. En el vuelo la suela sube enseguida (clearance(): 3 cm en UP_FRAMES cuadros del juego en
todos los ciclos, 5 cm en el medio) y baja recién al final, casi vertical: la punta que despegaba rozando el piso
a 8 mm se arrastraba 30 cm en el trote.

Kaito es chibi: piernas de 0.32 m para correr a 6.2 m/s. No hay zancada humana que llegue: corre como un
dibujo animado, con un apoyo de 2 cuadros por pie, mucho vuelo, la cadera que se hunde en el apoyo y el
cuerpo muy inclinado; el cuerpo y la katana cuentan la velocidad desde arriba.
"""
import math
from mathutils import Vector
import nindo_anim as NA
import kaito_rig as KR

TAU = 2.0 * math.pi
DENSITY = 2                 # cuadros horneados por cuadro del juego (ver arriba)
FLOOR_U = 0.015             # luz mínima de la suela en el vuelo (u)
CLEAR_U = (0.057, 0.095)    # luz (u) al despegar del todo y en el medio del vuelo: 3 y 5 cm
UP_FRAMES = 0.6             # cuadros del juego en que la punta llega a la primera luz


def hermite(p0, m0, p1, m1, t, dt):
    t2, t3 = t * t, t * t * t
    return (p0 * (2 * t3 - 3 * t2 + 1) + m0 * dt * (t3 - 2 * t2 + t) + p1 * (-2 * t3 + 3 * t2) + m1 * dt * (t3 - t2))


class FootCycle:
    """Trayectoria de un pie en un ciclo (fase 0 = el pie apoya). Devuelve (tobillo, (cabeceo, rolido, giro)).

    stance: fracción del ciclo apoyado; heel / toe: fracción del apoyo sobre el talón al llegar y sobre la
    punta al irse; pitch_in / pitch_out: grados al apoyar (negativo = punta arriba, talón primero) y al
    despegar (talón arriba); swing: [(fase dentro del vuelo 0..1, dy, z, cabeceo)] puntos del vuelo
    relativos a la huella central."""

    def __init__(self, side, speed_u, cycle_s, stance, x, y_mid=0.0, heel=0.0, toe=0.35, pitch_in=0.0, pitch_out=40.0,
                 swing=(), yaw=0.0, pivot="toe"):
        self.side, self.v, self.T, self.d = side, speed_u, cycle_s, stance
        self.x, self.ym, self.heel, self.toe = x, y_mid, heel, toe
        self.pin, self.pout, self.yaw = pitch_in, pitch_out, yaw
        self.pivot = pivot                                  # borde sobre el que despega: 'toe' o 'ball' (carrera)
        self.L = speed_u * stance * cycle_s                 # largo de la huella recorrida en el apoyo
        self.swing = list(swing)

    def stance_at(self, u):
        """u en [0, 1] del apoyo: (tobillo, giro) con la huella moviéndose hacia atrás (+Y) a v."""
        y = self.ym - self.L * 0.5 + self.L * u
        if self.heel > 0 and u < self.heel:
            k = 1.0 - u / self.heel
            return KR.foot_on(self.side, self.x, y, self.pin * k * k, self.yaw, "heel")
        if u > 1.0 - self.toe:
            k = (u - (1.0 - self.toe)) / self.toe
            p0 = self.pin if self.heel <= 0 else 0.0
            return KR.foot_on(self.side, self.x, y, p0 + (self.pout - p0) * k * k, self.yaw, self.pivot)
        p0 = self.pin if self.heel <= 0 else 0.0
        return KR.foot_on(self.side, self.x, y, p0, self.yaw, self.pivot if p0 > 0 else "flat")

    def at(self, phase):
        ph = phase % 1.0
        if ph < self.d:
            a, r = self.stance_at(ph / self.d)
            return Vector(a), r
        # vuelo: Hermite entre el despegue y el próximo apoyo pasando por los puntos del vuelo
        eps = 1e-3
        a1, r1 = self.stance_at(1.0)
        a1b, r1b = self.stance_at(1.0 - eps)
        a0, r0 = self.stance_at(0.0)
        a0b, r0b = self.stance_at(eps)
        sw = 1.0 - self.d
        dts = self.d * eps                      # fase de eps de apoyo
        v_off = (Vector(a1) - Vector(a1b)) / dts
        v_on = (Vector(a0b) - Vector(a0)) / dts
        # el giro del pie sale del despegue a la mitad de su velocidad: con la de la punta (que se para de golpe)
        # el pie seguía girando en el vuelo y la punta se clavaba en el piso
        p_off = 0.5 * (r1[0] - r1b[0]) / dts
        p_on = (r0b[0] - r0[0]) / dts
        pts = [(0.0, Vector(a1), v_off, r1[0], p_off)]
        for (s, dy, z, pit) in self.swing:
            pts.append((s * sw, Vector((self.x, self.ym + dy, z)), None, pit, None))
        pts.append((sw, Vector(a0), v_on, r0[0], p_on))
        # tangentes de los puntos del medio por diferencias (Catmull con tiempos)
        for i in range(1, len(pts) - 1):
            t0, P0 = pts[i - 1][0], pts[i - 1][1]
            t2, P2 = pts[i + 1][0], pts[i + 1][1]
            m = (P2 - P0) / max(1e-6, t2 - t0)
            pm = (pts[i + 1][3] - pts[i - 1][3]) / max(1e-6, t2 - t0)
            pts[i] = (pts[i][0], pts[i][1], m, pts[i][3], pm)
        s = ph - self.d
        for i in range(len(pts) - 1):
            ta, tb = pts[i][0], pts[i + 1][0]
            if s <= tb or i == len(pts) - 2:
                dt = max(1e-6, tb - ta)
                t = max(0.0, min(1.0, (s - ta) / dt))
                P = hermite(pts[i][1], pts[i][2], pts[i + 1][1], pts[i + 1][2], t, dt)
                pit = hermite(pts[i][3], pts[i][4], pts[i + 1][3], pts[i + 1][4], t, dt)
                s_up = min(0.3, UP_FRAMES / (sw * self.T * NA.FPS))
                return self.clear_floor(P, pit, clearance(s / sw, s_up)), (pit, 0.0, self.yaw)
        return Vector(a0), r0


    def clear_floor(self, ankle, pitch, floor=FLOOR_U):
        """En el vuelo ningún borde de la suela baja del piso: si la punta o el talón quedarían abajo, el
        tobillo sube lo justo."""
        A = KR.ankle_rest(self.side)
        R = KR.foot_rot(pitch, 0.0, self.yaw)
        low = min((ankle + R @ (P - A)).z for P in KR.sole_corners(self.side))
        if low < floor:
            ankle = ankle + Vector((0.0, 0.0, floor - low))
        return ankle

    def stance_frames(self, frames, offset):
        """Cuadros del ciclo (0..frames) en los que este pie está apoyado."""
        return [f for f in range(frames + 1) if ((f / frames + offset) % 1.0) <= self.d + 1e-6]


def clearance(s, s_up=0.12):
    """Luz mínima de la suela (u) en la fracción s del vuelo: la punta se despega del piso de entrada (la rampa
    arranca con pendiente: con una suave la punta seguía rozando medio cuadro mientras el pie ya iba adelante),
    se mantiene y cae casi vertical en el último 8 % (el pie se planta, no entra patinando)."""
    def smooth(a, b, x):
        k = max(0.0, min(1.0, (x - a) / (b - a)))
        return k * k * (3.0 - 2.0 * k)
    up = (FLOOR_U + (CLEAR_U[0] - FLOOR_U) * math.sin(0.5 * math.pi * min(1.0, s / s_up))
          + (CLEAR_U[1] - CLEAR_U[0]) * smooth(s_up, 0.45, s))
    return FLOOR_U + (up - FLOOR_U) * (1.0 - smooth(0.92, 1.0, s))


class Gait:
    """Un ciclo de locomoción completo (pie izquierdo apoya en la fase 0, el derecho en 0.5). 'frames' son cuadros
    del juego (30 fps); el clip horneado tiene frames * DENSITY."""

    def __init__(self, name, speed_mps, frames, feet, body, notes=""):
        self.name, self.speed_mps, self.frames = name, speed_mps, frames
        self.n = frames * DENSITY
        self.v = speed_mps * KR.U_PER_M
        self.feet = feet                # {"l": FootCycle, "r": FootCycle}
        self.body = body                # body(phase) -> dict de controles del cuerpo y los brazos
        self.notes = notes

    def controls(self, f):
        ph = (f / self.n) % 1.0
        c = dict(self.body(ph))
        al, rl = self.feet["l"].at(ph)
        ar, rr = self.feet["r"].at(ph + 0.5)
        c["foot_l"], c["foot_l_rot"] = tuple(al), rl
        c["foot_r"], c["foot_r_rot"] = tuple(ar), rr
        return c

    def clip(self, timing=None, sheet_frames=None):
        # el clip se toca a x DENSITY: en un segundo del clip el cuerpo avanza v / DENSITY
        tm = {"ground_speed_mps": self.speed_mps, "time_scale": DENSITY, "contact_l": 0, "contact_r": self.n // 2,
              "stance_l": self.feet["l"].stance_frames(self.n, 0.0), "stance_r": self.feet["r"].stance_frames(self.n, 0.5)}
        tm.update(timing or {})
        c = NA.ProcClip(self.name, self.n, self.controls, loop=True, timing=tm, notes=self.notes,
                        root_vel=(0.0, -self.v / DENSITY, 0.0), sheet_frames=sheet_frames)
        c.gait = self
        return c


def wave(ph, amp, lag=0.0, mul=1.0):
    return amp * math.cos(TAU * (mul * ph - lag))
