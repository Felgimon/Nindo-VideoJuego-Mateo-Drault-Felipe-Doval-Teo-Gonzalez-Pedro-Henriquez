using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;

namespace Nindo
{
    /// <summary>
    /// Ōzeki, el Gran Campeón del Bambú: una pelea de sumo de verdad, con la lectura de colores en el centro.
    ///  * HARITE / TSUPPARI (dorado): bofetadas de a una mano en ritmo; se desvían una por una y le van quebrando
    ///    la postura. En la fase 2 la última del tsuppari se demora (prueba el ritmo, no la reacción).
    ///  * AGARRE (rojo): abre los brazos y se cierra adelante; solo el dash lo evita (o salir de adelante a tiempo).
    ///    Mezclado detrás de una bofetada: dorado, rojo.
    ///  * SHIKO (rojo): levanta la pierna al costado y pisa; sale una onda que se abre por el piso a 7 m/s hasta 8 m.
    ///    Se esquiva con dash cuando la onda llega (el anillo se cierra con ella) o corriendo afuera del disco.
    ///  * TACHIAI (rojo): agachado con los puños en el piso y sale disparado. El bambú joven del claro lo frena:
    ///    si Kaito se pone detrás de una mata, el Ōzeki la rompe, tropieza y queda abierto.
    ///  * Fase 2 (50 %): pisa el shiko, la tsuna se enciende en oro y tira SAL al aire (el ritual de purificar el
    ///    dohyō): no pega y queda abierto un momento. Después repite la sal cada tanto como respiro.
    /// Todo pasa por la línea de tiempo del paso (el anillo nunca miente) y las poses salen de SumoPoser.
    /// </summary>
    public class OzekiBoss : Boss, ICameraProfile
    {
        // la onda del shiko: arranca en el borde del cuerpo y se abre a esta velocidad hasta specialParam
        const float WaveSpeed = 7f;
        const float TachiaiMax = 15f;
        const float CrashOpenTime = 2.4f, SaltOpenTime = 1.8f;

        // cámara: un poco más lejos que la de combate (la onda y las embestidas cubren medio claro)
        public float CameraPitch => 0f;
        public float CameraExtraDistance => 2.6f;

        SumoPoser poser;
        int seenPhase;
        bool introBeat, stompPending, forceSalt, saltOpen, crashOpen, crashToasted;
        float savedImbalance;

        // ---------------------------------------------------------------- onda del shiko
        bool waveLive, waveHit, waveOwnedByStep;
        Vector3 waveCenter;
        float waveR, waveMax;
        AttackDef waveAttack;
        ShockRing ring;

        // ---------------------------------------------------------------- tachiai
        bool laneFixed, crashed;
        Vector3 laneO, laneD;
        float laneLen, traveled, crashAt;
        int crashStalk = -1;

        // ---------------------------------------------------------------- tsuna encendida (fase 2)
        LineRenderer tsuna;
        Light aura;
        float tsunaW, tsunaTarget;
        readonly Vector3[] tsunaPts = new Vector3[28];
        static Material tsunaMat;

        // ---------------------------------------------------------------- bambú joven del claro
        class Stalk
        {
            public Transform t;
            public Vector3 pos, scale;
            public Quaternion rot;
            public bool broken;
            public float time;
            public Vector3 fall;
        }
        readonly List<Stalk> stalks = new List<Stalk>();
        const float StalkRadius = 0.7f;

        // ================================================================ setup
        protected override void Start()
        {
            base.Start();
            poser = GetComponentInChildren<SumoPoser>();
            if (poser != null) poser.Posed += UpdateTsuna;
            if (!Defeated) BuildStalks();
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            if (poser != null) poser.Posed -= UpdateTsuna;
            foreach (var s in stalks) if (s.t != null) Destroy(s.t.gameObject);
            if (ring != null) Destroy(ring.gameObject);
        }

        public override void ResetEnemy()
        {
            base.ResetEnemy();
            seenPhase = 0;
            introBeat = stompPending = forceSalt = saltOpen = crashOpen = crashToasted = false;
            waveLive = waveHit = false;
            laneFixed = crashed = false;
            if (ring != null) ring.Hide();
            tsunaW = tsunaTarget = 0f;
            if (tsuna != null) tsuna.enabled = false;
            if (aura != null) aura.enabled = false;
            foreach (var s in stalks) RestoreStalk(s);
        }

