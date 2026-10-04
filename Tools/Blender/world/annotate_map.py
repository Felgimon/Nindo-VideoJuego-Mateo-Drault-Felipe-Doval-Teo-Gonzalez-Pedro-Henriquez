"""Anota el mapa cenital (shot_map.png) con zonas, santuarios, jefes y portales -> Docs/img/mapa.jpg"""
import os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import world_plan as W
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
im = Image.open(os.path.join(HERE, "..", "out", "world", "shot_map.png")).convert("RGB")
d = ImageDraw.Draw(im, "RGBA")
FONTS = os.path.join(REPO, "Nindo", "Assets", "Nindo", "Art", "Fonts")
big = ImageFont.truetype(os.path.join(FONTS, "ShipporiMinchoB1-ExtraBold.ttf"), 30)
small = ImageFont.truetype(os.path.join(FONTS, "ZenMaruGothic-Bold.ttf"), 17)
SCALE, CX, CZ = im.width / 500.0, 0.0, -5.0   # ortho 500 m, centrado en (0,-5)


def P(x, z):
    return im.width / 2 + (x - CX) * SCALE, im.height / 2 - (z - CZ) * SCALE


def label(x, z, text, font, fill=(255, 255, 255), dy=0):
    px, py = P(x, z)
    w = d.textlength(text, font=font)
    d.text((px - w / 2, py + dy), text, font=font, fill=fill, stroke_width=3, stroke_fill=(10, 14, 28))


zones = {"hogar": "Hogar de Kaito", "campos": "Campos de Inaba", "bosque": "Linde del Bosque", "muralla": "Muralla",
         "jardin": "Jardín del Clan", "dojo": "Dojo Kurokage", "montana": "Montaña Kodoyama", "lago": "Lago Kohan", "bambu": "Bosque de Bambú"}
# posición del cartel de cada zona (para que no pise arenas ni caminos)
SPOT = {"dojo": (0, 178), "bambu": (128, 120), "montana": (-150, 40), "lago": (140, -20), "jardin": (0, 24),
        "muralla": (0, -38), "bosque": (0, -64), "campos": (8, -112), "hogar": (-20, -150)}
for zid, x, z, r, prio in W.ZONES:
    if zid in zones:
        x, z = SPOT.get(zid, (x, z))
        label(x, z, zones[zid], big, (255, 240, 210), -18)
for cid, x, z, yaw in W.CHECKPOINTS:
    px, py = P(x, z)
    d.polygon([(px, py - 9), (px + 9, py), (px, py + 9), (px - 9, py)], fill=(120, 200, 255, 255), outline=(10, 14, 28))
names = {"goro": "Goro (sello de la montaña)", "mizuchi": "Mizuchi (sello del lago)", "ozeki": "Ozeki (sello del bambú)", "kage": "Kage (jefe final)"}
for arch, ax, az, r, bx, bz, yaw in W.BOSSES:
    px, py = P(ax, az)
    rr = r * SCALE
    d.ellipse([px - rr, py - rr, px + rr, py + rr], outline=(255, 80, 70, 255), width=4)
    label(ax, az, names.get(arch, arch), small, (255, 150, 140), (-rr - 24) if arch in ("ozeki", "goro") else rr + 4)
for eid, x, z, r, lock, enemies in W.ENCOUNTERS:
    for arch, ex, ez, yaw in enemies:
        px, py = P(ex, ez)
        d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 120, 60, 230))
for pid, x, z, yaw, flag in W.PORTALS:
    px, py = P(x, z)
    d.ellipse([px - 8, py - 8, px + 8, py + 8], outline=(110, 230, 255, 255), width=3)
sx, sz, _ = W.START
px, py = P(sx, sz)
d.regular_polygon((px, py, 11), 3, fill=(255, 230, 90, 255), outline=(10, 14, 28))
label(sx, sz, "Inicio", small, (255, 230, 90), 12)
# leyenda
lx, ly = 24, im.height - 130
d.rounded_rectangle([lx - 12, ly - 12, lx + 330, ly + 112], 10, fill=(10, 14, 28, 200))
items = [((120, 200, 255), "◆ Santuario (guardado / viaje)"), ((255, 120, 60), "● Enemigos"),
         ((255, 80, 70), "◯ Arena de jefe"), ((110, 230, 255), "◯ Portal de regreso al dojo")]
for i, (c, t) in enumerate(items):
    d.text((lx, ly + i * 25), t, font=small, fill=c)
out = os.path.join(REPO, "Docs", "img", "mapa.jpg")
im.save(out, quality=86)
print("ok", out, im.size)
