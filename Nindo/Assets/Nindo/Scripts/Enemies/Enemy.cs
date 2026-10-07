using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

namespace Nindo
{
    public enum EnemyState { Idle, Alert, Chase, Strafe, Attack, Recoil, Guard, Counter, Exhausted, Stagger, Executed, Dead, Scripted }

    /// <summary>
    /// IA de enemigo genérica y data-driven. Mantiene el ritmo de combate original de Nindo:
    ///  * el enemigo ataca en combos; cada PARRY de Kaito le suma DESEQUILIBRIO (postura);
    ///  * si termina el combo con al menos un parry encima queda AGOTADO: ventana de daño (4 golpes o su tiempo);
    ///  * con la postura llena se QUIEBRA: agotado y, si es común, se lo puede EJECUTAR (o con poca vida);
    ///  * en GUARDIA el primer golpe rebota (suma postura) y el segundo te lo DESVÍA con un contraataque.
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
        public virtual bool Targetable => IsAlive && gameObject.activeInHierarchy && State != EnemyState.Scripted;
        public Faction Faction => Faction.Enemy;
        public Transform Root => transform;
        public float Radius => config.radius * Mathf.Max(0.5f, config.scale);
        public Vector3 AimPoint => transform.position + Vector3.up * config.height * 0.55f * config.scale;
        /// <summary>Punto del cuerpo más cercano a 'from', donde le entran los golpes de Kaito (se le resta Radius como a
        /// la posición). Un cuerpo largo lo cambia por el de su silueta: con el centro solo, la cabeza y la cola del koi
        /// de 7.5 m quedaban fuera del alcance de la katana.</summary>
        public virtual Vector3 HurtCenter(Vector3 from) => transform.position;
        public CharacterAnimator Anim => anim;
        public bool IsTelegraphingUnblockable { get; private set; }
        public bool IsExhausted => State == EnemyState.Exhausted;
        /// <summary>Agotado con la postura llena (parries o golpes a la guardia): la ejecución está disponible.</summary>
        public bool PostureBroken => State == EnemyState.Exhausted && Imbalance >= config.maxImbalance - 0.01f;
        /// <summary>El golpe actual está por salir (exacto: sale de la línea de tiempo del paso).</summary>
        /// <remarks>Se mide en segundos de juego: si el jugador aprieta parry en ese momento el golpe cae
        /// dentro de su ventana de parry (PlayerConfig.parryWindow).</remarks>
        public bool AboutToStrike => State == EnemyState.Attack && StrikeEta <= StrikeWarning;
        /// <summary>Segundos de juego que faltan para el próximo golpe de este enemigo: el del paso actual o el de
        /// un proyectil suyo en camino hacia Kaito (infinito si no hay ninguno).</summary>
        public float StrikeEta => Mathf.Min(State == EnemyState.Attack ? strikeEta : float.PositiveInfinity, ProjectileEta);
        float strikeEta = float.PositiveInfinity;
        /// <summary>Segundos hasta que un proyectil de este enemigo alcance a Kaito (las olas de Mizuchi).</summary>
        public virtual float ProjectileEta => float.PositiveInfinity;
        /// <summary>De dónde viene ese proyectil (para orientar el aviso a los pies de Kaito).</summary>
        public virtual Vector3 ProjectileFrom => transform.position;
        /// <summary>Alcance del golpe en curso: arco del ataque más lo que le queda de embestida.</summary>
        public float StrikeReach { get; private set; }
        /// <summary>Paso del combo que está ejecutando (null si no ataca). Lo usa el aviso en el suelo.</summary>
        public AttackDef CurrentAttack => State == EnemyState.Attack && pattern != null && pattern.steps != null && step >= 0 && step < pattern.steps.Length ? pattern.steps[step] : null;
        public const float StrikeWarning = 0.18f;
        /// <summary>Desde este tiempo antes del golpe un corte liviano de Kaito ya no lo interrumpe (s).</summary>
        public const float CommitArmorLead = 0.30f;
        /// <summary>En los últimos segundos antes del golpe deja de girar hacia Kaito (s).</summary>
        public const float TrackingStopLead = 0.20f;
        /// <summary>Golpes que aguanta agotado antes de volver a la guardia.</summary>
        public const int ExhaustedMaxHits = 4;
        /// <summary>Golpes que aguanta agotado este enemigo (un jefe puede dar una ventana más larga).</summary>
        protected virtual int ExhaustedHitCap => ExhaustedMaxHits;
        /// <summary>Desequilibrio mínimo al terminar el combo para quedar agotado: un parry entero (la guardia
        /// imperfecta y los golpes contra la guardia suman de a poco, solos no alcanzan).</summary>
        public const float ExhaustThreshold = 1f;
        /// <summary>Postura que suma cada golpe que rebota en la guardia.</summary>
        public const float GuardHitImbalance = 0.25f;