        // ================================================================ por frame
        protected override void Update()
        {
            base.Update();
            float dt = Time.deltaTime;
            TickWave(dt);
            TickStalks(dt);
            if (dt <= 0f) return;

            // presentación (y re-presentación al reintentar): el Ōzeki pisa el shiko mientras sale su nombre
            if (!introBeat && State == EnemyState.Scripted && anim.Current == introAnim && poser != null)
            {
                introBeat = true;
                poser.PlayBeat("Shiko D", 0.85f);
                stompPending = true;
            }
            // fase 2: pisa el shiko, se le prende la tsuna y lo primero que hace es tirar la sal
            if (CurrentPhase > seenPhase)
            {
                seenPhase = CurrentPhase;
                // el rugido corta el golpe y su aviso: una onda que siguiera sola pegaría sin anillo
                waveLive = false;
                if (ring != null) ring.Hide();
                tsunaTarget = 1f;
                forceSalt = true;
                Game.FX?.Shockwave(transform.position, 4f, TellStyle.Gold);
                Game.UI?.ShowToast(StoryText.OzekiLine("fase2"), UIFactory.Crimson, 2.4f);
                if (poser != null) { poser.PlayBeat("Shiko I", 0.5f); stompPending = true; }
            }
            if (stompPending && poser != null && poser.BeatEta <= 0f)
            {
                stompPending = false;
                // el pisotón de la presentación y del cambio de fase no pega: suena y tiembla como el de verdad
                Game.FX?.Shockwave(transform.position + transform.forward * 0.6f, 5f, new Color(1f, 0.75f, 0.45f));
                Game.FX?.GroundCrack(transform.position, 3f);
                Game.Camera?.Shake(0.45f);
                Game.Audio?.Play("slam", transform.position, 0.9f);
            }
            tsunaW = Mathf.MoveTowards(tsunaW, tsunaTarget, dt / 0.6f);
        }

        /// <summary>La sal de la fase 2 sale apenas termina el rugido (no espera a que el sorteo la elija).</summary>
        protected override void TickChase(float dt)
        {
            if (forceSalt && Time.time >= nextAttackTime && TargetAlive && Game.Combat != null && Game.Combat.RequestAttackToken(this))
            {
                forceSalt = false;
                pattern = FindPattern("Shio");
                if (pattern != null) { StartAttack(false); return; }
                ReleaseToken();
            }
            base.TickChase(dt);
        }

        bool TargetAlive => target != null && target.IsAlive;

        AttackPattern FindPattern(string n)
        {
            if (config.patterns != null) foreach (var p in config.patterns) if (p != null && p.name == n) return p;
            return null;
        }

        // ================================================================ golpes
        protected override void OnStepStarted(AttackDef a)
        {
            base.OnStepStarted(a);
            laneFixed = crashed = false;
            crashStalk = -1;
            if (a.special == "shiko")
            {
                // la fase activa del clip dura lo que tarda la onda en abrirse: el paso (y el aviso) sigue vivo
                // hasta que la onda pasa por donde está Kaito
                tl.sustain = Mathf.Max(0.1f, (a.specialParam - WaveStart) / WaveSpeed);
                waveOwnedByStep = false;
            }
        }

        float WaveStart => Radius + 0.6f;
        float Contact => Radius + (target != null ? target.Radius : 0.35f) + 0.6f;
        static float TachiaiSpeed(AttackDef a) => a.specialParam > 0f ? a.specialParam : 13f;

        protected override float TellTravel(AttackDef a)
        {
            if (target == null) return 0f;
            switch (a.special)
            {
                case "shiko": return Mathf.Clamp(DistToTarget - WaveStart, 0f, a.specialParam) / WaveSpeed;
                case "tachiai": return Mathf.Max(0f, DistToTarget - Contact) / TachiaiSpeed(a);
                default: return base.TellTravel(a);
            }
        }

        protected override float ComputeStrikeEta(AttackDef a)
        {
            switch (a.special)
            {
                case "shiko": return ShikoEta(a);
                case "tachiai": return TachiaiEta(a);
                default: return base.ComputeStrikeEta(a);
            }
        }

