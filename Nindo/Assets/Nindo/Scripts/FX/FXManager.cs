using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.VFX;

namespace Nindo
{
    /// <summary>
    /// Punto único para todos los efectos visuales del combate. Combina los VFX Graph que hizo
    /// el equipo (parry, golpe, ejecución...) con partículas generadas por código y luces flash.
    /// Todo pasa por pools: nada se instancia/destruye en medio del combate.
    /// </summary>
    public class FXManager : MonoBehaviour
    {
        public ScreenFX Screen { get; private set; }

        GameObject sparksGold, sparksWhite, sparksRed, flashWhite, flashGold, flashRed, dust, smoke, smokeDark,
            leaves, petals, heal, rage, inward, splash, debris, embers, ink;
        readonly Dictionary<VisualEffectAsset, GameObject> vfxTemplates = new Dictionary<VisualEffectAsset, GameObject>();
        readonly List<AfterImage> afterImages = new List<AfterImage>();
        int afterIndex;
        Light[] flashLights;
        int flashIndex;

        void Awake()
        {
            Game.FX = this;
            Screen = gameObject.AddComponent<ScreenFX>();
            BuildTemplates();
            flashLights = new Light[4];
            for (int i = 0; i < flashLights.Length; i++)
            {
                var go = new GameObject("FlashLight" + i);
                go.transform.SetParent(transform, false);
                var l = go.AddComponent<Light>();
                l.type = LightType.Point; l.shadows = LightShadows.None; l.enabled = false;
                flashLights[i] = l;
                go.AddComponent<FlashLightFade>();
            }
        }

        void OnDestroy() { if (Game.FX == this) Game.FX = null; }

        void BuildTemplates()
        {
            sparksGold = FXFactory.Sparks(new Color(1f, 0.85f, 0.4f), 16, 26, 11f, "SparksGold");
            sparksWhite = FXFactory.Sparks(new Color(0.85f, 0.95f, 1f), 10, 16, 9f, "SparksWhite");
            sparksRed = FXFactory.Sparks(new Color(1f, 0.35f, 0.25f), 12, 20, 9f, "SparksRed");
            flashWhite = FXFactory.FlashSprite(new Color(1f, 1f, 1f, 0.9f), 1.8f, 0.09f, "FlashWhite");
            flashGold = FXFactory.FlashSprite(new Color(1f, 0.85f, 0.45f, 0.9f), 2.6f, 0.13f, "FlashGold");
            flashRed = FXFactory.FlashSprite(new Color(1f, 0.25f, 0.2f, 0.8f), 2.2f, 0.18f, "FlashRed");
            dust = FXFactory.Puff(new Color(0.65f, 0.58f, 0.48f, 0.45f), 6, 0.7f, 0.6f, 1.2f, false, "Dust");
            smoke = FXFactory.Puff(new Color(0.72f, 0.72f, 0.8f, 0.55f), 10, 1.3f, 1.1f, 1.4f, false, "Smoke", -0.15f);
            smokeDark = FXFactory.Puff(new Color(0.2f, 0.15f, 0.28f, 0.7f), 12, 1.4f, 1.2f, 1.6f, false, "SmokeDark", -0.2f);
            leaves = FXFactory.Leaves(new Color(0.4f, 0.75f, 0.35f), new Color(0.75f, 0.9f, 0.4f), 40, 2.5f, 1.2f, "Leaves");
            petals = FXFactory.Leaves(new Color(1f, 0.7f, 0.8f), new Color(1f, 0.88f, 0.92f), 30, 1.5f, 1.4f, "Petals");
            heal = FXFactory.Rising(new Color(0.6f, 1f, 0.6f), new Color(1f, 0.95f, 0.5f), 18, 0.5f, 0.9f, "Heal");
            rage = FXFactory.Rising(new Color(1f, 0.5f, 0.15f), new Color(1f, 0.85f, 0.3f), 40, 0.8f, 1.2f, "RageEmbers");
            embers = FXFactory.Rising(new Color(1f, 0.6f, 0.2f), new Color(1f, 0.3f, 0.1f), 14, 0.4f, 0.8f, "Embers");
            inward = FXFactory.Inward(new Color(1f, 0.86f, 0.45f), 30, 2.2f, 0.45f, "Charge");
            splash = FXFactory.Sparks(new Color(0.7f, 0.95f, 1f), 18, 26, 6f, "Splash");
            debris = FXFactory.Puff(new Color(0.45f, 0.42f, 0.4f, 0.9f), 10, 0.25f, 0.9f, 6f, false, "Debris", 1.4f);
            ink = FXFactory.Sparks(new Color(0.12f, 0.08f, 0.1f), 8, 12, 6f, "InkFlecks");
            ink.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
        }

