using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

namespace Nindo
{
    /// <summary>
    /// Arma personajes en runtime a partir de NindoContent: instancia el modelo (FBX del equipo),
    /// le pone su AnimatorController, lo escala a la altura correcta midiendo sus bounds,
    /// agrega colliders/agentes y los componentes de gameplay. Así no dependemos de prefabs
    /// frágiles con referencias rotas.
    /// </summary>
    public static class CharacterFactory
    {
        static readonly Dictionary<string, Material[]> tintCache = new Dictionary<string, Material[]>();
        static readonly Dictionary<Material, Material> liftCache = new Dictionary<Material, Material>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { tintCache.Clear(); liftCache.Clear(); }

        /// <summary>Piso de brillo (canal más alto, sRGB) del color base de los personajes. Los trajes del
        /// equipo usan negro puro o casi (Negro = 0,0,0; GrisOscuro = 0.04): de noche no reciben luz y desde
        /// la cámara alta se ven como siluetas planas. Con este piso siguen leyéndose negros pero toman el
        /// sombreado de la luna y las antorchas.</summary>
        public const float BlackFloor = 0.13f;

        static void LiftBlacks(GameObject inst)
        {
            foreach (var r in inst.GetComponentsInChildren<Renderer>(true))
            {
                if (r is ParticleSystemRenderer) continue;
                var mats = r.sharedMaterials;
                bool changed = false;
                for (int i = 0; i < mats.Length; i++)
                {
                    var m = mats[i];
                    if (m == null || !m.HasProperty("_BaseColor")) continue;
                    if (!liftCache.TryGetValue(m, out var lifted))
                    {
                        lifted = m;
                        Color c = m.GetColor("_BaseColor");
                        bool textured = m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") != null;
                        float max = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
                        if (!textured && max < BlackFloor)
                        {
                            // conserva el matiz; el negro puro pasa a un carbón apenas azulado (luz de luna)
                            Color hue = max > 0.005f ? c / max : new Color(0.85f, 0.9f, 1f);
                            Color nc = hue * BlackFloor; nc.a = c.a;
                            lifted = new Material(m) { name = m.name + "_lift" };
                            lifted.SetColor("_BaseColor", nc);
                            if (lifted.HasProperty("_Color")) lifted.SetColor("_Color", nc);
                        }
                        liftCache[m] = lifted;
                    }
                    if (lifted != m) { mats[i] = lifted; changed = true; }
                }
                if (changed) r.sharedMaterials = mats;
            }
        }

        /// <summary>Instancia el modelo de un personaje como hijo de 'parent'.</summary>
        public static Animator BuildModel(string characterId, Transform parent, float scaleMul = 1f)
        {
            var content = Game.LoadContent();
            var entry = content.Character(characterId);
            GameObject inst;
            if (entry != null && entry.model != null)
            {
                inst = Object.Instantiate(entry.model, parent);
                inst.name = "Model";
            }
            else
            {
                Debug.LogWarning($"[Nindo] Falta el modelo del personaje '{characterId}' en NindoContent. Uso una cápsula.");
                inst = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                Object.Destroy(inst.GetComponent<Collider>());
                inst.transform.SetParent(parent, false);
                inst.transform.localPosition = Vector3.up;
                inst.name = "Model";
            }
            inst.transform.localPosition = Vector3.zero;
            inst.transform.localRotation = Quaternion.Euler(0f, entry != null ? entry.modelYaw : 0f, 0f);
            inst.transform.localScale = Vector3.one;

            // quitar cualquier collider/script viejo que traiga el modelo
            foreach (var c in inst.GetComponentsInChildren<Collider>(true)) Object.Destroy(c);

            var animator = inst.GetComponentInChildren<Animator>();
            if (animator == null) animator = inst.AddComponent<Animator>();
            if (entry != null && entry.controller != null) animator.runtimeAnimatorController = entry.controller;
            animator.applyRootMotion = false;
            if (animator.GetComponent<AnimationEventSink>() == null) animator.gameObject.AddComponent<AnimationEventSink>();

            if (entry != null && entry.materialOverrides != null && entry.materialOverrides.Length > 0)
                foreach (var r in inst.GetComponentsInChildren<Renderer>(true))
                {
                    var mats = r.sharedMaterials;
                    for (int i = 0; i < mats.Length && i < entry.materialOverrides.Length; i++)
                        if (entry.materialOverrides[i] != null) mats[i] = entry.materialOverrides[i];
                    r.sharedMaterials = mats;
                }
            LiftBlacks(inst);

            float targetHeight = (entry != null ? entry.height : 1.6f) * scaleMul;
            NormalizeHeight(inst.transform, targetHeight);
            foreach (var r in inst.GetComponentsInChildren<Renderer>(true))
            {
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
                if (r is SkinnedMeshRenderer smr) smr.updateWhenOffscreen = false;
            }
            return animator;
        }

