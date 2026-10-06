"""
Arte de UI de Nindō generado por código (PIL + numpy): el kit "Tinta y Bandana".

El lenguaje sale del arte del propio equipo, no se inventa:
  * contorno negro grueso con relleno plano (la bandana y el dragón del HUD);
  * pincel seco blanco sobre negro (el logo Sprites/Logo.jpg);
  * rojo de la bandana, dorado del dragón, papel y tinta.
Sin kanji ni símbolos japoneses: los íconos son pictogramas (montaña, olas, bambú, farol...).

Casi todo sale en blanco con el contorno de tinta ya horneado, para teñirlo en Unity sin perder el
borde (sobre la nieve un ícono blanco sin contorno no se leía). Los sellos rojos (hanko) y las teclas
salen ya coloreados. Se dibuja a 2-4x y se reduce (antialias); semillas fijas: siempre sale igual.

Salida: Nindo/Assets/Nindo/Resources/UI/*.png con su .meta de sprite (GUID determinístico y borde de
9-slice donde hace falta). Se cargan con Resources.Load<Sprite>("UI/<nombre>") (UISprites en C#).
Con --preview deja una hoja de contacto (_kit.png) en la carpeta que se indique.

Uso:  python Tools/UI/build_ui_art.py [--preview CARPETA]
"""
import argparse
import math
import os
import random
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Unity"))
from unity_yaml import ASSETS, texture_meta, write_meta  # noqa: E402

OUT = os.path.join(ASSETS, "Nindo", "Resources", "UI")
FONTS = os.path.join(ASSETS, "Nindo", "Art", "Fonts")

INK = (11, 10, 13)
PAPER = (245, 235, 209)
HANKO = (179, 18, 26)
WHITE = (255, 255, 255)

KIT = []  # (nombre, tamaño, borde, uso) para la hoja de contacto

# sprites que reemplazó este kit (kanji -> pictogramas, sin contorno -> con contorno)
OBSOLETE = ("SealRing", "SealMountain", "SealWater", "SealBamboo", "IconDanger")


def save(img, name, border=(0, 0, 0, 0), usage=""):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    img.save(path, optimize=True)
    size = 1 << max(5, (max(img.size) - 1).bit_length())   # potencia de 2 >= lado mayor: no se reduce al importar
    write_meta(path, texture_meta(sprite=True, mips=False, compress=False, max_size=size, border=border), force=True)
    KIT.append((name, img.size, border, usage))
    return img


# ------------------------------------------------------------------------------------- ruido
def vnoise1(n, freq, rng):
    """Ruido de valor 1D suave de largo n con ~freq nudos."""
    k = max(2, int(freq) + 2)
    knots = np.array([rng.random() for _ in range(k)])
    x = np.linspace(0, k - 1.001, n)
    i = np.floor(x).astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    return knots[i] * (1 - f) + knots[i + 1] * f