        /// <summary>Cuándo llega la onda a Kaito: lo que falta para el pisotón más el viaje desde el borde del cuerpo
        /// (infinito si Kaito está afuera del disco o la onda ya pasó).</summary>
        float ShikoEta(AttackDef a)
        {
            if (target == null || stepHit) return float.PositiveInfinity;
            if (!specialFired)
            {
                float d = CombatMath.FlatDistance(target.transform.position, transform.position);
                if (d > a.specialParam) return float.PositiveInfinity;
                return Mathf.Max(0f, tl.T - stepClock) + Mathf.Max(0f, d - WaveStart) / WaveSpeed;
            }
            if (!waveLive || waveHit || !waveOwnedByStep) return float.PositiveInfinity;
            float dw = CombatMath.FlatDistance(target.transform.position, waveCenter);
            if (dw < waveR || dw > waveMax) return float.PositiveInfinity;
            return (dw - waveR) / WaveSpeed;
        }

        float TachiaiEta(AttackDef a)
        {
            if (target == null || stepHit || crashed || stepNorm > a.activeEnd) return float.PositiveInfinity;
            float pre = Mathf.Max(0f, tl.T - stepClock), speed = TachiaiSpeed(a);
            // antes de soltarse sigue apuntando: la cuenta es hasta Kaito (si se esconde detrás del bambú, el anillo se
            // deshace recién cuando el carril queda fijo; antes podía salir de atrás de la mata y quedarse sin aviso)
            if (!laneFixed) return pre + Mathf.Max(0f, DistToTarget - Contact) / speed;
            Vector3 dir = laneD;
            Vector3 to = (target.transform.position - transform.position).Flat();
            float along = Vector3.Dot(to, dir) - Contact;
            float lateral = Mathf.Abs(Vector3.Dot(to, Vector3.Cross(Vector3.up, dir)));
            float left = Mathf.Min(laneLen, crashAt) - traveled;
            if (along < -0.5f || lateral > Contact || along > left + 0.3f) return float.PositiveInfinity;
            return pre + Mathf.Max(0f, along) / speed;
        }

        protected override bool HitAreaFor(AttackDef a, out TellArea area)
        {
            switch (a.special)
            {
                case "shiko":
                    area = new TellArea { origin = waveLive && waveOwnedByStep ? waveCenter : transform.position, size = a.specialParam };
                    return true;
                case "tachiai":
                {
                    Vector3 o = transform.position, dir = laneFixed ? laneD : transform.forward.Flat().normalized;
                    float len = laneFixed ? Mathf.Min(laneLen, crashAt + StalkRadius) - traveled
                                          : Mathf.Min(LaneLength(o, dir), StalkAlong(o, dir, TachiaiMax) + StalkRadius);
                    area = new TellArea { lane = true, origin = o, forward = dir, size = Mathf.Max(0.5f, len) + Radius, width = 2f * (Radius + 0.6f) };
                    return true;
                }
                case "grab":
                    area = new TellArea { lane = true, origin = transform.position, forward = transform.forward.Flat().normalized,
                                          size = GrabReach(a), width = 3.2f };
                    return true;
                default: return base.HitAreaFor(a, out area);
            }
        }

        float GrabReach(AttackDef a) => a.range * Mathf.Max(1f, config.scale * 0.85f) + a.lunge;

        protected override void TickSpecial(AttackDef a, float dt)
        {
            switch (a.special)
            {
                case "shiko":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        Stomp(a, true);
                    }
                    // la onda no lo va a alcanzar (pasó, o Kaito salió del disco corriendo): el aviso se deshace, no
                    // destella como un golpe que salió
                    if (!waveHit && float.IsInfinity(ShikoEta(a))) EndTell(TellOutcome.Cancelled);
                    break;

                case "tachiai":
                    TickTachiai(a, dt);
                    break;

                case "grab":
                    if (!stepHit && stepNorm >= a.activeStart && stepNorm <= a.activeEnd && target != null
                        && CombatMath.InArc(transform, target.transform.position, a.range * Mathf.Max(1f, config.scale * 0.85f), a.arc, target.Radius)
                        && Mathf.Abs(target.transform.position.y - transform.position.y) < 2.5f)
                    {
                        stepHit = true;
                        var r = HitPlayer(a, transform.position);
                        if (r == HitResult.Hit) StartCoroutine(Throw());
                    }
                    break;

                case "salt":
                    if (!specialFired && stepNorm >= a.activeStart)
                    {
                        specialFired = true;
                        SaltBurst();
                    }
                    break;

                default:
                    base.TickSpecial(a, dt);
                    break;
            }
        }

