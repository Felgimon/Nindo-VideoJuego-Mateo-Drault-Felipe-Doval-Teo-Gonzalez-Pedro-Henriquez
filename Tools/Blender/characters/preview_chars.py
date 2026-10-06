"""Renders de control de los personajes del equipo (Blender 4.4 -b). No escribe nada en Assets.

  sheet   <id> <out.png> [--src fbx] [--action A --frame F]   giros + cabeza de cerca + cámara del juego
  lineup  <out.png> [--src id=fbx,...] [--day] [--rim]         los 5 a escala real con la cámara del juego
                                                                (pitch 52°, 24 m, FOV 30) bajo luz de luna;
                                                                --rim imita el borde frío de Nindo/CharacterLit;
                                                                --anim id=fbx: pose de Idle prestada (FBX sin tomas)
  (sheet y lineup) --glint: filos encendidos como en un aviso; --prologue: Kaito sin bandana
  frames  <id> <out.png> <acción> <f1,f2,...> [--src fbx]       deformación en frames de una acción
  detail  <id> <out.png> <Objeto[,Objeto]> [--src fbx]          primer plano (armas) desde 4 lados
  stress  <id> <out.png> [--src fbx]                            pose exagerada a mano para revisar deformación

blender -b --python preview_chars.py -- sheet kaito /tmp/kaito.png
Los PNG salen a <= 1280 px de ancho.
"""
import bpy, sys, os, math
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C  # noqa: E402

# id: (fbx relativo a Assets, altura en el juego (m: la "height" de NindoContent, la de la unión de bounds), hacia dónde mira en Blender (azimut: 0=-Y, 90=+X, 180=+Y), ocultar)
CHARS = {
    "kaito": ("Animations teo/kaitooo.fbx", 1.5, 90, None),
    "ninja": ("Models/Ninja/Ninja 1.fbx", 1.7, 90, None),
    "sumo": ("Characters/Sumo/luchadorsumo.fbx", 2.6, 180, None),
    "goro": ("Models/Minijefe.fbx", 3.41, 0, None),
    "grandpa": ("Nindo/Art/Models/Characters/Grandpa.fbx", 1.45, 180, "Cube"),
}

argv = sys.argv[sys.argv.index("--") + 1:]
mode = argv[0]


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def direction(az, el):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
    for o in objs:
        oe = o.evaluated_get(dg); me = oe.to_mesh()
        for v in me.vertices:
            w = oe.matrix_world @ v.co
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
        oe.to_mesh_clear()
    return mn, mx


def visible():
    return [o for o in C.meshes() if not o.hide_render]


def import_char(cid, src=None):
    f, h, front, hide = CHARS[cid]
    before = set(bpy.data.objects); acts = set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=src or os.path.join(C.ASSETS, f))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == 'ARMATURE')
    for o in new:
        if o.type == 'MESH' and hide and o.name.startswith(hide):
            o.hide_render = True
    new_acts = [a for a in bpy.data.actions if a not in acts]
    C.bind_slots(arm, new_acts)
    return arm, [o for o in new if o.type == 'MESH'], new_acts


def pose(arm, new_acts, action, frame):
    if arm.animation_data is None: arm.animation_data_create()
    act = next((a for a in new_acts if a.name.lower().endswith("|" + action.lower())), None) if action else None
    if act is None and action:
        act = next((a for a in new_acts if action.lower() in a.name.lower()), None)
    C.use_action(arm, act)
    if act is None:
        C.rest(arm, True)
    else:
        C.rest(arm, False)
        bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def workbench():
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_WORKBENCH'
    sh = scn.display.shading
    sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_shadows = False
    sh.show_object_outline = True; sh.object_outline_color = (0.04, 0.04, 0.05); sh.show_specular_highlight = False
    sh.show_cavity = False
    sh.background_type = 'VIEWPORT'; sh.background_color = (0.36, 0.42, 0.48)
    scn.view_settings.view_transform = 'Standard'
    scn.render.film_transparent = False
    if scn.world is None: scn.world = bpy.data.worlds.new("Fondo")
    scn.world.color = (0.36, 0.42, 0.48)