def vnoise2(h, w, cell, rng):
    gh, gw = h // cell + 2, w // cell + 2
    g = np.array([[rng.random() for _ in range(gw)] for _ in range(gh)])
    y = np.linspace(0, gh - 1.001, h)[:, None]
    x = np.linspace(0, gw - 1.001, w)[None, :]
    iy, ix = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - iy, x - ix
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a = g[iy, ix]; b = g[iy, ix + 1]; c = g[iy + 1, ix]; d = g[iy + 1, ix + 1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def ss(x0, x1, v):
    t = np.clip((v - x0) / (x1 - x0 + 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def rgba(alpha, color):
    h, w = alpha.shape
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = color
    arr[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def down(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------------------------- pincelada
def brush_alpha(L, H, seed, dry=0.55, start_pool=True, taper_end=0.28, taper_start=0.05, bow=0.04, thick=0.40,
                bristles=46, end_narrow=0.85):
    """Pincelada horizontal de sumi como alfa [0,1] de L x H: la tinta se junta al empezar y las cerdas se
    secan hacia la derecha (como el logo del equipo)."""
    rng = random.Random(seed)
    ys, xs = np.mgrid[0:H, 0:L].astype(np.float32)
    u = xs / (L - 1)
    cy = H / 2 + (np.sin(u * math.pi) - 0.5) * H * bow + (vnoise1(L, 3, rng)[None, :] - 0.5) * H * 0.05
    prof = ss(0, taper_start, u) * (1 - ss(1 - taper_end, 1.0, u) * end_narrow)
    if start_pool:
        prof = prof * (1 + 0.12 * np.exp(-((u - 0.06) / 0.05) ** 2))
    hw_top = H * thick * prof * (0.92 + 0.16 * vnoise1(L, 18, rng)[None, :]) * (0.97 + 0.06 * vnoise1(L, 120, rng)[None, :])
    hw_bot = H * thick * prof * (0.92 + 0.16 * vnoise1(L, 15, rng)[None, :]) * (0.97 + 0.06 * vnoise1(L, 110, rng)[None, :])
    d = ys - cy
    inside = np.where(d < 0, ss(0, 1.5, hw_top + d), ss(0, 1.5, hw_bot - d))
    # cerdas: la coordenada a lo ancho del trazo decide la densidad de la veta; se seca hacia la derecha
    dn = np.clip(np.where(d < 0, d / np.maximum(hw_top, 1), d / np.maximum(hw_bot, 1)), -1, 1)
    br = vnoise1(2048, bristles, rng)
    br2 = vnoise1(2048, bristles * 3, rng)
    idx = ((dn + 1) * 0.5 * 2047).astype(int)
    streak = 0.6 * br[idx] + 0.4 * br2[idx]
    dryness = dry * ss(0.35, 1.0, u) + 0.25 * dry * (np.abs(dn) ** 3)
    gaps = ss(dryness - 0.08, dryness + 0.08, streak)
    gaps = 1 - (1 - gaps) * ss(0.03, 0.15, dryness)    # donde el pincel todavía está mojado no hay huecos
    density = 0.88 + 0.12 * vnoise2(H, L, max(8, H // 3), rng)
    return np.clip(inside * gaps * density, 0, 1)


def brush_swash():
    L, H = 2048, 400
    a = brush_alpha(L, H, 3, dry=0.8, taper_end=0.35, thick=0.40, end_narrow=0.35, bristles=60)
    return save(down(rgba(a, WHITE), 1024, 200), "BrushSwash",
                usage="blanco, se tiñe: tinta detrás del título de zona, objetivo, avisos; rojo en la muerte")


def brush_line():
    L, H = 2048, 56
    a = brush_alpha(L, H, 9, dry=0.35, taper_end=0.45, taper_start=0.18, thick=0.32, bristles=12, bow=0.0)
    return save(down(rgba(a, WHITE), 1024, 28), "BrushLine", usage="raya fina bajo títulos, pista de los deslizadores")


# ------------------------------------------------------------------------------------- paneles
def ink_panel(W=1024, H=256, cap=170, seed=21):
    """Panel oscuro de 3 partes: extremos de pincel seco a izquierda y derecha, bordes ásperos y grano."""
    rng = random.Random(seed)
    w, h = W * 2, H * 2
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    body = brush_alpha(w, h, seed, dry=0.0, taper_end=0.0, taper_start=0.0, thick=0.47, bow=0.0, bristles=60)
    u = xs / (w - 1)
    endL = ss(0.0, cap * 2 / w * 0.9, u + (vnoise2(h, w, 6, rng) - 0.5) * 0.05)
    endR = 1 - ss(1 - cap * 2 / w * 0.9, 1.0, u + (vnoise2(h, w, 6, rng) - 0.5) * 0.08)
    br = vnoise1(2048, 70, rng)
    streak = br[(ys / (h - 1) * 2047).astype(int)]
    dryR = ss(1 - cap * 2 / w, 1.0, u)
    dryL = 1 - ss(0, cap * 2 / w * 0.6, u)
    gaps = ss(dryR * 0.9 - 0.1, dryR * 0.9 + 0.1, streak) * ss(dryL * 0.7 - 0.1, dryL * 0.7 + 0.1, streak)
    a = body * endL * endR * gaps * 0.92 * (0.93 + 0.07 * vnoise2(h, w, 3, rng))
    return save(down(rgba(a, INK), W, H), "InkPanel", border=(cap, 0, cap, 0),
                usage="fondo del diálogo y del consejo. Sliced (3 partes horizontales)")


def ink_card(S=512, b=128, seed=71):
    """Tarjeta oscura de 9 partes con bordes de pincel seco en los cuatro lados (pausa, opciones, controles)."""
    rng = random.Random(seed)
    s = S * 2
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    e = b * 2 * 0.55
    dx = np.minimum(xs, s - 1 - xs) + (vnoise2(s, s, 5, rng) - 0.5) * e * 0.5
    dy = np.minimum(ys, s - 1 - ys) + (vnoise2(s, s, 5, rng) - 0.5) * e * 0.5
    a = ss(e * 0.25, e, np.minimum(dx, dy))
    # vetas secas: horizontales cerca de los lados, verticales cerca de arriba y abajo
    brh = vnoise1(4096, 160, rng)[(ys / s * 4095).astype(int)]
    brv = vnoise1(4096, 160, rng)[(xs / s * 4095).astype(int)]
    dryx = 1 - ss(0, e * 1.6, dx); dryy = 1 - ss(0, e * 1.6, dy)
    a = a * ss(dryx * 0.8 - 0.1, dryx * 0.8 + 0.1, brh) * ss(dryy * 0.8 - 0.1, dryy * 0.8 + 0.1, brv)
    a = a * (0.88 + 0.06 * vnoise2(s, s, 6, rng))
    return save(down(rgba(a, INK), S, S), "InkCard", border=(b, b, b, b), usage="tarjetas altas (controles, opciones). 9-slice")


def ribbon(W=640, H=120):
    """Cinta de bandana (estilo del equipo: relleno plano, sombra, contorno negro grueso) con las puntas del nudo
    a la izquierda. Blanca con sombra gris: se tiñe roja (ítem elegido, aviso de remate) o del color de quien habla."""
    k = 2
    w, h = W * k, H * k
    band = [(150 * k, 22 * k), (w - 18 * k, 26 * k), (w - 38 * k, h - 30 * k), (150 * k, h - 26 * k)]
    tail1 = [(152 * k, 40 * k), (20 * k, 6 * k), (54 * k, 46 * k), (8 * k, 62 * k), (150 * k, 62 * k)]
    tail2 = [(150 * k, 66 * k), (36 * k, 82 * k), (62 * k, 92 * k), (26 * k, h - 6 * k), (156 * k, h - 34 * k)]
    knot = [(128 * k, 30 * k), (168 * k, 26 * k), (172 * k, h - 32 * k), (130 * k, h - 36 * k)]
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    for poly in (band, tail1, tail2, knot):
        md.polygon(poly, fill=255)
    o = 6 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (w, h), INK + (255,)), (0, 0), mask.filter(ImageFilter.MaxFilter(2 * o + 1)))
    img.paste(Image.new("RGBA", (w, h), WHITE + (255,)), (0, 0), mask)
    # sombra del tercio de abajo de la banda y de la punta de abajo (como el marrón del Health_Frame)
    shade = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(shade)
    sd.polygon([(150 * k, h * 0.62), (w - 30 * k, h * 0.6), (w - 38 * k, h - 30 * k), (150 * k, h - 26 * k)], fill=255)
    sd.polygon(tail2, fill=255)
    shade = Image.fromarray((np.asarray(shade) * (np.asarray(mask) > 0)).astype(np.uint8))
    img.paste(Image.new("RGBA", (w, h), (158, 158, 158, 255)), (0, 0), shade)
    # brillo fino arriba (tela que toma la luna)
    sd2 = ImageDraw.Draw(img)
    sd2.line([(176 * k, 34 * k), (w - 34 * k, 37 * k)], fill=(255, 255, 255, 255), width=3 * k)
    # contorno interior del nudo: separa las puntas de la banda, como en el arte del equipo
    sd2.line([(150 * k, 30 * k), (150 * k, h - 30 * k)], fill=INK + (255,), width=o)
    return save(down(img, W, H), "Ribbon", border=(190, 0, 60, 0),
                usage="cinta: ítem elegido, nombre de quien habla, aviso de remate. Se tiñe. Sliced L=190 (nudo) R=60")


def keycap(S=96):
    k = 4
    s = S * k
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    o = 5 * k
    r = 20 * k
    d.rounded_rectangle((o, o, s - o, s - o), r, fill=INK + (255,))
    d.rounded_rectangle((o * 2, o * 2, s - o * 2, s - o * 2), r - o, fill=(176, 160, 128, 255))
    d.rounded_rectangle((o * 2, o * 2, s - o * 2, s - o * 2 - 14 * k), r - o, fill=PAPER + (255,))
    return save(down(img, S, S), "KeyCap", border=(34, 34, 34, 34), usage="tecla (letra en tinta encima). Sliced")


def keyround(S=96):
    """Botón redondo del mando (□ ○ △ × o A B X Y encima, del color de cada mando)."""
    k = 4
    s = S * k
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    o = 5 * k
    d.ellipse((o, o, s - o, s - o), fill=INK + (255,))
    d.ellipse((o * 2, o * 2, s - o * 2, s - o * 2), fill=(176, 160, 128, 255))
    d.ellipse((o * 2, o * 2, s - o * 2, s - o * 2 - 12 * k), fill=PAPER + (255,))
    return save(down(img, S, S), "KeyRound", usage="botón redondo del mando")


def kunai(W=160, H=56):
    """Kunai blanco con contorno de tinta: se tiñe dorado (cursor del menú, fijado, avanzar el diálogo)."""
    k = 4
    w, h = W * k, H * k
    cy = h / 2
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.polygon([(w - 6 * k, cy), (w * 0.53, cy - h * 0.30), (w * 0.45, cy), (w * 0.53, cy + h * 0.30)], fill=255)   # hoja
    md.rectangle((w * 0.20, cy - h * 0.085, w * 0.47, cy + h * 0.085), fill=255)                                     # mango
    md.ellipse((w * 0.05, cy - h * 0.19, w * 0.05 + h * 0.38, cy + h * 0.19), fill=255)                              # anillo
    hole = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hole).ellipse((w * 0.05 + h * 0.11, cy - h * 0.08, w * 0.05 + h * 0.27, cy + h * 0.08), fill=255)
    mask = Image.fromarray(np.minimum(np.asarray(mask), 255 - np.asarray(hole)).astype(np.uint8))
    o = 4 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (w, h), INK + (255,)), (0, 0), mask.filter(ImageFilter.MaxFilter(2 * o + 1)))
    img.paste(Image.new("RGBA", (w, h), WHITE + (255,)), (0, 0), mask)
    d = ImageDraw.Draw(img)
    # media hoja en sombra (lee como metal facetado) y cinta del mango
    d.polygon([(w - 6 * k, cy), (w * 0.53, cy + h * 0.30), (w * 0.45, cy)], fill=(190, 190, 190, 255))
    for i in range(5):
        x = w * (0.22 + i * 0.05)
        d.line([(x, cy - h * 0.085), (x + 7 * k, cy + h * 0.085)], fill=(120, 120, 120, 255), width=3 * k)
    return save(down(img, W, H), "Kunai", usage="cursor del menú (apunta a la derecha), fijado y avanzar diálogo (rotado). Se tiñe")


# ------------------------------------------------------------------------------------- íconos con contorno
def jitter_poly(pts, rng, amt):
    """Polígono con el borde apenas tembloroso (pincel, no vector perfecto)."""
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n = max(2, int(math.dist(a, b) / 14))
        for j in range(n):
            t = j / n
            out.append((a[0] + (b[0] - a[0]) * t + rng.uniform(-amt, amt), a[1] + (b[1] - a[1]) * t + rng.uniform(-amt, amt)))
    return out


def outlined(mask, S, outline_px=7, fill=WHITE, line=INK):
    """Máscara (a 4x) -> sprite S x S con el contorno de tinta horneado debajo del relleno blanco: al teñir en
    Unity se colorea solo el relleno y el borde sigue negro, como el arte del equipo."""
    k = mask.size[0] / S
    o = mask.filter(ImageFilter.MaxFilter(int(2 * outline_px * k) | 1))
    o = o.filter(ImageFilter.GaussianBlur(k * 0.5))
    img = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    img.paste(Image.new("RGBA", mask.size, line + (255,)), (0, 0), o)
    img.paste(Image.new("RGBA", mask.size, fill + (255,)), (0, 0), mask.filter(ImageFilter.GaussianBlur(k * 0.35)))
    return down(img, S, S)


def canvas(S=128):
    m = Image.new("L", (S * 4, S * 4), 0)
    return m, ImageDraw.Draw(m), S * 4


ICON_MASKS = {}


def icon(name, usage, S=128, outline_px=7):
    def deco(fn):
        def run():
            m, d, s = canvas(S)
            fn(m, d, s, random.Random(zlib.crc32(name.encode())))   # hash() de str cambia en cada corrida
            ICON_MASKS[name] = m
            return save(outlined(m, S, outline_px), name, usage=usage)
        run.__name__ = fn.__name__
        ICONS.append(run)
        return run
    return deco


ICONS = []


@icon("IconUnblockable", "golpe IMPARABLE (teñir carmesí): rombo con >> calado = DASH, no parry")
def _unblockable(m, d, s, rng):
    c = s / 2
    d.polygon([(c, s * 0.05), (s * 0.95, c), (c, s * 0.95), (s * 0.05, c)], fill=255)
    for dx in (-0.13, 0.09):
        x = c + s * dx
        d.polygon([(x - s * 0.09, c - s * 0.2), (x + s * 0.11, c), (x - s * 0.09, c + s * 0.2), (x - s * 0.17, c + s * 0.2),
                   (x + s * 0.03, c), (x - s * 0.17, c - s * 0.2)], fill=0)


@icon("IconAlert", "el enemigo te vio (teñir dorado)")
def _alert(m, d, s, rng):
    c = s / 2
    d.polygon(jitter_poly([(c - s * 0.13, s * 0.07), (c + s * 0.13, s * 0.07), (c + s * 0.05, s * 0.64), (c - s * 0.05, s * 0.64)], rng, s * 0.004), fill=255)
    d.ellipse((c - s * 0.1, s * 0.73, c + s * 0.1, s * 0.93), fill=255)


@icon("IconGuard", "el enemigo se cubre / rebotó tu golpe (teñir acero)")
def _guard(m, d, s, rng):
    outer = [(s * .5, s * .06), (s * .88, s * .18), (s * .84, s * .56), (s * .5, s * .94), (s * .16, s * .56), (s * .12, s * .18)]
    d.polygon(jitter_poly(outer, rng, s * 0.004), fill=255)
    d.line([(s * .5, s * .2), (s * .5, s * .8)], fill=0, width=int(s * 0.05))


@icon("IconFinisher", "remate (teñir dorado), junto a la tecla")
def _finisher(m, d, s, rng):
    c = s / 2
    d.polygon([(c, s * 0.95), (c + s * 0.11, s * 0.52), (c - s * 0.11, s * 0.52)], fill=255)
    d.rectangle((c - s * 0.24, s * 0.44, c + s * 0.24, s * 0.52), fill=255)
    d.rectangle((c - s * 0.07, s * 0.08, c + s * 0.07, s * 0.44), fill=255)
    d.ellipse((c - s * 0.1, s * 0.02, c + s * 0.1, s * 0.16), fill=255)


@icon("IconBoss", "jefe: katanas cruzadas (sello de la presentación y de la barra)")
def _boss(m, d, s, rng):
    for sgn in (1, -1):
        cx = s / 2
        d.line([(cx - sgn * s * .38, s * .1), (cx + sgn * s * .3, s * .82)], fill=255, width=int(s * .07))
        d.line([(cx + sgn * s * .17, s * .6), (cx + sgn * s * .41, s * .64)], fill=255, width=int(s * .07))
        d.line([(cx + sgn * s * .3, s * .82), (cx + sgn * s * .38, s * .92)], fill=255, width=int(s * .09))


@icon("ZoneMountain", "Montaña Kodoyama / sello de la montaña")
def _mountain(m, d, s, rng):
    d.polygon(jitter_poly([(s * .03, s * .86), (s * .40, s * .14), (s * .62, s * .55), (s * .72, s * .40), (s * .97, s * .86)], rng, s * 0.004), fill=255)
    # línea de nieve calada bajo la cima
    d.line([(s * .26, s * .42), (s * .33, s * .35), (s * .39, s * .44), (s * .46, s * .35), (s * .53, s * .45)], fill=0, width=int(s * .045), joint="curve")


@icon("ZoneLake", "Aldea del Lago Kohan / sello del lago")
def _lake(m, d, s, rng):
    for row, y in enumerate((0.30, 0.53, 0.76)):
        pts = []
        for i in range(60):
            x = 0.07 + 0.86 * i / 59
            pts.append((s * x, s * (y + 0.065 * math.sin((x * 2.3 + row * 0.33) * math.tau))))
        d.line(pts, fill=255, width=int(s * 0.1), joint="curve")


@icon("ZoneBamboo", "Bosque de Bambú / sello del bambú")
def _bamboo(m, d, s, rng):
    # dos cañas con nudos y hojas (una sola caña a 50 px se leía como una espada)
    for (x0, x1) in ((0.24, 0.41), (0.54, 0.71)):
        for (y0, y1) in ((0.05, 0.30), (0.34, 0.61), (0.65, 0.95)):
            d.rectangle((s * x0, s * y0, s * x1, s * y1), fill=255)
    d.polygon([(s * 0.71, s * 0.32), (s * 0.98, s * 0.14), (s * 0.82, s * 0.37)], fill=255)
    d.polygon([(s * 0.71, s * 0.37), (s * 0.96, s * 0.46), (s * 0.75, s * 0.43)], fill=255)
    d.polygon([(s * 0.24, s * 0.63), (s * 0.02, s * 0.50), (s * 0.19, s * 0.68)], fill=255)


@icon("ZoneHome", "Hogar de Kaito (minka de techo de paja empinado)")
def _home(m, d, s, rng):
    # techo de paja alto (gasshō) que ocupa casi todo: con un techo bajo se confundía con el dojo
    d.polygon(jitter_poly([(s * .5, s * .04), (s * .95, s * .64), (s * .05, s * .64)], rng, s * 0.004), fill=255)
    for k in (0.26, 0.44):   # capas de la paja, caladas
        d.line([(s * (.5 - k * .72), s * (.04 + k * .95)), (s * (.5 + k * .72), s * (.04 + k * .95))], fill=0, width=int(s * .028))
    d.rectangle((s * .2, s * .64, s * .8, s * .92), fill=255)
    d.rectangle((s * .43, s * .72, s * .57, s * .92), fill=0)


@icon("ZoneFields", "Campos de Inaba (espigas de arroz)")
def _fields(m, d, s, rng):
    for x in (0.28, 0.5, 0.72):
        d.line([(s * x, s * .9), (s * x, s * .44), (s * (x + .1), s * .18)], fill=255, width=int(s * .055), joint="curve")
        for j in range(4):
            yy = s * (.24 + j * .075)
            d.ellipse((s * (x + .02 + j * .015), yy, s * (x + .11 + j * .015), yy + s * .065), fill=255)
    d.rectangle((s * .08, s * .86, s * .92, s * .95), fill=255)


@icon("ZoneForest", "Linde del Bosque (pino)")
def _forest(m, d, s, rng):
    for y0, w0 in ((0.06, 0.2), (0.28, 0.31), (0.5, 0.42)):
        d.polygon(jitter_poly([(s * .5, s * y0), (s * (.5 + w0), s * (y0 + .31)), (s * (.5 - w0), s * (y0 + .31))], rng, s * 0.003), fill=255)
    d.rectangle((s * .44, s * .8, s * .56, s * .95), fill=255)


@icon("ZoneWall", "La Muralla Kurokage")
def _wall(m, d, s, rng):
    d.rectangle((s * .06, s * .3, s * .94, s * .92), fill=255)
    for i in range(5):
        d.rectangle((s * (.06 + i * .19), s * .16, s * (.06 + i * .19 + .1), s * .3), fill=255)
    d.pieslice((s * .36, s * .52, s * .64, s * .8), 180, 360, fill=0)
    d.rectangle((s * .36, s * .66, s * .64, s * .92), fill=0)


@icon("ZoneGarden", "Jardín del Clan / santuarios (farol de piedra)")
def _garden(m, d, s, rng):
    d.polygon([(s * .5, s * .03), (s * .88, s * .28), (s * .12, s * .28)], fill=255)
    d.rectangle((s * .29, s * .3, s * .71, s * .56), fill=255)
    d.rectangle((s * .41, s * .36, s * .59, s * .5), fill=0)
    d.rectangle((s * .43, s * .56, s * .57, s * .84), fill=255)
    d.rectangle((s * .22, s * .84, s * .78, s * .96), fill=255)


@icon("ZoneDojo", "Dojo Kurokage (dos aleros con las puntas levantadas)")
def _dojo(m, d, s, rng):
    d.polygon([(s * .0, s * .36), (s * .1, s * .44), (s * .9, s * .44), (s * 1., s * .36), (s * .8, s * .3), (s * .2, s * .3)], fill=255)
    d.polygon([(s * .12, s * .16), (s * .22, s * .24), (s * .78, s * .24), (s * .88, s * .16), (s * .66, s * .1), (s * .34, s * .1)], fill=255)
    d.rectangle((s * .3, s * .22, s * .7, s * .32), fill=255)
    d.rectangle((s * .44, s * .02, s * .56, s * .12), fill=255)
    d.rectangle((s * .18, s * .44, s * .82, s * .92), fill=255)
    d.rectangle((s * .34, s * .56, s * .66, s * .92), fill=0)
    d.line([(s * .5, s * .56), (s * .5, s * .92)], fill=255, width=int(s * .035))


@icon("ZoneMoon", "prólogo: luna llena con una nube")
def _moon(m, d, s, rng):
    d.ellipse((s * .12, s * .08, s * .88, s * .84), fill=255)
    # nube calada que cruza la luna (sin ella es solo un círculo)
    for (x, y, r) in ((.3, .7, .13), (.48, .64, .16), (.68, .7, .12)):
        d.ellipse((s * (x - r), s * (y - r), s * (x + r), s * (y + r)), fill=0)
    d.rectangle((s * .17, s * .7, s * .8, s * .86), fill=0)
    for (x, y, r) in ((.3, .72, .09), (.48, .67, .12), (.66, .72, .08)):
        d.ellipse((s * (x - r), s * (y - r), s * (x + r), s * (y + r)), fill=255)
    d.rectangle((s * .21, s * .72, s * .74, s * .81), fill=255)


def pip(S=32):
    """Rombo de postura con contorno: se tiñe dorado (lleno) o gris (vacío)."""
    m, d, s = canvas(S)
    c = s / 2
    d.polygon([(c, s * 0.12), (s * 0.88, c), (c, s * 0.88), (s * 0.12, c)], fill=255)
    return save(outlined(m, S, 3.2), "Pip", usage="rombo de postura (enemigos y jefes)")


def hanko(name, S=160, seed=31):
    """Sello rojo (cuadrado de bordes ásperos) con el pictograma calado en color papel."""
    rng = random.Random(seed + len(name))
    s = S * 2
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    n = vnoise2(s, s, 10, rng)
    m = 0.08 * s + (n - 0.5) * 0.035 * s
    inside = (xs > m) & (xs < s - m) & (ys > m) & (ys < s - m)
    speck = vnoise2(s, s, 3, rng) > 0.12            # el sello no entinta parejo
    a = (inside & speck).astype(np.float32) * (0.86 + 0.14 * vnoise2(s, s, 24, rng))
    img = rgba(a, HANKO)
    pm = ICON_MASKS[name].resize((int(s * 0.64),) * 2, Image.LANCZOS)
    pa = np.asarray(pm).astype(np.float32) / 255 * (0.9 + 0.1 * vnoise2(pm.size[1], pm.size[0], 4, rng))
    img.alpha_composite(rgba(pa, PAPER), (int(s * 0.18), int(s * 0.18)))
    return save(down(img, S, S), "Hanko_" + name, usage="sello del título de zona / jefe")


def seal_disc(S=128):
    """Medallón del sello: aro de tinta, disco blanco (se tiñe laca o dorado) y un aro fino en relieve."""
    k = 4
    s = S * k
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2 * k, 2 * k, s - 2 * k, s - 2 * k), fill=INK + (255,))
    d.ellipse((9 * k, 9 * k, s - 9 * k, s - 9 * k), fill=WHITE + (255,))
    d.ellipse((17 * k, 17 * k, s - 17 * k, s - 17 * k), outline=(150, 150, 150, 255), width=3 * k)
    # brillo de laca arriba a la izquierda
    d.arc((14 * k, 14 * k, s - 14 * k, s - 14 * k), 200, 250, fill=(255, 255, 255, 255), width=4 * k)
    return save(down(img, S, S), "SealDisc", usage="medallón del sello (teñir laca vacío / oro obtenido)")


