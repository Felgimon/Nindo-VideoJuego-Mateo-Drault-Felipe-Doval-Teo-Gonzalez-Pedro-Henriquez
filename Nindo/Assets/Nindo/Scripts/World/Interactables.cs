using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>Base de todo lo que Kaito puede usar con [E].</summary>
    public abstract class Interactable : MonoBehaviour
    {
        public string prompt = "Interactuar";
        public float radius = 2.2f;
        public float promptHeight = 2f;
        static readonly List<Interactable> all = new List<Interactable>();

        public virtual Vector3 PromptPosition => transform.position + Vector3.up * promptHeight;
        public virtual bool CanInteract => true;

        protected virtual void OnEnable() { all.Add(this); }
        protected virtual void OnDisable() { all.Remove(this); }

        public abstract void Interact(PlayerController p);

        public static Interactable FindBest(Vector3 pos, Vector3 forward)
        {
            Interactable best = null; float bestScore = float.MaxValue;
            for (int i = 0; i < all.Count; i++)
            {
                var it = all[i];
                if (it == null || !it.CanInteract) continue;
                float d = CombatMath.FlatDistance(it.transform.position, pos);
                if (d > it.radius || Mathf.Abs(it.transform.position.y - pos.y) > 3f) continue;
                float score = d - Vector3.Dot(forward, (it.transform.position - pos).Flat().normalized) * 0.5f;
                if (score < bestScore) { bestScore = score; best = it; }
            }
            return best;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetList() => all.Clear();
    }

    /// <summary>Santuario: guarda la partida, cura y es el punto de reaparición.</summary>
    public class Checkpoint : Interactable
    {
        public string id = "cp";
        public string displayName = "Santuario";
        public Transform spawnPoint;
        static readonly Dictionary<string, Checkpoint> byId = new Dictionary<string, Checkpoint>();
        Light glow;
        bool activated;
        string registeredId;   // id con el que quedó en byId (puede diferir de "id" si se cambió después)

        void Awake()
        {
            prompt = "Rezar en el santuario";
            if (spawnPoint == null)
            {
                spawnPoint = new GameObject("Spawn").transform;
                spawnPoint.SetParent(transform, false);
                spawnPoint.localPosition = new Vector3(0f, 0.1f, 1.8f);
                spawnPoint.localRotation = Quaternion.Euler(0, 180, 0);
            }
        }

        // por si alguien lo crea sin llamar a Register (idempotente)
        void Start() => Register();

        /// <summary>
        /// Registra el santuario con su id actual y busca su luz. Awake corre dentro de AddComponent,
        /// antes de que WorldBuilder asigne el id y agregue la "ShrineLight": por eso se llama
        /// explícitamente después de configurarlo (y Checkpoint.Get funciona ya durante la construcción).
        /// </summary>
        public void Register()
        {
            if (registeredId != id)
            {
                Unregister();
                if (!string.IsNullOrEmpty(id)) { byId[id] = this; registeredId = id; }
            }
            if (glow == null) glow = GetComponentInChildren<Light>();
        }

        void Unregister()
        {
            if (registeredId != null && byId.TryGetValue(registeredId, out var c) && c == this) byId.Remove(registeredId);
            registeredId = null;
        }

        void OnDestroy() => Unregister();

        public static Checkpoint Get(string id) => id != null && byId.TryGetValue(id, out var c) ? c : null;

        // no se reza en combate: curaba todo y reiniciaba los encuentros en plena pelea
        // (cp_dojo está adentro de la arena de Kage)
        public override bool CanInteract => Game.Combat == null || !Game.Combat.InCombat;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetDict() => byId.Clear();

        public override void Interact(PlayerController p)
        {
            Activate(p, true);
        }

        public void Activate(PlayerController p, bool fromPlayer)
        {
            bool first = Game.Save.checkpoint != id;
            Game.Save.checkpoint = id;
            SaveSystem.Save();
            if (p != null) p.RestoreAll();
            Game.FX?.SealGlow(transform.position + Vector3.up);
            Game.Audio?.Play("checkpoint", transform.position, 0.9f);
            if (fromPlayer) Game.UI?.ShowToast(first ? $"{displayName} — partida guardada" : "Vida restaurada", UIFactory.Gold);
            // reaparecen los enemigos de encuentros no completados (como en un souls, pero suave)
            if (fromPlayer) Encounter.ResetAllIncomplete();
            GameEvents.RaiseCheckpoint(id);
            activated = true;
        }

        void Update()
        {
            if (glow != null) glow.intensity = (Game.Save.checkpoint == id ? 2.4f : 1.2f) * (0.9f + 0.1f * Mathf.Sin(Time.time * 3f));
        }
    }

    /// <summary>Uno de los tres sellos/llaves que custodian los jefes.</summary>
    public class KeyPickup : Interactable
    {
        public SealId seal;
        Transform visual;
        float baseY;

        public static KeyPickup Spawn(SealId seal, Vector3 pos)
        {
            string prop = seal == SealId.Montana ? "key_seal_mountain" : seal == SealId.Lago ? "key_seal_lake" : "key_seal_bamboo";
            var go = new GameObject("Sello_" + seal);
            go.transform.position = pos;
            var model = Game.Content != null ? Game.Content.Prop(prop) : null;
            Transform vis;
            if (model != null) vis = Instantiate(model, go.transform).transform;
            else { vis = GameObject.CreatePrimitive(PrimitiveType.Cylinder).transform; vis.SetParent(go.transform, false); vis.localScale = new Vector3(0.5f, 0.05f, 0.5f); vis.localRotation = Quaternion.Euler(90, 0, 0); Destroy(vis.GetComponent<Collider>()); }
            vis.localPosition = Vector3.up * 1.1f;
            var l = new GameObject("Glow").AddComponent<Light>();
            l.transform.SetParent(go.transform, false); l.transform.localPosition = Vector3.up * 1.2f;
            l.type = LightType.Point; l.color = new Color(1f, 0.85f, 0.45f); l.range = 5f; l.intensity = 3f; l.shadows = LightShadows.None;
            var k = go.AddComponent<KeyPickup>();
            k.seal = seal; k.visual = vis; k.baseY = 1.1f;
            k.prompt = "Tomar el sello";
            Game.FX?.SealGlow(pos + Vector3.up);
            return k;
        }

        void Update()
        {
            if (visual == null) return;
            visual.localPosition = new Vector3(0f, baseY + Mathf.Sin(Time.time * 2f) * 0.12f, 0f);
            visual.localRotation = Quaternion.Euler(0f, Time.time * 60f, 0f);
        }

        public override void Interact(PlayerController p)
        {
            Game.Save.seals[(int)seal] = true;
            SaveSystem.Save();
            GameEvents.RaiseSeal(seal);
            Game.FX?.SealGlow(transform.position + Vector3.up);
            Game.Audio?.Play("seal", transform.position, 1f);
            Game.Story?.OnSealObtained(seal);
            Destroy(gameObject);
        }
    }

    /// <summary>Portal que lleva de vuelta a la puerta del dojo.</summary>
    public class Portal : Interactable
    {
        public string requiredFlag = "";
        public string destinationCheckpoint = "cp_dojo_gate";
        Transform visual;

        void Awake()
        {
            prompt = "Viajar a la puerta del dojo";
            promptHeight = 2.4f;
            visual = transform.childCount > 0 ? transform.GetChild(0) : null;
        }

        bool Unlocked => string.IsNullOrEmpty(requiredFlag) || Game.Save.HasFlag(requiredFlag);
        // visible apenas se desbloquea, pero no se viaja en plena pelea
        public override bool CanInteract => Unlocked && (Game.Combat == null || !Game.Combat.InCombat);

        void Update()
        {
            bool on = Unlocked;
            if (visual != null && visual.gameObject.activeSelf != on)
            {
                visual.gameObject.SetActive(on);
                if (on) Game.FX?.PortalBurst(transform.position + Vector3.up * 1.8f);
            }
        }

        public override void Interact(PlayerController p) => Game.Story?.TravelTo(destinationCheckpoint, true);
    }

    /// <summary>Habla con un personaje (abuelo, aldeanos).</summary>
    public class TalkInteractable : Interactable
    {
        public string dialogueId;
        public override void Interact(PlayerController p) => Game.Story?.PlayDialogueById(dialogueId);
    }

    /// <summary>Puerta/portón que se abre al cumplirse un flag (gira sobre la bisagra).</summary>
    public class GateDoor : MonoBehaviour
    {
        public string openFlag;
        public float openAngle = 100f;
        public float speed = 60f;
        Quaternion closed;
        float angle;
        Collider[] cols;
        UnityEngine.AI.NavMeshObstacle obstacle;

        void Awake()
        {
            closed = transform.localRotation;
            cols = GetComponentsInChildren<Collider>();
        }

        public bool IsOpen => !string.IsNullOrEmpty(openFlag) && Game.Save.HasFlag(openFlag);

        void Update()
        {
            float target = IsOpen ? openAngle : 0f;
            if (Mathf.Approximately(angle, target)) return;
            bool wasClosed = Mathf.Approximately(angle, 0f);
            angle = Mathf.MoveTowards(angle, target, speed * Time.deltaTime);
            transform.localRotation = closed * Quaternion.Euler(0f, angle, 0f);
            if (wasClosed && IsOpen) Game.Audio?.Play("gate_open", transform.position, 1f);
            foreach (var c in cols) c.enabled = !IsOpen || Mathf.Abs(angle) < 20f;
            if (obstacle == null) obstacle = GetComponent<UnityEngine.AI.NavMeshObstacle>();   // lo agrega WorldBuilder después de Awake
            if (obstacle != null) obstacle.enabled = !IsOpen || Mathf.Abs(angle) < 20f;
        }

        public void Snap()
        {
            angle = IsOpen ? openAngle : 0f;
            transform.localRotation = closed * Quaternion.Euler(0f, angle, 0f);
        }
    }

    /// <summary>Barrera (cuerda sagrada) que bloquea un camino hasta que se cumple un flag.</summary>
    public class FlagBarrier : MonoBehaviour
    {
        public string removeFlag;
        public bool invert;   // visible SOLO si el flag está puesto
        bool shown;

        bool ShouldShow
        {
            get
            {
                bool has = !string.IsNullOrEmpty(removeFlag) && Game.Save.HasFlag(removeFlag);
                return invert ? has : !has;
            }
        }

        // estado inicial según la partida, sin humo (al cargar no tiene que "desaparecer" de nuevo)
        void Start() => Apply(ShouldShow);

        void Update()
        {
            bool visible = ShouldShow;
            if (visible == shown) return;
            // solo en la transición visible -> oculta (el GameObject propio sigue activo: se ocultan los hijos)
            if (!visible) Game.FX?.SmokePuff(transform.position + Vector3.up, 1.5f);
            Apply(visible);
        }

        void Apply(bool visible)
        {
            shown = visible;
            foreach (Transform c in transform) c.gameObject.SetActive(visible);
            foreach (var col in GetComponents<Collider>()) col.enabled = visible;
            foreach (var o in GetComponents<UnityEngine.AI.NavMeshObstacle>()) o.enabled = visible;
        }
    }

    /// <summary>Volumen que dispara un evento de historia la primera vez que Kaito entra.</summary>
    public class StoryTrigger : MonoBehaviour
    {
        public string id;
        public float radius = 4f;
        public string requiredFlag = "";
        bool fired;

        void Update()
        {
            if (fired || Game.Player == null || Game.InCutscene) return;
            if (Game.Save.HasFlag("trig_" + id)) { fired = true; return; }
            if (!string.IsNullOrEmpty(requiredFlag) && !Game.Save.HasFlag(requiredFlag)) return;
            if (CombatMath.FlatDistance(Game.Player.transform.position, transform.position) <= radius &&
                Mathf.Abs(Game.Player.transform.position.y - transform.position.y) < 5f)
            {
                fired = true;
                GameEvents.RaiseStoryTrigger(id);
                Game.Story?.OnTrigger(id, this);
            }
        }

        public void Rearm() => fired = false;
    }
}