        // ---------------------------------------------------------------- shiko
        void Stomp(AttackDef a, bool damaging)
        {
            Vector3 c = transform.position;
            Game.FX?.Shockwave(c, 3f, new Color(1f, 0.75f, 0.45f));
            Game.FX?.GroundCrack(c, 3.5f);
            Game.Camera?.Shake(0.7f);
            Game.Audio?.Play("slam", c, 1f);
            Game.Input?.Rumble(0.9f, 0.6f, 0.3f);
            if (!damaging) return;
            waveLive = true; waveHit = false; waveOwnedByStep = true;
            waveCenter = c; waveR = 0f; waveMax = a.specialParam; waveAttack = a;
            if (ring == null) ring = ShockRing.Create();
            ring.Show(c);
        }

        void TickWave(float dt)
        {
            if (!waveLive) return;
            float prev = waveR;
            // el primer frame cubre de golpe hasta el borde del cuerpo (pisado a quemarropa = el pisotón mismo)
            waveR = prev <= 0f ? WaveStart : Mathf.Min(waveMax, waveR + WaveSpeed * dt);
            if (!waveHit && target != null && target.IsAlive && IsAlive)
            {
                // un solo golpe por onda, en el instante en que el frente cruza a Kaito (como un golpe normal: el dash
                // en el cierre del anillo lo cubre); si se dio vuelta corriendo más rápido que la onda, la cuenta sigue
                float d = CombatMath.FlatDistance(target.transform.position, waveCenter);
                if (d > prev && d <= waveR)
                {
                    waveHit = true;
                    HitPlayer(waveAttack, waveCenter);
                }
            }
            if (ring != null) ring.Tick(waveR, waveMax);
            if (waveR >= waveMax - 1e-3f)
            {
                waveLive = false;
                if (ring != null) ring.Hide();
            }
        }

        // ---------------------------------------------------------------- tachiai
        void TickTachiai(AttackDef a, float dt)
        {
            if (!laneFixed && stepClock >= tl.ReleaseTime) FixLane(a);
            if (!laneFixed || crashed) return;
            if (stepClock >= tl.T && stepNorm <= a.activeEnd && !anim.Frozen)
            {
                float step = TachiaiSpeed(a) * dt;
                if (traveled + step >= crashAt) { MoveBy(laneD * Mathf.Max(0f, crashAt - traveled)); traveled = crashAt; Crash(); return; }
                MoveBy(laneD * step);
                traveled += step;
                if (!stepHit && target != null && CombatMath.FlatDistance(target.transform.position, transform.position) <= Contact)
                {
                    stepHit = true;
                    HitPlayer(a, transform.position);
                }
                Game.FX?.DustTrail(transform.position);
            }
            // se corrió del carril, ya pasó de largo o se escondió detrás del bambú: el aviso se deshace (no fue un golpe)
            if (!stepHit && float.IsInfinity(TachiaiEta(a))) EndTell(TellOutcome.Cancelled);
        }

        void FixLane(AttackDef a)
        {
            laneFixed = true;
            laneO = transform.position;
            laneD = transform.forward.Flat().normalized;
            // pasa de largo 2.5 m; nunca más allá del borde del claro
            float toKaito = target != null ? Vector3.Dot((target.transform.position - laneO).Flat(), laneD) + 2.5f : TachiaiMax;
            laneLen = Mathf.Clamp(toKaito, 3f, Mathf.Min(TachiaiMax, LaneLength(laneO, laneD)));
            crashStalk = StalkIndexAlong(laneO, laneD, laneLen, out float s);
            crashAt = crashStalk >= 0 ? Mathf.Max(0f, s) : float.PositiveInfinity;
            traveled = 0f;
            tl.sustain = Mathf.Min(laneLen, crashAt) / TachiaiSpeed(a);
        }

        /// <summary>Hasta dónde puede correr por esa línea sin salirse de la arena.</summary>
        float LaneLength(Vector3 o, Vector3 d)
        {
            Vector3 c = (o - arenaCenter).Flat();
            float r = Mathf.Max(1f, arenaRadius - 0.5f);
            float b = Vector3.Dot(c, d), disc = b * b - (c.sqrMagnitude - r * r);
            return disc <= 0f ? 0f : Mathf.Max(0f, -b + Mathf.Sqrt(disc));
        }

