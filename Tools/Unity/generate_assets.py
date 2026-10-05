#!/usr/bin/env python3
"""Genera los assets de Unity de Nindo que no se pueden crear "a mano" en el editor desde
este entorno: AnimatorControllers, materiales, NindoContent.asset, escenas, sprites del HUD,
texturas de paleta y .meta con GUIDs estables.

Uso: python3 Tools/Unity/generate_assets.py
Es idempotente: se puede correr de nuevo después de exportar props/zonas desde Blender.
"""
import os, sys, json, glob, re, shutil, struct
from unity_yaml import *

sys.path.insert(0, os.path.join(REPO, "Tools", "Blender"))
import nindo_palette as PAL

N = os.path.join(ASSETS, "Nindo")
ART = os.path.join(N, "Art")
P_TEX = os.path.join(ART, "Textures")
P_MAT = os.path.join(ART, "Materials")
P_UI = os.path.join(ART, "UI")
P_FONTS = os.path.join(ART, "Fonts")
P_ANIM = os.path.join(N, "Animation")
P_PROPS = os.path.join(ART, "Models", "Props")
P_WORLD = os.path.join(ART, "Models", "World")
P_CHARS = os.path.join(ART, "Models", "Characters")
P_RES = os.path.join(N, "Resources")
P_DATA = os.path.join(N, "Data")
P_AUDIO = os.path.join(N, "Audio")


def A(p):
    return os.path.join(ASSETS, p)


# ============================================================================ scripts
def script_metas():
    for p in glob.glob(os.path.join(N, "**", "*.cs"), recursive=True):
        write_meta(p, MONO_META)
    for p in glob.glob(os.path.join(N, "**", "*.shader"), recursive=True):
        write_meta(p, SHADER_META)


def script_guid(cls_file):
    p = glob.glob(os.path.join(N, "Scripts", "**", cls_file), recursive=True)
    assert p, cls_file
    return ensure_guid(p[0])


# ============================================================================ texturas
def textures():
    from PIL import Image, ImageDraw, ImageFilter
    os.makedirs(P_TEX, exist_ok=True)
    pal = os.path.join(P_TEX, "NindoPalette.png")
    PAL.write_png(pal)
    write_meta(pal, texture_meta(point=True, mips=True, compress=False, max_size=256))
    em = os.path.join(P_TEX, "NindoPalette_Emission.png")
    PAL.write_png(em, emissive_only=True)
    write_meta(em, texture_meta(point=True, mips=True, compress=False, max_size=256))
    # punto suave para partículas
    S = 64
    img = Image.new("RGBA", (S, S))
    px = img.load()
    for y in range(S):
        for x in range(S):
            dx, dy = (x + 0.5) / S * 2 - 1, (y + 0.5) / S * 2 - 1
            d = (dx * dx + dy * dy) ** 0.5
            a = max(0.0, 1 - d)
            a = a * a * (3 - 2 * a)
            px[x, y] = (255, 255, 255, int(a * 255))
    sd = os.path.join(P_TEX, "Nindo_SoftDot.png")
    img.save(sd)
    write_meta(sd, texture_meta(mips=True, compress=False, max_size=64))


def ui_sprites():
    """Recorta el arte del HUD del equipo (bandana roja y dragón dorado)."""
    from PIL import Image
    os.makedirs(P_UI, exist_ok=True)
    out = {}
    def crop_pair(frame_src, fill_src, name, pad=6):
        f = Image.open(A(frame_src)).convert("RGBA")
        l = Image.open(A(fill_src)).convert("RGBA")
        fb, lb = f.getbbox(), l.getbbox()
        ub = (min(fb[0], lb[0]) - pad, min(fb[1], lb[1]) - pad, max(fb[2], lb[2]) + pad, max(fb[3], lb[3]) + pad)
        fc = f.crop(ub)
        lc = l.crop((lb[0], ub[1], lb[2], ub[3]))
        fp = os.path.join(P_UI, f"{name}_Frame.png"); fc.save(fp)
        lp = os.path.join(P_UI, f"{name}_Fill.png"); lc.save(lp)
        W = ub[2] - ub[0]
        area = [(lb[0] - ub[0]) / W, 0.0, (lb[2] - lb[0]) / W, 1.0]
        for p in (fp, lp):
            write_meta(p, texture_meta(sprite=True, compress=False, max_size=2048), force=True)
        out[name] = (ensure_guid(fp), ensure_guid(lp), area)
    crop_pair("Sprites/EmptyHealthBar.png", "Sprites/HealthBarFull.png", "Health")
    crop_pair("Sprites/dragonBar.png", "Sprites/dragonFill.png", "Spirit")
    return out


def fonts():
    os.makedirs(P_FONTS, exist_ok=True)
    res = {}
    for src, name, fam in (("/opt/work/fonts/Shippori_Mincho_B1_wght-800.ttf", "ShipporiMinchoB1-ExtraBold.ttf", "Shippori Mincho B1"),
                           ("/opt/work/fonts/Zen_Maru_Gothic_wght-700.ttf", "ZenMaruGothic-Bold.ttf", "Zen Maru Gothic")):
        dst = os.path.join(P_FONTS, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)
        if os.path.exists(dst):
            write_meta(dst, font_meta(fam))
            res[name] = ensure_guid(dst)
    lic = os.path.join(P_FONTS, "OFL-README.txt")
    write(lic, "Shippori Mincho B1 y Zen Maru Gothic: SIL Open Font License 1.1 (Google Fonts).\nSe pueden usar y distribuir libremente con el juego.\n")
    write_meta(lic, TEXT_META)
    return res


# ============================================================================ materiales
URP_LIT = "933532a4fcc9baf4fa0491de14d08ed7"
URP_UNLIT = "650dd9526735d5b46b79224bc6e94025"
URP_PARTICLES_UNLIT = "0406db5a14f94604a8c57ccfbc9f3b46"
ASSET_VERSION_SCRIPT = "d0353a89b1f911e48b9e16bdc9f2e058"


def _tex(name, guid, scale=(1, 1)):
    t = "{fileID: 0}" if guid is None else f"{{fileID: 2800000, guid: {guid}, type: 3}}"
    return f"""    - {name}:
        m_Texture: {t}
        m_Scale: {{x: {scale[0]}, y: {scale[1]}}}
        m_Offset: {{x: 0, y: 0}}
"""


def _col(name, c):
    return f"    - {name}: {{r: {c[0]}, g: {c[1]}, b: {c[2]}, a: {c[3]}}}\n"


