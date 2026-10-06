"""Renders de revisión de Kokuyō: cómo se ve EN EL JUEGO (cámara, luz de luna en Gamma, niebla)
y hojas de contacto por clip junto a Kaito (1.5 m, el modelo real del juego).

Se usa después de exportar: cambia los materiales de los objetos por los de revisión.
"""
import json, math, os
import bpy
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view
import nindo_anim as NA
import nindo_palette as P
import kokuyo_model as KM

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
KAITO_FBX = os.path.join(REPO, "Nindo", "Assets", "Animations teo", "kaitooo.fbx")
PALETTE_PNG = os.path.join(REPO, "Tools", "Blender", "out", "NindoPalette.png")
BLACK_FLOOR = 0.13          # CharacterFactory.BlackFloor


class Review:
    def __init__(self, arm, body, rigid, out_dir, kaito=True, res=(1920, 1080)):
        self.arm, self.body, self.rigid = arm, body, rigid
        self.out = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.scn = NA.setup_review_scene(res)
        self.look = NA.GameLook()
        self.cam = NA.camera(self.scn)
        img = bpy.data.images.load(PALETTE_PNG, check_existing=False)
        img.colorspace_settings.name = 'Non-Color'
        L = self.look
        hx = lambda n: P.hex_to_rgb(dict(P.PALETTE)[n])
        mats = {
            "Nindo_Palette": L.build("rv_palette", albedo_image=img),
            "Nindo_Emissive": L.build("rv_emissive", albedo_image=img, emission_rgb=KM.SEAM_RGB, emission_gain=1.5),
            "Kokuyo_Edge": L.build("rv_edge", albedo_rgb=KM.EDGE_BASE_RGB, emission_rgb=KM.SEAM_RGB, emission_gain=0.8),
            "Kokuyo_Seams": L.build("rv_seams", albedo_rgb=(0.35, 0.25, 0.5), emission_rgb=KM.SEAM_RGB, emission_gain=1.0),
            "Kokuyo_Ribbon": L.build("rv_ribbon", albedo_rgb=KM.BANDANA_RGB),
            "Kokuyo_MaskCrack": L.build("rv_maskcrack", albedo_rgb=hx("wood_red")),
        }
        for o in [body] + list(rigid.values()):
            for s in o.material_slots:
                if s.material and s.material.name in mats:
                    s.material = mats[s.material.name]
        # piso de patio de piedra clara (la arena del dojo)
        bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
        self.ground = bpy.context.active_object
        self.ground.data.materials.append(L.build("rv_ground", albedo_rgb=hx("stone")))
        self.kaito = self.import_kaito() if kaito else None

    # ------------------------------------------------------------------ Kaito de referencia
    def import_kaito(self):
        if not os.path.exists(KAITO_FBX):
            return None
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=KAITO_FBX)
        new = [o for o in bpy.data.objects if o not in before]
        arm = next(o for o in new if o.type == 'ARMATURE')
        meshes = [o for o in new if o.type == 'MESH']
        act = next((a for a in bpy.data.actions if a.name.endswith("|Idle")), None)
        if act:
            arm.animation_data_create()
            arm.animation_data.action = act
            try:
                if arm.animation_data.action_slot is None and len(act.slots):
                    arm.animation_data.action_slot = act.slots[0]
            except AttributeError:
                pass
        arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        zs = []
        for o in meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            zs += [(oe.matrix_world @ v.co).z for v in me.vertices]
            oe.to_mesh_clear()
        arm.data.pose_position = 'POSE'
        s = 1.5 / (max(zs) - min(zs))
        piv = bpy.data.objects.new("KaitoPivot", None)
        self.scn.collection.objects.link(piv)
        for o in new:
            if o.parent is None:
                o.parent = piv
        piv.scale = (s, s, s)
        self.kaito_z0 = -min(zs) * s
        # materiales del equipo con el piso de negros del juego (CharacterFactory.LiftBlacks)
        for o in meshes:
            for sl in o.material_slots:
                m = sl.material
                if m is None:
                    continue
                c = list(m.diffuse_color[:3])
                mx = max(c)
                if mx < BLACK_FLOOR:
                    c = [x / mx * BLACK_FLOOR for x in c] if mx > 0.005 else [0.85 * BLACK_FLOOR, 0.9 * BLACK_FLOOR, BLACK_FLOOR]
                sl.material = self.look.build("rv_k_" + m.name, albedo_rgb=tuple(c))
        self.kaito_piv = piv
        self.place_kaito((0, -4.6), 0.0)
        return piv

    def place_kaito(self, xy, face_deg):
        """face_deg 0 = Kaito mira a +Y (hacia el jefe, de espaldas a la cámara del juego)."""
        if getattr(self, "kaito_piv", None) is None:
            return
        self.kaito_piv.location = (xy[0], xy[1], self.kaito_z0)
        # el FBX del equipo mira a +X en Blender
        self.kaito_piv.rotation_euler = (0, 0, math.radians(90.0 + face_deg))

    def show_kaito(self, on):
        if getattr(self, "kaito_piv", None) is None:
            return
        for o in self.kaito_piv.children_recursive:
            o.hide_render = not on

    # ------------------------------------------------------------------ encuadre y render
    def subject_points(self):
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in [self.body] + list(self.rigid.values()):
            oe = o.evaluated_get(dg)
            for c in oe.bound_box:
                pts.append(oe.matrix_world @ Vector(c))
        return pts

    def render_framed(self, path, extra_pts=(), margin=0.06, min_size=(260, 260)):
        """Render con borde: solo la zona que ocupan el jefe (y Kaito), a la densidad real de píxeles
        de la pantalla del juego (1920x1080)."""
        scn = self.scn
        bpy.context.view_layer.update()
        pts = self.subject_points() + [Vector(p) for p in extra_pts]
        if getattr(self, "kaito_piv", None) and not self.kaito_piv.children[0].hide_render:
            k = self.kaito_piv.location
            pts += [Vector((k.x, k.y, 0.0)), Vector((k.x, k.y, 1.55))]
        uv = [world_to_camera_view(scn, self.cam, p) for p in pts]
        xs = [u.x for u in uv]
        ys = [u.y for u in uv]
        x0, x1 = max(0.0, min(xs) - margin), min(1.0, max(xs) + margin)
        y0, y1 = max(0.0, min(ys) - margin), min(1.0, max(ys) + margin)
        W, H = scn.render.resolution_x, scn.render.resolution_y
        if (x1 - x0) * W < min_size[0]:
            c = (x0 + x1) / 2; x0, x1 = max(0, c - min_size[0] / W / 2), min(1, c + min_size[0] / W / 2)
        if (y1 - y0) * H < min_size[1]:
            c = (y0 + y1) / 2; y0, y1 = max(0, c - min_size[1] / H / 2), min(1, c + min_size[1] / H / 2)
        scn.render.use_border = True
        scn.render.use_crop_to_border = True
        scn.render.border_min_x, scn.render.border_max_x = x0, x1
        scn.render.border_min_y, scn.render.border_max_y = y0, y1
        NA.render(scn, path)
        scn.render.use_border = False
        return path

    def render_full(self, path):
        self.scn.render.use_border = False
        NA.render(self.scn, path)
        return path

    def game_view(self, focus=(0, -2.3, 1.2), pitch=55.0, dist=30.0, fov=30.0, yaw=0.0):
        NA.game_camera(self.cam, focus, pitch, dist, fov, yaw)

    def ortho(self, center=(0, 0, 2.6), scale=6.8, azimuth=0.0, elevation=0.0):
        NA.ortho_camera(self.cam, center, scale, azimuth, elevation)

    def sheet(self, layout):
        p = os.path.join(self.out, "_layout.json")
        json.dump(layout, open(p, "w", encoding="utf-8"), indent=1)
        NA.compose_sheet(p)
        try:
            os.remove(p)
        except OSError:
            pass

    # ------------------------------------------------------------------ hojas
    def model_sheet(self, tag="model"):
        """Frente/perfil/espalda con luz de estudio (para juzgar el modelado) + la lectura del juego."""
        L = self.look
        tiles = []
        self.show_kaito(False)
        studio = Vector((-0.45, -0.7, 0.75))
        for az, name, sd in ((0, "frente", studio), (90, "perfil (izq.)", Vector((0.7, -0.3, 0.7))),
                             (180, "espalda", Vector((0.4, 0.75, 0.7))), (35, "3/4", studio)):
            L.set_moon(sd, scale=1.0)
            self.ortho((0, 0, 2.3), 5.6, az, 6)
            p = os.path.join(self.out, f"_{tag}_{az}.png")
            self.render_framed(p, margin=0.03)
            tiles.append({"img": p, "label": name + " (luz de estudio)"})
        row2 = []
        L.set_moon(None)
        self.show_kaito(True)
        self.place_kaito((0.6, -4.6), 0)
        self.game_view(pitch=55, dist=30)
        p = os.path.join(self.out, f"_{tag}_game55.png")
        self.render_framed(p)
        row2.append({"img": p, "label": "juego 55°/30 m, luna real (detrás del jefe)"})
        self.game_view(focus=(0, -2.3, 1.0), pitch=52, dist=24)
        p = os.path.join(self.out, f"_{tag}_game52.png")
        self.render_framed(p)
        row2.append({"img": p, "label": "juego 52°/24 m"})
        L.set_moon(None, fill_dir=Vector((0.2, -1.0, 0.25)), fill_rgb=(0.55, 0.32, 0.12))
        p = os.path.join(self.out, f"_{tag}_game55_brasero.png")
        self.game_view(pitch=55, dist=30)
        self.render_framed(p)
        row2.append({"img": p, "label": "con braseros (relleno cálido)"})
        L.set_moon(None)
        self.show_kaito(False)
        self.ortho((0, -0.25, 3.75), 1.9, 20, 10)
        L.set_moon(studio)
        p = os.path.join(self.out, f"_{tag}_head.png")
        self.render_full_square(p)
        row2.append({"img": p, "label": "cabeza"})
        # el rostro que queda al caer la máscara (final)
        self.rigid["Mask"].hide_render = True
        p = os.path.join(self.out, f"_{tag}_face.png")
        self.ortho((0, -0.25, 3.7), 1.2, 15, 4)
        self.render_full_square(p)
        self.rigid["Mask"].hide_render = False
        row2.append({"img": p, "label": "rostro (sin máscara)"})
        L.set_moon(None)
        out = os.path.join(self.out, f"{tag}_sheet.png")
        self.sheet({"out": out, "title": "Kokuyō - modelo", "width": 1280, "tile_h": 420, "delete": True,
                    "rows": [{"label": "modelo (ortográfica)", "tiles": tiles}, {"label": "lectura en el juego", "tiles": row2}]})
        return out

    def render_full_square(self, path, size=600):
        scn = self.scn
        rx, ry = scn.render.resolution_x, scn.render.resolution_y
        scn.render.resolution_x = scn.render.resolution_y = size
        self.render_full(path)
        scn.render.resolution_x, scn.render.resolution_y = rx, ry

    # ------------------------------------------------------------------ hoja de un clip
    def _border_from(self, pts, margin=0.04):
        scn = self.scn
        bpy.context.view_layer.update()        # la matriz de la cámara recién movida
        uv = [world_to_camera_view(scn, self.cam, p) for p in pts]
        x0, x1 = max(0.0, min(u.x for u in uv) - margin), min(1.0, max(u.x for u in uv) + margin)
        y0, y1 = max(0.0, min(u.y for u in uv) - margin), min(1.0, max(u.y for u in uv) + margin)
        return x0, x1, y0, y1

    def _render_border(self, path, b):
        scn = self.scn
        scn.render.use_border = True
        scn.render.use_crop_to_border = True
        scn.render.border_min_x, scn.render.border_max_x, scn.render.border_min_y, scn.render.border_max_y = b
        NA.render(scn, path)
        scn.render.use_border = False

    def clip_sheet(self, clip, start, roots, show, labels, report=None):
        """Dos filas con el MISMO encuadre en todos los cuadros (se ve el recorrido): la cámara del
        jefe (55°, +6 m) con Kaito a 4.6 m, y el perfil desde su derecha (el lado de la espada)."""
        scn = self.scn
        L = self.look
        rows = []
        views = [("juego, perfil del jefe 55°/30 m (luna del juego, de espaldas a ella)", "game"),
                 ("juego 52°/24 m (cámara normal)", "game52"), ("perfil (desde su derecha)", "side")]
        for title, kind in views:
            if kind in ("game", "game52"):
                L.set_moon(None)
                self.show_kaito(True)
                self.place_kaito((0.8, -4.6), 0)
                if kind == "game":
                    self.game_view(focus=(0, -2.3, 1.2), pitch=55, dist=30)
                else:
                    self.game_view(focus=(0, -2.3, 1.0), pitch=52, dist=24)
            else:
                L.set_moon(Vector((-0.8, -0.35, 0.6)))
                self.show_kaito(False)
            pts = []
            for f in show:
                scn.frame_set(start + f)
                self.arm.location = roots[f]
                bpy.context.view_layer.update()
                pts += self.subject_points()
            if kind == "side":
                ys = [p.y for p in pts]
                zs = [p.z for p in pts]
                cy, cz = (min(ys) + max(ys)) / 2, (max(zs) + min(0.0, min(zs))) / 2
                span = max(max(zs) - min(0.0, min(zs)), (max(ys) - min(ys)) * 1080 / 1920) + 0.6
                self.ortho((0, cy, cz), span, -90, 0)
            if kind in ("game", "game52"):
                k = self.kaito_piv.location
                pts += [Vector((k.x, k.y, 0.0)), Vector((k.x, k.y, 1.55))]
            b = self._border_from(pts)
            tiles = []
            for f, lab in zip(show, labels):
                scn.frame_set(start + f)
                self.arm.location = roots[f]
                p = os.path.join(self.out, f"_{clip.name}_{kind}_{f:03d}.png")
                self._render_border(p, b)
                tiles.append({"img": p, "label": lab})
            rows.append({"label": title, "tiles": tiles})
        self.arm.location = (0, 0, 0)
        L.set_moon(None)
        sub = ""
        if report:
            bits = []
            if "max_height_m" in report:
                bits.append(f"alto máx {report['max_height_m']} m")
            if "tip_peak_mps" in report:
                bits.append(f"punta pico {report['tip_peak_mps']} m/s, fuera del golpe {int(report['tip_outside_ratio'] * 100)} %")
            if "loop_seam_deg" in report:
                bits.append(f"costura {report['loop_seam_deg']}°")
            sub = "  |  " + ", ".join(bits)
        out = os.path.join(self.out, f"clip_{clip.name}.png")
        self.sheet({"out": out, "title": f"{clip.name}  ({clip.frames} cuadros, {clip.frames / NA.FPS:.2f} s){sub}", "width": 1280,
                    "tile_h": 200, "delete": True, "rows": rows})
        return out

    # ------------------------------------------------------------------ al lado del elenco del juego
    TEAM = [  # (fbx relativo a Assets, alto en el juego, hacia dónde mira en Blender: 0 = -Y, 90 = +X, 180 = +Y)
        ("Models/Ninja/Ninja 1.fbx", 1.7, 90.0),
        ("Characters/Sumo/luchadorsumo.fbx", 2.5, 180.0),
        ("Models/Minijefe.fbx", 3.2, 0.0),
    ]

    def import_team(self, rel, height, front_az, x):
        """Importa un personaje del equipo con las reglas de CharacterFactory (alto por bounds de reposo,
        negros levantados al piso de 0.13) mirando a la cámara."""
        path = os.path.join(REPO, "Nindo", "Assets", rel)
        if not os.path.exists(path):
            return None
        before, acts = set(bpy.data.objects), set(bpy.data.actions)
        bpy.ops.import_scene.fbx(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        arm = next((o for o in new if o.type == 'ARMATURE'), None)
        meshes = [o for o in new if o.type == 'MESH']
        if arm is not None:
            act = next((a for a in bpy.data.actions if a not in acts and a.name.endswith("|Idle")), None)
            if act:
                arm.animation_data_create()
                arm.animation_data.action = act
                try:
                    if arm.animation_data.action_slot is None and len(act.slots):
                        arm.animation_data.action_slot = act.slots[0]
                except AttributeError:
                    pass
            arm.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        zs = []
        for o in meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            zs += [(oe.matrix_world @ v.co).z for v in me.vertices]
            oe.to_mesh_clear()
        if arm is not None:
            arm.data.pose_position = 'POSE'
        s = height / (max(zs) - min(zs))
        piv = bpy.data.objects.new("TeamPivot", None)
        self.scn.collection.objects.link(piv)
        for o in new:
            if o.parent is None:
                o.parent = piv
        piv.scale = (s, s, s)
        piv.location = (x, -2.0, -min(zs) * s)
        piv.rotation_euler = (0, 0, math.radians(-front_az))
        for o in meshes:
            for sl in o.material_slots:
                m = sl.material
                if m is None:
                    continue
                c = list(m.diffuse_color[:3])
                mx = max(c)
                if mx < BLACK_FLOOR:
                    c = [v / mx * BLACK_FLOOR for v in c] if mx > 0.005 else [0.85 * BLACK_FLOOR, 0.9 * BLACK_FLOOR, BLACK_FLOOR]
                sl.material = self.look.build("rv_t_" + m.name, albedo_rgb=tuple(c))
        return piv

    def lineup_sheet(self, frame=1):
        """El elenco en fila con la cámara del juego: ¿se ve como el mismo juego? (Kaito 1.5 m, ninja,
        sumo, Gorō 3.2 m y Kokuyō 4.5 m)."""
        scn = self.scn
        scn.frame_set(frame)
        self.arm.location = (4.2, 0.4, 0.0)
        self.place_kaito((-5.6, -2.0), 180.0)
        self.show_kaito(True)
        x = -3.6
        for rel, h, az in self.TEAM:
            self.import_team(rel, h, az, x)
            x += 2.4 if h < 3 else 3.0
        L = self.look
        tiles = []
        for lab, fill in (("luna del juego", (0, 0, 0)), ("con braseros", (0.55, 0.32, 0.12))):
            L.set_moon(None, fill_dir=Vector((0.2, -1.0, 0.25)), fill_rgb=fill)
            self.game_view(focus=(0.0, -1.0, 1.4), pitch=52, dist=26)
            p = os.path.join(self.out, f"_lineup_{len(tiles)}.png")
            self.render_framed(p, margin=0.03)
            tiles.append({"img": p, "label": "cámara 52° - " + lab})
        L.set_moon(Vector((-0.45, -0.7, 0.75)))
        self.ortho((0.0, -1.0, 2.3), 5.2, 0, 4)
        p = os.path.join(self.out, "_lineup_front.png")
        self.render_framed(p, margin=0.02)
        tiles.append({"img": p, "label": "frente (luz de estudio)"})
        L.set_moon(None)
        out = os.path.join(self.out, "lineup_sheet.png")
        self.sheet({"out": out, "title": "Kokuyō junto al elenco: Kaito, ninja, sumo, Gorō", "width": 1280, "tile_h": 360,
                    "delete": True, "rows": [{"label": "", "tiles": tiles}]})
        self.arm.location = (0, 0, 0)
        return out
