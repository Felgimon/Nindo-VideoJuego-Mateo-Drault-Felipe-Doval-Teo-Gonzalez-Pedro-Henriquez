"""Clips de Kokuyō: claves, curvas, tiempos y resortes. Fuente única de los tiempos del FBX.

Gramática de cada golpe (la que pidió la auditoría para que el parry se lea):
  anticipación (contra-movimiento) -> pose de AVISO que rompe la silueta vista desde arriba ->
  espera que se mueve (nunca congelada) -> golpe de 2-3 cuadros por un arco limpio -> se pasa
  (follow-through) -> recuperación hasta una pose de encadenado.
La cadera y el tronco van un cuadro adelante de la hoja (las articulaciones se rompen en
sucesión) y la cabeza un cuadro atrás. El pie de adelante apoya justo en el cuadro del impacto.

'timing' de cada clip (cuadros a 30 fps, se copia al .fbx.json):
  tell [inicio, apex]   la anticipación hasta la pose de aviso
  apex                  cuadro de la pose de aviso (AttackDef.apex = apex / frames)
  hold [a, b]           la espera que se mueve
  contact               primer cuadro que pega (activeStart)
  active [a, b]         ventana que pega (activeStart, activeEnd)
  recover [a, b]        castigo / recuperación
  lunge [a, b, m]       avance que el JUEGO aplica al transform (en el clip ya está restado)
  release_rate          AttackDef.releaseRate con el que se midieron avance y punta (StepTimeline; 1.6 si falta)
  kind                  parry | dodge (imparable) | none
  ground / sink / bite  cuadros con la punta clavada / con todo hundido en la sombra / el tajo que entierra la
                        hoja cortando (ahí la entrada en la piedra puede saltar; en el resto no se corre)
"""
import copy, math
from mathutils import Vector, Quaternion
import nindo_anim as NA
from nindo_anim import Key, Clip, Spring, rot3
import kokuyo_rig as KR
from kokuyo_poses import *


# --------------------------------------------------------------------------- resortes
def springs(rig):
    """Cadenas secundarias. Los faldones además se abren cuando el muslo los empuja."""
    hips_rest = rot3(rig.rest["Hips"])
    thigh_rest = {S: rot3(rig.rest["Thigh_" + S]).col[1] for S in "RL"}
    hipj = {S: rig.head_rest("Thigh_" + S) for S in "RL"}
    plate = {}
    for a in KR.SKIRT_ANGLES:
        h, d, o, t = KR.skirt_frame(a)
        plate[KR.skirt_name(a)] = (h, o, t)

    def thigh_push(W, b):
        h, o, t = plate[b]
        Rh = rot3(W["Hips"]) @ hips_rest.transposed()
        oo, tt = Rh @ o, Rh @ t
        best = 0.0
        for S in "RL":
            cur = rot3(W["Thigh_" + S]).col[1]
            fol = Rh @ thigh_rest[S]
            ang = math.acos(max(-1.0, min(1.0, cur.dot(fol))))
            sw = cur - fol
            sw.z = 0.0
            if sw.length < 1e-5 or ang < 1e-3:
                continue
            c = max(0.0, sw.normalized().dot(oo))
            dist = Vector((h.x - hipj[S].x, h.y - hipj[S].y)).length
            w = max(0.0, min(1.0, 1.45 - dist / 0.65))
            best = max(best, ang * c * w)
        if best < 1e-3:
            return None
        return Quaternion(tt, -min(best, math.radians(75.0)))

    # la melena es pesada: rígida, amortiguada y con tope bajo (si no, en un tajo que frena de golpe se
    # da vuelta sobre la cabeza); busca colgar cuando el torso se inclina
    def local(bone, p):
        return rig.rest_inv[bone] @ Vector(p)
    # la coraza es ancha pero poco profunda: esferas grandes corridas hacia adelante, que asoman justo
    # por la espalda sin tocar la nuca (de donde sale la melena)
    back = [("Chest", local("Chest", (0.0, -0.12, 2.76)), 0.78), ("Spine", local("Spine", (0.0, -0.12, 2.36)), 0.7)]
    front = [("Hips", local("Hips", (0.0, -0.05, 1.95)), 0.8),
             ("Thigh_R", local("Thigh_R", (-0.41, -0.04, 1.36)), 0.46), ("Thigh_L", local("Thigh_L", (0.41, -0.04, 1.36)), 0.46)]
    # la melena va apoyada sobre la espalda: sigue la orientación del pecho (no de la cabeza) y solo se
    # mece un poco; suelta, en un tajo que frena de golpe se abría como un abanico
    sp = [Spring([f"Mane_{c}_1", f"Mane_{c}_2", f"Mane_{c}_3"], k=260.0, damp=0.25, grav=2.0, max_deg=16.0, floor=0.08,
                 colliders=back, follow="Chest") for c in "CRL"]
    sp += [Spring([f"Sash_{s}_1", f"Sash_{s}_2"], k=120.0, damp=0.14, grav=6.0, max_deg=60.0, floor=0.06, hang=0.6,
                  colliders=front) for s in "RL"]
    sp += [Spring(["Sode_R"], k=320.0, damp=0.2, grav=0.0, max_deg=16.0), Spring(["Sode_L"], k=320.0, damp=0.2, grav=0.0, max_deg=16.0)]
    sp += [Spring(["Ribbon_1", "Ribbon_2"], k=75.0, damp=0.1, grav=6.0, max_deg=70.0, floor=0.05, hang=0.7,
                  colliders=[("UpperArm_L", local("UpperArm_L", (1.27, 0.0, 2.85)), 0.38)])]
    sp += [Spring(["Tassel_1", "Tassel_2"], k=70.0, damp=0.1, grav=7.0, max_deg=80.0, floor=0.04, hang=0.85)]
    # el piso empuja la punta del faldón; las esquinas de la placa quedan más abajo que la punta del hueso
    sp += [Spring([KR.skirt_name(a)], k=240.0, damp=0.2, grav=0.0, max_deg=40.0, push=thigh_push, floor=0.22)
           for a in KR.SKIRT_ANGLES]
    return sp


SPRING_CHAINS = {"mane": ["Mane_C_1..3", "Mane_R_1..3", "Mane_L_1..3"], "obi_tails": ["Sash_R_1..2", "Sash_L_1..2"],
                 "ribbon_shoulder": ["Ribbon_1", "Ribbon_2"], "ribbon_pommel": ["Tassel_1", "Tassel_2"],
                 "sode": ["Sode_R", "Sode_L"], "kusazuri": [KR.skirt_name(a) for a in KR.SKIRT_ANGLES]}

LEAD = {"hips": -0.6, "hips_rot": -0.6, "spine": -0.3, "head": 1.0, "neck": 0.5}

CLIPS = []


# --------------------------------------------------------------------------- hoja que se clava
# Una nodachi clavada entra y sale de la piedra A LO LARGO DE SU EJE: el punto donde corta el piso no se
# mueve. Antes de clavarla, una clave con la hoja ya en su dirección final y la punta sobre la entrada
# ('hover'); al arrancarla, una clave con la hoja tirada hacia atrás por su eje hasta que la punta sale
# ('free'). Los tramos rectos llevan tope en 'grip' (el Catmull-Rom no los curva) y 'sword_ground' cambia
# con un escalón ('hold') en el cuadro en que la punta está afuera: el giro que esquiva el piso
# (Solver.clear_floor) protege los barridos de antes y de después, nunca a la hoja clavada.
SWORD_IN = {"sword_ground": "hold", "stop": ("grip",)}


def tip_of(p):
    """Punta de la hoja de una pose (espacio del personaje), igual que la ubica el Solver."""
    K = NA.compose(Vector(p["grip"]) + Vector((0.0, 0.0, p.get("lift") or 0.0)),
                   NA.basis_yz(p["blade"], -Vector(p["edge"])))
    return K @ KR.TIP_LOCAL


def along(p, tip_z, ground, **kw):
    """La pose 'p' (con cambios 'kw' en el cuerpo) con la hoja corrida por su propio eje hasta que la
    punta quede a 'tip_z' del piso; 'ground' = 1 si desde esta clave la hoja va clavada. El eje es la
    cuerda empuñadura -> punta, no el hueso: la hoja es curva (la punta va 14 cm hacia el lomo) y por el
    hueso la entrada se corría 3.5 cm por metro hundido."""
    t = tip_of(p)
    d = (t - Vector(p["grip"]) - Vector((0.0, 0.0, p.get("lift") or 0.0))).normalized()
    q = mod(p, **kw)
    q["grip"] = tuple(Vector(p["grip"]) + d * ((tip_z - t.z) / d.z))
    q["sword_ground"] = ground
    return q


def tip_above(p, tip_z):
    """La pose con la empuñadura subida o bajada en vertical hasta que la punta quede a 'tip_z' (hojas
    sueltas que cuelgan cerca del piso: que la clave ya lo esquive y no dependa de clear_floor)."""
    q = mod(p)
    g = Vector(q["grip"])
    q["grip"] = (g.x, g.y, g.z + tip_z - tip_of(p).z)
    return q


READY0 = mod(READY, sword_ground=0.0)      # guardia con la hoja suelta explícita (después de un tramo clavado)


def mix(p, q, w):
    """Pose intermedia entre dos claves (w = 0 -> p, 1 -> q): un cuadro en el aire del salto que no es
    ninguna de las dos. Posiciones y giros en línea recta, direcciones renormalizadas."""
    out = mod(p)
    for k, vb in q.items():
        va = p.get(k)
        if k == "extra" or va is None or vb is None:
            out[k] = copy.deepcopy(vb if va is None else va)
        elif isinstance(vb, (int, float)):
            out[k] = va + (vb - va) * w
        else:
            v = Vector(va).lerp(Vector(vb), w)
            out[k] = tuple(v.normalized() if k in NA.DIR_CHANNELS else v)
    return out


def add(name, frames, keys, loop=False, lag=None, timing=None, events=None, notes="", root_vel=(0, 0, 0)):
    """keys: (cuadro, pose, curva) o (cuadro, pose, curva, {canal: curva}); en ese dict, "stop": (canales,)
    hace de la clave un tope del arco en esos canales (ver nindo_anim.Key)."""
    def key(k):
        ch = dict(k[3]) if len(k) > 3 else {}
        stops = ch.pop("stop", ())
        # cada clave con su propia copia: varios clips (y claves) comparten las poses de la biblioteca
        return Key(k[0], copy.deepcopy(k[1]), k[2], ch, stops)
    c = Clip(name, frames, [key(k) for k in keys], loop=loop,
             lag=LEAD if lag is None else lag, timing=timing, events=events, notes=notes, root_vel=root_vel)
    CLIPS.append(c)
    return c


# =========================================================================== guardia que respira
_breath_in = mod(READY, breath=1.0, hips=(0.0, 0.06, -0.18), grip=(-1.22, 0.38, 1.54), head=(-8.0, 0.0, 3.0))
add("Idle", 72, [(0, READY, "sine"), (36, _breath_in, "sine"), (72, READY, "sine")], loop=True, lag={"head": 3.0, "grip": 2.0},
    notes="wakigamae: una mano, la nodachi colgando atrás; una respiración (el pecho sube a los 1.2 s)")

# =========================================================================== kesagiri (corte del monje)
# AVISO lateral: la hoja alta y hacia afuera, atrás del hombro derecho (desde arriba es una línea
# larga que sale de la silueta; vertical se acortaría y taparía la cabeza). El pie izquierdo entra
# en el impacto y el de atrás se arrastra con la embestida (1.2 m que mueve el juego).
_k_dip = mod(READY, hips=(0.0, 0.14, -0.27), hips_rot=(0.0, 0.0, -26.0), spine=(3.0, 0.0, -4.0), chest=(-2.0, 0.0, -6.0),
             neck=(-2.0, 0.0, 12.0), head=(-6.0, 0.0, 14.0),
             grip=(-1.3, 0.62, 1.8), blade=(-0.2, 0.92, -0.34), edge=(0.0, 0.3, -0.95), elbow_r=(-0.8, 0.4, -0.3))
