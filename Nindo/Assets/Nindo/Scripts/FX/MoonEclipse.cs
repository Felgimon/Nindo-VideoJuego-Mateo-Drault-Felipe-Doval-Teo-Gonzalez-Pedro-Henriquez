using System.Collections;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// La luna de la pelea final. Maneja la luz direccional (la "luna"), la niebla y el ambiente de la arena:
    ///  - EnterArena: la luna gira al norte (detrás del dojo) para que todas las sombras caigan hacia la cámara, como la
    ///    sombra viva de Kokuyō. Alta (62°): las sombras reales quedan cortas y el dojo no tapa medio patio.
    ///  - Eclipse: Kokuyō cierra el puño sobre la luna: 1.05 -> 0.35 (nunca menos: la noche se tiene que seguir leyendo),
    ///    niebla violeta #1e1430, ambiente apagado y el disco de tinta tapa la luna del cielo.
    ///  - ParryPulse: cada parry del Acto 3 le devuelve un instante la luz a la escena ("el parry ilumina").
    ///  - MoonReturn: al caer Kokuyō la luna vuelve de golpe (1.4 -> 1.05 en 3 s) y caen pétalos sobre el patio.
    ///  - ExitArena / ResetAll: deja todo como lo encontró (reintentos y salida).
    /// El disco visible es un quad lejano (Nindo/Moon) que sigue a la cámara; la luna del cielo se esconde mientras
    /// tanto (copia del material del cielo: el asset nunca se toca).
    /// </summary>
    public class MoonEclipse : MonoBehaviour
    {
        /// <summary>Luz de la arena: viaja hacia el sur (la cámara) y hacia abajo.</summary>
        public static readonly Quaternion ArenaRotation = Quaternion.Euler(62f, 180f, 0f);
        /// <summary>Dónde se ve la luna en el cielo: al norte, apenas al este, 30° sobre el horizonte (entra en la toma de abajo de la presentación).</summary>
        public static readonly Vector3 SkyDirection = new Vector3(0.16f, 0.5f, 0.85f).normalized;
        public static readonly Color EclipseFog = new Color(0.118f, 0.078f, 0.188f);     // #1e1430
        public const float EclipseIntensity = 0.35f;

        struct Look
        {
            public Quaternion rot;
            public float intensity, fogDensity;
            public Color color, fog, sky, equator, ground;

            public static Look Lerp(Look a, Look b, float t) => new Look
            {
                rot = Quaternion.Slerp(a.rot, b.rot, t), intensity = Mathf.Lerp(a.intensity, b.intensity, t),
                fogDensity = Mathf.Lerp(a.fogDensity, b.fogDensity, t), color = Color.Lerp(a.color, b.color, t),
                fog = Color.Lerp(a.fog, b.fog, t), sky = Color.Lerp(a.sky, b.sky, t), equator = Color.Lerp(a.equator, b.equator, t),
                ground = Color.Lerp(a.ground, b.ground, t),
            };
        }

        static readonly int IdEclipse = Shader.PropertyToID("_Eclipse"), IdVeil = Shader.PropertyToID("_Veil"),
            IdFlash = Shader.PropertyToID("_Flash"), IdAlpha = Shader.PropertyToID("_Alpha"),
            IdMoonGlow = Shader.PropertyToID("_MoonGlow"), IdMoonSize = Shader.PropertyToID("_MoonSize");

        public bool InArena { get; private set; }
        /// <summary>Volviendo a la luz de exploración (ExitArena en curso).</summary>
        public bool Exiting { get; private set; }
        public bool Eclipsed { get; private set; }
        public Light Sun => sun;

        Light sun;
        Look explore, arena, current;
        Coroutine tween;
        float boost, boostLen = 0.25f;
        Transform disc;
        Material discMat, skyOriginal, skyCopy;
        float eclipse, eclipseFrom, eclipseTo, eclipseT = 1f, eclipseDur;
        float veil, veilFrom, veilTo, veilT = 1f, veilDur;
        float discAlpha, discAlphaTarget, flash;
        ParticleSystem petals;
        Vector3 arenaCenter;

        public static MoonEclipse Create(Transform parent, Vector3 arenaCenter)
        {
            var go = new GameObject("LunaDeLaArena");
            go.transform.SetParent(parent, false);
            var m = go.AddComponent<MoonEclipse>();
            m.arenaCenter = arenaCenter;
            return m;
        }

        void Awake()
        {
            var sh = Resources.Load<Shader>("Shaders/NindoMoon");
            if (sh != null && sh.isSupported)
            {
                discMat = new Material(sh) { name = "Nindo_ArenaMoon" };
                var q = new GameObject("DiscoLunar");
                q.transform.SetParent(transform, false);
                q.AddComponent<MeshFilter>().sharedMesh = Quad();
                var mr = q.AddComponent<MeshRenderer>();
                mr.sharedMaterial = discMat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = false;
                mr.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off;
                disc = q.transform;
                disc.gameObject.SetActive(false);
            }
            petals = MakePetals();
        }

        void OnDestroy()
        {
            RestoreSky();
            if (discMat != null) Destroy(discMat);
        }

        static Mesh Quad()
        {
            var m = new Mesh { name = "QuadLuna" };
            m.vertices = new[] { new Vector3(-1, -1, 0), new Vector3(1, -1, 0), new Vector3(1, 1, 0), new Vector3(-1, 1, 0) };
            m.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) };
            m.triangles = new[] { 0, 2, 1, 0, 3, 2 };
            m.RecalculateBounds();
            return m;
        }

        ParticleSystem MakePetals()
        {
            var ps = FXFactory.NewSystem("Petalos", transform);
            var m = ps.main;
            m.loop = true; m.duration = 4f; m.playOnAwake = false;
            m.startLifetime = new ParticleSystem.MinMaxCurve(5f, 8f);
            m.startSpeed = new ParticleSystem.MinMaxCurve(0.2f, 0.6f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.09f, 0.18f);
            m.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 0.72f, 0.82f), new Color(1f, 0.9f, 0.93f));
            m.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
            m.gravityModifier = 0.03f;
            m.maxParticles = 400;
            var em = ps.emission; em.rateOverTime = 0f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(34f, 1f, 34f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.8f; noise.frequency = 0.25f; noise.scrollSpeed = 0.3f;
            var rot = ps.rotationOverLifetime; rot.enabled = true; rot.z = new ParticleSystem.MinMaxCurve(-3f, 3f);
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(-0.4f, 0.6f); vel.y = new ParticleSystem.MinMaxCurve(-1.1f, -0.7f); vel.z = new ParticleSystem.MinMaxCurve(-0.6f, -0.2f);
            var col = ps.colorOverLifetime; col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.1f), new GradientAlphaKey(1f, 0.85f), new GradientAlphaKey(0f, 1f) });
            col.color = g;
            ps.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
            ps.transform.position = arenaCenter + Vector3.up * 13f;
            return ps;
        }

        // ================================================================== API
        /// <summary>La luna gira detrás del dojo (las sombras caen hacia la cámara) y aparece su disco en el cielo.</summary>
        public void EnterArena(float seconds = 2f)
        {
            if (!FindSun()) return;
            if (!InArena)
            {
                explore = Capture();
                arena = explore;
                arena.rot = ArenaRotation;
                current = explore;
                InArena = true;
                HideSky();
            }
            Eclipsed = false;
            Exiting = false;
            TweenTo(arena, seconds);
            discAlphaTarget = 1f;
        }

        /// <summary>El eclipse: la luz baja a 0.35, niebla violeta, ambiente apagado y la tinta tapa la luna.</summary>
        public void Eclipse(float seconds = 2f)
        {
            if (!InArena) EnterArena(0f);
            if (sun == null) return;
            Eclipsed = true;
            var e = arena;
            e.intensity = EclipseIntensity;
            e.color = Color.Lerp(arena.color, new Color(0.62f, 0.52f, 1f), 0.5f);
            e.fog = EclipseFog;
            e.fogDensity = arena.fogDensity * 1.15f;
            // ambiente violeta y más bajo: lo que ilumina ahora es la bandana, los faroles de piedra y cada parry
            e.sky = Color.Lerp(arena.sky, new Color(0.11f, 0.08f, 0.2f), 0.65f);
            e.equator = Color.Lerp(arena.equator, new Color(0.07f, 0.05f, 0.12f), 0.65f);
            e.ground = arena.ground * 0.75f;
            TweenTo(e, seconds);
            EclipseTo(1f, seconds);
        }

        /// <summary>La luna vuelve (Kokuyō cae): golpe de luz a 1.4 que se asienta en 1.05 en 'settle' s, sin tinta, y pétalos.</summary>
        public void MoonReturn(float settle = 3f, float petalSeconds = 9f)
        {
            if (!InArena) EnterArena(0f);
            if (sun == null) return;
            Eclipsed = false;
            EclipseTo(0f, 0.35f);
            flash = 1.5f;
            current = Look.Lerp(current, arena, 1f);
            current.intensity = arena.intensity * (1.4f / 1.05f);
            Apply(current);
            TweenTo(arena, settle);
            Petals(petalSeconds);
        }

        /// <summary>La luna vuelve a su lugar de siempre (fin de la pelea o reintento) en 'seconds'.</summary>
        public void ExitArena(float seconds = 2f)
        {
            if (!InArena || Exiting) return;
            Exiting = true;
            Eclipsed = false;
            EclipseTo(0f, Mathf.Min(seconds, 0.5f));
            discAlphaTarget = 0f;
            if (tween != null) StopCoroutine(tween);
            tween = StartCoroutine(ExitRoutine(seconds));
        }

        IEnumerator ExitRoutine(float seconds)
        {
            yield return TweenRoutine(explore, seconds);
            InArena = false;
            Exiting = false;
            RestoreSky();
            tween = null;
        }

        /// <summary>Todo como estaba, ya (Kaito murió: el reintento empieza con la noche de siempre).</summary>
        public void ResetAll()
        {
            if (tween != null) { StopCoroutine(tween); tween = null; }
            if (InArena && sun != null) Apply(explore);
            InArena = false;
            Exiting = false;
            Eclipsed = false;
            eclipse = eclipseTo = 0f; eclipseT = 1f;
            veil = veilTo = 0f; veilT = 1f;
            discAlpha = discAlphaTarget = 0f;
            flash = boost = 0f;
            if (disc != null) disc.gameObject.SetActive(false);
            if (petals != null) petals.Clear();
            RestoreSky();
        }

        /// <summary>
        /// El parry le devuelve la luz a la escena: destello blanco-azulado en el choque (10, 26 m, 0.25 s), la luna
        /// sube un instante y el disco brilla. Pensado para el Acto 3 (en el eclipse cada parry es un relámpago).
        /// </summary>
        public void ParryPulse(Vector3 at, bool perfect)
        {
            Game.FX?.FlashLight(at + Vector3.up * 2f, new Color(0.78f, 0.88f, 1f), perfect ? 10f : 7f, 26f, 0.25f);
            boost = Mathf.Max(boost, perfect ? 0.9f : 0.6f);
            boostLen = 0.25f;
            flash = Mathf.Max(flash, perfect ? 1f : 0.6f);
        }

        /// <summary>Nubes delante del disco (1 = tapada): en la presentación "la luna rompe las nubes" con SetVeil(0, 1.5).</summary>
        public void SetVeil(float amount, float seconds)
        {
            veilFrom = veil; veilTo = Mathf.Clamp01(amount); veilDur = Mathf.Max(0f, seconds); veilT = veilDur > 0f ? 0f : 1f;
            if (veilDur <= 0f) veil = veilTo;
        }

        /// <summary>Pétalos que caen sobre el patio durante 'seconds' (el final, el lazo recuperado).</summary>
        public void Petals(float seconds)
        {
            if (petals == null) return;
            petals.transform.position = arenaCenter + Vector3.up * 13f;
            StartCoroutine(PetalRoutine(seconds));
        }

        IEnumerator PetalRoutine(float seconds)
        {
            var em = petals.emission;
            em.rateOverTime = 45f;
            if (!petals.isPlaying) petals.Play();
            yield return new WaitForSecondsRealtime(seconds);
            em.rateOverTime = 0f;
        }

        // ================================================================== luz
        bool FindSun()
        {
            if (sun != null) return true;
            sun = RenderSettings.sun;
            if (sun == null)
                foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None))
                    if (l.type == LightType.Directional) { sun = l; break; }
            return sun != null;
        }

        Look Capture() => new Look
        {
            rot = sun.transform.rotation, intensity = sun.intensity, color = sun.color,
            fog = RenderSettings.fogColor, fogDensity = RenderSettings.fogDensity,
            sky = RenderSettings.ambientSkyColor, equator = RenderSettings.ambientEquatorColor, ground = RenderSettings.ambientGroundColor,
        };

        void Apply(Look l)
        {
            current = l;
            sun.transform.rotation = l.rot;
            sun.intensity = l.intensity + boost;
            sun.color = l.color;
            RenderSettings.fogColor = l.fog;
            RenderSettings.fogDensity = l.fogDensity;
            RenderSettings.ambientSkyColor = l.sky;
            RenderSettings.ambientEquatorColor = l.equator;
            RenderSettings.ambientGroundColor = l.ground;
        }

        void TweenTo(Look to, float seconds)
        {
            if (tween != null) StopCoroutine(tween);
            tween = StartCoroutine(TweenRoutine(to, seconds));
        }

        IEnumerator TweenRoutine(Look to, float seconds)
        {
            Look from = current;
            float t = 0f;
            while (t < seconds)
            {
                // tiempo real: los cambios de fase pasan en cámara lenta
                t += Time.unscaledDeltaTime;
                Apply(Look.Lerp(from, to, Mathf.SmoothStep(0f, 1f, t / seconds)));
                yield return null;
            }
            Apply(to);
            tween = null;
        }

        void EclipseTo(float v, float seconds)
        {
            eclipseFrom = eclipse; eclipseTo = v; eclipseDur = Mathf.Max(0f, seconds); eclipseT = eclipseDur > 0f ? 0f : 1f;
            if (eclipseDur <= 0f) eclipse = v;
        }

        void HideSky()
        {
            if (skyCopy != null || RenderSettings.skybox == null || discMat == null) return;
            skyOriginal = RenderSettings.skybox;
            skyCopy = new Material(skyOriginal) { name = skyOriginal.name + "_SinLuna" };
            if (skyCopy.HasProperty(IdMoonGlow)) skyCopy.SetFloat(IdMoonGlow, 0f);
            if (skyCopy.HasProperty(IdMoonSize)) skyCopy.SetFloat(IdMoonSize, 0.0001f);
            RenderSettings.skybox = skyCopy;
        }

        void RestoreSky()
        {
            if (skyCopy == null) return;
            if (RenderSettings.skybox == skyCopy) RenderSettings.skybox = skyOriginal;
            Destroy(skyCopy);
            skyCopy = null;
        }

        void LateUpdate()
        {
            float udt = Time.unscaledDeltaTime;
            if (sun != null && InArena)
            {
                boost = Mathf.Max(0f, boost - udt / boostLen);
                sun.intensity = current.intensity + boost;
            }
            if (eclipseT < 1f) { eclipseT = Mathf.Clamp01(eclipseT + udt / eclipseDur); eclipse = Mathf.Lerp(eclipseFrom, eclipseTo, Mathf.SmoothStep(0f, 1f, eclipseT)); }
            if (veilT < 1f) { veilT = Mathf.Clamp01(veilT + udt / veilDur); veil = Mathf.Lerp(veilFrom, veilTo, Mathf.SmoothStep(0f, 1f, veilT)); }
            flash = Mathf.Max(0f, flash - udt * 4f);
            discAlpha = Mathf.MoveTowards(discAlpha, discAlphaTarget, udt * 0.8f);
            if (disc == null) return;
            bool show = discAlpha > 0.001f;
            if (disc.gameObject.activeSelf != show) disc.gameObject.SetActive(show);
            var cam = Game.Camera != null ? Game.Camera.Cam : Camera.main;
            if (!show || cam == null) return;
            // un objeto "infinitamente lejos": sigue a la cámara, siempre a la misma distancia y de frente
            float dist = Mathf.Min(340f, cam.farClipPlane * 0.85f);
            Vector3 ct = cam.transform.position;
            disc.position = ct + SkyDirection * dist;
            disc.rotation = Quaternion.LookRotation(disc.position - ct);
            float half = dist * Mathf.Tan(3.4f * Mathf.Deg2Rad) / 0.3f;
            disc.localScale = new Vector3(half, half, 1f);
            discMat.SetFloat(IdEclipse, eclipse);
            discMat.SetFloat(IdVeil, veil);
            discMat.SetFloat(IdFlash, flash);
            discMat.SetFloat(IdAlpha, discAlpha);
        }
    }
}
