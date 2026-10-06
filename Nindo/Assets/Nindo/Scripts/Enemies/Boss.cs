using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Jefe: enemigo con fases, presentación cinemática, barra de vida grande, arena cerrada y
    /// movimientos especiales (golpe sísmico, giro, ola, embestida, teletransporte, clones...).
    /// </summary>
    public class Boss : Enemy
    {
        [Header("Jefe")]
        public string bossId = "goro";
        public string title = "Gorō";
        public string subtitle = "El Martillo de Kodoyama";
        [Tooltip("Umbrales de vida (0..1) que inician cada fase nueva")] public float[] phaseThresholds = { 0.5f };
        public bool hasSeal = true;
        public SealId seal = SealId.Montana;
        public string introAnim = "Intro";
        public string phaseAnim = "Spotted";
        public string musicKey = "boss";
        public Vector3 arenaCenter;
        public float arenaRadius = 14f;
        [Tooltip("Arquetipo de los esbirros que invoca (si usa 'summon')")] public string minionArchetype = "ninja";
        public float phaseSpeedBonus = 0.15f;

        public bool Fighting { get; private set; }
        public bool Defeated { get; private set; }
        public bool FinisherAllowed => Health01 <= config.finisherHealth + 0.001f;
        int phase;
        public override int CurrentPhase => phase;

        readonly List<Enemy> minions = new List<Enemy>();
        float spinTick;
        bool hiddenForTeleport;
        // olas de Mizuchi: cuándo llega la próxima a Kaito (se calcula una vez por frame)
        float projEta = float.PositiveInfinity;
        Vector3 projFrom;
        bool waveCued;   // ya sonó el aviso de la ola por salir (que no suene otra vez al aparecer)
        // config original: los cambios de fase la modifican y al reintentar se restaura
        EnemyConfig pristineConfig;

        protected override void Start()
        {
            pristineConfig = config.Clone();
            base.Start();
            if (arenaCenter == Vector3.zero) arenaCenter = transform.position;
            if (Game.Save.HasFlag(Flags.Boss(bossId)))
            {
                Defeated = true;
                gameObject.SetActive(false);
            }
        }

        // ---------------------------------------------------------------- pelea
        /// <summary>No despierta solo: lo inicia la arena (BossArena) tras la presentación.</summary>
        protected override void TickIdle(float dt) { }

        public void BeginFight()
        {
            if (Fighting || Defeated) return;
            Fighting = true;
            phase = 0;
            IsAggro = true;
            target = Game.Player;
            if (Game.Combat != null) Game.Combat.ActiveBoss = this;
            Game.UI?.ShowBossBar(this);
            Game.Audio?.PlayMusic(musicKey);
            GameEvents.RaiseBossStarted(this);
            SetState(EnemyState.Chase);
            nextAttackTime = Time.time + 0.6f;
        }

        public override void ResetEnemy()
        {
            // deshace la aceleración de las fases (si no, cada reintento lo hace más rápido)
            if (pristineConfig != null) config = pristineConfig.Clone();
            base.ResetEnemy();
            Fighting = false;
            phase = 0;
            ShowModel(true);
            foreach (var m in minions) if (m != null) Destroy(m.gameObject);
            minions.Clear();
            if (Game.Combat != null && Game.Combat.ActiveBoss == this) Game.Combat.ActiveBoss = null;
            Game.UI?.HideBossBar();
        }

        protected override void Update()
        {
            base.Update();
            UpdateProjectiles();
            if (!Fighting || !IsAlive) return;
            // no salir de la arena
            Vector3 off = (transform.position - arenaCenter).Flat();
            if (off.magnitude > arenaRadius) MoveBy(-off.normalized * (off.magnitude - arenaRadius));
        }

        protected override void OnDamaged(in DamageInfo info)
        {
            int newPhase = 0;
            for (int i = 0; i < phaseThresholds.Length; i++)
                if (Health01 <= phaseThresholds[i]) newPhase = i + 1;
            if (newPhase > phase) StartCoroutine(PhaseChange(newPhase));
        }

        IEnumerator PhaseChange(int newPhase)
        {
            phase = newPhase;
            ReleaseToken();
            SetState(EnemyState.Scripted);
            Imbalance = 0f;
            anim.Play(phaseAnim, 0.1f);
            Game.Audio?.Play("boss_roar", transform.position, 1f);
            Game.Camera?.Shake(0.7f);
            Game.Camera?.Punch(-4f, 0.5f);
            Game.Time?.SlowMotion(0.4f, 0.7f, 0.05f, 0.3f);
            Game.FX?.Shockwave(transform.position, 6f, new Color(1f, 0.4f, 0.3f));
            Game.UI?.ShowToast($"{title} se enfurece", new Color(1f, 0.5f, 0.4f));
            if (target != null && CombatMath.FlatDistance(target.transform.position, transform.position) < 5f)
                target.Push((target.transform.position - transform.position), 3f);
            config.attackCooldown *= 0.75f;
            config.ScaleSteps(1f, 1f + phaseSpeedBonus); // cada golpe una vez, aunque lo compartan varios patrones
            yield return new WaitForSeconds(1.1f);
            if (IsAlive) { SetState(EnemyState.Chase); nextAttackTime = Time.time + 0.3f; }
        }

        // ---------------------------------------------------------------- especiales
        protected override void OnStepStarted(AttackDef a)
        {
            spinTick = 0f;
            waveCued = false;
        }

        // la ola no pega en activeStart: su golpe es el del proyectil, que avisa a los pies de Kaito (ProjectileEta)
        protected override float ComputeStrikeEta(AttackDef a) => a.special == "wave" ? float.PositiveInfinity : base.ComputeStrikeEta(a);
        protected override bool StepHasTell(AttackDef a) => a.special != "wave" && base.StepHasTell(a);

        protected override bool HitAreaFor(AttackDef a, out TellArea area)
        {
            switch (a.special)
            {
                case "spin":
                    area = new TellArea { origin = transform.position, size = a.range };
                    return true;
                case "windslash":
                    area = new TellArea { lane = true, origin = transform.position, forward = transform.forward.Flat().normalized, size = a.specialParam > 0 ? a.specialParam : 9f, width = 2.8f };
                    return true;
                default: return base.HitAreaFor(a, out area);
            }
        }

        public override float ProjectileEta => projEta;
        public override Vector3 ProjectileFrom => projFrom;

        /// <summary>
        /// Próxima ola que va a tocar a Kaito: las que están en vuelo y la que está por salir (misma cuenta desde
        /// donde va a aparecer). A 0.32 s suena el hyōshigi, igual que con un golpe desviable.
        /// </summary>
        void UpdateProjectiles()
        {
            projEta = float.PositiveInfinity;
            if (target == null || !target.IsAlive) return;
            Vector3 p = target.transform.position;
            WaveProjectile next = null;
            foreach (var w in WaveProjectile.Active)
            {
                if (w == null || w.Owner != this) continue;
                float eta = w.TimeToHit(p);
                if (eta < projEta) { projEta = eta; projFrom = w.transform.position; next = w; }
            }
            var a = CurrentAttack;
            bool pending = a != null && a.special == "wave" && !specialFired;
            if (pending)
            {
                float wait = Mathf.Max(0f, tl.T - stepClock), speed = WaveProjectile.SpeedFor(a);
                int n = Mathf.Max(1, Mathf.RoundToInt(a.specialParam));
                for (int i = 0; i < n; i++)
                {
                    Vector3 dir = WaveDirection(i, n);
                    float eta = wait + WaveProjectile.TimeToHit(transform.position + dir * 1.2f, dir, speed, p);
                    if (eta < projEta) { projEta = eta; projFrom = transform.position; next = null; }
                }
            }
            if (projEta > TellStyle.TickParryable) return;
            // aviso "¡ya!" de la ola: una sola vez por ola (o por ola por salir)
            if (next != null ? next.cued : waveCued) return;
            if (next != null) next.cued = true; else waveCued = true;
            Game.Audio?.Play("tell_tick", null, 0.8f, 0.03f);
            GameEvents.RaiseStrikeCue(next != null ? (Component)next : this, false);
        }

        Vector3 WaveDirection(int i, int n) => Quaternion.Euler(0f, (i - (n - 1) * 0.5f) * 22f, 0f) * transform.forward;

        protected override void TickSpecial(AttackDef a, float dt)
        {
            bool active = stepNorm >= a.activeStart && stepNorm <= a.activeEnd;
            switch (a.special)
            {
                case "spin":
                    if (active)
                    {
                        if (target != null) MoveTo(target.transform.position, a.specialParam > 0 ? a.specialParam : 3.5f);
                        model.localRotation = modelBaseRot * Quaternion.Euler(0f, stateTime * 900f, 0f);
                        spinTick -= dt;
                        if (spinTick <= 0f && target != null && CombatMath.FlatDistance(target.transform.position, transform.position) <= a.range + target.Radius)
                        {
                            spinTick = 0.35f;
                            HitPlayer(a, transform.position);
                        }
                    }
                    else if (stepNorm > a.activeEnd) { RestoreModelRotation(); Stop(); }
                    break;

                case "wave":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        int n = Mathf.Max(1, Mathf.RoundToInt(a.specialParam));
                        for (int i = 0; i < n; i++)
                        {
                            Vector3 dir = WaveDirection(i, n);
                            WaveProjectile.Spawn(this, transform.position + dir * 1.2f + Vector3.up * 0.4f, dir, a, waveCued);
                        }
                        Game.Audio?.Play("wave", transform.position, 1f);
                    }
                    break;

                case "teleport":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        StartCoroutine(TeleportBehindTarget(a.specialParam > 0 ? a.specialParam : 2.6f));
                    }
                    break;

                case "summon":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Summon(Mathf.Max(1, Mathf.RoundToInt(a.specialParam)), false);
                    }
                    break;

                case "clones":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Summon(Mathf.Max(1, Mathf.RoundToInt(a.specialParam)), true);
                    }
                    break;

                case "windslash":
                    // telegrafía una línea y la atraviesa (imparable: hay que esquivar con dash)
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Vector3 from = transform.position;
                        Vector3 to = from + transform.forward * (a.specialParam > 0 ? a.specialParam : 9f);
                        Game.FX?.SlashLine(from + Vector3.up, to + Vector3.up);
                        Vector3 p = target != null ? target.transform.position : to;
                        Vector3 ab = (to - from).Flat();
                        float t = Mathf.Clamp01(Vector3.Dot((p - from).Flat(), ab) / Mathf.Max(0.01f, ab.sqrMagnitude));
                        if (target != null && CombatMath.FlatDistance(from + ab * t, p) < 1.4f) HitPlayer(a, from);
                        MoveBy(ab * 0.95f);
                        Game.Audio?.Play("ability_wind", transform.position, 1f);
                    }
                    break;

                default:
                    base.TickSpecial(a, dt);
                    break;
            }
        }

        IEnumerator TeleportBehindTarget(float dist)
        {
            Game.FX?.SmokePuff(transform.position + Vector3.up * 0.6f, 1.4f);
            Game.Audio?.Play("teleport", transform.position, 0.9f);
            ShowModel(false);
            yield return new WaitForSeconds(0.25f);
            if (target != null)
            {
                Vector3 behind = target.transform.position - target.transform.forward * dist;
                behind.y = target.transform.position.y;
                MoveBy(behind - transform.position);
                transform.rotation = Quaternion.LookRotation((target.transform.position - behind).Flat().normalized);
            }
            Game.FX?.SmokePuff(transform.position + Vector3.up * 0.6f, 1.2f);
            ShowModel(true);
        }

        void ShowModel(bool v)
        {
            if (hiddenForTeleport == !v) return;
            hiddenForTeleport = !v;
            foreach (var r in model.GetComponentsInChildren<Renderer>()) r.enabled = v;
        }

        void Summon(int count, bool clones)
        {
            minions.RemoveAll(m => m == null || !m.IsAlive);
            if (minions.Count >= count) return;
            for (int i = 0; i < count; i++)
            {
                float ang = (360f / count) * i + Random.Range(-20f, 20f);
                Vector3 pos = transform.position + Quaternion.Euler(0, ang, 0) * Vector3.forward * 3.5f;
                Enemy e = clones ? EnemyFactory.SpawnClone(this, pos) : EnemyFactory.Spawn(minionArchetype, pos, Quaternion.LookRotation((transform.position - pos).Flat().normalized + Vector3.forward * 0.001f), null);
                if (e != null)
                {
                    minions.Add(e);
                    Game.FX?.SmokePuff(pos + Vector3.up * 0.6f, 1.2f);
                    e.startAggro = true;
                    e.Alert();
                }
            }
            Game.Audio?.Play("summon", transform.position, 1f);
        }

        // ---------------------------------------------------------------- derrota
        protected override void Die(in DamageInfo info, bool finisher = false)
        {
            if (State == EnemyState.Dead) return;
            Defeated = true;
            Fighting = false;
            foreach (var m in minions) if (m != null && m.IsAlive) m.Execute(Game.Player);
            if (Game.Combat != null && Game.Combat.ActiveBoss == this) Game.Combat.ActiveBoss = null;
            Game.UI?.HideBossBar();
            Game.Time?.SlowMotion(0.15f, 2.2f, 0.02f, 0.8f);
            Game.Camera?.PlayBossDeathShot(transform);
            Game.Audio?.Play("boss_defeat", transform.position, 1f);
            Game.Audio?.StopMusic(2f);
            Game.Save.SetFlag(Flags.Boss(bossId));
            base.Die(info, finisher);
            GameEvents.RaiseBossDefeated(this);
        }

        protected override void OnDeathFinished()
        {
            if (hasSeal) KeyPickup.Spawn(seal, transform.position + Vector3.up * 0.2f);
            gameObject.SetActive(false);
        }
    }

    /// <summary>Proyectil de agua (Mizuchi). Se puede desviar con parry o esquivar con dash.</summary>
    public class WaveProjectile : MonoBehaviour
    {
        /// <summary>Olas en vuelo: el jefe calcula con ellas cuándo llega la próxima a Kaito (aviso a sus pies).</summary>
        public static readonly List<WaveProjectile> Active = new List<WaveProjectile>();
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => Active.Clear();

        /// <summary>Distancia a la que la ola alcanza a Kaito (m).</summary>
        public const float HitRadius = 1.1f;
        public Enemy Owner => owner;
        /// <summary>Ya sonó el aviso "¡ya!" de esta ola.</summary>
        [System.NonSerialized] public bool cued;

        Enemy owner;
        AttackDef attack;
        Vector3 dir;
        float speed = 11f, life = 2.2f;
        bool done;

        public static float SpeedFor(AttackDef a) => a.specialParam > 4f ? a.specialParam : 11f;

        public static void Spawn(Enemy owner, Vector3 pos, Vector3 dir, AttackDef a, bool cued)
        {
            var go = Game.FX != null ? Game.FX.MakeWave(pos, dir) : new GameObject("Wave");
            go.transform.position = pos;
            var w = go.GetComponent<WaveProjectile>();
            if (w == null) w = go.AddComponent<WaveProjectile>();
            w.owner = owner; w.attack = a; w.dir = dir.Flat().normalized; w.done = false; w.life = 2.2f; w.cued = cued;
            w.speed = SpeedFor(a);
            if (!Active.Contains(w)) Active.Add(w);
        }

        /// <summary>Segundos hasta que una ola que sale de 'from' hacia 'dir' pase a HitRadius de 'p' (infinito si no lo toca).</summary>
        public static float TimeToHit(Vector3 from, Vector3 dir, float speed, Vector3 p)
        {
            Vector3 d = (p - from).Flat();
            float along = Vector3.Dot(d, dir);
            float lat2 = d.sqrMagnitude - along * along;
            if (lat2 >= HitRadius * HitRadius) return float.PositiveInfinity;
            float reach = along - Mathf.Sqrt(HitRadius * HitRadius - lat2);
            if (reach < -HitRadius) return float.PositiveInfinity;   // ya pasó
            return Mathf.Max(0f, reach) / Mathf.Max(0.1f, speed);
        }

        /// <summary>Segundos hasta que esta ola alcance a 'p' (infinito si no va a tocarlo antes de deshacerse).</summary>
        public float TimeToHit(Vector3 p)
        {
            if (done) return float.PositiveInfinity;
            float t = TimeToHit(transform.position, dir, speed, p);
            return t <= life ? t : float.PositiveInfinity;
        }

        void OnDisable() => Active.Remove(this);

        void Update()
        {
            if (done) return;
            float dt = Time.deltaTime;
            transform.position += dir * speed * dt;
            transform.rotation = Quaternion.LookRotation(dir);
            life -= dt;
            var p = Game.Player;
            if (p != null && p.IsAlive && CombatMath.FlatDistance(p.transform.position, transform.position) < HitRadius)
            {
                var info = new DamageInfo { damage = attack.damage, kind = AttackKind.Projectile, direction = dir, knockback = attack.knockback, sourceFaction = Faction.Enemy, source = owner, attackName = "Ola" };
                var r = p.ReceiveHit(info);
                if (r != HitResult.Dodged && r != HitResult.Ignored) { Burst(); return; }
            }
            if (life <= 0f) Burst();
        }

        void Burst()
        {
            done = true;
            Active.Remove(this);
            Game.FX?.Splash(transform.position);
            Pool.Despawn(gameObject);
        }
    }
}
