"""Motor de animación del Gran Koi: poses clave + capas procedurales horneadas cuadro por cuadro.

Por qué así y no curvas a mano en el Graph Editor: un pez de 7.5 m con 44 huesos se mueve por física
(onda que viaja de la cabeza a la cola, aletas y bigotes que siguen con retardo). Las poses clave dan la
actuación legible desde arriba (la C de la anticipación, la S del golpe, la pausa) y tres capas encima
le dan el peso:
  1. onda viajera en la columna (desfase ~0.9 rad por hueso, poca amplitud en la cabeza y mucha en la cola:
     la envolvente carangiforme de una carpa);
  2. resortes amortiguados (k, c) en aletas, bigotes, branquias y shide, empujados por la aceleración
     angular y lineal de su padre: el seguimiento y el solapamiento salen solos y no se pueden olvidar;
  3. ruido suave para que ninguna pausa quede congelada (una pose quieta más de medio segundo se lee
     como un error) y para el temblor del rugido.
Cada hueso puede ir 'lag' cuadros atrás de la clave (la ola del golpe baja por la cola).
Los clips cíclicos se simulan tres vueltas y se queda la última: la costura del loop es < 1°.
"""
import math, random, zlib
from mathutils import Vector, Quaternion, Matrix
from koi_common import clamp, lerp

FPS = 30.0


# ------------------------------------------------------------------ curvas de easing (u en 0..1)
def _back_out(u, s=1.2):
    u -= 1.0
    return 1.0 + (s + 1.0) * u ** 3 + s * u ** 2


EASE = {
    "lin": lambda u: u,
    # se pasa ~5 % y vuelve. Arranca y termina con velocidad cero: el BACK puro arrancaba a 4x la velocidad
    # media justo después de un 'out' que terminaba quieto, y la vuelta se leía como un segundo golpe
    "settle": lambda u: _back_out(0.5 - 0.5 * math.cos(math.pi * u)),
    "hold": lambda u: 0.5 - 0.5 * math.cos(math.pi * u),                  # seno: pausa viva
    "ease": lambda u: 2 * u * u if u < 0.5 else 1 - 2 * (1 - u) ** 2,
    "in": lambda u: u * u * u,
    "acc": lambda u: u * u,           # acelera y termina a 2x la velocidad media: empalma con un 'out' de igual largo
    "strike": lambda u: u ** 1.6,     # suelta de un golpe: acelera hasta el contacto sin saltos de un cuadro
    "out": lambda u: 1 - (1 - u) ** 2,
}


def smooth_noise(seed, t, period=None, octaves=((1.0, 1.0), (2.3, 0.5), (4.7, 0.25))):
    """Ruido suave determinista (suma de senos con fases fijas). Con 'period' es periódico (loops)."""
    rng = random.Random(seed)
    v = 0.0
    tot = 0.0
    for f, a in octaves:
        ph = rng.uniform(0, 2 * math.pi)
        if period:
            f = max(1, round(f * period)) / period
        v += a * math.sin(2 * math.pi * f * t + ph)
        tot += a
    return v / tot


class Clip:
    """Definición de un clip. keys: [(cuadro, pose, easing hacia esta clave)]. pose = {hueso: {canal: valor}}.
    lag: {hueso: cuadros}. wave: dict(amp=escala, cycles=n, env=[(cuadro, factor)]).
    noise: [(huesos, canal, amplitud, frecuencia Hz, env)]. extra(f, t, vals): ajustes procedurales.
    timing: datos para el sidecar (tell, hold, contact, activeEnd, strikeBone, ...)."""

    def __init__(self, name, frames, keys, loop=False, lag=None, wave=None, noise=None, extra=None,
                 springs=True, timing=None, spring_gain=1.0, spring_scale=None):
        self.name = name
        self.frames = frames
        self.keys = sorted(keys, key=lambda k: k[0])
        self.loop = loop
        self.lag = lag or {}
        self.wave = wave
        self.noise = noise or []
        self.extra = extra
        self.springs = springs
        self.timing = timing or {}
        self.spring_gain = spring_gain
        self.spring_scale = spring_scale or {}


