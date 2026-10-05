using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Zona del mapa (Hogar, Campos de Inaba, Jardín del Clan, Montaña Kodoyama...): al entrar
    /// muestra el título, cambia música/ambiente, niebla y (opcional) el ángulo de cámara.
    /// </summary>
    public class Zone : MonoBehaviour
    {
        public string id = "zone";
        public string title = "Zona";
        public string subtitle = "";
        public float radius = 40f;
        public int priority;
        public string music = "explore";
        public string ambience = "night";
        public Color fogColor = new Color(0.07f, 0.1f, 0.17f);
        public float fogDensity = 0.012f;
        public Color ambientSky = new Color(0.22f, 0.28f, 0.42f);
        public float cameraYaw;
        public float cameraPitchOffset;
        public float cameraDistanceOffset;
        public bool snow;

        static readonly List<Zone> zones = new List<Zone>();
        public static Zone Current { get; private set; }

        void OnEnable() => zones.Add(this);
        void OnDisable() => zones.Remove(this);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetList() { zones.Clear(); Current = null; }

        public bool Contains(Vector3 p) => CombatMath.FlatDistance(p, transform.position) <= radius;

        /// <summary>Llamado por WorldBuilder ~4 veces por segundo.</summary>
        public static void Tick(Vector3 playerPos)
        {
            Zone best = null;
            foreach (var z in zones)
            {
                if (!z.Contains(playerPos)) continue;
                if (best == null || z.priority > best.priority || (z.priority == best.priority && z.radius < best.radius)) best = z;
            }
            if (best != null && best != Current) Enter(best);
        }

        static void Enter(Zone z)
        {
            Current = z;
            Game.Audio?.SetExploreMusic(z.music, z.ambience);
            Game.Camera?.SetZoneOverride(z.cameraYaw, z.cameraPitchOffset, z.cameraDistanceOffset);
            WorldBuilder.SetAtmosphere(z.fogColor, z.fogDensity, z.ambientSky, z.snow);
            string flag = "zone_" + z.id;
            if (!Game.Save.HasFlag(flag) && !Game.InCutscene)
            {
                Game.Save.SetFlag(flag);
                Game.UI?.ShowAreaTitle(z.title, z.subtitle);
            }
            GameEvents.RaiseZoneEntered(z);
        }

        public static void ForceRefresh() => Current = null;
    }

    /// <summary>
    /// Grupo de enemigos que pelean juntos. Se completa cuando mueren todos (queda guardado).
    /// Si Kaito muere, los enemigos del encuentro vuelven a su lugar con vida completa.
    /// </summary>
    public class Encounter : MonoBehaviour
    {
        public string id = "enc";
        public float activationRadius = 12f;
        [Tooltip("Cierra el área con cuerdas sagradas mientras dura la pelea")] public bool lockArea;
        public string rewardFlag = "";
        public string onCompleteStory = "";
        [Tooltip("Solo lo activa la historia (no por proximidad)")] public bool manualActivation;
        readonly List<Enemy> members = new List<Enemy>();
        readonly List<(string archetype, Vector3 pos, Quaternion rot)> spawns = new List<(string, Vector3, Quaternion)>();
        bool active, completed;
        GameObject barrier;
        static readonly List<Encounter> all = new List<Encounter>();

        public bool Completed => completed;
        public IReadOnlyList<Enemy> Members => members;

        void OnEnable() => all.Add(this);
        void OnDisable() => all.Remove(this);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetList() => all.Clear();

        public static Encounter Get(string id)
        {
            foreach (var e in all) if (e.id == id) return e;
            return null;
        }

        public void AddSpawn(string archetype, Vector3 pos, Quaternion rot) => spawns.Add((archetype, pos, rot));

        /// <summary>Crea los enemigos (después de construir el NavMesh).</summary>
        public void SpawnAll()
        {
            completed = Game.Save.HasFlag(Flags.Encounter(id));
            if (completed) return;
            foreach (var s in spawns)
            {
                var e = EnemyFactory.Spawn(s.archetype, s.pos, s.rot, this);
                e.transform.SetParent(transform, true);
                members.Add(e);
            }
        }

        void Update()
        {
            if (completed || Game.Player == null || manualActivation) return;
            if (!active && CombatMath.FlatDistance(Game.Player.transform.position, transform.position) < activationRadius && !Game.InCutscene)
                Activate();
        }

        public void Activate()
        {
            if (active || completed) return;
            active = true;
            foreach (var m in members) if (m != null && m.IsAlive && !(m is Boss)) m.Alert();
            if (lockArea && barrier == null) barrier = ArenaBarrier.Create(transform.position, activationRadius + 3f, "Barrier_" + id);
        }

        public void OnMemberAlerted(Enemy e)
        {
            if (!active) Activate();
        }

        public void OnMemberDied(Enemy e)
        {
            foreach (var m in members) if (m != null && m.IsAlive) return;
            Complete();
        }

        void Complete()
        {
            if (completed) return;
            completed = true;
            active = false;
            Game.Save.SetFlag(Flags.Encounter(id));
            if (!string.IsNullOrEmpty(rewardFlag)) Game.Save.SetFlag(rewardFlag);
            if (barrier != null) { ArenaBarrier.Dissolve(barrier); barrier = null; }
            if (members.Count > 1) Game.UI?.ShowToast("Victoria", UIFactory.Gold, 1.2f);
            if (!string.IsNullOrEmpty(onCompleteStory)) Game.Story?.OnTrigger(onCompleteStory, null);
        }

        public void ResetEncounter()
        {
            // los encuentros que solo arranca la historia (prólogo) no se tocan antes de empezar: rezar en el
            // santuario liberaba al ninja congelado mientras Kaito todavía no tiene katana
            if (completed || (manualActivation && !active)) return;
            active = false;
            if (barrier != null) { Destroy(barrier); barrier = null; }
            foreach (var m in members) if (m != null) m.ResetEnemy();
        }

        public static void ResetAllIncomplete()
        {
            foreach (var e in all) e.ResetEncounter();
        }
    }

    /// <summary>Arena de jefe: al entrar, presentación cinemática y pelea con el área cerrada.</summary>
    public class BossArena : MonoBehaviour
    {
        public string archetype = "goro";
        public float radius = 15f;
        public float triggerRadius = 10f;
        public Boss Boss { get; private set; }
        GameObject barrier;
        bool started;

        public void SpawnBoss(Vector3 pos, Quaternion rot)
        {
            if (Game.Save.HasFlag(Flags.Boss(archetype)))
            {
                // El jefe marca su flag al morir, pero el sello recién aparece segundos después
                // (Boss.OnDeathFinished). Si se salió al menú o se cerró el juego antes de tomarlo,
                // el guardado queda con el jefe vencido y sin sello: lo volvemos a dejar en la arena
                // (si no, la puerta del dojo, que pide los tres sellos, no se abriría nunca).
                if (EnemyFactory.BossSeal(archetype, out var seal) && !Game.Save.HasSeal(seal))
                {
                    Vector3 p = UnityEngine.AI.NavMesh.SamplePosition(pos, out var hit, 4f, UnityEngine.AI.NavMesh.AllAreas) ? hit.position : pos;
                    var key = KeyPickup.Spawn(seal, p + Vector3.up * 0.2f);
                    key.transform.SetParent(transform, true);
                }
                return;
            }
            Boss = EnemyFactory.Spawn(archetype, pos, rot, null) as Boss;
            if (Boss != null)
            {
                Boss.transform.SetParent(transform, true);
                Boss.arenaCenter = transform.position;
                Boss.arenaRadius = radius - 1f;
            }
        }

        void Update()
        {
            if (Boss == null || Boss.Defeated || started || Game.Player == null || Game.InCutscene) return;
            if (CombatMath.FlatDistance(Game.Player.transform.position, transform.position) < triggerRadius)
            {
                started = true;
                barrier = ArenaBarrier.Create(transform.position, radius, "BossBarrier");
                Game.Story?.BossIntro(this);
            }
        }

        public void OnPlayerDied()
        {
            if (Boss == null || Boss.Defeated) return;
            started = false;
            if (barrier != null) { Destroy(barrier); barrier = null; }
            Boss.ResetEnemy();
        }

        public void OnBossDefeated()
        {
            if (barrier != null) { ArenaBarrier.Dissolve(barrier); barrier = null; }
        }
    }

    /// <summary>Muro circular de cuerdas sagradas (shimenawa) con colisión, para cerrar arenas.</summary>
    public static class ArenaBarrier
    {
        public static GameObject Create(Vector3 center, float radius, string name)
        {
            var root = new GameObject(name);
            root.transform.position = center;
            int n = Mathf.Clamp(Mathf.RoundToInt(radius * 2f * Mathf.PI / 3f), 10, 48);
            var mat = FXMaterials.MakeUnlitTransparent("BarrierGlow", new Color(1f, 0.75f, 0.35f, 0.35f), true);
            for (int i = 0; i < n; i++)
            {
                float a0 = i / (float)n * Mathf.PI * 2f, a1 = (i + 1) / (float)n * Mathf.PI * 2f;
                Vector3 p0 = new Vector3(Mathf.Cos(a0), 0, Mathf.Sin(a0)) * radius;
                Vector3 p1 = new Vector3(Mathf.Cos(a1), 0, Mathf.Sin(a1)) * radius;
                var seg = new GameObject("Seg" + i);
                seg.transform.SetParent(root.transform, false);
                seg.transform.localPosition = (p0 + p1) * 0.5f + Vector3.up * 1.5f;
                seg.transform.localRotation = Quaternion.LookRotation(p1 - p0);
                var col = seg.AddComponent<BoxCollider>();
                col.size = new Vector3(0.3f, 3f, (p1 - p0).magnitude + 0.2f);
                // cortina de luz tenue
                var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
                Object.Destroy(q.GetComponent<Collider>());
                q.transform.SetParent(seg.transform, false);
                q.transform.localRotation = Quaternion.Euler(0, 90, 0);
                q.transform.localScale = new Vector3((p1 - p0).magnitude, 2.2f, 1f);
                q.transform.localPosition = new Vector3(0, -0.4f, 0);
                var r = q.GetComponent<MeshRenderer>();
                r.sharedMaterial = mat;
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            }
            Game.FX?.Shockwave(center, radius, new Color(1f, 0.8f, 0.4f));
            Game.Audio?.Play("barrier", center, 0.8f);
            return root;
        }

        public static void Dissolve(GameObject barrier)
        {
            if (barrier == null) return;
            Game.FX?.Shockwave(barrier.transform.position, 6f, new Color(1f, 0.9f, 0.6f));
            Object.Destroy(barrier);
        }
    }

    /// <summary>
    /// Muchos faroles, pocas luces reales: solo las N más cercanas a Kaito están encendidas
    /// (el resto brilla igual por el material emisivo + bloom). Clave para el rendimiento.
    /// </summary>
    public class LightPool : MonoBehaviour
    {
        public int maxLights = 10;
        // owner: si el prop dueño de la luz está oculto (portal antes de vencer al jefe), la luz no se usa
        struct Anchor { public Vector3 pos; public Color color; public float range, intensity; public GameObject owner; public bool hasOwner; }
        readonly List<Anchor> anchors = new List<Anchor>();
        Light[] lights;
        readonly List<int> order = new List<int>();
        float timer;

        void Awake()
        {
            lights = new Light[maxLights];
            for (int i = 0; i < maxLights; i++)
            {
                var go = new GameObject("PooledLight" + i);
                go.transform.SetParent(transform, false);
                var l = go.AddComponent<Light>();
                l.type = LightType.Point; l.shadows = LightShadows.None; l.enabled = false;
                l.renderMode = LightRenderMode.ForcePixel;
                lights[i] = l;
            }
        }

        public void Add(Vector3 pos, Color c, float range, float intensity, GameObject owner = null)
        {
            anchors.Add(new Anchor { pos = pos, color = c, range = range, intensity = intensity, owner = owner, hasOwner = owner != null });
        }

        void Update()
        {
            timer -= Time.unscaledDeltaTime;
            if (timer > 0f || Game.Player == null) return;
            timer = 0.25f;
            Vector3 p = Game.Player.transform.position;
            order.Clear();
            for (int i = 0; i < anchors.Count; i++)
                if ((!anchors[i].hasOwner || (anchors[i].owner != null && anchors[i].owner.activeInHierarchy)) && (anchors[i].pos - p).sqrMagnitude < 45f * 45f) order.Add(i);
            order.Sort((a, b) => (anchors[a].pos - p).sqrMagnitude.CompareTo((anchors[b].pos - p).sqrMagnitude));
            for (int i = 0; i < lights.Length; i++)
            {
                if (i < order.Count)
                {
                    var a = anchors[order[i]];
                    lights[i].transform.position = a.pos;
                    lights[i].color = a.color; lights[i].range = a.range; lights[i].intensity = a.intensity;
                    lights[i].enabled = true;
                }
                else lights[i].enabled = false;
            }
            // parpadeo suave de fuego
            for (int i = 0; i < lights.Length && i < order.Count; i++)
                lights[i].intensity *= 0.92f + 0.08f * Mathf.PerlinNoise(Time.time * 4f, i);
        }
    }
}