        // ------------------------------------------------------------------ helpers
        GameObject Emit(GameObject template, Vector3 pos, Quaternion rot, float life = 2f, float scale = 1f)
        {
            if (template == null) return null;
            var go = Pool.Spawn(template, pos, rot);
            go.transform.localScale = Vector3.one * scale;
            var ps = go.GetComponent<ParticleSystem>();
            if (ps != null) { ps.Clear(true); ps.Play(true); }
            Pool.Despawn(go, life);
            return go;
        }

        GameObject PlayVfx(VisualEffectAsset asset, Vector3 pos, Quaternion rot, float life = 2.5f)
        {
            if (asset == null) return null;
            if (!vfxTemplates.TryGetValue(asset, out var tpl) || tpl == null)
            {
                tpl = new GameObject("VFX_" + asset.name);
                tpl.transform.SetParent(FXFactory.TemplatesRoot, false);
                var v = tpl.AddComponent<VisualEffect>();
                v.visualEffectAsset = asset;
                vfxTemplates[asset] = tpl;
            }
            var go = Pool.Spawn(tpl, pos, rot);
            var vfx = go.GetComponent<VisualEffect>();
            if (vfx != null) { vfx.Reinit(); vfx.Play(); }
            Pool.Despawn(go, life);
            return go;
        }

        public void FlashLight(Vector3 pos, Color c, float intensity, float range, float duration)
        {
            var l = flashLights[flashIndex];
            flashIndex = (flashIndex + 1) % flashLights.Length;
            l.transform.position = pos;
            l.color = c; l.range = range; l.intensity = intensity;
            l.enabled = true;
            l.GetComponent<FlashLightFade>().Begin(intensity, duration);
        }

        static Quaternion Dir(Vector3 d) => d.sqrMagnitude > 0.001f ? Quaternion.LookRotation(d) : Quaternion.identity;
        NindoContent C => Game.Content;

        // ------------------------------------------------------------------ combate
        public void HitImpact(Vector3 p, Vector3 dir, bool heavy, bool rageMode)
        {
            Emit(rageMode ? sparksRed : sparksGold, p, Dir(dir));
            Emit(heavy ? flashGold : flashWhite, p, Quaternion.identity, 0.3f, heavy ? 1.2f : 0.8f);
            Emit(ink, p, Dir(dir), 1f);
            if (rageMode) Emit(embers, p, Quaternion.identity);
            if (C != null) PlayVfx(heavy ? C.vfxImpact : C.vfxHit, p, Dir(dir));
            FlashLight(p, rageMode ? new Color(1f, 0.5f, 0.2f) : new Color(1f, 0.85f, 0.6f), heavy ? 6f : 3.5f, 5f, 0.12f);
        }

        public void Clash(Vector3 p, Vector3 dir, bool big)
        {
            Emit(sparksWhite, p, Dir(dir));
            Emit(sparksGold, p, Dir(-dir));
            Emit(flashWhite, p, Quaternion.identity, 0.3f, big ? 1.4f : 0.9f);
            FlashLight(p, new Color(0.85f, 0.9f, 1f), big ? 7f : 4f, 6f, 0.15f);
        }

        public void ParryFlash(Vector3 p, bool perfect)
        {
            if (C != null) PlayVfx(C.vfxParry, p, Quaternion.identity);
            Emit(flashGold, p, Quaternion.identity, 0.3f, perfect ? 1.8f : 1.1f);
            RingWave.Spawn(new Vector3(p.x, Game.Player != null ? Game.Player.transform.position.y : p.y, p.z), perfect ? 3.5f : 2.2f, new Color(1f, 0.85f, 0.45f, 0.8f), 0.35f);
            if (perfect) { Emit(inward, p, Quaternion.identity, 0.6f, 0.6f); FlashLight(p, new Color(1f, 0.9f, 0.6f), 10f, 9f, 0.25f); }
        }

        public void PlayerHurt(Vector3 p, Vector3 dir, bool heavy)
        {
            Emit(sparksRed, p, Dir(dir));
            Emit(flashRed, p, Quaternion.identity, 0.3f, heavy ? 1.2f : 0.8f);
            if (C != null) PlayVfx(C.vfxDamaged, p, Dir(dir));
        }

        public void DashBurst(Vector3 pos, Vector3 dir)
        {
            Emit(dust, pos + Vector3.up * 0.1f, Dir(-dir));
            if (C != null) PlayVfx(C.vfxLines, pos + Vector3.up * 0.8f, Dir(dir), 1.2f);
        }

        public void DodgeSpark(Vector3 p) => Emit(sparksWhite, p, Quaternion.identity, 0.6f, 0.6f);

        public void AfterImages(Transform model, float duration, float interval, bool hot)
        {
            StartCoroutine(AfterImageRoutine(model, duration, interval, hot));
        }

