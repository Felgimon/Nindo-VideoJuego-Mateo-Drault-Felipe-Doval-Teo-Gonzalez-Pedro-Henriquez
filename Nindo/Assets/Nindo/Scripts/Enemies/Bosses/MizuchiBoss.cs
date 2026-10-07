using System.Collections;
using UnityEngine;
using UnityEngine.AI;

namespace Nindo
{
    /// <summary>
    /// Mizuchi, el Gran Koi de la Cascada Kohan (diseño: judge_water "final"). Un koi espíritu de 7.5 m con el Sello del
    /// Agua clavado en el lomo, sobre la plataforma al pie de la cascada. Kaito no lo mata: lo libera.
    ///
    /// Sobre el Boss genérico agrega:
    ///  * su cuerpo (KoiBody): fase 1 blanca / fase 2 corrompida, nado que sigue el rumbo, la silueta de golpe larga
    ///    (HurtCenter) y la luz del sello;
    ///  * los especiales (MizuchiBoss.Moves.cs): perlas, peloteo, zambullida y salto, chorro y chorro barrido, la ola de la
    ///    cascada y los pilares. Ninguno empieza fuera de cuadro y todo lo rojo se puede esquivar corriendo a 6.2 m/s;
    ///  * la transición a la fase 2 (sube la cascada, el sello lo fulmina, vuelve corrompido y el agua inunda la
    ///    plataforma), la presentación (sale del pozo), la liberación del final (sube la cascada y se vuelve el dragón
    ///    dorado) y el reintento (todo vuelve a la fase 1);
    ///  * el encuadre de la pelea (ICameraProfile + el foco corrido hacia la cascada).
    /// </summary>
    public partial class MizuchiBoss : Boss, ICameraProfile
    {
        // ------------------------------------------------------------------ arena (lake_arena_platform: octógono de 10.6 m)
        /// <summary>Baranda: radio inscripto del octógono (9.8) menos los postes.</summary>
        public const float RailRadius = 9.6f;
        /// <summary>Hasta acá caen sus saltos: el cuerpo de 7.5 m no queda colgado de la baranda.</summary>
        public const float DeckRoom = 8.3f;
        /// <summary>Anillo de agua donde se zambulle y por donde sale: afuera de la baranda, adentro del cuadro.</summary>
        const float WaterRing = 11.6f;
        /// <summary>Clip 'Return': el hocico le pega a la perla en el cuadro 5 (0.167 s).</summary>
        public const float ReturnLead = 0.167f;
        /// <summary>El brillo del golpe (aleta, mandíbula, abanico) sale a esta distancia del contacto: entre el hyōshigi
        /// (0.38) y el cierre del anillo (0.10), sobre la parte del cuerpo que va a pegar.</summary>
        const float CueLead = 0.33f;
        const string GlowSlotP1 = "Mizuchi_Glow", GlowSlotP2 = "Mizuchi_Curse";

        KoiBody body;
        CharacterGlint glint;
        MizuchiMarks marks;
        KoiBeam beam;
        KoiGhost ghost;
        KoiWave waveFx;
        readonly KoiPillar[] pillarFx = new KoiPillar[4];
        BladeTrail trailJaw, trailFinL, trailFinR, trailTail;
        Material dragonMat;

        float baseArenaRadius, baseFinisherHealth;
        bool held, hidden, airborne, wideFrame, inCinematic;
        Coroutine move;
        int preGlintTell = -1;
        // varado: de dónde viene (salto o postura), cuándo pasa al loop echado y la postura que traía
        bool beachLanding, freeBeach;
        float beachLoopAt, savedImbalance;
        bool holdingCutscene, holdingLetterbox;
        bool lurking;
        float lurkAngle;

        protected override bool StepHeld => held;

        KohanFalls Falls => KohanFalls.Instance;
        /// <summary>Altura del piso de la plataforma.</summary>
        public float DeckHeight => Falls != null ? Falls.DeckY : arenaCenter.y;
        float WaterHeight => Falls != null ? Falls.WaterY : DeckHeight - 1f;
        Vector3 Center => new Vector3(arenaCenter.x, DeckHeight, arenaCenter.z);
        /// <summary>Hacia la cascada (norte: la cámara mira para ese lado y los controles no giran).</summary>
        Vector3 North
        {
            get
            {
                if (Falls != null) { var d = (Falls.PlungeCenter - arenaCenter).Flat(); if (d.sqrMagnitude > 1f) return d.normalized; }
                return Vector3.forward;
            }
        }
        Vector3 East => Vector3.Cross(Vector3.up, North);
        Vector3 Plunge { get { if (Falls != null) return Falls.PlungeCenter; var p = Center + North * 13f; p.y = WaterHeight; return p; } }
        Vector3 Lip => Falls != null ? Falls.LipCenter : Center + North * 16.5f + Vector3.up * 42f;
        /// <summary>Hocico (donde salen las perlas y el chorro).</summary>
        public Vector3 Snout => body != null ? body.Snout : transform.position + transform.forward * 2.9f + Vector3.up * 1.3f;

