"""Kaito (Animations teo/kaitooo.fbx): pulido y re-exportación en el mismo lugar.

blender -b --python export_kaito.py -- [--write] [--src otro.fbx] [--out carpeta]

Kaito mira a +X en Blender (modelYaw 90 en NindoContent), Z arriba, 2.83 u = 1.5 m.
Cambios (audit_models MODEL-02/04/09/12/13):
  - pelo en su propio material ('Pelo') con las caras que miran arriba en 'PeloBrillo': de noche la
    cabeza (42 % de su altura) era una mancha negra pegada al gi
  - ojos y cejas en 'Ojos' (antes compartían material con el gi) + brillos 'OjoBrillo' en cada ojo
  - gi índigo (opción A del audit): se separa de los ninjas negros; piel menos naranja
  - bandana: ya tiene su slot 'AmarilloBandana'; CharacterFactory.SetBandana la tapa con el material del
    pelo hasta que Kaito la recibe (MODEL-09)
  - katana 'Isan' reconstruida (260 tris en vez de 3054): hoja más ancha que se lee en pantalla,
    filo en el slot 'Glint' (CharacterGlint), mismo objeto, hueso y largo (KatanaRig y la estela no cambian)
"""
import bpy, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charlib as C
from mathutils import Vector

REL = "Animations teo/kaitooo.fbx"
COLORS = {
    "GrisOscuro": "#2e3a5e",        # gi índigo
    "Piel": "#e3a173",
    "Amarillo": "#e8b030",          # ribete del gi
    "AmarilloBandana": "#ffc21a",
    "Metal": dict(hexc="#c9d1dc", rough=0.45),
    "Blanco": "#ece6da",
    "Dorado": dict(hexc="#c9a24a", rough=0.5),
}

o = C.args()
src = o["src"] or os.path.join(C.ASSETS, REL)
pose = C.default_pose(src)
arm = C.load(src)
poses = C.sample_poses(arm)
C.rest(arm, True)
body = bpy.data.objects["Cuerpo"]
kat = bpy.data.objects["Isan"]

# ------------------------------------------------------------------ pelo, ojos
pelo = C.material("Pelo", "#1b1716")
brillo = C.material("PeloBrillo", "#3a2c27")
ojos = C.material("Ojos", "#17130f")
hair = lambda f: f.mat == "GrisOscuro" and f.dom == "cabeza" and (f.c.z > 2.28 or f.c.x < 0.30)
n_hi = C.reassign(body, lambda f: hair(f) and f.n.z > 0.55, brillo)
n_hair = C.reassign(body, hair, pelo)
# lo que queda del gi sobre el hueso de la cabeza (por delante, encima del cuello) son ojos y cejas
n_eyes = C.reassign(body, lambda f: f.mat == "GrisOscuro" and f.dom == "cabeza" and f.c.z > 1.95 and f.c.x >= 0.30, ojos)
print(f"pelo {n_hair} caras (+{n_hi} brillo), ojos/cejas {n_eyes}")

# ------------------------------------------------------------------ brillos de los ojos
if "OjoBrillo" not in [s.material.name for s in body.material_slots if s.material]:
    fs = [f for f in C.faces(body) if f.mat == "Ojos"]
    # dos ojos (y = lado) y, en cada lado, ojo abajo / ceja arriba
    geo = C.Geo()
    C.material("OjoBrillo", "#ffffff", rough=0.3, emission="#ffffff", strength=0.35)
    for side in (1, -1):
        mine = [f for f in fs if f.c.y * side > 0]
        zs = sorted(f.c.z for f in mine)
        zmid = (zs[0] + zs[-1]) / 2
        eye = [f for f in mine if f.c.z < zmid]
        pts = [body.matrix_world @ body.data.vertices[vi].co for f in eye for vi in body.data.polygons[f.index].vertices]
        x = max(p.x for p in pts) + 0.006
        y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
        z0, z1 = min(p.z for p in pts), max(p.z for p in pts)
        h = z1 - z0; w = y1 - y0
        # dos brillos cuadrados en la misma esquina de los dos ojos (una sola luz, como en el anime):
        # el grande arriba hacia +Y, el chico abajo hacia -Y
        for (cy, cz, r) in ((0.72, 0.70, 0.13), (0.30, 0.30, 0.065)):
            yy = y0 + w * cy; zz = z0 + h * cz; rr = h * r
            ids = geo.add_verts([(x, yy - rr, zz - rr), (x, yy + rr, zz - rr), (x, yy + rr, zz + rr), (x, yy - rr, zz + rr)])
            geo.face(ids, "OjoBrillo")
        print(f"ojo {side}: y {y0:.3f}..{y1:.3f} z {z0:.3f}..{z1:.3f}")
    print("brillos", C.attach(body, geo, ("bone", "cabeza")), "tris")

C.recolor(COLORS)

# ------------------------------------------------------------------ katana
# Marco medido sobre la katana original del equipo (mundo, reposo): eje de la hoja, centro del mango y
# extremos. Fijo en el script para que re-correrlo sobre el FBX ya procesado dé lo mismo.
AXIS = Vector((0.999, 0.045, 0.022)).normalized()
CENTER = Vector((-0.025, -1.082, 1.633))
POMMEL_T, GUARD_T, TIP_T = -0.39, 0.19, 1.632
C.material("Glint", "#eef3f8", rough=0.35)
side = AXIS.cross(Vector((0, 0, 1))).normalized()      # la original se curva hacia -side: el filo es +side
up = side.cross(AXIS).normalized()
geo = C.Geo()
C.katana(geo, CENTER + AXIS * GUARD_T, AXIS, side, up,
         handle_len=GUARD_T - POMMEL_T - 0.035, blade_len=TIP_T - GUARD_T, width=0.085, thick=0.024, sori=0.09,
         m={"steel": "Metal", "glint": "Glint", "wrap": "GrisOscuro", "skin": "Blanco", "metal": "Dorado"},
         handle_r=0.05, guard_r=0.095)
print("katana", C.replace_mesh(kat, geo), "tris")

C.finish(arm, src, REL, o, poses=poses, pose=pose)
