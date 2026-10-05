using System.Collections;
using UnityEngine;
using UnityEngine.AI;

namespace Nindo
{
    public enum EnemyState { Idle, Alert, Chase, Strafe, Attack, Recoil, Guard, Counter, Exhausted, Stagger, Executed, Dead, Scripted }

    /// <summary>
    /// IA de enemigo genérica y data-driven. Mantiene el ritmo de combate original de Nindo:
    ///  * el enemigo ataca en combos; cada PARRY de Kaito le suma DESEQUILIBRIO;
    ///  * si termina el combo desequilibrado queda AGOTADO (vulnerable, se lo puede ejecutar);
    ///  * cada golpe a un enemigo agotado le consume desequilibrio; al quedar en 0 se pone en GUARDIA;
    ///  * si le pegás en guardia te DESVÍA el golpe y contraataca.
    /// Reemplaza a EnemyMovement + EnemyCombat + EnemyBeingDamaged + versiones del luchador.
    /// </summary>
    public class Enemy : MonoBehaviour, IHittable
    {
        public EnemyConfig config = new EnemyConfig();
        [Tooltip("Encuentro al que pertenece (se reinicia si Kaito muere)")] public Encounter encounter;
        public bool startAggro;

        public EnemyState State { get; protected set; } = EnemyState.Idle;
        public float Health { get; protected set; }
        public float Health01 => config.maxHealth > 0 ? Health / config.maxHealth : 0f;
        public float Imbalance { get; protected set; }
        public float Imbalance01 => config.maxImbalance > 0 ? Imbalance / config.maxImbalance : 0f;
        public bool IsAlive => State != EnemyState.Dead && State != EnemyState.Executed;
        public bool IsAggro { get; protected set; }
        public bool Targetable => IsAlive && gameObject.activeInHierarchy && State != EnemyState.Scripted;
        public Faction Faction => Faction.Enemy;
        public Transform Root => transform;
        public float Radius => config.radius * Mathf.Max(0.5f, config.scale);
        public Vector3 AimPoint => transform.position + Vector3.up * config.height * 0.55f * config.scale;
        public CharacterAnimator Anim => anim;
        public bool IsTelegraphingUnblockable { get; private set; }
        public bool IsExhausted => State == EnemyState.Exhausted;
        /// <summary>El golpe actual está por salir (para tutoriales en cámara lenta).</summary>
        /// <remarks>Se mide en segundos de juego (no en tiempo normalizado del clip): a cualquier framerate
        /// hay al menos un frame dentro de la ventana, y si el jugador aprieta parry en ese momento
        /// el golpe cae dentro de su ventana de parry (PlayerConfig.parryWindow).</remarks>
        public bool AboutToStrike => State == EnemyState.Attack && StrikeEta <= StrikeWarning;
        /// <summary>Segundos de juego que faltan para que salga el golpe actual (infinito si no hay uno por salir).</summary>
        public float StrikeEta => State == EnemyState.Attack ? strikeEta : float.PositiveInfinity;
        float strikeEta = float.PositiveInfinity;
        /// <summary>Alcance del golpe en curso: arco del ataque más lo que le queda de embestida.</summary>
        public float StrikeReach { get; private set; }
        public const float StrikeWarning = 0.18f;
        public float LastHitTime { get; private set; } = -99f;
        public Transform katanaTip, katanaBase;

        protected CharacterAnimator anim = new CharacterAnimator();
        protected NavMeshAgent agent;
        protected Transform model;
        protected float stateTime;
        protected PlayerController target;
        protected Vector3 spawnPos;
        protected Quaternion spawnRot;
        protected float nextAttackTime;
        protected AttackPattern pattern;
        protected int step;
        protected float stepNorm, stepLen;
        protected bool stepHit;
        protected bool telegraphed;
        protected float strafeDir = 1f;
        protected float strafeSwitch;
        protected int neutralHits;
        protected float lastNeutralHit;
        protected float stateDuration;
        protected BladeTrail trail;
        HitFlash flash;
        Vector3 knock;
        float baseAgentSpeed;
        bool useAgent;
        // pose local del modelo tal como la dejó CharacterFactory (NormalizeHeight: escala y pies en y=0)
        Vector3 modelBasePos, modelBaseScale = Vector3.one;
        protected Quaternion modelBaseRot = Quaternion.identity;
        // tiene token y patrón elegido: se acerca hasta tenerlo en rango y ataca
        bool committed;
        float commitUntil;

