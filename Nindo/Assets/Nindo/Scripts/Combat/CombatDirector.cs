using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Coordina a los enemigos: quién puede atacar (tokens, para que en peleas grupales no
    /// ataquen todos a la vez y el parry siga siendo legible), qué enemigos están "en combate"
    /// (cámara, música) y búsquedas de objetivos para el fijado.
    /// </summary>
    public class CombatDirector : MonoBehaviour
    {
        [Tooltip("Cuántos enemigos pueden estar atacando al mismo tiempo")]
        public int maxAttackers = 2;
        [Tooltip("Radio en el que un enemigo alerta cuenta como 'en combate'")]
        public float engageRadius = 16f;

        readonly List<Enemy> enemies = new List<Enemy>(64);
        readonly List<Enemy> engaged = new List<Enemy>(16);
        readonly HashSet<Enemy> attackers = new HashSet<Enemy>();
        float lastTokenTime;
        bool inCombat;
        float leaveCombatTimer;

        public IReadOnlyList<Enemy> Engaged => engaged;
        public IReadOnlyList<Enemy> All => enemies;
        public bool InCombat => inCombat;
        public Boss ActiveBoss { get; set; }

        void Awake() { Game.Combat = this; }
        void OnDestroy() { if (Game.Combat == this) Game.Combat = null; }

        public void Register(Enemy e) { if (!enemies.Contains(e)) enemies.Add(e); }
        public void Unregister(Enemy e)
        {
            enemies.Remove(e); engaged.Remove(e); attackers.Remove(e); strikes.Remove(e);
        }

        // ------------------------------------------------------------ tokens
        public bool RequestAttackToken(Enemy e)
        {
            if (attackers.Contains(e)) return true;
            int limit = ActiveBoss != null ? 1 + (e is Boss ? 1 : 0) : maxAttackers;
            if (attackers.Count >= limit) return false;
            // pequeño escalonado entre ataques de distintos enemigos
            if (attackers.Count > 0 && Time.time - lastTokenTime < 0.6f) return false;
            attackers.Add(e);
            lastTokenTime = Time.time;
            return true;
        }

        public void ReleaseAttackToken(Enemy e) => attackers.Remove(e);
        public bool HasToken(Enemy e) => attackers.Contains(e);

        // ------------------------------------------------------------ separación de golpes
        // Los tokens solo escalonan el INICIO de los ataques; dónde cae cada golpe depende de la distancia,
        // el clip y la embestida, y dos golpes a < 0.2 s no se pueden desviar los dos. Cada enemigo anota
        // cuándo va a pegar (Time.time absoluto) y el que llega después espera en su apex.
        [Tooltip("Separación mínima entre golpes de distintos enemigos (s)")] public float minStrikeSpacing = 0.42f;
        [Tooltip("Separación entre un jefe y sus esbirros (s)")] public float bossStrikeSpacing = 0.5f;
        /// <summary>Más espera que esto y el ataque no arranca (vuelve a rondar y reintenta).</summary>
        public const float MaxStrikeDelay = 0.6f;
        readonly Dictionary<Enemy, float> strikes = new Dictionary<Enemy, float>(8);

        /// <summary>
        /// Reserva el golpe de 'e' para el instante 'naturalTime' (Time.time) y devuelve cuánto tiene que
        /// demorarlo (pausa extra en el apex) para quedar separado de los golpes ya anotados de otros enemigos.
        /// Los pasos del propio combo no cuentan (reemplazan su reserva).
        /// </summary>
        public float ReserveStrike(Enemy e, float naturalTime)
        {
            float shift = 0f;
            // corrimiento mínimo: cada choque empuja el golpe detrás del otro; con 2-3 atacantes converge rápido
            for (int iter = 0; iter < 4; iter++)
            {
                bool moved = false;
                foreach (var kv in strikes)
                {
                    if (kv.Key == e || kv.Key == null) continue;
                    float gap = e is Boss || kv.Key is Boss ? bossStrikeSpacing : minStrikeSpacing;
                    float t = naturalTime + shift;
                    if (Mathf.Abs(t - kv.Value) < gap) { shift = kv.Value + gap - naturalTime; moved = true; }
                }
                if (!moved) break;
            }
            strikes[e] = naturalTime + shift;
            return shift;
        }

        /// <summary>El golpe se movió (hit-stop local, embestida que persigue): actualiza la reserva.</summary>
        public void UpdateStrike(Enemy e, float time) { if (strikes.ContainsKey(e)) strikes[e] = time; }
        public void ReleaseStrike(Enemy e) => strikes.Remove(e);

        void Update()
        {
            var p = Game.Player;
            engaged.Clear();
            if (p != null && p.IsAlive)
            {
                Vector3 pp = p.transform.position;
                for (int i = 0; i < enemies.Count; i++)
                {
                    var e = enemies[i];
                    if (e == null || !e.IsAlive || !e.IsAggro) continue;
                    if ((e.transform.position - pp).sqrMagnitude < engageRadius * engageRadius) engaged.Add(e);
                }
            }
            // limpiar tokens y golpes anotados de enemigos que ya no atacan
            if (attackers.Count > 0 || strikes.Count > 0)
            {
                tmp.Clear();
                foreach (var a in attackers) if (a == null || !a.IsAlive) tmp.Add(a);
                foreach (var kv in strikes) if (kv.Key == null || !kv.Key.IsAlive || kv.Value < Time.time - 1f) tmp.Add(kv.Key);
                foreach (var a in tmp) { attackers.Remove(a); strikes.Remove(a); }
            }
            bool now = engaged.Count > 0 || ActiveBoss != null;
            if (now) leaveCombatTimer = 2.5f;
            else leaveCombatTimer -= Time.deltaTime;
            bool state = now || leaveCombatTimer > 0f;
            if (state != inCombat)
            {
                inCombat = state;
                GameEvents.RaiseCombatState(inCombat);
            }
        }

        readonly List<Enemy> tmp = new List<Enemy>(8);

        // ------------------------------------------------------------ queries
        public Enemy FindBestTarget(Vector3 from, Vector3 facing, float range, Enemy exclude = null)
        {
            Enemy best = null; float bestScore = float.MaxValue;
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (e == null || !e.IsAlive || e == exclude || !e.Targetable) continue;
                Vector3 d = (e.transform.position - from).Flat();
                float dist = d.magnitude;
                if (dist > range) continue;
                float ang = facing.sqrMagnitude > 0.01f ? Vector3.Angle(facing.Flat(), d) : 0f;
                float score = dist + ang * 0.05f;
                if (score < bestScore) { bestScore = score; best = e; }
            }
            return best;
        }

        /// <summary>Siguiente objetivo ordenado por ángulo alrededor del jugador (para cambiar de fijado).</summary>
        public Enemy CycleTarget(Vector3 from, Enemy current, float range, int dir)
        {
            sortBuf.Clear();
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (e == null || !e.IsAlive || !e.Targetable) continue;
                if (CombatMath.FlatDistance(e.transform.position, from) <= range) sortBuf.Add(e);
            }
            if (sortBuf.Count == 0) return null;
            if (current == null || sortBuf.Count == 1) return sortBuf[0];
            Vector3 camRight = Game.Camera != null ? Game.Camera.transform.right.Flat() : Vector3.right;
            sortBuf.Sort((a, b) => Vector3.Dot(a.transform.position - from, camRight).CompareTo(Vector3.Dot(b.transform.position - from, camRight)));
            int idx = sortBuf.IndexOf(current);
            if (idx < 0) return sortBuf[0];
            idx = (idx + dir + sortBuf.Count) % sortBuf.Count;
            return sortBuf[idx];
        }

        readonly List<Enemy> sortBuf = new List<Enemy>(16);

        /// <summary>Centroide de los enemigos en combate (para encuadrar la cámara).</summary>
        public bool EngagedBounds(out Vector3 center, out float radius)
        {
            center = Vector3.zero; radius = 0f;
            if (engaged.Count == 0) return false;
            for (int i = 0; i < engaged.Count; i++) center += engaged[i].transform.position;
            center /= engaged.Count;
            for (int i = 0; i < engaged.Count; i++)
                radius = Mathf.Max(radius, CombatMath.FlatDistance(center, engaged[i].transform.position));
            return true;
        }

        /// <summary>Aturde/alerta a todos los enemigos cercanos (p. ej. al iniciar un encuentro).</summary>
        public void AlertAround(Vector3 pos, float radius)
        {
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (e != null && e.IsAlive && (e.transform.position - pos).sqrMagnitude < radius * radius)
                    e.Alert();
            }
        }
    }
}
