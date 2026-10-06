"""Plano del mundo de Nindō (coordenadas de JUEGO: x = este, z = norte, metros).

La cámara mira hacia el norte (+z). Este archivo es el "diseño de niveles" en datos:
zonas transitables, caminos, agua, alturas, edificios/landmarks, enemigos, santuarios,
triggers de historia y jefes. build_world.py lo convierte en terreno + props + marcadores.

Recorrido (según el documento de diseño):
  Hogar de Kaito (sur) -> Campos de Inaba -> Linde del Bosque -> Muralla Kurokage ->
  Jardín del Clan (centro) -> Puerta del Dojo (norte, 3 sellos)
  Jardín -> Montaña Kodoyama (oeste, Gorō) / Aldea del Lago (este, Mizuchi) /
  Bosque de Bambú (noreste, Ōzeki) -> portales de vuelta -> Dojo: Kage -> abuelo.
"""
import math

# extensión del terreno exportado (x0, x1, z0, z1): también es la grilla de los límites invisibles
MAP_BOUNDS = (-244, 244, -204, 196)

# --------------------------------------------------------------------------- niveles
WATER_LAKE = -0.55
WATER_STREAM = -0.45
DOJO_H = 8.0
HOME_H = 3.2

# --------------------------------------------------------------------------- transitable
# círculos: (x, z, radio, altura_objetivo o None, suavidad)
AREAS = [
    # Hogar (colina)
    ("hogar", -34, -168, 17, HOME_H, 8),
    ("hogar_patio", -24, -160, 9, HOME_H, 6),
    # Campos de Inaba
    ("campos_o", -14, -122, 24, 0.0, 10),
    ("campos_e", 26, -118, 24, 0.0, 10),
    ("campos_n", 8, -96, 16, 0.0, 8),
    # Bosque
    ("bosque_claro", 6, -62, 12, 0.0, 6),
    # Muralla (antes y después)
    ("muralla_s", 0, -40, 14, 0.0, 6),
    ("muralla_n", 0, -18, 12, 0.0, 6),
    # Jardín del Clan
    ("jardin_o", -30, 15, 26, 0.0, 10),
    ("jardin_c", 0, 30, 30, 0.0, 10),
    ("jardin_e", 32, 22, 24, 0.0, 10),
    ("jardin_n", 0, 68, 22, 0.0, 10),
    ("jardin_ne", 34, 62, 14, 0.0, 6),
    ("jardin_no", -34, 56, 14, 0.0, 6),
    # Dojo (meseta)
    ("dojo_puerta", 0, 98, 10, None, 6),
    ("dojo_patio", 0, 132, 22, DOJO_H, 8),
    ("dojo_fondo", 0, 158, 16, DOJO_H, 8),
    # Montaña (oeste)
    ("mont_base", -100, 52, 13, 2.0, 8),
    ("mont_arena", -140, 70, 19, 7.5, 8),
    ("mont_paso", -168, 92, 7, 11.5, 5),
    ("mont_cumbre", -200, 122, 17, 15.5, 8),
    # Lago (este)
    ("lago_entrada", 88, 24, 11, 0.0, 6),
    ("lago_orilla", 112, 4, 16, 0.25, 8),
    ("lago_jefe", 184, 72, 9, None, 4),            # = plataforma de la arena (radio interior ~9.2)
    # Bambú (noreste)
    ("bambu_entrada", 66, 104, 9, 1.0, 6),
    ("bambu_claro", 96, 126, 13, 1.5, 6),
    ("bambu_arena", 124, 162, 17, 2.0, 8),
]

# caminos: (nombre, [(x,z),...], ancho, altura (None = terreno))
PATHS = [
    ("camino_hogar", [(-24, -160), (-12, -150), (-2, -138), (4, -120), (8, -100), (8, -82), (4, -70), (6, -56), (0, -42), (0, -26)], 6.5, None),
    ("camino_jardin", [(0, -18), (0, 0), (-4, 18), (0, 36), (0, 58), (0, 80), (0, 96)], 7, None),
    ("camino_oeste", [(-26, 18), (-50, 30), (-72, 40), (-90, 48), (-100, 52)], 6, None),
    ("subida_monte", [(-100, 52), (-112, 58), (-126, 64), (-140, 70)], 6, None),
    ("paso_monte", [(-140, 70), (-156, 82), (-168, 92), (-182, 106), (-196, 118)], 4.5, None),
    ("camino_este", [(30, 22), (52, 26), (70, 26), (88, 24), (104, 10), (112, 4)], 6, None),
    # ancho = tablones de boardwalk_segment (1.8 m): los límites invisibles quedan en el borde
    ("pasarela_lago", [(112, 4), (126, 14), (140, 26), (156, 40), (170, 56), (184, 72)], 1.9, None),
    ("camino_ne", [(30, 60), (46, 82), (58, 96), (66, 104), (80, 114), (96, 126), (108, 140), (118, 152), (124, 162)], 5.5, None),
    ("rodeo_jardin_o", [(-30, 15), (-36, 40), (-34, 56)], 5, None),
    ("rodeo_jardin_e", [(32, 22), (36, 44), (34, 62)], 5, None),
    ("dojo_subida", [(0, 95), (0, 113)], 10, None),
]

