"""Builds, previews and exports Nindo environment props.

Run (from anywhere):
  blender -b --python Tools/Blender/build_props.py -- [--only id1,id2] [--module props_nature]
                                                    [--preview] [--export] [--list]

* Prop modules live in Tools/Blender/props/props_*.py and expose
      PROPS = {"prop_id": build_fn, ...}
  where build_fn(seed:int) -> bpy object (returned by MeshBuilder.finish()).
* --preview renders  Tools/Blender/out/previews/<id>_game.png / _front34.png
* --export writes   Nindo/Assets/Nindo/Art/Models/Props/<id>.fbx
  and updates       Tools/Blender/out/manifest_<module>.json
"""
import sys, os, json, importlib, glob, traceback, math

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "props"))

import bpy
from mathutils import Vector
import nindo_lib as L
import nindo_preview as PV

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else True
    return default


EXPORT_DIR = os.path.join(REPO, "Nindo", "Assets", "Nindo", "Art", "Models", "Props")
OUT = os.path.join(HERE, "out")
MANIFEST = os.path.join(OUT, "props_manifest.json")


def load_modules():
    mods = {}
    only_mod = arg("--module")
    for p in sorted(glob.glob(os.path.join(HERE, "props", "props_*.py"))):
        name = os.path.splitext(os.path.basename(p))[0]
        if only_mod and name != only_mod:
            continue
        try:
            mods[name] = importlib.import_module(name)
        except Exception:
            print(f"!! failed to import {name}")
            traceback.print_exc()
    return mods


def bbox(o):
    mn = Vector((1e9, 1e9, 1e9)); mx = -mn
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    return mn, mx


def validate(pid, o):
    warnings = []
    tris = len(o.data.polygons)
    mn, mx = bbox(o)
    if abs(mn.z) > 0.05 and mn.z > 0:
        warnings.append(f"bottom is at z={mn.z:.2f} (should touch 0)")
    used = sorted({p.material_index for p in o.data.polygons})
    meta = json.loads(o.get("nindo_meta", "{}"))
    if meta.get("collider") is None:
        warnings.append("no collider declared (call mb.collider_* )")
    return tris, (mn, mx), used, meta, warnings


def main():
    mods = load_modules()
    only = arg("--only")
    only = set(only.split(",")) if isinstance(only, str) else None
    all_props = {}
    for mname, m in mods.items():
        for pid, fn in getattr(m, "PROPS", {}).items():
            all_props[pid] = (mname, fn)
    if arg("--list"):
        for pid, (mname, _) in sorted(all_props.items()):
            print(f"{mname:22} {pid}")
        return
    manifests = {}

    def manifest_for(mname):
        if mname not in manifests:
            p = os.path.join(OUT, f"manifest_{mname}.json")
            manifests[mname] = json.load(open(p)) if os.path.exists(p) else {}
        return manifests[mname]
    os.makedirs(os.path.join(OUT, "previews"), exist_ok=True)
    report = []
    for pid, (mname, fn) in sorted(all_props.items()):
        if only and pid not in only:
            continue
        L.clear_scene()
        try:
            o = fn(1)
        except Exception:
            print(f"!! {pid}: build failed")
            traceback.print_exc()
            report.append((pid, "FAILED"))
            continue
        o.name = pid
        tris, (mn, mx), used, meta, warns = validate(pid, o)
        dims = mx - mn
        line = f"{pid:28} tris={tris:5} dims=({dims.x:.2f},{dims.y:.2f},{dims.z:.2f}) slots={used}"
        if warns:
            line += "  WARN: " + "; ".join(warns)
        print(line)
        report.append((pid, line))
        if arg("--export"):
            path = os.path.join(EXPORT_DIR, f"{pid}.fbx")
            L.export_fbx([o], path)
            col = meta.get("collider") or {"type": "none"}
            ucol = dict(col)
            if col.get("type") == "box":
                ucol["size"] = L.blender_to_unity_size(col["size"])
                ucol["center"] = L.blender_to_unity_vec(col["center"])
            elif col.get("type") == "capsule":
                ucol["center"] = L.blender_to_unity_vec(col["center"])
            umeta = {k: v for k, v in meta.items() if k not in ("collider",)}
            if "light_offset" in umeta:
                umeta["light_offset"] = L.blender_to_unity_vec(umeta["light_offset"])
            manifest_for(mname)[pid] = {"module": mname, "tris": tris, "size": L.blender_to_unity_size(list(dims)),
                             "collider": ucol, "slots": used, **umeta}
        if arg("--preview"):
            PV.setup_night(ground_size=max(12, max(dims.x, dims.y) * 3))
            PV.render_views([o], os.path.join(OUT, "previews", pid), views=("game", "front34"))
    for mname, man in manifests.items():
        json.dump(man, open(os.path.join(OUT, f"manifest_{mname}.json"), "w"), indent=1, sort_keys=True)
    print("\n==== REPORT ====")
    for pid, line in report:
        print(line)


main()
