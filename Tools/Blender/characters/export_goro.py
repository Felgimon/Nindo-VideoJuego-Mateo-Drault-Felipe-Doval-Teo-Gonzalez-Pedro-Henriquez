"""Gorō, el Martillo de Kodoyama (Models/Minijefe.fbx): pulido y re-exportación en el mismo lugar.

blender -b --python export_goro.py -- [--write] [--src otro.fbx] [--out carpeta]

Gorō mira a -Y en Blender (modelYaw 0), Z arriba, 2.97 u = 3.2 m. Sus clips viven DENTRO del FBX
(Goro.controller usa las tomas 'Armature|Idle', ... con los rangos de MINIJEFE_CLIPS): se re-exportan
horneados con el mismo nombre, el mismo rango y los mismos fps, y charlib.finish compara las poses de
cada hueso en cada frame antes de pisar el archivo.

El documento de diseño pide "armadura pesada semirrústica de piedra"; el modelo leía como un orco
occidental con casco vikingo (MODEL-07). Cambios:
  - colores planos (fuera las tres fotos 4K: el FBX baja de 68 MB a 6.4 MB): piel de oni rojo que resalta en
    la nieve, armadura de piedra gris, cuero oscuro
  - los cuernos del casco en oro: pasan a ser el kuwagata de un kabuto; atrás, un shikoro de tres
    láminas (el cubrenuca escalonado) termina de sacarle la lectura de vikingo
  - nieve en las caras de la armadura y del martillo que miran arriba (viene de la montaña)
  - la soga de la cintura es un shimenawa de paja con cuatro shide de papel; las botas, cuero oscuro
  - ojos rojos que brillan (emisión) y más grandes: bajo el casco no se veían desde la cámara del juego
  - martillo 'Cylinder.005' reconstruido (252 tris en vez de 3390 con 792 aristas rotas): cabeza de
    piedra con zunchos de hierro en el slot 'Glint' (el aviso del golpe), mango de madera con agarres
"""
import bpy, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C
from mathutils import Vector

REL = "Models/Minijefe.fbx"
COLORS = {
    "PielMiniJefe": "#8f3a2a",
    "ArmaduraMiniJefe": dict(hexc="#83847f", rough=0.95),
    "CueroMiniJefe": "#4a3628",
    "CuerdaMiniJefe": "#3b2a20",          # lo que queda de la soga son las botas
    "MartilloMiniJefe": dict(hexc="#6f716d", rough=0.95),
    "BocaMiniJefe": "#2a1111",
    "NegroMiniJefe": "#1d1414",
    "RojoOjosMiniJefe": dict(hexc="#ff3a26", emission="#ff3a26", strength=4.0),
}

o = C.args()
src = o["src"] or os.path.join(C.ASSETS, REL)
arm = C.load(src)
poses = C.sample_poses(arm)
C.rest(arm, True)
body = bpy.data.objects["Cylinder.001"]
ham = bpy.data.objects["Cylinder.005"]

oro = C.material("OroMiniJefe", "#d9a93a", rough=0.5)
nieve = C.material("NieveMiniJefe", "#e8eef5", rough=0.9)
paja = C.material("PajaMiniJefe", "#c9b27a", rough=1.0)
shide = C.material("ShideMiniJefe", "#f4f1e8", rough=0.9)
madera = C.material("MaderaMiniJefe", "#5a3e2a")
C.material("Glint", "#3c3f45", rough=0.6)    # zunchos de hierro del martillo

# ------------------------------------------------------------------ casco, soga, ojos
n = C.reassign(body, lambda f: f.mat == "ArmaduraMiniJefe" and f.dom == "Cabeza" and f.c.z > 2.78 and abs(f.c.x) > 0.24, oro)
r = C.reassign(body, lambda f: f.mat == "CuerdaMiniJefe" and f.c.z > 0.95, paja)
print(f"cuernos {n}, soga de paja {r}")
# los ojos: las cuencas oscuras también brillan, así el par de ojos se ve debajo del ala del casco
e = C.reassign(body, lambda f: f.mat == "NegroMiniJefe" and f.dom == "Cabeza" and 2.5 < f.c.z < 2.58, bpy.data.materials["RojoOjosMiniJefe"])
print("cuencas que brillan", e)

