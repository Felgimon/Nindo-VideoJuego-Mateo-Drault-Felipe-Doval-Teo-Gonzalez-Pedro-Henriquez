"""Animación por script de los personajes del EQUIPO (ninja, sumo, Gorō, abuelo) sobre sus esqueletos
originales (Blender 4.4). Módulo hermano de nindo_anim.py: usa su núcleo (Rig, Pose, IK analítica, claves,
StepTimeline, mediciones) sin tocarlo, y agrega lo que cambia con un esqueleto que NO se hizo para esto.

Por qué sobre el esqueleto original y no uno "de juego" limpio (lo que pedía la auditoría, ANIM-04):
el modelo de cada personaje ya lo usan los kits de zona (cuelgan sus huesos por nombre), el pulido de la
fase B2 (malla, pesos, materiales re-exportados en el lugar y validados contra el original) y, en el sumo,
clips .anim del equipo que se ligan por ruta de transform. Re-emparentar manos y pies cambia esas rutas y
obliga a rehacer TODO a la vez; acá se autora sobre la jerarquía que hay y se la usa como si fuera limpia:
  * el hueso de control del que cuelga la mano o el pie (TargetBrazo, TargetPie, AntebrazoTarget...) se
    pone pegado a la mano/pie (con su offset de reposo): los vértices que pesa lo siguen como en el rig
    del equipo y la mano no se despega dentro de un clip;
  * los polos que pesan vértices (las rodillas del sumo) van rígidos con la tibia;
  * el resto de la ayuda de IK queda en reposo respecto de su padre (no pesa nada).
Lo que queda pendiente de ese esqueleto es el cruce entre dos clips muy distintos (Unity mezcla cada hueso
por separado y la muñeca de un control a la raíz no sigue al antebrazo): los cruces de ataque son cortos
(0.03-0.08 s) y las poses de salida de cada clip están pensadas para encadenar.

Marco de autoría (el mismo para los cuatro, en METROS DEL JUEGO): origen en el piso bajo el transform del
juego, frente = -Y, izquierda del personaje = +X, arriba = +Z (convención de nindo_anim / STYLE.md). Cada
personaje del equipo mira a otro eje de Blender y está en otras unidades; la conversión vive en TeamChar y
los clips no se enteran. Giros en grados XYZ de ese marco: x + = inclinarse hacia adelante, y + = hacia su
izquierda, z + = girar hacia su izquierda.
"""
import bpy, math, os, sys, json
from mathutils import Vector, Matrix, Quaternion, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ASSETS = os.path.join(REPO, "Nindo", "Assets")
for _p in (HERE, os.path.join(REPO, "Tools", "Blender", "characters")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import nindo_anim as NA                         # noqa: E402
from nindo_anim import V, compose, rot3, basis_yz   # noqa: E402

FPS = NA.FPS


def side_names(fmt, right, left):
    """Nombres de un hueso de cada lado: los FBX del equipo no respetan .L/.R respecto del personaje
    (el ninja y el sumo miran a +X/+Y, así que su '.L' queda del lado DERECHO). Se mapea por geometría."""
    return {"r": fmt.format(right), "l": fmt.format(left)}


# =============================================================================== fichas de personaje
# u: unidades del FBX por metro del juego = alto de la unión de bounds que mide CharacterFactory.NormalizeHeight
# dividido por el 'height' de NindoContent (se recalcula al cargar y se compara con este valor de control).
# fwd: hacia dónde mira el personaje en el mundo de Blender (medido con los ojos de la malla).
CHARS = {
    "ninja": dict(
        fbx="Models/Ninja/Ninja 1.fbx", height=1.7, fwd=(1, 0, 0), right_tag="L", left_tag="R",
        pelvis="Root", spine=["EspaldaBaja"], chest=["EspaldaAlta"], head="Cabeza",
        clav="Hombro.{}", upper="Brazo.{}", fore="Antebrazo.{}", hand="Mano.{}", hand_ctrl=None,
        thigh="Pierna.{}", shin="Tibia.{}", foot="Pie.{}", foot_ctrl=None,
        fingers={"r": [["Dedo1.L", "PuntaDedo.L"], ["Dedo2.l", "PuntaDedo2.L"], ["Dedo3.L", "PuntaDedo3.L"]],
                 "l": [["Dedo1.R", "PuntaDedo1.R"], ["Dedo2.R", "PuntaDedo2.R"], ["Dedo3.R", "PuntaDedo3.R"]]},
        thumb={"r": ["Pulgar.L", "PuntaPulgar.L"], "l": ["Pulgar.R", "PuntaPulgar.R"]},
        index_pinky={"r": ("Dedo1.L", "Dedo3.L"), "l": ("Dedo1.R", "Dedo3.R")},
        weapon=dict(kind="katana", bone="Katana", mesh="Katana", hand="r"),
        follow={}, kidnapper=None,
    ),
    "sumo": dict(
        fbx="Characters/Sumo/luchadorsumo.fbx", height=2.6, fwd=(0, 1, 0), right_tag="L", left_tag="R",
        pelvis="Root", spine=["Torso"], chest=[], head="Cabeza",
        clav="Hombro.{}", upper="Brazo.{}", fore="Antebrazo.{}", hand="Palma.{}", hand_ctrl="TargetBrazo.{}",
        thigh="Pierna.{}", shin="Tibia.{}", foot="pie.{}", foot_ctrl="TargetPie.{}",
        fingers={s: [[f"Dedo1.{t}", f"PuntaDedo1.{t}"], [f"Dedo2.{t}", f"PuntaDedo2.{t}"], [f"Dedo3.{t}", f"PuntaDedo3.{t}"]]
                 for s, t in (("r", "L"), ("l", "R"))},
        thumb={"r": ["Pulgar.L", "PuntaPulgar.L"], "l": ["Pulgar.R", "PuntaPulgar.R"]},
        index_pinky={"r": ("Dedo1.L", "Dedo3.L"), "l": ("Dedo1.R", "Dedo3.R")},
        weapon=None,
        # las rodillas pesan vértices en el polo (35 por pierna): van rígidos con la tibia
        follow={"PolePie.L": "Tibia.L", "PolePie.R": "Tibia.R", "PoleBrazo.L": "Antebrazo.L", "PoleBrazo.R": "Antebrazo.R"},
        kidnapper=None,
    ),
    "goro": dict(
        fbx="Models/Minijefe.fbx", height=3.41, fwd=(0, -1, 0), right_tag="R", left_tag="L",
        pelvis="Root", spine=["Torso"], chest=[], head="Cabeza",
        clav="Hombro.{}", upper="Brazo.{}", fore="Antebrazo.{}", hand="Mano.{}", hand_ctrl="TargetBrazo.{}",
        thigh="Pierna.{}", shin="Tibia.{}", foot="Pie.{}", foot_ctrl="TargetPie.{}",
        fingers={s: [[f"Dedo2.{t}", f"Puntadedo2.{t}"], [f"Dedo2.{t}.001", f"Puntadedo2.{t}.001"],
                     [f"Dedo2.{t}.002", f"Puntadedo2.{t}.002"]] for s, t in (("r", "R"), ("l", "L"))},
        thumb={s: [f"Dedo1.001.{t}", f"Puntadedo1.001.{t}"] for s, t in (("r", "R"), ("l", "L"))},
        index_pinky={"r": ("Dedo2.R.002", "Dedo2.R.001"), "l": ("Dedo2.L.002", "Dedo2.L.001")},
        weapon=dict(kind="club", bone="BaseM", mesh="Cylinder.005", grips=("Agarre1", "Agarre2")),
        follow={}, kidnapper=None,
    ),
    "grandpa": dict(
        fbx="Nindo/Art/Models/Characters/Grandpa.fbx", height=1.45, fwd=(0, 1, 0), right_tag="L", left_tag="R",
        pelvis="Root", spine=["Torso"], chest=[], head="Cabeza",
        clav="Hombro.{}", upper="Brazo.{}", fore="Antebrazo.{}", hand="Mano.{}", hand_ctrl="AntebrazoTarget.{}",
        thigh="Pierna.{}", shin="Tibia.{}", foot="Pie.{}", foot_ctrl="TibiaTarget.{}",
        fingers={s: [[f"Dedo1.{t}", f"PuntaDedo1.{t}"], [f"Dedo2.{t}", f"PuntaDedo2.{t}"], [f"Dedo3.{t}", f"PuntaDedo3.{t}"]]
                 for s, t in (("r", "L"), ("l", "R"))},
        thumb={"r": ["Pulgar.L", "PuntaPulgar.L"], "l": ["Pulgar.R", "PuntaPulgar.R"]},
        index_pinky={"r": ("Dedo1.L", "Dedo3.L"), "l": ("Dedo1.R", "Dedo3.R")},
        weapon=None, follow={},
        # el FBX del abuelo trae también al ninja del secuestro (esqueleto '.001'): en los clips nuevos queda
        # quieto en la pose del primer cuadro del secuestro (agazapado, esperando), que es lo que se ve del
        # NPC 'kidnap' mientras el abuelo respira antes de la toma del equipo
        kidnapper=dict(suffix=".001", take_frame=2),
        export_kw=dict(apply_scale_options='FBX_SCALE_UNITS'),
    ),
}

GRIP_CURL = (62.0, 78.0)          # grados de cada falange al cerrar el puño del todo
THUMB_CURL = (26.0, 34.0)


class TeamChar:
    """Un personaje del equipo cargado en la escena, con la conversión del marco de autoría al esqueleto."""

    def __init__(self, name, spec):
        self.name, self.spec = name, spec
        import charlib as C
        src = os.path.join(ASSETS, spec["fbx"])
        self.src = src
        self.arm = C.load(src)
        self.take_actions = [a for a in bpy.data.actions]
        arm = self.arm
        self.kid_pose = self.sample_kidnapper() if spec.get("kidnapper") else {}
        if arm.animation_data:
            arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.scale = (1, 1, 1)
        bpy.context.view_layer.update()
        self.meshes = [o for o in bpy.data.objects if o.type == 'MESH']
        self.rig = NA.Rig(arm)
        A = arm.matrix_world.copy()
        self.A, self.Ai = A, A.inverted()
        # alto que mide NormalizeHeight (unión de bounds de las mallas con skin en su pose de bind) -> unidades por
        # metro. Las piezas rígidas (katana, martillo) cuelgan de un hueso: en reposo el martillo de Gorō queda
        # parado en el piso adelante y estiraría la cuenta; en el prefab están en la mano y no la cambian
        dg = bpy.context.evaluated_depsgraph_get()
        lo, hi = 1e9, -1e9
        for o in self.meshes:
            if not o.vertex_groups:
                continue
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            for v in me.vertices:
                z = (oe.matrix_world @ v.co).z
                lo, hi = min(lo, z), max(hi, z)
            oe.to_mesh_clear()
        self.ground = lo
        self.u = (hi - lo) / spec["height"]
        F = Vector(spec["fwd"]).normalized()
        Z = Vector((0, 0, 1))
        # columnas = adónde va cada eje del marco de autoría: +X (izquierda), +Y (atrás), +Z (arriba)
        self.Rcw = Matrix((Z.cross(F), -F, Z)).transposed()
        self.Rc = rot3(self.Ai) @ self.Rcw            # marco de autoría -> ejes de la armadura
        self.Rci = self.Rc.transposed()
        self.O = Vector((0.0, 0.0, lo))
        s = spec
        self.side = {}
        for k, tag in (("r", s["right_tag"]), ("l", s["left_tag"])):
            d = {}
            for role in ("clav", "upper", "fore", "hand", "hand_ctrl", "thigh", "shin", "foot", "foot_ctrl"):
                d[role] = s[role].format(tag) if s[role] else None
            self.side[k] = d
        self.measure()

    # ------------------------------------------------------------------ conversión de marcos
    def P(self, p):
        """Punto del marco de autoría (m) -> espacio de la armadura."""
        return self.Ai @ (self.O + (self.Rcw @ V(p)) * self.u)

    def D(self, d):
        """Dirección del marco de autoría -> ejes de la armadura."""
        return (self.Rc @ V(d)).normalized()

    def Q(self, r):
        """Giro (grados XYZ del marco de autoría, o Quaternion en ese marco) -> Quaternion en ejes de la armadura."""
        q = r if isinstance(r, Quaternion) else NA.euler_q(r)
        return (self.Rc @ q.to_matrix() @ self.Rci).to_quaternion()

    def Pc(self, p_arm):
        """Punto de la armadura -> marco de autoría (m)."""
        return (self.Rcw.transposed() @ ((self.A @ V(p_arm)) - self.O)) / self.u

    def Dc(self, d_arm):
        return (self.Rci @ V(d_arm)).normalized()

    def offset_arm(self, d):
        """Desplazamiento del marco de autoría (m) -> desplazamiento en la armadura."""
        return self.Rc @ V(d) * self.u

    # ------------------------------------------------------------------ medidas de reposo
    def head(self, n):
        return self.rig.rest[n].translation.copy()

    def tail(self, n):
        return self.rig.rest[n] @ Vector((0.0, self.rig.length[n], 0.0))

    def measure(self):
        """Marcas de reposo en el marco de autoría y los marcos fijos de manos, pies y arma."""
        R = self.rig
        L = self.land = {}
        sp = self.spec
        L["pelvis"] = self.Pc(self.head(sp["pelvis"]))
        L["head"] = self.Pc(self.head(sp["head"]))
        self.hand_info, self.foot_info = {}, {}
        for k, d in self.side.items():
            L["shoulder_" + k] = self.Pc(self.head(d["upper"]))
            L["elbow_" + k] = self.Pc(self.head(d["fore"]))
            L["wrist_" + k] = self.Pc(self.head(d["hand"]))
            L["hip_" + k] = self.Pc(self.head(d["thigh"]))
            L["knee_" + k] = self.Pc(self.head(d["shin"]))
            L["ankle_" + k] = self.Pc(self.head(d["foot"]))
            # mano: dónde queda la punta del antebrazo vista desde la mano (IK apunta ahí), el dedo y la palma
            h = d["hand"]
            Rh0 = rot3(R.rest[h])
            fore_tail_local = R.rest_inv[h] @ self.tail(d["fore"])
            fdir = Rh0.col[1].normalized()
            ip = sp["index_pinky"][k]
            lat = (self.head(ip[0]) - self.head(ip[1]))
            lat = (lat - fdir * lat.dot(fdir)).normalized()          # hacia el índice
            thumb = self.head(sp["thumb"][k][1]) - self.head(h)
            n = thumb - fdir * thumb.dot(fdir) - lat * thumb.dot(lat)
            if n.length < 1e-5:
                n = fdir.cross(lat)
            n.normalize()                                              # hacia la palma (lado del pulgar)
            chi = 1.0 if n.dot(lat.cross(fdir)) > 0 else -1.0
            M0 = Matrix((fdir, lat, n)).transposed()
            hand_len = R.length[h]
            # centro del puño en el espacio de la mano: a media palma y hacia adentro
            fist = R.rest_inv[h] @ (self.head(h) + fdir * hand_len * 0.62 + n * hand_len * 0.28)
            self.hand_info[k] = dict(Rh0=Rh0, fore_tail_local=fore_tail_local, M0=M0, chi=chi, fist=fist, len=hand_len,
                                     curl=self.finger_axes(k, n))
            f = d["foot"]
            self.foot_info[k] = dict(shin_tail_local=R.rest_inv[f] @ self.tail(d["shin"]), Rf0=rot3(R.rest[f]))
        L["sole_z"] = {k: self.Pc(self.head(self.side[k]["foot"])).z for k in "rl"}
        w = sp.get("weapon")
        self.weapon_info = None
        if w and w["kind"] == "katana":
            self.weapon_info = self.measure_katana(w)
        elif w and w["kind"] == "club":
            self.weapon_info = self.measure_club(w)
        self.leg_len = {k: (R.length[self.side[k]["thigh"]] + R.length[self.side[k]["shin"]]) / self.u for k in "rl"}
        self.arm_len = {k: (R.length[self.side[k]["upper"]] + R.length[self.side[k]["fore"]]) / self.u for k in "rl"}
        self.measure_feet()

    def measure_feet(self):
        """Punta y talón de cada suela (malla en reposo) respecto del tobillo, en el marco de autoría: el pie que
        despega rueda sobre la punta y el que apoya, sobre el talón, con ese punto quieto en el piso."""
        dg = bpy.context.evaluated_depsgraph_get()
        self.sole = {}
        for k in "rl":
            names = {self.side[k]["foot"]} | ({self.side[k]["foot_ctrl"]} if self.side[k]["foot_ctrl"] else set())
            pts = []
            for o in self.meshes:
                gi = {g.index for g in o.vertex_groups if g.name in names}
                if not gi:
                    continue
                oe = o.evaluated_get(dg)
                me = oe.to_mesh()
                for v in o.data.vertices:
                    if sum(g.weight for g in v.groups if g.group in gi) > 0.5:
                        pts.append(self.Pc(self.Ai @ (oe.matrix_world @ me.vertices[v.index].co)))
                oe.to_mesh_clear()
            ank = self.land["ankle_" + k]
            low = [p for p in pts if p.z < min(q.z for q in pts) + 0.025]
            toe = min(low, key=lambda p: p.y)
            heel = max(low, key=lambda p: p.y)
            self.sole[k] = dict(toe=Vector((ank.x, toe.y, toe.z)) - ank, heel=Vector((ank.x, heel.y, heel.z)) - ank)

    def foot_at(self, k, x, y, yaw=0.0, pitch=0.0, roll=0.0, z=0.0):
        """Tobillo y giro de un pie apoyado en (x, y) del piso (m, marco de autoría) con la punta girada 'yaw' (° hacia
        la izquierda del personaje). pitch > 0 levanta el talón rodando sobre la punta, < 0 levanta la punta sobre el
        talón: el punto de apoyo queda clavado. z sube el pie entero (vuelo). Devuelve (tobillo, (pitch, roll, yaw))."""
        base = Vector((x, y, self.land["sole_z"][k] + z))
        R0 = Euler((0.0, math.radians(roll), math.radians(yaw)), 'XYZ').to_matrix()
        R = Euler((math.radians(pitch), math.radians(roll), math.radians(yaw)), 'XYZ').to_matrix()
        if abs(pitch) < 1e-6:
            return base, (0.0, roll, yaw)
        v = self.sole[k]["toe" if pitch > 0 else "heel"]
        pivot = base + R0 @ v
        return pivot - R @ v, (pitch, roll, yaw)

    def finger_axes(self, k, palm_n):
        """Eje de cierre de cada falange (espacio local del hueso): la punta va hacia la palma."""
        R = self.rig
        out = {}
        chains = [(c, GRIP_CURL) for c in self.spec["fingers"][k]] + [(self.spec["thumb"][k], THUMB_CURL)]
        for chain, angs in chains:
            for i, b in enumerate(chain):
                if b not in R.rest:
                    continue
                d = rot3(R.rest[b]).col[1].normalized()
                ax = d.cross(palm_n)
                if ax.length < 1e-4:
                    continue
                ax.normalize()
                # rota d hacia la palma: (eje x d) tiene que apuntar hacia n
                if ax.cross(d).dot(palm_n) < 0:
                    ax = -ax
                out[b] = (rot3(R.rest[b]).transposed() @ ax, math.radians(angs[min(i, 1)]))
        return out

    def measure_katana(self, w):
        """Eje de la hoja y del filo medidos en la malla de la katana, en el espacio de la mano."""
        k = w["hand"]
        h = self.side[k]["hand"]
        o = bpy.data.objects[w["mesh"]]
        dg = bpy.context.evaluated_depsgraph_get()
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        mats = [m.name if m else "" for m in me.materials]
        vs = [self.Ai @ (oe.matrix_world @ v.co) for v in me.vertices]
        hand0 = self.head(h)
        tip = max(vs, key=lambda v: (v - hand0).length)
        pom = min(vs, key=lambda v: (v - tip).length * -1.0)     # el más lejano a la punta: el pomo
        axis = (tip - pom).normalized()
        glint = Vector()
        for p in me.polygons:
            if mats[p.material_index] == "Glint":
                glint += (rot3(oe.matrix_world) @ p.normal) * p.area
        oe.to_mesh_clear()
        glint = rot3(self.Ai) @ glint
        edge = (glint - axis * glint.dot(axis)).normalized()
        # punto del mango que agarra el puño: el más cercano del eje al centro del puño de reposo
        fist_arm = self.rig.rest[h] @ self.hand_info[k]["fist"]
        t = (fist_arm - pom).dot(axis)
        grip = pom + axis * t
        Rh0 = rot3(self.rig.rest[h])
        F0 = basis_yz(axis, edge)
        return dict(kind="katana", hand=k, K=F0.transposed() @ Rh0, grip_local=self.rig.rest_inv[h] @ grip,
                    tip_local=self.rig.rest_inv[w["bone"]] @ tip, length=(tip - grip).length / self.u,
                    pommel_back=(grip - pom).length / self.u)

    def measure_club(self, w):
        """El martillo de Gorō cuelga de un hueso suelto ('BaseM'): el mango es su eje Y, la cabeza sale hacia +X
        del mundo en reposo. Agarre1 (abajo) y Agarre2 (arriba) son los dos puntos de agarre."""
        R = self.rig
        b = w["bone"]
        RB0 = rot3(R.rest[b])
        haft0 = RB0.col[1].normalized()
        o = bpy.data.objects[w["mesh"]]
        dg = bpy.context.evaluated_depsgraph_get()
        oe = o.evaluated_get(dg)
        me = oe.to_mesh()
        vs = [self.Ai @ (oe.matrix_world @ v.co) for v in me.vertices]
        oe.to_mesh_clear()
        base = self.head(b)
        ts = [(v - base).dot(haft0) for v in vs]
        far = max(ts)
        # la cabeza: los vértices del último tercio del largo; su eje es la dirección de mayor extensión
        head_vs = [v for v, t in zip(vs, ts) if t > far - 1.2 * self.u]
        c = sum(head_vs, Vector()) / len(head_vs)
        ext = max(head_vs, key=lambda v: ((v - c) - haft0 * (v - c).dot(haft0)).length)
        face0 = (ext - c) - haft0 * (ext - c).dot(haft0)
        face0.normalize()
        F0 = basis_yz(haft0, face0)
        g1, g2 = (self.head(n) for n in w["grips"])
        tips = sorted(vs, key=lambda v: (v - base).dot(haft0))
        return dict(kind="club", K=F0.transposed() @ RB0, base_local=Vector(), grips=[(g - base).dot(haft0) / self.u for g in (g1, g2)],
                    head_center=(c - base).dot(haft0) / self.u, head_radius=max(((v - c) - haft0 * (v - c).dot(haft0)).length for v in head_vs) / self.u,
                    butt=(tips[0] - base).dot(haft0) / self.u, top=(tips[-1] - base).dot(haft0) / self.u)

    def sample_kidnapper(self):
        """Pose (espacio de armadura) de los huesos del ninja del secuestro en el cuadro pedido de la toma del equipo."""
        kd = self.spec["kidnapper"]
        arm = self.arm
        acts = [a for a in bpy.data.actions]
        if not acts:
            return {}
        import charlib as C
        C.use_action(arm, acts[0])
        bpy.context.scene.frame_set(kd["take_frame"])
        bpy.context.view_layer.update()
        out = {pb.name: pb.matrix.copy() for pb in arm.pose.bones if pb.name.endswith(kd["suffix"])}
        return out

    def report(self):
        r = {k: [round(x, 3) for x in v] if isinstance(v, Vector) else v for k, v in self.land.items()}
        r["u"] = round(self.u, 4)
        r["leg_len"] = {k: round(v, 3) for k, v in self.leg_len.items()}
        r["arm_len"] = {k: round(v, 3) for k, v in self.arm_len.items()}
        if self.weapon_info:
            r["weapon"] = {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v] if isinstance(v, list) else None)
                           for k, v in self.weapon_info.items() if isinstance(v, (float, list))}
        return r


