using System;
using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Todos los valores ajustables de Kaito. Los defaults están pensados para que el combate
    /// sea rápido pero legible. Se pueden editar en el inspector del PlayerController en Play.
    /// </summary>
    [Serializable]
    public class PlayerConfig
    {
        [Header("Movimiento")]
        public float runSpeed = 6.2f;
        public float acceleration = 40f;
        public float turnSpeed = 18f;
        public float gravity = -28f;

        [Header("Vida / Espíritu / Furia")]
        public float maxHealth = 100f;
        public float maxSpirit = 100f;
        public float startSpirit = 40f;
        public float maxRage = 100f;
        public float healOnKill = 8f;
        public float healOnFinisher = 25f;
        public float spiritOnHit = 3f;
        public float spiritOnParry = 12f;
        public float spiritOnPerfectParry = 18f;
        public float spiritOnKill = 8f;
        public float rageOnHit = 4f;
        public float rageOnParry = 14f;
        public float rageOnPerfectParry = 20f;
        public float rageLossOnDamage = 40f;
        [Tooltip("Duración de 'Filo de Ira' con la barra llena (s)")] public float rageDuration = 9f;
        public float rageExtendOnHit = 0.6f;
        public float rageDamageMul = 1.45f;
        public float rageSpeedMul = 1.12f;

        [Header("Combo")]
        public AttackDef[] combo =
        {
            // temblor de los cortes livianos 0.18 → 0.28: con la cámara a 20+ m casi no se sentían
            // ventanas = cuadros de los clips de Tools/Blender/anim/kaito (kaitooo.fbx.json, "normalized"): el Corte 1
            // pega en f4/13, el 2 en f3/11 y el final en f7/20 al caer del salto; se encadena cuando la pose ya llegó a
            // la de empalme. El avance (lunge) es el que el clip descuenta de los pies, que van EN EL AIRE mientras avanza
            // (el imán puede cortarlo contra un enemigo pegado sin que patinen): cambiar el tramo los hace patinar
            new AttackDef { name = "Corte 1", state = "Attack1", damage = 10, imbalance = 1, range = 2.3f, arc = 150, activeStart = 0.308f, activeEnd = 0.538f, comboWindow = 0.538f, cancelWindow = 0.55f, lunge = 0.9f, lungeStart = 0.154f, lungeEnd = 0.385f, knockback = 0.35f, hitStop = 0.06f, shake = 0.28f, speed = 1.0f },
            new AttackDef { name = "Corte 2", state = "Attack2", damage = 11, imbalance = 1, range = 2.3f, arc = 150, activeStart = 0.273f, activeEnd = 0.545f, comboWindow = 0.545f, cancelWindow = 0.55f, lunge = 1.0f, lungeStart = 0.091f, lungeEnd = 0.364f, knockback = 0.4f, hitStop = 0.06f, shake = 0.3f, speed = 1.0f },
            new AttackDef { name = "Corte final", state = "Attack3", damage = 18, imbalance = 1.5f, kind = AttackKind.Heavy, range = 2.6f, arc = 200, activeStart = 0.35f, activeEnd = 0.5f, comboWindow = 0.95f, cancelWindow = 0.6f, lunge = 1.6f, lungeStart = 0.15f, lungeEnd = 0.35f, knockback = 1.6f, hitStop = 0.11f, shake = 0.45f, speed = 0.95f },
        };
        [Tooltip("Tiempo extra para encadenar después de que termina un golpe")] public float comboGrace = 0.25f;
        [Tooltip("Desde acá del último corte se puede volver a empezar el combo (con buffer de 0.3 s)")] [Range(0, 1)] public float comboRestart = 0.85f;
        [Tooltip("Parte de la velocidad de carrera que se conserva al atacar (se suma al avance del corte)")] [Range(0, 1)] public float attackMomentum = 0.35f;
        public float attackMagnetRange = 4.5f;
        public float attackMagnetAngle = 85f;

        [Header("Parry")]
        [Tooltip("Ventana total del parry (s)")] public float parryWindow = 0.24f;
        [Tooltip("Primeros segundos de la ventana que cuentan como parry PERFECTO")] public float perfectWindow = 0.11f;
        [Tooltip("Penalidad si se spamea el parry sin que viniera nada (multiplica la ventana)")] public float spamPenalty = 0.75f;
        [Tooltip("Cuánto dura la penalidad después de un parry al aire (s)")] public float spamDecay = 0.35f;
        [Tooltip("Cuánto se recuerda una pulsación de parry/dash mientras Kaito está ocupado (s)")] public float defenseBuffer = 0.2f;
        public float parryRecover = 0.28f;
        [Tooltip("Golpe que llega apenas cerrada la ventana: guardia imperfecta (s después del cierre)")] public float imperfectGuardTime = 0.15f;
        [Tooltip("Daño que pasa en la guardia imperfecta (fracción)")] [Range(0, 1)] public float imperfectGuardDamage = 0.35f;
        [Tooltip("Desequilibrio que igual le suma al enemigo")] public float imperfectGuardImbalance = 0.34f;
        public float riposteWindow = 0.7f;
        public float riposteDamageMul = 1.5f;
        [Tooltip("El contraataque arranca el Corte 1 en su carga (f2/13): los desvíos terminan en esa pose")] public float riposteStartNorm = 0.154f;

        [Header("Dash mágico")]
        public float dashCost = 15f;
        public float dashDistance = 6.5f;
        public float dashDuration = 0.26f;
        public float dashIFrameStart = 0.02f;
        public float dashIFrameEnd = 0.24f;
        public float dashRecover = 0.08f;
        public float perfectDodgeWindow = 0.16f;
        [Tooltip("Sin Espíritu: dash 'cansado' (mismos i-frames, más corto, con espera)")] public float tiredDashDistance = 4.5f;
        public float tiredDashCooldown = 1.2f;

        [Header("Finisher")]
        public float finisherCost = 30f;
        public float finisherRange = 3.6f;
        [Range(0, 1)] public float finisherHealthThreshold = 0.25f;

        [Header("Habilidades del Espíritu de la Bandana")]
        public float windSlashCost = 35f;
        public float windSlashDistance = 9f;
        public float windSlashDamage = 32f;
        public float whirlwindCost = 30f;
        public float whirlwindRadius = 4.2f;
        public float whirlwindDamage = 16f;

        [Header("Daño recibido")]
        public float hurtTime = 0.38f;
        public float heavyHurtTime = 0.65f;
        public float invulnAfterHit = 0.7f;
        public float lockRange = 15f;
    }
}
