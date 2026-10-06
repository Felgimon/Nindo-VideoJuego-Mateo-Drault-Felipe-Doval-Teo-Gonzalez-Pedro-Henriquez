using System.Collections;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Los especiales de Mizuchi. Reglas de todos (las mismas del resto del juego):
    ///  * dorado = parry (perlas, peloteo); rojo = salí de ahí (salto, chorro, ola, pilares). La zona roja aparece al menos
    ///    0.9 s antes y se llena al ritmo del golpe; el hyōshigi suena a 0.42 s, la parte que pega brilla a 0.33 s y la
    ///    zona se cierra a 0.16 s (el centro de los i-frames del dash);
    ///  * todo lo rojo se puede esquivar corriendo (6.2 m/s) dentro de su aviso; el dash es la salida con estilo;
    ///  * nada empieza fuera de cuadro: sale del agua solo por puntos que la cámara ve, y los pilares y la ola caen sobre
    ///    la plataforma;
    ///  * la ETA de cada uno es exacta (StrikeEta / ProjectileEta): el bot de pruebas y los avisos no mienten.
    /// </summary>
    public partial class MizuchiBoss
    {
        struct RedCue { public bool ticked, pre, glinted; }

        // ------------------------------------------------------------------ perlas
        const float FanSpread = 18f, FanSpeed = 9f, StormSpeed = 10f, StormGap = 0.15f, RallySpeed = 10f;
        float pearlEta = float.PositiveInfinity;
        Vector3 pearlFrom;
        bool pendingCued, pendingGlinted;
        int stormFired;
        WaterPearl rallyPearl;
        int rallyReturns;
        float rallyStart;

        // ------------------------------------------------------------------ chorro
        // medio ancho del chorro; se traba 0.75 s antes (un paso al costado alcanza). El barrido (±30°, 0.8 s) avisa
        // 1 s antes: simulado a pie (reacción 0.25 s, 6.2 m/s), desde cualquier punto del abanico a 4-11 m hay salida
        // por uno de los dos bordes (con ±35°/0.95/0.6 a 9-11 m había posiciones sin salida)
        const float JetHalf = 0.75f, JetLock = 0.75f, SweepLock = 1.0f, SweepHalf = 30f, SweepTime = 0.8f;
        const int SweepLanes = 7;
        static readonly Color AimColor = new Color(0.55f, 0.9f, 1f);
        bool jetLocked, jetFired, jetSwung;
        Vector3 jetOrigin, jetDir;
        float sweepSign = 1f;
        MizuchiMarks.Mark aimMark;
        readonly MizuchiMarks.Mark[] sweepMarks = new MizuchiMarks.Mark[SweepLanes];
        RedCue sweepCue;

        // ------------------------------------------------------------------ salto del dragón
        bool landPlanned;
        Vector3 landPoint;
        float landRadius, impactTime;
        RedCue leapCue;

        // ------------------------------------------------------------------ ola de la cascada
        // la ola nace sobre el agua al norte (11 m) y cruza a 8 m/s; dos canales de 3 m (medio ancho 1.5) sin cresta
        const float GapHalf = 1.5f, WaveSpeed = 8f, WaveStartZ = 11f, BandWarn = 1.2f, BandNear = 8.4f, BandDepth = 2.4f, BandHalfWidth = 6.6f;
        bool waveArmed;
        float waveLaunch, gap0, gap1;
        RedCue waveCue;
        readonly MizuchiMarks.Mark[] bandMarks = new MizuchiMarks.Mark[3];
        readonly MizuchiMarks.Mark[] laneMarks = new MizuchiMarks.Mark[2];

        // ------------------------------------------------------------------ pilares
        const float PillarRadius = 2.2f, PillarWarn = 1.1f, PillarFall = 0.35f, PillarGap = 0.45f;
        readonly Vector3[] pillarAt = new Vector3[4];
        readonly float[] pillarImpact = new float[4];
        readonly bool[] pillarDone = new bool[4], pillarDropped = new bool[4];
        readonly MizuchiMarks.Mark[] pillarMark = new MizuchiMarks.Mark[4];
        readonly RedCue[] pillarCue = new RedCue[4];
        int pillarCount;

        // ================================================================== paso: qué avisa y cuándo pega
        void ResetStepState(AttackDef a)
        {
            stormFired = 0;
            pendingCued = pendingGlinted = false;
            jetLocked = jetFired = jetSwung = false;
            aimMark = null;
            for (int i = 0; i < sweepMarks.Length; i++) sweepMarks[i] = null;
            sweepCue = default;
            if (a.special == "jet" || a.special == "jetsweep") Game.Audio?.Play("jet_charge", Snout, 0.9f, 0.03f);
        }

        void ClearPlans()
        {
            landPlanned = false;
            waveArmed = false;
            pillarCount = 0;
            jetLocked = false;
            aimMark = null;
            for (int i = 0; i < sweepMarks.Length; i++) sweepMarks[i] = null;
            for (int i = 0; i < bandMarks.Length; i++) bandMarks[i] = null;
            for (int i = 0; i < laneMarks.Length; i++) laneMarks[i] = null;
            for (int i = 0; i < pillarMark.Length; i++) pillarMark[i] = null;
            rallyReturns = 0;
        }

        protected override bool StepHasTell(AttackDef a)
        {
            switch (a.special)
            {
                // estos avisan con sus propias zonas en el mundo (o a los pies de Kaito, las perlas)
                case "pearls": case "storm": case "rally": case "dive": case "greatwave": case "pillars": case "jetsweep":
                    return false;
                default: return base.StepHasTell(a);
            }
        }

        protected override float ComputeStrikeEta(AttackDef a)
        {
            switch (a.special)
            {
                case "pearls": case "storm": case "rally": return float.PositiveInfinity;   // pegan las perlas (ProjectileEta)
                case "dive": return landPlanned ? Mathf.Max(0f, impactTime - Time.time) : float.PositiveInfinity;
                case "greatwave": return WaveEta();
                case "pillars": return PillarEta();
                case "jetsweep": return SweepEta();
                default: return base.ComputeStrikeEta(a);
            }
        }

        protected override bool HitAreaFor(AttackDef a, out TellArea area)
        {
            area = default;
            switch (a.special)
            {
                case "dive":
                    if (!landPlanned) return false;
                    area = new TellArea { origin = landPoint, size = landRadius };
                    return true;
                case "pillars":
                {
                    int i = NextPillarThreat();
                    if (i >= 0) { area = new TellArea { origin = pillarAt[i], size = PillarRadius }; return true; }
                    if (!landPlanned) return false;
                    area = new TellArea { origin = landPoint, size = landRadius };
                    return true;
                }
                case "greatwave":
                    if (!waveArmed || target == null || InTrough(LocalX(target.transform.position))) return false;
                    area = new TellArea { lane = true, origin = Center + North * WaveStartZ, forward = -North, size = WaveStartZ + RailRadius + 1f, width = 2f * KoiWave.HalfWidth };
                    return true;
                case "jet":
                    if (!jetLocked) return false;
                    area = new TellArea { lane = true, origin = Ground(jetOrigin), forward = jetDir, size = JetLength(a), width = 2f * (JetHalf + 0.35f) };
                    return true;
                case "jetsweep":
                    // solo para "¿me alcanza?" (no se dibuja: el abanico lo pintan las zonas propias)
                    if (!jetLocked) return false;
                    area = new TellArea { lane = true, origin = Ground(jetOrigin), forward = jetDir, size = JetLength(a), width = 2f * JetLength(a) * Mathf.Tan(SweepHalf * Mathf.Deg2Rad) };
                    return true;
                default: return base.HitAreaFor(a, out area);
            }
        }

        protected override void TickSpecial(AttackDef a, float dt)
        {
            switch (a.special)
            {
                case "pearls": TickPearls(a, false); break;
                case "storm": TickPearls(a, true); break;
                case "rally": TickRally(a, dt); break;
                case "jet": TickJet(a, dt, false); break;
                case "jetsweep": TickJet(a, dt, true); break;
                case "dive": case "greatwave": case "pillars": break;   // los lleva su rutina
                default: base.TickSpecial(a, dt); break;
            }
        }

        // ================================================================== avisos
        /// <summary>Aviso de un imparable que aparece: destello rojo donde va a pegar, marca sobre el koi y el taiko.</summary>
        void RedWarn(Vector3 at)
        {
            Game.FX?.FlashLight(at + Vector3.up * 1.2f, TellStyle.Crimson, 6f, 7f, 0.4f);
            Game.UI?.ShowDanger(this);
            Game.Audio?.Play("tell_danger", at, 1f, 0.03f);
        }

        /// <summary>Los tres tiempos de un rojo: hyōshigi (0.42 s), brillo del koi y de la zona (0.33), destello al cierre.</summary>
        void TickRedCue(ref RedCue c, float eta, Vector3 at)
        {
            if (float.IsInfinity(eta)) return;
            if (!c.ticked && AudioManager.CueDue(eta, TellStyle.TickUnblockable))
            {
                c.ticked = true;
                // la amenaza está sobre Kaito: siempre igual de clara (2D)
                Game.Audio?.Play("tell_tick", null, 0.8f, 0.03f);
                GameEvents.RaiseStrikeCue(this, true);
            }
            if (!c.pre && eta <= CueLead) { c.pre = true; PreGlint(at, true); }
            if (!c.glinted && eta <= TellStyle.BiasUnblockable) { c.glinted = true; Game.FX?.BladeGlint(at + Vector3.up, true); }
        }

        // ================================================================== perlas
        public override float ProjectileEta => pearlEta;
        public override Vector3 ProjectileFrom => pearlFrom;

        /// <summary>
        /// La próxima perla que toca a Kaito, en vuelo o por salir (misma cuenta desde la boca): el anillo de sus pies, el
        /// hyōshigi y el destello no esperan a que la perla exista.
        /// </summary>
        void UpdatePearls()
        {
            pearlEta = float.PositiveInfinity;
            var p = target;
            if (p == null || !p.IsAlive || inCinematic) return;
            Vector3 pp = p.transform.position;
            WaterPearl next = null;
            var list = WaterPearl.Active;
            for (int i = 0; i < list.Count; i++)
            {
                var w = list[i];
                if (w == null || w.Owner != this) continue;
                float eta = w.EtaToPlayer(pp);
                if (eta < pearlEta) { pearlEta = eta; pearlFrom = w.Position; next = w; }
            }
            var a = State == EnemyState.Attack ? CurrentAttack : null;
            if (a != null && PendingPearl(a, out float wait, out float speed, out float radius))
            {
                float eta = wait + Mathf.Max(0f, CombatMath.FlatDistance(Snout, pp) - radius) / speed;
                if (eta < pearlEta) { pearlEta = eta; pearlFrom = Snout; next = null; }
            }
            if (float.IsInfinity(pearlEta)) return;
            bool cued = next != null ? next.cued : pendingCued;
            if (!cued && AudioManager.CueDue(pearlEta, TellStyle.TickParryable))
            {
                if (next != null) next.cued = true; else pendingCued = true;
                Game.Audio?.Play("tell_tick", null, 0.8f, 0.03f);
                GameEvents.RaiseStrikeCue(this, false);
            }
            bool glinted = next != null ? next.glinted : pendingGlinted;
            if (!glinted && pearlEta <= CueLead)
            {
                if (next != null) next.glinted = true; else pendingGlinted = true;
                Vector3 at = next != null ? next.Position : Snout;
                Game.FX?.FlashLight(at, TellStyle.Gold, 6f, 4f, 0.25f);
                Game.FX?.BladeGlint(at, false);
            }
        }

        /// <summary>¿El paso tiene una perla por salir hacia Kaito? (cuánto falta, a qué velocidad y con qué radio de golpe)</summary>
        bool PendingPearl(AttackDef a, out float wait, out float speed, out float radius)
        {
            wait = 0f; speed = FanSpeed; radius = 1f;
            switch (a.special)
            {
                case "pearls": if (specialFired) return false; wait = tl.T - stepClock; break;
                case "rally": if (specialFired) return false; wait = tl.T - stepClock; speed = RallySpeed; radius = 1.2f; break;
                case "storm":
                    if (stormFired >= Mathf.RoundToInt(a.specialParam)) return false;
                    wait = tl.T + stormFired * StormGap - stepClock; speed = StormSpeed; break;
                default: return false;
            }
            wait = Mathf.Max(0f, wait);
            return true;
        }

        Vector3 AimFrom(Vector3 from)
        {
            Vector3 d = target != null ? (target.transform.position - from).Flat() : transform.forward;
            return d.sqrMagnitude > 0.01f ? d.normalized : transform.forward;
        }

        void TickPearls(AttackDef a, bool storm)
        {
            int n = Mathf.Max(1, Mathf.RoundToInt(a.specialParam));
            if (!storm)
            {
                if (specialFired || stepClock < tl.T) return;
                specialFired = true;
                Vector3 s = Snout, aim = AimFrom(s);
                for (int i = 0; i < n; i++)
                {
                    Vector3 d = Quaternion.Euler(0f, (i - (n - 1) * 0.5f) * FanSpread, 0f) * aim;
                    var w = WaterPearl.Spawn(this, WaterPearl.Mode.Fan, s, d, FanSpeed, 0.7f, a.damage, a.knockback);
                    // la del medio es la que viene a Kaito: hereda el aviso que ya sonó mientras salía
                    if (i == n / 2) { w.cued = pendingCued; w.glinted = pendingGlinted; }
                }
                WaterSplash.Spray(s, transform.forward + Vector3.up * 0.3f, 8, 5f, 0.18f);
                return;
            }
            // tormenta: de a una cada 0.15 s, cada una a donde está Kaito; el paso espera a que salgan todas
            if (stepClock >= tl.T && !held && stormFired < n) { held = true; anim.SetSpeed(1f); }
            while (stormFired < n && stepClock >= tl.T + stormFired * StormGap)
            {
                Vector3 s = Snout;
                var w = WaterPearl.Spawn(this, WaterPearl.Mode.Fan, s, AimFrom(s), StormSpeed, 0.6f, a.damage, a.knockback);
                w.cued = pendingCued; w.glinted = pendingGlinted;
                pendingCued = pendingGlinted = false;
                stormFired++;
            }
            if (stormFired >= n) held = false;
        }

        // ------------------------------------------------------------------ peloteo (Tama-asobi)
        /// <summary>El koi todavía devuelve la perla (si no, la próxima le pega a él).</summary>
        public bool RallyWillReturn => rallyReturns > 0 && IsAlive && State == EnemyState.Attack;

        void TickRally(AttackDef a, float dt)
        {
            if (!specialFired)
            {
                if (stepClock < tl.T) return;
                specialFired = true;
                Vector3 s = Snout;
                rallyPearl = WaterPearl.Spawn(this, WaterPearl.Mode.Rally, s, AimFrom(s), RallySpeed, 1.6f, a.damage, a.knockback);
                rallyPearl.cued = pendingCued; rallyPearl.glinted = pendingGlinted;
                // devoluciones antes de fallar: cada parry perfecto le saca una
                rallyReturns = CurrentPhase >= 2 ? Random.Range(3, 6) : Random.Range(2, 5);
                rallyStart = Time.time;
                held = true;
                anim.SetSpeed(1f);
                return;
            }
            if (!held || rallyPearl == null) return;
            Face(rallyPearl.Position, 2f, dt);
            if (Time.time - rallyStart > 14f) rallyPearl.Burst(true);
        }

        /// <summary>La perla viene al hocico: arranca el revés (el golpe sale 0.17 s después).</summary>
        public void OnRallyIncoming()
        {
            anim.Play("Return", 0.05f);
            anim.SetSpeed(1f);
        }

        public void OnRallyBatted(WaterPearl p)
        {
            rallyReturns--;
            Game.Audio?.Play("pearl_ping", p.Position, 0.9f, 0.05f);
            WaterSplash.Flop(p.Position, 0.4f);
        }

        public void OnRallyPerfect()
        {
            if (rallyReturns > 0) rallyReturns--;
        }

        /// <summary>Se le escapó: la perla le pega, se le quiebra la postura y queda varado (el premio del peloteo).</summary>
        public void OnRallyMissed(WaterPearl p)
        {
            rallyPearl = null;
            held = false;
            if (!IsAlive) return;
            Vector3 dir = (transform.position - p.Position).Flat();
            dir = dir.sqrMagnitude > 0.01f ? dir.normalized : -transform.forward;
            // primero la postura (queda varado) y después el daño, que ya entra en la ventana de castigo
            AddImbalance(config.maxImbalance);
            ReceiveHit(new DamageInfo { damage = 30f, kind = AttackKind.Ability, direction = dir, point = p.Position, sourceFaction = Faction.Player, source = Game.Player, attackName = "Tama-asobi" });
            Game.FX?.HitImpact(p.Position, dir, true, false);
            Game.Audio?.Play("hit_heavy", p.Position, 0.9f);
        }

        /// <summary>El peloteo terminó sin que el koi falle (Kaito recibió la perla o se le pasó y reventó en la baranda).</summary>
        public void OnRallyEnded(bool _)
        {
            rallyPearl = null;
            held = false;
        }

        /// <summary>Una perla del abanico devuelta con parry perfecto le pega: daño y postura como un parry de cerca.</summary>
        public void OnPearlReturned(WaterPearl p)
        {
            if (!IsAlive || hidden || airborne || inCinematic) return;
            Vector3 dir = (transform.position - p.Position).Flat();
            dir = dir.sqrMagnitude > 0.01f ? dir.normalized : -transform.forward;
            OnParried(false);
            ReceiveHit(new DamageInfo { damage = 8f, kind = AttackKind.Ability, direction = dir, point = p.Position, knockback = 0.2f, sourceFaction = Faction.Player, source = Game.Player, attackName = "Perla devuelta" });
            Game.FX?.HitImpact(p.Position, dir, true, false);
            Game.Audio?.Play("hit_heavy", p.Position, 0.8f);
        }

        // ================================================================== chorro y chorro barrido
        float JetLength(AttackDef a) => a.specialParam > 0f ? a.specialParam : 11f;
        Vector3 Ground(Vector3 p) { p.y = DeckHeight; return p; }

        void TickJet(AttackDef a, float dt, bool sweep)
        {
            float toFire = tl.T - stepClock;
            float len = JetLength(a);
            if (!jetLocked)
            {
                if (toFire > (sweep ? SweepLock : JetLock))
                {
                    // apunta: una línea tenue de agua (todavía no es la zona roja: se mueve con él)
                    if (target != null) Face(target.transform.position, 1.4f, dt);
                    Vector3 o = Ground(Snout);
                    if (aimMark == null) aimMark = marks.Lane(o, transform.forward, len, 0.6f, AimColor);
                    else aimMark.Aim(o, transform.forward, len);
                    aimMark.SetAlpha(0.35f);
                    aimMark.Progress = 1f;
                }
                else LockJet(a, sweep, len);
            }
            if (sweep && jetLocked)
            {
                UpdateSweepMarks(toFire);
                if (!jetSwung && AudioManager.CueDue(toFire, TellStyle.SwingHeavy)) { jetSwung = true; Game.Audio?.Play(a.sfx, transform.position, 0.9f, 0.05f); }
                TickRedCue(ref sweepCue, SweepEta(), target != null ? target.transform.position : jetOrigin);
            }
            bool firing = jetLocked && stepNorm >= a.activeStart && stepNorm <= a.activeEnd;
            if (firing)
            {
                Vector3 d = sweep ? SweepDir() : jetDir;
                beam.Fire(jetOrigin, d, len, CurrentPhase >= 1 ? 0.5f : 0f, DeckHeight);
                if (!jetFired) { jetFired = true; Game.Camera?.Shake(0.35f); }
                if (!stepHit && target != null && InBeam(jetOrigin, d, len, target.transform.position))
                {
                    stepHit = true;
                    HitPlayer(a, jetOrigin);
                }
            }
            else if (jetFired || stepNorm > a.activeEnd) beam.Stop();
        }

        /// <summary>Se traba: la línea queda fija (el chorro va recto) y se pinta roja. El barrido dibuja su abanico.</summary>
        void LockJet(AttackDef a, bool sweep, float len)
        {
            jetLocked = true;
            jetOrigin = Snout;
            jetDir = transform.forward.Flat().normalized;
            if (aimMark != null) { marks.Finish(aimMark, false); aimMark = null; }
            Game.Audio?.Play("lock", jetOrigin, 0.9f, 0.02f);
            if (!sweep) return;
            sweepSign = Random.value < 0.5f ? -1f : 1f;
            // el barrido dura 0.6 s de tramo activo (el clip se estira para acompañarlo)
            tl.sustain = SweepTime;
            for (int i = 0; i < SweepLanes; i++)
            {
                float ang = SweepAngle(i / (float)(SweepLanes - 1));
                sweepMarks[i] = marks.Lane(Ground(jetOrigin), Quaternion.Euler(0f, ang, 0f) * jetDir, len, 1.9f, TellStyle.Crimson);
            }
            RedWarn(Ground(jetOrigin) + jetDir * len * 0.5f);
        }

        float SweepAngle(float s) => Mathf.Lerp(-SweepHalf, SweepHalf, s) * sweepSign;

        void ClearJetMarks()
        {
            jetLocked = false;
            if (aimMark != null) { marks.Finish(aimMark, false); aimMark = null; }
            for (int i = 0; i < sweepMarks.Length; i++) { marks.Finish(sweepMarks[i], false); sweepMarks[i] = null; }
        }

        Vector3 SweepDir()
        {
            float s = Mathf.Clamp01((stepClock - tl.T) / SweepTime);
            return Quaternion.Euler(0f, SweepAngle(s), 0f) * jetDir;
        }

        /// <summary>El abanico se llena primero del lado donde arranca el barrido (dice para dónde va); cada rayo se apaga
        /// cuando el chorro lo pasa.</summary>
        void UpdateSweepMarks(float toFire)
        {
            float warn = 1f - Mathf.Clamp01((toFire - TellStyle.BiasUnblockable) / (SweepLock - TellStyle.BiasUnblockable));
            float s = toFire <= 0f ? Mathf.Clamp01(-toFire / SweepTime) : -1f;
            for (int i = 0; i < SweepLanes; i++)
            {
                var m = sweepMarks[i];
                if (m == null) continue;
                float order = i / (float)(SweepLanes - 1);
                m.Progress = Mathf.Clamp01(warn * 1.3f - order * 0.3f);
                if (s >= order) { marks.Finish(m, true); sweepMarks[i] = null; }
            }
        }

        /// <summary>Cuándo el chorro barrido llega a Kaito (infinito si está fuera del abanico o ya pasó).</summary>
        float SweepEta()
        {
            var a = CurrentAttack;
            if (!jetLocked || target == null || stepHit || a == null) return float.PositiveInfinity;
            Vector3 to = (target.transform.position - jetOrigin).Flat();
            float dist = to.magnitude;
            if (dist > JetLength(a) + 1f) return float.PositiveInfinity;
            float ang = Vector3.SignedAngle(jetDir, to, Vector3.up) * sweepSign;
            float margin = Mathf.Atan2(JetHalf + target.Radius, Mathf.Max(0.5f, dist)) * Mathf.Rad2Deg;
            if (ang < -SweepHalf - margin || ang > SweepHalf + margin) return float.PositiveInfinity;
            float sHit = Mathf.Clamp01((ang - margin + SweepHalf) / (2f * SweepHalf));
            float t = tl.T + sHit * SweepTime - stepClock;
            return t < -0.05f ? float.PositiveInfinity : Mathf.Max(0f, t);
        }

        static bool InBeam(Vector3 o, Vector3 d, float len, Vector3 p)
        {
            Vector3 to = (p - o).Flat();
            float along = Vector3.Dot(to, d);
            if (along < -0.5f || along > len + 0.5f) return false;
            return Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, d))) <= JetHalf + 0.35f;
        }

        // ================================================================== geometría de los saltos
        Vector3 OnDeck(Vector3 p, float r)
        {
            Vector3 d = (p - Center).Flat();
            if (d.magnitude > r) d = d.normalized * r;
            return Center + d;
        }

        /// <summary>Dónde va a estar Kaito en 'seconds' si sigue como va (sobre la plataforma).</summary>
        Vector3 Predict(float seconds)
        {
            if (target == null) return Center;
            return OnDeck(target.transform.position + target.Velocity.Flat() * seconds, DeckRoom);
        }

        float LocalX(Vector3 p) => Vector3.Dot((p - Center).Flat(), East);
        float LocalZ(Vector3 p) => Vector3.Dot((p - Center).Flat(), North);

        /// <summary>Rumbo desde el norte (grados, positivo hacia el este) de un punto alrededor de la arena.</summary>
        float Bearing(Vector3 p) => Vector3.SignedAngle(North, (p - Center).Flat(), Vector3.up);

        Vector3 RingPoint(float bearing)
        {
            Vector3 p = Center + Quaternion.AngleAxis(bearing, Vector3.up) * North * WaterRing;
            p.y = WaterHeight;
            return p;
        }

        static bool OnScreen(Vector3 p, float margin = 0.08f)
        {
            var cam = Game.Camera != null ? Game.Camera.Cam : Camera.main;
            if (cam == null) return true;
            Vector3 v = cam.WorldToViewportPoint(p);
            return v.z > 0f && v.x > margin && v.x < 1f - margin && v.y > margin && v.y < 1f - margin;
        }

        /// <summary>
        /// Punto del anillo de agua (norte, este u oeste: el sur queda debajo del cuadro) más cercano a 'near' que la cámara
        /// ve. 'awayFromKaito': para zambullirse se tira del lado contrario a Kaito (no salta por encima de él).
        /// </summary>
        Vector3 PickRing(Vector3 near, bool awayFromKaito)
        {
            float best = float.MaxValue;
            Vector3 res = RingPoint(0f);
            for (float b = -110f; b <= 110.1f; b += 10f)
            {
                Vector3 p = RingPoint(b);
                float score = CombatMath.FlatDistance(p, near);
                if (!OnScreen(p + Vector3.up * 1.5f)) score += 40f;
                if (awayFromKaito && target != null)
                {
                    Vector3 toK = (target.transform.position - Center).Flat();
                    if (toK.sqrMagnitude > 0.25f) score += 4f * Vector3.Dot((p - Center).Flat().normalized, toK.normalized);
                }
                if (score < best) { best = score; res = p; }
            }
            return res;
        }

        void TurnTo(Vector3 p, float rate)
        {
            Vector3 d = (p - transform.position).Flat();
            if (d.sqrMagnitude < 0.01f) return;
            transform.rotation = CombatMath.Damp(transform.rotation, Quaternion.LookRotation(d), rate, Time.deltaTime);
        }

        void BeginSequence()
        {
            held = true;
            wideFrame = true;
            arenaRadius = 60f;   // sale del borde de la plataforma: el tope de la arena lo traía de vuelta cada frame
            Stop();
        }

        void EndSequence()
        {
            held = false;
            wideFrame = false;
            if (baseArenaRadius > 0f) arenaRadius = baseArenaRadius;
            ghost?.Show(false);
            if (hidden) SetHidden(false);
            if (airborne) SetAirborne(false);
            if (agent != null && !agent.enabled) RestoreAgent(transform.position);
            move = null;
        }

        HitResult HitKaito(float damage, float knockback, Vector3 from, string attackName)
        {
            if (target == null || !target.IsAlive) return HitResult.Ignored;
            stepHit = true;
            Vector3 dir = (target.transform.position - from).Flat();
            var info = new DamageInfo
            {
                damage = damage, kind = AttackKind.Unblockable, direction = dir.sqrMagnitude > 0.01f ? dir.normalized : transform.forward,
                point = target.AimPoint, knockback = knockback, sourceFaction = Faction.Enemy, source = this, attackName = attackName,
            };
            return target.ReceiveHit(info);
        }

        /// <summary>Del piso (o del agua) al agua: se enrosca hacia el punto (0.27 s) y salta en arco. 'hide' = se sumerge.</summary>
        IEnumerator Leap(Vector3 exit, bool hide)
        {
            anim.Play("Dive", 0.1f);
            anim.SetSpeed(1f);
            for (float t = 0f; t < 0.27f; t += Time.deltaTime) { TurnTo(exit, 10f); yield return null; }
            Vector3 from = transform.position;
            float leap = Mathf.Clamp(CombatMath.FlatDistance(from, exit) / 11f, 0.45f, 0.85f);
            // el tramo del salto del clip (cuadros 8-22) dura lo que dura el arco
            anim.SetSpeed(14f / 30f / leap);
            SetAirborne(true);
            for (float t = 0f; t < leap; t += Time.deltaTime)
            {
                float s = t / leap;
                Vector3 q = Vector3.Lerp(from, exit, s);
                q.y = Mathf.Lerp(from.y, exit.y, s) + 4f * 1.8f * s * (1f - s);
                transform.position = q;
                TurnTo(exit, 10f);
                yield return null;
            }
            transform.position = exit;
            anim.SetSpeed(1f);
            WaterSplash.Column(exit, 1.6f, 4f);
            Game.Audio?.Play("water_splash", exit, 1f);
            if (hide) SetHidden(true);
        }

        /// <summary>
        /// Salto en parábola de 'from' a 'land' ('air' s, 'apex' m sobre el piso). Con daño: disco rojo de 'radius' en el
        /// lugar del impacto desde que despega (se llena hasta 0.16 s antes), taiko, hyōshigi y el golpe al caer.
        /// </summary>
        IEnumerator Breach(Vector3 from, Vector3 land, float air, float apex, float damage, float knockback, float radius)
        {
            SetHidden(false);
            SetAirborne(true);
            transform.position = from;
            Vector3 fwd = (land - from).Flat();
            fwd = fwd.sqrMagnitude > 0.01f ? fwd.normalized : transform.forward.Flat().normalized;
            transform.rotation = Quaternion.LookRotation(fwd);
            anim.Play("BreachAir", 0.05f);
            anim.SetSpeed(33f / 30f / air);
            bool damaging = damage > 0f;
            // ápice de hasta 'apex' m, más bajo si la cabeza saldría por arriba del cuadro: con la cámara mirando al norte,
            // un salto de 5 m desde el agua del norte dejaba la cabeza afuera (simulado: hasta 14 % sobre el borde)
            Vector3 mid = Vector3.Lerp(from, land, 0.5f);
            while (apex > 3f && !OnScreen(mid + Vector3.up * (apex + 3.4f), 0.03f)) apex -= 0.5f;
            MizuchiMarks.Mark disc = null;
            if (damaging)
            {
                landPlanned = true; landPoint = land; landRadius = radius; impactTime = Time.time + air;
                leapCue = default;
                disc = marks.Disc(land, radius);
                RedWarn(land);
            }
            for (float t = 0f; t < air; t += Time.deltaTime)
            {
                float s = t / air;
                Vector3 q = Vector3.Lerp(from, land, s);
                q.y = Mathf.Lerp(from.y, land.y, s) + 4f * apex * s * (1f - s);
                transform.position = q;
                if (disc != null)
                {
                    disc.Progress = Mathf.Clamp01(t / Mathf.Max(0.05f, air - TellStyle.BiasUnblockable));
                    TickRedCue(ref leapCue, impactTime - Time.time, land);
                }
                yield return null;
            }
            transform.position = land;
            anim.SetSpeed(1f);
            SetAirborne(false);
            RestoreAgent(land);
            landPlanned = false;
            marks.Finish(disc, true);
            Game.Camera?.Shake(damaging ? 0.8f : 0.45f);
            WaterSplash.Beached(land, fwd, damaging ? 1f : 0.8f);
            Game.Audio?.Play("slam", land, damaging ? 1f : 0.7f);
            if (damaging && target != null && CombatMath.FlatDistance(target.transform.position, land) <= radius + target.Radius)
                HitKaito(damage, knockback, land, "Salto del Dragón");
        }

        // ================================================================== salto del dragón
        /// <summary>
        /// Se zambulle por la baranda más cercana que se ve, nada bajo el agua (sombra y estela) hasta el punto del anillo
        /// más cercano a Kaito, el agua hierve 0.35 s y salta: 1.1 s de vuelo con el disco rojo (3.6 m) sobre donde va a
        /// estar Kaito. Queda varado 1.6 s.
        /// </summary>
        IEnumerator DiveRoutine(AttackDef a)
        {
            BeginSequence();
            Vector3 exit = PickRing(transform.position, true);
            yield return Leap(exit, true);
            if (SeqBroken) { EndSequence(); yield break; }
            float b0 = Bearing(exit);
            float b1 = Bearing(PickRing(target.transform.position, false));
            float arc = Mathf.Abs(b1 - b0) * Mathf.Deg2Rad * WaterRing;
            float travel = Mathf.Clamp(arc / 12f, 0.6f, 1.4f);
            // los dos rumbos están entre -110° y 110°: se nada por el norte (por el sur sería fuera de cuadro)
            float sense = b1 >= b0 ? 1f : -1f;
            ghost.Show(true);
            for (float t = 0f; t < travel; t += Time.deltaTime)
            {
                float bb = Mathf.Lerp(b0, b1, Mathf.SmoothStep(0f, 1f, t / travel));
                Vector3 p = RingPoint(bb);
                Vector3 tangent = (RingPoint(bb + sense * 3f) - p).Flat();
                transform.position = p;
                if (tangent.sqrMagnitude > 1e-4f) transform.rotation = Quaternion.LookRotation(tangent);
                ghost.Swim(p, tangent, WaterHeight);
                yield return null;
            }
            // hierve donde va a salir: el primer "por acá viene"
            Vector3 emerge = RingPoint(b1);
            for (float t = 0f; t < 0.35f; t += 0.07f)
            {
                WaterSplash.Flop(emerge + Random.insideUnitSphere.Flat() * 1.2f, 0.8f);
                ghost.Swim(emerge, transform.forward, WaterHeight);
                yield return new WaitForSeconds(0.07f);
            }
            ghost.Show(false);
            if (SeqBroken) { EndSequence(); yield break; }
            Vector3 land = Predict(0.4f);
            WaterSplash.Column(emerge, 1.8f, 5f);
            Game.Audio?.Play("water_splash", emerge, 1f);
            yield return Breach(emerge, land, 1.1f, 5f, a.damage, a.knockback, a.specialParam > 0f ? a.specialParam : 3.6f);
            EndSequence();
            if (IsAlive && State == EnemyState.Attack) Beach(1.6f, true);
        }

        // ================================================================== ola de la cascada
        bool InTrough(float x) => Mathf.Abs(x - gap0) <= GapHalf || Mathf.Abs(x - gap1) <= GapHalf;

        float WaveEta()
        {
            if (!waveArmed || target == null) return float.PositiveInfinity;
            Vector3 k = target.transform.position;
            if (InTrough(LocalX(k))) return float.PositiveInfinity;
            float zk = LocalZ(k);
            float toLaunch = waveLaunch - Time.time;
            float front = toLaunch > 0f ? WaveStartZ : WaveStartZ + WaveSpeed * toLaunch;
            float dist = front - (zk + 0.6f);
            if (dist < -1.2f) return float.PositiveInfinity;
            return Mathf.Max(0f, toLaunch) + Mathf.Max(0f, dist) / WaveSpeed;
        }

        /// <summary>
        /// Dos canales: uno a 1.5-3.5 m de Kaito (hay que moverse hasta 2 m: 0.65 s con la reacción, y el aviso da 1.2 s o
        /// más) y el otro a 8-10 m de ese (5 m o más de borde a borde).
        /// </summary>
        void PickGaps()
        {
            float kx = target != null ? Mathf.Clamp(LocalX(target.transform.position), -8f, 8f) : 0f;
            float side = Mathf.Abs(kx) > 5f ? -Mathf.Sign(kx) : (Random.value < 0.5f ? -1f : 1f);
            gap0 = Mathf.Clamp(kx + side * Random.Range(1.5f, 3.5f), -7f, 7f);
            float sep = Random.Range(8f, 10f);
            float r = gap0 + sep, l = gap0 - sep;
            bool okR = r <= 8.5f, okL = l >= -8.5f;
            gap1 = okR && okL ? (Random.value < 0.5f ? r : l) : okR ? r : okL ? l : (gap0 > 0f ? gap0 - 8f : gap0 + 8f);
            if (gap1 < gap0) { float t = gap0; gap0 = gap1; gap1 = t; }
        }

        /// <summary>
        /// Franja roja al norte (por donde entra la ola) cortada por los dos canales, y los canales pintados de agua clara
        /// de punta a punta de la plataforma: "rojo = la ola, celeste = por acá no pega".
        /// </summary>
        void BuildBand()
        {
            float[] edges = { -BandHalfWidth, gap0 - GapHalf, gap0 + GapHalf, gap1 - GapHalf, gap1 + GapHalf, BandHalfWidth };
            for (int i = 0; i < 3; i++)
            {
                float x0 = Mathf.Max(-BandHalfWidth, edges[i * 2]), x1 = Mathf.Min(BandHalfWidth, edges[i * 2 + 1]);
                bandMarks[i] = null;
                if (x1 - x0 < 0.3f) continue;
                Vector3 from = Center + North * BandNear + East * ((x0 + x1) * 0.5f);
                bandMarks[i] = marks.Lane(from, -North, BandDepth, x1 - x0, TellStyle.Crimson);
            }
            float[] gaps = { gap0, gap1 };
            for (int i = 0; i < 2; i++)
            {
                Vector3 from = Center + North * BandNear + East * gaps[i];
                laneMarks[i] = marks.Lane(from, -North, BandNear + RailRadius, GapHalf * 2f, AimColor);
                laneMarks[i].SetAlpha(0.45f);
                laneMarks[i].Progress = 1f;
            }
        }

        void ClearWave()
        {
            waveArmed = false;
            waveFx?.Hide();
            foreach (var m in bandMarks) marks?.Finish(m, false);
            foreach (var m in laneMarks) marks?.Finish(m, false);
        }

        /// <summary>
        /// Salta detrás de la baranda norte, asoma y golpea el agua con el abanico: la cascada crece, una franja roja
        /// marca el borde norte 1.2 s y una ola curva cruza la plataforma a 8 m/s con dos canales de espuma baja donde no
        /// pega. Se escapa yendo a un canal (hay uno a 4 m o menos) o pasándola con dash. El koi vuelve 0.5 s después.
        /// </summary>
        IEnumerator WaveRoutine(AttackDef a)
        {
            BeginSequence();
            // pegado a la baranda norte (1 m más adentro que el anillo): parado sobre la cola, con Kaito en la baranda sur
            // la cabeza quedaba justo arriba del cuadro
            Vector3 slam = Center + North * (WaterRing - 0.8f);
            slam.y = WaterHeight;
            yield return Leap(slam, true);
            yield return new WaitForSeconds(0.2f);
            if (SeqBroken) { EndSequence(); yield break; }
            transform.SetPositionAndRotation(slam, Quaternion.LookRotation(-North));
            SetHidden(false);
            anim.Play("GreatWave", 0.05f);
            anim.SetSpeed(1f);
            WaterSplash.Column(slam, 2f, 4f);
            Game.Audio?.Play("wave_rise", slam, 1f);
            yield return new WaitForSeconds(17f / 30f);   // el abanico pega el agua en el cuadro 17
            if (Falls != null) Falls.Surge(1.7f, 2.5f);
            WaterSplash.Column(slam + North * 2.5f, 2.6f, 7f);
            Game.Audio?.Play("water_splash", slam, 1f);
            Game.Camera?.Shake(0.6f);
            PickGaps();
            waveFx.Build(gap0, gap1, GapHalf);
            waveArmed = true;
            waveLaunch = Time.time + BandWarn;
            waveCue = default;
            BuildBand();
            RedWarn(Center + North * (BandNear - BandDepth * 0.5f));
            float sinkAt = Time.time + 0.45f;
            bool sunk = false;
            while (Time.time < waveLaunch)
            {
                if (SeqBroken) { ClearWave(); EndSequence(); yield break; }
                float k = 1f - (waveLaunch - Time.time) / BandWarn;
                foreach (var m in bandMarks) if (m != null) m.Progress = Mathf.Clamp01(k * BandWarn / (BandWarn - TellStyle.BiasUnblockable));
                if (!sunk && Time.time >= sinkAt) { sunk = true; anim.Play("Dive", 0.15f, 14f / 24f); }
                TickRedCue(ref waveCue, WaveEta(), target.transform.position);
                yield return null;
            }
            SetHidden(true);
            WaterSplash.Flop(slam, 1f);
            for (int i = 0; i < bandMarks.Length; i++) { marks.Finish(bandMarks[i], true); bandMarks[i] = null; }
            // rueda
            bool hitDone = false;
            float passedAt = -1f, rippleTimer = 0f;
            while (true)
            {
                float t = Time.time - waveLaunch;
                float front = WaveStartZ - WaveSpeed * t;
                if (front < -RailRadius - 3f) break;
                float vis = Mathf.Clamp01(t / 0.25f) * Mathf.Clamp01((front + RailRadius + 3f) / 2.5f);
                waveFx.Place(Center + North * front, -North, vis);
                if (target != null && target.IsAlive)
                {
                    Vector3 kp = target.transform.position;
                    float zk = LocalZ(kp);
                    if (!hitDone && Mathf.Abs(zk - front) <= 0.6f && !InTrough(LocalX(kp)))
                    {
                        hitDone = true;
                        HitKaito(a.damage, a.knockback, kp + North, "Ola de la Cascada");
                    }
                    if (passedAt < 0f && front < zk - 0.6f) passedAt = Time.time;
                    TickRedCue(ref waveCue, WaveEta(), kp);
                }
                rippleTimer -= Time.deltaTime;
                if (rippleTimer <= 0f && Falls != null && Falls.Flood != null && Mathf.Abs(front) < RailRadius)
                {
                    rippleTimer = 0.15f;
                    Falls.Flood.Ripple(Center + North * front + East * Random.Range(-5f, 5f));
                }
                yield return null;
            }
            waveFx.Hide();
            waveArmed = false;
            for (int i = 0; i < laneMarks.Length; i++) { marks.Finish(laneMarks[i], false); laneMarks[i] = null; }
            if (passedAt > 0f && passedAt + 0.5f > Time.time) yield return new WaitForSeconds(passedAt + 0.5f - Time.time);
            if (!IsAlive) yield break;
            // vuelve a la plataforma (sin daño), lejos de Kaito
            Vector3 land = Center + North * 3.5f;
            if (target != null && CombatMath.FlatDistance(land, target.transform.position) < 3.5f)
                land = target.transform.position + (land - target.transform.position).Flat().normalized * 3.5f;
            land = OnDeck(land, 6f);
            WaterSplash.Column(slam, 1.8f, 5f);
            yield return Breach(slam, land, 1.0f, 3.5f, 0f, 0f, 0f);
            EndSequence();
            if (IsAlive && State == EnemyState.Attack) ComboEnd();
        }

        // ================================================================== pilares
        bool PillarThreatens(int i) => target != null && !pillarDone[i] && CombatMath.FlatDistance(target.transform.position, pillarAt[i]) <= PillarRadius + target.Radius + 0.5f;

        int NextPillarThreat()
        {
            int best = -1;
            for (int i = 0; i < pillarCount; i++)
                if (PillarThreatens(i) && (best < 0 || pillarImpact[i] < pillarImpact[best])) best = i;
            return best;
        }

        float PillarEta()
        {
            int i = NextPillarThreat();
            if (i >= 0) return Mathf.Max(0f, pillarImpact[i] - Time.time);
            return landPlanned ? Mathf.Max(0f, impactTime - Time.time) : float.PositiveInfinity;
        }

        void PlacePillar(int i)
        {
            Vector3 c = i == 0 && target != null ? target.transform.position : Predict(0.6f);
            // a 3 m o más de los anteriores: entre pilar y pilar siempre queda por dónde salir
            for (int j = 0; j < i; j++)
            {
                Vector3 d = (c - pillarAt[j]).Flat();
                if (d.magnitude >= 3f) continue;
                if (d.sqrMagnitude < 0.01f) d = Quaternion.Euler(0f, Random.Range(0f, 360f), 0f) * Vector3.forward;
                c = pillarAt[j] + d.normalized * 3f;
            }
            c = OnDeck(c, 8.6f);
            pillarAt[i] = c;
            pillarImpact[i] = Time.time + PillarWarn;
            pillarDone[i] = pillarDropped[i] = false;
            pillarCue[i] = default;
            pillarMark[i] = marks.Disc(c, PillarRadius);
            Game.Audio?.Play("pillar_fall", c, 0.9f, 0.05f);
        }

        void CrashPillar(int i, AttackDef a)
        {
            pillarDone[i] = true;
            marks.Finish(pillarMark[i], true);
            pillarMark[i] = null;
            Vector3 c = pillarAt[i];
            WaterSplash.Column(c, PillarRadius, 3.5f);
            Game.Camera?.Shake(0.4f);
            Game.FX?.FlashLight(c + Vector3.up * 1.5f, new Color(0.66f, 0.9f, 1f), 8f, 8f, 0.3f);
            Game.Audio?.Play("water_splash", c, 0.9f);
            if (target != null && CombatMath.FlatDistance(target.transform.position, c) <= PillarRadius + target.Radius)
                HitKaito(a.damage, a.knockback, c, "Pilar de agua");
        }

        void ClearPillars()
        {
            for (int i = 0; i < pillarFx.Length; i++) { pillarFx[i]?.Hide(); marks?.Finish(pillarMark[i], false); pillarMark[i] = null; }
            pillarCount = 0;
        }

        /// <summary>
        /// Se para en la plataforma y ruge (se le puede pegar: no se interrumpe): cuatro columnas de agua caen del cielo,
        /// la primera donde está Kaito y las demás donde va a estar, a 3 m o más una de otra, cada una con 1.1 s de disco
        /// rojo. Después salta sobre Kaito (disco de 3.6 m) y queda varado.
        /// </summary>
        IEnumerator PillarRoutine(AttackDef a)
        {
            BeginSequence();
            anim.Play("Roar", 0.1f);
            anim.SetSpeed(1f);
            Game.Audio?.Play("koi_roar", transform.position, 1f);
            Game.Audio?.Play("boss_roar", transform.position, 0.6f);
            body?.FlareSeal(2.5f, 1.5f);
            Game.Camera?.Shake(0.35f);
            int n = Mathf.Clamp(Mathf.RoundToInt(a.specialParam), 1, pillarFx.Length);
            pillarCount = 0;
            float t0 = Time.time;
            while (true)
            {
                if (SeqBroken) { ClearPillars(); EndSequence(); yield break; }
                float now = Time.time;
                // rugido en loop (cuadros 14-30) mientras caen
                if (anim.TryNormalizedTime("Roar", out float nt) && nt > 30f / 48f) anim.Play("Roar", 0.08f, 14f / 48f);
                while (pillarCount < n && now >= t0 + 0.35f + pillarCount * PillarGap) PlacePillar(pillarCount++);
                bool pending = pillarCount < n;
                for (int i = 0; i < pillarCount; i++)
                {
                    if (pillarDone[i]) continue;
                    pending = true;
                    float left = pillarImpact[i] - now;
                    if (pillarMark[i] != null) pillarMark[i].Progress = Mathf.Clamp01(1f - (left - TellStyle.BiasUnblockable) / (PillarWarn - TellStyle.BiasUnblockable));
                    if (!pillarDropped[i] && left <= PillarFall) { pillarDropped[i] = true; pillarFx[i].Drop(pillarAt[i], PillarRadius, Mathf.Max(0.05f, left), DeckHeight); }
                    if (PillarThreatens(i)) TickRedCue(ref pillarCue[i], left, pillarAt[i]);
                    if (left <= 0f) CrashPillar(i, a);
                }
                if (!pending) break;
                yield return null;
            }
            yield return new WaitForSeconds(0.2f);
            if (SeqBroken) { EndSequence(); yield break; }
            // salto final desde la plataforma
            Vector3 land = Predict(0.4f);
            anim.Play("Dive", 0.1f);
            for (float t = 0f; t < 0.27f; t += Time.deltaTime) { TurnTo(land, 10f); yield return null; }
            yield return Breach(transform.position, land, 1.1f, 5f, a.damage * 1.5f, 3.2f, 3.6f);
            EndSequence();
            if (IsAlive && State == EnemyState.Attack) Beach(1.6f, true);
        }
    }
}
