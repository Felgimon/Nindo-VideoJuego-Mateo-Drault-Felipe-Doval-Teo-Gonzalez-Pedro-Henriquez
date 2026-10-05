using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Luz suave y fría sobre Kaito ("luz de luna"): de noche los ninjas de negro se leían como agujeros
    /// sobre el suelo oscuro. Explorando es apenas un relleno; en combate sube para que se vean las
    /// siluetas y los movimientos de quienes lo rodean. Sin sombras (barata en Forward+).
    /// </summary>
    [RequireComponent(typeof(Light))]
    public class MoonLantern : MonoBehaviour
    {
        public float exploreIntensity = 1.1f;
        public float combatIntensity = 1.7f;
        public float exploreRange = 9f;
        public float combatRange = 11f;
        Light l;

        void Awake() => l = GetComponent<Light>();

        void LateUpdate()
        {
            bool combat = Game.Combat != null && Game.Combat.InCombat;
            float dt = Time.unscaledDeltaTime;
            l.intensity = Mathf.MoveTowards(l.intensity, combat ? combatIntensity : exploreIntensity, dt * 1.2f);
            l.range = Mathf.MoveTowards(l.range, combat ? combatRange : exploreRange, dt * 3f);
            l.enabled = !Game.InCutscene || l.intensity > 0.01f;
        }
    }
}