# ------------------------------------------------------------------ onda viajera y resortes
WAVE_BONES = [("head", -1, -1.5), ("spine_f", 0, 2.0), ("spine_b1", 1, 3.0), ("spine_b2", 2, 5.0),
              ("spine_b3", 3, 8.0), ("spine_b4", 4, 10.0), ("tail", 5, 13.0)]
WAVE_PHASE = 0.9

# hueso: (k, c, ángulo máx, ganancia de la palanca lineal). k = 60, c = 8 es el resorte del diseño (≈1.2 Hz,
# amortiguamiento 0.5: un rebote y medio); los bigotes y el papel son más blandos, las branquias duras.
SPRINGS = {}
for s in ("L", "R"):
    SPRINGS.update({
        f"pec_{s}2": (60, 8, 18, 0.6), f"pec_{s}3": (60, 8, 20, 0.6), f"pel_{s}": (65, 8, 18, 0.6),
        f"fluke_{s}1": (55, 7, 16, 0.5), f"fluke_{s}2": (55, 7, 20, 0.6),
        f"barbel_{s}1": (70, 8, 14, 0.5), f"barbel_{s}2": (42, 5.5, 20, 0.6),
        # la raíz del bigote (whisker_1) va rígida con la cabeza: con resorte se quedaba quieta un cuadro y
        # saltaba al siguiente en los cabezazos; el flameo lo hacen los dos tramos de afuera
        f"whisker_{s}2": (36, 5.0, 16, 0.5), f"whisker_{s}3": (30, 4.4, 20, 0.5),
        f"gill_{s}": (140, 16, 5, 0.3), f"shide_{s}": (40, 4.5, 24, 0.8),
    })
SPRINGS.update({"dorsal_1": (70, 9, 14, 0.6), "dorsal_2": (70, 9, 15, 0.6), "dorsal_3": (65, 8.5, 16, 0.6),
                "dorsal_4": (60, 8, 18, 0.6), "anal": (65, 8, 16, 0.6)})
SPRING_GAIN = 0.55   # fracción de la inercia real: es un espíritu, no un pez de 3 toneladas en el aire


def rot_of(M):
    """Rotación de una matriz de pose aunque tenga escala no uniforme o cizalla (un hijo girado bajo una
    aleta plegada): base ortonormal desde el eje del hueso (Y) y su Z ortogonalizado."""
    m = M.to_3x3()
    y = m.col[1].normalized()
    z = m.col[2] - y * m.col[2].dot(y)
    z = z.normalized() if z.length > 1e-8 else y.orthogonal().normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed().to_quaternion().normalized()