        // ---- aviso de ataque (ensō): honesto en el tiempo, sale de la línea de tiempo del paso
        /// <summary>El anillo de aviso se está dibujando (desde TellStart hasta el golpe).</summary>
        public bool InTell => tellActive && State == EnemyState.Attack && stepClock >= tellStart;
        /// <summary>Cambia con cada aviso nuevo (para distinguir dos golpes seguidos del mismo enemigo).</summary>
        public int TellId { get; private set; }
        /// <summary>Tipo del golpe del paso actual (desviable o imparable).</summary>
        public AttackKind StepKind { get; private set; }
        /// <summary>
        /// 0..1: cuánto del anillo está dibujado. Llega a 1 justo 'TellBias' antes del golpe (el momento de
        /// apretar parry o dash). Si el golpe se demora (Kaito se aleja de una embestida) retrocede: nunca miente.
        /// </summary>
        public float TellProgress01
        {
            get
            {
                if (!InTell) return 0f;
                if (float.IsInfinity(strikeEta)) return 1f;
                float close = stepClock + strikeEta - pattern.steps[step].TellBias;
                return close <= tellStart ? 1f : Mathf.Clamp01((stepClock - tellStart) / (close - tellStart));
            }
        }
        public float LastHitTime { get; protected set; } = -99f;
        public Transform katanaTip, katanaBase;
        /// <summary>Segundos del paso en curso (el reloj de su línea de tiempo) y la línea de tiempo misma: las poses
        /// procedurales (SumoPoser, VariantMotion) se atan a esto para que el cuerpo diga lo mismo que el aviso.</summary>
        public float StepClock => stepClock;
        public StepTimeline Timeline => tl;
        /// <summary>Está en la práctica del parry del prólogo (sus avisos se dibujan aunque estén apagados en Opciones).</summary>
        public bool InParryPractice => practiceBackup != null;
        /// <summary>El filo se enciende este tiempo antes del golpe (s): dorado si se desvía, rojo si es imparable.</summary>
        public const float GlintLead = 0.33f;

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
        protected float stepNorm;
        protected bool stepHit;
        // línea de tiempo del paso: el golpe sale en tl.T segundos de 'stepClock', que avanza con el tiempo de
        // juego salvo en el hit-stop local (así el aviso, el sonido y el golpe nunca se desfasan)
        protected StepTimeline tl;
        protected float stepClock;
        protected bool specialFired;
        float clipLen;
        bool counterAttack;
        bool tellActive, tellShown, ticked, swung, glinted, released;
        // filo encendido del aviso (CharacterGlint, el slot 'Glint' del arma)
        CharacterGlint glint;
        bool glintOn;
        // saltos sin daño (hop_back / hop_side): hasta dónde del clip ya se recorrió y para qué lado
        float hopNorm, hopSide = 1f;
        float tellStart, lungeStartT, lungeEndT;
        // carril de la embestida: queda fijo al soltar (desde ahí no corrige la puntería)
        Vector3 laneOrigin, laneDir;
        float laneLength;
        const float ChargeMaxTravel = 9f;
        protected float strafeDir = 1f;
        protected float strafeSwitch;
        protected int neutralHits;
        protected float lastNeutralHit;
        int guardHits, exhaustedHits;
        // armadura de compromiso: a menos de CommitArmorLead s del golpe un corte liviano ya no lo interrumpe
        bool armored;
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
            glint = GetComponentInChildren<CharacterGlint>();
            if (glint != null && !glint.HasGlint) glint = null;   // sin arma con filo (el sumo): sus poses avisan con las manos
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
                trail = BladeTrail.Create(transform, katanaBase, katanaTip, Game.Content != null ? Game.Content.trailMaterial : null, TellStyle.TrailParry);
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

        // práctica del parry del prólogo: la config original queda guardada mientras dura
        EnemyConfig practiceBackup;
        /// <summary>Vida mínima en la práctica del parry: por encima del umbral de ejecución (0.25).</summary>
        const float PracticeMinHealth = 0.35f;
        /// <summary>Tope de la postura: en la práctica se queda a medio pip de quebrarse (las marcas se siguen viendo).</summary>
        float PostureCap => practiceBackup != null ? config.maxImbalance - 0.5f : config.maxImbalance;

        /// <summary>
        /// Práctica del parry del prólogo (StoryDirector): ataca de a un golpe liviano con el aviso largo, la postura
        /// no se quiebra y no baja del 35 % de vida (cada parry igual lo deja abierto un rato corto). Con la config
        /// normal los dos parries guiados ya le quebraban la postura y moría en la ventana de daño antes de que se
        /// practicara a velocidad real. Con 'false' vuelve a la config original.
        /// </summary>
        public void SetParryPractice(bool on)
        {
            if (on == (practiceBackup != null)) return;
            if (!on) { config = practiceBackup; practiceBackup = null; return; }
            practiceBackup = config;
            var c = config.Clone();
            c.exhaustedTime = 1.2f;
            var singles = new List<AttackPattern>();
            var seen = new HashSet<AttackDef>();
            if (c.patterns != null)
                foreach (var p in c.patterns)
                    if (p != null && p.steps != null)
                        foreach (var s in p.steps)
                            if (s != null && s.kind == AttackKind.Light && seen.Add(s))
                            {
                                s.windup = Mathf.Max(s.windup, 0.75f);
                                singles.Add(new AttackPattern { name = s.name, steps = new[] { s }, maxRange = p.maxRange });
                            }
            if (singles.Count > 0) c.patterns = singles.ToArray();
            config = c;
        }

