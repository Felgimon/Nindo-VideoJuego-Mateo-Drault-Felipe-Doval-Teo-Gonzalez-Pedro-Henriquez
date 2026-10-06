using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;

namespace Nindo
{
    /// <summary>
    /// Construye el mundo a partir de los modelos de zona exportados desde Blender
    /// (Tools/Blender/world). Cada zona es un FBX con:
    ///   T__*  terreno (MeshCollider)      W__*  agua      B__*  límites invisibles
    ///   D__*  decoración de suelo fusionada por chunk (pasto, flores...: sin collider ni sombras)
    ///   P__propId__n  instancias de props (se reemplazan por el modelo del prop + collider)
    ///   M__Tipo__args  marcadores de gameplay (spawns, santuarios, triggers, zonas, jefes...)
    /// Después hace static batching, construye el NavMesh en runtime y prepara la atmósfera.
    /// </summary>
    public class WorldBuilder : MonoBehaviour
    {
        [Serializable] public class ColliderSpec { public string type; public float[] size; public float[] center; public float radius; public float height; }
        [Serializable] public class PropSpec { public string id; public ColliderSpec collider; public string[] tags; public float[] light_offset; public float[] size; }
        [Serializable] class Manifest { public PropSpec[] props; }

        public Transform WorldRoot { get; private set; }
        public Vector3 StartPoint { get; private set; }
        public Quaternion StartRotation { get; private set; } = Quaternion.identity;
        public bool Built { get; private set; }

        readonly Dictionary<string, PropSpec> specs = new Dictionary<string, PropSpec>();
        readonly Dictionary<string, Transform> points = new Dictionary<string, Transform>();
        readonly List<Encounter> encounters = new List<Encounter>();
        readonly List<BossArena> arenas = new List<BossArena>();
        readonly List<(BossArena arena, Vector3 pos, Quaternion rot)> bossSpawns = new List<(BossArena, Vector3, Quaternion)>();
        LightPool lightPool;
        Transform staticRoot, dynamicRoot;
        NavMeshDataInstance navInstance;
        float zoneTimer;
        ParticleSystem snow;

        public IReadOnlyList<BossArena> Arenas => arenas;

        void Awake()
        {
            Game.World = this;
            lightPool = new GameObject("[Lights]").AddComponent<LightPool>();
            lightPool.transform.SetParent(transform, false);
        }

        void OnDestroy()
        {
            if (Game.World == this) Game.World = null;
            if (navInstance.valid) navInstance.Remove();
        }

        public Transform Point(string id) => points.TryGetValue(id, out var t) ? t : null;

        public Vector3 RespawnPoint()
        {
            var cp = Checkpoint.Get(Game.Save.checkpoint);
            return cp != null ? cp.spawnPoint.position : StartPoint;
        }

        // ================================================================== construcción
        public IEnumerator Build()
        {
            var content = Game.LoadContent();
            ParseManifest(content.propsManifest);
            WorldRoot = new GameObject("[World]").transform;
            staticRoot = new GameObject("Static").transform; staticRoot.SetParent(WorldRoot, false);
            dynamicRoot = new GameObject("Dynamic").transform; dynamicRoot.SetParent(WorldRoot, false);

            if (content.zones == null || content.zones.Length == 0)
            {
                Debug.LogWarning("[Nindo] NindoContent no tiene zonas: se crea un piso de prueba.");
                var g = GameObject.CreatePrimitive(PrimitiveType.Plane);
                g.transform.SetParent(staticRoot, false);
                g.transform.localScale = new Vector3(20, 1, 20);
            }
            else
            {
                // 1) instanciar todas las zonas y juntar sus nodos
                var nodes = new List<Transform>();
                foreach (var zone in content.zones)
                {
                    if (zone == null) continue;
                    var inst = Instantiate(zone, staticRoot);
                    inst.name = zone.name;
                    foreach (Transform c in inst.transform) nodes.Add(c);
                }
                yield return null;
                // 2) procesarlos por fases: geometría, después los marcadores "contenedores"
                //    (arenas, encuentros, zonas) y al final los que se enganchan a ellos (jefes, enemigos...).
                //    Así no importa en qué archivo ni en qué orden quedó cada nodo.
                nodes.Sort((a, b) => Phase(a.name).CompareTo(Phase(b.name)));
                int n = 0;
                foreach (var c in nodes)
                {
                    ProcessNode(c);
                    if (++n % 400 == 0) yield return null;
                }
            }
            ApplyFoliageWind(content);
            // static batching de todo lo estático (terreno + props)
            StaticBatchingUtility.Combine(staticRoot.gameObject);
            yield return null;

            yield return BuildNavMesh();

            foreach (var e in encounters) e.SpawnAll();
            foreach (var b in bossSpawns) b.arena.SpawnBoss(b.pos, b.rot);
            Built = true;
        }