# lago: polígono (x, z) y profundidad
LAKE = [(104, -60), (210, -70), (232, 60), (225, 150), (165, 150), (150, 100), (128, 62), (116, 34), (120, 18), (104, 0), (100, -30)]
LAKE_DEPTH = 3.0

# arroyos del jardín: polilíneas (ancho, profundidad)
STREAMS = [
    ([(-70, -4), (-46, 4), (-20, 2), (-4, 10), (14, 6), (40, 0), (66, -8)], 3.2),
    ([(-14, 44), (0, 40), (16, 46)], 2.6),
]
POND = (8, 30, 7.0)   # estanque central (x, z, radio)

# arrozales: rectángulos (x0, z0, x1, z1)
PADDIES = [(-34, -140, -18, -128), (-34, -124, -18, -112), (-14, -140, 0, -128), (-14, -124, 0, -112)]
WHEAT = [(18, -134, 40, -126), (18, -122, 40, -114)]

# --------------------------------------------------------------------------- landmarks
# (prop, x, z, yaw, scale) — yaw en grados (0 = el frente del prop mira al norte, 180 = al sur/cámara)
LANDMARKS = [
    # ---------------- Hogar
    ("house_kaito", -38, -172, 160, 1.0),
    ("storehouse_kura", -48, -160, 110, 0.9),
    ("well", -26, -170, 0, 1.0),
    ("firewood_stack", -45, -176, 200, 1.0),
    ("tree_sakura_a", -20, -176, 30, 1.1),
    ("tree_pine_b", -48, -182, 0, 1.0),
    ("fence_wood", -16, -166, 95, 1.0), ("fence_wood", -15.5, -168.5, 95, 1.0),
    ("lantern_post", -22, -158, 180, 1.0),
    ("cabbage_row", -30, -152, 90, 1.0), ("cabbage_row", -26, -152, 90, 1.0),
    ("scarecrow", -36, -152, 200, 1.0),
    ("grave_stone", -14, -152, 200, 1.0),
    # ---------------- Campos de Inaba
    ("house_farmer_a", 26, -100, 180, 1.0),
    ("house_farmer_b", 44, -104, 220, 1.0),
    ("house_farmer_a", -18, -96, 150, 0.95),
    ("cart_hand", 14, -106, 30, 1.0),
    ("hay_bale", 34, -108, 0, 1.0), ("hay_bale", 36, -110, 40, 0.9),
    ("sack_pile", 20, -104, 0, 1.0),
    ("scarecrow", -26, -126, 170, 1.0), ("scarecrow", 30, -130, 190, 1.0),
    ("well", 4, -108, 0, 1.0),
    ("signpost", 10, -86, 200, 1.0),
    ("lantern_post", 12, -112, 180, 1.0), ("lantern_post", 2, -96, 180, 1.0),
    ("barrel_stack", 50, -100, 200, 1.0),
    ("tree_round_a", 52, -116, 0, 1.0), ("tree_round_b", -40, -104, 0, 1.0),
    # ---------------- Bosque
    ("torii_stone", 7, -78, 180, 1.0),
    ("log_fallen", 14, -64, 40, 1.0), ("stump", -2, -58, 0, 1.0),
    ("mushroom_cluster", 12, -56, 0, 1.0), ("mushroom_cluster", -4, -66, 0, 1.0),
    ("lantern_stone", -2, -48, 180, 1.0), ("lantern_stone", 5, -48, 180, 1.0),
    # ---------------- Muralla
    ("wall_gate", 0, -30, 180, 1.0),
    ("banner_nobori", -6, -36, 180, 1.0), ("banner_nobori", 6, -36, 180, 1.0),
    ("torch_brazier", -5, -34, 0, 1.0), ("torch_brazier", 5, -34, 0, 1.0),
    ("weapon_rack", 9, -24, 180, 1.0),
    # ---------------- Jardín del Clan
    ("pagoda_small", -12, 36, 160, 1.0),
    ("pavilion_azumaya", 22, 36, 200, 1.0),
    ("bridge_arch@0", -2.2, 9.6, -12.5, 1.0),  # centrado en el cruce camino/arroyo (antes terminaba en medio del agua)
    ("bridge_arch@0", 0, 40, 0, 1.0),          # segundo arroyo sobre el camino al dojo (se vadeaba medio metro de agua)
    # (el puente del este, en 40,2, se quitó: el arroyo ahí no tiene orillas transitables a los dos lados)
    ("bridge_plank", -46, 4, 0, 1.0),
    ("house_village_a", -47, 21, 110, 1.0), ("house_village_b", -50, 0, 70, 1.0),
    ("house_village_a", 46, 32, 250, 1.0), ("house_village_b", 50, 8, 290, 1.0),
    ("house_village_a", -28, 70, 140, 1.0), ("house_village_b", 30, 76, 210, 1.0),
    ("storehouse_kura", -52, 48, 90, 1.0),
    ("temple_bell", 18, 60, 200, 1.0),
    ("shrine_small", -24, -10, 20, 1.0),
    ("torii_red", 0, -12, 180, 1.0), ("torii_red", 0, 88, 180, 1.0),
    ("tree_sakura_a", 14, 22, 0, 1.2), ("tree_sakura_b", -16, 52, 0, 1.1), ("tree_sakura_a", 30, 50, 0, 1.0),
    ("tree_sakura_b", -40, 36, 0, 1.0), ("tree_maple_a", 20, 4, 0, 1.0), ("tree_maple_a", -30, 4, 0, 0.9),
    ("tree_pine_a", -8, 22, 0, 1.0), ("tree_pine_c", 6, 50, 0, 0.9),
    ("training_dummy", -6, 64, 180, 1.0), ("training_dummy", 6, 64, 180, 1.0),
    ("weapon_rack", 0, 76, 180, 1.0),
    ("banner_nobori", -14, 74, 180, 1.0), ("banner_nobori", 14, 74, 180, 1.0),
    ("sake_table", 26, 38, 200, 1.0),
    ("stepping_stones", 10, 18, 30, 1.0),
    ("lily_pads", 6, 30, 0, 1.0), ("lily_pads", 11, 33, 60, 0.8),
    # ---------------- Dojo
    ("stairs_stone_large@0", 0, 100, 180, 1.0),       # 0 -> 4 m (el frente/escalón bajo mira al sur)
    ("stairs_stone_large@4", 0, 108, 180, 1.0),      # 4 -> 8 m (sufijo @altura = altura fija)
    ("dojo_gate@8", 0, 113, 180, 1.0),
    ("dojo_main", 0, 160, 180, 1.0),
    ("banner_nobori", -12, 118, 180, 1.0), ("banner_nobori", 12, 118, 180, 1.0),
    ("torch_brazier", -14, 128, 0, 1.0), ("torch_brazier", 14, 128, 0, 1.0),
    ("torch_brazier", -14, 146, 0, 1.0), ("torch_brazier", 14, 146, 0, 1.0),
    ("lantern_stone_tall", -8, 148, 180, 1.0), ("lantern_stone_tall", 8, 148, 180, 1.0),
    ("tree_pine_a", -24, 150, 0, 1.2), ("tree_pine_b", 24, 152, 0, 1.2),
    # ---------------- Montaña
    ("torii_stone", -96, 50, 292, 1.0),   # perpendicular al camino_oeste (rumbo -68°)
    ("tree_dead_a", -126, 56, 0, 1.0), ("tree_dead_a", -150, 82, 70, 0.9),
    ("rock_pillar", -150, 58, 0, 1.0), ("rock_pillar", -128, 82, 40, 0.8),
    ("torch_brazier", -134, 60, 0, 1.0), ("torch_brazier", -146, 80, 0, 1.0),
    ("mountain_cabin", -212, 138, 150, 1.0),
    ("torch_brazier", -192, 112, 0, 1.0), ("torch_brazier", -206, 112, 0, 1.0),
    ("torch_brazier", -190, 132, 0, 1.0),
    ("weapon_rack", -218, 124, 90, 1.0),
    ("campfire", -200, 130, 0, 1.0),
    # ---------------- Lago
    ("house_fisher", 134, 6, 200, 1.0), ("house_fisher", 152, 14, 230, 1.0), ("house_fisher", 128, 40, 160, 1.0),
    ("house_fisher", 165, 40, 250, 0.95),
    ("house_farmer_b", 96, 8, 160, 1.0),
    ("net_rack", 104, -8, 180, 1.0), ("net_rack", 118, -6, 200, 1.0),
    ("boat_small", 128, -6, 70, 1.0), ("boat_small", 144, 0, 120, 1.0), ("boat_small", 170, 30, 30, 1.0),
    ("barrel", 108, 14, 0, 1.0), ("crate_stack", 102, 16, 30, 1.0),
    ("lake_arena_platform", 184, 72, 225, 1.0),
    ("shrine_small", 189.1, 77.1, 225, 0.75),        # al fondo de la plataforma de la arena
    ("lantern_post", 110, 20, 180, 1.0), ("lantern_post", 98, -2, 180, 1.0),
    ("reeds_patch", 104.5, -18, 0, 1.2), ("reeds_patch", 119, 30, 40, 1.0),   # en la línea del agua (más atrás quedaban en el barranco)
    # ---------------- Bambú
    ("arch_bamboo_gate", 64, 102, 215, 1.0),
    ("arch_bamboo_gate", 116, 148, 215, 1.0),
    ("lantern_stone", 92, 120, 180, 1.0), ("lantern_stone", 102, 130, 180, 1.0),
    ("grave_stone", 84, 116, 200, 1.0),
    ("temple_bell", 134, 172, 200, 0.9),
    ("lantern_post", 118, 168, 180, 1.0), ("lantern_post", 134, 154, 180, 1.0),
]

