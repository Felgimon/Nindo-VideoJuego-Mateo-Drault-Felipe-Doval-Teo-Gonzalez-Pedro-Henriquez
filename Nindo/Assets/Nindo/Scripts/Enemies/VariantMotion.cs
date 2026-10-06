using System.Collections.Generic;
using UnityEngine;

namespace Nindo
{
    /// <summary>Cómo se mueve una variante sin clips nuevos (VariantMotion).</summary>
    [System.Serializable]
    public class MotionFlavor
    {
        [Tooltip("Velocidad de la animación quieto (respirar, mirar). Caminando y corriendo manda la velocidad de desplazamiento de la variante")]
        public float idleSpeed = 1f;
        [Tooltip("Grados de la columna hacia adelante (+) o atrás (-)")] public float lean;
        [Tooltip("Grados de los hombros hacia adelante (encogidos +, sacando pecho -)")] public float hunch;
        [Tooltip("Grados de la cabeza hacia abajo (+): compensa la inclinación para seguir mirando al frente")] public float headPitch;
        [Tooltip("Respiración: grados de la columna y ciclos por segundo")] public float breathe, breatheHz = 0.3f;
        [Tooltip("Vaivén lateral que sube por la columna hasta la cabeza, atrasado: grados y ciclos por segundo")] public float sway, swayHz = 0.4f;
        [Tooltip("Miradas rápidas a los costados quieto: grados (0 = no) y segundos entre una y otra")] public float scan, scanEvery = 1.6f;

        /// <summary>Montaña: encorvado contra el viento, respiración honda y lenta, todo un poco más pesado.</summary>
        public static readonly MotionFlavor Mountain = new MotionFlavor
        { idleSpeed = 0.8f, lean = 7f, hunch = 6f, headPitch = -5f, breathe = 2.6f, breatheHz = 0.26f };

        /// <summary>Lago: el cuerpo se mece como el agua, una ola que sube de la cintura a la cabeza.</summary>
        public static readonly MotionFlavor Lake = new MotionFlavor
        { idleSpeed = 0.95f, lean = 2f, breathe = 1.2f, breatheHz = 0.34f, sway = 3.5f, swayHz = 0.42f };

        /// <summary>Bambú: agazapado y nervioso, la cabeza salta de un lado a otro buscando a Kaito.</summary>
        public static readonly MotionFlavor Bamboo = new MotionFlavor
        { idleSpeed = 1.18f, lean = 9f, headPitch = -6f, breathe = 1f, breatheHz = 0.6f, scan = 24f, scanEvery = 1.5f };

        /// <summary>Ōzeki: el campeón saca pecho y respira lento; nada de apuro.</summary>
        public static readonly MotionFlavor Champion = new MotionFlavor
        { idleSpeed = 0.85f, lean = -5f, hunch = -4f, headPitch = 3f, breathe = 2f, breatheHz = 0.24f };
    }

    /// <summary>
    /// Aplica un MotionFlavor sobre la animación del equipo: retoca la velocidad del Animator y suma rotaciones a
    /// columna, hombros y cabeza DESPUÉS del Animator. Solo en el estado de locomoción (quieto, caminando, rodeando):
    /// al entrar a un ataque, golpe o guardia se desvanece en ~0.1 s, así las poses de los golpes (y el aviso de
    /// parry que se lee en ellas) quedan exactas. Los giros van en ejes del personaje (adelante, derecha, arriba),
    /// no en los locales de cada hueso: sirve igual para el ninja y para el sumo.
    /// También adorna los golpes propios de la zona (EnemyArchetypes.*Moves) atados al reloj del paso: el salto del
    /// bambú va por el aire, el remolino del lago gira entero, el rompeguardia de la montaña se echa atrás antes de
    /// soltar, y salen la nieve del shiko o el salpicón del empujón en el instante del golpe.
    /// Corre después de Enemy (que fija Animator.speed en su Update) y antes de SpringChain (que cuelga del pose).
    /// (Va en su propio archivo: Unity toma DefaultExecutionOrder del script, no de una clase de otro archivo; con
    /// el orden indefinido Enemy pisaba la velocidad y el sabor no se veía.)
    /// </summary>
    [DefaultExecutionOrder(110)]
    public class VariantMotion : MonoBehaviour
    {
        public MotionFlavor flavor;
        [Tooltip("Velocidad de la animación al desplazarse: la MISMA que multiplica la velocidad de la variante en el " +
                 "suelo (EnemyVariants.Variant.speed), si no los pies patinan")]
        public float moveSpeed = 1f;

        class Bone
        {
            public Transform t;
            public Quaternion written, animated;
            public bool has;
        }