        void ParseManifest(TextAsset t)
        {
            specs.Clear();
            if (t == null) return;
            try
            {
                var m = JsonUtility.FromJson<Manifest>(t.text);
                if (m?.props != null) foreach (var p in m.props) specs[p.id] = p;
            }
            catch (Exception e) { Debug.LogWarning("[Nindo] Manifest de props inválido: " + e.Message); }
        }

        /// <summary>Cambia el material de follaje por la versión con viento (si su shader compiló).</summary>
        void ApplyFoliageWind(NindoContent c)
        {
            var from = c.foliageMaterial;
            var to = c.foliageWindMaterial;
            if (!c.useFoliageWind || from == null || to == null || to.shader == null || !to.shader.isSupported) return;
            int swapped = 0;
            foreach (var r in WorldRoot.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                bool any = false;
                for (int i = 0; i < mats.Length; i++) if (mats[i] == from) { mats[i] = to; any = true; }
                if (any) { r.sharedMaterials = mats; swapped++; }
            }
            Debug.Log($"[Nindo] Follaje con viento en {swapped} objetos.");
        }

        static int Phase(string n)
        {
            if (!n.StartsWith("M__")) return 0;
            if (n.StartsWith("M__BossArena") || n.StartsWith("M__Encounter") || n.StartsWith("M__Zone")) return 1;
            return 2;
        }

        void ProcessNode(Transform c)
        {
            string n = c.name;
            if (n.StartsWith("P__")) SpawnProp(c);
            else if (n.StartsWith("M__")) SpawnMarker(c);
            else if (n.StartsWith("T__")) SetupTerrain(c);
            else if (n.StartsWith("W__")) SetupWater(c);
            else if (n.StartsWith("B__")) SetupBoundary(c);
            else if (n.StartsWith("D__")) SetupDecor(c);
            else SetupTerrain(c);
        }

        static string[] Parts(string name)
        {
            int dot = name.IndexOf(" (");
            if (dot > 0) name = name.Substring(0, dot);
            return name.Split(new[] { "__" }, StringSplitOptions.None);
        }

        static float F(string s, float def = 0f) => float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out float v) ? v : def;

        // ------------------------------------------------------------------ terreno / agua
        void SetupTerrain(Transform t)
        {
            foreach (var mf in t.GetComponentsInChildren<MeshFilter>())
            {
                if (mf.GetComponent<Collider>() == null) mf.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                var r = mf.GetComponent<MeshRenderer>();
                if (r != null) { r.shadowCastingMode = ShadowCastingMode.On; r.receiveShadows = true; }
                mf.gameObject.isStatic = true;
            }
        }

        void SetupDecor(Transform t)
        {
            bool shadows = t.name.Contains("_sh_");   // arbustos sí proyectan sombra; pasto y flores no
            foreach (var r in t.GetComponentsInChildren<MeshRenderer>())
            {
                r.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.receiveShadows = true;
                r.gameObject.isStatic = true;
            }
        }

        void SetupWater(Transform t)
        {
            var c = Game.Content;
            Material mat = c != null ? c.waterMaterial : null;
            // agua animada si su shader compiló en esta versión de URP
            if (c != null && c.useAnimatedWater && c.waterAnimatedMaterial != null && c.waterAnimatedMaterial.shader != null && c.waterAnimatedMaterial.shader.isSupported)
                mat = c.waterAnimatedMaterial;
            foreach (var r in t.GetComponentsInChildren<MeshRenderer>())
            {
                r.shadowCastingMode = ShadowCastingMode.Off;
                if (mat != null) r.sharedMaterial = mat;
                int water = LayerMask.NameToLayer("Water");
                if (water >= 0) r.gameObject.layer = water;
            }
            t.SetParent(dynamicRoot, true); // el agua anima su material, no la batcheamos
        }