        public bool CanBeFinished(float healthThreshold)
        {
            if (!IsAlive || State == EnemyState.Scripted) return false;
            bool lowHealth = Health01 <= Mathf.Max(config.finisherHealth, healthThreshold) && Health01 > 0f;
            if (this is Boss boss) return boss.FinisherAllowed && (State == EnemyState.Exhausted || lowHealth);
            // comunes: solo con la postura quebrada o casi muertos. Un parry suelto abre una ventana de daño, no
            // la ejecución (si no, el mejor juego era parry → F → mirar la cinemática)
            return PostureBroken || lowHealth;
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

            // el empujón del golpe espera a que termine el hit-stop local (si no, se desliza congelado)
            if (knock.sqrMagnitude > 0.0001f && !anim.Frozen)
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
            // y el aviso que quedaba a medias se borra (no puede quedar un anillo de un golpe que ya no va a salir)
            if (State == EnemyState.Attack && s != EnemyState.Attack)
            {
                trail?.Stop(); IsTelegraphingUnblockable = false; armored = false; RestoreModelRotation();
                EndTell(TellOutcome.Cancelled);
            }
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
            Vector3 dest;
            if (Game.Combat != null && Game.Combat.TryGetStrafeSlot(this, out float slot))
            {
                // va rodeando hacia su lugar (repartidos alrededor de Kaito: no se amontonan) y ahí se balancea
                float bearing = Mathf.Atan2(toMe.x, toMe.z) * Mathf.Rad2Deg;
                float turn = Mathf.Clamp(Mathf.DeltaAngle(bearing, slot + strafeDir * 10f), -40f, 40f);
                dest = target.transform.position + Quaternion.Euler(0f, bearing + turn, 0f) * Vector3.forward * config.preferredDistance;
            }
            else dest = target.transform.position + toMe * config.preferredDistance + Vector3.Cross(Vector3.up, toMe) * strafeDir * 1.6f;
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
                if (dist >= p.minRange && phase >= p.minPhase && Time.time - p.lastUsed >= p.cooldown && Usable(p, phase)) total += p.weight;
            if (total <= 0f) return false;
            float r = Random.value * total;
            foreach (var p in ps)
            {
                if (dist < p.minRange || phase < p.minPhase || Time.time - p.lastUsed < p.cooldown || !Usable(p, phase)) continue;
                r -= p.weight;
                if (r <= 0f) { chosen = p; return true; }
            }
            chosen = ps[ps.Length - 1];
            return true;
        }

        public virtual int CurrentPhase => 0;

        /// <summary>Fase máxima y ángulo hacia Kaito del patrón (p. ej. el coletazo de Mizuchi, solo con Kaito detrás).</summary>
        bool Usable(AttackPattern p, int phase)
        {
            if (phase > p.maxPhase) return false;
            if (p.minAngle <= 0f && p.maxAngle >= 180f || target == null) return true;
            float ang = Vector3.Angle(transform.forward.Flat(), (target.transform.position - transform.position).Flat());
            return ang >= p.minAngle && ang <= p.maxAngle;
        }

        // ---------------------------------------------------------------- ataque
        protected void StartAttack(bool counter)
        {
            // el contraataque también respeta los turnos: si otro está por pegar, se queda cubierto
            if (counter && Game.Combat != null && !Game.Combat.RequestAttackToken(this)) { pattern = null; EnterGuard(); return; }
            if (pattern == null && !PickPattern(0f, out pattern)) { ReleaseToken(); SetState(EnemyState.Chase); return; }
            pattern.lastUsed = Time.time;
            step = 0;
            counterAttack = counter;
            SetState(EnemyState.Attack);
            BeginStep();
        }

