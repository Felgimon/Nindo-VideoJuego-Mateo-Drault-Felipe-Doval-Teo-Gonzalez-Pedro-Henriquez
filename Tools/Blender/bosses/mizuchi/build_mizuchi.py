"""Mizuchi, el Gran Koi (jefe del Lago Kohan): modelo, esqueleto, animaciones, revisión y exportación.

Un solo comando, determinista (sin auto-weights ni azar sin semilla):
  blender -b --factory-startup --python Tools/Blender/bosses/mizuchi/build_mizuchi.py -- [opciones]

  --out DIR        carpeta de los renders de revisión (por defecto Tools/Blender/out/previews/mizuchi, ignorada por git)
  --sheets         hoja del modelo (vistas, cámara del juego, fase 1 y 2) + una hoja por clip
  --model-only     solo la hoja del modelo (iterar el modelado sin animar)
  --clips a,b      limita las hojas de clips a esos nombres
  --p2             las hojas de clips también con la malla de la fase 2 (corrompida)
  --export         escribe Nindo/Assets/Nindo/Art/Characters/Mizuchi/Mizuchi.fbx + Mizuchi.fbx.json
Sin opciones hace todo (hojas + export). Después: python Tools/Unity/generate_assets.py (o solo las
entradas de mizuchi_koi, ver el final de este archivo) para el .meta, el controller y NindoContent.
"""
import bpy, sys, os, math, json
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import koi_common as KC   # noqa: E402  (agrega Tools/Blender al path)
import koi_model as KM    # noqa: E402
import koi_rig as KR      # noqa: E402
import koi_review as RV   # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT = opt("--out", os.path.join(KC.TOOLS_BLENDER, "out", "previews", "mizuchi"))
FBX = os.path.join(KC.REPO, "Nindo", "Assets", "Nindo", "Art", "Characters", "Mizuchi", "Mizuchi.fbx")
ALL = not any(a.startswith("--") and a not in ("--out", "--p2") for a in argv)
DO_SHEETS = ALL or "--sheets" in argv or "--model-only" in argv
DO_EXPORT = ALL or "--export" in argv
MODEL_ONLY = "--model-only" in argv
ONLY = set(opt("--clips", "").split(",")) - {""}


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = 30
    arm = KR.build_armature("MizuchiRig")
    objs = {}
    for ph in (1, 2):
        ob = KM.Koi(ph).build()
        KR.skin(ob, arm)
        objs[ph] = ob
    rip = KM.build_ripple(KM.bone_names())
    KR.skin(rip, arm)
    return arm, objs[1], objs[2], rip


def facing_guard(arm):
    """El frente del koi es -Y de Blender (= +Z de Unity con axis_forward '-Z'): si alguien da vuelta la
    tabla de huesos, la exportación se corta acá y no en el juego (la clase de bug 'Kaito corre de costado')."""
    b = arm.data.bones
    assert b["head"].tail_local.y < b["tail"].tail_local.y, "la cabeza tiene que estar hacia -Y"
    assert b["eye_glint"].head_local.y < 0, "eye_glint fuera de la cabeza"
    assert b["FacingProbe"].head_local.y < 0, "FacingProbe tiene que apuntar al frente (-Y)"


