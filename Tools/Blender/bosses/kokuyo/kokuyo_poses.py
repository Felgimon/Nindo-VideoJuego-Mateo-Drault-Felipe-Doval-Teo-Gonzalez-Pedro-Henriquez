"""Poses clave de Kokuyō como datos legibles (controles de kokuyo_rig.Solver).

Posiciones en metros. Cadera y manos van relativas al transform del personaje (el juego lo mueve
en las embestidas); pies, espada clavada y máscara caída van en el MUNDO del clip (antes de restar
el avance del golpe), así un pie apoyado tiene la misma coordenada en todas las claves. Direcciones
como vectores; giros en grados (x + = adelante, y + = hacia su izquierda, z + = gira a su izquierda).
Frente = -Y, su derecha = -X. Las piernas: tobillo (x, y, z) y giro del pie (cabeceo, rolido, giro);
un pie apoyado plano tiene z = 0.24 y cabeceo 0.

Las poses de "encadenado" (READY, LOW_L, THRUST_END, KNEEL, SEIZA) son las que comparten el final
de un clip y el principio del siguiente: así un combo nunca salta de pose en el crossfade.
"""
import copy, math
from mathutils import Vector, Matrix
import kokuyo_rig as KR

# lo que se autora en el MUNDO (clavado en el piso); el resto va relativo al transform del juego
WORLD_POS = ("foot_r", "foot_l", "sword_pos", "mask_pos")


def mod(base, **kw):
    """Copia de una pose con cambios; 'extra' se combina hueso por hueso."""
    p = copy.deepcopy(base)
    ex = kw.pop("extra", None)
    p.update(kw)
    if ex:
        e = dict(p.get("extra", {}))
        e.update(ex)
        p["extra"] = e
    return p


def at_travel(p, travel):
    """La misma pose (en el espacio del personaje) cuando ya avanzó 'travel' metros en el golpe:
    solo se corre lo que está clavado en el mundo."""
    q = copy.deepcopy(p)
    for k in WORLD_POS:
        if k in q and q[k] is not None:
            x, y, z = q[k]
            q[k] = (x, y - travel, z)
    q["travel"] = travel
    return q


def flat(x, y, yaw=0.0):
    """Pie apoyado plano en (x, y) con la punta girada 'yaw' grados (+ = hacia su izquierda)."""
    return (x, y, 0.24), (0.0, 0.0, yaw)


def toe(x, y, yaw=0.0, heel=25.0):
    """Pie en punta con la MISMA huella que flat(x, y, yaw): el borde de la punta de la suela queda donde
    estaba y el talón sube 'heel' grados (el pie gira sobre ese borde: no patina ni se mete en el piso)."""
    R = Matrix.Rotation(math.radians(yaw), 3, 'Z')
    ty, tz = -KR.SOLE_TOE_Y, KR.ANKLE_Z
    tip = Vector((x, y, 0.24)) - R @ Vector((0.0, ty, tz))
    h = math.radians(heel)
    ank = tip + R @ Vector((0.0, ty * math.cos(h) - tz * math.sin(h), ty * math.sin(h) + tz * math.cos(h)))
    return tuple(ank), (heel, 0.0, yaw)


def shifted(p, dy):
    """La misma pose corrida 'dy' metros hacia atrás (+Y): cuerpo, manos y pies (una postura en el piso
    que tiene que coincidir con dónde quedaron apoyados los pies en la clave anterior)."""
    q = copy.deepcopy(p)
    for k in ("hips", "grip", "hand_l", "hand_r", "foot_r", "foot_l"):
        if q.get(k) is not None:
            x, y, z = q[k]
            q[k] = (x, y + dy, z)
    return q


def feet(p, r=None, l=None):
    if r:
        p["foot_r"], p["foot_r_rot"] = r
    if l:
        p["foot_l"], p["foot_l_rot"] = l
    return p