        /// <summary>
        /// Chocó contra una mata de bambú: la rompe, tropieza y queda abierto (y la postura le suma). El segundo
        /// tachiai de la fase 2 ya no sale.
        /// </summary>
        void Crash()
        {
            crashed = true;
            if (crashStalk >= 0) BreakStalk(stalks[crashStalk], laneD);
            Game.Camera?.Shake(0.55f);
            Game.Input?.Rumble(0.7f, 0.5f, 0.25f);
            Game.Audio?.Play("hit_heavy", transform.position, 1f);
            if (!crashToasted) { crashToasted = true; Game.UI?.ShowToast(StoryText.OzekiLine("choque"), UIFactory.Crimson, 2f); }
            if (!stepHit) EndTell(TellOutcome.Cancelled);
            poser?.PlayBeat("Tropiezo", 0.12f);
            ReleaseToken();
            pattern = null;
            nextAttackTime = Time.time + CrashOpenTime + 0.6f;
            AddImbalance(1.5f);                       // puede quebrarle la postura (y entonces la ventana es la entera)
            if (State == EnemyState.Attack) { crashOpen = true; BecomeExhausted(); }
        }

        IEnumerator Throw()
        {
            // lo levanta y lo tira lejos: el empujón extra va hacia donde mira el Ōzeki y el polvo sale donde cae
            var p = target;
            if (p == null) yield break;
            Vector3 dir = (transform.forward.Flat().normalized + (p.transform.position - transform.position).Flat().normalized).normalized;
            p.Push(dir, 2.5f);
            Game.Camera?.Shake(0.5f);
            yield return new WaitForSeconds(0.32f);
            if (p != null) { Game.FX?.Dust(p.transform.position, 1.6f); Game.Audio?.Play("hit_heavy", p.transform.position, 0.6f); }
        }

        // ---------------------------------------------------------------- sal (fase 2)
        static GameObject saltTpl, splinterTpl, leafTpl;

