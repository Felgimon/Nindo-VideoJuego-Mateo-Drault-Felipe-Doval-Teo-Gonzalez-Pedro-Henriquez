"""Ninja común (Models/Ninja/Ninja 1.fbx): pulido y re-exportación en el mismo lugar.

blender -b --python export_ninja.py -- [--write] [--src otro.fbx] [--out carpeta]

El ninja mira a +X en Blender (modelYaw 90), Z arriba, 2.88 u = 1.7 m.
Cambios (audit_models MODEL-01/02/12):
  - el traje sigue siendo NEGRO ("el ninja de vestimenta negra") pero carbón neutro: el negro casi puro
    de antes (98 % de la superficie) era un agujero de noche, y el carbón azulado que lo reemplazó, bajo
    la luna fría, se leía azul marino como el gi índigo de Kaito. Con uno neutro apenas cálido queda más
    oscuro y menos saturado que el gi (valor 0.30 contra 0.51 en el render de noche)
  - ojos claros en la ranura de la capucha: a 100 px de alto es lo único que dice hacia dónde mira
  - katana reconstruida (272 tris en vez de 3324) con el filo en el slot 'Glint' (aviso de parry)
Los detalles de zona (hachimaki, obi, abrigos) son kits aparte: no se tocan acá.
"""
import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C
from mathutils import Vector

REL = "Models/Ninja/Ninja 1.fbx"
COLORS = {
    "GrisOscuro": "#2e2b2c",      # carbón neutro, apenas cálido: la luna y el rim fríos ya lo azulan de noche
    "Piel": "#e9b88a",
    "Metal": dict(hexc="#b9c2cf", rough=0.45),
    "Plateado": dict(hexc="#7d828c", rough=0.5),    # tsuba y virolas de hierro
    "Negro": "#2b2124",                              # ito del mango: casi negro, apenas rojizo
    "Blanco": "#d8d4c8",
}

o = C.args()
src = o["src"] or os.path.join(C.ASSETS, REL)
pose = C.default_pose(src)
arm = C.load(src)
poses = C.sample_poses(arm)
C.rest(arm, True)
body = bpy.data.objects["Cube"]
kat = bpy.data.objects["Katana"]

# ------------------------------------------------------------------ ojos
# cada ojo es una cajita de 8 caras (GrisOscuro, hueso Cabeza) dentro de la ranura de piel
eyes = C.material("OjosNinja", "#e6ebf2", rough=0.4, emission="#dfe8ff", strength=0.25)
C.material("PupilaNinja", "#17161c")
is_eye = lambda f: f.mat == "GrisOscuro" and f.dom == "Cabeza" and 0.245 < f.c.x < 0.28 and 0.06 < abs(f.c.y + 0.022) < 0.2 and 2.43 < f.c.z < 2.545
n = C.reassign(body, is_eye, eyes)
print("caras de ojos", n)
if C.count(body, "PupilaNinja") == 0:
    # pupila: un cuadro oscuro sobre la cara frontal de cada ojo, corrido hacia la nariz (mirada fija)
    geo = C.Geo()
    for f in C.faces(body):
        if f.mat == "OjosNinja" and f.n.x > 0.9:
            pts = [body.matrix_world @ body.data.vertices[vi].co for vi in body.data.polygons[f.index].vertices]
            y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
            z0, z1 = min(p.z for p in pts), max(p.z for p in pts)
            x = max(p.x for p in pts) + 0.004
            inner = 1 if f.c.y < -0.022 else -1            # hacia el centro de la cara
            cy = (y0 + y1) / 2 + inner * (y1 - y0) * 0.12; cz = (z0 + z1) / 2 - (z1 - z0) * 0.05
            ry, rz = (y1 - y0) * 0.24, (z1 - z0) * 0.30
            geo.face(geo.add_verts([(x, cy - ry, cz - rz), (x, cy + ry, cz - rz), (x, cy + ry, cz + rz), (x, cy - ry, cz + rz)]), "PupilaNinja")
    if geo.f:
        print("pupilas", C.attach(body, geo, ("bone", "Cabeza")), "tris")

C.recolor(COLORS)

# ------------------------------------------------------------------ katana
# Marco medido sobre la katana original del equipo (mundo, reposo), fijo para que el script sea idempotente.
AXIS = Vector((0.994, 0.05, -0.093)).normalized()
CENTER = Vector((0.1, -1.34, 1.888))
POMMEL_T, GUARD_T, TIP_T = -0.643, -0.07, 1.321
C.material("Glint", "#eef3f8", rough=0.35)
side = AXIS.cross(Vector((0, 0, 1))).normalized()     # la original se curva hacia -side: el filo es +side
up = side.cross(AXIS).normalized()
geo = C.Geo()
C.katana(geo, CENTER + AXIS * GUARD_T, AXIS, side, up,
         handle_len=GUARD_T - POMMEL_T - 0.035, blade_len=TIP_T - GUARD_T, width=0.08, thick=0.022, sori=0.085,
         m={"steel": "Metal", "glint": "Glint", "wrap": "Negro", "skin": "Plateado", "metal": "Plateado"},
         handle_r=0.048, guard_r=0.085, wrap_bands=8)
print("katana", C.replace_mesh(kat, geo), "tris")

C.finish(arm, src, REL, o, poses=poses, pose=pose)
