"""Núcleo compartido para animar personajes de Nindō por script (Blender 4.4, bpy + mathutils).

Nació de los prototipos de la fase A (carrera de Kaito y ataque del ninja) y se generalizó para
todos los personajes. La idea es la de un animador que trabaja pose a pose, pero con números:

* Un **clip** es una lista de **poses clave** (diccionarios de *controles*: cadera, giros del
  tronco, dónde va cada mano y cada pie, hacia dónde apunta la hoja...) con una curva de
  aceleración por tramo. Entre claves se interpola en el espacio de los controles (arcos
  Catmull-Rom para manos y cadera, slerp para la hoja), NO en el de los huesos: así un pie
  apoyado queda clavado aunque la cadera se mueva y las manos describen arcos limpios.
* Cada cuadro se resuelve con **cinemática directa e IK analítica de dos huesos** en Python puro
  (mathutils): sin constraints de Blender, sin bake, determinista. El IK solo existe acá, en la
  autoría; en el FBX quedan rotaciones FK de un esqueleto limpio (manos bajo antebrazos, pies
  bajo tibias), que Unity mezcla sin despegar muñecas ni tobillos.
* Lo secundario (pelo, cintas, faldones, hombreras) lo hace una pasada de **resortes** sobre el
  movimiento ya resuelto, en espacio de mundo (incluye el avance del golpe), así la melena se
  atrasa cuando el personaje embiste.
* Las **mediciones** (deriva de pies apoyados, velocidad de la punta del arma, costura de los
  loops, altura máxima de la silueta, hoja clavada que se corre en el piso) se calculan sobre el
  resultado y fallan la exportación si no cumplen: lo que llega a Unity está medido. Las de los
  ataques se miden con el reloj con el que el juego los toca (StepTimeline), no a 30 fps.

Convenciones (las mismas de Tools/Blender/STYLE.md): metros, Blender Z arriba, el FRENTE del
personaje mira a -Y (en Unity +Z con la exportación de acá), la DERECHA del personaje es -X.
Los ángulos de los controles son grados en ejes de la armadura (XYZ):
  x + = la parte de arriba del hueso va hacia adelante (inclinarse),
  y + = se inclina hacia la izquierda del personaje (+X),
  z + = gira hacia la izquierda del personaje (visto desde arriba, antihorario).
"""
import bpy, math, json, os, subprocess, sys
from mathutils import Vector, Matrix, Quaternion, Euler

FPS = 30


# =============================================================================== curvas de aceleración
def _c(u):
    return 0.0 if u <= 0.0 else 1.0 if u >= 1.0 else u


def _expo_in(u):
    return 0.0 if u <= 0.0 else (2.0 ** (10.0 * (u - 1.0)) - 2.0 ** -10.0) / (1.0 - 2.0 ** -10.0)


EASES = {
    "lin": lambda u: u,
    "inout": lambda u: u * u * (3.0 - 2.0 * u),                       # smoothstep: sale y llega quieto
    "sine": lambda u: 0.5 - 0.5 * math.cos(math.pi * u),              # recuperaciones, respiración
    "in": lambda u: u * u * u,                                        # arranca lento, termina rápido
    "out": lambda u: 1.0 - (1.0 - u) ** 3,                            # arranca rápido, frena
    "in2": lambda u: u * u,
    "out2": lambda u: 1.0 - (1.0 - u) ** 2,
    "expo_in": _expo_in,                                              # hacia el impacto
    "expo_out": lambda u: 1.0 - _expo_in(1.0 - u),                    # después del impacto
    "snap": lambda u: 1.0 - (1.0 - u) ** 5,                           # golpe seco que se clava
    "back": lambda u: 1.0 + 2.70158 * (u - 1.0) ** 3 + 1.70158 * (u - 1.0) ** 2,   # se pasa y vuelve
    "hold": lambda u: 0.0,
}


def ease(name, u):
    """Curva de aceleración de un tramo: u en [0, 1] -> avance en [0, 1]."""
    return EASES[name](_c(u))


# =============================================================================== utilidades de vectores
def V(p):
    return Vector(p) if not isinstance(p, Vector) else p.copy()


def euler_q(r):
    """(x, y, z) en grados, ejes de la armadura -> Quaternion."""
    if isinstance(r, Quaternion):
        return r.copy()
    return Euler((math.radians(r[0]), math.radians(r[1]), math.radians(r[2])), 'XYZ').to_quaternion()


def catmull(p0, p1, p2, p3, t):
    """Catmull-Rom uniforme entre p1 y p2 (t en [0, 1]); pasa por las claves sin quiebres."""
    return 0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t)


def slerp_dir(a, b, t):
    """Interpola direcciones por el arco más corto (para hojas, miradas)."""
    a, b = V(a).normalized(), V(b).normalized()
    d = max(-1.0, min(1.0, a.dot(b)))
    if d > 0.9999:
        return a.lerp(b, t).normalized()
    if d < -0.999:
        # opuestas: gira por un eje cualquiera perpendicular
        ax = a.orthogonal().normalized()
        return (Quaternion(ax, math.pi * t) @ a).normalized()
    w = math.acos(d)
    s = math.sin(w)
    return (a * (math.sin((1.0 - t) * w) / s) + b * (math.sin(t * w) / s)).normalized()


def basis_yz(y, z_hint):
    """Matriz 3x3 con columna Y = y y Z lo más parecido a z_hint (convención de huesos de Blender)."""
    Y = V(y).normalized()
    Z = V(z_hint) - Y * V(z_hint).dot(Y)
    if Z.length < 1e-6:
        Z = Y.orthogonal()
    Z.normalize()
    X = Y.cross(Z).normalized()
    return Matrix((X, Y, Z)).transposed()


def quat_angle_deg(a, b):
    d = abs(a.dot(b))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


def rot3(m):
    return m.to_3x3().normalized()


def compose(loc, r3):
    M = r3.to_4x4()
    M.translation = loc
    return M


# =============================================================================== esqueleto
class BoneDef:
    """Una fila de la tabla de huesos: cabeza, cola, padre, si deforma y el vector hacia el
    que apunta el eje Z del hueso (edit_bone.align_roll)."""

    def __init__(self, name, head, tail, parent=None, deform=True, roll=(0, -1, 0)):
        self.name, self.head, self.tail = name, V(head), V(tail)
        self.parent, self.deform, self.roll = parent, deform, V(roll)


def side_swap(name):
    """'Hand_R' -> 'Hand_L', 'Mane_R_2' -> 'Mane_L_2' (None si el nombre no es del lado derecho)."""
    if name is None:
        return None
    if name.endswith("_R"):
        return name[:-2] + "_L"
    if "_R_" in name:
        return name.replace("_R_", "_L_", 1)
    return None