# =============================================================================== resolución de controles
class TeamSolver:
    """Traduce los controles de un cuadro (marco de autoría) a la pose de todos los huesos del personaje.

    Controles (todos opcionales; lo que falta queda en reposo):
      hips (m, desde el reposo), hips_rot, spine, chest, head, clav_r/l (grados)
      foot_r/l (tobillo, m absolutos), foot_r/l_rot (grados sobre el pie de reposo), knee_r/l (dirección)
      hand_r/l (muñeca, m absolutos), hand_r/l_dir (hacia dónde apuntan los dedos), hand_r/l_palm (normal
      de la palma), elbow_r/l (dirección), fist_r/l (0 abierta .. 1 puño)
      katana: grip (punto del mango en el puño), blade, edge (direcciones); grip_l > 0 lleva la izquierda al mango
      martillo: grip (mano derecha en el mango), haft (del extremo a la cabeza), face (cara de la cabeza que
      golpea), grip_l (0..1 la izquierda en el mango), slide_r/l (dónde agarra cada mano, m desde Agarre2/Agarre1)
      travel (m que avanzó el transform del juego: lo apoyado en el mundo se corre para atrás), breath (0..1)
      extra {hueso: grados} para lo que no tiene control propio."""

    def __init__(self, ch):
        self.ch = ch
        self.rig = ch.rig
        self.misses = {}
        self.hip_drop = 0.0

    # ---------------------------------------------------------------- piezas
    def hand_frame(self, k, d, palm):
        hi = self.ch.hand_info[k]
        fd = self.ch.D(d)
        n = self.ch.D(palm)
        n = (n - fd * n.dot(fd)).normalized()
        lat = n.cross(fd) * hi["chi"]
        M = Matrix((fd, lat, n)).transposed()
        return M @ hi["M0"].transposed() @ hi["Rh0"]

    def grip_frame(self, k, haft_arm, shoulder_arm, stick_pt):
        """Mano cerrada sobre un mango: los nudillos cruzan el palo apuntando lejos del hombro, el índice hacia la
        cabeza del arma."""
        hi = self.ch.hand_info[k]
        hv = haft_arm.normalized()
        fd = stick_pt - shoulder_arm
        fd = fd - hv * fd.dot(hv)
        if fd.length < 1e-5:
            fd = hv.orthogonal()
        fd.normalize()
        lat = hv
        n = lat.cross(fd) * hi["chi"]
        M = Matrix((fd, lat, n.normalized())).transposed()
        Rh = M @ hi["M0"].transposed() @ hi["Rh0"]
        wrist = stick_pt - Rh @ (hi["fist"] - Vector())     # fist está en el espacio de la mano (origen en la muñeca)
        return compose(wrist, Rh)

    def place_hand(self, pose, k, H, pole_c):
        """Ubica brazo y mano: el IK lleva la punta del antebrazo adonde la mano la espera."""
        ch, R = self.ch, self.rig
        d = ch.side[k]
        hi = ch.hand_info[k]
        tgt = H @ hi["fore_tail_local"]
        self.reach_with_clavicle(pose, k, tgt)
        miss = pose.two_bone(d["upper"], d["fore"], tgt, ch.D(pole_c))
        # la mano queda donde se pidió (si el brazo no llegó, se despega lo que faltó: lo mide 'miss')
        if d["hand_ctrl"]:
            pose.place(d["hand_ctrl"], H @ R.rel[d["hand"]].inverted())
        pose.place(d["hand"], H)
        return miss

    def reach_with_clavicle(self, pose, k, target, max_deg=20.0):
        """Si la muñeca no llega, la clavícula gira hacia el objetivo (la escápula al estirarse)."""
        R = self.rig
        d = self.ch.side[k]
        cl, ua, fa = d["clav"], d["upper"], d["fore"]
        reach = (R.length[ua] + R.length[fa]) * 0.985
        for _ in range(2):
            sh = (pose.get(cl) @ R.rel[ua]).translation
            ex = (V(target) - sh).length - reach
            if ex <= 0.0:
                return
            c0 = pose.head(cl)
            a, b = sh - c0, V(target) - c0
            ax = a.cross(b)
            if ax.length < 1e-6:
                return
            ang = min(ex / max(a.length, 1e-3), math.radians(max_deg))
            M = pose.get(cl)
            pose.place(cl, compose(c0, Quaternion(ax.normalized(), ang).to_matrix() @ rot3(M)))

    def curl(self, pose, k, amount):
        if amount <= 1e-4:
            return
        R = self.rig
        for b, (ax, ang) in self.ch.hand_info[k]["curl"].items():
            p = R.parent[b]
            Wb = pose.get(p) @ R.rel[b] @ Matrix.Rotation(ang * amount, 4, ax)
            pose.place(b, Wb)

    # ---------------------------------------------------------------- cuadro completo
    def solve(self, pose, c):
        ch, R = self.ch, self.rig
        sp = ch.spec
        g = lambda k, dflt=None: c.get(k) if c.get(k) is not None else dflt
        travel = g("travel", 0.0)
        # lo clavado en el mundo (pies) se autora en el mundo: en el clip se corre lo que avanzó el transform
        sh = Vector((0.0, travel, 0.0))
        # ---- cadera
        prest = R.rest[sp["pelvis"]]
        Hm = compose(prest.translation + ch.offset_arm(g("hips", (0, 0, 0))),
                     ch.Q(g("hips_rot", (0, 0, 0))).to_matrix() @ rot3(prest))
        feet = {}
        for k in "rl":
            d = ch.side[k]
            fi = ch.foot_info[k]
            ank = g("foot_" + k)
            if ank is None:
                ank = ch.land["ankle_" + k]
            fr = g("foot_%s_rot" % k, (0, 0, 0))
            Rf = ch.Q(fr).to_matrix() @ fi["Rf0"]
            F = compose(ch.P(V(ank) + sh), Rf)
            feet[k] = F
        drop = 0.0
        if g("auto_drop", 1.0) > 0.5:
            for k in "rl":
                d = ch.side[k]
                J = (Hm @ R.rel[d["thigh"]]).translation
                A_ = feet[k] @ ch.foot_info[k]["shin_tail_local"]
                reach = (R.length[d["thigh"]] + R.length[d["shin"]]) * 0.985
                dxy = Vector((J.x - A_.x, J.y - A_.y, J.z - A_.z))
                # la caída se mide en el eje 'arriba' del personaje (Z del mundo; las armaduras no están giradas)
                hor = Vector((dxy.x, dxy.y, 0.0)).length
                if hor < reach:
                    need = dxy.z - math.sqrt(reach * reach - hor * hor)
                    drop = max(drop, need)
        if drop > 0.0:
            Hm.translation.z -= drop
        self.hip_drop = drop / ch.u
        pose.place(sp["pelvis"], Hm)
        # ---- tronco y cabeza
        br = g("breath", 0.0)
        qs = ch.Q(V(g("spine", (0, 0, 0))))
        qc = ch.Q(V(g("chest", (0, 0, 0))) + Vector((-2.0 * br, 0.0, 0.0)))
        if sp["chest"]:
            pose.delta(sp["spine"][0], qs)
            pose.delta(sp["chest"][0], qc)
        else:
            pose.delta(sp["spine"][0], qc @ qs)
        pose.delta(sp["head"], ch.Q(V(g("head", (0, 0, 0))) + Vector((1.2 * br, 0.0, 0.0))))
        for k in "rl":
            sgn = -1.0 if k == "r" else 1.0
            pose.delta(ch.side[k]["clav"], ch.Q(V(g("clav_" + k, (0, 0, 0))) + Vector((0.0, sgn * 1.4 * br, 0.0))))
        # ---- brazos
        misses = {}
        w = ch.weapon_info
        hands = {}
        if w and w["kind"] == "katana":
            k = w["hand"]
            blade, edge = ch.D(g("blade", (0, -1, 0.3))), ch.D(g("edge", (0, -0.3, -1)))
            Fk = basis_yz(blade, edge - blade * edge.dot(blade))
            Rh = Fk @ w["K"]
            grip = ch.P(g("grip", ch.land["wrist_" + k]))
            hands[k] = compose(grip - Rh @ w["grip_local"], Rh)
        elif w and w["kind"] == "club":
            haft = ch.D(g("haft", (0, 0, 1)))
            face = ch.D(g("face", (0, -1, 0)))
            face = (face - haft * face.dot(haft)).normalized()
            RB = basis_yz(haft, face) @ w["K"]
            # 'grip' es la mano derecha; la base del mango queda 'slide_r' más abajo de Agarre2
            grip_r = ch.P(g("grip", (0, -0.6, 1.4)))
            t_r = w["grips"][1] - g("slide_r", 0.0)
            base = grip_r - haft * (t_r * ch.u)
            pose.place(sp["weapon"]["bone"], compose(base, RB))
            self.club = (base, haft, face)
            sh_r = (pose.get(ch.side["r"]["clav"]) @ R.rel[ch.side["r"]["upper"]]).translation
            hands["r"] = self.grip_frame("r", haft, sh_r, grip_r)
            gl = g("grip_l", 1.0)
            if gl > 1e-3:
                t_l = w["grips"][0] + g("slide_l", 0.0)
                stick = base + haft * (t_l * ch.u)
                sh_l = (pose.get(ch.side["l"]["clav"]) @ R.rel[ch.side["l"]["upper"]]).translation
                Hg = self.grip_frame("l", haft, sh_l, stick)
                if gl < 0.999:
                    Hf = self.free_hand(c, "l")
                    hands["l"] = compose(Hf.translation.lerp(Hg.translation, gl),
                                         Hf.to_quaternion().slerp(Hg.to_quaternion(), gl).to_matrix())
                else:
                    hands["l"] = Hg
        for k in "rl":
            if k not in hands:
                hands[k] = self.free_hand(c, k)
        if w and w["kind"] == "katana":
            gl = g("grip_l", 0.0)
            if gl > 1e-3:
                Hg = self.katana_left(hands[w["hand"]])
                Hf = hands["l"]
                hands["l"] = compose(Hf.translation.lerp(Hg.translation, gl), Hf.to_quaternion().slerp(Hg.to_quaternion(), gl).to_matrix())
        for k in "rl":
            dflt = (-0.3, 0.6, -0.4) if k == "r" else (0.3, 0.6, -0.4)
            misses["hand_" + k] = self.place_hand(pose, k, hands[k], g("elbow_" + k, dflt))
            self.curl(pose, k, g("fist_" + k, 1.0 if (w and (w["kind"] == "club" or w.get("hand") == k)) else 0.0))
        # ---- piernas
        ml = 0.0
        for k in "rl":
            d = ch.side[k]
            F = feet[k]
            tgt = F @ ch.foot_info[k]["shin_tail_local"]
            ml = max(ml, pose.two_bone(d["thigh"], d["shin"], tgt, ch.D(g("knee_" + k, (0, -1, 0)))))
            if d["foot_ctrl"]:
                pose.place(d["foot_ctrl"], F @ R.rel[d["foot"]].inverted())
            pose.place(d["foot"], F)
        misses["legs"] = ml
        # ---- huesos que siguen rígidos a otro (polos que pesan vértices)
        for b, t in sp["follow"].items():
            if b in R.rest:
                pose.place(b, pose.get(t) @ R.rest_inv[t] @ R.rest[b])
        for b, M in ch.kid_pose.items():
            pose.place(b, M)
        for bn, r in sorted((g("extra", {}) or {}).items(), key=lambda kv: R.names.index(kv[0])):
            pose.delta(bn, ch.Q(V(r)))
        self.misses = misses
        return misses

    def free_hand(self, c, k):
        """Mano libre: muñeca en 'hand_k'; sin dirección ni palma queda con la orientación de reposo."""
        ch = self.ch
        pos = c.get("hand_" + k)
        if pos is None:
            pos = ch.land["wrist_" + k]
        d, n = c.get("hand_%s_dir" % k), c.get("hand_%s_palm" % k)
        if d is None and n is None:
            return compose(ch.P(pos), ch.hand_info[k]["Rh0"])
        hi = ch.hand_info[k]
        if d is None:
            d = ch.Dc(hi["M0"].col[0])
        if n is None:
            n = ch.Dc(hi["M0"].col[2])
        return compose(ch.P(pos), self.hand_frame(k, d, n))

    def katana_left(self, Hr):
        """Mano izquierda en el mango: espejo de la derecha respecto del plano de la hoja, más cerca del pomo."""
        ch = self.ch
        w = ch.weapon_info
        k = w["hand"]
        grip = Hr @ w["grip_local"]
        Rr = rot3(Hr)
        Fk = Rr @ w["K"].transposed()
        blade = Fk.col[1]
        X = Fk.col[0]
        S = Matrix.Identity(3) - 2.0 * Matrix(((X.x * X.x, X.x * X.y, X.x * X.z), (X.y * X.x, X.y * X.y, X.y * X.z), (X.z * X.x, X.z * X.y, X.z * X.z)))
        hl, hr = ch.hand_info["l"], ch.hand_info[k]
        # la izquierda es la derecha reflejada: su marco (dedo, índice, palma) es el reflejo del de la derecha
        Mr = Rr @ hr["Rh0"].transposed() @ hr["M0"]
        Ml = S @ Mr
        Ml = Matrix((Ml.col[0], Ml.col[1], Ml.col[2])).transposed()
        if Ml.determinant() < 0:
            Ml = Matrix((Ml.col[0], Ml.col[1], -Ml.col[2])).transposed()
        Rl = Ml @ hl["M0"].transposed() @ hl["Rh0"]
        g_l = grip - blade * (0.11 * ch.u)
        fist = hl["fist"]
        return compose(g_l - Rl @ fist, Rl)


