# Traspaso a la sesión local de Claude Code (Nindō)

> Pegá este archivo entero como primer mensaje de la sesión local de Claude Code (o decile:
> "leé `Docs/HANDOFF_SESION_LOCAL.md` y seguí desde ahí"). Lo escribió la sesión en la nube que
> hizo todo el trabajo de la rama `claude/serene-edison-xd7v94`.

---

## 0. Quién sos y qué tenés que hacer

Vas a continuar el desarrollo de **Nindō**, un juego de acción ninja low‑poly en Unity, hecho
originalmente por cuatro amigos (Felipe Doval —el usuario con el que hablás—, Teo González,
Mateo Drault y Pedro Henríquez). Una sesión anterior de Claude en la nube reescribió casi todo
el juego, pero **nunca pudo abrir Unity**: todo compila contra las DLLs de Unity 6, los modelos
se revisaron con renders de Blender y el audio por análisis, pero **nada se jugó**.

Vos sí tenés Unity (6.3 LTS, 6000.3.25f1) y el MCP de Unity en la PC del usuario. Tu trabajo,
en orden:

1. **Dejar el proyecto abriendo y jugando sin errores** en la rama `claude/serene-edison-xd7v94`.
2. **Probar el juego de verdad** (con el MCP: entrar en Play, leer la consola, sacar capturas de
   la vista Game) y corregir todo lo que se rompa o se vea mal.
3. Seguir puliendo hacia lo que el usuario quiere (sección 1), siendo autocrítico.

Hablá con el usuario en español (rioplatense, como él). Explicá corto qué hiciste y qué
encontraste, y sé honesto con lo que no pudiste verificar.

---

## 1. Lo que pidió el usuario (requisitos, en sus palabras resumidas)

- Kaito tiene que vencer a **3 jefes** que guardan **3 llaves/sellos** para abrir las puertas del
  dojo donde está su abuelo/maestro. (El Google Doc del equipo tiene la historia completa.)
- **Mantener sí o sí**: los **modelos de enemigos/personajes** del equipo (los del proyecto y los
  del Drive) y el **formato del combate**: parry, habilidades, sistema de maná/espíritu similar al
  original. Todo lo demás se puede rehacer: refactorizar código, pulir mecánicas y animaciones
  (las animaciones de Blender del equipo son toscas).
- Mantener el núcleo: **low‑poly**, cámara elevada en ángulo **estilo Tunic**, estética ninja,
  combate dinámico.
- **Entornos**: reemplazar o modificar fuerte los modelos de entorno viejos (feos; por ejemplo la
  casa de Kaito). **Mapa mucho más grande** que el original.
- **Game feel**: movimientos de cámara en combate; al usar habilidades la cámara pasa detrás del
  personaje y cambia de perspectiva; dinámico e innovador. Mejor cielo, animaciones, más modelos.
- **Optimización** y código escalable/fácil de extender.
- Último pedido: el agua se veía muy plana → se hizo agua low‑poly animada (sección 5).
- Herramientas que el usuario ofreció: Higgsfield, Blender, su PC, Google/Drive (usar del Drive
  **solo** los modelos de personajes).

---

## 2. Git: estado y reglas

- Rama de trabajo: **`claude/serene-edison-xd7v94`** (11 commits sobre `main`). Toda la versión
  nueva está ahí. `main` es el juego viejo.
- El usuario tenía en su PC **~222 cambios sin commitear en `main`** (Unity actualizó el proyecto
  de 2022.3.6f1 a 6.3: `.csproj`, materiales re-serializados, `DefaultVolumeProfile`, etc.).
  Antes de cambiar de rama confirmá que los haya guardado en una rama aparte
  (`actualizacion-unity6`) o pedíselo. **No los descartes ni los commitees en `main`.**
- La rama nueva tiene `ProjectVersion.txt` en 2022.3.6f1; al abrirla con 6.3 Unity la va a
  actualizar: está bien, commiteá esa actualización en la rama de trabajo.
- Commits: mensajes claros en español; terminá cada mensaje con
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (sin otros identificadores de modelo).
- **No crees un Pull Request** salvo que el usuario lo pida. Pusheá a la misma rama
  (`git push -u origin claude/serene-edison-xd7v94`).