        static readonly int SpeedParam = Animator.StringToHash("Speed");
        Enemy enemy;
        Animator animator;
        Renderer watch;
        Bone lower, upper, head, shoulderL, shoulderR;
        bool hasSpeed;
        float weight, phase, scanYaw, scanTarget, nextScan;
        // adornos de los golpes: la pose del modelo que dejó CharacterFactory y si este paso ya la movió
        Vector3 basePos;
        Quaternion baseRot;
        bool moved;
        float lastClock;

        void Start()
        {
            enemy = GetComponentInParent<Enemy>();
            animator = GetComponent<Animator>();
            if (enemy == null || animator == null || flavor == null) { enabled = false; return; }
            foreach (var p in animator.parameters)
                if (p.nameHash == SpeedParam && p.type == AnimatorControllerParameterType.Float) hasSpeed = true;
            var map = new Dictionary<string, Transform>();
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (!map.ContainsKey(t.name)) map[t.name] = t;
            Bone Find(params string[] names)
            {
                foreach (var n in names) if (map.TryGetValue(n, out var t)) return new Bone { t = t };
                return null;
            }
            // ninja: EspaldaBaja/EspaldaAlta; sumo: un solo Torso (lleva toda la inclinación)
            lower = Find("EspaldaBaja");
            upper = Find("EspaldaAlta", "Torso");
            head = Find("Cabeza", "cabeza");
            shoulderL = Find("Hombro.L");
            shoulderR = Find("Hombro.R");
            watch = GetComponentInChildren<SkinnedMeshRenderer>();
            basePos = transform.localPosition;
            baseRot = transform.localRotation;
            phase = Random.value * 10f;                   // que dos del mismo grupo no respiren a la par
            nextScan = Time.time + Random.Range(0.3f, flavor.scanEvery);
        }

        bool InLocomotion => enemy.IsAlive && enemy.State != EnemyState.Scripted && enemy.Anim.Current == enemy.config.animLocomotion;

        float Speed01 => hasSpeed ? Mathf.Clamp01(animator.GetFloat(SpeedParam)) : 0f;

        void Update()
        {
            // Enemy fija Animator.speed en cada Update (CharacterAnimator.Tick): se escala recién si sigue siendo ese
            // valor (congelado por hit-stop o un frame sin Tick no se toca, y nunca se acumula)
            if (!InLocomotion || enemy.Anim.Frozen) return;
            float s = enemy.Anim.StateSpeed;
            // el ritmo de quieto solo parado: apenas arranca (caminar, rodear) ya va al de desplazamiento entero
            float rate = Mathf.Lerp(flavor.idleSpeed, moveSpeed, Mathf.InverseLerp(0f, 0.15f, Speed01));
            if (Mathf.Abs(animator.speed - s) < 1e-4f) animator.speed = s * rate;
        }

        void LateUpdate()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            weight = Mathf.MoveTowards(weight, InLocomotion ? 1f : 0f, dt * 10f);
            if (watch != null && !watch.isVisible) return;
            // un hueso que el Animator no escribió este frame (cullado, sin curva) vuelve a su pose antes de sumar
            Restore(lower); Restore(upper); Restore(head); Restore(shoulderL); Restore(shoulderR);
            Flourish();
            if (weight <= 0.001f) return;

            var root = enemy.transform;
            Vector3 right = root.right, fwd = root.forward;
            float t = Time.time + phase;
            float still = 1f - Speed01;
            float breathe = Mathf.Sin(t * flavor.breatheHz * 2f * Mathf.PI) * flavor.breathe * 0.5f * (0.4f + 0.6f * still);
            float sway = flavor.sway * (0.5f + 0.5f * still);
            float w = flavor.swayHz * 2f * Mathf.PI;
            float lean = flavor.lean * weight;

            // inclinación repartida en la columna (40 % abajo, 60 % arriba; el sumo tiene un solo hueso)
            float lowerShare = lower != null ? 0.4f : 0f;
            Rotate(lower, right, lean * lowerShare, fwd, Mathf.Sin(t * w) * sway * weight);
            Rotate(upper, right, lean * (1f - lowerShare) + breathe * weight, fwd, Mathf.Sin(t * w - 0.8f) * sway * 0.6f * weight);
            Rotate(shoulderL, right, flavor.hunch * weight, fwd, 0f);
            Rotate(shoulderR, right, flavor.hunch * weight, fwd, 0f);

            // la cabeza compensa la inclinación (sigue mirando a Kaito), cierra la ola del lago y busca en el bambú
            if (flavor.scan > 0f && Time.time >= nextScan)
            {
                scanTarget = still > 0.6f && Random.value < 0.7f ? Random.Range(-flavor.scan, flavor.scan) : 0f;
                nextScan = Time.time + flavor.scanEvery * Random.Range(0.6f, 1.4f);
            }
            scanYaw = Mathf.MoveTowards(scanYaw, scanTarget * still, dt * 260f);     // un giro seco, no un paneo
            if (head != null && head.t != null)
            {
                head.t.rotation = Quaternion.AngleAxis(scanYaw * weight, Vector3.up)
                                * Quaternion.AngleAxis(flavor.headPitch * weight - breathe * 0.5f * weight, right)
                                * Quaternion.AngleAxis(-Mathf.Sin(t * w - 1.6f) * sway * 0.5f * weight, fwd)
                                * head.t.rotation;
                Mark(head);
            }
        }