        // ================================================================== setup
        protected override void Start()
        {
            base.Start();
            if (!gameObject.activeSelf || Defeated) return;
            baseArenaRadius = arenaRadius;
            baseFinisherHealth = config.finisherHealth;
            // un jefe de 7.5 m siempre está en juego: con el recorte de huesos fuera de cámara su silueta de golpe se
            // congelaba cuando la cabeza salía del cuadro
            if (anim.Animator != null) anim.Animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            body = KoiBody.Attach(model, transform);
            glint = model.GetComponent<CharacterGlint>();
            marks = MizuchiMarks.Create();
            var fx = marks.transform;
            beam = KoiBeam.Create(fx);
            ghost = KoiGhost.Create(fx);
            waveFx = KoiWave.Create(fx);
            for (int i = 0; i < pillarFx.Length; i++) pillarFx[i] = KoiPillar.Create(fx);
            var mat = Game.Content != null ? Game.Content.trailMaterial : null;
            trailJaw = MakeTrail("jaw", body.JawTip, mat);
            trailFinL = MakeTrail("pec_L1", body.PecTipL, mat);
            trailFinR = MakeTrail("pec_R1", body.PecTipR, mat);
            trailTail = MakeTrail("fluke_L1", body.FlukeTip, mat);
            if (agent != null) agent.radius = 1.2f;
            if (!Seen) Lurk();
        }

        bool Seen => Game.Save != null && Game.Save.HasFlag(StoryDirector.BossSeenFlag(bossId));

        /// <summary>
        /// Antes de la presentación espera bajo el pozo de la cascada: la primera imagen de la arena (la grúa de la
        /// cascada de StoryDirector) es la plataforma vacía y una sombra larga que da vueltas en el hervor. Sale en
        /// Presentation. No se lo puede fijar ni pegar (guionado).
        /// </summary>
        void Lurk()
        {
            lurking = true;
            EnterScripted();
            SetHidden(true);
            SetAirborne(true);
            transform.position = Plunge;
        }

        void TickLurk()
        {
            var p = Game.Player;
            bool near = p != null && CombatMath.FlatDistance(p.transform.position, Plunge) < 45f;
            ghost.Show(near);
            if (!near) return;
            lurkAngle += Time.deltaTime * 0.45f;
            Vector3 tangent = new Vector3(-Mathf.Sin(lurkAngle), 0f, Mathf.Cos(lurkAngle));
            Vector3 pos = Plunge + new Vector3(Mathf.Cos(lurkAngle), 0f, Mathf.Sin(lurkAngle)) * 2.6f;
            transform.SetPositionAndRotation(pos, Quaternion.LookRotation(tangent));
            ghost.Swim(pos, tangent, WaterHeight);
        }

        BladeTrail MakeTrail(string baseBone, Transform tip, Material mat)
        {
            var b = KoiBody.Find(model, baseBone);
            return b != null && tip != null ? BladeTrail.Create(transform, b, tip, mat, TellStyle.TrailParry) : null;
        }

        // Unity llama solo al OnEnable/OnDisable del tipo más derivado: los de Enemy (privados) no corren para el koi, así
        // que acá se repite su alta y baja en el CombatDirector (si no, apagarlo y prenderlo vivo lo dejaba fuera de la lista)
        void OnEnable()
        {
            if (Game.Combat != null && Health > 0) Game.Combat.Register(this);
            GameEvents.BossStarted += OnBossStarted;
        }

        void OnDisable()
        {
            Game.Combat?.Unregister(this);
            GameEvents.BossStarted -= OnBossStarted;
            HoldCutscene(false);
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            if (marks != null) Destroy(marks.gameObject);
            if (dragonMat != null) Destroy(dragonMat);
        }

        void OnBossStarted(Boss b)
        {
            if (b != this) return;
            // los especiales grandes no abren la pelea: primero se aprende el ritmo de la mordida y las aletas
            StaggerCooldowns(0, 0.5f);
        }

        /// <summary>Los patrones de la fase 'minPhase' con espera larga arrancan con parte de su espera ya corrida.</summary>
        void StaggerCooldowns(int minPhase, float left)
        {
            if (config.patterns == null) return;
            foreach (var p in config.patterns)
                if (p != null && p.minPhase == minPhase && p.cooldown >= 8f) p.lastUsed = Time.time - p.cooldown * (1f - left);
        }

        // ================================================================== frame
        protected override void Update()
        {
            base.Update();
            if (body == null) return;
            if (lurking) { TickLurk(); return; }
            // un chorro cortado (golpe de habilidad, cambio de fase) no puede quedar disparando ni apuntando
            if (State != EnemyState.Attack)
            {
                beam.Stop();
                if (aimMark != null || jetLocked) ClearJetMarks();
            }
            DriveBody();
            if (State == EnemyState.Exhausted && beachLoopAt > 0f && Time.time >= beachLoopAt)
            {
                beachLoopAt = 0f;
                anim.Play("Exhausted", 0.25f);
            }
            UpdatePearls();
            PreGlintTick();
            if (Fighting && IsAlive && !inCinematic) UpdateFraming();
        }

        void DriveBody()
        {
            var s = State;
            bool swim = s == EnemyState.Chase || s == EnemyState.Strafe || s == EnemyState.Idle || s == EnemyState.Alert || s == EnemyState.Guard;
            bool look = swim && s != EnemyState.Idle && target != null;
            Vector3 at = target != null ? target.transform.position : transform.position + transform.forward;
            body.SetDrive(swim && !airborne && !hidden ? 1f : 0f, look ? 1f : 0f, at);
            body.SetRipple(!airborne && !hidden && s != EnemyState.Exhausted && Mathf.Abs(transform.position.y - DeckHeight) < 0.5f);
        }

        /// <summary>
        /// Con la cámara de combate el borde de arriba toca el agua ~12 m más allá del foco: corriendo el foco hacia la
        /// cascada (hasta 2.5 m) entran el pie de las cortinas y el rocío. El foco ya se corre solo hacia el koi (CameraDirector:
        /// 45 % hasta 6 m); entre los dos nunca más de 4.5 m al norte de Kaito o sus pies se van por abajo (simulado: con
        /// Kaito en la baranda sur y el koi al norte quedaban en el 1 % de abajo de la pantalla; así, en el 14 % o más).
        /// </summary>
        void UpdateFraming()
        {
            var cam = Game.Camera;
            if (cam == null || target == null) return;
            Vector3 toBoss = (transform.position - target.transform.position).Flat();
            float d = toBoss.magnitude;
            float lean = d > 0.01f ? Vector3.Dot(toBoss, North) * Mathf.Min(0.45f, 6f / d) : 0f;
            cam.SetFocusBias(North * Mathf.Clamp(4.5f - lean, 0f, 2.5f));
        }

