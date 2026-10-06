"""Chequeos de las animaciones del Gran Koi antes de exportar (corta la exportación con el cuadro y el
hueso que fallan). Mide sobre la malla deformada de verdad (skinning lineal con numpy), no sobre poses.

  a) frente: FacingProbe y eye_glint delante (-Y)                       -> build_mizuchi.facing_guard
  b) contacto = round(activeStart * cuadros) y apex antes del contacto
  c) proporción anticipación : suelta : recuperación de los golpes desviables (~55 : 8 : 37)
  d) la suelta del golpe dura 2-4 cuadros
  e) las pausas nunca quedan congeladas (> 0.5° de deriva y < 40°/s)
  f) el root no se mueve en horizontal; el body se aleja como mucho 1.2 m
  g) ningún vértice bajo la cubierta (salvo los clips que la atraviesan a propósito)
  h) picos de velocidad angular (saltos de un cuadro)
  i) costura de los loops < 1°
"""
import math
import numpy as np
from mathutils import Vector

# entran al agua o se juegan en el aire / sobre la cascada (el código mueve el root): sin límite
UNDER_DECK_OK = {"Dive", "Intro", "BreachAir", "GreatWave", "ClimbFalls"}
# varado de costado sobre la cubierta: se tolera que un borde quede apenas bajo las tablas (no se ve); en
# el golpe de BreachLand los shide del flanco de abajo quedan aplastados bajo el cuerpo un par de cuadros
DECK_SOFT = {"BreachLand": -0.6, "Exhausted": -0.25}
FAR_OK = {"Dive", "Intro", "BreachAir", "Freed", "ClimbFalls", "Jet", "GreatWave"}
# techos de grados por cuadro de los giros a propósito (el barrido de 150° del aletazo dura 4 cuadros)
SPIN_OK = {"TailWhip": 115.0, "Freed": 90.0, "FinL": 92.0, "FinR": 92.0}
# el abanico que se estrella contra el agua frena en seco a propósito: se tolera ese corte
POP_OK = {"GreatWave": 25.0}
MAIN = ["body", "spine_f", "head", "pec_L1", "pec_R1"]   # lo que lee el jugador en la pausa (la cola sigue asentándose)


class Skin:
    """Vértices (submuestreados) y pesos de las mallas para medir la malla deformada."""

    def __init__(self, rig, objs, step=3):
        cos, rows = [], []
        names = rig.names
        bi = {n: i for i, n in enumerate(names)}
        for ob in objs:
            gname = {g.index: g.name for g in ob.vertex_groups}
            for v in ob.data.vertices:
                if v.index % step:
                    continue
                w = np.zeros(len(names), dtype=np.float32)
                for g in v.groups:
                    w[bi[gname[g.group]]] += g.weight
                if w.sum() <= 0:
                    continue
                cos.append((*v.co, 1.0))
                rows.append(w / w.sum())
        self.V = np.array(cos, dtype=np.float32)
        self.W = np.array(rows, dtype=np.float32)
        self.dom = [names[int(i)] for i in self.W.argmax(axis=1)]     # hueso dominante (para el reporte)
        self.inv = np.array([np.array(rig.rest[n].inverted()) for n in names], dtype=np.float32)
        self.names = names

    def deform(self, M):
        Ms = np.array([np.array(M[n]) for n in self.names], dtype=np.float32) @ self.inv     # (B,4,4)
        P = np.einsum("bij,vj->bvi", Ms, self.V)                                             # (B,V,4)
        return np.einsum("vb,bvi->vi", self.W, P)[:, :3]


def _ang(q1, q2):
    d = abs(q1.normalized().dot(q2.normalized()))
    return math.degrees(2 * math.acos(min(1.0, d)))


def _rq(M):
    from koi_anim import rot_of
    return rot_of(M)


