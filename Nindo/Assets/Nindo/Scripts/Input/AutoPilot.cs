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
    ///   bot on|off             peleador automático: parry a los golpes que llegan, dash a los
    ///                          imparables, remata a los desequilibrados y si no, ataca/se acerca
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

        // ---------------------------------------------------------------- bot de combate
        /// <summary>Peleador automático (ver "bot on"). También se puede prender desde código.</summary>
        public static bool Bot
        {
            get => inst != null && inst.bot;
            set { if (inst == null) Run(""); inst.bot = value; }
        }
        /// <summary>Contadores del bot (pulsaciones) para los informes de prueba.</summary>
        public static int BotParries, BotDashes, BotFinishers, BotAttacks;
        /// <summary>Resultados reales (por eventos del juego), con o sin bot.</summary>
        public static int ParryOk, ParryPerfect, HitsTaken, Kills, Executions;
        public static float DamageTaken;
        public static void ResetStats()
        {
            BotParries = BotDashes = BotFinishers = BotAttacks = 0;
            ParryOk = ParryPerfect = HitsTaken = Kills = Executions = 0;
            DamageTaken = 0f;
        }
        public static string Stats =>
            $"bot: parry {BotParries} dash {BotDashes} remate {BotFinishers} ataque {BotAttacks} | " +
            $"juego: parry ok {ParryOk} (perfectos {ParryPerfect}) golpes recibidos {HitsTaken} ({DamageTaken:0} daño) muertes {Kills} ejecuciones {Executions}";

        void OnEnable()
        {
            GameEvents.Parry += OnParry;
            GameEvents.PlayerDamaged += OnDamaged;
            GameEvents.EnemyFinished += OnFinished;
        }
        void OnDisable()
        {
            GameEvents.Parry -= OnParry;
            GameEvents.PlayerDamaged -= OnDamaged;
            GameEvents.EnemyFinished -= OnFinished;
        }
        static void OnParry(bool perfect) { ParryOk++; if (perfect) ParryPerfect++; }
        static void OnDamaged(float d) { HitsTaken++; DamageTaken += d; }
        static void OnFinished(Enemy e, bool finisher) { Kills++; if (finisher) Executions++; }

        bool bot;
        float nextBotAction;
        Enemy lastParried;

        void Update()
        {
            if (!bot || Game.Player == null || !Game.Player.IsAlive || Game.Combat == null) return;
            var p = Game.Player;
            Enemy nearest = null, striking = null;
            float best = float.MaxValue, soonest = float.PositiveInfinity;
            foreach (var e in Game.Combat.Engaged)
            {
                if (e == null || !e.IsAlive) continue;
                float d = CombatMath.FlatDistance(e.transform.position, p.transform.position);
                if (d < best) { best = d; nearest = e; }
                if (e.AboutToStrike && d < 7f) striking = e;
                if (d < 7f) soonest = Mathf.Min(soonest, e.StrikeEta);
            }
            // defensa: no depende del cooldown de acciones
            if (striking != null && striking != lastParried)
            {
                lastParried = striking;
                if (striking.IsTelegraphingUnblockable) { InputReader.VirtualTap(Act.Dash); BotDashes++; }
                else { InputReader.VirtualTap(Act.Parry); BotParries++; }
                nextBotAction = Time.unscaledTime + 0.25f;
                return;
            }
            if (striking == null) lastParried = null;
            if (nearest == null) { InputReader.VirtualMove = Vector2.zero; return; }

            // acercarse en espacio de cámara (el "stick" es relativo a la cámara)
            Vector3 to = nearest.transform.position - p.transform.position; to.y = 0f;
            var cam = Camera.main != null ? Camera.main.transform : null;
            Vector3 f = cam != null ? Vector3.ProjectOnPlane(cam.forward, Vector3.up).normalized : Vector3.forward;
            Vector3 r = cam != null ? Vector3.ProjectOnPlane(cam.right, Vector3.up).normalized : Vector3.right;
            InputReader.VirtualMove = best > 2.2f ? new Vector2(Vector3.Dot(to.normalized, r), Vector3.Dot(to.normalized, f)) : Vector2.zero;

            if (Time.unscaledTime < nextBotAction) return;
            if (p.FinisherCandidate() != null) { InputReader.VirtualTap(Act.Finisher); BotFinishers++; nextBotAction = Time.unscaledTime + 1.2f; }
            // no empezar un ataque si alguien está por pegar: el parry no cancela el golpe a mitad
            else if (best < 2.6f && soonest > 0.6f) { InputReader.VirtualTap(Act.Attack); BotAttacks++; nextBotAction = Time.unscaledTime + 0.32f; }
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
                case "bot":
                    Bot = t.Length < 2 || t[1].ToLowerInvariant() != "off";
                    if (!Bot) InputReader.VirtualMove = Vector2.zero;
                    return null;
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
