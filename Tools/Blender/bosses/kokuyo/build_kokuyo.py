"""Kokuyō, el jefe final: modelo, esqueleto, animaciones, chequeos, FBX y renders de revisión.

Un solo comando, determinista:
  blender -b --factory-startup --python Tools/Blender/bosses/kokuyo/build_kokuyo.py -- [opciones]
    --export            escribe Nindo/Assets/Nindo/Art/Characters/Kokuyo/Kokuyo.fbx (+ Kokuyo.fbx.json)
    --renders DIR       hojas de revisión (modelo + una por clip) en DIR
    --only A,B          solo esos clips (para iterar; no exporta)
    --model-only        sin animaciones (iterar el modelado)
    --blend PATH        guarda el .blend resultante (para mirar a mano)
    --lineup            con --renders: solo la hoja del elenco (Kaito, ninja, sumo, Gorō, Kokuyō)
    --report PATH       el detalle de las mediciones en JSON sin renderizar (con --renders va en DIR)
Falla (código 1) si un chequeo no pasa: frente, apoyo en el piso, presupuesto de triángulos,
altura máxima de la silueta (5.8 m), alcance de manos y pies, deriva de los pies apoyados,
costura de los loops, quietud del apex, punta del arma rápida fuera del golpe (con el reloj del
juego), hoja clavada que se corre en el piso y avance de raíz que se teletransporta con StepTimeline.
"""
import sys, os, json, math, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
for p in (HERE, os.path.join(ROOT, "Tools", "Blender"), os.path.join(ROOT, "Tools", "Blender", "anim")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import bpy
from mathutils import Vector
import nindo_lib as L
import nindo_anim as NA
import kokuyo_rig as KR
import kokuyo_model as KM

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


EXPORT = "--export" in argv
RENDERS = opt("--renders")
ONLY = opt("--only")
MODEL_ONLY = "--model-only" in argv
BLEND = opt("--blend")
REPORT = opt("--report")
OUT_DIR = os.path.join(ROOT, "Nindo", "Assets", "Nindo", "Art", "Characters", "Kokuyo")
FBX = os.path.join(OUT_DIR, "Kokuyo.fbx")
HEIGHT_CAP = 5.8
GAP = 10                 # cuadros vacíos entre clips en la toma única
TIP_LOCAL = KR.TIP_LOCAL
BLADE_SLIDE = 0.03       # m por cuadro que puede correrse la entrada de la hoja clavada en el piso
ROOT_MAX = 20.0          # m/s del transform en un cuadro de juego (Enemy.cs limita la embestida a 12)
failures, warnings = [], []


def check(ok, msg, warn=False):
    print(("  ok   " if ok else ("  WARN " if warn else "  FAIL ")) + msg)
    if not ok:
        (warnings if warn else failures).append(msg)


def lint_clip(rig, clip, frames, ctrls, roots, misses):
    """Mediciones del clip ya resuelto (antes de exportar)."""
    rep = {}
    t = clip.timing
    n = clip.frames
    # alcance: el IK no puede quedarse corto (mano que se despega de la empuñadura, pie que flota)
    mh = max(max(m["hand_r"], m["hand_l"]) for m in misses)
    ml = max(m["legs"] for m in misses)
    fh = max(range(len(misses)), key=lambda i: max(misses[i]["hand_r"], misses[i]["hand_l"]))
    fl = max(range(len(misses)), key=lambda i: misses[i]["legs"])
    rep["reach_miss_cm"] = {"hands": round(mh * 100, 1), "legs": round(ml * 100, 1)}
    check(ml <= 0.03, f"{clip.name}: los pies llegan (faltó {ml * 100:.1f} cm en f{fl})")
    check(mh <= 0.05, f"{clip.name}: las manos llegan (faltó {mh * 100:.1f} cm en f{fh}: "
                      f"der {misses[fh]['hand_r'] * 100:.0f} / izq {misses[fh]['hand_l'] * 100:.0f})", warn=mh <= 0.12)
    # pies apoyados: no patinan
    gp = {}
    for S in "RL":
        fb = "Foot_" + S
        # bola del pie: lo que apoya entre la punta y el talón, y lo que no puede patinar
        gp[fb] = rig.rest_inv[fb] @ Vector((KR.ANKLE.x * (1 if S == "R" else -1), -0.38, 0.0))
    piv = {}
    for S in "RL":
        fb = "Foot_" + S
        x = KR.ANKLE.x * (1 if S == "R" else -1)
        # pivotes posibles: los bordes de la suela en la punta y el talón (un pie que se para en punta o se
        # echa atrás sobre el talón tiene uno quieto)
        piv[fb] = [rig.rest_inv[fb] @ Vector((x, KR.SOLE_TOE_Y, 0.0)), rig.rest_inv[fb] @ Vector((x, KR.SOLE_HEEL_Y, 0.0))]
    plants = NA.plant_report(rig, frames, roots, list(gp), gp, pivots=piv)
    worst = max([p["drift_cm"] for v in plants.values() for p in v] or [0.0])
    rep["plants"] = {k: v for k, v in plants.items()}
    wseg = [(k, p["frames"]) for k, v in plants.items() for p in v if p["drift_cm"] == worst]
    check(worst <= 2.0, f"{clip.name}: pies apoyados quietos (deriva máx. {worst:.1f} cm {wseg[:1]})")
    # loops sellados
    if clip.loop:
        seam, step = NA.loop_seam_deg(rig, frames)
        rep["loop_seam_deg"] = seam
        check(seam <= 0.5, f"{clip.name}: costura del loop {seam:.2f}°")
    # punta del arma: quieta en el apex y lenta fuera del golpe (un barrido rápido que no pega
    # es un aviso falso de parry)
    sp, pts = NA.tip_speeds(rig, frames, roots, "Katana", TIP_LOCAL)
    rep["tip_speed_mps"] = [round(v, 1) for v in sp]
    # la punta no atraviesa el piso salvo cuando la hoja está clavada a propósito (timing "ground")
    allowed = set()
    for a, b in t.get("ground", []):
        allowed.update(range(a, b + 1))
    under = [i for i, p in enumerate(pts) if p.z < -0.05 and i not in allowed]
    check(not under, f"{clip.name}: la punta no se mete en el piso ({len(under)} cuadros, p. ej. f{under[:3]})")
    # y cuando está clavada entra y sale a lo largo de su eje: el punto donde la hoja corta la piedra no
    # se corre (una hoja que gira con la punta enterrada se ve atravesando el piso). 'sink' = se hunde
    # entero en su sombra; 'bite' = el cuadro del tajo que la entierra cortando (kabuto-wari)
    sink = set()
    for s0, s1 in t.get("sink", []):
        sink.update(range(s0, s1 + 1))
    bite = set(t.get("bite", []))
    slide = [s for s in NA.blade_floor_slide(frames, roots, "Katana", TIP_LOCAL, skip=sink) if s[0] not in bite]
    if slide:
        ws = max(slide, key=lambda s: s[1])
        rep["blade_floor_slide_cm"] = round(min(ws[1], 99.0) * 100.0, 1)
        check(ws[1] <= BLADE_SLIDE, f"{clip.name}: la hoja clavada no se corre en el piso (f{ws[0]}: "
                                    f"{min(ws[1], 99.0) * 100:.1f} cm en un cuadro con la punta a {ws[2]:.2f} m; tope "
                                    f"{BLADE_SLIDE * 100:.0f} cm)")
    # avance de raíz con el reloj del juego: el ataque se toca con StepTimeline (suelta comprimida y
    # acelerada), no a 30 fps; se prueban los windups posibles con y sin la pausa extra del acto 1
    tr = [c.get("travel") or 0.0 for c in ctrls]
    if any(abs(v) > 1e-4 for v in tr) and not clip.root_vel.length:
        if "contact" in t and "apex" in t:
            rr = t.get("release_rate", 1.6)
            peak = (0.0, 0.0)
            for wmin in (0.38, 0.65, 0.8):
                for xh in (0.0, 0.42):
                    tl = NA.StepTimeline(n, t["apex"], t["contact"], rr, wmin, xh)
                    for s, f, v in NA.clock_speeds(tr, tl):
                        if v > peak[0]:
                            peak = (v, f)
            rep["root_peak_mps_60hz"] = round(peak[0], 1)
            rep["release_rate"] = rr
            check(peak[0] <= ROOT_MAX, f"{clip.name}: el transform no se teletransporta en el juego (pico {peak[0]:.1f} m/s "
                                       f"en el cuadro {peak[1]:.1f} del clip, 60 Hz, release_rate {rr}; tope {ROOT_MAX:.0f})")
        else:
            peak = max(abs(tr[i] - tr[i - 1]) * NA.FPS for i in range(1, len(tr)))
            rep["root_peak_mps_60hz"] = round(peak, 1)
            check(peak <= ROOT_MAX, f"{clip.name}: el transform no se teletransporta (pico {peak:.1f} m/s; tope {ROOT_MAX:.0f})")
    # espada soltada (derrota): queda clavada donde la dejó, no sigue a la mano
    free = [i for i, c in enumerate(ctrls) if (c.get("sword_free") or 0.0) >= 0.5]
    if free:
        K0 = frames[free[0]]["Katana"]
        a0, b0 = K0.translation + roots[free[0]], K0 @ TIP_LOCAL + roots[free[0]]
        drift = max(max((frames[i]["Katana"].translation + roots[i] - a0).length,
                        (frames[i]["Katana"] @ TIP_LOCAL + roots[i] - b0).length) for i in free)
        rep["sword_planted_drift_cm"] = round(drift * 100.0, 2)
        check(drift <= 0.01, f"{clip.name}: la espada soltada queda clavada (se corrió {drift * 100:.1f} cm)")
    # alcance real de la hoja en la ventana que pega: hasta dónde llega la punta desde el transform del juego
    if "active" in t:
        a0, a1 = t["active"]
        reach = max(Vector((pts[i].x - roots[i].x, pts[i].y - roots[i].y)).length for i in range(a0, a1 + 1))
        rep["reach_m"] = round(reach, 2)
        print(f"  info {clip.name}: alcance de la punta {reach:.2f} m (ventana f{a0}-{a1})")
    if "contact" in t and t.get("kind") in ("parry", "dodge"):
        a0, a1 = t["active"]
        apex = t["apex"]
        t0 = t.get("tell", [0])[0]
        # con el reloj del juego, que es lo que ve el jugador: la anticipación se toca hasta a 1.3x y la suelta
        # a release_rate (Tsuki: 0.4x), así que la proporción a 30 fps engaña; windup mínimo = la anticipación
        # más rápida posible
        tl = NA.StepTimeline(n, apex, t["contact"], t.get("release_rate", 1.6), 0.38, 0.0)
        gs = NA.clock_speeds(pts, tl)
        peak = max(v for s, f, v in gs if a0 - 1 <= f <= a1 + 2)
        outside = [(v, f) for s, f, v in gs if f > t0 and not (apex < f <= a1 + 3)]
        worst = max(outside) if outside else (0.0, 0)
        ratio = worst[0] / peak if peak > 0 else 0.0
        rep["tip_peak_mps"] = round(peak, 1)
        rep["tip_outside_ratio"] = round(ratio, 2)
        rep["tip_game_mps"] = [[f, round(v, 1)] for s, f, v in gs]
        lim = t.get("tip_ratio_max", 0.3)
        check(ratio <= lim, f"{clip.name}: punta fuera del golpe <= {lim * 100:.0f} % del pico con el reloj del juego "
                            f"({ratio * 100:.0f} % en el cuadro {worst[1]:.1f}; pico {peak:.1f} m/s)")
        o30 = max(sp[i] for i in range(t0 + 1, n + 1) if not (apex < i <= a1 + 3))
        print(f"  info {clip.name}: a 30 fps la punta fuera del golpe llega al {o30 / max(sp[a0 - 1:a1 + 2]) * 100:.0f} % del pico")
        # el apex y el cuadro siguiente: la pose de aviso se tiene que poder leer quieta
        still = [sp[i] for i in (apex, apex + 1)]
        rep["apex_tip_mps"] = [round(v, 1) for v in still]
        check(max(still) < 10.0, f"{clip.name}: apex quieto ({max(still):.1f} m/s)")
    return rep


def sheet_frames(clip):
    fs = sorted({k.frame for k in clip.keys})
    t = clip.timing
    for k in ("apex", "contact"):
        if k in t:
            fs.append(t[k])
    fs = sorted(set(fs))
    if len(fs) > 10:
        step = (len(fs) - 1) / 9.0
        fs = sorted({fs[round(i * step)] for i in range(10)})
    return fs


def frame_label(clip, f):
    t = clip.timing
    tags = []
    if t.get("apex") == f:
        tags.append("aviso")
    if t.get("contact") == f:
        tags.append("impacto")
    if "active" in t and t["active"][1] == f:
        tags.append("fin golpe")
    return f"f{f}" + (" " + "/".join(tags) if tags else "")


def main():
    t0 = time.time()
    L.clear_scene()
    scn = bpy.context.scene
    scn.render.fps = NA.FPS
    arm = NA.build_armature("Kokuyo", KR.bones(), data_name="KokuyoRig")
    rig = NA.Rig(arm)
    body, rigid, tris = KM.build(arm, rig)
    print("TRIS", json.dumps(tris), "total", sum(tris.values()))
    check(tris["body"] <= 5200, f"cuerpo {tris['body']} tris (presupuesto ~5000)")
    check(tris["Mask"] <= 320 and tris["Face"] <= 320 and tris["Katana_Nodachi"] <= 500, "máscara / rostro / espada en presupuesto")

    # ---------------------------------------------------------------- reposo
    bpy.context.view_layer.update()
    meshes = [body] + list(rigid.values())
    # la altura que va a medir Unity (CharacterFactory.NormalizeHeight) en la pose por defecto del FBX, que
    # es el reposo: con ese alto en NindoContent el modelo queda a escala 1 y los golpes en metros reales
    zlo, zhi = NA.unity_height(body, list(rigid.values()))
    bind_height = round(zhi - zlo, 3)
    check(abs(zlo) <= 0.005, f"nada bajo el piso en reposo y los pies en y=0 en Unity (min z {zlo:.3f})")
    print(f"  bind_height (medida de Unity) {bind_height}")
    mask = rigid["Mask"]
    mc = sum((mask.matrix_world @ v.co for v in mask.data.vertices), Vector()) / len(mask.data.vertices)
    check(mc.y < -0.2, f"la máscara está adelante (-Y) (y {mc.y:.2f})")
    fb = arm.data.bones["Facing"]
    check((fb.tail_local - fb.head_local).normalized().y < -0.99, "marcador Facing mira a -Y (Unity +Z)")
    fl = arm.data.bones["Foot_L"]
    check(fl.tail_local.y < fl.head_local.y, "la punta del pie va adelante del tobillo")
    info = {"fps": NA.FPS, "take": "Scene", "bind_height": bind_height,
            "bind_height_note": "alto que mide CharacterFactory.NormalizeHeight en la pose por defecto del FBX (el reposo): "
                                "con este valor en NindoContent la escala es 1",
            "tris": tris, "facing": "frente +Z en Unity (Blender -Y): modelYaw 0",
            "root_travel": "travel_m[f] = metros que el transform tiene que haber avanzado (hacia su frente; negativo = "
                           "hacia atrás) en el cuadro f del clip. Los pies apoyados quedan clavados solo si el juego mueve "
                           "el transform por deltas de travel_m(stepNorm * frames), con el reloj del paso (AttackDef.lunge = 0); "
                           "la embestida lineal de Enemy.cs no sigue la curva y hace patinar los pies. travel_m está medido con "
                           "StepTimeline y el release_rate de cada clip (AttackDef.releaseRate): con otro valor la suelta se "
                           "comprime y el avance se ve como un teletransporte (Tsuki necesita 0.4; con 1.6 salta 3.2 m en 0.1 s)"}

    rv = None
    if RENDERS:
        import kokuyo_review as RV
    if MODEL_ONLY:
        if RENDERS:
            rv = RV.Review(arm, body, rigid, RENDERS)
            print(rv.model_sheet())
        finish(t0)
        return

    # ---------------------------------------------------------------- clips
    import kokuyo_clips as KC
    solver = KR.Solver(rig)
    KC.SOLVER = solver
    sprs = KC.springs(rig)
    clips = KC.CLIPS
    if ONLY:
        names = ONLY.split(",")
        clips = [c for c in clips if c.name in names]
    baked, reports, rootsd, ctrlsd = [], {}, {}, {}
    for clip in clips:
        misses = []

        def solve(pose, c):
            misses.append(dict(solver.solve(pose, c)))
        frames, ctrls, roots = NA.bake_clip(rig, clip, solve, sprs)
        reports[clip.name] = lint_clip(rig, clip, frames, ctrls, roots, misses)
        baked.append((clip, frames))
        rootsd[clip.name] = roots
        ctrlsd[clip.name] = ctrls
    act, ranges = NA.write_pack(arm, rig, baked, start=1, gap=GAP)
    last = max(b for a, b in ranges.values())
    # techo y piso de la silueta en TODOS los cuadros (mallas evaluadas): la espada cuenta para el tope de
    # altura pero no para el piso (la punta clavada tiene su propio chequeo); 'sink' = se hunde a propósito
    for clip, frames in baked:
        a, b = ranges[clip.name]
        rows = NA.mesh_z_frames(meshes, range(a, b + 1))
        hi = [max(v[1] for v in r.values()) for r in rows]
        top = max(range(len(hi)), key=lambda i: hi[i])
        reports[clip.name]["max_height_m"] = round(hi[top], 2)
        check(hi[top] <= HEIGHT_CAP, f"{clip.name}: silueta {hi[top]:.2f} m en f{top} (tope {HEIGHT_CAP})")
        sink = set()
        for s0, s1 in clip.timing.get("sink", []):
            sink.update(range(s0, s1 + 1))
        lows = [min((v[0], i, k) for k, v in r.items() if k != "Katana_Nodachi") for i, r in enumerate(rows) if i not in sink]
        lo = min(lows) if lows else (0.0, 0, "")
        bad = [i for z, i, _ in lows if z < -0.03]
        reports[clip.name]["min_z_m"] = round(lo[0], 3)
        check(not bad, f"{clip.name}: nada atraviesa el piso (mín {lo[0]:.3f} m en f{lo[1]}, {lo[2]}; "
                       f"{len(bad)} cuadros bajo -3 cm: {bad[:4]})")
    # cada aviso tiene que cambiar la silueta vista desde la cámara del jefe (55°/30 m): lo que se lee desde
    # arriba es la forma, no el detalle
    if "Idle" in ranges:
        lint_tells(scn, arm, meshes, baked, ranges, rootsd, reports)
    else:
        print("  (sin Idle en --only: no se mide el cambio de silueta de los avisos)")
    scn.frame_set(1)
    if RENDERS or REPORT:
        # el detalle de las mediciones (velocidad de la punta por cuadro, apoyos) para revisar a mano
        path = REPORT or os.path.join(RENDERS, "lint_report.json")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump(reports, fh, indent=0)

    # ---------------------------------------------------------------- export
    if EXPORT and not ONLY:
        if failures:
            print("NO SE EXPORTA: fallaron chequeos")
        else:
            NA.export_fbx(FBX, arm, meshes, 1, last)
            clipd = {}
            for clip, frames in baked:
                a, b = ranges[clip.name]
                t = dict(clip.timing)
                norm = {}
                n = float(clip.frames)
                for k in ("apex", "contact"):
                    if k in t:
                        norm[k] = round(t[k] / n, 4)
                for k in ("tell", "hold", "active", "recover"):
                    if k in t:
                        norm[k] = [round(t[k][0] / n, 4), round(t[k][1] / n, 4)]
                if "lunge" in t:
                    norm["lunge"] = [round(t["lunge"][0] / n, 4), round(t["lunge"][1] / n, 4), t["lunge"][2]]
                rec = {"first": a, "last": b, "frames": clip.frames, "seconds": round(clip.frames / NA.FPS, 4),
                       "loop": clip.loop, "timing": t, "normalized": norm,
                       "events": [{"frame": e["frame"], "t": round(e["frame"] / n, 4), "fn": e["fn"]} for e in clip.events],
                       "strike_bone": "Katana", "tip_local_blender": list(TIP_LOCAL), "notes": clip.notes}
                if "reach_m" in reports[clip.name]:
                    rec["reach_m"] = reports[clip.name]["reach_m"]
                if "contact" in t:
                    # AttackDef.releaseRate con el que se midieron el avance y la punta (StepTimeline)
                    rec["release_rate"] = t.get("release_rate", 1.6)
                tr = [round(c.get("travel") or 0.0, 4) for c in ctrlsd[clip.name]]
                if any(abs(v) > 1e-4 for v in tr) and not clip.root_vel.length:
                    rec["travel_m"] = tr
                if clip.root_vel.length > 0:
                    rec["root_velocity_mps"] = round(clip.root_vel.length, 3)
                rec["lint"] = {k: v for k, v in reports[clip.name].items() if k not in ("tip_speed_mps", "tip_game_mps", "plants")}
                clipd[clip.name] = rec
            info["clips"] = clipd
            info["springs_baked"] = KC.SPRING_CHAINS
            info["parts"] = {"skinned": "Kokuyo_Body",
                             "rigid": {n: o.parent_bone for n, o in rigid.items()},
                             "materials": ["Nindo_Palette"] + KM.EXTRA_MATS,
                             "hidden_at_spawn": ["Sode_R_Broken"],
                             "notes": "Sode_R_Broken queda adentro de Sode_R (se ve al apagar Sode_R). "
                                      "Kokuyo_MaskCrack es del mismo rojo que la máscara: se ve solo al subirle la emisión. "
                                      "Crack_1..5 (Kokuyo_Cracks) nacen como vetas tenues: se encienden de a una por punto de "
                                      "desequilibrio con MaterialPropertyBlock (_EmissionColor de Kokuyo_Seams = encendida)."}
            with open(FBX + ".json", "w", encoding="utf-8", newline=chr(10)) as fh:
                json.dump(info, fh, indent=1, ensure_ascii=False)
            print("EXPORTADO", FBX, "cuadros 1 ..", last, f"{os.path.getsize(FBX) / 1e6:.1f} MB")

    # ---------------------------------------------------------------- renders
    if RENDERS:
        rv = RV.Review(arm, body, rigid, RENDERS)
        if not ONLY:
            print(rv.model_sheet(frame=ranges["Idle"][0]))
        if "--lineup" in argv:
            print(rv.lineup_sheet(ranges["Idle"][0]))
            finish(t0)
            return
        for clip, frames in baked:
            a, b = ranges[clip.name]
            fs = sheet_frames(clip)
            rv.clip_sheet(clip, a, rootsd[clip.name], fs, [frame_label(clip, f) for f in fs], reports[clip.name])
        if not ONLY:
            print(rv.lineup_sheet(ranges["Idle"][0]))
    finish(t0)


TELL_CAM = dict(focus=(0.0, -2.3, 1.2), pitch=55.0, dist=30.0, fov=30.0)
TELL_MIN = 0.15


def lint_tells(scn, arm, meshes, baked, ranges, rootsd, reports):
    """Silueta de cada pose de aviso contra la de la guardia, desde la cámara del jefe: la parte de la
    silueta del aviso que cae FUERA de la de Idle, sobre el área de Idle (>= 15 %)."""
    cam = NA.camera(scn, "LintCam")
    NA.game_camera(cam, **TELL_CAM)
    vis = [m for m in meshes if m.name != "Sode_R_Broken"]
    scn.frame_set(ranges["Idle"][0])
    arm.location = (0, 0, 0)
    bpy.context.view_layer.update()
    idle = NA.silhouette_mask(vis, cam)
    area = max(1, int(idle.sum()))
    for clip, frames in baked:
        t = clip.timing
        if t.get("kind") not in ("parry", "dodge") or "apex" not in t:
            continue
        f = t["apex"]
        scn.frame_set(ranges[clip.name][0] + f)
        arm.location = rootsd[clip.name][f]
        bpy.context.view_layer.update()
        m = NA.silhouette_mask(vis, cam)
        change = float((m & ~idle).sum()) / area
        reports[clip.name]["tell_silhouette_change"] = round(change, 3)
        check(change >= TELL_MIN, f"{clip.name}: el aviso (f{f}) cambia la silueta desde la cámara del jefe "
                                  f"{change * 100:.0f} % (mín. {TELL_MIN * 100:.0f} %)")
    arm.location = (0, 0, 0)


def finish(t0):
    if BLEND:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print(f"listo en {time.time() - t0:.1f} s; avisos {len(warnings)}")
    if failures:
        print("FALLARON", len(failures), "chequeos:")
        for f in failures:
            print("   -", f)
        sys.exit(1)


main()
