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
  j) ningún triángulo de piel (cuerpo, cabeza, boca, cuerda) se da vuelta al deformarse (con Cull Back
     sería un agujero; las aletas son de doble cara y no cuentan)
  k) el golpe es lo más rápido del clip: la punta del hueso del golpe tiene su pico de velocidad a 2
     cuadros o menos del contacto, y en los desviables la vuelta no pasa del 45 % de la velocidad del golpe
     (una vuelta rápida se lee como un segundo golpe justo cuando el jugador acaba de hacer parry)
  l) alcance: en el cuadro del contacto la malla del hueso del golpe llega al 85 % del alcance del
     AttackDef y está dentro del sector que ataca (timing 'reach'). El juego resuelve golpe y parry en ese
     cuadro: si el arma todavía no llegó, el jugador no tiene cómo saber cuándo apretar
  m) ninguna vértebra frena en seco: de más de 150°/s (respecto de su padre) a menos del 10 % en un
     cuadro. Solo se perdona el contacto en la cadena del hueso del golpe (la mordida que se clava)
  n) en los clips con golpe, la columna y la raíz de las pectorales no arrancan de golpe (de quieto a más
     de 120°/s en un cuadro) fuera de la suelta: en la vuelta eso se lee como otro ataque
"""
import math
from collections import Counter
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
# el chorro no es un golpe de un cuadro: la cabeza apunta (lo más rápido) y después dispara 14 cuadros
STRIKE_PEAK_EXEMPT = {"Jet"}
RECOVERY_MAX = 0.45
# huesos de piel de una cara (lo demás son aletas, papeles y bigotes de doble cara o tubos finos)
SKIN_BONES = {"root", "body", "spine_f", "head", "jaw", "spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail",
              "gill_L", "gill_R", "seal"}
FLIP_TOL = 3     # triángulos por cuadro: la soga del lado cóncavo de la C cerrada se arruga en 1-2 tris
SPINE = ["spine_f", "head", "spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail"]
REACH_MIN = 0.85
STOP_FAST, STOP_RATIO = 150.0, 0.1       # °/s respecto del padre
ONSET_FAST = 120.0
# varado: los coletazos de costado golpean la cubierta, que los frena en seco a propósito
STOP_OK = {"BreachLand"}


class Skin:
    """Vértices (submuestreados) y pesos de las mallas para medir la malla deformada, y la piel completa
    para los volteos."""

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
        # piel completa (sin submuestrear) para los volteos: triángulos de una sola cara (sin gemelo en las
        # mismas posiciones, como los papeles) cuyo hueso dominante es de la piel
        self.shells = []
        for ob in objs:
            gname = {g.index: g.name for g in ob.vertex_groups}
            me = ob.data
            V = np.array([(*v.co, 1.0) for v in me.vertices], dtype=np.float32)
            W = np.zeros((len(me.vertices), len(names)), dtype=np.float32)
            for v in me.vertices:
                for g in v.groups:
                    W[v.index, bi[gname[g.group]]] += g.weight
            W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
            T = np.array([tuple(p.vertices) for p in me.polygons])
            dom = W[T[:, 0]].argmax(1)
            keys = [tuple(sorted(tuple(np.round(V[i, :3], 4)) for i in t)) for t in T]
            seen = Counter(keys)
            keep = np.array([names[d] in SKIN_BONES and seen[k] == 1 for d, k in zip(dom, keys)])
            T, dom = T[keep], dom[keep]
            n0 = self._normals(V[:, :3], T)
            self.shells.append((ob.name, V, W, T, dom, n0))

    @staticmethod
    def _normals(X, T):
        n = np.cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)

    def _mats(self, M):
        return np.array([np.array(M[n]) for n in self.names], dtype=np.float32) @ self.inv     # (B,4,4)

    def deform(self, M):
        P = np.einsum("bij,vj->bvi", self._mats(M), self.V)                                  # (B,V,4)
        return np.einsum("vb,bvi->vi", self.W, P)[:, :3]

    def flips(self, M):
        """Triángulos de piel cuya normal deformada mira al revés de la de reposo girada por su hueso."""
        Ms = self._mats(M)
        out = 0
        for name, V, W, T, dom, n0 in self.shells:
            X = np.einsum("vb,bvi->vi", W, np.einsum("bij,vj->bvi", Ms, V))[:, :3]
            nf = self._normals(X, T)
            nr = np.einsum("tij,tj->ti", Ms[dom][:, :3, :3], n0)
            out += int((np.einsum("ti,ti->t", nf, nr) < -0.2).sum())
        return out


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
    # j) volteos de la piel
    worst_flip = max(((skin.flips(M), f) for f, M in enumerate(Ms)), default=(0, 0))
    info["flips"] = list(worst_flip)
    if worst_flip[0] > FLIP_TOL:
        errs.append(f"{clip.name}: {worst_flip[0]} triángulos de piel dados vuelta en f{worst_flip[1]}")
    # k) el golpe es el pico del clip y la vuelta es más lenta
    sb, ae = tm.get("strikeBone"), tm.get("activeEnd")
    if sb and c is not None and ae is not None and tm.get("kind") in ("parry", "danger") and clip.name not in STRIKE_PEAK_EXEMPT:
        tips = [M[sb] @ Vector((0, rig.length[sb], 0)) for M in Ms]
        v = [0.0] + [(tips[f] - tips[f - 1]).length * 30.0 for f in range(1, len(tips))]
        pk = max(range(len(v)), key=lambda f: v[f])
        info["strikePeak"] = [pk, round(v[pk], 1)]
        if abs(pk - c) > 2:
            errs.append(f"{clip.name}: la punta de {sb} es más rápida en f{pk} ({v[pk]:.0f} m/s), lejos del contacto f{c}")
        if tm.get("kind") == "parry":
            a0 = tm.get("apex") or 0
            strike = max(sp[b][f] for b in MAIN for f in range(a0, ae + 1))
            rec, rb, rf = max(((sp[b][f], b, f) for b in MAIN for f in range(ae + 1, len(Ms))), default=(0.0, "", 0))
            info["recovery"] = round(rec / max(strike, 1e-6), 2)
            if rec > RECOVERY_MAX * strike:
                errs.append(f"{clip.name}: la vuelta de {rb} en f{rf} va al {100 * rec / strike:.0f} % del golpe (máx {100 * RECOVERY_MAX:.0f} %)")
    # l) alcance en el contacto (el root no se mueve en horizontal: se mide desde el origen)
    if tm.get("reach") and sb and c is not None:
        rng, center, half = tm["reach"]
        X = skin.deform(Ms[c])[np.array(skin.dom) == sb]
        r = np.hypot(X[:, 0], X[:, 1])
        i = int(r.argmax())
        bearing = math.degrees(math.atan2(X[i, 0], -X[i, 1])) % 360      # 0 = frente (-Y), 90 = izquierda (+X)
        off = abs((bearing - center + 180) % 360 - 180)
        info["reach"] = [round(float(r[i]), 2), round(bearing), round(float(X[i, 2]), 2)]
        if r[i] < REACH_MIN * rng or off > half:
            errs.append(f"{clip.name}: en el contacto f{c} {sb} llega a {r[i]:.2f} m a {bearing:.0f}° "
                        f"(necesita {REACH_MIN * rng:.2f} m a {center}±{half}°)")
    # m, n) paradas en seco y arranques bruscos, con la velocidad de cada hueso respecto de su padre
    rel = {}
    for b in set(SPINE) | {"pec_L1", "pec_R1"}:
        p = rig.parent[b]
        q = [_rq(M[p].inverted() @ M[b]) for M in Ms]
        rel[b] = [0.0] + [_ang(q[f - 1], q[f]) * 30.0 for f in range(1, len(q))]
    chain_sb = set()
    b = sb
    while b:
        chain_sb.add(b)
        b = rig.parent[b]
    if clip.name not in STOP_OK:
        for b in SPINE:
            v = rel[b]
            for f in range(1, len(v) - 1):
                if v[f] > STOP_FAST and v[f + 1] < STOP_RATIO * v[f] and not (f == c and b in chain_sb):
                    errs.append(f"{clip.name}: {b} frena en seco en f{f}->{f + 1} ({v[f]:.0f} -> {v[f + 1]:.0f}°/s)")
                    break
    if c is not None and tm.get("kind") in ("parry", "danger") and clip.name not in STOP_OK:
        hold = tm.get("hold")
        r0 = hold[1] if hold else (tm.get("apex") or c)
        r1 = c + max(clip.lag.values(), default=0) + 1           # la suelta baja por la cola con su lag
        for b, v in rel.items():
            for f in range(1, len(v) - 1):
                if r0 <= f <= r1:
                    continue
                if v[f + 1] > ONSET_FAST and v[f] < STOP_RATIO * v[f + 1]:
                    errs.append(f"{clip.name}: {b} arranca de golpe en f{f}->{f + 1} ({v[f]:.0f} -> {v[f + 1]:.0f}°/s)")
                    break
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