        // =============================================================== setup
        protected virtual void Awake()
        {
            var a = GetComponentInChildren<Animator>();
            model = a != null ? a.transform : transform;
            anim.Init(a);
            agent = GetComponent<NavMeshAgent>();
            flash = HitFlash.Attach(model.gameObject);
            // el modelo ya está armado y normalizado (EnemyFactory lo crea antes de agregar este componente)
            modelBasePos = model.localPosition;
            modelBaseRot = model.localRotation;
            modelBaseScale = model.localScale;
        }

        protected virtual void Start()
        {
            Health = config.maxHealth;
            spawnPos = transform.position;
            spawnRot = transform.rotation;
            if (agent != null)
            {
                agent.updateRotation = false;
                agent.radius = Radius;
                agent.height = config.height * config.scale;
                agent.speed = config.runSpeed;
                agent.acceleration = 30f;
                agent.angularSpeed = 0f;
                agent.stoppingDistance = 0.1f;
                agent.autoBraking = true;
                agent.obstacleAvoidanceType = ObstacleAvoidanceType.MedQualityObstacleAvoidance;
                agent.avoidancePriority = Random.Range(40, 60);
                baseAgentSpeed = agent.speed;
            }
            if (katanaBase == null || katanaTip == null)
                KatanaRig.Find(model, new[] { "Katana", "katana", "Isan", "Cylinder.005", "Martillo", "Arma" }, out katanaBase, out katanaTip);
            if (katanaBase != null && katanaTip != null)
                trail = BladeTrail.Create(transform, katanaBase, katanaTip, Game.Content != null ? Game.Content.trailMaterial : null, new Color(0.85f, 0.85f, 1f, 0.6f));
            Game.Combat?.Register(this);
            anim.Play(config.animLocomotion, 0f);
            nextAttackTime = Time.time + Random.Range(0.4f, 1.2f);
            if (startAggro) Alert();
        }

        protected virtual void OnDestroy()
        {
            Game.Combat?.Unregister(this);
        }

        void OnEnable() { if (Game.Combat != null && Health > 0) Game.Combat.Register(this); }
        void OnDisable() { Game.Combat?.Unregister(this); }

        /// <summary>Vuelve al estado inicial (cuando Kaito muere y se reinicia el encuentro).</summary>
        public virtual void ResetEnemy()
        {
            StopAllCoroutines();
            gameObject.SetActive(true);
            // la muerte o un giro pueden haber quedado a medias: vuelve a la pose original del modelo
            if (model != null && model != transform) { model.localPosition = modelBasePos; model.localRotation = modelBaseRot; model.localScale = modelBaseScale; }
            Health = config.maxHealth;
            Imbalance = 0f;
            IsAggro = false;
            neutralHits = 0;
            pattern = null;
            ReleaseToken();
            Warp(spawnPos, spawnRot);
            SetState(EnemyState.Idle);
            anim.Play(config.animLocomotion, 0f);
            foreach (var c in GetComponentsInChildren<Collider>()) c.enabled = true;
            Game.Combat?.Register(this);
        }

        void Warp(Vector3 pos, Quaternion rot)
        {
            if (agent != null && agent.isOnNavMesh) agent.Warp(pos);
            else transform.position = pos;
            transform.rotation = rot;
        }

        // =============================================================== API
        public void Alert()
        {
            if (!IsAlive || IsAggro || State == EnemyState.Scripted) return;
            IsAggro = true;
            target = Game.Player;
            SetState(EnemyState.Alert);
            anim.Play(config.animSpotted, 0.1f);
            Game.UI?.ShowAlertMark(this);
            Game.Audio?.Play("alert", transform.position, 0.6f, 0.1f);
            stateDuration = Mathf.Clamp(anim.Length(config.animSpotted, 0.6f), 0.4f, 0.9f);
            // alerta a los compañeros del mismo encuentro
            encounter?.OnMemberAlerted(this);
        }

        public bool CanBeFinished(float healthThreshold)
        {
            if (!IsAlive || State == EnemyState.Scripted || this is Boss && !((Boss)this).FinisherAllowed) return false;
            return State == EnemyState.Exhausted || Health01 <= Mathf.Max(config.finisherHealth, healthThreshold) && Health01 > 0f;
        }