        static GameObject SaltTemplate()
        {
            if (saltTpl != null) return saltTpl;
            saltTpl = FXFactory.Sparks(new Color(0.95f, 0.97f, 1f), 50, 70, 9f, "OzekiSalt");
            var ps = saltTpl.GetComponent<ParticleSystem>();
            var m = ps.main;
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.6f, 1.1f);
            m.startSize = new ParticleSystem.MinMaxCurve(0.05f, 0.12f);
            m.gravityModifier = 0.9f;
            var sh = ps.shape; sh.angle = 28f;
            return saltTpl;
        }

        void SaltBurst()
        {
            Vector3 hand = poser != null && poser.Ready ? poser.HandR : AimPoint + Vector3.up;
            Vector3 dir = (transform.forward + Vector3.up * 1.1f).normalized;
            var go = Pool.Spawn(SaltTemplate(), hand, Quaternion.LookRotation(dir));
            var ps = go.GetComponent<ParticleSystem>();
            if (ps != null) { ps.Clear(true); ps.Play(true); }
            Pool.Despawn(go, 1.6f);
            RingWave.Spawn(transform.position, 6f, new Color(0.9f, 0.95f, 1f, 0.6f), 0.9f);
            Game.FX?.FlashLight(hand, new Color(0.9f, 0.95f, 1f), 5f, 8f, 0.4f);
            Game.Audio?.Play("checkpoint", transform.position, 0.8f);
        }

        /// <summary>La sal no pega: al terminar queda abierto un momento (sin perder la postura acumulada).</summary>
        protected override void ComboEnd()
        {
            bool salt = pattern != null && pattern.name == "Shio";
            if (!salt) { base.ComboEnd(); return; }
            ReleaseToken();
            pattern = null;
            nextAttackTime = Time.time + SaltOpenTime + Random.Range(config.attackCooldown.x, config.attackCooldown.y);
            saltOpen = true;
            savedImbalance = Imbalance;
            BecomeExhausted();
        }

        protected override void BecomeExhausted()
        {
            bool broken = Imbalance >= config.maxImbalance - 0.01f;
            base.BecomeExhausted();
            // la postura quebrada da la ventana entera; la sal y el choque, una corta
            if (!broken && saltOpen) stateDuration = SaltOpenTime;
            else if (!broken && crashOpen) stateDuration = CrashOpenTime;
        }

        protected override void OnExhaustionEnded()
        {
            if (saltOpen) Imbalance = savedImbalance;
            saltOpen = crashOpen = false;
            base.OnExhaustionEnded();
        }

        // ================================================================ tsuna encendida
        void UpdateTsuna()
        {
            if (poser == null || !poser.Ready) return;
            bool on = tsunaW > 0.001f && IsAlive;
            if (!on)
            {
                if (tsuna != null && tsuna.enabled) { tsuna.enabled = false; aura.enabled = false; }
                return;
            }
            if (tsuna == null) BuildTsuna();
            tsuna.enabled = true; aura.enabled = true;
            Transform t = poser.Torso, h = poser.Head;
            float u = poser.Unit;
            // la soga del kit va a 0.14 u sobre la cabeza del torso, elipse de 1.40 x 1.24 u (build_kits.py sumo_tsuna)
            Vector3 up = (h.position - t.position).normalized;
            Vector3 right = Vector3.ProjectOnPlane(transform.right, up).normalized;
            Vector3 fwd = Vector3.Cross(right, up);
            Vector3 c = t.position + up * (0.14f * u);
            for (int i = 0; i < tsunaPts.Length; i++)
            {
                float ang = i / (float)tsunaPts.Length * Mathf.PI * 2f;
                tsunaPts[i] = c + (right * (Mathf.Cos(ang) * 1.44f) + fwd * (Mathf.Sin(ang) * 1.3f)) * u;
            }
            tsuna.SetPositions(tsunaPts);
            // late lento, como un brasero: se lee encendida sin parpadear
            float pulse = 0.85f + 0.15f * Mathf.Sin(Time.time * 4f);
            Color g = new Color(1f, 0.72f, 0.24f) * (2.6f * pulse * tsunaW); g.a = tsunaW;
            tsuna.startColor = tsuna.endColor = g;
            tsuna.widthMultiplier = 0.17f * u;
            aura.transform.position = c + fwd * (1.6f * u);
            aura.intensity = 2.2f * pulse * tsunaW;
            aura.range = 6f * u;
        }

        void BuildTsuna()
        {
            if (tsunaMat == null) tsunaMat = FXMaterials.MakeUnlitTransparent("Nindo_Tsuna", Color.white, true);
            var go = new GameObject("TsunaEncendida");
            go.transform.SetParent(transform, false);
            tsuna = go.AddComponent<LineRenderer>();
            tsuna.useWorldSpace = true;
            tsuna.loop = true;
            tsuna.positionCount = tsunaPts.Length;
            tsuna.sharedMaterial = tsunaMat;
            tsuna.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            tsuna.receiveShadows = false;
            tsuna.numCornerVertices = 2;
            var lg = new GameObject("AuraTsuna");
            lg.transform.SetParent(transform, false);
            aura = lg.AddComponent<Light>();
            aura.type = LightType.Point;
            aura.color = new Color(1f, 0.74f, 0.36f);
            aura.shadows = LightShadows.None;
        }

        // ================================================================ bambú joven del claro
        /// <summary>
        /// Seis matas de bambú joven (3 m) en un anillo a ~9 m del centro, dejando libre la entrada de Kaito y el lugar
        /// del Ōzeki. No tienen colisión (Kaito pasa entre las cañas); solo frenan el tachiai.
        /// </summary>
        void BuildStalks()
        {
            var prefab = Game.Content != null ? Game.Content.Prop("bamboo_young") : null;
            if (prefab == null) return;
            Vector3 entry = (arenaCenter - transform.position).Flat();
            entry = entry.sqrMagnitude > 0.01f ? entry.normalized : -transform.forward.Flat().normalized;
            float[] angles = { 46f, -46f, 102f, -102f, 150f, -150f };
            float[] radii = { 8.6f, 8.9f, 9.6f, 9.3f, 8.2f, 8.5f };
            var rng = new System.Random(7);
            for (int i = 0; i < angles.Length; i++)
            {
                Vector3 p = arenaCenter + Quaternion.Euler(0f, angles[i], 0f) * entry * Mathf.Min(radii[i], arenaRadius - 2f);
                if (NavMesh.SamplePosition(p, out var hit, 2f, NavMesh.AllAreas)) p = hit.position;
                else if (Physics.Raycast(p + Vector3.up * 8f, Vector3.down, out var rh, 16f, 1, QueryTriggerInteraction.Ignore)) p = rh.point;
                var go = Instantiate(prefab, p, Quaternion.Euler(0f, (float)rng.NextDouble() * 360f, 0f), transform.parent);
                go.name = "BambuJoven" + i;
                go.transform.localScale = go.transform.localScale * 1.3f;
                stalks.Add(new Stalk { t = go.transform, pos = go.transform.position, rot = go.transform.rotation, scale = go.transform.localScale });
            }
        }

        /// <summary>Distancia a lo largo de la línea hasta la primera mata sana que la tapa (infinito si ninguna).</summary>
        float StalkAlong(Vector3 o, Vector3 d, float max)
        {
            StalkIndexAlong(o, d, max, out float s);
            return s;
        }

        int StalkIndexAlong(Vector3 o, Vector3 d, float max, out float stop)
        {
            stop = float.PositiveInfinity;
            int best = -1;
            for (int i = 0; i < stalks.Count; i++)
            {
                var s = stalks[i];
                if (s.broken || s.t == null) continue;
                Vector3 v = (s.pos - o).Flat();
                float along = Vector3.Dot(v, d);
                if (along <= 0f || along > max + Radius) continue;
                float lat = (v - d * along).magnitude;
                if (lat > Radius + StalkRadius) continue;
                // el cuerpo frena al tocar las cañas: su borde contra el borde de la mata
                float at = Mathf.Max(0f, along - Radius * 0.8f - StalkRadius);
                if (at < stop) { stop = at; best = i; }
            }
            return best;
        }

        void BreakStalk(Stalk s, Vector3 dir)
        {
            if (s.broken) return;
            s.broken = true;
            s.time = 0f;
            s.fall = dir;
            Vector3 p = s.pos + Vector3.up * 1.2f;
            Emit(SplinterTemplate(), p, Quaternion.LookRotation(dir + Vector3.up * 0.4f), 1.2f);
            Emit(LeafTemplate(), p + Vector3.up * 1f, Quaternion.identity, 1.8f);
            Game.Audio?.Play("step_wood", s.pos, 1f, 0.15f);
        }

        void TickStalks(float dt)
        {
            foreach (var s in stalks)
            {
                if (!s.broken || s.t == null || !s.t.gameObject.activeSelf) continue;
                s.time += dt;
                // cae como un árbol talado (acelerando) y después se hunde y desaparece: no queda un cadáver de cañas
                float k = Mathf.Clamp01(s.time / 0.55f);
                Vector3 axis = Vector3.Cross(Vector3.up, s.fall);
                s.t.rotation = Quaternion.AngleAxis(82f * k * k, axis) * s.rot;
                if (s.time > 3f)
                {
                    float sink = Mathf.Clamp01((s.time - 3f) / 0.8f);
                    s.t.position = s.pos - Vector3.up * (1.2f * sink);
                    s.t.localScale = s.scale * (1f - sink);
                    if (sink >= 1f) s.t.gameObject.SetActive(false);
                }
            }
        }

        static void RestoreStalk(Stalk s)
        {
            if (s.t == null) return;
            s.broken = false;
            s.t.gameObject.SetActive(true);
            s.t.SetPositionAndRotation(s.pos, s.rot);
            s.t.localScale = s.scale;
        }

        static GameObject SplinterTemplate()
        {
            if (splinterTpl != null) return splinterTpl;
            splinterTpl = FXFactory.Sparks(new Color(0.78f, 0.72f, 0.38f), 16, 24, 8f, "BambooSplinters");
            splinterTpl.GetComponent<ParticleSystemRenderer>().sharedMaterial = FXMaterials.Alpha;
            var m = splinterTpl.GetComponent<ParticleSystem>().main;
            m.startSize = new ParticleSystem.MinMaxCurve(0.06f, 0.14f);
            m.startLifetime = new ParticleSystem.MinMaxCurve(0.3f, 0.7f);
            return splinterTpl;
        }

        static GameObject LeafTemplate()
        {
            if (leafTpl != null) return leafTpl;
            leafTpl = FXFactory.Leaves(new Color(0.42f, 0.66f, 0.3f), new Color(0.68f, 0.82f, 0.38f), 26, 1.2f, 1.5f, "BambooLeaves");
            return leafTpl;
        }

        static void Emit(GameObject tpl, Vector3 pos, Quaternion rot, float life)
        {
            var go = Pool.Spawn(tpl, pos, rot);
            var ps = go.GetComponent<ParticleSystem>();
            if (ps != null) { ps.Clear(true); ps.Play(true); }
            Pool.Despawn(go, life);
        }

