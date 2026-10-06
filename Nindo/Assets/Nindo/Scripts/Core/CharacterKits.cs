using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Kits de accesorios sobre los personajes del equipo (Tools/Blender/characters/kits/build_kits.py): el
    /// hachimaki y la capa de paja de los ninjas de cada zona, la red y el sombrero del lago, la armadura de
    /// cañas del bambú, la tsuna del Ōzeki, las colas de la bandana de Kaito...
    ///
    /// Cada kit es un FBX con el MISMO esqueleto que el personaje y una malla con skin ('Acc_Kit'). Al vestir:
    ///  1. los huesos nuevos del kit ('Acc_*' de las cadenas, 'AccCol_*' de las colisiones) se cuelgan de los
    ///     huesos vivos del personaje que se llaman igual que su padre en el kit (mismo transform local);
    ///  2. la malla re-apunta sus huesos por nombre a los vivos y pasa a ser hija del modelo;
    ///  3. el resto de la instancia (la copia del esqueleto) se destruye.
    /// Funciona porque el skin depende solo de la pose de bind, que es la misma en el kit y en el personaje
    /// (el kit se exporta desde el armature del FBX del equipo sin tocar un hueso).
    /// Las cadenas las mueve SpringChain. Se viste ANTES de que Enemy/HitFlash miren los renderers, así el
    /// destello de golpe y la capa de enemigos alcanzan al kit.
    /// </summary>
    public static class CharacterKits
    {
        static Transform holder;
        static Shader litShader;
        static bool litSearched;
        static readonly Dictionary<Material, Material> litCache = new Dictionary<Material, Material>();
        static readonly Dictionary<(Material, Color), Material> recolorCache = new Dictionary<(Material, Color), Material>();
        static readonly HashSet<string> warned = new HashSet<string>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void Reset() { holder = null; litShader = null; litSearched = false; litCache.Clear(); recolorCache.Clear(); warned.Clear(); }

        /// <summary>Prefijos de los huesos que agrega un kit (los demás son la copia del esqueleto del personaje).</summary>
        public const string ChainPrefix = "Acc_", ColliderPrefix = "AccCol_";

        /// <summary>Padre desactivado para instanciar los kits: sus componentes no llegan a despertarse.</summary>
        static Transform Holder
        {
            get
            {
                if (holder == null)
                {
                    var go = new GameObject("[Kits]");
                    go.SetActive(false);
                    holder = go.transform;
                }
                return holder;
            }
        }

        /// <summary>Nombre del material sin " (Instance)", "_lift" (CharacterFactory.LiftBlacks) ni ".001".</summary>
        public static string BaseName(string n)
        {
            if (n.EndsWith(" (Instance)")) n = n.Substring(0, n.Length - 11);
            if (n.EndsWith("_lift")) n = n.Substring(0, n.Length - 5);
            int dot = n.Length - 4;
            if (dot > 0 && n[dot] == '.' && char.IsDigit(n[dot + 1]) && char.IsDigit(n[dot + 2]) && char.IsDigit(n[dot + 3])) n = n.Substring(0, dot);
            return n;
        }

        static bool IsKitBone(string n) => n.StartsWith(ChainPrefix) || n.StartsWith(ColliderPrefix);

        /// <summary>
        /// Viste 'model' (la instancia del FBX que arma CharacterFactory.BuildModel) con el kit 'kitId' y le agrega
        /// SpringChain si el kit trae cadenas. Devuelve el renderer del kit (null si el kit no está o no encaja).
        /// </summary>
        public static SkinnedMeshRenderer Attach(Transform model, string kitId)
        {
            var prefab = Game.LoadContent().Kit(kitId);
            if (prefab == null)
            {
                if (warned.Add(kitId)) Debug.LogWarning($"[Nindo] Falta el kit '{kitId}' en NindoContent (Tools/Unity/generate_assets.py).");
                return null;
            }
            var live = new Dictionary<string, Transform>();
            foreach (var t in model.GetComponentsInChildren<Transform>(true))
                if (!live.ContainsKey(t.name)) live[t.name] = t;

            var inst = Object.Instantiate(prefab, Holder);
            // 1. raíces de las cadenas y marcadores: su padre en el kit es un hueso del personaje
            var roots = new List<(Transform bone, Transform parent)>();
            foreach (var t in inst.GetComponentsInChildren<Transform>(true))
            {
                if (!IsKitBone(t.name) || t.parent == null || IsKitBone(t.parent.name) || t.GetComponent<Renderer>() != null) continue;
                if (live.TryGetValue(t.parent.name, out var lp)) roots.Add((t, lp));
            }
            int layer = model.gameObject.layer;
            foreach (var (bone, parent) in roots)
            {
                bone.SetParent(parent, false);      // mismo local: el hueso del kit y el vivo tienen el mismo marco
                foreach (var d in bone.GetComponentsInChildren<Transform>(true))
                {
                    d.gameObject.layer = layer;
                    if (!live.ContainsKey(d.name)) live[d.name] = d;
                }
            }

            // 2. la malla con skin pasa al modelo con los huesos vivos
            SkinnedMeshRenderer result = null;
            foreach (var smr in inst.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var src = smr.bones;
                var bones = new Transform[src.Length];
                string missing = null;
                for (int i = 0; i < src.Length; i++)
                    if (src[i] == null || !live.TryGetValue(src[i].name, out bones[i])) { missing = src[i] != null ? src[i].name : "?"; break; }
                if (missing != null)
                {
                    if (warned.Add(kitId + missing)) Debug.LogWarning($"[Nindo] El kit '{kitId}' usa el hueso '{missing}' que '{model.name}' no tiene: no se viste.");
                    continue;
                }
                smr.bones = bones;
                smr.rootBone = smr.rootBone != null && live.TryGetValue(smr.rootBone.name, out var rb) ? rb : bones[0];
                smr.transform.SetParent(model, false);
                smr.gameObject.name = "Acc_Kit_" + kitId;
                smr.gameObject.layer = layer;           // la capa del personaje (cámara, luces y golpes la miran)
                smr.updateWhenOffscreen = false;
                smr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
                // las colas y capas salen de los bounds de reposo cuando flamean: margen para que no se recorten
                var b = smr.localBounds; b.Expand(b.size.magnitude * 0.35f); smr.localBounds = b;
                ConvertMaterials(smr, model);
                result = smr;
            }
            Object.Destroy(inst);
            if (result == null)
            {
                // no encajó: los huesos que ya se colgaron del personaje se van con el resto del kit
                foreach (var (bone, _) in roots) Object.Destroy(bone.gameObject);
                return null;
            }

            if (roots.Exists(r => r.bone.name.StartsWith(ChainPrefix)))
            {
                var spring = model.GetComponent<SpringChain>();
                if (spring == null) spring = model.gameObject.AddComponent<SpringChain>();
                spring.Rebuild(result);
            }
            return result;
        }

        /// <summary>
        /// Materiales del kit: el de la paleta pasa a Nindo/CharacterLit (el rim y la luz de los personajes) si el
        /// proyecto lo tiene; el emisivo queda como está; uno con nombre propio toma el material vivo del cuerpo que
        /// se llame igual (las colas de Kaito usan el de su bandana: mismo amarillo, brillo y rim que el nudo).
        /// </summary>
        static void ConvertMaterials(SkinnedMeshRenderer kit, Transform model)
        {
            var mats = kit.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                var m = mats[i];
                if (m == null) continue;
                string n = BaseName(m.name);
                if (n == "Nindo_Emissive") continue;
                var liveMat = n != "Nindo_Palette" ? BodyMaterial(model, kit, n) : null;
                mats[i] = liveMat != null ? liveMat : ToCharacterLit(m);
            }
            kit.sharedMaterials = mats;
        }

        /// <summary>Material del cuerpo (no de un kit) cuyo nombre base es 'name'; null si ahora no lo lleva.</summary>
        static Material BodyMaterial(Transform model, Renderer kit, string name)
        {
            foreach (var r in model.GetComponentsInChildren<Renderer>(true))
            {
                if (r == kit || r is ParticleSystemRenderer || r.name.StartsWith(ChainPrefix)) continue;
                foreach (var m in r.sharedMaterials)
                    if (m != null && BaseName(m.name) == name) return m;
            }
            return null;
        }

        /// <summary>
        /// Vuelve a tomar del cuerpo el material vivo 'name' para los slots del kit que se llaman igual. La bandana
        /// de Kaito pasa el prólogo tapada con el material del pelo (CharacterFactory.SetBandana): sus colas copian
        /// el amarillo recién cuando el cuerpo lo vuelve a mostrar. Devuelve false si el cuerpo todavía no lo lleva.
        /// </summary>
        public static bool ShareBodyMaterial(Renderer kit, string name)
        {
            var model = kit.transform.parent;
            var liveMat = model != null ? BodyMaterial(model, kit, name) : null;
            if (liveMat == null) return false;
            var mats = kit.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
                if (mats[i] != null && BaseName(mats[i].name) == name) mats[i] = liveMat;
            kit.sharedMaterials = mats;
            return true;
        }

        static Material ToCharacterLit(Material src)
        {
            if (litCache.TryGetValue(src, out var m)) return m;
            if (!litSearched)
            {
                litSearched = true;
                litShader = Shader.Find("Nindo/CharacterLit");
                if (litShader != null && !litShader.isSupported) litShader = null;
            }
            m = src;
            if (litShader != null)
            {
                // mismo nombre base que en el FBX: ShareBodyMaterial y Recolor lo siguen reconociendo
                m = new Material(litShader) { name = BaseName(src.name) };
                if (src.HasProperty("_BaseColor")) m.SetColor("_BaseColor", src.GetColor("_BaseColor"));
                Texture tex = src.HasProperty("_BaseMap") ? src.GetTexture("_BaseMap") : null;
                if (tex != null) m.SetTexture("_BaseMap", tex);
                // la paleta y las telas casi mates, como el resto de los personajes
                m.SetFloat("_Smoothness", 0.15f);
                m.SetColor("_EmissionColor", Color.black);
            }
            litCache[src] = m;
            return m;
        }

        /// <summary>
        /// Pinta materiales del cuerpo por nombre (el traje negro con el matiz de la zona, el mawashi de cada sumo).
        /// Copias cacheadas por (material, color): todos los ninjas del lago comparten el mismo material.
        /// </summary>
        public static void Recolor(Transform model, IReadOnlyList<KeyValuePair<string, Color>> colors)
        {
            if (colors == null || colors.Count == 0) return;
            foreach (var r in model.GetComponentsInChildren<Renderer>(true))
            {
                if (r is ParticleSystemRenderer || r.name.StartsWith(ChainPrefix)) continue;
                var mats = r.sharedMaterials;
                bool changed = false;
                for (int i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null || !mats[i].HasProperty("_BaseColor")) continue;
                    string n = BaseName(mats[i].name);
                    foreach (var kv in colors)
                    {
                        if (kv.Key != n) continue;
                        if (!recolorCache.TryGetValue((mats[i], kv.Value), out var nm))
                        {
                            nm = new Material(mats[i]) { name = n };
                            nm.SetColor("_BaseColor", kv.Value);
                            if (nm.HasProperty("_Color")) nm.SetColor("_Color", kv.Value);
                            recolorCache[(mats[i], kv.Value)] = nm;
                        }
                        mats[i] = nm; changed = true;
                        break;
                    }
                }
                if (changed) r.sharedMaterials = mats;
            }
        }

        // ================================================================== Kaito
        /// <summary>Slot de la bandana de Kaito (export_kaito.py): el nudo es del cuerpo, las colas del kit.</summary>
        public const string BandanaMaterial = "AmarilloBandana";

        /// <summary>
        /// Las dos colas de la bandana de Kaito (kit 'kaito_bandana'). Mientras no tiene la katana (el prólogo) no
        /// están: la bandana se le ata sola en BandanaAwakening y ahí aparecen con un latigazo.
        /// </summary>
        public static void DressPlayer(Transform model)
        {
            if (model == null) return;
            var tails = Attach(model, "kaito_bandana");
            if (tails == null) return;
            var reveal = tails.gameObject.AddComponent<KitReveal>();
            reveal.flag = Flags.KatanaObtained;
            reveal.liveMaterial = BandanaMaterial;
        }
    }

    /// <summary>
    /// Muestra un accesorio recién cuando se cumple un flag de la partida (las colas de la bandana de Kaito antes
    /// de que la reciba). Al aparecer toma el material vivo del cuerpo ('liveMaterial': hasta ese momento el slot
    /// del cuerpo puede estar tapado) y patea la cadena para que se vea el nudo atándose; después se apaga sola.
    /// </summary>
    public class KitReveal : MonoBehaviour
    {
        public string flag;
        public string liveMaterial;
        [Tooltip("Velocidad inicial de las puntas al aparecer (m/s): hacia arriba y hacia la espalda del personaje")]
        public float kickUp = 3.5f, kickBack = 2.5f;
        [Tooltip("Segundos (reales) que espera a que el cuerpo vuelva a mostrar 'liveMaterial' antes de aparecer igual")]
        public float maxWaitSeconds = 3f;
        Renderer r;
        float since = -1f;

        void Awake()
        {
            r = GetComponent<Renderer>();
            if (!Has()) r.enabled = false;
            else enabled = false;
        }

        bool Has() => Game.Save != null && Game.Save.HasFlag(flag);

        void Update()
        {
            if (!Has()) return;
            // la historia pone el flag al tomar la hoz y destapa el nudo recién ~0.9 s después (en tiempo real, con
            // la cámara lenta de StoryDirector.BandanaAwakening): las colas esperan ese momento para aparecer junto
            // con el destello del nudo y con su material vivo. En tiempo real y no en frames: a 144 fps 30 frames
            // eran 0.2 s y aparecían antes, con una copia del amarillo sin la emisión de la bandana
            if (since < 0f) since = Time.unscaledTime;
            if (!string.IsNullOrEmpty(liveMaterial) && !CharacterKits.ShareBodyMaterial(r, liveMaterial)
                && Time.unscaledTime - since < maxWaitSeconds) return;
            r.enabled = true;
            var spring = GetComponentInParent<SpringChain>();
            if (spring != null) spring.Kick(Vector3.up * kickUp - spring.Owner.forward * kickBack);
            enabled = false;
        }
    }
}
