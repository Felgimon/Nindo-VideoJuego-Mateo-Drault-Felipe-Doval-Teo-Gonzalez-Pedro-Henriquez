using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Nindo
{
    /// <summary>
    /// Post-procesado URP creado por código: el "look" base (bloom para faroles y luciérnagas,
    /// tonemapping, viñeta, profundidad de campo tipo diorama) y los golpes de pantalla del
    /// game-feel (aberración cromática en parry perfecto, desaturación en cámara lenta,
    /// viñeta roja al recibir daño, tinte naranja en Filo de Ira, foco en habilidades).
    /// </summary>
    public class ScreenFX : MonoBehaviour
    {
        Volume volume;
        VolumeProfile profile;
        Bloom bloom;
        Vignette vignette;
        ChromaticAberration chroma;
        ColorAdjustments color;
        LensDistortion lens;
        DepthOfField dof;
        Tonemapping tonemap;
        WhiteBalance white;

        float chromaPunch, damagePulse, abilityFocus, abilityTarget, rageAmount, rageTarget, shadowInstant, finisher, finisherTarget;
        float lowHealth;
        Color baseFilter = Color.white;

        public float BaseVignette = 0.28f;
        public float BaseSaturation = 8f;
        public float BaseContrast = 12f;
        public bool DiormaDof = true;

        void Awake()
        {
            var go = new GameObject("Nindo PostFX");
            go.transform.SetParent(transform, false);
            volume = go.AddComponent<Volume>();
            volume.isGlobal = true;
            volume.priority = 10f;
            profile = ScriptableObject.CreateInstance<VolumeProfile>();
            profile.name = "NindoRuntimeProfile";
            volume.sharedProfile = profile;

            tonemap = profile.Add<Tonemapping>(true);
            tonemap.mode.value = TonemappingMode.ACES;

            bloom = profile.Add<Bloom>(true);
            bloom.threshold.value = 0.95f;
            bloom.intensity.value = 0.9f;
            bloom.scatter.value = 0.72f;
            bloom.tint.value = new Color(1f, 0.92f, 0.8f);

            vignette = profile.Add<Vignette>(true);
            vignette.intensity.value = BaseVignette;
            vignette.smoothness.value = 0.45f;
            vignette.color.value = new Color(0.02f, 0.02f, 0.06f);

            chroma = profile.Add<ChromaticAberration>(true);
            chroma.intensity.value = 0.04f;

            color = profile.Add<ColorAdjustments>(true);
            color.saturation.value = BaseSaturation;
            color.contrast.value = BaseContrast;
            color.postExposure.value = 0.15f;
            color.colorFilter.value = baseFilter;

            white = profile.Add<WhiteBalance>(true);
            white.temperature.value = -6f;
            white.tint.value = 4f;

            lens = profile.Add<LensDistortion>(true);
            lens.intensity.value = 0f;

            dof = profile.Add<DepthOfField>(true);
            dof.mode.value = DepthOfFieldMode.Gaussian;
            dof.gaussianStart.value = 26f;
            dof.gaussianEnd.value = 60f;
            dof.gaussianMaxRadius.value = 1.2f;
            dof.highQualitySampling.value = false;
            dof.active = DiormaDof && QualitySettings.GetQualityLevel() >= 2;
        }

        // ------------------------------------------------------------------ API
        public void ChromaticPunch(float amount) => chromaPunch = Mathf.Max(chromaPunch, amount);
        public void DamagePulse(float amount) => damagePulse = Mathf.Max(damagePulse, amount);
        public void AbilityFocus(float amount) => abilityTarget = amount;
        public void SetRage(bool on) => rageTarget = on ? 1f : 0f;
        public void ShadowInstant() => shadowInstant = 1f;
        public void Finisher(bool on) => finisherTarget = on ? 1f : 0f;
        public void WhiteFlash(float amount) => Game.UI?.ScreenFlash(new Color(1f, 0.97f, 0.9f, amount), 0.35f);

        /// <summary>Distancia focal de la cámara (para el desenfoque de fondo tipo diorama).</summary>
        public void SetFocusDistance(float d)
        {
            if (dof == null) return;
            dof.gaussianStart.value = d + 8f;
            dof.gaussianEnd.value = d + 38f;
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime;
            chromaPunch = Mathf.MoveTowards(chromaPunch, 0f, dt * 2.5f);
            damagePulse = Mathf.MoveTowards(damagePulse, 0f, dt * 2.2f);
            shadowInstant = Mathf.MoveTowards(shadowInstant, 0f, dt * 0.9f);
            abilityFocus = Mathf.MoveTowards(abilityFocus, abilityTarget, dt * 4f);
            rageAmount = Mathf.MoveTowards(rageAmount, rageTarget, dt * 2f);
            finisher = Mathf.MoveTowards(finisher, finisherTarget, dt * 4f);
            var p = Game.Player;
            float lh = p != null && p.IsAlive ? Mathf.Clamp01((0.3f - p.Health01) / 0.3f) : 0f;
            lowHealth = Mathf.MoveTowards(lowHealth, lh, dt);

            // cámara lenta = mundo más frío y desaturado
            float slow = Game.Time != null ? 1f - Mathf.Clamp01(Game.Time.GameplayScale) : 0f;

            chroma.intensity.value = 0.04f + chromaPunch * 0.9f + abilityFocus * 0.35f + shadowInstant * 0.4f;
            lens.intensity.value = -0.18f * chromaPunch - 0.22f * abilityFocus - 0.12f * finisher;
            float pulse = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 6f);
            vignette.intensity.value = BaseVignette + damagePulse * 0.25f + abilityFocus * 0.18f + lowHealth * (0.12f + 0.06f * pulse) + finisher * 0.2f + shadowInstant * 0.15f;
            Color vc = new Color(0.02f, 0.02f, 0.06f);
            vc = Color.Lerp(vc, new Color(0.45f, 0.02f, 0.02f), Mathf.Max(damagePulse, lowHealth * 0.6f));
            vc = Color.Lerp(vc, new Color(0.35f, 0.12f, 0.0f), rageAmount * 0.6f);
            vignette.color.value = vc;
            color.saturation.value = BaseSaturation - slow * 45f - shadowInstant * 35f + rageAmount * 10f - finisher * 30f;
            color.contrast.value = BaseContrast + abilityFocus * 15f + finisher * 15f;
            Color filter = Color.Lerp(Color.white, new Color(1f, 0.86f, 0.75f), rageAmount * 0.6f);
            filter = Color.Lerp(filter, new Color(0.8f, 0.9f, 1.05f), shadowInstant * 0.6f);
            color.colorFilter.value = filter;
            bloom.intensity.value = 0.9f + rageAmount * 0.5f + chromaPunch * 0.8f;
        }
    }
}