        void SetupBoundary(Transform t)
        {
            foreach (var mf in t.GetComponentsInChildren<MeshFilter>())
            {
                mf.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                var r = mf.GetComponent<MeshRenderer>();
                if (r != null) r.enabled = false;
                // son paredes verticales: en el NavMesh funcionan como obstáculo (los enemigos no salen del mapa)
            }
        }

        // ------------------------------------------------------------------ props
        void SpawnProp(Transform marker)
        {
            var parts = Parts(marker.name);
            if (parts.Length < 2) return;
            string id = parts[1];
            var model = Game.Content.Prop(id);
            if (model == null)
            {
                if (missing.Add(id)) Debug.LogWarning($"[Nindo] Falta el prop '{id}' en NindoContent.");
                return;
            }
            specs.TryGetValue(id, out var spec);
            bool floating = Array.IndexOf(FloatingProps, id) >= 0;
            bool nonStatic = floating || (spec != null && spec.tags != null && Array.IndexOf(spec.tags, "nonstatic") >= 0);
            var go = Instantiate(model, marker.position, marker.rotation, nonStatic ? dynamicRoot : staticRoot);
            Vector3 ms = marker.lossyScale;
            // la pasarela del lago se estira solo a lo largo: con escala uniforme la primera tabla quedaba
            // de 0.96 m de ancho y 0.38 m hundida respecto de la orilla (y el NavMesh se cortaba)
            if (id == "boardwalk_segment") ms = new Vector3(1f, 1f, ms.z);
            go.transform.localScale = Vector3.Scale(go.transform.localScale, ms);
            go.name = id;
            ApplySpec(go, spec, ms);
            if (floating)
            {
                foreach (var tr in go.GetComponentsInChildren<Transform>()) tr.gameObject.isStatic = false;
                go.AddComponent<FloatingBob>();
            }
            Destroy(marker.gameObject);
        }

        readonly HashSet<string> missing = new HashSet<string>();
        /// <summary>Props que flotan y se mecen con las olas del agua.</summary>
        static readonly string[] FloatingProps = { "boat_small" };

        GameObject InstantiateProp(string id, Vector3 pos, Quaternion rot, Transform parent, float scale = 1f)
        {
            var model = Game.Content.Prop(id);
            if (model == null) { if (missing.Add(id)) Debug.LogWarning($"[Nindo] Falta el prop '{id}'."); return null; }
            var go = Instantiate(model, pos, rot, parent);
            go.transform.localScale *= scale;
            go.name = id;
            specs.TryGetValue(id, out var spec);
            ApplySpec(go, spec, Vector3.one * scale);
            return go;
        }

        void ApplySpec(GameObject go, PropSpec spec, Vector3 scale)
        {
            if (spec == null) return;
            var col = spec.collider;
            if (col != null)
            {
                switch (col.type)
                {
                    case "box":
                        var b = go.AddComponent<BoxCollider>();
                        b.size = V(col.size, Vector3.one);
                        b.center = V(col.center, Vector3.zero);
                        break;
                    case "capsule":
                        var c = go.AddComponent<CapsuleCollider>();
                        c.radius = col.radius; c.height = col.height; c.center = V(col.center, Vector3.up * col.height * 0.5f);
                        break;
                    case "mesh":
                        foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
                            mf.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                        break;
                }
            }
            if (spec.tags == null) return;
            foreach (var tag in spec.tags)
            {
                switch (tag)
                {
                    case "occluder": go.AddComponent<Occluder>(); break;
                    case "light_warm": AddLight(go, spec, new Color(1f, 0.68f, 0.32f), 7f, 2.2f); break;
                    case "light_fire": AddLight(go, spec, new Color(1f, 0.5f, 0.2f), 8f, 2.8f); break;
                    case "light_cool": AddLight(go, spec, new Color(0.45f, 0.8f, 1f), 8f, 2.5f); break;
                    case "fireflies":
                        if (UnityEngine.Random.value < 0.35f) FXFactory.Fireflies(go.transform, new Vector3(4f, 1.5f, 4f) * Mathf.Max(1f, scale.x), 12);
                        break;
                    case "smoke":
                        var s = FXFactory.Smoke(go.transform, 0.6f);
                        s.transform.localPosition = spec.light_offset != null ? V(spec.light_offset, Vector3.up) : Vector3.up;
                        break;
                }
            }
            // lo que también tapa la pelea aunque el manifest no lo marque (acantilados, campana, bambú joven)
            if (Occluder.AlsoOccludes(spec.id) && go.GetComponent<Occluder>() == null) go.AddComponent<Occluder>();
            foreach (var t in go.GetComponentsInChildren<Transform>()) t.gameObject.isStatic = Array.IndexOf(spec.tags, "nonstatic") < 0;
        }

