using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    public partial class PlayerController
    {
        // =============================================================== ATAQUE
        int comboIndex;
        AttackDef currentAttack;
        float attackNorm;            // 0..1 del clip
        float attackLen;
        Enemy attackTarget;
        float lungeDone;
        float riposteUntil;
        readonly HashSet<IHittable> hitThisSwing = new HashSet<IHittable>();
        bool swingSoundPlayed;

        void StartAttack(int index)
        {
            var defs = config.combo;
            if (defs == null || defs.Length == 0) return;
            comboIndex = Mathf.Clamp(index, 0, defs.Length - 1);
            currentAttack = defs[comboIndex];
            attackLen = anim.Length(currentAttack.state, 0.45f) / Mathf.Max(0.05f, currentAttack.speed);
            attackNorm = 0f;
            lungeDone = 0f;
            hitThisSwing.Clear();
            swingSoundPlayed = false;
            SetState(PlayerState.Attack);

            attackTarget = AttackTarget(config.attackMagnetRange);
            Vector3 aim = attackTarget != null ? attackTarget.transform.position - transform.position : InputToWorld(MoveInput);
            if (aim.sqrMagnitude > 0.01f) FaceInstant(aim);
            velocity = Vector3.zero;
            anim.Play(currentAttack.state, comboIndex == 0 ? 0.05f : 0.03f);
            Game.UI?.HideInteractPrompt();
        }

        void TickAttack(InputReader input, float dt)
        {
            var a = currentAttack;
            float timing = a.Timing(attackNorm) * a.speed * (RageActive ? config.rageSpeedMul : 1f);
            anim.SetSpeed(timing);
            if (!anim.Frozen) attackNorm += dt * timing / Mathf.Max(0.05f, attackLen * a.speed);

            // seguir apuntando al objetivo durante la anticipación
            if (attackTarget != null && attackNorm < a.activeStart && attackTarget.IsAlive)
                FaceTowards(attackTarget.transform.position - transform.position, 25f, dt);

            // avance (lunge) con imán: se frena antes de atravesar al enemigo
            if (attackNorm >= a.lungeStart && attackNorm <= a.lungeEnd && lungeDone < a.lunge)
            {
                float span = Mathf.Max(0.01f, (a.lungeEnd - a.lungeStart) * attackLen);
                float step = a.lunge / span * dt;
                float maxStep = a.lunge - lungeDone;
                if (attackTarget != null && attackTarget.IsAlive)
                {
                    float room = CombatMath.FlatDistance(attackTarget.transform.position, transform.position) - attackTarget.Radius - Radius - 0.35f;
                    maxStep = Mathf.Min(maxStep, Mathf.Max(0f, room));
                }
                step = Mathf.Min(step, maxStep);
                lungeDone += step;
                velocity = transform.forward * (step / dt);
            }
            else velocity = Vector3.MoveTowards(velocity, Vector3.zero, 60f * dt);

            if (!swingSoundPlayed && attackNorm >= a.activeStart - 0.08f)
            {
                swingSoundPlayed = true;
                Game.Audio?.Play(a.sfx, transform.position, 0.7f, 0.12f);
                trail?.Begin();
            }

            if (attackNorm >= a.activeStart && attackNorm <= a.activeEnd)
                DoAttackHits(a);
            if (attackNorm > a.activeEnd + 0.05f) trail?.Stop();

            if (input != null && !Game.InCutscene)
            {
                // cancelaciones: parry durante la anticipación, dash/parry al final
                bool earlyCancel = attackNorm < a.activeStart * 0.7f;
                bool lateCancel = attackNorm >= a.cancelWindow;
                if ((earlyCancel || lateCancel) && input.Buffered(Act.Parry, 0.1f)) { input.Consume(Act.Parry); StartParry(); return; }
                if (lateCancel && input.Buffered(Act.Dash, 0.12f)) { input.Consume(Act.Dash); if (TryDash()) return; }
                if (lateCancel && input.Buffered(Act.Finisher, 0.12f) && TryFinisher()) { input.Consume(Act.Finisher); return; }
                // combo
                if (attackNorm >= a.comboWindow && comboIndex < config.combo.Length - 1 && input.Buffered(Act.Attack, 0.3f))
                {
                    input.Consume(Act.Attack);
                    StartAttack(comboIndex + 1);
                    return;
                }
            }

            if (attackNorm >= 1f)
            {
                // pequeño margen para seguir el combo después del final del clip
                if (input != null && comboIndex < config.combo.Length - 1 && attackNorm < 1f + config.comboGrace / attackLen && input.Buffered(Act.Attack, 0.3f))
                {
                    input.Consume(Act.Attack);
                    StartAttack(comboIndex + 1);
                    return;
                }
                if (attackNorm >= 1f + config.comboGrace / attackLen || MoveInput.sqrMagnitude > 0.1f)
                {
                    trail?.Stop();
                    SetState(PlayerState.Locomotion);
                }
            }
        }

        void DoAttackHits(AttackDef a)
        {
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return;
            for (int i = 0; i < list.Count; i++)
            {
                // una muerte pudo arrancar una cinemática: no seguir pegando (un "Guarded" sacaría a Kaito del modo guionado)
                if (State == PlayerState.Scripted) return;
                var e = list[i];
                if (e == null || !e.IsAlive || hitThisSwing.Contains(e)) continue;
                if (!CombatMath.InArc(transform, e.transform.position, a.range, a.arc, e.Radius)) continue;
                if (Mathf.Abs(e.transform.position.y - transform.position.y) > 2.5f) continue;
                hitThisSwing.Add(e);
                ResolveHitOnEnemy(e, a.damage, a.imbalance, a.kind, a.knockback, a.hitStop, a.shake, a.name);
            }
        }

        /// <summary>Aplica un golpe de Kaito a un enemigo y produce todo el feedback.</summary>
        HitResult ResolveHitOnEnemy(Enemy e, float damage, float imbalance, AttackKind kind, float knockback, float hitStop, float shake, string attackName)
        {
            bool riposte = Time.time < riposteUntil;
            var info = new DamageInfo
            {
                damage = damage * DamageMul * (riposte ? config.riposteDamageMul : 1f),
                imbalance = imbalance * (RageActive ? 1.5f : 1f) * (riposte ? 1.5f : 1f),
                kind = kind,
                direction = (e.transform.position - transform.position).Flat().normalized,
                point = e.AimPoint,
                knockback = knockback,
                sourceFaction = Faction.Player,
                source = this,
                attackName = attackName,
            };
            if (info.direction.sqrMagnitude < 0.01f) info.direction = transform.forward;
            var r = e.ReceiveHit(info);
            Vector3 p = Vector3.Lerp(AimPoint, e.AimPoint, 0.65f);
            switch (r)
            {
                case HitResult.Hit:
                case HitResult.Killed:
                {
                    bool kill = r == HitResult.Killed;
                    bool heavy = kind != AttackKind.Light || kill || riposte;
                    anim.Freeze(hitStop * (kill ? 1.6f : 1f));
                    e.Anim.Freeze(hitStop * (kill ? 1.6f : 1f));
                    if (kill) Game.Time?.HitStop(0.05f);
                    Game.FX?.HitImpact(p, info.direction, heavy, RageActive);
                    Game.Audio?.Play(heavy ? "hit_heavy" : "hit", p, 0.85f, 0.12f);
                    Game.Camera?.Shake(shake * (kill ? 1.6f : 1f));
                    Game.Camera?.Impulse(info.direction, shake * 0.5f);
                    Game.Input?.Rumble(0.25f, 0.55f, 0.08f);
                    AddSpirit(config.spiritOnHit);
                    AddRage(config.rageOnHit);
                    if (riposte) riposteUntil = 0f;
                    if (kill) OnKilledEnemy(e, false);
                    break;
                }
                case HitResult.Guarded:
                    // el enemigo desvió el golpe: Kaito rebota
                    Game.FX?.Clash(p, -info.direction, false);
                    Game.Audio?.Play("clang", p, 0.9f, 0.08f);
                    Game.Camera?.Shake(0.35f);
                    Game.Time?.HitStop(0.06f);
                    Game.Input?.Rumble(0.5f, 0.3f, 0.15f);
                    GetCountered(e);
                    break;
            }
            return r;
        }

        void OnKilledEnemy(Enemy e, bool finisher)
        {
            Heal(finisher ? config.healOnFinisher : config.healOnKill);
            AddSpirit(config.spiritOnKill);
            AddRage(finisher ? 20f : 8f);
            if (!finisher) Game.Time?.SlowMotion(0.3f, 0.35f, 0.01f, 0.25f);
            Game.Camera?.Punch(-3f, 0.25f);
        }

        /// <summary>El enemigo estaba en guardia y contraatacó: animación "Bloked".</summary>
        void GetCountered(Enemy by)
        {
            trail?.Stop();
            SetState(PlayerState.Blocked);
            anim.Play("Blocked", 0.03f);
            Push(-(by.transform.position - transform.position), 0.9f);
        }

        void TickBlocked(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 40f * dt);
            if (stateTime > 0.28f && input != null && input.Buffered(Act.Parry, 0.12f)) { input.Consume(Act.Parry); StartParry(); return; }
            if (stateTime > 0.32f && input != null && input.Buffered(Act.Dash, 0.12f)) { input.Consume(Act.Dash); if (TryDash()) return; }
            if (stateTime >= 0.5f) SetState(PlayerState.Locomotion);
        }

        // =============================================================== PARRY
        float lastParryWhiff = -9f;
        float parryWindowMul = 1f;
        float CurrentParryWindow => config.parryWindow * parryWindowMul;

        void StartParry()
        {
            CancelAbilityCamera();
            trail?.Stop();
            // spam: si fallaste un parry hace muy poco, la ventana se achica
            parryWindowMul = Time.time - lastParryWhiff < 0.55f ? config.spamPenalty : 1f;
            SetState(PlayerState.Parry);
            velocity = Vector3.zero;
            var t = lockTarget != null ? lockTarget : AttackTarget(5f);
            if (t != null) FaceInstant(t.transform.position - transform.position);
            anim.Play("ParryStance", 0.03f);
            Game.Audio?.Play("parry_ready", transform.position, 0.25f, 0.1f);
        }

        void TickParry(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 50f * dt);
            if (stateTime > CurrentParryWindow)
            {
                lastParryWhiff = Time.time;
                SetState(PlayerState.ParryRecover);
            }
        }

        void TickParryRecover(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 50f * dt);
            if (stateTime >= config.parryRecover)
            {
                SetState(PlayerState.Locomotion);
                anim.Play("Locomotion", 0.15f);
            }
        }

        void OnParrySuccess(in DamageInfo info, bool perfect)
        {
            SetState(PlayerState.ParrySuccess);
            anim.Play("ParrySuccess", 0.02f);
            riposteUntil = Time.time + config.riposteWindow;
            Vector3 dir = info.direction.sqrMagnitude > 0.01f ? info.direction.Flat().normalized : -transform.forward;
            FaceInstant(-dir);
            Push(dir, perfect ? 0.25f : 0.55f);
            var e = info.source as Enemy;
            if (e != null) e.OnParried(perfect);

            Vector3 p = AimPoint + transform.forward * 0.55f;
            Game.FX?.Clash(p, transform.forward, true);
            Game.FX?.ParryFlash(p, perfect);
            Game.Audio?.Play(perfect ? "parry_perfect" : "parry", p, 1f, 0.06f);
            Game.Camera?.Punch(perfect ? -6f : -3.5f, perfect ? 0.35f : 0.22f);
            Game.Camera?.Shake(perfect ? 0.45f : 0.3f);
            Game.Time?.HitStop(perfect ? 0.11f : 0.07f);
            if (perfect)
            {
                Game.Time?.SlowMotion(0.3f, 0.45f, 0.02f, 0.3f);
                Game.FX?.Screen?.ChromaticPunch(1f);
            }
            Game.Input?.Rumble(0.4f, 0.9f, perfect ? 0.2f : 0.12f);
            AddSpirit(perfect ? config.spiritOnPerfectParry : config.spiritOnParry);
            AddRage(perfect ? config.rageOnPerfectParry : config.rageOnParry);
            lastParryWhiff = -9f;
            GameEvents.RaiseParry(perfect);
        }

        void TickParrySuccess(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 40f * dt);
            if (input != null && stateTime > 0.06f)
            {
                // contraataque inmediato o nuevo parry
                if (input.Buffered(Act.Attack, 0.25f)) { input.Consume(Act.Attack); StartAttack(0); return; }
                if (input.Buffered(Act.Parry, 0.1f)) { input.Consume(Act.Parry); StartParry(); return; }
                if (input.Buffered(Act.Dash, 0.12f)) { input.Consume(Act.Dash); if (TryDash()) return; }
                if (input.Buffered(Act.Finisher, 0.12f) && TryFinisher()) { input.Consume(Act.Finisher); return; }
            }
            if (stateTime >= 0.38f) SetState(PlayerState.Locomotion);
        }

        // =============================================================== DASH MÁGICO
        Vector3 dashDir;
        bool perfectDodgeDone;

        bool TryDash()
        {
            if (!DashUnlocked) return false;
            if (State == PlayerState.Dash) return false;
            if (!SpendSpirit(config.dashCost)) return false;
            CancelAbilityCamera();
            trail?.Stop();
            Vector3 d = InputToWorld(MoveInput);
            if (d.sqrMagnitude < 0.01f)
                d = lockTarget != null ? -(lockTarget.transform.position - transform.position) : transform.forward;
            dashDir = d.Flat().normalized;
            FaceInstant(dashDir);
            SetState(PlayerState.Dash);
            perfectDodgeDone = false;
            anim.Play("Dash", 0.03f, 0f, 1.4f);
            Game.FX?.DashBurst(transform.position, dashDir);
            Game.FX?.AfterImages(model != null ? model : transform, 0.3f, 0.045f, RageActive);
            Game.Audio?.Play("dash", transform.position, 0.8f, 0.1f);
            Game.Camera?.Punch(2.5f, 0.2f);
            return true;
        }

        void TickDash(InputReader input, float dt)
        {
            float t = stateTime / config.dashDuration;
            if (t < 1f)
            {
                // curva rápida al principio, frena al final
                float speed = config.dashDistance / config.dashDuration * (1.6f - 1.2f * t);
                velocity = dashDir * speed;
            }
            else
            {
                velocity = Vector3.MoveTowards(velocity, Vector3.zero, 80f * dt);
                if (input != null)
                {
                    if (input.Buffered(Act.Attack, 0.25f)) { input.Consume(Act.Attack); StartAttack(0); return; }
                    if (input.Buffered(Act.Parry, 0.12f)) { input.Consume(Act.Parry); StartParry(); return; }
                }
                if (stateTime >= config.dashDuration + config.dashRecover)
                {
                    SetState(PlayerState.Locomotion);
                    anim.Play("Locomotion", 0.12f);
                }
            }
        }

        void OnDodged(in DamageInfo info)
        {
            Game.FX?.DodgeSpark(AimPoint);
            if (perfectDodgeDone) return;
            if (stateTime <= config.perfectDodgeWindow + config.dashIFrameStart || info.kind == AttackKind.Unblockable)
            {
                perfectDodgeDone = true;
                // "Instante Sombra": el mundo se ralentiza, recuperás espíritu
                Game.Time?.SlowMotion(0.25f, 1.0f, 0.03f, 0.4f);
                Game.FX?.Screen?.ShadowInstant();
                Game.Audio?.Play("perfect_dodge", transform.position, 0.9f);
                Game.UI?.ShowToast("Instante sombra", new Color(0.6f, 0.85f, 1f));
                AddSpirit(config.dashCost);
                AddRage(10f);
                Game.Input?.Rumble(0.2f, 0.5f, 0.15f);
            }
        }

        // =============================================================== FINISHER
        Enemy finisherTarget;
        bool finisherStruck;
        int finisherShot = -1;
        int finisherSlowMo = -1;

        public Enemy FinisherCandidate()
        {
            if (!HasKatana) return null;
            Enemy best = null; float bestD = float.MaxValue;
            if (lockTarget != null && lockTarget.CanBeFinished(config.finisherHealthThreshold) &&
                CombatMath.FlatDistance(lockTarget.transform.position, transform.position) <= config.finisherRange + 1f)
                return lockTarget;
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return null;
            for (int i = 0; i < list.Count; i++)
            {
                var e = list[i];
                if (e == null || !e.IsAlive || !e.CanBeFinished(config.finisherHealthThreshold)) continue;
                float d = CombatMath.FlatDistance(e.transform.position, transform.position);
                if (d < config.finisherRange && d < bestD) { bestD = d; best = e; }
            }
            return best;
        }

        bool TryFinisher()
        {
            var e = FinisherCandidate();
            if (e == null) return false;
            if (!SpendSpirit(config.finisherCost)) return false;
            finisherTarget = e;
            finisherStruck = false;
            CancelAbilityCamera();
            trail?.Stop();
            SetState(PlayerState.Finisher);
            velocity = Vector3.zero;
            FaceInstant(e.transform.position - transform.position);
            e.BeginExecution(this);
            anim.Play("Finisher", 0.05f, 0f, 1.7f);
            finisherSlowMo = Game.Time != null ? Game.Time.SlowMotion(0.45f, 1.6f, 0.05f, 0.3f) : -1;
            finisherShot = Game.Camera != null ? Game.Camera.PlayFinisherShot(transform, e.transform) : -1;
            Game.FX?.Screen?.Finisher(true);
            Game.Audio?.Play("finisher_start", transform.position, 0.9f);
            Game.UI?.HideInteractPrompt();
            return true;
        }

        void TickFinisher(float dt)
        {
            velocity = Vector3.zero;
            // la línea de tiempo asume el clip a 1.7 (Play de TryFinisher): la furia no lo acelera
            // (SetState pone su multiplicador y puede activarse en plena ejecución con la muerte)
            anim.SetSpeed(1f);
            float len = anim.Length("Finisher", 2.6f) / 1.7f;
            float n = stateTime / len;
            if (!finisherStruck && n >= 0.68f)
            {
                finisherStruck = true;
                var e = finisherTarget;
                if (e != null)
                {
                    // aparece detrás del enemigo de un tajo
                    Vector3 dir = (e.transform.position - transform.position).Flat().normalized;
                    if (dir.sqrMagnitude < 0.01f) dir = transform.forward;
                    Vector3 from = transform.position;
                    Vector3 behind = e.transform.position + dir * (e.Radius + 1.4f);
                    Game.FX?.AfterImages(model != null ? model : transform, 0.12f, 0.02f, true);
                    Teleport(behind, Quaternion.LookRotation(dir));
                    Game.FX?.SlashLine(from + Vector3.up, behind + Vector3.up);
                    Game.FX?.Execution(e.AimPoint, dir);
                    Game.Audio?.Play("finisher_hit", e.transform.position, 1f);
                    Game.Camera?.CancelShot(finisherShot);
                    Game.Camera?.Shake(0.8f);
                    Game.Camera?.Punch(-7f, 0.4f);
                    Game.Time?.CancelSlowMotion(finisherSlowMo);
                    Game.Time?.HitStop(0.16f);
                    Game.FX?.Screen?.WhiteFlash(0.8f);
                    Game.Input?.Rumble(1f, 1f, 0.35f);
                    e.Execute(this);
                    OnKilledEnemy(e, true);
                    GameEvents.RaiseEnemyFinished(e, true);
                }
                // la muerte pudo completar un encuentro y arrancar una cinemática: EnterScripted ya
                // limpió todo y Kaito no debe volver a Locomotion en medio de ella
                if (State != PlayerState.Finisher) return;
            }
            if (n >= 1f)
            {
                Game.FX?.Screen?.Finisher(false);
                Game.Camera?.CancelShot(finisherShot);
                finisherShot = -1;
                finisherSlowMo = -1;
                SetState(PlayerState.Locomotion);
                anim.Play("Locomotion", 0.2f);
                finisherTarget = null;
            }
        }

        // =============================================================== HABILIDADES
        int abilityIndex;
        bool abilityInvulnerable;
        int abilityShot = -1;
        Vector3 abilityStart, abilityEnd;
        bool abilityFired;
        readonly List<Enemy> abilityVictims = new List<Enemy>(8);
        int whirlTicks;

        bool TryAbility(int index)
        {
            float cost = index == 1 ? config.windSlashCost : config.whirlwindCost;
            if (!SpendSpirit(cost)) return false;
            trail?.Stop();
            abilityIndex = index;
            abilityFired = false;
            abilityVictims.Clear();
            whirlTicks = 0;
            SetState(PlayerState.Ability);
            velocity = Vector3.zero;
            GameEvents.RaiseAbility(index);
            Game.UI?.HideInteractPrompt();

            var t = AttackTarget(config.windSlashDistance + 2f);
            Vector3 dir = t != null ? t.transform.position - transform.position : InputToWorld(MoveInput);
            if (dir.sqrMagnitude < 0.01f) dir = transform.forward;
            FaceInstant(dir);

            if (index == 1)
            {
                // Corte del Viento: la cámara se pone detrás de Kaito, el tiempo se frena, y zas.
                abilityInvulnerable = true;
                anim.Play("Attack3", 0.05f, 0f, 0.5f);
                abilityShot = Game.Camera != null ? Game.Camera.PlayAbilityShot(transform, CameraDirector.AbilityShot.OverShoulder, 1.15f) : -1;
                Game.Time?.SlowMotion(0.2f, 0.55f, 0.05f, 0.15f);
                Game.FX?.AbilityCharge(transform.position, false);
                Game.Audio?.Play("ability_charge", transform.position, 0.9f);
                Game.FX?.Screen?.AbilityFocus(0.6f);
            }
            else
            {
                // Torbellino de hojas: giro con daño en área, cámara baja orbitando
                abilityInvulnerable = true;
                anim.Play("Attack3", 0.05f, 0f, 0.8f);
                abilityShot = Game.Camera != null ? Game.Camera.PlayAbilityShot(transform, CameraDirector.AbilityShot.LowOrbit, 1.1f) : -1;
                Game.Time?.SlowMotion(0.35f, 0.3f, 0.03f, 0.15f);
                Game.FX?.AbilityCharge(transform.position, true);
                Game.Audio?.Play("ability_whirl", transform.position, 0.9f);
                Game.FX?.Screen?.AbilityFocus(0.4f);
            }
            Game.Input?.Rumble(0.3f, 0.6f, 0.25f);
            return true;
        }

        void TickAbility(InputReader input, float dt)
        {
            if (abilityIndex == 1) TickWindSlash(dt);
            else TickWhirlwind(dt);
        }

        void TickWindSlash(float dt)
        {
            // fase 1 (0-0.32s escalados): preparación; fase 2: tajo-dash; fase 3: los cortes "llegan"
            const float prep = 0.32f, travel = 0.16f;
            if (stateTime < prep) { velocity = Vector3.zero; return; }
            if (!abilityFired)
            {
                abilityFired = true;
                abilityStart = transform.position;
                abilityEnd = abilityStart + transform.forward * config.windSlashDistance;
                // no atravesar paredes
                if (Physics.SphereCast(abilityStart + Vector3.up * 0.8f, 0.3f, transform.forward, out var hit, config.windSlashDistance, WorldMask, QueryTriggerInteraction.Ignore))
                    abilityEnd = abilityStart + transform.forward * Mathf.Max(0f, hit.distance - 0.4f);
                anim.Play("Dash", 0.02f, 0f, 1.6f);
                Game.FX?.AfterImages(model != null ? model : transform, travel + 0.05f, 0.02f, true);
                Game.Audio?.Play("ability_wind", transform.position, 1f);
                Game.Camera?.Punch(6f, 0.25f);
                CollectLineVictims(abilityStart, abilityEnd, 1.6f);
            }
            float t = (stateTime - prep) / travel;
            if (t <= 1f)
            {
                velocity = (abilityEnd - abilityStart).Flat() / travel;
                return;
            }
            velocity = Vector3.zero;
            if (stateTime > prep + travel + 0.06f && abilityVictims.Count > 0)
            {
                // los cortes aparecen después de pasar (iaido)
                Game.FX?.SlashLine(abilityStart + Vector3.up, abilityEnd + Vector3.up);
                foreach (var e in abilityVictims)
                {
                    // una muerte pudo arrancar una cinemática (EnterScripted ya cortó la habilidad)
                    if (State != PlayerState.Ability) break;
                    if (e != null && e.IsAlive)
                        ResolveHitOnEnemy(e, config.windSlashDamage, 2f, AttackKind.Ability, 1.8f, 0.12f, 0.5f, "Corte del Viento");
                }
                abilityVictims.Clear();
                Game.Time?.HitStop(0.08f);
                if (State != PlayerState.Ability) return;
                anim.Play("Attack3", 0.05f, 0.55f, 1f);
            }
            if (stateTime > prep + travel + 0.55f) EndAbility();
        }

        void CollectLineVictims(Vector3 a, Vector3 b, float radius)
        {
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return;
            for (int i = 0; i < list.Count; i++)
            {
                var e = list[i];
                if (e == null || !e.IsAlive) continue;
                Vector3 p = e.transform.position;
                Vector3 ab = (b - a).Flat();
                float t = ab.sqrMagnitude > 0.001f ? Mathf.Clamp01(Vector3.Dot((p - a).Flat(), ab) / ab.sqrMagnitude) : 0f;
                Vector3 closest = a + ab * t;
                if (CombatMath.FlatDistance(closest, p) <= radius + e.Radius) abilityVictims.Add(e);
            }
        }

        void TickWhirlwind(float dt)
        {
            const float spinStart = 0.12f, spinTime = 0.62f;
            velocity = Vector3.zero;
            if (stateTime >= spinStart && stateTime <= spinStart + spinTime)
            {
                float t = (stateTime - spinStart) / spinTime;
                if (model != null) model.localRotation = modelBaseRot * Quaternion.Euler(0f, 720f * EaseOut(t), 0f);
                if (!abilityFired) { abilityFired = true; Game.FX?.Whirlwind(transform.position, config.whirlwindRadius, spinTime); trail?.Begin(); }
                int tick = t < 0.45f ? 1 : 2;
                if (tick > whirlTicks)
                {
                    whirlTicks = tick;
                    WhirlHit();
                }
            }
            else if (stateTime > spinStart + spinTime)
            {
                if (model != null) model.localRotation = modelBaseRot;
                trail?.Stop();
                if (stateTime > spinStart + spinTime + 0.25f) EndAbility();
            }
        }

        void WhirlHit()
        {
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return;
            for (int i = 0; i < list.Count; i++)
            {
                if (State != PlayerState.Ability) return; // una muerte arrancó una cinemática
                var e = list[i];
                if (e == null || !e.IsAlive) continue;
                if (CombatMath.FlatDistance(e.transform.position, transform.position) <= config.whirlwindRadius + e.Radius)
                    ResolveHitOnEnemy(e, config.whirlwindDamage, 1f, AttackKind.Ability, 1.4f, 0.06f, 0.3f, "Torbellino");
            }
        }

        static float EaseOut(float t) => 1f - (1f - t) * (1f - t);

        void EndAbility()
        {
            abilityInvulnerable = false;
            if (model != null) model.localRotation = modelBaseRot;
            CancelAbilityCamera();
            Game.FX?.Screen?.AbilityFocus(0f);
            SetState(PlayerState.Locomotion);
            anim.Play("Locomotion", 0.2f);
        }

        void CancelAbilityCamera()
        {
            if (abilityShot >= 0) { Game.Camera?.CancelShot(abilityShot); abilityShot = -1; }
            abilityInvulnerable = false;
            if (model != null && State == PlayerState.Ability) model.localRotation = modelBaseRot;
        }

        /// <summary>
        /// Otro sistema le quita el control a Kaito en plena ejecución o habilidad (la muerte del
        /// último enemigo de un encuentro arranca una cinemática dentro de e.Execute(), un respawn...).
        /// TickFinisher / EndAbility ya no van a llegar a su final, así que acá se deshace lo que
        /// pidieron esos estados: pantalla desaturada/foco, planos de cámara, cámara lenta,
        /// invulnerabilidad y giro del modelo. Llamar ANTES de cambiar de estado.
        /// Devuelve el enemigo que quedó entregado ("Executed") si el tajo todavía no había llegado.
        /// </summary>
        Enemy AbortFinisherAndAbility()
        {
            Enemy pending = State == PlayerState.Finisher && !finisherStruck ? finisherTarget : null;
            if (finisherShot >= 0) { Game.Camera?.CancelShot(finisherShot); finisherShot = -1; }
            if (finisherSlowMo >= 0) { Game.Time?.CancelSlowMotion(finisherSlowMo); finisherSlowMo = -1; }
            finisherTarget = null;
            finisherStruck = true;
            CancelAbilityCamera();
            Game.FX?.Screen?.Finisher(false);
            Game.FX?.Screen?.AbilityFocus(0f);
            // abilityVictims NO se limpia acá: TickWindSlash puede estar recorriéndola (la muerte
            // que arrancó la cinemática ocurre dentro de ese foreach); TryAbility la limpia al empezar.
            return pending;
        }

        static int worldMask = -1;
        static int WorldMask
        {
            get
            {
                if (worldMask == -1) worldMask = LayerMask.GetMask("Default", "Water");
                return worldMask;
            }
        }
    }
}