        // ------------------------------------------------------------------ ICameraProfile
        /// <summary>44° en la fase 1, 42° corrompido (se ve más cortina); en las cinemáticas, la de combate.</summary>
        public float CameraPitch => inCinematic ? 0f : CurrentPhase == 0 ? 44f : 42f;
        /// <summary>El cuerpo entero y el anillo de agua donde sale: más lejos durante los saltos y la ola.</summary>
        public float CameraExtraDistance => (CurrentPhase == 0 ? 3.5f : 4.2f) + (wideFrame ? 1.5f : 0f);

        // ================================================================== golpes: brillo, estelas, silueta
        protected override void OnStepStarted(AttackDef a)
        {
            base.OnStepStarted(a);
            // un paso que quedó retenido (peloteo o tormenta cortados por un golpe de habilidad) no puede trabar el siguiente
            held = false;
            katanaTip = StrikePoint(a);
            trail = TrailFor(a);
            ResetStepState(a);
            switch (a.special)
            {
                case "dive": Run(DiveRoutine(a)); break;
                case "greatwave": Run(WaveRoutine(a)); break;
                case "pillars": Run(PillarRoutine(a)); break;
            }
            // BeginStep deja el clip quieto un frame; los pasos que maneja una rutina van a su ritmo
            if (held) anim.SetSpeed(1f);
        }

        Transform StrikePoint(AttackDef a)
        {
            if (body == null) return null;
            switch (a.state)
            {
                case "FinL": return body.PecTipL;
                case "FinR": return body.PecTipR;
                case "TailWhip": case "GreatWave": return body.FlukeTip;
                default: return body.JawTip;
            }
        }

        BladeTrail TrailFor(AttackDef a)
        {
            if (a.damage <= 0f || !string.IsNullOrEmpty(a.special)) return null;
            switch (a.state)
            {
                case "FinL": return trailFinL;
                case "FinR": return trailFinR;
                case "TailWhip": return trailTail;
                case "Bite": return trailJaw;
                default: return null;
            }
        }

        void PreGlintTick()
        {
            if (State != EnemyState.Attack || !InTell || TellId == preGlintTell) return;
            var a = CurrentAttack;
            if (a == null || ComputeStrikeEta(a) > CueLead) return;
            preGlintTell = TellId;
            PreGlint(katanaTip != null ? katanaTip.position : AimPoint, StepKind == AttackKind.Unblockable);
        }

        /// <summary>
        /// El "¡ya!" visual del koi: la parte que va a pegar se enciende (luz dorada = desviá, roja = salí) y los filos de
        /// las aletas y las escamas gin-rin destellan del mismo color. Con la cámara a 26 m el destello chico del arma de
        /// los ninjas no se veía en un cuerpo blanco de 7 m.
        /// </summary>
        void PreGlint(Vector3 at, bool danger)
        {
            Color c = danger ? TellStyle.Crimson : TellStyle.Gold;
            Game.FX?.FlashLight(at + Vector3.up * 0.4f, c, 7f, 5f, 0.3f);
            if (glint != null)
            {
                Color hdr = c * 3f; hdr.a = 1f;
                glint.Pulse(GlowSlotP1, hdr, CueLead);
                glint.Pulse(GlowSlotP2, hdr, CueLead);
            }
        }

        /// <summary>Punto de la silueta del koi más cercano a 'from', corrido para que Radius dé el grosor real ahí.</summary>
        public override Vector3 HurtCenter(Vector3 from)
        {
            if (body == null || hidden) return transform.position;
            Vector3 c = body.Closest(from, out float r);
            Vector3 u = (from - c).Flat();
            u = u.sqrMagnitude > 1e-4f ? u.normalized : transform.forward;
            c.y = transform.position.y;
            return c - u * Mathf.Max(0f, Radius - r);
        }

        public override HitResult ReceiveHit(in DamageInfo info)
        {
            if (info.sourceFaction == Faction.Player)
            {
                // bajo el agua o en una cinemática no se le puede pegar (la katana no llega y no es justo para él)
                if (hidden || inCinematic) return HitResult.Ignored;
                // en el aire o asomado detrás de la baranda (la ola) se lo ve: el tajo rebota con clang, como en el
                // rugido, en vez de atravesarlo en silencio (eso se leía como un error)
                if (airborne) { LastHitTime = Time.time; return HitResult.Blocked; }
            }
            var r = base.ReceiveHit(info);
            if (State == EnemyState.Exhausted && r == HitResult.Hit)
            {
                // varado, cada golpe es un coletazo contra las tablas (el "Hit" genérico es un sacudón en el aire)
                anim.Play("Exhausted", 0.12f);
                beachLoopAt = 0f;
                if (Game.Player != null) WaterSplash.Flop(HurtCenter(Game.Player.transform.position), 0.5f);
            }
            return r;
        }

        // ================================================================== varado / agotado
        /// <summary>Queda varado 'seconds' (después de un salto): ventana de castigo sin gastar la postura que traía.</summary>
        void Beach(float seconds, bool fromLanding)
        {
            savedImbalance = Imbalance;
            freeBeach = true;
            beachLanding = fromLanding;
            pattern = null;
            BecomeExhausted();
            if (State != EnemyState.Exhausted) { freeBeach = false; return; }
            stateDuration = seconds;
            nextAttackTime = Time.time + seconds + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
        }

