using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Kage, la sombra que Kokuyō se arrancó del piso (Acto 2): un segundo cazador hecho de tinta. Es un Enemy sin modelo
    /// propio (lo que se ve es el doble de PlanarShadow, suelto y parado como humo) para que sus golpes usen el mismo
    /// idioma que todos: aviso rojo en el suelo con su zona, hyōshigi a 0.42 s, marca de imparable.
    ///  * Kage-nui: se acuesta, se desliza bajo Kaito, la zona se traba y 0.8 s después estalla en agujas (disco de 2.2 m).
    ///  * Kage-watari: se para a 8 m al costado de Kaito, apunta 0.6 s y cruza 16 m a 24 m/s.
    /// No se fija ni se corta: la katana la atraviesa. Una habilidad (Corte del Viento, Torbellino) la CLAVA 6 s y le
    /// suma 2 de postura al cuerpo. Kokuyō decide cuándo puede atacar (nunca a menos de 0.9 s de un golpe suyo).
    /// </summary>
    public class KageShadow : Enemy
    {
        KokuyoBoss owner;
        PlanarShadow ink;
        KokuyoHazards hazards;

        enum Mode { Hunt, LineUp, Pinned, Recall }
        Mode mode = Mode.Hunt;
        float pinnedUntil, lastGhostHit = -9f, recallT;
        Vector3 lineUp, laneOrigin, laneDir, lockPos, recallFrom;
        bool locked, erupted, crossing, crossHit;
        float lockTime, slideTime;
        int sideSign = 1;
        AttackPattern nui, watari;

        public const float SlideSpeed = 9f, NuiHold = 0.8f, NuiRadius = 2.2f, SlideMax = 1.0f;
        public const float CrossSpeed = 24f, CrossLength = 16f, CrossHalfWidth = 1.2f, LineUpDistance = 8f;
        const float GlideSpeed = 7f, HuntDistance = 6.5f, PinTime = 6f;

        public bool Pinned => mode == Mode.Pinned;
        /// <summary>Atacando o con un ataque en camino: el cuerpo espera.</summary>
        public bool Busy => State == EnemyState.Attack || mode == Mode.LineUp;
        public override bool Targetable => false;

        public static KageShadow Spawn(KokuyoBoss owner, PlanarShadow ink, KokuyoHazards hazards)
        {
            var go = new GameObject("Kage");
            int layer = LayerMask.NameToLayer("Enemy");
            if (layer >= 0) go.layer = layer;
            go.transform.SetPositionAndRotation(ink.Root.position.Flat() + Vector3.up * owner.transform.position.y, owner.transform.rotation);
            var k = go.AddComponent<KageShadow>();
            k.config = KokuyoMoves.Shadow();
            k.owner = owner;
            k.ink = ink;
            k.hazards = hazards;
            k.nui = k.config.patterns[0];
            k.watari = k.config.patterns[1];
            return k;
        }

        protected override void Start()
        {
            base.Start();
            nextAttackTime = Time.time + 1.6f;
            target = Game.Player;
        }

        // ------------------------------------------------------------------ recibir golpes
        public override HitResult ReceiveHit(in DamageInfo info)
        {
            if (!IsAlive || info.sourceFaction != Faction.Player || mode == Mode.Recall) return HitResult.Ignored;
            if (info.kind == AttackKind.Ability)
            {
                if (mode != Mode.Pinned) Pin();
                return HitResult.Hit;
            }
            // la katana pasa a través: un susurro y un salpicón de tinta (y la primera vez, la pista)
            if (Time.time - lastGhostHit > 0.35f)
            {
                lastGhostHit = Time.time;
                ink?.Strike(0.06f);
                owner?.OnShadowSlashed();
            }
            return HitResult.Ignored;
        }

        void Pin()
        {
            if (State == EnemyState.Attack) SetState(EnemyState.Idle);   // corta el golpe (el aviso se borra como cortado)
            ReleaseStrikeReservation();
            mode = Mode.Pinned;
            pinnedUntil = Time.time + PinTime;
            hazards?.Puddle(Vector3.zero, 0f);
            if (ink != null)
            {
                ink.Strike(0.3f);
                ink.RiseTo(1f, 0.15f);
                ink.FadeTo(0.45f, 0.2f);
            }
            Game.FX?.Shockwave(transform.position, 2.4f, new Color(1f, 0.8f, 0.35f));
            Game.FX?.FlashLight(transform.position + Vector3.up * 2f, new Color(1f, 0.85f, 0.45f), 5f, 9f, 0.3f);
            Game.Audio?.Play("seal", transform.position, 0.9f);
            owner?.OnShadowPinned();
        }

        void ReleaseStrikeReservation() => Game.Combat?.ReleaseStrike(this);

        // ------------------------------------------------------------------ cazar (estado Idle: el cerebro es propio)
        // si la agenda de golpes no le hace lugar, Enemy lo manda a perseguir como a un ninja: vuelve a su ronda
        protected override void TickChase(float dt) => SetState(EnemyState.Idle);
        protected override void TickStrafe(float dt) => SetState(EnemyState.Idle);

        protected override void TickIdle(float dt)
        {
            if (target == null || !target.IsAlive || owner == null) return;
            switch (mode)
            {
                case Mode.Pinned:
                    if (Time.time >= pinnedUntil)
                    {
                        mode = Mode.Hunt;
                        if (ink != null) ink.FadeTo(1f, 0.4f);
                        nextAttackTime = Time.time + 1.2f;
                    }
                    break;
                case Mode.Recall:
                    TickRecall(dt);
                    break;
                case Mode.LineUp:
                    Glide(lineUp, GlideSpeed * 1.4f, dt);
                    FaceFlat(target.transform.position, dt);
                    if (CombatMath.FlatDistance(transform.position, lineUp) < 0.6f || !owner.ShadowMayAttack())
                    {
                        if (owner.ShadowMayAttack()) BeginWatari();
                        else mode = Mode.Hunt;
                    }
                    break;
                default:
                    Hunt(dt);
                    break;
            }
        }

        void Hunt(float dt)
        {
            // ronda a un costado de Kaito en pantalla (un poco hacia arriba): el cuerpo suele estar arriba y la cámara
            // mira hacia allá; del lado opuesto al cuerpo quedaba debajo del cuadro y el segundo cazador no se veía
            Vector3 kp = target.transform.position;
            Vector3 right = Game.Camera != null ? Game.Camera.transform.right.Flat().normalized : Vector3.right;
            if (right.sqrMagnitude < 0.01f) right = Vector3.right;
            Vector3 up = Vector3.Cross(right, Vector3.up);
            Vector3 dest = kp + (right * sideSign * 0.92f + up * 0.38f) * HuntDistance;
            Glide(ClampToArena(dest), GlideSpeed, dt);
            FaceFlat(kp, dt);
            if (ink != null) ink.SampleAhead(KokuyoTimings.Idle.State, Mathf.Repeat(Time.time / KokuyoTimings.Idle.Seconds, 1f));
            if (Time.time < nextAttackTime || !owner.ShadowMayAttack()) return;
            // 2:1 a favor del estallido; el cruce necesita lugar a un costado de Kaito
            bool cross = Random.value < 1f / 3f && TryLineUp(kp, out lineUp);
            if (cross) { mode = Mode.LineUp; return; }
            if (CombatMath.FlatDistance(transform.position, kp) > SlideSpeed * SlideMax + 2f) return;   // muy lejos: se acerca primero
            BeginNui();
        }

        bool TryLineUp(Vector3 kp, out Vector3 p)
        {
            // al este o al oeste de Kaito (de costado en pantalla: nunca entra por arriba o por abajo del cuadro)
            Vector3 side = Game.Camera != null ? Game.Camera.transform.right.Flat().normalized : Vector3.right;
            if (side.sqrMagnitude < 0.01f) side = Vector3.right;
            float pick = Vector3.Dot(transform.position - kp, side) >= 0f ? 1f : -1f;
            for (int i = 0; i < 2; i++, pick = -pick)
            {
                p = kp + side * pick * LineUpDistance;
                if (owner.InArena(p, 1f)) return true;
            }
            p = kp;
            return false;
        }

        void BeginNui()
        {
            pattern = nui;
            var a = nui.steps[0];
            float slide = Mathf.Min(SlideMax, Mathf.Max(0f, CombatMath.FlatDistance(transform.position, target.transform.position) - 0.5f) / SlideSpeed);
            a.windup = slide + NuiHold;
            locked = erupted = false;
            slideTime = 0f;
            StartAttack(false);
            if (State != EnemyState.Attack) return;
            // el deslizamiento puede durar hasta SlideMax si Kaito corre: el cuerpo espera lo peor
            owner.ReserveAfterShadow(Time.time + SlideMax + NuiHold);
            if (ink != null) ink.RiseTo(0f, 0.25f);   // se acuesta: es tinta en el piso que corre hacia Kaito
            hazards?.Boil(25f);
            Game.Audio?.Play("kokuyo_whisper", transform.position, 1f);
        }

        void BeginWatari()
        {
            mode = Mode.Hunt;
            pattern = watari;
            crossing = crossHit = false;
            StartAttack(false);
            if (State != EnemyState.Attack) return;
            owner.ReserveAfterShadow(Time.time + watari.steps[0].windup + LineUpDistance / CrossSpeed);
        }

        // ------------------------------------------------------------------ golpes
        protected override void OnStepStarted(AttackDef a)
        {
            base.OnStepStarted(a);
            // después de cada golpe ronda del otro costado (o del mismo): no se lo ve venir siempre igual
            sideSign = Random.value < 0.5f ? -1 : 1;
        }

        protected override float ComputeStrikeEta(AttackDef a)
        {
            if (target == null) return float.PositiveInfinity;
            switch (a.special)
            {
                case KokuyoMoves.Nui:
                    if (erupted) return float.PositiveInfinity;
                    if (locked) return Mathf.Max(0f, lockTime + NuiHold - Time.time);
                    return Mathf.Max(0f, CombatMath.FlatDistance(transform.position, target.transform.position) - 0.5f) / SlideSpeed + NuiHold;
                case KokuyoMoves.Watari:
                {
                    if (crossHit) return float.PositiveInfinity;
                    Vector3 o = crossing ? laneOrigin : transform.position;
                    Vector3 dir = crossing ? laneDir : transform.forward.Flat().normalized;
                    Vector3 to = (target.transform.position - o).Flat();
                    float along = Vector3.Dot(to, dir);
                    float lateral = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, dir)));
                    float pre = Mathf.Max(0f, tl.T - stepClock);
                    if (crossing)
                    {
                        float done = (stepClock - tl.T) * CrossSpeed;
                        if (along < done - 0.5f || along > CrossLength || lateral > CrossHalfWidth + target.Radius) return float.PositiveInfinity;
                        return Mathf.Max(0f, along - done) / CrossSpeed;
                    }
                    return pre + Mathf.Max(0f, along) / CrossSpeed;
                }
            }
            return base.ComputeStrikeEta(a);
        }

        protected override bool HitAreaFor(AttackDef a, out TellArea area)
        {
            switch (a.special)
            {
                case KokuyoMoves.Nui:
                    area = new TellArea { origin = locked ? lockPos : transform.position, size = NuiRadius };
                    return true;
                case KokuyoMoves.Watari:
                    area = new TellArea
                    {
                        lane = true, origin = crossing ? laneOrigin : transform.position,
                        forward = crossing ? laneDir : transform.forward.Flat().normalized, size = CrossLength, width = CrossHalfWidth * 2f,
                    };
                    return true;
            }
            return base.HitAreaFor(a, out area);
        }

        protected override void TickSpecial(AttackDef a, float dt)
        {
            switch (a.special)
            {
                case KokuyoMoves.Nui: TickNui(a, dt); return;
                case KokuyoMoves.Watari: TickWatari(a, dt); return;
            }
            base.TickSpecial(a, dt);
        }

        void TickNui(AttackDef a, float dt)
        {
            if (!erupted)
            {
                // el reloj del paso espera en el golpe hasta que estalla de verdad (el deslizamiento dura lo que dure)
                if (stepClock > tl.T - 0.01f) { stepClock = tl.T - 0.01f; stepNorm = tl.NormAt(stepClock); }
                if (!locked)
                {
                    slideTime += dt;
                    Vector3 kp = target.transform.position;
                    Glide(kp, SlideSpeed, dt);
                    hazards?.Puddle(transform.position, 1.6f);
                    // la zona se traba al llegar (o si Kaito corre más que la tinta): desde acá 0.8 s para salir
                    if (CombatMath.FlatDistance(transform.position, kp) <= 0.5f || slideTime >= SlideMax)
                    {
                        locked = true;
                        lockTime = Time.time;
                        lockPos = transform.position;
                        hazards?.Boil(60f);
                        Game.Audio?.Play("tell_danger", lockPos, 0.8f, 0.03f);
                    }
                }
                else
                {
                    hazards?.Puddle(lockPos, 1.6f + 0.6f * Mathf.Clamp01((Time.time - lockTime) / NuiHold));
                    if (Time.time >= lockTime + NuiHold) Erupt(a);
                }
            }
            if (ink != null) ink.SampleAhead(KokuyoTimings.ShadowEmerge.State, erupted ? Mathf.Min(KokuyoTimings.ShadowEmerge.Contact + (Time.time - lockTime - NuiHold) * 0.9f, 1f) : 0.15f);
        }

        void Erupt(AttackDef a)
        {
            erupted = true;
            stepClock = tl.T;
            stepNorm = tl.NormAt(stepClock);
            hazards?.Puddle(Vector3.zero, 0f);
            // anillo de agujas alrededor del punto trabado y la tinta se para de golpe
            if (hazards != null)
                for (int i = 0; i < 9; i++)
                {
                    float ang = i * 40f + Random.Range(-12f, 12f);
                    float r = i == 0 ? 0f : Random.Range(0.6f, NuiRadius - 0.2f);
                    hazards.Shard(lockPos + Quaternion.Euler(0f, ang, 0f) * Vector3.forward * r, i == 0 ? 2 : Random.Range(0, 2), 0.9f);
                }
            if (ink != null) ink.RiseTo(1f, 0.2f);
            Game.FX?.Shockwave(lockPos, NuiRadius, new Color(0.75f, 0.54f, 1f));
            Game.FX?.Dust(lockPos, 1.4f);
            Game.Camera?.Shake(0.45f);
            Game.Audio?.Play("slam", lockPos, 0.9f);
            if (target != null && CombatMath.FlatDistance(target.transform.position, lockPos) <= NuiRadius + target.Radius)
            {
                stepHit = true;
                // lo despide hacia afuera del estallido (parado justo en el centro, hacia donde mira)
                Vector3 from = (target.transform.position - lockPos).Flat().sqrMagnitude > 0.09f ? lockPos : target.transform.position - target.transform.forward;
                HitPlayer(a, from);
            }
        }

        void TickWatari(AttackDef a, float dt)
        {
            if (!crossing)
            {
                // apunta hasta el "¡ahora!" y desde ahí el carril queda fijo
                if (StrikeEta > KokuyoMoves.GoLead) FaceFlat(target.transform.position, dt, 10f);
                if (ink != null) ink.SampleAhead(KokuyoTimings.Tsuki.State, KokuyoTimings.Tsuki.Apex);
                if (stepClock >= tl.T)
                {
                    crossing = true;
                    laneOrigin = transform.position;
                    laneDir = transform.forward.Flat().normalized;
                    tl.sustain = CrossLength / CrossSpeed;
                    Game.Audio?.Play("ability_wind", transform.position, 0.8f);
                }
                return;
            }
            if (ink != null) ink.SampleAhead(KokuyoTimings.Tsuki.State, KokuyoTimings.Tsuki.ActiveEnd);
            float travelled = (stepClock - tl.T) * CrossSpeed;
            if (travelled <= CrossLength && !anim.Frozen)
            {
                Vector3 p = laneOrigin + laneDir * Mathf.Min(travelled, CrossLength);
                p.y = transform.position.y;
                transform.position = p;
                Game.FX?.DustTrail(p);
                if (!crossHit && target != null)
                {
                    Vector3 to = (target.transform.position - p).Flat();
                    float along = Vector3.Dot(to, laneDir);
                    float lateral = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, laneDir)));
                    if (along <= 0.3f && along > -1.5f && lateral <= CrossHalfWidth + target.Radius)
                    {
                        crossHit = true;
                        stepHit = true;
                        HitPlayer(a, p - laneDir);
                    }
                }
            }
        }

        protected override void ComboEnd()
        {
            ReleaseToken();
            pattern = null;
            crossing = false;
            hazards?.Puddle(Vector3.zero, 0f);
            nextAttackTime = Time.time + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
            SetState(EnemyState.Idle);
        }

        // ------------------------------------------------------------------ vuelta al cuerpo (eclipse)
        /// <summary>La sombra vuelve volando a los pies de Kokuyō y se acuesta (el eclipse la borra después).</summary>
        public void Recall()
        {
            if (State == EnemyState.Attack) SetState(EnemyState.Idle);
            ReleaseStrikeReservation();
            hazards?.Puddle(Vector3.zero, 0f);
            mode = Mode.Recall;
            recallT = 0f;
            recallFrom = transform.position;
            if (ink != null) { ink.FadeTo(1f, 0.2f); ink.RiseTo(0f, 0.45f); }
        }

        void TickRecall(float dt)
        {
            recallT += dt / 0.5f;
            float k = 1f - (1f - Mathf.Clamp01(recallT)) * (1f - Mathf.Clamp01(recallT));
            Vector3 p = Vector3.Lerp(recallFrom, owner.transform.position, k);
            p.y = owner.transform.position.y;
            transform.position = p;
            if (recallT >= 1f && ink != null && ink.Detached)
            {
                ink.Reattach();
                ink.Lead = false;   // vuelve a ser su sombra: copia la pose del cuerpo
            }
        }

        /// <summary>Se va del todo (eclipse, reintento, final). La sombra dibujada la maneja KageArenaFX.</summary>
        public void Dismiss()
        {
            if (State == EnemyState.Attack) SetState(EnemyState.Idle);
            ReleaseStrikeReservation();
            hazards?.Puddle(Vector3.zero, 0f);
            Destroy(gameObject);
        }

        // ------------------------------------------------------------------ movimiento
        void Glide(Vector3 dest, float speed, float dt)
        {
            Vector3 d = (dest - transform.position).Flat();
            float m = d.magnitude;
            if (m < 0.05f) return;
            MoveBy(d / m * Mathf.Min(m, speed * dt));
        }

        void FaceFlat(Vector3 p, float dt, float rate = 8f)
        {
            Vector3 d = (p - transform.position).Flat();
            if (d.sqrMagnitude > 0.01f) transform.rotation = CombatMath.Damp(transform.rotation, Quaternion.LookRotation(d), rate, dt);
        }

        Vector3 ClampToArena(Vector3 p) => owner != null ? owner.ClampToArena(p, 1.5f) : p;

        protected override void Update()
        {
            base.Update();
            // la figura de tinta va donde está este cazador (suelta: PlanarShadow ya no la pega al cuerpo)
            if (ink != null && ink.Detached && ink.Root != null) ink.Root.SetPositionAndRotation(transform.position, transform.rotation);
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            if (Game.Combat != null) Game.Combat.ReleaseStrike(this);
        }
    }
}
