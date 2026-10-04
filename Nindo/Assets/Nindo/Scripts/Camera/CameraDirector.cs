using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace Nindo
{
    /// <summary>
    /// Cámara de Nindo. Base: cámara alta en ángulo estilo Tunic (perspectiva, FOV bajo = look de
    /// diorama). Encima se suman capas de game-feel:
    ///  * encuadre de combate (se acomoda y aleja según dónde estén los enemigos),
    ///  * fijado (centra a Kaito y al objetivo, leve giro para dar profundidad),
    ///  * "planos" cinemáticos que se mezclan suavemente: habilidad por encima del hombro,
    ///    órbita baja del torbellino, órbita del finisher, presentación y muerte de jefes,
    ///  * temblor por trauma (Perlin), impulsos direccionales y "punch" de FOV,
    ///  * objetos que tapan a Kaito (árboles, techos) pasan a modo "solo sombra".
    /// </summary>
    [DefaultExecutionOrder(500)]
    public class CameraDirector : MonoBehaviour
    {
        public enum AbilityShot { OverShoulder, LowOrbit }

        [Header("Exploración")]
        public float exploreDistance = 21f;
        public float explorePitch = 52f;
        public float fov = 30f;
        public float lookAhead = 0.35f;
        [Header("Combate")]
        public float combatDistanceMin = 17f;
        public float combatDistanceMax = 27f;
        public float combatPitch = 47f;
        public float bossExtraDistance = 3f;
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
            if (GetComponent<AudioListener>() == null) gameObject.AddComponent<AudioListener>();
            var data = Cam.GetUniversalAdditionalCameraData();
            if (data != null)
            {
                data.renderPostProcessing = true;
                data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
                data.antialiasingQuality = AntialiasingQuality.Medium;
            }
            distance = exploreDistance; pitch = explorePitch;
        }

        void OnDestroy() { if (Game.Camera == this) Game.Camera = null; }

        // ================================================================== API
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

        public void Shake(float amount) => trauma = Mathf.Clamp01(trauma + amount * Settings.ScreenShake);

        public void Impulse(Vector3 dir, float strength)
        {
            dir.y = 0f;
            impulseVel += dir.normalized * strength * 6f * Settings.ScreenShake;
        }

        /// <summary>Golpe de FOV (negativo = zoom in).</summary>
        public void Punch(float fovDelta, float duration)
        {
            fovPunch = fovDelta;
            fovPunchVel = 0f;
        }

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

        public int PlayBossIntroShot(Transform boss, float height, float duration)
        {
            return PlayShot(t =>
            {
                float k = Mathf.SmoothStep(0f, 1f, t / duration);
                Vector3 fwd = boss.forward.Flat().normalized;
                Vector3 right = Vector3.Cross(Vector3.up, fwd);
                Vector3 pos = boss.position + fwd * Mathf.Lerp(9f, 6f, k) + right * Mathf.Lerp(2.5f, -1f, k) + Vector3.up * Mathf.Lerp(1.2f, height * 0.9f, k);
                Vector3 look = boss.position + Vector3.up * height * 0.6f;
                return new Pose(pos, Quaternion.LookRotation(look - pos));
            }, () => 34f, 1.0f, duration, 0.9f);
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
            float gdt = Time.deltaTime;

            UpdateBaseParams(p, dt);
            ComputeBase(out var pos, out var rot);
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

            // punch de FOV (resorte subamortiguado: se siente como un golpe)
            fovPunchVel += -fovPunch * 160f * dt;
            fovPunchVel *= Mathf.Exp(-12f * dt);
            fovPunch += fovPunchVel * dt;
            if (Mathf.Abs(fovPunch) < 0.01f && Mathf.Abs(fovPunchVel) < 0.01f) fovPunch = 0f;

            transform.SetPositionAndRotation(pos, rot);
            Cam.fieldOfView = Mathf.Clamp(camFov + fovPunch, 10f, 80f);
            Game.FX?.Screen?.SetFocusDistance(distance);
            UpdateOccluders(p);
        }

        void UpdateBaseParams(PlayerController p, float dt)
        {
            Vector3 ppos = p.transform.position + Vector3.up * 1.0f;
            Vector3 targetFocus = ppos;
            float targetDist = exploreDistance + zoneDistanceOffset;
            float targetPitch = explorePitch + zonePitchOffset;
            float targetYaw = zoneYaw;
            var combat = Game.Combat;
            bool boss = combat != null && combat.ActiveBoss != null;

            if (lockTarget != null)
            {
                Vector3 t = lockTarget.position + Vector3.up;
                float d = CombatMath.FlatDistance(t, ppos);
                targetFocus = Vector3.Lerp(ppos, t, Mathf.Clamp01(0.42f - d * 0.005f));
                targetDist = Mathf.Clamp(15.5f + d * 0.6f, combatDistanceMin - 1f, combatDistanceMax);
                targetPitch = combatPitch + zonePitchOffset;
                // giro sutil hacia el objetivo para dar profundidad
                Vector3 baseFwd = Quaternion.Euler(0f, zoneYaw, 0f) * Vector3.forward;
                float side = Vector3.SignedAngle(baseFwd, (t - ppos).Flat(), Vector3.up);
                targetYaw = zoneYaw + Mathf.Clamp(side * 0.08f, -9f, 9f);
            }
            else if (combat != null && combat.InCombat && combat.EngagedBounds(out var center, out var radius))
            {
                center += Vector3.up;
                float d = CombatMath.FlatDistance(center, ppos);
                targetFocus = Vector3.Lerp(ppos, center, Mathf.Clamp01(0.3f - d * 0.004f));
                targetDist = Mathf.Clamp(combatDistanceMin + (radius + d * 0.5f) * 0.55f, combatDistanceMin, combatDistanceMax);
                targetPitch = combatPitch + zonePitchOffset;
            }
            else
            {
                targetFocus += p.Velocity * lookAhead;
            }
            if (boss) targetDist += bossExtraDistance;

            focus = CombatMath.Damp(focus, targetFocus, followDamping, dt);
            distance = CombatMath.Damp(distance, targetDist, paramDamping, dt);
            pitch = CombatMath.Damp(pitch, targetPitch, paramDamping, dt);
            yaw = Mathf.LerpAngle(yaw, targetYaw, 1f - Mathf.Exp(-2.5f * dt));
            BaseYaw = yaw;
        }

        void ComputeBase(out Vector3 pos, out Quaternion rot)
        {
            rot = Quaternion.Euler(pitch, yaw, 0f);
            pos = focus - rot * Vector3.forward * distance;
        }

        // ================================================================== oclusión
        readonly RaycastHit[] hits = new RaycastHit[16];
        readonly HashSet<Occluder> hidden = new HashSet<Occluder>();
        readonly List<Occluder> toShow = new List<Occluder>();
        float occluderTimer;

        void UpdateOccluders(PlayerController p)
        {
            occluderTimer -= Time.unscaledDeltaTime;
            if (occluderTimer > 0f) return;
            occluderTimer = 0.1f;
            Vector3 target = p.transform.position + Vector3.up * 0.9f;
            Vector3 dir = target - transform.position;
            float len = dir.magnitude - 0.6f;
            int n = Physics.SphereCastNonAlloc(transform.position, 0.6f, dir.normalized, hits, len, ~0, QueryTriggerInteraction.Collide);
            toShow.Clear();
            foreach (var o in hidden) toShow.Add(o);
            for (int i = 0; i < n; i++)
            {
                var occ = hits[i].collider != null ? hits[i].collider.GetComponentInParent<Occluder>() : null;
                if (occ == null) continue;
                occ.SetHidden(true);
                hidden.Add(occ);
                toShow.Remove(occ);
            }
            foreach (var o in toShow) { if (o != null) o.SetHidden(false); hidden.Remove(o); }
        }
    }

    /// <summary>Objeto que se vuelve "solo sombra" cuando tapa a Kaito.</summary>
    public class Occluder : MonoBehaviour
    {
        Renderer[] rs;
        bool isHidden;
        void Awake() { rs = GetComponentsInChildren<Renderer>(); }
        public void SetHidden(bool h)
        {
            if (h == isHidden) return;
            isHidden = h;
            if (rs == null) rs = GetComponentsInChildren<Renderer>();
            foreach (var r in rs)
                if (r != null) r.shadowCastingMode = h ? UnityEngine.Rendering.ShadowCastingMode.ShadowsOnly : UnityEngine.Rendering.ShadowCastingMode.On;
        }
    }
}