#if UNITY_EDITOR || DEVELOPMENT_BUILD
        /// <summary>Pruebas (RunCommand): lo deja con esa vida, p. ej. 0.52 para probar la fase 2 con el próximo golpe.</summary>
        public void DebugSetHealth01(float v) => Health = Mathf.Clamp01(v) * config.maxHealth;
#endif
    }

    /// <summary>
    /// El frente de la onda del shiko: un aro de ancho fijo (0.6 m) que se abre por el piso al ritmo del golpe (el
    /// RingWave del juego se abre frenando y se afina con el radio: no decía dónde estaba el frente).
    /// </summary>
    public class ShockRing : MonoBehaviour
    {
        const int N = 64;
        const float Width = 0.6f;
        Mesh mesh;
        MeshRenderer mr;
        MaterialPropertyBlock mpb;
        readonly Vector3[] verts = new Vector3[N * 2];
        float lastR = -1f;

        public static ShockRing Create()
        {
            var go = new GameObject("OndaShiko");
            var r = go.AddComponent<ShockRing>();
            r.mesh = new Mesh { name = "OndaShiko" };
            r.mesh.MarkDynamic();
            var tri = new int[N * 6];
            var uv = new Vector2[N * 2];
            for (int i = 0; i < N; i++)
            {
                int j = (i + 1) % N;
                tri[i * 6] = i * 2; tri[i * 6 + 1] = j * 2; tri[i * 6 + 2] = i * 2 + 1;
                tri[i * 6 + 3] = i * 2 + 1; tri[i * 6 + 4] = j * 2; tri[i * 6 + 5] = j * 2 + 1;
                uv[i * 2] = new Vector2(0.5f, 0.5f); uv[i * 2 + 1] = new Vector2(0.5f, 0.5f);
            }
            r.Fill(1f);
            r.mesh.uv = uv;
            r.mesh.triangles = tri;
            r.mesh.bounds = new Bounds(Vector3.zero, new Vector3(40f, 2f, 40f));
            go.AddComponent<MeshFilter>().sharedMesh = r.mesh;
            r.mr = go.AddComponent<MeshRenderer>();
            r.mr.sharedMaterial = FXMaterials.Additive;
            r.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.mr.receiveShadows = false;
            r.mpb = new MaterialPropertyBlock();
            go.SetActive(false);
            return r;
        }

        void Fill(float radius)
        {
            float rin = Mathf.Max(0f, radius - Width);
            for (int i = 0; i < N; i++)
            {
                float a = i / (float)N * Mathf.PI * 2f;
                Vector3 d = new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
                verts[i * 2] = d * rin; verts[i * 2 + 1] = d * radius;
            }
            mesh.vertices = verts;
        }

        public void Show(Vector3 center)
        {
            transform.position = center + Vector3.up * 0.08f;
            lastR = -1f;
            gameObject.SetActive(true);
        }

        public void Tick(float radius, float max)
        {
            if (Mathf.Abs(radius - lastR) > 0.01f) { Fill(radius); lastR = radius; }
            // rojo del imparable, aclarándose en el frente; se apaga en el último metro
            float fade = Mathf.Clamp01((max - radius) / 1f);
            Color c = Color.Lerp(TellStyle.Crimson, new Color(1f, 0.75f, 0.45f), 0.35f) * 1.6f;
            c.a = 0.85f * fade;
            mpb.SetColor("_BaseColor", c); mpb.SetColor("_Color", c);
            mr.SetPropertyBlock(mpb);
            if (Time.frameCount % 3 == 0)
            {
                // polvo levantado por el frente (de a pocos puntos por frame: no un estallido)
                float a = Random.value * Mathf.PI * 2f;
                Game.FX?.Dust(transform.position + new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a)) * radius, 0.7f);
            }
        }

        public void Hide() => gameObject.SetActive(false);

        void OnDestroy() { if (mesh != null) Destroy(mesh); }
    }
}