- Puede haber también una sesión en la nube trabajando en la misma rama (Blender, audio, código
  sin Unity): hacé `git pull` antes de empezar y seguido; commits chicos y frecuentes.

---

## 3. Cómo arranca el juego (arquitectura en 1 minuto)

Leé **`README.md`** de la raíz (controles, estructura, pipelines). Lo esencial:

- Escenas: **`Assets/Nindo/Scenes/Menu.unity`** (inicio) y **`Assets/Nindo/Scenes/Nindo.unity`**
  (juego). Están en Build Settings (Menu índice 0). Las escenas viejas de `Assets/Scenes/`
  (`World`, `MateScene`, `Probando…`, `DebugScene…`) son del juego viejo: ignoralas
  (sus errores, como el prefab `MurallaPuerta` faltante, no importan).
- Las escenas nuevas tienen **solo un bootstrap** (`GameBootstrap` / `MenuBootstrap`). Todo se
  construye en runtime desde **`Assets/Nindo/Resources/NindoContent.asset`** (ScriptableObject
  con referencias a modelos, controllers, props, zonas del mundo, materiales, VFX, audio, UI).
- `WorldBuilder` instancia los FBX de `Assets/Nindo/Art/Models/World/`:
  `World_Terrain.fbx` (`T__` terreno por chunks, `W__` agua, `B__` límites invisibles,
  `D__` decoración fusionada) y `World_<zona>.fbx` con *empties* `P__<prop>__…` (props) y
  `M__<Tipo>__<args>` (marcadores: Start, Checkpoint, Encounter, Enemy, BossArena, Boss, Zone,
  Trigger, Portal, Door, Barrier, NPC, Fireflies, SealGate). Procesa por fases, hace static
  batching, construye el **NavMesh en runtime** y reparte luces con un pool.
- Código en `Assets/Nindo/Scripts/` (namespace `Nindo`): Core (Game = service locator,
  bootstrap, eventos, guardado JSON en `persistentDataPath/nindo_save.json`, fábricas),
  Input, Combat (AttackDef, CombatDirector con tokens de ataque, CharacterAnimator con CrossFade
  por código), Player, Enemies (Enemy, Boss, EnemyArchetypes), Camera (CameraDirector: tomas
  mezclables, lock-on, shake, oclusión), FX, Audio, UI (todo por código), World, Story
  (StoryDirector = cinemáticas/objetivos; **StoryText = todos los textos**), Editor (menú Nindo).
- Debug en el Inspector del `GameBootstrap` de `Nindo.unity`: `debugSkipIntro`,
  `debugStartCheckpoint` (`cp_home`, `cp_fields`, `cp_forest`, `cp_wall`, `cp_garden`,
  `cp_dojo_gate`, `cp_mountain`, `cp_mountain_top`, `cp_lake`, `cp_lake_docks`, `cp_bamboo`,
  `cp_dojo`), `debugUnlockAll`.
- Menú **Nindo** del editor: *Contenido/Validar*, *Contenido/Autocompletar* (rellena
  NindoContent buscando assets por convención), *Jugar desde el menú* (Ctrl+Shift+P),
  *Borrar partida guardada*.
- `Assets/_Legacy/` y el entorno viejo (`Assets/Models/Environment`, `Assets/Materials`,
  `Assets/Textures`) no entran en el build; los materiales de Sumo y Goro sí usan texturas de
  `Assets/Textures`.

### Historia / progresión
Prólogo en el hogar (secuestro del abuelo, la bandana y la guadaña→katana, pelea tutorial) →
campos de Inaba → linde del bosque → muralla Kurokage (portón) → jardín del clan (sumo,
habilidades) → tres ramas: **Montaña Kodoyama (Goro, sello de la montaña)**, **Lago Kohan
(Mizuchi, sello del lago, arena flotante)**, **Bosque de Bambú (Ozeki, sello del bambú)** →
portón del dojo con 3 huecos (`SealGate`) → patio del dojo: **Kage** (jefe final, espejo de
Kaito) → final con el abuelo. Tras cada jefe aparece un portal de regreso al dojo.
Mapa anotado: `Docs/img/mapa.jpg`. Plan del nivel: `Tools/Blender/world/world_plan.py`.

