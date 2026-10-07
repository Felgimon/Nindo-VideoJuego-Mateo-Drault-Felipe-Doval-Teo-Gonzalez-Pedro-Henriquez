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
juego), suelas que rozan el piso y se corren (< 2 cm por cuadro del juego y < 3 cm por tramo, con el avance y el
giro del modelo que pone el código, entre cuadros en los ciclos, y también con el avance del corte cortado por el
imán), pies en el aire donde el juego mueve el cuerpo ('airborne'), empalmes de los crossfades cortos
(kaito_clips.CHAINS), costura de los loops (< 1°), velocidad de los ciclos contra la autorada, el impacto dentro de
la ventana que pega, nada bajo el piso, y la re-importación del FBX igual a lo horneado.
    --detail A,B      imprime, muestra por muestra, la altura y el corrimiento de las suelas de esos clips
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
DETAIL = (opt("--detail") or "").split(",")     # clips cuyos pies se imprimen muestra por muestra (para iterar)
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


# ------------------------------------------------------------------------------- pies que rozan el piso
# plant_report solo mira apoyos que ya están casi quietos: un pie que toca el piso y SE MUEVE (la punta de atrás
# arrastrada en un tajo, la punta que roza al despegar en el trote) no lo ve. Acá cuenta cualquier punto de la
# suela a menos de CONTACT del piso en dos muestras seguidas, con el avance del juego aplicado
CONTACT_U = 0.012 * KR.U_PER_M
SKATE_STEP_CM, SKATE_RUN_CM = 2.0, 3.0      # por cuadro del juego / acumulado en un tramo
SKATE_NOISE_CM = 0.5                        # cm por cuadro del juego (15 cm/s) que no se ven: no suman


def sole_grid(S):
    """9 puntos de la suela en reposo (espacio C): punta, bola y talón por adentro, al medio y por afuera."""
    toe, heel, ball = KR.sole_points(S)
    xs = sorted({round(c.x, 4) for c in KR.sole_corners(S)} | {round(toe.x, 4)})
    return [Vector((x, y, 0.0)) for x in xs for y in (toe.y, ball.y, heel.y)]


def chain_of(rig, n):
    out = []
    while n:
        out.append(n)
        n = rig.parent[n]
    return out[::-1]


def interp_world(rig, Wa, Wb, t, chain):
    """Pose del último hueso de 'chain' entre dos cuadros horneados como la arma Unity: cada hueso interpola su
    transform local (posición lineal, giro por slerp) y la cadena se recompone. Entre claves a 30 fps un pie
    clavado en el mundo describe un arco: eso es lo que patina entre cuadros aunque cada cuadro esté quieto."""
    W = None
    for n in chain:
        p = rig.parent[n]
        la = (Wa[p].inverted() @ Wa[n]) if p else Wa[n]
        lb = (Wb[p].inverted() @ Wb[n]) if p else Wb[n]
        L = NA.compose(la.translation.lerp(lb.translation, t), la.to_quaternion().slerp(lb.to_quaternion(), t).to_matrix())
        W = L if W is None else W @ L
    return W


def spin_deg(spin, f):
    """Giro del MODELO que aplica el código (timing 'spin' = [desde, hasta, grados], con la curva EaseOut de
    PlayerController.TickWhirlwind); afuera del tramo, 0 (el código lo devuelve a la base: 720° = 0°)."""
    if not spin:
        return 0.0
    a, b, deg = spin
    if f < a or f > b:
        return 0.0
    u = (f - a) / (b - a)
    return deg * (1.0 - (1.0 - u) ** 2)


def foot_samples(rig, frames, roots, fb, S, sub, use_roots, spin=None):
    loc = [rig.rest_inv[fb] @ p for p in sole_grid(S)]
    chain = chain_of(rig, fb)
    out = []
    n = len(frames) - 1
    for f in range(n + 1):
        for k in range(sub if f < n else 1):
            t = k / sub
            W = frames[f][fb] if k == 0 else interp_world(rig, frames[f], frames[f + 1], t, chain)
            r = (roots[f].lerp(roots[f + 1], t) if k else roots[f]) if use_roots else Vector()
            Rz = Matrix.Rotation(math.radians(spin_deg(spin, f + t)), 3, 'Z')
            out.append((f + t, [Rz @ (W @ p) + r for p in loc]))
    return out


