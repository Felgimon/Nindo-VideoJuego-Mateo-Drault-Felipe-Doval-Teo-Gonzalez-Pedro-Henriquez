"""Clips nuevos de los personajes del equipo: autoría, chequeos, FBX de animación y hojas de revisión.

  blender -b --factory-startup --python Tools/Blender/anim/build_team_anims.py -- <ninja|sumo|goro|grandpa> [opciones]
    --export        escribe Nindo/Assets/Nindo/Art/Characters/TeamAnims/<Personaje>Anims.fbx (+ .json)
    --renders DIR   una hoja por clip (cámara del juego de frente y de perfil, perfil ortográfico)
    --only A,B      solo esos clips (para iterar; no exporta)
    --frames F      con --renders: cuadros de la hoja (si no, los del timing del clip)

El FBX de animación lleva SOLO la armadura (mismos nombres, padres y reposo que el modelo, exportada con los
mismos ajustes del equipo que usan los export_<personaje>.py): Unity liga sus clips por ruta de transform al
modelo de siempre, que no se toca (malla, pesos, kits de zona, .meta y GUID quedan como estaban).

Falla (código 1) si un chequeo no pasa: manos y pies que no llegan, pies apoyados que patinan, costuras de
loop, golpes cuyo contacto no cae en la ventana activa de EnemyArchetypes.cs, punta del arma rápida en la
pausa del aviso, avisos que no cambian la silueta vista desde la cámara del juego.
"""
import sys, os, json, math, re, time, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for p in (HERE, os.path.join(ROOT, "Tools", "Blender"), os.path.join(ROOT, "Tools", "Blender", "characters")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import bpy
from mathutils import Vector, Matrix
import nindo_anim as NA
import team_rig as T

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHAR = argv[0] if argv and not argv[0].startswith("--") else "ninja"


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


EXPORT = "--export" in argv
RENDERS = opt("--renders")
ONLY = opt("--only")
FRAMES = opt("--frames")
OUT_DIR = os.path.join(ROOT, "Nindo", "Assets", "Nindo", "Art", "Characters", "TeamAnims")
FBX = os.path.join(OUT_DIR, CHAR.capitalize() + "Anims.fbx")
ARCHETYPES = os.path.join(ROOT, "Nindo", "Assets", "Nindo", "Scripts", "Enemies", "EnemyArchetypes.cs")
GAP = 10
failures, warnings = [], []


def check(ok, msg, warn=False):
    print(("  ok   " if ok else ("  WARN " if warn else "  FAIL ")) + msg)
    if not ok:
        (warnings if warn else failures).append(msg)


# ------------------------------------------------------------------------------- golpes del juego
def archetype_hits(func_names):
    """Hit("Estado", ...) de las funciones dadas de EnemyArchetypes.cs:
    {estado: [(activeStart, activeEnd, apex, función, embestida, velocidad), ...]}.
    Los apex con nombre (NinjaApex1 = 0.50f) se resuelven con las constantes del archivo; embestida y velocidad, con
    los valores por omisión de Hit() (0.8 m, 1)."""
    src = open(ARCHETYPES, encoding="utf-8").read()
    consts = {m.group(1): float(m.group(2)) for m in re.finditer(r"(\w+)\s*=\s*([\d.]+)f", src)}
    out = {}
    for fn in func_names:
        m = re.search(r"public static \w+ " + fn + r"\([^)]*\)\s*\{(.*?)\n        \}", src, re.S)
        if not m:
            continue
        for h in re.finditer(r'Hit\("(\w+)",\s*[\d.]+,\s*([\d.]+)f,\s*([\d.]+)f(.*?)\);', m.group(1)):
            st, a0, a1, rest = h.group(1), float(h.group(2)), float(h.group(3)), h.group(4)
            am = re.search(r"apex:\s*([\w.]+)", rest)
            apex = None
            if am:
                v = am.group(1).rstrip("f")
                apex = consts.get(v, None) if not re.match(r"[\d.]+$", v) else float(v)
            lm = re.search(r"lunge:\s*([\d.]+)f", rest)
            sm = re.search(r"speed:\s*([\d.]+)f", rest)
            out.setdefault(st, []).append((a0, a1, apex, fn, float(lm.group(1)) if lm else 0.8, float(sm.group(1)) if sm else 1.0))
    return out


# las variantes de zona reusan los clips con sus propios números: también tienen que coincidir
ARCH_FUNCS = {"ninja": ["Ninja", "NinjaElite", "NinjaMountainMoves", "NinjaLakeMoves", "NinjaBambooMoves"],
              "sumo": ["Sumo", "Ozeki", "SumoMountainMoves", "SumoLakeMoves", "SumoBambooMoves"], "goro": ["Goro"], "grandpa": []}


# ------------------------------------------------------------------------------- mediciones
def canon_track(ch, frames, roots, bone, local):
    """Recorrido de un punto de un hueso en el marco de autoría (m), con el avance del transform incluido."""
    return [ch.Pc(W[bone] @ local + r) for W, r in zip(frames, roots)]


def plants(ch, frames, roots, ctrls):
    """Apoyos de cada pie (el tobillo casi quieto y a la altura de apoyo) y cuánto se corre dentro de cada uno el
    punto de la suela que menos se movió (punta, talón o planta: un pie que rueda sobre la punta no patina)."""
    R = ch.rig
    out = {}
    for k in "rl":
        fb = ch.side[k]["foot"]
        # puntos de la suela en el espacio del hueso del pie: bajo el tobillo, punta y talón (medidos en la malla)
        a0 = ch.land["ankle_" + k]
        so = ch.sole[k]
        loc = [R.rest_inv[fb] @ ch.P(a0 + v) for v in (Vector((0.0, 0.0, so["toe"].z)), so["toe"], so["heel"])]
        tracks = [canon_track(ch, frames, roots, fb, l) for l in loc]
        ankle = canon_track(ch, frames, roots, fb, Vector())
        segs, cur = [], None
        sz = ch.land["sole_z"][k]
        for i in range(1, len(ankle)):
            sp = (ankle[i] - ankle[i - 1]).length * T.FPS
            low = ankle[i].z < sz + 0.035
            if sp < 0.5 and low:
                cur = [i - 1, i] if cur is None else [cur[0], i]
            else:
                if cur and cur[1] - cur[0] >= 3:
                    segs.append(cur)
                cur = None
        if cur and cur[1] - cur[0] >= 3:
            segs.append(cur)
        rep = []
        for a, b in segs:
            drift = min(max(Vector((p.x - tr[a].x, p.y - tr[a].y)).length for p in tr[a:b + 1]) for tr in tracks)
            rep.append({"frames": [a, b], "drift_cm": round(drift * 100.0, 2)})
        out[k] = rep
    return out


def lint(ch, clip, frames, ctrls, roots, drops, misses, hits):
    rep = {}
    t = clip.timing
    n = clip.frames
    hm = [max(m["hand_r"], m["hand_l"]) / ch.u for m in misses]
    lm = [m["legs"] / ch.u for m in misses]
    mh, ml = max(hm), max(lm)
    fh, fl, fd = hm.index(mh), lm.index(ml), drops.index(max(drops))
    rep["reach_miss_cm"] = {"hands": round(mh * 100, 1), "legs": round(ml * 100, 1)}
    check(ml <= 0.02, f"{clip.name}: los pies llegan (faltó {ml * 100:.1f} cm en f{fl})")
    side = "derecha" if misses[fh]["hand_r"] >= misses[fh]["hand_l"] else "izquierda"
    check(mh <= 0.03, f"{clip.name}: las manos llegan (faltó {mh * 100:.1f} cm en f{fh}, {side})", warn=mh <= 0.06)
    rep["hip_drop_cm"] = round(max(drops) * 100, 1)
    check(max(drops) <= 0.04, f"{clip.name}: la cadera no se cae para alcanzar los pies ({max(drops) * 100:.1f} cm en f{fd})", warn=True)
    pl = plants(ch, frames, roots, ctrls)
    rep["plants"] = pl
    worst = max([p["drift_cm"] for v in pl.values() for p in v] or [0.0])
    allow = t.get("slide_ok", 2.0)
    where = "; ".join(f"{k} f{p['frames'][0]}-f{p['frames'][1]} {p['drift_cm']}" for k, v in pl.items() for p in v if p["drift_cm"] > 1.0)
    check(worst <= max(2.0, allow), f"{clip.name}: pies apoyados quietos (deriva máx. {worst:.1f} cm{'; ' + where if where else ''})")
    if clip.loop:
        seam, step = NA.loop_seam_deg(ch.rig, frames)
        rep["loop_seam_deg"] = seam
        check(seam <= 0.5, f"{clip.name}: costura del loop {seam:.2f}°")
    w = ch.weapon_info
    if "contact" in t:
        a = t["contact"]
        if w and w["kind"] == "katana":
            bone, local = ch.spec["weapon"]["bone"], w["tip_local"]
        elif w and w["kind"] == "club":
            bone = ch.spec["weapon"]["bone"]
            local = Vector((0.0, w["head_center"] * ch.u, 0.0))
        else:
            hk = t.get("striker", "r")
            if hk.startswith("foot_"):
                bone, local = ch.side[hk[5:]]["foot"], Vector()
            else:
                bone, local = ch.side[hk]["hand"], Vector((0.0, ch.rig.length[ch.side[hk]["hand"]], 0.0))
        tip = canon_track(ch, frames, roots, bone, local)
        # pausa y pico se miden respecto del cuerpo (sin el avance del transform: en una embestida el cuerpo entero
        # vuela, lo que importa es que el arma quede quieta en la pausa y que el golpe sea lo más rápido del clip)
        rel = canon_track(ch, frames, [Vector()] * len(frames), bone, local)
        sp = [0.0] + [(rel[i] - rel[i - 1]).length * T.FPS for i in range(1, len(rel))]
        rep["tip_speed_mps"] = [round(v, 1) for v in sp]
        ap = t["apex"]
        h0, h1 = t.get("hold", [ap, ap])
        qmax = max(sp[h0 + 1:h1 + 1] or [0.0])
        rep["hold_tip_mps"] = round(qmax, 2)
        check(qmax <= 2.5, f"{clip.name}: la punta casi quieta en la pausa del aviso f{h0}-f{h1} ({qmax:.1f} m/s)")
        act = t.get("active", [a, a + 2])
        peak = max(range(ap, min(n, act[1] + 2) + 1), key=lambda i: sp[i])
        rep["peak_frame"] = peak
        check(ap < peak <= act[1] + 1, f"{clip.name}: la punta va más rápido en el golpe (pico f{peak}, golpe f{ap}-f{act[1]})")
        # el golpe del juego: activeStart = contacto / largo (±1 cuadro), apex = fin de la pausa
        st = t.get("state", clip.name)
        for a0, a1, apex, fn, hl, hs in hits.get(st, []):
            ok = abs(a0 - a / n) <= 1.0 / n + 1e-3 and (apex is None or abs(apex - ap / n) <= 1.0 / n + 1e-3)
            check(ok, f"{clip.name}: {fn}() Hit(\"{st}\") activo {a0:.2f}-{a1:.2f} apex {apex} vs clip contacto "
                      f"{a / n:.3f} apex {ap / n:.3f}")
            # las variantes que reusan el clip con otra embestida: los pies quedan corridos la diferencia, y si la
            # embestida no entra en la suelta, el cuerpo se desliza durante la pausa (aviso, no falla: es su número)
            if t.get("lunge") is not None and hl > 0.0:
                g = prerelease_glide(n, ap, a, hl, hs)
                check(g <= 0.02 and abs(hl - t["lunge"]) <= 0.1,
                      f"{clip.name}: {fn}() embestida {hl:.2f} m (clip {t['lunge']:.2f}), {g * 100:.0f} cm antes de la suelta", warn=True)
        # la embestida del clip tiene que arrancar en la suelta: si arranca antes, con cualquier pausa del juego en el
        # apex (CombatDirector la estira hasta 0.6 s) el ninja se desliza con la pose quieta y los pies clavados
        if t.get("lunge"):
            g = prerelease_glide(n, ap, a, t["lunge"], 1.0)
            rep["prerelease_glide_cm"] = round(g * 100.0, 1)
            check(g <= 0.02, f"{clip.name}: la embestida de {t['lunge']:.1f} m arranca en la suelta ({g * 100:.0f} cm antes)")
            # lo mismo medido con el reloj: con 0.45 s más de pausa, lo que avanzó hasta el apex (la pose congelada)
            held, _ = T.lunge_travel(n, ap, a, t["lunge"], windup_min=t.get("windup", 0.55) + 0.45)
            dh = max(held[:ap + 1])
            check(dh <= 0.02, f"{clip.name}: con 0.45 s de pausa no avanza con la pose del apex quieta ({dh * 100:.1f} cm)")
        # con el reloj del juego: segundos desde que arranca el paso hasta el golpe
        tl = NA.StepTimeline(n, ap, a, windup_min=t.get("windup", 0.55))
        rep["game_T_s"] = round(tl.T, 3)
        rep["game_hold_s"] = round(tl.hold, 3)
        rep["contact_tip_m"] = [round(x, 2) for x in tip[a]]
    return rep


def prerelease_glide(frames, apex, contact, lunge, speed):
    """Metros que el transform avanza ANTES de la suelta (Enemy.BeginStep: la embestida termina en T + 0.05 * largo
    del paso y no va a más de 12 m/s; si la suelta no alcanza, arranca antes). No depende de la pausa."""
    tl = NA.StepTimeline(frames, apex, contact, windup_min=0.0, speed=speed)
    room = tl.tR + 0.05 * tl.step_len
    span = max(room, lunge / 12.0)
    return lunge * (span - room) / span


def body_points(ch, W):
    """Todos los huesos y la punta del arma (m, marco de autoría, sin el avance del transform): para comparar poses."""
    pts = [ch.Pc(W[n].translation) for n in ch.rig.names]
    w = ch.weapon_info
    if w and w["kind"] == "katana":
        pts.append(ch.Pc(W[ch.spec["weapon"]["bone"]] @ w["tip_local"]))
    elif w and w["kind"] == "club":
        pts.append(ch.Pc(W[ch.spec["weapon"]["bone"]] @ Vector((0.0, w["head_center"] * ch.u, 0.0))))
    return pts


def pose_at(ch, frames, f):
    """Puntos de body_points en un cuadro fraccionario (interpolados entre los dos enteros)."""
    i = max(0, min(len(frames) - 1, int(math.floor(f))))
    j = min(len(frames) - 1, i + 1)
    a, b = body_points(ch, frames[i]), body_points(ch, frames[j])
    s = f - i
    return [p + (q - p) * s for p, q in zip(a, b)]


def chain_checks(ch, baked_by_name):
    """Cortes del juego que encadenan con otro clip (timing['chain'] = [(cuadro, clip, cuadro del otro, tolerancia m)]):
    el retroceso del parry que corta Parried y arranca el paso siguiente, el sacudón que vuelve al loop de agotado,
    el final del abuelo que vuelve al Idle. La pose en el corte tiene que ser la del otro clip (peor punto)."""
    for name, (clip, frames) in baked_by_name.items():
        for f, other, fo, tol in clip.timing.get("chain", []):
            if other not in baked_by_name:
                continue
            a = pose_at(ch, frames, f)
            b = pose_at(ch, baked_by_name[other][1], fo)
            d = max((p - q).length for p, q in zip(a, b))
            check(d <= tol, f"{name}: en f{f:g} empalma con {other} f{fo:g} (peor punto {d * 100:.1f} cm, tope {tol * 100:.0f})")


def locomotion_weapon(ch, baked_by_name, states):
    """El blend de locomoción mezcla cada hueso por separado: si el arma apunta para lados opuestos en dos hijos
    vecinos, a mitad de mezcla se mete en el cuerpo o en el piso. Punta del arma a la misma fase, < 60 cm."""
    w = ch.weapon_info
    if not w:
        return
    bone = ch.spec["weapon"]["bone"]
    local = w["tip_local"] if w["kind"] == "katana" else Vector((0.0, w["head_center"] * ch.u, 0.0))
    for s0, s1 in zip(states, states[1:]):
        if s0 not in baked_by_name or s1 not in baked_by_name:
            continue
        fa, fb = baked_by_name[s0][1], baked_by_name[s1][1]
        worst = 0.0
        for ph in (0.0, 0.25, 0.5, 0.75):
            pa = ch.Pc(fa[int(round(ph * (len(fa) - 1)))][bone] @ local)
            pb = ch.Pc(fb[int(round(ph * (len(fb) - 1)))][bone] @ local)
            worst = max(worst, (pa - pb).length)
        check(worst <= 0.6, f"locomoción: el arma de {s0} a {s1} a la misma fase ({worst * 100:.0f} cm)")
        # la mezcla como la hace Unity (posición y giro LOCALES de cada hueso, interpolados): la punta a media mezcla
        # no puede irse lejos del promedio de las dos (se metía en las piernas) ni bajar del piso
        R = ch.rig
        dev, low = 0.0, 9.0
        for ph in (0.0, 0.25, 0.5, 0.75):
            Wa, Wb = fa[int(round(ph * (len(fa) - 1)))], fb[int(round(ph * (len(fb) - 1)))]
            la, lb = R.to_local(Wa), R.to_local(Wb)
            for wgt in (0.25, 0.5, 0.75):
                W = {}
                for nm in R.names:
                    (pa, qa), (pb, qb) = la[nm], lb[nm]
                    if qa.dot(qb) < 0.0:
                        qb = -qb
                    L = Matrix.Translation(pa.lerp(pb, wgt)) @ qa.slerp(qb, wgt).to_matrix().to_4x4()
                    par = R.parent[nm]
                    W[nm] = (W[par] @ R.rel[nm] if par else R.rest[nm]) @ L
                tip = ch.Pc(W[bone] @ local)
                ref = ch.Pc(Wa[bone] @ local).lerp(ch.Pc(Wb[bone] @ local), wgt)
                dev = max(dev, (tip - ref).length)
                low = min(low, tip.z)
        check(dev <= 0.3 and low >= 0.25, f"locomoción: a media mezcla {s0}-{s1} el arma sigue su camino (se aparta {dev * 100:.0f} cm, "
                                          f"punta/cabeza a {low * 100:.0f} cm del piso)")


def foot_vertices(ch):
    """Vértices de la suela de cada pie (malla con skin): los que pesan más de la mitad en el pie o en su control.
    {k: [(objeto, [índices])]}"""
    out = {}
    for k in "rl":
        names = {ch.side[k]["foot"]} | ({ch.side[k]["foot_ctrl"]} if ch.side[k]["foot_ctrl"] else set())
        lst = []
        for o in ch.meshes:
            gi = {g.index for g in o.vertex_groups if g.name in names}
            if not gi:
                continue
            idx = [v.index for v in o.data.vertices if sum(g.weight for g in v.groups if g.group in gi) > 0.5]
            if idx:
                lst.append((o, idx))
        out[k] = lst
    return out


def mesh_pass(ch, clip, first, roots, feet_v, floor_tol=0.01):
    """Una pasada por la malla deformada de cada cuadro (la acción ya escrita) con dos medidas:
      * patinada CON el pie tocando el piso (revisión AK-03): en cada par de cuadros, de los vértices de la suela que
        están a menos de 1 cm del piso en los dos, el que menos se corrió en el plano del piso (con el avance del
        transform del juego sumado). Un pie que rueda sobre la punta o el talón tiene un vértice quieto: no cuenta; uno
        que se arrastra entero sí. {k: [(cuadro inicial, final, total cm, peor cm por cuadro)]} de las tiradas > 0.5 cm;
      * lo más hondo que se mete en el piso el cuerpo (mallas con skin) y el arma (piezas rígidas), en cm por cuadro."""
    import numpy as np
    scn = bpy.context.scene
    n = clip.frames
    Rw = np.array(ch.Rcw, dtype=np.float64)
    O = np.array(ch.O, dtype=np.float64)
    A3 = ch.A.to_3x3()
    feet_idx = {o.name: {k: np.array(idx) for k, lst in feet_v.items() for oo, idx in lst if oo is o} for o in ch.meshes}
    pts, low_body, low_weapon, low_where = [], [], [], []
    for f in range(n + 1):
        scn.frame_set(first + f)
        dg = bpy.context.evaluated_depsgraph_get()
        shift = np.array(A3 @ roots[f], dtype=np.float64)
        row = {k: [] for k in feet_v}
        lb = lw = 9.0
        where = ""
        for o in ch.meshes:
            oe = o.evaluated_get(dg)
            me = oe.to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            oe.to_mesh_clear()
            M = np.array(oe.matrix_world, dtype=np.float64)
            w = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3] + shift
            c = (w - O) @ Rw / ch.u                         # marco de autoría (m)
            z = float(c[:, 2].min())
            if o.vertex_groups:
                if z < lb:
                    lb, where = z, dominant_group(o, int(c[:, 2].argmin()))
            else:
                lw = min(lw, z)
            for k, idx in feet_idx[o.name].items():
                row[k].append(c[idx])
        pts.append({k: np.concatenate(v) for k, v in row.items() if v})
        low_body.append(lb)
        low_weapon.append(lw)
        low_where.append(where)
    out = {}
    for k in feet_v:
        runs, run = [], None
        for a in range(n):
            pa, pb = pts[a][k], pts[a + 1][k]
            on = (pa[:, 2] < floor_tol) & (pb[:, 2] < floor_tol)
            if on.any():
                m = float(np.min(np.hypot(pb[on, 0] - pa[on, 0], pb[on, 1] - pa[on, 1]))) * 100.0
                if run is None:
                    run = [a, a + 1, 0.0, 0.0]
                run[1] = a + 1
                run[2] += m
                run[3] = max(run[3], m)
            elif run:
                runs.append(run)
                run = None
        if run:
            runs.append(run)
        out[k] = [(r0, r1, round(t, 2), round(w, 2)) for r0, r1, t, w in runs if t > 0.5]
    return out, [round(v * 100.0, 1) for v in low_body], [round(v * 100.0, 1) for v in low_weapon], low_where