# =============================================================================== pasos
class FootKey:
    """Un pie en el piso del mundo en el cuadro 'frame': (x, y) del tobillo con el pie plano, punta girada 'yaw',
    'pitch' > 0 talón arriba (rueda sobre la punta) / < 0 punta arriba (sobre el talón), 'z' lo despega entero.
    El tramo que TERMINA acá usa 'ease' (inout: sale y llega quieto en el mundo, sin patinar) y, si el pie se
    traslada, sube en arco 'lift' m (por defecto un tercio de lo que recorre, hasta 8 cm): nunca se arrastra."""

    def __init__(self, frame, x, y, yaw=0.0, pitch=0.0, z=0.0, roll=0.0, ease="inout", lift=None):
        self.frame, self.x, self.y, self.yaw, self.pitch, self.z, self.roll = frame, x, y, yaw, pitch, z, roll
        self.ease, self.lift = ease, lift


def sample_feet(ch, k, track, f):
    ks = track
    if f <= ks[0].frame:
        a = b = ks[0]
        s = u = 0.0
    elif f >= ks[-1].frame:
        a = b = ks[-1]
        s = u = 1.0
    else:
        i = max(j for j in range(len(ks) - 1) if ks[j].frame <= f)
        a, b = ks[i], ks[i + 1]
        u = (f - a.frame) / max(1e-6, b.frame - a.frame)
        s = NA.ease(b.ease, u)
    lerp = lambda p, q: p + (q - p) * s
    d = math.hypot(b.x - a.x, b.y - a.y)
    lift = b.lift if b.lift is not None else (min(0.08, d / 3.0) if d > 0.01 else 0.0)
    # el arco va con el tiempo, no con la curva: con 'out' el pie llega adelante enseguida y baja vertical (no roza)
    z = lerp(a.z, b.z) + lift * math.sin(math.pi * u)
    return ch.foot_at(k, lerp(a.x, b.x), lerp(a.y, b.y), lerp(a.yaw, b.yaw), lerp(a.pitch, b.pitch), lerp(a.roll, b.roll), z)