def material(path, name, shader_guid, textures, floats, colors, keywords=(), queue=-1, tags=None, disabled_passes=(), version_block=True, shader_fileid=4800000):
    texs = "".join(_tex(k, v) for k, v in textures.items())
    fl = "".join(f"    - {k}: {v}\n" for k, v in floats.items())
    cl = "".join(_col(k, v) for k, v in colors.items())
    kw = "\n".join(f"  - {k}" for k in keywords)
    tags = tags or {"RenderType": "Opaque"}
    tg = "\n".join(f"    {k}: {v}" for k, v in tags.items())
    dp = "\n".join(f"  - {p}" for p in disabled_passes)
    vb = f"""--- !u!114 &-{stable_id(name, 'v') % 9000000000000000000}
MonoBehaviour:
  m_ObjectHideFlags: 11
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: 0}}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {{fileID: 11500000, guid: {ASSET_VERSION_SCRIPT}, type: 3}}
  m_Name:
  m_EditorClassIdentifier:
  version: 7
""" if version_block else ""
    text = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
{vb}--- !u!21 &2100000
Material:
  serializedVersion: 8
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {name}
  m_Shader: {{fileID: {shader_fileid}, guid: {shader_guid}, type: 3}}
  m_Parent: {{fileID: 0}}
  m_ModifiedSerializedProperties: 0
  m_ValidKeywords:{chr(10) + kw if kw else ' []'}
  m_InvalidKeywords: []
  m_LightmapFlags: 4
  m_EnableInstancingVariants: 1
  m_DoubleSidedGI: 0
  m_CustomRenderQueue: {queue}
  stringTagMap:
{tg}
  disabledShaderPasses:{chr(10) + dp if dp else ' []'}
  m_LockedProperties:
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs:{chr(10) + texs if texs else ' []' + chr(10)}    m_Ints: []
    m_Floats:{chr(10) + fl if fl else ' []' + chr(10)}    m_Colors:{chr(10) + cl if cl else ' []' + chr(10)}  m_BuildTextureStacks: []
  m_AllowLocking: 1
