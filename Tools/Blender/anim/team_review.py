"""Hojas de revisión de los clips del equipo: cómo se ven EN EL JUEGO (cámara 52°/24 m/FOV 30 a la densidad
de una pantalla 1080p, luz de luna en Gamma, niebla, negros levantados como CharacterFactory.LiftBlacks) y de
perfil para juzgar la pose. Kaito (1.5 m) está al lado como escala y como objetivo del golpe.
"""
import bpy, math, os, json
from mathutils import Vector, Matrix, Euler
from bpy_extras.object_utils import world_to_camera_view
import nindo_anim as NA

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
KAITO_FBX = os.path.join(REPO, "Nindo", "Assets", "Animations teo", "kaitooo.fbx")
BLACK_FLOOR = 0.13


def base_color(m):
    """Color plano del material del equipo (Principled del importador FBX) y su emisión."""
    col, emi = tuple(m.diffuse_color[:3]), (0.0, 0.0, 0.0)
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                col = tuple(n.inputs["Base Color"].default_value[:3])
                e = n.inputs.get("Emission Color")
                s = n.inputs.get("Emission Strength")
                if e is not None and s is not None and s.default_value > 0:
                    emi = tuple(c * s.default_value for c in e.default_value[:3])
    return col, emi


class Review:
    def __init__(self, ch, out_dir, kaito=True):
        self.ch = ch
        self.out = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.scn = NA.setup_review_scene((1920, 1080))
        self.look = NA.GameLook()
        self.cam = NA.camera(self.scn)
        done = {}
        for o in ch.meshes:
            for s in o.material_slots:
                m = s.material
                if m is None:
                    continue
                if m.name not in done:
                    c, e = base_color(m)
                    mx = max(c)
                    if mx < BLACK_FLOOR:
                        c = tuple(x / mx * BLACK_FLOOR for x in c) if mx > 0.005 else (0.11, 0.115, 0.13)
                    done[m.name] = self.look.build("rv_" + m.name, albedo_rgb=c, emission_rgb=e)
                s.material = done[m.name]
        # el kidnapper del FBX del abuelo no se ve en el NPC 'grandpa'
        for o in ch.meshes:
            if ch.name == "grandpa" and o.name.startswith("Cube"):
                o.hide_render = True
        # pivote: el personaje en metros, parado en el origen y mirando a -Y del mundo (hacia la cámara del juego)
        self.piv = bpy.data.objects.new("CharPivot", None)
        self.scn.collection.objects.link(self.piv)
        ch.arm.parent = self.piv
        ch.arm.matrix_parent_inverse = Matrix.Diagonal((1.0 / ch.u, 1.0 / ch.u, 1.0 / ch.u, 1.0)) @ ch.Rcw.transposed().to_4x4() @ Matrix.Translation(-ch.O)
        self.face(0.0)
        bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
        self.ground = bpy.context.active_object
        self.ground.data.materials.append(self.look.build("rv_ground", albedo_rgb=(0.32, 0.34, 0.3)))
        self.kaito = self.import_kaito() if kaito and os.path.exists(KAITO_FBX) else None

    def face(self, yaw_deg, travel=Vector()):
        """yaw 0 = el personaje mira a -Y (a la cámara del juego); 90 = mira a +X (perfil a la derecha)."""
        R = Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
        self.piv.matrix_world = Matrix.Translation(R.to_3x3() @ travel) @ R
        self.yaw = yaw_deg

    def import_kaito(self):
        before = set(bpy.data.objects)
        acts_before = set(bpy.data.actions)
        bpy.ops.import_scene.fbx(filepath=KAITO_FBX)
        new = [o for o in bpy.data.objects if o not in before]
        arm = next(o for o in new if o.type == 'ARMATURE')
        meshes = [o for o in new if o.type == 'MESH']
        act = next((a for a in bpy.data.actions if a not in acts_before and a.name.endswith("|Idle")), None)
        if act:
            arm.animation_data_create()
            arm.animation_data.action = act
            try:
                if arm.animation_data.action_slot is None and len(act.slots):
                    arm.animation_data.action_slot = act.slots[0]
            except AttributeError:
                pass
        dg = bpy.context.evaluated_depsgraph_get()
        zs = []
        for o in meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            zs += [(oe.matrix_world @ v.co).z for v in me.vertices]
            oe.to_mesh_clear()
        s = 1.5 / (max(zs) - min(zs))
        piv = bpy.data.objects.new("KaitoPivot", None)
        self.scn.collection.objects.link(piv)
        for o in new:
            if o.parent is None:
                o.parent = piv
        piv.scale = (s, s, s)
        self.kaito_z0 = -min(zs) * s
        for o in meshes:
            for sl in o.material_slots:
                m = sl.material
                if m is None:
                    continue
                c, e = base_color(m)
                mx = max(c)
                if mx < BLACK_FLOOR:
                    c = tuple(x / mx * BLACK_FLOOR for x in c) if mx > 0.005 else (0.11, 0.115, 0.13)
                sl.material = self.look.build("rv_k_" + m.name, albedo_rgb=c, emission_rgb=e)
        self.kaito_piv = piv
        self.kaito_meshes = meshes
        return piv

    def place_kaito(self, dist):
        """Kaito a 'dist' m delante del personaje, mirándolo (de espaldas a la cámara si el personaje la mira)."""
        if not self.kaito:
            return
        a = math.radians(self.yaw)
        fwd = Vector((math.sin(a), -math.cos(a), 0.0))       # frente del personaje en el mundo de revisión
        p = fwd * dist
        self.kaito_piv.location = (p.x, p.y, self.kaito_z0)
        # el FBX de Kaito mira a +X: girarlo para que mire al personaje (-fwd)
        look = -fwd
        self.kaito_piv.rotation_euler = (0, 0, math.atan2(look.y, look.x))

    def show_kaito(self, on):
        if self.kaito:
            for o in self.kaito_meshes:
                o.hide_render = not on

    # ------------------------------------------------------------------ encuadre
    def subject_points(self):
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in self.ch.meshes:
            if o.hide_render:
                continue
            oe = o.evaluated_get(dg)
            for c in oe.bound_box:
                pts.append(oe.matrix_world @ Vector(c))
        if self.kaito and not self.kaito_meshes[0].hide_render:
            k = self.kaito_piv.location
            pts += [Vector((k.x, k.y, 0.0)), Vector((k.x, k.y, 1.55))]
        return pts

    def render_framed(self, path, box=None, margin=0.03):
        scn = self.scn
        bpy.context.view_layer.update()
        if box is None:
            uv = [world_to_camera_view(scn, self.cam, p) for p in self.subject_points()]
            xs, ys = [u.x for u in uv], [u.y for u in uv]
            box = (max(0.0, min(xs) - margin), min(1.0, max(xs) + margin), max(0.0, min(ys) - margin), min(1.0, max(ys) + margin))
        scn.render.use_border = True
        scn.render.use_crop_to_border = True
        scn.render.border_min_x, scn.render.border_max_x, scn.render.border_min_y, scn.render.border_max_y = box
        NA.render(scn, path)
        scn.render.use_border = False
        return box

    def union_box(self, frames, setter, margin=0.03):
        """Caja de cámara que contiene al personaje en todos los cuadros (todas las celdas de una fila con la
        misma escala y encuadre: así se ve cuánto se mueve)."""
        lo_x, hi_x, lo_y, hi_y = 1, 0, 1, 0
        for f in frames:
            setter(f)
            bpy.context.view_layer.update()
            for p in self.subject_points():
                u = world_to_camera_view(self.scn, self.cam, p)
                lo_x, hi_x, lo_y, hi_y = min(lo_x, u.x), max(hi_x, u.x), min(lo_y, u.y), max(hi_y, u.y)
        return (max(0.0, lo_x - margin), min(1.0, hi_x + margin), max(0.0, lo_y - margin), min(1.0, hi_y + margin))

    def sheet(self, layout):
        p = os.path.join(self.out, "_layout.json")
        json.dump(layout, open(p, "w", encoding="utf-8"), indent=1)
        NA.compose_sheet(p)
        try:
            os.remove(p)
        except OSError:
            pass

    # ------------------------------------------------------------------ hoja de un clip
    def clip_sheet(self, clip, first, roots_m, frames, labels, kaito_dist=2.4, note=""):
        """Tres filas: cámara del juego con el personaje de frente (Kaito delante, de espaldas), cámara del juego
        de perfil (el golpe cruza la pantalla) y perfil ortográfico grande."""
        scn = self.scn
        rows = []
        tmp = []
        h = self.ch.spec["height"]
        for view, yaw in (("juego, de frente", 0.0), ("juego, de perfil", 90.0), ("perfil", 90.0)):
            # el perfil grande es para leer la pose: en el lugar (sin el avance), con la cámara quieta
            moving = view.startswith("juego")

            def setter(f, yaw=yaw, moving=moving):
                scn.frame_set(first + f)
                self.face(yaw, Vector((0.0, -roots_m[f], 0.0)) if moving else Vector())
            self.face(yaw)
            if view.startswith("juego"):
                self.show_kaito(True)
                self.place_kaito(kaito_dist)
                a = math.radians(yaw)
                mid = Vector((math.sin(a), -math.cos(a), 0.0)) * (kaito_dist * 0.5)
                NA.game_camera(self.cam, (mid.x, mid.y, 0.8), pitch=52.0, dist=24.0, fov=30.0)
                self.look.set_moon()
            else:
                self.show_kaito(False)
                NA.ortho_camera(self.cam, (0.0, 0.0, h * 0.55), h * 1.45, azimuth=0.0, elevation=8.0)
                self.look.set_moon(Vector((0.5, -0.7, 0.6)), scale=1.0)
            box = self.union_box(frames, setter)
            tiles = []
            for f, lab in zip(frames, labels):
                setter(f)
                p = os.path.join(self.out, f"_{clip.name}_{yaw:.0f}_{view[0]}_{f:03d}.png")
                self.render_framed(p, box)
                tiles.append({"img": p, "label": lab})
                tmp.append(p)
            rows.append({"label": view, "tiles": tiles})
        # 1:1: lo que ve el jugador en 1080p (cámara del juego, el personaje de frente, sin achicar): ~82 px por metro
        th = max(170, int(h * 82 + 46))
        self.show_kaito(False)
        self.look.set_moon()
        tiles = []
        for f, lab in zip(frames, labels):
            scn.frame_set(first + f)
            self.face(0.0, Vector((0.0, -roots_m[f], 0.0)))
            c = Vector((0.0, -roots_m[f], h * 0.5))
            NA.game_camera(self.cam, (c.x, c.y, 0.8), pitch=52.0, dist=24.0, fov=30.0)
            bpy.context.view_layer.update()
            u = world_to_camera_view(scn, self.cam, c)
            hw, hh = th * 0.55 / 1920.0, th * 0.5 / 1080.0
            box = (max(0.0, u.x - hw), min(1.0, u.x + hw), max(0.0, u.y - hh), min(1.0, u.y + hh))
            p = os.path.join(self.out, f"_{clip.name}_1to1_{f:03d}.png")
            self.render_framed(p, box)
            tiles.append({"img": p, "label": lab})
        rows.append({"label": "juego 1:1 (tamaño real en 1080p)", "tiles": tiles})
        self.face(0.0)
        out = os.path.join(self.out, f"{self.ch.name}_{clip.name}.png")
        self.sheet({"out": out, "title": f"{self.ch.name} · {clip.name} · {clip.frames} cuadros ({clip.frames / NA.FPS:.2f} s) {note}",
                    "width": 1280, "tile_h": th, "rows": rows, "delete": True})
        return out