        /// <summary>Escala uniforme para que el modelo mida 'height' y apoye los pies en y=0.</summary>
        public static void NormalizeHeight(Transform model, float height)
        {
            var rs = model.GetComponentsInChildren<Renderer>(true);
            if (rs.Length == 0) return;
            Bounds b = default; bool any = false;
            foreach (var r in rs)
            {
                if (r is ParticleSystemRenderer) continue;
                Bounds rb;
                if (r is SkinnedMeshRenderer smr && smr.sharedMesh != null)
                {
                    // bounds del mesh en pose de bind, en espacio del modelo
                    rb = TransformBounds(smr.transform, smr.sharedMesh.bounds, model);
                }
                else if (r is MeshRenderer && r.GetComponent<MeshFilter>() is MeshFilter mf && mf.sharedMesh != null)
                    rb = TransformBounds(r.transform, mf.sharedMesh.bounds, model);
                else continue;
                if (!any) { b = rb; any = true; } else b.Encapsulate(rb);
            }
            if (!any || b.size.y < 0.01f) return;
            float s = height / b.size.y;
            model.localScale = Vector3.one * s;
            model.localPosition = new Vector3(0f, -b.min.y * s, 0f);
        }

        static Bounds TransformBounds(Transform from, Bounds local, Transform to)
        {
            Matrix4x4 m = to.worldToLocalMatrix * from.localToWorldMatrix;
            Vector3 c = local.center, e = local.extents;
            Bounds res = new Bounds(m.MultiplyPoint3x4(c), Vector3.zero);
            for (int i = 0; i < 8; i++)
            {
                Vector3 p = c + new Vector3((i & 1) == 0 ? -e.x : e.x, (i & 2) == 0 ? -e.y : e.y, (i & 4) == 0 ? -e.z : e.z);
                res.Encapsulate(m.MultiplyPoint3x4(p));
            }
            return res;
        }

        /// <summary>Tiñe los materiales del modelo (cacheado por clave para no romper el batching).</summary>
        public static void Tint(Transform model, string key, Color tint, float strength, bool emissive = false)
        {
            if (strength <= 0.001f) return;
            foreach (var r in model.GetComponentsInChildren<Renderer>(true))
            {
                if (r is ParticleSystemRenderer) continue;
                var src = r.sharedMaterials;
                string k = key + "|" + r.name + "|" + src.Length;
                if (!tintCache.TryGetValue(k, out var mats))
                {
                    mats = new Material[src.Length];
                    for (int i = 0; i < src.Length; i++)
                    {
                        if (src[i] == null) continue;
                        var m = new Material(src[i]) { name = src[i].name + "_" + key };
                        Color baseC = m.HasProperty("_BaseColor") ? m.GetColor("_BaseColor") : (m.HasProperty("_Color") ? m.GetColor("_Color") : Color.white);
                        Color c = Color.Lerp(baseC, tint * Mathf.Max(baseC.grayscale, 0.25f) * 1.6f, strength);
                        c.a = baseC.a;
                        if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
                        if (m.HasProperty("_Color")) m.SetColor("_Color", c);
                        if (emissive && m.HasProperty("_EmissionColor"))
                        {
                            m.EnableKeyword("_EMISSION");
                            m.SetColor("_EmissionColor", tint * 0.6f);
                        }
                        mats[i] = m;
                    }
                    tintCache[k] = mats;
                }
                r.sharedMaterials = mats;
            }
        }