# muralla: segmentos a lo largo de z=-30 (el portón está en x=0)
WALL_Z = -30.0
WALL_X_RANGE = (-68, 68)

# --------------------------------------------------------------------------- gameplay
START = (-26, -162, 200)             # Kaito despierta acá (x, z, yaw)
POINTS = {                           # puntos con nombre para la historia
    "scythe": (-25, -163.5),
    "kidnap_a": (-14, -150),
    "kidnap_exit": (6, -128),
    "forest_kidnap_a": (2, -46),
    "forest_kidnap_b": (0, -34),
    "wall_gate": (0, -30),
}

CHECKPOINTS = [
    ("cp_home", -22, -166, 200),
    ("cp_fields", 16, -96, 180),
    ("cp_forest", 10, -60, 200),
    ("cp_wall", 8, -16, 180),
    ("cp_garden", 1, 22, 200),     # al sur del estanque (antes en 10,28: caía adentro del agua)
    ("cp_dojo_gate", 5, 93, 180),
    ("cp_mountain", -98, 56, 120),
    ("cp_mountain_top", -189, 112, 120),
    ("cp_lake", 90, 28, 200),
    ("cp_lake_docks", 112, 16, 220),
    ("cp_bamboo", 72, 108, 200),
    ("cp_dojo", 10, 140, 180),
    # a la entrada de los jefes (antes el más cercano quedaba a 75-91 m y cada reintento era una caminata):
    # Mizuchi: sobre un muelle al costado de la pasarela, 15 m antes de la plataforma (mirando a la pasarela)
    ("cp_lake_falls", 177.25, 57.98, 311),
    # Ōzeki: en el centro del camino, 6 m antes del arco de bambú (fuera de la barrera de la arena, r 15)
    ("cp_bamboo_gate", 111.5, 144.2, 220),
]