        /// <summary>
        /// La regla común ("combo con un parry encima = agotado") varaba al koi con cada parry: la pelea se volvía
        /// parry + 3.4 s de castigo y la barra de postura no significaba nada. Acá solo se vara con la postura llena
        /// (4 pips: parry 1, perfecto 1.5, perla devuelta 1; el fallo del peloteo la llena entera) o si el patrón lo pide.
        /// </summary>
        protected override void ComboEnd()
        {
            if ((pattern == null || !pattern.exhaustAfter) && Imbalance < config.maxImbalance - 0.01f)
            {
                ReleaseToken();
                pattern = null;
                nextAttackTime = Time.time + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
                EnterGuard();
                return;
            }
            base.ComboEnd();
        }

        protected override void BecomeExhausted()
        {
            if (inCinematic) return;
            base.BecomeExhausted();
            config.animHit = "Exhausted";
            // de flotar a echado: cae de costado (BreachLand 3-12) y recién después el loop de varado
            anim.Play("BreachLand", 0.15f, beachLanding ? 0f : 0.06f);
            beachLoopAt = Time.time + (beachLanding ? 40f : 38f) / 30f;
            if (!beachLanding) WaterSplash.Beached(transform.position, transform.forward, 0.9f);
            beachLanding = false;
        }

        protected override void OnExhaustionEnded()
        {
            config.animHit = "Hit";
            beachLoopAt = 0f;
            if (freeBeach) { Imbalance = savedImbalance; freeBeach = false; }
            base.OnExhaustionEnded();
            // se endereza (los últimos cuadros de BreachLand) en vez de saltar de echado a la guardia
            if (State == EnemyState.Guard)
            {
                anim.Play("BreachLand", 0.2f, 40f / 54f);
                stateDuration = Mathf.Max(stateDuration, 0.55f);
            }
        }

        // ================================================================== reintento / cancelar
        public override void ResetEnemy()
        {
            CancelMoves();
            HoldCutscene(false);
            inCinematic = false;
            beachLoopAt = 0f; freeBeach = false;
            lurking = false;
            base.ResetEnemy();
            if (body != null) { body.SetPhase(0); body.SetHidden(false); }
            baseFinisherHealth = config.finisherHealth;
            Game.Camera?.SetFocusBias(Vector3.zero);
            // Kaito murió en otro lado antes de conocerlo: vuelve a esperar en el pozo
            if (body != null && !Seen) Lurk();
        }

        /// <summary>Corta cualquier especial en curso y deja al koi sano y salvo sobre la plataforma.</summary>
        void CancelMoves()
        {
            if (move != null) { StopCoroutine(move); move = null; }
            held = false;
            wideFrame = false;
            marks?.Clear();
            WaterPearl.ClearAll(this);
            rallyPearl = null;
            if (beam != null) beam.Stop();
            ghost?.Show(false);
            waveFx?.Hide();
            foreach (var p in pillarFx) p?.Hide();
            ClearPlans();
            SetHidden(false);
            SetAirborne(false);
            if (baseArenaRadius > 0f) arenaRadius = baseArenaRadius;
            RestoreAgent(transform.position);
        }

        void Run(IEnumerator routine)
        {
            if (move != null) StopCoroutine(move);
            move = StartCoroutine(routine);
        }

        void SetHidden(bool h)
        {
            hidden = h;
            body?.SetHidden(h);
            ApplyFinisherGate();
        }

        /// <summary>En el aire: sin colisión (no empuja a Kaito por arriba), sin agente y sin remate.</summary>
        void SetAirborne(bool on)
        {
            airborne = on;
            foreach (var c in GetComponentsInChildren<Collider>()) c.enabled = !on && IsAlive;
            if (on && agent != null && agent.enabled) agent.enabled = false;
            ApplyFinisherGate();
        }

        // el remate no puede agarrarlo en pleno salto ni bajo el agua (lo dejaría flotando en Executed)
        void ApplyFinisherGate()
        {
            if (baseFinisherHealth <= 0f) return;
            config.finisherHealth = hidden || airborne ? -1f : baseFinisherHealth;
        }

        void RestoreAgent(Vector3 near)
        {
            if (agent == null) return;
            if (!agent.enabled) agent.enabled = true;
            if (NavMesh.SamplePosition(near, out var hit, 4f, NavMesh.AllAreas)) agent.Warp(hit.position);
            else if (NavMesh.SamplePosition(Center, out hit, 6f, NavMesh.AllAreas)) agent.Warp(hit.position);
        }

        /// <summary>
        /// Cinemática propia (transición, liberación): bloquea el control y deja a Kaito guionado e invulnerable. Se suelta
        /// sí o sí en el reintento y al desactivarse (no puede quedar el juego trabado en una cinemática).
        /// </summary>
        void HoldCutscene(bool on, bool letterbox = false)
        {
            if (on == holdingCutscene) return;
            holdingCutscene = on;
            Game.InCutscene = on;
            if (Game.Input != null) Game.Input.GameplayBlocked = on || Game.IsPaused;
            if (on && letterbox) { holdingLetterbox = true; Game.UI?.Letterbox(true); }
            if (!on && holdingLetterbox) { holdingLetterbox = false; Game.UI?.Letterbox(false); }
            var p = Game.Player;
            if (p != null && p.IsAlive) { if (on) p.EnterScripted(); else p.ExitScripted(); }
            if (!on) Game.Input?.ClearBuffer();
        }