def gait2(ch, frames, speed, duty, feet, lift=0.08, toe_off=30.0, heel=-14.0, phase_l=0.5, swing_ease="inout"):
    """Ciclo de locomoción en el lugar (el transform del juego avanza 'speed' m/s) con los pies clavados en el MUNDO:
    el apoyado no se mueve (en el clip va para atrás exactamente a la velocidad del suelo), apoya de talón y rueda
    hasta quedar plano, despega rodando sobre la punta, y el vuelo va de un apoyo al siguiente saliendo y llegando
    quieto en el mundo (sin el resbalón del pie que aterriza todavía yendo para adelante).
    feet = {k: (x, y medio del apoyo, yaw)}. Devuelve fn(f) -> {foot_k, foot_k_rot}."""
    T = frames / FPS
    stride = speed * T

    def one(k, f):
        x, ym, yaw = feet[k]
        p = ((f / frames) + (phase_l if k == "l" else 0.0)) % 1.0
        if p < duty:
            y = ym + stride * (p - duty * 0.5)
            hs, to = 0.14 * duty, 0.62 * duty
            if p < hs:
                pitch = heel * (1.0 - NA.ease("out2", p / hs))
            elif p > to:
                pitch = toe_off * NA.ease("in2", (p - to) / (duty - to))
            else:
                pitch = 0.0
            return ch.foot_at(k, x, y, yaw, pitch)
        q = (p - duty) / (1.0 - duty)
        s = NA.ease(swing_ease, q)
        y0 = ym + stride * duty * 0.5
        y = y0 + speed * T * (1.0 - duty) * q - stride * s
        z = lift * math.sin(math.pi * q) ** 0.8
        pitch = toe_off * (1.0 - s) + heel * s
        return ch.foot_at(k, x, y, yaw, pitch, 0.0, z)

    def fn(f):
        out = {}
        for k in "rl":
            out["foot_" + k], out["foot_%s_rot" % k] = one(k, f)
        return out
    return fn