def mirrored(bones):
    """Agrega el lado izquierdo (x negativa -> positiva) de cada hueso derecho (*_R, *_R_n) de la tabla."""
    out = list(bones)
    mx = lambda v: Vector((-v.x, v.y, v.z))
    for b in bones:
        ln = side_swap(b.name)
        if ln:
            p = side_swap(b.parent) or b.parent
            out.append(BoneDef(ln, mx(b.head), mx(b.tail), p, b.deform, mx(b.roll)))
    return out


def build_armature(name, bones, data_name=None):
    """Crea el objeto armadura desde la tabla (en el origen, sin rotación)."""
    data = bpy.data.armatures.new(data_name or name + "Rig")
    arm = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for b in bones:
        e = data.edit_bones.new(b.name)
        e.head, e.tail = b.head, b.tail
        e.align_roll(b.roll)
        e.use_deform = b.deform
        eb[b.name] = e
    for b in bones:
        if b.parent:
            eb[b.name].parent = eb[b.parent]
            eb[b.name].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return arm


class Rig:
    """Datos de reposo de una armadura para resolver poses en Python puro.

    rest[n]  = matriz del hueso en reposo (espacio de la armadura, = bone.matrix_local)
    rel[n]   = reposo del hijo respecto del padre (rest[p]^-1 @ rest[n])
    La pose de un hueso en espacio de la armadura es  W[n] = W[p] @ rel[n] @ base[n],
    la misma fórmula que usa Blender (y Unity al leer el FBX) para huesos sin conexión."""

    def __init__(self, arm):
        self.arm = arm
        bones = arm.data.bones
        self.names = []
        def walk(b):
            self.names.append(b.name)
            for c in b.children:
                walk(c)
        for b in bones:
            if b.parent is None:
                walk(b)
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.rest_inv = {n: m.inverted() for n, m in self.rest.items()}
        self.rel = {n: (self.rest_inv[self.parent[n]] @ self.rest[n]) if self.parent[n] else self.rest[n].copy()
                    for n in self.names}
        self.length = {b.name: b.length for b in bones}
        self.children = {n: [c.name for c in bones[n].children] for n in self.names}

    def head_rest(self, n):
        return self.rest[n].translation.copy()

    def to_local(self, W):
        """{hueso: matriz en espacio de la armadura} -> {hueso: (location, quaternion)} de pose."""
        out = {}
        for n in self.names:
            p = self.parent[n]
            base = (W[p] @ self.rel[n]).inverted() @ W[n] if p else self.rest_inv[n] @ W[n]
            out[n] = (base.to_translation(), base.to_quaternion().normalized())
        return out

    def subtree(self, n):
        out = [n]
        for c in self.children[n]:
            out += self.subtree(c)
        return out


class Pose:
    """Pose de un cuadro en espacio de la armadura, construida de padres a hijos.

    Cualquier hueso que no se toque queda 'en reposo respecto de su padre'. Los métodos fijan la
    matriz de mundo de un hueso; el padre tiene que estar resuelto antes (se resuelve solo si no)."""

    def __init__(self, rig):
        self.rig = rig
        self.W = {}

    def get(self, n):
        if n not in self.W:
            self.W[n] = self.follow(n)
        return self.W[n]

    def follow(self, n):
        p = self.rig.parent[n]
        return (self.get(p) @ self.rig.rel[n]) if p else self.rig.rest[n].copy()

    def head(self, n):
        return self.get(n).translation.copy()

    def tail(self, n):
        return self.get(n) @ Vector((0.0, self.rig.length[n], 0.0))

    def place(self, n, M):
        self.W[n] = M.copy()

    def delta(self, n, r, loc=None):
        """Giro 'r' (grados XYZ en ejes de la armadura, o Quaternion) aplicado sobre el reposo del
        hueso relativo a su padre: los giros de una cadena se suman como en un muñeco articulado."""
        p = self.rig.parent[n]
        A = (self.get(p) @ self.rig.rest_inv[p]) if p else Matrix.Identity(4)
        h = self.rig.head_rest(n)
        D = Matrix.Translation(h) @ euler_q(r).to_matrix().to_4x4() @ Matrix.Translation(-h)
        M = A @ D @ self.rig.rest[n]
        if loc is not None:
            M.translation = M.translation + V(loc)
        self.W[n] = M

    def orient(self, n, R3, head=None):
        """Fija la orientación (3x3 de armadura); la cabeza queda donde la pone el padre."""
        h = self.follow(n).translation if head is None else V(head)
        self.W[n] = compose(h, R3)

    def aim(self, n, y_dir, z_hint=None):
        F = rot3(self.follow(n))
        z = F.col[2] if z_hint is None else V(z_hint)
        self.orient(n, basis_yz(y_dir, z))

    def two_bone(self, upper, lower, target, pole, reach=0.999):
        """IK analítica: ubica 'upper' y 'lower' para que la cola de 'lower' llegue a 'target', con
        la articulación del medio hacia 'pole' (dirección). Conserva el 'roll' de cada hueso respecto
        del plano de flexión del reposo (la rodilla dobla como rodilla). Devuelve cuánto faltó (m)."""
        R = self.rig
        S = self.head(upper) if upper in self.W else self.follow(upper).translation
        a, b = R.length[upper], R.length[lower]
        Fu0 = rot3(self.follow(upper))
        Fl0 = Fu0 @ rot3(R.rel[lower])
        u0, l0 = Fu0.col[1], Fl0.col[1]
        n0 = u0.cross(l0)
        if n0.length < 1e-6:
            n0 = u0.orthogonal()
        n0.normalize()
        T = V(target)
        d_vec = T - S
        d = d_vec.length
        miss = max(0.0, d - (a + b) * reach)
        d = max(abs(a - b) + 1e-4, min(d, (a + b) * reach))
        nd = d_vec.normalized() if d_vec.length > 1e-6 else u0
        cosA = max(-1.0, min(1.0, (a * a + d * d - b * b) / (2.0 * a * d)))
        sinA = math.sqrt(max(0.0, 1.0 - cosA * cosA))
        P = V(pole) - nd * V(pole).dot(nd)
        if P.length < 1e-6:
            P = n0.cross(nd)
        P.normalize()
        E = S + nd * (a * cosA) + P * (a * sinA)
        Tc = S + nd * d
        u = (E - S).normalized()
        l = (Tc - E).normalized()
        nn = u.cross(l)
        if nn.length < 1e-6:
            nn = n0
        nn.normalize()

        def frame(y, n):
            return Matrix((y, n, y.cross(n))).transposed()
        Ru = frame(u, nn) @ frame(u0, n0).transposed()
        Rl = frame(l, nn) @ frame(l0, n0).transposed()
        self.W[upper] = compose(S, Ru @ Fu0)
        self.W[lower] = compose(E, Rl @ Fl0)
        return miss

    def twist_follow(self, lower, end, amount=0.5):
        """Reparte en el hueso de abajo parte del giro de la mano/pie sobre su eje (el antebrazo
        acompaña la muñeca): no mueve nada de lugar, solo evita el 'caramelo' en el puño."""
        Wl, We = self.get(lower), self.get(end)
        base = (Wl @ self.rig.rel[end]).inverted() @ We
        q = base.to_quaternion()
        ang = 2.0 * math.atan2(q.y, q.w)
        if ang > math.pi:
            ang -= 2.0 * math.pi
        elif ang < -math.pi:
            ang += 2.0 * math.pi
        R = rot3(Wl) @ Matrix.Rotation(ang * amount, 3, 'Y')
        self.W[lower] = compose(Wl.translation, R)


