"""Helpers to write Unity YAML assets and .meta files from Python.

All GUIDs created here are deterministic (md5 of the asset path), so running the
generators again produces the same GUIDs and references stay valid."""
import hashlib, os, re, json

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(REPO, "Nindo", "Assets")


def rel(path):
    return os.path.relpath(path, os.path.dirname(ASSETS)).replace(os.sep, "/")


def guid_for(path):
    return hashlib.md5(("nindo:" + rel(path)).encode()).hexdigest()


def read_guid(path):
    meta = path + ".meta"
    if not os.path.exists(meta):
        return None
    m = re.search(r"^guid: (\w+)", open(meta, encoding="utf-8", errors="ignore").read(), re.M)
    return m.group(1) if m else None


def ensure_guid(path):
    return read_guid(path) or guid_for(path)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_meta(path, body, force=False):
    """body = importer section (without fileFormatVersion/guid lines)."""
    meta = path + ".meta"
    if os.path.exists(meta) and not force:
        return read_guid(path)
    g = read_guid(path) or guid_for(path)
    write(meta, f"fileFormatVersion: 2\nguid: {g}\n{body}")
    return g


def ensure_folder_metas(path):
    """Creates folder .meta files for every folder between Assets and path."""
    path = os.path.abspath(path)
    while path.startswith(ASSETS) and path != ASSETS:
        if os.path.isdir(path) and not os.path.exists(path + ".meta"):
            write(path + ".meta", f"fileFormatVersion: 2\nguid: {guid_for(path)}\nfolderAsset: yes\nDefaultImporter:\n  externalObjects: {{}}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n")
        path = os.path.dirname(path)


MONO_META = """MonoImporter:
  externalObjects: {}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {instanceID: 0}
  userData:
  assetBundleName:
  assetBundleVariant:
"""

NATIVE_META = """NativeFormatImporter:
  externalObjects: {{}}
  mainObjectFileID: {main}
  userData:
  assetBundleName:
  assetBundleVariant:
"""

DEFAULT_META = """DefaultImporter:
  externalObjects: {}
  userData:
  assetBundleName:
  assetBundleVariant:
"""

TEXT_META = """TextScriptImporter:
  externalObjects: {}
  userData:
  assetBundleName:
  assetBundleVariant:
"""

SHADER_META = """ShaderImporter:
  externalObjects: {}
  defaultTextures: []
  nonModifiableTextures: []
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def font_meta(name):
    return f"""TrueTypeFontImporter:
  externalObjects: {{}}
  serializedVersion: 4
  fontSize: 16
  forceTextureCase: -2
  characterSpacing: 0
  characterPadding: 1
  includeFontData: 1
  fontNames:
  - {name}
  fallbackFontReferences: []
  customCharacters:
  fontRenderingMode: 0
  ascentCalculationMode: 1
  useLegacyBoundsCalculation: 0
  shouldRoundAdvanceValue: 1
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def audio_meta(stream=False, mono=False):
    return f"""AudioImporter:
  externalObjects: {{}}
  serializedVersion: 7
  defaultSettings:
    serializedVersion: 2
    loadType: {2 if stream else 0}
    sampleRateSetting: 0
    sampleRateOverride: 44100
    compressionFormat: 1
    quality: {0.7 if stream else 0.6}
    conversionMode: 0
    preloadAudioData: {0 if stream else 1}
  platformSettingOverrides: {{}}
  forceToMono: {1 if mono else 0}
  normalize: 0
  loadInBackground: {1 if stream else 0}
  ambisonic: 0
  3D: 1
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def texture_meta(sprite=False, point=False, mips=True, srgb=True, max_size=2048, compress=True, readable=False, wrap_clamp=True, alpha_transparency=True, border=(0, 0, 0, 0)):
    """border = 9-slice del sprite en píxeles (izquierda, abajo, derecha, arriba)."""
    plat = ""
    for target in ("DefaultTexturePlatform", "Standalone"):
        plat += f"""  - serializedVersion: 3
    buildTarget: {target}
    maxTextureSize: {max_size}
    resizeAlgorithm: 0
    textureFormat: -1
    textureCompression: {1 if compress else 0}
    compressionQuality: 50
    crunchedCompression: 0
    allowsAlphaSplitting: 0
    overridden: 0
    ignorePlatformSupport: 0
    androidETC2FallbackOverride: 0
    forceMaximumCompressionQuality_BC6H_BC7: 0