        // =================================================================== jugador
        public static PlayerController BuildPlayer(Vector3 pos, Quaternion rot)
        {
            var root = new GameObject("Kaito");
            root.tag = "Player";
            int layer = LayerMask.NameToLayer("Player");
            if (layer >= 0) root.layer = layer;
            root.transform.SetPositionAndRotation(pos, rot);
            var cc = root.AddComponent<CharacterController>();
            cc.radius = 0.35f; cc.height = 1.45f; cc.center = new Vector3(0, 0.75f, 0);
            cc.stepOffset = 0.4f; cc.slopeLimit = 50f; cc.skinWidth = 0.04f; cc.minMoveDistance = 0f;
            var anim = BuildModel("kaito", root.transform);
            if (layer >= 0) foreach (var t in root.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;
            if (anim != null) CharacterKits.DressPlayer(anim.transform);     // colas de la bandana (antes que HitFlash)
            var pc = root.AddComponent<PlayerController>();
            pc.animator = anim;
            pc.model = anim != null ? anim.transform : null;
            root.AddComponent<ProceduralMotion>();
            // "luz de luna" que acompaña a Kaito: de noche los enemigos negros a su alrededor se
            // leían como agujeros; en combate sube un poco (MoonLantern)
            var moon = new GameObject("MoonLantern");
            moon.transform.SetParent(root.transform, false);
            moon.transform.localPosition = new Vector3(0f, 3.4f, -0.8f);
            var ml = moon.AddComponent<Light>();
            ml.type = LightType.Point; ml.range = 9f; ml.intensity = 1.1f; ml.color = new Color(0.72f, 0.82f, 1f);
            ml.shadows = LightShadows.None; ml.renderMode = LightRenderMode.ForcePixel;
            moon.AddComponent<MoonLantern>();
            return pc;
        }
    }

    /// <summary>Crea enemigos y jefes.</summary>
    public static class EnemyFactory
    {
        public static string CharacterFor(string archetype)
        {
            switch (archetype)
            {
                case "sumo": case "sumo_mountain": case "ozeki": return "sumo";
                case "goro": return "goro";
                case "kage": case "kage_clone": return "kage";
                default: return "ninja";
            }
        }

        public static bool IsBoss(string archetype) => archetype == "goro" || archetype == "mizuchi" || archetype == "ozeki" || archetype == "kage";

