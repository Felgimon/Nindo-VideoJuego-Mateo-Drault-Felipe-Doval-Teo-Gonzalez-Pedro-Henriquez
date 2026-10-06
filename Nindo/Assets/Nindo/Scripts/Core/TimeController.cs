using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Controla Time.timeScale de forma segura: cámara lenta apilable, hit-stop global y pausa.
    /// Antes cada script hacía "timeScale = 0 ... restaurar el original", lo que dejaba el juego
    /// trabado en cámara lenta si dos efectos se superponían. Acá se calcula siempre el mínimo.
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
}
