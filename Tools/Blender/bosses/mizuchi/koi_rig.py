"""Esqueleto del Gran Koi y la traducción de poses 'semánticas' a rotaciones locales de hueso.

Las poses se escriben en términos del animal, no de los ejes de cada hueso:
  columna (spine_f, head, spine_b1..4, tail): bend (+ = la punta va hacia la IZQUIERDA del koi, +X),
      lift (+ = la punta sube), twist (+ = el lomo gira hacia su derecha).
  Con esta convención una C (cabeza y cola del mismo lado) es el MISMO signo en las dos cadenas y una S
  es signo opuesto: el error de signos del prototipo no se puede repetir.
  body: turn (+ = la cabeza gira a su izquierda), pitch (+ = nariz arriba), roll (+ = cae sobre su lado
      derecho), tx/ty/tz (m; ty negativo = adelante), sx/sy/sz (escala - 1).
  aletas, branquias, bigotes, shide (lado L/R espejado): up, fwd, out (+ = la punta se aleja del cuerpo),
      twist, fold (escala X local - 1: cierra el abanico), grow (escala Y local - 1: largo).
  dorsales/anal: lean (+ = hacia la izquierda), rake (+ = la punta va hacia la cola).
  jaw: open (+ = abre), fwd (m, la boca protráctil sale), bend.
  seal: tz/ty (m), spin (grados), scale.  root: tz.
Cada canal se convierte a un cuaternión en el espacio de reposo del esqueleto ('la punta va hacia v' =
giro alrededor de d × v) y luego al espacio local del hueso, así que la tabla de huesos puede cambiar sin
tocar las animaciones.
"""
import bpy, math
from mathutils import Vector, Matrix, Quaternion
import koi_model as KM

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
CHAIN = ["spine_f", "head", "spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail"]
FRONT = ["spine_f", "head"]
BACK = ["spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail"]


def build_armature(name="MizuchiRig"):
    ad = bpy.data.armatures.new(name)
    ao = bpy.data.objects.new(name, ad)
    bpy.context.scene.collection.objects.link(ao)
    bpy.context.view_layer.objects.active = ao
    ao.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    table = KM.bones()
    eb = {}
    for n, h, t, p, z in table:
        b = ad.edit_bones.new(n)
        b.head, b.tail = h, t
        b.align_roll(z)
        b.use_deform = True
        eb[n] = b
    for n, h, t, p, z in table:
        if p:
            eb[n].parent = eb[p]
            eb[n].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    ad.display_type = 'STICK'
    for pb in ao.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ao


def skin(ob, arm):
    ob.parent = arm
    m = ob.modifiers.new("Armature", 'ARMATURE')
    m.object = arm


class Rig:
    """Datos de reposo del esqueleto + conversión de poses semánticas + cinemática directa propia
    (rápida y sin depsgraph: la usan los resortes, el lint y las mediciones)."""

    def __init__(self, arm):
        self.arm = arm
        bones = arm.data.bones
        self.names = [b.name for b in bones]
        self.order = []
        seen = set()

        def visit(b):
            if b.name in seen:
                return
            if b.parent:
                visit(b.parent)
            seen.add(b.name)
            self.order.append(b.name)
        for b in bones:
            visit(b)
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.rest_q = {n: m.to_quaternion() for n, m in self.rest.items()}
        self.rel = {}
        for b in bones:
            self.rel[b.name] = (self.rest[b.parent.name].inverted() @ self.rest[b.name]) if b.parent else self.rest[b.name].copy()
        self.d = {b.name: (b.tail_local - b.head_local).normalized() for b in bones}
        self.length = {b.name: b.length for b in bones}
        self.head_rest = {b.name: b.head_local.copy() for b in bones}
        self.side = {n: (1 if n.endswith(("_L", "_L1", "_L2", "_L3")) else -1 if n.endswith(("_R", "_R1", "_R2", "_R3")) else 0)
                     for n in self.names}
        self.children = {n: [c for c in self.names if self.parent[c] == n] for n in self.names}

    # ------------------------------------------------------------ canales
    def channels(self, n):
        d, s = self.d[n], self.side[n]
        if n == "body":
            return {"turn": ("axis", Z), "pitch": ("axis", -X), "roll": ("axis", -Y),
                    "tx": ("loc", X), "ty": ("loc", Y), "tz": ("loc", Z), "sx": ("scale", 0), "sy": ("scale", 1), "sz": ("scale", 2)}
        if n == "root":
            return {"tz": ("loc", Z)}
        if n in CHAIN:
            return {"bend": ("toward", X), "lift": ("toward", Z), "twist": ("axis", -Y)}
        if n == "jaw":
            return {"open": ("toward", -Z), "fwd": ("loc", -Y), "bend": ("toward", X)}
        if n == "seal":
            return {"tz": ("loc", Z), "ty": ("loc", Y), "spin": ("axis", Z), "scale": ("uscale", None), "tilt": ("toward", -Y)}
        if n.startswith(("dorsal", "anal")):
            return {"lean": ("toward", X), "rake": ("toward", Y), "grow": ("scale", 1)}
        if n.startswith(("pec", "pel", "fluke", "gill", "barbel", "whisker", "shide", "horn")):
            return {"up": ("toward", Z), "fwd": ("toward", -Y), "out": ("toward", X * (s or 1)),
                    "twist": ("axis", d * (s or 1)), "fold": ("scale", 0), "grow": ("scale", 1)}
        return {}

    def basis(self, n, vals):
        """vals: {canal: valor} -> (loc local, quat local, escala local)."""
        ch = self.channels(n)
        d = self.d[n]
        q = Quaternion()
        loc = Vector()
        scl = Vector((1, 1, 1))
        # orden fijo: primero el giro sobre su eje, después las flexiones
        order = ["twist", "roll", "up", "out", "fwd", "lift", "pitch", "rake", "lean", "open", "bend", "turn", "spin", "tilt"]
        for c in order:
            a = vals.get(c, 0.0)
            if not a or c not in ch:
                continue
            kind, v = ch[c]
            if kind == "axis":
                q = Quaternion(v.normalized(), math.radians(a)) @ q
            elif kind == "toward":
                # el eje sale de la dirección YA girada: up 45 + fwd -70 deja la punta donde se espera
                ax = (q @ d).cross(v)
                if ax.length < 1e-4:
                    continue
                q = Quaternion(ax.normalized(), math.radians(a)) @ q
        for c, a in vals.items():
            if c not in ch or not a:
                continue
            kind, v = ch[c]
            if kind == "loc":
                loc += v * a
            elif kind == "scale":
                scl[v] *= (1.0 + a)
            elif kind == "uscale":
                scl *= (1.0 + a)
        R = self.rest_q[n]
        Ri = R.inverted()
        ql = Ri @ q @ R
        ll = Ri @ loc
        return ll, ql, scl

    # ------------------------------------------------------------ cinemática directa
    def fk(self, basis):
        """basis: {hueso: (loc, quat, escala) locales}. Devuelve las matrices de pose en espacio del
        esqueleto (igual que pose_bone.matrix)."""
        M = {}
        for n in self.order:
            l, q, s = basis.get(n, (Vector(), Quaternion(), Vector((1, 1, 1))))
            B = Matrix.Translation(l) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
            p = self.parent[n]
            M[n] = (M[p] @ self.rel[n] @ B) if p else (self.rel[n] @ B)
        return M
