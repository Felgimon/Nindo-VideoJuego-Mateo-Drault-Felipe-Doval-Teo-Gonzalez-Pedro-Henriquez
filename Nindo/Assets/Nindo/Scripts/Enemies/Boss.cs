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
        bool specialFired;
        bool hiddenForTeleport;
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
            specialFired = false;
            spinTick = 0f;
        }

        protected override float ComputeStrikeEta(AttackDef a, float holdEnd)
        {
            switch (a.special)
            {
                // nada pega en activeStart (la onda pega cuando llega; el AutoPilot la tendría que mirar aparte)
                case "teleport": case "summon": case "clones": case "wave": return float.PositiveInfinity;
                case "charge":
                    if (stepHit || stepNorm > a.activeEnd || target == null) return float.PositiveInfinity;
                    float pre = stepNorm < a.activeStart ? EstimateStrikeEta(a, holdEnd) : 0f;
                    float room = Mathf.Max(0f, DistToTarget - Radius - target.Radius - 0.6f);
                    return pre + room / (a.specialParam > 0f ? a.specialParam : 14f);
                default: return base.ComputeStrikeEta(a, holdEnd);
            }
        }

        protected override void TickSpecial(AttackDef a, float dt)
        {
            bool active = stepNorm >= a.activeStart && stepNorm <= a.activeEnd;
            switch (a.special)
            {
                case "slam":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Vector3 c = transform.position + transform.forward * Mathf.Max(0.5f, a.range * 0.4f);
                        float radius = a.specialParam > 0f ? a.specialParam : 4f;
                        Game.FX?.Shockwave(c, radius, new Color(1f, 0.75f, 0.45f));
                        Game.FX?.GroundCrack(c, radius);
                        Game.Camera?.Shake(0.75f);
                        Game.Audio?.Play("slam", c, 1f);
                        Game.Input?.Rumble(0.9f, 0.6f, 0.3f);
                        if (target != null && CombatMath.FlatDistance(target.transform.position, c) <= radius + target.Radius)
                            HitPlayer(a, c);
                    }
                    break;

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
                            float ang = (i - (n - 1) * 0.5f) * 22f;
                            Vector3 dir = Quaternion.Euler(0f, ang, 0f) * transform.forward;
                            WaveProjectile.Spawn(this, transform.position + dir * 1.2f + Vector3.up * 0.4f, dir, a);
                        }
                        Game.Audio?.Play("wave", transform.position, 1f);
                    }
                    break;

                case "charge":
                    if (active)
                    {
                        float speed = a.specialParam > 0f ? a.specialParam : 14f;
                        MoveBy(transform.forward * speed * dt);
                        if (!stepHit && target != null && CombatMath.FlatDistance(target.transform.position, transform.position) <= Radius + target.Radius + 0.6f)
                        {
                            stepHit = true;
                            HitPlayer(a, transform.position);
                        }
                        Game.FX?.DustTrail(transform.position);
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
        Enemy owner;
        AttackDef attack;
        Vector3 dir;
        float speed = 11f, life = 2.2f;
        bool done;

        public static void Spawn(Enemy owner, Vector3 pos, Vector3 dir, AttackDef a)
        {
            var go = Game.FX != null ? Game.FX.MakeWave(pos, dir) : new GameObject("Wave");
            go.transform.position = pos;
            var w = go.GetComponent<WaveProjectile>();
            if (w == null) w = go.AddComponent<WaveProjectile>();
            w.owner = owner; w.attack = a; w.dir = dir.Flat().normalized; w.done = false; w.life = 2.2f;
            w.speed = a.specialParam > 0 && a.specialParam > 4 ? a.specialParam : 11f;
        }

        void Update()
        {
            if (done) return;
            float dt = Time.deltaTime;
            transform.position += dir * speed * dt;
            transform.rotation = Quaternion.LookRotation(dir);
            life -= dt;
            var p = Game.Player;
            if (p != null && p.IsAlive && CombatMath.FlatDistance(p.transform.position, transform.position) < 1.1f)
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
            Game.FX?.Splash(transform.position);
            Pool.Despawn(gameObject);
        }
    }
}