        protected void BeginStep()
        {
            var a = pattern.steps[step];
            EndTell(TellOutcome.Struck);   // (el paso anterior ya pegó; por las dudas no queda un anillo colgado)
            clipLen = anim.Length(a.state, 0.8f);
            stepNorm = 0f;
            stepClock = 0f;
            stepHit = specialFired = released = armored = false;
            tellShown = ticked = swung = glinted = false;
            hopNorm = a.activeStart;
            hopSide = Random.value < 0.5f ? -1f : 1f;
            strikeEta = float.PositiveInfinity;
            StepKind = a.kind;
            IsTelegraphingUnblockable = a.kind == AttackKind.Unblockable;
            stateTime = 0f;
            // windup mínimo solo para lo que pega: teletransporte, invocaciones... van a su ritmo natural.
            // "Encadenado" = viene después de otro golpe (el jugador ya está en ritmo); tras un teletransporte no
            float windup = a.damage > 0f
                ? StepTimeline.MinWindup(a, step > 0 && pattern.steps[step - 1].damage > 0f, counterAttack && step == 0, CurrentPhase, config.windupScale)
                : a.telegraph;
            tl = StepTimeline.Build(a, clipLen, windup, 0f);
            tellActive = StepHasTell(a);
            if (tellActive)
            {
                // que no peguen dos enemigos casi juntos: si hace falta, este demora su golpe
                float travel = TellTravel(a);
                float delay = Game.Combat != null ? Game.Combat.ReserveStrike(this, Time.time + tl.T + travel) : 0f;
                if (delay > CombatDirector.MaxStrikeDelay && step == 0)
                {
                    // demasiada espera para abrir un combo: vuelve a rondar y reintenta enseguida
                    tellActive = false;
                    Game.Combat.ReleaseStrike(this);
                    pattern = null;
                    ReleaseToken();
                    SetState(EnemyState.Chase);
                    nextAttackTime = Time.time + 0.3f;
                    return;
                }
                // la espera se arma de nuevo como windup (no como pausa extra en el apex): Build deja la pose quieta
                // en MaxHold y reparte el resto en una anticipación más lenta. Sumada al apex llegaba a ~1 s congelado
                float dly = Mathf.Min(delay, CombatDirector.MaxStrikeDelay);
                if (dly > 0f) tl = StepTimeline.Build(a, clipLen, tl.T + dly, 0f);
                tellStart = Mathf.Max(0f, tl.T + travel - TellStyle.MaxLead(a.kind));
                TellId++;
                Game.FX?.BeginTell(this);
            }
            // embestida corta del golpe: termina un poco después del impacto; si es larga arranca antes de la
            // suelta para no superar ~12 m/s (si no, el ninja se teletransporta en la estocada)
            lungeEndT = tl.T + 0.05f * tl.stepLen;
            lungeStartT = Mathf.Max(0f, lungeEndT - Mathf.Max(lungeEndT - tl.ReleaseTime, a.lunge / 12f));
            // ETA real desde este mismo frame: con el infinito del reset, un aviso que arranca ya (tellStart 0) se
            // dibujaba un frame cerrado del todo, con el destello de "¡ahora!"
            strikeEta = ComputeStrikeEta(a);
            anim.Play(a.state, 0.08f);
            anim.SetSpeed(0f);   // este frame el clip no avanza: el reloj del paso arranca en el próximo
            OnStepStarted(a);
        }

        protected virtual void OnStepStarted(AttackDef a) { }

        /// <summary>Lo que tarda el golpe en llegar a Kaito después de soltarse (embestidas, ondas): el aviso arranca
        /// antes por eso y la agenda de golpes lo reserva para cuando de verdad llega.</summary>
        protected virtual float TellTravel(AttackDef a) => a.special == "charge" ? ChargeRoom() / ChargeSpeed(a) : 0f;

        /// <summary>
        /// Un especial largo (zambullida, salto, pilares, peloteo) lleva su propio reloj: mientras es true el paso no avanza
        /// el clip ni termina, y solo corren la ETA (ComputeStrikeEta), los avisos y TickSpecial.
        /// </summary>
        protected virtual bool StepHeld => false;

        /// <summary>¿Este paso dibuja el aviso alrededor del atacante? (los que no hacen daño no; los proyectiles
        /// avisan a los pies de Kaito, ver ProjectileEta)</summary>
        protected virtual bool StepHasTell(AttackDef a) => a.damage > 0f;

        /// <summary>Arranca el aviso de un imparable: destello rojo, marca sobre la cabeza y el taiko.</summary>
        protected virtual void OnUnblockableTelegraph(AttackDef a)
        {
            Game.FX?.DangerTelegraph(this);
            Game.UI?.ShowDanger(this);
            Game.Audio?.Play("tell_danger", transform.position, 1f, 0.03f);
        }

