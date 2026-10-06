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
        bool swingConnected;          // el primer impacto de cada corte lleva hit-stop global
        Vector3 lungeVelocity, carry; // avance del corte e inercia de la carrera (se suman)
        float cutStartedAt = -1f;     // tiempo real en que la hoja empezó a cortar (-1 = todavía no)

        /// <param name="startNorm">desde dónde arranca el clip (y su línea de tiempo): el contraataque sale de la carga
        /// del Corte 1 (config.riposteStartNorm), que es la pose en que terminan los clips del desvío</param>
        void StartAttack(int index, float startNorm = 0f)
        {
            var defs = config.combo;
            if (defs == null || defs.Length == 0) return;
            Vector3 run = State == PlayerState.Locomotion ? velocity : Vector3.zero;
            comboIndex = Mathf.Clamp(index, 0, defs.Length - 1);
            currentAttack = defs[comboIndex];
            attackLen = anim.Length(currentAttack.state, 0.45f) / Mathf.Max(0.05f, currentAttack.speed);
            attackNorm = startNorm;
            lungeDone = 0f;
            hitThisSwing.Clear();
            swingSoundPlayed = false;
            swingConnected = false;
            cutStartedAt = -1f;
            SetState(PlayerState.Attack);

            attackTarget = AttackTarget(config.attackMagnetRange);
            Vector3 aim = attackTarget != null ? attackTarget.transform.position - transform.position : InputToWorld(MoveInput);
            if (aim.sqrMagnitude > 0.01f) FaceInstant(aim);
            // atacar corriendo ya no frena en seco: conserva parte de la carrera hacia donde corta
            carry = transform.forward * Mathf.Max(0f, Vector3.Dot(run, transform.forward)) * config.attackMomentum;
            lungeVelocity = Vector3.zero;
            velocity = carry;
            // el contraataque funde un poco más largo: puede salir desde el desvío (0.06 s), no solo desde la carga
            anim.Play(currentAttack.state, startNorm > 0f ? 0.08f : comboIndex == 0 ? 0.05f : 0.03f, startNorm);
            Game.UI?.HideInteractPrompt();
        }

        void TickAttack(InputReader input, float dt)
        {
            var a = currentAttack;
            float timing = a.Timing(attackNorm) * a.speed * (RageActive ? config.rageSpeedMul : 1f);
            anim.SetSpeed(timing);
            bool frozen = anim.Frozen;
            if (!frozen) attackNorm += dt * timing / Mathf.Max(0.05f, attackLen * a.speed);

            // seguir apuntando al objetivo durante la anticipación
            if (attackTarget != null && attackNorm < a.activeStart && attackTarget.IsAlive)
                FaceTowards(attackTarget.transform.position - transform.position, 25f, dt);

            // avance (lunge) con imán: se frena antes de atravesar al enemigo
            float room = attackTarget != null && attackTarget.IsAlive
                ? CombatMath.FlatDistance(attackTarget.transform.position, transform.position) - attackTarget.Radius - Radius - 0.35f
                : float.MaxValue;
            if (!frozen && attackNorm >= a.lungeStart && attackNorm <= a.lungeEnd && lungeDone < a.lunge)
            {
                float span = Mathf.Max(0.01f, (a.lungeEnd - a.lungeStart) * attackLen);
                float step = Mathf.Min(a.lunge / span * dt, Mathf.Min(a.lunge - lungeDone, Mathf.Max(0f, room)));
                lungeDone += step;
                lungeVelocity = transform.forward * (step / dt);
            }
            else lungeVelocity = Vector3.MoveTowards(lungeVelocity, Vector3.zero, 60f * dt);
            carry = room > 0.1f ? CombatMath.Damp(carry, Vector3.zero, 7f, dt) : Vector3.zero;
            // durante el hit-stop del impacto, quieto (antes seguía deslizándose congelado como una estatua)
            velocity = frozen ? Vector3.zero : lungeVelocity + carry;

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
                // parry y dash en cualquier momento del corte salvo mientras la hoja está cortando: los avisos arrancan
                // 0.4-0.85 s antes del golpe y antes casi todo el corte quedaba bloqueado. Lo que se aprieta mientras
                // corta queda en el buffer y sale apenas termina el tramo activo
                float cutEnd = Mathf.Min(a.cancelWindow, a.activeEnd);
                bool cutting = attackNorm >= a.activeStart && attackNorm <= cutEnd;
                bool lateCancel = attackNorm > cutEnd;
                // el buffer se estira lo que duró el corte: con el hit-stop del impacto el tramo activo dura 0.2-0.35 s
                // reales y lo apretado al principio del corte vencía antes de que terminara
                if (cutting && cutStartedAt < 0f) cutStartedAt = Time.unscaledTime;
                float defenseWindow = config.defenseBuffer + (cutStartedAt >= 0f ? Time.unscaledTime - cutStartedAt : 0f);
                if (!cutting && input.Buffered(Act.Parry, defenseWindow)) { input.Consume(Act.Parry); StartParry(); return; }
                if (!cutting && input.Buffered(Act.Dash, defenseWindow)) { input.Consume(Act.Dash); if (TryDash()) return; }
                if (lateCancel && input.Buffered(Act.Finisher, 0.12f) && TryFinisher()) { input.Consume(Act.Finisher); return; }
                // combo
                if (attackNorm >= a.comboWindow && comboIndex < config.combo.Length - 1 && input.Buffered(Act.Attack, 0.3f))
                {
                    input.Consume(Act.Attack);
                    StartAttack(comboIndex + 1);
                    return;
                }
                // después del último corte se puede volver a empezar sin esperar el final del clip (antes se perdían
                // pulsaciones y el reinicio se sentía pegajoso)
                if (comboIndex == config.combo.Length - 1 && attackNorm >= config.comboRestart && input.Buffered(Act.Attack, 0.3f))
                {
                    input.Consume(Act.Attack);
                    StartAttack(0);
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
                riposte = riposte,
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
                    // el primer impacto de cada corte congela el mundo un instante (los siguientes del mismo corte
                    // solo congelan a los dos): antes los cortes livianos casi no se sentían
                    if (!swingConnected) { swingConnected = true; Game.Time?.HitStop(heavy ? 0.07f : 0.035f); }
                    Game.FX?.HitImpact(p, info.direction, heavy, RageActive);
                    Game.Audio?.Play(heavy ? "hit_heavy" : "hit", p, 0.85f, 0.12f);
                    Game.Camera?.Shake(shake * (kill ? 1.6f : 1f));
                    Game.Camera?.Impulse(info.direction, shake * 0.55f);
                    Game.Input?.Rumble(0.25f, 0.55f, 0.08f);
                    AddSpirit(config.spiritOnHit);
                    AddRage(config.rageOnHit);
                    if (riposte) riposteUntil = 0f;
                    if (kill) OnKilledEnemy(e, false);
                    break;
                }
                case HitResult.Blocked:
                    // rebotó en la guardia (o en un jefe que ruge): clang y un empujoncito, sin castigo. Es el aviso:
                    // el próximo golpe contra esa guardia se lo devuelve
                    Game.FX?.Clash(p, -info.direction, false);
                    Game.Audio?.Play("clang", p, 0.8f, 0.08f);
                    Game.Camera?.Shake(0.2f);
                    Game.Time?.HitStop(0.05f);
                    Game.Input?.Rumble(0.3f, 0.2f, 0.08f);
                    anim.Freeze(0.06f);
                    Push(-info.direction, 0.3f);
                    if (State == PlayerState.Attack && currentAttack != null) lungeDone = currentAttack.lunge;   // no sigue avanzando contra la guardia
                    break;
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

        float lastKillAt = -9f;

        void OnKilledEnemy(Enemy e, bool finisher)
        {
            Heal(finisher ? config.healOnFinisher : config.healOnKill);
            AddSpirit(config.spiritOnKill);
            AddRage(finisher ? 20f : 8f);
            if (!finisher)
            {
                // cámara lenta solo para cerrar la pelea o un doble kill: en cada muerte se perdía de vista el
                // golpe siguiente (y medio combate grupal pasaba en cámara lenta). Si no, un hit-stop seco
                if (LastOfFight(e) || Time.unscaledTime - lastKillAt < 1f) Game.Time?.SlowMotion(0.3f, 0.35f, 0.01f, 0.25f);
                else Game.Time?.HitStop(0.06f);
            }
            lastKillAt = Time.unscaledTime;
            Game.Camera?.Punch(-3f, 0.25f);
        }

        /// <summary>¿No queda nadie más vivo en esta pelea? (su encuentro; si no tiene, los enemigos en combate y el jefe)</summary>
        static bool LastOfFight(Enemy e)
        {
            if (e.encounter != null)
            {
                foreach (var m in e.encounter.Members) if (m != null && m != e && m.IsAlive) return false;
                return true;
            }
            var cd = Game.Combat;
            if (cd == null) return true;
            if (cd.ActiveBoss != null && cd.ActiveBoss != e && cd.ActiveBoss.IsAlive) return false;
            var list = cd.Engaged;
            for (int i = 0; i < list.Count; i++) if (list[i] != null && list[i] != e && list[i].IsAlive) return false;
            return true;
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
            if (stateTime > 0.28f && input != null && input.Buffered(Act.Parry, config.defenseBuffer)) { input.Consume(Act.Parry); StartParry(); return; }
            if (stateTime > 0.32f && input != null && input.Buffered(Act.Dash, config.defenseBuffer)) { input.Consume(Act.Dash); if (TryDash()) return; }
            if (stateTime >= 0.5f) SetState(PlayerState.Locomotion);
        }

        // =============================================================== PARRY
        float lastParryWhiff = -9f;
        bool parryLeft;
        float parryWindowMul = 1f;
        bool parryHadThreat;
        float CurrentParryWindow => config.parryWindow * parryWindowMul;
        // "venía algo" al apretar parry: un golpe a menos de 0.6 s de un enemigo a menos de 6 m (o una ola)
        const float SpamThreatEta = 0.6f, SpamThreatRange = 6f;

        void StartParry()
        {
            CancelAbilityCamera();
            trail?.Stop();
            // anti-spam: la ventana se achica solo si el parry anterior fue al aire SIN que viniera nada. Apretar
            // contra un golpe real (aunque sea temprano) es un intento legítimo: antes eso achicaba la ventana del
            // golpe siguiente del combo a 0.13 s
            parryWindowMul = Time.time - lastParryWhiff < config.spamDecay ? config.spamPenalty : 1f;
            parryHadThreat = ThreatNear();
            SetState(PlayerState.Parry);
            velocity = Vector3.zero;
            var t = lockTarget != null ? lockTarget : AttackTarget(5f);
            if (t != null) FaceInstant(t.transform.position - transform.position);
            anim.Play("ParryStance", 0.03f);
            Game.Audio?.Play("parry_ready", transform.position, 0.25f, 0.1f);
            // media luna de la ventana: dorada mientras es perfecta, se achica hasta cerrarse
            Game.FX?.Crescent?.Begin(transform, CurrentParryWindow, config.perfectWindow * parryWindowMul);
        }

        bool ThreatNear()
        {
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return false;
            for (int i = 0; i < list.Count; i++)
            {
                var e = list[i];
                if (e == null || !e.IsAlive) continue;
                if (e.ProjectileEta < SpamThreatEta) return true;
                if (e.StrikeEta < SpamThreatEta && CombatMath.FlatDistance(e.transform.position, transform.position) < SpamThreatRange) return true;
            }
            return false;
        }

        void TickParry(InputReader input, float dt)
        {
            velocity = Vector3.MoveTowards(velocity, Vector3.zero, 50f * dt);
            if (stateTime > CurrentParryWindow)
            {
                // al aire: la media luna se rompe en gris con un "fiu" (antes no pasaba nada y no se aprendía)
                parryClosedAt = Time.time;
                if (!parryHadThreat) lastParryWhiff = Time.time;
                Game.FX?.Crescent?.Whiff();
                Game.Audio?.Play("parry_whiff", transform.position, 0.5f, 0.08f);
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
            Game.FX?.Crescent?.Success();
            SetState(PlayerState.ParrySuccess);
            // el golpe siempre llega de frente (FaceInstant de abajo): los desvíos se alternan izquierda/derecha para
            // que una cadena de parrys no repita el mismo gesto, y el perfecto tiene su floreo; sin esos clips, el de siempre
            string parryClip = perfect ? "PerfectParry" : (parryLeft = !parryLeft) ? "ParrySuccessL" : "ParrySuccessR";
            anim.Play(anim.HasState(parryClip) ? parryClip : "ParrySuccess", 0.02f);
            riposteUntil = Time.time + config.riposteWindow;
            Vector3 dir = info.direction.sqrMagnitude > 0.01f ? info.direction.Flat().normalized : -transform.forward;
            FaceInstant(-dir);
            Push(dir, perfect ? 0.25f : 0.55f);
            var e = info.source as Enemy;
            // si le quiebra la postura, el enemigo pone la cámara lenta (la única del parry) y enciende la escena
            if (e != null) e.OnParried(perfect);

            // el parry ILUMINA la escena (luz, exposición, bloom, tinta dorada): ya no la apaga con cámara lenta gris
            Vector3 p = AimPoint + transform.forward * 0.55f;
            Game.FX?.ParryFlash(p, transform.forward, perfect);
            Game.Audio?.Play(perfect ? "parry_perfect" : "parry", p, 1f, 0.06f);
            // golpe de FOV chico: los anillos en pantalla no pueden saltar de tamaño justo cuando arranca el siguiente
            Game.Camera?.Punch(perfect ? -3f : -1.5f, perfect ? 0.35f : 0.22f);
            Game.Camera?.Shake(perfect ? 0.45f : 0.3f);
            if (perfect)
            {
                Game.Time?.HitStop(0.09f);
                Game.FX?.Screen?.ChromaticPunch(0.6f);
            }
            else
            {
                // el normal congela solo a los dos que chocan: un hit-stop global frenaba también al resto del grupo
                anim.Freeze(0.07f);
                if (e != null && CombatMath.FlatDistance(e.transform.position, transform.position) < 5f) e.Anim.Freeze(0.07f);
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
                if (input.Buffered(Act.Attack, 0.25f)) { input.Consume(Act.Attack); StartAttack(0, config.riposteStartNorm); return; }
                if (input.Buffered(Act.Parry, config.defenseBuffer)) { input.Consume(Act.Parry); StartParry(); return; }
                if (input.Buffered(Act.Dash, config.defenseBuffer)) { input.Consume(Act.Dash); if (TryDash()) return; }
                if (input.Buffered(Act.Finisher, 0.12f) && TryFinisher()) { input.Consume(Act.Finisher); return; }
            }
            if (stateTime >= 0.38f) SetState(PlayerState.Locomotion);
        }

        // =============================================================== DASH MÁGICO
        Vector3 dashDir;
        bool perfectDodgeDone;
        bool dashTired;
        float tiredDashReadyAt = -9f;

        /// <summary>Sin Espíritu para el dash normal: el próximo será el "cansado" (más corto, con espera).</summary>
        public bool DashTired => Spirit + 0.01f < config.dashCost;
        /// <summary>Segundos hasta que se pueda volver a hacer el dash cansado (0 = listo). Para el HUD.</summary>
        public float TiredDashReadyIn => Mathf.Max(0f, tiredDashReadyAt - Time.time);

        bool TryDash()
        {
            if (!DashUnlocked) return false;
            if (State == PlayerState.Dash) return false;
            // sin Espíritu igual se puede esquivar: los imparables no tienen otra respuesta y quien gastó bien el
            // Espíritu (remate, habilidades) quedaba indefenso. Mismos i-frames, más corto, con espera y sin premio
            bool tired = DashTired;
            if (tired)
            {
                if (Time.time < tiredDashReadyAt) { Game.UI?.DenySpirit(); Game.Audio?.Play("denied", null, 0.5f); return false; }
                tiredDashReadyAt = Time.time + config.tiredDashCooldown;
            }
            else Spirit -= config.dashCost;
            dashTired = tired;
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
            if (tired)
            {
                // estela gris y apagada: se lee que fue el dash de emergencia
                Game.FX?.AfterImages(model != null ? model : transform, 0.24f, 0.06f, new Color(0.55f, 0.57f, 0.62f, 0.3f));
                Game.Audio?.Play("dash", transform.position, 0.55f, 0.1f);
            }
            else
            {
                Game.FX?.AfterImages(model != null ? model : transform, 0.3f, 0.045f, RageActive);
                Game.Audio?.Play("dash", transform.position, 0.8f, 0.1f);
                Game.Camera?.Punch(2.5f, 0.2f);
            }
            return true;
        }

        void TickDash(InputReader input, float dt)
        {
            float t = stateTime / config.dashDuration;
            if (t < 1f)
            {
                // curva rápida al principio, frena al final (el cansado recorre menos en el mismo tiempo: mismos i-frames)
                float dist = dashTired ? config.tiredDashDistance : config.dashDistance;
                float speed = dist / config.dashDuration * (1.6f - 1.2f * t);
                velocity = dashDir * speed;
            }
            else
            {
                velocity = Vector3.MoveTowards(velocity, Vector3.zero, 80f * dt);
                if (input != null)
                {
                    if (input.Buffered(Act.Attack, 0.25f)) { input.Consume(Act.Attack); StartAttack(0); return; }
                    if (input.Buffered(Act.Parry, config.defenseBuffer)) { input.Consume(Act.Parry); StartParry(); return; }
                }
                if (stateTime >= config.dashDuration + config.dashRecover)
                {
                    SetState(PlayerState.Locomotion);
                    anim.Play("Locomotion", 0.12f);
                }
            }
        }

        float lastShadowAt = -99f;
        const float ShadowCooldown = 6f;

        void OnDodged(in DamageInfo info)
        {
            Game.FX?.DodgeSpark(AimPoint);
            // el dash cansado salva pero no premia (sin Instante Sombra, sin devolver Espíritu ni sumar furia)
            if (perfectDodgeDone || dashTired) return;
            bool perfect = stateTime <= config.perfectDodgeWindow + config.dashIFrameStart;
            if (!perfect && info.kind != AttackKind.Unblockable) return;
            // esquivar a tiempo (o un imparable) devuelve el Espíritu y suma furia
            perfectDodgeDone = true;
            Game.Audio?.Play("perfect_dodge", transform.position, 0.9f);
            AddSpirit(config.dashCost);
            AddRage(10f);
            Game.Input?.Rumble(0.2f, 0.5f, 0.15f);
            // "Instante Sombra" (el mundo se frena): solo la esquiva perfecta, corta y no más de una cada 6 s. Antes
            // cada imparable esquivado daba 1 s de cámara lenta gris: en un jefe era un 10-18 % de la pelea y el
            // anillo siguiente corría a otro ritmo del que se aprendió
            if (!perfect || Time.unscaledTime - lastShadowAt < ShadowCooldown) return;
            lastShadowAt = Time.unscaledTime;
            Game.Time?.SlowMotion(0.35f, 0.4f, 0.02f, 0.15f);
            Game.FX?.Screen?.ShadowInstant();
            Game.UI?.ShowCallout("Instante sombra", new Color(0.6f, 0.85f, 1f));
        }

        // =============================================================== FINISHER
        Enemy finisherTarget;
        bool finisherStruck;
        int finisherShot = -1;
        int finisherSlowMo = -1;
        // los comunes se rematan rápido (≤ 1 s, sin plano de cámara); la cinemática (~2.6 s) queda para élites,
        // sumos, jefes y el último de la pelea: antes cada ejecución era mirar una película
        bool finisherCinematic;
        float finisherSpeed = CinematicFinisherSpeed;
        // corto: clip x2.8 con cámara lenta 0.6 hasta el tajo → tajo a 0.75 s y control de vuelta a 1.0 s reales
        // (el cinemático: tajo a 1.85 s, fin a 2.5 s)
        const float CinematicFinisherSpeed = 1.7f, ShortFinisherSpeed = 2.8f;
        // ShortFinisherEnd = f72/80 del clip (kaitooo.fbx.json, Finisher 'short_end'): ya volvió a la guardia y el fundido
        // a Locomotion no arrastra los pies
        const float FinisherStrikeAt = 0.68f, ShortFinisherEnd = 0.9f;
        // después del remate: los que estaban cerca salen despedidos y esperan antes de atacar; Kaito queda
        // invulnerable un instante (el control volvía en medio del golpe de otro)
        const float FinisherRoomRadius = 4f, FinisherPush = 1.5f, FinisherAttackDelay = 0.8f, FinisherGrace = 0.6f;

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
            finisherCinematic = e is Boss || e.config.cinematicFinisher || LastOfFight(e);
            finisherSpeed = finisherCinematic ? CinematicFinisherSpeed : ShortFinisherSpeed;
            CancelAbilityCamera();
            trail?.Stop();
            SetState(PlayerState.Finisher);
            velocity = Vector3.zero;
            FaceInstant(e.transform.position - transform.position);
            e.BeginExecution(this);
            anim.Play("Finisher", 0.05f, 0f, finisherSpeed);
            if (finisherCinematic)
            {
                finisherSlowMo = Game.Time != null ? Game.Time.SlowMotion(0.45f, 1.6f, 0.05f, 0.3f) : -1;
                finisherShot = Game.Camera != null ? Game.Camera.PlayFinisherShot(transform, e.transform) : -1;
                Game.FX?.Screen?.Finisher(true);
            }
            else finisherSlowMo = Game.Time != null ? Game.Time.SlowMotion(0.6f, 0.35f, 0.03f, 0.15f) : -1;
            Game.Audio?.Play("finisher_start", transform.position, 0.9f);
            Game.UI?.HideInteractPrompt();
            return true;
        }

        void TickFinisher(float dt)
        {
            velocity = Vector3.zero;
            // la línea de tiempo asume el clip a finisherSpeed (Play de TryFinisher): la furia no lo acelera
            // (SetState pone su multiplicador y puede activarse en plena ejecución con la muerte)
            anim.SetSpeed(1f);
            float len = anim.Length("Finisher", 2.6f) / finisherSpeed;
            float n = stateTime / len;
            if (!finisherStruck && n >= FinisherStrikeAt)
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
                    Game.FX?.FinisherSlash(from + Vector3.up, behind + Vector3.up, RageActive);
                    Game.FX?.Execution(e.AimPoint, dir);
                    Game.Audio?.Play("finisher_hit", e.transform.position, 1f);
                    Game.Camera?.CancelShot(finisherShot);
                    Game.Camera?.Shake(finisherCinematic ? 0.8f : 0.6f);
                    Game.Camera?.Punch(finisherCinematic ? -7f : -3f, 0.4f);
                    Game.Time?.CancelSlowMotion(finisherSlowMo);
                    Game.Time?.HitStop(finisherCinematic ? 0.16f : 0.08f);
                    Game.FX?.Screen?.WhiteFlash(finisherCinematic ? 0.8f : 0.35f);
                    Game.Input?.Rumble(1f, 1f, 0.35f);
                    GiveRoomAround(transform.position);
                    e.Execute(this);
                    OnKilledEnemy(e, true);
                    GameEvents.RaiseEnemyFinished(e, true);
                }
                // la muerte pudo completar un encuentro y arrancar una cinemática: EnterScripted ya
                // limpió todo y Kaito no debe volver a Locomotion en medio de ella
                if (State != PlayerState.Finisher) return;
            }
            // el corto devuelve el control apenas termina el tajo (el resto del clip es la vuelta a la guardia)
            if (n >= (finisherCinematic ? 1f : ShortFinisherEnd))
            {
                Game.FX?.Screen?.Finisher(false);
                Game.Camera?.CancelShot(finisherShot);
                finisherShot = -1;
                finisherSlowMo = -1;
                invulnUntil = Mathf.Max(invulnUntil, Time.time + FinisherGrace);
                SetState(PlayerState.Locomotion);
                anim.Play("Locomotion", 0.2f);
                finisherTarget = null;
            }
        }

        /// <summary>El tajo del remate despide a los que están cerca y les da un respiro antes de volver a atacar.</summary>
        void GiveRoomAround(Vector3 c)
        {
            var list = Game.Combat != null ? Game.Combat.All : null;
            if (list == null) return;
            for (int i = 0; i < list.Count; i++)
            {
                var o = list[i];
                if (o != null && o.IsAlive && CombatMath.FlatDistance(o.transform.position, c) <= FinisherRoomRadius)
                    o.GiveRoom(c, FinisherPush, FinisherAttackDelay);
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
        bool abilityOwnClip;

        bool TryAbility(int index)
        {
            float cost = index == 1 ? config.windSlashCost : config.whirlwindCost;
            if (!SpendSpirit(cost)) return false;
            trail?.Stop();
            abilityIndex = index;
            abilityFired = false;
            abilityVictims.Clear();
            whirlTicks = 0;
            swingConnected = false;
            SetState(PlayerState.Ability);
            velocity = Vector3.zero;
            GameEvents.RaiseAbility(index);
            Game.UI?.HideInteractPrompt();

            var t = AttackTarget(config.windSlashDistance + 2f);
            Vector3 dir = t != null ? t.transform.position - transform.position : InputToWorld(MoveInput);
            if (dir.sqrMagnitude < 0.01f) dir = transform.forward;
            FaceInstant(dir);

            // clips propios (WindSlash / Whirlwind) autorados con los tiempos de TickWindSlash / TickWhirlwind; sin
            // ellos, el Corte final estirado como antes
            abilityOwnClip = anim.HasState(index == 1 ? "WindSlash" : "Whirlwind");
            if (index == 1)
            {
                // Corte del Viento: la cámara se pone detrás de Kaito, el tiempo se frena, y zas.
                abilityInvulnerable = true;
                if (abilityOwnClip) anim.Play("WindSlash", 0.05f);
                else anim.Play("Attack3", 0.05f, 0f, 0.5f);
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
                if (abilityOwnClip) anim.Play("Whirlwind", 0.05f);
                else anim.Play("Attack3", 0.05f, 0f, 0.8f);
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
            // el clip propio sigue el reloj de stateTime: la furia no lo acelera (SetState le pone su multiplicador)
            if (abilityOwnClip) anim.SetSpeed(1f);
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
                if (!abilityOwnClip) anim.Play("Dash", 0.02f, 0f, 1.6f);
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
                if (!abilityOwnClip) anim.Play("Attack3", 0.05f, 0.55f, 1f);
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