def model_sheet(arm, p1, p2, rip):
    """Hoja del modelo: fase 1 y 2 en perfil, frente, arriba, 3/4 y cámara del juego sobre la plataforma."""
    os.makedirs(OUT, exist_ok=True)
    RV.setup(res=(640, 360), samples=24)
    RV.place_kaito((-1.2, 6.0), 180)
    views = [
        ("side", RV.camera("v_side", (16, 0.8, 1.8), (0, 0.8, 1.8), ortho=9.6)),
        ("front", RV.camera("v_front", (0, -16, 1.9), (0, 0, 1.9), ortho=6.2)),
        ("top", RV.camera("v_top", (0, 0.8, 30), (0, 0.8, 0), ortho=9.6, up_roll=90)),
        ("q34", RV.camera("v_q34", (8.5, -8.0, 5.2), (0, 0.3, 1.6), fov=34)),
        ("game", RV.game_cam((0, 1.8, 1.0), pitch=47, dist=24)),
        ("game43", RV.game_cam((0, 1.0, 1.0), pitch=43, dist=28)),
    ]
    for ph, ob in ((1, p1), (2, p2)):
        p1.hide_render = ph != 1
        p2.hide_render = ph != 2
        cells = []
        for nm, cam in views:
            if nm.startswith("game"):
                arm.rotation_euler = (0, 0, math.radians(200))
            else:
                arm.rotation_euler = (0, 0, 0)
            stage = nm.startswith("game") or nm == "q34"
            RV.show_stage(stage)
            cells.append(RV.render(os.path.join(OUT, f"_m{ph}_{nm}.png"), cam))
        RV.stitch(cells, 2, os.path.join(OUT, f"model_p{ph}.png"))
        # primer plano a 1280 px: para juzgar facetas, colores y accesorios contra el concept
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 1280, 720
        arm.rotation_euler = (0, 0, math.radians(215))
        RV.show_stage(True)
        RV.render(os.path.join(OUT, f"hero_p{ph}.png"), RV.camera("v_hero", (7.6, 6.4, 4.4), (0.2, 0.2, 1.7), fov=38))
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = 640, 360
    arm.rotation_euler = (0, 0, 0)
    p1.hide_render = False
    p2.hide_render = True


def stats(p1, p2, rip, arm):
    out = {"tris": {o.name: KC.tri_count(o) for o in (p1, p2, rip)}, "bones": len(arm.data.bones)}
    zs = [(o.matrix_world @ v.co).z for o in (p1, p2, rip) for v in o.data.vertices]
    # alto del modelo en reposo: el anillo Ripple (cubierta) define el piso y NormalizeHeight escala a esto,
    # así que en Unity la escala queda en 1 y el koi flota a la altura diseñada sin código
    out["height"] = round(max(zs) - min(zs), 3)
    out["min_z"] = round(min(zs), 3)
    print("STATS", json.dumps(out))
    return out


# ------------------------------------------------------------------ animaciones
def bake_all(arm):
    import koi_anim as KA, koi_clips as KCL
    rig = KR.Rig(arm)
    baker = KA.Baker(rig, {})
    arm.animation_data_create()
    results = []
    for clip in KCL.clips():
        base = baker.bake(clip)
        act = KA.write_action(arm, clip.name, base, rig)
        results.append((clip, base, act))
    return rig, results


def run_lint(rig, results, objs):
    import koi_lint as LN
    skin = LN.Skin(rig, objs)
    report, errors = {}, []
    for clip, base, act in results:
        e, info = LN.lint(rig, clip, base, skin)
        report[clip.name] = info
        errors += e
        print("LINT", clip.name, json.dumps(info), "ERR" if e else "ok")
    for e in errors:
        print("LINT-ERROR", e)
    return report, errors


FRAME_KEYS = ("tell", "apex", "contact", "activeEnd", "release", "event", "hide", "roar", "land", "swap")


