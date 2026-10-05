"""
Agrega las vocales con macrón del rōmaji (Ā ā Ē ē Ī ī Ō ō Ū ū) a las fuentes del juego.

Shippori Mincho B1 y Zen Maru Gothic no traen esos caracteres: TextMeshPro los dibujaba con
LiberationSans y "NINDŌ", "Gorō" u "Ōzeki" quedaban con una letra de otra tipografía.
Las dos fuentes sí tienen la vocal y el macrón suelto (U+00AF), así que cada vocal nueva es un
glifo compuesto (vocal + macrón):
  * el macrón va donde la propia fuente pone la diéresis sobre esa vocal (Ä, ö, ï...), así queda
    a la misma altura y centrado igual que sus acentos;
  * hereda el kerning (GPOS) y la clase GDEF de la vocal base ("Tō" se acerca como "To");
  * la versión (nameID 5) lo dice y la descripción de licencia (nameID 13) apunta a la OFL.

Licencia: SIL OFL 1.1 sin "Reserved Font Name": se pueden modificar y distribuir con el mismo
nombre si van con el copyright y la licencia (Nindo/Assets/Nindo/Art/Fonts/OFL.txt).

Uso (fontTools):  python Tools/Fonts/add_macrons.py [fuente.ttf ...]
Es idempotente: si la fuente ya tiene los caracteres no la toca. Para rehacerlas desde las originales:
  git show a0c7815:Nindo/Assets/Nindo/Art/Fonts/<fuente>.ttf > Nindo/Assets/Nindo/Art/Fonts/<fuente>.ttf
"""
import copy
import os
import sys

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = [os.path.join(ROOT, "Nindo", "Assets", "Nindo", "Art", "Fonts", n)
         for n in ("ShipporiMinchoB1-ExtraBold.ttf", "ZenMaruGothic-Bold.ttf")]

# (código, glifo nuevo, carácter base, la misma vocal con diéresis) - la ī va sobre la i sin punto
VOWELS = [
    (0x0100, "Amacron", "A", "Ä"), (0x0101, "amacron", "a", "ä"),
    (0x0112, "Emacron", "E", "Ë"), (0x0113, "emacron", "e", "ë"),
    (0x012A, "Imacron", "I", "Ï"), (0x012B, "imacron", "ı", "ï"),
    (0x014C, "Omacron", "O", "Ö"), (0x014D, "omacron", "o", "ö"),
    (0x016A, "Umacron", "U", "Ü"), (0x016B, "umacron", "u", "ü"),
]
GAP = 0.05          # solo si la fuente no tiene la vocal con diéresis: separación vocal-macrón en em
VERSION_TAG = "; Nindo: macrones"
LICENSE_NOTE = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
                "This license is available with a FAQ at: https://openfontlicense.org")


def bounds(glyf, name):
    g = glyf[name]
    g.recalcBounds(glyf)
    return g.xMin, g.yMin, g.xMax, g.yMax


def accent_box(glyf, accented, base):
    """Caja del acento de 'accented' (la vocal con diéresis), sin la vocal. None si no se puede."""
    g = glyf[accented]
    if g.isComposite():
        for c in g.components:
            if c.glyphName != base:
                x0, y0, x1, y1 = bounds(glyf, c.glyphName)
                return x0 + c.x, y0 + c.y, x1 + c.x, y1 + c.y
        return None
    top = bounds(glyf, base)[3]
    coords, ends, _ = g.getCoordinates(glyf)
    boxes, start = [], 0
    for e in ends:
        pts = coords[start:e + 1]
        start = e + 1
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if min(ys) > top:                       # contornos por encima de la vocal: los puntos
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def copy_kerning(font, base, name):
    """El glifo nuevo kernea igual que su vocal (PairPos formato 1 y 2, también dentro de Extension)."""
    if "GPOS" not in font:
        return
    gid = font.getGlyphID
    for lookup in font["GPOS"].table.LookupList.Lookup:
        subs = lookup.SubTable
        if lookup.LookupType == 9:
            subs = [s.ExtSubTable for s in subs if s.ExtSubTable.LookupType == 2]
        elif lookup.LookupType != 2:
            continue
        for st in subs:
            cov = st.Coverage.glyphs
            if st.Format == 2:
                if base in cov and name not in cov:
                    cov.append(name)
                if base in st.ClassDef1.classDefs:
                    st.ClassDef1.classDefs[name] = st.ClassDef1.classDefs[base]
                if base in st.ClassDef2.classDefs:
                    st.ClassDef2.classDefs[name] = st.ClassDef2.classDefs[base]
            elif st.Format == 1:
                # como primer glifo: copia su PairSet (el glifo nuevo tiene el id más alto: va al final)
                if base in cov and name not in cov:
                    st.PairSet.append(copy.deepcopy(st.PairSet[cov.index(base)]))
                    cov.append(name)
                    st.PairSetCount = len(st.PairSet)
                # como segundo glifo: un registro más en cada PairSet que nombra a la base
                for ps in st.PairSet:
                    recs = ps.PairValueRecord
                    for r in list(recs):
                        if r.SecondGlyph == base and not any(x.SecondGlyph == name for x in recs):
                            nr = copy.deepcopy(r)
                            nr.SecondGlyph = name
                            recs.append(nr)
                    recs.sort(key=lambda r: gid(r.SecondGlyph))
                    ps.PairValueCount = len(recs)


def add_macrons(path):
    font = TTFont(path)
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    vmtx = font["vmtx"] if "vmtx" in font else None
    gdef = font["GDEF"].table.GlyphClassDef if "GDEF" in font and font["GDEF"].table.GlyphClassDef else None
    upm = font["head"].unitsPerEm
    macron = cmap[0x00AF]
    mx0, my0, mx1, _ = bounds(glyf, macron)
    order = font.getGlyphOrder()
    added = []
    for code, name, base_char, accented_char in VOWELS:
        if code in cmap:
            continue
        base = cmap[ord(base_char)]
        bx0, _, bx1, by1 = bounds(glyf, base)
        acc = accent_box(glyf, cmap[ord(accented_char)], base) if ord(accented_char) in cmap else None
        if acc is not None:
            dx = round((acc[0] + acc[2]) / 2 - (mx0 + mx1) / 2)
            dy = round(acc[1] - my0)
        else:
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
        added.append((chr(code), base, name))
    if added:
        glyf.glyphOrder = order
        font.setGlyphOrder(order)
        for _, base, name in added:
            copy_kerning(font, base, name)
            if gdef is not None and base in gdef.classDefs:
                gdef.classDefs[name] = gdef.classDefs[base]
        names = font["name"]
        for rec in list(names.names):
            if rec.nameID == 5 and VERSION_TAG not in rec.toUnicode():
                names.setName(rec.toUnicode() + VERSION_TAG, 5, rec.platformID, rec.platEncID, rec.langID)
        if names.getDebugName(13) is None:
            names.setName(LICENSE_NOTE, 13, 3, 1, 0x409)
            names.setName(LICENSE_NOTE, 13, 1, 0, 0)
        font.save(path)
    # en códigos U+: la consola de Windows (cp1252) no imprime "Ā" y el generador también llama a esto
    print(os.path.basename(path) + ": " + ("agregadas " + " ".join("U+%04X" % ord(a[0]) for a in added) if added else "ya estaba completa"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for f in (sys.argv[1:] or FONTS):
        add_macrons(f)