def skate_report(rig, frames, roots, sub=1, use_roots=True, skid=(), detail=False, time_scale=1.0, spin=None):
    """{pie: [[desde, hasta, cm acumulados, cm/cuadro del juego máx], ...]} de los tramos en que la suela roza el
    piso y se corre (el punto que menos se mueve: rodar sobre la punta o el talón no cuenta). 'skid' = tramos de
    cuadros donde patinar es a propósito (no cuentan). time_scale: cuadros del clip por cuadro del juego."""
    out = {}
    for S, fb in (("R", "Pie.R"), ("L", "Pie.L")):
        smp = foot_samples(rig, frames, roots, fb, S, sub, use_roots, spin)
        runs, cur = [], None
        for (ta, pa), (tb, pb) in zip(smp, smp[1:]):
            idx = [i for i in range(len(pa)) if pa[i].z < CONTACT_U and pb[i].z < CONTACT_U]
            ok = any(a <= ta and tb <= b for a, b in skid)
            if detail:
                zl = min(p.z for p in pa) * M * 100
                dd = min((Vector((pb[i].x - pa[i].x, pb[i].y - pa[i].y)).length for i in idx), default=0.0) * M * 100
                print(f"    {fb} t{ta:5.2f} z {zl:5.1f} cm  {'roza' if idx else '    '} {dd:5.2f} cm")
            if idx and not ok:
                d = min(Vector((pb[i].x - pa[i].x, pb[i].y - pa[i].y)).length for i in idx) * M * 100
                rate = d / ((tb - ta) / time_scale)
                if cur is None:
                    cur = [ta, tb, 0.0, 0.0, []]
                cur[1] = tb
                cur[2] += d if rate > SKATE_NOISE_CM else 0.0
                cur[4].append((ta / time_scale, d, (tb - ta) / time_scale))
            elif cur is not None:
                runs.append(cur)
                cur = None
        if cur is not None:
            runs.append(cur)
        # velocidad en ventanas de medio cuadro del juego (lo que se ve a 60 fps), o de una muestra si están más
        # separadas: una muestra de 1/8 de cuadro en el instante en que la punta toca no es un patinazo
        for r in runs:
            ds = r.pop()
            w = max(0.5, max(dt for _, _, dt in ds))
            r[3] = max(sum(d for t, d, _ in ds if t0 <= t < t0 + w) / w for t0, _, _ in ds)
        out[fb] = [[round(r[0], 2), round(r[1], 2), round(r[2], 2), round(r[3], 2)] for r in runs if r[2] > 0.3]
    return out


def touching(rig, frames, roots, a, b):
    """Cuadros de [a, b] en que algún pie toca el piso (para los tramos en que el juego mueve el cuerpo solo)."""
    hit = []
    for S, fb in (("R", "Pie.R"), ("L", "Pie.L")):
        loc = [rig.rest_inv[fb] @ p for p in sole_grid(S)]
        for f in range(a, b + 1):
            if min((frames[f][fb] @ p).z for p in loc) < CONTACT_U:
                hit.append((fb, f))
    return hit


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
    # suela que roza el piso y se corre: en los ciclos también entre cuadros (4 muestras por cuadro, como interpola
    # Unity: ahí el pie clavado recorre 10-20 cm por cuadro en el espacio del cuerpo); en el resto, cuadro a cuadro.
    # 'skid' = tramos en que se corre a propósito (un corte de cámara o un teletransporte del código); 'spin' = el
    # giro del modelo que pone el código (un pie apoyado mientras el modelo gira dibuja un círculo en el piso)
    skid = [tuple(s) for s in t.get("skid", ())]
    sk = skate_report(rig, frames, roots, 4 if clip.loop else 1, True, skid, clip.name in DETAIL, t.get("time_scale", 1.0),
                      t.get("spin"))
    rep["skate"] = sk
    bad = [(fb, r) for fb, v in sk.items() for r in v if r[2] > SKATE_RUN_CM or r[3] > SKATE_STEP_CM]
    rep["skate_cm"] = round(max([r[2] for v in sk.values() for r in v] or [0.0]), 2)
    check(not bad, f"{clip.name}: ninguna suela patina rozando el piso (peor {bad[:3]})")
    # el imán del ataque corta el avance contra un enemigo pegado: un pie clavado en el mundo mientras el clip
    # descuenta el avance patina hacia atrás. Mientras el juego mueve el cuerpo, los pies van en el aire
    if not clip.loop and any((roots[i + 1] - roots[i]).length > 1e-6 for i in range(n)):
        sk0 = skate_report(rig, frames, roots, 1, False, skid)
        rep["skate_no_lunge"] = sk0
        bad0 = [(fb, r) for fb, v in sk0.items() for r in v if r[2] > SKATE_RUN_CM or r[3] > SKATE_STEP_CM]
        check(not bad0, f"{clip.name}: con el avance cortado por el imán tampoco patina (peor {bad0[:3]})")
    if "airborne" in t:
        a, b = t["airborne"]
        hits = touching(rig, frames, roots, a, b)
        check(not hits, f"{clip.name}: en el aire mientras el juego lo mueve (f{a}-f{b}; tocan {hits[:4]})")
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