if C.count(body, "ShideMiniJefe") == 0:
    # shikoro: tres láminas abiertas adelante, cada una más ancha y más baja (centro del casco y=-0.05)
    geo = C.Geo()
    for k, (z, rx, ry) in enumerate(((2.47, 0.47, 0.42), (2.38, 0.54, 0.48), (2.29, 0.61, 0.54))):
        C.arc_band(geo, (0, -0.05, z), rx, ry, 0.10, 0.035, "ArmaduraMiniJefe", -25, 205, seg=10,
                   rx2=rx - 0.06, ry2=ry - 0.06, drop=0.03)
        # el borde de arriba de cada lámina en nieve, como el resto de la armadura
        C.arc_band(geo, (0, -0.05, z + 0.055), rx - 0.05, ry - 0.05, 0.015, 0.03, "NieveMiniJefe", 10, 170, seg=8)
    print("shikoro", C.attach(body, geo, ("bone", "Cabeza")), "tris")

    # shide de papel colgando del shimenawa (adelante); siguen a la soga
    pts = [body.matrix_world @ body.data.vertices[vi].co for f in C.faces(body) if f.mat == "PajaMiniJefe"
           for vi in body.data.polygons[f.index].vertices]
    geo = C.Geo()
    for x in (-0.36, -0.12, 0.12, 0.36):
        near = [p for p in pts if abs(p.x - x) < 0.08 and 1.15 < p.z < 1.35]
        y = min(p.y for p in near) - 0.015
        top = Vector((x, y, 1.27))
        zig = [top + Vector((0.035 * (1 if i % 2 else -1) if i else 0, -0.012 * i, -0.075 * i)) for i in range(6)]
        geo.ribbon(zig, [0.085, 0.085, 0.08, 0.08, 0.075, 0.07], "ShideMiniJefe", thick=0.012, up=(0, -1, 0))
    print("shide", C.attach(body, geo, ("nearest_each", None), near_mat="PajaMiniJefe"), "tris")

# nieve al final, también sobre los escalones del shikoro: así re-correr el script no cambia nada
s = C.reassign(body, lambda f: f.mat == "ArmaduraMiniJefe" and f.n.z > 0.55, nieve)
print("nieve", s)
C.recolor(COLORS)

# ------------------------------------------------------------------ martillo
# Marco medido sobre el martillo original (mundo, reposo): mango vertical, cabeza a lo largo de X.
AX = Vector((0.013, 0.01, 1.0)).normalized()
CENTER = Vector((0.015, -2.026, 1.417))
POMMEL_T, HEAD_T, TOP_T = -1.929, 1.12, 1.515
X = Vector((1, 0, 0)); X = (X - AX * X.dot(AX)).normalized()
Y = AX.cross(X).normalized()
geo = C.Geo()


def P(t, x=0.0, y=0.0):
    return CENTER + AX * t + X * x + Y * y


# mango de madera con dos agarres de cuero (donde van Agarre1/Agarre2) y pomo de piedra
shaft = [(-1.80, 0.085, "MaderaMiniJefe"), (-1.62, 0.08, "CueroMiniJefe"), (-1.05, 0.08, "MaderaMiniJefe"), (-0.80, 0.078, "CueroMiniJefe"),
         (-0.30, 0.076, "MaderaMiniJefe"), (0.80, 0.07, None)]
for (t0, r0, m), (t1, r1, _) in zip(shaft, shaft[1:]):
    geo.prism(P(t0), P(t1), r0 * (1.12 if m == "CueroMiniJefe" else 1.0), r1 * (1.12 if m == "CueroMiniJefe" else 1.0), m, seg=6, up=X, cap0=False, cap1=False)
geo.prism(P(POMMEL_T), P(-1.80), 0.10, 0.13, "MartilloMiniJefe", seg=6, up=X)

# cabeza: bloque octogonal de piedra a lo largo de X, irregular (piedra tallada, no un barril), con las
# dos caras de golpe y sus zunchos de hierro en 'Glint': lo que se enciende en el aviso es la punta que pega
HX0, HX1 = -0.62, 0.78
RY, RZ = 0.30, (TOP_T - HEAD_T)        # alto = lo que subía la cabeza original
prof = [(HX0, 0.84, "Glint"), (HX0 + 0.05, 1.03, "Glint"), (HX0 + 0.17, 1.03, "MartilloMiniJefe"),
        (HX0 + 0.19, 0.97, "MartilloMiniJefe"), (0.08, 1.06, "MartilloMiniJefe"), (HX1 - 0.19, 0.97, "MartilloMiniJefe"),
        (HX1 - 0.17, 1.03, "Glint"), (HX1 - 0.05, 1.03, "Glint"), (HX1, 0.84, None)]
rings = []
for a, (x, k, _) in enumerate(prof):
    stone = 2 < a < 6
    rings.append([P(HEAD_T + math.sin(2 * math.pi * j / 8 + math.pi / 8) * RZ * k * (1 + (0.06 * math.sin(j * 2.3 + a * 1.7) if stone else 0)), x,
                    math.cos(2 * math.pi * j / 8 + math.pi / 8) * RY * k * (1 + (0.06 * math.cos(j * 1.9 + a * 2.1) if stone else 0)))
                  for j in range(8)])
mats = [m for _, _, m in prof]
top_face = {j for j in range(8) if math.sin(2 * math.pi * (j + 0.5) / 8 + math.pi / 8) > 0.9}
geo.loft(rings, "Glint", cap0=True, cap1=True,
         mats=lambda a, j: "NieveMiniJefe" if (j in top_face and 2 <= a <= 5) else mats[a])
# soga de paja en el centro de la cabeza: el martillo también es sagrado en Kodoyama
# (sin tapas: los extremos quedan apoyados en la piedra)
for x in (-0.06, 0.20):
    geo.prism(P(HEAD_T, x - 0.045), P(HEAD_T, x + 0.045), RY * 1.13, RY * 1.13, "PajaMiniJefe", seg=8, up=AX,
              sy=RZ / RY, cap0=False, cap1=False)
print("martillo", C.replace_mesh(ham, geo), "tris")

C.finish(arm, src, REL, o, poses=poses)