def moonlight(ground=True):
    """Noche como en el juego: luna fría alta, ambiente azul oscuro, un farol cálido de relleno."""
    scn = bpy.context.scene
    scn.render.engine = 'BLENDER_EEVEE_NEXT'
    scn.eevee.taa_render_samples = 24
    w = bpy.data.worlds.new("Noche"); scn.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.045, 0.06, 0.11, 1); bg.inputs[1].default_value = 1.0
    sd = bpy.data.lights.new("Luna", 'SUN'); sd.energy = 1.7; sd.color = (0.62, 0.74, 1.0); sd.angle = 0.03
    so = bpy.data.objects.new("Luna", sd); scn.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(-145))
    pd = bpy.data.lights.new("Farol", 'POINT'); pd.energy = 700; pd.color = (1.0, 0.62, 0.3); pd.shadow_soft_size = 0.3
    po = bpy.data.objects.new("Farol", pd); scn.collection.objects.link(po); po.location = (-3.0, -3.5, 2.4)
    # la MoonLantern de Kaito (CharacterFactory.BuildPlayer): luz fría suave sobre el jugador
    ld = bpy.data.lights.new("MoonLantern", 'POINT'); ld.energy = 120; ld.color = (0.72, 0.82, 1.0)
    lo = bpy.data.objects.new("MoonLantern", ld); scn.collection.objects.link(lo); lo.location = (0, -1.0, 3.4)
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=80)
        g = bpy.context.active_object
        gm = C.material("Suelo", "#2c3d2a", rough=1.0); g.data.materials.append(gm)
    scn.view_settings.view_transform = 'Standard'


def character_rim(objs, strength=0.3, power=3.0, color=(0.624, 0.761, 1.0)):
    """Imita el rim de Nindo/CharacterLit en EEVEE: emisión fría = (1 - N·V)^3 * 0.3 sumada a cada material."""
    done = set()
    for o in objs:
        for sl in o.material_slots:
            m = sl.material
            if m is None or m.name in done or not m.use_nodes: continue
            done.add(m.name)
            nt = m.node_tree
            b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if b is None or out is None: continue
            lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs[0].default_value = 0.5
            pw = nt.nodes.new("ShaderNodeMath"); pw.operation = 'POWER'; pw.inputs[1].default_value = power
            nt.links.new(lw.outputs["Facing"], pw.inputs[0])
            em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (*color, 1)
            mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = strength
            nt.links.new(pw.outputs[0], mul.inputs[0]); nt.links.new(mul.outputs[0], em.inputs[1])
            add = nt.nodes.new("ShaderNodeAddShader")
            nt.links.new(b.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
            nt.links.new(add.outputs[0], out.inputs[0])


def tweak_materials():
    """--glint: el filo 'Glint' encendido en dorado como lo haría CharacterGlint.SetGlint en un aviso de parry.
    --prologue: la bandana de Kaito tapada con el material del pelo (antes de recibirla)."""
    for m in bpy.data.materials:
        if not m.use_nodes: continue
        b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if b is None: continue
        if "--glint" in argv and C.base(m.name) == "Glint":
            b.inputs["Emission Color"].default_value = (*C.lin("#ffd86b"), 1); b.inputs["Emission Strength"].default_value = 4.0
        if "--prologue" in argv and C.base(m.name) == "AmarilloBandana":
            pelo = bpy.data.materials.get("Pelo")
            if pelo:
                b.inputs["Base Color"].default_value = pelo.diffuse_color[:]
                m.diffuse_color = pelo.diffuse_color[:]     # Workbench pinta con el color de viewport


def ortho_cam(name="Cam"):
    scn = bpy.context.scene
    cam = bpy.data.objects.get(name)
    if cam is None:
        cd = bpy.data.cameras.new(name); cam = bpy.data.objects.new(name, cd); scn.collection.objects.link(cam)
    cam.data.type = 'ORTHO'; scn.camera = cam
    return cam


def shoot(path, ctr, d, scale, res):
    scn = bpy.context.scene
    cam = ortho_cam()
    R = 40
    cam.location = ctr + d * R
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = scale; cam.data.clip_end = R * 3
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _read(path):
    """PNG -> array numpy (alto, ancho, 4) con el origen arriba (Blender guarda las filas de abajo hacia arriba)."""
    import numpy as np
    im = bpy.data.images.load(path)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32); im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)[::-1]


def _write(arr, path):
    import numpy as np
    h, w = arr.shape[:2]
    im = bpy.data.images.new("sheet", w, h, alpha=False)
    im.pixels.foreach_set(np.ascontiguousarray(arr[::-1]).ravel())
    im.filepath_raw = path; im.file_format = 'PNG'; im.save()
    bpy.data.images.remove(im)


