using System.Collections;
using UnityEngine;

namespace Nindo
{
    public enum PlayerState { Locomotion, Attack, Parry, ParryRecover, ParrySuccess, Dash, Hurt, Blocked, Finisher, Ability, Dead, Scripted }

    /// <summary>
    /// Kaito. Un solo componente con una máquina de estados explícita (reemplaza a
    /// NewPlayerMovement + PlayerCombat + PlayerDash + PlayerFinisher + LockOnTarget +
    /// PlayerLifeManager + ManaBar, que se pisaban entre sí).
    /// Movimiento con CharacterController (estable con cámara lenta y hit-stop).
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    [DefaultExecutionOrder(-100)]
    public partial class PlayerController : MonoBehaviour, IHittable
    {
        public PlayerConfig config = new PlayerConfig();

        [Header("Referencias (se autocompletan)")]
        public Transform model;          // hijo con el Animator
        public Animator animator;
        public Transform katanaTip;
        public Transform katanaBase;

        // --------------------------------------------------------------- estado
        public PlayerState State { get; private set; } = PlayerState.Locomotion;
        public float Health { get; private set; }
        public float Spirit { get; private set; }
        public float Rage { get; private set; }
        public bool RageActive { get; private set; }
        public float Health01 => Health / config.maxHealth;
        public float Spirit01 => Spirit / config.maxSpirit;
        public float Rage01 => Rage / config.maxRage;
        public bool IsAlive => State != PlayerState.Dead;
        public bool IsLockedOn => lockTarget != null;
        public Enemy LockTarget => lockTarget;
        public bool HasKatana { get; private set; } = true;
        public bool AbilitiesUnlocked => Game.Save.HasFlag(Flags.AbilitiesUnlocked) || debugUnlockAll;
        public bool DashUnlocked => Game.Save.HasFlag(Flags.DashUnlocked) || debugUnlockAll;
        public bool debugUnlockAll;

        public Faction Faction => Faction.Player;
        public Transform Root => transform;
        public float Radius => cc != null ? cc.radius : 0.35f;
        public Vector3 AimPoint => transform.position + Vector3.up * 0.9f;
        public Vector3 Velocity => velocity;

        CharacterController cc;
        CharacterAnimator anim = new CharacterAnimator();
        BladeTrail trail;
        KatanaFire katanaFire;
        Vector3 velocity;          // horizontal
        float verticalSpeed;
        float stateTime;           // segundos en el estado actual (escalados)
        float invulnUntil;
        float noDamageTime;
        Enemy lockTarget;
        float lockHeldTime;
        float stepTimer;
        float rageTimer;
        Vector3 externalPush;
        Quaternion modelBaseRot = Quaternion.identity;
        Vector3 modelBasePos;

        public CharacterAnimator Anim => anim;

        // =============================================================== ciclo de vida
        void Awake()
        {
            Game.Player = this;
            cc = GetComponent<CharacterController>();
            if (animator == null) animator = GetComponentInChildren<Animator>();
            if (model == null && animator != null) model = animator.transform;
            if (model != null) { modelBaseRot = model.localRotation; modelBasePos = model.localPosition; }
            anim.Init(animator);
            SetupKatana();
            Health = config.maxHealth;
            Spirit = config.startSpirit;
            Rage = 0f;
        }

        void OnDestroy()
        {
            if (Game.Player == this) Game.Player = null;
        }

        void SetupKatana()
        {
            if (katanaTip == null || katanaBase == null)
                KatanaRig.Find(model != null ? model : transform, new[] { "Isan", "Katana", "katana" }, out katanaBase, out katanaTip);
            if (katanaTip != null && katanaBase != null)
            {
                trail = BladeTrail.Create(transform, katanaBase, katanaTip, Game.Content != null ? Game.Content.trailMaterial : null, new Color(1f, 0.92f, 0.65f, 0.9f));
                katanaFire = KatanaFire.Create(katanaBase, katanaTip);
            }
        }

        /// <summary>Muestra/oculta la katana (en el prólogo Kaito todavía no la tiene).</summary>
        public void SetKatanaVisible(bool visible)
        {
            HasKatana = visible;
            var root = model != null ? model : transform;
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                string n = r.gameObject.name;
                if (n.Contains("Isan") || n.Contains("Katana") || n.Contains("katana")) r.enabled = visible;
            }
        }

