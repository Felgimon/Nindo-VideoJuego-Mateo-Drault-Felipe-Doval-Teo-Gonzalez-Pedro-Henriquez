using System;
using UnityEngine;

namespace Nindo
{
    public enum Faction { Player, Enemy }

    public enum HitResult
    {
        Ignored,     // no aplica (muerto, invulnerable, misma facción)
        Hit,         // recibió daño
        Parried,     // el defensor desvió el golpe (parry)
        PerfectParry,
        Guarded,     // el enemigo estaba en guardia y contraatacó
        Dodged,      // i-frames del dash
        Killed
    }

    public enum AttackKind { Light, Heavy, Unblockable, Ability, Finisher, Projectile }

    /// <summary>Todo lo que hace falta saber de un golpe.</summary>
    public struct DamageInfo
    {
        public float damage;
        public float imbalance;        // cuánto desequilibrio agrega/quita
        public AttackKind kind;
        public Vector3 point;
        public Vector3 direction;      // dirección del golpe (de atacante a víctima)
        public float knockback;        // metros
        public Faction sourceFaction;
        public Component source;       // PlayerController / Enemy
        public string attackName;

        public bool CanBeParried => kind != AttackKind.Unblockable && kind != AttackKind.Finisher;
    }

    /// <summary>Cualquier cosa que pueda recibir golpes.</summary>
    public interface IHittable
    {
        Faction Faction { get; }
        bool IsAlive { get; }
        Transform Root { get; }
        float Radius { get; }
        HitResult ReceiveHit(in DamageInfo info);
    }

    /// <summary>
    /// Definición de un ataque. Los tiempos son normalizados respecto del clip (0..1).
    /// La curva "timing" re-timea la animación en runtime: valores &lt; 1 = anticipación lenta,
    /// &gt; 1 = golpe rápido. Así las animaciones de Blender ganan "peso" sin re-exportarlas.
    /// </summary>
    [Serializable]
    public class AttackDef
    {
        public string name = "Attack";
        public string state = "Attack1";       // estado del Animator
        public float damage = 10f;
        public float imbalance = 1f;
        public AttackKind kind = AttackKind.Light;
        [Tooltip("Alcance del arco de golpe (m)")] public float range = 2.2f;
        [Tooltip("Ángulo total del arco (grados)")] public float arc = 140f;
        [Range(0, 1)] public float activeStart = 0.25f;
        [Range(0, 1)] public float activeEnd = 0.55f;
        [Tooltip("Desde acá se puede encadenar el siguiente ataque")] [Range(0, 1)] public float comboWindow = 0.45f;
        [Tooltip("Desde acá se puede cancelar con dash/parry")] [Range(0, 1)] public float cancelWindow = 0.6f;
        [Tooltip("Avance durante el golpe (m)")] public float lunge = 0.8f;
        [Range(0, 1)] public float lungeStart = 0.1f;
        [Range(0, 1)] public float lungeEnd = 0.4f;
        public float knockback = 0.6f;
        public float hitStop = 0.07f;
        public float shake = 0.25f;
        public float speed = 1f;
        public AnimationCurve timing;
        [Tooltip("Para enemigos: duración del aviso antes del golpe (s, extra)")] public float telegraph = 0f;
        public string sfx = "swing";
        public string hitSfx = "hit";
        [Tooltip("Movimiento especial de jefe: spin, slam, wave, charge, teleport, summon, clones, windslash")]
        public string special = "";
        public float specialParam = 0f;
        [Tooltip("El atacante sigue girando hacia el objetivo durante la anticipación")] public bool tracking = true;

        public float Timing(float n) => timing != null && timing.length > 1 ? Mathf.Max(0.05f, timing.Evaluate(n)) : 1f;

        public AttackDef Clone() => (AttackDef)MemberwiseClone();

        /// <summary>Curva típica: anticipación lenta, impacto rápido, recuperación normal.</summary>
        public static AnimationCurve Snappy(float windup = 0.75f, float strike = 1.6f, float strikeAt = 0.3f, float recover = 1.05f)
        {
            return new AnimationCurve(
                new Keyframe(0f, windup),
                new Keyframe(Mathf.Max(0.05f, strikeAt - 0.12f), windup),
                new Keyframe(strikeAt, strike),
                new Keyframe(Mathf.Min(0.95f, strikeAt + 0.2f), recover),
                new Keyframe(1f, recover));
        }
    }

    public static class CombatMath
    {
        public static Vector3 Flat(this Vector3 v) { v.y = 0f; return v; }

        public static float FlatDistance(Vector3 a, Vector3 b)
        {
            a.y = 0; b.y = 0; return Vector3.Distance(a, b);
        }

        /// <summary>¿Está 'target' dentro del arco frontal de 'from'?</summary>
        public static bool InArc(Transform from, Vector3 target, float range, float arcDeg, float targetRadius = 0f)
        {
            Vector3 d = (target - from.position).Flat();
            float dist = d.magnitude - targetRadius;
            if (dist > range) return false;
            if (d.sqrMagnitude < 0.01f) return true;
            return Vector3.Angle(from.forward.Flat(), d) <= arcDeg * 0.5f;
        }

        public static float Damp(float a, float b, float lambda, float dt) => Mathf.Lerp(a, b, 1f - Mathf.Exp(-lambda * dt));
        public static Vector3 Damp(Vector3 a, Vector3 b, float lambda, float dt) => Vector3.Lerp(a, b, 1f - Mathf.Exp(-lambda * dt));
        public static Quaternion Damp(Quaternion a, Quaternion b, float lambda, float dt) => Quaternion.Slerp(a, b, 1f - Mathf.Exp(-lambda * dt));
    }
}