def stitch(paths, out, cols=None, nearest=()):
    """Une los renders en una hoja (<= 1280 px de ancho). 'nearest': índices a agrandar sin suavizar."""
    import numpy as np
    ims = [_read(p) for p in paths]
    cols = cols or len(ims)
    w = max(i.shape[1] for i in ims); h = max(i.shape[0] for i in ims)
    for k in nearest:
        im = ims[k]; f = max(1, min(w // im.shape[1], h // im.shape[0]))
        ims[k] = np.repeat(np.repeat(im, f, axis=0), f, axis=1)
    rows = (len(ims) + cols - 1) // cols
    sheet = np.zeros((h * rows, w * cols, 4), dtype=np.float32); sheet[..., :3] = (0.12, 0.13, 0.16); sheet[..., 3] = 1
    for k, im in enumerate(ims):
        y, x = (k // cols) * h, (k % cols) * w
        ih, iw = min(h, im.shape[0]), min(w, im.shape[1])
        sheet[y:y + ih, x:x + iw] = im[:ih, :iw]
    if sheet.shape[1] > 1280:
        f = int(math.ceil(sheet.shape[1] / 1280))
        sheet = sheet[::f, ::f]
    _write(sheet, out)
    for p in paths:
        os.remove(p)
    print("SHEET", out, sheet.shape[1], "x", sheet.shape[0])


def sheet(cid, out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, ms, acts = import_char(cid, opt("--src"))
    pose(arm, acts, opt("--action"), opt("--frame", 1))
    workbench()
    tweak_materials()
    _, h, front, _ = CHARS[cid]
    mn, mx = bounds(visible()); ctr = (mn + mx) / 2; size = mx - mn
    big = max(size) * 1.08
    tmp = []
    base = os.path.splitext(out)[0]
    for k, (daz, el) in enumerate(((0, 8), (40, 12), (90, 5), (160, 15), (200, 52))):
        p = f"{base}_t{k}.png"; shoot(p, ctr, direction(front + daz, el), big, (320, 320)); tmp.append(p)
    # cabeza: el cuarto superior del personaje, de frente y 3/4
    head_c = Vector((ctr.x, ctr.y, mx.z - size.z * 0.2))
    for k, daz in enumerate((0, 35)):
        p = f"{base}_h{k}.png"; shoot(p, head_c, direction(front + daz, 6), size.z * 0.5, (320, 320)); tmp.append(p)
    # cámara del juego a escala de píxel real (1080p: 84 px por metro) agrandada x3 para verla
    ppm = 1080 / (2 * 24 * math.tan(math.radians(15)))
    s = h / size.z
    px = min(320, int(ppm * max(size) * s * 1.1))   # más grande que la celda: se recorta, no se achica
    scn = bpy.context.scene
    p = f"{base}_g.png"
    shoot(p, ctr, direction(front + 30, 52), px / (ppm * s), (px, px))
    tmp.append(p)
    stitch(tmp, out, cols=4, nearest=(len(tmp) - 1,))


def lineup(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    srcs = dict(kv.split("=", 1) for kv in opt("--src", "").split(",") if "=" in kv)
    anims = dict(kv.split("=", 1) for kv in opt("--anim", "").split(",") if "=" in kv)
    placed = []
    for cid in ("kaito", "grandpa", "ninja", "sumo", "goro"):
        arm, ms, acts = import_char(cid, srcs.get(cid))
        if not acts and cid in anims:
            # el FBX ya no trae tomas (el sumo anima con .anim de Unity): se toma la pose de otro FBX con el mismo esqueleto
            helper, hms, hacts = import_char(cid, anims[cid])
            for o in [helper] + hms: bpy.data.objects.remove(o, do_unlink=True)
            acts = hacts
        C.rest(arm, True)
        mn, mx = bounds(ms)   # como NormalizeHeight: bounds de bind de todos los renderers
        s = CHARS[cid][1] / (mx.z - mn.z)
        pose(arm, acts, "Idle" if cid != "grandpa" else "Scene", 2)
        # escala y giro en un vacío padre: las tomas horneadas también animan el objeto Armature
        root = bpy.data.objects.new("Raiz_" + cid, None); bpy.context.scene.collection.objects.link(root)
        arm.parent = root
        root.rotation_euler.z = math.radians(-CHARS[cid][2] + 25)
        root.scale = (s, s, s)
        placed.append((root, [o for o in ms if not o.hide_render]))
    bpy.context.view_layer.update()
    x = 0.0
    for arm, ms in placed:
        mn, mx = bounds(ms)
        arm.location.x += x - mn.x; arm.location.y -= (mn.y + mx.y) / 2; arm.location.z -= mn.z
        bpy.context.view_layer.update()
        x += (mx.x - mn.x) + 0.9
    for arm, _ in placed:
        arm.location.x -= (x - 0.9) / 2
    if "--day" in argv:
        workbench()
    else:
        moonlight()
        if "--rim" in argv:
            character_rim([o for _, ms in placed for o in ms])
    tweak_materials()
    scn = bpy.context.scene
    cd = bpy.data.cameras.new("Juego"); cam = bpy.data.objects.new("Juego", cd); scn.collection.objects.link(cam)
    cd.sensor_fit = 'VERTICAL'; cd.angle_y = math.radians(30); cd.clip_end = 200
    pitch = math.radians(52); target = Vector((0, 0, 1.0))
    cam.location = target + Vector((0, -math.cos(pitch) * 24, math.sin(pitch) * 24))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam
    # recorte central de un frame 1080p: misma densidad de píxeles que en el juego
    scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
    scn.render.use_border = True; scn.render.use_crop_to_border = True
    scn.render.border_min_x, scn.render.border_max_x = 0.5 - 640 / 1920, 0.5 + 640 / 1920
    scn.render.border_min_y, scn.render.border_max_y = 0.5 - 200 / 1080, 0.5 + 220 / 1080
    scn.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("LINEUP", out)


def detail(cid, out, names):
    """Primer plano de objetos/regiones: 'Isan' (un objeto) o 'z>2.0' (franja de altura del cuerpo)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, ms, acts = import_char(cid, opt("--src"))
    pose(arm, acts, opt("--action"), opt("--frame", 1))
    workbench()
    front = CHARS[cid][2]
    zr = None
    if "@" in names:   # 'Cuerpo@2.3:2.8': solo la franja de alturas (reposo) de ese objeto
        names, z = names.split("@"); zr = tuple(float(v) for v in z.split(":"))
    objs = [o for o in visible() if any(o.name.startswith(n) for n in names.split(","))] or visible()
    mn, mx = bounds(objs)
    if zr:
        mn.z, mx.z = zr
        span = (zr[1] - zr[0]) * 1.2
        ctr = (mn + mx) / 2; ctr.y = mx.y if CHARS[cid][2] == 180 else ctr.y
        size = span
    else:
        ctr = (mn + mx) / 2; size = max(mx - mn) * 1.1
    tmp = []
    base = os.path.splitext(out)[0]
    views = ((0, 4), (35, 10), (-35, 10), (0, 40)) if zr else ((0, 10), (60, 35), (180, 20), (30, 70))
    for k, (daz, el) in enumerate(views):
        p = f"{base}_d{k}.png"; shoot(p, ctr, direction(front + daz, el), size, (320, 320)); tmp.append(p)
    stitch(tmp, out, cols=4)


STRESS = (("Torso", (18, 0, 12)), ("tronco", (18, 0, 12)), ("EspaldaBaja", (18, 0, 12)), ("Cabeza", (20, 0, -20)),
          ("cabeza", (20, 0, -20)), ("Pierna.L", (-40, 0, 0)), ("Pierna.l", (-40, 0, 0)), ("Pierna.R", (35, 0, 0)),
          ("Pierna.r", (35, 0, 0)), ("Tibia.L", (45, 0, 0)), ("Tibia.R", (30, 0, 0)), ("Brazo.L", (0, 0, 45)),
          ("Antebrazo.R", (0, 0, -55)), ("Hombro.R", (0, 25, 0)))


def stress(cid, out):
    """Pose exagerada a mano (sin acción): para los FBX cuyas tomas son estáticas (el sumo anima con .anim de
    Unity), comprueba que lo agregado (pelo, sagari, fajas) siga a los huesos sin romperse."""
    import mathutils
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, ms, acts = import_char(cid, opt("--src"))
    workbench()
    if arm.animation_data: C.use_action(arm, None)
    C.rest(arm, True)
    mn, mx = bounds(visible()); size = mx - mn
    C.rest(arm, False)
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        for name, rot in STRESS:
            if pb.name == name:
                pb.rotation_euler = mathutils.Euler([math.radians(a) for a in rot])
    bpy.context.view_layer.update()
    a, b = bounds(visible()); ctr = (a + b) / 2
    front = CHARS[cid][2]
    tmp = []
    base = os.path.splitext(out)[0]
    for k, (daz, el) in enumerate(((20, 10), (110, 10), (200, 20), (300, 45))):
        p = f"{base}_s{k}.png"; shoot(p, ctr, direction(front + daz, el), max(size) * 1.2, (320, 320)); tmp.append(p)
    stitch(tmp, out, cols=4)


def frames(cid, out, action, fl):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm, ms, acts = import_char(cid, opt("--src"))
    workbench()
    _, h, front, _ = CHARS[cid]
    C.rest(arm, True)
    mn, mx = bounds(visible()); size = mx - mn
    tmp = []
    base = os.path.splitext(out)[0]
    for k, f in enumerate(fl):
        pose(arm, acts, action, f)
        a, b = bounds(visible()); ctr = (a + b) / 2
        p = f"{base}_f{k}.png"; shoot(p, ctr, direction(front + 35, 14), max(size) * 1.25, (360, 360)); tmp.append(p)
    stitch(tmp, out, cols=len(tmp))


if mode == "sheet":
    sheet(argv[1], argv[2])
elif mode == "lineup":
    lineup(argv[1])
elif mode == "detail":
    detail(argv[1], argv[2], argv[3])
elif mode == "stress":
    stress(argv[1], argv[2])
elif mode == "frames":
    frames(argv[1], argv[2], argv[3], [int(x) for x in argv[4].split(",")])