def heel(x, y, yaw=0.0, toe_up=20.0):
    """Pie apoyado en el talón con la punta levantada (se echa atrás), misma huella que flat()."""
    R = Matrix.Rotation(math.radians(yaw), 3, 'Z')
    hy, hz = KR.SOLE_HEEL_Y, KR.ANKLE_Z
    hp = Vector((x, y, 0.24)) + R @ Vector((0.0, hy, -hz))       # borde del talón
    h = math.radians(toe_up)
    ank = hp + R @ Vector((0.0, -hy * math.cos(h) + hz * math.sin(h), hy * math.sin(h) + hz * math.cos(h)))
    return tuple(ank), (-toe_up, 0.0, yaw)


# --------------------------------------------------------------------------- guardia (wakigamae)
# las poses de encadenado comparten la huella de los pies: pasar de una a otra nunca los hace patinar
R_FOOT = (-0.62, 0.62, -30.0)
L_FOOT = (0.52, -0.58, 14.0)
# el pie izquierdo adelante, la nodachi colgando atrás a la derecha con la punta a un palmo del piso
READY = feet({
    "hips": (0.0, 0.05, -0.16), "hips_rot": (0.0, 0.0, -16.0),
    "spine": (6.0, 0.0, 6.0), "chest": (4.0, 0.0, 7.0), "neck": (-4.0, 0.0, 1.0), "head": (-7.0, 0.0, 3.0),
    "clav_r": (0.0, -3.0, 0.0), "clav_l": (0.0, 3.0, 0.0),
    "grip": (-1.22, 0.38, 1.5), "blade": (-0.34, 0.82, -0.46), "edge": (-0.3, 0.1, -0.95), "elbow_r": (-0.7, 0.4, -0.2),
    "hand_l": (0.86, -0.52, 1.72), "hand_l_dir": (0.15, -0.55, -0.8), "hand_l_up": (0.3, -0.8, 0.4), "elbow_l": (0.6, 0.5, -0.1),
    "grip_l": 0.0, "knee_r": (-0.35, -1.0, 0.0), "knee_l": (0.25, -1.0, 0.0),
    "travel": 0.0, "lift": 0.0, "breath": 0.0, "extra": {},
}, r=flat(*R_FOOT), l=flat(*L_FOOT))

# final del kesagiri / principio del gyakugiri: la hoja quedó abajo a su izquierda, a dos manos
LOW_L = feet(mod(READY, hips=(0.05, -0.08, -0.36), hips_rot=(0.0, 0.0, 16.0), spine=(18.0, 0.0, 8.0), chest=(6.0, 0.0, 4.0),
                 neck=(-10.0, 0.0, -6.0), head=(-12.0, 0.0, -8.0),
                 grip=(0.4, -0.85, 1.62), blade=(0.62, -0.5, -0.6), edge=(0.5, -0.1, -0.85), elbow_r=(-0.4, 0.2, -0.9),
                 grip_l=1.0, elbow_l=(0.7, 0.4, -0.5)),
             r=flat(*R_FOOT), l=flat(*L_FOOT))

# guardia seigan: a dos manos, la punta a los ojos del rival (filo claro: "no ataques")
GUARD = feet(mod(READY, hips=(0.0, 0.05, -0.2), hips_rot=(0.0, 0.0, -8.0), spine=(8.0, 0.0, 2.0), chest=(2.0, 0.0, 4.0),
                 neck=(-2.0, 0.0, 1.0), head=(-6.0, 0.0, 1.0),
                 grip=(-0.28, -0.88, 2.42), blade=(0.08, -0.82, 0.57), edge=(0.0, -0.57, -0.82), elbow_r=(-0.8, 0.3, -0.5),
                 grip_l=1.0, elbow_l=(0.8, 0.3, -0.5)),
             r=flat(*R_FOOT), l=flat(*L_FOOT))