        IEnumerator AfterImageRoutine(Transform model, float duration, float interval, bool hot)
        {
            var smrs = model.GetComponentsInChildren<SkinnedMeshRenderer>();
            float t = 0f;
            Color c = hot ? new Color(1f, 0.55f, 0.2f, 0.45f) : new Color(1f, 0.88f, 0.5f, 0.4f);
            while (t < duration && model != null)
            {
                foreach (var smr in smrs)
                {
                    if (smr == null || !smr.enabled) continue;
                    var a = NextAfterImage();
                    a.Bake(smr, c, 0.3f);
                }
                yield return new WaitForSeconds(interval);
                t += interval;
            }
        }

        AfterImage NextAfterImage()
        {
            if (afterImages.Count < 24)
            {
                var a = AfterImage.Create();
                a.transform.SetParent(transform, false);
                afterImages.Add(a);
                return a;
            }
            afterIndex = (afterIndex + 1) % afterImages.Count;
            return afterImages[afterIndex];
        }

        public void SlashLine(Vector3 a, Vector3 b)
        {
            SlashLineFX.Spawn(a, b, new Color(1f, 0.95f, 0.8f, 1f), 0.45f, 0.4f);
            SlashLineFX.Spawn(a, b, new Color(1f, 0.6f, 0.25f, 0.8f), 0.9f, 0.25f);
        }

        public void Execution(Vector3 p, Vector3 dir)
        {
            if (C != null) PlayVfx(C.vfxSlay, p, Dir(dir), 3f);
            Emit(sparksGold, p, Dir(dir), 1f, 1.5f);
            Emit(sparksRed, p, Dir(-dir), 1f, 1.3f);
            Emit(flashGold, p, Quaternion.identity, 0.4f, 2.2f);
            Emit(ink, p, Dir(dir), 1.2f, 1.8f);
            Emit(petals, p, Quaternion.identity, 2f, 1.2f);
            RingWave.Spawn(p - Vector3.up * 0.8f, 5f, new Color(1f, 0.8f, 0.5f, 0.9f), 0.5f);
            FlashLight(p, new Color(1f, 0.85f, 0.55f), 14f, 10f, 0.35f);
        }

        public void AbilityCharge(Vector3 pos, bool whirl)
        {
            Emit(inward, pos + Vector3.up, Quaternion.identity, 0.8f);
            if (C != null) PlayVfx(C.vfxAura, pos, Quaternion.identity, 1.5f);
            FlashLight(pos + Vector3.up, new Color(1f, 0.85f, 0.45f), 5f, 6f, 0.5f);
        }

        public void Whirlwind(Vector3 pos, float radius, float duration)
        {
            Emit(leaves, pos + Vector3.up * 0.3f, Quaternion.identity, duration + 1.5f, radius / 2.5f);
            Emit(petals, pos + Vector3.up * 0.6f, Quaternion.identity, duration + 1.5f, radius / 3f);
            RingWave.Spawn(pos, radius, new Color(0.8f, 1f, 0.7f, 0.6f), duration);
            Emit(dust, pos, Quaternion.identity, 1.2f, 1.5f);
        }

        public void HealBurst(Vector3 pos) => Emit(heal, pos + Vector3.up * 0.2f, Quaternion.identity, 1.5f);

        public void RageBurst(Vector3 pos)
        {
            Emit(rage, pos, Quaternion.identity, 2f);
            RingWave.Spawn(pos, 4.5f, new Color(1f, 0.5f, 0.2f, 0.9f), 0.5f);
            FlashLight(pos + Vector3.up, new Color(1f, 0.5f, 0.2f), 10f, 8f, 0.6f);
        }

        // ------------------------------------------------------------------ enemigos
        public void BladeGlint(Vector3 p, bool danger)
        {
            Emit(danger ? flashRed : flashWhite, p, Quaternion.identity, 0.3f, danger ? 0.9f : 0.5f);
        }

        public void DangerTelegraph(Enemy e)
        {
            Emit(flashRed, e.AimPoint + Vector3.up * 0.6f, Quaternion.identity, 0.4f, 1.6f);
            FlashLight(e.AimPoint, new Color(1f, 0.2f, 0.15f), 6f, 6f, 0.4f);
        }

        public void Exhausted(Enemy e)
        {
            Emit(sparksGold, e.AimPoint + Vector3.up * 0.4f, Quaternion.Euler(-90, 0, 0), 1f, 0.7f);
        }

        public void PostureBreak(Vector3 p)
        {
            Emit(flashGold, p, Quaternion.identity, 0.4f, 2.4f);
            Emit(sparksGold, p, Quaternion.Euler(-90, 0, 0), 1f, 1.6f);
            RingWave.Spawn(p - Vector3.up, 3.5f, new Color(1f, 0.85f, 0.4f, 0.9f), 0.4f);
            FlashLight(p, new Color(1f, 0.85f, 0.4f), 8f, 7f, 0.3f);
        }

