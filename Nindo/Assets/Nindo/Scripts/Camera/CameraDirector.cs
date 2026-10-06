using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace Nindo
{
    /// <summary>
    /// Cámara de Nindo. Base: cámara alta en ángulo estilo Tunic (perspectiva, FOV bajo = look de
    /// diorama). Encima se suman capas de game-feel:
    ///  * encuadre de combate: se baja a 45° y se acomoda a los enemigos; fijado nunca más cerca de 19 m (más cerca
    ///    no entraban en pantalla las embestidas que arrancan a 5 m) y sin girar (el giro rotaba los controles),
    ///  * jefes: perfil propio (ICameraProfile) o distancia extra por altura, y auto-encuadre si se salen por arriba,
    ///  * un atacante que avisa fuera de pantalla tira un poco del encuadre hacia él,
    ///  * "planos" cinemáticos que se mezclan suavemente: habilidad por encima del hombro,
    ///    órbita baja del torbellino, órbita del finisher, presentación y muerte de jefes,
    ///  * temblor por trauma (Perlin), impulsos direccionales y golpe de FOV amortiguado (tope ±3°),
    ///  * lo que tapa a Kaito, al fijado o a un atacante se disuelve (CameraOcclusion),
    ///  * el oído (AudioListener) va sobre Kaito, girado como la cámara.
    /// </summary>
    [DefaultExecutionOrder(500)]
    public class CameraDirector : MonoBehaviour
    {
        public enum AbilityShot { OverShoulder, LowOrbit }

        [Header("Exploración")]
        public float exploreDistance = 24f;
        public float explorePitch = 52f;
        public float fov = 30f;
        public float lookAhead = 0.35f;
        [Header("Combate")]
        public float combatDistanceMin = 19f;
        public float combatDistanceMax = 26f;
        public float combatPitch = 45f;
        [Tooltip("Fijado: distancia = 18 + 0.5 x separación, entre estos dos")]
        public float lockDistanceMin = 19f, lockDistanceMax = 25f;
        [Tooltip("Jefe sin perfil propio: 0.9 m por cada metro de altura sobre 1.7, hasta esto")]
        public float bossExtraMax = 2.5f;
        [Tooltip("Auto-encuadre del jefe: metros que puede alejarse si la cabeza o el arma pasan el 94 % de la pantalla")]
        public float autoFitMax = 3f;
        [Header("Suavizado")]
        public float followDamping = 7f;
        public float paramDamping = 3.5f;
        [Header("Temblor")]
        public float maxShakeAngle = 2.6f;
        public float maxShakeOffset = 0.35f;

        public Camera Cam { get; private set; }
        public float BaseYaw { get; private set; }

        Transform lockTarget;
        Vector3 focus;
        float distance, pitch, yaw, zoneYaw, zonePitchOffset, zoneDistanceOffset;
        float trauma;
        Vector3 impulse, impulseVel;
        float fovPunch, fovPunchVel;
        bool initialized;
        Transform listener;

        class Shot
        {
            public int id;
            public Func<float, Pose> pose;   // t (segundos reales) -> pose
            public Func<float> fov;
            public float blendIn, blendOut, duration, t;
            public bool ending;
            public float endT;
        }
        readonly List<Shot> shots = new List<Shot>();
        int nextShotId = 1;

        void Awake()
        {
            Game.Camera = this;
            Cam = GetComponent<Camera>();
            if (Cam == null) Cam = gameObject.AddComponent<Camera>();
            Cam.fieldOfView = fov;
            Cam.nearClipPlane = 0.3f;
            Cam.farClipPlane = 400f;
            gameObject.tag = "MainCamera";
            // el oído no va en la cámara (a 24-31 m de la pelea todo sonaba lejos y saltaba de volumen con cada plano
            // cercano): va sobre Kaito. El de la escena se apaga en el acto (Destroy espera al final del frame y
            // Unity avisaba de dos AudioListener)
            var camEar = GetComponent<AudioListener>();
            if (camEar != null) { camEar.enabled = false; Destroy(camEar); }
            listener = new GameObject("[Oído]").transform;
            listener.gameObject.AddComponent<AudioListener>();
            var data = Cam.GetUniversalAdditionalCameraData();
            if (data != null)
            {
                data.renderPostProcessing = true;
                data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
                data.antialiasingQuality = AntialiasingQuality.Medium;
            }
            if (GetComponent<CameraOcclusion>() == null) gameObject.AddComponent<CameraOcclusion>();
            // las marcas de amenaza proyectan con la pose de la cámara de este frame: viven acá y corren después
            if (GetComponent<ThreatIndicators>() == null) gameObject.AddComponent<ThreatIndicators>();
            distance = exploreDistance; pitch = explorePitch;
        }

        void OnDestroy()
        {
            if (Game.Camera == this) Game.Camera = null;
            if (listener != null) Destroy(listener.gameObject);
        }

        // ================================================================== API
        /// <summary>
        /// Base del movimiento: solo el giro de la zona (amortiguado al cambiar de zona). El fijado ya no gira la cámara:
        /// rodeando a un objetivo, "arriba" cambiaba de dirección en medio de la pelea.
        /// </summary>
        public void MovementBasis(out Vector3 forward, out Vector3 right)
        {
            Quaternion q = Quaternion.Euler(0f, yaw, 0f);
            forward = q * Vector3.forward;
            right = q * Vector3.right;
        }

        public void SetLockTarget(Transform t) => lockTarget = t;

        /// <summary>Zonas pueden rotar levemente la cámara (p. ej. senderos de montaña).</summary>
        public void SetZoneOverride(float yawDeg, float pitchOffset, float distanceOffset)
        {
            zoneYaw = yawDeg; zonePitchOffset = pitchOffset; zoneDistanceOffset = distanceOffset;
        }

        /// <summary>
        /// Corrimiento del punto de mira en metros de mundo (amortiguado), para arenas que necesitan mostrar algo más
        /// de un lado (p. ej. la cascada detrás de Mizuchi). Vector3.zero lo quita.
        /// </summary>
        public void SetFocusBias(Vector3 bias) => focusBiasTarget = bias;
        Vector3 focusBias, focusBiasTarget;

        public void Shake(float amount) => trauma = Mathf.Clamp01(trauma + amount * Settings.ScreenShake);

        public void Impulse(Vector3 dir, float strength)
        {
            dir.y = 0f;
            impulseVel += dir.normalized * strength * 6f * Settings.ScreenShake;
        }

        /// <summary>
        /// Golpe de FOV (negativo = acercar): un impulso a un resorte casi crítico (ζ 0.7) que llega a 'fovDelta' en
        /// ~0.08 s y vuelve en ~0.3 s sin rebotar. Tope ±3° (un 10 % de zoom a FOV 30): con -7 en el remate todo lo
        /// que había en pantalla, anillos de aviso incluidos, cambiaba de tamaño justo cuando arrancaba el siguiente.
        /// Lo pedido se comprime (tanh) para conservar el orden entre golpes chicos y grandes, y los que alejan (dash,
        /// Corte del Viento) van a la mitad: alejar en cada dash hacía "respirar" el encuadre. 'duration' ya no se usa:
        /// la duración la da el resorte.
        /// </summary>
        public void Punch(float fovDelta, float duration)
        {
            float d = MaxPunch * (float)Math.Tanh(fovDelta / MaxPunch);
            if (d > 0f) d *= ZoomOutPunchScale;
            fovPunchVel += d * PunchImpulse;
        }
        const float MaxPunch = 3f, ZoomOutPunchScale = 0.5f;
        // resorte: ω 14 rad/s, ζ 0.7. Un impulso v0 llega a un pico de 0.0328·v0 => v0 = Δ / 0.0328
        const float PunchStiffness = 196f, PunchDamping = 19.6f, PunchImpulse = 30.5f;

        public void Snap()
        {
            var p = Game.Player;
            if (p == null) return;
            focus = p.transform.position + Vector3.up;
            initialized = true;
            ComputeBase(out var pos, out var rot);
            transform.SetPositionAndRotation(pos, rot);
        }

        public void CancelShot(int id)
        {
            foreach (var s in shots)
                if (s.id == id && !s.ending) { s.ending = true; s.endT = 0f; }
        }

        public void CancelAllShots()
        {
            foreach (var s in shots) if (!s.ending) { s.ending = true; s.endT = 0f; }
        }

        public int PlayShot(Func<float, Pose> pose, Func<float> shotFov, float blendIn, float duration, float blendOut)
        {
            var s = new Shot { id = nextShotId++, pose = pose, fov = shotFov, blendIn = blendIn, blendOut = blendOut, duration = duration };
            shots.Add(s);
            return s.id;
        }

        /// <summary>¿Hay un plano cinemático mezclándose? (el encuadre de juego no es lo que se ve)</summary>
        public bool InShot => shots.Count > 0;

        /// <summary>Plano fijo mirando a un punto (cinemáticas).</summary>
        public int PlayStaticShot(Vector3 pos, Vector3 lookAt, float shotFov, float duration, float blendIn = 0.8f, float blendOut = 0.8f)
        {
            Quaternion r = Quaternion.LookRotation(lookAt - pos);
            return PlayShot(_ => new Pose(pos, r), () => shotFov, blendIn, duration, blendOut);
        }

        /// <summary>Plano que sigue a un objetivo desde un offset (en espacio del objetivo si local=true).</summary>
        public int PlayFollowShot(Transform target, Vector3 offset, float lookHeight, float shotFov, float duration, float blendIn = 0.8f, float blendOut = 0.8f, bool local = true)
        {
            return PlayShot(t =>
            {
                if (target == null) return new Pose(transform.position, transform.rotation);
                Vector3 p = target.position + (local ? target.rotation * offset : offset);
                Vector3 look = target.position + Vector3.up * lookHeight;
                return new Pose(p, Quaternion.LookRotation(look - p));
            }, () => shotFov, blendIn, duration, blendOut);
        }

        public int PlayAbilityShot(Transform kaito, AbilityShot type, float duration)
        {
            Vector3 fwd0 = kaito.forward;
            if (type == AbilityShot.OverShoulder)
            {
                return PlayShot(t =>
                {
                    Vector3 fwd = Vector3.Slerp(fwd0, kaito.forward, 0.3f).Flat().normalized;
                    Vector3 right = Vector3.Cross(Vector3.up, fwd);
                    float push = Mathf.SmoothStep(0f, 1f, t / duration) * 1.2f;
                    Vector3 pos = kaito.position - fwd * (3.6f - push) + Vector3.up * 1.9f + right * 1.05f;
                    Vector3 look = kaito.position + fwd * 8f + Vector3.up * 1.1f;
                    return new Pose(pos, Quaternion.LookRotation(look - pos));
                }, () => 44f, 0.18f, duration, 0.5f);
            }
            return PlayShot(t =>
            {
                float ang = Mathf.Lerp(-40f, 70f, Mathf.SmoothStep(0f, 1f, t / duration));
                Vector3 dir = Quaternion.Euler(0f, ang, 0f) * -fwd0.Flat().normalized;
                Vector3 pos = kaito.position + dir * 5.2f + Vector3.up * 1.5f;
                Vector3 look = kaito.position + Vector3.up * 1.0f;
                return new Pose(pos, Quaternion.LookRotation(look - pos));
            }, () => 46f, 0.15f, duration, 0.45f);
        }

        public int PlayFinisherShot(Transform kaito, Transform enemy)
        {
            Vector3 mid0 = (kaito.position + enemy.position) * 0.5f;
            Vector3 axis = (enemy.position - kaito.position).Flat().normalized;
            Vector3 side = Vector3.Cross(Vector3.up, axis);
            // elegimos el lado que mira más hacia la cámara actual
            if (Vector3.Dot(side, (transform.position - mid0).Flat()) < 0f) side = -side;
            return PlayShot(t =>
            {
                float ang = Mathf.Lerp(-25f, 45f, Mathf.SmoothStep(0f, 1f, t / 1.8f));
                Vector3 dir = Quaternion.AngleAxis(ang, Vector3.up) * side;
                Vector3 mid = kaito != null && enemy != null ? (kaito.position + enemy.position) * 0.5f : mid0;
                Vector3 pos = mid + dir * 4.4f + Vector3.up * 1.3f;
                return new Pose(pos, Quaternion.LookRotation(mid + Vector3.up * 0.9f - pos));
            }, () => 36f, 0.12f, 6f, 0.35f);
        }

        /// <summary>Presentación de jefe: se acerca de frente y sube. La re-presentación de un reintento usa fundidos cortos.</summary>
        public int PlayBossIntroShot(Transform boss, float height, float duration, float blendIn = 1.0f, float blendOut = 0.9f)
        {
            return PlayShot(t =>
            {
                float k = Mathf.SmoothStep(0f, 1f, t / duration);
                Vector3 fwd = boss.forward.Flat().normalized;
                Vector3 right = Vector3.Cross(Vector3.up, fwd);
                Vector3 pos = boss.position + fwd * Mathf.Lerp(9f, 6f, k) + right * Mathf.Lerp(2.5f, -1f, k) + Vector3.up * Mathf.Lerp(1.2f, height * 0.9f, k);
                Vector3 look = boss.position + Vector3.up * height * 0.6f;
                return new Pose(pos, Quaternion.LookRotation(look - pos));
            }, () => 34f, blendIn, duration, blendOut);
        }

        public int PlayBossDeathShot(Transform boss)
        {
            Vector3 center = boss.position;
            Vector3 start = (transform.position - center).Flat().normalized;
            return PlayShot(t =>
            {
                Vector3 dir = Quaternion.Euler(0f, t * 25f, 0f) * start;
                Vector3 pos = center + dir * Mathf.Lerp(9f, 6f, Mathf.Clamp01(t / 3f)) + Vector3.up * 3f;
                return new Pose(pos, Quaternion.LookRotation(center + Vector3.up * 1.5f - pos));
            }, () => 34f, 0.4f, 3.2f, 1.2f);
        }

        // ================================================================== update
        void LateUpdate()
        {
            var p = Game.Player;
            if (p == null) return;
            if (!initialized) Snap();
            float dt = Time.unscaledDeltaTime;

            UpdateBaseParams(p, dt);
            ComputeBase(out var pos, out var rot);
            UpdateAutoFit(pos, rot, dt);
            float camFov = fov;

            // planos cinemáticos mezclados encima
            for (int i = 0; i < shots.Count; i++)
            {
                var s = shots[i];
                s.t += dt;
                float w = s.blendIn > 0f ? Mathf.Clamp01(s.t / s.blendIn) : 1f;
                if (!s.ending && s.duration > 0f && s.t >= s.duration) { s.ending = true; s.endT = 0f; }
                if (s.ending)
                {
                    s.endT += dt;
                    w = Mathf.Min(w, 1f - Mathf.Clamp01(s.endT / Mathf.Max(0.01f, s.blendOut)));
                }
                w = w * w * (3f - 2f * w);
                var sp = s.pose(s.t);
                pos = Vector3.Lerp(pos, sp.position, w);
                rot = Quaternion.Slerp(rot, sp.rotation, w);
                camFov = Mathf.Lerp(camFov, s.fov(), w);
            }
            shots.RemoveAll(s => s.ending && s.endT >= s.blendOut);

            // impulsos (resorte) + temblor
            impulseVel += -impulse * 90f * dt;
            impulseVel *= Mathf.Exp(-10f * dt);
            impulse += impulseVel * dt;
            pos += impulse;
            trauma = Mathf.Max(0f, trauma - dt * 1.4f);
            float shake = trauma * trauma;
            if (shake > 0.0001f)
            {
                float tt = Time.unscaledTime * 22f;
                rot *= Quaternion.Euler((Mathf.PerlinNoise(tt, 1.1f) - 0.5f) * 2f * maxShakeAngle * shake,
                                        (Mathf.PerlinNoise(tt, 2.3f) - 0.5f) * 2f * maxShakeAngle * shake,
                                        (Mathf.PerlinNoise(tt, 3.7f) - 0.5f) * 2f * maxShakeAngle * shake);
                pos += new Vector3(Mathf.PerlinNoise(tt, 4.1f) - 0.5f, Mathf.PerlinNoise(tt, 5.3f) - 0.5f, Mathf.PerlinNoise(tt, 6.7f) - 0.5f) * 2f * maxShakeOffset * shake;
            }

            UpdatePunch(dt);

            transform.SetPositionAndRotation(pos, rot);
            Cam.fieldOfView = Mathf.Clamp(camFov + fovPunch, 10f, 80f);
            Game.FX?.Screen?.SetFocusDistance(distance);
            // el oído sobre Kaito (a la altura de la cabeza) y girado como la cámara: lo que se ve a la derecha suena a
            // la derecha
            if (listener != null) listener.SetPositionAndRotation(p.transform.position + Vector3.up * 1.2f, rot);
        }

        void UpdatePunch(float dt)
        {
            // solución exacta del oscilador amortiguado en cada frame: el golpe mide lo mismo a 30, 60 o 144 fps
            // (integrando con Euler el pico salía 15-30 % más chico y dependía del frame rate)
            float h = Mathf.Min(dt, 0.1f);
            float w0 = Mathf.Sqrt(PunchStiffness), a = PunchDamping * 0.5f, wd = Mathf.Sqrt(w0 * w0 - a * a);
            float e = Mathf.Exp(-a * h), c = Mathf.Cos(wd * h), s = Mathf.Sin(wd * h);
            float x = fovPunch, v = fovPunchVel;
            fovPunch = e * (x * c + (v + a * x) / wd * s);
            fovPunchVel = e * (v * c - (a * v + w0 * w0 * x) / wd * s);
            // dos golpes seguidos (remate y muerte) suman velocidad: tope ±3° en total
            fovPunch = Mathf.Clamp(fovPunch, -MaxPunch, MaxPunch);
            if (Mathf.Abs(fovPunch) < 0.005f && Mathf.Abs(fovPunchVel) < 0.01f) { fovPunch = 0f; fovPunchVel = 0f; }
        }

        void UpdateBaseParams(PlayerController p, float dt)
        {
            Vector3 ppos = p.transform.position + Vector3.up * 1.0f;
            Vector3 targetFocus = ppos;
            float targetDist = exploreDistance + zoneDistanceOffset;
            float targetPitch = explorePitch + zonePitchOffset;
            var combat = Game.Combat;
            Boss boss = combat != null && combat.ActiveBoss != null && combat.ActiveBoss.IsAlive ? combat.ActiveBoss : null;
            bool fighting = true;

            if (lockTarget != null)
            {
                Vector3 t = lockTarget.position + Vector3.up;
                float d = CombatMath.FlatDistance(t, ppos);
                targetFocus = Vector3.Lerp(ppos, t, Mathf.Clamp01(0.42f - d * 0.005f));
                // nunca más cerca de 19 m: a 17 m quedaban ~5 m de suelo detrás de Kaito y la estocada del ninja
                // (embestida de 3.2 m desde 5.5 m) arrancaba fuera de pantalla
                targetDist = Mathf.Clamp(18f + d * 0.5f, lockDistanceMin, lockDistanceMax);
            }
            else if (boss != null)
            {
                // sin fijar: el jefe y Kaito en cuadro. Se mira 45 % hacia el jefe, pero Kaito nunca a más de 6 m del
                // centro (el borde de abajo está a ~7 m del punto de mira con 45°)
                Vector3 b = boss.transform.position + Vector3.up;
                float d = CombatMath.FlatDistance(b, ppos);
                targetFocus = Vector3.Lerp(ppos, b, d > 0.01f ? Mathf.Min(0.45f, 6f / d) : 0f);
                targetDist = Mathf.Clamp(combatDistanceMin + d * 0.35f, combatDistanceMin, combatDistanceMax);
            }
            else if (combat != null && combat.InCombat && combat.EngagedBounds(out var center, out var radius))
            {
                center += Vector3.up;
                float d = CombatMath.FlatDistance(center, ppos);
                targetFocus = Vector3.Lerp(ppos, center, Mathf.Clamp01(0.3f - d * 0.004f));
                targetDist = Mathf.Clamp(combatDistanceMin + (radius + d * 0.5f) * 0.55f, combatDistanceMin, combatDistanceMax);
            }
            else
            {
                fighting = false;
                targetFocus += p.Velocity * lookAhead;
            }
            if (fighting) targetPitch = combatPitch + zonePitchOffset;
            if (boss != null)
            {
                if (boss is ICameraProfile prof)
                {
                    targetDist += prof.CameraExtraDistance;
                    if (prof.CameraPitch > 0f) targetPitch = prof.CameraPitch;
                }
                else targetDist += Mathf.Clamp(0.9f * (boss.config.height * boss.config.scale - 1.7f), 0f, bossExtraMax);
            }
            targetDist += fitExtra;

            UpdateThreatFraming(ppos, fighting && !InShot, dt);
            focusBias = CombatMath.Damp(focusBias, focusBiasTarget, 2f, dt);
            targetFocus += threatBias + focusBias;

            focus = CombatMath.Damp(focus, targetFocus, followDamping, dt);
            distance = CombatMath.Damp(distance, targetDist, paramDamping, dt);
            pitch = CombatMath.Damp(pitch, targetPitch, paramDamping, dt);
            // solo el giro de la zona: el fijado ya no agrega giro (rotaba la base de los controles al rodear)
            yaw = Mathf.LerpAngle(yaw, zoneYaw, 1f - Mathf.Exp(-2.5f * dt));
            BaseYaw = yaw;
        }

        void ComputeBase(out Vector3 pos, out Quaternion rot)
        {
            rot = Quaternion.Euler(pitch, yaw, 0f);
            pos = focus - rot * Vector3.forward * distance;
        }

        // ================================================================== amenazas fuera de cuadro
        Vector3 threatBias;
        /// <summary>Hasta qué fracción del camino Kaito→atacante se corre el punto de mira (y el tope en metros).</summary>
        const float ThreatPull = 0.25f, ThreatPullMax = 3f, ThreatRange = 14f;

        /// <summary>
        /// Un enemigo que ya dibuja su aviso pero está fuera del 84 % central de la pantalla (o detrás de la cámara)
        /// corre el punto de mira hasta un 25 % hacia él: la estocada o la embestida que arranca fuera de cuadro entra.
        /// Si hay varios, manda el que pega antes. Lo que no alcanza a entrar lo marca UI/ThreatIndicators.
        /// </summary>
        void UpdateThreatFraming(Vector3 ppos, bool active, float dt)
        {
            Vector3 want = Vector3.zero;
            var combat = Game.Combat;
            if (active && combat != null)
            {
                float best = float.PositiveInfinity;
                var list = combat.Engaged;
                for (int i = 0; i < list.Count; i++)
                {
                    var e = list[i];
                    if (e == null || !e.InTell || e.StrikeEta >= best) continue;
                    Vector3 off = (e.transform.position - ppos).Flat();
                    if (off.sqrMagnitude > ThreatRange * ThreatRange) continue;
                    Vector3 v = Cam.WorldToViewportPoint(e.AimPoint);
                    if (v.z > 0f && v.x > 0.08f && v.x < 0.92f && v.y > 0.08f && v.y < 0.92f) continue;
                    best = e.StrikeEta;
                    want = Vector3.ClampMagnitude(off * ThreatPull, ThreatPullMax);
                }
            }
            threatBias = CombatMath.Damp(threatBias, want, 4f, dt);
        }

        // ================================================================== auto-encuadre del jefe
        float fitExtra, fitTarget;
        Boss fitBoss;
        readonly List<Renderer> fitRenderers = new List<Renderer>();
        readonly List<Transform> fitBones = new List<Transform>();

        /// <summary>
        /// Con un jefe en pelea se proyecta lo más alto de su cuerpo (renderers y huesos: el bounds de un skinned mesh
        /// no sigue un arma levantada) con la pose base. Si pasa el 94 % de la altura de la pantalla, la cámara se aleja
        /// lo justo para dejarlo en el 92 % (hasta autoFitMax); si baja del 86 % vuelve a acercarse. La banda evita que
        /// "respire" con cada golpe.
        /// </summary>
        void UpdateAutoFit(Vector3 pos, Quaternion rot, float dt)
        {
            var boss = Game.Combat != null ? Game.Combat.ActiveBoss : null;
            if (boss == null || !boss.IsAlive) { fitTarget = 0f; fitBoss = null; }
            else if (!InShot)
            {
                if (boss != fitBoss) CacheFitParts(boss);
                float top = float.NegativeInfinity;
                for (int i = 0; i < fitRenderers.Count; i++)
                {
                    var r = fitRenderers[i];
                    // un jefe puede cambiar de malla (fase 2): solo cuenta la que está prendida
                    if (r != null && r.enabled && r.gameObject.activeInHierarchy) top = Mathf.Max(top, r.bounds.max.y);
                }
                // la malla sobresale del hueso más alto (cabeza, punta del arma): un margen
                for (int i = 0; i < fitBones.Count; i++) if (fitBones[i] != null && fitBones[i].gameObject.activeInHierarchy) top = Mathf.Max(top, fitBones[i].position.y + 0.3f);
                if (!float.IsInfinity(top))
                {
                    Vector3 bp = boss.transform.position;
                    Vector3 local = Quaternion.Inverse(rot) * (new Vector3(bp.x, top, bp.z) - pos);
                    float tanHalf = Mathf.Tan(fov * 0.5f * Mathf.Deg2Rad);
                    if (local.z > 0.5f)
                    {
                        float vy = 0.5f + 0.5f * local.y / (local.z * tanHalf);
                        // alejarse Δ sobre el eje de la cámara suma Δ a local.z: Δ para que el punto quede en 'v'
                        if (vy > 0.94f) fitTarget = Mathf.Clamp(fitExtra + NeededPullBack(local, tanHalf, 0.92f), 0f, autoFitMax);
                        else if (vy < 0.86f) fitTarget = Mathf.Clamp(fitExtra + NeededPullBack(local, tanHalf, 0.90f), 0f, autoFitMax);
                    }
                }
            }
            fitExtra = CombatMath.Damp(fitExtra, fitTarget, 2.5f, dt);
        }

        static float NeededPullBack(Vector3 local, float tanHalf, float v)
        {
            // por debajo del eje óptico alejarse no lo baja: se puede volver a acercar del todo
            if (local.y <= 0f) return float.NegativeInfinity;
            return local.y / (tanHalf * (2f * v - 1f)) - local.z;
        }

        void CacheFitParts(Boss boss)
        {
            fitBoss = boss;
            fitRenderers.Clear();
            fitBones.Clear();
            foreach (var r in boss.GetComponentsInChildren<Renderer>())
                if (r is SkinnedMeshRenderer || r is MeshRenderer) fitRenderers.Add(r);
            var animator = boss.GetComponentInChildren<Animator>();
            if (animator != null) foreach (var t in animator.GetComponentsInChildren<Transform>()) fitBones.Add(t);
        }
    }
}
