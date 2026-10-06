using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// El latido de poca vida, uno solo para todo: lo marca la bandana (late y se enrojece) y lo puede seguir
    /// la viñeta de ScreenFX con <see cref="Value"/>. Antes la bandana latía a 0.86 s y la viñeta con un seno
    /// de 1.05 s: se desfasaban a la vista.
    /// Lub-dub que se acelera: 70 por minuto con 30 % de vida, 110 con 5 %. La fase se integra (no sale de
    /// t / período) para que no salte cuando la vida cambia en medio de un latido.
    /// Lo avanza UIManager una vez por cuadro, en tiempo sin escala.
    /// </summary>
    public static class UIBeat
    {
        public const float Threshold = 0.3f;
        static float phase;

        /// <summary>0..1 cuánta urgencia hay (0 con 30 % de vida o más, 1 casi muerto).</summary>
        public static float Urgency { get; private set; }

        /// <summary>Latido actual 0..1 ya multiplicado por la urgencia (0 si la vida está bien).</summary>
        public static float Value { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { phase = 0f; Urgency = 0f; Value = 0f; }

        public static void Tick(float dt, float health01)
        {
            bool low = health01 > 0f && health01 < Threshold;
            Urgency = low ? Mathf.Clamp01((Threshold - health01) / (Threshold - 0.05f)) : 0f;
            if (!low) { Value = 0f; phase = 0f; return; }
            float bpm = Mathf.Lerp(70f, 110f, Urgency);
            phase = Mathf.Repeat(phase + dt * bpm / 60f, 1f);
            Value = (0.45f + 0.55f * Urgency) * Sample(phase);
        }

        /// <summary>Forma del latido en una fase 0..1: golpe fuerte y uno más chico enseguida.</summary>
        public static float Sample(float ph) => Mathf.Exp(-Mathf.Pow(ph / 0.05f, 2)) + 0.6f * Mathf.Exp(-Mathf.Pow((ph - 0.18f) / 0.05f, 2));
    }
}