        // =============================================================== update
        protected virtual void Update()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) { anim.Tick(); return; }
            stateTime += dt;
            if (target == null) target = Game.Player;
            useAgent = agent != null && agent.enabled && agent.isOnNavMesh;

            switch (State)
            {
                case EnemyState.Idle: TickIdle(dt); break;
                case EnemyState.Alert: TickAlert(dt); break;
                case EnemyState.Chase: TickChase(dt); break;
                case EnemyState.Strafe: TickStrafe(dt); break;
                case EnemyState.Attack: TickAttack(dt); break;
                case EnemyState.Recoil: TickTimed(dt, () => ContinueCombo()); break;
                case EnemyState.Guard: TickGuard(dt); break;
                case EnemyState.Counter: TickTimed(dt, () => StartAttack(true)); break;
                case EnemyState.Exhausted: TickExhausted(dt); break;
                case EnemyState.Stagger: TickTimed(dt, () => SetState(EnemyState.Chase)); break;
            }
            // los controllers no tienen transiciones (todo es CrossFade por código): al volver a moverse
            // hay que reentrar al blend tree de locomoción, si no se desliza congelado en la última pose
            // (fin de Spotted, Guard, Hit, Counter, intro de jefe...)
            if ((State == EnemyState.Chase || State == EnemyState.Strafe || State == EnemyState.Idle) && stateTime > 0.02f && anim.Current != config.animLocomotion)
                anim.Play(config.animLocomotion, 0.15f);