        /// <summary>El especial en curso se cortó: lo remataron, un golpe de habilidad lo sacó del ataque o Kaito murió.</summary>
        bool SeqBroken => !IsAlive || State != EnemyState.Attack || target == null || !target.IsAlive;

        // ================================================================== fases
        /// <summary>
        /// 55 %: la transición de 5.5 s (el sello lo corrompe en la cascada). 25 %: el cambio corto genérico, con la
        /// cascada a pleno y el arcoíris de luna doble. La base hace la cuenta de la fase, el ritmo, el rugido y el empujón.
        /// </summary>
        protected override void PhaseChange(int newPhase)
        {
            // de a una: saltar de la 1 a la 3 (los dos umbrales en una misma ventana de castigo, o DebugPhase(2)) dejaba la
            // fase 3 con el cuerpo blanco, sin inundación ni los valores corrompidos. La 3 entra con el próximo golpe
            // después de la transición (Boss.OnDamaged vuelve a mirar los umbrales en cada golpe)
            newPhase = Mathf.Min(newPhase, CurrentPhase + 1);
            CancelMoves();
            base.PhaseChange(newPhase);
            if (newPhase == 1)
            {
                Imbalance = 0f;
                // corrompido: más rápido para girar, menos tiempo agotado, golpes 10 % más fuertes y 12 % más rápidos
                config.turnSpeed = 6f;
                config.exhaustedTime = 2.8f;
                config.ScaleSteps(1.1f, 1.12f / (1f + phaseSpeedBonus));
                Run(CorruptionRoutine());
            }
            else
            {
                if (Falls != null) { Falls.Intensity = 1.6f; Falls.Surge(2f, 2f); Falls.MoonbowBoost = 2f; }
                Game.UI?.ShowToast(StoryText.MizuchiPhase3, UIFactory.Gold, 2.2f);
                var pil = FindPattern("Pilares");
                if (pil != null) pil.cooldown = 12f;
                StaggerCooldowns(2, 0.6f);
            }
        }

        AttackPattern FindPattern(string name)
        {
            if (config.patterns != null) foreach (var p in config.patterns) if (p != null && p.name == name) return p;
            return null;
        }

        /// <summary>
        /// Transición a la fase 2 (~5.5 s): el sello destella y ruge; se tira a la cascada y la trepa; un rayo violeta
        /// desde el labio lo fulmina; cae al pozo (el chapuzón tapa el cambio de cuerpo) y sale corrompido, la cascada
        /// crece y el agua inunda la plataforma. La toma mira la cortina desde abajo: la primera vez que se la ve entera
        /// en la pelea.
        /// </summary>
        IEnumerator CorruptionRoutine()
        {
            inCinematic = true;
            HoldCutscene(true);
            EnterScripted();
            arenaRadius = 60f;   // va hasta la cascada: el tope de la arena lo traía de vuelta en cada espera
            anim.Play(phaseAnim, 0.1f);
            body?.FlareSeal(3f, 1.4f);
            Vector3 sealPos = body != null ? body.SealPosition : AimPoint;
            Game.FX?.FlashLight(sealPos, new Color(0.75f, 0.54f, 1f), 14f, 12f, 0.6f);
            Game.FX?.Shockwave(Center, 5f, new Color(0.75f, 0.54f, 1f));
            Game.Audio?.Play("koi_roar", transform.position, 1f);
            if (Falls != null) Falls.Corruption = 0.5f;
            yield return new WaitForSeconds(1.2f);

            // toma: baja, sobre la plataforma, mirando la cortina; sigue al koi
            Vector3 camPos = BehindKaito(3.5f, 2f, 2.1f);
            Vector3 look = transform.position + Vector3.up * 2f;
            int shot = Game.Camera != null ? Game.Camera.PlayShot(t =>
            {
                look = Vector3.Lerp(look, transform.position + Vector3.up * 2.5f, 1f - Mathf.Exp(-5f * Time.unscaledDeltaTime));
                return new Pose(camPos, Quaternion.LookRotation(look - camPos));
            }, () => 44f, 0.9f, 3.6f, 1.1f) : -1;

            // se tira al pie de la cascada y la trepa
            Vector3 plunge = Plunge;
            yield return Leap(plunge, false);
            anim.Play("ClimbFalls", 0.15f);
            transform.rotation = Quaternion.LookRotation(North);
            Vector3 top = Vector3.Lerp(plunge, Lip, 24f / Mathf.Max(1f, Lip.y - plunge.y)) - North * 1f;
            for (float t = 0f; t < 1.4f; t += Time.deltaTime)
            {
                float k = Mathf.SmoothStep(0f, 1f, t / 1.4f);
                transform.position = Vector3.Lerp(plunge, top, k);
                if (Falls != null) Falls.Corruption = Mathf.Lerp(0.5f, 1f, k);
                yield return null;
            }
            // el sello lo fulmina desde el labio
            SealBolt.Strike(Lip, body != null ? body.SealPosition : transform.position + Vector3.up * 3f, 0.4f);
            body?.FlareSeal(4f, 0.8f);
            anim.Play("Parried", 0.05f);
            yield return new WaitForSeconds(0.25f);
            anim.Play("BreachAir", 0.1f, 0.6f);
            Vector3 from = transform.position;
            for (float t = 0f; t < 0.7f; t += Time.deltaTime)
            {
                float k = t / 0.7f;
                transform.position = Vector3.Lerp(from, plunge, k * k);
                yield return null;
            }
            // el chapuzón tapa el cambio de cuerpo
            transform.position = plunge;
            // (Beached no: deja una mancha mojada, y esto es agua)
            WaterSplash.Column(plunge, 2.6f, 9f);
            WaterSplash.Column(plunge + East * 2f, 1.6f, 5f);
            WaterSplash.Column(plunge - East * 2f, 1.6f, 5f);
            Game.Camera?.Shake(0.6f);
            SetHidden(true);
            body?.SetPhase(1);
            if (Falls != null)
            {
                Falls.Intensity = 1.4f;
                Falls.Surge(1.8f, 2.5f);
                Falls.Corruption = 0.35f;
                Falls.Flood?.Rise(2f);
            }
            yield return new WaitForSeconds(0.3f);
            if (shot >= 0) Game.Camera.CancelShot(shot);
            // sale corrompido y cae a la plataforma, lejos de Kaito
            Vector3 land = Center + North * 3f;
            if (target != null && CombatMath.FlatDistance(land, target.transform.position) < 4.5f)
                land = OnDeck(target.transform.position + (land - target.transform.position).Flat().normalized * 4.5f, 6f);
            yield return Breach(plunge, land, 1.15f, 4f, 0f, 0f, 0f);
            anim.Play("Roar", 0.1f);
            Game.Audio?.Play("boss_roar", transform.position, 1f);
            Game.Audio?.Play("koi_roar", transform.position, 0.9f);
            Game.Camera?.Shake(0.5f);
            body?.FlareSeal(2.5f, 1f);
            Game.UI?.ShowToast(StoryText.MizuchiPhase2, UIFactory.Crimson, 2.4f);
            Game.UI?.BossEnraged(this);
            yield return new WaitForSeconds(1.1f);
            inCinematic = false;
            move = null;
            arenaRadius = baseArenaRadius;
            HoldCutscene(false);
            ExitScripted(false);
            SetState(EnemyState.Chase);
            IsAggro = true;
            nextAttackTime = Time.time + 0.8f;
            // los especiales nuevos entran de a uno en los próximos segundos (no todos juntos al volver)
            StaggerCooldowns(1, 0.6f);
        }