        public void EnemyDeath(Vector3 p, Vector3 dir, bool finisher)
        {
            Emit(ink, p, Dir(dir), 1.2f, finisher ? 1.8f : 1.2f);
            Emit(sparksGold, p, Dir(dir), 1f, 1.2f);
        }

        public void SmokePuff(Vector3 p, float size)
        {
            Emit(smoke, p, Quaternion.identity, 1.8f, size);
        }

        // ------------------------------------------------------------------ jefes
        public void Shockwave(Vector3 pos, float radius, Color c)
        {
            RingWave.Spawn(pos, radius, c, 0.5f);
            RingWave.Spawn(pos, radius * 0.6f, c, 0.35f);
            Emit(dust, pos, Quaternion.identity, 1.5f, radius * 0.5f);
            FlashLight(pos + Vector3.up, c, 8f, radius * 2f, 0.3f);
        }

        public void GroundCrack(Vector3 pos, float radius)
        {
            Emit(debris, pos, Quaternion.Euler(-90, 0, 0), 1.6f, radius * 0.4f);
        }

        float lastDustTrail;
        public void DustTrail(Vector3 pos)
        {
            if (Time.time - lastDustTrail < 0.08f) return;
            lastDustTrail = Time.time;
            Emit(dust, pos, Quaternion.identity, 1f, 0.8f);
        }

        public void Splash(Vector3 pos)
        {
            Emit(splash, pos, Quaternion.Euler(-90, 0, 0), 1f);
            Emit(flashWhite, pos, Quaternion.identity, 0.3f, 0.8f);
        }

        GameObject waveTemplate;
        /// <summary>Visual de la ola de Mizuchi (se reutiliza con Pool).</summary>
        public GameObject MakeWave(Vector3 pos, Vector3 dir)
        {
            if (waveTemplate == null)
            {
                var ps = FXFactory.NewSystem("Wave");
                var m = ps.main;
                m.loop = true; m.duration = 1f;
                m.startLifetime = 0.35f; m.startSpeed = new ParticleSystem.MinMaxCurve(0.5f, 2f);
                m.startSize = new ParticleSystem.MinMaxCurve(0.2f, 0.5f);
                m.startColor = new ParticleSystem.MinMaxGradient(new Color(0.6f, 0.95f, 1f, 0.9f), new Color(0.3f, 0.7f, 0.95f, 0.8f));
                m.simulationSpace = ParticleSystemSimulationSpace.World;
                var em = ps.emission; em.rateOverTime = 90f;
                var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.SingleSidedEdge; sh.radius = 0.9f;
                var lg = new GameObject("Glow"); lg.transform.SetParent(ps.transform, false);
                var l = lg.AddComponent<Light>(); l.type = LightType.Point; l.color = new Color(0.4f, 0.85f, 1f); l.range = 4f; l.intensity = 3f; l.shadows = LightShadows.None;
                waveTemplate = ps.gameObject;
            }
            var go = Pool.Spawn(waveTemplate, pos, Dir(dir));
            go.GetComponent<ParticleSystem>()?.Play(true);
            return go;
        }

        public void Petals(Vector3 pos, float scale = 1f) => Emit(petals, pos, Quaternion.identity, 2f, scale);
        public void Embers(Vector3 pos) => Emit(embers, pos, Quaternion.identity, 1.2f);
        public void Dust(Vector3 pos, float scale = 1f) => Emit(dust, pos, Quaternion.identity, 1.2f, scale);
        public void PortalBurst(Vector3 pos)
        {
            Emit(inward, pos, Quaternion.identity, 1f, 1.2f);
            Emit(flashWhite, pos, Quaternion.identity, 0.4f, 2.5f);
            FlashLight(pos, new Color(0.5f, 0.85f, 1f), 10f, 10f, 0.5f);
        }
        public void SealGlow(Vector3 pos)
        {
            Emit(rage, pos, Quaternion.identity, 2f, 0.6f);
            Emit(flashGold, pos, Quaternion.identity, 0.5f, 2f);
            FlashLight(pos, new Color(1f, 0.85f, 0.45f), 10f, 8f, 0.8f);
        }
    }

    public class FlashLightFade : MonoBehaviour
    {
        Light l; float start, dur = 1f, t;
        // arranca apagado: Update solo corre entre Begin() y el final del fundido
        void Awake() { l = GetComponent<Light>(); enabled = false; }
        public void Begin(float intensity, float duration) { if (l == null) l = GetComponent<Light>(); start = intensity; dur = Mathf.Max(0.01f, duration); t = 0f; enabled = true; }
        void Update()
        {
            t += Time.unscaledDeltaTime;
            float k = t / dur;
            l.intensity = start * (1f - k) * (1f - k);
            if (k >= 1f) { l.enabled = false; enabled = false; }
        }
    }
}