# muelles que sostienen un santuario sobre el agua: (prop, x, z, yaw, escala). El largo (4 m) va perpendicular a la
# pasarela, del lado sin baranda (sureste), con la punta cercana tocando el borde de los tablones
CHECKPOINT_LANDINGS = [
    ("dock_segment", 176.35, 58.77, 131.2, 1.0),
]

# zonas (id, x, z, radio, prioridad)
ZONES = [
    ("hogar", -30, -165, 32, 1), ("campos", 10, -115, 50, 0), ("bosque", 4, -62, 24, 1),
    ("muralla", 0, -32, 16, 2), ("jardin", 0, 35, 75, 0), ("dojo", 0, 135, 42, 1),
    ("montana", -160, 85, 80, 1), ("lago", 140, 30, 75, 1), ("bambu", 100, 135, 50, 1),
]

# encuentros: (id, x, z, radio_activación, cerrar_área, [(arquetipo, x, z, yaw)])
ENCOUNTERS = [
    ("intro", -18, -156, 8, 0, [("ninja", -16, -152, 200)]),
    ("fields1", 14, -118, 12, 0, [("ninja", 10, -122, 0), ("ninja", 18, -114, 0)]),
    ("forest1", 6, -62, 11, 1, [("ninja", 2, -66, 180), ("ninja", 10, -58, 180), ("ninja", 4, -54, 180)]),
    ("wall", 0, -40, 9, 1, [("ninja", -4, -36, 180), ("ninja", 4, -36, 180)]),
    ("garden1", -30, 14, 14, 1, [("ninja", -36, 10, 90), ("ninja", -24, 20, 200), ("ninja", -32, 22, 150)]),
    ("garden2", 32, 22, 13, 1, [("ninja", 28, 18, 270), ("ninja", 36, 26, 200), ("ninja_elite", 32, 30, 180)]),
    ("sumo", 0, 68, 15, 1, [("sumo", 0, 72, 180), ("ninja", -8, 66, 180), ("ninja", 8, 66, 180)]),
    ("dojo_guards", 0, 92, 9, 0, [("ninja_elite", -4, 94, 180), ("ninja_elite", 4, 94, 180)]),
    ("mountain1", -140, 70, 16, 1, [("ninja_elite", -136, 74, 220), ("ninja_elite", -146, 66, 220), ("sumo_mountain", -142, 78, 220)]),
    ("mountain2", -168, 92, 7, 0, [("ninja_elite", -172, 96, 220)]),
    ("lake1", 112, 4, 14, 1, [("ninja", 108, 8, 250), ("ninja", 116, 0, 250), ("ninja_elite", 118, 10, 250), ("ninja", 110, -4, 250)]),
    ("lake2", 156, 40, 6, 0, [("ninja_elite", 159.5, 44, 220)]),   # emboscada sobre la pasarela,
    ("bamboo1", 96, 126, 12, 1, [("ninja", 92, 130, 220), ("ninja_elite", 100, 122, 220), ("ninja", 102, 132, 220)]),
]

