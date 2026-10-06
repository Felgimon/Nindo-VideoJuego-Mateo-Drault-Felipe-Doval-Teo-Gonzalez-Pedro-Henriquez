using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Controla Time.timeScale de forma segura: cámara lenta apilable, hit-stop global y pausa.
    /// Antes cada script hacía "timeScale = 0 ... restaurar el original", lo que dejaba el juego
    /// trabado en cámara lenta si dos efectos se superponían. Acá se calcula siempre el mínimo.
    ///
    /// Política de cámara lenta (la cámara lenta es un acento, no el ritmo de la pelea: en una pelea de tres ninjas
    /// medio combate pasaba lento y gris y se perdía de vista el golpe siguiente):
    ///  * Los momentos de combate van por Moment(SlowMoMoment), con los valores en un solo lugar. Los "acentos"
    ///    (último enemigo, doble kill, postura quebrada, esquiva perfecta, Filo de Ira) no se encadenan: si uno
    ///    llega mientras otro dura o en los 0.6 s siguientes, pasa a un hit-stop seco de 0.06 s.
    ///  * SlowMotion() directo queda para cinemáticas y tutoriales (la duración la decide la escena).
    ///  * Un golpe común nunca frena el mundo: hit-stop corto (0.035-0.07) y nada más.
    ///  * Lo que reacciona a la cámara lenta (gris de ScreenFX, pitch del audio) lee SlowMoScale: el hit-stop no.
    /// Llamadas a migrar (Player/* y Enemies/* son de combate): PlayerController.Combat (muerte de un enemigo ->
    /// LastKill/DoubleKill, esquiva perfecta -> PerfectDodge, remate -> FinisherCinematic/FinisherQuick,
    /// habilidades -> AbilityWind/AbilityWhirl), PlayerController (Filo de Ira -> Rage, muerte -> PlayerDeath),
    /// Enemy.BreakPosture -> PostureBreak, Boss (derrota) -> BossDefeat. Los valores de la tabla son los de hoy.
    /// </summary>
    [DefaultExecutionOrder(-900)]
    public class TimeController : MonoBehaviour
    {
        const float BaseFixedDelta = 0.02f;

        class SlowMo
        {
            public float scale, duration, easeIn, easeOut, t;
            public int id;
        }

        readonly List<SlowMo> slowMos = new List<SlowMo>(8);
        float hitStopUntil;
        int nextId = 1;
        bool paused;

        /// <summary>Escala actual sin contar pausa (útil para el audio).</summary>
        public float GameplayScale { get; private set; } = 1f;
        /// <summary>
        /// Solo la cámara lenta, sin el hit-stop. Para lo que debe reaccionar a la cámara lenta pero no a los
        /// congelados de 2-6 frames de cada golpe (desaturar la pantalla, bajar el pitch): si no, cada golpe
        /// parpadea en gris y su sonido arranca grave.
        /// </summary>
        public float SlowMoScale { get; private set; } = 1f;

        void Awake()
        {
            Game.Time = this;
            Time.timeScale = 1f;
            Time.fixedDeltaTime = BaseFixedDelta;
        }

        void OnDestroy()
        {
            if (Game.Time == this) Game.Time = null;
            Time.timeScale = 1f;
            Time.fixedDeltaTime = BaseFixedDelta;
        }

        // ------------------------------------------------------------------ política
        struct Preset
        {
            public float scale, duration, easeIn, easeOut;
            public bool accent;
            public Preset(float s, float d, float i, float o, bool a) { scale = s; duration = d; easeIn = i; easeOut = o; accent = a; }
        }

        static readonly Preset[] Presets =
        {
            new Preset(0.30f, 0.35f, 0.01f, 0.25f, true),    // LastKill
            new Preset(0.30f, 0.35f, 0.01f, 0.25f, true),    // DoubleKill
            new Preset(0.25f, 0.30f, 0.02f, 0.15f, true),    // PostureBreak
            new Preset(0.35f, 0.40f, 0.02f, 0.15f, true),    // PerfectDodge
            new Preset(0.35f, 0.45f, 0.02f, 0.30f, true),    // Rage
            new Preset(0.45f, 1.60f, 0.05f, 0.30f, false),   // FinisherCinematic
            new Preset(0.60f, 0.35f, 0.03f, 0.15f, false),   // FinisherQuick
            new Preset(0.20f, 0.55f, 0.05f, 0.15f, false),   // AbilityWind
            new Preset(0.35f, 0.30f, 0.03f, 0.15f, false),   // AbilityWhirl
            new Preset(0.15f, 2.20f, 0.02f, 0.80f, false),   // BossDefeat
            new Preset(0.25f, 1.60f, 0.02f, 0.50f, false),   // PlayerDeath
        };
        /// <summary>Tras un acento, cuánto esperar (s reales) antes de permitir otro.</summary>
        const float AccentCooldown = 0.6f, AccentFallbackHitStop = 0.06f;
        float accentFreeAt;

        /// <summary>
        /// Momento de cámara lenta con nombre (ver la política arriba). Devuelve el id para CancelSlowMotion, o -1 si
        /// un acento se convirtió en hit-stop porque otro acababa de pasar.
        /// </summary>
        public int Moment(SlowMoMoment m)
        {
            var p = Presets[(int)m];
            if (p.accent)
            {
                float now = Time.unscaledTime;
                if (now < accentFreeAt) { HitStop(AccentFallbackHitStop); return -1; }
                accentFreeAt = now + p.duration + AccentCooldown;
            }
            return SlowMotion(p.scale, p.duration, p.easeIn, p.easeOut);
        }

        // medición: qué parte de cada pelea pasa en cámara lenta (para ajustar; se loguea en el editor al terminar)
        float fightTime, fightSlow;
        bool wasFighting;

        /// <summary>Fracción (0..1) de la pelea en curso que lleva en cámara lenta (escala < 0.9).</summary>
        public float FightSlowShare => fightTime > 0f ? fightSlow / fightTime : 0f;

        void MeasureFight(float dt)
        {
            bool fighting = Game.Combat != null && Game.Combat.InCombat;
            if (fighting)
            {
                fightTime += dt;
                if (SlowMoScale < 0.9f) fightSlow += dt;
            }
            else if (wasFighting)
            {
#if UNITY_EDITOR
                if (fightTime > 3f) Debug.Log($"[Nindo] Pelea de {fightTime:0.0} s: {FightSlowShare:P0} en cámara lenta");
#endif
                fightTime = fightSlow = 0f;
            }
            wasFighting = fighting;
        }

        /// <summary>Cámara lenta. duration y fades en segundos reales.</summary>
        public int SlowMotion(float scale, float duration, float easeIn = 0.05f, float easeOut = 0.25f)
        {
            if (!Settings.SlowMotionEnabled && scale > 0.05f) scale = Mathf.Lerp(scale, 1f, 0.6f);
            var s = new SlowMo { scale = Mathf.Clamp(scale, 0.02f, 1f), duration = duration, easeIn = easeIn, easeOut = easeOut, id = nextId++ };
            slowMos.Add(s);
            return s.id;
        }

        public void CancelSlowMotion(int id)
        {
            for (int i = 0; i < slowMos.Count; i++)
                if (slowMos[i].id == id)
                {
                    // dispara el fade de salida
                    var s = slowMos[i];
                    if (s.t < s.duration - s.easeOut) s.t = Mathf.Max(0f, s.duration - s.easeOut);
                }
        }

        public void ClearSlowMotion() => slowMos.Clear();

        /// <summary>Congela el mundo entero unos milisegundos (impactos fuertes).</summary>
        public void HitStop(float seconds)
        {
            hitStopUntil = Mathf.Max(hitStopUntil, Time.unscaledTime + seconds);
        }

        public void SetPaused(bool p)
        {
            paused = p;
            Game.IsPaused = p;
            Apply();
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime;
            float scale = 1f;
            for (int i = slowMos.Count - 1; i >= 0; i--)
            {
                var s = slowMos[i];
                s.t += dt;
                if (s.t >= s.duration) { slowMos.RemoveAt(i); continue; }
                float w = 1f;
                if (s.easeIn > 0f && s.t < s.easeIn) w = s.t / s.easeIn;
                float remain = s.duration - s.t;
                if (s.easeOut > 0f && remain < s.easeOut) w = Mathf.Min(w, remain / s.easeOut);
                float k = Mathf.Lerp(1f, s.scale, Smooth(w));
                if (k < scale) scale = k;
            }
            SlowMoScale = scale;
            if (!paused) MeasureFight(dt);
            if (Time.unscaledTime < hitStopUntil) scale = 0f;
            GameplayScale = scale;
            Apply();
        }

        void Apply()
        {
            float s = paused ? 0f : GameplayScale;
            Time.timeScale = s;
            Time.fixedDeltaTime = BaseFixedDelta * Mathf.Max(s, 0.05f);
        }

        static float Smooth(float x) => x * x * (3f - 2f * x);
    }

    /// <summary>Momentos de cámara lenta de la política (TimeController.Moment).</summary>
    public enum SlowMoMoment
    {
        LastKill, DoubleKill, PostureBreak, PerfectDodge, Rage,
        FinisherCinematic, FinisherQuick, AbilityWind, AbilityWhirl, BossDefeat, PlayerDeath
    }
}
