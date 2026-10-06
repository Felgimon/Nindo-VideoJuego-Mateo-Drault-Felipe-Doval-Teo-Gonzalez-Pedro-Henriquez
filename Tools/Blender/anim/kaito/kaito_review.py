"""Hojas de revisión de los clips de Kaito: cómo se ven EN EL JUEGO (cámara 52° / 24 m / FOV 30 a la densidad
real de píxeles de 1080p, luz de luna en Gamma, niebla) y de perfil (ortográfica, para leer arcos y pies).

Se usa después de exportar: cambia los materiales del modelo por los de revisión (GameLook).
"""
import math, os, json
import bpy
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view
import nindo_anim as NA
import kaito_rig as KR

BLACK_FLOOR = 0.13          # CharacterFactory.LiftBlacks: ningún material más oscuro que esto


class Review:
    def __init__(self, arm, meshes, out_dir):
        self.arm, self.meshes, self.out = arm, meshes, out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.arm_world0 = arm.matrix_world.copy()
        self.scn = NA.setup_review_scene((1920, 1080))
        self.look = NA.GameLook()
        self.cam = NA.camera(self.scn)
        done = {}
        for o in meshes:
            for sl in o.material_slots:
                m = sl.material
                if m is None:
                    continue
                if m.name not in done:
                    c = list(m.diffuse_color[:3])
                    mx = max(c)
                    if mx < BLACK_FLOOR:
                        c = [x / mx * BLACK_FLOOR for x in c] if mx > 0.005 else [0.85 * BLACK_FLOOR, 0.9 * BLACK_FLOOR, BLACK_FLOOR]
                    em = (0.6, 0.6, 0.6) if m.name == "OjoBrillo" else (0.3, 0.2, 0.03) if m.name == "AmarilloBandana" else (0, 0, 0)
                    done[m.name] = self.look.build("rv_" + m.name, albedo_rgb=tuple(c), emission_rgb=em)
                sl.material = done[m.name]
        bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
        self.ground = bpy.context.active_object
        self.ground.data.materials.append(self.look.build("rv_ground", albedo_rgb=(0.23, 0.27, 0.2)))
        # marcas en el piso cada 1 m (se lee el avance y si los pies patinan)
        self.marks = []
        for i in range(-6, 7):
            bpy.ops.mesh.primitive_plane_add(size=1, location=(0, i * KR.U_PER_M, 0.002))
            mk = bpy.context.active_object
            mk.scale = (40.0, 0.02, 1.0)
            mk.data.materials.append(self.look.build("rv_mark", albedo_rgb=(0.32, 0.36, 0.28)))
            self.marks.append(mk)

    # ------------------------------------------------------------------ pose en el mundo de revisión
    def place(self, frame, yaw_deg, root=Vector()):
        """El modelo en el cuadro 'frame' de la toma, mirando 'yaw_deg' (0 = de frente a la cámara del juego,
        90 = hacia la derecha de la pantalla), corrido por el avance de raíz del clip."""
        self.scn.frame_set(frame)
        Rz = Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
        self.arm.matrix_world = Matrix.Translation(Rz @ Vector(root)) @ Rz @ KR.TO_C
        bpy.context.view_layer.update()

    def restore(self):
        self.arm.matrix_world = self.arm_world0
        bpy.context.view_layer.update()

    def bounds_pts(self):
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in self.meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            M = oe.matrix_world
            vs = [M @ v.co for v in me.vertices]
            oe.to_mesh_clear()
            if vs:
                lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
                hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
                pts += [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        return pts

    def render_crop(self, path, pts, margin=0.08, min_px=(150, 170)):
        scn = self.scn
        uv = [world_to_camera_view(scn, self.cam, p) for p in pts]
        x0, x1 = min(u.x for u in uv), max(u.x for u in uv)
        y0, y1 = min(u.y for u in uv), max(u.y for u in uv)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w = max(x1 - x0 + 2 * margin * (x1 - x0), min_px[0] / scn.render.resolution_x)
        h = max(y1 - y0 + 2 * margin * (y1 - y0), min_px[1] / scn.render.resolution_y)
        scn.render.use_border = True
        scn.render.use_crop_to_border = True
        scn.render.border_min_x, scn.render.border_max_x = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
        scn.render.border_min_y, scn.render.border_max_y = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
        NA.render(scn, path)
        scn.render.use_border = False

    def game_view(self, path, focus):
        NA.game_camera(self.cam, focus, pitch=52.0, dist=24.0 * KR.U_PER_M, fov=30.0)
        self.render_crop(path, self.bounds_pts())

    def close_view(self, path, focus):
        """Mismo ángulo que el juego pero de cerca: para ver manos, pies y la hoja."""
        NA.game_camera(self.cam, focus, pitch=52.0, dist=9.0 * KR.U_PER_M, fov=30.0)
        self.render_crop(path, self.bounds_pts(), min_px=(380, 420))

    def side_view(self, path, center, scale=5.2):
        NA.ortho_camera(self.cam, center, scale, azimuth=90.0, elevation=4.0)
        self.render_crop(path, self.bounds_pts(), min_px=(300, 420))

    # ------------------------------------------------------------------ hoja de un clip
    def clip_sheet(self, clip, first, roots, frames, labels, report, gait=False):
        tiles = {"juego 52° / 24 m, de frente 3/4 (píxeles reales de 1080p)": [],
                 "juego, de espaldas 3/4": [], "ángulo del juego de cerca": [], "perfil": []}
        keys = list(tiles)
        for f, lab in zip(frames, labels):
            root = Vector() if gait else roots[f]
            spec = ((keys[0], 35.0, "g"), (keys[1], 215.0, "g"), (keys[2], 35.0, "c"), (keys[3], 0.0, "s"))
            for k, yaw, kind in spec:
                self.place(first + f, yaw, root)
                rz = Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Vector(root)
                focus = Vector((rz.x, rz.y, 1.3))
                p = os.path.join(self.out, f"_{clip.name}_{kind}{int(yaw)}_{f}.png")
                if kind == "g":
                    self.game_view(p, focus)
                elif kind == "c":
                    self.close_view(p, focus)
                else:
                    self.side_view(p, Vector((rz.x, rz.y, 1.3)))
                tiles[k].append({"img": p, "label": lab})
        self.restore()
        lay = {"out": os.path.join(self.out, f"kaito_{clip.name}.png"), "width": 1280, "tile_h": 190, "delete": True,
               "title": f"Kaito {clip.name}: {clip.frames} cuadros ({clip.frames / 30.0 / clip.timing.get('time_scale', 1.0):.2f} s)"
                        f"{'  loop' if clip.loop else ''}  "
                        f"{report.get('summary', '')}",
               "rows": [{"label": k, "tiles": v} for k, v in tiles.items()]}
        jp = os.path.join(self.out, f"_{clip.name}_layout.json")
        with open(jp, "w", encoding="utf-8") as fh:
            json.dump(lay, fh, ensure_ascii=False)
        NA.compose_sheet(jp)
        try:
            os.remove(jp)
        except OSError:
            pass
        return lay["out"]