        public static Enemy Spawn(string archetype, Vector3 pos, Quaternion rot, Encounter encounter)
        {
            var cfg = EnemyArchetypes.Get(archetype);
            var root = new GameObject(cfg.displayName);
            int layer = LayerMask.NameToLayer("Enemy");
            if (layer >= 0) root.layer = layer;
            root.transform.SetPositionAndRotation(pos, rot);

            var anim = CharacterFactory.BuildModel(CharacterFor(archetype), root.transform, cfg.scale);
            EnemyVariants.Apply(archetype, cfg, anim, pos);     // kit de la zona (apaga el tinte si lo viste)
            if (cfg.tintStrength > 0f) CharacterFactory.Tint(anim.transform, cfg.id, cfg.tint, cfg.tintStrength, archetype.StartsWith("kage"));
            if (layer >= 0) foreach (var t in root.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;

            var col = root.AddComponent<CapsuleCollider>();
            col.radius = cfg.radius * cfg.scale;
            col.height = cfg.height * cfg.scale;
            col.center = new Vector3(0f, col.height * 0.5f, 0f);

            var agent = root.AddComponent<NavMeshAgent>();
            agent.baseOffset = 0f;
            if (NavMesh.SamplePosition(pos, out var hit, 4f, NavMesh.AllAreas)) agent.Warp(hit.position);

            Enemy e;
            if (IsBoss(archetype))
            {
                var b = root.AddComponent<Boss>();
                ConfigureBoss(b, archetype);
                e = b;
            }
            else e = root.AddComponent<Enemy>();
            e.config = cfg;
            e.encounter = encounter;
            return e;
        }

        static void ConfigureBoss(Boss b, string archetype)
        {
            switch (archetype)
            {
                case "goro":
                    b.bossId = "goro"; b.title = "Gorō"; b.subtitle = "El Martillo de Kodoyama";
                    b.introAnim = "Intro"; b.phaseAnim = "Spotted"; b.musicKey = "boss"; b.phaseThresholds = new[] { 0.5f };
                    break;
                case "mizuchi":
                    b.bossId = "mizuchi"; b.title = "Mizuchi"; b.subtitle = "La Marea del Lago Kohan";
                    b.introAnim = "Spotted"; b.phaseAnim = "Spotted"; b.musicKey = "boss"; b.phaseThresholds = new[] { 0.55f };
                    b.minionArchetype = "ninja";
                    break;
                case "ozeki":
                    b.bossId = "ozeki"; b.title = "Ōzeki"; b.subtitle = "El Gran Campeón del Bambú";
                    b.introAnim = "Spotted"; b.phaseAnim = "Spotted"; b.musicKey = "boss"; b.phaseThresholds = new[] { 0.5f };
                    break;
                case "kage":
                    b.bossId = "kage"; b.title = "Kage"; b.subtitle = "La Sombra del Clan";
                    b.introAnim = "ParryStance"; b.phaseAnim = "Blocked"; b.musicKey = "boss_final"; b.phaseThresholds = new[] { 0.6f, 0.25f };
                    b.phaseSpeedBonus = 0.1f;
                    break;
            }
            b.hasSeal = BossSeal(archetype, out b.seal);
        }

        /// <summary>Sello que entrega cada jefe al morir (Kage no da sello). Lo usa también BossArena.</summary>
        public static bool BossSeal(string archetype, out SealId seal)
        {
            switch (archetype)
            {
                case "goro": seal = SealId.Montana; return true;
                case "mizuchi": seal = SealId.Lago; return true;
                case "ozeki": seal = SealId.Bambu; return true;
                default: seal = SealId.Montana; return false;
            }
        }

        /// <summary>Clon de sombra de Kage (1 golpe lo destruye).</summary>
        public static Enemy SpawnClone(Boss owner, Vector3 pos)
        {
            var e = Spawn("kage_clone", pos, owner.transform.rotation, null);
            return e;
        }
    }

    /// <summary>
    /// Recibe los Animation Events que traen los clips originales del equipo (StartTrail,
    /// DealDamage, ...). El nuevo sistema usa tiempos normalizados en código, así que acá no
    /// se hace nada: solo evita los errores "AnimationEvent has no receiver".
    /// </summary>
    public class AnimationEventSink : MonoBehaviour
    {
        public void StartTrail() { }
        public void StopTrail() { }
        public void EnableComboWindow() { }
        public void DisableComboWindow() { }
        public void StartAttacking() { }
        public void StopAttacking() { }
        public void AttackEnd() { }
        public void ActivateSlowMotion() { }
        public void Fbx1() { }
        public void EndFinisher() { }
        public void ActivateSlash() { }
        public void StartParry() { }
        public void EndParry() { }
        public void StartAttack() { }
        public void DealDamage() { }
        public void StopAttack() { }
        public void ComboEnd() { }
        public void OnParryAnimationEnd() { }
    }
}