        // =============================================================== update
        void Update()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) { anim.Tick(); return; }
            var input = Game.Input;
            stateTime += dt;
            noDamageTime += dt;

            if (State != PlayerState.Dead && State != PlayerState.Scripted && !Game.InCutscene)
                UpdateTargeting(input, dt);

            switch (State)
            {
                case PlayerState.Locomotion: TickLocomotion(input, dt); break;
                case PlayerState.Attack: TickAttack(input, dt); break;
                case PlayerState.Parry: TickParry(input, dt); break;
                case PlayerState.ParryRecover: TickParryRecover(input, dt); break;
                case PlayerState.ParrySuccess: TickParrySuccess(input, dt); break;
                case PlayerState.Dash: TickDash(input, dt); break;
                case PlayerState.Hurt: TickHurt(input, dt); break;
                case PlayerState.Blocked: TickBlocked(input, dt); break;
                case PlayerState.Finisher: TickFinisher(dt); break;
                case PlayerState.Ability: TickAbility(input, dt); break;
                case PlayerState.Scripted: TickScripted(dt); break;
                case PlayerState.Dead: velocity = Vector3.zero; break;
            }

            TickRage(dt);
            ApplyMovement(dt);
            anim.Tick();
        }

        void SetState(PlayerState s)
        {
            if (State == PlayerState.Attack || State == PlayerState.Ability) trail?.Stop();
            State = s;
            stateTime = 0f;
            anim.SetSpeed(RageActive ? config.rageSpeedMul : 1f);
        }

        // =============================================================== movimiento
        Vector3 InputToWorld(Vector2 move)
        {
            Vector3 f = Vector3.forward, r = Vector3.right;
            if (Game.Camera != null) Game.Camera.MovementBasis(out f, out r);
            return f * move.y + r * move.x;
        }

        Vector2 MoveInput => (Game.Input != null && !Game.InCutscene) ? Game.Input.GameplayMove : Vector2.zero;

        void TickLocomotion(InputReader input, float dt)
        {
            Vector3 wish = InputToWorld(MoveInput) * config.runSpeed;
            velocity = Vector3.MoveTowards(velocity, wish, config.acceleration * dt);
            float speed01 = velocity.magnitude / config.runSpeed;

            if (wish.sqrMagnitude > 0.01f)
                FaceTowards(wish, config.turnSpeed, dt);
            else if (lockTarget != null)
                FaceTowards(lockTarget.transform.position - transform.position, config.turnSpeed * 0.6f, dt);

            anim.SetLocomotion(speed01, dt);
            if (anim.Current != "Locomotion" && stateTime > 0.02f) anim.Play("Locomotion", 0.12f);

            // pasos
            if (speed01 > 0.3f && IsGrounded)
            {
                stepTimer -= dt * speed01;
                if (stepTimer <= 0f) { stepTimer = 0.32f; Game.Audio?.Play(StepSound(), transform.position, 0.35f, 0.15f); }
            }

            if (input == null || Game.InCutscene) return;
            TryCombatActions(input, allowAttack: true);
            TryInteract(input);
        }

        /// <summary>Acciones que se pueden iniciar desde estados "libres".</summary>
        bool TryCombatActions(InputReader input, bool allowAttack)
        {
            if (!HasKatana) return false;
            if (input.Buffered(Act.Finisher, 0.15f) && TryFinisher()) { input.Consume(Act.Finisher); return true; }
            if (input.Buffered(Act.Ability1) && AbilitiesUnlocked && TryAbility(1)) { input.Consume(Act.Ability1); return true; }
            if (input.Buffered(Act.Ability2) && AbilitiesUnlocked && TryAbility(2)) { input.Consume(Act.Ability2); return true; }
            if (input.Buffered(Act.Parry, 0.12f)) { input.Consume(Act.Parry); StartParry(); return true; }
            if (input.Buffered(Act.Dash, 0.15f)) { input.Consume(Act.Dash); if (TryDash()) return true; }
            if (allowAttack && input.Buffered(Act.Attack, 0.2f)) { input.Consume(Act.Attack); StartAttack(0); return true; }
            return false;
        }

        void FaceTowards(Vector3 dir, float speed, float dt)
        {
            dir.y = 0f;
            if (dir.sqrMagnitude < 0.0001f) return;
            Quaternion target = Quaternion.LookRotation(dir.normalized, Vector3.up);
            transform.rotation = CombatMath.Damp(transform.rotation, target, speed, dt);
        }

        void FaceInstant(Vector3 dir)
        {
            dir.y = 0f;
            if (dir.sqrMagnitude < 0.0001f) return;
            transform.rotation = Quaternion.LookRotation(dir.normalized, Vector3.up);
        }

        bool IsGrounded => cc != null && cc.isGrounded;

        /// <summary>Sonido de paso según la superficie: madera (pasarelas, puentes), piedra (escaleras,
        /// patio del dojo), nieve (zona nevada) o tierra/pasto.</summary>
        string StepSound()
        {
            if (Physics.Raycast(transform.position + Vector3.up * 0.3f, Vector3.down, out var hit, 0.8f, ~0, QueryTriggerInteraction.Ignore))
            {
                string n = hit.collider.name;
                if (n.StartsWith("boardwalk") || n.StartsWith("dock") || n.StartsWith("bridge") || n.StartsWith("lake_arena") || n.StartsWith("house_fisher")) return "step_wood";
                if (n.StartsWith("stairs") || n.StartsWith("dojo") || n.StartsWith("stepping")) return "step_stone";
            }
            if (Zone.Current != null && Zone.Current.snow) return "step_snow";
            return "step";
        }

        void ApplyMovement(float dt)
        {
            if (cc == null || !cc.enabled) return;
            if (IsGrounded && verticalSpeed < 0f) verticalSpeed = -2f;
            verticalSpeed += config.gravity * dt;
            Vector3 motion = (velocity + externalPush) * dt;
            motion.y = verticalSpeed * dt;
            externalPush = Vector3.MoveTowards(externalPush, Vector3.zero, 30f * dt);
            cc.Move(motion);
            // red de seguridad: si se cae del mundo, volver al checkpoint
            if (transform.position.y < -60f && State != PlayerState.Dead) RespawnAt(Game.World != null ? Game.World.RespawnPoint() : Vector3.up * 2f, transform.rotation);
        }

        /// <summary>Empujón externo (knockback) en metros.</summary>
        public void Push(Vector3 dir, float meters)
        {
            dir.y = 0f;
            externalPush += dir.normalized * meters * 10f;
        }

        /// <summary>Teletransporte seguro (desactiva el CharacterController un frame).</summary>
        public void Teleport(Vector3 pos, Quaternion rot)
        {
            if (cc != null) cc.enabled = false;
            transform.SetPositionAndRotation(pos, rot);
            if (cc != null) cc.enabled = true;
            velocity = Vector3.zero; externalPush = Vector3.zero; verticalSpeed = 0f;
            Game.Camera?.Snap();
        }

        // =============================================================== fijado
        void UpdateTargeting(InputReader input, float dt)
        {
            if (lockTarget != null && (!lockTarget.IsAlive || !lockTarget.Targetable ||
                CombatMath.FlatDistance(lockTarget.transform.position, transform.position) > config.lockRange + 4f))
            {
                // si murió, saltar automáticamente al siguiente enemigo cercano
                var next = Game.Combat != null ? Game.Combat.FindBestTarget(transform.position, transform.forward, 9f, lockTarget) : null;
                SetLock(next);
            }
            if (input == null) return;
            if (input.LockHeld) lockHeldTime += Time.unscaledDeltaTime; else lockHeldTime = 0f;
            if (lockTarget != null && lockHeldTime > 0.45f) { SetLock(null); lockHeldTime = -999f; Game.Audio?.Play("ui_move", null, 0.4f); }

            if (input.Pressed(Act.Lock) && !Game.InCutscene)
            {
                if (lockTarget == null)
                {
                    Vector3 facing = InputToWorld(MoveInput);
                    if (facing.sqrMagnitude < 0.01f) facing = transform.forward;
                    SetLock(Game.Combat?.FindBestTarget(transform.position, facing, config.lockRange));
                }
                else
                {
                    var next = Game.Combat?.CycleTarget(transform.position, lockTarget, config.lockRange, 1);
                    if (next != null && next != lockTarget) SetLock(next);
                }
            }
            if (lockTarget != null && (input.Pressed(Act.LockNext) || input.Pressed(Act.LockPrev)))
            {
                var next = Game.Combat?.CycleTarget(transform.position, lockTarget, config.lockRange, input.Pressed(Act.LockNext) ? 1 : -1);
                if (next != null) SetLock(next);
            }
        }

        public void SetLock(Enemy e)
        {
            if (e == lockTarget) return;
            lockTarget = e;
            Game.Camera?.SetLockTarget(e != null ? e.transform : null);
            Game.UI?.SetLockTarget(e);
            if (e != null) Game.Audio?.Play("lock", null, 0.35f);
        }

        /// <summary>Objetivo para "imantar" un ataque: el fijado o el mejor enemigo cerca hacia donde apunta el stick.</summary>
        Enemy AttackTarget(float range)
        {
            if (lockTarget != null && CombatMath.FlatDistance(lockTarget.transform.position, transform.position) < range + 1.5f) return lockTarget;
            if (Game.Combat == null) return null;
            Vector3 dir = InputToWorld(MoveInput);
            if (dir.sqrMagnitude < 0.01f) dir = transform.forward;
            var e = Game.Combat.FindBestTarget(transform.position, dir, range);
            if (e == null) return null;
            if (Vector3.Angle(dir.Flat(), (e.transform.position - transform.position).Flat()) > config.attackMagnetAngle) return null;
            return e;
        }

        // =============================================================== recursos
        public void AddSpirit(float v)
        {
            Spirit = Mathf.Clamp(Spirit + v, 0f, config.maxSpirit);
        }

        public bool SpendSpirit(float cost)
        {
            if (Spirit + 0.01f < cost)
            {
                Game.UI?.DenySpirit();
                Game.Audio?.Play("denied", null, 0.5f);
                return false;
            }
            Spirit -= cost;
            return true;
        }

        public void Heal(float v)
        {
            if (!IsAlive) return;
            float before = Health;
            Health = Mathf.Clamp(Health + v, 0f, config.maxHealth);
            if (Health > before + 0.5f) Game.FX?.HealBurst(transform.position);
        }

        public void RestoreAll()
        {
            Health = config.maxHealth;
            Spirit = Mathf.Max(Spirit, config.maxSpirit * 0.5f);
        }

        void AddRage(float v)
        {
            if (RageActive) { rageTimer = Mathf.Min(config.rageDuration, rageTimer + config.rageExtendOnHit * Mathf.Sign(v)); return; }
            // jugar bien sin recibir daño llena más rápido
            float streak = Mathf.Lerp(1f, 1.6f, Mathf.Clamp01(noDamageTime / 20f));
            Rage = Mathf.Clamp(Rage + v * streak, 0f, config.maxRage);
            if (Rage >= config.maxRage - 0.01f) EnterRage();
        }

        void EnterRage()
        {
            RageActive = true;
            rageTimer = config.rageDuration;
            katanaFire?.SetActive(true);
            trail?.SetColor(new Color(1f, 0.55f, 0.2f, 1f));
            Game.FX?.RageBurst(transform.position);
            Game.FX?.Screen?.SetRage(true);
            Game.Audio?.Play("rage_on", transform.position, 0.9f);
            Game.Camera?.Punch(-5f, 0.35f);
            Game.Camera?.Shake(0.45f);
            Game.Time?.SlowMotion(0.35f, 0.45f, 0.02f, 0.3f);
            Game.UI?.ShowToast("¡FILO DE IRA!", new Color(1f, 0.45f, 0.2f));
            Game.Input?.Rumble(0.6f, 0.8f, 0.35f);
            anim.SetSpeed(config.rageSpeedMul);
        }

        void ExitRage()
        {
            RageActive = false;
            Rage = 0f;
            katanaFire?.SetActive(false);
            trail?.SetColor(new Color(1f, 0.92f, 0.65f, 0.9f));
            Game.FX?.Screen?.SetRage(false);
            anim.SetSpeed(1f);
        }

        void TickRage(float dt)
        {
            if (!RageActive) return;
            rageTimer -= dt;
            Rage = config.maxRage * Mathf.Clamp01(rageTimer / config.rageDuration);
            if (rageTimer <= 0f) ExitRage();
        }

        float DamageMul => RageActive ? config.rageDamageMul : 1f;

        // =============================================================== recibir golpes
        public bool IsInvulnerable => Time.time < invulnUntil || State == PlayerState.Finisher || State == PlayerState.Dead || Game.InCutscene;

        public HitResult ReceiveHit(in DamageInfo info)
        {
            if (!IsAlive || info.sourceFaction == Faction.Player) return HitResult.Ignored;

            // 1) dash: i-frames (y esquive perfecto)
            if (State == PlayerState.Dash && stateTime >= config.dashIFrameStart && stateTime <= config.dashIFrameEnd)
            {
                OnDodged(info);
                return HitResult.Dodged;
            }
            if (State == PlayerState.Ability && abilityInvulnerable) return HitResult.Dodged;
            if (IsInvulnerable) return HitResult.Ignored;

            // 2) parry
            if (State == PlayerState.Parry && info.CanBeParried && stateTime <= CurrentParryWindow)
            {
                bool perfect = stateTime <= config.perfectWindow * parryWindowMul;
                OnParrySuccess(info, perfect);
                return perfect ? HitResult.PerfectParry : HitResult.Parried;
            }
            if (State == PlayerState.ParrySuccess && info.CanBeParried && stateTime < 0.18f)
            {
                // encadenar parrys contra combos rápidos
                OnParrySuccess(info, false);
                return HitResult.Parried;
            }

            // 3) daño
            TakeDamage(info);
            return Health <= 0f ? HitResult.Killed : HitResult.Hit;
        }

        void TakeDamage(in DamageInfo info)
        {
            float dmg = info.damage;
            Health = Mathf.Max(0f, Health - dmg);
            noDamageTime = 0f;
            if (!RageActive) Rage = Mathf.Max(0f, Rage - config.rageLossOnDamage);
            invulnUntil = Time.time + config.invulnAfterHit;
            GameEvents.RaisePlayerDamaged(dmg);

            Vector3 dir = info.direction.sqrMagnitude > 0.01f ? info.direction.Flat().normalized : -transform.forward;
            bool heavy = info.kind == AttackKind.Heavy || info.kind == AttackKind.Unblockable || dmg >= 20f;
            Game.FX?.PlayerHurt(AimPoint, dir, heavy);
            Game.Audio?.Play("hurt", transform.position, 0.9f, 0.1f);
            Game.Camera?.Shake(heavy ? 0.6f : 0.4f);
            Game.Camera?.Impulse(dir, heavy ? 0.6f : 0.35f);
            Game.Time?.HitStop(heavy ? 0.09f : 0.06f);
            Game.FX?.Screen?.DamagePulse(heavy ? 1f : 0.6f);
            Game.Input?.Rumble(0.7f, 0.4f, heavy ? 0.35f : 0.2f);

            if (Health <= 0f) { Die(); return; }

            CancelAbilityCamera();
            trail?.Stop();
            FaceInstant(-dir);
            Push(dir, info.knockback + (heavy ? 1.2f : 0.5f));
            SetState(PlayerState.Hurt);
            hurtDuration = heavy ? config.heavyHurtTime : config.hurtTime;
            anim.Play("Hit", 0.04f);
        }

        float hurtDuration;

        void TickHurt(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 40f * dt);
            if (stateTime >= hurtDuration)
            {
                SetState(PlayerState.Locomotion);
                return;
            }
            // permite escapar con dash al final del aturdimiento
            if (stateTime > hurtDuration * 0.6f && input != null && input.Buffered(Act.Dash))
            {
                input.Consume(Act.Dash);
                TryDash();
            }
        }

        // =============================================================== muerte / respawn
        void Die()
        {
            if (State == PlayerState.Dead) return;
            CancelAbilityCamera();
            if (RageActive) ExitRage();
            SetLock(null);
            SetState(PlayerState.Dead);
            velocity = Vector3.zero;
            anim.Play("Hit", 0.05f);
            Game.Time?.SlowMotion(0.25f, 1.6f, 0.02f, 0.5f);
            Game.Audio?.Play("death", transform.position, 1f);
            StartCoroutine(DeathFall());
            Game.Save.deaths++;
            GameEvents.RaisePlayerDied();
        }

        IEnumerator DeathFall()
        {
            if (model == null) yield break;
            float t = 0f;
            Quaternion from = model.localRotation;
            Quaternion to = modelBaseRot * Quaternion.Euler(-80f, 0f, 0f);
            while (t < 1f)
            {
                t += Time.unscaledDeltaTime * 2.2f;
                model.localRotation = Quaternion.Slerp(from, to, t * t);
                yield return null;
            }
        }

        public void RespawnAt(Vector3 pos, Quaternion rot)
        {
            StopAllCoroutines();
            AbortFinisherAndAbility(); // p. ej. caer del mundo en pleno Corte del Viento
            if (model != null) { model.localRotation = modelBaseRot; model.localPosition = modelBasePos; }
            Teleport(pos, rot);
            Health = config.maxHealth;
            Spirit = Mathf.Max(Spirit, config.maxSpirit * 0.5f);
            if (RageActive) ExitRage();
            Rage = 0f;
            invulnUntil = Time.time + 1.5f;
            SetState(PlayerState.Locomotion);
            anim.Play("Locomotion", 0f);
            GameEvents.RaisePlayerRespawned();
        }

        // =============================================================== interacción
        Interactable nearInteractable;

        void TryInteract(InputReader input)
        {
            nearInteractable = Interactable.FindBest(transform.position, transform.forward);
            Game.UI?.SetInteractPrompt(nearInteractable);
            if (nearInteractable != null && input.Buffered(Act.Interact, 0.1f))
            {
                // F también es finisher: si hay un enemigo ejecutable cerca, gana el finisher
                if (FinisherCandidate() != null) return;
                input.Consume(Act.Interact);
                input.Consume(Act.Finisher);
                nearInteractable.Interact(this);
            }
        }

        // =============================================================== modo guionado (cinemáticas)
        Vector3 scriptedTarget;
        bool scriptedMoving;
        float scriptedSpeed;

        public void EnterScripted()
        {
            // la cinemática puede arrancar en plena ejecución/habilidad (p. ej. dentro de e.Execute()
            // al completar el encuentro): apagar sus efectos de pantalla, planos y cámara lenta
            var pendingExecution = AbortFinisherAndAbility();
            trail?.Stop();
            SetLock(null);
            SetState(PlayerState.Scripted);
            velocity = Vector3.zero;
            scriptedMoving = false;
            anim.Play("Locomotion", 0.15f);
            // si el tajo no había llegado, el enemigo quedó congelado en "Executed" (ni vivo ni muerto):
            // ya estaba entregado, así que se completa la ejecución sin el tajo
            if (pendingExecution != null && pendingExecution.State == EnemyState.Executed) pendingExecution.Execute(this);
        }

        public void ExitScripted()
        {
            if (State == PlayerState.Scripted) SetState(PlayerState.Locomotion);
        }

        public void ScriptedMoveTo(Vector3 target, float speed = 3.5f)
        {
            scriptedTarget = target; scriptedMoving = true; scriptedSpeed = speed;
        }

        public bool ScriptedArrived => !scriptedMoving;

        public void ScriptedFace(Vector3 worldPoint) => FaceInstant(worldPoint - transform.position);

        public void ScriptedPlay(string state, float fade = 0.1f) => anim.Play(state, fade);

        void TickScripted(float dt)
        {
            if (scriptedMoving)
            {
                Vector3 d = (scriptedTarget - transform.position).Flat();
                if (d.magnitude < 0.2f) { scriptedMoving = false; velocity = Vector3.zero; }
                else
                {
                    velocity = d.normalized * scriptedSpeed;
                    FaceTowards(d, 10f, dt);
                }
            }
            else velocity = Vector3.MoveTowards(velocity, Vector3.zero, 20f * dt);
            anim.SetLocomotion(velocity.magnitude / config.runSpeed, dt);
            if (anim.Current != "Locomotion" && scriptedMoving) anim.Play("Locomotion", 0.15f);
        }
    }

    /// <summary>Nombres de flags de progreso usados por varios sistemas.</summary>
    public static class Flags
    {
        public const string IntroDone = "intro_done";
        public const string KatanaObtained = "katana";
        public const string ParryTutorial = "tut_parry";
        public const string DashUnlocked = "dash_unlocked";
        public const string AbilitiesUnlocked = "abilities_unlocked";
        public const string WallGateOpen = "wall_gate_open";
        public const string ForestSeen = "forest_seen";
        public const string SumoIntro = "sumo_intro";
        public const string DojoGateSeen = "dojo_gate_seen";
        public const string DojoOpen = "dojo_open";
        public const string FinalBossDone = "final_boss_done";
        public const string Ending = "ending";
        public static string Boss(string id) => "boss_" + id;
        public static string Encounter(string id) => "enc_" + id;
    }
}
