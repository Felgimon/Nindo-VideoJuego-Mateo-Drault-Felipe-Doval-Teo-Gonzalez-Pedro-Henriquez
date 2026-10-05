"""
Agrega las vocales con macrón del rōmaji (Ā ā Ē ē Ī ī Ō ō Ū ū) a las fuentes del juego.

Shippori Mincho B1 y Zen Maru Gothic no traen esos caracteres: TextMeshPro los dibujaba con
LiberationSans y "NINDŌ", "Gorō" u "Ōzeki" quedaban con una letra de otra tipografía.
Las dos fuentes sí tienen la vocal y el macrón suelto (U+00AF), así que cada vocal nueva es un
glifo compuesto (vocal + macrón centrado arriba), igual que las fuentes arman la Ô.

Licencia: SIL OFL 1.1 sin "Reserved Font Name" (ver Nindo/Assets/Nindo/Art/Fonts/OFL-README.txt),
así que se pueden modificar y distribuir con el mismo nombre.

Uso (fontTools):  python Tools/Fonts/add_macrons.py
Es idempotente: si la fuente ya tiene el carácter no lo toca.
"""
import os
import sys

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = [os.path.join(ROOT, "Nindo", "Assets", "Nindo", "Art", "Fonts", n)
         for n in ("ShipporiMinchoB1-ExtraBold.ttf", "ZenMaruGothic-Bold.ttf")]

# (código, nombre del glifo nuevo, carácter base) - la ī va sobre la i sin punto
VOWELS = [
    (0x0100, "Amacron", "A"), (0x0101, "amacron", "a"),
    (0x0112, "Emacron", "E"), (0x0113, "emacron", "e"),
    (0x012A, "Imacron", "I"), (0x012B, "imacron", "ı"),
    (0x014C, "Omacron", "O"), (0x014D, "omacron", "o"),
    (0x016A, "Umacron", "U"), (0x016B, "umacron", "u"),
]
GAP = 0.066  # separación vocal-macrón en em (la que trae Shippori entre la O y su macrón)


def bounds(glyf, name):
    g = glyf[name]
    g.recalcBounds(glyf)
    return g.xMin, g.yMin, g.xMax, g.yMax


def add_macrons(path):
    font = TTFont(path)
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    vmtx = font["vmtx"] if "vmtx" in font else None
    upm = font["head"].unitsPerEm
    macron = cmap[0x00AF]
    mx0, my0, mx1, _ = bounds(glyf, macron)
    order = font.getGlyphOrder()
    added = []
    for code, name, base_char in VOWELS:
        if code in cmap:
            continue
        base = cmap[ord(base_char)]
        bx0, _, bx1, by1 = bounds(glyf, base)
        dx = round((bx0 + bx1) / 2 - (mx0 + mx1) / 2)
        dy = round(by1 + GAP * upm - my0)
        pen = TTGlyphPen(font.getGlyphSet())
        pen.addComponent(base, (1, 0, 0, 1, 0, 0))
        pen.addComponent(macron, (1, 0, 0, 1, dx, dy))
        glyph = pen.glyph()
        glyph.components[0].flags |= 0x0200  # USE_MY_METRICS: avance y lsb de la vocal
        glyf[name] = glyph  # según la versión de fontTools esto ya lo suma al orden de glifos
        if name not in order:
            order.append(name)
        glyph.recalcBounds(glyf)
        hmtx[name] = (hmtx[base][0], glyph.xMin)
        if vmtx is not None:
            adv_h, tsb = vmtx[base]
            vmtx[name] = (adv_h, tsb - (glyph.yMax - by1))
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[code] = name
        added.append(chr(code))
    if added:
        glyf.glyphOrder = order
        font.setGlyphOrder(order)
        font.save(path)
    print(os.path.basename(path) + ": " + ("agregadas " + " ".join(added) if added else "ya estaba completa"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for f in FONTS:
        add_macrons(f)