        /// <summary>Cámara baja por detrás de Kaito (mirando hacia la cascada): Kaito en primer plano, el koi y el agua atrás.</summary>
        Vector3 BehindKaito(float back, float side, float up)
        {
            Vector3 k = Game.Player != null ? Game.Player.transform.position : Center - North * 4f;
            Vector3 c = k - North * back + East * side;
            c.y = k.y + up;
            return c;
        }

        // ================================================================== presentación
        /// <summary>
        /// Primera vez en la arena (StoryDirector.BossIntroRoutine, ya dentro de la cinemática): el pozo de la cascada
        /// hierve, el koi sale de un salto contra la cortina, cae en su lugar, gira hacia Kaito y ruge. La grúa de la
        /// cascada ya la mostró StoryDirector.FallsReveal al entrar a la zona; esta toma es del koi.
        /// </summary>
        public IEnumerator Presentation(PlayerController p)
        {
            inCinematic = true;
            lurking = false;
            ghost?.Show(false);
            Game.Save.SetFlag(StoryDirector.FallsSeenFlag);
            Vector3 land = spawnPos;
            Vector3 pool = Plunge;
            SetHidden(true);
            SetAirborne(true);
            transform.SetPositionAndRotation(pool, Quaternion.LookRotation(-North));
            if (p != null) p.ScriptedFace(pool);
            Vector3 camPos = BehindKaito(4f, 1.8f, 2.3f);
            Vector3 look = pool + Vector3.up * 2f;
            int shot = Game.Camera != null ? Game.Camera.PlayShot(t =>
            {
                look = Vector3.Lerp(look, transform.position + Vector3.up * 2.2f, 1f - Mathf.Exp(-4f * Time.unscaledDeltaTime));
                return new Pose(camPos, Quaternion.LookRotation(look - camPos));
            }, () => 40f, 1.0f, 5.4f, 1.0f) : -1;
            // el pozo hierve
            for (float t = 0f; t < 0.9f; t += 0.12f)
            {
                WaterSplash.Flop(pool + Random.insideUnitSphere.Flat() * 2.5f, 0.9f);
                yield return new WaitForSeconds(0.12f);
            }
            // sale
            SetHidden(false);
            anim.Play("Intro", 0f);
            anim.SetSpeed(1f);
            WaterSplash.Column(pool, 2.4f, 7f);
            Game.Audio?.Play("water_splash", pool, 1f);
            Game.Camera?.Shake(0.3f);
            const float arcTime = 58f / 30f;   // aterriza en el cuadro 58 del clip
            Vector3 fwd = (land - pool).Flat().normalized;
            for (float t = 0f; t < arcTime; t += Time.deltaTime)
            {
                float s = t / arcTime;
                float k = Mathf.SmoothStep(0f, 1f, s);
                Vector3 q = Vector3.Lerp(pool, land, k);
                q.y = Mathf.Lerp(WaterHeight, DeckHeight, k) + 4f * 3.5f * s * (1f - s);
                transform.position = q;
                transform.rotation = Quaternion.LookRotation(fwd);
                yield return null;
            }
            SetAirborne(false);
            RestoreAgent(land);
            WaterSplash.Beached(land, fwd, 0.8f);
            Game.Audio?.Play("slam", land, 0.7f);
            Game.Camera?.Shake(0.4f);
            // gira hacia Kaito y ruge (cuadro 76)
            Quaternion from = transform.rotation;
            Vector3 toK = p != null ? (p.transform.position - transform.position).Flat() : -North;
            Quaternion to = toK.sqrMagnitude > 0.01f ? Quaternion.LookRotation(toK) : from;
            for (float t = 0f; t < (76f - 58f) / 30f; t += Time.deltaTime)
            {
                transform.rotation = Quaternion.Slerp(from, to, Mathf.SmoothStep(0f, 1f, t / 0.55f));
                yield return null;
            }
            transform.rotation = to;
            Game.Audio?.Play("boss_roar", transform.position, 1f);
            Game.Audio?.Play("koi_roar", transform.position, 0.9f);
            Game.Camera?.Shake(0.35f);
            body?.FlareSeal(2.5f, 1.2f);
            Game.UI?.ShowAreaTitle(title, subtitle);
            yield return new WaitForSeconds((90f - 76f) / 30f + 0.9f);
            if (shot >= 0) Game.Camera.CancelShot(shot);
            yield return Game.UI.Dialogue(StoryText.Dialogue("mizuchi_intro"));
            inCinematic = false;
        }