        void TickAttack(float dt)
        {
            if (!TargetValid()) return;
            var a = pattern.steps[step];
            if (StepHeld)
            {
                if (!anim.Frozen) stepClock += dt;
                strikeEta = ComputeStrikeEta(a);
                TickTell(a);
                TickSpecial(a, dt);
                return;
            }
            float prevNorm = stepNorm;
            if (!anim.Frozen) stepClock += dt;
            stepNorm = tl.NormAt(stepClock);
            // el Animator avanza este frame exactamente lo que avanzó el reloj del paso; si se despegó (transición
            // larga, clip cambiado) se lo empuja de a poco hacia donde tiene que estar
            float speed = (stepNorm - prevNorm) / dt * clipLen;
            if (anim.TryNormalizedTime(a.state, out float shown) && Mathf.Abs(prevNorm - shown) > 0.04f)
                speed += 6f * (prevNorm - shown) * clipLen;
            anim.SetSpeed(Mathf.Clamp(speed, 0f, 8f));

            strikeEta = ComputeStrikeEta(a);
            if (tellActive && !float.IsInfinity(strikeEta)) Game.Combat?.UpdateStrike(this, Time.time + strikeEta);
            // comprometido con el golpe: si a esta altura Kaito le mete un corte liviano, cambian golpes (antes pegar
            // primero siempre ganaba y el parry era opcional)
            armored = strikeEta <= CommitArmorLead;

            // puntería hasta la suelta y nunca en los últimos 0.2 s: desde ahí el golpe va recto y correrse sirve
            if (a.tracking && stepClock < tl.ReleaseTime && strikeEta > TrackingStopLead) Face(target.transform.position, 1.3f, dt);
            if (!released && stepClock >= tl.ReleaseTime) Release(a);
            TickTell(a);

            float lungeLeft = 0f;
            if (a.lunge > 0f && stepClock < lungeEndT)
            {
                float span = Mathf.Max(0.01f, lungeEndT - lungeStartT);
                lungeLeft = a.lunge * Mathf.Clamp01((lungeEndT - Mathf.Max(stepClock, lungeStartT)) / span);
                if (stepClock >= lungeStartT && !anim.Frozen)
                {
                    float room = DistToTarget - Radius - target.Radius - 0.3f;
                    if (room > 0f) MoveBy(transform.forward * Mathf.Min(a.lunge / span * dt, room));
                }
            }
            StrikeReach = a.range * Mathf.Max(1f, config.scale * 0.85f) + lungeLeft;

            TickSpecial(a, dt);
            if (State != EnemyState.Attack) return;   // lo desviaron (Recoil) o cambió de fase
            // el golpe ya salió (pegó o no): el aviso termina. Una embestida que no lo tocó (Kaito salió del carril
            // o ya pasó de largo) se deshace como cortada: se corrió a tiempo
            if (tellActive && float.IsInfinity(ComputeStrikeEta(a)))
            {
                bool dodged = a.special == "charge" && !stepHit;
                // sin aviso no hay golpe: la carrera sigue de largo pero ya no pega si Kaito vuelve a meterse en el carril
                if (dodged) stepHit = true;
                EndTell(dodged ? TellOutcome.Cancelled : TellOutcome.Struck);
            }

            if (stepNorm > a.activeEnd + 0.05f) trail?.Stop();
            if (stepNorm >= 1f) NextStep();
        }

        /// <summary>Empieza la suelta del golpe: estela del arma y, si es una embestida, el carril queda fijo.</summary>
        void Release(AttackDef a)
        {
            released = true;
            if (trail != null && a.damage > 0f)
            {
                trail.SetColor(a.kind == AttackKind.Unblockable ? TellStyle.TrailDanger : TellStyle.TrailParry);
                trail.SetLifetime(0.22f);
                trail.Begin();
            }
            if (a.special == "charge")
            {
                // pasa de largo 1.5 m: si Kaito no se corre del carril, lo alcanza
                float travel = Mathf.Clamp(ChargeRoom() + 1.5f, 2f, ChargeMaxTravel);
                laneOrigin = transform.position;
                laneDir = transform.forward.Flat().normalized;
                laneLength = travel + Radius;
                // la carrera dura lo que tarda en recorrer el carril (el clip se estira para acompañarla)
                tl.sustain = travel / ChargeSpeed(a);
            }
        }

        /// <summary>Sonidos y destellos atados al reloj del golpe (cada uno una sola vez por paso).</summary>
        void TickTell(AttackDef a)
        {
            if (!tellActive) return;
            if (!tellShown && stepClock >= tellStart)
            {
                tellShown = true;
                if (StepKind == AttackKind.Unblockable) OnUnblockableTelegraph(a);
            }
            float eta = strikeEta;
            // los sonidos se adelantan la latencia de salida del audio: cuentan desde que se OYEN
            if (!ticked && AudioManager.CueDue(eta, TellStyle.TickLead(StepKind)))
            {
                ticked = true;
                // cerca o fijado: en 2D, siempre igual de claro; lejos, posicional para saber de dónde viene
                bool close = target != null && (target.LockTarget == this || DistToTarget < 8f);
                Game.Audio?.Play("tell_tick", close ? (Vector3?)null : transform.position, 0.8f, 0.03f);
                GameEvents.RaiseStrikeCue(this, StepKind == AttackKind.Unblockable);
            }
            // el silbido del arma arranca antes para que su pico caiga justo en el golpe
            if (!swung && AudioManager.CueDue(eta, a.kind == AttackKind.Light ? TellStyle.SwingLight : TellStyle.SwingHeavy))
            {
                swung = true;
                Game.Audio?.Play(a.sfx, transform.position, 0.65f, 0.1f);
            }
            // el filo se enciende en el último tramo (dorado: parry; rojo: dash) y sube hasta el cierre del anillo: es lo
            // que el jugador mira. Queda prendido hasta que el golpe sale (EndTell lo apaga)
            if (glint != null && eta <= GlintLead)
            {
                float k = Mathf.InverseLerp(GlintLead, a.TellBias, eta);
                glint.SetGlint(StepKind == AttackKind.Unblockable ? TellStyle.Crimson : TellStyle.Gold, Mathf.Lerp(1.5f, 5f, k * k));
                glintOn = true;
            }
            // brillo del arma en el instante en que se cierra el anillo (el "¡ahora!")
            if (!glinted && eta <= a.TellBias)
            {
                glinted = true;
                Game.FX?.BladeGlint(katanaTip != null ? katanaTip.position : AimPoint + transform.forward * 0.6f, StepKind == AttackKind.Unblockable);
            }
        }