        void AddLight(GameObject go, PropSpec spec, Color c, float range, float intensity)
        {
            Vector3 off = spec.light_offset != null ? V(spec.light_offset, Vector3.up) : Vector3.up * 1.2f;
            lightPool.Add(go.transform.TransformPoint(off), c, range, intensity, go);
        }

        static Vector3 V(float[] a, Vector3 def) => a != null && a.Length >= 3 ? new Vector3(a[0], a[1], a[2]) : def;

        // ------------------------------------------------------------------ marcadores
        void SpawnMarker(Transform m)
        {
            var p = Parts(m.name);
            string type = p.Length > 1 ? p[1] : "";
            Vector3 pos = m.position;
            Quaternion rot = Quaternion.Euler(0f, m.eulerAngles.y, 0f);
            switch (type)
            {
                case "Start":
                    StartPoint = pos; StartRotation = rot;
                    break;
                case "Point":
                case "Camera":
                {
                    var t = new GameObject(m.name).transform;
                    t.SetParent(dynamicRoot, false); t.SetPositionAndRotation(pos, m.rotation);
                    points[p.Length > 2 ? p[2] : m.name] = t;
                    break;
                }
                case "Checkpoint":
                {
                    var go = InstantiateProp("shrine_checkpoint", pos, rot, dynamicRoot) ?? new GameObject("Shrine");
                    go.transform.SetPositionAndRotation(pos, rot);
                    var cp = go.AddComponent<Checkpoint>();
                    cp.id = p.Length > 2 ? p[2] : "cp";
                    cp.displayName = StoryText.CheckpointName(cp.id);
                    var lg = new GameObject("ShrineLight"); lg.transform.SetParent(go.transform, false); lg.transform.localPosition = new Vector3(0, 1.3f, 0.6f);
                    var l = lg.AddComponent<Light>(); l.type = LightType.Point; l.color = new Color(1f, 0.8f, 0.45f); l.range = 6f; l.intensity = 1.5f; l.shadows = LightShadows.None;
                    cp.Register();   // ya con su id y su luz (Awake corrió antes de asignarlos)
                    points[cp.id] = cp.transform;
                    break;
                }
                case "Encounter":
                {
                    var go = new GameObject("Encounter_" + (p.Length > 2 ? p[2] : "x"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.position = pos;
                    var e = go.AddComponent<Encounter>();
                    e.id = p.Length > 2 ? p[2] : "enc";
                    e.activationRadius = p.Length > 3 ? F(p[3], 12f) : 12f;
                    e.lockArea = p.Length > 4 && p[4] == "1";
                    e.onCompleteStory = "enc_done_" + e.id;
                    encounters.Add(e);
                    break;
                }
                case "Enemy":
                {
                    string arch = p.Length > 2 ? p[2] : "ninja";
                    string enc = p.Length > 3 ? p[3] : "";
                    var e = FindOrCreateEncounter(enc, pos);
                    e.AddSpawn(arch, pos, rot);
                    break;
                }
                case "BossArena":
                {
                    var go = new GameObject("BossArena_" + (p.Length > 2 ? p[2] : "boss"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.position = pos;
                    var a = go.AddComponent<BossArena>();
                    a.archetype = p.Length > 2 ? p[2] : "goro";
                    a.radius = p.Length > 3 ? F(p[3], 15f) : 15f;
                    a.triggerRadius = a.radius * 0.7f;
                    arenas.Add(a);
                    break;
                }
                case "Boss":
                {
                    string arch = p.Length > 2 ? p[2] : "goro";
                    BossArena arena = null;
                    foreach (var a in arenas) if (a.archetype == arch) arena = a;
                    if (arena == null)
                    {
                        var go = new GameObject("BossArena_" + arch);
                        go.transform.SetParent(dynamicRoot, false); go.transform.position = pos;
                        arena = go.AddComponent<BossArena>(); arena.archetype = arch; arenas.Add(arena);
                    }
                    bossSpawns.Add((arena, pos, rot));
                    break;
                }
                case "Zone":
                {
                    var go = new GameObject("Zone_" + (p.Length > 2 ? p[2] : "z"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.position = pos;
                    var z = go.AddComponent<Zone>();
                    z.id = p.Length > 2 ? p[2] : "zone";
                    z.radius = p.Length > 3 ? F(p[3], 40f) : 40f;
                    z.priority = p.Length > 4 ? (int)F(p[4], 0f) : 0;
                    StoryText.ConfigureZone(z);
                    break;
                }
                case "Trigger":
                {
                    var go = new GameObject("Trigger_" + (p.Length > 2 ? p[2] : "t"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.SetPositionAndRotation(pos, rot);
                    var t = go.AddComponent<StoryTrigger>();
                    t.id = p.Length > 2 ? p[2] : "t";
                    t.radius = p.Length > 3 ? F(p[3], 4f) : 4f;
                    points["trigger_" + t.id] = go.transform;
                    break;
                }
                case "Portal":
                {
                    var go = new GameObject("Portal_" + (p.Length > 2 ? p[2] : "p"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.SetPositionAndRotation(pos, rot);
                    var vis = InstantiateProp("portal_ring", pos, rot, go.transform);
                    if (vis != null) vis.transform.SetSiblingIndex(0);
                    var portal = go.AddComponent<Portal>();
                    portal.requiredFlag = p.Length > 3 ? p[3] : "";
                    portal.destinationCheckpoint = p.Length > 4 ? p[4] : "cp_dojo_gate";
                    // (la luz ya la pone el manifest del portal_ring; antes se sumaba una segunda igual)
                    break;
                }
                case "Door":
                {
                    // M__Door__flag__propId__angle  (el marcador está en la bisagra)
                    var pivot = new GameObject("Door_" + (p.Length > 3 ? p[3] : "door"));
                    pivot.transform.SetParent(dynamicRoot, false); pivot.transform.SetPositionAndRotation(pos, rot);
                    InstantiateProp(p.Length > 3 ? p[3] : "wall_gate_door", pos, rot, pivot.transform);
                    var d = pivot.AddComponent<GateDoor>();
                    d.openFlag = p.Length > 2 ? p[2] : "";
                    d.openAngle = p.Length > 4 ? F(p[4], 100f) : 100f;
                    d.Snap();
                    // la puerta no se hornea en el NavMesh (se hornea una sola vez): la tapa un obstáculo
                    // que GateDoor apaga al abrirse, así los enemigos pueden seguir a Kaito por el portón
                    pivot.AddComponent<NavMeshExclude>();
                    var obs = pivot.AddComponent<NavMeshObstacle>();
                    obs.shape = NavMeshObstacleShape.Box; obs.carving = true;
                    if (specs.TryGetValue(p.Length > 3 ? p[3] : "wall_gate_door", out var ds) && ds.collider != null)
                    {
                        obs.center = V(ds.collider.center, Vector3.zero);
                        obs.size = V(ds.collider.size, Vector3.one);
                    }
                    obs.enabled = !d.IsOpen;
                    break;
                }
                case "Barrier":
                {
                    // M__Barrier__flag__width
                    var go = new GameObject("Barrier_" + (p.Length > 2 ? p[2] : "b"));
                    go.transform.SetParent(dynamicRoot, false); go.transform.SetPositionAndRotation(pos, rot);
                    float w = p.Length > 3 ? F(p[3], 3f) : 3f;
                    // estirar solo a lo ancho (con escala uniforme la cuerda quedaba de 3.4 m de alto)
                    var vis = InstantiateProp("rope_barrier", pos, rot, go.transform);
                    if (vis != null) vis.transform.localScale = Vector3.Scale(vis.transform.localScale, new Vector3(w / 3f, 1f, 1f));
                    var col = go.AddComponent<BoxCollider>(); col.size = new Vector3(w, 3f, 0.6f); col.center = new Vector3(0, 1.5f, 0);
                    // igual que las puertas: fuera del horneado y tapada por un obstáculo que se apaga con el flag
                    go.AddComponent<NavMeshExclude>();
                    var bo = go.AddComponent<NavMeshObstacle>();
                    bo.shape = NavMeshObstacleShape.Box; bo.carving = true; bo.center = col.center; bo.size = col.size;
                    var fb = go.AddComponent<FlagBarrier>(); fb.removeFlag = p.Length > 2 ? p[2] : "";
                    break;
                }
                case "NPC":
                {
                    var npc = NPC.Spawn(p.Length > 2 ? p[2] : "grandpa", pos, rot, dynamicRoot);
                    points["npc_" + (p.Length > 2 ? p[2] : "grandpa") + (p.Length > 3 ? "_" + p[3] : "")] = npc.transform;
                    break;
                }
                case "Fireflies":
                {
                    var go = new GameObject("Fireflies"); go.transform.SetParent(dynamicRoot, false); go.transform.position = pos + Vector3.up;
                    FXFactory.Fireflies(go.transform, new Vector3(p.Length > 2 ? F(p[2], 10f) : 10f, 2.5f, p.Length > 3 ? F(p[3], 10f) : 10f), 30);
                    break;
                }
                case "Light":
                {
                    Color c = p.Length > 2 && ColorUtility.TryParseHtmlString("#" + p[2], out var cc) ? cc : new Color(1f, 0.7f, 0.35f);
                    lightPool.Add(pos, c, p.Length > 3 ? F(p[3], 8f) : 8f, p.Length > 4 ? F(p[4], 2f) : 2f);
                    break;
                }
                case "SealGate":
                {
                    var go = new GameObject("SealGate"); go.transform.SetParent(dynamicRoot, false); go.transform.SetPositionAndRotation(pos, rot);
                    go.AddComponent<SealGate>();
                    points["seal_gate"] = go.transform;
                    break;
                }
            }
            Destroy(m.gameObject);
        }

        Encounter FindOrCreateEncounter(string id, Vector3 pos)
        {
            if (string.IsNullOrEmpty(id)) id = "solo_" + encounters.Count;
            foreach (var e in encounters) if (e.id == id) return e;
            var go = new GameObject("Encounter_" + id);
            go.transform.SetParent(dynamicRoot, false); go.transform.position = pos;
            var enc = go.AddComponent<Encounter>();
            enc.id = id; enc.activationRadius = 11f; enc.onCompleteStory = "enc_done_" + id;
            encounters.Add(enc);
            return enc;
        }

        // ================================================================== NavMesh
        IEnumerator BuildNavMesh()
        {
            var sources = new List<NavMeshBuildSource>();
            var markups = new List<NavMeshBuildMarkup>();
            foreach (var ex in WorldRoot.GetComponentsInChildren<NavMeshExclude>())
                markups.Add(new NavMeshBuildMarkup { root = ex.transform, overrideIgnore = true, ignoreFromBuild = true, applyToChildren = true });
            int mask = LayerMask.GetMask("Default");
            NavMeshBuilder.CollectSources(WorldRoot, mask, NavMeshCollectGeometry.PhysicsColliders, 0, markups, sources);
            var bounds = new Bounds(Vector3.zero, Vector3.one * 2000f);
            var settings = NavMesh.GetSettingsByID(0);
            settings.agentRadius = 0.45f;
            settings.agentHeight = 1.8f;
            settings.agentClimb = 0.5f;
            settings.agentSlope = 42f;
            settings.minRegionArea = 4f;
            settings.overrideVoxelSize = true;
            settings.voxelSize = 0.2f;        // mapa grande: voxels algo más gruesos = build mucho más rápido
            var data = new NavMeshData(0);
            navInstance = NavMesh.AddNavMeshData(data);
            var op = NavMeshBuilder.UpdateNavMeshDataAsync(data, settings, sources, bounds);
            while (op != null && !op.isDone) yield return null;
        }

        // ================================================================== atmósfera
        public void SetupLighting()
        {
            var c = Game.Content;
            if (c != null && c.skyboxMaterial != null) RenderSettings.skybox = c.skyboxMaterial;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.22f, 0.28f, 0.42f);
            RenderSettings.ambientEquatorColor = new Color(0.12f, 0.15f, 0.22f);
            RenderSettings.ambientGroundColor = new Color(0.05f, 0.05f, 0.07f);
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = new Color(0.07f, 0.1f, 0.17f);
            RenderSettings.fogDensity = 0.012f;

            Light moon = null;
            foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None))
                if (l.type == LightType.Directional) { moon = l; break; }
            if (moon == null) moon = new GameObject("Luna").AddComponent<Light>();
            moon.type = LightType.Directional;
            moon.color = new Color(0.62f, 0.72f, 1f);
            moon.intensity = 1.05f;
            moon.shadows = LightShadows.Soft;
            moon.shadowStrength = 0.85f;
            moon.transform.rotation = Quaternion.Euler(48f, -38f, 0f);
            RenderSettings.sun = moon;
        }

        public static void SetAtmosphere(Color fog, float density, Color ambient, bool snowOn)
        {
            if (Game.World != null) Game.World.StartCoroutine(Game.World.Atmosphere(fog, density, ambient, snowOn));
        }

        IEnumerator Atmosphere(Color fog, float density, Color ambient, bool snowOn)
        {
            Color f0 = RenderSettings.fogColor, a0 = RenderSettings.ambientSkyColor;
            float d0 = RenderSettings.fogDensity;
            float t = 0f;
            SetSnow(snowOn);
            while (t < 2.5f)
            {
                t += Time.unscaledDeltaTime;
                float k = Mathf.SmoothStep(0f, 1f, t / 2.5f);
                RenderSettings.fogColor = Color.Lerp(f0, fog, k);
                RenderSettings.fogDensity = Mathf.Lerp(d0, density, k);
                RenderSettings.ambientSkyColor = Color.Lerp(a0, ambient, k);
                yield return null;
            }
        }

        void SetSnow(bool on)
        {
            if (on && snow == null)
            {
                snow = FXFactory.NewSystem("Snow", transform);
                var m = snow.main;
                m.loop = true; m.duration = 5f; m.startLifetime = 6f; m.startSpeed = 0.4f; m.startSize = new ParticleSystem.MinMaxCurve(0.04f, 0.1f);
                m.startColor = new Color(0.9f, 0.95f, 1f, 0.9f); m.gravityModifier = 0.05f; m.maxParticles = 600; m.prewarm = true;
                var em = snow.emission; em.rateOverTime = 90f;
                var sh = snow.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(40f, 1f, 30f);
                var noise = snow.noise; noise.enabled = true; noise.strength = 0.4f; noise.frequency = 0.2f;
                snow.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
                snow.Play();
            }
            if (snow != null) { if (on) snow.Play(); else snow.Stop(); }
        }

        void Update()
        {
            if (!Built || Game.Player == null) return;
            zoneTimer -= Time.unscaledDeltaTime;
            if (zoneTimer <= 0f) { zoneTimer = 0.25f; Zone.Tick(Game.Player.transform.position); }
            if (snow != null && snow.isPlaying) snow.transform.position = Game.Player.transform.position + Vector3.up * 14f;
        }

        // ================================================================== respawn
        public void ResetAfterDeath()
        {
            Encounter.ResetAllIncomplete();
            foreach (var a in arenas) a.OnPlayerDied();
        }
    }

    /// <summary>Marca objetos que no deben formar parte del NavMesh.</summary>
    public class NavMeshExclude : MonoBehaviour { }
}
