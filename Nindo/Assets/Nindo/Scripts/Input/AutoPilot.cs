#if (UNITY_EDITOR || DEVELOPMENT_BUILD) && ENABLE_INPUT_SYSTEM
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;

namespace Nindo
{
    /// <summary>
    /// Piloto automático para pruebas (MCP del editor, tests): inyecta teclado y mouse en el
    /// Input System siguiendo un guion de texto, así InputReader lo lee como input real.
    /// Pasos separados por ';':
    ///   tap KEY [xN] [pausa]   apretar y soltar (N veces, con 'pausa' segundos entre medio)
    ///   hold KEY seg           mantener apretada
    ///   down KEY / up KEY      dejar apretada / soltar
    ///   click L|R|M [xN] [pausa]  botones del mouse
    ///   wait seg               esperar (tiempo real, no le afecta la cámara lenta)
    /// Ej.: AutoPilot.Run("tap Enter x4 0.5; down W; wait 1.5; up W; tap J x3 0.3")
    /// KEY usa los nombres de UnityEngine.InputSystem.Key (Enter, Space, W, J, K, Digit1...).
    /// </summary>
    public class AutoPilot : MonoBehaviour
    {
        static AutoPilot inst;
        readonly HashSet<Key> keys = new HashSet<Key>();
        readonly HashSet<MouseButton> buttons = new HashSet<MouseButton>();
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
            if (inst == null) return;
            inst.steps.Clear();
            if (inst.loop != null) inst.StopCoroutine(inst.loop);
            inst.loop = null;
            inst.keys.Clear(); inst.buttons.Clear();
            inst.Apply();
        }

        void OnDestroy() { if (inst == this) inst = null; }

        // el estado se reenvía cada frame: si el editor pierde el foco el Input System puede
        // resetear los dispositivos y una tecla mantenida se "soltaría" sola
        void Update() { if (keys.Count > 0 || buttons.Count > 0) Apply(); }

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
            string cmd = t[0].ToLowerInvariant();
            switch (cmd)
            {
                case "wait": return Wait(F(t, 1, 0.5f));
                case "tap": return Tap(ParseKey(t[1]), Times(t), F(t, 3, 0.15f));
                case "hold": return Hold(ParseKey(t[1]), F(t, 2, 0.5f));
                case "down": keys.Add(ParseKey(t[1])); Apply(); return null;
                case "up": keys.Remove(ParseKey(t[1])); Apply(); return null;
                case "click": return Click(ParseButton(t[1]), Times(t), F(t, 3, 0.15f));
                default: throw new System.ArgumentException("paso desconocido '" + cmd + "'");
            }
        }

        IEnumerator Wait(float s) { yield return new WaitForSecondsRealtime(s); }

        IEnumerator Tap(Key k, int n, float gap)
        {
            for (int i = 0; i < n; i++)
            {
                keys.Add(k); Apply();
                yield return new WaitForSecondsRealtime(0.06f);
                keys.Remove(k); Apply();
                yield return new WaitForSecondsRealtime(gap);
            }
        }

        IEnumerator Hold(Key k, float s)
        {
            keys.Add(k); Apply();
            yield return new WaitForSecondsRealtime(s);
            keys.Remove(k); Apply();
        }

        IEnumerator Click(MouseButton b, int n, float gap)
        {
            for (int i = 0; i < n; i++)
            {
                buttons.Add(b); Apply();
                yield return new WaitForSecondsRealtime(0.06f);
                buttons.Remove(b); Apply();
                yield return new WaitForSecondsRealtime(gap);
            }
        }

        void Apply()
        {
            var kb = Keyboard.current;
            if (kb != null)
            {
                var arr = new Key[keys.Count];
                keys.CopyTo(arr);
                InputSystem.QueueStateEvent(kb, new KeyboardState(arr));
            }
            var mouse = Mouse.current;
            if (mouse != null)
            {
                var ms = new MouseState { position = mouse.position.ReadValue() };
                foreach (var b in buttons) ms = ms.WithButton(b);
                InputSystem.QueueStateEvent(mouse, ms);
            }
        }

        static Key ParseKey(string s)
        {
            if (System.Enum.TryParse(s, true, out Key k)) return k;
            throw new System.ArgumentException("tecla desconocida '" + s + "'");
        }

        static MouseButton ParseButton(string s)
        {
            switch (s.ToUpperInvariant())
            {
                case "L": return MouseButton.Left;
                case "R": return MouseButton.Right;
                case "M": return MouseButton.Middle;
                default: throw new System.ArgumentException("botón desconocido '" + s + "'");
            }
        }

        static int Times(string[] t) => t.Length > 2 && t[2].StartsWith("x") ? int.Parse(t[2].Substring(1), CultureInfo.InvariantCulture) : 1;

        static float F(string[] t, int i, float def)
        {
            // "tap K 0.3" (sin xN) también vale como pausa
            string c = t[0].ToLowerInvariant();
            if ((c == "tap" || c == "click") && t.Length == 3 && !t[2].StartsWith("x")) i = 2;
            return t.Length > i ? float.Parse(t[i], CultureInfo.InvariantCulture) : def;
        }
    }
}
#endif
