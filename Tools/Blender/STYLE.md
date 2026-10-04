# Nindō — Environment art style guide (procedural Blender props)

Game: *Nindō*, a low-poly ninja action game with a high angled camera like *Tunic*
(perspective, pitch ≈ 50°, FOV ≈ 30°, ~20 m from the player). Rural feudal Japan at
night: moonlight (cool blue), warm lantern pools (orange), fireflies, cherry
blossoms as accents, red lacquer for important/sacred buildings. Characters are
chibi low-poly (Kaito ≈ 1.5 m tall, big head, faceted, flat colours).

## Look
* **Faceted low-poly, flat shading, solid colours** from the shared palette
  (`nindo_palette.py`). No textures, no smooth shading, no bevel modifiers.
* **Chunky, readable silhouettes**: the camera is high and far. Exaggerate roofs,
  eaves, lanterns, trunks. Nothing thinner than ~4 cm. Prefer 5–8 sided prisms
  over round things. Slight irregularity (`Part.jitter`) on natural things and
  on old wood/thatch makes it feel hand-made; keep architecture straight-ish.
* **Value contrast**: dark wood frames vs pale plaster; dark roofs vs light walls;
  foliage in 2–3 shades (light on top clusters, dark lower ones).
* **Warm glow accents**: windows/shoji/lantern paper/fire use `glow_*` colours
  (automatically on the emissive slot). Every house should have at least one
  glowing window or doorway — it is what makes the night scene read.
* Roofs dominate what the player sees from above: give them character
  (ridge caps, thick thatch edges, upturned tile eaves, gable boards).

## Technical rules
* Build with `nindo_lib.MeshBuilder` (see docstrings). One prop = one mesh.
* Origin at centre of footprint, ground at z = 0, **front faces Blender -Y**.
  (Exception: water-based props like stilt houses/docks: z = 0 is the WATER SURFACE.)
* Units: metres. Reference sizes: Kaito 1.5 m, door 2.0×1.1 m, ceiling 2.6 m,
  stone lantern 1.7 m, house 8×6 m footprint, pine 6–9 m, bamboo 8–10 m.
* Don't model faces that can never be seen (undersides resting on the ground,
  insides of closed boxes) — use `prism(..., base=False)` etc. where convenient.
* Triangle budgets (after triangulation): small prop ≤ 300, tree/bush ≤ 700,
  house ≤ 3000, big landmark ≤ 7000.
* Declare a collider for every prop: `mb.collider_box(size, center)`,
  `mb.collider_capsule(r, h)`, `mb.collider_mesh()` (only for walkable/complex
  things like bridges, stairs, platforms) or `mb.collider_none()` (grass,
  flowers, small decoration). Colliders are in prop space (Blender axes).
* Tags (`mb.tag(...)`): `occluder` (big things that can hide Kaito: trees,
  roofs, walls; the game makes them shadows-only when they block the view),
  `light_warm` / `light_fire` / `light_cool` + `mb.set("light_offset", [x,y,z])`
  (spawns a real point light there), `fireflies`, `smoke`, `nonstatic`
  (animated / interactive / pickups), `walkable` (player can stand on it).
* Foliage that should sway: pass `slot=L.SLOT_FOLIAGE` and then
  `part.wind_by_height(z_bottom, z_top)` so tips move and bases stay fixed.
* Water surfaces: `slot=L.SLOT_WATER` with `water_shallow`/`water_deep`.

## Workflow
1. Write builders in your module `Tools/Blender/props/props_<name>.py` exposing
   `PROPS = {"prop_id": build_fn}`; `build_fn(seed) -> mb.finish()`.
2. Preview: `/opt/blender/blender-4.5.14-linux-x64/blender -b --python Tools/Blender/build_props.py -- --module props_<name> --only a,b --preview`
   then `python3 Tools/Blender/contact_sheet.py /tmp/sheet.png a b` and LOOK at
   the sheet (Read tool). Iterate until it looks good *from the game camera*.
3. Export: same command with `--export` (writes FBX + manifest entry).