        // ================================================================== liberación (muerte)
        protected override void Die(in DamageInfo info, bool finisher = false)
        {
            if (State == EnemyState.Dead) return;
            CancelMoves();
            Game.Camera?.SetFocusBias(Vector3.zero);
            base.Die(info, finisher);
        }

        /// <summary>
        /// El remate común deja a Kaito "detrás" del centro del enemigo (raíz + radio + 1.4 m): en un cuerpo de 7.5 m eso
        /// cae dentro de la cola y ahí se quedaba toda la liberación. Lo corre al costado de la silueta, mirándolo.
        /// </summary>
        void PushPlayerOutOfBody()
        {
            var p = Game.Player;
            if (p == null || body == null) return;
            Vector3 pp = p.transform.position;
            Vector3 c = body.Closest(pp, out float r);
            Vector3 u = (pp - c).Flat();
            if (u.magnitude >= r + p.Radius + 0.4f) return;
            // del lado en que ya estaba; si quedó justo sobre el eje, al costado del cuerpo que da a la cámara (sur)
            if (u.sqrMagnitude < 1e-3f) u = Vector3.Dot(transform.right, North) > 0f ? -transform.right : transform.right;
            u = u.Flat().normalized;
            Vector3 q = OnDeck(c + u * (r + p.Radius + 1.1f), DeckRoom);
            q.y = pp.y;
            p.Teleport(q, Quaternion.LookRotation(-u));
        }

        // BeginExecution (código común) gira al enemigo de golpe hacia Kaito: en este cuerpo de 7.5 m echado de costado
        // era un latigazo de hasta 180° en la pose del remate. Se le devuelve el giro que traía, antes de dibujar el cuadro
        Quaternion liveRotation = Quaternion.identity;
        bool executionRestored;

        void LateUpdate()
        {
            if (State == EnemyState.Executed)
            {
                if (!executionRestored) { executionRestored = true; transform.rotation = liveRotation; }
            }
            else { liveRotation = transform.rotation; executionRestored = false; }
        }