# =============================================================================== resortes (secundario)
class Spring:
    """Cadena de huesos que se atrasa y rebota respecto de su padre (pelo, cintas, faldones).

    k: rigidez (1/s²) hacia la pose 'rígida'; damp: fracción de velocidad que se pierde por
    subpaso; grav: m/s² hacia abajo (las telas cuelgan más cuando el hueso queda horizontal);
    max_deg: tope del desvío respecto de la pose rígida; push: función opcional (pose, hueso) ->
    Quaternion que corrige la pose rígida (p. ej. el faldón que empuja el muslo); floor: la punta
    no baja de esa altura (el piso empuja la tela hacia afuera en vez de atravesarlo)."""

    def __init__(self, bones, k=140.0, damp=0.12, grav=4.0, max_deg=55.0, push=None, floor=None, hang=0.0, colliders=(),
                 follow=None):
        self.bones, self.k, self.damp, self.grav, self.max_deg, self.push = list(bones), k, damp, grav, max_deg, push
        self.hang = hang        # 0..1: cuánto busca colgar hacia abajo en vez de seguir rígido al padre (pelo, telas)
        # esferas (hueso, centro en el espacio del hueso, radio) que la punta no puede atravesar: la melena
        # cae sobre la espalda en vez de meterse en la coraza
        self.colliders = list(colliders)
        # orientación de reposo tomada de otro hueso (la melena acompaña la espalda, no la cabeza: con la
        # cabeza agachada no se levanta como una cresta); la raíz sigue colgando de su padre
        self.follow = follow
        self.floor = floor      # altura mínima de la punta en mundo (faldones al arrodillarse, melena al agacharse)


