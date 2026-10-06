using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// La bandana de Kaito brilla dorada en el eclipse (Acto 3 de Kokuyō): "la cinta ve por vos". La luz de luna que
    /// acompaña a Kaito (MoonLantern) se vuelve una luz dorada #ffd86b de 2.2 y 9 m que ilumina el piso a su
    /// alrededor; el slot de la bandana se enciende y suben motas doradas desde la cabeza. Enable / Disable con
    /// fundido; Pulse para el destello de cada parry. La bandana del FBX trae un Lit sin la keyword _EMISSION (y un
    /// MaterialPropertyBlock no puede prenderla): mientras brilla, el slot usa una copia del material con la emisión
    /// activa y al apagarse vuelve el original (el batching de Kaito queda como estaba).
    /// Radius es el alcance actual de la luz: la sombra viva usa ese radio como hueco (el lazo empuja la tinta).
    /// </summary>
    public class BandanaGlow : MonoBehaviour
    {
        public static readonly Color Gold = new Color(1f, 0.847f, 0.42f);     // #ffd86b (glow_spirit)
        /// <summary>Emisión de la bandana: oro saturado (con el ACES de ScreenFX el #ffd86b x2.4 llegaba casi blanco).</summary>
        static readonly Color EmissionGold = new Color(1.6f, 1.0f, 0.25f);
        public const string BandanaSlot = "AmarilloBandana";                  // material de la bandana en el FBX de Kaito
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        public float Intensity = 2.2f;
        public float Range = 9f;

        /// <summary>0..1: cuánto está encendida (con fundido).</summary>
        public float Amount => amount;
        public bool On => target > 0.5f;
        /// <summary>Alcance actual de la luz dorada (0 apagada).</summary>
        public float Radius => light != null && amount > 0.01f ? light.range : 0f;

        Light light;
        MoonLantern lantern;
        Color lanternColor; float lanternIntensity, lanternRange;
        Renderer bandana;
        int bandanaIndex = -1;
        Material bandanaOriginal, bandanaGlow;
        MaterialPropertyBlock mpb;
        ParticleSystem motes;
        Transform head;
        float amount, target, speed = 1f, pulse;
        Color pulseColor = Color.white;
        bool cleared = true;

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
            if (light == null)
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
            foreach (var r in GetComponentsInChildren<Renderer>(true))
            {
                if (!(r is SkinnedMeshRenderer || r is MeshRenderer)) continue;
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                    if (mats[i] != null && mats[i].name.Contains(BandanaSlot)) { bandana = r; bandanaIndex = i; break; }
                if (bandana != null) break;
            }
            motes = MakeMotes();
            enabled = false;
        }

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

        /// <summary>Se enciende en 'seconds' (la luz de luna de Kaito pasa a ser la luz de la bandana).</summary>
        public void Enable(float seconds = 0.8f)
        {
            if (light == null) return;
            if (target < 0.5f && amount <= 0.001f && lantern != null)
            {
                lanternColor = light.color; lanternIntensity = light.intensity; lanternRange = light.range;
                lantern.enabled = false;
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

        /// <summary>Destello: la bandana y su luz suben un instante (parry en la ventana: blanco; Filo de Ira: naranja).</summary>
        public void Pulse(Color c, float strength = 1f)
        {
            pulse = Mathf.Max(pulse, strength);
            pulseColor = c;
            if (light != null) light.enabled = true;
            enabled = true;
        }

        /// <summary>Pone (true) o saca (false) la copia de la bandana con la emisión activa.</summary>
        void SwapBandana(bool glow)
        {
            var mats = bandana.sharedMaterials;
            if (bandanaIndex >= mats.Length) return;
            if (glow)
            {
                if (mats[bandanaIndex] == bandanaGlow && bandanaGlow != null) return;
                bandanaOriginal = mats[bandanaIndex];
                if (bandanaOriginal == null) return;
                if (bandanaGlow == null)
                {
                    bandanaGlow = new Material(bandanaOriginal) { name = bandanaOriginal.name + "_Brilla" };
                    bandanaGlow.EnableKeyword("_EMISSION");
                    bandanaGlow.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
                }
                mats[bandanaIndex] = bandanaGlow;
            }
            else
            {
                if (bandanaOriginal == null || mats[bandanaIndex] != bandanaGlow) return;
                mats[bandanaIndex] = bandanaOriginal;
            }
            bandana.sharedMaterials = mats;
        }

        void OnDestroy() { if (bandanaGlow != null) Destroy(bandanaGlow); }

        void LateUpdate()
        {
            float dt = Time.unscaledDeltaTime;
            amount = Mathf.MoveTowards(amount, target, dt * speed);
            pulse = Mathf.Max(0f, pulse - dt * 4f);
            float k = Mathf.SmoothStep(0f, 1f, amount);
            float breathe = 0.92f + 0.08f * Mathf.Sin(Time.time * 2.2f);
            if (light != null)
            {
                Color baseC = lantern != null ? lanternColor : Gold;
                light.color = Color.Lerp(Color.Lerp(baseC, Gold, k), pulseColor, pulse * 0.6f);
                light.intensity = Mathf.Lerp(lantern != null ? lanternIntensity : 0f, Intensity * breathe, k) + pulse * 2.5f;
                light.range = Mathf.Lerp(lantern != null ? lanternRange : Range, Range, k);
            }
            if (motes != null)
            {
                motes.transform.position = head != null ? head.position : transform.position + Vector3.up * 1.35f;
                var em = motes.emission; em.rateOverTime = 14f * k;
            }
            if (bandana != null && bandanaIndex >= 0)
            {
                // cada cuadro: un HitFlash o un destello de CharacterGlint pueden haber pisado el bloque
                if (k > 0.001f || pulse > 0.001f)
                {
                    if (cleared) SwapBandana(true);
                    Color e = EmissionGold * (k * breathe) + pulseColor * (1.4f * pulse);
                    e.a = 1f;
                    bandana.GetPropertyBlock(mpb, bandanaIndex);
                    mpb.SetColor(EmissionId, e);
                    bandana.SetPropertyBlock(mpb, bandanaIndex);
                    cleared = false;
                }
                else if (!cleared)
                {
                    bandana.SetPropertyBlock(null, bandanaIndex);
                    SwapBandana(false);
                    cleared = true;
                }
            }
            if (amount <= 0f && target <= 0f && pulse <= 0f)
            {
                // apagada del todo: la luz vuelve a ser la luna de Kaito
                if (lantern != null) { light.color = lanternColor; light.intensity = lanternIntensity; light.range = lanternRange; lantern.enabled = true; }
                else if (light != null) light.enabled = false;
                enabled = false;
            }
        }
    }
}
