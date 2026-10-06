"""Luchador de sumo (Characters/Sumo/luchadorsumo.fbx): pulido y re-exportación en el mismo lugar.

blender -b --python export_sumo.py -- [--write] [--src otro.fbx] [--out carpeta]

El sumo mira a +Y en Blender (modelYaw 180), Z arriba, 4.85 u = 2.5 m de cuerpo (con el chonmage la unión de bounds
mide 5.06 u: por eso su "height" en NindoContent es 2.6).
Cambios (audit_models MODEL-06/11):
  - pelo pintado sobre el cráneo (caras de la cabeza arriba de la línea del pelo: cero triángulos y se
    deforma perfecto) + chonmage (el moño doblado hacia adelante) con su motoyui blanco: desde arriba
    era un huevo pelado
  - la 'Pollera' gris con foto de cuero 4K pasa a mawashi de color plano; su anillo de arriba es el
    cinto más oscuro ('PolleraCinto') y adelante cuelgan 9 sagari ('Sagari') que siguen a la tela
  - fuera las dos texturas 4K empaquetadas y las tomas que nada usa: el FBX baja de 100 MB a menos de 1 MB
  - pesos limitados a 4 huesos (185 vértices tenían 5-8)
"""
import bpy, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C
from mathutils import Vector

REL = "Characters/Sumo/luchadorsumo.fbx"
COLORS = {
    "Piel": "#d9936a",
    "Pollera": "#2e3d6b",          # mawashi índigo
    "Marron": "#3a2418",           # cejas
    "Negro": "#24150e",            # ojos y boca
}

o = C.args()
src = o["src"] or os.path.join(C.ASSETS, REL)
pose = C.default_pose(src)
arm = C.load(src)
C.rest(arm, True)
body = bpy.data.objects["Cube"]

pelo = C.material("Pelo", "#1c1c22")
pelo_b = C.material("PeloBrillo", "#34343e")
cinto = C.material("PolleraCinto", "#1d2747")
sagari = C.material("Sagari", "#45568c")      # un tono más claro que la tela: si no, de lejos no se ven
moto = C.material("Motoyui", "#ece6da")


# ------------------------------------------------------------------ pelo pintado
def hairline(y):
    """Altura de la línea del pelo según la profundidad: alta sobre la frente, baja en la nuca."""
    return 3.98 + (y + 0.78) * 0.50


is_hair = lambda f: f.mat == "Piel" and f.dom == "Cabeza" and f.c.z > hairline(f.c.y) and not (f.c.y > 0.25 and f.c.z < 4.5)
n_hi = C.reassign(body, lambda f: is_hair(f) and f.n.z > 0.6, pelo_b)
n_hair = C.reassign(body, is_hair, pelo)
print("pelo", n_hair, "+ brillo", n_hi)

# ------------------------------------------------------------------ mawashi
top = max(f.c.z for f in C.faces(body) if f.mat in ("Pollera", "PolleraCinto"))
n_belt = C.reassign(body, lambda f: f.mat == "Pollera" and f.c.z > top - 0.34, cinto)
print("cinto", n_belt, "caras (arriba de", round(top - 0.34, 2), ")")
C.recolor(COLORS)

if C.count(body, "Sagari") == 0:
    # frente de la tela a cada altura (para que las tiras bajen apoyadas, no adentro de la pollera)
    pts = [body.matrix_world @ body.data.vertices[vi].co for f in C.faces(body) if f.mat in ("Pollera", "PolleraCinto")
           for vi in body.data.polygons[f.index].vertices]

    def front(x, z):
        near = [p.y for p in pts if abs(p.z - z) < 0.09 and abs(p.x - x) < 0.18]
        return max(near) if near else max(p.y for p in pts)
    geo = C.Geo()
    z0, z1 = top - 0.36, top - 1.18
    for i in range(9):
        x = -0.56 + i * 0.14
        ring = []
        for k, z in enumerate((z0, (z0 + z1) / 2, z1)):
            y = front(x, z) + 0.035
            w = 0.09 * (1 - 0.2 * k)
            ring.append([Vector((x - w / 2, y - 0.02, z)), Vector((x + w / 2, y - 0.02, z)), Vector((x + w / 2, y + 0.03, z)), Vector((x - w / 2, y + 0.03, z))])
        geo.loft(ring, "Sagari", cap0=True, cap1=True)
    # nudo de atrás (musubi) con dos puntas: lo que se ve cuando el sumo da la espalda
    belt = [p for p in pts if p.z > top - 0.34 and abs(p.x) < 0.25]
    yb, zb = min(p.y for p in belt) - 0.05, top - 0.17
    geo.prism((0, yb + 0.06, zb), (0, yb - 0.14, zb), 0.22, 0.17, "PolleraCinto", seg=6, up=(0, 0, 1), sy=0.85)
    for sx in (-1, 1):
        geo.ribbon([(sx * 0.08, yb - 0.06, zb - 0.10), (sx * 0.12, yb - 0.08, zb - 0.32), (sx * 0.15, yb - 0.07, zb - 0.55)],
                   [0.16, 0.14, 0.11], "PolleraCinto", thick=0.05, up=(0, -1, 0))
    print("sagari + nudo", C.attach(body, geo, ("nearest_each", None), near_mat="Pollera"), "tris")

# ------------------------------------------------------------------ chonmage + motoyui
if C.count(body, "Motoyui") == 0:
    geo = C.Geo()
    # el moño: un rollo aplastado que nace en la coronilla y se dobla hacia adelante sobre el cráneo
    geo.prism((0, -0.40, 4.80), (0, -0.20, 4.92), 0.11, 0.12, "Pelo", seg=6, up=(1, 0, 0), sy=0.75)
    geo.prism((0, -0.20, 4.92), (0, 0.16, 4.93), 0.12, 0.10, "Pelo", seg=6, up=(1, 0, 0), sy=0.7)
    geo.prism((0, 0.16, 4.93), (0, 0.27, 4.88), 0.10, 0.06, "Pelo", seg=6, up=(1, 0, 0), sy=0.7)
    # motoyui: el atado blanco en la base del moño
    geo.prism((0, -0.27, 4.86), (0, -0.19, 4.915), 0.125, 0.13, "Motoyui", seg=6, up=(1, 0, 0), sy=0.8)
    print("chonmage", C.attach(body, geo, ("bone", "Cabeza")), "tris")

# sin tomas: el sumo anima con los .anim de Characters/Sumo (Sumo.controller) y ningún controller usa los
# clips del FBX; sus 8 tomas (casi estáticas) eran 2.4 MB del archivo. La pose por defecto sí se conserva.
C.finish(arm, src, REL, o, pose=pose, export_kw=dict(bake_anim=False))
