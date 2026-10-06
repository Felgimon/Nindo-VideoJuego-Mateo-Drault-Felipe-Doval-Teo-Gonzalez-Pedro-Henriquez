"""El abuelo (Nindo/Art/Models/Characters/Grandpa.fbx): pulido y re-exportación en el mismo lugar.

blender -b --python export_grandpa.py -- [--write] [--src otro.fbx] [--out carpeta]

La primera versión de este script (en el historial de git) armaba el FBX desde ViejoGaga.blend del Drive
del equipo, coloreando por hueso dominante. Ahora el punto de partida es el propio FBX, como el resto de
los personajes. El archivo trae al abuelo ('Cuerpo') y al ninja del secuestro ('Cube') en un solo
Armature con una toma global 'Scene' (frames 1-75 a 30 fps): Grandpa.fbx.json y el .meta que genera
generate_assets.py (clips 'Idle' y 'Kidnap') dependen de ese nombre y ese rango, así que se re-exporta igual
(toma de escena, sin desplazar frames, unidades FBX_SCALE_UNITS como la exportación original).

El abuelo mira a +Y en Blender, Z arriba, 3.18 u = 1.45 m. Cambios (audit_models MODEL-08):
  - la faja roja: la regla vieja no tocaba ninguna cara (el kimono no tenía aristas en la cintura).
    Se cortan dos anillos en z 1.33 / 1.52 (los pesos se interpolan) y la franja pasa a 'Abuelo_Faja',
    con un moño atrás
  - el sombrero era casi del color del camino (#c9a868 contra #b9a074): paja oscura con anillos tejidos
    más claros, se separa del suelo desde la cámara alta; la frente vuelve a ser piel (la regla vieja,
    descentrada en x, la pintaba de sombrero de un solo lado)
  - cara amable: ojos cerrados en arco, cejas blancas caídas, bigote y mejillas
  - el ninja del secuestro pasa al mismo carbón frío que los ninjas del juego
"""
import bpy, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C
from mathutils import Vector

REL = "Nindo/Art/Models/Characters/Grandpa.fbx"
COLORS = {
    "Abuelo_Sombrero": "#7a5634",
    "Abuelo_Kimono": "#3d5a7a",
    "Abuelo_Faja": "#9a2c22",
    "Abuelo_Piel": "#e3ab84",
    "GrisOscuro": "#2a2d3a",          # el secuestrador
    "Piel": "#e9b88a",
}
GRANDPA = dict(apply_scale_options='FBX_SCALE_UNITS', bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False)

o = C.args()
src = o["src"] or os.path.join(C.ASSETS, REL)
arm = C.load(src, anim_offset=0.0)      # frames del archivo tal cual: la toma de escena es absoluta
act = arm.animation_data.action
f0, f1 = (int(round(x)) for x in act.frame_range)
scn = bpy.context.scene
scn.frame_start, scn.frame_end = f0, f1
poses = C.sample_poses(arm)
C.rest(arm, True)
body = bpy.data.objects["Cuerpo"]
faja = C.material("Abuelo_Faja", "#9a2c22")
trenza = C.material("Abuelo_SombreroTrenza", "#a8814a")
ojos = C.material("Abuelo_Ojos", "#3a2a22")
mejilla = C.material("Abuelo_Mejilla", "#d98f78")
barba = bpy.data.materials["Abuelo_Barba"]

# ------------------------------------------------------------------ faja
if C.count(body, "Abuelo_Faja") == 0:
    C.bisect_loops(body, (1.33, 1.52), "Abuelo_Kimono")
    n = C.reassign(body, lambda f: f.mat == "Abuelo_Kimono" and 1.33 < f.c.z < 1.52, faja)
    print("faja", n, "caras")

# ------------------------------------------------------------------ sombrero y frente
# lo que estaba pintado de sombrero debajo del ala y mirando de costado es la frente
n = C.reassign(body, lambda f: f.mat == "Abuelo_Sombrero" and f.c.z < 2.76 and abs(f.n.z) < 0.5, bpy.data.materials["Abuelo_Piel"])
print("frente devuelta a piel", n)
# anillos tejidos: las caras empinadas de los escalones del ala (n.z 0.4-0.78; las planas pasan de 0.85)
# van más claras, así los anillos siguen la geometría (desde arriba es lo que más se ve de él)
n = C.reassign(body, lambda f: f.mat == "Abuelo_Sombrero" and f.c.z > 2.76 and 0.4 < f.n.z < 0.78, trenza)
print("anillos del sombrero", n)
C.recolor(COLORS)

