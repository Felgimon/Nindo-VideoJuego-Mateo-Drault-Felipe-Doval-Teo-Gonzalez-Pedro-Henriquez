"""
Arte de UI de Nindō generado por código (PIL): íconos de pincel y texturas para el HUD y los paneles.

Reemplaza a los kanji que se usaban como íconos (山 水 竹 en los sellos, 危 en los ataques
imparables, 防 en la guardia): nadie los entendía. Todo se dibuja a 4x y se reduce (antialias), en
blanco sobre transparente para teñirlo en Unity, salvo donde se indica.

Salida: Nindo/Assets/Nindo/Resources/UI/*.png (+ .meta de sprite con GUID determinístico), se cargan
con Resources.Load<Sprite>("UI/<nombre>").

Uso:  python Tools/UI/build_ui_art.py
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Unity"))
from unity_yaml import ASSETS, texture_meta, write_meta  # noqa: E402

OUT = os.path.join(ASSETS, "Nindo", "Resources", "UI")
SS = 4  # supersampling


def canvas(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def finish(img, w, h, blur=0.6):
    img = img.filter(ImageFilter.GaussianBlur(blur * SS * 0.5)) if blur else img
    return img.resize((w, h), Image.LANCZOS)


def save(img, name, border=(0, 0, 0, 0)):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    img.save(path)
    write_meta(path, texture_meta(sprite=True, mips=False, compress=False, max_size=1024, border=border), force=True)
    print("  " + os.path.relpath(path, ASSETS))


def brush_poly(draw, pts, rng, jitter, fill=(255, 255, 255, 255)):
    """Polígono con el borde levemente tembloroso (trazo a pincel, no vector perfecto)."""
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n = max(2, int(math.dist(a, b) / (6 * SS)))
        for k in range(n):
            t = k / n
            x = a[0] + (b[0] - a[0]) * t + rng.uniform(-jitter, jitter)
            y = a[1] + (b[1] - a[1]) * t + rng.uniform(-jitter, jitter)
            out.append((x, y))
    draw.polygon(out, fill=fill)


def stroke(draw, pts, width0, width1, rng, fill=(255, 255, 255, 255)):
    """Trazo de pincel: ancho que va de width0 a width1 a lo largo de la polilínea."""
    total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = math.dist(a, b)
        n = max(2, int(seg / (1.5 * SS)))
        for k in range(n):
            t = k / n
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            w = (width0 + (width1 - width0) * ((acc + seg * t) / total)) * (1 + rng.uniform(-0.06, 0.06))
            draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=fill)
        acc += seg


# ------------------------------------------------------------------ sellos (montaña, agua, bambú)
def seal_ring(size=128):
    """Medallón del sello: disco con borde de pincel (se tiñe: oscuro vacío / dorado obtenido)."""
    rng = random.Random(7)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    c, r = size * SS / 2, size * SS * 0.46
    pts = [(c + math.cos(a) * r * (1 + rng.uniform(-0.015, 0.015)), c + math.sin(a) * r * (1 + rng.uniform(-0.015, 0.015)))
           for a in [i / 90 * math.tau for i in range(90)]]
    d.polygon(pts, fill=(255, 255, 255, 255))
    # aro interior más claro (el tinte lo oscurece igual: queda como relieve)
    r2 = r * 0.84
    d.ellipse((c - r2, c - r2, c + r2, c + r2), fill=(225, 225, 225, 255))
    return finish(img, size, size)


def seal_mountain(size=96):
    rng = random.Random(11)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    S = size * SS
    # pico principal y uno más chico detrás
    brush_poly(d, [(S * 0.50, S * 0.84), (S * 0.70, S * 0.40), (S * 0.96, S * 0.84)], rng, S * 0.004)
    brush_poly(d, [(S * 0.04, S * 0.84), (S * 0.40, S * 0.14), (S * 0.78, S * 0.84)], rng, S * 0.004)
    # línea de nieve: zigzag calado bajo la cima (separa el casquete blanco del resto)
    zig = [(S * 0.25, S * 0.44), (S * 0.31, S * 0.38), (S * 0.37, S * 0.45), (S * 0.43, S * 0.37), (S * 0.49, S * 0.44), (S * 0.55, S * 0.43)]
    stroke(d, zig, S * 0.035, S * 0.03, rng, fill=(0, 0, 0, 0))
    return finish(img, size, size)


def seal_water(size=96):
    rng = random.Random(13)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    S = size * SS
    for row, y in enumerate((0.36, 0.56, 0.76)):
        pts = []
        for i in range(41):
            x = 0.1 + 0.8 * i / 40
            pts.append((S * x, S * (y + 0.055 * math.sin((x * 2.6 + row * 0.35) * math.tau))))
        stroke(d, pts, S * 0.085, S * 0.03, rng)
    return finish(img, size, size)


def seal_bamboo(size=96):
    rng = random.Random(17)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    S = size * SS
    # caña con nudos (huecos) y dos hojas
    x0, x1 = S * 0.40, S * 0.56
    for k, (y0, y1) in enumerate(((0.10, 0.34), (0.37, 0.62), (0.65, 0.92))):
        brush_poly(d, [(x0, S * y0), (x1, S * y0), (x1 + S * 0.01, S * y1), (x0 - S * 0.01, S * y1)], rng, S * 0.004)
    stroke(d, [(S * 0.56, S * 0.36), (S * 0.70, S * 0.27), (S * 0.88, S * 0.24)], S * 0.07, S * 0.012, rng)
    stroke(d, [(S * 0.40, S * 0.63), (S * 0.27, S * 0.55), (S * 0.12, S * 0.55)], S * 0.065, S * 0.012, rng)
    return finish(img, size, size)


# ------------------------------------------------------------------ marcadores de combate
def icon_danger(size=128):
    """Ataque imparable (antes 危): estallido de puntas con un "!" calado. Se tiñe rojo."""
    rng = random.Random(23)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    S = size * SS
    c = S / 2
    pts = []
    n = 9
    for i in range(n * 2):
        a = i / (n * 2) * math.tau - math.pi / 2
        r = S * (0.47 if i % 2 == 0 else 0.30) * (1 + rng.uniform(-0.05, 0.05))
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    d.polygon(pts, fill=(255, 255, 255, 255))
    # "!" transparente
    d.rounded_rectangle((c - S * 0.055, S * 0.24, c + S * 0.055, S * 0.60), radius=S * 0.04, fill=(0, 0, 0, 0))
    d.ellipse((c - S * 0.065, S * 0.66, c + S * 0.065, S * 0.79), fill=(0, 0, 0, 0))
    return finish(img, size, size, blur=0.4)


def icon_guard(size=128):
    """Enemigo en guardia (antes 防): escudo. Se tiñe celeste."""
    rng = random.Random(29)
    img = canvas(size, size)
    d = ImageDraw.Draw(img)
    S = size * SS
    outer = [(S * 0.5, S * 0.06), (S * 0.86, S * 0.18), (S * 0.82, S * 0.56), (S * 0.5, S * 0.94), (S * 0.18, S * 0.56), (S * 0.14, S * 0.18)]
    brush_poly(d, outer, rng, S * 0.004)
    inner = [(S * 0.5, S * 0.18), (S * 0.74, S * 0.26), (S * 0.71, S * 0.53), (S * 0.5, S * 0.80), (S * 0.29, S * 0.53), (S * 0.26, S * 0.26)]
    brush_poly(d, inner, rng, S * 0.003, fill=(0, 0, 0, 0))
    d.polygon([(S * 0.5, S * 0.24), (S * 0.66, S * 0.30), (S * 0.64, S * 0.50), (S * 0.5, S * 0.70)], fill=(255, 255, 255, 200))
    return finish(img, size, size, blur=0.4)


def soft_dot(size=64):
    """Punto suave (brasas, brillo de los ojos del dragón, destellos)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    px = img.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - c, y - c) / c
            a = max(0.0, 1 - r) ** 2.2
            px[x, y] = (255, 255, 255, int(255 * a))
    return img


def main():
    print("UI ->", os.path.relpath(OUT, ASSETS))
    save(seal_ring(), "SealRing")
    save(seal_mountain(), "SealMountain")
    save(seal_water(), "SealWater")
    save(seal_bamboo(), "SealBamboo")
    save(icon_danger(), "IconDanger")
    save(icon_guard(), "IconGuard")
    save(soft_dot(), "SoftDot")


if __name__ == "__main__":
    main()
