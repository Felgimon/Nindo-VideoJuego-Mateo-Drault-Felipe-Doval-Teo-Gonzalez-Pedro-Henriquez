"""Hojas de contacto de animación con rótulos (Python del sistema + Pillow; Blender no trae PIL).

uso: python contact_sheet_anim.py layout.json
layout = {"out": png, "title": str, "width": 1280, "rows": [{"label": str, "tiles": [{"img": png,
          "label": str, "crop": [x0, y0, x1, y1] | null}]}], "tile_h": 300, "delete": true}
Cada fila escala sus cuadros a la misma altura y los parte en renglones que entren en 'width'
(los renders de revisión no pasan de 1280 px). 'delete' borra los cuadros sueltos al terminar.
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont


def font(size):
    for f in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main(path):
    lay = json.load(open(path, encoding="utf-8"))
    W = int(lay.get("width", 1280))
    th = int(lay.get("tile_h", 300))
    f_t, f_r, f_c = font(22), font(16), font(14)
    blocks = []
    for row in lay["rows"]:
        ims = []
        for t in row["tiles"]:
            if not os.path.exists(t["img"]):
                continue
            im = Image.open(t["img"]).convert("RGB")
            if t.get("crop"):
                im = im.crop(tuple(int(v) for v in t["crop"]))
            h = th
            w = max(1, int(im.width * h / im.height))
            im = im.resize((w, h), Image.LANCZOS)
            d = ImageDraw.Draw(im)
            if t.get("label"):
                d.rectangle((0, 0, im.width, 20), fill=(0, 0, 0))
                d.text((5, 2), t["label"], fill=(255, 230, 160), font=f_c)
            ims.append(im)
        if not ims:
            continue
        lines, cur, cw = [], [], 0
        for im in ims:
            if cur and cw + im.width > W:
                lines.append(cur)
                cur, cw = [], 0
            cur.append(im)
            cw += im.width + 2
        if cur:
            lines.append(cur)
        blocks.append((row.get("label", ""), lines))
    H = 34 + sum(24 + len(lines) * (th + 2) for _, lines in blocks)
    sheet = Image.new("RGB", (W, H), (14, 14, 18))
    d = ImageDraw.Draw(sheet)
    d.text((8, 6), lay.get("title", ""), fill=(255, 255, 255), font=f_t)
    y = 34
    for label, lines in blocks:
        d.text((8, y + 3), label, fill=(170, 200, 255), font=f_r)
        y += 24
        for line in lines:
            x = 0
            for im in line:
                sheet.paste(im, (x, y))
                x += im.width + 2
            y += th + 2
    sheet.save(lay["out"], optimize=True)
    print("SHEET", lay["out"], sheet.size)
    if lay.get("delete"):
        for row in lay["rows"]:
            for t in row["tiles"]:
                try:
                    os.remove(t["img"])
                except OSError:
                    pass


if __name__ == "__main__":
    main(sys.argv[1])