"""
    write(path, text)
    write_meta(path, NATIVE_META.format(main=2100000))
    return ensure_guid(path)


def lit(path, name, base_tex, base_color=(1, 1, 1, 1), smooth=0.08, emission_tex=None, emission=(0, 0, 0, 1), cull=2, metallic=0.0, spec=0):
    kws = []
    if emission_tex is not None or emission[0] + emission[1] + emission[2] > 0:
        kws.append("_EMISSION")
    floats = {"_AlphaClip": 0, "_AlphaToMask": 0, "_Blend": 0, "_BlendModePreserveSpecular": 1, "_BumpScale": 1,
              "_ClearCoatMask": 0, "_ClearCoatSmoothness": 0, "_Cull": cull, "_Cutoff": 0.5, "_DetailAlbedoMapScale": 1,
              "_DetailNormalMapScale": 1, "_DstBlend": 0, "_DstBlendAlpha": 0, "_EnvironmentReflections": 1,
              "_GlossMapScale": 0, "_Glossiness": 0, "_GlossyReflections": 0, "_Metallic": metallic, "_OcclusionStrength": 1,
              "_Parallax": 0.005, "_QueueOffset": 0, "_ReceiveShadows": 1, "_Smoothness": smooth, "_SmoothnessTextureChannel": 0,
              "_SpecularHighlights": spec, "_SrcBlend": 1, "_SrcBlendAlpha": 1, "_Surface": 0, "_WorkflowMode": 1, "_ZWrite": 1}
    texs = {"_BaseMap": base_tex, "_BumpMap": None, "_DetailAlbedoMap": None, "_DetailMask": None, "_DetailNormalMap": None,
            "_EmissionMap": emission_tex, "_MainTex": base_tex, "_MetallicGlossMap": None, "_OcclusionMap": None,
            "_ParallaxMap": None, "_SpecGlossMap": None}
    colors = {"_BaseColor": base_color, "_Color": base_color, "_EmissionColor": emission, "_SpecColor": (0.2, 0.2, 0.2, 1)}
    return material(path, name, URP_LIT, texs, floats, colors, kws, -1)


def transparent(path, name, shader, tex, color, additive, particles=False):
    floats = {"_AlphaClip": 0, "_Blend": 2 if additive else 0, "_Cull": 0, "_Cutoff": 0.5, "_DstBlend": 1 if additive else 10,
              "_DstBlendAlpha": 1 if additive else 10, "_QueueOffset": 0, "_SrcBlend": 5, "_SrcBlendAlpha": 1, "_Surface": 1,
              "_ZWrite": 0, "_ColorMode": 0, "_SoftParticlesEnabled": 0, "_CameraFadingEnabled": 0, "_DistortionEnabled": 0,
              "_FlipbookBlending": 0}
    kws = ["_SURFACE_TYPE_TRANSPARENT"] + (["_BLENDMODE_ADD"] if additive else [])
    texs = {"_BaseMap": tex, "_MainTex": tex}
    colors = {"_BaseColor": color, "_Color": color}
    return material(path, name, shader, texs, floats, colors, kws, 3000, {"RenderType": "Transparent"}, ("DepthOnly", "SHADOWCASTER"))


def materials(tex):
    os.makedirs(P_MAT, exist_ok=True)
    palg = ensure_guid(os.path.join(P_TEX, "NindoPalette.png"))
    emg = ensure_guid(os.path.join(P_TEX, "NindoPalette_Emission.png"))
    dot = ensure_guid(os.path.join(P_TEX, "Nindo_SoftDot.png"))
    m = {}
    m["palette"] = lit(os.path.join(P_MAT, "Nindo_Palette.mat"), "Nindo_Palette", palg, smooth=0.12)
    m["emissive"] = lit(os.path.join(P_MAT, "Nindo_Emissive.mat"), "Nindo_Emissive", palg, smooth=0.2, emission_tex=emg, emission=(3.2, 3.2, 3.2, 1))
    m["foliage"] = lit(os.path.join(P_MAT, "Nindo_Foliage.mat"), "Nindo_Foliage", palg, smooth=0.05, cull=0)
    m["water"] = lit(os.path.join(P_MAT, "Nindo_Water.mat"), "Nindo_Water", palg, smooth=0.92, spec=1, base_color=(0.85, 0.95, 1.0, 1))
    m["trail"] = transparent(os.path.join(P_MAT, "Nindo_Trail.mat"), "Nindo_Trail", URP_PARTICLES_UNLIT, dot, (1, 0.92, 0.7, 1), True, True)
    m["ghost"] = transparent(os.path.join(P_MAT, "Nindo_Ghost.mat"), "Nindo_Ghost", URP_UNLIT, None, (1, 0.85, 0.45, 0.35), True)
    m["additive"] = transparent(os.path.join(P_MAT, "Nindo_FX_Additive.mat"), "Nindo_FX_Additive", URP_PARTICLES_UNLIT, dot, (1, 1, 1, 1), True, True)
    m["alpha"] = transparent(os.path.join(P_MAT, "Nindo_FX_Alpha.mat"), "Nindo_FX_Alpha", URP_PARTICLES_UNLIT, dot, (1, 1, 1, 1), False, True)
    m["flash"] = material(os.path.join(P_MAT, "Nindo_HitFlash.mat"), "Nindo_HitFlash", URP_UNLIT, {"_BaseMap": None, "_MainTex": None},
                          {"_Surface": 0, "_Cull": 2, "_ZWrite": 1, "_SrcBlend": 1, "_DstBlend": 0, "_QueueOffset": 0, "_AlphaClip": 0},
                          {"_BaseColor": (1, 0.97, 0.9, 1), "_Color": (1, 0.97, 0.9, 1)})
    wind_shader = ensure_guid(os.path.join(N, "Shaders", "NindoFoliage.shader"))
    m["foliage_wind"] = material(os.path.join(P_MAT, "Nindo_FoliageWind.mat"), "Nindo_FoliageWind", wind_shader, {"_BaseMap": palg},
                                 {"_WindStrength": 0.14, "_WindSpeed": 1.4, "_WindScale": 0.08, "_Flutter": 0.03, "_Wrap": 0.35},
                                 {"_BaseColor": (1, 1, 1, 1)}, version_block=False)
    water_shader = ensure_guid(os.path.join(N, "Shaders", "NindoWater.shader"))
    # _WaveHeight = WAVE_HEIGHT de Tools/Blender/world/build_world.py (FloatingBob lo lee del material)
    m["water_anim"] = material(os.path.join(P_MAT, "Nindo_WaterLowpoly.mat"), "Nindo_WaterLowpoly", water_shader, {},
                               {"_AlphaShallow": 0.55, "_AlphaDeep": 0.92, "_WaveHeight": 0.26, "_WaveSpeed": 1.0, "_Gloss": 128,
                                "_FacetBoost": 4.5, "_SpecStrength": 1.4, "_FoamThreshold": 0.64, "_SparkleAmount": 0.06,
                                "_CrestContrast": 0.35, "_RippleScale": 0.9, "_RippleStrength": 0.3, "_RippleSpeed": 1.0},
                               {"_ShallowColor": (0.13, 0.42, 0.47, 1), "_DeepColor": (0.02, 0.08, 0.17, 1), "_FoamColor": (0.78, 0.9, 0.95, 1),
                                "_SkyColor": (0.2, 0.3, 0.48, 1), "_SparkleColor": (1.0, 0.97, 0.85, 1), "_CrestColor": (0.36, 0.66, 0.68, 1)},
                               queue=2990, tags={"RenderType": "Transparent"}, version_block=False)
    sky_shader = ensure_guid(os.path.join(N, "Shaders", "NindoSky.shader"))
    m["sky"] = material(os.path.join(P_MAT, "Nindo_NightSky.mat"), "Nindo_NightSky", sky_shader, {},
                        {"_MoonSize": 0.045, "_MoonGlow": 0.6, "_StarDensity": 0.9965, "_StarBrightness": 1.6, "_CloudAmount": 0.35, "_Exposure": 1},
                        {"_ZenithColor": (0.015, 0.028, 0.08, 1), "_MidColor": (0.045, 0.08, 0.16, 1), "_HorizonColor": (0.13, 0.19, 0.27, 1),
                         "_GroundColor": (0.04, 0.055, 0.09, 1), "_MoonColor": (1, 0.97, 0.88, 1), "_MoonDir": (0.3, 0.42, 0.85, 0),
                         "_CloudColor": (0.1, 0.13, 0.2, 1)}, version_block=False)
    return m


# ============================================================================ personajes
def anim_guid(p):
    g = read_guid(A(p))
    assert g, f"falta {p}"
    return g


def clip_ref(p):
    return ref(anim_guid(p), 7400000, 2)


def anim_length(p):
    """Duración (s) de un .anim suelto: m_StopTime - m_StartTime de m_AnimationClipSettings."""
    txt = open(A(p), encoding="utf-8", errors="ignore").read()
    m = re.search(r"m_AnimationClipSettings:.*?m_StartTime: ([-\d.eE]+)\s+m_StopTime: ([-\d.eE]+)", txt, re.S)
    assert m, f"{p}: no tiene m_AnimationClipSettings"
    return round(float(m.group(2)) - float(m.group(1)), 4)


def clip(p):
    """(referencia, duración) de un .anim suelto."""
    return clip_ref(p), anim_length(p)


FBX_TIME_MODES = {1: 120, 2: 100, 3: 60, 4: 50, 5: 48, 6: 30, 7: 30, 8: 29.97, 9: 29.97, 10: 25, 11: 24,
                  12: 1000, 13: 23.976, 15: 96, 16: 72, 17: 59.94, 18: 119.88}


def fbx_fps(path):
    """Frame rate del FBX (GlobalSettings: TimeMode / CustomFrameRate): Unity mide firstFrame/lastFrame con él."""
    data = open(path, "rb").read(1 << 20)

    def prop(name):
        if data.startswith(b"Kaydara FBX Binary"):
            key = b"S" + struct.pack("<I", len(name)) + name.encode()
            i = data.find(key)
            if i < 0:
                return None
            i += len(key)
            for _ in range(3):  # tipo, etiqueta, flags
                if data[i:i + 1] != b"S":
                    return None
                i += 5 + struct.unpack_from("<I", data, i + 1)[0]
            t = data[i:i + 1]
            return struct.unpack_from("<i", data, i + 1)[0] if t == b"I" else struct.unpack_from("<d", data, i + 1)[0] if t == b"D" else None
        m = re.search(rb'"' + name.encode() + rb'",\s*"[^"]*",\s*"[^"]*",\s*"[^"]*",\s*([-\d.eE]+)', data)
        return float(m.group(1)) if m else None

    mode = prop("TimeMode")
    if mode is not None and int(mode) in FBX_TIME_MODES:
        return FBX_TIME_MODES[int(mode)]
    custom = prop("CustomFrameRate")
    return custom if custom and custom > 0 else 30.0


def fbx_clip_lengths(path):
    """{clip: duración (s)} de los clips definidos en el .fbx.meta (clipAnimations: firstFrame/lastFrame)."""
    meta = open(path + ".meta", encoding="utf-8", errors="ignore").read()
    sec = re.search(r"^    clipAnimations:\n((?:    - .*\n|      .*\n)*)", meta, re.M)
    out = {}
    if sec:
        fps = fbx_fps(path)
        for m in re.finditer(r"^    - serializedVersion: \d+\n      name: (.*)\n(?:      .*\n)*?      firstFrame: ([-\d.eE]+)\n      lastFrame: ([-\d.eE]+)$",
                             sec.group(1), re.M):
            out.setdefault(m.group(1).strip(), round((float(m.group(3)) - float(m.group(2))) / fps, 4))
    return out


def controller(path, name, states, locomotion):
    """states: {stateName: motionRef(str) | (motionRef, duración)}; locomotion: (idle, run) or None.
    Devuelve (guid, {stateName: duración del clip}) para la tabla de NindoContent."""
    sm_id = stable_id(name, "sm")
    objs = []
    child_states = []
    state_ids = {}
    lengths = {}
    states = dict(states)
    for sname, motion in list(states.items()):
        if isinstance(motion, tuple):
            states[sname], ln = motion
            if ln:
                lengths[sname] = ln
    if locomotion:
        locomotion = [m[0] if isinstance(m, tuple) else m for m in locomotion]
        bt_id = stable_id(name, "bt")
        objs.append(f"""--- !u!206 &{bt_id}