# ------------------------------------------------------------------ cara amable
if C.count(body, "Abuelo_Ojos") == 0:
    skin = [body.matrix_world @ body.data.vertices[vi].co for f in C.faces(body) if f.mat == "Abuelo_Piel" and f.dom == "Cabeza"
            for vi in body.data.polygons[f.index].vertices]

    def surf(x, z, off=0.012):
        near = [p.y for p in skin if abs(p.x - x) < 0.035 and abs(p.z - z) < 0.035]
        return (max(near) if near else 0.3) + off

    def on_face(pts, off=0.012):
        return [Vector((x, surf(x, z, off), z)) for x, z in pts]
    geo = C.Geo()
    # alturas medidas en la cara del equipo: cuencas ~2.64, base de la nariz ~2.53, boca ~2.42, barba desde 2.32
    for s in (1, -1):
        # ojos cerrados en arco (la sonrisa de los ojos), metidos en las cuencas
        eye = on_face([(s * 0.06, 2.626), (s * 0.09, 2.643), (s * 0.125, 2.646), (s * 0.155, 2.628)], off=0.006)
        geo.ribbon(eye, [0.016, 0.02, 0.02, 0.016], "Abuelo_Ojos", thick=0.012, up=(0, 1, 0))
        # cejas blancas, tupidas y caídas hacia afuera
        brow = on_face([(s * 0.04, 2.695), (s * 0.10, 2.712), (s * 0.16, 2.70), (s * 0.21, 2.665)], off=0.018)
        geo.ribbon(brow, [0.03, 0.042, 0.036, 0.022], "Abuelo_Barba", thick=0.03, up=(0, 1, 0))
        # bigote: nace bajo la nariz y cae por los costados de la boca hasta la barba
        mus = on_face([(s * 0.015, 2.505), (s * 0.07, 2.485), (s * 0.12, 2.44), (s * 0.15, 2.37)], off=0.018)
        geo.ribbon(mus, [0.036, 0.042, 0.034, 0.022], "Abuelo_Barba", thick=0.028, up=(0, 1, 0))
        # mejillas
        cx, cz = s * 0.18, 2.535
        y = surf(cx, cz, 0.006)
        geo.face(geo.add_verts([(cx - 0.035, y, cz - 0.022), (cx + 0.035, y, cz - 0.022), (cx + 0.035, y, cz + 0.022), (cx - 0.035, y, cz + 0.022)]), "Abuelo_Mejilla")
    print("cara", C.attach(body, geo, ("bone", "Cabeza")), "tris")

    # moño de la faja, atrás (el abuelo da la espalda en el secuestro)
    sash = [body.matrix_world @ body.data.vertices[vi].co for f in C.faces(body) if f.mat == "Abuelo_Faja"
            for vi in body.data.polygons[f.index].vertices]
    yb = min(p.y for p in sash if abs(p.x) < 0.12) - 0.02
    geo = C.Geo()
    geo.prism((0, yb + 0.03, 1.43), (0, yb - 0.07, 1.43), 0.07, 0.06, "Abuelo_Faja", seg=6, up=(0, 0, 1), sy=0.8)
    for sx in (-1, 1):
        geo.ribbon([(sx * 0.03, yb - 0.04, 1.40), (sx * 0.06, yb - 0.05, 1.28), (sx * 0.075, yb - 0.04, 1.16)],
                   [0.07, 0.065, 0.055], "Abuelo_Faja", thick=0.02, up=(0, -1, 0))
    print("moño", C.attach(body, geo, ("nearest_each", None), near_mat="Abuelo_Faja"), "tris")

# bind_tol: Blender reconstruye el giro de los huesos de los pies (casi paralelos a -Y) con 0.07° de error;
# las poses animadas dan exactamente igual (compare_poses) y a esa escala es menos de 0.001 u en el pie
C.finish(arm, src, REL, o, export_kw=GRANDPA, anim_offset=0.0, poses=poses, bind_tol=0.1)
