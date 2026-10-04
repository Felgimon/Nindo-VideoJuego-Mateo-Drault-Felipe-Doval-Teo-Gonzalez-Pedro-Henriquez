"""Nindo shared colour palette.

Every environment mesh is UV-mapped onto a single 256x256 palette atlas
(16x16 swatches of 16px).  A face's colour is chosen by name; the UVs of the
whole face are collapsed onto the centre of that swatch, so the result is a
flat, faceted low-poly look that batches perfectly in Unity (one material).

Colours are authored for a moonlit night: the lighting in Unity is blue and
dim, so albedos are kept fairly saturated and not too dark.
"""

# name -> hex (sRGB).  ORDER MATTERS: index in this list == swatch index.
PALETTE = [
    # --- woods -------------------------------------------------------------
    ("wood_dark", "#3b2a20"), ("wood", "#6b4a32"), ("wood_light", "#9a7350"),
    ("wood_pale", "#c39f74"), ("wood_red", "#a8322a"), ("wood_red_dark", "#6e1d1b"),
    ("wood_black", "#2a2422"), ("wood_grey", "#7d756a"),
    # --- bamboo ------------------------------------------------------------
    ("bamboo", "#7fa140"), ("bamboo_dark", "#4e6b2a"), ("bamboo_dry", "#b8a35a"),
    ("bamboo_light", "#a4c25a"),
    # --- roofs -------------------------------------------------------------
    ("thatch", "#a8905a"), ("thatch_dark", "#75613c"), ("thatch_light", "#c8b07a"),
    ("tile_dark", "#2f3640"), ("tile_blue", "#3d4a5c"), ("tile_light", "#58667a"),
    ("copper_green", "#4f8a7a"),
    # --- walls / plaster / paper -------------------------------------------
    ("plaster", "#e6dcc8"), ("plaster_shade", "#bfb39c"), ("plaster_dirty", "#a99c84"),
    ("shoji", "#f2ead6"), ("paper", "#efe3c6"),
    # --- stone -------------------------------------------------------------
    ("stone", "#8a8a86"), ("stone_dark", "#5f615f"), ("stone_light", "#b0aea6"),
    ("stone_moss", "#6f7d5a"), ("stone_warm", "#9a8f7d"),
    # --- rock / cliff --------------------------------------------------------
    ("rock", "#7d7f86"), ("rock_dark", "#55575e"), ("rock_light", "#a3a5aa"),
    ("rock_brown", "#7b6656"), ("rock_brown_dark", "#56463b"),
    # --- ground --------------------------------------------------------------
    ("grass", "#4f7d3a"), ("grass_dark", "#365c2e"), ("grass_light", "#78a04a"),
    ("grass_teal", "#3e6b55"), ("grass_dry", "#9a9a52"), ("moss", "#5a7a3a"),
    ("dirt", "#7a5c3e"), ("dirt_dark", "#5a4330"), ("path", "#b9a074"),
    ("path_dark", "#97805c"), ("mud", "#5c4632"), ("sand", "#d6c49a"),
    ("snow", "#e8eef5"), ("snow_shade", "#b9c7d8"), ("ice", "#a9d4e6"),
    # --- foliage -------------------------------------------------------------
    ("leaf_pine", "#2f5a3c"), ("leaf_pine_dark", "#203f2c"), ("leaf_pine_light", "#3f7350"),
    ("leaf", "#4c8a3e"), ("leaf_dark", "#33652c"), ("leaf_light", "#6aa84e"),
    ("sakura", "#f2a7c3"), ("sakura_dark", "#d97aa0"), ("sakura_light", "#ffd0e0"),
    ("maple", "#c4462f"), ("maple_orange", "#e07b39"), ("maple_dark", "#8f2c22"),
    ("reed", "#9caa5a"), ("wheat", "#d9b85a"), ("wheat_dark", "#b08f3e"),
    ("rice_green", "#7cb34a"), ("trunk", "#4a3628"), ("trunk_light", "#6e5440"),
    ("trunk_snow", "#5a4a40"),
    # --- flowers -------------------------------------------------------------
    ("flower_yellow", "#f2cc4a"), ("flower_blue", "#5a7fd6"), ("flower_white", "#f4f1e8"),
    ("flower_red", "#d6453a"), ("flower_purple", "#9a6ad0"), ("flower_pink", "#f08ab0"),
    # --- water ---------------------------------------------------------------
    ("water_shallow", "#3f7f8f"), ("water_deep", "#1f4a5e"), ("water_foam", "#cfe7ec"),
    # --- cloth / misc ----------------------------------------------------------
    ("cloth_red", "#b0302a"), ("cloth_indigo", "#2e3d6b"), ("cloth_white", "#ece6da"),
    ("cloth_black", "#26262c"), ("cloth_purple", "#5b3a6b"), ("cloth_blue", "#3a6b9a"),
    ("rope", "#c9b27a"), ("straw", "#d2bd80"), ("gold", "#d9a93a"), ("gold_dark", "#a07a24"),
    ("iron", "#4a4d52"), ("iron_light", "#7a7e85"), ("black", "#1c1c20"),
    ("white", "#f4f4f0"), ("lantern_paper", "#f0c27a"), ("lantern_red", "#c23a2a"),
    ("clay", "#a8653f"), ("clay_dark", "#7a4a30"), ("tatami", "#c9c08a"),
    ("tatami_edge", "#3a4a3a"), ("ink", "#22252a"),
    # --- emissive (only meaningful on the Nindo_Emissive material slot) -------
    ("glow_warm", "#ffb347"), ("glow_fire", "#ff7a2a"), ("glow_spirit", "#ffd86b"),
    ("glow_portal", "#6fd6ff"), ("glow_moon", "#cfe6ff"), ("glow_window", "#ffcf7a"),
    ("glow_firefly", "#d8ff7a"), ("glow_red", "#ff4a3a"), ("glow_white", "#ffffff"),
    ("glow_purple", "#c08aff"), ("glow_water", "#7ff0e0"),
]