"""
    return f"""TextureImporter:
  internalIDToNameTable: []
  externalObjects: {{}}
  serializedVersion: 12
  mipmaps:
    mipMapMode: 0
    enableMipMap: {1 if (mips and not sprite) else 0}
    sRGBTexture: {1 if srgb else 0}
    linearTexture: 0
    fadeOut: 0
    borderMipMap: 0
    mipMapsPreserveCoverage: 0
    alphaTestReferenceValue: 0.5
    mipMapFadeDistanceStart: 1
    mipMapFadeDistanceEnd: 3
  bumpmap:
    convertToNormalMap: 0
    externalNormalMap: 0
    heightScale: 0.25
    normalMapFilter: 0
    flipGreenChannel: 0
  isReadable: {1 if readable else 0}
  streamingMipmaps: 0
  streamingMipmapsPriority: 0
  vTOnly: 0
  ignoreMipmapLimit: 0
  grayScaleToAlpha: 0
  generateCubemap: 6
  cubemapConvolution: 0
  seamlessCubemap: 0
  textureFormat: 1
  maxTextureSize: {max_size}
  textureSettings:
    serializedVersion: 2
    filterMode: {0 if point else 1}
    aniso: 1
    mipBias: 0
    wrapU: {1 if wrap_clamp else 0}
    wrapV: {1 if wrap_clamp else 0}
    wrapW: 0
  nPOTScale: {0 if sprite else 1}
  lightmap: 0
  compressionQuality: 50
  spriteMode: {1 if sprite else 0}
  spriteExtrude: 1
  spriteMeshType: 1
  alignment: 0
  spritePivot: {{x: 0.5, y: 0.5}}
  spritePixelsToUnits: 100
  spriteBorder: {{x: {border[0]}, y: {border[1]}, z: {border[2]}, w: {border[3]}}}
  spriteGenerateFallbackPhysicsShape: 1
  alphaUsage: 1
  alphaIsTransparency: {1 if alpha_transparency else 0}
  spriteTessellationDetail: -1
  textureType: {8 if sprite else 0}
  textureShape: 1
  singleChannelComponent: 0
  flipbookRows: 1
  flipbookColumns: 1
  maxTextureSizeSet: 0
  compressionQualitySet: 0
  textureFormatSet: 0
  ignorePngGamma: 0
  applyGammaDecoding: 0
  swizzle: 50462976
  cookieLightType: 0
  platformSettings:
{plat}  spriteSheet:
    serializedVersion: 2
    sprites: []
    outline: []
    physicsShape: []
    bones: []
    spriteID: {"5e97eb03825dee720800000000000000" if sprite else ""}
    internalID: 0
    vertices: []
    indices:
    edges: []
    weights: []
    secondaryTextures: []
    nameFileIdTable: {{}}
  mipmapLimitGroupName:
  pSDRemoveMatte: 0
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def model_meta(remap=None, readable=True, anim_type=0, import_anim=False, clips=None, global_scale=1.0, import_materials=True):
    """remap: {material_name_in_fbx: material_guid}; clips: list of dicts(name, take, id, first, last, loop)."""
    ext = "externalObjects: {}\n"
    if remap:
        ext = "externalObjects:\n"
        for name, g in remap.items():
            ext += f"""  - first:
      type: UnityEngine:Material
      assembly: UnityEngine.CoreModule
      name: {name}
    second: {{fileID: 2100000, guid: {g}, type: 2}}
"""
    clip_txt = "clipAnimations: []\n"
    if clips:
        clip_txt = "clipAnimations:\n"
        for c in clips:
            loop = 1 if c.get("loop") else 0
            clip_txt += f"""    - serializedVersion: 16
      name: {c['name']}
      takeName: {c['take']}
      internalID: {c['id']}
      firstFrame: {c['first']}
      lastFrame: {c['last']}
      wrapMode: 0
      orientationOffsetY: 0
      level: 0
      cycleOffset: 0
      loop: 0
      hasAdditiveReferencePose: 0
      loopTime: {loop}
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
    return f"""ModelImporter:
  serializedVersion: 22200
  internalIDToNameTable: []
  {ext}  materials:
    materialImportMode: {2 if import_materials else 0}
    materialName: 0
    materialSearch: 1
    materialLocation: 1
  animations:
    legacyGenerateAnimations: 4
    bakeSimulation: 0
    resampleCurves: 1
    optimizeGameObjects: 0
    removeConstantScaleCurves: 0
    motionNodeName:
    rigImportErrors:
    rigImportWarnings:
    animationImportErrors:
    animationImportWarnings:
    animationRetargetingWarnings:
    animationDoRetargetingWarnings: 0
    importAnimatedCustomProperties: 0
    importConstraints: 0
    animationCompression: 1
    animationRotationError: 0.5
    animationPositionError: 0.5
    animationScaleError: 0.5
    animationWrapMode: 0
    extraExposedTransformPaths: []
    extraUserProperties: []
    {clip_txt}    isReadable: {1 if readable else 0}
  meshes:
    lODScreenPercentages: []
    globalScale: {global_scale}
    meshCompression: 0
    addColliders: 0
    useSRGBMaterialColor: 1
    sortHierarchyByName: 1
    importPhysicalCameras: 0
    importVisibility: 0
    importBlendShapes: 0
    importCameras: 0
    importLights: 0
    nodeNameCollisionStrategy: 1
    fileIdsGeneration: 2
    swapUVChannels: 0
    generateSecondaryUV: 0
    useFileUnits: 1
    keepQuads: 0
    weldVertices: 1
    bakeAxisConversion: 0
    preserveHierarchy: 0
    skinWeightsMode: 0
    maxBonesPerVertex: 4
    minBoneWeight: 0.001
    optimizeBones: 1
    meshOptimizationFlags: -1
    indexFormat: 0
    secondaryUVAngleDistortion: 8
    secondaryUVAreaDistortion: 15.000001
    secondaryUVHardAngle: 88
    secondaryUVMarginMethod: 1
    secondaryUVMinLightmapResolution: 40
    secondaryUVMinObjectScale: 1
    secondaryUVPackMargin: 4
    useFileScale: 1
    strictVertexDataChecks: 0
  tangentSpace:
    normalSmoothAngle: 60
    normalImportMode: 0
    tangentImportMode: 3
    normalCalculationMode: 4
    legacyComputeAllNormalsFromSmoothingGroupsWhenMeshHasBlendShapes: 0
    blendShapeNormalImportMode: 1
    normalSmoothingSource: 0
  referencedClips: []
  importAnimation: {1 if import_anim else 0}
  humanDescription:
    serializedVersion: 3
    human: []
    skeleton: []
    armTwist: 0.5
    foreArmTwist: 0.5
    upperLegTwist: 0.5
    legTwist: 0.5
    armStretch: 0.05
    legStretch: 0.05
    feetSpacing: 0
    globalScale: 1
    rootMotionBoneName:
    hasTranslationDoF: 0
    hasExtraRoot: 0
    skeletonHasParents: 1
  lastHumanDescriptionAvatarSource: {{instanceID: 0}}
  autoGenerateAvatarMappingIfUnspecified: 1
  animationType: {anim_type}
  humanoidOversampling: 1
  avatarSetup: {1 if anim_type == 2 else 0}
  addHumanoidExtraRootOnlyWhenUsingAvatar: 1
  importBlendShapeDeformPercent: 1
  remapMaterialsIfMaterialImportModeIsNone: 0
  additionalBone: 0
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def ref(guid, file_id, typ):
    if guid is None:
        return "{fileID: 0}"
    return f"{{fileID: {file_id}, guid: {guid}, type: {typ}}}"


def stable_id(*parts):
    """Deterministic local fileID (positive 63-bit)."""
    h = hashlib.md5(("|".join(map(str, parts))).encode()).hexdigest()
    return int(h[:15], 16)