# jefes: (arquetipo, x_arena, z_arena, radio, x_jefe, z_jefe, yaw_jefe)
BOSSES = [
    ("goro", -200, 122, 15, -204, 128, 150),
    ("mizuchi", 184, 72, 9.5, 186, 74, 225),
    ("ozeki", 124, 162, 15, 126, 166, 215),
    ("kage", 0, 132, 18, 0, 140, 180),
]

# portales de vuelta al dojo (aparecen al vencer al jefe): (id, x, z, yaw, flag)
PORTALS = [
    ("p_mountain", -190, 128, 120, "boss_goro"),
    ("p_lake", 179, 67, 225, "boss_mizuchi"),       # sobre la plataforma, junto a la entrada
    ("p_bamboo", 114, 158, 215, "boss_ozeki"),
]

# triggers de historia: (id, x, z, radio)
TRIGGERS = [
    ("fields", 8, -110, 6),
    ("forest_reveal", 8, -74, 5),
    ("wall_guards", 0, -46, 6),
    ("garden", 0, -6, 7),
    ("sumo_intro", 0, 56, 8),
    ("dojo_gate", 0, 100, 6),
]

# puertas que se abren con flags: (flag, prop, x, z, yaw_bisagra, ángulo)
DOORS = [
    # la hoja del portón se extiende hacia -X de Unity desde la bisagra: la izquierda va rotada 180°
    ("wall_gate_open", "wall_gate_door", -1.7, -30.4, 180, -105),
    ("wall_gate_open", "wall_gate_door", 1.7, -30.4, 0, 105),
    ("dojo_open", "dojo_gate_door", -2.1, 112.6, 180, -100),
    ("dojo_open", "dojo_gate_door", 2.1, 112.6, 0, 100),
]

# barreras (cuerdas) que bloquean hasta un flag: (flag, x, z, yaw, ancho)
BARRIERS = [
    ("enc_sumo", -72, 40, 70, 7),          # camino a la montaña: después del sumo
    ("enc_sumo", 70, 26, 90, 7),           # camino al lago
    ("enc_sumo", 58, 96, 35, 6.5),         # camino al bambú
]

NPCS = [("grandpa", "dojo", 0, 150, 180)]
FIREFLIES = [(30, 70, 24, 18), (-40, 40, 20, 20), (20, -8, 30, 10), (6, -62, 16, 16), (100, 130, 20, 20), (-30, -170, 16, 16)]
