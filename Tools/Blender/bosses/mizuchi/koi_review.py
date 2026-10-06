"""Renders de revisión del Gran Koi: la plataforma real de la arena del lago (props_structures), un Kaito
de 1.5 m (el FBX del equipo), luz de luna + farol, y la cámara del juego (pitch 43-52°, FOV 30).

Las hojas se arman con numpy dentro de Blender (sin PIL) y nunca pasan de 1280 px de ancho.
Debajo de cada cuadro una franja de color marca el tiempo del golpe: gris = anticipación/recuperación,
dorado = pausa en el apex (cuando el jugador tiene que leer el aviso), rojo = golpe activo.
"""
import bpy, math, os
from mathutils import Vector
import numpy as np
from koi_common import REPO, P, SLOTS, GLOW_P2, materials as KC_materials

DECK = 0.0
_kaito = None


def srgb2lin(c):
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def flat_mat(name, hexname, emit=0.0):
    m = bpy.data.materials.get("rv_" + name)
    if m:
        return m
    m = bpy.data.materials.new("rv_" + name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    rgb = srgb2lin(P.hex_to_rgb(dict(P.PALETTE)[hexname]))
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.9
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def setup(res=(320, 180), platform=True, kaito=True, samples=12):
    scn = bpy.context.scene
    # como en Unity: caras traseras descartadas (las aletas de doble cara no pelean entre sí); la fuerza
    # de los brillos ya viene de koi_common.GLOW_STRENGTH
    for m in KC_materials(SLOTS + [GLOW_P2]):
        m.use_backface_culling = True
    scn.render.engine = 'BLENDER_EEVEE_NEXT'
    scn.eevee.taa_render_samples = samples
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.render.film_transparent = False
    scn.view_settings.view_transform = 'Standard'
    scn.render.image_settings.file_format = 'PNG'
    scn.render.image_settings.color_mode = 'RGB'
    if bpy.data.objects.get("moon"):
        return scn       # el escenario ya está armado (hojas de clips y del modelo en la misma corrida)
    w = bpy.data.worlds.new("night")
    scn.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.02, 0.035, 0.075, 1)
    bg.inputs[1].default_value = 1.6
    # luna: la del juego (Unity euler 48,-38,0) pasada a ejes de Blender; fría y fuerte
    d = Vector((0.41, -0.53, -0.74)).normalized()
    sd = bpy.data.lights.new("moon", 'SUN'); sd.energy = 3.2; sd.color = (0.7, 0.8, 1.0); sd.angle = math.radians(3)
    s = bpy.data.objects.new("moon", sd); scn.collection.objects.link(s)
    s.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    # relleno frío desde la cascada (norte = -Y de Blender) y un farol cálido en la baranda
    rd = bpy.data.lights.new("falls", 'SUN'); rd.energy = 1.1; rd.color = (0.55, 0.85, 1.0)
    r = bpy.data.objects.new("falls", rd); scn.collection.objects.link(r)
    r.rotation_euler = Vector((0.1, 0.9, -0.35)).normalized().to_track_quat('-Z', 'Y').to_euler()
    ld = bpy.data.lights.new("lantern", 'POINT'); ld.energy = 1500; ld.color = (1.0, 0.62, 0.32); ld.shadow_soft_size = 0.4
    lo = bpy.data.objects.new("lantern", ld); scn.collection.objects.link(lo); lo.location = (-6.0, 6.0, 2.2)
    if platform:
        import props_structures as PS
        ob = PS.build_lake_arena_platform(3)
        ob.location.z = DECK - 1.0
        bpy.ops.mesh.primitive_plane_add(size=160, location=(0, 0, DECK - 1.0))
        wtr = bpy.context.active_object
        wtr.data.materials.append(flat_mat("water", "water_deep"))
    if kaito:
        load_kaito()
    return scn


def show_stage(on):
    """Plataforma, agua y Kaito: sí en las vistas de juego, no en las vistas ortográficas del modelo."""
    for o in bpy.data.objects:
        if o.name.startswith(("lake_arena_platform", "Plane")) or (_kaito and (o == _kaito or o.parent == _kaito)):
            o.hide_render = not on