def lint(rig, clip, base, skin):
    errs, info = [], {}
    n = clip.frames
    Ms = [rig.fk(b) for b in base]
    tm = clip.timing
    # b, c, d
    c = tm.get("contact")
    if c is not None and tm.get("kind") == "parry":
        a_start = c / n
        info["activeStart"] = round(a_start, 4)
        ap = tm.get("apex")
        if ap is not None and not ap < c:
            errs.append(f"{clip.name}: apex f{ap} no está antes del contacto f{c}")
        hold = tm.get("hold")
        rel = (c - hold[1]) if hold else (c - ap if ap is not None else None)
        if rel is not None:
            info["snapFrames"] = rel
            if not 2 <= rel <= 4:
                errs.append(f"{clip.name}: la suelta dura {rel} cuadros (2-4)")
            ant = c - rel
            info["ratio"] = [round(100 * ant / n), round(100 * rel / n), round(100 * (n - c) / n)]
    # e) pausas vivas
    hold = tm.get("hold")
    if hold:
        h0, h1 = hold
        mx_drift = 0.0
        mx_speed, sp_bone = 0.0, ""
        for b in MAIN:
            q0 = _rq(Ms[h0][b])
            for f in range(h0 + 1, h1 + 1):
                q = _rq(Ms[f][b])
                mx_drift = max(mx_drift, _ang(q0, q))
                v = _ang(_rq(Ms[f - 1][b]), q) * 30.0
                if v > mx_speed:
                    mx_speed, sp_bone = v, b
        info["holdDrift"] = round(mx_drift, 2)
        info["holdSpeed"] = [round(mx_speed, 1), sp_bone]
        if mx_drift < 0.5:
            errs.append(f"{clip.name}: la pausa f{h0}-{h1} está congelada ({mx_drift:.2f}°)")
        if mx_speed > 40.0:
            errs.append(f"{clip.name}: la pausa f{h0}-{h1} se mueve demasiado ({mx_speed:.0f}°/s)")
    # f) root y body
    r0 = Ms[0]["root"].to_translation()
    far = 0.0
    for f, M in enumerate(Ms):
        r = M["root"].to_translation()
        if (Vector((r.x, r.y)) - Vector((r0.x, r0.y))).length > 1e-4:
            errs.append(f"{clip.name}: el root se movió en horizontal en f{f}")
            break
        far = max(far, (M["body"].to_translation() - rig.head_rest["body"]).length)
    info["bodyTravel"] = round(far, 2)
    if far > 1.2 and clip.name not in FAR_OK:
        errs.append(f"{clip.name}: el body se aleja {far:.2f} m (máx 1.2)")
    # g) cubierta
    lowest = (9.0, 0, "")
    for f, M in enumerate(Ms):
        zs = skin.deform(M)[:, 2]
        i = int(zs.argmin())
        if zs[i] < lowest[0]:
            lowest = (float(zs[i]), f, skin.dom[i])
    info["minZ"] = [round(lowest[0], 3), lowest[2], lowest[1]]
    if lowest[0] < DECK_SOFT.get(clip.name, -0.02) and clip.name not in UNDER_DECK_OK:
        errs.append(f"{clip.name}: un vértice de {lowest[2]} baja a {lowest[0]:.2f} m (bajo la cubierta) en f{lowest[1]}")
    # h) picos: un cuadro que va mucho más rápido que sus dos vecinos es un 'pop' (los golpes rápidos de
    #    verdad aceleran y frenan en varios cuadros); y un techo absoluto por si algo explota
    lim = SPIN_OK.get(clip.name, 75.0)
    Q = [{b: _rq(M[b]) for b in rig.names} for M in Ms]
    sp = {b: [0.0] + [_ang(Q[f - 1][b], Q[f][b]) for f in range(1, len(Ms))] for b in rig.names}
    worst, pop = (0.0, "", 0), (0.0, "", 0)
    for b in rig.names:
        v = sp[b]
        for f in range(1, len(v)):
            if v[f] > worst[0]:
                worst = (v[f], b, f)
            if 1 < f < len(v) - 1:
                nb = max(v[f - 1], v[f + 1])
                if v[f] > 18.0 and v[f] > 3.0 * nb and v[f] - nb > pop[0]:
                    pop = (v[f] - nb, b, f)
    info["maxDegPerFrame"] = [round(worst[0], 1), worst[1], worst[2]]
    if worst[0] > lim:
        errs.append(f"{clip.name}: {worst[0]:.0f}°/cuadro en {worst[1]} f{worst[2]} (techo {lim:.0f})")
    if pop[0] > 0:
        info["pop"] = [round(pop[0], 1), pop[1], pop[2]]
        if pop[0] > POP_OK.get(clip.name, 0.0):
            errs.append(f"{clip.name}: salto aislado de {pop[0]:.0f}° en {pop[1]} f{pop[2]}")
    # i) costura
    if clip.loop:
        seam = max(_ang(_rq(Ms[0][b]), _rq(Ms[n][b])) for b in rig.names)
        # el último tramo (n-1 -> n) tiene que parecerse a los demás: un pop en la costura se ve igual
        step_end = max(_ang(_rq(Ms[n - 1][b]), _rq(Ms[n][b])) for b in rig.names)
        step_mid = max(_ang(_rq(Ms[n // 2 - 1][b]), _rq(Ms[n // 2][b])) for b in rig.names)
        info["seam"] = round(seam, 3)
        info["seamStep"] = [round(step_end, 2), round(step_mid, 2)]
        if seam > 1.0 or step_end > max(2.5, 2.5 * step_mid):
            errs.append(f"{clip.name}: costura del loop {seam:.2f}° / paso {step_end:.1f}° vs {step_mid:.1f}°")
    return errs, info
