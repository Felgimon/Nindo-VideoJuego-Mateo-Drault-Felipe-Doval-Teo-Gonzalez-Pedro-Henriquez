using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Línea de tiempo determinista de un golpe enemigo (sin estado de Unity: se puede probar sola).
    /// Antes el clip se re-timeaba con una curva normalizada y el "telegraph" se perdía según la
    /// velocidad del clip: nadie sabía en qué segundo salía el golpe. Acá cada paso del combo es:
    ///   anticipación (0 → apex, desacelerando)  ·  pausa en el apex (respira)  ·  suelta rápida
    ///   (apex → activeStart, acelerando)  ·  seguimiento (vuelve a velocidad 1).
    /// El golpe sale EXACTO en <see cref="T"/> segundos de reloj del paso, así que StrikeEta = T - reloj
    /// y el aviso en el suelo (ensō) se cierra cuando corresponde, a cualquier framerate.
    /// </summary>
    public struct StepTimeline
    {
        // ritmo de la anticipación respecto del clip: un poco más lenta le da peso al golpe
        const float AnticipationRate = 0.85f;
        // pausa máxima "congelada" en el apex: lo que falte para el windup mínimo se reparte en una
        // anticipación más lenta (una pose quieta más de medio segundo se lee como un error)
        const float MaxHold = 0.45f;
        // el seguimiento después del impacto vuelve de la velocidad de la suelta a 1 con esta constante
        const float FollowTau = 0.06f;

        public float stepLen;     // duración del clip a la velocidad del golpe (s)
        public float apex, activeStart, activeEnd;
        public float tA;          // fin de la anticipación (s)
        public float hold;        // pausa en el apex (s)
        public float tR;          // duración de la suelta (s)
        public float T;           // el golpe pega acá (s desde el inicio del paso)
        public float creep;       // lo que avanza el clip durante la pausa (normalizado)
        public float sustain;     // si > 0, la fase activa (activeStart → activeEnd) dura esto en segundos (embestidas)

        /// <summary>Segundo en que empieza la suelta: desde acá el golpe ya no corrige la puntería.</summary>
        public float ReleaseTime => tA + hold;

        public static StepTimeline Build(AttackDef a, float clipLen, float windupMin, float extraHold)
        {
            var t = new StepTimeline();
            t.stepLen = Mathf.Max(0.05f, clipLen) / Mathf.Max(0.05f, a.speed);
            t.activeStart = Mathf.Clamp(a.activeStart, 0.02f, 1f);
            t.activeEnd = Mathf.Max(t.activeStart, a.activeEnd);
            float apex = a.apex >= 0f ? a.apex : t.activeStart - 0.15f;
            t.apex = Mathf.Clamp(apex, 0f, t.activeStart - 0.02f);
            float release = a.releaseRate > 0.1f ? a.releaseRate : 1.6f;
            t.tA = t.apex * t.stepLen / AnticipationRate;
            t.tR = (t.activeStart - t.apex) * t.stepLen / release;
            float extra = Mathf.Max(0f, windupMin - (t.tA + t.tR));
            t.hold = Mathf.Min(extra, MaxHold);
            t.tA += extra - t.hold;
            t.hold += Mathf.Max(0f, extraHold);
            t.T = t.tA + t.hold + t.tR;
            t.creep = Mathf.Min(0.01f, (t.activeStart - t.apex) * 0.25f);
            t.sustain = 0f;
            return t;
        }

        /// <summary>Tiempo normalizado del clip a 't' segundos del inicio del paso.</summary>
        public float NormAt(float t)
        {
            if (t <= 0f) return 0f;
            if (t < tA) return apex * Mathf.Sin(t / tA * Mathf.PI * 0.5f);
            t -= tA;
            if (t < hold) return apex + creep * t / hold;
            t -= hold;
            float from = apex + creep;
            if (t < tR) { float u = t / tR; return from + (activeStart - from) * u * u; }
            t -= tR;
            if (sustain > 0f)
                return t < sustain ? activeStart + (activeEnd - activeStart) * t / sustain : activeEnd + (t - sustain) / stepLen;
            // al final de la suelta el clip va a r0 veces su velocidad: frena hacia 1 sin saltos
            float r0 = Mathf.Max(1f, 2f * (activeStart - from) / tR * stepLen);
            return activeStart + (t + (r0 - 1f) * FollowTau * (1f - Mathf.Exp(-t / FollowTau))) / stepLen;
        }

        /// <summary>
        /// Windup mínimo (segundos desde que arranca el paso hasta que pega) según el tipo de golpe:
        /// lo que hace falta para que el aviso se vea y se pueda reaccionar. 'chained' = no es el primer
        /// golpe del combo (el jugador ya está en ritmo). El 'telegraph' del golpe se suma como windup extra.
        /// </summary>
        public static float MinWindup(AttackDef a, bool chained, bool counter, int phase, float scale)
        {
            float b;
            if (a.windup > 0f) b = a.windup;
            else if (a.kind == AttackKind.Unblockable) b = 0.80f;
            else if (a.kind == AttackKind.Heavy) b = chained ? 0.50f : 0.65f;
            else b = chained ? 0.42f : 0.55f;
            bool unblockable = a.kind == AttackKind.Unblockable;
            if (!unblockable) b *= Mathf.Max(0.1f, scale);
            if (counter) b = Mathf.Max(b, 0.50f);
            if (phase >= 1) b *= 0.9f;
            b = Mathf.Max(b, unblockable ? 0.70f : 0.38f);
            return b + Mathf.Max(0f, a.telegraph);
        }
    }

    /// <summary>Cómo terminó un aviso: el golpe salió, Kaito lo desvió, o se cortó (stagger, muerte, cambio de fase).</summary>
    public enum TellOutcome { Struck, Parried, Cancelled }

    /// <summary>Zona real que golpea un especial (disco del pisotón/giro, carril de la embestida/tajo), apoyada en el suelo.</summary>
    public struct TellArea
    {
        public bool lane;          // false = disco
        public Vector3 origin;     // centro del disco o inicio del carril
        public Vector3 forward;    // dirección del carril (plana)
        public float size;         // radio del disco o largo del carril (m)
        public float width;        // ancho total del carril (m)

        public bool Contains(Vector3 p, float pad)
        {
            Vector3 d = (p - origin).Flat();
            if (!lane) return d.magnitude <= size + pad;
            float along = Vector3.Dot(d, forward);
            if (along < -pad || along > size + pad) return false;
            return Mathf.Abs(Vector3.Dot(d, Vector3.Cross(Vector3.up, forward))) <= width * 0.5f + pad;
        }
    }

    /// <summary>
    /// Constantes del aviso de ataque (ensō): tiempos, colores y anchos en un solo lugar para ajustar.
    /// Dorado = se desvía con parry al cerrarse; rojo dentado + zona = imparable, dash al cerrarse.
    /// </summary>
    public static class TellStyle
    {
        /// <summary>El anillo se dibuja como mucho durante este tiempo antes del golpe (s).</summary>
        public const float MaxParryable = 0.85f, MaxUnblockable = 1.0f;
        /// <summary>
        /// El anillo se cierra este tiempo ANTES del golpe. Parry: la ventana es [golpe - 0.24, golpe] y la perfecta
        /// los últimos 0.11 s; fallar tarde es lo caro (daño entero y aturdimiento) y quien aprieta al ver el cierre
        /// llega 2-4 frames después (pantalla + entrada). Cerrando a 0.10, con error N(0, 0.05): 84 % de parries
        /// (72 % perfectos) sin compensar la latencia y 97 % (55 %) compensándola; a 0.08 era 72 % / 94 %
        /// (Monte Carlo). Dash: los i-frames van de 0.02 a 0.24; a 0.16, 96 % de esquivas sin compensar, 94 % compensando.
        /// </summary>
        public const float BiasParryable = 0.10f, BiasUnblockable = 0.16f;
        /// <summary>
        /// Hyōshigi (toc de madera) a este tiempo del golpe, contado desde que se OYE (AudioManager.CueDue suma
        /// la latencia de salida). Es la pista "reactiva"; el anillo es la "predictiva". Reaccionando al sonido con
        /// N(0.25, 0.04) s + 1-2 frames de entrada: ~100 % de parries (~45 % perfectos); con N(0.30, 0.05), ~89 %.
        /// Dash a 0.42: 98 % / 94 %. A 0.32 / 0.36 y sin compensar el audio caía casi siempre tarde.
        /// </summary>
        public const float TickParryable = 0.38f, TickUnblockable = 0.42f;
        /// <summary>El silbido del arma se adelanta lo que tarda en llegar a su pico (medido en los .wav).</summary>
        public const float SwingLight = 0.13f, SwingHeavy = 0.24f;

        // dorado profundo: el #FFD678 anterior salía crema después del tonemapping y en la nieve casi no se veía
        // (prueba en Play, 2026-10-05); con más rojo y menos azul sigue siendo dorado sobre nieve, agua y madera
        public static readonly Color Gold = new Color(1f, 0.72f, 0.24f);          // #FFB83D
        // el tramo decisivo se aclara pero sin llegar al blanco (el bloom ya lo hace brillar)
        public static readonly Color GoldHot = new Color(1f, 0.84f, 0.4f);         // #FFD666
        public static readonly Color Crimson = new Color(0.92f, 0.157f, 0.118f);   // #EB281E
        public static readonly Color Ink = new Color(0.07f, 0.04f, 0.047f);        // #120A0C
        public static readonly Color TrailParry = new Color(1f, 0.93f, 0.8f, 0.7f);
        public static readonly Color TrailDanger = new Color(1f, 0.2f, 0.12f, 0.8f);

        public static float Bias(AttackKind k) => k == AttackKind.Unblockable ? BiasUnblockable : BiasParryable;
        public static float MaxLead(AttackKind k) => k == AttackKind.Unblockable ? MaxUnblockable : MaxParryable;
        public static float TickLead(AttackKind k) => k == AttackKind.Unblockable ? TickUnblockable : TickParryable;
    }
}