def ring(S=128, width=0.08, seed=41):
    """Aro de pincel fino (estallidos del sello y del remate)."""
    rng = random.Random(seed)
    s = S * 2
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.hypot(xs - s / 2, ys - s / 2) / (s / 2)
    ang = np.arctan2(ys - s / 2, xs - s / 2)
    wob = (vnoise1(4096, 30, rng)[((ang + math.pi) / math.tau * 4095).astype(int)] - 0.5) * 0.03
    a = ss(0.9 - width + wob, 0.9 - width + 0.02 + wob, r) * (1 - ss(0.9 + wob, 0.92 + wob, r))
    return save(down(rgba(a, WHITE), S, S), "Ring", usage="aro de estallido (teñir)")


def boss_bar(W=1400, H=72, seed=61):
    L, Hs = W * 2, H * 2
    back = brush_alpha(L, Hs, seed, dry=0.45, taper_end=0.06, taper_start=0.03, thick=0.47, bow=0.0, bristles=80)
    save(down(rgba(back, INK), W, H), "BossBarBack", border=(80, 0, 80, 0), usage="trazo de tinta de la barra del jefe (sliced)")
    fill = brush_alpha(L, Hs, seed + 1, dry=0.15, taper_end=0.02, taper_start=0.01, thick=0.27, bow=0.0, bristles=90)
    return save(down(rgba(fill, WHITE), W, H), "BossBarFill", usage="vida del jefe y de los enemigos (teñir; Filled horizontal)")


