"""Preview renders that approximate the in-game look (moonlit night, high camera)."""
import bpy, math, os
from mathutils import Vector
import nindo_lib as L


def _engine():
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            bpy.context.scene.render.engine = e
            return e
        except Exception:
            pass
    bpy.context.scene.render.engine = "CYCLES"
    return "CYCLES"


def setup_night(ground=True, ground_size=40, ground_color="grass_dark", strength=1.0):
    scn = bpy.context.scene
    _engine()
    scn.render.resolution_x, scn.render.resolution_y = 640, 480
    scn.render.film_transparent = False
    try:
        scn.view_settings.view_transform = 'AgX'
    except Exception:
        scn.view_settings.view_transform = 'Filmic'
    world = bpy.data.worlds.new("NightWorld")
    scn.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.035, 0.055, 0.11, 1)
    bg.inputs[1].default_value = 1.2 * strength
    sun_d = bpy.data.lights.new("Moon", 'SUN')
    sun_d.energy = 2.2 * strength
    sun_d.color = (0.72, 0.82, 1.0)
    sun_d.angle = math.radians(3)
    sun = bpy.data.objects.new("Moon", sun_d)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    scn.collection.objects.link(sun)
    fill_d = bpy.data.lights.new("Fill", 'SUN')
    fill_d.energy = 0.35 * strength
    fill_d.color = (0.55, 0.45, 0.65)
    fill = bpy.data.objects.new("Fill", fill_d)
    fill.rotation_euler = (math.radians(70), 0, math.radians(150))
    scn.collection.objects.link(fill)
    try:
        scn.eevee.use_shadows = True
    except Exception:
        pass
    if ground:
        mb = L.MeshBuilder("PreviewGround")
        s = ground_size / 2
        mb.face([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], ground_color)
        g = mb.finish()
        g.location.z = -0.002
        return g
    return None


def _bbox(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9, 1e9, 1e9)); mx = -mn
    for o in objs:
        for c in o.evaluated_get(dg).bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    return mn, mx


def _camera(name, fov):
    cd = bpy.data.cameras.new(name)
    cd.lens_unit = 'FOV'
    cd.angle = math.radians(fov)
    cd.clip_end = 2000
    c = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(c)
    return c


def look(cam, eye, target):
    cam.location = eye
    d = Vector(target) - Vector(eye)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def render_views(objs, out_prefix, views=("game", "front34", "back34"), res=(640, 480)):
    """Renders the given objects. 'game' = in-game camera (pitch 50, fov 30, looking
    toward Blender -Y which is Unity +Z / screen-up)."""
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    mn, mx = _bbox(objs)
    ctr = (mn + mx) / 2
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z, 1.0)
    paths = []
    for v in views:
        if v == "game":
            cam = _camera("CamGame", 30)
            pitch = math.radians(50)
            dist = size * 2.6 + 4
            # camera sits "south" of the target in game space == Blender +Y side
            eye = ctr + Vector((0, math.cos(pitch) * dist, math.sin(pitch) * dist))
        elif v == "front34":
            cam = _camera("Cam34", 35)
            dist = size * 2.2 + 2
            eye = ctr + Vector((-0.6, -1.0, 0.55)).normalized() * dist
        elif v == "back34":
            cam = _camera("CamB34", 35)
            dist = size * 2.2 + 2
            eye = ctr + Vector((0.8, 0.9, 0.6)).normalized() * dist
        elif v == "top":
            cam = _camera("CamTop", 30)
            eye = ctr + Vector((0, 0.01, size * 3.5))
        look(cam, eye, ctr)
        scn.camera = cam
        p = f"{out_prefix}_{v}.png"
        scn.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)
    return paths


def montage(paths, out, cols=3):
    try:
        from PIL import Image
    except ImportError:
        return None
    ims = [Image.open(p) for p in paths]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    m = Image.new("RGB", (w * min(cols, len(ims)), h * rows), (20, 20, 25))
    for i, im in enumerate(ims):
        m.paste(im, ((i % cols) * w, (i // cols) * h))
    m.save(out)
    return out
