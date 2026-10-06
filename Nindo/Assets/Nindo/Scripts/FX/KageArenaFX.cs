using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Los sistemas visuales del patio del dojo, la arena de Kokuyō (WorldBuilder lo agrega a la BossArena "kage"):
    /// braseros (Braziers), luna y eclipse (MoonEclipse), cuerdas de sombra del abuelo (ShadowRopes), la sombra viva
    /// del jefe (PlanarShadow) y la luz dorada de la bandana de Kaito (BandanaGlow).
    ///
    /// Cada momento de la pelea es un método ("beat") que arma todo junto: Intro, AttachShadow, ShadowTear, Eclipse,
    /// ParryLight, Finale y ResetArena. Mientras no exista la pelea guionada de Kokuyō, AutoDirect los dispara solo
    /// mirando al jefe actual (presentación, fase 1 -> sombra arrancada, fase 2 -> eclipse, derrota, muerte de Kaito):
    /// la pelea guionada pone AutoDirect = false y los llama en sus tiempos (KageArenaFX.Current).
    /// </summary>
    public class KageArenaFX : MonoBehaviour
    {
        public static KageArenaFX Current { get; private set; }

        /// <summary>Dispara los beats solo (con el jefe de hoy). La pelea guionada lo apaga.</summary>
        public bool AutoDirect = true;
        /// <summary>Radio del piso de losas: la sombra viva no se dibuja afuera (escaleras, pasto).</summary>
        public float FloorRadius = 19f;

        public Braziers Braziers { get; private set; }
        public MoonEclipse Moon { get; private set; }
        public ShadowRopes Ropes { get; private set; }
        public PlanarShadow Shadow { get; private set; }
        public BossArena Arena { get; private set; }
        public bool Ready { get; private set; }
        public Vector3 Center => transform.position;

        bool introDone, torn, eclipsed, finale;
        int skyShot = -1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatic() => Current = null;

        void Awake()
        {
            Current = this;
            Arena = GetComponent<BossArena>();
        }

        void OnEnable()
        {
            GameEvents.BossStarted += OnBossStarted;
            GameEvents.BossDefeated += OnBossDefeated;
            GameEvents.PlayerRespawned += OnRespawned;
            GameEvents.Parry += OnParry;
        }

        void OnDisable()
        {
            GameEvents.BossStarted -= OnBossStarted;
            GameEvents.BossDefeated -= OnBossDefeated;
            GameEvents.PlayerRespawned -= OnRespawned;
            GameEvents.Parry -= OnParry;
        }

        void OnDestroy() { if (Current == this) Current = null; }

        IEnumerator Start()
        {
            // los props, el abuelo y el jefe existen recién cuando el mundo terminó de armarse
            while (Game.World == null || !Game.World.Built) yield return null;
            var anchors = new List<Transform>();
            Transform post = null;
            float postD = 30f;
            foreach (var t in Game.World.WorldRoot.GetComponentsInChildren<Transform>(true))
            {
                if (t.name != "brazier_kage" && t.name != "binding_post") continue;
                float d = CombatMath.FlatDistance(t.position, Center);
                if (t.name == "brazier_kage" && d < FloorRadius + 4f) anchors.Add(t);
                else if (t.name == "binding_post" && d < postD) { post = t; postD = d; }
            }
            Braziers = Braziers.Create(transform, anchors, Center);
            Moon = MoonEclipse.Create(transform, Center);
            bool defeated = Game.Save.HasFlag(Flags.Boss("kage"));
            // vencido Kokuyō el patio queda en paz: braseros encendidos y el abuelo sin cuerdas
            Braziers.SetAll(defeated);
            var grandpa = Game.World.Point("npc_grandpa_dojo");
            if (!defeated) Ropes = ShadowRopes.Bind(post, grandpa, transform);
            Ready = true;
        }

        // ================================================================== beats
        /// <summary>
        /// Presentación: los braseros se encienden en ola desde el jefe y aparece la luna tapada por nubes. Si hay
        /// cinemática, 'skyShotDelay' s después (pasados el rugido y el título de StoryDirector.BossIntroRoutine) un
        /// plano al cielo muestra cómo la luna rompe las nubes sobre el techo del dojo; si no, las nubes se abren ya.
        /// Un valor negativo no toma la cámara (la pelea guionada puede usar Moon.PlaySkyShot en su momento).
        /// </summary>
        public void Intro(Transform boss, float skyShotDelay = 3.4f)
        {
            introDone = true;
            if (Moon != null)
            {
                Moon.SetVeil(1f, 0f);
                Moon.EnterArena(2f);
                if (skyShotDelay >= 0f && Game.InCutscene) StartCoroutine(IntroSky(skyShotDelay));
                else Moon.SetVeil(0f, 2.2f);
            }
            if (Braziers != null)
            {
                Braziers.SetStyle(FlameStyle.Fire, 0f);
                Braziers.IgniteFrom(boss != null ? boss.position : Center, 0.12f);
            }
        }

        IEnumerator IntroSky(float delay)
        {
            yield return new WaitForSecondsRealtime(delay);
            if (!Game.InCutscene) { Moon.SetVeil(0f, 1f); yield break; }
            const float blendIn = 1.0f, hold = 2.8f;
            skyShot = Moon.PlaySkyShot(hold, blendIn, 1.0f);
            // las nubes se abren cuando el plano ya llegó arriba
            yield return new WaitForSecondsRealtime(blendIn * 0.6f);
            Moon.SetVeil(0f, 2.0f);
            float t = 0f;
            while (t < hold + blendIn * 0.4f && skyShot >= 0)
            {
                // diálogo salteado: la pelea no arranca mirando al cielo
                if (!Game.InCutscene) { Game.Camera?.CancelShot(skyShot); break; }
                t += Time.unscaledDeltaTime;
                yield return null;
            }
            skyShot = -1;
        }

        /// <summary>La sombra viva del jefe (espejo de su pose; la pelea guionada la adelanta con Shadow.SampleAhead).</summary>
        public PlanarShadow AttachShadow(Boss boss)
        {
            if (Shadow != null || boss == null) return Shadow;
            var anim = boss.GetComponentInChildren<Animator>();
            Shadow = PlanarShadow.Create(anim, Center, FloorRadius);
            return Shadow;
        }

        /// <summary>
        /// La sombra arrancada (Acto 2): los braseros se vuelven violetas con un golpe de chispas y la sombra se suelta
        /// del cuerpo (Detach) y se para como figura de humo desde su punta, a ~60% de su largo hacia la cámara: se ve
        /// arrancarse (parada sobre el cuerpo lo pintaba entero de tinta). Sin la pelea guionada (que la convierte en
        /// Kage y la mueve por Shadow.Root) se desvanece: el cuerpo queda sin sombra, a propósito inquietante. Quien la
        /// levante por su cuenta tiene que soltarla igual (Detach) antes de RiseTo.
        /// </summary>
        public void ShadowTear(bool fadeShadow = true)
        {
            torn = true;
            if (Braziers != null) { Braziers.SetStyle(FlameStyle.Violet, 1f); Braziers.FlareAll(1f); }
            if (Shadow != null)
            {
                Shadow.Strike(0.3f);
                Shadow.Detach();
                Vector3 l = PlanarShadow.DefaultLight; l.y = 0f;
                Vector3 from = Shadow.Root.position;
                StartCoroutine(PeelShadow(Shadow, from, from + l.normalized * Shadow.Length * 0.6f, 0.8f));
                Shadow.RiseTo(1f, 0.8f);
                if (fadeShadow) StartCoroutine(FadeShadowLater(1.3f, 0.7f));
            }
            Game.Audio?.Play("shadow_tear", Shadow != null ? Shadow.Root.position : Center, 1f);
            Game.Camera?.Shake(0.6f);
        }

        /// <summary>La raíz de la sombra suelta viaja hasta la punta mientras se levanta (sale rápido y frena).</summary>
        IEnumerator PeelShadow(PlanarShadow s, Vector3 from, Vector3 to, float seconds)
        {
            float t = 0f;
            while (t < seconds && s != null && s.Detached)
            {
                t += Time.deltaTime;
                float k = 1f - Mathf.Pow(1f - Mathf.Clamp01(t / seconds), 3f);
                s.Root.position = Vector3.Lerp(from, to, k);
                yield return null;
            }
        }

        IEnumerator FadeShadowLater(float delay, float seconds)
        {
            yield return new WaitForSecondsRealtime(delay);
            if (Shadow != null) Shadow.FadeTo(0f, seconds);
        }

        /// <summary>El eclipse (Acto 3): braseros que se apagan uno por uno, la luna tapada y la bandana de Kaito dorada.</summary>
        public void Eclipse()
        {
            eclipsed = true;
            // en 2D: el eclipse no pasa en un punto del patio, le pasa a toda la noche
            Game.Audio?.Play("eclipse", null, 1f);
            if (Braziers != null) Braziers.ExtinguishAll(0.18f);
            if (Moon != null) Moon.Eclipse(2f);
            if (Shadow != null) Shadow.FadeTo(0f, 0.6f);
            BandanaGlow.Ensure(Game.Player)?.Enable(1.2f);
        }

        /// <summary>Un parry en la oscuridad le devuelve la luz a la escena y hace brillar la bandana.</summary>
        public void ParryLight(Vector3 at, bool perfect)
        {
            if (Moon != null) Moon.ParryPulse(at, perfect);
            var g = Game.Player != null ? Game.Player.GetComponent<BandanaGlow>() : null;
            if (g != null) g.Pulse(Color.white, perfect ? 1f : 0.6f);
        }

        /// <summary>
        /// Kokuyō cae. Con skyShot, pasado lo mejor del plano de su muerte (Boss.Die) un plano al cielo muestra la tinta
        /// escurriéndose de la luna: MoonReturn llega cuando el plano ya está arriba, así el golpe de luz se ve. Sin
        /// él, la luna vuelve en el acto. Después se encienden los braseros y las cuerdas del abuelo se deshacen a los
        /// ~4.4 s, ya en el plano del final de StoryDirector (Kaito y el abuelo): "está libre" se ve. Con ropesAt
        /// negativo las cuerdas quedan para quien arma el final (StoryDirector las suelta en su plano). skyAt corre el
        /// plano del cielo (y con él la luna y los braseros) para que no tape lo que pasa en el patio.
        /// </summary>
        public void Finale(bool skyShot = true, float ropesAt = 4.4f, float skyAt = 1.8f)
        {
            finale = true;
            if (Shadow != null) { Shadow.Release(); Shadow = null; }
            var g = Game.Player != null ? Game.Player.GetComponent<BandanaGlow>() : null;
            if (g != null) g.Disable(2.5f);
            StartCoroutine(FinaleRoutine(skyShot && Moon != null && Game.Camera != null, ropesAt, skyAt));
        }

        IEnumerator FinaleRoutine(bool sky, float ropesAt, float skyAt)
        {
            float t = 0f;
            if (sky)
            {
                const float blendIn = 0.6f;
                yield return new WaitForSecondsRealtime(skyAt);
                skyShot = Moon.PlaySkyShot(1.0f, blendIn, 0.8f);
                yield return new WaitForSecondsRealtime(blendIn);
                t = skyAt + blendIn;
            }
            if (Moon != null) Moon.MoonReturn(3f, 9f);
            // los braseros, 0.6 s después de que vuelve la luna (sin cielo, a los 3 s como siempre)
            yield return new WaitForSecondsRealtime(sky ? 0.6f : Mathf.Max(0f, 3.0f - t));
            if (Braziers != null) { Braziers.SetStyle(FlameStyle.Fire, 0f); Braziers.IgniteAll(0.25f, 0, true); }
            yield return new WaitForSecondsRealtime(1.4f);
            skyShot = -1;
            if (ropesAt < 0f) yield break;
            yield return new WaitForSecondsRealtime(Mathf.Max(0f, ropesAt - 4.4f));
            if (Ropes != null) Ropes.Dissolve(1.6f);
        }

        /// <summary>Todo como antes de la pelea (Kaito murió): braseros fríos, noche de siempre, abuelo atado, sin sombra viva.</summary>
        public void ResetArena()
        {
            introDone = torn = eclipsed = finale = false;
            StopAllCoroutines();
            if (skyShot >= 0) { Game.Camera?.CancelShot(skyShot); skyShot = -1; }
            if (Braziers != null) Braziers.SetAll(false);
            if (Moon != null) Moon.ResetAll();
            if (Ropes != null) Ropes.Restore();
            if (Shadow != null) { Shadow.Release(); Shadow = null; }
            var g = Game.Player != null ? Game.Player.GetComponent<BandanaGlow>() : null;
            if (g != null) g.Disable(0f);
        }

        // ================================================================== dirección automática (hasta la pelea guionada)
        Boss ActiveBoss => Arena != null ? Arena.Boss : null;

        void Update()
        {
            if (!Ready) return;
            // vencido Kokuyō, si Kaito sale del patio la luna vuelve a su lugar de siempre (si no, todo el mundo
            // seguiría con la luz girada al norte de la arena)
            if (Moon != null && Moon.InArena && Game.Player != null && (ActiveBoss == null || !ActiveBoss.Fighting)
                && CombatMath.FlatDistance(Game.Player.transform.position, Center) > FloorRadius + 14f)
                Moon.ExitArena(3f);
            if (!AutoDirect) return;
            var b = ActiveBoss;
            if (b == null || b.Defeated || finale) return;
            // la presentación arranca cuando Kaito cruza el radio de la arena y empieza la cinemática
            if (!introDone && Game.InCutscene && Game.Player != null && Arena != null
                && CombatMath.FlatDistance(Game.Player.transform.position, Center) < Arena.triggerRadius + 1.5f)
                Intro(b.transform);
            if (!b.Fighting) return;
            if (!torn && b.CurrentPhase >= 1) ShadowTear();
            if (!eclipsed && b.CurrentPhase >= 2) Eclipse();
        }

        void OnBossStarted(Boss b)
        {
            if (!AutoDirect || !Ready || b == null || b != ActiveBoss) return;
            if (!introDone) Intro(b.transform);
            if (!torn) AttachShadow(b);
        }

        void OnBossDefeated(Boss b)
        {
            if (!AutoDirect || !Ready || b == null || b != ActiveBoss) return;
            Finale();
        }

        void OnRespawned()
        {
            if (!AutoDirect || !Ready || finale) return;
            if (introDone || torn || eclipsed || Shadow != null) ResetArena();
        }

        void OnParry(bool perfect)
        {
            if (!AutoDirect || !eclipsed || finale || Game.Player == null) return;
            ParryLight(Game.Player.transform.position + Game.Player.transform.forward * 0.8f, perfect);
        }
    }
}