# =============================================================================== horneado
def bake(ch, clip, solver):
    """Resuelve todos los cuadros: (poses W, controles, desplazamiento del transform del juego en la armadura,
    caída automática de cadera por cuadro, faltas de alcance)."""
    frames, ctrls, roots, drops, misses = [], [], [], [], []
    clip.ch = ch
    for f in range(clip.frames + 1):
        c = clip.controls(f)
        pose = NA.Pose(ch.rig)
        m = solver.solve(pose, c)
        for n in ch.rig.names:
            pose.get(n)
        frames.append(pose.W)
        ctrls.append(c)
        roots.append(ch.offset_arm((0.0, -(c.get("travel") or 0.0), 0.0)) + ch.offset_arm(clip.root_vel * (f / FPS)))
        drops.append(solver.hip_drop)
        misses.append(dict(m))
    if clip.loop:
        frames[-1] = {n: M.copy() for n, M in frames[0].items()}
    return frames, ctrls, roots, drops, misses


# =============================================================================== clips
class TeamClip(NA.Clip):
    """Clip de pose a pose con lo que piden los golpes del juego:
      * 'travel' sale del reloj real del golpe (lunge_travel): el transform del juego avanza AttackDef.lunge
        entre la suelta y el golpe; los pies se autoran en el mundo y quedan clavados aunque el cuerpo avance;
      * pausas que se mueven ('tremble'): en los cuadros de 'hold' la mano del arma tiembla 0.5-1 cm, nunca
        una pose muerta (ANIM-02);
      * timing: apex (fin de la pausa: la pose de máxima carga), contact (= activeStart), active, hold,
        kind (light/heavy/unblockable), lunge, windup del juego para medir con StepTimeline."""

    def __init__(self, name, frames, keys, loop=False, timing=None, lag=None, notes="", root_vel=(0, 0, 0),
                 travel=None, tremble=0.006, feet=None):
        super().__init__(name, frames, keys, loop=loop, lag=lag, timing=timing, notes=notes, root_vel=root_vel)
        self.travel_table = travel
        self.tremble = tremble
        # pasos: {k: [FootKey...]} en el piso del mundo (antes del avance del golpe); mandan sobre foot_k de las claves
        self.feet = feet or {}
        self.ch = None

    # canales propios de los personajes del equipo que no son posiciones (nindo_anim no los conoce)
    SCALARS = ("fist_r", "fist_l", "grip_l", "slide_r", "slide_l", "auto_drop")
    DIRS = ("hand_r_palm", "hand_l_palm", "haft", "face")

    def sample(self, f, channel):
        if channel not in self.SCALARS and channel not in self.DIRS:
            return super().sample(f, channel)
        ks = self.keys
        f = max(0.0, min(float(self.frames), f))
        i = self._seg(f)
        a, b = ks[i], ks[i + 1]
        s = NA.ease(b.ease_ch.get(channel, b.ease), (f - a.frame) / max(1e-6, b.frame - a.frame))
        va, vb = a.ctrl.get(channel), b.ctrl.get(channel)
        if va is None and vb is None:
            return None
        va = vb if va is None else va
        vb = va if vb is None else vb
        if channel in self.SCALARS:
            return va + (vb - va) * s
        return NA.slerp_dir(va, vb, s)

    def controls(self, f):
        c = super().controls(f)
        for k, track in self.feet.items():
            c["foot_" + k], c["foot_%s_rot" % k] = sample_feet(self.ch, k, track, f)
        if self.travel_table is not None:
            i = max(0, min(len(self.travel_table) - 1, int(round(f))))
            c["travel"] = self.travel_table[i]
        h = self.timing.get("hold")
        if h and self.tremble > 0 and h[0] <= f <= h[1]:
            w = math.sin(math.pi * (f - h[0]) / max(1, h[1] - h[0]))       # entra y sale de la pausa sin salto
            tr = Vector((math.sin(f * 2.7), math.cos(f * 3.3), math.sin(f * 4.1 + 1.0))) * (self.tremble * w)
            for k in ("grip", "hand_r", "hand_l"):
                if c.get(k) is not None:
                    c[k] = V(c[k]) + tr
        return c


