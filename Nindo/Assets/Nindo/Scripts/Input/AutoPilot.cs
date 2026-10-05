#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Piloto automático para pruebas (MCP del editor, tests): maneja la entrada virtual de
    /// InputReader siguiendo un guion de texto. No depende del foco de la ventana ni del framerate
    /// (una pulsación siempre entra en el próximo Update). Pasos separados por ';':
    ///   tap ACT [xN] [pausa]   pulsar (N veces, con 'pausa' segundos entre medio)
    ///   hold ACT seg           mantener
    ///   down ACT / up ACT      dejar mantenida / soltar
    ///   move X Y [seg]         mover con el "stick" (x derecha, y adelante); sin seg queda puesto
    ///   wait seg               esperar (tiempo real: no le afecta la cámara lenta)
    /// ACT = nombre de <see cref="Act"/> (Attack, Parry, Dash, Lock, Finisher, Interact, Ability1,
    /// Ability2, Pause, LockNext, LockPrev, Submit, Cancel).
    /// Ej.: AutoPilot.Run("tap Submit x4 0.5; move 0 1 1.5; tap Attack x3 0.3; hold Parry 0.4")
    /// </summary>
    public class AutoPilot : MonoBehaviour
    {
        static AutoPilot inst;
        readonly Queue<string> steps = new Queue<string>();
        Coroutine loop;

        /// <summary>true mientras quedan pasos por ejecutar.</summary>
        public static bool Busy => inst != null && inst.loop != null;
        /// <summary>Último error de interpretación del guion (vacío si todo bien).</summary>
        public static string LastError { get; private set; } = "";

        public static void Run(string script)
        {
            if (inst == null)
            {
                var go = new GameObject("[AutoPilot]");
                DontDestroyOnLoad(go);
                inst = go.AddComponent<AutoPilot>();
            }
            LastError = "";
            foreach (var s in script.Split(';'))
                if (!string.IsNullOrWhiteSpace(s)) inst.steps.Enqueue(s.Trim());
            if (inst.loop == null) inst.loop = inst.StartCoroutine(inst.Loop());
        }

        /// <summary>Corta el guion y suelta todo.</summary>
        public static void Stop()
        {
            InputReader.ClearVirtual();
            if (inst == null) return;
            inst.steps.Clear();
            if (inst.loop != null) inst.StopCoroutine(inst.loop);
            inst.loop = null;
        }

        void OnDestroy()
        {
            if (inst == this) inst = null;
            InputReader.ClearVirtual();
        }

        IEnumerator Loop()
        {
            while (steps.Count > 0)
            {
                var step = steps.Dequeue();
                IEnumerator e = null;
                try { e = Exec(step.Split((char[])null, System.StringSplitOptions.RemoveEmptyEntries)); }
                catch (System.Exception ex) { LastError = step + ": " + ex.Message; Debug.LogWarning("[AutoPilot] " + LastError); }
                if (e != null) yield return e;
            }
            loop = null;
        }

        IEnumerator Exec(string[] t)
        {
            switch (t[0].ToLowerInvariant())
            {
                case "wait": return Wait(F(t, 1, 0.5f));
                case "tap":
                {
                    bool hasTimes = t.Length > 2 && t[2].StartsWith("x");
                    return Tap(ParseAct(t[1]), hasTimes ? int.Parse(t[2].Substring(1), CultureInfo.InvariantCulture) : 1, F(t, hasTimes ? 3 : 2, 0.15f));
                }
                case "hold": return Hold(ParseAct(t[1]), F(t, 2, 0.5f));
                case "down": InputReader.VirtualHold(ParseAct(t[1]), true); return null;
                case "up": InputReader.VirtualHold(ParseAct(t[1]), false); return null;
                case "move":
                {
                    InputReader.VirtualMove = new Vector2(F(t, 1, 0f), F(t, 2, 0f));
                    return t.Length > 3 ? MoveFor(F(t, 3, 0f)) : null;
                }
                default: throw new System.ArgumentException("paso desconocido '" + t[0] + "'");
            }
        }

        IEnumerator Wait(float s) { yield return new WaitForSecondsRealtime(s); }

        IEnumerator Tap(Act a, int n, float gap)
        {
            for (int i = 0; i < n; i++)
            {
                InputReader.VirtualTap(a);
                yield return new WaitForSecondsRealtime(gap);
            }
        }

        IEnumerator Hold(Act a, float s)
        {
            InputReader.VirtualHold(a, true);
            yield return new WaitForSecondsRealtime(s);
            InputReader.VirtualHold(a, false);
        }

        IEnumerator MoveFor(float s)
        {
            yield return new WaitForSecondsRealtime(s);
            InputReader.VirtualMove = Vector2.zero;
        }

        static Act ParseAct(string s)
        {
            if (System.Enum.TryParse(s, true, out Act a)) return a;
            throw new System.ArgumentException("acción desconocida '" + s + "'");
        }

        static float F(string[] t, int i, float def) => t.Length > i ? float.Parse(t[i], CultureInfo.InvariantCulture) : def;
    }
}
#endif