# final de la estocada: estirado y bajo, la hoja al frente apuntando 17° abajo (la punta llega a la altura
# del pecho de Kaito, ~1.1 m), el brazo libre atrás de contrapeso
THRUST_END = feet(mod(READY, hips=(0.0, -0.34, -0.62), hips_rot=(0.0, 0.0, 26.0), spine=(18.0, 0.0, 10.0), chest=(6.0, 0.0, 8.0),
                      neck=(-10.0, 0.0, -14.0), head=(-12.0, 0.0, -18.0), clav_r=(0.0, 0.0, 10.0),
                      grip=(-0.3, -1.7, 1.95), blade=(0.04, -0.953, -0.3), edge=(0.0, -0.3, -0.953), elbow_r=(-0.6, 0.4, -0.6),
                      hand_l=(1.1, 0.75, 2.0), hand_l_dir=(0.4, 0.8, -0.4), hand_l_up=(0.0, 0.3, 1.0), elbow_l=(0.4, 0.9, -0.3)),
                  r=toe(*R_FOOT, heel=20.0), l=flat(0.52, -1.08, 14.0))

# rodilla en el piso (agotado / derrota): rodilla derecha abajo, la nodachi clavada adelante
KNEEL = feet(mod(READY, hips=(0.0, 0.18, -0.82), hips_rot=(0.0, 0.0, -6.0), spine=(22.0, 0.0, 2.0), chest=(10.0, 0.0, 2.0),
                 neck=(6.0, 0.0, 0.0), head=(14.0, 0.0, 2.0), clav_r=(0.0, 6.0, 0.0), clav_l=(0.0, -4.0, 0.0),
                 grip=(-0.62, -1.05, 1.95), blade=(0.04, -0.12, -0.99), edge=(0.0, -1.0, 0.0), elbow_r=(-0.8, 0.4, -0.3),
                 hand_l=(0.58, -0.82, 1.32), hand_l_dir=(0.0, -0.5, -0.86), hand_l_up=(0.0, -0.86, 0.5), elbow_l=(0.8, 0.3, 0.0),
                 knee_r=(0.0, -0.55, -0.83), sword_ground=1.0),
             r=toe(-0.45, 0.62, -6.0, 62.0), l=flat(0.52, -0.82, 8.0))

# seiza: sentado sobre los talones, la espada cruzada sobre los muslos (espera e intro). Las grebas son
# gruesas: las tibias apoyan sobre las placas (tobillo a 24 cm del piso) y el pie estirado toca el piso
# con la punta, como un empeine que no llega a aplanarse
SEIZA_FEET = {"foot_r": (-0.38, 0.38, 0.24), "foot_r_rot": (147.0, 0.0, 0.0),
              "foot_l": (0.38, 0.38, 0.24), "foot_l_rot": (147.0, 0.0, 0.0)}
SEIZA = {**mod(READY, hips=(0.0, 0.16, -0.9), hips_rot=(0.0, 0.0, 0.0), spine=(4.0, 0.0, 0.0), chest=(-2.0, 0.0, 0.0),
               neck=(4.0, 0.0, 0.0), head=(8.0, 0.0, 0.0), clav_r=(0.0, 0.0, 0.0), clav_l=(0.0, 0.0, 0.0),
               grip=(-0.6, -0.5, 1.28), blade=(0.995, 0.0, 0.06), edge=(0.0, -1.0, 0.0), elbow_r=(-0.7, 0.5, -0.3),
               hand_l=(0.62, -0.55, 1.26), hand_l_dir=(0.0, -0.98, -0.2), hand_l_up=(0.0, 0.2, 1.0), elbow_l=(0.7, 0.5, -0.3),
               knee_r=(0.0, -0.85, -0.5), knee_l=(0.0, -0.85, -0.5)), **SEIZA_FEET}

# kiza: de rodillas con los dedos metidos y los talones arriba (el paso entre seiza y pararse, o al revés)
KIZA_FEET = {**dict(zip(("foot_r", "foot_r_rot"), toe(-0.38, 0.98, 0.0, 74.0))),
             **dict(zip(("foot_l", "foot_l_rot"), toe(0.38, 0.98, 0.0, 74.0)))}
KIZA = {**mod(SEIZA, hips=(0.0, 0.12, -0.86), spine=(10.0, 0.0, 0.0)), **KIZA_FEET}