BlendTree:
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: Locomotion
  m_Childs:
  - serializedVersion: 2
    m_Motion: {locomotion[0]}
    m_Threshold: 0
    m_Position: {{x: 0, y: 0}}
    m_TimeScale: 1
    m_CycleOffset: 0
    m_DirectBlendParameter: Speed
    m_Mirror: 0
  - serializedVersion: 2
    m_Motion: {locomotion[1]}
    m_Threshold: 1
    m_Position: {{x: 0, y: 0}}
    m_TimeScale: 1
    m_CycleOffset: 0
    m_DirectBlendParameter: Speed
    m_Mirror: 0
  m_BlendParameter: Speed
  m_BlendParameterY: Speed
  m_MinThreshold: 0
  m_MaxThreshold: 1
  m_UseAutomaticThresholds: 0
  m_NormalizedBlendValues: 0
  m_BlendType: 0
""")
        states = dict(states)
        states = {"Locomotion": f"{{fileID: {bt_id}}}", **states}
    for i, (sname, motion) in enumerate(states.items()):
        sid = stable_id(name, "state", sname)
        state_ids[sname] = sid
        child_states.append(f"""  - serializedVersion: 1
    m_State: {{fileID: {sid}}}
    m_Position: {{x: {300 + (i % 3) * 250}, y: {60 + (i // 3) * 70}, z: 0}}""")
        objs.append(f"""--- !u!1102 &{sid}
AnimatorState:
  serializedVersion: 6
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {sname}
  m_Speed: 1
  m_CycleOffset: 0
  m_Transitions: []
  m_StateMachineBehaviours: []
  m_Position: {{x: 50, y: 50, z: 0}}
  m_IKOnFeet: 0
  m_WriteDefaultValues: 1
  m_Mirror: 0
  m_SpeedParameterActive: 0
  m_MirrorParameterActive: 0
  m_CycleOffsetParameterActive: 0
  m_TimeParameterActive: 0
  m_Motion: {motion}
  m_Tag:
  m_SpeedParameter:
  m_MirrorParameter:
  m_CycleOffsetParameter:
  m_TimeParameter:
""")
    default = state_ids.get("Locomotion", next(iter(state_ids.values())))
    head = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!91 &9100000
AnimatorController:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: {name}
  serializedVersion: 5
  m_AnimatorParameters:
  - m_Name: Speed
    m_Type: 1
    m_DefaultFloat: 0
    m_DefaultInt: 0
    m_DefaultBool: 0
    m_Controller: {{fileID: 9100000}}
  m_AnimatorLayers:
  - serializedVersion: 5
    m_Name: Base Layer
    m_StateMachine: {{fileID: {sm_id}}}
    m_Mask: {{fileID: 0}}
    m_Motions: []
    m_Behaviours: []
    m_BlendingMode: 0
    m_SyncedLayerIndex: -1
    m_DefaultWeight: 0
    m_IKPass: 0
    m_SyncedLayerAffectsTiming: 0
    m_Controller: {{fileID: 9100000}}
--- !u!1107 &{sm_id}
AnimatorStateMachine:
  serializedVersion: 6
  m_ObjectHideFlags: 1
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_Name: Base Layer
  m_ChildStates:
{chr(10).join(child_states)}
  m_ChildStateMachines: []
  m_AnyStateTransitions: []
  m_EntryTransitions: []
  m_StateMachineTransitions: {{}}
  m_StateMachineBehaviours: []
  m_AnyStatePosition: {{x: 50, y: 20, z: 0}}
  m_EntryPosition: {{x: 50, y: 120, z: 0}}
  m_ExitPosition: {{x: 800, y: 120, z: 0}}
  m_ParentStateMachinePosition: {{x: 800, y: 20, z: 0}}
  m_DefaultState: {{fileID: {default}}}
"""
    write(path, head + "".join(objs))
    write_meta(path, NATIVE_META.format(main=9100000))
    return ensure_guid(path), lengths


MINIJEFE_CLIPS = [
    # (clip name, take, first, last, loop)   frames = rango de Blender - 1
    ("Idle", "Armature|Idle", 0, 79, True),
    ("Run", "Armature|Run", 0, 80, True),
    ("Combo1", "Armature|Combo1", 0, 36, False),
    ("Combo2", "Armature|Combo2", 0, 39, False),
    ("Combo3", "Armature|Combo3", 0, 26, False),
    ("Heavy", "Armature|HeavyAtack", 0, 89, False),
    ("Spin", "Armature|Spinn", 0, 62, False),
    ("StunSpin", "Armature|StunSpinn", 0, 79, True),
    ("Parried", "Armature|parryed", 0, 56, False),
    ("Spotted", "Armature|EnemySpotted", 0, 77, False),
    ("Intro", "Armature|Firstinteraction", 0, 77, False),
]


def patch_minijefe_meta():
    """Agrega definiciones de clips con internalID fijos al FBX del Minijefe (Gorō)."""
    p = A("Models/Minijefe.fbx.meta")
    txt = open(p).read()
    if "name: Combo1" in txt and "takeName: Armature|Combo1" in txt:
        return
    clips = ""
    for name, take, first, last, loop in MINIJEFE_CLIPS:
        cid = -stable_id("minijefe", name) if name != "Idle" else stable_id("minijefe", name)
        clips += f"""    - serializedVersion: 16
      name: {name}
      takeName: {take}
      internalID: {cid}
      firstFrame: {first}
      lastFrame: {last}
      wrapMode: 0
      orientationOffsetY: 0
      level: 0
      cycleOffset: 0
      loop: 0
      hasAdditiveReferencePose: 0
      loopTime: {1 if loop else 0}
      loopBlend: 0
      loopBlendOrientation: 0
      loopBlendPositionY: 0
      loopBlendPositionXZ: 0
      keepOriginalOrientation: 0
      keepOriginalPositionY: 1
      keepOriginalPositionXZ: 0
      heightFromFeet: 0
      mirror: 0
      bodyMask: 01000000010000000100000001000000010000000100000001000000010000000100000001000000010000000100000001000000
      curves: []
      events: []
      transformMask: []
      maskType: 3
      maskSource: {{instanceID: 0}}
      additiveReferencePoseFrame: 0
"""
    txt = txt.replace("    clipAnimations: []\n", "    clipAnimations:\n" + clips, 1)
    open(p, "w", newline="\n").write(txt)


def minijefe_clip(name):
    cid = -stable_id("minijefe", name) if name != "Idle" else stable_id("minijefe", name)
    return ref(read_guid(A("Models/Minijefe.fbx")), cid, 3)


def controllers():
    os.makedirs(P_ANIM, exist_ok=True)
    c = {}
    K = "Animations teo/"
    c["kaito"] = controller(os.path.join(P_ANIM, "Kaito.controller"), "Kaito", {
        "Attack1": clip(K + "Attackk1.anim"), "Attack2": clip(K + "Attackk2.anim"), "Attack3": clip(K + "Attackk3.anim"),
        "ParryStance": clip(K + "TrueBlock.anim"), "ParrySuccess": clip(K + "Parried.anim"), "Blocked": clip(K + "Blockk.anim"),
        "Hit": clip("Preiliminar Kaito/Stunned.anim"), "Dash": clip(K + "Dash.anim"), "Finisher": clip(K + "Finishing.anim"),
        "Idle": clip(K + "Idle.anim"),
    }, (clip(K + "Idle.anim"), clip(K + "AuraRun.anim")))
    NB = "Characters/Ninja/body/"
    c["ninja"] = controller(os.path.join(P_ANIM, "Ninja.controller"), "Ninja", {
        "Attack1": clip(NB + "Attack 1.anim"), "Attack2": clip(NB + "animation/Attack 2.anim"), "Attack3": clip(NB + "animation/Attack 3.anim"),
        "Hit": clip(NB + "animation/Damaged.anim"), "Exhausted": clip(NB + "animation/Exausto.anim"), "Guard": clip(NB + "animation/Block.anim"),
        "Counter": clip(NB + "animation/ParryUltimate.anim"), "Spotted": clip(NB + "EnemySpotted.anim"), "Death": clip(NB + "animation/Stuned.anim"),
        "Idle": clip(NB + "animation/Idle.anim"),
    }, (clip(NB + "animation/Idle.anim"), clip(NB + "animation/RUN.anim")))
    S = "Characters/Sumo/"
    c["sumo"] = controller(os.path.join(P_ANIM, "Sumo.controller"), "Sumo", {
        "Attack1": clip(S + "Attack1.anim"), "Attack2": clip(S + "Attack2.anim"), "Attack3": clip(S + "Attack3.anim"),
        "Special": clip(S + "SpecialAttack.anim"), "Hit": clip(S + "Blocked.anim"), "Exhausted": clip(S + "Cansado.anim"),
        "Spotted": clip(S + "EnemySpotted.anim"), "Idle": clip(S + "Idle.anim"),
    }, (clip(S + "Idle.anim"), clip(S + "Walk.anim")))
    patch_minijefe_meta()
    mj = fbx_clip_lengths(A("Models/Minijefe.fbx"))
    c["goro"] = controller(os.path.join(P_ANIM, "Goro.controller"), "Goro",
                           {n: (minijefe_clip(n), mj.get(n)) for n, *_ in MINIJEFE_CLIPS if n not in ("Run",)},
                           (minijefe_clip("Idle"), minijefe_clip("Run")))
    gp = os.path.join(P_CHARS, "Grandpa.fbx")
    if os.path.exists(gp):
        g = ensure_guid(gp)
        gl = fbx_clip_lengths(gp)
        idle = (ref(g, stable_id("grandpa", "Idle"), 3), gl.get("Idle"))
        kid = (ref(g, stable_id("grandpa", "Kidnap"), 3), gl.get("Kidnap"))
        c["grandpa"] = controller(os.path.join(P_ANIM, "Grandpa.controller"), "Grandpa", {"Idle": idle, "Kidnap": kid}, (idle, idle))
    return c


def character_fbx_metas():
    gp = os.path.join(P_CHARS, "Grandpa.fbx")
    if os.path.exists(gp):
        info = json.load(open(gp + ".json")) if os.path.exists(gp + ".json") else {"frames": 75}
        clips = [dict(name="Idle", take="Armature|inicio", id=stable_id("grandpa", "Idle"), first=0, last=1, loop=True),
                 dict(name="Kidnap", take="Armature|inicio", id=stable_id("grandpa", "Kidnap"), first=0, last=info["frames"] - 1, loop=False)]
        write_meta(gp, model_meta(anim_type=2, import_anim=True, clips=clips, readable=False), force=True)
    write_meta(os.path.join(P_CHARS, "Grandpa.fbx.json"), TEXT_META)


# ============================================================================ props y mundo
def model_metas(mats):
    remap = {"Nindo_Palette": mats["palette"], "Nindo_Emissive": mats["emissive"], "Nindo_Foliage": mats["foliage"], "Nindo_Water": mats["water"]}
    props, zones = {}, []
    for p in sorted(glob.glob(os.path.join(P_PROPS, "*.fbx"))):
        write_meta(p, model_meta(remap=remap, readable=True), force=True)
        props[os.path.splitext(os.path.basename(p))[0]] = ensure_guid(p)
    for p in sorted(glob.glob(os.path.join(P_WORLD, "*.fbx"))):
        write_meta(p, model_meta(remap=remap, readable=True), force=True)
        zones.append(ensure_guid(p))
    return props, zones


def props_manifest():
    out = {"props": []}
    for mf in sorted(glob.glob(os.path.join(REPO, "Tools", "Blender", "out", "manifest_*.json"))):
        for pid, m in json.load(open(mf)).items():
            if pid.startswith("zz_"):
                continue
            e = {"id": pid, "collider": m.get("collider"), "tags": m.get("tags", []), "size": m.get("size")}
            if "light_offset" in m:
                e["light_offset"] = m["light_offset"]
            out["props"].append(e)
    os.makedirs(P_DATA, exist_ok=True)
    p = os.path.join(P_DATA, "PropsManifest.json")
    write(p, json.dumps(out, indent=1))
    write_meta(p, TEXT_META)
    return ensure_guid(p)


# ============================================================================ audio
def audio_entries():
    """Mapea claves de sonido a clips (del equipo + generados en Assets/Nindo/Audio)."""
    def g(p):
        full = A(p)
        return read_guid(full) if os.path.exists(full) else None
    team = {
        "swing": ["Audios/SwordSwing.wav"], "enemy_swing": ["Audios/SwordSwing.wav"], "enemy_swing_heavy": ["Audios/SwordSwing.wav"],
        "clang": ["Audios/SwordClash.wav"], "parry": ["Audios/SwordClash.wav"], "hurt": ["Audios/Hurt.wav"],
        "dash": ["Audios/Dash.wav"], "finisher_hit": ["Audios/Finisher.flac"], "ui_select": ["Audios/Boton.mp3"],
        "step": ["Audios/Footsteps.wav"],
    }
    gen = {}
    for p in glob.glob(os.path.join(P_AUDIO, "Sfx", "*.wav")):
        key = os.path.splitext(os.path.basename(p))[0]
        key = re.sub(r"_\d+$", "", key)
        gen.setdefault(key, []).append(rel(p)[len("Assets/"):])
    sfx = {}
    for k, v in team.items():
        sfx[k] = v
    for k, v in gen.items():
        sfx.setdefault(k, [])
        sfx[k] = sorted(set(sfx[k] + v)) if k not in ("step",) else sorted(v)
    vols = {"swing": 0.8, "hurt": 0.9, "ui_select": 0.6, "hit": 0.9, "clang": 0.85}
    entries = []
    for k in sorted(sfx):
        clips = [g(p) for p in sfx[k] if g(p)]
        if clips:
            entries.append((k, clips, vols.get(k, 1.0), 0.06, k not in ("ui_select", "ui_move", "ui_open", "ui_close", "ui_start", "area_title", "dialogue", "denied", "lock", "seal")))
    music = {}
    for p in glob.glob(os.path.join(P_AUDIO, "Music", "*.*")):
        if p.endswith(".meta"):
            continue
        key = os.path.splitext(os.path.basename(p))[0]
        music[key] = [read_guid(p)]
    # "explore" es el tema genérico (fallback de las zonas): reutiliza el del jardín
    if "explore" not in music and "explore_garden" in music:
        music["explore"] = music["explore_garden"]
    amb = {}
    for p in glob.glob(os.path.join(P_AUDIO, "Ambience", "*.*")):
        if not p.endswith(".meta"):
            amb[os.path.splitext(os.path.basename(p))[0]] = [read_guid(p)]
    return entries, music, amb


# ============================================================================ NindoContent
def yaml_entries_audio(entries):
    out = ""
    for k, clips, vol, pv, spatial in entries:
        cl = "\n".join(f"    - {{fileID: 8300000, guid: {c}, type: 3}}" for c in clips)
        out += f"""  - key: {k}
    clips:
{cl}
    volume: {vol}
    pitchVariance: {pv}
    spatial: {1 if spatial else 0}
"""
    return ("\n" + out) if out else " []\n"


def content_asset(mats, ctrls, props, zones, manifest, sprites, fonts_g, audio):
    os.makedirs(P_RES, exist_ok=True)
    path = os.path.join(P_RES, "NindoContent.asset")
    sg = script_guid("NindoContent.cs")
    MODEL = 919132149155446097

    def chars():
        rows = []
        defs = [
            ("kaito", read_guid(A("Animations teo/kaitooo.fbx")), ctrls["kaito"], 1.5),
            ("kage", read_guid(A("Animations teo/kaitooo.fbx")), ctrls["kaito"], 1.6),
            ("ninja", read_guid(A("Models/Ninja/Ninja 1.fbx")), ctrls["ninja"], 1.7),
            ("sumo", read_guid(A("Characters/Sumo/luchadorsumo.fbx")), ctrls["sumo"], 2.5),
            ("goro", read_guid(A("Models/Minijefe.fbx")), ctrls["goro"], 3.2),
        ]
        if "grandpa" in ctrls:
            defs.append(("grandpa", ensure_guid(os.path.join(P_CHARS, "Grandpa.fbx")), ctrls["grandpa"], 1.45))
            defs.append(("kidnap", ensure_guid(os.path.join(P_CHARS, "Grandpa.fbx")), ctrls["grandpa"], 1.45))
        for cid, mg, (cg, lens), h in defs:
            # duración del clip de cada estado (CharacterAnimator.Length busca por estado, no por clip)
            names = "".join(f"\n    - {n}" for n in lens) or " []"
            secs = "".join(f"\n    - {lens[n]}" for n in lens) or " []"
            rows.append(f"""  - id: {cid}
    model: {ref(mg, MODEL, 3)}
    controller: {ref(cg, 9100000, 2)}
    height: {h}
    materialOverrides: []
    stateNames:{names}
    stateLengths:{secs}""")
        return "\n".join(rows)

    prop_rows = ("\n" + "\n".join(f"  - id: {pid}\n    model: {ref(g, MODEL, 3)}" for pid, g in sorted(props.items()))) if props else " []"
    zone_rows = ("\n" + "\n".join(f"  - {ref(g, MODEL, 3)}" for g in zones)) if zones else " []"

    def vfx(name):
        g = read_guid(A(f"vfx Graph/{name}.vfx"))
        return ref(g, 8926484042661614526, 3)

    def tex2d(g):
        return ref(g, 2800000, 3)

    def sprite(g):
        return ref(g, 21300000, 3)

    sfx, music, amb = audio
    mus_entries = [(k, v, 0.8 if k != "menu" else 0.7, 0, False) for k, v in sorted(music.items())]
    amb_entries = [(k, v, 0.45, 0, False) for k, v in sorted(amb.items())]
    eyes_closed = read_guid(A("Sprites/Menunindo.png"))
    eyes_open = read_guid(A("Sprites/Menunindo (1).png"))
    text = f"""%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400000
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: 0}}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {{fileID: 11500000, guid: {sg}, type: 3}}
  m_Name: NindoContent
  m_EditorClassIdentifier:
  characters:
{chars()}
  zones:{zone_rows}
  props:{prop_rows}
  propsManifest: {ref(manifest, 4900000, 3)}
  worldData: {{fileID: 0}}
  paletteTexture: {tex2d(ensure_guid(os.path.join(P_TEX, 'NindoPalette.png')))}
  paletteMaterial: {ref(mats['palette'], 2100000, 2)}
  emissiveMaterial: {ref(mats['emissive'], 2100000, 2)}
  foliageMaterial: {ref(mats['foliage'], 2100000, 2)}
  foliageWindMaterial: {ref(mats['foliage_wind'], 2100000, 2)}
  waterAnimatedMaterial: {ref(mats['water_anim'], 2100000, 2)}
  useAnimatedWater: 1
  useFoliageWind: 1
  waterMaterial: {ref(mats['water'], 2100000, 2)}
  trailMaterial: {ref(mats['trail'], 2100000, 2)}
  ghostMaterial: {ref(mats['ghost'], 2100000, 2)}
  flashMaterial: {ref(mats['flash'], 2100000, 2)}
  additiveMaterial: {ref(mats['additive'], 2100000, 2)}
  alphaMaterial: {ref(mats['alpha'], 2100000, 2)}
  skyboxMaterial: {ref(mats['sky'], 2100000, 2)}
  vfxParry: {vfx('ParryEffect')}
  vfxHit: {vfx('HitAttack')}
  vfxImpact: {vfx('Inpact')}
  vfxDamaged: {vfx('Damaged')}
  vfxSlay: {vfx('Slay')}
  vfxSlash: {vfx('vfxGraph_Slash')}
  vfxLines: {vfx('LinesAttack')}
  vfxAura: {vfx('Aura')}
  sfx:{yaml_entries_audio(sfx)}  music:{yaml_entries_audio(mus_entries)}  ambience:{yaml_entries_audio(amb_entries)}  healthFill: {sprite(sprites['Health'][1])}
  healthFrame: {sprite(sprites['Health'][0])}
  spiritFill: {sprite(sprites['Spirit'][1])}
  spiritFrame: {sprite(sprites['Spirit'][0])}
  healthFillArea: {{x: {sprites['Health'][2][0]}, y: 0, width: {sprites['Health'][2][2]}, height: 1}}
  spiritFillArea: {{x: {sprites['Spirit'][2][0]}, y: 0, width: {sprites['Spirit'][2][2]}, height: 1}}
  menuEyesClosed: {sprite(eyes_closed)}
  menuEyesOpen: {sprite(eyes_open)}
  logo: {{fileID: 0}}
  titleFont: {ref(fonts_g.get('ShipporiMinchoB1-ExtraBold.ttf'), 12800000, 3)}
  bodyFont: {ref(fonts_g.get('ZenMaruGothic-Bold.ttf'), 12800000, 3)}
"""
    write(path, text)
    write_meta(path, NATIVE_META.format(main=11400000))
    return ensure_guid(path)


# ============================================================================ escenas
SCENE_HEADER = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!29 &1
OcclusionCullingSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_OcclusionBakeSettings:
    smallestOccluder: 5
    smallestHole: 0.25
    backfaceThreshold: 100
  m_SceneGUID: 00000000000000000000000000000000
  m_OcclusionCullingData: {{fileID: 0}}
--- !u!104 &2
RenderSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 9
  m_Fog: 1
  m_FogColor: {{r: 0.07, g: 0.1, b: 0.17, a: 1}}
  m_FogMode: 3
  m_FogDensity: 0.012
  m_LinearFogStart: 0
  m_LinearFogEnd: 300
  m_AmbientSkyColor: {{r: 0.22, g: 0.28, b: 0.42, a: 1}}
  m_AmbientEquatorColor: {{r: 0.12, g: 0.15, b: 0.22, a: 1}}
  m_AmbientGroundColor: {{r: 0.05, g: 0.05, b: 0.07, a: 1}}
  m_AmbientIntensity: 1
  m_AmbientMode: 1
  m_SubtractiveShadowColor: {{r: 0.42, g: 0.478, b: 0.627, a: 1}}
  m_SkyboxMaterial: {sky}
  m_HaloStrength: 0.5
  m_FlareStrength: 1
  m_FlareFadeSpeed: 3
  m_HaloTexture: {{fileID: 0}}
  m_SpotCookie: {{fileID: 10001, guid: 0000000000000000e000000000000000, type: 0}}
  m_DefaultReflectionMode: 0
  m_DefaultReflectionResolution: 128
  m_ReflectionBounces: 1
  m_ReflectionIntensity: 1
  m_CustomReflection: {{fileID: 0}}
  m_Sun: {{fileID: 0}}
  m_IndirectSpecularColor: {{r: 0, g: 0, b: 0, a: 1}}
  m_UseRadianceAmbientProbe: 0
--- !u!157 &3
LightmapSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 12
  m_GIWorkflowMode: 1
  m_GISettings:
    serializedVersion: 2
    m_BounceScale: 1
    m_IndirectOutputScale: 1
    m_AlbedoBoost: 1
    m_EnvironmentLightingMode: 0
    m_EnableBakedLightmaps: 0
    m_EnableRealtimeLightmaps: 0
  m_LightmapEditorSettings:
    serializedVersion: 12
    m_Resolution: 2
    m_BakeResolution: 40
    m_AtlasSize: 1024
    m_AO: 0
    m_AOMaxDistance: 1
    m_CompAOExponent: 1
    m_CompAOExponentDirect: 0
    m_ExtractAmbientOcclusion: 0
    m_Padding: 2
    m_LightmapParameters: {{fileID: 0}}
    m_LightmapsBakeMode: 1
    m_TextureCompression: 1
    m_FinalGather: 0
    m_FinalGatherFiltering: 1
    m_FinalGatherRayCount: 256
    m_ReflectionCompression: 2
    m_MixedBakeMode: 2
    m_BakeBackend: 1
    m_PVRSampling: 1
    m_PVRDirectSampleCount: 32
    m_PVRSampleCount: 512
    m_PVRBounces: 2
    m_PVREnvironmentSampleCount: 256
    m_PVREnvironmentReferencePointCount: 2048
    m_PVRFilteringMode: 1
    m_PVRDenoiserTypeDirect: 1
    m_PVRDenoiserTypeIndirect: 1
    m_PVRDenoiserTypeAO: 1
    m_PVRFilterTypeDirect: 0
    m_PVRFilterTypeIndirect: 0
    m_PVRFilterTypeAO: 0
    m_PVREnvironmentMIS: 1
    m_PVRCulling: 1
    m_PVRFilteringGaussRadiusDirect: 1
    m_PVRFilteringGaussRadiusIndirect: 5
    m_PVRFilteringGaussRadiusAO: 2
    m_PVRFilteringAtrousPositionSigmaDirect: 0.5
    m_PVRFilteringAtrousPositionSigmaIndirect: 2
    m_PVRFilteringAtrousPositionSigmaAO: 1
    m_ExportTrainingData: 0
    m_TrainingDataDestination: TrainingData
    m_LightProbeSampleCountMultiplier: 4
  m_LightingDataAsset: {{fileID: 0}}
  m_LightingSettings: {{fileID: 0}}
--- !u!196 &4
NavMeshSettings:
  serializedVersion: 2
  m_ObjectHideFlags: 0
  m_BuildSettings:
    serializedVersion: 3
    agentTypeID: 0
    agentRadius: 0.5
    agentHeight: 2
    agentSlope: 45
    agentClimb: 0.4
    ledgeDropHeight: 0
    maxJumpAcrossDistance: 0
    minRegionArea: 2
    manualCellSize: 0
    cellSize: 0.16666667
    manualTileSize: 0
    tileSize: 256
    buildHeightMesh: 0
    maxJobWorkers: 0
    preserveTilesOutsideBounds: 0
    debug:
      m_Flags: 0
  m_NavMeshData: {{fileID: 0}}
"""


def scene(path, name, script_guid, sky_guid, fields=""):
    go, tr, mb = stable_id(name, "go"), stable_id(name, "tr"), stable_id(name, "mb")
    text = SCENE_HEADER.format(sky=ref(sky_guid, 2100000, 2)) + f"""--- !u!1 &{go}
GameObject:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  serializedVersion: 6
  m_Component:
  - component: {{fileID: {tr}}}
  - component: {{fileID: {mb}}}
  m_Layer: 0
  m_Name: {name}
  m_TagString: Untagged
  m_Icon: {{fileID: 0}}
  m_NavMeshLayer: 0
  m_StaticEditorFlags: 0
  m_IsActive: 1
--- !u!4 &{tr}
Transform:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {go}}}
  serializedVersion: 2
  m_LocalRotation: {{x: 0, y: 0, z: 0, w: 1}}
  m_LocalPosition: {{x: 0, y: 0, z: 0}}
  m_LocalScale: {{x: 1, y: 1, z: 1}}
  m_ConstrainProportionsScale: 0
  m_Children: []
  m_Father: {{fileID: 0}}
  m_LocalEulerAnglesHint: {{x: 0, y: 0, z: 0}}
--- !u!114 &{mb}
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {{fileID: 0}}
  m_PrefabInstance: {{fileID: 0}}
  m_PrefabAsset: {{fileID: 0}}
  m_GameObject: {{fileID: {go}}}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {{fileID: 11500000, guid: {script_guid}, type: 3}}
  m_Name:
  m_EditorClassIdentifier:
{fields}--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_ObjectHideFlags: 0
  m_Roots:
  - {{fileID: {tr}}}
"""
    write(path, text)
    write_meta(path, DEFAULT_META)
    return ensure_guid(path)


def scenes(mats):
    sd = os.path.join(N, "Scenes")
    os.makedirs(sd, exist_ok=True)
    menu = scene(os.path.join(sd, "Menu.unity"), "Menu", script_guid("MenuBootstrap.cs"), mats["sky"])
    game = scene(os.path.join(sd, "Nindo.unity"), "Nindo", script_guid("GameBootstrap.cs"), mats["sky"],
                 "  debugStartCheckpoint: \n  debugUnlockAll: 0\n  debugSkipIntro: 0\n")
    bs = os.path.join(os.path.dirname(ASSETS), "ProjectSettings", "EditorBuildSettings.asset")
    txt = open(bs).read()
    txt = re.sub(r"  m_Scenes:\n(  - .*\n(    .*\n)*)*", f"""  m_Scenes:
  - enabled: 1
    path: Assets/Nindo/Scenes/Menu.unity
    guid: {menu}
  - enabled: 1
    path: Assets/Nindo/Scenes/Nindo.unity
    guid: {game}
""", txt)
    open(bs, "w", newline="\n").write(txt)


# ============================================================================ main
def main():
    for d in (P_TEX, P_MAT, P_UI, P_FONTS, P_ANIM, P_PROPS, P_WORLD, P_CHARS, P_RES, P_DATA, P_AUDIO,
              os.path.join(P_AUDIO, "Sfx"), os.path.join(P_AUDIO, "Music"), os.path.join(P_AUDIO, "Ambience")):
        os.makedirs(d, exist_ok=True)
    script_metas()
    textures()
    sprites = ui_sprites()
    fonts_g = fonts()
    mats = materials(None)
    character_fbx_metas()
    ctrls = controllers()
    props, zones = model_metas(mats)
    manifest = props_manifest()
    audio = audio_entries()
    for p in glob.glob(os.path.join(P_AUDIO, "**", "*.wav"), recursive=True) + glob.glob(os.path.join(P_AUDIO, "**", "*.ogg"), recursive=True):
        write_meta(p, audio_meta(stream="Music" in p or "Ambience" in p, mono="Sfx" in p))
    audio = audio_entries()
    content_asset(mats, ctrls, props, zones, manifest, sprites, fonts_g, audio)
    scenes(mats)
    # metas de carpetas
    for dp, dn, fn in os.walk(N):
        ensure_folder_metas(dp)
    ensure_folder_metas(os.path.join(ASSETS, "_Legacy"))
    ensure_folder_metas(os.path.join(ASSETS, "Characters"))
    for dp, dn, fn in os.walk(os.path.join(ASSETS, "_Legacy")):
        ensure_folder_metas(dp)
    print(f"props={len(props)} zones={len(zones)} sfx={len(audio[0])} music={len(audio[1])} ambience={len(audio[2])}")


if __name__ == "__main__":
    main()
