"""Renders de control de los kits (Blender 4.4, EEVEE): luz de luna, cámara del juego y primeros planos.

Escala real: el armature se escala a la altura del juego (CHARS[...]['height']) y la cámara del juego es la de
CameraDirector (pitch 52°, 24 m, FOV vertical 30°). Las vistas "game" se renderizan con la misma densidad de
píxeles que el juego a 1080p (un personaje de 1.5 m mide ~100 px), y se amplían x3 sin filtrar para mirarlas.
"""
import bpy, os, math
from mathutils import Vector, Matrix
import kitlib as K

GAME_PITCH, GAME_DIST, GAME_FOV = 52.0, 24.0, 30.0


def s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexlin(h):
    h = h.lstrip("#")
    return tuple(s2l(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def body_height(ch):
    """Alto de la unión de las mallas del personaje en reposo (lo que mide NormalizeHeight)."""
    zs = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name.startswith("Acc_"):
            continue
        for v in o.data.vertices:
            zs.append((o.matrix_world @ v.co).z)
    return min(zs), max(zs)


def place(ch, loc=(0, 0, 0), yaw=0.0, scale_mul=1.0):
    """Escala el personaje a metros, pies en z=0, mirando a -Y del mundo (hacia la cámara del juego, que está al
    sur) girado 'yaw' grados."""
    arm = ch.arm
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    z0, z1 = body_height(ch)
    s = K.CHARS[ch.key]["height"] / (z1 - z0) * scale_mul
    f = ch.front
    face_yaw = math.atan2(f.y, f.x)                 # ángulo del frente en el FBX
    rot = Matrix.Rotation(math.radians(-90 + yaw) - face_yaw, 4, 'Z')
    base = arm.matrix_world.copy()
    M = Matrix.Translation(Vector(loc)) @ rot @ Matrix.Scale(s, 4) @ Matrix.Translation((0, 0, -z0))
    arm.matrix_world = M @ base
    bpy.context.view_layer.update()
    return s


def night_scene(ground=True, ground_color="#2a3a2c"):
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_EEVEE_NEXT'
    scn.eevee.taa_render_samples = 24
    scn.view_settings.view_transform = 'Standard'
    scn.view_settings.look = 'None'
    w = scn.world or bpy.data.worlds.new("W")
    scn.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.05, 0.07, 0.13, 1)
    bg.inputs[1].default_value = 1.0
    if "Moon" not in bpy.data.objects:
        ld = bpy.data.lights.new("Moon", 'SUN'); ld.energy = 2.6; ld.color = (0.70, 0.80, 1.0); ld.angle = math.radians(2)
        lo = bpy.data.objects.new("Moon", ld); scn.collection.objects.link(lo)
        lo.rotation_euler = (math.radians(42), 0, math.radians(-35))
        # contraluz frío: hace las veces del rim de Nindo/CharacterLit
        rd = bpy.data.lights.new("Rim", 'SUN'); rd.energy = 1.2; rd.color = (0.62, 0.76, 1.0)
        ro = bpy.data.objects.new("Rim", rd); scn.collection.objects.link(ro)
        ro.rotation_euler = (math.radians(70), 0, math.radians(160))
        # farol cálido de relleno (las antorchas y faroles del mundo)
        fd = bpy.data.lights.new("Lantern", 'SUN'); fd.energy = 0.55; fd.color = (1.0, 0.72, 0.45)
        fo = bpy.data.objects.new("Lantern", fd); scn.collection.objects.link(fo)
        fo.rotation_euler = (math.radians(65), 0, math.radians(60))
    if ground and "Ground" not in bpy.data.objects:
        me = bpy.data.meshes.new("Ground")
        me.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("Ground", me); scn.collection.objects.link(g)
        m = bpy.data.materials.new("GroundMat"); m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*hexlin(ground_color), 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
        me.materials.append(m)
    scn.render.film_transparent = False


def camera():
    scn = bpy.context.scene
    cam = bpy.data.objects.get("KitCam")
    if cam is None:
        cd = bpy.data.cameras.new("KitCam")
        cam = bpy.data.objects.new("KitCam", cd)
        scn.collection.objects.link(cam)
    scn.camera = cam
    return cam


def aim(cam, target, yaw, pitch, dist, fov, ortho=None):
    """Cámara mirando a 'target' desde el acimut 'yaw' (0 = desde -Y del mundo, el sur, como en el juego) y 'pitch'
    grados hacia abajo. Un personaje colocado con place(yaw=0) mira a la cámara con yaw 0."""
    a, e = math.radians(yaw), math.radians(pitch)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = Vector(target) + d * dist
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cd = cam.data
    cd.clip_end = dist * 4
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.type = 'PERSP'; cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(fov)


def render(path, w, h):
    scn = bpy.context.scene
    scn.render.resolution_x = w; scn.render.resolution_y = h
    scn.render.resolution_percentage = 100
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def game_view(path, target, yaw, w=320, h=320):
    """Recorte de la cámara del juego a densidad de 1080p: FOV reducido en proporción al recorte."""
    cam = camera()
    fov = 2 * math.degrees(math.atan(math.tan(math.radians(GAME_FOV / 2)) * h / 1080))
    aim(cam, target, yaw, GAME_PITCH, GAME_DIST, fov)
    return render(path, w, h)


def sheet(paths, out, cols, cell=None, scale_game=None):
    """Junta imágenes en una grilla; las chicas (vistas a escala de juego) se amplían x'scale_game' sin filtrar."""
    import numpy as np
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p)
        a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        bpy.data.images.remove(im)
        if scale_game and a.shape[1] * scale_game <= (cell[0] if cell else 1e9):
            a = a.repeat(scale_game, 0).repeat(scale_game, 1)
        imgs.append(a)
    cw = cell[0] if cell else max(a.shape[1] for a in imgs)
    chh = cell[1] if cell else max(a.shape[0] for a in imgs)
    rows = (len(imgs) + cols - 1) // cols
    W, H = cw * cols, chh * rows
    buf = np.zeros((H, W, 4), dtype=np.float32); buf[..., 3] = 1
    for n, a in enumerate(imgs):
        ih, iw = a.shape[:2]
        cx = (n % cols) * cw + (cw - iw) // 2
        cy = (rows - 1 - n // cols) * chh + (chh - ih) // 2      # las imágenes de Blender van de abajo hacia arriba
        buf[cy:cy + ih, cx:cx + iw] = a
    o = bpy.data.images.new("sheet", W, H)
    o.pixels.foreach_set(buf.ravel())
    o.filepath_raw = out
    o.file_format = 'PNG'
    o.save()
    bpy.data.images.remove(o)
    return out


# celda de las hojas de comparación (lineup.py): misma cámara y mismo punto de mira para todos, así los tamaños
# se comparan entre variantes (1x = la densidad del juego a 1080p); el sumo necesita una celda más ancha
CELL = {"ninja": (128, 240), "sumo": (220, 320), "kaito": (128, 240)}
CELL_TARGET_Z = 1.5


def preview(ch, kit_obj, name, outdir, action="Idle", frame=10, scale_mul=1.0):
    """Hoja por kit: reposo 3/4 adelante y atrás, Idle de cerca, y game cam de frente/espalda a escala real.
    Deja además en outdir/_tmp/<name>_cell.png la celda para las hojas de comparación (con scale_mul: el Ōzeki
    mide 1.35 sumos en el juego)."""
    os.makedirs(outdir, exist_ok=True)
    night_scene()
    place(ch, (0, 0, 0), 0)
    h = K.CHARS[ch.key]["height"]
    tgt = Vector((0, 0, h * 0.55))
    cam = camera()
    shots = []
    tmp = os.path.join(outdir, "_tmp")
    os.makedirs(tmp, exist_ok=True)
    for i, (yaw, pitch) in enumerate(((35, 12), (200, 22))):
        aim(cam, tgt, yaw, pitch, h * 6, 0, ortho=h * 1.35)
        shots.append(render(os.path.join(tmp, f"{name}_r{i}.png"), 420, 420))
    act = K.use_action(ch.arm, action)
    bpy.context.scene.frame_set(frame)
    for i, (yaw, pitch) in enumerate(((30, 20), (210, 30))):
        aim(cam, tgt, yaw, pitch, h * 6, 0, ortho=h * 1.35)
        shots.append(render(os.path.join(tmp, f"{name}_p{i}.png"), 420, 420))
    for i, yaw in enumerate((20, 200)):
        shots.append(game_view(os.path.join(tmp, f"{name}_g{i}.png"), Vector((0, 0, h * 0.45)), yaw, 140, 140))
    out = sheet(shots, os.path.join(outdir, f"{name}.png"), 3, cell=(420, 420), scale_game=3)
    if scale_mul != 1.0:
        ch.arm.matrix_world = Matrix.Scale(scale_mul, 4) @ ch.arm.matrix_world     # los pies siguen en z=0
        bpy.context.view_layer.update()
    game_view(os.path.join(tmp, f"{name}_cell.png"), Vector((0, 0, CELL_TARGET_Z)), 20, *CELL[ch.key])
    print("PREVIEW", out, "acción", act.name if act else None)
    return out
