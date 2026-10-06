"""Banco de pruebas de FX/SpringChain.cs (Python 3 + numpy + matplotlib, sin Unity).

    python Tools/Blender/characters/kits/spring_sim.py OUT_DIR

Copia el algoritmo de SpringChain (verlet en el mundo, rigidez hacia la pose animada, amortiguación relativa al
ancla, arrastre del aire, viento suave, largo fijo, ángulo máximo, esferas del cuerpo y piso) y lee los perfiles
del propio .cs, así lo que se mide acá es lo que corre en el juego. Escenario: quieto, carrera a 5 m/s, frenada
seca, quieto, media vuelta en el lugar y un golpe que empuja hacia atrás. Escribe:
  spring_angles.png  ángulo de la punta (la forma que se dibuja, interpolada entre pasos) respecto de la pose
                     animada para cada tipo de accesorio, a 30, 60 y 144 fps: con pasos fijos de 1/60 s las
                     curvas tienen que coincidir
  spring_strip.png   la cola del hachimaki y la capa de paja vistas de costado en momentos del escenario
e imprime por perfil el desvío máximo corriendo, el tiempo hasta asentarse después de frenar y si alguna
partícula entró en el cuerpo.
"""
import os, re, sys, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.join(HERE, "..", "..", "..", "..", "Nindo", "Assets", "Nindo", "Scripts", "FX", "SpringChain.cs")
STEP = 1 / 60
MAX_STEPS = 4
G = np.array([0.0, -9.81, 0.0])
UP = np.array([0.0, 1.0, 0.0])


def profiles():
    """Los perfiles tal cual están en SpringChain.ProfileFor."""
    src = open(CS, encoding="utf-8").read()
    out = {}
    for kind, args in re.findall(r'case "(\w+)": return new Profile\(([^)]*)\)', src):
        out[kind] = [float(a.strip().rstrip("f")) for a in args.split(",")]
    return out


# geometría de reposo en metros de juego, en el marco del personaje (x adelante, y arriba, z a su izquierda):
# (hueso ancla, puntos de la cadena relativos al centro de la cadera del personaje)
CHAINS = {
    "Tail": [(-0.13, 1.56, 0.0), (-0.17, 1.47, 0.03), (-0.21, 1.35, 0.06), (-0.23, 1.23, 0.09), (-0.25, 1.11, 0.11)],
    "Cape": [(-0.22, 1.16, 0.0), (-0.27, 0.88, 0.0), (-0.30, 0.64, 0.0), (-0.32, 0.40, 0.0)],
    "Shide": [(0.23, 0.78, 0.07), (0.24, 0.71, 0.07), (0.25, 0.64, 0.07), (0.25, 0.58, 0.07)],
    "Float": [(-0.14, 0.77, 0.22), (-0.14, 0.67, 0.22), (-0.14, 0.55, 0.22)],
    "Tasset": [(0.21, 0.76, 0.13), (0.26, 0.54, 0.15)],
    "Apron": [(0.60, 1.15, 0.0), (0.62, 0.83, 0.0), (0.63, 0.50, 0.0)],
    "Leaf": [(-0.08, 1.72, 0.02), (-0.17, 1.64, 0.05), (-0.24, 1.51, 0.09), (-0.28, 1.36, 0.12), (-0.30, 1.23, 0.14)],
    "Flap": [(0.24, 0.77, 0.0), (0.26, 0.64, 0.0), (0.27, 0.51, 0.0)],
    # los del sumo, a escala de ninja: se mide la dinámica del perfil, no el cuerpo
    "Tie": [(-0.18, 1.50, 0.02), (-0.27, 1.40, 0.05), (-0.31, 1.27, 0.07), (-0.33, 1.14, 0.08)],
    "Chimes": [(0.62, 1.10, 0.0), (0.64, 0.95, 0.0), (0.65, 0.78, 0.0)],
    "Tassel": [(0.62, 1.12, 0.08), (0.63, 0.97, 0.09), (0.64, 0.80, 0.10)],
}
# esferas del cuerpo (centro en el marco del personaje, radio en m): cabeza, pecho, cadera, muslos
SPHERES = [((0.0, 1.47, 0.0), 0.23), ((-0.01, 1.07, 0.0), 0.21), ((-0.01, 0.81, 0.0), 0.21),
           ((0.01, 0.51, 0.13), 0.12), ((0.01, 0.51, -0.13), 0.12)]


