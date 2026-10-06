using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// La bandana de Kaito brilla dorada en el eclipse (Acto 3 de Kokuyō): "la cinta ve por vos". La luz de luna que
    /// acompaña a Kaito (MoonLantern) se vuelve una luz dorada #ffd86b de 2.2 y 9 m que ilumina el piso a su
    /// alrededor; la bandana (el nudo del cuerpo y las colas del kit, todo slot que se llame AmarilloBandana) se
    /// enciende y suben motas doradas desde la cabeza. Enable / Disable con fundido; Pulse para el destello de cada
    /// parry (con la bandana apagada no toca la luz de luna: suma un destello aparte).
    /// La emisión va por MaterialPropertyBlock por (renderer, índice). Con Nindo/CharacterLit alcanza (su emisión no
    /// depende de keywords); con el Lit de URP la keyword _EMISSION no se prende desde un bloque, así que mientras
    /// brilla el slot usa una copia del material con la keyword. HitFlash cambia todos los materiales un instante: el
    /// slot se revisa en cada cuadro y el cambio (o la vuelta al original) se reintenta hasta que el slot tenga lo
    /// esperado, sin tomar nunca el material del destello por el de la bandana.
    /// Radius es el alcance actual de la luz: la sombra viva usa ese radio como hueco (el lazo empuja la tinta).
    /// </summary>
    public class BandanaGlow : MonoBehaviour
    {
        public static readonly Color Gold = new Color(1f, 0.847f, 0.42f);     // #ffd86b (glow_spirit)
        /// <summary>Emisión de la bandana: oro saturado (con el ACES de ScreenFX el #ffd86b x2.4 llegaba casi blanco).</summary>
        static readonly Color EmissionGold = new Color(1.6f, 1.0f, 0.25f);
        public const string BandanaSlot = "AmarilloBandana";                  // material de la bandana en el FBX de Kaito
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");
        /// <summary>Si el slot no vuelve a su material en este tiempo (algo lo tapa), se deja de insistir.</summary>
        const float GiveUpSeconds = 1f;

        public float Intensity = 2.2f;
        public float Range = 9f;

        /// <summary>0..1: cuánto está encendida (con fundido).</summary>
        public float Amount => amount;
        public bool On => target > 0.5f;
        /// <summary>Alcance actual de la luz dorada (0 apagada).</summary>
        public float Radius => ownsLight && amount > 0.01f ? light.range : 0f;

        class Slot { public Renderer r; public int index; public bool block; }

        Light light;
        MoonLantern lantern;
        Color lanternColor; float lanternIntensity, lanternRange;
        bool ownsLight;                     // la luz de MoonLantern es de la bandana (Enable) hasta que se apague
        readonly List<Slot> slots = new List<Slot>();
        readonly Dictionary<Material, Material> copyOf = new Dictionary<Material, Material>();      // original -> copia
        readonly Dictionary<Material, Material> originalOf = new Dictionary<Material, Material>();  // copia -> original
        readonly List<Material> mats = new List<Material>();
        MaterialPropertyBlock mpb;
        ParticleSystem motes;
        Transform head;
        float amount, target, speed = 1f, pulse, dirty;
        Color pulseColor = Color.white;

        /// <summary>El componente en Kaito (lo crea la primera vez).</summary>
        public static BandanaGlow Ensure(PlayerController p)
        {
            if (p == null) return null;
            var g = p.GetComponent<BandanaGlow>();
            return g != null ? g : p.gameObject.AddComponent<BandanaGlow>();
        }

        void Awake()
        {
            mpb = new MaterialPropertyBlock();
            lantern = GetComponentInChildren<MoonLantern>(true);
            light = lantern != null ? lantern.GetComponent<Light>() : null;
            if (light != null) CaptureLantern();
            else
            {
                var lg = new GameObject("LuzDeLaBandana");
                lg.transform.SetParent(transform, false);
                lg.transform.localPosition = new Vector3(0f, 3.2f, -0.6f);
                light = lg.AddComponent<Light>();
                light.type = LightType.Point; light.shadows = LightShadows.None; light.intensity = 0f; light.enabled = false;
            }
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                string n = t.name.ToLowerInvariant();
                if (n == "cabeza" || n == "head") { head = t; break; }
            }
            // todos los slots de la bandana: el nudo en el cuerpo y las colas del kit (comparten el material vivo)
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (!(r is SkinnedMeshRenderer || r is MeshRenderer)) continue;
                r.GetSharedMaterials(mats);
                for (int i = 0; i < mats.Count; i++)
                    if (mats[i] != null && mats[i].name.Contains(BandanaSlot)) slots.Add(new Slot { r = r, index = i });
            }
            motes = MakeMotes();
            enabled = false;
        }

        void CaptureLantern() { lanternColor = light.color; lanternIntensity = light.intensity; lanternRange = light.range; }

        ParticleSystem MakeMotes()
        {
            var ps = FXFactory.NewSystem("MotasDoradas", transform);
            var m = ps.main;
            m.loop = true; m.duration = 2f; m.playOnAwake = true;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.9f, 1.6f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.15f, 0.45f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.03f, 0.07f);
            m.startColor = new ParticleSystem.MinMaxGradient(Gold, new Color(1f, 0.95f, 0.75f));
            m.gravityModifier = -0.2f;
            m.maxParticles = 60;
            var em = ps.emission; em.rateOverTime = 0f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Sphere; sh.radius = 0.25f;
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.3f; noise.frequency = 1.4f;
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.2f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            ps.Play();
            return ps;
        }

        Vector3 HeadPosition => head != null ? head.position : transform.position + Vector3.up * 1.35f;

        /// <summary>Se enciende en 'seconds' (la luz de luna de Kaito pasa a ser la luz de la bandana).</summary>
        public void Enable(float seconds = 0.8f)
        {
            if (light == null) return;
            if (!ownsLight)
            {
                // los valores de la luna de Kaito de ESTE momento (exploración o combate): a esos vuelve al apagarse
                if (lantern != null) { CaptureLantern(); lantern.enabled = false; }
                ownsLight = true;
            }
            target = 1f;
            speed = seconds > 0f ? 1f / seconds : 1000f;
            light.enabled = true;
            enabled = true;
        }

        /// <summary>Se apaga en 'seconds' y le devuelve la luz a MoonLantern.</summary>
        public void Disable(float seconds = 0.8f)
        {
            target = 0f;
            speed = seconds > 0f ? 1f / seconds : 1000f;
        }

        /// <summary>
        /// Destello: la bandana sube un instante (parry en la ventana: blanco; Filo de Ira: naranja). Encendida, su luz
        /// sube con ella; apagada, la luz de luna de Kaito sigue siendo de MoonLantern y el destello es una luz aparte.
        /// </summary>
        public void Pulse(Color c, float strength = 1f)
        {
            pulse = Mathf.Max(pulse, strength);
            pulseColor = c;
            if (!ownsLight) Game.FX?.FlashLight(HeadPosition + Vector3.up * 0.3f, c, 2.5f * strength, Range * 0.7f, 0.3f);
            enabled = true;
        }

        bool NeedsKeyword(Material m) => m.shader != null && m.shader.name.StartsWith("Universal Render Pipeline/");

        Material GlowCopy(Material original)
        {
            if (copyOf.TryGetValue(original, out var c) && c != null) return c;
            c = new Material(original) { name = original.name + "_Brilla" };
            c.EnableKeyword("_EMISSION");
            c.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            copyOf[original] = c;
            originalOf[c] = original;
            return c;
        }

        void SetSlotMaterial(Slot s, Material m)
        {
            mats[s.index] = m;
            s.r.sharedMaterials = mats.ToArray();
        }

        /// <summary>
        /// Pone o saca la emisión en cada slot. Devuelve true si todos quedaron limpios (sin copia ni bloque). Un slot
        /// con otro material (el de HitFlash) no se toca: se vuelve a mirar en el cuadro siguiente.
        /// </summary>
        bool UpdateSlots(bool glowing, Color emission)
        {
            bool clean = true;
            foreach (var s in slots)
            {
                if (s.r == null) continue;
                s.r.GetSharedMaterials(mats);
                if (s.index >= mats.Count) continue;
                var cur = mats[s.index];
                bool isCopy = cur != null && originalOf.ContainsKey(cur);
                bool isOwn = cur != null && !isCopy && cur.name.Contains(BandanaSlot);
                if (glowing)
                {
                    if (isOwn && NeedsKeyword(cur)) { SetSlotMaterial(s, GlowCopy(cur)); isCopy = true; isOwn = false; }
                    if (isOwn || isCopy)
                    {
                        s.r.GetPropertyBlock(mpb, s.index);
                        mpb.SetColor(EmissionId, emission);
                        s.r.SetPropertyBlock(mpb, s.index);
                        s.block = true;
                    }
                    continue;
                }
                if (isCopy) { SetSlotMaterial(s, originalOf[cur]); isOwn = true; }
                if (s.block && isOwn) { s.r.SetPropertyBlock(null, s.index); s.block = false; }
                // un destello en curso puede devolver la copia al terminar: hasta ver el original, no está limpio
                if (!isOwn || s.block) clean = false;
            }
            return clean;
        }

        void OnDestroy()
        {
            if (amount > 0f || pulse > 0f) UpdateSlots(false, Color.black);
            foreach (var c in originalOf.Keys) if (c != null) Destroy(c);
        }

        void LateUpdate()
        {
            float dt = Time.unscaledDeltaTime;
            amount = Mathf.MoveTowards(amount, target, dt * speed);
            pulse = Mathf.Max(0f, pulse - dt * 4f);
            float k = Mathf.SmoothStep(0f, 1f, amount);
            float breathe = 0.92f + 0.08f * Mathf.Sin(Time.time * 2.2f);
            if (ownsLight)
            {
                bool hasLantern = lantern != null;
                light.color = Color.Lerp(Color.Lerp(hasLantern ? lanternColor : Gold, Gold, k), pulseColor, pulse * 0.6f);
                light.intensity = Mathf.Lerp(hasLantern ? lanternIntensity : 0f, Intensity * breathe, k) + pulse * 2.5f;
                light.range = Mathf.Lerp(hasLantern ? lanternRange : Range, Range, k);
            }
            if (motes != null)
            {
                motes.transform.position = HeadPosition;
                var em = motes.emission; em.rateOverTime = 14f * k;
            }
            bool glowing = k > 0.001f || pulse > 0.001f;
            Color e = EmissionGold * (k * breathe) + pulseColor * (1.4f * pulse);
            e.a = 1f;
            bool clean = UpdateSlots(glowing, e);
            dirty = clean || glowing ? 0f : dirty + dt;
            if (amount <= 0f && target <= 0f && ownsLight)
            {
                // apagada del todo: la luz vuelve a ser la luna de Kaito (con sus valores; MoonLantern sigue desde ahí)
                if (lantern != null) { light.color = lanternColor; light.intensity = lanternIntensity; light.range = lanternRange; lantern.enabled = true; }
                else light.enabled = false;
                ownsLight = false;
            }
            if (!ownsLight && !glowing && (clean || dirty > GiveUpSeconds)) enabled = false;
        }
    }
}