class Baker:
    def __init__(self, rig, poses):
        self.rig = rig
        self.poses = poses

    # --- valores semánticos de un hueso en el cuadro f (con lag)
    def _key_vals(self, clip, bone, f):
        keys = clip.keys
        lag = clip.lag.get(bone, 0)
        x = f - lag
        n = clip.frames
        if clip.loop:
            x = x % n
        else:
            x = clamp(x, 0, n)
        # tramo
        i = 0
        while i + 1 < len(keys) and keys[i + 1][0] <= x:
            i += 1
        k0 = keys[i]
        if i + 1 >= len(keys):
            if clip.loop:
                k1 = (keys[0][0] + n, keys[0][1], keys[0][2])
            else:
                return self._pose(k0[1]).get(bone, {})
        else:
            k1 = keys[i + 1]
        span = max(1e-6, k1[0] - k0[0])
        u = clamp((x - k0[0]) / span)
        e = EASE[k1[2]](u)
        a, b = self._pose(k0[1]).get(bone, {}), self._pose(k1[1]).get(bone, {})
        out = {}
        for c in set(a) | set(b):
            out[c] = lerp(a.get(c, 0.0), b.get(c, 0.0), e)
        return out

    def _pose(self, p):
        return self.poses[p] if isinstance(p, str) else p

    def _env(self, env, f, default=1.0):
        if not env:
            return default
        if f <= env[0][0]:
            return env[0][1]
        for (f0, v0), (f1, v1) in zip(env[:-1], env[1:]):
            if f0 <= f <= f1:
                u = (f - f0) / max(1e-6, f1 - f0)
                u = 0.5 - 0.5 * math.cos(math.pi * u)
                return lerp(v0, v1, u)
        return env[-1][1]

    def values(self, clip, f):
        """{hueso: {canal: valor}} del cuadro f con claves, onda, ruido y extras (sin resortes)."""
        rig = self.rig
        t = f / FPS
        T = clip.frames / FPS
        vals = {}
        for b in rig.names:
            v = self._key_vals(clip, b, f)
            if v:
                vals[b] = dict(v)
        if clip.wave:
            w = clip.wave
            amp = w.get("amp", 1.0) * self._env(w.get("env"), f)
            cyc = w.get("cycles", 1)
            om = 2 * math.pi * cyc / T
            for b, i, a in WAVE_BONES:
                ph = om * t - WAVE_PHASE * i + w.get("phase", 0.0)
                vals.setdefault(b, {})
                vals[b]["bend"] = vals[b].get("bend", 0.0) + a * amp * math.sin(ph)
        for k, (bones, ch, amp, hz, env) in enumerate(clip.noise):
            e = self._env(env, f)
            if not e:
                continue
            for j, b in enumerate(bones):
                per = T if clip.loop else None
                # semilla estable entre corridas (hash() de str cambia en cada proceso de Python)
                seed = zlib.crc32(f"{clip.name}|{b}|{ch}|{k}".encode())
                nz = smooth_noise(seed, t * hz, period=(T * hz) if per else None)
                vals.setdefault(b, {})
                vals[b][ch] = vals[b].get(ch, 0.0) + amp * e * nz
        if clip.extra:
            clip.extra(f, t, vals)
        return vals

    # --- horneado completo de un clip
    def bake(self, clip):
        rig = self.rig
        n = clip.frames
        frames = list(range(n + 1))
        # 1) bases sin resortes
        base = []
        for f in frames:
            vals = self.values(clip, f)
            base.append({b: rig.basis(b, vals.get(b, {})) for b in rig.names})
        if clip.springs:
            base = self._springs(clip, base)
        if clip.loop:
            # costura exacta: el último cuadro es el primero
            base[n] = dict(base[0])
        return base

    def _springs(self, clip, base):
        rig = self.rig
        n = clip.frames
        loop = clip.loop
        reps = 3 if loop else 1
        dt = 1.0 / FPS
        sub = 4
        # serie extendida (3 vueltas para los loops)
        if loop:
            seq = [base[i % n] for i in range(n * reps + 1)]
        else:
            seq = list(base)
        L = len(seq)
        world = [dict() for _ in range(L)]   # matrices por cuadro de los huesos ya resueltos
        out = [dict(s) for s in seq]
        for b in rig.order:
            p = rig.parent[b]
            sp = SPRINGS.get(b) if clip.springs else None
            if sp and p is not None:
                k, c, mx, lev = sp
                k *= clip.spring_scale.get(b, 1.0)
                gain = clip.spring_gain * SPRING_GAIN
                Rp = [rot_of(world[i][p]) for i in range(L)]
                Pp = [world[i][p] for i in range(L)]
                rel = rig.rel[b]
                rel_q = rel.to_quaternion()
                head_local = rel.to_translation()
                d_par = (rel_q @ Vector((0, 1, 0))).normalized()     # dirección del hueso en el padre
                ell = max(0.15, rig.length[b] * 0.6)
                # velocidad angular del padre (en su propio marco) y aceleración lineal de la cabeza del hueso
                def omega(i):
                    a, bq = Rp[max(i - 1, 0)], Rp[min(i + 1, L - 1)]
                    dq = a.inverted() @ bq
                    if dq.w < 0:
                        dq = -dq
                    ax, ang = dq.to_axis_angle()
                    span = (min(i + 1, L - 1) - max(i - 1, 0)) * dt
                    return Vector(ax) * (ang / span if span > 0 else 0.0)   # en el marco del padre
                om = [omega(i) for i in range(L)]
                alpha = [(om[min(i + 1, L - 1)] - om[max(i - 1, 0)]) / (max(1, min(i + 1, L - 1) - max(i - 1, 0)) * dt) for i in range(L)]
                hp = [Pp[i] @ head_local for i in range(L)]
                acc = []
                for i in range(L):
                    i0, i1 = max(i - 1, 0), min(i + 1, L - 1)
                    if i1 - i0 < 2:
                        acc.append(Vector())
                        continue
                    aw = (hp[i1] - 2 * hp[i] + hp[i0]) / (dt * dt)
                    acc.append(Rp[i].to_matrix().inverted() @ aw)
                # empuje suavizado en 3 cuadros (1/4, 1/2, 1/4): el corte de velocidad de un golpe (la suelta
                # termina rápida y la vuelta arranca quieta) es un impulso de un solo cuadro que pateaba el
                # resorte contra su tope y se veía como un salto aislado del papel o del bigote
                alpha = _smooth3(alpha)
                acc = _smooth3(acc)
                th = Vector()
                thd = Vector()
                mxr = math.radians(mx)
                vmax = mxr * FPS / 1.5
                for i in range(L):
                    # el cuadro i muestra el estado ANTES de integrar su empuje: el primer cuadro de un clip
                    # no lineal sale sin desvío (no hay pop al entrar desde otro clip)
                    tw = d_par * th.dot(d_par)
                    th_use = th - tw * 0.8
                    m = th_use.length
                    if m > 1e-6:
                        th_use = th_use * (mxr * math.tanh(m / mxr) / m)
                    th_rest = rel_q.inverted() @ th_use
                    ang = th_rest.length
                    l, q, s = out[i][b]
                    if ang > 1e-7:
                        q = Quaternion(th_rest.normalized(), ang) @ q
                    out[i][b] = (l, q, s)
                    drive = -alpha[i] * gain - d_par.cross(acc[i]) * (lev * gain / ell)
                    for _ in range(sub):
                        h = dt / sub
                        thdd = -k * th - c * thd + drive
                        thd = thd + thdd * h
                        # arrastre del agua/aire: la aleta o el papel no cruzan de un tope al otro en un cuadro
                        # (eso se veía como un salto aislado); como mucho 2/3 del tope por cuadro
                        if thd.length > vmax:
                            thd = thd * (vmax / thd.length)
                        th = th + thd * h
                    # el estado tampoco se va lejos del tope: si no, después de un tirón quedaría 'pegado'
                    if th.length > 1.4 * mxr:
                        th = th * (1.4 * mxr / th.length)
                        thd = thd * 0.5
            # matrices del hueso con su base final
            for i in range(L):
                l, q, s = out[i][b]
                B = Matrix.Translation(l) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
                world[i][b] = (world[i][p] @ rig.rel[b] @ B) if p else (rig.rel[b] @ B)
        if loop:
            return out[n * (reps - 1): n * reps + 1]
        return out