def lunge_travel(frames, apex, contact, lunge, windup_min, speed=1.0, release_rate=1.6, hz=240.0):
    """Cuánto avanzó el transform del juego (m) en cada cuadro del clip durante un golpe con embestida, con el
    mismo reloj que Enemy.BeginStep/TickAttack: el avance va de la suelta (apex) a T + 0.05 * largo del paso a
    velocidad constante (y nunca a más de 12 m/s). Supone que Kaito no lo frena (con Kaito pegado avanza menos y
    el pie de atrás patina: es el caso raro)."""
    tl = NA.StepTimeline(frames, apex, contact, release_rate=release_rate, windup_min=windup_min, speed=speed)
    T = tl.T
    end = T + 0.05 * tl.step_len
    release = tl.tA + tl.hold
    start = max(0.0, end - max(end - release, lunge / 12.0))
    samples = []
    t = 0.0
    while True:
        n = min(1.0, tl.norm_at(t))
        tr = 0.0 if t <= start else lunge * min(1.0, (t - start) / max(1e-4, end - start))
        samples.append((n * frames, tr))
        if n >= 1.0:
            break
        t += 1.0 / hz
    out = []
    j = 0
    for f in range(frames + 1):
        while j + 1 < len(samples) and samples[j + 1][0] <= f:
            j += 1
        out.append(round(samples[j][1], 4))
    return out, tl


