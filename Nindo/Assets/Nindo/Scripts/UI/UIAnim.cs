using System;
using System.Collections;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Movimiento de la UI, para que todo se mueva con el mismo pulso: rápido 0.12 s (EaseOutCubic), medio
    /// 0.25 s (EaseOutBack 1.4), lento 0.6 s (EaseInOutSine). Siempre en tiempo sin escala: los paneles se
    /// abren en pausa (timeScale 0) y en cámara lenta. Lo único que sigue al tiempo de juego son los avisos
    /// de combate (atados al golpe), y esos los maneja cada marcador.
    /// </summary>
    public static class UIAnim
    {
        public const float Fast = 0.12f, Medium = 0.25f, Slow = 0.6f;

        public static float OutCubic(float t) { t = Mathf.Clamp01(t); float u = 1f - t; return 1f - u * u * u; }
        public static float InCubic(float t) { t = Mathf.Clamp01(t); return t * t * t; }
        public static float InOutSine(float t) => 0.5f - 0.5f * Mathf.Cos(Mathf.Clamp01(t) * Mathf.PI);

        public static float OutBack(float t, float s = 1.4f)
        {
            t = Mathf.Clamp01(t) - 1f;
            return t * t * ((s + 1f) * t + s) + 1f;
        }

        /// <summary>Salto de aparición: de 'from' pasa de largo a 'over' y se asienta en 1 (golpe de sello).</summary>
        public static float Pop(float t, float duration, float from = 0.7f, float over = 1.08f)
        {
            float k = duration > 0f ? t / duration : 1f;
            if (k >= 1f) return 1f;
            return k < 0.6f ? Mathf.Lerp(from, over, OutCubic(k / 0.6f)) : Mathf.Lerp(over, 1f, InOutSine((k - 0.6f) / 0.4f));
        }

        /// <summary>Interpola de 0 a 1 en 'duration' s sin escala, llamando a step(k) cada cuadro (k ya con la curva).</summary>
        public static IEnumerator Tween(float duration, Func<float, float> ease, Action<float> step)
        {
            float t = 0f;
            while (t < duration)
            {
                t += Time.unscaledDeltaTime;
                step(ease(t / duration));
                yield return null;
            }
            step(1f);
        }
    }
}