def run_springs(rig, frames, springs, root_offsets, loop=False, preroll=1.0, substeps=4, floor_offsets=None):
    """Simula los resortes sobre una lista de poses (dicts W) ya resueltas, en el lugar.

    root_offsets[f] = desplazamiento del personaje en el mundo en ese cuadro (el avance de un
    golpe, que en el clip se resta): la simulación corre en mundo para sentir esa inercia.
    En loops se simulan dos vueltas antes de la que se graba y el último cuadro se iguala al
    primero; en clips sueltos se arranca con 'preroll' segundos quietos en la primera pose.
    floor_offsets[f] corre el piso de los resortes (al hundirse en la sombra el piso ya no está debajo)."""
    n = len(frames)
    if n == 0 or not springs:
        return
    order = []
    for s in springs:
        order += s.bones
    spring_of = {b: s for s in springs for b in s.bones}
    # hijos que no son resorte de un hueso resorte: conservan su base local de la pose primaria
    riders = []
    for b in order:
        for c in rig.subtree(b)[1:]:
            if c not in spring_of and c not in riders:
                riders.append(c)
    prim = [dict(W) for W in frames]

    def base_of(W, b):
        p = rig.parent[b]
        return (W[p] @ rig.rel[b]).inverted() @ W[b] if p else rig.rest_inv[b] @ W[b]

    state = {}
    dt = 1.0 / FPS / substeps
    # en loops el último cuadro es igual al primero: se simula sobre 0..n-2, dos vueltas de calentamiento
    cyc = n - 1 if loop and n > 1 else n
    if loop:
        seq = [i % cyc for i in range(cyc * 2)] + list(range(cyc))
    else:
        seq = [0] * int(preroll * FPS) + list(range(n))
    record_from = len(seq) - cyc

    # en un loop que avanza (caminar) cada vuelta arranca donde terminó la anterior, no en el origen
    shift = (root_offsets[cyc] - root_offsets[0]) if loop and n > 1 else Vector()

    def solve_frame(fi, lap=0):
        P = prim[fi]
        fo = floor_offsets[fi] if floor_offsets else 0.0
        Wc = dict(P)
        off = Matrix.Translation(root_offsets[fi] + shift * lap)
        offi = off.inverted()
        spheres = {}
        for b in order:
            s = spring_of[b]
            sph = []
            for cb, cl, cr in s.colliders:
                key = (cb, tuple(cl))
                if key not in spheres:
                    spheres[key] = off @ (P[cb] @ V(cl))
                sph.append((spheres[key], cr))
            p = rig.parent[b]
            Fp = (off @ Wc[p]) if p else off
            F = Fp @ rig.rel[b] @ base_of(P, b)
            if s.follow and b == s.bones[0]:
                Rf = rot3(off @ P[s.follow]) @ rot3(rig.rest_inv[s.follow] @ rig.rest[b])
                F = compose(F.translation, Rf)
            if s.push:
                q = s.push(P, b)
                if q is not None:
                    F = compose(F.translation, q.to_matrix() @ rot3(F))
            h = F.translation
            L = rig.length[b]
            t = F @ Vector((0.0, L, 0.0))
            if s.hang > 0.0:
                # el reposo de una tela es colgar: con el cuerpo inclinado, la melena cae (no queda horizontal)
                hd = slerp_dir((t - h).normalized(), Vector((0.0, 0.0, -1.0)), s.hang)
                t = h + hd * L
            fl = None if s.floor is None else s.floor + fo
            if fl is not None and t.z < fl:
                t.z = fl
                dv = t - h
                t = h + dv.normalized() * L if dv.length > 1e-6 else t
            st = state.get(b)
            if st is None:
                st = state[b] = [t.copy(), t.copy(), t.copy()]
            x, xp, tp = st
            # el amortiguamiento frena la velocidad RELATIVA al ancla (fricción interna), no la del mundo:
            # caminando a velocidad constante el pelo acompaña; solo se atrasa al acelerar o frenar
            vt = (t - tp) / substeps
            for _ in range(substeps):
                acc = (t - x) * s.k + Vector((0.0, 0.0, -s.grav))
                xn = x + (x - xp) * (1.0 - s.damp) + vt * s.damp + acc * dt * dt
                dirn = xn - h
                if dirn.length < 1e-6:
                    dirn = t - h
                xn = h + dirn.normalized() * L
                for cc, cr in sph:
                    dv = xn - cc
                    if dv.length < cr:
                        xn = cc + dv.normalized() * cr
                        dirn = xn - h
                        if dirn.length > 1e-6:
                            xn = h + dirn.normalized() * L
                if fl is not None and xn.z < fl:
                    xn.z = fl
                    dirn = xn - h
                    if dirn.length > 1e-6:
                        xn = h + dirn.normalized() * L
                xp, x = x, xn
            a = (x - h).normalized()
            b0 = (t - h).normalized()
            ang = math.degrees(a.angle(b0)) if a.length > 0 and b0.length > 0 else 0.0
            if ang > s.max_deg:
                x = h + slerp_dir(b0, a, s.max_deg / ang) * L
            st[0], st[1], st[2] = x, xp, t.copy()
            q = b0.rotation_difference((x - h).normalized())
            Wc[b] = offi @ compose(h, q.to_matrix() @ rot3(F))
        for c in riders:
            Wc[c] = Wc[rig.parent[c]] @ rig.rel[c] @ base_of(P, c)
        return Wc

    for i, fi in enumerate(seq):
        Wc = solve_frame(fi, i // cyc if loop else 0)
        if i >= record_from:
            frames[fi] = Wc
    if loop and n > 1:
        frames[n - 1] = dict(frames[0])


# =============================================================================== clips
class Key:
    """Pose clave: cuadro, diccionario de controles y la curva del tramo que TERMINA en ella.
    ease_ch cambia la curva de algunos canales en ese tramo (un pie que se clava antes que el cuerpo).
    stops: canales en los que la clave es un tope del arco (tangente cero): el Catmull-Rom no se pasa de
    largo entre dos claves muy distintas (una mano que baja al piso entre dos poses altas no lo atraviesa)."""

    def __init__(self, frame, ctrl, ease="inout", ease_ch=None, stops=()):
        self.frame, self.ctrl, self.ease = frame, ctrl, ease
        self.ease_ch = ease_ch or {}
        self.stops = set(stops)


# canales que se interpolan como direcciones (slerp) y como escalares
DIR_CHANNELS = ("blade", "edge", "hand_r_dir", "hand_r_up", "hand_l_dir", "hand_l_up", "elbow_r", "elbow_l",
                "knee_r", "knee_l", "look", "sword_dir", "sword_up")
SCALAR_CHANNELS = ("grip_l", "travel", "lift", "breath", "sword_free", "mask_free", "sword_ground")
LINEAR_POS = ("foot_r", "foot_l")       # los pies van en línea recta entre claves (apoyos limpios)


class Clip:
    """Clip autoral: claves + metadatos de timing. 'lag' atrasa (cuadros +) o adelanta (-) canales
    para que las articulaciones se 'rompan' en sucesión (la cadera guía, la cabeza llega después)."""

    def __init__(self, name, frames, keys, loop=False, lag=None, timing=None, events=None, notes="", root_vel=(0, 0, 0),
                 prepare=None):
        self.name, self.frames, self.loop = name, frames, loop
        self.prepare = prepare           # prepare(clip, rig, solve): completa claves que dependen de la pose resuelta
        self.root_vel = V(root_vel)      # velocidad del transform en el juego (locomoción), m/s
        self.keys = sorted(keys, key=lambda k: k.frame)
        self.lag = lag or {}
        self.timing = timing or {}
        self.events = events or []
        self.notes = notes
        assert self.keys[0].frame == 0 and self.keys[-1].frame == frames, f"{name}: claves de 0 a {frames}"

    def _seg(self, f):
        # tramo semiabierto [clave i, clave i+1): en el cuadro de una clave manda el tramo que ARRANCA
        # en ella (así un tramo 'hold' es un escalón limpio)
        ks = self.keys
        for i in range(len(ks) - 1):
            if ks[i].frame <= f < ks[i + 1].frame:
                return i
        return len(ks) - 2

    def sample(self, f, channel):
        """Valor de un canal en el cuadro f (puede ser fraccionario)."""
        ks = self.keys
        f = max(0.0, min(float(self.frames), f))
        i = self._seg(f)
        a, b = ks[i], ks[i + 1]
        span = max(1e-6, b.frame - a.frame)
        s = ease(b.ease_ch.get(channel, b.ease), (f - a.frame) / span)
        va, vb = a.ctrl.get(channel), b.ctrl.get(channel)
        if va is None and vb is None:
            return None
        if va is None:
            va = vb
        if vb is None:
            vb = va
        # cualquier número suelto es un escalar (los canales propios de cada personaje no tienen que estar en
        # SCALAR_CHANNELS)
        if channel in SCALAR_CHANNELS or isinstance(va, (int, float)):
            return va + (vb - va) * s
        if channel in DIR_CHANNELS:
            return slerp_dir(va, vb, s)
        if channel == "extra":
            out = {}
            for bn in set(va) | set(vb):
                x0 = V(va.get(bn, (0, 0, 0)))
                x1 = V(vb.get(bn, (0, 0, 0)))
                out[bn] = x0.lerp(x1, s)
            return out
        p1, p2 = V(va), V(vb)
        if channel in LINEAR_POS or len(p1) != 3:
            return p1.lerp(p2, s)
        # arco Catmull-Rom por las claves vecinas (en loops, las vecinas dan la vuelta)
        def nb(j):
            if self.loop:
                m = len(ks) - 1
                j2 = j % m
                return ks[j2].ctrl.get(channel)
            return ks[max(0, min(len(ks) - 1, j))].ctrl.get(channel)
        p0 = nb(i - 1)
        p3 = nb(i + 2)
        p0 = V(p0) if p0 is not None and channel not in a.stops else p1
        p3 = V(p3) if p3 is not None and channel not in b.stops else p2
        return catmull(p0, p1, p2, p3, s)

    def controls(self, f):
        chans = set()
        for k in self.keys:
            chans.update(k.ctrl.keys())
        out = {}
        for c in chans:
            lag = self.lag.get(c, 0.0)
            ff = f - lag
            if self.loop:
                ff = ff % self.frames
            out[c] = self.sample(ff, c)
        return out


class ProcClip(Clip):
    """Clip cuyos controles salen de una función del cuadro: ciclos de locomoción, donde los pies
    siguen una trayectoria por fase (apoyo lineal a la velocidad del suelo, vuelo en arco)."""

    def __init__(self, name, frames, fn, loop=True, timing=None, events=None, notes="", root_vel=(0, 0, 0), sheet_frames=None):
        self.name, self.frames, self.loop, self.fn = name, frames, loop, fn
        self.root_vel = V(root_vel)
        self.lag, self.timing, self.events, self.notes = {}, timing or {}, events or [], notes
        self.prepare = None
        self.keys = [Key(f, {}, "lin") for f in (sheet_frames or range(0, frames + 1, max(1, frames // 6)))]

    def controls(self, f):
        return self.fn(f % self.frames if self.loop else f)


def bake_clip(rig, clip, solve, springs=(), preroll=1.0):
    """Resuelve todos los cuadros de un clip: devuelve (poses W por cuadro, controles, desplazamientos
    de raíz en mundo). 'solve(pose, ctrl)' es la función propia del personaje que traduce controles
    a huesos (ver kokuyo_rig.solve)."""
    frames, ctrls, roots = [], [], []
    if getattr(clip, "prepare", None):
        clip.prepare(clip, rig, solve)
    for f in range(clip.frames + 1):
        c = clip.controls(f)
        pose = Pose(rig)
        solve(pose, c)
        for n in rig.names:
            pose.get(n)
        frames.append(pose.W)
        ctrls.append(c)
        roots.append(Vector((0.0, -(c.get("travel") or 0.0), 0.0)) + clip.root_vel * (f / FPS))
    lifts = [min(0.0, c.get("lift") or 0.0) for c in ctrls]
    run_springs(rig, frames, list(springs), roots, loop=clip.loop, preroll=preroll, floor_offsets=lifts)
    if clip.loop:
        frames[-1] = {n: m.copy() for n, m in frames[0].items()}
    return frames, ctrls, roots


# =============================================================================== acciones y FBX
def write_pack(arm, rig, baked, start=1, gap=10, name="Pack"):
    """Escribe todos los clips en UNA acción, uno detrás de otro (Blender 4.4 exporta una sola toma
    confiable: Unity la corta por rangos de cuadros). baked = [(clip, frames W)].
    En el cuadro start - 1 (fuera de la toma exportada) queda la pose de reposo: es la pose por defecto
    del FBX (ver export_fbx), la que mide CharacterFactory.NormalizeHeight al instanciar el modelo.
    Devuelve {clip: (primer cuadro, último cuadro)}."""
    act = bpy.data.actions.new(name)
    arm.animation_data_create()
    arm.animation_data.action = act
    data = {n: ([0.0], [0.0], [0.0], [1.0], [0.0], [0.0], [0.0]) for n in rig.names}   # lx ly lz qw qx qy qz
    times = [start - 1]
    ranges = {}
    cur = start
    prevq = {n: Quaternion() for n in rig.names}
    for clip, frames in baked:
        ranges[clip.name] = (cur, cur + clip.frames)
        for i, W in enumerate(frames):
            loc = rig.to_local(W)
            times.append(cur + i)
            for n, (l, q) in loc.items():
                pq = prevq.get(n)
                if pq is not None and pq.dot(q) < 0.0:
                    q = -q          # mismo hemisferio que el cuadro anterior: sin vueltas raras al interpolar
                prevq[n] = q
                d = data[n]
                d[0].append(l.x); d[1].append(l.y); d[2].append(l.z)
                d[3].append(q.w); d[4].append(q.x); d[5].append(q.y); d[6].append(q.z)
        cur += clip.frames + gap
    for n in rig.names:
        d = data[n]
        for path, idxs in (("location", (0, 1, 2)), ("rotation_quaternion", (3, 4, 5, 6))):
            for ai, di in enumerate(idxs):
                fc = act.fcurves.new(f'pose.bones["{n}"].{path}', index=ai, action_group=n)
                fc.keyframe_points.add(len(times))
                co = [0.0] * (2 * len(times))
                co[0::2] = times
                co[1::2] = d[di]
                fc.keyframe_points.foreach_set("co", co)
                fc.keyframe_points.foreach_set("interpolation", [1] * len(times))   # LINEAR
                fc.update()
    try:
        if arm.animation_data.action_slot is None and len(act.slots):
            arm.animation_data.action_slot = act.slots[0]
    except AttributeError:
        pass
    return act, ranges


def export_fbx(path, arm, meshes, frame_start, frame_end):
    """Exportación validada en la fase A: esqueleto solo de huesos que deforman, sin hojas extra,
    una toma 'Scene' con todos los cuadros (sin simplificar: no se pierden los golpes de 2 cuadros).
    El exportador escribe como transform por defecto de cada hueso la pose del cuadro ACTUAL: se exporta
    parado en frame_start - 1, la pose de reposo que deja write_pack (si no, el prefab de Unity nace en
    la primera pose del primer clip y NormalizeHeight mide otra altura)."""
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = frame_start, frame_end
    scn.frame_set(frame_start - 1)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm] + list(meshes):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                             axis_forward='-Z', axis_up='Y', mesh_smooth_type='FACE',
                             add_leaf_bones=False, use_armature_deform_only=True,
                             primary_bone_axis='Y', secondary_bone_axis='X',
                             bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                             bake_anim_simplify_factor=0.0, path_mode='STRIP', embed_textures=False,
                             use_custom_props=False, colors_type='NONE', use_tspace=False)


# =============================================================================== mediciones
def tip_speeds(rig, frames, roots, bone, local_tip):
    """Velocidad (m/s) de un punto del arma por cuadro (índice i = tramo i-1 -> i)."""
    pts = [W[bone] @ V(local_tip) + r for W, r in zip(frames, roots)]
    return [0.0] + [(pts[i] - pts[i - 1]).length * FPS for i in range(1, len(pts))], pts


def blade_floor_slide(frames, roots, bone, local_tip, below=-0.05, skip=()):
    """Una hoja clavada entra y sale del piso a lo largo de su propio eje: el punto donde la recta
    empuñadura -> punta corta el piso (z = 0) no se mueve mientras la punta está abajo. Mide cuánto se
    corre ese punto (m, en el plano del piso) entre cada par de cuadros en el que la punta de alguno de
    los dos está bajo 'below'; si en uno de ellos la hoja no apunta hacia abajo (sale o entra girando)
    el corrimiento es infinito. 'skip' = cuadros que no cuentan (se hunde entero en su sombra).
    Devuelve [(cuadro, corrimiento, z de la punta)] de los pares medidos."""
    grip = [W[bone].translation + r for W, r in zip(frames, roots)]
    tip = [W[bone] @ V(local_tip) + r for W, r in zip(frames, roots)]

    def hit(i):
        a, b = grip[i], tip[i]
        if a.z - b.z < 0.05:
            return None
        return a + (b - a) * (a.z / (a.z - b.z))
    out = []
    for i in range(1, len(tip)):
        if i in skip or i - 1 in skip or min(tip[i].z, tip[i - 1].z) >= below:
            continue
        p0, p1 = hit(i - 1), hit(i)
        d = Vector((p1.x - p0.x, p1.y - p0.y)).length if p0 is not None and p1 is not None else float("inf")
        out.append((i, d, min(tip[i].z, tip[i - 1].z)))
    return out


class StepTimeline:
    """Copia en Python de Nindo/Scripts/Enemies/StepTimeline.cs (mismas constantes): con qué reloj toca
    el juego un clip de ataque. Anticipación hasta el apex que desacelera (seno), pausa en el apex que
    apenas avanza ('creep'), suelta del apex al golpe acelerando (u²) a 'release_rate' veces la velocidad
    del clip y seguimiento que vuelve a 1. Sirve para medir lo que se VE en el juego: un avance de raíz
    autorado a 30 fps puede ser un teletransporte con la suelta comprimida."""
    ANTICIPATION_RATE, MAX_HOLD, FOLLOW_TAU = 0.85, 0.45, 0.06

    def __init__(self, frames, apex, contact, release_rate=1.6, windup_min=0.65, extra_hold=0.0, speed=1.0):
        n = float(frames)
        self.step_len = max(0.05, n / FPS) / max(0.05, speed)
        self.active = min(1.0, max(0.02, contact / n))
        self.apex = min(max(0.0, apex / n), self.active - 0.02)
        rel = release_rate if release_rate > 0.1 else 1.6
        self.tA = self.apex * self.step_len / self.ANTICIPATION_RATE
        self.tR = (self.active - self.apex) * self.step_len / rel
        extra = max(0.0, windup_min - (self.tA + self.tR))
        self.hold = min(extra, self.MAX_HOLD)
        self.tA += extra - self.hold
        self.hold += max(0.0, extra_hold)
        self.T = self.tA + self.hold + self.tR
        self.creep = min(0.01, (self.active - self.apex) * 0.25)

    def norm_at(self, t):
        """Tiempo normalizado del clip a 't' segundos del inicio del paso (NormAt de C#)."""
        if t <= 0.0:
            return 0.0
        if t < self.tA:
            return self.apex * math.sin(t / self.tA * math.pi * 0.5)
        t -= self.tA
        if t < self.hold:
            return self.apex + self.creep * t / self.hold
        t -= self.hold
        frm = self.apex + self.creep
        if t < self.tR:
            u = t / self.tR
            return frm + (self.active - frm) * u * u
        t -= self.tR
        r0 = max(1.0, 2.0 * (self.active - frm) / self.tR * self.step_len)
        return self.active + (t + (r0 - 1.0) * self.FOLLOW_TAU * (1.0 - math.exp(-t / self.FOLLOW_TAU))) / self.step_len


def clock_speeds(samples, timeline, hz=60.0):
    """Velocidad (m/s) en cada cuadro de juego de algo medido en cada cuadro entero del clip (el avance
    de raíz en metros que el juego aplica al transform, o la punta del arma como Vector en mundo),
    interpolado en línea recta entre cuadros y tocado con el reloj de 'timeline' (StepTimeline).
    Devuelve [(segundo, cuadro del clip al final del tramo, m/s)] hasta el final del clip."""
    n = len(samples) - 1

    def at(f):
        f = min(max(f, 0.0), float(n))
        i = min(int(f), n - 1)
        return samples[i] + (samples[i + 1] - samples[i]) * (f - i)
    out, k, prev = [], 1, at(0.0)
    while True:
        t = k / hz
        f = min(1.0, timeline.norm_at(t)) * n
        x = at(f)
        d = x - prev
        out.append((round(t, 4), round(f, 2), (d.length if isinstance(d, Vector) else abs(d)) * hz))
        prev = x
        if f >= n:
            return out
        k += 1


def plant_report(rig, frames, roots, foot_bones, ground_pts, thresh=0.02, pivots=None):
    """Detecta apoyos (pie casi quieto en mundo cerca del piso) y mide cuánto se corre dentro de cada uno.
    Con 'pivots' (puntos extra por pie: punta, talón) la deriva es la del punto que menos se movió: un pie
    que gira sobre la punta o el talón no patina."""
    out = {}
    for fb in foot_bones:
        pts = [W[fb] @ V(ground_pts[fb]) + r for W, r in zip(frames, roots)]
        segs, cur = [], None
        for i in range(1, len(pts)):
            sp = (pts[i] - pts[i - 1]).length
            low = pts[i].z < 0.12
            if sp < thresh and low:
                if cur is None:
                    cur = [i - 1, i]
                else:
                    cur[1] = i
            else:
                if cur and cur[1] - cur[0] >= 3:
                    segs.append(cur)
                cur = None
        if cur and cur[1] - cur[0] >= 3:
            segs.append(cur)
        rep = []
        tracks = [pts]
        for pv in (pivots or {}).get(fb, []):
            tracks.append([W[fb] @ V(pv) + r for W, r in zip(frames, roots)])
        for a, b in segs:
            drift = min(max(Vector((p.x - tr[a].x, p.y - tr[a].y, 0.0)).length for p in tr[a:b + 1]) for tr in tracks)
            rep.append({"frames": [a, b], "drift_cm": round(drift * 100.0, 2)})
        out[fb] = rep
    return out


def loop_seam_deg(rig, frames):
    a = rig.to_local(frames[0])
    b = rig.to_local(frames[-2] if len(frames) > 2 else frames[-1])
    c = rig.to_local(frames[-1])
    seam = max(quat_angle_deg(a[n][1], c[n][1]) for n in rig.names)
    # salto entre el anteúltimo y el primero comparado con el paso típico (continuidad de velocidad)
    step = max(quat_angle_deg(b[n][1], a[n][1]) for n in rig.names)
    return round(seam, 3), round(step, 3)


def world_verts(o, dg):
    """Vértices evaluados (armadura aplicada) de un objeto en mundo, como array numpy (n, 3)."""
    import numpy as np
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    M = np.array(oe.matrix_world)
    oe.to_mesh_clear()
    return co @ M[:3, :3].T + M[:3, 3]


def mesh_z_frames(objs, frame_list, scene=None):
    """Altura mínima y máxima de los vértices evaluados de cada objeto en cada cuadro:
    [{nombre: (z_min, z_max)}, ...] (el piso y el techo de la silueta se miden por pieza)."""
    scn = scene or bpy.context.scene
    out = []
    for f in frame_list:
        scn.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        row = {}
        for o in objs:
            w = world_verts(o, dg)
            if len(w):
                row[o.name] = (float(w[:, 2].min()), float(w[:, 2].max()))
        out.append(row)
    return out


def mesh_height_range(objs, frame_list, scene=None):
    """Altura mínima/máxima de los vértices evaluados en los cuadros dados (y el cuadro del máximo)."""
    fl = list(frame_list)
    zs = [(min(v[0] for v in r.values()), max(v[1] for v in r.values())) for r in mesh_z_frames(objs, fl, scene)]
    i = max(range(len(zs)), key=lambda k: zs[k][1])
    return min(z[0] for z in zs), zs[i][1], fl[i]


def unity_height(skinned, rigid):
    """La altura que mide CharacterFactory.NormalizeHeight en Unity, en la pose actual de la escena:
    el skinned aporta los bounds de su malla de bind (sin deformar) y cada pieza rígida las 8 esquinas
    de SUS bounds locales llevadas al mundo (una caja girada mide más que los vértices). Devuelve
    (z_min, z_max). Con ese alto en NindoContent el modelo queda a escala 1 (metros reales)."""
    lo, hi = 1e9, -1e9
    M = skinned.matrix_world
    for v in skinned.data.vertices:
        z = (M @ v.co).z
        lo, hi = min(lo, z), max(hi, z)
    for o in rigid:
        bb = [Vector(c) for c in o.bound_box]          # caja local de la malla (sin modificadores)
        for c in bb:
            z = (o.matrix_world @ c).z
            lo, hi = min(lo, z), max(hi, z)
    return lo, hi


def silhouette_mask(objs, cam, scene=None, res=(1920, 1080)):
    """Silueta de los objetos vista por la cámara, rasterizada con numpy a la densidad de píxeles de la
    pantalla del juego. Devuelve una imagen booleana (alto, ancho) de píxeles cubiertos (para comparar
    poses: cuánto de una pose de aviso cae FUERA de la silueta de la guardia)."""
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get()
    P = np.array(cam.calc_matrix_camera(dg, x=res[0], y=res[1]))
    Vw = np.array(cam.matrix_world.inverted())
    PV = P @ Vw
    cov = np.zeros((res[1], res[0]), dtype=bool)
    for o in objs:
        if o.hide_render:
            continue
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        n = len(me.vertices)
        co = np.empty(n * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        M = np.array(oe.matrix_world)
        w = co @ M[:3, :3].T + M[:3, 3]
        h = np.c_[w, np.ones(n)] @ PV.T
        sx = (h[:, 0] / h[:, 3] * 0.5 + 0.5) * res[0]
        sy = (h[:, 1] / h[:, 3] * 0.5 + 0.5) * res[1]
        me.calc_loop_triangles()
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tri)
        oe.to_mesh_clear()
        for a, b, c in tri.reshape(-1, 3):
            xs = (sx[a], sx[b], sx[c])
            ys = (sy[a], sy[b], sy[c])
            x0, x1 = max(0, int(math.floor(min(xs)))), min(res[0], int(math.ceil(max(xs))))
            y0, y1 = max(0, int(math.floor(min(ys)))), min(res[1], int(math.ceil(max(ys))))
            if x1 <= x0 or y1 <= y0:
                continue
            d = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (ys[1] - ys[0]) * (xs[2] - xs[0])
            if abs(d) < 1e-9:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            l1 = ((xs[1] - gx) * (ys[2] - gy) - (ys[1] - gy) * (xs[2] - gx)) / d
            l2 = ((xs[2] - gx) * (ys[0] - gy) - (ys[2] - gy) * (xs[0] - gx)) / d
            cov[y0:y1, x0:x1] |= (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
    return cov


# =============================================================================== render de revisión
class GameLook:
    """Materiales de revisión que imitan cómo ilumina el juego (URP en espacio Gamma, Lambert sin
    brillo especular): color = albedo * (ambiente trilight + N·L * luna [+ N·L * relleno]) + emisión,
    con la niebla exponencial². Se arma con emisión pura en EEVEE y la vista 'Raw': el píxel del PNG
    es el valor que pinta Unity, no una interpretación 'linda' de Blender. Valores de
    World/WorldBuilder.cs. Las texturas se cargan como 'Non-Color' (valores crudos, como en Gamma).
    El 'relleno' (apagado por defecto) aproxima los braseros cálidos de una arena."""

    MOON_COLOR = (0.62, 0.72, 1.0)
    MOON_INTENSITY = 1.05
    WORLD_MOON = (48.0, -38.0)              # rotación (x, y) de la luna de World/WorldBuilder.cs
    ARENA_MOON = (35.0, 180.0)              # luna de las arenas de jefe del diseño: a contraluz del jefe
    SKY, EQUATOR, GROUND = (0.22, 0.28, 0.42), (0.12, 0.15, 0.22), (0.05, 0.05, 0.07)
    FOG, FOG_DENSITY = (0.07, 0.1, 0.17), 0.012

    def __init__(self, moon_scale=1.0, moon_euler=WORLD_MOON):
        self.moon_scale = moon_scale
        self.to_moon = self.moon_dir(moon_euler)
        self.game_moon = self.to_moon.copy()
        self._moon_nodes, self._fill_nodes, self._moon_col_nodes = [], [], []
        self._state = (None, None, None, (0, 0, 0))

    @staticmethod
    def moon_dir(euler_xy):
        """Dirección HACIA la luna en la escena de revisión para una rotación (x, y) de Unity.

        La escena de revisión es el mundo del juego visto igual que en pantalla: la cámara mira a +Y de
        Blender como la del juego mira a +Z de Unity (el norte) y el este (+X) queda a la derecha en los
        dos. Unity es zurdo, así que el cambio es solo cambiar y por z: (x, y, z)_unity = (x, z, y)_blender.
        Un personaje que mira a la cámara (su frente -Y) mira al sur, como el jefe que enfrenta a Kaito."""
        ax, ay = (math.radians(a) for a in euler_xy)
        fwd_u = Vector((math.sin(ay) * math.cos(ax), -math.sin(ax), math.cos(ay) * math.cos(ax)))
        return -Vector((fwd_u.x, fwd_u.z, fwd_u.y)).normalized()

    def set_moon(self, to_moon=None, scale=None, fill_dir=None, fill_rgb=(0, 0, 0)):
        """Cambia la luz de todos los materiales ya creados (para mostrar el modelado de frente o la
        lectura real del juego, con la luna detrás del jefe)."""
        self._state = (to_moon, scale, fill_dir, fill_rgb)
        d = V(to_moon or self.game_moon).normalized()
        for n in self._moon_nodes:
            n.inputs[0].default_value, n.inputs[1].default_value, n.inputs[2].default_value = d
        k = self.MOON_INTENSITY * (self.moon_scale if scale is None else scale)
        for n in self._moon_col_nodes:
            n.inputs[0].default_value, n.inputs[1].default_value, n.inputs[2].default_value = (c_ * k for c_ in self.MOON_COLOR)
        fd = V(fill_dir or (0, -1, 0.5)).normalized()
        for nd, nc in self._fill_nodes:
            nd.inputs[0].default_value, nd.inputs[1].default_value, nd.inputs[2].default_value = fd
            nc.inputs[0].default_value, nc.inputs[1].default_value, nc.inputs[2].default_value = fill_rgb

    def build(self, name, albedo_image=None, albedo_rgb=None, emission_rgb=(0, 0, 0), emission_gain=1.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        N = nt.nodes.new
        L = nt.links.new
        out = N("ShaderNodeOutputMaterial")
        em = N("ShaderNodeEmission")
        L(em.outputs[0], out.inputs[0])
        if albedo_image is not None:
            tex = N("ShaderNodeTexImage")
            tex.image = albedo_image
            tex.interpolation = 'Closest'
            alb = tex.outputs[0]
        else:
            c = N("ShaderNodeRGB")
            c.outputs[0].default_value = (*albedo_rgb, 1.0)
            alb = c.outputs[0]
        geo = N("ShaderNodeNewGeometry")

        def lambert(dir_node, col_node):
            dot = N("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
            L(geo.outputs["Normal"], dot.inputs[0]); L(dir_node.outputs[0], dot.inputs[1])
            ndl = N("ShaderNodeMath"); ndl.operation = 'MAXIMUM'; ndl.inputs[1].default_value = 0.0
            L(dot.outputs["Value"], ndl.inputs[0])
            sc = N("ShaderNodeVectorMath"); sc.operation = 'SCALE'
            L(col_node.outputs[0], sc.inputs[0]); L(ndl.outputs[0], sc.inputs["Scale"])
            return sc
        ldir = N("ShaderNodeCombineXYZ"); mc = N("ShaderNodeCombineXYZ")
        self._moon_nodes.append(ldir); self._moon_col_nodes.append(mc)
        moon = lambert(ldir, mc)
        fdir = N("ShaderNodeCombineXYZ"); fcol = N("ShaderNodeCombineXYZ")
        self._fill_nodes.append((fdir, fcol))
        fill = lambert(fdir, fcol)
        # ambiente trilight por la normal z
        sep = N("ShaderNodeSeparateXYZ"); L(geo.outputs["Normal"], sep.inputs[0])
        up = N("ShaderNodeMath"); up.operation = 'MAXIMUM'; up.inputs[1].default_value = 0.0
        L(sep.outputs[2], up.inputs[0])
        dn = N("ShaderNodeMath"); dn.operation = 'MULTIPLY'; dn.inputs[1].default_value = -1.0
        L(sep.outputs[2], dn.inputs[0])
        dn2 = N("ShaderNodeMath"); dn2.operation = 'MAXIMUM'; dn2.inputs[1].default_value = 0.0
        L(dn.outputs[0], dn2.inputs[0])
        mix1 = N("ShaderNodeMix"); mix1.data_type = 'RGBA'
        mix1.inputs["A"].default_value = (*self.EQUATOR, 1); mix1.inputs["B"].default_value = (*self.SKY, 1)
        L(up.outputs[0], mix1.inputs["Factor"])
        mix2 = N("ShaderNodeMix"); mix2.data_type = 'RGBA'
        L(mix1.outputs["Result"], mix2.inputs["A"]); mix2.inputs["B"].default_value = (*self.GROUND, 1)
        L(dn2.outputs[0], mix2.inputs["Factor"])
        sh1 = N("ShaderNodeVectorMath"); sh1.operation = 'ADD'
        L(mix2.outputs["Result"], sh1.inputs[0]); L(moon.outputs[0], sh1.inputs[1])
        shade = N("ShaderNodeVectorMath"); shade.operation = 'ADD'
        L(sh1.outputs[0], shade.inputs[0]); L(fill.outputs[0], shade.inputs[1])
        lit = N("ShaderNodeVectorMath"); lit.operation = 'MULTIPLY'
        L(alb, lit.inputs[0]); L(shade.outputs[0], lit.inputs[1])
        emi = N("ShaderNodeCombineXYZ")
        emi.inputs[0].default_value, emi.inputs[1].default_value, emi.inputs[2].default_value = (c_ * emission_gain for c_ in emission_rgb)
        col = N("ShaderNodeVectorMath"); col.operation = 'ADD'
        L(lit.outputs[0], col.inputs[0]); L(emi.outputs[0], col.inputs[1])
        # niebla exp² por distancia a la cámara
        cam = N("ShaderNodeCameraData")
        fd = N("ShaderNodeMath"); fd.operation = 'MULTIPLY'; fd.inputs[1].default_value = self.FOG_DENSITY
        L(cam.outputs["View Distance"], fd.inputs[0])
        fsq = N("ShaderNodeMath"); fsq.operation = 'MULTIPLY'
        L(fd.outputs[0], fsq.inputs[0]); L(fd.outputs[0], fsq.inputs[1])
        fneg = N("ShaderNodeMath"); fneg.operation = 'MULTIPLY'; fneg.inputs[1].default_value = -1.0
        L(fsq.outputs[0], fneg.inputs[0])
        fexp = N("ShaderNodeMath"); fexp.operation = 'EXPONENT'
        L(fneg.outputs[0], fexp.inputs[0])
        finv = N("ShaderNodeMath"); finv.operation = 'SUBTRACT'; finv.inputs[0].default_value = 1.0
        L(fexp.outputs[0], finv.inputs[1])
        fog = N("ShaderNodeMix"); fog.data_type = 'RGBA'
        L(finv.outputs[0], fog.inputs["Factor"]); L(col.outputs[0], fog.inputs["A"])
        fog.inputs["B"].default_value = (*self.FOG, 1)
        L(fog.outputs["Result"], em.inputs["Color"])
        self.set_moon(*self._state)
        return m


def setup_review_scene(res=(1280, 720), samples=1):
    scn = bpy.context.scene
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scn.render.engine = e
            break
        except TypeError:
            continue
    try:
        scn.eevee.taa_render_samples = 8
        scn.eevee.use_shadows = False
    except AttributeError:
        pass
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.view_settings.view_transform = 'Raw'
    scn.view_settings.look = 'None'
    scn.render.film_transparent = False
    w = bpy.data.worlds.new("ReviewWorld")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*GameLook.FOG, 1)
    scn.world = w
    scn.render.image_settings.file_format = 'PNG'
    scn.render.image_settings.color_mode = 'RGB'
    return scn


def camera(scn, name="ReviewCam"):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cd = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cd)
        scn.collection.objects.link(cam)
    scn.camera = cam
    return cam


def game_camera(cam, focus, pitch=52.0, dist=24.0, fov=30.0, yaw=0.0):
    """Cámara del juego: perspectiva, FOV vertical, mirando hacia +Y de Blender (el norte del mapa)
    desde atrás y arriba. yaw gira alrededor del foco."""
    cd = cam.data
    cd.type = 'PERSP'
    cd.sensor_fit = 'VERTICAL'
    cd.angle_y = math.radians(fov)
    cd.clip_start, cd.clip_end = 0.5, 200.0
    off = Vector((0.0, -dist * math.cos(math.radians(pitch)), dist * math.sin(math.radians(pitch))))
    off = Matrix.Rotation(math.radians(yaw), 3, 'Z') @ off
    cam.location = V(focus) + off
    cam.rotation_euler = Euler((math.radians(90.0 - pitch), 0.0, math.radians(yaw)), 'XYZ')


def ortho_camera(cam, center, scale, azimuth=0.0, elevation=0.0):
    """Ortográfica para hojas de perfil/frente: azimuth 0 = mira el frente del personaje (desde -Y)."""
    cd = cam.data
    cd.type = 'ORTHO'
    cd.ortho_scale = scale
    cd.sensor_fit = 'VERTICAL'
    cd.clip_start, cd.clip_end = 0.1, 200.0
    d = Matrix.Rotation(math.radians(azimuth), 3, 'Z') @ Vector((0.0, -1.0, 0.0))
    d = (d * math.cos(math.radians(elevation)) + Vector((0, 0, math.sin(math.radians(elevation))))).normalized()
    cam.location = V(center) + d * 40.0
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()


def render(scn, path):
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)


def compose_sheet(layout_json, python="python"):
    """Arma las hojas de contacto con PIL fuera de Blender (el Python de Blender no trae PIL)."""
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "contact_sheet_anim.py")
    try:
        r = subprocess.run([python, script, layout_json], capture_output=True, text=True, timeout=600)
        print(r.stdout.strip())
        if r.returncode != 0:
            print("[nindo_anim] no se pudo componer la hoja:", r.stderr.strip()[-400:])
    except (OSError, subprocess.SubprocessError) as e:
        print("[nindo_anim] sin Python externo para componer hojas:", e)