        /// <summary>
        /// Segundos exactos hasta que el golpe del paso actual pega (infinito si ya pegó o no hace daño).
        /// Una embestida pega al alcanzar a Kaito; los jefes cambian sus especiales.
        /// </summary>
        protected virtual float ComputeStrikeEta(AttackDef a)
        {
            if (stepHit || a.damage <= 0f) return float.PositiveInfinity;
            switch (a.special)
            {
                case "charge": return ChargeEta(a);
                case "slam": return specialFired ? float.PositiveInfinity : Mathf.Max(0f, tl.T - stepClock);
                default: return stepClock >= tl.T ? float.PositiveInfinity : tl.T - stepClock;
            }
        }

        /// <summary>Termina el aviso del paso (una sola vez) y libera su lugar en la agenda de golpes.</summary>
        protected void EndTell(TellOutcome outcome)
        {
            if (glintOn) { glintOn = false; glint.SetGlint(Color.black, 0f); }
            if (!tellActive) return;
            tellActive = false;
            Game.Combat?.ReleaseStrike(this);
            Game.FX?.EndTell(this, outcome);
        }

        // ---------------------------------------------------------------- zona del golpe
        /// <summary>Zona real que golpea el paso actual (solo especiales: pisotón, embestida; los jefes suman los suyos).</summary>
        public bool TryGetTellArea(out TellArea area)
        {
            area = default;
            var a = CurrentAttack;
            return a != null && tellActive && HitAreaFor(a, out area);
        }

        protected virtual bool HitAreaFor(AttackDef a, out TellArea area)
        {
            area = default;
            switch (a.special)
            {
                case "slam":
                    area = new TellArea { origin = SlamCenter(a), size = SlamRadius(a) };
                    return true;
                case "charge":
                    if (released) area = new TellArea { lane = true, origin = laneOrigin, forward = laneDir, size = laneLength, width = 2f * (Radius + 0.6f) };
                    else area = new TellArea { lane = true, origin = transform.position, forward = transform.forward.Flat().normalized, size = Mathf.Clamp(ChargeRoom() + 1.5f, 2f, ChargeMaxTravel) + Radius, width = 2f * (Radius + 0.6f) };
                    return true;
            }
            return false;
        }

        /// <summary>¿El golpe en curso puede alcanzar ese punto? (para no enseñar parry/dash con un golpe que no llega)</summary>
        public bool StrikeCanReach(Vector3 p, float pad)
        {
            var a = CurrentAttack;
            if (a == null) return false;
            if (HitAreaFor(a, out var area)) return area.Contains(p, pad);
            return CombatMath.FlatDistance(p, transform.position) <= StrikeReach + pad;
        }

        // ---------------------------------------------------------------- especiales comunes
        Vector3 SlamCenter(AttackDef a) => transform.position + transform.forward * Mathf.Max(0.5f, a.range * 0.4f);
        static float SlamRadius(AttackDef a) => a.specialParam > 0f ? a.specialParam : 4f;
        static float ChargeSpeed(AttackDef a) => a.specialParam > 0f ? a.specialParam : 14f;
        float ChargeContact => Radius + (target != null ? target.Radius : 0.35f) + 0.6f;
        float ChargeRoom() => Mathf.Max(0f, DistToTarget - ChargeContact);

