using System;
using UnityEngine;

namespace Nindo
{
    /// <summary>Un patrón = secuencia de golpes que el enemigo encadena (combo).</summary>
    [Serializable]
    public class AttackPattern
    {
        public string name = "Combo";
        public AttackDef[] steps;
        public float weight = 1f;
        public float minRange = 0f;
        public float maxRange = 3f;
        public float cooldown = 0f;
        [Tooltip("Fase mínima del jefe para usar este patrón (0 = siempre)")] public int minPhase = 0;
        [Tooltip("Al terminar queda agotado/mareado (p. ej. después del giro de Gorō)")] public bool exhaustAfter = false;
        [NonSerialized] public float lastUsed = -99f;
    }

    /// <summary>
    /// Datos de un tipo de enemigo. Las presets viven en EnemyArchetypes.cs; se pueden
    /// ajustar en el inspector del Enemy en Play mode.
    /// </summary>
    [Serializable]
    public class EnemyConfig
    {
        public string id = "ninja";
        public string displayName = "Ninja del Clan";
        public float maxHealth = 60f;
        public float walkSpeed = 2.2f;
        public float runSpeed = 5.2f;
        public float turnSpeed = 10f;
        public float radius = 0.45f;
        public float height = 1.7f;
        [Tooltip("Escala visual del modelo")] public float scale = 1f;
        public Color tint = Color.white;
        [Range(0, 1)] public float tintStrength = 0f;

        [Header("Percepción")]
        public float detectRadius = 10f;
        public float loseRadius = 26f;
        public float preferredDistance = 3.6f;

        [Header("Ritmo de combate")]
        [Tooltip("Pausa entre combos (s)")] public Vector2 attackCooldown = new Vector2(0.6f, 1.6f);
        public int maxImbalance = 3;
        [Tooltip("Tiempo agotado tras un combo con desequilibrio (s)")] public float exhaustedTime = 3.2f;
        [Tooltip("Daño extra al estar agotado")] public float exhaustedDamageMul = 1.3f;
        [Tooltip("Tiempo en guardia tras un combo sin desequilibrio (s)")] public float guardTime = 1.4f;
        [Tooltip("Golpes seguidos que aguanta en neutral antes de cubrirse")] public int poiseHits = 2;
        [Tooltip("No se interrumpe al recibir golpes mientras ataca")] public bool hyperArmor = false;
        public float knockbackResist = 0f;
        public float staggerTime = 0.32f;
        public float parriedRecoil = 0.32f;
        [Range(0, 1)] public float finisherHealth = 0.25f;

        [Header("Animación (nombres de estado del Animator)")]
        public string animLocomotion = "Locomotion";
        public string animHit = "Hit";
        public string animExhausted = "Exhausted";
        public string animGuard = "Guard";
        public string animCounter = "Counter";
        public string animSpotted = "Spotted";
        public string animDeath = "Death";
        public string animParried = "Hit";

        [Header("Ataques")]
        public AttackPattern[] patterns;

        [Header("Recompensa")]
        public float spiritReward = 0f;

        public EnemyConfig Clone()
        {
            var c = (EnemyConfig)MemberwiseClone();
            if (patterns != null)
            {
                c.patterns = new AttackPattern[patterns.Length];
                for (int i = 0; i < patterns.Length; i++)
                {
                    var p = patterns[i];
                    var np = new AttackPattern { name = p.name, weight = p.weight, minRange = p.minRange, maxRange = p.maxRange, cooldown = p.cooldown, minPhase = p.minPhase, exhaustAfter = p.exhaustAfter };
                    np.steps = new AttackDef[p.steps.Length];
                    for (int s = 0; s < p.steps.Length; s++) np.steps[s] = p.steps[s].Clone();
                    c.patterns[i] = np;
                }
            }
            return c;
        }
    }
}