HIGH_R = mod(READY, hips=(0.0, 0.2, -0.22), hips_rot=(0.0, 0.0, -28.0), spine=(-5.0, -4.0, -12.0), chest=(-6.0, 2.0, -10.0),
             neck=(2.0, 0.0, 18.0), head=(-4.0, 0.0, 24.0), clav_r=(0.0, 8.0, 0.0), clav_l=(0.0, -4.0, -6.0),
             grip=(-0.86, 0.24, 3.6), blade=(-0.55, 0.62, 0.56), edge=(-0.3, -0.62, 0.72), elbow_r=(-0.9, 0.3, 0.2),
             grip_l=1.0, elbow_l=(0.5, -0.6, -0.5))
# el avance sigue la curva del juego: arranca al soltar el apex y lleva ~60 % en el impacto
_k_settle = feet(mod(HIGH_R, hips=(0.0, 0.16, -0.26), grip=(-0.9, 0.27, 3.62), blade=(-0.57, 0.62, 0.54), travel=0.45),
                 r=toe(-0.62, 0.62, -30.0, 12.0), l=((0.53, -0.92, 0.42), (-12.0, 0.0, 14.0)))
_k_mid = feet(mod(HIGH_R, hips=(0.03, -0.14, -0.38), hips_rot=(0.0, 0.0, 2.0), spine=(12.0, 0.0, 2.0), chest=(4.0, 0.0, 2.0),
                  neck=(-4.0, 0.0, 0.0), head=(-8.0, 0.0, -2.0),
                  grip=(-0.35, -0.95, 3.0), blade=(0.2, -0.95, 0.25), edge=(0.6, 0.0, -0.8), elbow_r=(-0.8, -0.2, -0.3),
                  travel=0.6),
              r=toe(-0.62, 0.22, -26.0, 22.0), l=((0.53, -1.7, 0.34), (-8.0, 0.0, 14.0)))
# impacto: paso largo y brazos estirados hacia Kaito (la punta llega a ~4 m del transform: el alcance que
# el juego tiene que usar sale medido en el .fbx.json, reach_m)
_k_impact = feet(mod(HIGH_R, hips=(0.05, -0.44, -0.6), hips_rot=(0.0, 0.0, 24.0), spine=(28.0, 0.0, 10.0), chest=(10.0, 0.0, 2.0),
                     neck=(-12.0, 0.0, -12.0), head=(-16.0, 0.0, -14.0), clav_r=(0.0, -4.0, 8.0), clav_l=(0.0, 4.0, 6.0),
                     grip=(0.34, -1.44, 1.84), blade=(0.58, -0.67, -0.46), edge=(0.55, 0.3, -0.78), elbow_r=(-0.5, 0.1, -0.85),
                     elbow_l=(0.8, 0.3, -0.5), travel=0.72),
                 r=toe(-0.62, -0.12, -28.0, 26.0), l=flat(0.52, -2.08, 14.0))
# después del impacto el juego toca el clip a ~3x (StepTimeline) y vuelve a 1x en 0.1 s: el resto del avance
# (0.48 m) va en línea recta hasta f21 y frena hasta f25, así el cuerpo sigue a la velocidad del tajo
# (~10 m/s) y se detiene; en un solo cuadro era un tirón de 28 m/s
_k_over = feet(mod(_k_impact, hips=(0.06, -0.2, -0.54), hips_rot=(0.0, 0.0, 22.0), spine=(28.0, 0.0, 10.0), chest=(12.0, 0.0, 6.0),
                   grip=(0.45, -1.2, 1.4), blade=(0.72, -0.4, -0.57), edge=(0.6, 0.45, -0.66), travel=1.03),
               r=toe(-0.62, -0.58, -30.0, 18.0))
_k_rec_a = mod(_k_over, hips=(0.05, -0.08, -0.42), hips_rot=(0.0, 0.0, 18.0), spine=(22.0, 0.0, 8.0),
               grip=(0.4, -0.84, 1.56), blade=(0.66, -0.4, -0.62), travel=1.2)
_low_l_w = at_travel(LOW_L, 1.2)
_k_step = feet(mod(_low_l_w, hips=(0.05, -0.08, -0.38)), r=toe(-0.62, -0.58, -30.0, 6.0))
add("Kesagiri", 36, [
    (0, READY, "sine"), (8, _k_dip, "sine"), (14, HIGH_R, "inout"), (16, _k_settle, "sine"), (17, _k_mid, "expo_in"),
    (18, _k_impact, "lin"), (21, _k_over, "expo_out", {"foot_r": "out2", "foot_r_rot": "out2", "travel": "lin"}),
    (25, _k_rec_a, "sine", {"travel": "out2"}), (30, _k_step, "inout"), (36, _low_l_w, "inout")],
    timing={"tell": [0, 14], "apex": 14, "hold": [14, 16], "contact": 18, "active": [18, 21], "recover": [21, 36],
            "lunge": [14, 25, 1.2], "kind": "parry", "chain_from": "READY", "chain_to": "LOW_L"},
    events=[{"frame": 14, "fn": "Apex"}, {"frame": 18, "fn": "Strike"}, {"frame": 18, "fn": "Step"}, {"frame": 34, "fn": "Step"}],
    notes="apex HIGH_R (hoja alta y afuera, atrás del hombro derecho); el pie izquierdo apoya en el impacto")

# solver compartido para los clips que necesitan leer la pose resuelta (soltar la espada, la máscara)
SOLVER = None


def solved(clip, f):
    """Pose resuelta de un cuadro del clip (sin resortes): para anclar en el mundo lo que se suelta."""
    pose = NA.Pose(SOLVER.rig)
    SOLVER.solve(pose, clip.controls(f))
    for n in SOLVER.rig.names:
        pose.get(n)
    return pose.W


# =========================================================================== recuperaciones cortas
add("RecoverL", 15, [(0, LOW_L, "sine"), (8, mod(READY, hips=(0.0, 0.0, -0.22), grip=(-0.9, -0.1, 1.5), blade=(-0.3, 0.6, -0.74),
                                                  grip_l=0.3), "sine"), (15, READY, "sine")],
    timing={"recover": [0, 15], "chain_from": "LOW_L", "chain_to": "READY"}, notes="LOW_L -> guardia (cierra un patrón)")
# chiburi: sacude la hoja (castigo corto que cierra un patrón y le da carácter)
_chi_a = mod(READY, grip=(-1.0, -0.35, 2.3), blade=(-0.45, -0.75, 0.48), edge=(-0.2, -0.45, -0.87), elbow_r=(-0.8, 0.2, -0.3),
             chest=(2.0, 0.0, 2.0), head=(-4.0, 0.0, 6.0))
_chi_b = mod(READY, grip=(-1.28, 0.05, 1.45), blade=(-0.6, 0.2, -0.78), edge=(-0.6, -0.5, 0.2), elbow_r=(-0.8, 0.3, -0.3))
add("RecoverHR", 12, [(0, READY, "sine"), (5, _chi_a, "out"), (7, _chi_b, "snap"), (12, READY, "sine")],
    timing={"recover": [0, 12], "chain_from": "READY", "chain_to": "READY"}, notes="chiburi: sacude la sangre de la hoja")

# =========================================================================== gyakugiri (luna ascendente)
# desde LOW_L: se enrosca bajo a su izquierda y corta subiendo hasta arriba a su derecha
# el enrosque deja la hoja casi horizontal y abierta a su izquierda (desde arriba sale de la silueta hacia
# el lado contrario de la guardia: el aviso se lee por la forma)
_g_coil = feet(mod(LOW_L, hips=(0.3, 0.06, -0.62), hips_rot=(0.0, 0.0, 38.0), spine=(20.0, 10.0, 14.0), chest=(6.0, 6.0, 12.0),
                   neck=(-8.0, -8.0, -26.0), head=(-10.0, -8.0, -30.0),
                   grip=(1.25, 0.25, 1.5), blade=(0.84, 0.47, -0.22), edge=(0.1, 0.25, 0.96), elbow_r=(-0.3, -0.4, -0.9)),
               l=flat(*L_FOOT))
_g_hold = mod(_g_coil, hips=(0.3, 0.07, -0.64), grip=(1.27, 0.27, 1.49), blade=(0.84, 0.48, -0.21))
_g_hold2 = mod(_g_coil, hips=(0.3, 0.075, -0.645), grip=(1.28, 0.28, 1.48), blade=(0.84, 0.49, -0.2))
# primer cuadro del golpe: la hoja apenas sale del enrosque (el barrido grande es f12-14, con el impacto)
_g_mid = feet(mod(_g_coil, hips=(0.03, -0.05, -0.5), hips_rot=(0.0, 0.0, 22.0), spine=(14.0, 0.0, 8.0), chest=(3.0, 0.0, 6.0),
                  neck=(-6.0, 0.0, -14.0), head=(-8.0, 0.0, -16.0),
                  grip=(0.85, -0.35, 1.55), blade=(0.86, 0.12, -0.5), edge=(0.3, -0.3, 0.9), travel=0.3),
              r=toe(-0.62, 0.45, -30.0, 20.0), l=((0.53, -0.98, 0.38), (-10.0, 0.0, 14.0)))
_g_impact = feet(mod(_g_coil, hips=(-0.05, -0.18, -0.34), hips_rot=(0.0, 0.0, -24.0), spine=(4.0, 0.0, -14.0), chest=(-4.0, 0.0, -10.0),
                     neck=(-2.0, 0.0, 18.0), head=(-6.0, 0.0, 22.0), clav_r=(0.0, 10.0, 0.0),
                     grip=(-0.55, -0.85, 2.95), blade=(-0.6, -0.5, 0.62), edge=(-0.55, 0.0, 0.83), elbow_r=(-0.8, 0.3, -0.2),
                     elbow_l=(0.4, -0.6, -0.6), travel=0.6),
                 r=toe(-0.62, 0.2, -30.0, 20.0), l=flat(0.52, -1.38, 14.0))
_g_over = feet(mod(_g_impact, hips=(-0.06, -0.05, -0.3), hips_rot=(0.0, 0.0, -32.0), spine=(0.0, 0.0, -16.0),
                   grip=(-0.82, -0.45, 3.35), blade=(-0.62, 0.05, 0.78), edge=(-0.7, 0.3, -0.5), travel=0.8),
               r=toe(-0.62, -0.18, -30.0, 14.0))
_g_drop = feet(mod(READY, hips=(0.0, 0.0, -0.2), grip=(-1.12, 0.05, 2.1), blade=(-0.62, 0.35, -0.2), grip_l=0.0,
                   hand_l=(0.8, -0.6, 2.0), travel=0.8), r=flat(-0.62, -0.18, -30.0), l=flat(0.52, -1.38, 14.0))
_g_end = at_travel(READY, 0.8)
add("Gyakugiri", 30, [
    (0, LOW_L, "sine"), (7, _g_coil, "inout"), (10, _g_hold, "sine"), (11, _g_hold2, "sine"), (12, _g_mid, "expo_in"),
    (14, _g_impact, "lin"), (17, _g_over, "expo_out", {"foot_r": "snap", "foot_r_rot": "snap"}), (25, _g_drop, "sine"),
    (30, _g_end, "sine")],
    timing={"tell": [0, 10], "apex": 10, "hold": [10, 11], "contact": 14, "active": [14, 17], "recover": [17, 30],
            "lunge": [10, 15, 0.8], "kind": "parry", "chain_from": "LOW_L", "chain_to": "READY"},
    events=[{"frame": 10, "fn": "Apex"}, {"frame": 14, "fn": "Strike"}, {"frame": 14, "fn": "Step"}],
    notes="apex enroscado bajo a su izquierda (cadera 15 cm más baja); corta subiendo hasta arriba a su derecha")