def sidecar(rig, results, report, st):
    """Mizuchi.fbx.json: lo que Unity y el código del jefe necesitan de cada clip (tiempos en cuadros de la
    toma del FBX, que empieza en 0; el contacto normalizado ya es el activeStart del AttackDef)."""
    clips = []
    for clip, base, act in results:
        n = clip.frames
        tm = dict(clip.timing)
        e = {"name": clip.name, "take": f"MizuchiRig|{clip.name}", "first": 0, "last": n, "frames": n,
             "length": round(n / 30.0, 4), "loop": clip.loop}
        for k in ("tell", "apex", "contact", "activeEnd", "strikeBone", "kind", "release", "event", "hide", "roar",
                  "land", "swap", "holdsLast", "punish"):
            if tm.get(k) is not None:
                e[k + ("Frame" if k in FRAME_KEYS else "")] = tm[k]
        # cuadros con sufijo Frame; los normalizados llevan el nombre del campo de AttackDef (apex, activeStart, activeEnd)
        for k in ("hold", "loopRange", "beached", "eject"):
            if tm.get(k):
                e[k] = list(tm[k])
        if tm.get("apex") is not None:
            e["apex"] = round(tm["apex"] / n, 4)              # AttackDef.apex (pose de máxima carga)
        if tm.get("contact") is not None:
            e["activeStart"] = round(tm["contact"] / n, 4)
        if tm.get("activeEnd") is not None:
            e["activeEnd"] = round(tm["activeEnd"] / n, 4)
        # desplazamiento del body (no hay root motion: el código del jefe decide el avance real)
        M0, Mc, Mn = rig.fk(base[0]), rig.fk(base[tm.get("contact") or 0]), rig.fk(base[n])

        def uvec(v):
            return [round(-v.x, 3), round(v.z, 3), round(-v.y, 3)]   # Blender -> Unity
        e["bodyAtContact"] = uvec(Mc["body"].to_translation() - M0["body"].to_translation())
        e["bodyAtEnd"] = uvec(Mn["body"].to_translation() - M0["body"].to_translation())
        e["lint"] = report.get(clip.name, {})
        clips.append(e)
    return {"character": "mizuchi_koi", "fps": 30, "height": st["height"], "modelYaw": 0, "bones": st["bones"],
            "tris": st["tris"], "meshes": {"Body_P1": "fase 1 (Tancho)", "Body_P2": "fase 2 (corrompido) y forma del dragón liberado",
                                           "Ripple": "espejo de agua en la cubierta (100 % root)"},
            "clips": clips}


def export(arm, p1, p2, rip, data):
    os.makedirs(os.path.dirname(FBX), exist_ok=True)
    arm.animation_data.action = bpy.data.actions["Hover"]
    bpy.context.scene.frame_set(0)
    bpy.ops.object.select_all(action='DESELECT')
    for o in (arm, p1, p2, rip):
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    # mismos ejes que el resto de los personajes del juego y una toma por acción ('MizuchiRig|<Clip>', cada
    # una empieza en 0). simplify 0.05 = tolerancia relativa de 0.005 %: los canales constantes (escala,
    # posición de casi todos los huesos) quedan en dos claves y los latigazos de 2-3 cuadros no se tocan
    bpy.ops.export_scene.fbx(filepath=FBX, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y',
                             use_armature_deform_only=True, mesh_smooth_type='FACE', add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.05,
                             path_mode='STRIP', embed_textures=False, use_custom_props=False,
                             primary_bone_axis='Y', secondary_bone_axis='X')
    with open(FBX + ".json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    print("EXPORTED", FBX, os.path.getsize(FBX))


# cabezas (articulaciones): el FBX no guarda el largo de los huesos, así que las puntas no se comparan
ROUNDTRIP_BONES = ("head", "jaw", "spine_b3", "tail", "pec_L3", "fluke_L2", "seal", "FacingProbe", "barbel_L2", "whisker_R3")


def roundtrip_ref(rig, results):
    """Posición de algunas articulaciones por cuadro (mundo de Blender) para check_fbx.py."""
    out = {}
    for clip, base, act in results:
        bones = {b: [] for b in ROUNDTRIP_BONES}
        for bs in base:
            M = rig.fk(bs)
            for b in ROUNDTRIP_BONES:
                bones[b].append([round(c, 5) for c in M[b].to_translation()])
        out[clip.name] = bones
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "roundtrip_ref.json")
    with open(path, "w") as fh:
        json.dump({"clips": out}, fh)
    print("ROUNDTRIP_REF", path)


# ------------------------------------------------------------------ hojas de clips
GREY, GOLD, RED = (0.35, 0.37, 0.42), (0.95, 0.72, 0.2), (0.9, 0.22, 0.18)