def chain_report(rig, baked):
    """Empalmes que el código hace con crossfades cortos (kaito_clips.CHAINS): el giro local más grande entre
    el cuadro que termina y el que arranca, y cuánto se corre un pie. Un empalme de combo tiene que dar 0; uno
    que vuelve a la guardia con 0.12-0.2 s de fundido aguanta poco, pero un brazo que da media vuelta salta."""
    import kaito_clips as KC
    by = {c.name: fr for c, fr in baked}
    skip = set(KR.LEGACY)
    out = {}
    for a, fa, b, fb_, lim in KC.CHAINS:
        if a not in by or b not in by:
            continue
        Wa = by[a][fa if fa >= 0 else len(by[a]) - 1]
        Wb = by[b][fb_]
        la, lb = rig.to_local(Wa), rig.to_local(Wb)
        worst = sorted(((NA.quat_angle_deg(la[n][1], lb[n][1]), n) for n in rig.names if n not in skip), reverse=True)
        ang, bone = worst[0]
        foot = max((Wa[f].translation - Wb[f].translation).length for f in ("Pie.R", "Pie.L")) * M * 100
        # lo que se ve: cuánto se corren en el mundo los codos, las rodillas, las manos y la punta de la katana
        # (con brazos de 30 cm el antebrazo gira mucho para un hombro que baja unos centímetros)
        joint = max(((Wa[n].translation - Wb[n].translation).length * M * 100, n)
                    for n in ("Antebrazo.R", "Antebrazo.L", "Mando.R", "Mando.L", "Tibia.R", "Tibia.L", "cabeza", "KatanaBone"))
        key = f"{a}{'@' + str(fa) if fa >= 0 else ''}->{b}{'@' + str(fb_) if fb_ else ''}"
        out[key] = [round(ang, 1), bone, round(foot, 1), round(joint[0], 1), joint[1]]
        check(ang <= lim and foot <= 4.0, f"empalme {key}: {ang:.1f}° en {bone} (tope {lim}°), pies {foot:.1f} cm, "
                                          f"articulaciones {joint[0]:.1f} cm ({joint[1]})"
                                          + ("" if ang <= lim else f"; siguen {[(n, round(d)) for d, n in worst[1:4]]}"))
    return out


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
    reports["_chains"] = chain_report(rig, baked)
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
        # 'seconds' es lo que dura EN EL JUEGO: los ciclos horneados densos se tocan a x time_scale (kaito_gait)
        clipd[clip.name] = {
            "first": a, "last": b, "frames": clip.frames, "loop": clip.loop,
            "seconds": round(clip.frames / NA.FPS / t.get("time_scale", 1.0), 4), "time_scale": t.get("time_scale", 1.0),
            "timing": t, "normalized": norm,
            "events": [{"frame": e["frame"], "t": round(e["frame"] / n, 4), "fn": e["fn"]} for e in clip.events],
            "notes": clip.notes,
            "lint": {k: v for k, v in rep.items() if k not in ("plants", "tip_speed_mps", "summary")},
        }
    info = {"fps": NA.FPS, "take": "Scene", "units_per_meter": round(KR.U_PER_M, 4),
            "facing": "frente +Y de la armadura (Blender +X): modelYaw 90 en NindoContent, como siempre",
            "skeleton": "de juego: Mando bajo Antebrazo, Pie bajo Tibia; Target*/Pole* quedan sin pesos y quietos (kits)",
            "chains": reports.get("_chains", {}), "clips": clipd}
    with open(FBX + ".json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(info, fh, indent=1, ensure_ascii=False)


main()
