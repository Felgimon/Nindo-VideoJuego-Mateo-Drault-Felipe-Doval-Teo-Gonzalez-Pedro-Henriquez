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
        /// <summary>Presentación: la luna gira detrás del dojo y rompe las nubes; los braseros se encienden en ola desde el jefe.</summary>
        public void Intro(Transform boss)
        {
            introDone = true;
            if (Moon != null) { Moon.SetVeil(1f, 0f); Moon.EnterArena(2f); Moon.SetVeil(0f, 2.2f); }
            if (Braziers != null)
            {
                Braziers.SetStyle(FlameStyle.Fire, 0f);
                Braziers.IgniteFrom(boss != null ? boss.position : Center, 0.12f);
            }
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
        /// La sombra arrancada (Acto 2): los braseros se vuelven violetas con un golpe de chispas y la sombra se despega
        /// del piso como figura de humo. Sin la pelea guionada (que la convierte en Kage) se desvanece: el cuerpo queda
        /// sin sombra, a propósito inquietante.
        /// </summary>
        public void ShadowTear(bool fadeShadow = true)
        {
            torn = true;
            if (Braziers != null) { Braziers.SetStyle(FlameStyle.Violet, 1f); Braziers.FlareAll(1f); }
            if (Shadow != null)
            {
                Shadow.Strike(0.3f);
                Shadow.RiseTo(1f, 0.8f);
                if (fadeShadow) StartCoroutine(FadeShadowLater(1.3f, 0.7f));
            }
            Game.Camera?.Shake(0.6f);
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

        /// <summary>Kokuyō cae: vuelve la luna con pétalos, se deshacen las cuerdas del abuelo y los braseros se encienden tibios.</summary>
        public void Finale()
        {
            finale = true;
            if (Moon != null) Moon.MoonReturn(3f, 9f);
            if (Shadow != null) { Shadow.Release(); Shadow = null; }
            var g = Game.Player != null ? Game.Player.GetComponent<BandanaGlow>() : null;
            if (g != null) g.Disable(2.5f);
            StartCoroutine(FinaleRoutine());
        }

        IEnumerator FinaleRoutine()
        {
            yield return new WaitForSecondsRealtime(1.2f);
            if (Ropes != null) Ropes.Dissolve(1.6f);
            yield return new WaitForSecondsRealtime(1.3f);
            if (Braziers != null) { Braziers.SetStyle(FlameStyle.Fire, 0f); Braziers.IgniteAll(0.25f, 0, true); }
        }

        /// <summary>Todo como antes de la pelea (Kaito murió): braseros fríos, noche de siempre, abuelo atado, sin sombra viva.</summary>
        public void ResetArena()
        {
            introDone = torn = eclipsed = finale = false;
            StopAllCoroutines();
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
