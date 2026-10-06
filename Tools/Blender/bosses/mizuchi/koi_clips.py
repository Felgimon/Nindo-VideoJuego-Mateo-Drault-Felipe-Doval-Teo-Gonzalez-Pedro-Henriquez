"""Los 21 clips del Gran Koi (30 fps). Ver koi_rig.py para los canales semánticos y koi_anim.py para el motor.

Gramática de lectura desde la cámara alta (la del diseño, 'el agua no miente'):
  * cada golpe desviable arranca con un cambio de silueta grande visto desde arriba (C de la mordida,
    rolido del aletazo, C cerrada del coletazo, el koi que se para para escupir) y una pausa VIVA en el
    apex; la suelta dura 2-4 cuadros y el contacto cae en un cuadro exacto (timing en el sidecar);
  * después del contacto la ola baja por la cola (lag por hueso) y las aletas siguen por resorte.
Signos: bend + = la punta del hueso va a la izquierda del koi (+X). C = mismo signo adelante y atrás.
"""
import math
from koi_anim import Clip


def merge(*ds):
    out = {}
    for d in ds:
        for b, ch in d.items():
            out.setdefault(b, {}).update(ch)
    return out


def both(prefix, **ch):
    """Canal simétrico en los dos lados: both('pec_{}1', up=10) -> pec_L1 y pec_R1."""
    return {prefix.format(s): dict(ch) for s in ("L", "R")}


def side(prefix, s, **ch):
    return {prefix.format(s): dict(ch)}


def chain(front=(0, 0), back=(0, 0, 0, 0, 0), ch="bend"):
    """front = (spine_f, head); back = (b1, b2, b3, b4, tail)."""
    names = ["spine_f", "head", "spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail"]
    vals = list(front) + list(back)
    return {n: {ch: v} for n, v in zip(names, vals) if v}


def body(**ch):
    return {"body": ch}


BACK = ["spine_b1", "spine_b2", "spine_b3", "spine_b4", "tail"]
FRONT = ["spine_f", "head"]
SPINE = FRONT + BACK
FINS1 = ["pec_L1", "pec_R1"]
LAG_TAIL = {"spine_b1": 1, "spine_b2": 2, "spine_b3": 3, "spine_b4": 3, "tail": 4}

# ------------------------------------------------------------------ poses base
H = merge(both("pec_{}1", out=4, fwd=4), both("fluke_{}1", out=4), both("barbel_{}1", fwd=4), both("whisker_{}1", up=3))
SWIM = merge(body(pitch=-4), both("pec_{}1", fwd=-30, up=-4, fold=-0.1), both("fluke_{}1", out=10),
             both("pel_{}", fwd=-12), {"dorsal_1": {"rake": 6}, "dorsal_2": {"rake": 6}})


# ------------------------------------------------------------------ extras procedurales
def hover_extra(cycles=1, row=18.0, bob=0.10, pitch=2.0):
    def fx(f, t, vals, T=None):
        T2 = 60 / 30.0
        w = 2 * math.pi * cycles * t / T2
        vals.setdefault("body", {})
        vals["body"]["tz"] = vals["body"].get("tz", 0) + bob * math.sin(w)
        vals["body"]["pitch"] = vals["body"].get("pitch", 0) + pitch * math.sin(w - 1.2)
        # remo de las pectorales: izquierda y derecha alternadas con 0.5 s de desfase
        for s, ph in (("L", 0.0), ("R", math.pi / 2)):
            d = vals.setdefault(f"pec_{s}1", {})
            d["fwd"] = d.get("fwd", 0) + row * math.sin(w + ph)
            d["up"] = d.get("up", 0) + 6 * math.sin(w + ph + 1.0)
            d2 = vals.setdefault(f"pec_{s}2", {})
            d2["up"] = d2.get("up", 0) + 5 * math.sin(w + ph - 0.8)
        # las branquias respiran una vez por ciclo (abren rápido, cierran lento)
        g = max(0.0, math.sin(w + 0.4)) ** 2 * 12
        for s in ("L", "R"):
            vals.setdefault(f"gill_{s}", {})["out"] = g
        for i, n in enumerate(("dorsal_1", "dorsal_2", "dorsal_3", "dorsal_4")):
            vals.setdefault(n, {})["lean"] = 6 * math.sin(w - 0.7 * i)
    return fx


def swim_extra(f, t, vals):
    w = 2 * math.pi * t / 1.0
    vals.setdefault("body", {})
    vals["body"]["tz"] = vals["body"].get("tz", 0) + 0.05 * math.sin(2 * w)
    for s, ph in (("L", 0.0), ("R", math.pi)):
        d = vals.setdefault(f"pec_{s}1", {})
        d["up"] = d.get("up", 0) + 6 * math.sin(2 * w + ph)
    for i, n in enumerate(("dorsal_1", "dorsal_2", "dorsal_3", "dorsal_4")):
        vals.setdefault(n, {})["lean"] = 8 * math.sin(w - 0.9 * (i + 1))


def add(vals, bone, ch, v):
    d = vals.setdefault(bone, {})
    d[ch] = d.get(ch, 0.0) + v