def gait(frames, speed, duty, feet, sole_z, lift=0.08, toe_off=25.0, heel=-12.0, phase_l=0.5):
    """Trayectorias de pies de un ciclo de locomoción en el lugar (el transform del juego avanza 'speed' m/s):
    durante el apoyo el pie va para atrás exactamente a la velocidad del suelo (clavado en el mundo), en el
    vuelo vuelve adelante en arco, despega en punta y apoya de talón. feet = {k: (x, y_medio)}.
    Devuelve fn(f) -> {foot_k, foot_k_rot} y la fase de apoyo (0..1) por pie."""
    T = frames / FPS
    span = speed * T * duty

    def foot(k, f):
        x, ym = feet[k]
        p = ((f / frames) + (phase_l if k == "l" else 0.0)) % 1.0
        if p < duty:
            y = ym - span * 0.5 + span * (p / duty)
            # el pie apoyado se despega del talón al final del apoyo (rueda sobre la punta)
            roll = max(0.0, (p / duty - 0.75) / 0.25)
            return Vector((x, y, sole_z + 0.01 * roll)), (toe_off * 0.6 * roll * roll, 0.0, 0.0), p
        q = (p - duty) / (1.0 - duty)
        s = 0.5 - 0.5 * math.cos(math.pi * q)
        y = ym + span * 0.5 - span * s
        z = sole_z + lift * math.sin(math.pi * min(1.0, q * 1.1)) ** 0.8
        pitch = toe_off * (1.0 - q) ** 2 * (q < 0.5) + heel * max(0.0, (q - 0.6) / 0.4) ** 1.5
        return Vector((x, y, z)), (pitch, 0.0, 0.0), p

    return foot
