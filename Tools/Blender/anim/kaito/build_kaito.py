"""Kaito: esqueleto de juego + todos sus clips, chequeos, FBX y hojas de revisión. Un solo comando, determinista:

  blender -b --factory-startup --python Tools/Blender/anim/kaito/build_kaito.py -- [opciones]
    --export          re-escribe EN EL LUGAR Nindo/Assets/Animations teo/kaitooo.fbx (mismo .meta y GUID) y su
                      sidecar kaitooo.fbx.json; después correr Tools/Unity/generate_assets.py (o su parte de Kaito)
    --src FBX         modelo de partida (por defecto el del repo: el script es idempotente)
    --renders DIR     hojas de revisión por clip en DIR
    --only A,B        solo esos clips (para iterar; no exporta)
    --report PATH     las mediciones en JSON
    --blend PATH      guarda el .blend

Orden con export_kaito.py (malla, materiales y katana del pulido B2): primero export_kaito.py, después este.

Falla (código 1) si un chequeo no pasa: alcance de manos y pies, deriva de los pies apoyados (< 2 cm en el
juego), costura de los loops (< 1°), velocidad de los ciclos contra la autorada, el impacto dentro de la
ventana que pega, nada bajo el piso, y la re-importación del FBX igual a lo horneado.
"""
import sys, os, json, math, time, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
for p in (HERE, os.path.join(ROOT, "Tools", "Blender", "anim"), os.path.join(ROOT, "Tools", "Blender", "characters")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import bpy
from mathutils import Vector, Matrix
import nindo_anim as NA
import charlib as C
import fbxcheck
import kaito_rig as KR

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


REL = "Animations teo/kaitooo.fbx"
FBX = os.path.join(ROOT, "Nindo", "Assets", REL)
SRC = opt("--src", FBX)
EXPORT = "--export" in argv
RENDERS = opt("--renders")
ONLY = opt("--only")
REPORT = opt("--report")
BLEND = opt("--blend")
GAP = 10
M = KR.M_PER_U
failures, warnings = [], []


def check(ok, msg, warn=False):
    print(("  ok   " if ok else ("  WARN " if warn else "  FAIL ")) + msg)
    if not ok:
        (warnings if warn else failures).append(msg)


# =============================================================================== mediciones de un clip
def sole_pivots():
    """{hueso del pie: [punta, talón, bola]} de la suela en reposo (espacio C)."""
    return {fb: list(KR.sole_points(S)) for S, fb in (("R", "Pie.R"), ("L", "Pie.L"))}


def lint_clip(rig, clip, frames, ctrls, roots, misses):
    rep = {}
    t = clip.timing
    n = clip.frames
    mh = max(max(m["hand_r"], m["hand_l"]) for m in misses)
    ml = max(m["legs"] for m in misses)
    rep["reach_miss_cm"] = {"hands": round(mh * M * 100, 1), "legs": round(ml * M * 100, 1)}
    check(ml * M <= 0.015, f"{clip.name}: los pies llegan (faltó {ml * M * 100:.1f} cm en "
                           f"f{max(range(len(misses)), key=lambda i: misses[i]['legs'])})")
    fr_ = max(range(len(misses)), key=lambda i: max(misses[i]["hand_r"], misses[i]["hand_l"]))
    fl_ = max(range(len(misses)), key=lambda i: misses[i]["legs"])
    check(mh * M <= 0.02, f"{clip.name}: las manos llegan (faltó {mh * M * 100:.1f} cm en f{fr_}: der "
                          f"{misses[fr_]['hand_r'] * M * 100:.0f} / izq {misses[fr_]['hand_l'] * M * 100:.0f}; pies f{fl_})",
          warn=mh * M <= 0.05)
    # apoyos: el punto de la suela que menos se mueve (punta, talón o bola) no se corre
    piv = sole_pivots()
    gp = {fb: rig.rest_inv[fb] @ piv[fb][2] for fb in piv}
    pivl = {fb: [rig.rest_inv[fb] @ p for p in piv[fb]] for fb in piv}
    # plant_report detecta apoyos con el punto bajo (z < 0.12 u = 6 cm) y casi quieto
    plants = NA.plant_report(rig, frames, roots, list(gp), gp, thresh=0.02, pivots=pivl)
    worst = max([p["drift_cm"] for v in plants.values() for p in v] or [0.0]) * M
    rep["plants"] = plants
    rep["plant_drift_cm"] = round(worst, 2)
    wseg = [(k, p["frames"]) for k, v in plants.items() for p in v if p["drift_cm"] * M >= worst - 1e-6]
    check(worst <= 2.0 or t.get("slide_ok"), f"{clip.name}: pies apoyados quietos (deriva máx. {worst:.2f} cm en el juego {wseg[:2]})")
    if clip.loop:
        seam, step = NA.loop_seam_deg(rig, frames)
        rep["loop_seam_deg"] = seam
        check(seam <= 1.0, f"{clip.name}: costura del loop {seam:.2f}°")
    # velocidad del suelo de los ciclos: el pie apoyado se mueve hacia atrás a la velocidad autorada
    if "stance_l" in t:
        # apoyos de los ciclos (2 cuadros en la carrera: plant_report pide 3): el borde de la suela que menos se
        # mueve en cada apoyo, medido en el mundo con el cuerpo avanzando a la velocidad autorada
        worst_g = 0.0
        for fb, key in (("Pie.L", "stance_l"), ("Pie.R", "stance_r")):
            fs = t[key]
            runs, cur = [], [fs[0]]
            for f in fs[1:]:
                if f == cur[-1] + 1:
                    cur.append(f)
                else:
                    runs.append(cur)
                    cur = [f]
            runs.append(cur)
            for run in runs:
                if len(run) < 2:
                    continue
                # el pie rueda (talón -> plano -> punta): entre cada par de cuadros tiene que haber un borde quieto;
                # se suma lo que se corrió el borde más quieto de cada par (el resbalón acumulado del apoyo)
                d = 0.0
                for f0, f1 in zip(run, run[1:]):
                    d += min((frames[f1][fb] @ pv + roots[f1] - (frames[f0][fb] @ pv + roots[f0])).length for pv in pivl[fb])
                worst_g = max(worst_g, d * M * 100)
        rep["stance_drift_cm"] = round(worst_g, 2)
        check(worst_g <= 2.0, f"{clip.name}: en el ciclo el pie apoyado no patina ({worst_g:.2f} cm en el juego)")
    if "ground_speed_mps" in t:
        # el cuerpo avanza a root_vel en el mundo: si el pie apoyado no deriva, el suelo va a esa velocidad
        rep["ground_speed_mps"] = t["ground_speed_mps"]
    # punta de la katana
    tip_local = rig.rest_inv["KatanaBone"] @ KR.TIP_C_REST
    sp, pts = NA.tip_speeds(rig, frames, roots, "KatanaBone", tip_local)
    rep["tip_speed_mps"] = [round(v * M, 1) for v in sp]
    if "contact" in t:
        a0, a1 = t["active"]
        check(a0 <= t["contact"] <= a1, f"{clip.name}: el impacto (f{t['contact']}) está dentro de la ventana {a0}-{a1}")
        # el tramo más rápido de la punta tiene que caer en la ventana que pega (el corte se VE cuando pega)
        fmax = max(range(1, n + 1), key=lambda i: sp[i])
        rep["tip_peak"] = [fmax, round(sp[fmax] * M, 1)]
        check(a0 - 1 <= fmax <= a1 + 1, f"{clip.name}: la punta va más rápido (f{fmax}, {sp[fmax] * M:.1f} m/s) dentro de la "
                                        f"ventana {a0}-{a1}")
        reach = max(Vector((pts[i].x - roots[i].x, pts[i].y - roots[i].y)).length for i in range(a0, a1 + 1)) * M
        rep["reach_m"] = round(reach, 2)
    if "strike" in t:
        s = t["strike"]
        rep["strike_n"] = round(s / n, 4)
    return rep


def mesh_floor(meshes, rng):
    """Altura mínima (m) de la malla evaluada por cuadro (espacio C: la armadura en TO_C)."""
    out = []
    for f in rng:
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        z = min(float(NA.world_verts(o, dg)[:, 2].min()) for o in meshes)
        out.append(z)
        if z < -0.04 and "--floor-debug" in argv:
            import numpy as np
            for o in meshes:
                w = NA.world_verts(o, dg)
                i = int(np.argmin(w[:, 2]))
                gs = sorted(((g.weight, o.vertex_groups[g.group].name) for g in o.data.vertices[i].groups), reverse=True)[:2] if o.vertex_groups else []
                print(f"    f{f} {o.name}: z {w[i, 2]:.3f} en {tuple(round(x, 2) for x in w[i])} {gs}")
    return out


def sheet_frames(clip):
    if isinstance(clip, NA.ProcClip):
        return list(range(0, clip.frames, max(1, clip.frames // 8)))[:10]
    fs = sorted({k.frame for k in clip.keys} | {clip.timing[k] for k in ("apex", "contact", "strike") if k in clip.timing})
    if len(fs) > 10:
        step = (len(fs) - 1) / 9.0
        fs = sorted({fs[round(i * step)] for i in range(10)})
    return fs


def frame_label(clip, f):
    t = clip.timing
    tags = []
    if t.get("apex") == f:
        tags.append("carga")
    if t.get("contact") == f:
        tags.append("impacto")
    if t.get("strike") == f:
        tags.append("tajo")
    return f"f{f}" + (" " + "/".join(tags) if tags else "")


# =============================================================================== principal
def main():
    t0 = time.time()
    print("origen:", SRC)
    before = fbxcheck.summary(SRC)
    arm = C.load(SRC)
    scn = bpy.context.scene
    scn.render.fps = NA.FPS
    body = bpy.data.objects["Cuerpo"]
    kat = bpy.data.objects["Isan"]
    meshes = [body, kat]
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    C.rest(arm, True)
    print("esqueleto de juego:", KR.game_skeleton(arm, body))
    C.limit_weights(body)
    C.flat_normals(body)
    C.flat_normals(kat)
    C.strip_images()
    C.rest(arm, False)
    arm_world0 = arm.matrix_world.copy()
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    rig = KR.c_rig(arm)
    solver = KR.Solver(rig)
    import kaito_clips as KC
    clips = KC.CLIPS
    if ONLY:
        names = ONLY.split(",")
        clips = [c for c in clips if c.name in names]
    baked, reports, rootsd = [], {}, {}
    for clip in clips:
        misses = []

        def solve(pose, c):
            misses.append(dict(solver.solve(pose, c)))
        frames, ctrls, roots = NA.bake_clip(rig, clip, solve, ())
        reports[clip.name] = lint_clip(rig, clip, frames, ctrls, roots, misses)
        baked.append((clip, frames))
        rootsd[clip.name] = roots
    act, ranges = NA.write_pack(arm, rig, baked, start=1, gap=GAP, name="KaitoB3")
    last = max(b for a, b in ranges.values())
    # nada atraviesa el piso (la armadura en el espacio C para medir; el FBX se exporta con la original)
    arm.matrix_world = KR.TO_C
    for clip, frames in baked:
        a, b = ranges[clip.name]
        zs = mesh_floor(meshes, range(a, b + 1))
        lo = min(zs)
        reports[clip.name]["min_z_cm"] = round(lo * M * 100, 1)
        allow = clip.timing.get("floor_ok", -0.02)
        check(lo * M >= allow, f"{clip.name}: nada bajo el piso (mín {lo * M * 100:.1f} cm en f{zs.index(lo)})")
    arm.matrix_world = arm_world0
    if REPORT:
        with open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(reports, fh, indent=0)

    # ---------------------------------------------------------------- export
    tmp = None
    if not ONLY and (EXPORT or RENDERS):
        tmp = os.path.join(tempfile.gettempdir(), "nindo_kaito_b3", "kaitooo.fbx")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        scn.frame_start, scn.frame_end = 1, last
        scn.frame_set(0)
        C.export(tmp, bake_anim_use_all_actions=False)
        after = fbxcheck.summary(tmp)
        validate_fbx(before, after)
        verify_roundtrip(tmp, rig, baked, ranges)
        if EXPORT:
            if failures:
                print("NO SE EXPORTA: fallaron chequeos")
            else:
                shutil.copyfile(tmp, FBX)
                write_sidecar(baked, ranges, reports, after)
                print("ESCRITO", FBX, f"{os.path.getsize(FBX) / 1e6:.2f} MB, cuadros 1..{last}")

    # ---------------------------------------------------------------- renders
    if RENDERS:
        import kaito_review as RV
        rv = RV.Review(arm, meshes, RENDERS)
        for clip, frames in baked:
            a, b = ranges[clip.name]
            fs = sheet_frames(clip)
            r = reports[clip.name]
            r["summary"] = summary(clip, r)
            print(rv.clip_sheet(clip, a, rootsd[clip.name], fs, [frame_label(clip, f) for f in fs], r,
                                gait=isinstance(clip, NA.ProcClip)))
    if BLEND:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print(f"listo en {time.time() - t0:.1f} s; avisos {len(warnings)}")
    if failures:
        print("FALLARON", len(failures), "chequeos:")
        for f in failures:
            print("   -", f)
        sys.exit(1)


def summary(clip, r):
    out = []
    if "plant_drift_cm" in r:
        out.append(f"pies {r['plant_drift_cm']:.1f} cm")
    if "loop_seam_deg" in r:
        out.append(f"costura {r['loop_seam_deg']:.2f}°")
    if "reach_m" in r:
        out.append(f"alcance {r['reach_m']:.2f} m")
    if "ground_speed_mps" in r:
        out.append(f"{r['ground_speed_mps']:.1f} m/s")
    return ", ".join(out)


def validate_fbx(A, B):
    """El FBX nuevo tiene los mismos nodos y el mismo bind pose que el anterior (solo cambian padres)."""
    missing = [n for n in A["models"] if n not in B["models"]]
    check(not missing, f"FBX: están todos los nodos ({len(A['models'])} -> {len(B['models'])}; faltan {missing[:5]})")
    worst = (0.0, 0.0, "")
    for n, ma in A["bind"].items():
        mb = B["bind"].get(n)
        if mb is None:
            continue
        ang = fbxcheck._rot_angle(ma, mb)
        dt = math.dist(ma[12:15], mb[12:15])
        if (ang, dt) > worst[:2]:
            worst = (ang, dt, n)
    check(worst[0] <= 0.02 and worst[1] <= 0.005, f"FBX: bind pose igual (peor {worst[0]:.4f}° / {worst[1]:.5f} en {worst[2]})")
    check(B["fps"] == 30, f"FBX: 30 fps ({B['fps']})")
    check(list(B["stacks"]) == ["Scene"], f"FBX: una sola toma 'Scene' ({list(B['stacks'])})")
    check(not B["video_bytes"], "FBX: sin texturas embebidas")


def verify_roundtrip(path, rig, baked, ranges):
    """Re-importa el FBX y compara cuadros horneados con lo leído (posición de manos, pies, cabeza y katana)."""
    scn = bpy.context.scene
    keep_frame = scn.frame_current
    objs0, acts0, meshes0 = set(bpy.data.objects), set(bpy.data.actions), set(bpy.data.meshes)
    bpy.ops.import_scene.fbx(filepath=path, anim_offset=0.0)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm2 = next(o for o in new if o.type == 'ARMATURE')
    acts = [a for a in bpy.data.actions if a not in acts0]
    C.bind_slots(arm2, acts)
    if acts:
        C.use_action(arm2, acts[0])
    parents_ok = all(arm2.data.bones[c].parent.name == p for c, p in (("Mando.R", "Antebrazo.R"), ("Mando.L", "Antebrazo.L"),
                                                                      ("Pie.L", "Tibia.L"), ("Pie.R", "Tibia.R")))
    check(parents_ok, "FBX: manos bajo los antebrazos y pies bajo las tibias")
    inv = KR.TO_C.inverted()
    best = None
    for off in (0, 1, -1):
        worst = (0.0, "")
        for clip, frames in baked:
            a, b = ranges[clip.name]
            for i in sorted({0, clip.frames // 2, clip.frames}):
                scn.frame_set(a + i + off)
                for n in ("Mando.R", "Mando.L", "Pie.R", "Pie.L", "cabeza", "KatanaBone", "Root"):
                    want = inv @ frames[i][n]
                    got = arm2.pose.bones[n].matrix
                    d = (want.translation - got.translation).length * M * 100
                    if d > worst[0]:
                        worst = (d, f"{clip.name}@{i}:{n}")
        if best is None or worst[0] < best[1][0]:
            best = (off, worst)
    off, worst = best
    check(worst[0] <= 0.5, f"FBX re-importado = horneado (peor {worst[0]:.2f} cm en {worst[1]}; desfase de cuadro {off})")
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    for a in [a for a in bpy.data.actions if a not in acts0]:
        bpy.data.actions.remove(a)
    for m in [m for m in bpy.data.meshes if m not in meshes0]:
        bpy.data.meshes.remove(m)
    scn.frame_set(keep_frame)


def write_sidecar(baked, ranges, reports, fbx_summary):
    clipd = {}
    for clip, frames in baked:
        a, b = ranges[clip.name]
        t = dict(clip.timing)
        n = float(clip.frames)
        norm = {}
        for k in ("apex", "contact", "combo", "strike", "cancel"):
            if k in t:
                norm[k] = round(t[k] / n, 4)
        for k in ("active", "hold", "recover"):
            if k in t:
                norm[k] = [round(t[k][0] / n, 4), round(t[k][1] / n, 4)]
        if "lunge" in t:
            norm["lunge"] = [round(t["lunge"][0] / n, 4), round(t["lunge"][1] / n, 4), t["lunge"][2]]
        rep = reports[clip.name]
        clipd[clip.name] = {
            "first": a, "last": b, "frames": clip.frames, "seconds": round(clip.frames / NA.FPS, 4), "loop": clip.loop,
            "timing": t, "normalized": norm,
            "events": [{"frame": e["frame"], "t": round(e["frame"] / n, 4), "fn": e["fn"]} for e in clip.events],
            "notes": clip.notes,
            "lint": {k: v for k, v in rep.items() if k not in ("plants", "tip_speed_mps", "summary")},
        }
    info = {"fps": NA.FPS, "take": "Scene", "units_per_meter": round(KR.U_PER_M, 4),
            "facing": "frente +Y de la armadura (Blender +X): modelYaw 90 en NindoContent, como siempre",
            "skeleton": "de juego: Mando bajo Antebrazo, Pie bajo Tibia; Target*/Pole* quedan sin pesos y quietos (kits)",
            "clips": clipd}
    with open(FBX + ".json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(info, fh, indent=1, ensure_ascii=False)


main()
