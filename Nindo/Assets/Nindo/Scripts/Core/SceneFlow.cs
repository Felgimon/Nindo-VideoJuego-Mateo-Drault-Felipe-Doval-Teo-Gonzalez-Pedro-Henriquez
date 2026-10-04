using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Nindo
{
    /// <summary>Carga de escenas (menú ↔ juego) con fundido.</summary>
    public static class SceneFlow
    {
        public const string MenuScene = "Menu";
        public const string GameScene = "Nindo";

        /// <summary>true = partida nueva, false = continuar.</summary>
        public static bool NewGameRequested { get; private set; } = true;
        /// <summary>false si se le dio Play directo a la escena de juego desde el editor.</summary>
        public static bool CameFromMenu { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() { CameFromMenu = false; NewGameRequested = true; }

        public static void StartGame(bool newGame)
        {
            NewGameRequested = newGame;
            CameFromMenu = true;
            if (newGame) SaveSystem.NewGame(); else SaveSystem.Load();
            Load(GameScene);
        }

        public static void LoadMenu()
        {
            SaveSystem.Save();
            Load(MenuScene);
        }

        static void Load(string scene)
        {
            Time.timeScale = 1f;
            Game.IsPaused = false;
            Game.InCutscene = false;
            var runner = Game.Audio != null ? (MonoBehaviour)Game.Audio : null;
            if (runner != null) runner.StartCoroutine(LoadRoutine(scene));
            else SceneManager.LoadScene(scene);
        }

        static IEnumerator LoadRoutine(string scene)
        {
            if (Game.UI != null) yield return Game.UI.Fade(1f, 0.6f);
            SceneManager.LoadScene(scene);
        }
    }
}