def dragon_eye(W=64, H=40):
    """Ojo del dragón del HUD (el arte del equipo no lo trae): almendra con contorno, iris blanco para teñir
    (oro / brasa) y pupila rasgada de tinta. El brillo y el parpadeo los hace la UI."""
    k = 4
    w, h = W * k, H * k
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    pts = []
    for i in range(64):
        t = i / 63
        x = w * (0.08 + 0.84 * t)
        pts.append((x, h * 0.5 - h * 0.36 * math.sin(t * math.pi) ** 0.8 - h * 0.06 * t))      # párpado de arriba
    for i in range(64):
        t = 1 - i / 63
        x = w * (0.08 + 0.84 * t)
        pts.append((x, h * 0.5 + h * 0.26 * math.sin(t * math.pi) ** 1.1 - h * 0.06 * t))      # de abajo
    md.polygon(pts, fill=255)
    o = 4 * k
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (w, h), INK + (255,)), (0, 0), mask.filter(ImageFilter.MaxFilter(2 * o + 1)))
    img.paste(Image.new("RGBA", (w, h), WHITE + (255,)), (0, 0), mask)
    d = ImageDraw.Draw(img)
    cx, cy = w * 0.56, h * 0.47
    d.ellipse((cx - w * 0.06, cy - h * 0.32, cx + w * 0.06, cy + h * 0.32), fill=INK + (255,))    # pupila rasgada
    return save(down(img, W, H), "DragonEye", usage="ojo del dragón (iris se tiñe)")