        /// <summary>Los golpes de zona en el cuerpo entero (sin clips nuevos), atados a Enemy.Timeline.</summary>
        void Flourish()
        {
            var a = enemy.IsAlive && enemy.State == EnemyState.Attack ? enemy.CurrentAttack : null;
            if (a == null)
            {
                if (moved) { transform.localPosition = basePos; transform.localRotation = baseRot; moved = false; }
                return;
            }
            var tl = enemy.Timeline;
            float t = enemy.StepClock, T = tl.T;
            bool struck = lastClock < T && t >= T;
            lastClock = t;
            float lift = 0f, yaw = 0f;
            switch (a.name)
            {
                case "Salto":
                    // en el aire desde que arranca la embestida hasta que cae con el golpe (1.2 m de alto)
                    lift = 1.2f * Mathf.Sin(Mathf.PI * Mathf.Clamp01((t - (T - 0.42f)) / 0.47f));
                    if (struck) Game.FX?.Dust(enemy.transform.position, 1.1f);
                    break;
                case "Repliegue":
                case "Finta":
                {
                    // en el aire mientras recorre el salto (Enemy lo mueve entre activeStart y activeEnd del clip)
                    float k = Mathf.InverseLerp(a.activeStart, a.activeEnd, tl.NormAt(t));
                    lift = (a.name == "Finta" ? 0.45f : 0.7f) * Mathf.Sin(Mathf.PI * k);
                    break;
                }
                case "Remolino":
                {
                    // un giro entero desde la suelta hasta un poco después del golpe (pega en 360°)
                    float k = Mathf.Clamp01((t - tl.ReleaseTime) / Mathf.Max(0.05f, T - tl.ReleaseTime + 0.22f));
                    yaw = 360f * k * k * (3f - 2f * k);
                    if (struck) Game.FX?.Splash(enemy.transform.position + Vector3.up * 0.6f);
                    break;
                }
                case "Rompeguardia":
                    // se echa atrás con la espada arriba durante la carga y cae con todo el peso al soltar
                    if (upper != null)
                    {
                        float back = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(t / Mathf.Max(0.05f, tl.ReleaseTime)));
                        float fwd = Mathf.Clamp01((t - tl.ReleaseTime) / Mathf.Max(0.02f, T - tl.ReleaseTime));
                        float rec = Mathf.Clamp01((t - T - 0.15f) / 0.3f);
                        float pitch = Mathf.Lerp(Mathf.Lerp(-16f * back, 18f, fwd * fwd), 0f, rec);
                        Rotate(upper, enemy.transform.right, pitch, enemy.transform.forward, 0f);
                    }
                    if (struck) Game.FX?.Dust(enemy.transform.position + enemy.transform.forward * 1.2f, 0.9f);
                    break;
                case "Morote":
                    if (struck) Game.FX?.Splash(enemy.transform.position + enemy.transform.forward * 1.6f * enemy.config.scale + Vector3.up);
                    break;
                case "Shiko D":
                case "Shiko I":
                    // el shiko de la montaña levanta nieve (el del Ōzeki ya tiene su onda)
                    if (struck && flavor == MotionFlavor.Mountain) Game.FX?.SmokePuff(enemy.transform.position + enemy.transform.forward * 1.3f, 2.2f);
                    break;
            }
            if (lift > 0.001f || Mathf.Abs(yaw) > 0.01f || moved)
            {
                transform.localPosition = basePos + Vector3.up * (lift / Mathf.Max(0.01f, transform.parent != null ? transform.parent.lossyScale.y : 1f));
                transform.localRotation = baseRot * Quaternion.Euler(0f, yaw, 0f);
                moved = lift > 0.001f || Mathf.Abs(yaw) > 0.01f;
            }
        }

        static void Restore(Bone b)
        {
            if (b == null || b.t == null) return;
            if (b.has && b.t.localRotation == b.written) b.t.localRotation = b.animated;
            b.animated = b.t.localRotation;
        }

        static void Mark(Bone b)
        {
            b.written = b.t.localRotation;
            b.has = true;
        }

        static void Rotate(Bone b, Vector3 pitchAxis, float pitch, Vector3 rollAxis, float roll)
        {
            if (b == null || b.t == null) return;
            b.t.rotation = Quaternion.AngleAxis(pitch, pitchAxis) * Quaternion.AngleAxis(roll, rollAxis) * b.t.rotation;
            Mark(b);
        }
    }
}