# =========================================================================== tsuki (colmillo)
# AVISO en hanmi: gira la cadera 56° a su derecha y RECOGE la nodachi atrás de la cadera derecha, con la
# hoja horizontal abierta hacia afuera y el brazo izquierdo estirado APUNTANDO a Kaito. Desde la cámara del
# jefe se ve el cambio de forma: la empuñadura asoma arriba a la derecha (detrás) y la hoja sale de la
# silueta por su derecha. La recogida es un solo arco lento: la hoja gira 120° desde colgar atrás, la punta
# recorre ~5 m y tiene que quedar bajo el 30 % del pico de la estocada (un barrido rápido que no pega es un
# aviso de parry falso). El juego toca la anticipación con un seno (arranca a 1.3x y llega al apex frenando):
# la hoja avanza poco en los primeros cuadros (f0-4), parejo en el medio y frena en f20-22; así, con el reloj
# del juego, la punta va pareja todo el arco.
# La embestida (3.5 m) es un salto: empuja con el pie de atrás, los dos pies dejan el piso y el de adelante
# cae en el impacto; después se desliza apenas 30 cm sobre ese pie ya clavado (lo mueve el juego). La hoja
# viaja recogida en el aire y la estocada se estira de golpe al caer: lo más rápido del clip es el golpe.
# Reloj del juego: la suelta (apex -> impacto) se toca con u² (StepTimeline), así que los cuadros del clip
# justo después del apex duran mucho y los del final poco. Con release_rate 0.4 la suelta dura 0.42 s: la
# espera f22-23 se ve 0.15 s, el empuje f23-24 0.1 s (de 4 a 9 m/s) y el vuelo f24-27 0.17 s a 13-16 m/s.
# El avance por cuadro del clip va decreciendo en el vuelo (0.99, 0.79, 0.7 m) para compensar la u². Con la
# suelta por defecto (1.6) el salto entero dura 0.1 s y el gigante se teletransporta (chequeo de 20 m/s).
TSUKI_RELEASE = 0.4
_T_APEX_SWORD = dict(grip=(-0.92, 1.08, 1.98), blade=(-0.5, -0.86, -0.08), edge=(0.0, 0.0, -1.0))


def _t_sword(w):
    """La hoja a la fracción w del arco de la recogida (0 = colgando atrás en la guardia, 1 = el aviso): la
    dirección y el filo giran por el arco más corto y la empuñadura se abre un poco hacia afuera al pasar
    junto a la cadera."""
    bulge = math.sin(math.pi * w)
    g = Vector(READY["grip"]).lerp(Vector(_T_APEX_SWORD["grip"]), w) + Vector((-0.14 * bulge, 0.0, 0.08 * bulge))
    return dict(grip=tuple(g), blade=tuple(NA.slerp_dir(READY["blade"], _T_APEX_SWORD["blade"], w)),
                edge=tuple(NA.slerp_dir(READY["edge"], _T_APEX_SWORD["edge"], w)))


_t_turn = mod(READY, hips=(0.0, 0.07, -0.2), hips_rot=(0.0, 0.0, -22.0), spine=(5.0, 0.0, -2.0), chest=(2.0, 0.0, -2.0),
              neck=(-4.0, 0.0, 6.0), head=(-6.0, 0.0, 8.0),
              hand_l=(0.8, -0.85, 1.95), hand_l_dir=(-0.05, -0.95, 0.3), hand_l_up=(-1.0, 0.0, 0.0), **_t_sword(0.07))
_t_under = mod(READY, hips=(0.0, 0.14, -0.3), hips_rot=(0.0, 0.0, -30.0), spine=(4.0, 0.0, -6.0), chest=(0.0, 0.0, -6.0),
               neck=(-4.0, 0.0, 14.0), head=(-6.0, 0.0, 16.0), elbow_r=(-0.7, 0.6, -0.2),
               hand_l=(0.62, -1.2, 2.3), hand_l_dir=(-0.05, -0.95, 0.3), hand_l_up=(-1.0, 0.0, 0.0), elbow_l=(0.6, 0.2, -0.6),
               **_t_sword(0.44))
_t_gather = mod(_t_under, hips=(0.0, 0.28, -0.42), hips_rot=(0.0, 0.0, -52.0), spine=(8.0, 0.0, -11.0), chest=(2.0, 0.0, -11.0),
                neck=(-6.0, 0.0, 30.0), head=(-8.0, 0.0, 34.0), elbow_r=(-0.6, 0.8, 0.1),
                hand_l=(0.3, -2.1, 2.85), hand_l_dir=(-0.05, -0.97, 0.2), elbow_l=(0.6, 0.1, -0.6), **_t_sword(0.93))
TSUKI_APEX = mod(_t_gather, hips=(0.0, 0.3, -0.45), hips_rot=(0.0, 0.0, -56.0), spine=(8.0, 0.0, -12.0), chest=(2.0, 0.0, -12.0),
                 neck=(-6.0, 0.0, 32.0), head=(-8.0, 0.0, 36.0), hand_l=(0.22, -2.25, 2.9), **_T_APEX_SWORD)
# la espera carga el peso sobre el pie de atrás (apenas baja y se adelanta 3 cm)
_t_hold = mod(TSUKI_APEX, hips=(0.0, 0.31, -0.48), grip=(-0.92, 1.1, 1.96), hand_l=(0.22, -2.27, 2.88), travel=0.03)
# empuje: el pie de atrás se para en punta (la punta no se mueve) y el izquierdo ya se levanta; el tronco
# empieza a desenroscarse pero la hoja sigue recogida junto a la cadera
_t_launch = feet(mod(TSUKI_APEX, hips=(0.0, 0.08, -0.42), hips_rot=(0.0, 0.0, -24.0), spine=(14.0, 0.0, -4.0),
                     grip=(-0.84, 0.8, 1.98), blade=(-0.42, -0.9, -0.1), hand_l=(0.5, -1.4, 2.5), travel=0.72),
                 r=toe(*R_FOOT, heel=48.0), l=((0.52, -1.5, 0.5), (-12.0, 0.0, 12.0)))


def _air(x, y, z, rot, travel):
    """Pie en el aire a (x, y, z) RELATIVO al transform (los pies del salto viajan con el cuerpo)."""
    return (x, y - travel, z), rot


# en el aire: los dos pies despegados (la cadera sube un poco en el medio del salto), la hoja apuntando a
# Kaito y todavía recogida: se estira entera recién en el último cuadro, al caer
_t_fly = feet(mod(THRUST_END, hips=(0.0, -0.12, -0.4), hips_rot=(0.0, 0.0, 8.0), spine=(14.0, 0.0, 4.0),
                  grip=(-0.6, -0.45, 2.02), blade=(-0.08, -0.97, -0.22), hand_l=(0.9, 0.2, 2.2), travel=2.5),
              r=_air(-0.62, 0.8, 0.62, (36.0, 0.0, -26.0), 2.5), l=_air(0.52, -1.05, 0.46, (-8.0, 0.0, 14.0), 2.5))
_t_fly_a = feet(mod(mix(_t_launch, _t_fly, 0.5), hips=(0.0, -0.02, -0.36), grip=(-0.74, 0.5, 2.0), blade=(-0.26, -0.95, -0.16),
                    travel=1.71),
                r=_air(-0.62, 1.1, 0.7, (44.0, 0.0, -28.0), 1.71), l=_air(0.52, -0.82, 0.62, (-14.0, 0.0, 12.0), 1.71))
_t_impact = at_travel(feet(mod(THRUST_END, hips=(0.0, -0.36, -0.58)), r=((-0.62, 0.5, 0.52), (30.0, 0.0, -28.0)),
                           l=flat(0.52, -1.38, 14.0)), 3.2)
_t_end = at_travel(THRUST_END, 3.5)
_t_end_hold = mod(_t_end, hips=(0.0, -0.33, -0.6), grip=(-0.3, -1.66, 1.98))
_T_ARC = {"grip": "lin", "blade": "lin", "edge": "lin"}
add("Tsuki", 46, [
    (0, READY, "sine"), (4, _t_turn, "sine", {"grip": "in2", "blade": "in2", "edge": "in2"}), (12, _t_under, "sine", _T_ARC),
    (20, _t_gather, "sine", _T_ARC), (22, TSUKI_APEX, "out", {"grip": "out2", "blade": "out2", "edge": "out2"}),
    (23, _t_hold, "sine"),
    (24, _t_launch, "in2"), (25, _t_fly_a, "lin"), (26, _t_fly, "lin"), (27, _t_impact, "lin"),
    (30, _t_end, "expo_out", {"travel": "out"}), (46, _t_end_hold, "sine")],
    timing={"tell": [0, 22], "apex": 22, "hold": [22, 23], "contact": 27, "active": [27, 30], "recover": [30, 46],
            "lunge": [23, 30, 3.5], "release_rate": TSUKI_RELEASE, "kind": "parry", "chain_from": "READY", "chain_to": "THRUST_END"},
    events=[{"frame": 22, "fn": "Apex"}, {"frame": 24, "fn": "Step"}, {"frame": 27, "fn": "Strike"}, {"frame": 27, "fn": "Step"}],
    notes="estocada desde hanmi: la nodachi recogida atrás de la cadera derecha y el brazo izquierdo apunta a Kaito; "
          "empuja f23-24, vuela f24-27 (3.2 m) con la hoja recogida y la estira al caer sobre el pie de adelante en el "
          "impacto; la punta llega a ~1.1 m de alto. AttackDef.releaseRate = release_rate (0.4): el salto dura 0.27 s a "
          "~14 m/s; con 1.6 dura 0.1 s")
# el pie de adelante vuelve atrás de un paso y el de atrás se arrastra hasta la guardia
_tr_a = feet(mod(THRUST_END, hips=(0.0, -0.18, -0.42), hips_rot=(0.0, 0.0, 10.0), spine=(10.0, 0.0, 4.0),
                 grip=(-0.7, -1.2, 2.0), blade=(-0.1, -0.95, -0.3), hand_l=(1.0, 0.2, 1.9)),
             r=toe(*R_FOOT, heel=12.0), l=((0.52, -0.86, 0.46), (-10.0, 0.0, 14.0)))
_tr_b = feet(mod(READY, hips=(0.0, 0.02, -0.2), grip=(-1.1, 0.05, 1.6), blade=(-0.3, 0.7, -0.65)),
             r=toe(*R_FOOT, heel=8.0), l=flat(*L_FOOT))
add("TsukiRecover", 18, [(0, THRUST_END, "sine"), (6, _tr_a, "inout"), (12, _tr_b, "inout", {"foot_l": "out2"}), (18, READY, "sine")],
    timing={"recover": [0, 18], "chain_from": "THRUST_END", "chain_to": "READY"},
    events=[{"frame": 12, "fn": "Step"}], notes="castigo: retrae la estocada; el pie de atrás se adelanta")


# =========================================================================== ichimonji (horizonte, imparable)
# se enrosca a su izquierda con la hoja horizontal atrás (aviso lento y ancho: dash o meterse bajo
# la empuñadura) y barre 240° a la altura de la cintura hasta pasarse atrás a su derecha
ICHI_BASE = mod(READY, hips=(0.05, 0.06, -0.4), grip_l=1.0, elbow_r=(-0.6, 0.5, -0.6), elbow_l=(0.6, 0.5, -0.6))


