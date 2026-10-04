using UnityEngine;

namespace Nindo
{
    /// <summary>
    /// Punto de acceso central a los sistemas del juego (service locator liviano).
    /// Cada sistema se registra a sí mismo en Awake; nadie usa FindObjectOfType en Update.
    /// </summary>
    public static class Game
    {
        public static NindoContent Content { get; internal set; }
        public static PlayerController Player { get; internal set; }
        public static CameraDirector Camera { get; internal set; }
        public static TimeController Time { get; internal set; }
        public static AudioManager Audio { get; internal set; }
        public static UIManager UI { get; internal set; }
        public static FXManager FX { get; internal set; }
        public static CombatDirector Combat { get; internal set; }
        public static StoryDirector Story { get; internal set; }
        public static WorldBuilder World { get; internal set; }
        public static InputReader Input { get; internal set; }

        /// <summary>Progreso persistente (llaves, flags, checkpoint).</summary>
        public static SaveData Save => SaveSystem.Data;

        public static bool IsPaused { get; internal set; }

        /// <summary>True durante cinemáticas: el jugador no recibe input de combate.</summary>
        public static bool InCutscene { get; internal set; }

        public static NindoContent LoadContent()
        {
            if (Content == null)
                Content = Resources.Load<NindoContent>("NindoContent");
            if (Content == null)
            {
                Debug.LogWarning("[Nindo] No se encontró Resources/NindoContent.asset. Se crea uno vacío (el juego usará fallbacks).");
                Content = ScriptableObject.CreateInstance<NindoContent>();
            }
            return Content;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            // Necesario con "Enter Play Mode Options" (domain reload desactivado).
            Content = null; Player = null; Camera = null; Time = null; Audio = null; UI = null;
            FX = null; Combat = null; Story = null; World = null; Input = null;
            IsPaused = false; InCutscene = false;
            GameEvents.Clear();
        }
    }
}