def _smooth3(xs):
    n = len(xs)
    return [xs[max(i - 1, 0)] * 0.25 + xs[i] * 0.5 + xs[min(i + 1, n - 1)] * 0.25 for i in range(n)]


# ------------------------------------------------------------------ escritura a una acción de Blender
def write_action(arm, name, base, rig):
    import bpy
    act = bpy.data.actions.new(name)
    n = len(base)
    for b in rig.names:
        pb = f'pose.bones["{b}"]'
        locs = [base[i][b][0] for i in range(n)]
        qs = []
        prev = None
        for i in range(n):
            q = base[i][b][1].copy()
            if prev is not None and prev.dot(q) < 0:
                q = -q
            qs.append(q)
            prev = q
        scs = [base[i][b][2] for i in range(n)]
        for path, data, comps in (("location", locs, 3), ("rotation_quaternion", qs, 4), ("scale", scs, 3)):
            for ci in range(comps):
                vals = [data[i][ci] for i in range(n)]
                fc = act.fcurves.new(f"{pb}.{path}", index=ci, action_group=b)
                fc.keyframe_points.add(n)
                co = []
                for i, v in enumerate(vals):
                    co += [float(i), float(v)]
                fc.keyframe_points.foreach_set("co", co)
                fc.keyframe_points.foreach_set("interpolation", [1] * n)   # LINEAR: hay una clave por cuadro
                fc.update()
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = n - 1
    act.use_fake_user = True
    return act