        /// <summary>
        /// No cae ni se hace humo: la estaca salta, la tinta se le despega y queda blanco; nada hasta la cascada, la sube
        /// y en el labio se vuelve el dragón dorado (el del Espíritu del HUD) que se va hacia la luna. El sello limpio queda
        /// en el centro de la plataforma. La cascada se calma y el agua se va.
        /// </summary>
        protected override IEnumerator DeathRoutine(Vector3 dir)
        {
            inCinematic = true;
            Game.Camera?.CancelAllShots();     // el plano genérico de muerte de jefe: este tiene el suyo
            HoldCutscene(true, true);
            PushPlayerOutOfBody();
            if (Game.Player != null) Game.Player.ScriptedFace(transform.position);
            // al sur del koi (del lado contrario a la cascada): lo ve echado y después subiendo la cortina
            Vector3 camPos = transform.position - North * 7.5f + East * 3f;
            camPos.y = DeckHeight + 2.4f;
            Vector3 look = transform.position + Vector3.up * 2f;
            int shot = Game.Camera != null ? Game.Camera.PlayShot(t =>
            {
                look = Vector3.Lerp(look, transform.position + Vector3.up * 2.2f, 1f - Mathf.Exp(-3.5f * Time.unscaledDeltaTime));
                return new Pose(camPos, Quaternion.LookRotation(look - camPos));
            }, () => 42f, 1.0f, 11f, 1.2f) : -1;
            body?.FlareSeal(3f, 0.9f);
            // la cámara lenta del golpe final queda en el arco tenso (Freed 0-20); el crujido la corta de golpe
            yield return new WaitForSecondsRealtime(0.9f);
            Game.Time?.ClearSlowMotion();
            anim.Play("Freed", 0.05f, 18f / 120f);
            Vector3 seal = body != null ? body.SealPosition : AimPoint;
            Game.Audio?.Play("seal_crack", seal, 1f);
            Game.FX?.FlashLight(seal, new Color(0.75f, 0.54f, 1f), 16f, 10f, 0.5f);
            Game.FX?.EnemyDeath(seal, Vector3.up, true);
            Game.Camera?.Shake(0.5f);
            yield return new WaitForSeconds(22f / 30f);
            body?.SealOut();
            // cuadro 55: la tinta se despega y queda blanco
            yield return new WaitForSeconds(15f / 30f);
            Game.FX?.Screen?.WhiteFlash(0.7f);
            Game.FX?.FlashLight(AimPoint, Color.white, 18f, 14f, 0.6f);
            for (int i = -2; i <= 2; i++) Game.FX?.EnemyDeath(transform.position + transform.forward * (i * 1.4f) + Vector3.up * 1.8f, Vector3.up, true);
            body?.SetPhase(0);
            if (Falls != null) Falls.Corruption = 0f;
            yield return new WaitForSeconds(0.5f);

            // nada hasta el pie de la cascada y la sube
            if (agent != null) agent.enabled = false;
            Vector3 start = transform.position, plunge = Plunge;
            transform.rotation = Quaternion.LookRotation((plunge - start).Flat().sqrMagnitude > 0.01f ? (plunge - start).Flat() : North);
            anim.Play("Swim", 0.25f);
            for (float t = 0f; t < 1.4f; t += Time.deltaTime)
            {
                float k = Mathf.SmoothStep(0f, 1f, t / 1.4f);
                Vector3 q = Vector3.Lerp(start, plunge, k);
                q.y = Mathf.Lerp(start.y, plunge.y, k) + Mathf.Sin(k * Mathf.PI) * 1.2f;
                transform.position = q;
                yield return null;
            }
            anim.Play("ClimbFalls", 0.2f);
            transform.rotation = Quaternion.LookRotation(North);
            Vector3 lip = Lip - North * 1f;
            for (float t = 0f; t < 1.8f; t += Time.deltaTime)
            {
                float k = t / 1.8f;
                transform.position = Vector3.Lerp(plunge, lip, k * (2f - k));
                yield return null;
            }

            // en el labio: el dragón dorado
            dragonMat = new Material(FXMaterials.Ghost) { name = "MizuchiDragon" };
            FXMaterials.SetColor(dragonMat, new Color(1f, 0.85f, 0.42f, 0.7f));
            body?.SetDragon(dragonMat);
            var trails = AttachDragonTrails();
            Game.FX?.Screen?.WhiteFlash(0.6f);
            Game.FX?.FlashLight(transform.position + Vector3.up * 2f, new Color(1f, 0.85f, 0.42f), 40f, 40f, 1.2f);
            Game.Audio?.Play("koi_freed", transform.position, 1f);
            Game.Audio?.Play("boss_roar", transform.position, 0.6f);
            Game.UI?.ShowToast(StoryText.MizuchiFreed, UIFactory.Gold, 3f);
            if (Falls != null) { Falls.Intensity = KohanFalls.CalmIntensity; Falls.MoonbowBoost = 1.5f; Falls.Flood?.Drain(3f); }
            Vector3 moon = RenderSettings.sun != null ? -RenderSettings.sun.transform.forward : (Vector3.up - North).normalized;
            if (moon.y < 0.3f) moon = (moon + Vector3.up).normalized;
            Vector3 rise = (Vector3.up * 1.4f + moon).normalized;
            anim.Play("Swim", 0.3f);
            Vector3 p0 = transform.position;
            for (float t = 0f; t < 2.6f; t += Time.deltaTime)
            {
                float k = t / 2.6f;
                transform.position = p0 + rise * (34f * k * k + 6f * k);
                transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(rise), 1f - Mathf.Exp(-3f * Time.deltaTime));
                FXMaterials.SetColor(dragonMat, new Color(1f, 0.85f, 0.42f, 0.7f * (1f - k * k)));
                yield return null;
            }
            foreach (var tr in trails) if (tr != null) tr.emitting = false;
            SetHidden(true);
            yield return new WaitForSeconds(0.6f);
            if (shot >= 0) Game.Camera.CancelShot(shot);
            HoldCutscene(false);
            inCinematic = false;
            OnDeathFinished();
        }

        TrailRenderer[] AttachDragonTrails()
        {
            var at = new[] { body != null ? body.Head : null, body != null ? body.Tail : null };
            var res = new TrailRenderer[at.Length];
            for (int i = 0; i < at.Length; i++)
            {
                if (at[i] == null) continue;
                var tr = at[i].gameObject.AddComponent<TrailRenderer>();
                tr.sharedMaterial = KoiWater.GlowLine;
                tr.time = 1.4f;
                tr.widthMultiplier = i == 0 ? 1.6f : 1.1f;
                tr.widthCurve = new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(1f, 0f));
                tr.startColor = new Color(1f, 0.85f, 0.42f, 0.9f);
                tr.endColor = new Color(1f, 0.6f, 0.2f, 0f);
                tr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                res[i] = tr;
            }
            return res;
        }

        /// <summary>El sello cae limpio en el centro de la plataforma (el koi ya no está ahí).</summary>
        protected override void OnDeathFinished()
        {
            if (hasSeal) KeyPickup.Spawn(seal, Center + Vector3.up * 0.2f);
            gameObject.SetActive(false);
        }

        // ================================================================== pruebas (RunCommand del editor)
        /// <summary>
        /// Salta a la fase 'p' (1 = corrompido, 2 = desesperación) con la vida justo debajo del umbral. Desde la fase 1
        /// pasa primero por la corrupción: DebugPhase(2) se vuelve a llamar (o se le pega) cuando termina.
        /// </summary>
        public void DebugPhase(int p)
        {
            if (!IsAlive || inCinematic || p <= CurrentPhase || p > phaseThresholds.Length) return;
            Health = Mathf.Min(Health, config.maxHealth * (phaseThresholds[p - 1] - 0.01f));
            PhaseChange(p);
        }

        /// <summary>Usa ya el patrón con ese nombre (EnemyArchetypes.Mizuchi: "Salto del Dragón", "Pilares", "Tama-asobi"...).</summary>
        public void DebugMove(string patternName)
        {
            var p = FindPattern(patternName);
            if (p == null || !IsAlive || inCinematic) return;
            if (State == EnemyState.Attack) CancelMoves();
            Game.Combat?.RequestAttackToken(this);
            pattern = p;
            StartAttack(false);
        }

        /// <summary>Vida a 'health01' (0..1) sin cambiar de fase: para probar el remate y la liberación.</summary>
        public void DebugHealth(float health01) => Health = Mathf.Clamp01(health01) * config.maxHealth;
    }
}