def load_kaito():
    """Kaito del equipo (kaitooo.fbx) a 1.5 m, en Idle, como regla de escala."""
    global _kaito
    path = os.path.join(REPO, "Nindo", "Assets", "Animations teo", "kaitooo.fbx")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == 'ARMATURE')
    act = next((a for a in bpy.data.actions if a.name.endswith("Idle")), None)
    if act and arm.animation_data:
        arm.animation_data.action = act
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    body = [o for o in new if o.type == 'MESH' and o.name.startswith("Cuerpo")]

    def zs():
        return [(o.matrix_world @ Vector(c)).z for o in body for c in o.bound_box]
    arm.scale = arm.scale * (1.5 / (max(zs()) - min(zs())))
    bpy.context.view_layer.update()
    arm.location.z += DECK - min(zs())
    _kaito = arm
    # las animaciones de Kaito no deben seguir los cuadros de los clips del koi
    if arm.animation_data:
        arm.animation_data.action = None
    return arm


KAITO_YAW0 = 0.0   # giro con el que el FBX importado mira a -Y de Blender (medido en el render de prueba)


def place_kaito(pos, facing_deg):
    """facing_deg: hacia dónde mira Kaito, girando desde -Y de Blender (90 = mira a +X)."""
    if _kaito is None:
        return
    _kaito.location.x, _kaito.location.y = pos[0], pos[1]
    _kaito.rotation_euler = (0, 0, math.radians(KAITO_YAW0 + facing_deg))


def camera(name, loc, look, fov=30.0, ortho=None, up_roll=0.0):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    c = bpy.data.objects.get(name)
    if c is None:
        c = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(c)
    if ortho:
        cd.type = 'ORTHO'; cd.ortho_scale = ortho
    else:
        cd.type = 'PERSP'; cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(fov)
    cd.clip_end = 300
    c.location = Vector(loc)
    q = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y')
    if up_roll:
        from mathutils import Quaternion
        q = q @ Quaternion((0, 0, 1), math.radians(up_roll))
    c.rotation_euler = q.to_euler()
    return c


def game_cam(focus, pitch=47.0, dist=26.0, yaw=0.0, fov=30.0, name="game"):
    """Cámara del juego: mira al 'norte' del mundo (Unity +Z = Blender -Y) desde arriba y atrás."""
    p, yw = math.radians(pitch), math.radians(yaw)
    back = Vector((math.sin(yw) * math.cos(p), math.cos(yw) * math.cos(p), math.sin(p)))
    return camera(name, Vector(focus) + back * dist, focus, fov)


def render(path, cam):
    scn = bpy.context.scene
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


# ------------------------------------------------------------------ hojas
def _load(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)


def stitch(cells, cols, out, strip=None, strip_h=6, bg=(0.06, 0.07, 0.1)):
    """cells: lista de rutas PNG (mismo tamaño). strip: lista de colores RGB (0-1) bajo cada cuadro."""
    ims = [_load(p) for p in cells]
    h, w = ims[0].shape[:2]
    rows = (len(ims) + cols - 1) // cols
    ch = h + (strip_h if strip else 0)
    canvas = np.zeros((rows * ch, cols * w, 4), dtype=np.float32)
    canvas[..., :3] = bg
    canvas[..., 3] = 1
    for i, im in enumerate(ims):
        r, c = divmod(i, cols)
        # numpy de Blender: la fila 0 es la de ABAJO; se arma de arriba hacia abajo
        y0 = (rows - 1 - r) * ch + (strip_h if strip else 0)
        canvas[y0:y0 + h, c * w:(c + 1) * w] = im
        if strip:
            canvas[y0 - strip_h:y0 - 1, c * w + 2:(c + 1) * w - 2, :3] = strip[i]
    H, W = canvas.shape[:2]
    img = bpy.data.images.new("sheet", W, H)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = out
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    for p in cells:
        try:
            os.remove(p)
        except OSError:
            pass
    return out