### Combate (formato original, pulido)
Parry con ventana (perfecta = cámara lenta) → desequilibrio; si el enemigo termina el combo
desequilibrado queda **Exhausto** (rematable con F/△); golpes a un exhausto consumen el
desequilibrio y vuelve a la guardia (contraataca). Ataques **imparables** (rojos) se esquivan con el
dash (esquiva perfecta = cámara lenta). **Espíritu** (maná): lo llenan parries/golpes; lo gastan
dash, remate, **Corte del Viento** (cámara sobre el hombro) y **Torbellino** (órbita baja).
**Filo de Ira** con poca vida; matar cura. Tokens de ataque para peleas grupales legibles.
No hay guardia sosteniendo el parry (el README ya lo dice).

---

## 4. Primera abierta: checklist (hacelo en este orden con el MCP)

1. Abrir el proyecto en la rama nueva; esperar la importación (≈120 FBX nuevos + audio).
   Aceptar la actualización de paquetes si la pide (URP 17, Input System, VFX Graph).
2. **Consola**: anotar todos los errores de compilación/importación y corregirlos primero.
   El código compiló limpio contra las DLLs de 6000.3 (Roslyn), pero los paquetes reales del
   proyecto pueden diferir.
3. Menú *Nindo → Contenido → Validar*; si algo falta, *Autocompletar* y volver a validar.
4. **Shaders propios** (nunca compilados en Unity): `Assets/Nindo/Shaders/NindoWater.shader`
   ("Nindo/Water Lowpoly"), `NindoFoliage.shader` ("Nindo/Foliage Wind"),
   `NindoSky.shader` ("Nindo/Night Sky"). Si alguno da error o se ve rosa: corregirlo. Mientras
   tanto se pueden apagar con `useAnimatedWater` / `useFoliageWind` en NindoContent (vuelven a
   URP/Lit). Los renderers se pasaron a **Forward+** (`m_RenderingMode: 2`).
5. Abrir `Menu.unity` → Play. Verificar menú, opciones, Nueva partida.
6. Jugar el prólogo completo (sin `debugSkipIntro`): cinemática del secuestro, tutorial de
   parry/dash, remate del ninja, objetivo. Después probar con `debugStartCheckpoint` cada zona y
   cada jefe.
7. Cosas a mirar con atención (riesgos conocidos):
   - **Escala y orientación** de props y mundo (FBX exportados con `bake_space_transform`,
     frente de los props = +Z de Unity; los empties del mundo traen rotación/escala).
   - **NavMesh en runtime**: que los enemigos caminen por caminos, escaleras del dojo
     (2 tramos de 16 escalones), pasarela del lago (1.8 m) y la arena flotante.
   - **CharacterController** en escaleras/rampas (stepOffset), límites invisibles (`B__`).
   - **Cámara**: distancia 24 / pitch 52 / FOV 30 en exploración; tomas de habilidades,
     remate, intro/muerte de jefes; oclusores (árboles/techos pasan a "solo sombra").
   - **Animaciones**: duraciones por estado generadas (`stateNames/stateLengths` en
     NindoContent), velocidades por estado, CrossFade repetido al mismo estado.
   - **Tiempos de combate**: ventanas de parry (`PlayerConfig`), ritmo de enemigos
     (`EnemyArchetypes`). Ojo: los contraataques de ninja/Mizuchi/Kage quedaron más rápidos al
     usar las duraciones reales de los clips; a Kage se le subió el aviso (telegraph). Ajustar
     jugando.
   - **Agua**: ajustar a ojo el material `Assets/Nindo/Art/Materials/Nindo_WaterLowpoly.mat`
     (`_WaveHeight`, `_FacetBoost`, `_CrestContrast`, `_RippleStrength/_RippleScale`,
     `_FoamThreshold`, `_SparkleAmount`, colores) y copiar los valores finales a
     `Tools/Unity/generate_assets.py` (si no, una regeneración los pisa).
   - Luces de faroles (LightPool), niebla por zona, nieve en la montaña, luciérnagas.
   - **Audio**: volúmenes en NindoContent (sfx/music/ambience), música por zona/combate/jefe,
     game over sin cortarse, pasos por superficie.
   - Guardado/carga: santuarios (respawn, viaje por portales), sellos, flags de jefes.