def dominant_group(o, vi):
    """Hueso que más pesa en un vértice (para decir QUÉ se mete en el piso)."""
    gs = o.data.vertices[vi].groups
    return o.vertex_groups[max(gs, key=lambda g: g.weight).group].name if len(gs) else o.name


def floor_checks(clip, low_body, low_weapon, low_where):
    """Nada atraviesa el piso: el cuerpo nunca más de 3 cm (las suelas que ruedan rozan); el arma tampoco, salvo el
    mordisco del golpe (hasta 6 cm, del contacto a 3 cuadros después: el martillo que pega en el piso)."""
    t = clip.timing
    bite = range(t["contact"], t["contact"] + 4) if "contact" in t else range(0)
    wb = min(range(len(low_body)), key=lambda i: low_body[i])
    check(low_body[wb] >= -3.0, f"{clip.name}: el cuerpo no se mete en el piso (f{wb} {low_body[wb]:.1f} cm)")
    if low_body[wb] < -3.0:
        print("       cuadro a cuadro (cm):", " ".join(f"{i}:{v:.0f}({low_where[i]})" for i, v in enumerate(low_body) if v < -3.0))
    if min(low_weapon) < 800.0:          # sin arma queda en 900 (centinela)
        bad = [(i, v) for i, v in enumerate(low_weapon) if v < (-6.0 if i in bite else -3.0)]
        ww = min(range(len(low_weapon)), key=lambda i: low_weapon[i])
        check(not bad, f"{clip.name}: el arma no se mete en el piso (f{ww} {low_weapon[ww]:.1f} cm"
                       f"{'; ' + str(len(bad)) + ' cuadros de más' if bad else ''})")