GRID = 16          # swatches per row
SWATCH_PX = 16     # pixels per swatch
SIZE = GRID * SWATCH_PX

INDEX = {name: i for i, (name, _) in enumerate(PALETTE)}
assert len(PALETTE) <= GRID * GRID, "palette too large"


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def uv_of(name):
    """UV coordinate of the centre of a swatch (origin bottom-left, like Blender/Unity)."""
    if name not in INDEX:
        raise KeyError(f"Unknown palette colour '{name}'")
    i = INDEX[name]
    col, row = i % GRID, i // GRID
    u = (col + 0.5) / GRID
    v = 1.0 - (row + 0.5) / GRID
    return (u, v)


def write_png(path, emissive_only=False):
    """Writes the atlas with PIL (outside Blender) or numpy-free fallback."""
    from PIL import Image
    img = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    px = img.load()
    for i, (name, hx) in enumerate(PALETTE):
        if emissive_only and not name.startswith("glow_"):
            continue
        r, g, b = (int(c * 255) for c in hex_to_rgb(hx))
        col, row = i % GRID, i // GRID
        for y in range(row * SWATCH_PX, (row + 1) * SWATCH_PX):
            for x in range(col * SWATCH_PX, (col + 1) * SWATCH_PX):
                px[x, y] = (r, g, b)
    img.save(path)


if __name__ == "__main__":
    import json, sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    write_png(f"{out}/NindoPalette.png")
    write_png(f"{out}/NindoPalette_Emission.png", emissive_only=True)
    json.dump({n: {"index": i, "hex": h, "uv": uv_of(n)} for i, (n, h) in enumerate(PALETTE)},
              open(f"{out}/NindoPalette.json", "w"), indent=1)
    print(len(PALETTE), "colours")