def soft_dot(size=64):
    """Punto suave (brasas, brillo de los ojos del dragón, sombras de legibilidad del HUD)."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    r = np.hypot(xs - c, ys - c) / c
    a = np.clip(1 - r, 0, 1) ** 2.2
    return save(rgba(a, WHITE), "SoftDot", usage="punto suave")


# ------------------------------------------------------------------------------------- hoja de contacto
def contact(path):
    cols, cw, ch = 5, 380, 230
    rows = math.ceil(len(KIT) / cols)
    sheet = Image.new("RGB", (cols * cw, rows * ch), (58, 64, 72))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(os.path.join(FONTS, "ZenMaruGothic-Bold.ttf"), 15)
    for i, (name, size, border, usage) in enumerate(KIT):
        x, y = (i % cols) * cw, (i // cols) * ch
        d.rectangle((x + 4, y + 4, x + cw - 4, y + ch - 52), fill=(38, 44, 40) if (i // cols + i) % 2 == 0 else (128, 140, 156))
        im = Image.open(os.path.join(OUT, name + ".png")).convert("RGBA")
        im.thumbnail((cw - 20, ch - 66))
        sheet.paste(im, (x + (cw - im.width) // 2, y + 8 + (ch - 60 - im.height) // 2), im)
        d.text((x + 8, y + ch - 48), f"{name}  {size[0]}x{size[1]}  {border}", font=f, fill=(255, 240, 210))
        d.text((x + 8, y + ch - 28), usage[:52], font=f, fill=(200, 200, 200))
    sheet.save(path)
    print("hoja de contacto:", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=None, help="carpeta donde dejar la hoja de contacto (_kit.png)")
    a = ap.parse_args()
    print("UI ->", os.path.relpath(OUT, ASSETS))
    for name in OBSOLETE:
        for p in (os.path.join(OUT, name + ".png"), os.path.join(OUT, name + ".png.meta")):
            if os.path.exists(p):
                os.remove(p)
    brush_swash(); brush_line(); ink_panel(); ink_card(); ribbon(); keycap(); keyround(); kunai()
    for fn in ICONS:
        fn()
    pip()
    for n in ("ZoneHome", "ZoneFields", "ZoneForest", "ZoneWall", "ZoneGarden", "ZoneDojo", "ZoneMountain", "ZoneLake", "ZoneBamboo", "ZoneMoon", "IconBoss"):
        hanko(n)
    seal_disc(); ring(); boss_bar(); dragon_eye(); soft_dot()
    for name, size, border, usage in KIT:
        print(f"  {name:18s} {size[0]}x{size[1]}  borde {border}")
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        contact(os.path.join(a.preview, "_kit.png"))


if __name__ == "__main__":
    main()