# ------------------------------------------------------------------------------- export
def export_fbx(ch, path, frame_start, frame_end):
    """Solo la armadura, con los ajustes del equipo (charlib.TEAM): el nodo 'Armature' y el reposo de cada hueso
    salen idénticos a los del modelo, así las curvas se ligan a la misma ruta y no mueven nada que no animen."""
    import charlib as C
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = frame_start, frame_end
    scn.frame_set(frame_start - 1)
    bpy.ops.object.select_all(action='DESELECT')
    ch.arm.select_set(True)
    bpy.context.view_layer.objects.active = ch.arm
    kw = dict(C.TEAM)
    kw.update(object_types={'ARMATURE'}, bake_anim_use_all_actions=False, bake_anim_step=1.0)
    # el abuelo se exportó en centímetros (FBX_SCALE_UNITS): el nodo de la armadura tiene que salir igual al del modelo
    kw.update(ch.spec.get("export_kw", {}))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, **kw)


def verify_fbx(ch, path, last):
    """El FBX de animación contra el modelo: mismos nodos (nombres), el nodo de la armadura con el mismo transform
    (si no, cada clip lo movería), las mismas unidades y una sola toma que cubre todos los clips."""
    import fbxcheck as FC
    a, m = FC.summary(path), FC.summary(ch.src)
    extra = [n for n in a["models"] if n not in m["models"]]
    check(not extra, f"FBX: todos los nodos existen en el modelo ({extra[:4]})")
    arm = ch.arm.name
    ra, ta, sa = a["local"][arm]
    rm, tm, sm = m["local"][arm]
    d_rot = FC._rot3_angle(ra, rm)
    d_pos = max(abs(x - y) for x, y in zip(ta, tm))
    d_scl = max(abs(x - y) for x, y in zip(sa, sm))
    check(d_rot < 0.01 and d_pos < 1e-4 and d_scl < 1e-5, f"FBX: nodo '{arm}' igual al del modelo (giro {d_rot:.4f}°, "
                                                          f"posición {d_pos:.2e}, escala {d_scl:.2e})")
    check(abs(a.get("unit", 1) - m.get("unit", 1)) < 1e-6, f"FBX: unidades {a.get('unit')} = {m.get('unit')}")
    check(list(a["stacks"]) == ["Scene"], f"FBX: una toma 'Scene' ({list(a['stacks'])})")
    lo, hi = a["stacks"].get("Scene", (0, 0))
    check(abs(hi * T.FPS - last) < 0.51, f"FBX: la toma llega al cuadro {last} ({hi * T.FPS:.1f})")
    return a