            if (knock.sqrMagnitude > 0.0001f)
            {
                Vector3 step = knock * Mathf.Min(1f, dt * 10f);
                knock -= step;
                MoveBy(step);
            }
            anim.Tick();
            if (State == EnemyState.Chase || State == EnemyState.Strafe || State == EnemyState.Idle)
            {
                float v = useAgent ? agent.velocity.magnitude : 0f;
                anim.SetLocomotion(Mathf.Clamp01(v / Mathf.Max(0.1f, config.runSpeed)), dt);
            }
            else anim.SetLocomotion(0f, dt);
        }

        protected void SetState(EnemyState s)
        {
            // al salir del ataque (fin, stagger, cambio de fase...) el modelo vuelve a su rotación (p. ej. el giro de Gorō)
            if (State == EnemyState.Attack && s != EnemyState.Attack) { trail?.Stop(); IsTelegraphingUnblockable = false; RestoreModelRotation(); }
            // si deja de acercarse para atacar por otra cosa que el ataque, suelta el token
            if (committed && s != EnemyState.Chase)
            {
                committed = false;
                if (s != EnemyState.Attack) ReleaseToken();
            }
            State = s;
            stateTime = 0f;
            anim.SetSpeed(1f);
            if (useAgent && s != EnemyState.Chase && s != EnemyState.Strafe) Stop();
        }

        void TickTimed(float dt, System.Action onDone)
        {
            if (stateTime >= stateDuration) onDone();
        }

        protected void RestoreModelRotation()
        {
            if (model != null && model != transform) model.localRotation = modelBaseRot;
        }

        // ---------------------------------------------------------------- movimiento
        protected void MoveTo(Vector3 p, float speed)
        {
            if (useAgent)
            {
                agent.isStopped = false;
                agent.speed = speed;
                if ((agent.destination - p).sqrMagnitude > 0.25f) agent.SetDestination(p);
            }
            else
            {
                Vector3 d = (p - transform.position).Flat();
                if (d.magnitude > 0.1f) MoveBy(d.normalized * speed * Time.deltaTime);
            }
        }

        protected void Stop()
        {
            if (agent != null && agent.enabled && agent.isOnNavMesh) { agent.isStopped = true; agent.velocity = Vector3.zero; }
        }

        protected void MoveBy(Vector3 delta)
        {
            if (agent != null && agent.enabled && agent.isOnNavMesh) agent.Move(delta);
            else
            {
                Vector3 p = transform.position + delta;
                if (Physics.Raycast(p + Vector3.up * 2f, Vector3.down, out var hit, 6f, GroundMask, QueryTriggerInteraction.Ignore)) p.y = hit.point.y;
                transform.position = p;
            }
        }

        static int groundMask = -1;
        static int GroundMask { get { if (groundMask == -1) groundMask = LayerMask.GetMask("Default"); return groundMask; } }

        protected void Face(Vector3 worldPos, float speedMul, float dt)
        {
            Vector3 d = (worldPos - transform.position).Flat();
            if (d.sqrMagnitude < 0.001f) return;
            transform.rotation = CombatMath.Damp(transform.rotation, Quaternion.LookRotation(d), config.turnSpeed * speedMul, dt);
        }

        protected float DistToTarget => target != null ? CombatMath.FlatDistance(target.transform.position, transform.position) : 999f;

        // ---------------------------------------------------------------- estados neutrales
        protected virtual void TickIdle(float dt)
        {
            if (target == null || !target.IsAlive || Game.InCutscene) return;
            if (DistToTarget < config.detectRadius && Mathf.Abs(target.transform.position.y - transform.position.y) < 4f) Alert();
        }

        void TickAlert(float dt)
        {
            if (target != null) Face(target.transform.position, 1f, dt);
            if (stateTime >= stateDuration) SetState(EnemyState.Chase);
        }

        protected virtual void TickChase(float dt)
        {
            if (!TargetValid()) return;
            float d = DistToTarget;
            Face(target.transform.position, 1f, dt);
            if (d > config.loseRadius) { LoseAggro(); return; }
            // ya tiene token y patrón (lo tomó rondando): se acerca hasta tenerlo en rango y ataca
            if (committed)
            {
                if (pattern != null && Time.time < commitUntil && Game.Combat != null && Game.Combat.HasToken(this))
                {
                    if (d <= pattern.maxRange) { committed = false; StartAttack(false); return; }
                    MoveTo(target.transform.position, config.runSpeed);
                    return;
                }
                CancelCommit();
            }
            if (Time.time >= nextAttackTime && PickPattern(d, out var p))
            {
                if (d <= p.maxRange && Game.Combat != null && Game.Combat.RequestAttackToken(this))
                {
                    pattern = p;
                    StartAttack(false);
                    return;
                }
            }
            if (d > config.preferredDistance + 1.2f) MoveTo(target.transform.position, config.runSpeed);
            else { SetState(EnemyState.Strafe); strafeSwitch = Time.time + Random.Range(1.2f, 2.6f); }
        }

        protected virtual void TickStrafe(float dt)
        {
            if (!TargetValid()) return;
            float d = DistToTarget;
            Face(target.transform.position, 1.2f, dt);
            if (Time.time > strafeSwitch) { strafeDir = -strafeDir; strafeSwitch = Time.time + Random.Range(1.2f, 2.6f); }
            Vector3 toMe = (transform.position - target.transform.position).Flat().normalized;
            Vector3 tangent = Vector3.Cross(Vector3.up, toMe) * strafeDir;
            Vector3 dest = target.transform.position + toMe * config.preferredDistance + tangent * 1.6f;
            MoveTo(dest, config.walkSpeed);
            if (d > config.preferredDistance + 2.5f) { SetState(EnemyState.Chase); return; }
            if (Time.time >= nextAttackTime && PickPattern(d + 0.6f, out var p) && Game.Combat != null && Game.Combat.RequestAttackToken(this))
            {
                pattern = p;
                SetState(EnemyState.Chase); // se compromete: se acerca con este patrón y ataca al tenerlo en rango
                committed = true;
                commitUntil = Time.time + 2.5f;
            }
        }

        /// <summary>No llegó a tiempo (Kaito se alejó, camino bloqueado...): suelta el token para que ataque otro.</summary>
        void CancelCommit()
        {
            committed = false;
            pattern = null;
            ReleaseToken();
            nextAttackTime = Time.time + Random.Range(0.4f, 0.9f);
        }

        bool TargetValid()
        {
            if (target == null || !target.IsAlive)
            {
                Stop();
                if (State != EnemyState.Idle) { SetState(EnemyState.Idle); IsAggro = false; ReleaseToken(); anim.Play(config.animLocomotion, 0.2f); }
                return false;
            }
            return true;
        }

        void LoseAggro()
        {
            IsAggro = false;
            ReleaseToken();
            SetState(EnemyState.Idle);
            MoveTo(spawnPos, config.walkSpeed);
        }

        protected bool PickPattern(float dist, out AttackPattern chosen)
        {
            chosen = null;
            var ps = config.patterns;
            if (ps == null || ps.Length == 0) return false;
            float total = 0f;
            int phase = CurrentPhase;
            foreach (var p in ps)
                if (dist >= p.minRange && phase >= p.minPhase && Time.time - p.lastUsed >= p.cooldown) total += p.weight;
            if (total <= 0f) return false;
            float r = Random.value * total;
            foreach (var p in ps)
            {
                if (dist < p.minRange || phase < p.minPhase || Time.time - p.lastUsed < p.cooldown) continue;
                r -= p.weight;
                if (r <= 0f) { chosen = p; return true; }
            }
            chosen = ps[ps.Length - 1];
            return true;
        }

        public virtual int CurrentPhase => 0;

        // ---------------------------------------------------------------- ataque
        protected void StartAttack(bool counter)
        {
            if (pattern == null && !PickPattern(0f, out pattern)) { SetState(EnemyState.Chase); return; }
            if (counter) Game.Combat?.RequestAttackToken(this);
            pattern.lastUsed = Time.time;
            step = 0;
            SetState(EnemyState.Attack);
            BeginStep();
        }

        protected void BeginStep()
        {
            var a = pattern.steps[step];
            stepLen = anim.Length(a.state, 0.8f) / Mathf.Max(0.05f, a.speed);
            stepNorm = 0f;
            stepHit = false;
            telegraphed = false;
            strikeEta = float.PositiveInfinity;
            IsTelegraphingUnblockable = a.kind == AttackKind.Unblockable;
            stateTime = 0f;
            anim.Play(a.state, 0.08f);
            if (IsTelegraphingUnblockable) OnUnblockableTelegraph(a);
            OnStepStarted(a);
        }

        protected virtual void OnStepStarted(AttackDef a) { }
        protected virtual void OnUnblockableTelegraph(AttackDef a)
        {
            Game.FX?.DangerTelegraph(this);
            Game.UI?.ShowDanger(this);
            Game.Audio?.Play("danger", transform.position, 0.9f);
        }

        void TickAttack(float dt)
        {
            if (!TargetValid()) return;
            var a = pattern.steps[step];
            // telegrafía extra: el golpe espera un instante más antes de salir
            float timing = a.Timing(stepNorm) * a.speed;
            float holdEnd = a.telegraph + (a.activeStart - 0.12f) * stepLen;
            bool holding = a.telegraph > 0f && stepNorm >= a.activeStart - 0.12f && stateTime < holdEnd;
            if (holding) timing *= 0.15f;
            anim.SetSpeed(timing);
            if (!anim.Frozen) stepNorm += dt * timing / Mathf.Max(0.05f, stepLen * a.speed);
            strikeEta = ComputeStrikeEta(a, holdEnd);
            float lungeLeft = a.lunge > 0f && stepNorm < a.lungeEnd
                ? a.lunge * Mathf.Clamp01((a.lungeEnd - Mathf.Max(stepNorm, a.lungeStart)) / Mathf.Max(0.01f, a.lungeEnd - a.lungeStart)) : 0f;
            StrikeReach = a.range * Mathf.Max(1f, config.scale * 0.85f) + lungeLeft;

            if (a.tracking && stepNorm < a.activeStart) Face(target.transform.position, 1.3f, dt);

            // destello de aviso justo antes del golpe (lectura del parry)
            if (!telegraphed && stepNorm >= a.activeStart - 0.18f)
            {
                telegraphed = true;
                Game.FX?.BladeGlint(katanaTip != null ? katanaTip.position : AimPoint + transform.forward * 0.6f, a.kind == AttackKind.Unblockable);
                Game.Audio?.Play(a.sfx, transform.position, 0.65f, 0.1f);
                trail?.Begin();
            }

            if (stepNorm >= a.lungeStart && stepNorm <= a.lungeEnd && a.lunge > 0f)
            {
                float room = DistToTarget - Radius - target.Radius - 0.3f;
                float spd = a.lunge / Mathf.Max(0.05f, (a.lungeEnd - a.lungeStart) * stepLen);
                if (room > 0f) MoveBy(transform.forward * Mathf.Min(spd * dt, room));
            }

            if (!string.IsNullOrEmpty(a.special)) TickSpecial(a, dt);
            else if (!stepHit && stepNorm >= a.activeStart && stepNorm <= a.activeEnd) TryHitPlayer(a);

            if (stepNorm > a.activeEnd + 0.05f) trail?.Stop();
            if (stepNorm >= 1f) NextStep();
        }

        /// <summary>Segundos hasta que el golpe del paso actual pega (infinito si ya pegó o no hace daño). Los jefes lo
        /// cambian para sus especiales (una embestida pega al alcanzar a Kaito, no en activeStart).</summary>
        protected virtual float ComputeStrikeEta(AttackDef a, float holdEnd) =>
            stepHit || stepNorm >= a.activeStart || a.damage <= 0f ? float.PositiveInfinity : EstimateStrikeEta(a, holdEnd);

        /// <summary>Segundos hasta activeStart al ritmo actual, contando la pausa del telegraph (presente o por venir).
        /// Dentro de la pausa el clip sigue avanzando al 15%, así que el golpe puede salir antes de que termine.</summary>
        protected float EstimateStrikeEta(AttackDef a, float holdEnd)
        {
            float rate = a.Timing(stepNorm) / Mathf.Max(0.05f, stepLen);   // tiempo normalizado por segundo
            float left = a.activeStart - stepNorm;
            if (a.telegraph <= 0f || stateTime >= holdEnd) return left / rate;
            float toZone = Mathf.Max(0f, a.activeStart - 0.12f - stepNorm) / rate;
            float holdLeft = holdEnd - stateTime - toZone;                   // pausa que queda al llegar a la zona
            if (holdLeft <= 0f) return left / rate;
            float tail = Mathf.Min(0.12f, left), slow = 0.15f * rate;
            if (tail <= slow * holdLeft) return toZone + tail / slow;
            return toZone + holdLeft + (tail - slow * holdLeft) / rate;
        }

        /// <summary>Movimientos especiales (jefes). Por defecto, golpe normal.</summary>
        protected virtual void TickSpecial(AttackDef a, float dt)
        {
            if (!stepHit && stepNorm >= a.activeStart && stepNorm <= a.activeEnd) TryHitPlayer(a);
        }

        protected void TryHitPlayer(AttackDef a, float rangeMul = 1f)
        {
            if (target == null) return;
            if (!CombatMath.InArc(transform, target.transform.position, a.range * Mathf.Max(1f, config.scale * 0.85f) * rangeMul, a.arc, target.Radius)) return;
            if (Mathf.Abs(target.transform.position.y - transform.position.y) > 2.5f) return;
            stepHit = true;
            HitPlayer(a, transform.position);
        }

        protected HitResult HitPlayer(AttackDef a, Vector3 from)
        {
            var info = new DamageInfo
            {
                damage = a.damage,
                imbalance = a.imbalance,
                kind = a.kind,
                direction = (target.transform.position - from).Flat().normalized,
                point = target.AimPoint,
                knockback = a.knockback,
                sourceFaction = Faction.Enemy,
                source = this,
                attackName = a.name,
            };
            var r = target.ReceiveHit(info);
            if (r == HitResult.Hit || r == HitResult.Killed) anim.Freeze(a.hitStop);
            return r;
        }

        void NextStep()
        {
            step++;
            trail?.Stop();
            if (pattern != null && step < pattern.steps.Length && TargetValid()) { BeginStep(); return; }
            ComboEnd();
        }

        /// <summary>Después de un parry el enemigo retrocede y sigue con el resto del combo.</summary>
        void ContinueCombo()
        {
            if (Imbalance >= config.maxImbalance) { BecomeExhausted(); return; }
            step++;
            if (pattern != null && step < pattern.steps.Length && TargetValid()) { SetState(EnemyState.Attack); BeginStep(); }
            else ComboEnd();
        }

        protected virtual void ComboEnd()
        {
            ReleaseToken();
            if (pattern != null && pattern.exhaustAfter) Imbalance = config.maxImbalance;
            pattern = null;
            nextAttackTime = Time.time + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
            if (Imbalance > 0.01f) BecomeExhausted();
            else EnterGuard();
        }

        protected void ReleaseToken() => Game.Combat?.ReleaseAttackToken(this);

        // ---------------------------------------------------------------- guardia / agotado
        protected void EnterGuard()
        {
            SetState(EnemyState.Guard);
            stateDuration = config.guardTime * Random.Range(0.7f, 1.2f);
            anim.Play(config.animGuard, 0.12f);
        }

        void TickGuard(float dt)
        {
            if (!TargetValid()) return;
            Face(target.transform.position, 1f, dt);
            if (stateTime >= stateDuration) SetState(EnemyState.Chase);
        }

        protected virtual void BecomeExhausted()
        {
            ReleaseToken();
            SetState(EnemyState.Exhausted);
            stateDuration = config.exhaustedTime;
            anim.Play(config.animExhausted, 0.12f);
            Game.FX?.Exhausted(this);
            Game.Audio?.Play("exhausted", transform.position, 0.8f);
        }

        void TickExhausted(float dt)
        {
            if (stateTime >= stateDuration)
            {
                Imbalance = 0f;
                EnterGuard();
            }
        }

        // ---------------------------------------------------------------- recibir golpes
        public virtual HitResult ReceiveHit(in DamageInfo info)
        {
            if (!IsAlive || info.sourceFaction == Faction.Enemy || State == EnemyState.Scripted) return HitResult.Ignored;
            if (!IsAggro) Alert();
            LastHitTime = Time.time;

            // en guardia: desvía y contraataca (solo golpes normales)
            bool guardable = info.kind == AttackKind.Light || info.kind == AttackKind.Heavy;
            if (State == EnemyState.Guard && guardable)
            {
                Counter();
                return HitResult.Guarded;
            }
            // en neutral aguanta pocos golpes seguidos antes de cubrirse
            bool neutral = State == EnemyState.Chase || State == EnemyState.Strafe || State == EnemyState.Idle || State == EnemyState.Alert || State == EnemyState.Stagger;
            if (neutral && guardable)
            {
                if (Time.time - lastNeutralHit > 2.2f) neutralHits = 0;
                lastNeutralHit = Time.time;
                neutralHits++;
                if (neutralHits > config.poiseHits)
                {
                    neutralHits = 0;
                    Counter();
                    return HitResult.Guarded;
                }
            }

            float dmg = info.damage;
            if (State == EnemyState.Exhausted)
            {
                dmg *= config.exhaustedDamageMul;
                Imbalance = Mathf.Max(0f, Imbalance - Mathf.Max(1f, info.imbalance));
                stateDuration = Mathf.Max(stateDuration, stateTime + 0.6f);
            }
            Health -= dmg;
            flash?.Flash();
            if (Health <= 0f)
            {
                Die(info);
                return HitResult.Killed;
            }

            float kb = info.knockback * (1f - config.knockbackResist);
            if (kb > 0f) knock += info.direction.Flat().normalized * kb;

            if (State == EnemyState.Exhausted)
            {
                if (Imbalance <= 0.01f) { Imbalance = 0f; EnterGuard(); }
                else anim.Play(config.animHit, 0.03f);
            }
            else if (State == EnemyState.Attack && config.hyperArmor && info.kind != AttackKind.Ability)
            {
                // aguanta el golpe sin interrumpirse
            }
            else if (State != EnemyState.Counter)
            {
                ReleaseToken();
                SetState(EnemyState.Stagger);
                stateDuration = config.staggerTime * (info.kind == AttackKind.Heavy || info.kind == AttackKind.Ability ? 1.6f : 1f);
                anim.Play(config.animHit, 0.03f);
            }
            OnDamaged(info);
            return HitResult.Hit;
        }

        protected virtual void OnDamaged(in DamageInfo info) { }

        void Counter()
        {
            Stop();
            ReleaseToken();
            if (pattern == null) PickPattern(1f, out pattern);
            SetState(EnemyState.Counter);
            stateDuration = Mathf.Clamp(anim.Length(config.animCounter, 0.35f), 0.2f, 0.6f);
            anim.Play(config.animCounter, 0.02f);
            if (target != null) transform.rotation = Quaternion.LookRotation((target.transform.position - transform.position).Flat().normalized + transform.forward * 0.001f);
            Game.UI?.ShowGuardMark(this);
            nextAttackTime = Time.time;
        }

        /// <summary>Kaito le hizo parry a un golpe de este enemigo.</summary>
        public virtual void OnParried(bool perfect)
        {
            if (!IsAlive) return;
            Imbalance = Mathf.Min(config.maxImbalance, Imbalance + (perfect ? 1.5f : 1f));
            trail?.Stop();
            Game.UI?.PulseImbalance(this);
            if (State == EnemyState.Attack)
            {
                SetState(EnemyState.Recoil);
                stateDuration = config.parriedRecoil * (perfect ? 1.5f : 1f);
                anim.Play(config.animParried, 0.03f);
                knock += -transform.forward * (perfect ? 0.8f : 0.4f);
            }
            if (Imbalance >= config.maxImbalance) { BecomeExhausted(); Game.FX?.PostureBreak(AimPoint); Game.Audio?.Play("posture_break", transform.position, 1f); }
        }

        // ---------------------------------------------------------------- muerte / ejecución
        public void BeginExecution(PlayerController by)
        {
            ReleaseToken();
            Stop();
            SetState(EnemyState.Executed);
            anim.Play(config.animExhausted, 0.1f);
            transform.rotation = Quaternion.LookRotation((by.transform.position - transform.position).Flat().normalized);
        }

        public virtual void Execute(PlayerController by)
        {
            Health = 0f;
            Die(new DamageInfo { damage = 999, kind = AttackKind.Finisher, direction = (transform.position - by.transform.position).Flat().normalized, sourceFaction = Faction.Player, source = by }, true);
        }

        protected virtual void Die(in DamageInfo info, bool finisher = false)
        {
            if (State == EnemyState.Dead) return;
            ReleaseToken();
            Stop();
            trail?.Stop();
            RestoreModelRotation(); // si murió en pleno giro, cae desde la pose normal
            committed = false;
            State = EnemyState.Dead;
            stateTime = 0f;
            IsAggro = false;
            Game.Combat?.Unregister(this);
            foreach (var c in GetComponentsInChildren<Collider>()) c.enabled = false;
            anim.Play(config.animDeath, 0.06f);
            Game.FX?.EnemyDeath(AimPoint, info.direction, finisher);
            Game.Audio?.Play("kill", transform.position, 0.9f);
            GameEvents.RaiseEnemyKilled(this);
            encounter?.OnMemberDied(this);
            StartCoroutine(DeathRoutine(info.direction));
        }

        IEnumerator DeathRoutine(Vector3 dir)
        {
            // cae hacia atrás y se desvanece en humo (sin ragdoll: barato y legible)
            float t = 0f;
            Quaternion from = model.localRotation;
            Quaternion to = from * Quaternion.Euler(-75f, 0f, 0f);
            Vector3 fromPos = transform.position;
            while (t < 1f)
            {
                t += Time.deltaTime * 1.8f;
                model.localRotation = Quaternion.Slerp(from, to, t * t);
                transform.position = fromPos + dir.Flat().normalized * 0.8f * Mathf.Sin(t * Mathf.PI * 0.5f);
                yield return null;
            }
            yield return new WaitForSeconds(0.9f);
            Game.FX?.SmokePuff(transform.position + Vector3.up * 0.4f, 1.2f * config.scale);
            float s = 1f;
            Vector3 baseScale = model.localScale;
            while (s > 0.02f)
            {
                s -= Time.deltaTime * 3f;
                model.localScale = baseScale * Mathf.Max(0.02f, s);
                yield return null;
            }
            model.localRotation = from;
            model.localScale = baseScale;
            OnDeathFinished();
        }

        protected virtual void OnDeathFinished()
        {
            gameObject.SetActive(false);
        }

        // ---------------------------------------------------------------- guion
        public void EnterScripted()
        {
            if (!IsAlive) return;   // un muerto en Scripted cuenta como vivo y el encuentro no termina nunca
            ReleaseToken(); Stop();
            SetState(EnemyState.Scripted);
            anim.Play(config.animLocomotion, 0.15f);
        }

        public void ExitScripted(bool aggro)
        {
            if (State != EnemyState.Scripted) return;
            SetState(EnemyState.Idle);
            // si ya estaba en aggro antes de la cinemática, Alert() no hacía nada y quedaba quieto en Idle
            if (aggro) { IsAggro = false; Alert(); }
        }

        public void ScriptedPlay(string state, float fade = 0.1f) => anim.Play(state, fade);
        public void ScriptedMoveTo(Vector3 p, float speed) { useAgent = agent != null && agent.isOnNavMesh; MoveTo(p, speed); }
        public void ScriptedFace(Vector3 p) { Vector3 d = (p - transform.position).Flat(); if (d.sqrMagnitude > 0.01f) transform.rotation = Quaternion.LookRotation(d); }
        public void ScriptedStop() => Stop();
    }
}