def _sweep(az_deg, r=1.05, z=2.05, hips_rot=0.0, spine_z=0.0, chest_z=0.0, tip_z=0.02, lean=0.0, **kw):
    """Pose del barrido: la hoja apunta al azimut dado (0 = frente, + = hacia su izquierda); 'lean' inclina
    el tronco hacia su izquierda (+) o derecha (-)."""
    a = math.radians(az_deg)
    bd = Vector((math.sin(a), -math.cos(a), tip_z)).normalized()
    edge = Vector((-math.cos(a), -math.sin(a), 0.0))          # el filo mira hacia donde barre (horario)
    g = Vector((math.sin(a) * r, -math.cos(a) * r * 0.85, z))
    turn = hips_rot + spine_z + chest_z
    return feet(mod(ICHI_BASE, hips_rot=(0.0, 0.0, hips_rot), spine=(8.0, lean, spine_z), chest=(2.0, lean * 0.5, chest_z),
                    neck=(-4.0, 0.0, -turn * 0.55), head=(-6.0, 0.0, -turn * 0.4),
                    grip=tuple(g), blade=tuple(bd), edge=tuple(edge), **kw), r=flat(-0.98, 0.74, -40.0), l=flat(*L_FOOT))


_i_step = feet(mod(READY, hips=(0.03, 0.06, -0.26), hips_rot=(0.0, 0.0, 6.0), grip=(-0.4, 0.2, 1.7), blade=(0.6, 0.5, -0.62),
                   grip_l=0.6), r=((-0.82, 0.7, 0.46), (-10.0, 0.0, -36.0)), l=flat(*L_FOOT))