def pick_frames(clip, k=8):
    """Cuadros que cuentan la actuación: inicio, aviso, pausa, apex, el cuadro antes del golpe, el golpe,
    el seguimiento y el final (los loops, equiespaciados)."""
    n = clip.frames
    if clip.loop:
        return [round(i * n / k) for i in range(k)]
    tm = clip.timing
    want = [0, n]
    for key in ("tell", "apex", "contact"):
        if tm.get(key) is not None:
            want.append(tm[key])
    if tm.get("hold"):
        want += list(tm["hold"])
    if tm.get("contact") is not None:
        want += [tm["contact"] - 1, tm["contact"] + 3]
    fr = sorted(set(max(0, min(n, int(f))) for f in want))
    while len(fr) < k:
        g, i = max((fr[j + 1] - fr[j], j) for j in range(len(fr) - 1))
        if g < 2:
            break
        fr.insert(i + 1, fr[i] + g // 2)
    keep = {tm.get("contact"), 0, n}
    while len(fr) > k:
        g, i = min((fr[j + 1] - fr[j - 1], j) for j in range(1, len(fr) - 1) if fr[j] not in keep)
        fr.pop(i)
    return fr


def strip_color(clip, f):
    tm = clip.timing
    c, e = tm.get("contact"), tm.get("activeEnd")
    if c is not None and c <= f <= (e if e is not None else c):
        return RED
    h = tm.get("hold")
    if h and h[0] <= f <= h[1]:
        return GOLD
    return GREY


def clip_sheets(arm, p1, p2, results, phase=1):
    """Una hoja por clip: 8 cuadros con la cámara del juego (arriba, 47°, más cerca que en el juego para
    ver el detalle) y 8 de perfil sobre la cubierta, con la franja de tiempos debajo de cada cuadro."""
    os.makedirs(OUT, exist_ok=True)
    RV.setup(res=(320, 180), samples=10)
    p1.hide_render = phase != 1
    p2.hide_render = phase != 2
    yaw = 150.0
    fwd = (math.sin(math.radians(yaw)), -math.cos(math.radians(yaw)))
    RV.place_kaito((fwd[0] * 6.0, fwd[1] * 6.0), yaw + 180)
    gcam = RV.game_cam((0.0, 0.6, 1.0), pitch=47, dist=17.5, name="g_clip")
    scam = RV.camera("s_clip", (18, 0.6, 1.9), (0, 0.6, 1.9), ortho=10.5)
    for clip, base, act in results:
        if ONLY and clip.name not in ONLY:
            continue
        arm.animation_data.action = act
        frames = pick_frames(clip)
        cells, strip = [], []
        for view in ("game", "side"):
            arm.rotation_euler = (0, 0, math.radians(yaw) if view == "game" else 0)
            RV.show_stage(True)
            for f in frames:
                bpy.context.scene.frame_set(f)
                cells.append(RV.render(os.path.join(OUT, f"_c_{clip.name}_{view}_{f}.png"), gcam if view == "game" else scam))
                strip.append(strip_color(clip, f))
        RV.stitch(cells, 4, os.path.join(OUT, f"clip_{clip.name}{'' if phase == 1 else '_p2'}.png"), strip=strip)
        print("SHEET", clip.name, frames)
    arm.rotation_euler = (0, 0, 0)


def main():
    arm, p1, p2, rip = build()
    facing_guard(arm)
    st = stats(p1, p2, rip, arm)
    if MODEL_ONLY:
        model_sheet(arm, p1, p2, rip)
        return
    rig, results = bake_all(arm)
    report, errors = run_lint(rig, results, [p1, p2])
    if DO_EXPORT:
        if errors:
            raise SystemExit("LINT: la exportación se cancela (ver LINT-ERROR arriba)")
        export(arm, p1, p2, rip, sidecar(rig, results, report, st))
        roundtrip_ref(rig, results)
    if DO_SHEETS:
        clip_sheets(arm, p1, p2, results)
        if "--p2" in argv:
            clip_sheets(arm, p1, p2, results, phase=2)
        model_sheet(arm, p1, p2, rip)
    print("DONE")


main()