# ------------------------------------------------------------------ clips
def clips():
    C = []

    # 1. Hover: flota en el lugar. Onda lenta, remo de pectorales, respiración. Idle del jefe.
    C.append(Clip("Hover", 60, [(0, H, "lin")], loop=True, wave=dict(amp=1.0, cycles=1),
                  extra=hover_extra(), noise=[(["barbel_L1", "barbel_R1", "whisker_L1", "whisker_R1"], "up", 4, 0.5, None),
                                              (["whisker_L2", "whisker_R2"], "out", 5, 0.5, None)]))

    # 2. Swim: un coletazo por segundo a 5 m/s; aletas recogidas, nariz apenas abajo.
    C.append(Clip("Swim", 30, [(0, SWIM, "lin")], loop=True, wave=dict(amp=1.8, cycles=1), extra=swim_extra))

    # 3. Bite: C (se aleja y carga) -> pausa viva -> S (la cabeza vuelve como un látigo) -> la ola baja.
    settle = merge(H, body(tz=-0.12, ty=0.08), both("gill_{}", out=15), both("pec_{}1", fwd=10))
    coil = merge(H, body(tz=-0.06, ty=0.3, turn=-6), chain((26, 22), (14, 18, 22, 24, 20)), {"head": {"bend": 22, "lift": 12}},
                 both("pec_{}1", fwd=40, out=10, up=6), both("gill_{}", out=18), {"jaw": {"open": 6}},
                 {"dorsal_1": {"rake": -10}, "dorsal_2": {"rake": -8}})
    coil2 = merge(coil, chain((26.7, 22.7), (15, 19, 23, 25, 21)), body(tz=-0.05, ty=0.31, turn=-6, sx=0.02, sz=0.02))
    strike = merge(body(ty=-0.6, tz=0.02, turn=3), chain((-8, -6), (-6, -8, -10, -12, -10)), {"head": {"bend": -6, "lift": -6}},
                   {"jaw": {"open": 30, "fwd": 0.28}}, both("pec_{}1", fwd=-35, up=6, fold=-0.15), both("gill_{}", out=4))
    gulp = merge(body(ty=-0.45), chain((-3, -2), (-6, -8, -10, -12, -10)), {"jaw": {"open": -5, "fwd": 0.12}},
                 both("pec_{}1", fwd=-10))
    C.append(Clip("Bite", 33, [(0, H, "lin"), (7, settle, "ease"), (13, coil, "ease"), (16, coil2, "hold"),
                               (19, strike, "strike"), (25, gulp, "ease"), (27, merge(gulp, {"jaw": {"open": 1, "fwd": 0.06}}), "ease"),
                               (33, H, "settle")],
                  lag=LAG_TAIL, wave=dict(amp=0.5, cycles=1, env=[(0, 1), (6, 0.15), (26, 0.15), (33, 1)]),
                  noise=[(SPINE, "bend", 0.9, 0.7, [(12, 0), (13, 1), (16, 1), (17, 0)])],
                  timing=dict(tell=7, hold=(13, 16), apex=15, contact=19, activeEnd=23, strikeBone="jaw", kind="parry")))

    # 4. FinL: rola a la derecha, el ala izquierda sube plegada como una hoja y barre 150° por delante.
    raise_l = merge(H, body(roll=35, tz=0.1, turn=8), side("pec_{}1", "L", up=66, fwd=-20), side("pec_{}2", "L", fold=-0.25, up=10),
                    side("pec_{}3", "L", fold=-0.25), {"head": {"bend": 10}}, side("pec_{}1", "R", up=30, fwd=10),
                    chain((4, 0), (6, 8, 10, 10, 8)))
    raise_l2 = merge(raise_l, body(roll=36, tz=0.11, turn=8.5), side("pec_{}1", "L", up=67, fwd=-21))
    sweep_l = merge(body(roll=-16, tz=0.15, turn=-12, ty=-0.2), side("pec_{}1", "L", up=14, fwd=110), side("pec_{}2", "L", fold=0.2),
                    side("pec_{}3", "L", fold=0.2), {"head": {"bend": -6}}, chain((-6, 0), (-8, -10, -12, -12, -10)),
                    side("pec_{}1", "R", up=10, fwd=-15))
    over_l = merge(sweep_l, body(roll=-18, turn=-20, ty=-0.25, tz=0.18), side("pec_{}1", "L", up=22, fwd=125))
    cock_r = merge(H, body(roll=-15, turn=-6), side("pec_{}1", "R", up=22, fwd=-10), side("pec_{}2", "R", fold=-0.15),
                   side("pec_{}1", "L", fwd=10, up=14))
    # la vuelta pliega el ala y la pasa por DEBAJO del cuerpo en un solo arco parejo (acelera hasta la pose
    # plegada y frena en la pose armada, sin pararse en el medio): volver por delante de la cara, o con un
    # arranque brusco, barría otra vez el frente justo después de la ventana de parry y se leía como un
    # segundo golpe. Pico de la vuelta ~40 % del barrido (koi_lint: máx 45 %)
    tuck_l = merge(over_l, body(roll=-17, turn=-14, ty=-0.18, tz=0.14), side("pec_{}1", "L", up=-2, fwd=68),
                   side("pec_{}2", "L", fold=-0.3), side("pec_{}3", "L", fold=-0.3))
    C.append(Clip("FinL", 27, [(0, H, "lin"), (7, raise_l, "ease"), (11, raise_l2, "hold"), (15, sweep_l, "strike"),
                               (18, over_l, "out"), (22, tuck_l, "acc"), (27, cock_r, "out")],
                  lag={"spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 3}, wave=dict(amp=0.4, cycles=1, env=[(0, 1), (6, 0.2), (22, 0.2), (27, 0.6)]),
                  noise=[(["body"], "roll", 1.2, 0.8, [(7, 0), (8, 1), (11, 1), (12, 0)])],
                  timing=dict(tell=3, hold=(7, 11), apex=11, contact=15, activeEnd=18, strikeBone="pec_L3", kind="parry")))

    # 5. FinR: espejo desde la pose armada del final de FinL, sin pausa ('taa... ta').
    raise_r = merge(H, body(roll=-34, tz=0.1, turn=-8), side("pec_{}1", "R", up=64, fwd=-20), side("pec_{}2", "R", fold=-0.25, up=10),
                    side("pec_{}3", "R", fold=-0.25), {"head": {"bend": -10}}, side("pec_{}1", "L", up=30, fwd=10),
                    chain((-4, 0), (-6, -8, -10, -10, -8)))
    sweep_r = merge(body(roll=16, tz=0.15, turn=12, ty=-0.2), side("pec_{}1", "R", up=14, fwd=110), side("pec_{}2", "R", fold=0.2),
                    side("pec_{}3", "R", fold=0.2), {"head": {"bend": 6}}, chain((6, 0), (8, 10, 12, 12, 10)),
                    side("pec_{}1", "L", up=10, fwd=-15))
    over_r = merge(sweep_r, body(roll=18, turn=20, ty=-0.25, tz=0.18), side("pec_{}1", "R", up=22, fwd=125))
    tuck_r = merge(over_r, body(roll=12, turn=14, ty=-0.18, tz=0.14), side("pec_{}1", "R", up=-2, fwd=68),
                   side("pec_{}2", "R", fold=-0.3), side("pec_{}3", "R", fold=-0.3))
    C.append(Clip("FinR", 24, [(0, cock_r, "lin"), (6, raise_r, "ease"), (10, sweep_r, "strike"), (13, over_r, "out"), (18, tuck_r, "acc"),
                               (24, H, "out")],
                  lag={"spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 3}, wave=dict(amp=0.4, cycles=1, env=[(0, 0.6), (5, 0.2), (19, 0.2), (24, 1)]),
                  timing=dict(tell=0, hold=None, apex=6, contact=10, activeEnd=13, strikeBone="pec_R3", kind="parry")))

    # 6. TailWhip: se levanta y se enrosca mirando hacia atrás por encima del hombro; el abanico gotea en la
    #    pausa; giro completo de 360° (45-60°/cuadro) con la cola arrastrada: barre un disco entero.
    coil_t = merge(H, body(tz=0.5, turn=10, pitch=4), chain((30, 26), (28, 32, 34, 35, 30)), {"head": {"lift": 8}},
                   both("fluke_{}1", out=18, up=25, fold=0.3), both("fluke_{}2", out=8), both("pec_{}1", up=20, out=15, fwd=10),
                   {"dorsal_1": {"rake": -12}, "dorsal_2": {"rake": -12}, "dorsal_3": {"rake": -10}})
    coil_t2 = merge(coil_t, body(tz=0.52, turn=11, pitch=5), chain((31.5, 27), (29, 33.5, 35.5, 36.5, 31)))
    # el giro va hacia la izquierda (turn +): la C cargada a la izquierda queda ATRÁS del giro y la cola
    # arrastrada barre el disco; al frenar, la cola se pasa en el sentido del giro (over_t) y rebota (wob_t).
    # Girando a la derecha la cola enroscada iba adelante y el latigazo salía al revés, después del frenazo
    whip_end = merge(body(tz=0.32, turn=360), chain((-6, -4), (-4, -6, -8, -10, -10)), both("fluke_{}1", out=14, fold=0.2),
                     both("pec_{}1", up=8, out=12, fwd=-20))
    # el pasarse y el rebote son chicos (~45° y ~20° del abanico): más grandes eran un segundo latigazo
    over_t = merge(body(tz=0.25, turn=376), chain((-7, -4), (-6, -8, -9, -10, -8)), both("pec_{}1", up=4, fwd=-10))
    wob_t = merge(body(tz=0.14, turn=357), chain((3, 1), (3, 4, 4, 4, 3)))
    end_t = merge(H, body(turn=360))
    C.append(Clip("TailWhip", 42, [(0, H, "lin"), (12, coil_t, "ease"), (20, coil_t2, "hold"), (29, whip_end, "hold"),
                                   (32, over_t, "out"), (37, wob_t, "ease"), (42, end_t, "settle")],
                  lag={"spine_b1": 1, "spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 2},
                  wave=dict(amp=0.3, cycles=1, env=[(0, 1), (8, 0), (36, 0), (42, 0.8)]),
                  noise=[(["fluke_L1", "fluke_R1"], "up", 3, 2.2, [(12, 0), (13, 1), (20, 1), (21, 0)]),
                         (SPINE, "bend", 0.9, 0.7, [(12, 0), (13, 1), (20, 1), (21, 0)])],
                  extra=tailwhip_extra,
                  timing=dict(tell=4, hold=(12, 20), apex=19, contact=23, activeEnd=30, strikeBone="fluke_L2", kind="parry")))

    # 7. Spit: se para, infla las branquias, aspira (se hincha), cabezazo y sale la perla; retroceso.
    rear = merge(H, body(pitch=30, tz=0.3, ty=0.15), chain((0, -6), (8, 9, 9, 8, 6), ch="lift"), both("gill_{}", out=25),
                 {"jaw": {"open": 10}}, both("pec_{}1", up=18, out=12, fwd=15))
    inhale = merge(rear, body(pitch=32, tz=0.3, ty=0.18, sx=0.06, sy=0.04, sz=0.06), {"jaw": {"open": 16}}, both("gill_{}", out=30))
    inhale2 = merge(inhale, body(pitch=33.2, tz=0.31, ty=0.19, sx=0.066, sy=0.045, sz=0.066), {"jaw": {"open": 17}})
    spit = merge(body(pitch=10, tz=0.12, ty=0.0), chain((0, -15), ch="lift"), {"jaw": {"open": 35, "fwd": 0.12}},
                 both("gill_{}", out=6), both("pec_{}1", up=12, fwd=2))
    recoil = merge(body(pitch=14, tz=0.15, ty=0.3), chain((0, -6), ch="lift"), {"jaw": {"open": 18}}, both("pec_{}1", fwd=15, up=10))
    C.append(Clip("Spit", 36, [(0, H, "lin"), (10, rear, "ease"), (16, inhale, "ease"), (18, inhale2, "hold"),
                               (20, spit, "strike"), (26, recoil, "out"), (36, H, "settle")],
                  wave=dict(amp=0.5, cycles=1, env=[(0, 1), (8, 0.3), (28, 0.3), (36, 1)]),
                  noise=[(["body"], "pitch", 0.6, 0.8, [(15, 0), (16, 1), (18, 1), (19, 0)])],
                  timing=dict(tell=4, hold=(16, 18), apex=16, contact=20, activeEnd=21, strikeBone="jaw", kind="parry", release=20)))

    # 8. Return (Tama-asobi): mini C y hocicazo que devuelve la perla en el cuadro 5.
    mini = merge(H, chain((10, 15), (3, 4, 4, 3, 0)), body(ty=0.1))
    bat = merge(body(ty=-0.4), chain((-4, -5), (-2, -3, -3, -3, -2)), {"jaw": {"open": -3}}, both("pec_{}1", fwd=-10))
    # la mini C se arma en 3 cuadros con ease: con 'out' desde el reposo el primer cuadro era más rápido que
    # el hocicazo; el golpe tiene que ser el cuadro más rápido del clip
    C.append(Clip("Return", 12, [(0, H, "lin"), (3, mini, "ease"), (5, bat, "strike"), (12, H, "settle")], lag={"spine_b2": 1, "spine_b3": 1, "spine_b4": 2, "tail": 2},
                  timing=dict(tell=0, hold=None, apex=3, contact=5, activeEnd=6, strikeBone="jaw", kind="parry", event=5)))

    # 9. Jet: se para casi vertical, la cola se recoge abajo, aspira, apunta y dispara con temblor y retroceso.
    # de pie como una cobra: la cola queda plana detrás (en L) en vez de clavarse en la cubierta
    rear_j = merge(H, body(pitch=62, tz=1.25, ty=0.4), chain((0, -8), (13, 14, 14, 12, 10), ch="lift"),
                   both("pec_{}1", out=22, up=16, fwd=10), both("fluke_{}1", out=14))
    swell = merge(rear_j, body(pitch=65, tz=1.32, ty=0.42, sx=0.08, sy=0.05, sz=0.08), {"jaw": {"open": 8}}, both("gill_{}", out=20))
    swell2 = merge(swell, body(pitch=66, tz=1.33, ty=0.43, sx=0.085, sy=0.055, sz=0.085), {"jaw": {"open": 10}})
    aim = merge(swell, body(pitch=15, tz=0.7, ty=0.2, sx=0.08, sy=0.05, sz=0.08), chain((0, -10), ch="lift"), {"jaw": {"open": 30}})
    fire = merge(aim, body(pitch=14, tz=0.65, ty=0.7, sx=0.04, sy=0.02, sz=0.04), {"jaw": {"open": 40, "fwd": 0.1}}, both("gill_{}", out=28),
                 both("pec_{}1", out=26, up=10, fwd=-10))
    fire2 = merge(fire, body(pitch=13, tz=0.62, ty=0.72, sx=0.0, sy=0.0, sz=0.0))
    C.append(Clip("Jet", 66, [(0, H, "lin"), (18, rear_j, "ease"), (26, swell, "ease"), (32, swell2, "hold"), (36, aim, "ease"), (41, fire, "ease"),
                              (50, fire2, "lin"), (66, H, "ease")],
                  lag={"spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 3}, wave=dict(amp=0.6, cycles=2, env=[(0, 1), (16, 0.4), (52, 0.4), (66, 1)]),
                  noise=[(["body"], "pitch", 2.0, 15.0, [(36, 0), (37, 1), (50, 1), (52, 0)]),
                         (["body"], "turn", 2.0, 13.0, [(36, 0), (37, 1), (50, 1), (52, 0)])],
                  timing=dict(tell=6, hold=(26, 32), apex=32, contact=36, activeEnd=50, strikeBone="jaw", kind="danger")))

    # 10. Dive: gira hacia la baranda, se enrosca, salta 0.5 m y entra de cabeza (el código lo oculta en f22).
    turn_d = merge(H, body(turn=40, tz=-0.1), chain((18, 12), (14, 16, 18, 16, 12)), both("pec_{}1", up=15, out=10))
    spring_d = merge(body(turn=45, tz=0.5, pitch=-45), chain((2, 0), (-4, -6, -8, -8, -6)), chain((0, 0), (10, 10, 12, 12, 10), ch="lift"),
                     both("pec_{}1", fwd=-45, up=-5, fold=-0.3), both("pec_{}2", fold=-0.3))
    plunge = merge(body(turn=45, tz=-1.6, pitch=-80), chain((0, 0), (6, 8, 10, 10, 8), ch="lift"), both("pec_{}1", fwd=-60, fold=-0.45),
                   both("pec_{}2", fold=-0.4), both("fluke_{}1", out=-6))
    C.append(Clip("Dive", 24, [(0, H, "lin"), (8, turn_d, "ease"), (14, spring_d, "out"), (24, plunge, "in")],
                  lag={"spine_b2": 1, "spine_b3": 1, "spine_b4": 2, "tail": 2},
                  timing=dict(tell=0, hold=None, apex=8, contact=None, hide=22, kind="danger")))

    # 11. BreachAir (escalado al tiempo de vuelo real por código): sale de punta, arco de la 'Puerta del
    #     Dragón' con las pectorales como alas, y cae de cabeza con la boca abierta.
    erupt = merge(body(pitch=60, roll=0), chain((0, 2), (-6, -8, -8, -6, -4), ch="lift"), both("pec_{}1", up=50, out=15, fwd=-15),
                  both("fluke_{}1", out=10), {"jaw": {"open": 8}})
    arch = merge(body(pitch=5, roll=30), chain((-8, -6), (-10, -10, -10, -8, -6), ch="lift"), both("pec_{}1", up=45, out=22, fwd=5),
                 both("fluke_{}1", out=18, up=8), {"dorsal_1": {"rake": -12}})
    fall = merge(body(pitch=-50, roll=10), chain((0, 0), (6, 8, 8, 6, 4), ch="lift"), both("pec_{}1", up=25, out=10, fwd=-25),
                 {"jaw": {"open": 25}})
    C.append(Clip("BreachAir", 33, [(0, erupt, "lin"), (6, merge(erupt, body(pitch=55, roll=6)), "out"), (14, arch, "ease"),
                                    (20, merge(arch, body(pitch=-5, roll=30)), "hold"), (33, fall, "in")],
                  lag={"spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 3}, wave=dict(amp=0.8, cycles=1),
                  timing=dict(tell=0, hold=None, apex=14, contact=None, kind="danger")))

    # 12. BreachLand: aplasta, rebota, cae de costado y aletea tres veces jadeando; se endereza y se sacude.
    squash = merge(body(sx=0.18, sz=-0.18, sy=0.04, tz=-0.35, pitch=-6), both("pec_{}1", up=30, out=20), {"jaw": {"open": 20}})
    stretch = merge(body(sx=-0.05, sz=0.08, sy=-0.03, tz=-0.2, pitch=2), both("pec_{}1", up=10))
    side_ = merge(body(roll=80, tz=-0.6, pitch=0), side("pec_{}1", "R", fwd=-85, up=20, out=-40, fold=-0.4), side("shide_{}", "R", out=-60), side("pec_{}1", "L", up=-24, fwd=-10),
                  side("pel_{}", "R", up=40), side("fluke_{}1", "R", up=34), side("fluke_{}1", "L", up=-10), {"jaw": {"open": 18}}, side("gill_{}", "L", out=24),
                  side("whisker_{}1", "R", up=40), side("whisker_{}2", "R", up=20), side("barbel_{}1", "R", up=35),
                  chain((0, 0), (6, 8, 10, 10, 8)))
    upright = merge(H, body(tz=0.05))
    # a mitad de enderezarse la aleta de abajo ya se despegó de la cubierta
    rolling = merge(body(roll=38, tz=-0.3), side("shide_{}", "R", out=-30), side("pec_{}1", "R", up=30, fwd=-40, out=-20, fold=-0.2), side("pec_{}1", "L", up=-6),
                    side("whisker_{}1", "R", up=20), side("barbel_{}1", "R", up=15))
    C.append(Clip("BreachLand", 54, [(0, squash, "lin"), (3, stretch, "out"), (12, side_, "ease"), (40, side_, "lin"),
                                     (45, rolling, "ease"), (49, upright, "ease"), (54, H, "settle")],
                  extra=breachland_extra,
                  timing=dict(tell=None, hold=None, contact=0, kind="danger", beached=(12, 40))))

    # 13. GreatWave: se para en la baranda norte con el abanico en alto y lo estrella contra el agua.
    # el abanico sube por detrás como un escorpión (se lee desde arriba y de perfil) y baja de golpe
    rear_w = merge(H, body(pitch=58, tz=1.0, ty=0.2), chain((0, -6), (16, 20, 24, 24, 20), ch="lift"),
                   both("fluke_{}1", out=20, up=20, fold=0.3), both("pec_{}1", up=30, out=20))
    rear_w2 = merge(rear_w, body(pitch=60, tz=0.95, ty=0.22))
    slam = merge(body(pitch=8, tz=-0.2, ty=-0.2), chain((0, -4), (-8, -10, -10, -8, -6), ch="lift"), both("fluke_{}1", out=14, up=-10),
                 both("pec_{}1", up=-6, out=26), {"jaw": {"open": 12}})
    low = merge(body(pitch=2, tz=-0.42, ty=-0.1), chain((0, 0), (-6, -8, -8, -6, -4), ch="lift"), both("pec_{}1", out=24, up=4))
    # el body baja en f15 y la cola llega 2 cuadros después (lag): el abanico pega en el agua en f17, el
    # cuadro del diseño (activeStart 0.354)
    C.append(Clip("GreatWave", 48, [(0, H, "lin"), (10, rear_w, "ease"), (12, rear_w2, "hold"), (15, slam, "strike"),
                                    (23, low, "out"), (48, merge(low, body(tz=-0.38)), "hold")],
                  lag={"spine_b1": 1, "spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 2},
                  noise=[(["body"], "turn", 1.5, 1.0, [(17, 0), (23, 1), (48, 1)])],
                  timing=dict(tell=2, hold=(10, 12), apex=12, contact=17, activeEnd=19, kind="danger", strikeBone="fluke_L2")))

    # 14. Roar: echa la cabeza atrás, abre todo (boca, branquias, aletas, dorsal, bigotes) y tiembla.
    rear_r = merge(H, body(pitch=25, tz=0.2, ty=0.3), chain((0, 8), (5, 5, 5, 4, 3), ch="lift"), both("pec_{}1", up=10, out=10))
    roar = merge(body(pitch=18, tz=0.25, ty=0.15), chain((4, 10), (4, 4, 4, 3, 2), ch="lift"), {"jaw": {"open": 45, "fwd": 0.14}}, both("gill_{}", out=30),
                 both("barbel_{}1", out=25, up=12), both("barbel_{}2", out=12),
                 # bigotes: la raíz apenas se levanta y el tramo que corre por el flanco se abre (la raíz sale
                 # hacia adelante: abrirla a ella metía la parte de atrás del bigote contra el cuerpo)
                 both("whisker_{}1", out=-4, up=6), both("whisker_{}2", out=12, up=5), both("whisker_{}3", up=6),
                 both("pec_{}1", up=22, out=18, fwd=8),
                 both("pec_{}2", fold=0.2, up=6), both("pec_{}3", fold=0.2), both("fluke_{}1", out=20, fold=0.3),
                 {"dorsal_1": {"rake": -16, "grow": 0.1}, "dorsal_2": {"rake": -14, "grow": 0.1}, "dorsal_3": {"rake": -12}, "dorsal_4": {"rake": -10}})
    C.append(Clip("Roar", 48, [(0, H, "lin"), (10, rear_r, "ease"), (14, roar, "out"), (34, merge(roar, body(pitch=17)), "hold"),
                               (48, H, "ease")],
                  noise=[(["body"], "turn", 3.0, 12.0, [(13, 0), (15, 1), (32, 1), (36, 0)]),
                         (["body"], "roll", 2.5, 11.0, [(13, 0), (15, 1), (32, 1), (36, 0)]),
                         (SPINE, "bend", 1.5, 9.0, [(13, 0), (15, 1), (32, 1), (36, 0)])],
                  timing=dict(tell=0, hold=None, loopRange=(14, 30), kind=None)))

    # 15. Intro: sale del pozo de la cascada girando 180°, planea con las pectorales como alas, cae al
    #     hover con rebote, encara a Kaito y ruge corto.
    out_i = merge(body(pitch=70, roll=0, tz=-2.6), both("pec_{}1", up=-10, fwd=-50, fold=-0.4), chain((0, 0), (6, 8, 8, 6, 4), ch="lift"))
    top_i = merge(body(pitch=20, roll=180, tz=2.4), both("pec_{}1", up=50, out=20, fwd=-5), chain((-6, -4), (-8, -8, -8, -6, -4), ch="lift"))
    glide = merge(body(pitch=-15, roll=360, tz=1.6), both("pec_{}1", up=42, out=24), chain((0, 0), (4, 4, 4, 4, 2), ch="lift"))
    land = merge(H, body(roll=360, tz=-0.25, sx=0.06, sz=-0.06), both("pec_{}1", up=28, out=18))
    flare = merge(H, body(roll=360, pitch=14, ty=0.15), both("pec_{}1", up=24, out=20, fwd=6), {"jaw": {"open": 36, "fwd": 0.1}},
                  both("gill_{}", out=24), both("barbel_{}1", out=20), both("whisker_{}1", up=8),
                  both("whisker_{}2", out=10, up=4),
                  {"dorsal_1": {"rake": -14}, "dorsal_2": {"rake": -12}})
    C.append(Clip("Intro", 90, [(0, out_i, "lin"), (20, top_i, "out"), (50, glide, "ease"), (58, land, "in"), (64, merge(H, body(roll=360, tz=0.06)), "settle"),
                                (76, flare, "out"), (84, merge(flare, body(roll=360, pitch=12)), "hold"), (90, merge(H, body(roll=360)), "ease")],
                  wave=dict(amp=1.0, cycles=3), lag={"spine_b2": 1, "spine_b3": 2, "spine_b4": 2, "tail": 3},
                  noise=[(["body"], "turn", 2.5, 12.0, [(75, 0), (77, 1), (84, 1), (86, 0)])],
                  timing=dict(tell=None, hold=None, roar=76, land=58, kind=None)))

    # 16. Hit: sacudón lejos del golpe, aletas que se abren, vuelve con BACK.
    jolt = merge(H, body(turn=-12, roll=8, ty=0.12), chain((-6, -4), (4, 6, 6, 4, 2)), both("pec_{}1", up=15, out=12), both("gill_{}", out=12))
    C.append(Clip("Hit", 14, [(0, H, "lin"), (2, jolt, "out"), (14, H, "settle")], lag={"spine_b3": 1, "spine_b4": 1, "tail": 2},
                  timing=dict(kind=None)))

    # 17. Parried: cabeza volteada atrás y arriba, se desliza 0.6 m, mandíbula que castañetea, mareo que se apaga.
    knock = merge(body(ty=0.6, tz=0.08, pitch=10), chain((0, 15), ch="lift"), {"head": {"lift": 15, "bend": 15}, "jaw": {"open": -3}},
                  both("pec_{}1", up=20, out=20, fwd=-10), both("barbel_{}1", up=18), both("whisker_{}1", up=14))
    C.append(Clip("Parried", 21, [(0, H, "lin"), (3, knock, "out"), (12, merge(knock, body(ty=0.55, tz=0.04, pitch=6), {"head": {"lift": 6, "bend": 6}}), "ease"),
                                  (21, H, "ease")],
                  extra=parried_extra, timing=dict(kind=None)))

    # 18. Guard: muestra el flanco blindado (giro 70°, rolido hacia Kaito), aletas pegadas, cola enroscada.
    guard = merge(body(turn=70, roll=20, tz=0.05), chain((6, 4), (12, 16, 18, 18, 14)), both("pec_{}1", up=8, fwd=-35, fold=-0.25),
                  side("pec_{}1", "R", up=30, fwd=-35, fold=-0.25), side("whisker_{}1", "R", up=16),
                  both("fluke_{}1", fold=-0.2), {"dorsal_1": {"rake": 10}, "dorsal_2": {"rake": 10}})
    C.append(Clip("Guard", 36, [(0, H, "lin"), (10, guard, "out"), (36, merge(guard, body(turn=69, roll=19)), "hold")],
                  noise=[(["body"], "roll", 1.0, 0.8, [(10, 0), (14, 1)])],
                  timing=dict(kind=None, holdsLast=True)))

    # 19. Exhausted (varado): de costado sobre la cubierta, aletea cada 0.8 s cada vez más débil, jadea.
    beached = merge(body(roll=85, tz=-0.6), side("pec_{}1", "R", fwd=-85, up=20, out=-40, fold=-0.4), side("shide_{}", "R", out=-60), side("pec_{}1", "L", up=-26, fwd=-10),
                    side("pel_{}", "R", up=40), side("fluke_{}1", "R", up=36), side("fluke_{}1", "L", up=-10),
                    side("whisker_{}1", "R", up=40), side("whisker_{}2", "R", up=20), side("barbel_{}1", "R", up=35),
                    {"jaw": {"open": 14}}, chain((0, 0), (4, 6, 8, 8, 6)))
    C.append(Clip("Exhausted", 72, [(0, beached, "lin")], loop=True, extra=exhausted_extra,
                  timing=dict(kind=None, punish=True)))

    # 20. Freed: arco rígido, la estaca sale disparada girando y desaparece, se relaja, nado vertical.
    arch_f = merge(body(pitch=12, tz=0.15), chain((14, 8), (12, 14, 14, 12, 8), ch="lift"), both("pec_{}1", up=35, out=25, fold=0.2),
                   both("fluke_{}1", out=22, fold=0.3), {"jaw": {"open": 30}}, both("gill_{}", out=26))
    # la estaca sale dando vueltas de campana (el medallón va boca arriba: girando solo sobre su eje se veía
    # como una moneda quieta) mientras se achica hasta desaparecer
    eject = merge(arch_f, {"seal": {"tz": 1.5, "spin": 720, "scale": -0.999, "tilt": 300}})
    relax = merge(H, body(tz=0.9, pitch=6), {"seal": {"tz": 1.5, "spin": 720, "scale": -0.999, "tilt": 300}})
    # se para para subir: el cuerpo se eleva (ascensión) para que la cola no atraviese la cubierta; el root
    # (y el anillo Ripple) se quedan en la cubierta
    vert = merge(body(tz=4.6, pitch=80), {"seal": {"tz": 1.5, "spin": 720, "scale": -0.999, "tilt": 300}},
                 both("pec_{}1", fwd=-25, up=8), both("fluke_{}1", out=12))
    C.append(Clip("Freed", 120, [(0, H, "lin"), (16, arch_f, "out"), (20, merge(arch_f, body(pitch=13)), "hold"),
                                 (40, eject, "out"), (70, relax, "ease"), (100, vert, "ease"), (120, merge(vert, body(tz=4.7)), "lin")],
                  wave=dict(amp=1.2, cycles=4, env=[(0, 0.4), (20, 0), (40, 0), (70, 1), (120, 1.6)]),
                  noise=[(SPINE, "bend", 1.5, 6.0, [(14, 0), (17, 1), (38, 1), (42, 0)])],
                  timing=dict(kind=None, eject=(20, 40), swap=55)))

    # 21. ClimbFalls (solo cinemática): casi vertical, onda fuerte de 0.6 s, pectorales que empujan.
    climb = merge(body(pitch=80, tz=0.3), both("pec_{}1", fwd=-20, out=8), both("fluke_{}1", out=12), {"dorsal_1": {"rake": 8}})
    C.append(Clip("ClimbFalls", 36, [(0, climb, "lin")], loop=True, wave=dict(amp=2.3, cycles=2), extra=climb_extra,
                  timing=dict(kind=None)))
    return C


# ------------------------------------------------------------------ extras por clip
def tailwhip_extra(f, t, vals):
    # durante el giro la cola se arrastra hacia afuera de la curva (lo contrario a la velocidad de giro)
    if 20 <= f <= 32:
        u = (f - 20) / 12.0
        trail = math.sin(math.pi * u) * 16.0
        for i, b in enumerate(BACK):
            add(vals, b, "bend", trail * (0.6 + 0.15 * i))
        for s in ("L", "R"):
            add(vals, f"fluke_{s}1", "out", trail * 0.5)


def breachland_extra(f, t, vals):
    # tres coletazos de pez fuera del agua (0.3 s cada uno, 30° -> 22° -> 15°): de costado, la 'flexión
    # lateral' se ve como un golpe contra la cubierta. Branquias y boca jadean.
    if 12 <= f <= 40:
        u = (f - 12) / 28.0
        amp = 30 * (1 - 0.5 * u)
        ph = 2 * math.pi * 3 * u
        env = min(1.0, u * 4.0, (1.0 - u) * 4.0)     # entra y se apaga: sin corte al terminar los coletazos
        for i, b in enumerate(SPINE):
            # de costado (rolido +80) la flexión + es hacia arriba: los extremos solo se levantan de la
            # cubierta y vuelven a golpearla, alternando cabeza y cola
            ph_b = ph + (0.0 if b in FRONT else math.pi) - 0.35 * i
            add(vals, b, "bend", amp * env * max(0.0, math.sin(ph_b)) * (0.5 if b in FRONT else 0.22 + 0.1 * i))
        g = 18 * max(0.0, math.sin(2 * math.pi * 2.0 * (f / 30.0)))
        add(vals, "gill_L", "out", g)          # la de abajo queda apretada contra la cubierta
        add(vals, "jaw", "open", 10 * max(0.0, math.sin(2 * math.pi * 1.6 * f / 30.0)))
    if 49 <= f <= 54:
        add(vals, "body", "turn", 5 * math.sin((f - 49) * 2.4) * (54 - f) / 5.0)


def parried_extra(f, t, vals):
    if 3 <= f <= 14:
        u = (f - 3) / 11.0
        a = (1 - u) ** 1.5
        add(vals, "body", "roll", 7 * a * math.sin(2 * math.pi * 3 * u))
        add(vals, "body", "turn", 5 * a * math.sin(2 * math.pi * 3 * u + 1.2))
    if 3 <= f <= 6:
        add(vals, "jaw", "open", 12 * math.sin(math.pi * (f - 3) / 3.0))


def exhausted_extra(f, t, vals):
    T = 72 / 30.0
    w = 2 * math.pi * t / T
    # tres coletazos por vuelta (cada 0.8 s), cada uno más débil: 1.0, 0.6, 0.35
    k = int(f // 24)
    u = (f % 24) / 24.0
    amp = (1.0, 0.6, 0.35)[min(k, 2)] * 22
    pulse = math.sin(math.pi * u) ** 2
    for i, b in enumerate(SPINE):
        lift = max(0.0, math.sin(math.pi * min(1.0, u * 1.25 + (0.0 if b in FRONT else 0.12))))
        add(vals, b, "bend", amp * pulse * lift * (0.5 if b in FRONT else 0.22 + 0.1 * i))
    add(vals, "gill_L", "out", 10 + 12 * max(0.0, math.sin(2 * math.pi * 5 * t / T)))   # ~2 Hz, 5 jadeos por vuelta
    add(vals, "jaw", "open", 6 * math.sin(w * 3))
    add(vals, "body", "tz", 0.03 * math.sin(w * 3 + 0.5) * amp / 22)


def climb_extra(f, t, vals):
    w = 2 * math.pi * t / 0.6
    for s, ph in (("L", 0.0), ("R", math.pi)):
        add(vals, f"pec_{s}1", "fwd", 14 * math.sin(w + ph))
        add(vals, f"pec_{s}1", "up", 6 * math.sin(w + ph + 1.0))