# el enrosque levanta la hoja (apunta arriba y afuera a su izquierda: desde arriba es una línea larga que
# sale de la silueta); el barrido baja: la empuñadura pasa alta (el núcleo seguro bajo ella se ve) y la punta
# corta a ~1 m del piso en la banda que pega
ICHI_APEX = _sweep(122.0, r=0.95, z=2.12, hips_rot=34.0, spine_z=12.0, chest_z=8.0, tip_z=0.3, lean=10.0, hips=(0.3, 0.1, -0.5))
_ICHI_CUT = dict(z=1.9, tip_z=-0.36)
add("Ichimonji", 48, [
    (0, READY, "sine"), (9, _i_step, "inout"),
    (16, _sweep(114.0, r=0.95, z=2.08, hips_rot=28.0, spine_z=10.0, chest_z=6.0, tip_z=0.2, lean=7.0, hips=(0.22, 0.08, -0.46)), "inout"),
    (21, ICHI_APEX, "sine"),
    (24, _sweep(126.0, r=0.95, z=2.12, hips_rot=35.0, spine_z=12.0, chest_z=8.0, tip_z=0.31, lean=10.0, hips=(0.31, 0.1, -0.51)), "sine"),
    (26, _sweep(90.0, hips_rot=22.0, spine_z=8.0, chest_z=6.0, **_ICHI_CUT), "in2"),
    (28, _sweep(30.0, hips_rot=6.0, spine_z=4.0, chest_z=2.0, **_ICHI_CUT), "lin"), (29, _sweep(-8.0, hips_rot=-8.0, **_ICHI_CUT), "lin"),
    (30, _sweep(-48.0, hips_rot=-20.0, spine_z=-6.0, chest_z=-4.0, **_ICHI_CUT), "lin"),
    (31, _sweep(-88.0, hips_rot=-30.0, spine_z=-10.0, chest_z=-6.0, **_ICHI_CUT), "lin"),
    (34, _sweep(-118.0, r=1.0, z=1.86, hips_rot=-42.0, spine_z=-12.0, chest_z=-8.0, tip_z=-0.32), "out"),
    (38, _sweep(-125.0, r=0.95, z=1.8, hips_rot=-40.0, spine_z=-10.0, chest_z=-8.0, tip_z=-0.36, grip_l=0.5), "sine"),
    (43, feet(mod(READY, hips=(0.0, 0.05, -0.24), hips_rot=(0.0, 0.0, -20.0), grip=(-1.2, 0.3, 1.6)),
              r=((-0.8, 0.68, 0.44), (-10.0, 0.0, -34.0)), l=flat(*L_FOOT)), "inout"),
    (48, READY, "inout")],
    timing={"tell": [0, 21], "apex": 21, "hold": [21, 24], "contact": 28, "active": [28, 32], "recover": [32, 48],
            "lunge": [24, 29, 0.0], "kind": "dodge", "safe_core_m": 1.65, "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 21, "fn": "Apex"}, {"frame": 28, "fn": "Strike"}],
    notes="barrido de 240° a la cintura; se pasa 0.33 s (castigo). Sin embestida: la hoja ya llega a 4.4 m")

# =========================================================================== kabuto-wari (rompecascos, imparable)
# AVISO: en puntas de pie con la hoja HORIZONTAL detrás de la cabeza (jōdan-ura: la silueta no pasa
# de 5.8 m); el tajo baja por encima y la hoja queda clavada: dos tirones (castigo) y la arranca
_kw_crouch = feet(mod(READY, hips=(0.0, 0.1, -0.48), hips_rot=(0.0, 0.0, -10.0), spine=(18.0, 0.0, -4.0), chest=(6.0, 0.0, -2.0),
                      neck=(-10.0, 0.0, 6.0), head=(-14.0, 0.0, 8.0),
                      grip=(-0.75, 0.05, 1.85), blade=(-0.3, 0.75, 0.59), edge=(-0.2, -0.6, 0.77), grip_l=1.0,
                      elbow_r=(-0.8, 0.4, -0.4), elbow_l=(0.6, -0.4, -0.6)),
                  r=flat(*R_FOOT), l=flat(*L_FOOT))
_kw_rise = feet(mod(_kw_crouch, hips=(0.0, 0.12, -0.08), spine=(-2.0, 0.0, 0.0), chest=(-4.0, 0.0, 0.0), neck=(-4.0, 0.0, 2.0),
                    head=(-6.0, 0.0, 2.0), grip=(-0.25, 0.2, 3.6), blade=(-0.25, 0.85, 0.46), edge=(0.0, -0.45, 0.89)),
                r=toe(*R_FOOT, heel=14.0), l=toe(*L_FOOT, heel=12.0))
KW_APEX = feet(mod(_kw_rise, hips=(0.0, 0.12, 0.03), spine=(-8.0, 0.0, 0.0), chest=(-8.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0),
                   head=(-4.0, 0.0, 0.0), clav_r=(0.0, 10.0, 0.0), clav_l=(0.0, -10.0, 0.0),
                   grip=(-0.05, 0.25, 4.12), blade=(-0.1, 0.99, -0.08), edge=(0.0, 0.08, 1.0),
                   elbow_r=(-0.9, -0.2, 0.2), elbow_l=(0.9, -0.2, 0.2)),
               r=toe(*R_FOOT, heel=22.0), l=toe(*L_FOOT, heel=20.0))
_kw_hold = mod(KW_APEX, grip=(-0.05, 0.27, 4.13), blade=(-0.1, 0.99, -0.09))
_kw_a = feet(mod(KW_APEX, hips=(0.0, -0.05, -0.12), spine=(6.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0),
                 grip=(-0.05, -0.62, 3.45), blade=(0.0, 0.55, 0.83), edge=(0.0, -0.83, 0.55)),
             r=toe(*R_FOOT, heel=16.0), l=((0.52, -0.95, 0.5), (-12.0, 0.0, 14.0)))
_kw_b = feet(mod(KW_APEX, hips=(0.0, -0.18, -0.36), spine=(18.0, 0.0, 0.0), chest=(8.0, 0.0, 0.0), neck=(-8.0, 0.0, 0.0),
                 head=(-10.0, 0.0, 0.0), grip=(0.0, -1.25, 2.6), blade=(0.0, -0.55, 0.83), edge=(0.0, -0.83, -0.55)),
             r=toe(*R_FOOT, heel=10.0), l=((0.52, -1.55, 0.34), (-6.0, 0.0, 14.0)))
KW_TIP = Vector((0.0, -3.98, -0.42))      # donde queda clavada la punta en el impacto (0.4 m bajo el piso)


def _kw_chord(d):
    """Dirección y filo de la hoja, y el vector empuñadura -> punta (la hoja es curva: no es el eje del hueso)."""
    d = Vector(d).normalized()
    e = Vector((0.0, -d.z, d.y))
    return d, e, NA.basis_yz(d, -e) @ KR.TIP_LOCAL


# la ranura que abre en la piedra: los tirones hacen palanca ahí (no en la punta enterrada, que se corre)
_c0 = _kw_chord((0.0, -0.8, -0.6))[2]
_g0 = KW_TIP - _c0                         # empuñadura del impacto
_r0 = _g0.z / -_c0.z                       # fracción de la cuerda que queda sobre el piso
KW_ENTRY = _g0 + _c0 * _r0
KW_ABOVE = _c0.length * _r0


def _kw_stuck(d):
    """Empuñadura y hoja clavadas en la dirección d, pivotando en la ranura KW_ENTRY."""
    d, e, c = _kw_chord(d)
    return dict(grip=tuple(KW_ENTRY - c.normalized() * KW_ABOVE), blade=tuple(d), edge=tuple(e))


KW_IMPACT = feet(mod(KW_APEX, hips=(0.0, -0.4, -0.7), spine=(36.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(-12.0, 0.0, 0.0),
                     head=(-16.0, 0.0, 0.0), clav_r=(0.0, -4.0, 6.0), clav_l=(0.0, 4.0, -6.0),
                     elbow_r=(-0.7, 0.3, -0.6), elbow_l=(0.7, 0.3, -0.6), sword_ground=1.0, **_kw_stuck((0.0, -0.8, -0.6))),
                 r=toe(*R_FOOT, heel=32.0), l=flat(0.52, -1.72, 14.0))
_kw_tug1 = mod(KW_IMPACT, hips=(0.0, -0.32, -0.64), spine=(20.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0), neck=(-4.0, 0.0, 0.0), head=(-10.0, 0.0, 0.0),
               **_kw_stuck((0.0, -0.79, -0.62)))
_kw_slack = mod(KW_IMPACT, hips=(0.0, -0.34, -0.68), spine=(32.0, 0.0, 0.0))
_kw_tug2 = mod(KW_IMPACT, hips=(0.0, -0.33, -0.62), spine=(16.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0),
               head=(-12.0, 0.0, 0.0), **_kw_stuck((0.0, -0.76, -0.65)))
_kw_yank0 = mod(_kw_tug2, hips=(0.0, -0.34, -0.6), spine=(22.0, 0.0, 0.0), **_kw_stuck((0.0, -0.72, -0.69)))
# el tercer tirón la saca por su eje (antes giraba hacia arriba con la punta enterrada: la entrada en la
# piedra se corría casi un metro en un cuadro); recién afuera la levanta
_kw_out = along(_kw_yank0, 0.08, 0.0, hips=(0.0, -0.3, -0.5), spine=(14.0, 0.0, 0.0), chest=(-4.0, 0.0, 0.0), head=(-12.0, 0.0, 0.0))
_kw_lift = feet(mod(_kw_yank0, hips=(0.0, -0.32, -0.5), spine=(16.0, 0.0, 0.0), grip=(-0.2, -1.25, 1.9), blade=(-0.1, -0.85, 0.5),
                    edge=(0.0, -0.5, -0.86)), r=toe(*R_FOOT, heel=18.0), l=flat(0.52, -1.72, 14.0))
_kw_lift["sword_ground"] = 0.0
_kw_free = feet(mod(READY, hips=(0.0, 0.0, -0.32), spine=(4.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0),
                    grip=(-0.62, -0.62, 2.45), blade=(-0.3, 0.25, 0.92), edge=(-0.3, -0.9, 0.2), grip_l=1.0,
                    elbow_r=(-0.8, 0.3, -0.3), elbow_l=(0.6, -0.4, -0.6)),
                r=flat(*R_FOOT), l=((0.52, -1.1, 0.46), (-10.0, 0.0, 14.0)))
add("KabutoWari", 60, [
    (0, READY, "sine"), (12, _kw_crouch, "inout"), (17, _kw_rise, "out"), (20, KW_APEX, "out"), (23, _kw_hold, "sine"),
    (25, _kw_a, "expo_in"), (26, _kw_b, "lin"), (27, KW_IMPACT, "lin", {"foot_l": "snap", "stop": ("grip",)}), (33, _kw_tug1, "inout"),
    (36, _kw_slack, "inout"), (39, _kw_tug2, "inout"), (44, _kw_yank0, "sine", {"stop": ("grip",)}),
    (48, _kw_out, "inout", SWORD_IN),
    (52, _kw_lift, "out"), (56, _kw_free, "inout"), (60, READY0, "inout")],
    timing={"tell": [0, 20], "apex": 20, "hold": [20, 24], "contact": 27, "active": [27, 29], "recover": [29, 60],
            "stuck": [28, 44], "rift_start": 27, "ground": [[27, 46]], "bite": [27], "kind": "dodge", "chain_from": "READY",
            "chain_to": "READY"},
    events=[{"frame": 20, "fn": "Apex"}, {"frame": 27, "fn": "Strike"}, {"frame": 27, "fn": "RiftStart"},
            {"frame": 33, "fn": "Tug"}, {"frame": 39, "fn": "Tug"}, {"frame": 47, "fn": "BladeFree"}],
    notes="la hoja queda clavada f28-44 (0.55 s de golpes libres); la grieta de obsidiana arranca en f27")

# =========================================================================== paso de sombra
_ss_crouch = feet(mod(READY, hips=(0.0, 0.06, -0.58), spine=(30.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(-12.0, 0.0, 0.0),
                      head=(-16.0, 0.0, 0.0), grip=(-0.95, 0.3, 1.25), blade=(-0.2, 0.75, -0.63), hand_l=(0.7, -0.7, 1.3)),
                  r=flat(*R_FOOT), l=flat(*L_FOOT))
add("ShadowSink", 21, [(0, READY, "sine"), (6, _ss_crouch, "inout"), (12, mod(_ss_crouch, lift=-1.1), "in2"),
                        (18, mod(_ss_crouch, lift=-4.0), "in2"), (21, mod(_ss_crouch, lift=-4.0), "lin")],
    timing={"kind": "none", "chain_from": "READY", "ground": [[8, 21]], "sink": [[7, 21]]}, events=[{"frame": 8, "fn": "ShadowPuddle"}],
    notes="se agacha y se hunde 4 m en su propia sombra (el charco violeta lo pone el juego)")
# sale del charco todavía más enroscado que el gyakugiri (viene de abajo: se lee aunque aparezca de costado)
_se_hold = mod(_g_hold, hips=(0.34, 0.08, -0.66), spine=(22.0, 12.0, 14.0), chest=(6.0, 8.0, 12.0))
_se_hold2 = mod(_se_hold, hips=(0.34, 0.085, -0.665), grip=(1.28, 0.28, 1.48), blade=(0.84, 0.49, -0.2))
add("ShadowEmerge", 33, [
    (0, mod(_g_hold, lift=-4.0), "lin"), (5, mod(_g_hold, lift=0.18, hips=(0.24, 0.0, -0.42)), "out"), (7, mod(_g_hold, lift=0.0), "in2"),
    (9, _se_hold, "sine"), (11, _se_hold2, "sine"), (12, _g_mid, "expo_in"), (14, _g_impact, "lin"),
    (17, _g_over, "expo_out", {"foot_r": "snap", "foot_r_rot": "snap"}), (25, _g_drop, "sine"), (33, _g_end, "sine")],
    timing={"tell": [5, 9], "apex": 9, "hold": [9, 11], "contact": 14, "active": [14, 17], "recover": [17, 33],
            "lunge": [10, 15, 0.8], "kind": "parry", "chain_to": "READY", "ground": [[0, 4]], "sink": [[0, 4]]},
    events=[{"frame": 4, "fn": "ShadowErupt"}, {"frame": 9, "fn": "Apex"}, {"frame": 14, "fn": "Strike"}],
    notes="sale del charco enroscado y corta subiendo (como el gyakugiri)")

# =========================================================================== reacciones
# parry recibido: el brazo de la espada sale disparado arriba y atrás, la cabeza se va atrás y el
# gigante se balancea sobre los talones (los pies no se mueven: a los 0.5 s puede seguir el combo)
_p_hit = feet(mod(READY, hips=(0.0, 0.22, -0.18), hips_rot=(0.0, 0.0, -14.0), spine=(-14.0, 0.0, -4.0), chest=(-10.0, 0.0, 6.0),
                  neck=(-8.0, 0.0, 6.0), head=(-18.0, 0.0, 10.0), clav_r=(0.0, 14.0, 0.0),
                  grip=(-1.12, 0.55, 3.55), blade=(-0.32, 0.6, 0.73), edge=(-0.4, -0.75, 0.53), elbow_r=(-0.9, 0.3, 0.2),
                  hand_l=(1.35, -0.25, 2.55), hand_l_dir=(0.7, -0.3, 0.6), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.6, 0.6, -0.4)),
              r=flat(*R_FOOT), l=flat(*L_FOOT))
# el empujón del parry: el cuerpo retrocede KNOCK metros con la curva del juego (1 - e^(-10 t), la de
# Enemy.knock) y los pies lo acompañan: el de atrás da el paso primero y el de adelante se arrastra
KNOCK = 0.6


def _knock(f):
    return -KNOCK * (1.0 - math.exp(-10.0 * f / NA.FPS))


_p_lift = feet(mod(_p_hit, hips=(0.0, 0.32, -0.2), spine=(-16.0, 0.0, -4.0), head=(-19.0, 0.0, 11.0), travel=_knock(2)),
               r=((-0.64, 1.0, 0.44), (6.0, 0.0, -30.0)), l=flat(*L_FOOT))
_p_rock = feet(mod(_p_hit, hips=(0.0, 0.42, -0.26), spine=(-18.0, 0.0, -4.0), head=(-20.0, 0.0, 12.0),
                   grip=(-1.15, 0.65, 3.4), blade=(-0.3, 0.72, 0.62), travel=_knock(5)),
               r=flat(R_FOOT[0], R_FOOT[1] + KNOCK, R_FOOT[2]), l=heel(*L_FOOT, toe_up=22.0))
_p_back = feet(mod(_p_hit, hips=(0.0, 0.25, -0.3), spine=(2.0, 0.0, 0.0), chest=(0.0, 0.0, 2.0), head=(-4.0, 0.0, 4.0),
                   grip=(-0.6, 0.0, 2.4), blade=(0.3, -0.4, -0.86), hand_l=(0.8, -0.5, 2.2), travel=_knock(9)),
               r=flat(R_FOOT[0], R_FOOT[1] + KNOCK, R_FOOT[2]), l=heel(L_FOOT[0], L_FOOT[1] + 0.28, L_FOOT[2], toe_up=10.0))
_lin_travel = {"travel": "lin"}
add("Parried", 30, [(0, _p_hit, "lin"), (2, _p_lift, "out", _lin_travel), (5, _p_rock, "out", _lin_travel),
                    (9, _p_back, "inout", _lin_travel), (15, at_travel(LOW_L, -KNOCK), "inout"), (30, at_travel(READY, -KNOCK), "sine")],
    lag={"head": 2.0, "neck": 1.0, "hand_l": 1.5},
    timing={"recover": [0, 30], "resume": 15, "chain_to": "READY", "knock_m": KNOCK, "knock_curve": "1 - exp(-10 t)"},
    events=[{"frame": 0, "fn": "Parried"}, {"frame": 5, "fn": "Step"}],
    notes="el clip de 'feel' más importante: cada parry tiene que sacudir al gigante. Retrocede knock_m (0.6 m) con la "
          "curva de Enemy.knock: el juego lo tiene que empujar exactamente eso, en parry y en parry perfecto (Enemy.OnParried "
          "empuja 0.4 / 0.8; con eso los pies patinan +-20 cm). f15 = LOW_L (sigue el combo)")
_f_hit = mod(READY, hips=(0.0, 0.14, -0.2), spine=(-6.0, 4.0, 2.0), chest=(-8.0, 2.0, 4.0), neck=(-6.0, 0.0, 4.0), head=(-14.0, 0.0, 8.0),
             clav_r=(0.0, 6.0, 0.0), clav_l=(0.0, -6.0, 0.0), grip=(-1.12, 0.32, 1.7), hand_l=(0.9, -0.3, 2.0))
add("Flinch", 15, [(0, READY, "lin"), (3, _f_hit, "out"), (15, READY, "sine")], lag={"head": 1.5},
    timing={"recover": [0, 15], "chain_to": "READY"}, notes="lo usa la interrupción por habilidad (antes del aviso)")
add("Guard", 36, [(0, READY, "sine"), (10, GUARD, "inout"), (23, mod(GUARD, breath=0.7), "sine"), (36, GUARD, "sine")],
    timing={"chain_from": "READY", "hold_last": True},
    notes="seigan a dos manos (el juego deja el último cuadro: es una pose quieta y limpia)")
_c_flick = mod(GUARD, hips=(0.0, 0.0, -0.22), hips_rot=(0.0, 0.0, -18.0), grip=(-0.62, -0.78, 2.7), blade=(-0.78, -0.42, 0.46),
               edge=(-0.5, 0.6, -0.6), chest=(0.0, 0.0, -6.0))
_c_check = mod(GUARD, hips=(0.0, -0.42, -0.34), hips_rot=(0.0, 0.0, 30.0), spine=(16.0, 0.0, 14.0), chest=(6.0, 0.0, 10.0),
               neck=(-6.0, 0.0, -18.0), head=(-8.0, 0.0, -20.0), grip=(-0.75, -0.2, 2.15), blade=(-0.35, -0.5, -0.79),
               edge=(-0.3, 0.8, -0.4))
add("Counter", 15, [(0, GUARD, "lin"), (3, _c_flick, "snap"), (7, _c_check, "expo_out"), (10, mod(_c_check, hips=(0.0, -0.38, -0.36)), "sine"),
                    (15, LOW_L, "inout")],
    timing={"contact": 7, "active": [7, 9], "apex": 2, "recover": [9, 15], "kind": "push", "chain_from": "GUARD", "chain_to": "LOW_L"},
    events=[{"frame": 3, "fn": "Deflect"}, {"frame": 7, "fn": "Strike"}],
    notes="desvía la katana de Kaito y lo empuja con el hombro; termina en LOW_L para seguir con un gyakugiri")
_r_crouch = mod(READY, hips=(0.0, 0.1, -0.42), spine=(28.0, 0.0, 0.0), chest=(12.0, 0.0, 0.0), neck=(10.0, 0.0, 0.0), head=(20.0, 0.0, 0.0),
                clav_r=(0.0, -8.0, 0.0), clav_l=(0.0, 8.0, 0.0), grip=(-0.85, -0.25, 1.45), blade=(-0.2, 0.6, -0.77),
                hand_l=(0.62, -0.62, 1.55))
_r_out = mod(READY, hips=(0.0, 0.04, -0.06), spine=(-14.0, 0.0, 0.0), chest=(-16.0, 0.0, 0.0), neck=(-10.0, 0.0, 0.0), head=(-24.0, 0.0, 0.0),
             clav_r=(0.0, 14.0, 0.0), clav_l=(0.0, -14.0, 0.0), grip=(-1.62, 0.0, 2.85), blade=(-0.8, 0.3, -0.52), edge=(-0.3, 0.2, 0.93),
             hand_l=(1.72, -0.12, 2.85), hand_l_dir=(0.9, -0.1, 0.3), hand_l_up=(0.0, -1.0, 0.0), elbow_r=(-0.5, 0.6, -0.6),
             elbow_l=(0.5, 0.6, -0.6))
_r_tr = [mod(_r_out, head=(-24.0 + d, 0.0, d * 0.4), chest=(-16.0 + d * 0.3, 0.0, 0.0), grip=(-1.62, 0.0, 2.85 + d * 0.006))
         for d in (2.5, -2.0, 2.0, -1.5)]
add("Roar", 39, [(0, READY, "sine"), (9, _r_crouch, "inout"), (14, _r_out, "expo_out"), (18, _r_tr[0], "sine"), (22, _r_tr[1], "sine"),
                 (26, _r_tr[2], "sine"), (30, _r_tr[3], "sine"), (39, READY, "inout")],
    timing={"kind": "none", "chain_to": "READY"}, events=[{"frame": 14, "fn": "Roar"}],
    notes="se encoge y explota abriendo los brazos; tiembla hasta f30")


# =========================================================================== rodilla en el piso (agotado)
# cae sobre la rodilla derecha clavando la nodachi adelante; jadea 3 veces (las grietas laten con la
# respiración: evento Breath) y se levanta. Dura exhaustedTime (3.6 s)
KNEEL_W = feet(mod(KNEEL), l=flat(*L_FOOT))
# cae con la hoja YA en la dirección en que la va a clavar y la punta a 20 cm de la piedra, y la hunde por
# su eje con el golpe de la rodilla (antes la punta entraba y se arrastraba 76 cm bajo el piso)
_kn_drop = along(feet(mod(KNEEL_W, hips=(0.0, 0.12, -0.5), spine=(14.0, 0.0, 0.0), chest=(6.0, 0.0, 0.0), neck=(2.0, 0.0, 0.0),
                          head=(6.0, 0.0, 0.0), hand_l=(0.7, -0.75, 1.6), knee_r=(0.0, -0.6, -0.8)),
                      r=((-0.52, 0.66, 0.58), (30.0, 0.0, -10.0)), l=flat(*L_FOOT)), 0.2, 1.0)
_kn_in = mod(KNEEL_W, breath=1.0, hips=(0.0, 0.17, -0.8), spine=(18.0, 0.0, 2.0), head=(10.0, 0.0, 2.0), clav_r=(0.0, 9.0, 0.0),
             clav_l=(0.0, -7.0, 0.0))
# para levantarse primero arranca la hoja por su eje empujándose en la rodilla (la punta sale de la piedra
# donde entró) y recién afuera la lleva colgando a su derecha hacia la guardia; el tronco sigue inclinado
# mientras tira (si se endereza de golpe la melena salta por encima del casco)
_kn_free = along(mod(KNEEL_W, hips=(0.0, 0.16, -0.68), spine=(18.0, 0.0, 0.0), chest=(7.0, 0.0, 0.0), neck=(3.0, 0.0, 0.0),
                     head=(6.0, 0.0, 0.0)), 0.08, 0.0)
_kn_rise = tip_above(feet(mod(READY, hips=(0.0, 0.1, -0.45), spine=(20.0, 0.0, 0.0), chest=(6.0, 0.0, 0.0),
                              grip=(-1.0, -0.4, 2.2), blade=(-0.35, 0.55, -0.76), edge=(-0.2, -0.75, -0.6), hand_l=(0.62, -0.72, 1.5)),
                          r=((-0.55, 0.64, 0.48), (20.0, 0.0, -20.0)), l=flat(*L_FOOT)), 0.12)
_kn_keys = [(0, READY0, "sine"), (5, _kn_drop, "in2", SWORD_IN), (10, KNEEL_W, "snap")]
for i, f in enumerate((23, 36, 49, 62, 75, 88)):
    _kn_keys.append((f, _kn_in if i % 2 == 0 else KNEEL_W, "sine"))
_kn_keys += [(93, _kn_free, "inout", SWORD_IN), (100, _kn_rise, "inout"), (108, READY0, "out")]
add("Kneel", 108, _kn_keys, lag={"head": 2.0, "neck": 1.0},
    timing={"kneel": [10, 90], "ground": [[6, 91]], "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 10, "fn": "Armor"}] + [{"frame": f, "fn": "Breath"} for f in (23, 49, 75)],
    notes="agotado: clava la nodachi al caer, 3 respiraciones (las grietas del pecho laten); la arranca por su eje en "
          "f88-93 y se levanta hasta f108")
add("KneelRise", 15, [(0, KNEEL_W, "sine"), (4, _kn_free, "inout", SWORD_IN), (10, _kn_rise, "inout"), (15, READY0, "out")],
    timing={"chain_from": "KNEEL", "chain_to": "READY", "ground": [[0, 3]]},
    notes="cuando el agotamiento termina antes (que Guard no salte): arranca la hoja por su eje y se para")

# =========================================================================== arranca su sombra (acto 1 -> 2)
_st_down = feet(mod(READY, hips=(0.0, 0.0, -0.74), hips_rot=(0.0, 0.0, -6.0), spine=(40.0, 0.0, 6.0), chest=(14.0, 0.0, 4.0),
                    neck=(-10.0, 0.0, 0.0), head=(-14.0, 0.0, 0.0), grip=(-1.15, 0.45, 1.25), blade=(-0.3, 0.85, -0.42),
                    hand_l=(0.75, -1.25, 0.4), hand_l_dir=(0.0, -0.5, -0.86), hand_l_up=(0.0, -0.86, 0.5), elbow_l=(0.8, 0.4, 0.2)),
                r=flat(*R_FOOT), l=flat(*L_FOOT))
_st_grab = mod(_st_down, hand_l=(0.75, -1.25, 0.36), spine=(42.0, 0.0, 6.0))
_st_rip = feet(mod(READY, hips=(0.0, 0.18, -0.12), spine=(-16.0, 0.0, -4.0), chest=(-14.0, 0.0, -4.0), neck=(-8.0, 0.0, 0.0),
                   head=(-22.0, 0.0, 0.0), clav_l=(0.0, -16.0, 0.0), grip=(-1.4, 0.4, 2.2), blade=(-0.6, 0.6, -0.53),
                   hand_l=(0.85, -0.35, 4.05), hand_l_dir=(0.1, -0.2, 0.97), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.3, 0.0)),
               r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=10.0))
_st_stagger = feet(mod(READY, hips=(0.0, 0.3, -0.3), spine=(4.0, 0.0, 6.0), chest=(-4.0, 0.0, 6.0), head=(-8.0, 0.0, 8.0),
                       grip=(-1.25, 0.45, 1.8), hand_l=(1.0, -0.2, 2.4)), r=flat(*R_FOOT), l=heel(*L_FOOT, toe_up=14.0))
add("ShadowTear", 54, [(0, READY, "sine"), (10, _st_down, "inout", {"stop": ("hand_l",)}), (16, _st_grab, "sine", {"stop": ("hand_l",)}),
                       (24, _st_rip, "expo_out"),
                       (30, mod(_st_rip, head=(-24.0, 0.0, 2.0), hand_l=(0.88, -0.3, 4.1)), "sine"), (40, _st_stagger, "inout"),
                       (54, READY, "inout")],
    lag={"head": 2.0, "neck": 1.0, "hand_l": -0.5},
    timing={"chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 16, "fn": "ShadowGrab"}, {"frame": 24, "fn": "CrestSnap"}, {"frame": 24, "fn": "ShadowTear"}],
    notes="la mano izquierda agarra la sombra del piso y la arranca hacia arriba (la media luna izquierda salta en f24)")

# =========================================================================== eclipse (acto 2 -> 3)
_ec_plant = feet(mod(READY, hips=(0.0, 0.05, -0.3), spine=(10.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0),
                     grip=(-0.58, -1.0, 2.15), blade=(0.03, -0.12, -0.99), edge=(0.0, -1.0, 0.0), elbow_r=(-0.8, 0.3, -0.3),
                     hand_l=(0.7, -0.6, 1.8), sword_ground=1.0), r=flat(*R_FOOT), l=flat(*L_FOOT))
# levanta la nodachi con la punta abajo YA sobre el punto donde la va a clavar (60 cm arriba) y la hunde
# por su eje: el expo_in hace que la sostenga arriba y la baje de golpe en los últimos cuadros
_ec_lift = along(mod(_ec_plant, hips=(0.0, 0.05, -0.18), spine=(-2.0, 0.0, 0.0), chest=(-6.0, 0.0, 0.0), neck=(-4.0, 0.0, 0.0),
                     head=(-12.0, 0.0, 0.0), elbow_r=(-0.8, 0.3, 0.2), hand_l=(0.86, -0.52, 1.9)), 0.6, 1.0)
_ec_reach = mod(_ec_plant, hips=(0.0, 0.1, -0.24), spine=(-10.0, 0.0, 0.0), chest=(-12.0, 0.0, 2.0), neck=(-10.0, 0.0, 0.0),
                head=(-26.0, 0.0, 4.0), clav_l=(0.0, -16.0, 0.0),
                hand_l=(0.42, 0.2, 4.3), hand_l_dir=(0.0, 0.2, 0.98), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.0, 0.2))
_ec_close = mod(_ec_reach, hand_l=(0.44, 0.15, 4.25), hand_l_dir=(0.05, 0.4, 0.92))
_ec_pull = mod(_ec_plant, hips=(0.0, 0.05, -0.34), spine=(6.0, 0.0, 0.0), chest=(-4.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0),
               hand_l=(0.62, -0.45, 3.2), hand_l_dir=(0.0, -0.3, 0.95), hand_l_up=(0.0, -1.0, 0.0), elbow_l=(0.9, 0.3, -0.2))
# con la luna en el puño arranca la hoja por su eje y la deja volver colgando a la guardia
_ec_out = along(mod(_ec_pull, hips=(0.0, 0.05, -0.26), spine=(4.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0), head=(-4.0, 0.0, 0.0),
                    hand_l=(0.7, -0.5, 2.6)), 0.08, 0.0)
add("Eclipse", 72, [(0, READY0, "sine"), (10, _ec_lift, "inout", SWORD_IN), (20, _ec_plant, "expo_in"), (30, _ec_reach, "inout"),
                    (34, _ec_close, "snap"), (44, _ec_pull, "inout"), (50, _ec_out, "inout", SWORD_IN), (72, READY0, "inout")],
    lag={"head": 2.0, "hand_l": 1.0},
    events=[{"frame": 20, "fn": "SwordPlant"}, {"frame": 30, "fn": "MoonFade"}, {"frame": 34, "fn": "FistClose"}],
    timing={"chain_from": "READY", "chain_to": "READY", "ground": [[20, 48]]},
    notes="clava la nodachi y cierra el puño sobre la luna (las luces empiezan a bajar en f30)")

# =========================================================================== último desfile: "¡Todavía no!"
_ls_slump = feet(mod(KNEEL_W, hips=(0.0, 0.2, -0.86), spine=(30.0, 0.0, 4.0), head=(22.0, 0.0, 0.0)), l=flat(*L_FOOT))
_ls_slump["sword_ground"] = 1.0
# se empuja hacia arriba apoyado en la empuñadura: la hoja no se mueve de donde quedó clavada (antes la
# clave la corría 21 cm y al soltarla en f16 saltaba fuera del piso en un cuadro); la arranca por su eje
# mientras termina de pararse y recién afuera la levanta rugiendo
_ls_push = feet(mod(READY, hips=(0.0, 0.1, -0.45), spine=(24.0, 0.0, 0.0), chest=(8.0, 0.0, 0.0), head=(4.0, 0.0, 0.0),
                    grip=KNEEL["grip"], blade=KNEEL["blade"], edge=KNEEL["edge"], elbow_r=KNEEL["elbow_r"], sword_ground=1.0,
                    hand_l=(0.6, -0.75, 1.55)),
                r=toe(-0.45, 0.62, -6.0, 40.0), l=flat(*L_FOOT))
_ls_free = along(mod(_ls_push, hips=(0.0, 0.08, -0.3), spine=(12.0, 0.0, 0.0), chest=(2.0, 0.0, 0.0), head=(-4.0, 0.0, 0.0),
                     hand_l=(0.8, -0.5, 1.9)), 0.08, 0.0)
_ls_roar = feet(mod(_r_out, hips=(0.0, 0.06, -0.2)), r=flat(*R_FOOT), l=flat(*L_FOOT))
add("LastStand", 45, [(0, _ls_slump, "lin"), (8, mod(_ls_slump, hips=(0.0, 0.22, -0.9), head=(26.0, 0.0, 0.0)), "sine"),
                      (15, _ls_push, "inout"), (19, _ls_free, "inout", SWORD_IN), (23, _ls_roar, "expo_out"),
                      (27, _r_tr[0], "sine"), (31, _r_tr[1], "sine"), (45, READY0, "inout")],
    lag={"head": 2.0},
    timing={"chain_to": "READY", "ground": [[0, 18]]}, events=[{"frame": 23, "fn": "Roar"}],
    notes="al 10 %: se apoya en la espada para pararse, la arranca de la piedra, ruge y arranca el último desfile")

# =========================================================================== derrota, máscara que cae, seiza
# la nodachi queda clavada donde la soltó y la máscara rueda hasta el piso: ambas viven en el clip (así
# no dependen de reparentar en runtime) y siguen ahí en DefeatLoop y SeizaBow
FALLEN = {}
# se sienta donde quedó arrodillado: el seiza del final va 36 cm más adelante que el de la espera, así los
# dedos metidos (kiza) caen justo donde estaba apoyada la punta del pie derecho de la rodilla en el piso
SEIZA_DY = -0.36
SEIZA_D = shifted(mod(SEIZA, head=(18.0, 0.0, 0.0), neck=(6.0, 0.0, 0.0), spine=(8.0, 0.0, 0.0),
                      hand_l=(0.58, -0.5, 1.2), hand_l_dir=(-0.1, -0.95, -0.3), hand_l_up=(0.0, 0.3, 1.0),
                      sword_free=1.0, hand_r=(-0.58, -0.5, 1.2), hand_r_dir=(0.1, -0.95, -0.3), hand_r_up=(0.0, 0.3, 1.0),
                      elbow_r=(-0.7, 0.5, -0.3)), SEIZA_DY)
_kiza_d = feet(mod(SEIZA_D, hips=(0.0, 0.12 + SEIZA_DY, -0.86), spine=(14.0, 0.0, 0.0), head=(16.0, 0.0, 0.0),
                   hand_l=(0.6, -0.62 + SEIZA_DY, 1.32), hand_r=(-0.6, -0.62 + SEIZA_DY, 1.32)),
               r=toe(-0.48, 0.62, -3.0, 74.0), l=toe(0.42, 0.62, 3.0, 74.0))


def _prepare_defeat(clip, rig, solve=None):
    """Ancla en el mundo la espada (cuando la suelta, f20) y la máscara (cuando se cortan los cordones, f40).
    La mano derecha arranca su recorrido libre exactamente desde la empuñadura."""
    for k in clip.keys:
        k.ctrl["sword_free"] = 0.0
        k.ctrl["mask_free"] = 0.0
    W = solved(clip, 20)
    K = W["Katana"]
    FALLEN["sword"] = (tuple(K.translation), tuple(rot3(K).col[1]), tuple(rot3(K).col[2]))
    H = W["Hand_R"]
    hand20 = (tuple(H @ SOLVER.grip_in_hand_r_local()), tuple(rot3(H).col[1]), tuple(rot3(H).col[2]))
    W = solved(clip, 40)
    M = W["Mask"]
    r0 = rot3(rig.rest["Mask"])
    eul = (rot3(M) @ r0.transposed()).to_euler('XYZ')
    m0 = (tuple(M.translation), tuple(math.degrees(a) for a in eul))
    # rueda hacia adelante y a su izquierda, lejos de donde después apoya las manos en la reverencia
    floor = Vector((0.62, -2.08, 0.07))
    FALLEN["mask"] = (tuple(floor), (-88.0, 0.0, 160.0))
    path = {40: m0, 44: ((m0[0][0] + 0.05, m0[0][1] - 0.35, m0[0][2] - 0.55), (m0[1][0] - 40.0, m0[1][1], m0[1][2] + 20.0)),
            48: ((0.4, -1.6, 0.34), (-110.0, 0.0, 70.0)), 50: ((0.46, -1.74, 0.13), (-95.0, 0.0, 95.0)),
            53: ((0.52, -1.87, 0.24), (-80.0, 0.0, 120.0)), 56: ((0.57, -1.98, 0.11), (-92.0, 0.0, 140.0)),
            62: (FALLEN["mask"][0], FALLEN["mask"][1])}
    for k in clip.keys:
        if k.frame >= 20:
            k.ctrl["sword_free"] = 1.0
            k.ctrl["sword_pos"], k.ctrl["sword_dir"], k.ctrl["sword_up"] = FALLEN["sword"]
        if k.frame == 20:
            k.ctrl["hand_r"], k.ctrl["hand_r_dir"], k.ctrl["hand_r_up"] = hand20
            k.ease_ch["sword_free"] = "hold"
        if k.frame == 40:
            k.ease_ch["mask_free"] = "hold"
        if k.frame >= 40:
            k.ctrl["mask_free"] = 1.0
            p = path.get(k.frame)
            if p is None:
                p = FALLEN["mask"]
            k.ctrl["mask_pos"], k.ctrl["mask_rot"] = p


def _with_fallen(p):
    q = mod(p)
    q["sword_free"] = 1.0
    q["sword_pos"], q["sword_dir"], q["sword_up"] = FALLEN["sword"]
    q["mask_free"] = 1.0
    q["mask_pos"], q["mask_rot"] = FALLEN["mask"]
    return q


def _prepare_fallen(clip, rig, solve=None):
    if not FALLEN:
        _prepare_defeat(DEFEAT, rig)
    for k in clip.keys:
        k.ctrl.update(_with_fallen(k.ctrl))


_df_bow = mod(KNEEL_W, head=(22.0, 0.0, 0.0), spine=(26.0, 0.0, 2.0))
_df_let = mod(_df_bow, hand_r=(-0.7, -0.75, 1.75), hand_r_dir=(0.0, -0.6, -0.8), hand_r_up=(0.0, -0.8, 0.6))
_df_rest = mod(_df_bow, hand_r=(-0.55, -0.55, 1.35), hand_r_dir=(0.0, -0.9, -0.4), hand_r_up=(0.0, 0.0, 1.0),
               hand_l=(0.55, -0.62, 1.32))
_df_snap = mod(_df_rest, head=(-12.0, 0.0, 0.0), neck=(-6.0, 0.0, 0.0))
_df_low = mod(_df_rest, head=(24.0, 0.0, 0.0), neck=(8.0, 0.0, 0.0))
# se sienta: la rodilla izquierda baja (el pie se va atrás levantado), los dos quedan con los dedos metidos
# y recién ahí estira los pies y se sienta sobre los talones (nada se arrastra por el piso)
_df_lift = feet(mod(_df_low, hips=(0.0, 0.08, -0.86), spine=(18.0, 0.0, 2.0)), l=((0.46, -0.3, 0.66), (40.0, 0.0, 6.0)))
_df_keys = [(0, KNEEL_W, "sine"), (10, _df_bow, "sine"), (20, _df_bow, "sine"),
            (26, _df_let, "inout"), (34, _df_rest, "inout"), (40, _df_rest, "sine"), (42, _df_snap, "snap"),
            (44, mod(_df_snap), "sine"), (48, mod(_df_low, head=(10.0, 0.0, 0.0)), "sine"), (50, mod(_df_low, head=(14.0, 0.0, 0.0)), "sine"),
            (53, mod(_df_low, head=(18.0, 0.0, 0.0)), "sine"), (56, _df_low, "sine"), (62, mod(_df_low), "sine"),
            (68, _df_lift, "inout"), (75, _kiza_d, "inout"),
            (84, mod(SEIZA_D, hips=(0.0, 0.18 + SEIZA_DY, -0.86)), "inout", {"foot_r": "in2", "foot_l": "in2"}), (90, SEIZA_D, "sine")]
DEFEAT = add("Defeat", 90, _df_keys, lag={"head": 2.0, "neck": 1.0},
             timing={"release": 20, "mask_snap": 40, "ground": [[0, 90]], "chain_from": "KNEEL", "chain_to": "SEIZA_D"},
             events=[{"frame": 20, "fn": "SwordRelease"}, {"frame": 40, "fn": "MaskSnap"}, {"frame": 50, "fn": "MaskHit"},
                     {"frame": 56, "fn": "MaskHit"}],
             notes="suelta la espada (queda clavada), se cortan los cordones de la máscara (cae y rueda) y se sienta en seiza")
DEFEAT.prepare = _prepare_defeat
_dl = add("DefeatLoop", 60, [(0, SEIZA_D, "sine"), (30, mod(SEIZA_D, breath=1.0, head=(16.0, 0.0, 0.0)), "sine"), (60, SEIZA_D, "sine")],
          loop=True, lag={"head": 3.0}, timing={"chain_from": "SEIZA_D", "ground": [[0, 60]]}, notes="seiza respirando, sin máscara")
_dl.prepare = _prepare_fallen
_bow = mod(SEIZA_D, spine=(42.0, 0.0, 0.0), chest=(10.0, 0.0, 0.0), neck=(6.0, 0.0, 0.0), head=(18.0, 0.0, 0.0),
           hand_l=(0.4, -1.25 + SEIZA_DY, 0.3), hand_l_dir=(-0.2, -0.95, 0.0), hand_l_up=(0.0, 0.0, 1.0),
           hand_r=(-0.4, -1.25 + SEIZA_DY, 0.3), hand_r_dir=(0.2, -0.95, 0.0), hand_r_up=(0.0, 0.0, 1.0))
_sb = add("SeizaBow", 60, [(0, SEIZA_D, "sine"), (16, _bow, "inout"), (36, mod(_bow, spine=(44.0, 0.0, 0.0)), "sine"), (60, SEIZA_D, "inout")],
          lag={"head": 3.0, "hand_l": 1.0}, timing={"chain_from": "SEIZA_D", "chain_to": "SEIZA_D", "ground": [[0, 60]]},
          notes="la reverencia del final (Kaito le devuelve su media cinta)")
_sb.prepare = _prepare_fallen

# =========================================================================== seiza de espera e intro
add("SeizaIdle", 90, [(0, SEIZA, "sine"), (45, mod(SEIZA, breath=1.0, head=(6.0, 0.0, 0.0)), "sine"), (90, SEIZA, "sine")],
    loop=True, lag={"head": 3.0}, notes="espera arrodillado al pie de la escalera, la espada sobre los muslos")
# se para como un samurái: mete los dedos (kiza), adelanta el pie izquierdo levantándolo (rodilla derecha
# en el piso), se empuja en la rodilla izquierda y el pie derecho da el paso a la guardia
_in_look = mod(SEIZA, head=(-4.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0))
_in_kiza = mod(KIZA, head=(-6.0, 0.0, 0.0), neck=(-2.0, 0.0, 0.0), grip=(-0.62, -0.58, 1.36), hand_l=(0.62, -0.62, 1.34))
_in_swing = feet(mod(_in_kiza, hips=(0.0, 0.1, -0.84), spine=(14.0, 0.0, 0.0), hand_l=(0.66, -0.7, 1.4),
                     knee_l=(0.25, -1.0, 0.4)), l=((0.48, -0.08, 0.72), (12.0, 0.0, 10.0)))
_in_knee = feet(mod(SEIZA, hips=(0.0, 0.12, -0.8), spine=(16.0, 0.0, 0.0), head=(-2.0, 0.0, 0.0),
                    hand_l=(0.6, -0.86, 1.3), hand_l_dir=(0.0, -0.6, -0.8), hand_l_up=(0.0, -0.8, 0.6),
                    grip=(-0.68, -0.7, 1.4), blade=(0.6, -0.6, -0.53), edge=(0.0, -0.7, 0.7), knee_l=(0.25, -1.0, 0.0)),
                r=(KIZA_FEET["foot_r"], KIZA_FEET["foot_r_rot"]), l=flat(*L_FOOT))
_in_push = feet(mod(_in_knee, hips=(0.0, 0.04, -0.5), spine=(22.0, 0.0, 2.0), chest=(6.0, 0.0, 0.0), hand_l=(0.62, -0.8, 1.55)),
                r=toe(-0.38, 0.98, 0.0, 56.0), l=flat(*L_FOOT))
_in_stand = feet(mod(READY, hips=(0.0, 0.05, -0.3), spine=(14.0, 0.0, 2.0), grip=(-1.05, -0.4, 1.7), blade=(0.1, -0.85, -0.52),
                     edge=(0.0, -0.5, 0.86), hand_l=(0.62, -0.75, 1.6)),
                 r=((-0.56, 0.7, 0.52), (14.0, 0.0, -20.0)), l=flat(*L_FOOT))
_in_draw = mod(READY, hips=(0.0, 0.05, -0.12), spine=(-4.0, 0.0, 0.0), chest=(-6.0, 0.0, 0.0), head=(-8.0, 0.0, 0.0),
               clav_r=(0.0, 12.0, 0.0), grip=(-0.6, -0.05, 4.1), blade=(0.35, 0.93, 0.08), edge=(0.0, -0.08, 1.0),
               elbow_r=(-0.9, 0.2, 0.3), hand_l=(0.9, -0.5, 2.2))
_in_flick = mod(READY, hips=(0.0, 0.02, -0.24), grip=(-1.25, -0.45, 2.1), blade=(-0.55, -0.55, -0.63), edge=(-0.6, 0.6, -0.1))
add("Intro", 96, [(0, SEIZA, "sine"), (24, SEIZA, "sine"), (30, _in_look, "inout"),
                  (38, _in_kiza, "inout", {"foot_r": "out2", "foot_l": "out2"}), (43, _in_swing, "inout"), (49, _in_knee, "inout"),
                  (57, _in_push, "inout"), (64, _in_stand, "inout"), (69, feet(mod(_in_stand, hips=(0.0, 0.05, -0.26)), r=flat(*R_FOOT)), "in2"),
                  (75, _in_draw, "inout"), (79, _in_flick, "snap"), (85, mod(READY, grip=(-1.22, 0.3, 1.55)), "sine"), (96, READY, "sine")],
    lag={"head": 2.0, "neck": 1.0},
    timing={"chain_from": "SEIZA", "chain_to": "READY"},
    events=[{"frame": 24, "fn": "HeadRise"}, {"frame": 49, "fn": "Step"}, {"frame": 69, "fn": "Step"},
            {"frame": 79, "fn": "Chiburi"}, {"frame": 81, "fn": "EyesIgnite"}],
    notes="seiza -> levanta la cabeza -> mete los dedos -> adelanta el pie izquierdo -> se empuja en la rodilla y da el "
          "paso -> alza la nodachi -> chiburi -> guardia")

# =========================================================================== tsukuyomi (anillos)
_ty_plant = feet(mod(READY, hips=(0.0, 0.1, -0.3), spine=(12.0, 0.0, 0.0), chest=(4.0, 0.0, 0.0),
                     grip=(-0.12, -1.05, 2.3), blade=(0.02, -0.05, -0.998), edge=(0.0, -1.0, 0.0), grip_l=1.0,
                     elbow_r=(-0.8, 0.0, -0.3), elbow_l=(0.8, 0.0, -0.3), sword_ground=1.0), r=flat(*R_FOOT), l=flat(*L_FOOT))
# alza la nodachi a dos manos con la punta abajo sobre el punto donde la clava y la baja por su eje; los tres
# golpes la suben y la hunden por la misma recta; al final la arranca por su eje antes de volver a la guardia
# (antes giraba desde la guardia con la punta bajo el piso: el piso la cortaba mientras entraba)
_ty_hover = along(_ty_plant, 0.25, 1.0, hips=(0.0, 0.12, -0.2), spine=(4.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0), head=(-8.0, 0.0, 0.0))
_ty_up = along(_ty_plant, -0.3, 1.0, hips=(0.0, 0.12, -0.12), spine=(2.0, 0.0, 0.0), head=(-10.0, 0.0, 0.0))
_ty_slam = along(_ty_plant, -0.62, 1.0, hips=(0.0, 0.05, -0.5), spine=(24.0, 0.0, 0.0), chest=(10.0, 0.0, 0.0))
_ty_rebound = along(_ty_plant, -0.58, 1.0, hips=(0.0, 0.05, -0.46), spine=(24.0, 0.0, 0.0), chest=(10.0, 0.0, 0.0))
_ty_free = along(_ty_plant, 0.08, 0.0, hips=(0.0, 0.1, -0.24), spine=(6.0, 0.0, 0.0), chest=(0.0, 0.0, 0.0), head=(-6.0, 0.0, 0.0))
_ty = [(0, READY0, "sine"), (10, _ty_hover, "inout", SWORD_IN), (14, _ty_plant, "in2")]
for f in (30, 45, 60):
    _ty += [(f - 6, _ty_up, "inout"), (f, _ty_slam, "expo_in"), (f + 3, _ty_rebound, "out")]
_ty += [(67, _ty_free, "inout", SWORD_IN), (75, READY0, "inout")]
add("Tsukuyomi", 75, _ty, timing={"rings": [30, 45, 60], "ground": [[12, 66]], "chain_from": "READY", "chain_to": "READY"},
    events=[{"frame": 14, "fn": "SwordPlant"}] + [{"frame": f, "fn": "RingSlam"} for f in (30, 45, 60)],
    notes="clava la espada al frente (f14) y la hunde tres veces: un anillo por golpe; la arranca en f63-67")


# =========================================================================== locomoción (ciclos procedurales)
# Los pies siguen una trayectoria por fase: en el apoyo se deslizan hacia atrás EXACTAMENTE a la
# velocidad del juego (sin patinar) y en el vuelo hacen un arco. La cadera sube y baja dos veces por
# ciclo (más baja al recibir el peso), gira con la pierna que avanza y el pecho contrarresta.
def _smooth(u):
    return u * u * (3.0 - 2.0 * u)


def gait(name, frames, speed, direction, stance, lift, bob, lean, yaw_amp, sway, sword="trail", notes=""):
    """direction: (x, y) en el que avanza el personaje (frente = (0, -1)); speed en m/s."""
    T = frames / NA.FPS
    d = Vector((direction[0], direction[1], 0.0)).normalized()
    span = speed * stance * T                   # lo que recorre el pie apoyado (en el espacio del personaje)
    side = abs(d.x) > 0.5
    base_r = Vector((-0.62, 0.15 if not side else 0.05, 0.24))
    base_l = Vector((0.52, -0.15 if not side else -0.05, 0.24))
    yaw_r, yaw_l = (-30.0, 14.0) if not side else (-12.0, 8.0)

    def foot(u, base, yaw):
        """u: fase del pie (0 = apoya plano adelante)."""
        heel_max = 18.0
        if u < stance:
            w = u / stance
            p = base + d * (span * (0.5 - w))
            if w > 0.75:                          # despega el talón al final del apoyo (gira sobre la punta)
                return toe(p.x, p.y, yaw, (w - 0.75) / 0.25 * heel_max)
            return (p.x, p.y, 0.24), (0.0, 0.0, yaw)
        # vuelo: de la punta del despegue al apoyo plano siguiente, en arco
        w = (u - stance) / (1.0 - stance)
        s = _smooth(w)
        p0 = base + d * (-0.5 * span)
        a0, _ = toe(p0.x, p0.y, yaw, heel_max)
        p1 = base + d * (0.5 * span)
        a = Vector(a0).lerp(Vector((p1.x, p1.y, 0.24)), s) + Vector((0.0, 0.0, lift * math.sin(math.pi * w)))
        pitch = heel_max * (1.0 - s) - 12.0 * math.sin(math.pi * w)   # adelanta la punta levantada
        return tuple(a), (pitch, 0.0, yaw)

    def fn(f):
        t = f / frames
        ur, ul = t % 1.0, (t + 0.5) % 1.0
        fr, rr = foot(ur, base_r, yaw_r)
        fl, rl = foot(ul, base_l, yaw_l)
        c2 = math.cos(4.0 * math.pi * (t - 0.08))            # dos bajadas por ciclo, justo después de apoyar
        yw = yaw_amp * math.sin(2.0 * math.pi * (t + 0.25))
        sw = sway * math.sin(2.0 * math.pi * t)
        lean_v = Vector((d.x, d.y, 0.0)) * 0.05
        p = mod(READY, hips=(sw * (0 if side else 1) + lean_v.x, 0.05 + lean_v.y, -0.2 - bob * (0.5 + 0.5 * c2)),
                hips_rot=(lean * (0.3 if not side else 0.0), sw * 10.0 * (0 if side else 1), -16.0 + yw),
                spine=(6.0 + lean * 0.5, 0.0, 6.0 - yw * 0.6), chest=(4.0 + lean * 0.3, 0.0, 7.0 - yw * 0.7),
                neck=(-4.0 - lean * 0.4, 0.0, 1.0 + yw * 0.5), head=(-7.0 - lean * 0.4, 0.0, 3.0 + yw * 0.3))
        # la nodachi cuelga atrás y rebota con el paso; al acechar la punta casi raspa el piso
        g = Vector(READY["grip"]) + Vector((0.0, 0.0, -bob * 0.4 * c2))
        bl = Vector(READY["blade"])
        if sword == "drag":
            bl = Vector((-0.3, 0.8, -0.58)).normalized()
        p["grip"] = tuple(g)
        p["blade"] = tuple((bl + Vector((0.0, 0.0, 0.03 * c2))).normalized())
        swing = math.sin(2.0 * math.pi * (t + 0.5))           # el brazo libre va contra la pierna izquierda
        p["hand_l"] = (0.86, -0.52 + 0.25 * swing * (0 if side else 1), 1.72 + 0.05 * abs(swing))
        p["foot_r"], p["foot_r_rot"] = fr, rr
        p["foot_l"], p["foot_l_rot"] = fl, rl
        return p
    c = NA.ProcClip(name, frames, fn, loop=True, root_vel=(d.x * speed, d.y * speed, 0.0),
                    timing={"ground_speed_mps": speed, "stance": stance, "contacts": [0, frames // 2]},
                    events=[{"frame": 0, "fn": "Step"}, {"frame": frames // 2, "fn": "Step"}], notes=notes,
                    sheet_frames=[round(frames * k / 8) for k in range(9)])
    CLIPS.append(c)
    return c


gait("Walk", 36, 1.8, (0.0, -1.0), stance=0.62, lift=0.28, bob=0.05, lean=3.0, yaw_amp=6.0, sway=0.04,
     notes="camina a 1.8 m/s (walkSpeed): pasos de 1.08 m, cadera +-5 cm")
gait("Stalk", 30, 3.0, (0.0, -1.0), stance=0.46, lift=0.42, bob=0.08, lean=8.0, yaw_amp=9.0, sway=0.05, sword="drag",
     notes="acecha a 3.0 m/s (runSpeed): pasos de 1.5 m, la punta casi raspa el piso")
gait("StrafeL", 36, 1.8, (1.0, 0.0), stance=0.6, lift=0.24, bob=0.04, lean=2.0, yaw_amp=3.0, sway=0.0,
     notes="rodea hacia su izquierda a 1.8 m/s sin cruzar los pies (suriashi de costado)")
gait("StrafeR", 36, 1.8, (-1.0, 0.0), stance=0.6, lift=0.24, bob=0.04, lean=2.0, yaw_amp=3.0, sway=0.0,
     notes="rodea hacia su derecha a 1.8 m/s")