        /// <summary>Embestida: lo que falta para soltarla más el recorrido hasta Kaito (por el carril una vez fijo).</summary>
        float ChargeEta(AttackDef a)
        {
            if (target == null || stepNorm > a.activeEnd) return float.PositiveInfinity;
            float pre = Mathf.Max(0f, tl.T - stepClock);
            if (!released) return pre + ChargeRoom() / ChargeSpeed(a);
            Vector3 to = (target.transform.position - transform.position).Flat();
            float along = Vector3.Dot(to, laneDir) - ChargeContact;
            // ya pasó de largo, o Kaito salió del carril de costado (la respuesta correcta): no lo va a alcanzar y
            // el anillo no puede seguir pidiendo un dash que gasta Espíritu
            float lateral = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, laneDir)));
            return along < -0.5f || lateral > ChargeContact ? float.PositiveInfinity : pre + Mathf.Max(0f, along) / ChargeSpeed(a);
        }

        /// <summary>Movimientos especiales: pisotón y embestida (cualquier enemigo); los jefes agregan los suyos.
        /// Sin especial, golpe normal en la ventana activa.</summary>
        protected virtual void TickSpecial(AttackDef a, float dt)
        {
            switch (a.special)
            {
                case "slam":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Vector3 c = SlamCenter(a);
                        float radius = SlamRadius(a);
                        Game.FX?.Shockwave(c, radius, new Color(1f, 0.75f, 0.45f));
                        Game.FX?.GroundCrack(c, radius);
                        Game.Camera?.Shake(0.75f);
                        Game.Audio?.Play("slam", c, 1f);
                        Game.Input?.Rumble(0.9f, 0.6f, 0.3f);
                        if (target != null && CombatMath.FlatDistance(target.transform.position, c) <= radius + target.Radius)
                            HitPlayer(a, c);
                    }
                    break;

                case "charge":
                    // corre por el carril fijo desde el golpe hasta el final de la fase activa (tl.sustain)
                    if (stepClock >= tl.T && stepNorm <= a.activeEnd && !anim.Frozen)
                    {
                        MoveBy(laneDir * ChargeSpeed(a) * dt);
                        if (!stepHit && target != null && CombatMath.FlatDistance(target.transform.position, transform.position) <= ChargeContact)
                        {
                            stepHit = true;
                            HitPlayer(a, transform.position);
                        }
                        Game.FX?.DustTrail(transform.position);
                    }
                    break;

                case "hop_back":
                case "hop_side":
                    // salto sin daño (el repliegue del ninja del bambú, la finta de su sumo): recorre 'specialParam'
                    // metros entre activeStart y activeEnd, de espaldas a Kaito o de costado (al azar)
                    if (!anim.Frozen)
                    {
                        float n = Mathf.Clamp(stepNorm, a.activeStart, a.activeEnd);
                        if (n > hopNorm)
                        {
                            Vector3 dir = a.special == "hop_back" ? -transform.forward : transform.right * hopSide;
                            MoveBy(dir.Flat().normalized * (a.specialParam * (n - hopNorm) / Mathf.Max(0.01f, a.activeEnd - a.activeStart)));
                            hopNorm = n;
                        }
                    }
                    break;

                default:
                    if (!stepHit && stepNorm >= a.activeStart && stepNorm <= a.activeEnd) TryHitPlayer(a);
                    break;
            }
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
            if (Imbalance >= ExhaustThreshold - 0.01f) BecomeExhausted();
            else EnterGuard();
        }

        protected void ReleaseToken() => Game.Combat?.ReleaseAttackToken(this);

        // ---------------------------------------------------------------- guardia / agotado
        protected void EnterGuard()
        {
            guardHits = 0;
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
            exhaustedHits = 0;
            SetState(EnemyState.Exhausted);
            stateDuration = config.exhaustedTime;
            if (!ExhaustedFeedback) return;
            anim.Play(config.animExhausted, 0.12f);
            Game.FX?.Exhausted(this);
            Game.Audio?.Play("exhausted", transform.position, 0.8f);
        }

        /// <summary>¿Este agotamiento se muestra como postura quebrada (clip mareado, chispas, sonido)? Una pausa que el
        /// jefe se da solo (el ritual de la sal del Ōzeki) queda abierta sin mentir que Kaito le quebró la guardia.</summary>
        protected virtual bool ExhaustedFeedback => true;

        void TickExhausted(float dt)
        {
            if (stateTime >= stateDuration) EndExhaustion();
        }

        /// <summary>Se recupera: la postura vuelve a cero y se cubre.</summary>
        void EndExhaustion()
        {
            Imbalance = 0f;
            EnterGuard();
            OnExhaustionEnded();
        }

        /// <summary>Terminó de estar agotado (los jefes cambian de fase recién acá si les tocaba).</summary>
        protected virtual void OnExhaustionEnded() { }

        /// <summary>
        /// Suma desequilibrio fuera del parry (guardia imperfecta de Kaito, golpes que rebotan en la guardia).
        /// Si la postura se llena se quiebra, igual que con un parry.
        /// </summary>
        public void AddImbalance(float amount)
        {
            if (!IsAlive || amount <= 0f || State == EnemyState.Exhausted) return;
            Imbalance = Mathf.Min(PostureCap, Imbalance + amount);
            Game.UI?.PulseImbalance(this);
            if (Imbalance >= config.maxImbalance - 0.01f) BreakPosture();
        }

        /// <summary>
        /// Postura quebrada: agotado al instante (corta el golpe que estuviera tirando), estallido dorado y la
        /// única cámara lenta del combate común junto con el último enemigo: la escena se ilumina, no se apaga.
        /// </summary>
        void BreakPosture()
        {
            BecomeExhausted();
            Game.FX?.PostureBreak(AimPoint);
            Game.Audio?.Play("posture_break", transform.position, 1f);
            Game.Time?.SlowMotion(0.25f, 0.3f, 0.02f, 0.15f);
        }

        /// <summary>
        /// Después de un remate de Kaito los que están cerca salen despedidos y esperan antes de volver a atacar
        /// (antes el control volvía en medio del golpe de otro). Jefes y enemigos con armadura no se interrumpen.
        /// </summary>
        public void GiveRoom(Vector3 from, float meters, float delay)
        {
            if (!IsAlive || State == EnemyState.Scripted || State == EnemyState.Exhausted) return;
            Vector3 d = (transform.position - from).Flat();
            if (d.sqrMagnitude < 0.01f) d = -transform.forward;
            knock += d.normalized * meters * (1f - config.knockbackResist);
            if (committed) CancelCommit();
            nextAttackTime = Mathf.Max(nextAttackTime, Time.time) + delay;
            // el que estaba por pegar (o por contraatacar) se corta; el resto solo espera
            if (State != EnemyState.Attack && State != EnemyState.Counter) { ReleaseToken(); return; }
            if (config.hyperArmor || this is Boss) return;
            ReleaseToken();
            SetState(EnemyState.Stagger);
            stateDuration = config.staggerTime;
            anim.Play(config.animHit, 0.03f);
        }

        // ---------------------------------------------------------------- recibir golpes
        public virtual HitResult ReceiveHit(in DamageInfo info)
        {
            if (!IsAlive || info.sourceFaction == Faction.Enemy || State == EnemyState.Scripted) return HitResult.Ignored;
            if (!IsAggro) Alert();
            LastHitTime = Time.time;

            // en guardia (solo golpes normales): el primero rebota, el segundo lo desvía y contraataca
            bool guardable = info.kind == AttackKind.Light || info.kind == AttackKind.Heavy;
            if (State == EnemyState.Guard && guardable) return GuardHit();
            // en neutral aguanta pocos golpes seguidos; el siguiente lo frena con la guardia (rebota: es el aviso)
            // y recién si Kaito insiste contraataca. Antes el 3er corte del combo se devolvía siempre, sin aviso
            bool neutral = State == EnemyState.Chase || State == EnemyState.Strafe || State == EnemyState.Idle || State == EnemyState.Alert || State == EnemyState.Stagger;
            if (neutral && guardable)
            {
                if (Time.time - lastNeutralHit > 2.2f) neutralHits = 0;
                lastNeutralHit = Time.time;
                neutralHits++;
                if (neutralHits > config.poiseHits)
                {
                    neutralHits = 0;
                    ReleaseToken();
                    EnterGuard();
                    return GuardHit();
                }
            }

            float dmg = info.damage;
            if (State == EnemyState.Exhausted)
            {
                // ventana de daño: el desequilibrio ya no se gasta por golpe (antes el 2º corte ya chocaba con la guardia)
                dmg *= config.exhaustedDamageMul;
                exhaustedHits++;
                stateDuration = Mathf.Max(stateDuration, stateTime + 0.6f);
            }
            Health -= dmg;
            if (practiceBackup != null) Health = Mathf.Max(Health, config.maxHealth * PracticeMinHealth);
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
                if (exhaustedHits >= ExhaustedHitCap) EndExhaustion();
                else anim.Play(config.animHit, 0.03f);
            }
            else if (State == EnemyState.Attack && (config.hyperArmor && info.kind != AttackKind.Ability || armored && info.kind == AttackKind.Light && !info.riposte))
            {
                // aguanta el golpe sin interrumpirse (armadura propia, o ya comprometido con el golpe: cambian golpes)
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

        /// <summary>Golpe contra la guardia: el primero rebota (clang, suma postura, sin castigo); el segundo se contraataca.</summary>
        HitResult GuardHit()
        {
            if (++guardHits >= 2) { Counter(); return HitResult.Guarded; }
            if (target != null) transform.rotation = Quaternion.LookRotation((target.transform.position - transform.position).Flat().normalized + transform.forward * 0.001f);
            Game.UI?.ShowGuardMark(this);
            // sigue cubierto un poco más: el que castiga es el segundo golpe, tiene que poder llegar
            stateDuration = Mathf.Max(stateDuration, stateTime + 0.5f);
            AddImbalance(GuardHitImbalance);
            return HitResult.Blocked;
        }

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
            Imbalance = Mathf.Min(PostureCap, Imbalance + (perfect ? 1.5f : 1f));
            trail?.Stop();
            Game.UI?.PulseImbalance(this);
            EndTell(TellOutcome.Parried);   // el anillo se rompe en pedazos (antes de que el Recoil lo cancele)
            // un paso 'noRecoil' (los combos de ritmo de Mizuchi) suma la postura pero el combo sigue a su ritmo
            if (State == EnemyState.Attack && (CurrentAttack == null || !CurrentAttack.noRecoil))
            {
                SetState(EnemyState.Recoil);
                stateDuration = config.parriedRecoil * (perfect ? 1.5f : 1f);
                anim.Play(config.animParried, 0.03f);
                knock += -transform.forward * (perfect ? 0.8f : 0.4f);
            }
            if (Imbalance >= config.maxImbalance - 0.01f) BreakPosture();
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
            EndTell(TellOutcome.Cancelled);   // muere a mitad de un golpe (acá no pasa por SetState)
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

        protected virtual IEnumerator DeathRoutine(Vector3 dir)
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