def sheet_frames(clip):
    t = clip.timing
    if FRAMES:
        return [int(x) for x in FRAMES.split(",")]
    if "contact" in t:
        fs = {0, t["hold"][0], t["apex"], t["contact"] - 1, t["contact"], t["active"][1], clip.frames}
        fs |= set(t.get("sheet", []))
        return sorted(f for f in fs if 0 <= f <= clip.frames)
    k = max(1, clip.frames // 7)
    return sorted(set(list(range(0, clip.frames + 1, k)) + list(t.get("sheet", []))))


def frame_label(clip, f):
    t = clip.timing
    tags = []
    if "contact" in t:
        if f == t["hold"][0]:
            tags.append("aviso")
        if f == t["apex"]:
            tags.append("apex")
        if f == t["contact"]:
            tags.append("GOLPE")
    return f"f{f}" + (" " + "/".join(tags) if tags else "")


# ------------------------------------------------------------------------------- main
def main():
    global mod
    t0 = time.time()
    ch = T.TeamChar(CHAR, T.CHARS[CHAR])
    print("PERSONAJE", CHAR, json.dumps(ch.report()))
    mod = importlib.import_module("team_clips_" + CHAR)
    clips = mod.clips(ch)
    if ONLY:
        keep = ONLY.split(",")
        clips = [c for c in clips if c.name in keep]
    solver = T.TeamSolver(ch)
    hits = archetype_hits(ARCH_FUNCS.get(CHAR, []))
    baked, reports, rootsd, rootsa = [], {}, {}, {}
    for clip in clips:
        frames, ctrls, roots, drops, misses = T.bake(ch, clip, solver)
        print(f"[{clip.name}] {clip.frames} cuadros ({clip.frames / T.FPS:.2f} s){' loop' if clip.loop else ''}")
        reports[clip.name] = lint(ch, clip, frames, ctrls, roots, drops, misses, hits)
        rootsd[clip.name] = [(c.get("travel") or 0.0) + clip.root_vel.length * (f / T.FPS) for f, c in enumerate(ctrls)]
        rootsa[clip.name] = roots
        baked.append((clip, frames))
    act, ranges = NA.write_pack(ch.arm, ch.rig, baked, start=1, gap=GAP)
    # pies que patinan tocando el piso: se mide sobre la malla deformada por la acción ya escrita
    feet_v = foot_vertices(ch)
    for clip, _ in baked:
        sk, lb, lw, lwh = mesh_pass(ch, clip, ranges[clip.name][0], rootsa[clip.name], feet_v)
        reports[clip.name]["floor_skate_cm"] = sk
        reports[clip.name]["lowest_body_cm"] = min(lb)
        reports[clip.name]["lowest_weapon_cm"] = min(lw) if min(lw) < 800 else None
        floor_checks(clip, lb, lw, lwh)
        allow = clip.timing.get("slide_ok", 0.0)
        runs = [r for v in sk.values() for r in v]
        tot = max([r[2] for r in runs] or [0.0])
        per = max([r[3] for r in runs] or [0.0])
        where = "; ".join(f"{k} f{r[0]}-f{r[1]} {r[2]} cm" for k, v in sk.items() for r in v if r[2] > 1.0)
        check(tot <= max(3.0, allow) and per <= max(2.0, allow),
              f"{clip.name}: sin patinar con el pie en el piso (total {tot:.1f} cm, peor cuadro {per:.1f} cm{'; ' + where if where else ''})")
    by_name = {c.name: (c, fr) for c, fr in baked}
    chain_checks(ch, by_name)
    lo = getattr(mod, "LOCOMOTION", None)
    if lo:
        locomotion_weapon(ch, by_name, [nm for nm, _ in lo])
    last = max(b for a, b in ranges.values())
    if EXPORT and not ONLY:
        if failures:
            print("NO SE EXPORTA: fallaron chequeos")
        else:
            export_fbx(ch, FBX, 1, last)
            nfail = len(failures)
            verify_fbx(ch, FBX, last)
            if len(failures) > nfail:
                os.remove(FBX)
                print("FBX BORRADO: no coincide con el modelo")
                sys.exit(1)
            info = {"fps": T.FPS, "take": "Scene", "character": CHAR, "model": ch.spec["fbx"], "units_per_meter": round(ch.u, 5),
                    "clips": {}}
            lo = getattr(mod, "LOCOMOTION", None)
            if lo and all(n in ranges for n, _ in lo):
                # estados y umbrales de Speed (velocidad / runSpeed) del blend tree de locomoción
                info["locomotion"] = {"states": [n for n, _ in lo], "thresholds": [th for _, th in lo]}
            for clip, frames in baked:
                a, b = ranges[clip.name]
                t = dict(clip.timing)
                nn = float(clip.frames)
                norm = {k: round(t[k] / nn, 4) for k in ("apex", "contact") if k in t}
                for k in ("hold", "active"):
                    if k in t:
                        norm[k] = [round(t[k][0] / nn, 4), round(t[k][1] / nn, 4)]
                rec = {"first": a, "last": b, "frames": clip.frames, "seconds": round(clip.frames / T.FPS, 4), "loop": clip.loop,
                       "timing": t, "normalized": norm, "notes": clip.notes,
                       "lint": {k: v for k, v in reports[clip.name].items() if k not in ("tip_speed_mps", "plants")}}
                if clip.root_vel.length > 0:
                    rec["root_velocity_mps"] = round(clip.root_vel.length, 3)
                info["clips"][clip.name] = rec
            with open(FBX + ".json", "w", encoding="utf-8", newline="\n") as fh:
                json.dump(info, fh, indent=1, ensure_ascii=False)
            print("EXPORTADO", FBX, "cuadros 1 ..", last, f"{os.path.getsize(FBX) / 1e6:.2f} MB")
    if RENDERS:
        import team_review as TR
        rv = TR.Review(ch, RENDERS)
        for clip, frames in baked:
            fs = sheet_frames(clip)
            # Kaito donde lo alcanza el golpe: a la embestida más el alcance (los demás clips, a 2.4 m)
            t = clip.timing
            kd = max(2.4, t.get("lunge", 0.0) + t.get("reach", 1.6)) if "contact" in t else 2.4
            print(rv.clip_sheet(clip, ranges[clip.name][0], rootsd[clip.name], fs, [frame_label(clip, f) for f in fs], kaito_dist=kd))
        with open(os.path.join(RENDERS, CHAR + "_lint.json"), "w", encoding="utf-8") as fh:
            json.dump(reports, fh, indent=0)
    print(f"listo en {time.time() - t0:.1f} s; avisos {len(warnings)}")
    if failures:
        print("FALLARON", len(failures), "chequeos:")
        for f in failures:
            print("   -", f)
        sys.exit(1)


main()
