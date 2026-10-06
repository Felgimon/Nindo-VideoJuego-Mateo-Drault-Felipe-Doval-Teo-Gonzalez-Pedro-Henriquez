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
    ///                          imparables, remata a los de postura quebrada (o casi muertos) y si no,
    ///                          ataca/se acerca (no le pega a una guardia).
    ///                          Defiende como una persona: no lee StrikeEta, reacciona al aviso
    ///                          "¡ya!" (hyōshigi) con ~0.25 s de reacción; si el aviso llega tarde, falla
    ///   talk [max]             espera un diálogo (hasta 'max' s) y lo avanza hasta que no quede ninguno
    ///   waitcontrol [max]      espera a que no haya cinemática ni diálogo
    ///   goto X Z [max]         camina hasta el punto (x, z) del mundo (o hasta 'max' s)
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
            if (inst != null)
            {
                inst.steps.Clear();
                // StopAllCoroutines corta también el paso en curso (goto/talk corren como corrutina hija)
                inst.StopAllCoroutines();
                inst.loop = null;
                inst.bot = false;
                inst.pending.Clear();
            }
            InputReader.ClearVirtual();
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
            GameEvents.StrikeCue += OnCue;
            GameEvents.Parry += OnParry;
            GameEvents.PlayerDamaged += OnDamaged;
            GameEvents.EnemyFinished += OnFinished;
            GameEvents.EnemyKilled += OnKilled;
        }
        void OnDisable()
        {
            GameEvents.StrikeCue -= OnCue;
            GameEvents.Parry -= OnParry;
            GameEvents.PlayerDamaged -= OnDamaged;
            GameEvents.EnemyFinished -= OnFinished;
            GameEvents.EnemyKilled -= OnKilled;
        }
        static void OnParry(bool perfect) { ParryOk++; if (perfect) ParryPerfect++; }
        static void OnDamaged(float d) { HitsTaken++; DamageTaken += d; }
        static void OnFinished(Enemy e, bool finisher) { if (finisher) Executions++; }
        static void OnKilled(Enemy e) { Kills++; }

        bool bot;
        float nextBotAction;
        readonly List<Enemy> botTargets = new List<Enemy>();
        // pulsaciones de defensa pendientes: (tiempo real en que se aprieta, acción)
        readonly List<KeyValuePair<float, Act>> pending = new List<KeyValuePair<float, Act>>();
        /// <summary>Tiempo de reacción del bot a un aviso sonoro (media y desvío, s).</summary>
        public const float ReactionMean = 0.25f, ReactionSd = 0.04f;

        /// <summary>
        /// Sonó el "¡ya!" de un golpe: el bot aprieta un tiempo de reacción humano después (tiempo real, como
        /// una persona). Así las pruebas fallan si el aviso llega más tarde de lo que se puede reaccionar.
        /// </summary>
        void OnCue(Component source, bool unblockable)
        {
            var p = Game.Player;
            if (!bot || p == null || !p.IsAlive) return;
            // ¿viene hacia Kaito? (lo que una persona ve: el anillo del atacante lo alcanza o una ola le apunta)
            var e = source as Enemy;
            bool mine = source is WaveProjectile || e != null && (e.StrikeCanReach(p.transform.position, p.Radius + 0.5f) || e.ProjectileEta < 0.5f);
            if (!mine) return;
            float rt = Mathf.Clamp(ReactionMean + Gaussian() * ReactionSd, 0.15f, 0.4f);
            pending.Add(new KeyValuePair<float, Act>(Time.unscaledTime + rt, unblockable ? Act.Dash : Act.Parry));
        }

        static float Gaussian()
        {
            // Box-Muller
            float u1 = Mathf.Max(1e-6f, Random.value), u2 = Random.value;
            return Mathf.Sqrt(-2f * Mathf.Log(u1)) * Mathf.Cos(2f * Mathf.PI * u2);
        }

        void Update()
        {
            if (!bot || Game.Player == null || !Game.Player.IsAlive || Game.Combat == null) return;
            var p = Game.Player;
            Enemy nearest = null;
            float best = float.MaxValue;
            bool threatened = false;
            botTargets.Clear();
            foreach (var e in Game.Combat.Engaged) botTargets.Add(e);
            // el jefe activo no siempre está en Engaged (lo maneja la arena)
            if (Game.Combat.ActiveBoss != null && !botTargets.Contains(Game.Combat.ActiveBoss)) botTargets.Add(Game.Combat.ActiveBoss);
            foreach (var e in botTargets)
            {
                if (e == null || !e.IsAlive) continue;
                float d = CombatMath.FlatDistance(e.transform.position, p.transform.position);
                if (d < best) { best = d; nearest = e; }
                // un anillo de aviso a la vista: mejor no empezar un ataque (no se puede desviar a mitad del tajo)
                if (e.InTell && d < 7f) threatened = true;
            }
            // defensa: aprieta cuando se cumple su tiempo de reacción (no depende del cooldown de acciones)
            for (int i = pending.Count - 1; i >= 0; i--)
            {
                if (Time.unscaledTime < pending[i].Key) continue;
                var act = pending[i].Value;
                pending.RemoveAt(i);
                InputReader.VirtualTap(act);
                if (act == Act.Dash) BotDashes++; else BotParries++;
                nextBotAction = Time.unscaledTime + 0.25f;
                return;
            }
            if (nearest == null) { InputReader.VirtualMove = Vector2.zero; return; }

            // acercarse en espacio de cámara (el "stick" es relativo a la cámara)
            Vector3 to = nearest.transform.position - p.transform.position; to.y = 0f;
            var cam = Camera.main != null ? Camera.main.transform : null;
            Vector3 f = cam != null ? Vector3.ProjectOnPlane(cam.forward, Vector3.up).normalized : Vector3.forward;
            Vector3 r = cam != null ? Vector3.ProjectOnPlane(cam.right, Vector3.up).normalized : Vector3.right;
            InputReader.VirtualMove = best > 2.2f ? new Vector2(Vector3.Dot(to.normalized, r), Vector3.Dot(to.normalized, f)) : Vector2.zero;

            if (Time.unscaledTime < nextBotAction) return;
            if (p.FinisherCandidate() != null) { InputReader.VirtualTap(Act.Finisher); BotFinishers++; nextBotAction = Time.unscaledTime + 1.2f; }
            // no empezar un ataque si alguien está por pegar (el anillo ya se está dibujando) ni contra una guardia
            // (una persona ve el rebote: el segundo golpe contra la guardia se lo devuelven)
            else if (best < 2.6f && !threatened && pending.Count == 0 && nearest.State != EnemyState.Guard) { InputReader.VirtualTap(Act.Attack); BotAttacks++; nextBotAction = Time.unscaledTime + 0.32f; }
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
                case "talk": return Talk(F(t, 1, 15f));
                case "waitcontrol": return WaitControl(F(t, 1, 30f));
                case "goto": return GoTo(F(t, 1, 0f), F(t, 2, 0f), F(t, 3, 20f));
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

        static bool DialogueOpen => Game.UI != null && Game.UI.DialogueOpen;

        IEnumerator Talk(float max)
        {
            float t = 0f;
            while (!DialogueOpen && t < max) { t += Time.unscaledDeltaTime; yield return null; }
            float quiet = 0f;
            while (quiet < 1.2f && t < max + 120f)
            {
                if (DialogueOpen) { quiet = 0f; InputReader.VirtualTap(Act.Submit); yield return new WaitForSecondsRealtime(0.35f); t += 0.35f; }
                else { quiet += Time.unscaledDeltaTime; t += Time.unscaledDeltaTime; yield return null; }
            }
        }

        IEnumerator WaitControl(float max)
        {
            float t = 0f;
            while ((Game.InCutscene || DialogueOpen || Game.Player == null) && t < max) { t += Time.unscaledDeltaTime; yield return null; }
        }

        IEnumerator GoTo(float x, float z, float max)
        {
            float t = 0f;
            while (t < max && Game.Player != null)
            {
                Vector3 to = new Vector3(x, 0f, z) - Game.Player.transform.position; to.y = 0f;
                if (to.magnitude < 1.2f) break;
                var cam = Camera.main != null ? Camera.main.transform : null;
                Vector3 f = cam != null ? Vector3.ProjectOnPlane(cam.forward, Vector3.up).normalized : Vector3.forward;
                Vector3 r = cam != null ? Vector3.ProjectOnPlane(cam.right, Vector3.up).normalized : Vector3.right;
                InputReader.VirtualMove = new Vector2(Vector3.Dot(to.normalized, r), Vector3.Dot(to.normalized, f));
                t += Time.unscaledDeltaTime;
                yield return null;
            }
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