def _vel(t):
    """Velocidad hacia +x: 0-0.6 quieto, 0.6-0.85 acelera, 0.85-2.0 corre a 5 m/s, 2.0-2.15 frena, después quieto."""
    if t < 0.6: return 0.0
    if t < 0.85: return 5.0 * (t - 0.6) / 0.25
    if t < 2.0: return 5.0
    if t < 2.15: return 5.0 * (1 - (t - 2.0) / 0.15)
    return 0.0


_TT = np.arange(0.0, 8.0, 0.001)
_XX = np.cumsum([_vel(t) for t in _TT]) * 0.001


def scenario(t):
    """(posición del personaje, yaw en radianes) en el instante t (s): la carrera, media vuelta en el lugar de 3.6 a
    3.9 s y a los 4.8 s un golpe que lo empuja 0.5 m hacia atrás en 0.12 s."""
    x = float(np.interp(t, _TT, _XX))
    yaw = math.pi * min(1.0, (t - 3.6) / 0.3) if t > 3.6 else 0.0
    if t > 4.8:
        x += 0.5 * min(1.0, (t - 4.8) / 0.12)
    return np.array([x, 0.0, 0.0]), yaw


def to_world(p, pos, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = p
    return pos + np.array([c * x + s * z, y, -s * x + c * z])


class Chain:
    def __init__(self, kind, prof):
        self.kind = kind
        self.p = dict(zip(("stiffness", "damping", "airDrag", "gravity", "maxAngle", "flutter", "radius"), prof))
        self.rest = [np.array(q) for q in CHAINS[kind]]
        n = len(self.rest)
        self.pos = np.zeros((n, 3)); self.prev = np.zeros((n, 3))
        self.target = np.zeros((n, 3)); self.last = np.zeros((n, 3))
        self.phase = (sum(map(ord, kind)) & 1023) * 0.0061
        self.inside = 0.0


def wind(t):
    a = 0.6 + math.sin(t * 0.11) * 0.5
    return np.array([math.cos(a), 0.0, math.sin(a)])


def simulate(c, u, t, spheres):
    """Un paso fijo de 1/60 s (SpringChain.Simulate): u = instante del paso dentro del frame (anclas y esferas)."""
    p = c.p
    n = len(c.pos) - 1
    stiff = p["stiffness"]
    damp = 1 - p["damping"]
    drag = 1 - p["airDrag"]
    a0 = c.last[0] + (c.target[0] - c.last[0]) * u
    anchor_vel = a0 - c.pos[0]
    c.pos[0] = c.prev[0] = a0
    w = wind(t)
    gust = w * (p["flutter"] * (0.55 + 0.45 * math.sin(t * 1.7 + c.phase * 6.3))) +         np.cross(w, UP) * (p["flutter"] * 0.5 * math.sin(t * 3.1 + c.phase * 11))
    accel = (G * p["gravity"] + gust) * STEP * STEP
    max_rad = math.radians(p["maxAngle"])
    for i in range(1, n + 1):
        ti = c.last[i] + (c.target[i] - c.last[i]) * u
        tp = c.last[i - 1] + (c.target[i - 1] - c.last[i - 1]) * u
        rest = ti - tp
        ln = np.linalg.norm(rest)
        vel = (c.pos[i] - c.prev[i]) * drag
        vel = anchor_vel + (vel - anchor_vel) * damp
        c.prev[i] = c.pos[i].copy()
        x = c.pos[i] + vel + accel
        x = x + (c.pos[i - 1] + rest - x) * stiff
        for s0, s1, sr in spheres:
            r = sr + p["radius"] * 0.55       # grosor en unidades del FBX -> metros (1 u ~ 0.55 m)
            sc = s0 + (s1 - s0) * u           # las esferas interpolan entre frames como las anclas
            d = x - sc
            m = np.dot(d, d)
            if 1e-10 < m < r * r:
                x = sc + d * (r / math.sqrt(m))
        floor = p["radius"] * 0.55
        x[1] = max(x[1], floor)
        dvec = x - c.pos[i - 1]
        rd = rest / ln
        dn = dvec / max(np.linalg.norm(dvec), 1e-9)
        ang = math.acos(max(-1.0, min(1.0, float(np.dot(rd, dn)))))
        if ang > max_rad:
            # RotateTowards: gira la pose animada hacia dvec como mucho max_rad
            axis = np.cross(rd, dn)
            an = np.linalg.norm(axis)
            axis = axis / an if an > 1e-9 else np.array([0.0, 0.0, 1.0])
            dn = rd * math.cos(max_rad) + np.cross(axis, rd) * math.sin(max_rad) + axis * np.dot(axis, rd) * (1 - math.cos(max_rad))
        c.pos[i] = c.pos[i - 1] + dn * ln


def run(kind, prof, fps, T=6.0):
    """SpringChain.LateUpdate: acumulador de pasos fijos y forma dibujada = interpolación de los dos últimos pasos
    (relativa al ancla) sobre el ancla del frame."""
    c = Chain(kind, prof)
    dt = 1 / fps
    acc = 0.0
    times, angles, shapes = [], [], []
    t = 0.0
    first = True
    while t < T:
        pos, yaw = scenario(t)
        for i, q in enumerate(c.rest):
            c.target[i] = to_world(q, pos, yaw)
        now = [to_world(np.array(sc), pos, yaw) for sc, r in SPHERES]
        if first:
            c.pos[:] = c.prev[:] = c.last[:] = c.target
            shape_prev = shape_last = c.target - c.target[0]
            spheres = [(a, a, r) for a, (_, r) in zip(now, SPHERES)]
            first = False
        else:
            spheres = [(b, a, r) for b, a, (_, r) in zip(before, now, SPHERES)]
            acc = min(acc + dt, MAX_STEPS * STEP)
            while acc >= STEP:
                acc -= STEP
                simulate(c, min(1.0, max(0.0, 1 - acc / dt)), t, spheres)
                shape_prev, shape_last = shape_last, c.pos - c.pos[0]
        before = now
        c.last[:] = c.target
        shape = shape_prev + (shape_last - shape_prev) * (acc / STEP)
        # desvío de la punta: ángulo entre (punta - ancla) dibujado y animado
        a = shape[-1]; b = c.target[-1] - c.target[0]
        ang = math.degrees(math.acos(max(-1, min(1, np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))))
        drawn = c.target[0] + shape
        for _, sc, r in spheres:
            for q in drawn[1:]:
                if np.linalg.norm(q - sc) < r - 0.01:
                    c.inside += dt
        times.append(t); angles.append(ang)
        shapes.append((t, pos.copy(), yaw, drawn.copy(), c.target.copy()))
        t += dt
    return np.array(times), np.array(angles), shapes, c.inside


def settle_time(times, angles, t0=2.15, tol=6.0):
    """Segundos después de frenar hasta que el desvío queda debajo de 'tol' grados (hasta la media vuelta)."""
    m = (times >= t0) & (times < 3.6)
    ts, an = times[m], angles[m]
    for i in range(len(ts)):
        if np.all(an[i:] < tol):
            return ts[i] - t0
    return float("inf")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    profs = profiles()
    kinds = [k for k in CHAINS if k in profs]
    fig, axes = plt.subplots(len(kinds), 1, figsize=(9, 1.7 * len(kinds)), sharex=True)
    # arranque: el pico al acelerar (0.6-1.3 s); corriendo: la estela ya asentada (1.3-2.0 s)
    print(f"{'perfil':8} {'arranque°':>9} {'corriendo°':>10} {'asienta s':>9} {'dentro s':>8}  "
          "(30/60/144 fps: pico al arrancar | máx corriendo)")
    for ax, kind in zip(axes, kinds):
        res = {}
        for fps, col in ((30, "#d9a93a"), (60, "#2e3d6b"), (144, "#b0302a")):
            ts, an, _, inside = run(kind, profs[kind], fps)
            res[fps] = (ts, an, inside)
            ax.plot(ts, an, color=col, lw=1.2, label=f"{fps} fps")
        ts, an, inside = res[60]

        def peak(f, t0, t1):
            tt, aa, _ = res[f]
            return aa[(tt > t0) & (tt < t1)].max()
        print(f"{kind:8} {peak(60, 0.6, 1.3):9.1f} {peak(60, 1.3, 2.0):10.1f} {settle_time(ts, an):9.2f} {inside:8.2f}  "
              + " / ".join(f"{peak(f, 0.6, 1.3):.1f}" for f in (30, 60, 144)) + "  |  "
              + " / ".join(f"{peak(f, 1.3, 2.0):.1f}" for f in (30, 60, 144)))
        ax.set_ylabel(kind, rotation=0, ha="right", va="center")
        ax.axvspan(0.6, 2.15, color="#88aacc", alpha=0.15)
        ax.axvspan(3.6, 3.9, color="#aacc88", alpha=0.2)
        ax.axvline(4.8, color="#cc8888", lw=0.8)
        ax.set_ylim(0, max(10, an.max() * 1.15))
    axes[0].legend(loc="upper right", fontsize=7, ncol=3)
    axes[0].set_title("desvío de la punta respecto de la pose animada (°): carrera (azul), media vuelta (verde), empujón (rojo)", fontsize=9)
    axes[-1].set_xlabel("s")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "spring_angles.png"), dpi=110)
    plt.close(fig)

    # tira: cola del hachimaki y capa de paja de costado (plano x-y del mundo), en el marco que sigue al personaje
    moments = [0.5, 1.0, 1.6, 2.1, 2.25, 2.5, 3.0, 3.75, 4.9]
    fig, axes = plt.subplots(2, len(moments), figsize=(1.35 * len(moments), 4.2), sharey=True)
    for row, kind in enumerate(("Tail", "Cape")):
        _, _, shapes, _ = run(kind, profs[kind], 60)
        for ax, tm in zip(axes[row], moments):
            t, pos, yaw, sim, anim = min(shapes, key=lambda s: abs(s[0] - tm))
            ax.plot(anim[:, 0] - pos[0], anim[:, 1], "o-", color="#bbbbbb", ms=2, lw=1)
            ax.plot(sim[:, 0] - pos[0], sim[:, 1], "o-", color="#b0302a" if kind == "Tail" else "#a8905a", ms=3, lw=2)
            for sc, r in SPHERES[:3]:
                w = to_world(np.array(sc), pos, yaw)
                ax.add_patch(plt.Circle((w[0] - pos[0], w[1]), r, color="#2e2b2c", alpha=0.25))
            ax.set_xlim(-0.9, 0.9); ax.set_ylim(0, 1.9); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            if row == 0:
                ax.set_title(f"{t:.2f} s", fontsize=8)
    axes[0][0].set_ylabel("hachimaki"); axes[1][0].set_ylabel("capa")
    fig.suptitle("gris = pose animada, color = simulada (corre hacia +x de 0.6 a 2.0 s, frena, media vuelta a 3.6 s)", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "spring_strip.png"), dpi=110)
    plt.close(fig)
    print("ok", out)


if __name__ == "__main__":
    main()