8. Commit + push después de cada bloque de arreglos que funcione.

---

## 5. Lo que se hizo (para que no lo rehagas)

- **Arquitectura nueva** completa (sección 3), compatible con 2022.3 donde era barato.
- **Personajes**: modelos y clips originales del equipo con AnimatorControllers generados
  (`Assets/Nindo/Animation/*.controller`); abuelo exportado desde Blender (`Grandpa.fbx`, su clip
  'inicio' es el secuestro). Kage reutiliza los clips de Kaito.
- **Mundo** generado en Blender (`Tools/Blender/world`): ~500×400 m, 9 zonas, terreno facetado
  con colores por zona, 115 props low‑poly nuevos (`Assets/Nindo/Art/Models/Props`,
  manifest con colliders/tags en `Assets/Nindo/Data/PropsManifest.json`), decoración de suelo
  fusionada por chunk, límites invisibles, marcadores de gameplay. `validate_plan.py` chequea el
  plan (0 problemas).
- **Agua low‑poly animada**: malla con datos en color de vértice (R amplitud, G orilla por cara,
  B profundidad por cara), shader con olas, crestas, facetas finas, reflejo de luna, destellos y
  espuma facetada; botes con `FloatingBob` (misma fórmula de ola, reloj `Time.time`).
- **Follaje con viento** (peso en color R, se decodifica gamma en el shader).
- **Audio** (`Tools/Audio/build_audio.py`): 48 claves de efectos (Kenney CC0 + síntesis), 6
  ambientes en loop sintetizados, 13 temas CC0 de OpenGameArt. Créditos en
  `Assets/Nindo/Audio/CREDITS.md`. Los mp3 viejos del equipo (`Assets/Audios`, incluido uno de
  John Coltrane con copyright) ya no se usan; conviene borrarlos antes de publicar.
- **Auditoría de runtime** (20 hallazgos; 17 corregidos, 3 refutados) con revisión adversarial:
  registro de santuarios, jefes que se aceleraban al reintentar, sello perdido (soft‑lock),
  humo infinito de barreras, efectos de pantalla trabados tras remate+cinemática, enemigos que no
  atacaban, duraciones/velocidades de animación, intro en bucle, input tras pausa, música de game
  over, plantillas de FX duplicadas.
- Texturas 4K de personajes importadas a 1024. README, mapa anotado y renders en `Docs/img/`.

## 6. Pendientes / ideas (después de que todo funcione)

- Todo lo de la checklist de la sección 4 (es lo más importante: nada se probó jugando).
- Balance general del combate y la dificultad de cada jefe, jugándolo.
- Pulir animaciones toscas del equipo (sobre todo ataques de enemigos) si se ven mal en juego.
- Iluminación nocturna, post-proceso (`ScreenFX`) y lectura de enemigos desde la cámara alta.
- Rendimiento: medir con el Profiler (≈1900 props + decoración fusionada + NavMesh runtime).
- Borrar assets viejos que no se usan (con el OK del usuario).

## 7. Regenerar assets (si tocás Blender o audio)

```bash
# Blender 4.x (ajustá la ruta en Windows)
blender -b --python Tools/Blender/build_props.py -- --export [--module props_nature] [--only id1,id2]
python Tools/Blender/world/validate_plan.py
blender -b --python Tools/Blender/world/build_world.py -- --export [--map] [--preview]
python Tools/Audio/build_audio.py [--only sfx|amb|music]   # necesita numpy y ffmpeg
python Tools/Unity/generate_assets.py   # metas con GUID deterministas, materiales, controllers, NindoContent, escenas
```

`generate_assets.py` **sobrescribe** NindoContent.asset, materiales generados y escenas
`Menu/Nindo`: si cambiás algo a mano en Unity que el generador produce, pasalo también al
script. Convenciones de Blender en `Tools/Blender/STYLE.md` (frente = −Y de Blender = +Z de
Unity; metros; paleta de colores por UV).
