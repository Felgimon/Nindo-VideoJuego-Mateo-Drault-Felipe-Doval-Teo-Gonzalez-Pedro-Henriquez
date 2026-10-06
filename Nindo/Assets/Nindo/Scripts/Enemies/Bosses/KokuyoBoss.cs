using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Kokuyō, Señor del Clan Kurokage (jefe final, bossId "kage": las banderas, la puerta y el final siguen igual).
    /// Un samurái de 4.5 m que se cortó la sombra para no tener lazos; la sombra no se lo perdonó y se mueve primero.
    ///  * Acto 1 "El Maestro" (100-65 %): su sombra en el piso actúa cada golpe 0.36 s antes que el cuerpo (el doble
    ///    de PlanarShadow muestreado más adelante en el mismo clip). Una sola cosa por vez: parry, dash, castigo.
    ///  * Acto 2 "La Sombra Suelta" (65-30 %): se la arranca (Kage, un segundo cazador que no se puede cortar) y el cuerpo
    ///    queda sin sombra. Nunca pegan los dos a menos de 0.9 s: el cuerpo coordina.
    ///  * Acto 3 "Eclipse" (30-10 %): cierra el puño sobre la luna. Sin luz no hay sombra: quedan el anillo, el destello
    ///    y el hyōshigi; cada parry devuelve la luz. La bandana de Kaito alumbra.
    ///  * Última resistencia (10 %): el Último Desfile termina de rodillas sí o sí y solo ahí se lo puede ejecutar.
    /// Los cambios de acto son escenas cortas e invulnerables (los golpes rebotan) que curan a Kaito: no hay esbirros.
    /// Los pisos de vida en cada umbral hacen que cada acto dure lo que tiene que durar.
    /// </summary>
    public class KokuyoBoss : Boss, ICameraProfile
    {
        /// <summary>Acto actual (1..3); la última resistencia es LastStand dentro del 3.</summary>
        public int Act { get; private set; } = 1;
        public bool LastStand { get; private set; }
        public bool Transitioning => transition != null;
        public KageArenaFX ArenaFX => fx;
        public override int CurrentPhase => Act - 1;

        // cámara para un gigante: un poco más alta y lejos que la de combate, y el foco corrido hacia él (UpdateFraming)
        public float CameraPitch => 54f;
        public float CameraExtraDistance => 2f;

        /// <summary>Vida (fracción) en la que termina cada acto: 1 → 65 %, 2 → 30 %, 3 → 10 % (la última resistencia).</summary>
        static readonly float[] Gates = { 1f, 0.65f, 0.30f, 0.10f };
        /// <summary>Postura con la que queda de rodillas al terminar un combo: en el Acto 1 alcanza un parry (enseña);
        /// después hacen falta dos (los puntos se acumulan entre combos).</summary>
        const float KneelThresholdFirst = 1f, KneelThreshold = 2f;
        /// <summary>De rodillas aguanta 8 golpes (no 4): la ventana entera de 3.6 s vale la pena.</summary>
        const int KneelHitCap = 8;
        const float TransitionHeal = 30f, TransitionSpirit = 30f;
        /// <summary>El cuerpo no arranca a pegar hasta esto después del golpe de la sombra (más su anticipación ≥ 0.6 s).</summary>
        const float ShadowGap = 0.35f;
        /// <summary>El Counter suelta recién esto después del impacto de la sombra: con su resto (≥ 0.05 s) y la
        /// anticipación del gyakugiri (≥ 0.7 s) el corte llega a más de 0.9 s del golpe de la sombra.</summary>
        const float CounterAfterShadow = 0.2f;
        /// <summary>Paso de Sombra: si el charco no llega (borde de la malla, un brasero en el camino) sale igual.</summary>
        const float SinkTimeout = 1.8f;
        /// <summary>De rodillas los golpes lo devuelven a este punto del Kneel como mucho: después del último
        /// respiro (0.69) y antes de que se pare (si no, cada golpe tardío lo volvía a bajar).</summary>
        const float KneelReplayMax = 0.72f;
        const float RageLightRange = 5f;

        KageArenaFX fx;
        KokuyoLook look;
        KokuyoHazards hazards;
        KageShadow kage;
        Coroutine transition;
        AttackPattern counterPattern, teachSweep, teachRift;
        AttackDef riftDef;
        float fightStart, kneelStart = -99f, tipHideAt = -1f;
        bool lastStandKneel;
        // reintentos: dos muertes en el Acto 1 → pista del abuelo; llegar al eclipse → se reintenta desde el 65 %
        int act1Deaths;
        bool hintPending, shadowTipShown;
        int retryAct = 1;
        // el arranque rápido del reintento espera al primer Update de la pelea: BeginFight levanta el evento ANTES de
        // ponerlo en Chase, y una escena empezada ahí adentro quedaba pisada (caminaba y pegaba siendo inmune)
        bool retryTearPending;

        // paso en curso
        KokuyoClip clip;
        float travelDone, emberAt;
        bool goFired, afterRecoil;
        string prevChainTo = "READY";
        // grieta del Rompecascos
        bool riftOn, riftHit;
        Vector3 riftOrigin, riftDir;
        float riftStart, riftShardAt;
        // Paso de Sombra
        bool sinking, sinkArrived;
        Vector3 emergeDir;
        float sinkStart, sinkArriveTime, sinkHoldClock = -1f;
        // un clavado de la sombra mientras está hundido: la postura se cobra cuando terminó de salir
        float pendingPosture;
        // de rodillas: reloj del clip que se detiene con el hit-stop (Time.time no)
        float kneelClock;
        // cuándo pega (o pegó) la sombra suelta: el Counter del cuerpo espera a eso
        float kageImpactAt = -99f;
        bool pulledOut;
        readonly List<Collider> colliders = new List<Collider>();
        // el parry lo empuja knock_m (0.6) con la curva de Enemy: lo que falta (o sobra) respecto de 0.4 / 0.8
        Vector3 knockExtra;
        // encuadre
        float framingBias;
        readonly List<Transform> bones = new List<Transform>(64);
        readonly List<Renderer> rigidParts = new List<Renderer>(16);
        int finisherShot = -1;
        // locomoción lateral (StrafeL/R no están en el blend tree)
        string strafeWanted = "Locomotion";
        float strafeWantedFor;
        Transform head;
        Light rageLight;

        // ================================================================== setup
        protected override void Start()
        {
            base.Start();
            if (Defeated) return;
            fx = GetComponentInParent<KageArenaFX>();
            if (fx != null) fx.AutoDirect = false;   // los beats del patio los marca esta pelea
            look = new KokuyoLook(model);
            hazards = KokuyoHazards.Create(transform.parent);
            riftDef = new AttackDef
            {
                name = "Grieta de obsidiana", damage = KokuyoMoves.RiftDamage, kind = AttackKind.Unblockable,
                knockback = KokuyoMoves.RiftKnockback, hitStop = 0f, imbalance = 0f,
            };
            foreach (var t in model.GetComponentsInChildren<Transform>(true))
            {
                bones.Add(t);
                if (t.name == "Head") head = t;
            }
            foreach (var r in model.GetComponentsInChildren<Renderer>(true)) if (r is MeshRenderer) rigidParts.Add(r);
            GetComponentsInChildren(true, colliders);
            counterPattern = KokuyoMoves.Counter(1);
            GameEvents.BossStarted += OnBossStarted;
            GameEvents.PlayerDied += OnPlayerDied;
            WaitKneeling();
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            GameEvents.BossStarted -= OnBossStarted;
            GameEvents.PlayerDied -= OnPlayerDied;
            if (rageLight != null) Destroy(rageLight.gameObject);
        }

        /// <summary>Espera arrodillado al pie de la escalera, la espada sobre los muslos (lo levanta la presentación).</summary>
        void WaitKneeling()
        {
            EnterScripted();
            anim.Play(KokuyoTimings.SeizaIdle.State, 0f);
        }

        void OnBossStarted(Boss b)
        {
            if (b != this) return;
            fightStart = Time.time;
            Act = 1;
            LastStand = false;
            counterPattern = KokuyoMoves.Counter(1);
            CacheTeaching();
            if (fx != null && fx.Shadow == null) fx.AttachShadow(this);
            if (hintPending) { hintPending = false; Bark("kokuyo_hint_suelo"); }
            // ya llegó al eclipse una vez: el reintento arranca con la sombra arrancada (no se repiten 2 minutos)
            if (retryAct >= 2)
            {
                Health = Mathf.Min(Health, Gates[1] * config.maxHealth);
                retryTearPending = true;
            }
        }

        void OnPlayerDied()
        {
            if (!Fighting) return;
            if (Act == 1 && ++act1Deaths == 2) hintPending = true;
            if (Act >= 3) retryAct = 2;
        }

        public override void ResetEnemy()
        {
            transition = null;
            base.ResetEnemy();   // config de fábrica (patrones del Acto 1, sin ejecución), vida, lugar
            if (look == null) return;
            Act = 1;
            LastStand = lastStandKneel = false;
            retryTearPending = false;
            pendingPosture = 0f;
            kageImpactAt = -99f;
            sinking = false;
            sinkHoldClock = -1f;
            knockExtra = Vector3.zero;
            prevChainTo = "READY";
            if (kage != null) { kage.Dismiss(); kage = null; }
            hazards.ClearAll();
            look.ResetAll();
            fx?.ResetArena();
            foreach (var c in colliders) if (c != null) c.enabled = true;
            if (finisherShot >= 0) { Game.Camera?.CancelShot(finisherShot); finisherShot = -1; }
            framingBias = 0f;
            Game.Camera?.SetFocusBias(Vector3.zero);
            if (rageLight != null) rageLight.enabled = false;
            if (tipHideAt > 0f) { Game.UI?.HideTutorial(); tipHideAt = -1f; }
            WaitKneeling();
        }

        // ================================================================== por frame
        protected override void Update()
        {
            if (look == null) { base.Update(); return; }
            if (retryTearPending && Fighting && IsAlive && State == EnemyState.Chase) { retryTearPending = false; StartTransition(2, true); }
            ApplyPendingPosture();
            TrackShadowImpact();
            BiasStrafe();
            base.Update();
            float dt = Time.deltaTime;
            if (State == EnemyState.Exhausted && !anim.Frozen) kneelClock += dt * anim.StateSpeed;
            if (knockExtra.sqrMagnitude > 1e-4f && !anim.Frozen)
            {
                Vector3 s = knockExtra * Mathf.Min(1f, dt * 10f);
                knockExtra -= s;
                MoveBy(s);
            }
            // el contraataque siempre es el gyakugiri (el Counter termina en LOW_L, de donde sale ese corte). Si la
            // sombra está por pegar, espera en la pose final del Counter: nunca dos golpes a menos de 0.9 s
            if (State == EnemyState.Counter)
            {
                if (pattern != counterPattern) pattern = counterPattern;
                if (kage != null && (kage.Busy || Time.time < kageImpactAt + CounterAfterShadow) && stateTime < 2.8f)
                    stateDuration = Mathf.Max(stateDuration, stateTime + 0.05f);
            }
            if (State != EnemyState.Attack)
            {
                if (sinking) EndSink();
                if (clip != null) { clip = null; look.SetEdge(KokuyoLook.Violet, 0f); hazards.Core(Vector3.zero, 0f); }
            }
            UpdateShadowLead();
            UpdateStrafeAnim(dt);
            UpdateExecution();
            look.Tick(Imbalance, State == EnemyState.Exhausted, dt);
            UpdateFraming(dt);
            UpdateRageLight(dt);
            if (Fighting && Act == 1) TeachUnblockables();
            if (tipHideAt > 0f && Time.unscaledTime > tipHideAt) { tipHideAt = -1f; Game.UI?.HideTutorial(); }
        }

        /// <summary>
        /// Ronda "guardando el dojo": si quedó lejos del lado del dojo (arriba en pantalla) gira hacia ese lado. Así casi
        /// siempre está arriba de Kaito: no lo tapa con su cuerpo y su sombra cae hacia la cámara, delante de él.
        /// </summary>
        void BiasStrafe()
        {
            if (State != EnemyState.Strafe || target == null) return;
            Vector3 home = (spawnPos - arenaCenter).Flat();
            if (home.sqrMagnitude < 0.01f) home = Vector3.forward;
            Vector3 toMe = (transform.position - target.transform.position).Flat();
            if (toMe.sqrMagnitude < 0.01f || Vector3.Angle(toMe, home) < 35f) return;
            Vector3 around = Vector3.Cross(Vector3.up, toMe.normalized);
            strafeDir = Vector3.Dot(around, home) >= 0f ? 1f : -1f;
            strafeSwitch = Time.time + 0.5f;
        }

        /// <summary>La postura de un clavado hecho con él bajo el piso se cobra cuando ya salió del charco: si no, se
        /// arrodillaba a mitad del viaje, pegado a Kaito (sin colliders) y con el charco dibujado.</summary>
        void ApplyPendingPosture()
        {
            if (pendingPosture <= 0f || sinking) return;
            var a = CurrentAttack;
            if (State == EnemyState.Attack && a != null && a.state == KokuyoTimings.ShadowEmerge.State
                && stepNorm < KokuyoTimings.ShadowEmerge.Event("ShadowErupt") + 0.08f) return;
            float p = pendingPosture;
            pendingPosture = 0f;
            if (IsAlive && transition == null) AddImbalance(p);
        }

        void TrackShadowImpact()
        {
            if (kage == null) return;
            float e = kage.StrikeEta;
            if (!float.IsInfinity(e)) kageImpactAt = Time.time + e;
        }

        void UpdateStrafeAnim(float dt)
        {
            string want = "Locomotion";
            if (State == EnemyState.Strafe && agent != null && agent.enabled)
            {
                Vector3 v = transform.InverseTransformDirection(agent.velocity);
                if (Mathf.Abs(v.x) > 0.6f && Mathf.Abs(v.x) > Mathf.Abs(v.z) * 1.2f) want = v.x > 0f ? KokuyoTimings.StrafeR.State : KokuyoTimings.StrafeL.State;
            }
            // un poco de histéresis: el agente corrige y el costado no titila
            if (want != strafeWanted) { strafeWanted = want; strafeWantedFor = 0f; }
            else strafeWantedFor += dt;
            if (strafeWantedFor > 0.15f || want == "Locomotion") config.animLocomotion = strafeWanted;
        }

        // ================================================================== golpes
        protected override void OnStepStarted(AttackDef a)
        {
            base.OnStepStarted(a);
            var c = KokuyoMoves.ClipOf(a);
            clip = c;
            travelDone = 0f;
            goFired = false;
            riftOn = riftHit = pulledOut = false;
            emberAt = 0f;
            if (c != null)
            {
                // fundido según de qué pose viene: los clips encadenan pose con pose (READY, LOW_L...); si no
                // coinciden, o viene de un parry, 0.08 s cruza la hoja por el cuerpo
                bool counter = step == 0 && pattern == counterPattern;
                string from = counter ? KokuyoTimings.Counter.ChainTo : prevChainTo;
                float fade = afterRecoil ? 0.18f : step == 0 && !counter ? 0.15f : from == c.ChainFrom ? 0.08f : 0.22f;
                if (fade > 0.08f) anim.Play(a.state, fade);
                prevChainTo = c.ChainTo;
            }
            afterRecoil = false;
            if (a.special == KokuyoMoves.Sink) BeginSink(); else if (sinking) EndSink();
            if (a.state == KokuyoTimings.ShadowEmerge.State)
            {
                // sale del charco: la tinta salta y el patio tiembla (el anillo dorado ya marca dónde)
                Game.FX?.Shockwave(transform.position, 2.6f, KokuyoLook.Violet);
                Game.FX?.Dust(transform.position, 1.2f);
                Game.Audio?.Play("teleport", transform.position, 0.9f);
            }
            hazards.Core(transform.position, a.special == KokuyoMoves.Sweep ? KokuyoMoves.SweepCore + 0.35f : 0f);
        }

        protected override void TickSpecial(AttackDef a, float dt)
        {
            if (clip == null) { base.TickSpecial(a, dt); return; }
            bool hits = a.damage > 0f;
            // apunta hasta el "¡ahora!" (o hasta la suelta): desde ahí el golpe va recto y correrse sirve
            if (hits && target != null && stepClock < tl.ReleaseTime && StrikeEta > KokuyoMoves.GoLead) Face(target.transform.position, 1.3f, dt);
            Travel();
            if (hits && !goFired && StrikeEta <= KokuyoMoves.GoLead) OnGo(a);
            TickEdge(a);
            switch (a.special)
            {
                case KokuyoMoves.Cut:
                case KokuyoMoves.Thrust:
                    HitArc(a, 0f);
                    break;
                case KokuyoMoves.Sweep:
                    if (stepNorm > a.activeEnd) hazards.Core(Vector3.zero, 0f);
                    else hazards.Core(transform.position, KokuyoMoves.SweepCore + 0.35f);
                    HitArc(a, KokuyoMoves.SweepCore);
                    break;
                case KokuyoMoves.Rift:
                    HitArc(a, 0f);
                    TickRift(a);
                    // arranca la hoja de la piedra: el polvo marca que se terminó el castigo gratis
                    if (!pulledOut && stepNorm >= KokuyoTimings.KabutoStuckEnd && katanaTip != null)
                    {
                        pulledOut = true;
                        Vector3 tip = katanaTip.position;
                        tip.y = transform.position.y;
                        Game.FX?.Dust(tip, 1.1f);
                        Game.FX?.GroundCrack(tip, 0.8f);
                    }
                    break;
                case KokuyoMoves.Sink:
                    TickSink();
                    break;
            }
            // el charco del que salió se borra cuando terminó de salir
            if (a.state == KokuyoTimings.ShadowEmerge.State)
                hazards.Puddle(transform.position, stepNorm < KokuyoTimings.ShadowEmerge.Event("ShadowErupt") + 0.06f ? 1.6f : 0f);
        }

        /// <summary>
        /// El cuerpo avanza lo que avanza el clip (travel_m), en el reloj del paso: los pies apoyados quedan clavados.
        /// Nunca lo atraviesa a Kaito (lo que no entra se pierde, no se recupera después).
        /// </summary>
        void Travel()
        {
            if (clip.Travel == null || anim.Frozen) return;
            float x = clip.TravelAt(stepNorm);
            float d = x - travelDone;
            travelDone = x;
            if (d <= 0f) return;
            // solo frena contra lo que tiene adelante: con Kaito al costado de la estocada la embestida sigue entera
            float room = d;
            if (target != null)
            {
                Vector3 to = (target.transform.position - transform.position).Flat();
                float along = Vector3.Dot(to, transform.forward), lat = Mathf.Abs(Vector3.Dot(to, transform.right));
                if (along > 0f && lat < Radius + target.Radius) room = along - Radius - target.Radius - 0.25f;
            }
            if (room > 0f) MoveBy(transform.forward * Mathf.Min(d, room));
        }

        void HitArc(AttackDef a, float core)
        {
            if (stepHit || target == null || stepNorm < a.activeStart || stepNorm > a.activeEnd) return;
            Vector3 tp = target.transform.position;
            if (Mathf.Abs(tp.y - transform.position.y) > 2.5f) return;
            // el alcance de la hoja desde donde está ahora (más el grosor del filo), no el número de diseño
            if (!CombatMath.InArc(transform, tp, clip.Reach + 0.3f, a.arc, target.Radius)) return;
            // Ichimonji: bajo la empuñadura la hoja pasa por arriba de la cabeza
            if (core > 0f && CombatMath.FlatDistance(tp, transform.position) - target.Radius <= core) return;
            stepHit = true;
            HitPlayer(a, transform.position);
        }

        /// <summary>El "¡ahora!" (0.36 s antes): filo, sombra (Acto 1) y bandana (Acto 3). El hyōshigi lo toca Enemy.</summary>
        void OnGo(AttackDef a)
        {
            goFired = true;
            bool danger = a.kind == AttackKind.Unblockable;
            look.GoFlash(danger);
            var sh = fx != null ? fx.Shadow : null;
            if (Act == 1 && sh != null && !sh.Detached) sh.Strike(0.12f);
            // en la oscuridad la cinta "ve por vos": destella con el aviso (el abuelo lo dice en la transición)
            if (Act >= 3 && Game.Player != null) Game.Player.GetComponent<BandanaGlow>()?.Pulse(Color.white, danger ? 0.5f : 0.8f);
        }

        void TickEdge(AttackDef a)
        {
            if (a.damage <= 0f) { look.SetEdge(KokuyoLook.Violet, 0f); return; }
            bool before = stepNorm <= a.activeEnd;
            if (a.kind == AttackKind.Unblockable)
            {
                // rojo desde que arranca: el arma ya dice "no se para" antes que el anillo
                look.SetEdge(KokuyoLook.Red, before ? 5f : 0f);
                if (before && Time.time >= emberAt && katanaTip != null) { emberAt = Time.time + 0.15f; Game.FX?.Embers(katanaTip.position); }
            }
            else look.SetEdge(KokuyoLook.GoldHot, stepNorm < a.activeStart ? 1.2f * Mathf.Clamp01(stepClock / Mathf.Max(0.05f, tl.T)) : 0f);
        }

        protected override float ComputeStrikeEta(AttackDef a)
        {
            if (a.special != KokuyoMoves.Rift) return base.ComputeStrikeEta(a);
            // Rompecascos: la hoja (si Kaito está a su alcance) o la grieta, que llega más tarde cuanto más lejos esté en
            // su carril. El aviso, el hyōshigi y el dash se miden contra lo que de verdad lo va a tocar: contra la hoja,
            // un dash al cierre del anillo terminaba sus i-frames antes de que la grieta llegara a 6 m
            if (stepHit || riftHit || target == null) return float.PositiveInfinity;
            Vector3 tp = target.transform.position;
            if (!riftOn)
            {
                float pre = Mathf.Max(0f, tl.T - stepClock);
                if (clip != null && CombatMath.InArc(transform, tp, clip.Reach + 0.3f, a.arc, target.Radius)) return pre;
                Vector3 fwd = transform.forward.Flat().normalized;
                Vector3 to = (tp - (transform.position + fwd * 1.2f)).Flat();
                float al = Vector3.Dot(to, fwd), lat = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, fwd)));
                bool inLane = lat <= KokuyoMoves.RiftHalfWidth + target.Radius && al <= KokuyoMoves.RiftLength;
                return inLane ? pre + Mathf.Max(0f, al) / KokuyoMoves.RiftSpeed : pre;
            }
            RiftCoords(tp, out float along, out float lateral);
            float front = (Time.time - riftStart) * KokuyoMoves.RiftSpeed;
            if (lateral > KokuyoMoves.RiftHalfWidth + target.Radius || along > KokuyoMoves.RiftLength || along < front - 1f) return float.PositiveInfinity;
            return Mathf.Max(0f, along - front) / KokuyoMoves.RiftSpeed;
        }

        protected override bool HitAreaFor(AttackDef a, out TellArea area)
        {
            switch (a.special)
            {
                case KokuyoMoves.Sweep:
                    area = new TellArea { origin = transform.position, size = (clip != null ? clip.Reach : 3.6f) + 0.3f };
                    return true;
                case KokuyoMoves.Rift:
                {
                    Vector3 fwd = transform.forward.Flat().normalized;
                    area = new TellArea
                    {
                        lane = true, origin = riftOn ? riftOrigin : transform.position + fwd * 1.2f, forward = riftOn ? riftDir : fwd,
                        size = KokuyoMoves.RiftLength, width = KokuyoMoves.RiftHalfWidth * 2f,
                    };
                    return true;
                }
            }
            return base.HitAreaFor(a, out area);
        }

        void RiftCoords(Vector3 p, out float along, out float lateral)
        {
            Vector3 to = (p - riftOrigin).Flat();
            along = Vector3.Dot(to, riftDir);
            lateral = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, riftDir)));
        }

        /// <summary>La hoja se clava y una grieta de agujas de obsidiana corre 14 m por el patio a 28 m/s.</summary>
        void TickRift(AttackDef a)
        {
            if (!riftOn && stepNorm >= a.activeStart)
            {
                riftOn = true;
                riftStart = Time.time;
                riftDir = transform.forward.Flat().normalized;
                riftOrigin = transform.position + riftDir * 1.2f;
                riftShardAt = 0f;
                Game.Camera?.Shake(0.6f);
                Game.Audio?.Play("slam", riftOrigin, 1f);
                Game.FX?.GroundCrack(riftOrigin, 2.5f);
                Game.Input?.Rumble(0.8f, 0.6f, 0.3f);
            }
            if (!riftOn) return;
            float front = Mathf.Min((Time.time - riftStart) * KokuyoMoves.RiftSpeed, KokuyoMoves.RiftLength);
            Vector3 side = Vector3.Cross(Vector3.up, riftDir);
            while (riftShardAt <= front)
            {
                int k = Mathf.RoundToInt(riftShardAt / 0.9f);
                Vector3 p = riftOrigin + riftDir * riftShardAt + side * ((k & 1) == 0 ? 0.35f : -0.35f);
                hazards.Shard(p, k % 3 == 0 ? 2 : 1, 1.0f);
                if ((k & 1) == 0) Game.FX?.Dust(p, 0.8f);
                riftShardAt += 0.9f;
            }
            if (riftHit || stepHit || target == null) return;
            RiftCoords(target.transform.position, out float along, out float lateral);
            if (lateral <= KokuyoMoves.RiftHalfWidth + target.Radius && along <= front && along >= front - 1.5f && along <= KokuyoMoves.RiftLength)
            {
                riftHit = true;
                HitPlayer(riftDef, riftOrigin + riftDir * Mathf.Max(0f, along - 1f));
            }
        }

        // ------------------------------------------------------------------ Paso de Sombra
        void BeginSink()
        {
            sinking = true;
            sinkArrived = false;
            sinkStart = Time.time;
            sinkHoldClock = -1f;
            emergeDir = PickEmergeDir();
            Game.Audio?.Play("teleport", transform.position, 0.8f);
        }

        /// <summary>
        /// Por dónde sale: al este, al oeste o al norte de Kaito (nunca del lado de la cámara: un gigante de 4.5 m
        /// entre la cámara y Kaito lo taparía) y siempre adentro del patio.
        /// </summary>
        Vector3 PickEmergeDir()
        {
            Vector3 right = Game.Camera != null ? Game.Camera.transform.right.Flat().normalized : Vector3.right;
            if (right.sqrMagnitude < 0.01f) right = Vector3.right;
            Vector3 up = Vector3.Cross(right, Vector3.up);   // hacia arriba en pantalla
            Vector3 kp = target != null ? target.transform.position : transform.position;
            int first = Random.Range(0, 3);
            for (int i = 0; i < 3; i++)
            {
                int k = (first + i) % 3;
                Vector3 d = k == 0 ? right : k == 1 ? -right : up;
                if (InArena(kp + d * 3f, 1.5f)) return d;
            }
            Vector3 toCenter = (arenaCenter - kp).Flat();
            return toCenter.sqrMagnitude > 0.01f ? toCenter.normalized : up;
        }

        void TickSink()
        {
            if (target == null) return;
            var c = KokuyoTimings.ShadowSink;
            if (stepNorm < c.Event("ShadowPuddle")) return;
            // ya bajo el piso: el charco viaja a 9 m/s hasta su lugar al costado de Kaito, hierve y recién ahí sale
            if (colliders.Count > 0 && colliders[0] != null && colliders[0].enabled) foreach (var col in colliders) if (col != null) col.enabled = false;
            if (!sinkArrived)
            {
                hazards.Boil(20f);
                // sobre la malla (escalera del dojo, el poste, los braseros): agent.Move no sale de ella y el charco
                // se quedaba frotando el borde, hundido e inmune. Y si igual no llega, sale donde esté
                Vector3 dest = ClampToArena(target.transform.position + emergeDir * 3f, 1.5f);
                if (UnityEngine.AI.NavMesh.SamplePosition(dest, out var hit, 1.5f, UnityEngine.AI.NavMesh.AllAreas)) dest = hit.position;
                Vector3 d = (dest - transform.position).Flat();
                float m = d.magnitude;
                if (m > 0.05f && !anim.Frozen) MoveBy(d / m * Mathf.Min(m, 9f * Time.deltaTime));
                if (m < 0.3f || Time.time - sinkStart > SinkTimeout)
                {
                    sinkArrived = true;
                    sinkArriveTime = Time.time;
                    hazards.Boil(60f);
                    Game.Audio?.Play("summon", transform.position, 0.7f);
                }
            }
            hazards.Puddle(transform.position, 1.6f);
            ScriptedFace(target.transform.position);
            // el paso espera hundido (fin del clip: 4 m bajo las losas) hasta llegar y hervir 0.45 s
            bool hold = !sinkArrived || Time.time - sinkArriveTime < 0.45f;
            if (stepNorm > 0.95f && hold)
            {
                if (sinkHoldClock < 0f) sinkHoldClock = stepClock;
                stepClock = sinkHoldClock;
                stepNorm = tl.NormAt(stepClock);
            }
        }

        void EndSink()
        {
            sinking = false;
            sinkHoldClock = -1f;
            foreach (var c in colliders) if (c != null) c.enabled = true;
            hazards.Puddle(Vector3.zero, 0f);   // la salida lo vuelve a dibujar donde corresponde
            // sin colliders pudo quedar encima de Kaito (salida por tiempo, o cortado): lo corre a un costado
            if (target != null)
            {
                Vector3 away = (transform.position - target.transform.position).Flat();
                float gap = Radius + target.Radius + 0.1f, m = away.magnitude;
                if (m < gap) MoveBy((m > 0.05f ? away / m : -transform.forward) * (gap - m));
            }
        }

        // ------------------------------------------------------------------ sombra adelantada (Acto 1)
        /// <summary>
        /// Durante cada paso el doble de la sombra muestrea el mismo clip 0.36 s más adelante en la línea de tiempo del
        /// paso (la misma pausa, la misma suelta): su golpe cae exacto en el "¡ahora!". El adelanto entra en 0.35 s
        /// (la sombra "arranca primero"); fuera del ataque vuelve a copiar la pose del cuerpo.
        /// </summary>
        void UpdateShadowLead()
        {
            var sh = fx != null ? fx.Shadow : null;
            if (sh == null || sh.Detached || Act != 1) return;
            var a = CurrentAttack;
            if (State == EnemyState.Attack && a != null && clip != null)
            {
                float k = Mathf.Clamp01(stepClock / 0.35f);
                float lead = KokuyoMoves.GoLead * k * k * (3f - 2f * k);
                sh.SampleAhead(a.state, Mathf.Min(tl.NormAt(stepClock + lead), 1f));
            }
            else if (sh.Lead) sh.Lead = false;
        }

        // ================================================================== recibir golpes
        public override HitResult ReceiveHit(in DamageInfo info)
        {
            bool fromKaito = info.sourceFaction == Faction.Player;
            if (fromKaito && IsAlive && look != null)
            {
                if (transition != null) { LastHitTime = Time.time; return HitResult.Blocked; }   // rebota (clang): está en escena
                if (sinking) return HitResult.Ignored;                                             // es un charco: no hay a quién
            }
            var i = info;
            bool early = false;
            if (fromKaito && i.kind == AttackKind.Ability && State == EnemyState.Attack)
            {
                // una habilidad ANTES del aviso le corta el golpe (+1 de postura); después solo hace daño
                var a = CurrentAttack;
                if (a != null && a.damage > 0f && StrikeEta > KokuyoMoves.GoLead) early = true;
                else i.kind = AttackKind.Heavy;
            }
            // piso de vida del acto: el que lo baja al umbral dispara la transición; lo que sobra no se cuenta
            if (fromKaito && i.damage > 0f && IsAlive)
            {
                float floor = Gates[LastStand ? 3 : Mathf.Clamp(Act, 1, 3)] * config.maxHealth;
                float mul = State == EnemyState.Exhausted ? config.exhaustedDamageMul : 1f;
                i.damage = Mathf.Min(i.damage, Mathf.Max(0f, Health - floor) / mul);
            }
            bool kneeling = State == EnemyState.Exhausted;
            var r = base.ReceiveHit(i);
            if (r == HitResult.Hit && fromKaito && look != null)
            {
                // de rodillas no hace la reacción de golpe parado (Flinch lo levantaba): sigue en el clip, con chispas
                if (kneeling && State == EnemyState.Exhausted)
                {
                    // vuelve al punto del clip que se ve (el reloj se frena con el hit-stop), nunca a la parte en
                    // que se para: los golpes tardíos lo dejaban subiendo y bajando
                    float n = Mathf.Min(kneelClock / KokuyoTimings.Kneel.Seconds, KneelReplayMax);
                    kneelClock = n * KokuyoTimings.Kneel.Seconds;
                    anim.Play(config.animExhausted, 0.05f, n);
                }
                if (early && State == EnemyState.Stagger)
                {
                    int before = Mathf.FloorToInt(Imbalance + 0.001f);
                    AddImbalance(1f);
                    look.FlareCrack(Mathf.Clamp(before, 0, 4), AimPoint);
                }
            }
            return r;
        }

        protected override int ExhaustedHitCap => LastStand ? int.MaxValue : KneelHitCap;

        protected override void OnDamaged(in DamageInfo info)
        {
            // sin la fase genérica de Boss: los umbrales son pisos y cada uno abre su escena
            if (transition != null || LastStand || !IsAlive) return;
            if (Health <= Gates[Act] * config.maxHealth + 0.5f) StartTransition(Act + 1, false);
        }

        public override void OnParried(bool perfect)
        {
            bool wasAttack = State == EnemyState.Attack;
            int before = Mathf.FloorToInt(Imbalance + 0.001f);
            base.OnParried(perfect);
            if (look == null) return;
            // knock_m del clip Parried para los dos parries (Enemy empuja 0.4 / 0.8): los pies no patinan
            if (wasAttack) knockExtra += -transform.forward * (KokuyoTimings.ParriedKnock - (perfect ? 0.8f : 0.4f));
            afterRecoil = true;
            int after = Mathf.FloorToInt(Imbalance + 0.001f);
            for (int k = before; k < after && k < 5; k++) look.FlareCrack(k, AimPoint);
            // el sonido más fuerte de la pelea que no es música: la recompensa
            Game.Audio?.Play("clang", AimPoint, 1f, 0.05f);
            Game.Camera?.Shake(perfect ? 0.35f : 0.25f);
            if (Act >= 3 && fx != null && Game.Player != null)
                fx.ParryLight(Game.Player.transform.position + Game.Player.transform.forward * 0.8f, perfect);
        }

        protected override void ComboEnd()
        {
            ReleaseToken();
            bool forced = pattern != null && pattern.exhaustAfter;
            if (forced) Imbalance = config.maxImbalance;
            pattern = null;
            nextAttackTime = Time.time + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
            float need = Act == 1 ? KneelThresholdFirst : KneelThreshold;
            if (forced || Imbalance >= need - 0.01f) BecomeExhausted();
            else EnterGuard();
        }

        protected override void BecomeExhausted()
        {
            base.BecomeExhausted();
            kneelStart = Time.time;
            kneelClock = 0f;
            if (look == null) return;
            look.FlareAll();
            Game.FX?.Dust(transform.position + transform.forward * 0.8f, 1.6f);
            // la primera vez de rodillas en el eclipse se le parte la hombrera
            if (Act >= 3) look.ShatterSode();
            if (LastStand)
            {
                // la ejecución: solo acá, y con Espíritu para pagarla
                lastStandKneel = true;
                config.finisherHealth = 1f;
                TopUpSpirit();
            }
        }

        protected override void OnExhaustionEnded()
        {
            // si se levanta antes de terminar el clip (8 golpes) arranca la hoja del piso en vez de saltar a la guardia
            if (Time.time - kneelStart < config.exhaustedTime - 0.3f) anim.Play(KokuyoTimings.KneelRise.State, 0.08f);
            if (lastStandKneel) { lastStandKneel = false; config.finisherHealth = 0f; }
        }

        // ================================================================== coordinación con la sombra (Acto 2)
        /// <summary>La sombra puede atacar: el cuerpo no tiene un golpe en camino, no está de rodillas ni en escena.</summary>
        public bool ShadowMayAttack()
        {
            if (!Fighting || !IsAlive || transition != null || Act != 2) return false;
            if (State != EnemyState.Chase && State != EnemyState.Strafe && State != EnemyState.Guard) return false;
            return Game.Combat == null || !Game.Combat.HasToken(this);
        }

        /// <summary>La sombra va a pegar en 'impactTime': el cuerpo no arranca antes de eso más el respiro.</summary>
        public void ReserveAfterShadow(float impactTime) => nextAttackTime = Mathf.Max(nextAttackTime, impactTime + ShadowGap);

        public void OnShadowPinned()
        {
            if (sinking) pendingPosture += 2f; else AddImbalance(2f);
            look?.FlareAll();
            Game.Camera?.Shake(0.3f);
        }

        public void OnShadowSlashed()
        {
            if (shadowTipShown) return;
            shadowTipShown = true;
            ShowTip(StoryText.Hint("kage_shadow"));
        }

        public bool InArena(Vector3 p, float margin) => CombatMath.FlatDistance(p, arenaCenter) <= arenaRadius - margin;

        public Vector3 ClampToArena(Vector3 p, float margin)
        {
            Vector3 off = (p - arenaCenter).Flat();
            float max = Mathf.Max(0f, arenaRadius - margin);
            if (off.magnitude > max) p = arenaCenter + off.normalized * max + Vector3.up * (p.y - arenaCenter.y);
            return p;
        }

        // ================================================================== transiciones
        void StartTransition(int next, bool quick)
        {
            if (transition != null) return;
            transition = StartCoroutine(TransitionRoutine(next, quick));
        }

        IEnumerator TransitionRoutine(int next, bool quick)
        {
            bool fromKneel = State == EnemyState.Exhausted;
            ReleaseToken();
            if (sinking) EndSink();
            SetState(EnemyState.Alert);   // mira a Kaito; los golpes rebotan; sigue fijable (no se pierde el fijado)
            stateDuration = 99f;
            Imbalance = 0f;
            lastStandKneel = false;
            config.finisherHealth = 0f;
            hazards.Core(Vector3.zero, 0f);
            if (!quick) Game.UI?.BossEnraged(this);
            if (fromKneel)
            {
                // de rodillas: primero arranca la hoja del piso (si no, el fundido la saca de la piedra en 0.15 s)
                anim.Play(KokuyoTimings.KneelRise.State, 0.08f);
                yield return new WaitForSeconds(KokuyoTimings.KneelRise.Seconds * 0.9f);
            }
            if (next == 2) yield return ShadowTear(quick);
            else if (next == 3) yield return Eclipse();
            else yield return LastStandRise();
            transition = null;
            if (!IsAlive) yield break;
            ReleaseToken();
            SetState(EnemyState.Chase);
            nextAttackTime = Time.time + 0.5f;
        }

        /// <summary>1 → 2: se agarra la sombra del piso y la arranca. Le salta la media luna izquierda.</summary>
        IEnumerator ShadowTear(bool quick)
        {
            var c = KokuyoTimings.ShadowTear;
            float snapN = c.Event("CrestSnap");
            float from = quick ? Mathf.Max(0f, snapN - 0.12f) : 0f;
            anim.Play(c.State, 0.15f, from);
            if (!quick) Bark("kokuyo_bark_tear");
            float snap = (snapN - from) * c.Seconds;
            yield return new WaitForSeconds(snap);
            Game.Audio?.Play("boss_roar", transform.position, 1f);
            look.SnapCrest(transform.position);
            fx?.ShadowTear(false);
            Game.FX?.SmokePuff(transform.position + Vector3.up, 2.2f);
            Game.Camera?.Punch(-3f, 0.4f);
            PushKaito(5f, 3f);
            // la tinta se despega del piso y se para (KageArenaFX la lleva 0.8 s): recién ahí caza
            yield return new WaitForSeconds(0.9f);
            if (fx != null && fx.Shadow != null) kage = KageShadow.Spawn(this, fx.Shadow, hazards);
            RewardKaito();
            yield return new WaitForSeconds(quick ? 0.2f : Mathf.Max(0.2f, 2.4f - snap - 0.9f));
            Act = 2;
            config.patterns = KokuyoMoves.Act(2);
            counterPattern = KokuyoMoves.Counter(2);
            // lo nuevo de este acto se dice una vez: la katana no la toca, las habilidades sí
            if (!shadowTipShown) { shadowTipShown = true; ShowTip(StoryText.Hint("kage_shadow")); }
        }

        /// <summary>2 → 3: la sombra vuelve a sus pies, clava la nodachi y cierra el puño sobre la luna.</summary>
        IEnumerator Eclipse()
        {
            var c = KokuyoTimings.Eclipse;
            kage?.Recall();
            anim.Play(c.State, 0.15f);
            Bark("kokuyo_bark_eclipse");
            float plant = c.Event("SwordPlant") * c.Seconds, fade = c.Event("MoonFade") * c.Seconds;
            yield return new WaitForSeconds(plant);
            Game.FX?.Shockwave(transform.position, 4.5f, KokuyoLook.Violet);
            Game.FX?.Dust(transform.position + transform.forward * 1.5f, 1.6f);
            Game.Camera?.Shake(0.4f);
            Game.Audio?.Play("slam", transform.position, 0.8f);
            yield return new WaitForSeconds(Mathf.Max(0f, fade - plant));
            if (kage != null) { kage.Dismiss(); kage = null; }
            Game.Audio?.StopMusic(0.4f);   // viento y silencio: lo que queda es el aviso
            fx?.Eclipse();
            look.SetEclipse(true);
            // un vistazo al cielo mientras no puede atacar (la cámara de juego nunca ve la luna)
            if (fx != null && fx.Moon != null) fx.Moon.PlaySkyShot(0.9f, 0.5f, 0.6f);
            RewardKaito();
            yield return new WaitForSeconds(1.6f);
            Game.Audio?.PlayMusic(musicKey, 0.3f);
            yield return new WaitForSeconds(Mathf.Max(0.2f, 3.0f - fade - 1.6f));
            Act = 3;
            config.patterns = KokuyoMoves.Act(3);
            counterPattern = KokuyoMoves.Counter(3);
        }

        /// <summary>10 %: se apoya en la espada, la arranca de la piedra y ruge. Después, el Último Desfile.</summary>
        IEnumerator LastStandRise()
        {
            var c = KokuyoTimings.LastStand;
            Bark("kokuyo_bark_last");
            anim.Play(c.State, 0.12f);
            TopUpSpirit();
            float roar = c.Event("Roar") * c.Seconds;
            yield return new WaitForSeconds(roar);
            Game.Audio?.Play("boss_roar", transform.position, 1f);
            Game.Camera?.Shake(0.7f);
            Game.FX?.Shockwave(transform.position, 6f, new Color(1f, 0.4f, 0.3f));
            PushKaito(5f, 3f);
            yield return new WaitForSeconds(Mathf.Max(0.1f, c.Seconds - roar));
            LastStand = true;
            config.patterns = new[] { KokuyoMoves.LastParade() };
        }

        void PushKaito(float radius, float meters)
        {
            var p = Game.Player;
            if (p != null && CombatMath.FlatDistance(p.transform.position, transform.position) < radius)
                p.Push(p.transform.position - transform.position, meters);
        }

        /// <summary>No hay esbirros que curen: cada cambio de acto le devuelve vida y Espíritu, con la bandana.</summary>
        void RewardKaito()
        {
            var p = Game.Player;
            if (p == null || !p.IsAlive) return;
            p.Heal(TransitionHeal);
            p.AddSpirit(TransitionSpirit);
            Game.FX?.HealBurst(p.transform.position);
            BandanaGlow.Ensure(p)?.Pulse(BandanaGlow.Gold, 1f);
        }

        void TopUpSpirit()
        {
            var p = Game.Player;
            if (p == null) return;
            if (p.Spirit < p.config.finisherCost) p.AddSpirit(p.config.finisherCost - p.Spirit + 0.5f);
            BandanaGlow.Ensure(p)?.Pulse(BandanaGlow.Gold, 1f);
        }

        // ================================================================== enseñar
        void CacheTeaching()
        {
            teachSweep = teachRift = null;
            foreach (var p in config.patterns)
            {
                if (p.steps[0].special == KokuyoMoves.Sweep) teachSweep = p;
                else if (p.steps[0].special == KokuyoMoves.Rift) teachRift = p;
            }
        }

        /// <summary>Los dos imparables salen sí o sí en los primeros ~45 s: a los 12 y 20 s pesan cuatro veces más.</summary>
        void TeachUnblockables()
        {
            float t = Time.time - fightStart;
            Boost(teachSweep, t > 12f, 1.0f);
            Boost(teachRift, t > 20f, 0.9f);
        }

        void Boost(AttackPattern p, bool due, float baseWeight)
        {
            if (p == null) return;
            bool used = p.lastUsed >= fightStart;
            p.weight = due && !used ? baseWeight * 4f : baseWeight;
        }

        void Bark(string id)
        {
            foreach (var l in StoryText.Dialogue(id))
                Game.UI?.ShowToast(l.speaker + ": " + l.text, l.speaker == StoryText.Abuelo ? new Color(0.66f, 0.76f, 1f) : new Color(1f, 0.46f, 0.4f), 3.4f);
        }

        void ShowTip(string text)
        {
            Game.UI?.ShowTutorial(text);
            tipHideAt = Time.unscaledTime + 5f;
        }

        // ================================================================== cámara
        /// <summary>
        /// Encuadre del gigante: corre el foco hacia adelante (o atrás) lo justo para que su cabeza y la punta de la
        /// nodachi queden bajo el 92 % de la pantalla sin que los pies de Kaito (ni los de él) bajen del 12 %. Con el
        /// fijado de siempre Kaito queda en el centro y medio cuadro de piso de abajo se desperdicia: así Kaito mide
        /// ~75 px (no 60 alejando la cámara 6 m) y casi nunca hace falta el auto-encuadre.
        /// </summary>
        void UpdateFraming(float dt)
        {
            var cd = Game.Camera;
            if (cd == null || cd.Cam == null) return;
            if (!Fighting || !IsAlive || target == null)
            {
                if (framingBias != 0f) { framingBias = 0f; cd.SetFocusBias(Vector3.zero); }
                return;
            }
            if (cd.InShot || dt <= 0f) return;
            var cam = cd.Cam;
            Vector3 bp = transform.position;
            float top = bp.y + 2f;
            for (int i = 0; i < bones.Count; i++) if (bones[i] != null) top = Mathf.Max(top, bones[i].position.y + 0.3f);
            for (int i = 0; i < rigidParts.Count; i++) { var r = rigidParts[i]; if (r != null && r.enabled) top = Mathf.Max(top, r.bounds.max.y); }
            Vector3 kp = target.transform.position;
            float vTop = Mathf.Max(View(cam, new Vector3(bp.x, top, bp.z)), View(cam, kp + Vector3.up * 1.6f));
            float vLow = Mathf.Min(View(cam, kp), View(cam, bp));
            float need = vTop - 0.92f, room = vLow - 0.12f;
            float s = need > 0f ? Mathf.Min(need, room) : room < 0f ? room : 0f;
            // 1 de pantalla ≈ 15 m de piso a 23 m y 54°: integra despacio (la cámara además amortigua el foco)
            if (Mathf.Abs(s) > 0.001f) framingBias += s * 15f * 1.5f * dt;
            else if (need < -0.05f && room > 0.05f) framingBias = Mathf.MoveTowards(framingBias, 0f, 0.4f * dt);
            framingBias = Mathf.Clamp(framingBias, -2f, 4f);
            Vector3 fwd = cd.transform.forward.Flat().normalized;
            cd.SetFocusBias(fwd * framingBias);
        }

        static float View(Camera cam, Vector3 p)
        {
            Vector3 v = cam.WorldToViewportPoint(p);
            return v.z > 0.1f ? v.y : 0.5f;
        }

        /// <summary>La ejecución: Enemy.BeginExecution lo tira al cuadro 0 de Kneel (de parado a la rodilla) y el plano del
        /// remate es para alguien de 1.7 m. Se lo deja de rodillas y un plano escalado a su altura toma el control.</summary>
        void UpdateExecution()
        {
            if (State != EnemyState.Executed || finisherShot >= 0 || Game.Camera == null || Game.Player == null) return;
            anim.Play(config.animExhausted, 0.12f, 0.35f);
            Transform k = Game.Player.transform, me = transform;
            Vector3 mid0 = (k.position + me.position) * 0.5f;
            Vector3 axis = (me.position - k.position).Flat().normalized;
            Vector3 side = Vector3.Cross(Vector3.up, axis);
            if (Vector3.Dot(side, (Game.Camera.transform.position - mid0).Flat()) < 0f) side = -side;
            const float s = 2.6f;   // altura del jefe / 1.7, con tope
            finisherShot = Game.Camera.PlayShot(t =>
            {
                float ang = Mathf.Lerp(-25f, 40f, Mathf.SmoothStep(0f, 1f, t / 1.8f));
                Vector3 dir = Quaternion.AngleAxis(ang, Vector3.up) * side;
                Vector3 mid = k != null && me != null ? (k.position + me.position) * 0.5f : mid0;
                Vector3 pos = mid + dir * 3.6f * s + Vector3.up * 1.15f * s;
                return new Pose(pos, Quaternion.LookRotation(mid + Vector3.up * 0.9f * s - pos));
            }, () => 36f, 0.15f, 6f, 0.35f);
        }

        void UpdateRageLight(float dt)
        {
            // en el eclipse el Filo de Ira prende la katana: la racha de Kaito alumbra la oscuridad
            var p = Game.Player;
            bool want = Act >= 3 && Fighting && IsAlive && p != null && p.RageActive;
            if (rageLight == null)
            {
                if (!want) return;
                var go = new GameObject("LuzDeIra");
                go.transform.SetParent(p.transform, false);
                go.transform.localPosition = new Vector3(0f, 1.4f, 0.3f);
                rageLight = go.AddComponent<Light>();
                rageLight.type = LightType.Point; rageLight.range = RageLightRange; rageLight.color = new Color(1f, 0.54f, 0.23f);
                rageLight.shadows = LightShadows.None; rageLight.intensity = 0f;
            }
            rageLight.intensity = Mathf.MoveTowards(rageLight.intensity, want ? 2.4f : 0f, dt * 6f);
            rageLight.enabled = rageLight.intensity > 0.01f;
        }

        // ================================================================== final
        public override void Execute(PlayerController by)
        {
            if (finisherShot >= 0) { Game.Camera?.CancelShot(finisherShot); finisherShot = -1; }
            // dos tajos dorados cruzados, la luz y la campana del templo
            Vector3 c = AimPoint;
            Vector3 right = Vector3.Cross(Vector3.up, (c - by.transform.position).Flat().normalized);
            Game.FX?.SlashLine(c - right * 2.4f + Vector3.up * 1.6f, c + right * 2.4f - Vector3.up * 1.2f);
            Game.FX?.SlashLine(c + right * 2.4f + Vector3.up * 1.6f, c - right * 2.4f - Vector3.up * 1.2f);
            Game.FX?.FlashLight(c, new Color(1f, 0.85f, 0.45f), 9f, 16f, 0.5f);
            base.Execute(by);
            StartCoroutine(BellWithTheMoon(c));
        }

        /// <summary>
        /// Tiempos reales del final desde el golpe (la cámara lenta de Boss.Die estira el Defeat de 3 s a ~4.5 s):
        /// suelta la espada a ~2.2 s y la máscara pega en las losas a ~3.4 s, con el plano de su muerte encima. Recién
        /// a los 3.6 s el plano sube al cielo (la luna vuelve a los 4.2 s), baja a los braseros encendiéndose y a los
        /// 6.6 s StoryDirector funde al final. Antes el cielo tapaba la espada y la máscara.
        /// </summary>
        public const float FinaleSkyAt = 3.6f, FinaleSeconds = 6.6f;

        /// <summary>La campana llega con la luna, ya fuera de la cámara lenta (en cámara lenta el audio baja de tono y
        /// una campana deslizándose de 0.55 a 1 suena a cinta gastada).</summary>
        IEnumerator BellWithTheMoon(Vector3 at)
        {
            yield return new WaitForSecondsRealtime(FinaleSkyAt + 0.6f);
            Game.Audio?.Play("temple_bell", at, 0.9f);
        }

        protected override void Die(in DamageInfo info, bool finisher = false)
        {
            if (State == EnemyState.Dead) return;
            if (sinking) EndSink();
            if (kage != null) { kage.Dismiss(); kage = null; }
            hazards?.ClearAll();
            look?.Extinguish();
            framingBias = 0f;
            Game.Camera?.SetFocusBias(Vector3.zero);
            if (rageLight != null) rageLight.enabled = false;
            base.Die(info, finisher);
            // el plano genérico de muerte (a 6 m, mirando a 1.5 m) es para alguien de 1.7 m: este, más lejos y más
            // alto, deja ver la espada clavándose y la máscara cayendo hasta las losas. Gana por ser el último
            if (Game.Camera != null)
            {
                Vector3 center = transform.position;
                Vector3 start = (Game.Camera.transform.position - center).Flat().normalized;
                if (start.sqrMagnitude < 0.01f) start = -transform.forward;
                Game.Camera.PlayShot(t =>
                {
                    Vector3 dir = Quaternion.Euler(0f, t * 12f, 0f) * start;
                    Vector3 pos = center + dir * Mathf.Lerp(11f, 8.5f, Mathf.Clamp01(t / FinaleSkyAt)) + Vector3.up * 3.6f;
                    return new Pose(pos, Quaternion.LookRotation(center + Vector3.up * 2f - pos));
                }, () => 34f, 0.4f, FinaleSkyAt + 0.2f, 1.0f);
            }
            // la luna vuelve después de la máscara; las cuerdas del abuelo se deshacen en el plano del final (StoryDirector)
            fx?.Finale(true, -1f, FinaleSkyAt);
        }

        /// <summary>No cae ni se hace humo: suelta la espada (queda clavada), se le cae la máscara y queda en seiza.</summary>
        protected override IEnumerator DeathRoutine(Vector3 dir)
        {
            yield return new WaitForSeconds(KokuyoTimings.Defeat.Seconds * 0.97f);
            if (State == EnemyState.Dead) anim.Play(KokuyoTimings.DefeatLoop.State, 0.35f);
        }

        // ================================================================== presentación y final (StoryDirector)
        public Transform Head => head != null ? head : transform;

        /// <summary>Se levanta (Intro): desde el seiza o, en un reintento, desde la mitad del gesto.</summary>
        public void PlayIntro(float fromNormalized) => anim.Play(KokuyoTimings.Intro.State, 0.2f, fromNormalized);

        /// <summary>Se le encienden los ojos (el final del Intro).</summary>
        public void EyesIgnite()
        {
            Vector3 p = Head.position + transform.forward * 0.4f;
            Game.FX?.FlashLight(p + transform.right * 0.12f, KokuyoLook.Violet, 3f, 4f, 0.5f);
            Game.FX?.FlashLight(p - transform.right * 0.12f, KokuyoLook.Violet, 3f, 4f, 0.5f);
            look?.FlareAll();
        }

        /// <summary>La luna rompe las nubes: la sombra viva aparece y se estira hasta los pies de Kaito (en 'reach').</summary>
        public void RevealShadow(float seconds, Vector3 reach)
        {
            if (fx == null) return;
            var sh = fx.AttachShadow(this);
            if (sh != null) StartCoroutine(SwingInShadow(sh, seconds, reach));
        }

        /// <summary>
        /// A largo 1 la sombra mide ~6.4 m (4.5 m de cuerpo con la luna a 35°): no llegaba a un Kaito a 15 m. Se estira
        /// hasta 0.6 m antes de sus pies (tope x2.5), aguanta así mientras habla el abuelo y vuelve a su largo real
        /// cuando arranca la pelea (el adelanto del Acto 1 se lee contra la sombra de verdad, no contra una estirada).
        /// </summary>
        IEnumerator SwingInShadow(PlanarShadow sh, float seconds, Vector3 reach)
        {
            sh.FadeTo(0f, 0f);
            sh.FadeTo(1f, seconds * 0.6f);
            // lo que hay que cubrir se mide a lo largo de la sombra (la luna puede no estar justo detrás de él)
            float unit = sh.Stretch > 0.01f ? sh.Length / sh.Stretch : 0f;
            Vector3 axis = (sh.ProjectToGround(transform.position + Vector3.up) - transform.position).Flat();
            float along = axis.sqrMagnitude > 1e-4f ? Vector3.Dot((reach - transform.position).Flat(), axis.normalized) : 0f;
            float full = unit > 0.1f ? Mathf.Clamp((along - 0.6f) / unit, 1f, 2.5f) : 1f;
            float t = 0f;
            while (t < seconds && sh != null)
            {
                t += Time.unscaledDeltaTime;
                float k = Mathf.Clamp01(t / seconds);
                sh.Stretch = Mathf.Lerp(0.15f, full, 1f - (1f - k) * (1f - k));
                yield return null;
            }
            while (sh != null && !Fighting && IsAlive) yield return null;
            // (si el reintento ya la arrancó, la Kage la maneja: vuelve a 1 de una)
            for (t = 0f; t < 0.8f && sh != null && !sh.Detached; t += Time.deltaTime)
            {
                sh.Stretch = Mathf.Lerp(full, 1f, Mathf.SmoothStep(0f, 1f, t / 0.8f));
                yield return null;
            }
            if (sh != null) sh.Stretch = 1f;
        }

        /// <summary>Vencido, arrodillado en 'pos' (el final lo pone frente al abuelo; espada y máscara van con él).</summary>
        public void KneelAt(Vector3 pos, Quaternion rot)
        {
            if (agent != null && agent.enabled && agent.isOnNavMesh) agent.Warp(pos); else transform.position = pos;
            transform.rotation = rot;
            anim.Play(KokuyoTimings.DefeatLoop.State, 0f);
        }

        /// <summary>La reverencia en seiza (Kaito le devuelve su media cinta).</summary>
        public void Bow() => anim.Play(KokuyoTimings.SeizaBow.State, 0.25f);

#if UNITY_EDITOR || DEVELOPMENT_BUILD
        /// <summary>Pruebas (AutoPilot "kokuyo act N"): salta al acto 2, 3 o a la última resistencia (4) en plena pelea.</summary>
        public void DebugJump(int act)
        {
            if (!Fighting || !IsAlive || transition != null) return;
            act = Mathf.Clamp(act, Act + 1, 4);
            if (act >= 3 && Act == 1)
            {
                look.SnapCrest(transform.position);
                fx?.ShadowTear(true);
                Act = 2;
            }
            if (act == 4 && Act == 2)
            {
                if (kage != null) { kage.Dismiss(); kage = null; }   // el salto se saltea el regreso a sus pies
                fx?.Eclipse();
                look.SetEclipse(true);
                Act = 3;
            }
            Health = Gates[act - 1] * config.maxHealth + 1f;
            StartTransition(act, false);
        }
#endif
    }
}
